"""Offline tests for tools/render_table.py on invented transcriptions.

The tool draws a table transcription so it can be held beside the crop it
was made from. Nothing here reads the picture: what is asserted is that a
picture is produced for a table, that none is produced for anything else,
and that a sideways exhibit gets a render turned to match its crop.
"""

import pymupdf
import pytest

from conftest import load_tool

# The shape the format exists to carry, and the shape a plain grid cannot:
# a group header spanning two columns over a stub column that spans two
# rows, with one cell the paper leaves empty.
SPANNING = (
    '<table><thead>'
    '<tr><th rowspan="2" scope="col">Study</th>'
    '<th colspan="2" scope="colgroup">Intervention</th></tr>'
    '<tr><th scope="col">n</th><th scope="col">Mean (SD)</th></tr>'
    '</thead><tbody>'
    '<tr><td>Ashby 2019</td><td>142</td><td>12.4 (3.1)</td></tr>'
    '<tr><td>Brune 2021<sup>a</sup></td><td>88</td><td></td></tr>'
    '</tbody></table>'
)


@pytest.fixture(scope="session")
def render_table_tool():
    return load_tool("render_table")


def _page_width_px(tool, width, dpi):
    """The pixel width of the page a table of `width` is first laid out on.

    A render truncated to that page is this wide, so it is the threshold a
    grown render has to beat. Read off the tool's own padding rather than
    written down here, so the two cannot drift apart.
    """
    return (width + 2 * tool.PAD) * dpi / 72


def write(tmp_path, markup, name="table_01.html"):
    path = tmp_path / name
    path.write_text(markup, encoding="utf-8")
    return path


def test_a_spanning_table_renders(render_table_tool, tmp_path):
    source = write(tmp_path, SPANNING)
    out = tmp_path / "renders" / "table_01.png"
    assert render_table_tool.main([str(source), "--out", str(out)]) == 0
    assert out.is_file()
    pix = pymupdf.Pixmap(str(out))
    assert pix.width > 100 and pix.height > 40


def test_the_render_is_the_table_and_not_the_sheet(render_table_tool,
                                                   tmp_path):
    """A narrow table comes back narrow.

    The story is laid out into a frame as wide as --width, so without
    tightening to what was drawn every render would be a small table in a
    large field of white, and two of them side by side would be mostly
    margin.
    """
    source = write(tmp_path, "<table><tr><td>x</td></tr></table>")
    out = tmp_path / "tiny.png"
    assert render_table_tool.main([str(source), "--out", str(out),
                                   "--width", "760", "--dpi", "150"]) == 0
    pix = pymupdf.Pixmap(str(out))
    assert pix.width < 760 * 150 / 72 / 4


def test_rotation_turns_the_render_to_match_a_sideways_crop(
        render_table_tool, tmp_path):
    source = write(tmp_path, SPANNING)
    upright = tmp_path / "upright.png"
    turned = tmp_path / "turned.png"
    assert render_table_tool.main([str(source), "--out", str(upright)]) == 0
    assert render_table_tool.main([str(source), "--out", str(turned),
                                   "--rotate", "90"]) == 0
    before = pymupdf.Pixmap(str(upright))
    after = pymupdf.Pixmap(str(turned))
    assert (after.width, after.height) == (before.height, before.width)


def test_prose_is_refused_rather_than_drawn(render_table_tool, tmp_path,
                                            capsys):
    """The one silent failure this tool could produce.

    A file of prose lays out perfectly happily and would come back as a
    good picture of the wrong thing, which the comparison step might well
    accept. It is refused by the format's own rule, not by a second
    opinion formed here.
    """
    source = write(tmp_path, "The table could not be read.")
    out = tmp_path / "prose.png"
    assert render_table_tool.main([str(source), "--out", str(out)]) == 1
    assert not out.exists()
    assert "contains no <table>" in capsys.readouterr().err


def test_a_holed_grid_is_refused_with_its_position(render_table_tool,
                                                   tmp_path, capsys):
    source = write(tmp_path, '<table><tr><th colspan="2">Wide</th></tr>'
                             '<tr><td>a</td></tr></table>')
    out = tmp_path / "holed.png"
    assert render_table_tool.main([str(source), "--out", str(out)]) == 1
    assert not out.exists()
    assert "leaves row 1 column 1 uncovered" in capsys.readouterr().err


def test_a_missing_source_is_a_loud_failure(render_table_tool, tmp_path,
                                            capsys):
    out = tmp_path / "absent.png"
    assert render_table_tool.main([str(tmp_path / "nope.html"),
                                   "--out", str(out)]) == 1
    assert "transcription missing" in capsys.readouterr().err


@pytest.mark.parametrize("flag, value", [("--width", "0"), ("--dpi", "0")])
def test_nonsense_dimensions_are_refused(render_table_tool, tmp_path,
                                         capsys, flag, value):
    source = write(tmp_path, SPANNING)
    assert render_table_tool.main([str(source), "--out",
                                   str(tmp_path / "x.png"),
                                   flag, value]) == 1
    assert "must be positive" in capsys.readouterr().err


