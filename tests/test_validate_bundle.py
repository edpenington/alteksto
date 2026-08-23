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

from alteksto.bundle import figure_files, validate_bundle
from conftest import load_tool

REPO_ROOT = Path(__file__).resolve().parents[1]

PNG_STUB = b"\x89PNG\r\n\x1a\n invented bytes; no check reads pixels"


def make_bundle(root, *, manifest=None, text="# An invented paper\n\nBody.",
                figures=()):
    """A bundle directory; defaults form a minimal valid bundle."""
    if manifest is None:
        manifest = {
            "schema_version": 2,
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


def test_schema_version_must_be_two_and_not_bool(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["schema_version"] = 1
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("schema_version must be 2" in p
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


def test_a_manifest_nested_too_deeply_to_walk_is_still_reported(tmp_path):
    # The duplicate is found at the top of a structure far deeper than the
    # interpreter's recursion limit. Locating it must report, not raise:
    # validate_bundle never raises for a malformed bundle.
    deep = "[" * 5000 + "]" * 5000
    bundle = make_bundle(tmp_path / "b")
    (bundle / "manifest.json").write_text(
        '{"schema_version": 2, "id": "inv-01", "title": "An invented paper", '
        '"id": "inv-02", "exhibits": [], "warden": ' + deep + '}',
        encoding="utf-8")
    problems = validate_bundle(bundle)
    assert any("duplicate key: 'id'" in p for p in problems)


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
