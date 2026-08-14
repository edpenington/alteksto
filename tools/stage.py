#!/usr/bin/env python3
"""Put a paper PDF where a converter will find it, under the id it already has.

A conversion is named by the paper's id, and that id belongs to whoever
asked for the conversion: a review's registry, a spreadsheet, a Covidence
export. This tool never invents one. It answers the only question the
caller cannot answer alone, which is which downloaded file is which
known paper, and then copies that file to {work}/{id}/source.pdf.

Two modes, and the difference is who decides:

    --id ID --pdf PATH          the caller decides; this tool copies.
    --map-file FILE             the same for many, a JSON object of
                                {"id": "path to pdf"}.
    --from DIR --registry FILE  this tool proposes, by scoring each PDF
                                in DIR against the registry's records.

Scoring is a fixed formula, no model and no randomness:

    score = 100*doi + 50*title_overlap + 10*author_overlap + 5*year

A DOI printed on the page is decisive because it identifies one paper.
Everything else is corroboration. A candidate is CONFIDENT when the DOI
matched, or when the title overlap is high and beats the runner-up by a
clear margin; anything else is AMBIGUOUS, which stages nothing and is
reported for a human. Guessing here is the expensive kind of wrong: a
paper converted under another paper's id is a defect no later stage can
see, because every stage after this one trusts the id.

Only the first few pages are read. A systematic review's registry
describes papers that cite each other, so a reference list is full of
other registry entries' titles and DOIs; front matter is where a paper
states its own identity.

The registry is any JSON this repo did not write: a list of records each
carrying an id, or an object keyed by id. Records are matched on their
title, doi, authors, and year fields when present, and ignored when not.
Use --records to descend into a wrapper key first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pymupdf

# Front matter: where a paper states its own identity, before the
# reference list starts describing everybody else's.
IDENTITY_PAGES = 3

# Score weights. The DOI outruns any combination of the others because it
# is an identifier and they are only corroboration.
DOI_WEIGHT = 100.0
TITLE_WEIGHT = 50.0
AUTHOR_WEIGHT = 10.0
YEAR_WEIGHT = 5.0

# What it takes to stage without asking, absent a DOI: most of the title
# on the page, and daylight between the winner and the runner-up.
TITLE_CONFIDENT = 0.7
MARGIN_CONFIDENT = 15.0

# Content words only. Matching on "the" and "of" makes every paper
# resemble every other paper.
STOP_WORDS = frozenset("""
a an and are as at be by for from in into is it its of on or that the to
with without between among during effect effects study trial randomised
randomized controlled review analysis patients people health care
""".split())

DOI_PREFIXES = ("https://dx.doi.org/", "https://doi.org/",
                "http://dx.doi.org/", "http://doi.org/", "doi:", "doi ")

# The fields a page can confirm. A record carrying none of them names no
# paper, whatever else it holds.
MATCHABLE_FIELDS = ("title", "doi", "authors", "year")


def normalise_doi(raw: str) -> str:
    """A DOI reduced to the part that identifies, lowercase, no spaces."""
    value = (raw or "").strip().lower()
    for prefix in DOI_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return re.sub(r"\s+", "", value)


def content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}


def surnames(raw: str) -> set[str]:
    """Surnames from an authors field, however it punctuates them.

    Handles the common exports: "Surname, A. B.; Other, C." and
    "Surname AB, Other C" and plain "Surname and Other". The surname is
    the first alphabetic run of each author chunk, which is what both
    orders agree on.
    """
    found = set()
    for chunk in re.split(r"[;&]|\band\b", raw or ""):
        match = re.search(r"[A-Za-z][A-Za-z'\-]{2,}", chunk)
        if match:
            found.add(match.group(0).lower())
    return found


def read_identity_text(pdf_path: Path, pages: int = IDENTITY_PAGES) -> str:
    """The text layer of the PDF's first pages, lowercase.

    Raises ValueError naming the file when it cannot be opened or holds
    no pages, because a PDF this tool cannot read is not a PDF it may
    quietly skip.
    """
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        raise ValueError(f"unreadable PDF {pdf_path}: {exc}") from exc
    try:
        if len(doc) < 1:
            raise ValueError(f"{pdf_path} has no pages")
        chunks = [doc[i].get_text() for i in range(min(pages, len(doc)))]
    finally:
        doc.close()
    return "\n".join(chunks).lower()


def is_matchable(record: dict) -> bool:
    """Whether a record says anything a page could confirm.

    A record with no title, DOI, authors, or year identifies no paper.
    The distinction matters because a registry's own wrapper is a
    mapping of mappings like the records are: {"_meta": {...}, "data":
    {...}} reads as two records with the ids `_meta` and `data` unless
    something asks what they claim about a paper.
    """
    return any(str(record.get(field) or "").strip()
               for field in MATCHABLE_FIELDS)


def load_registry(path: Path, records_key: str | None = None) -> list[dict]:
    """The registry as a list of records, each with an id.

    Accepts a list of records carrying an id field, or an object keyed by
    id. The key is the id in the second form: a record's own id-looking
    fields are often a citation label ("Packnett 2019") rather than the
    id the caller files papers under.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"registry not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"registry is not JSON: {path}: {exc}") from exc

    if records_key:
        if not isinstance(data, dict) or records_key not in data:
            raise ValueError(f"registry {path} has no key {records_key!r}")
        data = data[records_key]

    records = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict) and is_matchable(value):
                records.append({**value, "id": str(key)})
    elif isinstance(data, list):
        for value in data:
            if (isinstance(value, dict) and value.get("id") is not None
                    and is_matchable(value)):
                records.append({**value, "id": str(value["id"])})
    if not records:
        raise ValueError(
            f"registry {path} holds no records this tool can match on "
            f"({', '.join(sorted(MATCHABLE_FIELDS))}); pass --records to "
            f"descend into a wrapper key")
    return records


