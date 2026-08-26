"""Offline tests for the worked example in examples/.

Three things are held together here, because a worked example is only
worth having if its parts describe the same paper: the PDF that
examples/build_pdf.py prints, the skeleton and bundle committed beside
it, and the crop regions recorded in expected/crops.json. Nothing here
touches the network, and no OCR is called.

The PDF is built into tmp and thrown away, as the fixture rule requires.
"""

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest

from alteksto.bundle import SCHEMA_VERSION, validate_table_html
from conftest import load_tool

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
EXPECTED = EXAMPLES / "expected"


def _load_builder():
    """Load examples/build_pdf.py as a module, the way conftest loads tools."""
    spec = importlib.util.spec_from_file_location(
        "build_pdf", EXAMPLES / "build_pdf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_builder()

STYLES = {builder.ITALIC: "italic", builder.BOLD: "bold"}
# The roles whose text reaches text.md as running prose. A caption reaches
# it inside a sentinel and an exhibit line never reaches it at all, so both
# are checked apart from these.
PROSE_ROLES = ("front", "body", "heading")


@pytest.fixture(scope="module")
def paper(tmp_path_factory):
    """The example built once, then rendered and dumped like any paper."""
    work = tmp_path_factory.mktemp("example")
    builder.build(work)
    assert load_tool("render_pages").main([str(work)]) == 0
    assert load_tool("dump_blocks").main([str(work)]) == 0
    return work


@pytest.fixture(scope="module")
def blocks(paper):
    return json.loads((paper / "blocks.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def flat(paper):
    return (paper / "blocks.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skeleton():
    return json.loads((EXPECTED / "skeleton.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest():
    return json.loads(
        (EXPECTED / "bundle" / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def crops():
    return json.loads((EXPECTED / "crops.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def text():
    return (EXPECTED / "bundle" / "text.md").read_text(encoding="utf-8")


def _normalised(markdown):
    """text.md as one line of plain characters, for substring checks.

    Line wrapping and emphasis markers are the only differences between a
    printed line and the same words in the bundle, so both are removed
    before a printed line is looked for.
    """
    return " ".join(markdown.replace("*", "").split())


def _lines(role=None, page=None):
    """The example's printed lines, filtered."""
    return [line
            for sheet in builder.layout()
            for line in sheet.lines
            if (role is None or line.role in role)
            and (page is None or line.page == page)]


# --------------------------------------------------- the PDF the tools read

def test_the_example_builds_the_pages_it_claims(paper, blocks):
    assert blocks["page_count"] == builder.PAGE_COUNT == 3
    assert sorted((paper / "pages").glob("page_*.png")) == [
        paper / "pages" / f"page_{n:02d}.png" for n in (1, 2, 3)]


def test_every_printed_line_reaches_the_dump(flat):
    # The text layer is character-exact, so each line the builder prints
    # comes back verbatim. Cells sharing a baseline arrive one per line
    # inside their block, which is the flattening quality.md catalogues.
    for line in _lines():
        assert line.text in flat, f"missing from the dump: {line.text!r}"


def test_the_invented_strings_are_all_the_paper_prints(flat):
    # The title is printed over two lines, so the dump holds it broken;
    # everything looked for here sits on one printed line.
    for invented in ("Reed bed management and heron counts", "Ada Quill",
                     "Institute of Invented Wetlands", "Marrow Levels",
                     "herons", "wardens", "reed bed",
                     "Journal of Invented Wetlands"):
        assert invented in flat


def test_the_emphasis_runs_come_from_real_font_flags(blocks):
    # Every italic and bold piece the builder sets in a base 14 italic or
    # bold font must come back as an emphasis run, and nothing else may.
    expected = sorted((STYLES[font], text.strip())
                      for line in _lines()
                      for text, font in line.pieces
                      if font in STYLES and text.strip())
    found = sorted((run["style"], run["text"])
                   for block in blocks["blocks"]
                   for run in block.get("emphasis", []))
    assert found == expected
    # The runs the walk has to carry into text.md, stated literally.
    assert ("italic", "et al.") in found
    assert ("italic", "p") in found
    assert ("italic", "t") in found
    assert ("bold", "3. Results") in found


def test_the_line_break_hyphen_survives_unhealed(flat):
    # The dump keeps the artefact; healing it is the walk's job, and
    # text.md is where the healed form has to appear.
    assert "compart-\nments," in flat


def test_the_furniture_repeats_on_every_page(flat, blocks):
    assert flat.count(builder.RUNNING_HEAD) == builder.PAGE_COUNT
    pages = {block["page"] for block in blocks["blocks"]
             if block["text"] == builder.RUNNING_HEAD}
    assert pages == {1, 2, 3}
    for number in builder.PAGE_NUMBERS:
        assert any(block["text"] == number for block in blocks["blocks"])


def test_the_page_join_falls_mid_sentence():
    # The seam the walk has to carry: page two stops in the middle of a
    # sentence and page three completes it.
    tail = _lines(role=("body",), page=2)[-1].text
    head = _lines(role=("body",), page=3)[0].text
    assert tail == "(t = 3.4, p = 0.02), and the autumn difference was of " \
                   "the opposite sign, a"
    assert head.startswith("reversal the discussion returns to.")
    assert not tail.endswith(".")


# ------------------------------------------------- the crops and the bundle

def _crop_argv(exhibit, paper, bundle):
    render = paper / "pages" / f"page_{exhibit['page']:02d}.png"
    argv = [str(render)]
    for box in exhibit["boxes"]:
        argv += ["--box"] + [str(value) for value in box]
    argv += ["--space"] + [str(value) for value in exhibit["space"]]
    argv += ["--out", str(bundle / "figures" / f"{exhibit['label']}.png")]
    return argv


def test_the_recorded_crops_assemble_a_bundle_that_validates(paper, crops,
                                                             tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "figures").mkdir(parents=True)
    crop = load_tool("crop")
    for exhibit in crops["exhibits"]:
        assert crop.main(_crop_argv(exhibit, paper, bundle)) == 0
        cut = bundle / "figures" / f"{exhibit['label']}.png"
        assert cut.stat().st_size > 0
    shutil.copy(EXPECTED / "bundle" / "text.md", bundle / "text.md")
    shutil.copy(EXPECTED / "bundle" / "manifest.json",
                bundle / "manifest.json")
    shutil.copytree(EXPECTED / "bundle" / "tables", bundle / "tables")
    assert load_tool("validate_bundle").main([str(bundle)]) == 0


def test_each_crop_box_holds_its_exhibit_whole(crops):
    # What no validator can see: the crop covers every printed part of the
    # exhibit, rules and bars included.
    sheets = {sheet.number: sheet for sheet in builder.layout()}
    for exhibit in crops["exhibits"]:
        x0, y0, x1, y1 = exhibit["boxes"][0]
        sheet = sheets[exhibit["page"]]
        for line in sheet.lines:
            if line.role != "exhibit":
                continue
            left, top, right, bottom = builder.line_box(line)
            assert x0 <= left and right <= x1, line
            assert y0 <= top and bottom <= y1, line
        for rule_x0, rule_y0, rule_x1, rule_y1, _width in sheet.rules:
            assert x0 <= rule_x0 and rule_x1 <= x1
            assert y0 <= rule_y0 and rule_y1 <= y1
        for bar_x0, bar_y0, bar_x1, bar_y1, _filled in sheet.bars:
            assert x0 <= bar_x0 and bar_x1 <= x1
            assert y0 <= bar_y0 and bar_y1 <= y1


def test_no_crop_box_reaches_the_paper_s_own_text(crops):
    # The caption lives in text.md, so it must fall outside the crop, and
    # so must every line of prose around the float.
    sheets = {sheet.number: sheet for sheet in builder.layout()}
    for exhibit in crops["exhibits"]:
        x0, y0, x1, y1 = exhibit["boxes"][0]
        for line in sheets[exhibit["page"]].lines:
            if line.role == "exhibit":
                continue
            left, top, right, bottom = builder.line_box(line)
            assert bottom < y0 or top > y1 or right < x0 or left > x1, line


def test_the_crop_boxes_are_recorded_in_the_page_s_own_space(crops, blocks):
    for exhibit in crops["exhibits"]:
        size = next(page for page in blocks["pages"]
                    if page["page"] == exhibit["page"])
        assert exhibit["space"] == [size["width"], size["height"]]
    assert crops["render_dpi"] == 150


# ----------------------------------------------------------- the skeleton

def test_the_skeleton_covers_every_page_with_no_gaps(skeleton, blocks):
    assert skeleton["page_count"] == blocks["page_count"]
    spans = [unit["pages"] for unit in skeleton["units"]]
    covered = set()
    for start, end in spans:
        assert start <= end
        covered.update(range(start, end + 1))
    assert covered == set(range(1, skeleton["page_count"] + 1))
    assert spans[0][0] == 1
    assert spans[-1][1] == skeleton["page_count"]
    for (_, previous_end), (next_start, _) in zip(spans, spans[1:]):
        assert next_start in (previous_end, previous_end + 1)


def test_the_skeleton_units_are_ordered_and_depthed(skeleton):
    indices = [unit["index"] for unit in skeleton["units"]]
    assert indices == list(range(1, len(indices) + 1))
    depths = [unit["depth"] for unit in skeleton["units"]]
    assert depths.count(1) == 1 and depths[0] == 1
    assert set(depths) == {1, 2, 3}
    for unit in skeleton["units"]:
        assert unit["opening_words"] and unit["closing_words"]
        assert unit["kind"] in ("front_matter", "section", "references",
                               "back_matter")


def test_the_skeleton_titles_and_headings_match_the_page(skeleton, text):
    for unit in skeleton["units"]:
        if unit["depth"] == 1:
            assert f"# {unit['title']}" in text
        else:
            assert f"{'#' * unit['depth']} {unit['title']}" in text


def test_the_exhibit_labels_agree_everywhere(skeleton, crops, manifest):
    labels = [exhibit["label"] for exhibit in skeleton["exhibits"]]
    assert labels == [exhibit["label"] for exhibit in crops["exhibits"]]
    assert labels == [exhibit["label"] for exhibit in manifest["exhibits"]]
    assert labels == ["table_01", "figure_01"]
    for exhibit in skeleton["exhibits"]:
        assert exhibit["pages"] == [crops["exhibits"][
            labels.index(exhibit["label"])]["page"]]


def test_the_reference_count_matches_the_list(skeleton, text):
    entries = [line for line in text.splitlines() if line.startswith("- ")]
    assert len(entries) == skeleton["reference_count"] == 3
    assert sum(1 for entry in entries if "doi:" in entry) == 1


# ------------------------------------------------------------- the bundle

def test_text_md_carries_every_printed_line(text):
    # The omission guard: each line of prose the page prints is in the
    # bundle, healed of its line-break hyphen but otherwise as printed.
    body = _normalised(text)
    for line in _lines(role=PROSE_ROLES):
        printed = line.text.rstrip("-")
        assert printed in body, f"not in text.md: {printed!r}"


def test_text_md_heals_the_hyphen_and_keeps_the_word(text):
    assert "compart-" not in text
    assert "matched compartments, three seasons" in text


def test_text_md_carries_the_emphasis_the_page_prints(text):
    assert "Reeve *et al.* (1998)" in text
    assert "(*p* = 0.03)" in text
    assert "(*t* = 3.4, *p* = 0.02)" in text


def test_text_md_strips_the_furniture(text):
    assert builder.RUNNING_HEAD not in text
    assert builder.DOI_LINE not in text
    printed = {line.strip() for line in text.splitlines()}
    for number in builder.PAGE_NUMBERS:
        assert number not in printed


def test_text_md_leaves_the_exhibits_to_the_crops(text):
    # A table's content, a figure's internal text, and an exhibit footnote
    # all belong to the crop; only the sentinel stands in the text.
    assert builder.TABLE_FOOTNOTE not in text
    assert builder.FIGURE_TITLE not in text
    assert builder.FIGURE_AXIS_LABEL not in text
    for row in builder.TABLE_ROWS:
        assert f"| {row[0]} |" not in text


def test_the_sentinels_stand_where_the_exhibits_are_printed(text, skeleton):
    for exhibit in skeleton["exhibits"]:
        sentinel = f"[{exhibit['printed'].upper()}. {exhibit['caption']}]"
        assert sentinel in text
    # In reading order: the table inside the protocol section, the figure
    # after the results paragraph.
    assert text.index("[TABLE 1.") < text.index("### 2.3 Analysis")
    assert text.index("## 2.2 Counting protocol") < text.index("[TABLE 1.")
    assert text.index("## 3. Results") < text.index("[FIGURE 1.")
    assert text.index("[FIGURE 1.") < text.index("## 4. Discussion")


def test_the_manifest_is_the_paper_s_own_identity(manifest, skeleton):
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["id"] == skeleton["id"]
    assert manifest["title"] == builder.TITLE
    assert manifest["doi"] == builder.DOI
    assert manifest["summary"] == builder.ABSTRACT


def test_the_table_transcription_is_the_printed_table():
    """The committed transcription is the printed table, cell for cell.

    Rebuilt from build_pdf.py's own constants and compared whole rather
    than asked whether each cell appears somewhere. A substring test
    passes on rows reordered, transposed or duplicated, which are exactly
    the faults a transcription exists to rule out, so it would assert
    almost nothing while reading as though it asserted everything.

    Whitespace between tags is normalised and whitespace inside a cell is
    not: how the file is wrapped is nobody's business, and what a cell
    says is entirely the point.
    """
    markup = (EXPECTED / "bundle" / "tables" / "table_01.html").read_text(
        encoding="utf-8")
    assert validate_table_html(markup, "table_01.html") == []
    header = "".join(f'<th scope="col">{cell}</th>'
                     for cell in builder.TABLE_HEADER)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row)
                   + "</tr>" for row in builder.TABLE_ROWS)
    expected = (f"<table><thead><tr>{header}</tr></thead>"
                f"<tbody>{body}</tbody></table>")
    assert re.sub(r">\s+<", "><", markup).strip() == expected
    # Both are printed inside the crop, and both belong elsewhere in the
    # bundle, so transcribing either would put a second copy in front of a
    # consumer. The comparison above already forbids them; these say why.
    assert builder.TABLE_CAPTION not in markup
    assert builder.TABLE_FOOTNOTE not in markup


def test_only_the_table_is_transcribed(manifest):
    """A figure's content is its pixels, so it has no transcription."""
    transcribed = {path.stem for path in
                   (EXPECTED / "bundle" / "tables").iterdir()
                   if path.suffix == ".html"}
    declared = {exhibit["label"] for exhibit in manifest["exhibits"]}
    assert transcribed == {"table_01"}
    assert transcribed < declared


def test_the_manifest_captions_are_the_printed_ones(manifest, skeleton):
    captions = {exhibit["label"]: exhibit["caption"]
                for exhibit in manifest["exhibits"]}
    assert captions["table_01"] == builder.TABLE_CAPTION
    assert captions["figure_01"] == builder.FIGURE_CAPTION
    assert captions == {exhibit["label"]: exhibit["caption"]
                        for exhibit in skeleton["exhibits"]}


def test_the_table_footnote_is_the_manifest_s_notes(manifest, skeleton):
    entries = {exhibit["label"]: exhibit for exhibit in manifest["exhibits"]}
    assert entries["table_01"]["notes"] == builder.TABLE_FOOTNOTE
    assert "notes" not in entries["figure_01"]
    flags = {exhibit["label"]: exhibit["footnote"]
             for exhibit in skeleton["exhibits"]}
    assert flags == {"table_01": True, "figure_01": False}


def test_the_doi_bearing_reference_is_character_exact(text):
    assert f"- {builder.REFERENCES[1]}" in text
    assert "doi:10.5555/invented.1998.0088" in text
    # The en dashes of the page ranges are the paper's own characters.
    assert "88–104" in text
    assert "12–19" in text
