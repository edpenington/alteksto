"""Offline tests for engines/walk/tools/crop.py on invented render PNGs."""

import pymupdf
import pytest

from tests.engines.walk.support import load_tool

WIDTH, HEIGHT = 400, 300
INK = bytes((30, 30, 30))
PAPER = bytes((255, 255, 255))

# One invented exhibit: a dark rectangle on a white page render.
CONTENT = (100, 80, 220, 160)


@pytest.fixture(scope="session")
def crop_tool():
    return load_tool("crop")


def make_render(path, rects, size=(WIDTH, HEIGHT)):
    """Write a PNG of a white page holding dark rectangles."""
    width, height = size
    samples = bytearray(PAPER * (width * height))
    for x0, y0, x1, y1 in rects:
        for y in range(y0, y1):
            row = y * width * 3
            for x in range(x0, x1):
                samples[row + x * 3:row + x * 3 + 3] = INK
    pix = pymupdf.Pixmap(pymupdf.csRGB, width, height, bytes(samples), 0)
    pix.save(str(path))
    return path


def run(crop_tool, render, out, *extra):
    return crop_tool.main([str(render), *extra, "--out", str(out)])


def test_a_generous_box_is_trimmed_to_the_content(crop_tool, tmp_path):
    render = make_render(tmp_path / "page_01.png", [CONTENT])
    # The out directory does not exist yet; the tool creates it.
    out = tmp_path / "figures" / "figure_01.png"
    assert run(crop_tool, render, out,
               "--box", "60", "40", "280", "220") == 0
    pix = pymupdf.Pixmap(str(out))
    pad = crop_tool.TRIM_PAD
    assert (pix.width, pix.height) == (CONTENT[2] - CONTENT[0] + 2 * pad,
                                       CONTENT[3] - CONTENT[1] + 2 * pad)


def test_an_oversized_box_clamps_to_the_render(crop_tool, tmp_path):
    render = make_render(tmp_path / "page_01.png", [CONTENT])
    out = tmp_path / "figure_01.png"
    assert run(crop_tool, render, out,
               "--box", "0", "0", "9999", "9999") == 0
    pix = pymupdf.Pixmap(str(out))
    pad = crop_tool.TRIM_PAD
    assert (pix.width, pix.height) == (CONTENT[2] - CONTENT[0] + 2 * pad,
                                       CONTENT[3] - CONTENT[1] + 2 * pad)


def test_panel_boxes_union_into_one_crop(crop_tool, tmp_path):
    # Two panels of one exhibit, one proposal box each; the crop covers
    # both and the gap between them.
    panel_a = (60, 60, 140, 120)
    panel_b = (200, 60, 300, 140)
    render = make_render(tmp_path / "page_02.png", [panel_a, panel_b])
    out = tmp_path / "figure_02.png"
    assert run(crop_tool, render, out,
               "--box", "50", "50", "150", "130",
               "--box", "190", "50", "310", "150") == 0
    pix = pymupdf.Pixmap(str(out))
    pad = crop_tool.TRIM_PAD
    assert (pix.width, pix.height) == (panel_b[2] - panel_a[0] + 2 * pad,
                                       panel_b[3] - panel_a[1] + 2 * pad)


def test_space_maps_witness_boxes_into_render_pixels(crop_tool, tmp_path):
    # The same generous box as the first test, given in a witness space
    # twice the render's size, lands on the same content.
    render = make_render(tmp_path / "page_01.png", [CONTENT])
    out = tmp_path / "figure_01.png"
    assert run(crop_tool, render, out,
               "--box", "120", "80", "560", "440",
               "--space", "800", "600") == 0
    pix = pymupdf.Pixmap(str(out))
    pad = crop_tool.TRIM_PAD
    assert (pix.width, pix.height) == (CONTENT[2] - CONTENT[0] + 2 * pad,
                                       CONTENT[3] - CONTENT[1] + 2 * pad)


def test_content_at_the_edges_is_left_untrimmed(crop_tool, tmp_path):
    # Content touching the crop's corner: the corners disagree on a
    # border colour, so there is no single border and nothing is cut.
    render = make_render(tmp_path / "page_03.png", [(0, 0, 60, 40)])
    out = tmp_path / "figure_03.png"
    assert run(crop_tool, render, out, "--box", "0", "0", "100", "80") == 0
    pix = pymupdf.Pixmap(str(out))
    assert (pix.width, pix.height) == (100, 80)


def test_a_blank_region_is_refused(crop_tool, tmp_path, capsys):
    render = make_render(tmp_path / "page_01.png", [CONTENT])
    out = tmp_path / "figure_01.png"
    assert run(crop_tool, render, out,
               "--box", "240", "200", "380", "280") == 1
    assert "uniform colour" in capsys.readouterr().err
    assert not out.exists()


def test_an_inverted_box_is_refused(crop_tool, tmp_path, capsys):
    render = make_render(tmp_path / "page_01.png", [CONTENT])
    assert run(crop_tool, render, tmp_path / "out.png",
               "--box", "280", "220", "60", "40") == 1
    assert "inverted" in capsys.readouterr().err


def test_a_region_outside_the_render_is_refused(crop_tool, tmp_path, capsys):
    render = make_render(tmp_path / "page_01.png", [CONTENT])
    assert run(crop_tool, render, tmp_path / "out.png",
               "--box", "500", "40", "600", "200") == 1
    assert "outside" in capsys.readouterr().err


def test_a_nonpositive_space_is_refused(crop_tool, tmp_path, capsys):
    render = make_render(tmp_path / "page_01.png", [CONTENT])
    assert run(crop_tool, render, tmp_path / "out.png",
               "--box", "60", "40", "280", "220",
               "--space", "0", "600") == 1
    assert "--space" in capsys.readouterr().err


def test_missing_render_fails(crop_tool, tmp_path, capsys):
    assert run(crop_tool, tmp_path / "absent.png", tmp_path / "out.png",
               "--box", "60", "40", "280", "220") == 1
    assert "render missing" in capsys.readouterr().err
