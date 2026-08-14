#!/usr/bin/env python3
"""Render a work directory's source.pdf to page PNGs.

Reads {work_dir}/source.pdf and writes {work_dir}/pages/page_NN.png at the
chosen DPI. Stale renders are deleted first, so a re-run replaces the
whole set and can never leave two renders mixed. One work directory, one
job, then exit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

from alteksto.workdir import dpi_error, open_source_pdf


def render_pages(doc: pymupdf.Document, pages_dir: Path, *,
                 dpi: int) -> list[Path]:
    """Render every page to pages_dir as page_NN.png; return the paths."""
    pages_dir.mkdir(parents=True, exist_ok=True)
    for old in pages_dir.glob("page_*.png"):
        old.unlink()
    matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
    written: list[Path] = []
    for number in range(1, len(doc) + 1):
        pixmap = doc.load_page(number - 1).get_pixmap(matrix=matrix)
        path = pages_dir / f"page_{number:02d}.png"
        pixmap.save(str(path))
        written.append(path)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="render_pages.py",
        description="Render {work_dir}/source.pdf to "
                    "{work_dir}/pages/page_NN.png.",
    )
    parser.add_argument("work_dir", type=Path,
                        help="the paper's work directory, holding source.pdf")
    parser.add_argument("--dpi", type=int, default=150,
                        help="render resolution (default 150)")
    args = parser.parse_args(argv)

    problem = dpi_error(args.dpi)
    if problem:
        print(f"render-pages: {problem}", file=sys.stderr)
        return 1
    try:
        doc = open_source_pdf(args.work_dir)
    except ValueError as exc:
        print(f"render-pages: {exc}", file=sys.stderr)
        return 1
    try:
        written = render_pages(doc, args.work_dir / "pages", dpi=args.dpi)
    finally:
        doc.close()
    print(f"render-pages: {len(written)} pages at {args.dpi} DPI -> "
          f"{args.work_dir / 'pages'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