def score_record(record: dict, text: str, flat_text: str) -> tuple[float, list]:
    """How well one registry record matches one PDF, and why.

    Returns the score and the reasons behind it, so an operator reading
    the output can see what matched rather than trusting a number.
    """
    reasons = []
    score = 0.0

    doi = normalise_doi(str(record.get("doi") or ""))
    doi_hit = bool(doi) and doi in flat_text
    if doi_hit:
        score += DOI_WEIGHT
        reasons.append(f"doi {doi}")

    title_words = content_words(str(record.get("title") or ""))
    page_words = content_words(text)
    overlap = 0.0
    if title_words:
        overlap = len(title_words & page_words) / len(title_words)
        score += TITLE_WEIGHT * overlap
        reasons.append(f"title {overlap:.0%}")

    author_names = surnames(str(record.get("authors") or ""))
    if author_names:
        hit = len({n for n in author_names if n in page_words})
        share = hit / len(author_names)
        score += AUTHOR_WEIGHT * share
        reasons.append(f"authors {hit}/{len(author_names)}")

    year = str(record.get("year") or "").strip()
    if year and re.fullmatch(r"\d{4}", year) and year in text:
        score += YEAR_WEIGHT
        reasons.append(f"year {year}")

    return score, (doi_hit, overlap, reasons)


