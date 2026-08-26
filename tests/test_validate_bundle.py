"""Tests for the bundle validator against docs/bundle.md.

Every fixture is an invented bundle built in tmp_path. The helper builds
a minimal valid bundle; each test then breaks exactly one rule and
asserts the validator names it.
"""

import ast
import json
import sys
import tomllib
from pathlib import Path

import pytest

from alteksto.bundle import (SCHEMA_VERSION, _walk_objects, figure_files,
                             table_files, validate_bundle,
                             validate_table_html)
from conftest import load_tool

REPO_ROOT = Path(__file__).resolve().parents[1]

PNG_STUB = b"\x89PNG\r\n\x1a\n invented bytes; no check reads pixels"

# A correct transcription: a header row and two body rows, tiling 3 by 2.
# Tests that need a wrong one write it out beside the right one, so what
# the validator is being asked about is on the page.
TABLE_STUB = ("<table><thead><tr><th>Season</th><th>Count</th></tr></thead>"
              "<tbody><tr><td>April</td><td>4.8</td></tr>"
              "<tr><td>July</td><td>2.6</td></tr></tbody></table>")


def make_bundle(root, *, manifest=None, text="# An invented paper\n\nBody.",
                figures=(), tables=None):
    """A bundle directory; defaults form a minimal valid bundle.

    `tables` is a label -> markup map written under tables/. It is not
    derived from `figures` because a transcription is optional exhibit by
    exhibit, and most of what these tests ask about is what happens when
    the two directories disagree.
    """
    if manifest is None:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "id": "inv-01",
            "title": "An invented paper",
            "exhibits": [{"label": label, "caption": f"Caption for {label}"}
                         for label in figures],
        }
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(manifest),
                                        encoding="utf-8")
    if text is not None:
        (root / "text.md").write_text(text, encoding="utf-8")
    if figures:
        (root / "figures").mkdir(exist_ok=True)
        for label in figures:
            (root / "figures" / f"{label}.png").write_bytes(PNG_STUB)
    if tables:
        (root / "tables").mkdir(exist_ok=True)
        for label, markup in tables.items():
            (root / "tables" / f"{label}.html").write_text(markup,
                                                          encoding="utf-8")
    return root


def test_a_minimal_bundle_is_valid(tmp_path):
    assert validate_bundle(make_bundle(tmp_path / "b")) == []


