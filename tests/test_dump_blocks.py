"""Offline tests for tools/dump_blocks.py on an invented PDF."""

import json

import pymupdf

from conftest import PAGE_ONE_LINES

MARKER_ONE = "<!-- page 1 -->"
MARKER_TWO = "<!-- page 2 -->"


def test_blocks_json_holds_the_text_layer(dump_blocks_tool, work_dir):
    assert dump_blocks_tool.main([str(work_dir)]) == 0
    data = json.loads((work_dir / "blocks.json").read_text(encoding="utf-8"))
    assert data["page_count"] == 2
    # Each page's size is recorded, so a bbox carries its space with it.
    sizes = {p["page"]: (p["width"], p["height"]) for p in data["pages"]}
    assert sorted(sizes) == [1, 2]
    texts = [block["text"] for block in data["blocks"]]
    assert PAGE_ONE_LINES[0] in texts
    assert PAGE_ONE_LINES[1] in texts
    for block in data["blocks"]:
        assert block["page"] in (1, 2)
        assert isinstance(block["index"], int)
        assert block["text"].strip()
        width, height = sizes[block["page"]]
        x0, y0, x1, y1 = block["bbox"]
        assert 0 <= x0 < x1 <= width
        assert 0 <= y0 < y1 <= height


def test_line_break_hyphen_stays_raw(dump_blocks_tool, work_dir):
    # The dump is bytes-faithful: a hyphen split across a line break inside
    # a block is exactly the artefact downstream stages adjudicate, so it
    # must survive the dump unhealed.
    assert dump_blocks_tool.main([str(work_dir)]) == 0
    text = (work_dir / "blocks.txt").read_text(encoding="utf-8")
    assert "pres-\nsure" in text


def test_blocks_txt_marks_the_pages_in_order(dump_blocks_tool, work_dir):
    assert dump_blocks_tool.main([str(work_dir)]) == 0
    text = (work_dir / "blocks.txt").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert MARKER_ONE in lines and MARKER_TWO in lines
    # Page one's text sits between its marker and page two's.
    assert (text.index(MARKER_ONE)
            < text.index(PAGE_ONE_LINES[0])
            < text.index(MARKER_TWO))


def test_emphasis_runs_come_from_the_font_flags(dump_blocks_tool, tmp_path):
    # A block mixing plain, italic, and bold text: the record lists the
    # styled runs in order, and plain-only blocks omit the key.
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "The invented heron count was ",
                     fontname="helv")
    page.insert_text((72, 130), "significant", fontname="tiit")
    page.insert_text((72, 160), "Results:", fontname="hebo")
    page.insert_text((200, 300), "A plain closing sentence.",
                     fontname="helv")
    doc.save(tmp_path / "source.pdf")
    doc.close()
    assert dump_blocks_tool.main([str(tmp_path)]) == 0
    data = json.loads((tmp_path / "blocks.json").read_text(encoding="utf-8"))
    styled = {run["text"]: run["style"]
              for block in data["blocks"]
              for run in block.get("emphasis", [])}
    assert styled == {"significant": "italic", "Results:": "bold"}
    plain = [b for b in data["blocks"] if "plain closing" in b["text"]]
    assert plain and "emphasis" not in plain[0]


def test_emphasis_pairing_survives_an_image_block(dump_blocks_tool,
                                                  tmp_path):
    # The dict listing carries image blocks that the block listing
    # omits, so pairing runs to blocks by raw position shifts after an
    # image and styled runs land on the wrong block. Observed on real
    # image-bearing pages; the pairing must skip image blocks.
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "A plain opening block.", fontname="helv")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
    pix.clear_with(120)
    page.insert_image(pymupdf.Rect(72, 150, 172, 250), pixmap=pix)
    page.insert_text((72, 300), "significant", fontname="tiit")
    doc.save(tmp_path / "source.pdf")
    doc.close()
    assert dump_blocks_tool.main([str(tmp_path)]) == 0
    data = json.loads((tmp_path / "blocks.json").read_text(encoding="utf-8"))
    by_text = {b["text"]: b for b in data["blocks"]}
    assert "emphasis" not in by_text["A plain opening block."]
    assert by_text["significant"]["emphasis"] == [
        {"style": "italic", "text": "significant"}]


def test_a_rotated_page_reports_display_space_bboxes(dump_blocks_tool,
                                                     tmp_path):
    # A landscape table ships as a portrait page rotated 90 degrees.
    # PyMuPDF reports its block bboxes in the unrotated space; the dump
    # maps them into the space the renders show. A horizontal line of
    # text on the unrotated page therefore comes out tall and thin, and
    # inside the displayed page size.
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 120), "An invented sideways table heading.")
    page.set_rotation(90)
    doc.save(tmp_path / "source.pdf")
    doc.close()
    assert dump_blocks_tool.main([str(tmp_path)]) == 0
    data = json.loads((tmp_path / "blocks.json").read_text(encoding="utf-8"))
    size = data["pages"][0]
    assert (size["width"], size["height"]) == (792, 612)
    (block,) = data["blocks"]
    x0, y0, x1, y1 = block["bbox"]
    assert 0 <= x0 < x1 <= size["width"]
    assert 0 <= y0 < y1 <= size["height"]
    assert (y1 - y0) > (x1 - x0)


def test_rerun_overwrites_cleanly(dump_blocks_tool, work_dir):
    assert dump_blocks_tool.main([str(work_dir)]) == 0
    first = (work_dir / "blocks.json").read_text(encoding="utf-8")
    assert dump_blocks_tool.main([str(work_dir)]) == 0
    assert (work_dir / "blocks.json").read_text(encoding="utf-8") == first


def test_empty_text_layer_is_reported_loudly(dump_blocks_tool, tmp_path,
                                             capsys):
    # A page with no text at all: the dump succeeds, writes an empty block
    # list, and says out loud that the PDF is likely scanned.
    doc = pymupdf.open()
    doc.new_page()
    doc.save(tmp_path / "source.pdf")
    doc.close()
    assert dump_blocks_tool.main([str(tmp_path)]) == 0
    data = json.loads((tmp_path / "blocks.json").read_text(encoding="utf-8"))
    assert data["blocks"] == []
    assert "empty" in capsys.readouterr().err


def test_missing_source_pdf_fails(dump_blocks_tool, tmp_path, capsys):
    assert dump_blocks_tool.main([str(tmp_path)]) == 1
    assert "source PDF missing" in capsys.readouterr().err
