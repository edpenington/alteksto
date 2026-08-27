"""What the page tools share: the work directory contract and page markers.

A work directory holds one paper's intermediates and is named by the
paper's id: {work_dir}/source.pdf is the input every tool starts from.
Nothing here creates a work directory; acquiring the PDF is the caller's
job.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

# Render resolution bounds, shared by every stage that rasterises a page so
# they cannot drift apart on it.
MIN_DPI, MAX_DPI = 1, 1200


def dpi_error(dpi) -> str | None:
    """A message describing why dpi is unusable, or None if it is fine.

    A negative dpi is a negative zoom, and a negative zoom is a point
    reflection rather than a scale, so it silently turns the output through
    180 degrees and reports success. Zero and the very large values make
    PyMuPDF raise from inside the render, which reaches the operator as an
    opaque pixmap error rather than a statement about the argument they
    gave.
    """
    if isinstance(dpi, bool) or not isinstance(dpi, int):
        return f"--dpi must be an integer, got {dpi!r}"
    if not (MIN_DPI <= dpi <= MAX_DPI):
        return f"--dpi must be from {MIN_DPI} to {MAX_DPI}, got {dpi}"
    return None


# The page marker line. The flattened block dump carries it, and the walk
# reads it back to slice a witness to a page range mechanically.
PAGE_MARKER = "<!-- page {page} -->"
PAGE_MARKER_RE = re.compile(r"^<!-- page (\d+) -->$")


def page_marker(page: int) -> str:
    return PAGE_MARKER.format(page=page)


def open_source_pdf(work_dir: Path) -> pymupdf.Document:
    """Open {work_dir}/source.pdf, or raise ValueError saying exactly why.

    The caller owns the returned document and closes it. A missing
    directory, a missing PDF, an unreadable PDF, and a PDF with no pages
    are all distinct failures, each naming the path it rejected.
    """
    if not work_dir.is_dir():
        raise ValueError(f"not a work directory: {work_dir}")
    pdf_path = work_dir / "source.pdf"
    if not pdf_path.is_file():
        raise ValueError(f"source PDF missing: {pdf_path}")
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        raise ValueError(f"unreadable PDF {pdf_path}: {exc}") from exc
    if len(doc) < 1:
        doc.close()
        raise ValueError(f"{pdf_path} has no pages")
    return doc
