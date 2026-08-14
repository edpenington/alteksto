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

from alteksto.bundle import validate_bundle
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


def test_the_contract_costs_a_consumer_nothing_to_install():
    """A package that only reads and checks bundles depends on this one,
    and gets the standard library and no more.

    Both halves are asserted because either alone would let the promise
    rot: a runtime dependency added to pyproject would land the page stack
    in every consumer's environment, and an import added to bundle.py
    would break a plain install at the one moment it matters. Neither
    fault is visible to a suite that runs with the tools extra installed,
    as this one always does, so both are read off the files.
    """
    declared = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert declared["project"]["dependencies"] == []

    tree = ast.parse((REPO_ROOT / "src" / "alteksto" / "bundle.py")
                     .read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names), sorted(
        imported - set(sys.stdlib_module_names))


def test_the_cli_reports_and_exits_nonzero(tmp_path, capsys):
    tool = load_tool("validate_bundle")
    good = make_bundle(tmp_path / "good")
    bad = tmp_path / "bad"
    bad.mkdir()
    assert tool.main([str(good)]) == 0
    assert tool.main([str(good), str(bad)]) == 1
    err = capsys.readouterr().err
    assert "valid" in err and "manifest.json is missing" in err