def test_a_bundle_with_exhibits_is_valid(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01", "figure_01"))
    assert validate_bundle(bundle) == []


def test_a_missing_directory_is_one_problem(tmp_path):
    problems = validate_bundle(tmp_path / "absent")
    assert len(problems) == 1 and "does not exist" in problems[0]


def test_missing_manifest_and_text_both_reported(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    problems = validate_bundle(root)
    assert any("manifest.json is missing" in p for p in problems)
    assert any("text.md is missing" in p for p in problems)


def test_unknown_manifest_key_rejected(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["provenance"] = "not allowed"
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("unknown key: 'provenance'" in p
               for p in validate_bundle(bundle))


def test_schema_version_must_be_the_format_s_own_and_not_bool(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["schema_version"] = SCHEMA_VERSION - 1
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(f"schema_version must be {SCHEMA_VERSION}" in p
               for p in validate_bundle(bundle))
    manifest["schema_version"] = True
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("must be an integer" in p for p in validate_bundle(bundle))


@pytest.mark.parametrize("bad_id, expected", [
    ("has space", "must match"),
    ("a/b", "must match"),
    ("..", "at least one letter or digit"),
    ("", "non-empty"),
])
def test_bad_ids_are_rejected(tmp_path, bad_id, expected):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["id"] = bad_id
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(expected in p for p in validate_bundle(bundle))


@pytest.mark.parametrize("key", ["schema_version", "id", "title", "exhibits"])
def test_every_required_manifest_key_is_required(tmp_path, key):
    """Each of the four, named as missing rather than defaulted.

    A consumer reads these straight off the manifest once the verdict is in
    (`manifest["id"]` names its output directory, `manifest["exhibits"]` is
    the declaration it walks), so a key this stops requiring does not become
    an absent value downstream: it becomes a crash after the verdict said the
    bundle was fine.
    """
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    del manifest[key]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(f"missing required key: '{key}'" in p
               for p in validate_bundle(bundle))


def test_an_exhibit_entry_needs_a_label(tmp_path):
    # The other key a consumer indexes directly, one entry down.
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"caption": "Table 1."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("missing required key: 'label'" in p
               for p in validate_bundle(bundle))


@pytest.mark.parametrize("key, value, expected", [
    ("doi", 10.5555, "must be a string"),
    ("summary", ["not", "a", "string"], "must be a string"),
    ("summary", "   ", "non-empty"),
    ("title", "  ", "non-empty"),
    ("id", "", "non-empty"),
])
def test_a_present_value_is_still_typed(tmp_path, key, value, expected):
    # Optional does not mean unchecked. A consumer that reads `doi` as a
    # string, or shows `summary` to a model, gets a number or a list here
    # unless this holds.
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest[key] = value
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(key in p and expected in p for p in validate_bundle(bundle))


def test_an_exhibit_label_is_filename_and_citation_safe(tmp_path):
    """The label rule, checked where the cross-check cannot mask it.

    The crop is on disk under the offending name, so the declaration and the
    directory agree and the only thing left to object to is the label itself.
    It is a `figures/*.png` stem and the token a consumer cites, so a space,
    a separator or a pipe in it breaks both uses.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "figures").mkdir(exist_ok=True)
    (bundle / "figures" / "Table 1 | fleet.png").write_bytes(PNG_STUB)
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "Table 1 | fleet", "caption": "T1."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    problems = validate_bundle(bundle)
    assert any("must match" in p and "Table 1 | fleet" in p for p in problems)


def test_a_dotted_id_with_an_alphanumeric_is_allowed(tmp_path):
    # The positive half of the id rule: the character class admits dots, and
    # only an id with no letter or digit at all is refused.
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["id"] = "demo.001"
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert validate_bundle(bundle) == []


@pytest.mark.parametrize("entry, expected", [
    ({"label": "table_01", "caption": "  "}, "'caption' must be a non-empty"),
    ({"label": "  ", "caption": "T1."}, "'label' must be a non-empty"),
    ({"label": 1, "caption": "T1."}, "'label' must be a string"),
    ({"label": "table_01", "caption": ["T1."]}, "'caption' must be a string"),
])
def test_an_exhibit_entry_carries_non_empty_strings(tmp_path, entry, expected):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [entry]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(expected in p for p in validate_bundle(bundle))


@pytest.mark.parametrize("exhibits, expected", [
    ({"table_01": "Table 1."}, "'exhibits' must be a list"),
    (["table_01"], "exhibits[0] must be an object"),
])
def test_exhibits_is_a_list_of_objects(tmp_path, exhibits, expected):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = exhibits
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(expected in p for p in validate_bundle(bundle))


def test_a_malformed_exhibits_block_is_not_cross_checked(tmp_path):
    # The shape problem is the thing to fix. Cross-checking a declaration
    # that does not parse against the directory would bury it under derived
    # noise about crops nobody declared.
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "table_01"}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    problems = validate_bundle(bundle)
    assert any("missing required key: 'caption'" in p for p in problems)
    assert not any("not declared" in p for p in problems)


@pytest.mark.parametrize("raw, expected", [
    ("{not json", "not valid JSON"),
    ('["a", "list"]', "must be a JSON object"),
])
def test_a_manifest_that_is_not_an_object_is_one_problem(tmp_path, raw,
                                                         expected):
    # Reported, not raised: a consumer takes the verdict and reads the
    # manifest afterwards, so a file that cannot be read as an object has to
    # come back as a problem rather than as an exception out of the parse.
    bundle = make_bundle(tmp_path / "b")
    (bundle / "manifest.json").write_text(raw, encoding="utf-8")
    problems = validate_bundle(bundle)
    assert len(problems) == 1 and expected in problems[0]


def test_a_duplicated_manifest_key_is_rejected(tmp_path):
    """The manifest is written as text, because `json.dumps` cannot
    produce the file this rule is about: a duplicate key exists only in
    the bytes, and a Python dict has already lost it.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "manifest.json").write_text(
        '{"schema_version": 2, "id": "inv-01", "title": "An invented paper", '
        '"id": "inv-02", "exhibits": []}', encoding="utf-8")
    problems = validate_bundle(bundle)
    assert len(problems) == 1
    assert "manifest.json has a duplicate key: 'id'" in problems[0]


def test_a_duplicated_key_inside_an_exhibit_is_located(tmp_path):
    # The hook runs on every object in the document, not just the root, and
    # the problem says which entry, as every other exhibit problem does.
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "manifest.json").write_text(
        '{"schema_version": 2, "id": "inv-01", "title": "An invented paper", '
        '"exhibits": [{"label": "table_01", "caption": "Herons at dawn", '
        '"caption": "Herons at dusk"}]}', encoding="utf-8")
    problems = validate_bundle(bundle)
    assert len(problems) == 1
    assert ("manifest.json exhibits[0] has a duplicate key: 'caption'"
            in problems[0])


def test_every_duplicate_is_named_and_the_rest_is_still_checked(tmp_path):
    """A duplicate hides neither the ones after it nor anything else.

    Two reasons. The parser finishes an exhibit entry before the object
    holding it, so reporting the first duplicate it finds would name the
    caption and never reach the id, the key this rule exists for. And the
    file's other problems are still true of it, so an author fixing the
    manifest sees them in one run of gate 1 rather than one per run.

    The id is written three times to pin that a key is one problem however
    often it repeats.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "manifest.json").write_text(
        '{"schema_version": 2, "id": "inv-01", "id": "inv-02", '
        '"id": "inv-03", "warden": "not a manifest key", '
        '"exhibits": [{"label": "table_01", "caption": "Herons at dawn", '
        '"caption": "Herons at dusk"}]}', encoding="utf-8")
    problems = validate_bundle(bundle)
    named = [p for p in problems if "duplicate key" in p]
    assert len(named) == 2
    assert "manifest.json has a duplicate key: 'id'" in named[0]
    assert ("manifest.json exhibits[0] has a duplicate key: 'caption'"
            in named[1])
    assert any("unknown key: 'warden'" in p for p in problems)
    assert any("missing required key: 'title'" in p for p in problems)


def test_a_repeated_key_is_not_confused_with_a_repeated_value(tmp_path):
    # A guard against a false positive, so it passes with or without the
    # rule: two exhibits carrying the same caption text is ordinary (two
    # panels of one figure often print alike), and the rule is about one
    # object carrying one key twice.
    bundle = make_bundle(tmp_path / "b", figures=("table_01", "table_02"))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [
        {"label": "table_01", "caption": "Heron counts by reed bed"},
        {"label": "table_02", "caption": "Heron counts by reed bed"},
    ]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert validate_bundle(bundle) == []


def _deeply_nested_manifest(root, depth):
    bundle = make_bundle(root)
    (bundle / "manifest.json").write_text(
        '{"schema_version": 2, "id": "inv-01", "title": "An invented paper", '
        '"id": "inv-02", "exhibits": [], "warden": '
        + "[" * depth + "]" * depth + '}',
        encoding="utf-8")
    return bundle


def test_the_walk_carries_its_own_queue_rather_than_the_stack():
    """Depth costs the walk nothing, which is why it has a queue.

    Asked of `_walk_objects` directly and on a structure built in Python
    rather than parsed, because through `validate_bundle` the question
    cannot be asked at all: json's scanner is itself bounded by the
    recursion limit on some supported interpreters, so a manifest deeper
    than that limit never reaches the walk, and raising the limit to get
    it there would raise it for a recursive walk too and prove nothing.
    """
    deep = []
    cursor = deep
    for _ in range(5000):
        nested = []
        cursor.append(nested)
        cursor = nested
    assert sys.getrecursionlimit() < 5000
    found = list(_walk_objects({"warden": deep}, "manifest.json"))
    assert found and found[0][0] == "manifest.json"


def test_a_duplicate_is_located_inside_a_nested_manifest(tmp_path):
    bundle = _deeply_nested_manifest(tmp_path / "b", 50)
    problems = validate_bundle(bundle)
    assert any("duplicate key: 'id'" in p for p in problems)


def test_a_manifest_too_deep_for_the_parser_reports_rather_than_raises(
        tmp_path):
    # Deeper than json's own scanner tolerates on some supported
    # interpreters, and how deep that is belongs to the interpreter rather
    # than to this format. So the assertion is the one that holds on all of
    # them: problems come back, and nothing is raised. Which problems
    # depends on whether the parse finished, and the duplicate can only be
    # named when it did.
    bundle = _deeply_nested_manifest(tmp_path / "b", 5000)
    problems = validate_bundle(bundle)
    assert problems
    assert any("duplicate key: 'id'" in p or "nested too deeply" in p
               for p in problems), problems


def test_exhibit_entries_take_label_caption_and_optional_notes(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "table_01",
                             "caption": "Caption",
                             "notes": "Invented footnote: counts exclude "
                                      "the pilot pond."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert validate_bundle(bundle) == []
    manifest["exhibits"] = [{"label": "table_01",
                             "caption": "Caption",
                             "footnote": "not allowed"}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("unknown key: 'footnote'" in p
               for p in validate_bundle(bundle))
    manifest["exhibits"] = [{"label": "table_01"}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("missing required key: 'caption'" in p
               for p in validate_bundle(bundle))


def test_empty_notes_is_a_mistake_not_a_signal(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "table_01", "caption": "Caption",
                             "notes": "   "}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("'notes' must be a non-empty string" in p
               for p in validate_bundle(bundle))


def test_duplicate_labels_are_rejected(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [
        {"label": "table_01", "caption": "First"},
        {"label": "table_01", "caption": "Second"},
    ]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("more than once" in p for p in validate_bundle(bundle))


def test_empty_text_md_is_invalid(tmp_path):
    bundle = make_bundle(tmp_path / "b", text="   \n")
    assert any("text.md is empty" in p for p in validate_bundle(bundle))


def test_cross_check_both_directions(tmp_path):
    # Declared but no PNG.
    bundle = make_bundle(tmp_path / "declared", figures=("table_01",))
    (bundle / "figures" / "table_01.png").unlink()
    assert any("no figures/table_01.png" in p
               for p in validate_bundle(bundle))
    # PNG but not declared.
    bundle2 = make_bundle(tmp_path / "stray")
    (bundle2 / "figures").mkdir()
    (bundle2 / "figures" / "figure_09.png").write_bytes(PNG_STUB)
    assert any("figure_09.png is not declared" in p
               for p in validate_bundle(bundle2))


def test_figures_rejects_non_png_and_subdirs(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "figures" / "notes.txt").write_text("stray")
    (bundle / "figures" / "sub").mkdir()
    problems = validate_bundle(bundle)
    assert any("non-png" in p for p in problems)
    assert any("subdirectory" in p for p in problems)


def test_hidden_files_in_figures_are_ignored(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "figures" / ".DS_Store").write_bytes(b"junk")
    assert validate_bundle(bundle) == []


def test_extra_files_beside_the_contract_are_ignored(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    (bundle / "paperwork.txt").write_text("allowed")
    assert validate_bundle(bundle) == []


class TestFigureFiles:
    """The enumeration a consumer reads instead of writing its own."""

    def test_it_answers_label_to_path_in_label_order(self, tmp_path):
        bundle = make_bundle(tmp_path / "b",
                             figures=("table_02", "fig_01", "table_01"))
        found = figure_files(bundle)
        assert list(found) == ["fig_01", "table_01", "table_02"]
        assert found["fig_01"] == bundle / "figures" / "fig_01.png"

    def test_it_skips_what_validation_skips(self, tmp_path):
        # Hidden OS metadata is not an asset, and the two readings agree
        # about that: a consumer that enumerated it would carry a label no
        # check ever saw.
        bundle = make_bundle(tmp_path / "b", figures=("table_01",))
        (bundle / "figures" / ".DS_Store").write_bytes(b"junk")
        assert validate_bundle(bundle) == []
        assert list(figure_files(bundle)) == ["table_01"]

    def test_no_figures_directory_is_no_crops(self, tmp_path):
        bundle = make_bundle(tmp_path / "b")
        assert not (bundle / "figures").exists()
        assert figure_files(bundle) == {}

    def test_it_refuses_nothing_itself(self, tmp_path):
        # A stray file is validate_bundle's to reject. This reports the
        # crops beside it rather than raising, so a caller that has already
        # taken the verdict gets what it came for.
        bundle = make_bundle(tmp_path / "b", figures=("table_01",))
        (bundle / "figures" / "notes.txt").write_text("x", encoding="utf-8")
        assert any("non-png" in p for p in validate_bundle(bundle))
        assert list(figure_files(bundle)) == ["table_01"]

    def test_a_png_suffix_is_read_case_insensitively(self, tmp_path):
        # The case this function exists to keep in one place: a crop saved as
        # .PNG is a crop, and validation and enumeration have to agree that
        # its label is the stem. A consumer with its own reading would see
        # either a stray file or no crop at all, for a bundle that is valid.
        bundle = make_bundle(tmp_path / "b", figures=("table_01",))
        crop = bundle / "figures" / "table_01.png"
        data = crop.read_bytes()
        crop.unlink()
        (bundle / "figures" / "table_01.PNG").write_bytes(data)
        assert validate_bundle(bundle) == []
        assert list(figure_files(bundle)) == ["table_01"]


# ------------------------------------------------------- tables/

# A table shape that must pass, and the printed table it stands for. Every
# one of these is a real arrangement a journal prints, and the suite is as
# interested in these as in the broken ones below: a check with no negative
# cases eventually refuses everything, and the shapes most likely to be
# refused by accident are the awkward ones this format exists to carry.
CORRECT_TABLES = {
    "a plain grid": TABLE_STUB,
    "rows directly in table, no row groups":
        "<table><tr><th>Season</th><th>Count</th></tr>"
        "<tr><td>April</td><td>4.8</td></tr></table>",
    "a spanning group header over a rowspan stub":
        '<table><thead>'
        '<tr><th rowspan="2" scope="col">Study</th>'
        '<th colspan="2" scope="colgroup">Intervention</th></tr>'
        '<tr><th scope="col">n</th><th scope="col">Mean</th></tr></thead>'
        '<tbody><tr><td>Ashby 2019</td><td>142</td><td>12.4</td></tr>'
        '</tbody></table>',
    "an empty cell, which is a value the paper prints":
        "<table><tr><th>Study</th><th>Mean</th></tr>"
        "<tr><td>Brune 2021</td><td></td></tr></table>",
    "a footnote marker as a superscript":
        "<table><tr><th>Study</th><th>n</th></tr>"
        "<tr><td>Brune 2021<sup>a</sup></td><td>2,089</td></tr></table>",
    "emphasis and a line break inside a cell":
        "<table><tr><th>Outcome</th><th>Result</th></tr>"
        "<tr><td><em>N</em> = 1,227</td>"
        "<td>12.4<br>(3.1)</td></tr></table>",
    "a row header with scope=row":
        '<table><tr><th scope="col">Season</th><th scope="col">n</th></tr>'
        '<tr><th scope="row">April</th><td>142</td></tr></table>',
    "a continuation page, repeating its header and carrying one row":
        "<table><thead><tr><th>Study</th><th>n</th></tr></thead>"
        "<tbody><tr><td>Calder 2023</td><td>310</td></tr></tbody></table>",
    "one cell, which is all some exhibits are":
        "<table><tr><td>None reported</td></tr></table>",
    "a rowspan reaching the last row, leaving that row one cell":
        '<table><tr><td rowspan="2">Cut</td><td>4.8</td></tr>'
        '<tr><td>3.1</td></tr></table>',
}


@pytest.mark.parametrize("shape", sorted(CORRECT_TABLES))
def test_a_correct_transcription_passes_clean(tmp_path, shape):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": CORRECT_TABLES[shape]})
    assert validate_bundle(bundle) == []


@pytest.mark.parametrize("markup, expected", [
    # The grid. Each of these reads plausibly and puts a value in the wrong
    # column, which is the whole reason the tiling is checked.
    ('<table><tr><th>Study</th><th colspan="2">Cut</th></tr>'
     '<tr><td>Ashby</td><td>4.8</td></tr></table>',
     "leaves row 1 column 2 uncovered"),
    ('<table><tr><th>Study</th><th>Cut</th><th>Uncut</th></tr>'
     '<tr><td>Ashby</td><td>4.8</td></tr></table>',
     "leaves row 1 column 2 uncovered"),
    # A rowspan one too long does not collide: the next row's cells skip
    # the position it claimed and the row runs one wide, so the fault
    # surfaces as a hole. An overlap needs a span that starts on a free
    # position and then reaches across a claimed one.
    ('<table><tr><td rowspan="2">Cut</td><td>4.8</td></tr>'
     '<tr><td>3.1</td><td>2.4</td></tr></table>',
     "leaves row 0 column 2 uncovered"),
    ('<table><tr><td>a</td><td rowspan="2">b</td></tr>'
     '<tr><td colspan="3">c</td></tr></table>',
     "two cells covering row 1 column 1"),
    # The whitelist.
    ("<table><caption>Table 1.</caption><tr><td>a</td></tr></table>",
     "the exhibit's caption is carried by text.md"),
    ('<table><tfoot><tr><td>Total</td></tr></tfoot></table>',
     "the exhibit's printed footnote is the manifest's 'notes'"),
    ("<table><tr><td><table><tr><td>a</td></tr></table></td></tr></table>",
     "holds more than one <table>"),
    ("<table><tr><td>a</td></tr></table><table><tr><td>b</td></tr></table>",
     "holds more than one <table>"),
    ("<div><table><tr><td>a</td></tr></table></div>",
     "uses <div>, which a transcription may not carry"),
    ("<!DOCTYPE html><table><tr><td>a</td></tr></table>",
     "carries a document declaration"),
    ("<table><!-- checked --><tr><td>a</td></tr></table>",
     "carries an HTML comment"),
    # Attributes.
    ('<table><tr><td class="num">a</td></tr></table>',
     "gives <td> the attribute 'class'"),
    ('<table><tr><td style="text-align:right">a</td></tr></table>',
     "gives <td> the attribute 'style'"),
    ('<table><tr colspan="2"><td>a</td></tr></table>',
     "gives <tr> the attribute 'colspan'"),
    ('<table><tr><td scope="row">a</td></tr></table>',
     "gives <td> the attribute 'scope'"),
    ('<table><tr><th scope="middle">a</th></tr></table>',
     "scope='middle'"),
    ('<table><tr><td colspan="2" colspan="3">a</td><td>b</td></tr></table>',
     "repeats the 'colspan' attribute"),
    # Spans that are not spans.
    ('<table><tr><td colspan="0">a</td></tr></table>',
     "colspan='0'"),
    ('<table><tr><td colspan="two">a</td></tr></table>',
     "colspan='two'"),
    ('<table><tr><td colspan="-1">a</td></tr></table>',
     "colspan='-1'"),
    ('<table><tr><td rowspan="5000">a</td></tr></table>',
     "beyond the 1000 this format allows"),
    # Structure and balance.
    ("<table><tr><td>a</td></tr>", "never closes <table>"),
    ("<table><tr><td>a</tr></td></table>",
     "closes </tr> while <td> is still open"),
    ("<table><tr><td>a</td></tr>oops</table>",
     "has text outside any cell: 'oops'"),
    ("<table><td>a</td></table>", "opens <td> inside <table>"),
    ("<table><tr><td>a</td></tr><td>b</td></table>",
     "opens <td> inside <table>"),
    ("<table><thead><td>a</td></thead></table>",
     "opens <td> inside <thead>"),
    ("<table><tr><td/></tr></table>", "writes <td/> in the self-closing"),
    ("<table></table>", "has no cells"),
    ("<table><tr><td>a</td></tr><tr></tr></table>",
     "has no cells in row 1"),
    ("not a table at all", "contains no <table>"),
    ("<sup>a</sup>", "uses <sup> outside any cell"),
])
def test_a_broken_transcription_is_named(tmp_path, markup, expected):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": markup})
    problems = validate_bundle(bundle)
    assert any(expected in problem for problem in problems), problems
    assert all(problem.startswith("tables/table_01.html")
               for problem in problems), problems


def test_an_empty_transcription_is_not_a_transcription(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": "   \n"})
    assert any("is empty" in p for p in validate_bundle(bundle))


def test_a_holed_grid_reports_its_position_and_stops_counting(tmp_path):
    """Five holes are named and the rest are counted.

    A table that lost its first column holes every row, and a hundred
    lines saying so would bury whatever else the file gets wrong.
    """
    rows = "".join("<tr><td>a</td></tr>" for _ in range(12))
    markup = f'<table><tr><th colspan="2">Wide</th></tr>{rows}</table>'
    problems = validate_bundle(make_bundle(tmp_path / "b",
                                           figures=("table_01",),
                                           tables={"table_01": markup}))
    named = [p for p in problems if "uncovered" in p and "further" not in p]
    assert len(named) == 5
    assert any("leaves 7 further positions uncovered" in p
               for p in problems), problems


def test_a_transcription_is_optional_exhibit_by_exhibit(tmp_path):
    bundle = make_bundle(tmp_path / "b",
                         figures=("table_01", "figure_01"),
                         tables={"table_01": TABLE_STUB})
    assert validate_bundle(bundle) == []


def test_a_bundle_may_transcribe_nothing(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    assert validate_bundle(bundle) == []
    assert table_files(bundle) == {}


def test_a_transcription_needs_a_declared_exhibit(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB,
                                 "table_09": TABLE_STUB})
    problems = validate_bundle(bundle)
    assert any("tables/table_09.html is not declared" in p
               for p in problems), problems
    assert not any("table_01" in p for p in problems), problems


def test_a_transcription_never_stands_in_for_a_crop(tmp_path):
    """A transcribed exhibit still owes its PNG.

    The figures cross-check is what enforces it, so this is a test of the
    two rules together: nothing reaches a reader as text alone.
    """
    bundle = make_bundle(tmp_path / "b", tables={"table_01": TABLE_STUB})
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "table_01", "caption": "A table."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("there is no figures/table_01.png" in p
               for p in validate_bundle(bundle))


def test_tables_rejects_non_html_and_subdirs(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB})
    (bundle / "tables" / "notes.txt").write_text("stray", encoding="utf-8")
    (bundle / "tables" / "old").mkdir()
    problems = validate_bundle(bundle)
    assert any("contains a non-html file" in p for p in problems), problems
    assert any("contains a subdirectory" in p for p in problems), problems


def test_hidden_files_in_tables_are_ignored(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB})
    (bundle / "tables" / ".DS_Store").write_bytes(b"\x00")
    assert validate_bundle(bundle) == []


def test_tables_that_is_not_a_directory_is_one_problem(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "tables").write_text("not a directory", encoding="utf-8")
    problems = validate_bundle(bundle)
    assert any("tables exists but is not a directory" in p
               for p in problems), problems


def test_a_transcription_must_be_utf8(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB})
    (bundle / "tables" / "table_01.html").write_bytes(b"<table>\xff</table>")
    assert any("could not be read as UTF-8" in p
               for p in validate_bundle(bundle))


class TestTableFiles:
    """`table_files` is the directory's reading, and consumers use it."""

    def test_it_maps_label_to_path_sorted(self, tmp_path):
        bundle = make_bundle(tmp_path / "b",
                             figures=("table_02", "table_01"),
                             tables={"table_02": TABLE_STUB,
                                     "table_01": TABLE_STUB})
        found = table_files(bundle)
        assert list(found) == ["table_01", "table_02"]
        assert found["table_01"].name == "table_01.html"

    def test_an_absent_directory_is_no_transcriptions(self, tmp_path):
        assert table_files(make_bundle(tmp_path / "b")) == {}

    def test_it_skips_dotfiles_and_other_suffixes(self, tmp_path):
        bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                             tables={"table_01": TABLE_STUB})
        (bundle / "tables" / ".DS_Store").write_bytes(b"\x00")
        (bundle / "tables" / "notes.txt").write_text("x", encoding="utf-8")
        assert list(table_files(bundle)) == ["table_01"]


def test_validate_table_html_is_the_rule_a_tool_can_reuse():
    """The transcription rule is public, and it is the same rule.

    `tools/render_table.py` refuses what the format refuses by calling
    this, rather than forming its own opinion of what a table is. If this
    ever stops being importable the tool grows a second definition, which
    is the drift the function exists to prevent.
    """
    assert validate_table_html(TABLE_STUB, "t.html") == []
    problems = validate_table_html("<p>not a table</p>", "t.html")
    assert problems and all(p.startswith("t.html") for p in problems)


def test_the_contract_costs_a_consumer_nothing_to_install():
    """A package that only reads and checks bundles depends on this one,
    and gets the standard library and no more.

    Both halves are asserted because either alone would let the promise
    rot: a runtime dependency added to pyproject would land the page stack
    in every consumer's environment, and an import added on the path to
    `alteksto.bundle` would break a plain install at the one moment it
    matters. Neither fault is visible to a suite that runs with the tools
    extra installed, as this one always does, so both are read off the
    files.

    The path is BOTH files an importer executes, `__init__.py` and then
    `bundle.py`, and a relative import counts: `from . import workdir`
    reaches pymupdf as surely as importing it by name, and is the shape a
    refactor is most likely to introduce.

    Reading the source is the cheap guard, run on every change. The
    expensive one is real: the `contract-is-installable-alone` job in CI
    installs the built wheel where the page stack genuinely is not present
    and validates a bundle there.
    """
    declared = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert declared["project"]["dependencies"] == []

    package = REPO_ROOT / "src" / "alteksto"
    for name in ("__init__.py", "bundle.py"):
        tree = ast.parse((package / name).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    # A relative import: the module it names is a sibling in
                    # this package, and what that sibling imports is not this
                    # file's to promise. `workdir` opens PDFs.
                    imported.update(a.name for a in node.names)
                    if node.module:
                        imported.add(node.module.split(".")[0])
                else:
                    imported.add(node.module.split(".")[0])
        assert imported <= set(sys.stdlib_module_names), (
            name, sorted(imported - set(sys.stdlib_module_names)))


def test_the_cli_reports_and_exits_nonzero(tmp_path, capsys):
    tool = load_tool("validate_bundle")
    good = make_bundle(tmp_path / "good")
    bad = tmp_path / "bad"
    bad.mkdir()
    assert tool.main([str(good)]) == 0
    assert tool.main([str(good), str(bad)]) == 1
    err = capsys.readouterr().err
    assert "valid" in err and "manifest.json is missing" in err