def identify(pdf_path: Path, records: list[dict]) -> dict:
    """The best registry match for one PDF, with a confident/ambiguous verdict."""
    text = read_identity_text(pdf_path)
    flat_text = re.sub(r"\s+", "", text)

    scored = []
    for record in records:
        score, (doi_hit, overlap, reasons) = score_record(record, text,
                                                          flat_text)
        scored.append({"id": record["id"], "score": score, "doi_hit": doi_hit,
                       "title_overlap": overlap, "reasons": reasons,
                       "title": str(record.get("title") or "")})
    scored.sort(key=lambda c: c["score"], reverse=True)

    best = scored[0]
    runner_up = scored[1]["score"] if len(scored) > 1 else 0.0
    margin = best["score"] - runner_up
    confident = bool(best["doi_hit"]) or (
        best["title_overlap"] >= TITLE_CONFIDENT and margin >= MARGIN_CONFIDENT)

    return {"pdf": pdf_path, "best": best, "margin": margin,
            "confident": confident, "runners_up": scored[1:3]}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def stage_one(work_root: Path, paper_id: str, pdf_path: Path) -> str:
    """Copy the PDF to {work_root}/{id}/source.pdf. Returns what it did.

    An id already staged from this very PDF is left alone, so a rerun
    resumes rather than repeats. An id already staged from a different
    PDF is a stop: overwriting it would convert one paper's pages under
    another paper's name, and the id is what every later stage trusts.
    """
    if not pdf_path.is_file():
        raise ValueError(f"no such PDF: {pdf_path}")
    destination = work_root / paper_id / "source.pdf"
    if destination.is_file():
        if sha256(destination) == sha256(pdf_path):
            return "already staged"
        raise ValueError(
            f"{destination} already holds a different PDF; remove the work "
            f"directory to restage id {paper_id}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_path, destination)
    return "staged"


def report(paper_id: str, pdf_path: Path, action: str) -> None:
    """One line per paper on stdout: what a caller reads to spawn from."""
    print(f"{paper_id}\t{pdf_path}\t{action}")


def run_explicit(work_root: Path, pairs: list[tuple[str, Path]]) -> int:
    failures = 0
    for paper_id, pdf_path in pairs:
        try:
            action = stage_one(work_root, paper_id, pdf_path)
        except ValueError as exc:
            print(f"stage: {exc}", file=sys.stderr)
            failures += 1
            continue
        report(paper_id, pdf_path, action)
    if failures:
        print(f"stage: {failures} of {len(pairs)} could not be staged",
              file=sys.stderr)
        return 1
    return 0


def run_registry(work_root: Path, source_dir: Path, registry: Path,
                 records_key: str | None) -> int:
    if not source_dir.is_dir():
        print(f"stage: not a directory: {source_dir}", file=sys.stderr)
        return 1
    try:
        records = load_registry(registry, records_key)
    except ValueError as exc:
        print(f"stage: {exc}", file=sys.stderr)
        return 1

    pdfs = sorted(p for p in source_dir.iterdir()
                  if p.is_file() and p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"stage: no PDFs in {source_dir}", file=sys.stderr)
        return 1

    matches, unresolved, unreadable = [], [], []
    for pdf_path in pdfs:
        try:
            matches.append(identify(pdf_path, records))
        except ValueError as exc:
            print(f"stage: {exc}", file=sys.stderr)
            unreadable.append(pdf_path)

    # Two PDFs claiming one id means at least one of them is wrong, and
    # nothing here can tell which. Neither is staged.
    claimed: dict[str, list] = {}
    for match in matches:
        if match["confident"]:
            claimed.setdefault(match["best"]["id"], []).append(match)
    contested = {i for i, group in claimed.items() if len(group) > 1}

    staged = 0
    failures = 0
    for match in matches:
        best, pdf_path = match["best"], match["pdf"]
        if not match["confident"]:
            unresolved.append(match)
            continue
        if best["id"] in contested:
            unresolved.append(match)
            continue
        try:
            action = stage_one(work_root, best["id"], pdf_path)
        except ValueError as exc:
            print(f"stage: {exc}", file=sys.stderr)
            failures += 1
            continue
        report(best["id"], pdf_path, action)
        staged += 1

    for paper_id in sorted(contested):
        names = ", ".join(m["pdf"].name for m in claimed[paper_id])
        print(f"stage: id {paper_id} claimed by more than one PDF ({names}); "
              f"staged neither", file=sys.stderr)

    for match in unresolved:
        best = match["best"]
        if best["id"] in contested:
            continue
        others = ", ".join(f"{c['id']} ({c['score']:.0f})"
                           for c in match["runners_up"])
        print(f"stage: AMBIGUOUS {match['pdf'].name}: best {best['id']} "
              f"score {best['score']:.0f} [{', '.join(best['reasons'])}], "
              f"margin {match['margin']:.0f}; then {others or 'nothing'}",
              file=sys.stderr)

    print(f"stage: {staged} of {len(pdfs)} staged into {work_root}",
          file=sys.stderr)
    if failures or unreadable:
        return 1
    if unresolved:
        print(f"stage: {len(unresolved)} need a decision before they can be "
              f"staged; confirm the id and restage with --id/--pdf",
              file=sys.stderr)
        return 3
    return 0


def parse_map_file(path: Path) -> list[tuple[str, Path]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"map file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"map file is not JSON: {path}: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise ValueError(f"map file {path} must be a JSON object of id to path")
    return [(str(k), Path(v)) for k, v in data.items()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="stage.py",
        description="Copy paper PDFs to {work}/{id}/source.pdf under the ids "
                    "they already have.",
    )
    parser.add_argument("--work", type=Path, default=Path("work"),
                        help="the work root holding one directory per paper "
                             "(default work)")
    parser.add_argument("--id", help="the paper's id, supplied by the caller")
    parser.add_argument("--pdf", type=Path, help="the PDF to stage under --id")
    parser.add_argument("--map-file", type=Path,
                        help="JSON object of id to PDF path, for many papers")
    parser.add_argument("--from", dest="source_dir", type=Path,
                        help="a directory of PDFs to match against --registry")
    parser.add_argument("--registry", type=Path,
                        help="JSON registry of known papers (id, title, doi, "
                             "authors, year)")
    parser.add_argument("--records",
                        help="key to descend into before reading records")
    args = parser.parse_args(argv)

    modes = [bool(args.id or args.pdf), bool(args.map_file),
             bool(args.source_dir or args.registry)]
    if sum(modes) != 1:
        parser.error("choose exactly one of --id/--pdf, --map-file, or "
                     "--from/--registry")

    if args.map_file:
        try:
            pairs = parse_map_file(args.map_file)
        except ValueError as exc:
            print(f"stage: {exc}", file=sys.stderr)
            return 1
        return run_explicit(args.work, pairs)

    if args.source_dir or args.registry:
        if not (args.source_dir and args.registry):
            parser.error("--from and --registry are used together")
        return run_registry(args.work, args.source_dir, args.registry,
                            args.records)

    if not (args.id and args.pdf):
        parser.error("--id and --pdf are used together")
    return run_explicit(args.work, [(args.id, args.pdf)])


if __name__ == "__main__":
    sys.exit(main())
