#!/usr/bin/env python3
"""Render a table transcription back to an image, for comparison with its crop.

A transcription is the exhibit's content as text, and nothing in the bundle
contract can see whether it says what the exhibit says. This tool closes
that by putting the two side by side as pictures: it lays out
`tables/{label}.html` and writes a PNG, which the figure stage and the
sweep hold beside `figures/{label}.png`. A cell that moved column, a
spanning header that lands over the wrong columns, and a row that went
missing are all obvious as pictures and subtle as markup, which is the
whole reason the comparison is made this way round.

The rendering is deliberately plain and fixed. It is not an attempt to
imitate the journal's typesetting, and it will not look like the crop: the
face is different, the rules are uniform, nothing is shaded. Only the
content and its arrangement are being compared, so the styling is the same
for every table this repository renders and is not configurable.

An exhibit printed sideways is the one case that needs a flag. Its crop
comes off the page rotated, so `--rotate` turns the render to match; the
transcription itself is always written in reading order, whichever way the
page prints it. Pass the rotation the crop has, not the one it needs.

The transcription is checked before it is drawn, by the format's own rule
(`alteksto.bundle.validate_table_html`) and not by a second opinion formed
here. Nothing is written when it does not pass, and every problem is
printed. This is the order the checks are meant to run in: structure is
settled deterministically first, and only a transcription that tiles its
grid is worth an agent's time comparing against the crop. It also stops the
one silent failure this tool could otherwise produce, which is laying out a
file holding prose rather than a table and handing back a perfectly good
picture of the wrong thing.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pymupdf

from alteksto.bundle import validate_table_html

# The layout the comparison always uses. Borders on every cell because cell
# boundaries are exactly what is being checked, and a header that is visibly
# a header because a spanning group header sitting over the wrong columns is
# the error this render exists to make obvious.
TABLE_CSS = """
table { border-collapse: collapse; font-family: sans-serif; }
th, td { border: 1px solid #666; padding: 4px 7px; font-size: 10pt;
         text-align: left; vertical-align: top; }
th { background: #eee; }
"""
# Points of white kept around the laid-out table.
PAD = 8
# The height the table is laid out into, and the ceiling it may grow to
# before the tool gives up. A story that does not fit is grown rather than
# broken across pages: one exhibit is one picture, because a comparison
# against one crop is what the output is for.
START_HEIGHT = 1400.0
MAX_HEIGHT = 40000.0


def content_box(page):
    """The rectangle the page actually draws in, rules and text together.

    The story is laid out into a frame as wide as `--width` and as tall as
    it needs, and a table narrower or shorter than that frame would
    otherwise be delivered as a small table in a large sheet of white. The
    extent is taken from what was drawn rather than from what `place`
    reports filled, which is the frame it was given. None when the page
    draws nothing at all.
    """
    boxes = [pymupdf.Rect(drawing["rect"])
             for drawing in page.get_drawings()]
    boxes += [pymupdf.Rect(block["bbox"])
              for block in page.get_text("dict")["blocks"]]
    boxes = [box for box in boxes if not box.is_empty]
    if not boxes:
        return None
    # Accumulated from a real rectangle rather than from an empty one: a
    # union that starts at pymupdf's default Rect drags the result out to
    # the page origin, which would put the whole top left corner in shot.
    extent = pymupdf.Rect(boxes[0])
    for box in boxes[1:]:
        extent |= box
    return extent


def render(source: str, width: float, dpi: int, rotate: int = 0):
    """Lay the markup out and return a pixmap of the table alone.

    Returns None when nothing is drawn at all. Raises ValueError when the
    table will not fit inside MAX_HEIGHT, rather than quietly handing back
    its first page: one exhibit is one picture, because one crop is what
    the picture gets compared against.
    """
    height = START_HEIGHT
    while height <= MAX_HEIGHT:
        story = pymupdf.Story(html=source, user_css=TABLE_CSS)
        page = pymupdf.Rect(0, 0, width + 2 * PAD, height)
        buffer = io.BytesIO()
        writer = pymupdf.DocumentWriter(buffer)
        device = writer.begin_page(page)
        more, _ = story.place(page + (PAD, PAD, -PAD, -PAD))
        story.draw(device)
        writer.end_page()
        writer.close()
        if more:
            height *= 2
            continue
        document = pymupdf.open("pdf", buffer.getvalue())
        drawn = content_box(document[0])
        if drawn is None or drawn.width <= 0 or drawn.height <= 0:
            return None
        clip = (drawn + (-PAD, -PAD, PAD, PAD)) & document[0].rect
        # Rotation is applied by the render matrix rather than to a saved
        # image, so a turned render is drawn at full resolution rather than
        # resampled from an upright one.
        zoom = dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom).prerotate(rotate)
        return document[0].get_pixmap(matrix=matrix, clip=clip)
    raise ValueError(
        f"the table did not fit in {MAX_HEIGHT:.0f} points of height; "
        f"either it is not a table or it is far larger than any exhibit")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="render_table.py",
        description="Render a bundle's table transcription to a PNG so it "
                    "can be compared against the exhibit's crop.",
    )
    parser.add_argument("source", type=Path,
                        help="the transcription to render, usually "
                             "bundles/{id}/tables/{label}.html")
    parser.add_argument("--out", type=Path, required=True,
                        help="the PNG to write, usually "
                             "work/{id}/table_renders/{label}.png")
    parser.add_argument("--rotate", type=int, default=0,
                        choices=(0, 90, 180, 270),
                        help="turn the render to match a crop that came "
                             "off the page rotated; pass the rotation the "
                             "crop has")
    parser.add_argument("--width", type=float, default=760.0,
                        help="points of width to lay the table out in "
                             "(default 760)")
    parser.add_argument("--dpi", type=int, default=150,
                        help="render resolution, matching the page "
                             "renders (default 150)")
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"render-table: transcription missing: {args.source}",
              file=sys.stderr)
        return 1
    if args.width <= 0 or args.dpi <= 0:
        print(f"render-table: --width and --dpi must be positive, got "
              f"{args.width} and {args.dpi}", file=sys.stderr)
        return 1
    try:
        source = args.source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"render-table: could not read {args.source}: {exc}",
              file=sys.stderr)
        return 1
    problems = validate_table_html(source, str(args.source))
    if problems:
        for problem in problems:
            print(f"render-table: {problem}", file=sys.stderr)
        print(f"render-table: nothing written; fix the transcription and "
              f"run this again", file=sys.stderr)
        return 1
    try:
        pix = render(source, args.width, args.dpi, args.rotate)
    except ValueError as exc:
        print(f"render-table: {exc}", file=sys.stderr)
        return 1
    except (RuntimeError, TypeError) as exc:
        print(f"render-table: {args.source} did not lay out: {exc}",
              file=sys.stderr)
        return 1
    if pix is None:
        print(f"render-table: {args.source} passed the format's checks and "
              f"still laid out to nothing; this is a bug in this tool, not "
              f"in the transcription.", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(args.out))
    turned = f", turned {args.rotate} degrees" if args.rotate else ""
    print(f"render-table: {args.source.name} -> {args.out} "
          f"({pix.width}x{pix.height}{turned})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