def test_a_wide_table_grows_the_frame_rather_than_being_cut(
        render_table_tool, tmp_path):
    """The failure this replaces was silent and exited zero.

    `place()` reports vertical overflow and says nothing about
    horizontal, so a table wider than the frame used to come back with
    its right-hand columns simply absent and a success line naming the
    truncated size. A comparison against that either reads as a
    transcription that dropped those columns, sending an author to
    mangle a correct table, or gets waved through.
    """
    header = "".join(f"<th>Column {n}</th>" for n in range(40))
    values = "".join(f"<td>{n}</td>" for n in range(40))
    source = write(tmp_path, f"<table><tr>{header}</tr>"
                             f"<tr>{values}</tr></table>")
    out = tmp_path / "wide.png"
    assert render_table_tool.main([str(source), "--out", str(out),
                                   "--width", "760", "--dpi", "150"]) == 0
    pix = pymupdf.Pixmap(str(out))
    # Wider than the whole PAGE it was first laid out on, not merely wider
    # than the frame inside it. A fully truncated render fills that page,
    # so the looser threshold passed against the very code this test was
    # written to catch, by nine pixels.
    assert pix.width > _page_width_px(render_table_tool, 760, 150)


def test_an_unbreakable_cell_widens_the_frame(render_table_tool, tmp_path):
    source = write(tmp_path, "<table><tr><th>Compound</th><th>n</th></tr>"
                             f"<tr><td>{'Aaaaaaaaaa' * 24}</td>"
                             "<td>142</td></tr></table>")
    out = tmp_path / "unbreakable.png"
    assert render_table_tool.main([str(source), "--out", str(out)]) == 0
    assert (pymupdf.Pixmap(str(out)).width
            > _page_width_px(render_table_tool, 760, 150))


def test_a_table_taller_than_the_first_frame_still_renders(
        render_table_tool, tmp_path):
    """The growth loop reaches its stated ceiling.

    Doubling from the starting height used to stop at 22400 points while
    the message named 40000, so a long but perfectly correct
    transcription was refused and the operator was sent looking for a
    table that is not a table.
    """
    rows = "".join(f"<tr><td>Row {n}</td><td>{n}</td></tr>"
                   for n in range(1200))
    source = write(tmp_path, f"<table>{rows}</table>")
    out = tmp_path / "verylong.png"
    assert render_table_tool.main([str(source), "--out", str(out)]) == 0
    assert pymupdf.Pixmap(str(out)).height > 20000


def test_a_picture_too_large_to_use_is_refused_by_this_tool(
        render_table_tool, tmp_path, capsys):
    """Growing in both directions has a ceiling, and it is ours.

    A table the format accepts can ask for hundreds of megapixels, and
    past a point MuPDF refuses to draw one and raises an error of a type
    a caller would not think to name. A nine-frame traceback where a
    `render-table:` line belongs is the tool failing at the one thing it
    promises when it refuses something.
    """
    # Reached with resolution rather than with an enormous table: the
    # ceiling is on the picture, so a modest table at a high --dpi crosses
    # it for the same reason and lays out in a fraction of the time.
    row = "<tr>" + "<td>12.4 (3.1)</td>" * 20 + "</tr>"
    source = write(tmp_path, "<table>" + row * 60 + "</table>")
    out = tmp_path / "huge.png"
    assert render_table_tool.main([str(source), "--out", str(out),
                                   "--dpi", "900"]) == 1
    assert not out.exists()
    err = capsys.readouterr().err
    assert "megapixels" in err and "lower --dpi" in err
    # And the advice works: the same table at a lower resolution renders.
    assert render_table_tool.main([str(source), "--out", str(out),
                                   "--dpi", "150"]) == 0


def test_a_width_beyond_the_ceiling_is_refused(render_table_tool, tmp_path,
                                               capsys):
    source = write(tmp_path, SPANNING)
    assert render_table_tool.main([str(source), "--out",
                                   str(tmp_path / "x.png"),
                                   "--width", "99999"]) == 1
    assert "beyond the 20000" in capsys.readouterr().err


def test_a_long_table_grows_the_page_rather_than_splitting(
        render_table_tool, tmp_path):
    """One exhibit is one picture, because one crop is what it faces.

    A table taller than the starting frame is laid out again into a taller
    one. If it were allowed to overflow instead, the render would show the
    first page of the transcription and the comparison would silently be
    against part of it.
    """
    rows = "".join(f"<tr><td>Row {n}</td><td>{n}</td></tr>"
                   for n in range(300))
    source = write(tmp_path, f"<table>{rows}</table>")
    out = tmp_path / "long.png"
    assert render_table_tool.main([str(source), "--out", str(out)]) == 0
    pix = pymupdf.Pixmap(str(out))
    assert pix.height > 2000
