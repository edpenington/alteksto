#!/usr/bin/env python3
"""Dump a work directory's PDF text layer as blocks.

Reads {work_dir}/source.pdf and writes {work_dir}/blocks.json (each
page's size in points, then one record per text block: page, index,
bbox, text) and {work_dir}/blocks.txt (the same text flattened, with a
page marker line before each page).

The text is raw: character-exact and badly assembled, which is the whole
point of dumping it. The text layer is the authority on what the
characters are, never on what order they go in, and nothing here cleans,
heals, or reorders it.

The layer is not blind to styling: each glyph's font carries italic and
bold flags, and every block record lists its styled runs under an
`emphasis` key (style plus run text, in reading order; a block with no
styled runs omits the key). The flags are a witness, not an authority:
some PDFs fake italics with a slanting transform the flags cannot see,
so a run the flags miss is settled by the render like any other
disagreement. The run text repeats characters already in the block's
`text`; it locates the styling, it is not a second transcription.

The geometry is bookkeeping, not text, so it is recorded in the one
space every consumer shares: the page as displayed, which is the space
the page renders show. PyMuPDF reports block bboxes in unrotated
coordinates even on a page shipped with a rotation (a landscape table
page, as journals print one), so each bbox is mapped through the page's
rotation before it is written. On an unrotated page the mapping is the
identity. Without it a bbox handed to the crop tool would land on a
plausible wrong region of the render, silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf

from alteksto.workdir import open_source_pdf, page_marker


def _span_style(flags: int) -> str | None:
    """The span's emphasis as the walk names it, or None for plain text."""
    italic = bool(flags & 2)
    bold = bool(flags & 16)
    if italic and bold:
        return "bold italic"
    if italic:
        return "italic"
    if bold:
        return "bold"
    return None


def _emphasis_runs(dict_block: dict) -> list[dict]:
    """The block's styled runs, adjacent same-style spans merged per line.

    Merging within a line keeps a phrase that the layer split across
    spans (kerning, font substitution) as one run; runs never merge
    across lines, so a line break stays visible as two runs.
    """
    runs: list[dict] = []

    def flush(style, parts):
        text = "".join(parts).strip()
        if style and text:
            runs.append({"style": style, "text": text})

    for line in dict_block.get("lines", []):
        style, parts = None, []
        for span in line.get("spans", []):
            span_style = _span_style(span.get("flags", 0))
            if span_style != style:
                flush(style, parts)
                style, parts = span_style, []
            if span_style:
                parts.append(span.get("text", ""))
        flush(style, parts)
    return runs


def dump_blocks(doc: pymupdf.Document, work_dir: Path) -> int:
    """Write blocks.json and blocks.txt; return the number of text blocks."""
    pages: list[dict] = []
    records: list[dict] = []
    flat: list[str] = []
    for number in range(1, len(doc) + 1):
        page = doc.load_page(number - 1)
        pages.append({
            "page": number,
            "width": round(page.rect.width, 2),
            "height": round(page.rect.height, 2),
        })
        flat.append(page_marker(number))
        # Both listings walk one TextPage in the same order, but the
        # dict listing carries image blocks the block listing omits, so
        # image blocks are dropped before position pairs them; the
        # styled runs for block index live at dict_blocks[index].
        dict_blocks = [b for b in page.get_text("dict")["blocks"]
                       if b.get("type") == 0]
        for index, block in enumerate(page.get_text("blocks")):
            x0, y0, x1, y1, text, _block_no, block_type = block[:7]
            if block_type != 0 or not text.strip():
                continue
            text = text.rstrip()
            # Into display space (see the module docstring); identity on
            # an unrotated page.
            rect = (pymupdf.Rect(x0, y0, x1, y1)
                    * page.rotation_matrix).normalize()
            record = {
                "page": number,
                "index": index,
                "bbox": [round(float(v), 2)
                         for v in (rect.x0, rect.y0, rect.x1, rect.y1)],
                "text": text,
            }
            if index < len(dict_blocks):
                runs = _emphasis_runs(dict_blocks[index])
                if runs:
                    record["emphasis"] = runs
            records.append(record)
            flat.append(text)
    (work_dir / "blocks.json").write_text(
        json.dumps({"page_count": len(doc), "pages": pages,
                    "blocks": records},
                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (work_dir / "blocks.txt").write_text("\n\n".join(flat) + "\n",
                                         encoding="utf-8")
    return len(records)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="dump_blocks.py",
        description="Dump {work_dir}/source.pdf's text layer to blocks.json "
                    "and blocks.txt.",
    )
    parser.add_argument("work_dir", type=Path,
                        help="the paper's work directory, holding source.pdf")
    args = parser.parse_args(argv)

    try:
        doc = open_source_pdf(args.work_dir)
    except ValueError as exc:
        print(f"dump-blocks: {exc}", file=sys.stderr)
        return 1
    try:
        pages = len(doc)
        count = dump_blocks(doc, args.work_dir)
    finally:
        doc.close()
    print(f"dump-blocks: {count} text blocks over {pages} pages -> "
          f"{args.work_dir / 'blocks.json'}", file=sys.stderr)
    if count == 0:
        print("dump-blocks: the text layer is empty; the PDF is likely "
              "scanned, and triage should treat the dump as void",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
