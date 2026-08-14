#!/usr/bin/env python3
"""OCR a work directory's source.pdf with Mistral OCR.

Reads {work_dir}/source.pdf and writes, under {work_dir}/ocr/:

    page_NN.md   one markdown file per page, the OCR's structural reading
    images.json  per page, the image bounding boxes the OCR reported and
                 the page dimensions they are measured in
    meta.json    model, usage, and cost for the run

The OCR is the structural witness: headings, tables, equations, reading
order. Its characters are plausible but fallible, and nothing here checks
them against the text layer; downstream stages adjudicate. The image
bounding boxes seed the figure crop proposals.

The key arrives as MISTRAL_API_KEY, read from the environment first and
then from the .env file at the repository root. Without it the http
transport fails before anything is read or sent. --transport fake needs
no key and no network: it answers with a response of the same shape,
deriving page markdown from the PDF's own text layer and image boxes from
the PDF's image blocks, so the rest of the route can be exercised
offline.

The whole response is written or none of it: a reply that does not cover
every page is refused, so a partial witness can never pass for a full
one.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pymupdf

from alteksto import __version__
from alteksto.env import read_var
from alteksto.workdir import open_source_pdf

MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"
DEFAULT_MODEL = "mistral-ocr-latest"
API_KEY_VAR = "MISTRAL_API_KEY"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
USER_AGENT = f"alteksto/{__version__}"

# Price in US dollars per thousand pages, read from Mistral's pricing page
# on the date below. It moves, and nothing here re-checks it, so every
# cost figure this tool writes carries the date with it.
USD_PER_1000_PAGES = 1.0
PRICES_AS_OF = "2026-08-13"

# One retry, on the failures a second attempt can plausibly clear.
MAX_RETRIES = 1
RETRY_BACKOFF_SECONDS = 5.0
MAX_RETRY_AFTER_SECONDS = 60.0

# The bounding-box fields of one OCR image record, kept in this order in
# images.json.
IMAGE_FIELDS = ("id", "top_left_x", "top_left_y",
                "bottom_right_x", "bottom_right_y")


class OcrCallError(RuntimeError):
    """One OCR call that failed, carrying whatever the server said."""

    def __init__(self, message: str, *, status: int | None = None,
                 retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _retryable(status: int | None) -> bool:
    """Rate limiting, a server-side fault, or no reply at all."""
    return status is None or status == 429 or 500 <= status < 600


def _retry_after(headers) -> float | None:
    try:
        seconds = float(headers.get("Retry-After", ""))
    except (TypeError, ValueError):
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


def _post_ocr(payload: dict, api_key: str, timeout: float) -> dict:
    request = Request(
        MISTRAL_OCR_URL, data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}",
                 "User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail = ""
        raise OcrCallError(f"HTTP {exc.code} {detail}".strip(),
                           status=exc.code,
                           retry_after=_retry_after(exc.headers)) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise OcrCallError(f"no reply ({exc!r})") from exc
    except json.JSONDecodeError as exc:
        raise OcrCallError(f"unreadable reply ({exc})") from exc


def ocr_http(pdf_bytes: bytes, *, model: str, api_key: str,
             timeout: float) -> dict:
    """The whole PDF through the OCR endpoint, with one retry."""
    payload = {
        "model": model,
        "document": {
            "type": "document_url",
            "document_url": ("data:application/pdf;base64,"
                             + base64.b64encode(pdf_bytes).decode("ascii")),
        },
        "include_image_base64": False,
    }
    attempt = 0
    while True:
        attempt += 1
        try:
            return _post_ocr(payload, api_key, timeout)
        except OcrCallError as exc:
            if attempt > MAX_RETRIES or not _retryable(exc.status):
                raise
            delay = exc.retry_after or RETRY_BACKOFF_SECONDS
            print(f"ocr: retrying in {delay:.0f}s after {exc}",
                  file=sys.stderr)
            time.sleep(delay)


def ocr_fake(doc: pymupdf.Document) -> dict:
    """A response of the API's shape, answered locally from the PDF.

    A stand-in, not a simulation: the markdown is the raw text layer, not
    a structural reading, and the image boxes are the PDF's own image
    blocks in PDF points (so dimensions carry dpi 72). Enough to exercise
    every consumer of the output offline.
    """
    pages = []
    for number in range(1, len(doc) + 1):
        page = doc.load_page(number - 1)
        images = []
        for index, info in enumerate(page.get_image_info()):
            x0, y0, x1, y1 = info["bbox"]
            images.append({
                "id": f"img-p{number}-{index}.png",
                "top_left_x": int(x0), "top_left_y": int(y0),
                "bottom_right_x": int(x1), "bottom_right_y": int(y1),
            })
        pages.append({
            "index": number - 1,
            "markdown": page.get_text().strip(),
            "images": images,
            "dimensions": {"dpi": 72, "width": int(page.rect.width),
                           "height": int(page.rect.height)},
        })
    return {
        "pages": pages,
        "model": "fake",
        "usage_info": {"pages_processed": len(pages),
                       "doc_size_bytes": None},
    }


def write_outputs(ocr_dir: Path, response: dict, *, transport: str,
                  requested_model: str, page_count: int,
                  wall_seconds: float) -> dict:
    """Write page_NN.md, images.json, and meta.json; return the meta.

    Raises ValueError, before writing anything, when the response does not
    cover exactly the PDF's pages.
    """
    pages = response.get("pages") or []
    got = sorted(page.get("index") for page in pages)
    expected = list(range(page_count))
    if got != expected:
        raise ValueError(
            f"the OCR reply covers page indexes {got}, the PDF has "
            f"{expected}: refusing to write a partial witness")

    ocr_dir.mkdir(parents=True, exist_ok=True)
    for old in ocr_dir.glob("page_*.md"):
        old.unlink()
    image_pages = []
    for page in sorted(pages, key=lambda page: page["index"]):
        number = page["index"] + 1
        markdown = (page.get("markdown") or "").rstrip()
        (ocr_dir / f"page_{number:02d}.md").write_text(
            markdown + "\n", encoding="utf-8")
        image_pages.append({
            "page": number,
            "dimensions": page.get("dimensions"),
            "images": [{field: image.get(field) for field in IMAGE_FIELDS}
                       for image in page.get("images") or []],
        })
    (ocr_dir / "images.json").write_text(
        json.dumps({"pages": image_pages}, indent=2, ensure_ascii=False)
        + "\n", encoding="utf-8")

    usage = response.get("usage_info") or {}
    processed = int(usage.get("pages_processed") or 0)
    meta = {
        "model": response.get("model") or requested_model,
        "transport": transport,
        "endpoint": MISTRAL_OCR_URL if transport == "http" else None,
        "pages": page_count,
        "wall_seconds": wall_seconds,
        "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "usage": {"pages_processed": processed,
                  "doc_size_bytes": usage.get("doc_size_bytes")},
        "cost_estimate": {
            "total_usd": round(processed / 1000 * USD_PER_1000_PAGES, 6),
            "usd_per_1000_pages": USD_PER_1000_PAGES,
            "prices_as_of": PRICES_AS_OF,
        },
    }
    (ocr_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return meta


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ocr.py",
        description="OCR {work_dir}/source.pdf into {work_dir}/ocr/ "
                    "(per-page markdown, image bboxes, usage and cost).",
    )
    parser.add_argument("work_dir", type=Path,
                        help="the paper's work directory, holding source.pdf")
    parser.add_argument("--transport", choices=("http", "fake"),
                        default="http",
                        help="fake answers locally from the PDF, offline "
                             "and free")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"OCR model id (default {DEFAULT_MODEL})")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="request timeout in seconds (default 300)")
    args = parser.parse_args(argv)

    api_key = None
    if args.transport == "http":
        api_key = read_var(API_KEY_VAR, ENV_FILE)
        if not api_key:
            print(f"ocr: {API_KEY_VAR} is not set, in the environment or in "
                  f"{ENV_FILE}; the http transport sends nothing without it",
                  file=sys.stderr)
            return 1

    try:
        doc = open_source_pdf(args.work_dir)
    except ValueError as exc:
        print(f"ocr: {exc}", file=sys.stderr)
        return 1
    started = time.monotonic()
    try:
        page_count = len(doc)
        if args.transport == "fake":
            response = ocr_fake(doc)
        else:
            pdf_bytes = (args.work_dir / "source.pdf").read_bytes()
            try:
                response = ocr_http(pdf_bytes, model=args.model,
                                    api_key=api_key, timeout=args.timeout)
            except OcrCallError as exc:
                print(f"ocr: the OCR call failed: {exc}", file=sys.stderr)
                return 1
    finally:
        doc.close()

    try:
        meta = write_outputs(args.work_dir / "ocr", response,
                             transport=args.transport,
                             requested_model=args.model,
                             page_count=page_count,
                             wall_seconds=round(
                                 time.monotonic() - started, 2))
    except ValueError as exc:
        print(f"ocr: {exc}", file=sys.stderr)
        return 1

    cost = meta["cost_estimate"]["total_usd"]
    print(f"ocr: {page_count} pages via {args.transport}, ${cost:.4f} "
          f"estimated at {PRICES_AS_OF} prices -> {args.work_dir / 'ocr'}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
