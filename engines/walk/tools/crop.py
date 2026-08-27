#!/usr/bin/env python3
"""Cut a region from a page render into a cropped exhibit PNG.

Reads a page render (a PNG from {work_dir}/pages/), cuts the union of
the given boxes out of it, auto-trims the uniform margins, and writes
the result. One region, one PNG, then exit: the figure stage's loop of
view, crop, inspect, adjust runs this tool once per attempt, and a
re-run simply overwrites the previous attempt.

Each --box is X0 Y0 X1 Y1 with the origin at the page's top left. By
default the numbers are pixels of the render itself. Boxes taken from a
witness are in that witness's own page space: OCR image bboxes are in
the dimensions images.json declares for the page, text-layer bboxes are
in the page size blocks.json records in points. Pass that space's width
and height as --space and the tool maps the boxes into render pixels.
The mapping is never done by hand: a slightly wrong scale crops a
plausible-looking wrong region, which is the silent kind of failure.

Several --box flags union into one rectangle. A multi-panel figure's
proposals go in verbatim, one box per panel, and the crop covers them
all: the gaps between panels, and anything printed in them, stay
inside.

A generous box is expected and cheap. The union is clamped to the
render, and the trim cuts the uniform border back to a few pixels
around the content, so overshooting the exhibit costs nothing. A box
that is inverted, a union that lands outside the render, and a crop
that comes back one uniform colour with nothing in it are all errors:
each means the region does not hold the exhibit, so nothing is written
and the failure says why.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pymupdf

# Device pixels of border kept around the trimmed content.
TRIM_PAD = 6
# How far a byte may sit from the border colour and still count as border.
# Not zero: a page that arrived as a scan or through a JPEG carries a
# little noise in its whitespace, and an exact-match trim finds content
# in it and does nothing at all. Small enough that anything a reader can
# see is content.
TRIM_TOLERANCE = 8


def resolve_region(boxes, space, width, height):
    """The union of the boxes as integer render-pixel coords, clamped.

    Rounds outward (floor the near edges, ceil the far ones), so mapping
    never shaves a pixel off a proposal. Raises ValueError naming the
    problem when a box is inverted or the union misses the render.
    """
    for box in boxes:
        x0, y0, x1, y1 = box
        if not (x0 < x1 and y0 < y1):
            raise ValueError(
                f"box {box} is empty or inverted; boxes are X0 Y0 X1 Y1 "
                f"from the page's top left with x0 < x1 and y0 < y1")
    sx = width / space[0] if space else 1.0
    sy = height / space[1] if space else 1.0
    x0 = min(box[0] for box in boxes) * sx
    y0 = min(box[1] for box in boxes) * sy
    x1 = max(box[2] for box in boxes) * sx
    y1 = max(box[3] for box in boxes) * sy
    left = max(0, math.floor(x0))
    top = max(0, math.floor(y0))
    right = min(width, math.ceil(x1))
    bottom = min(height, math.ceil(y1))
    if not (left < right and top < bottom):
        raise ValueError(
            f"the region [{x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}] lies "
            f"outside the {width}x{height} render; check the boxes and "
            f"the --space they were given in")
    return left, top, right, bottom


def crop_pixmap(pix, region):
    """A new pixmap holding just the region (render-pixel coords)."""
    left, top, right, bottom = region
    n, stride = pix.n, pix.stride
    samples = pix.samples
    kept = b"".join(samples[y * stride + left * n:y * stride + right * n]
                    for y in range(top, bottom))
    return pymupdf.Pixmap(pix.colorspace, right - left, bottom - top,
                          kept, pix.alpha)


def trim_margins(pix):
    """Cut the crop's uniform border back to TRIM_PAD pixels around the
    content; None for a crop holding no content at all.

    A box proposed off a witness or estimated off a render is generous
    by habit: better a stray margin than a clipped last row, so most
    crops arrive framed in page whitespace. This removes that frame, and
    only that frame. The kept region is the bounding box of every pixel
    that differs from the border colour by more than TRIM_TOLERANCE,
    grown by TRIM_PAD and clamped to the image, so no pixel a reader
    would call content can be cut however wide the margin was.

    A crop whose four corners do not agree on a colour is returned
    untouched: it has no single border to remove, and the safe reading
    of a crop whose top edge is a solid rule and whose bottom edge is
    white is that both are content. The corners can also agree because
    the border is itself content, in the one geometry that rule does not
    cover: a table ruled full width top and bottom with no side margin
    puts all four corners on a rule. TRIM_PAD is what protects it, so a
    rule up to that many pixels thick survives whole.

    A crop that is one uniform colour holds no exhibit. None tells the
    caller to refuse it rather than write a blank PNG.
    """
    w, h, n, stride = pix.width, pix.height, pix.n, pix.stride
    if w < 1 or h < 1:
        return pix
    samples = pix.samples

    def pixel(x, y):
        start = y * stride + x * n
        return samples[start:start + n]

    background = pixel(0, 0)
    corners = (pixel(w - 1, 0), pixel(0, h - 1), pixel(w - 1, h - 1))
    if any(any(abs(a - b) > TRIM_TOLERANCE for a, b in zip(background, corner))
           for corner in corners):
        return pix

    # One 256-byte translation table per channel: 0 for a byte within
    # tolerance of that channel's border value, 1 for content. The
    # translate and find calls then do the per-pixel work in C, which is
    # what makes this affordable over a full-page crop's pixels.
    tables = [bytes(0 if abs(value - background[c]) <= TRIM_TOLERANCE else 1
                    for value in range(256))
              for c in range(n)]
    uniform_row = background * w

    top = bottom = None
    left, right = w, -1
    for y in range(h):
        start = y * stride
        row = samples[start:start + w * n]
        if row == uniform_row:
            continue
        first, last = w, -1
        for c in range(n):
            marks = row[c::n].translate(tables[c])
            hit = marks.find(1)
            if hit >= 0:
                first = min(first, hit)
                last = max(last, marks.rfind(1))
        if last < 0:
            continue  # differs from the border colour, but within tolerance
        if top is None:
            top = y
        bottom = y
        left = min(left, first)
        right = max(right, last)

    if top is None:
        return None
    x0, y0 = max(0, left - TRIM_PAD), max(0, top - TRIM_PAD)
    x1, y1 = min(w, right + 1 + TRIM_PAD), min(h, bottom + 1 + TRIM_PAD)
    if (x0, y0, x1, y1) == (0, 0, w, h):
        return pix
    kept = b"".join(samples[y * stride + x0 * n:y * stride + x1 * n]
                    for y in range(y0, y1))
    return pymupdf.Pixmap(pix.colorspace, x1 - x0, y1 - y0, kept, pix.alpha)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="crop.py",
        description="Cut the union of the given boxes from a page render "
                    "into a trimmed exhibit PNG.",
    )
    parser.add_argument("render", type=Path,
                        help="the page render PNG to cut from")
    parser.add_argument("--box", type=float, nargs=4, action="append",
                        required=True, metavar=("X0", "Y0", "X1", "Y1"),
                        help="a region, origin at the page's top left; "
                             "repeat for the panels of one exhibit and the "
                             "union is cropped")
    parser.add_argument("--space", type=float, nargs=2, metavar=("W", "H"),
                        help="width and height of the space the boxes are "
                             "in (the page's images.json dimensions, or its "
                             "blocks.json size in points); omit when the "
                             "boxes are render pixels")
    parser.add_argument("--out", type=Path, required=True,
                        help="the PNG to write, usually "
                             "bundles/{id}/figures/{label}.png")
    args = parser.parse_args(argv)

    if not args.render.is_file():
        print(f"crop: render missing: {args.render}", file=sys.stderr)
        return 1
    if args.space and min(args.space) <= 0:
        print(f"crop: --space must be positive, got {args.space}",
              file=sys.stderr)
        return 1
    try:
        pix = pymupdf.Pixmap(str(args.render))
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"crop: could not read {args.render}: {exc}", file=sys.stderr)
        return 1
    try:
        region = resolve_region(args.box, args.space, pix.width, pix.height)
    except ValueError as exc:
        print(f"crop: {exc}", file=sys.stderr)
        return 1
    trimmed = trim_margins(crop_pixmap(pix, region))
    if trimmed is None:
        print(f"crop: the region {list(region)} of {args.render.name} is "
              f"one uniform colour with nothing in it; nothing written. "
              f"The proposal missed the exhibit; check it against the "
              f"render.", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    trimmed.save(str(args.out))
    print(f"crop: {args.render.name} {list(region)} -> {args.out} "
          f"({trimmed.width}x{trimmed.height} after trim)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
