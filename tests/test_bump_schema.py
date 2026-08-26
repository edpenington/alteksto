"""Offline tests for tools/bump_schema.py on invented bundles.

The tool moves a bundle's declared version to the one this repository now
enforces. What is asserted here is that it moves that integer and nothing
else, that it says so honestly when a bundle needs more than a version
bump, and that it refuses to guess at a manifest that is not the shape it
expects.
"""

import json

import pytest

from alteksto.bundle import SCHEMA_VERSION, validate_bundle
from conftest import load_tool

PNG_STUB = b"\x89PNG\r\n\x1a\n invented bytes; no check reads pixels"
OLD = SCHEMA_VERSION - 1


@pytest.fixture(scope="session")
def bump_tool():
    return load_tool("bump_schema")


def make_old_bundle(root, *, version=OLD, raw=None, figures=("table_01",)):
    """A bundle valid under `version`, written as a human would write it."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "text.md").write_text("# An invented paper\n\nBody.\n",
                                  encoding="utf-8")
    if figures:
        (root / "figures").mkdir(exist_ok=True)
        for label in figures:
            (root / "figures" / f"{label}.png").write_bytes(PNG_STUB)
    if raw is None:
        exhibits = ",\n    ".join(
            f'{{"label": "{label}", "caption": "Caption for {label}."}}'
            for label in figures)
        raw = (f'{{\n  "schema_version" : {version},\n'
               f'  "id": "inv-01",\n'
               f'  "title": "A paper with an accent: café",\n'
               f'  "exhibits": [\n    {exhibits}\n  ]\n}}\n')
    (root / "manifest.json").write_text(raw, encoding="utf-8")
    return root


def test_it_moves_the_integer_and_nothing_else(bump_tool, tmp_path):
    """Textually, not by reserialising.

    A round trip through a JSON library would re-indent the whole file and
    escape the accent, changing bytes far beyond the one value that had to
    move. Those bytes are the paper's identity to a consumer that hashes
    them, and the diff is what a human reviews.
    """
    bundle = make_old_bundle(tmp_path / "b")
    before = (bundle / "manifest.json").read_text(encoding="utf-8")
    assert bump_tool.main([str(bundle)]) == 0
    after = (bundle / "manifest.json").read_text(encoding="utf-8")
    assert after == before.replace(f'"schema_version" : {OLD}',
                                   f'"schema_version" : {SCHEMA_VERSION}')
    # The spacing the author chose, and the accent, both survive.
    assert f'"schema_version" : {SCHEMA_VERSION}' in after
    assert "café" in after
    assert validate_bundle(bundle) == []


def test_a_bumped_bundle_validates(bump_tool, tmp_path):
    bundle = make_old_bundle(tmp_path / "b")
    assert validate_bundle(bundle) != []  # only because of the version
    assert bump_tool.main([str(bundle)]) == 0
    assert validate_bundle(bundle) == []


def test_a_bundle_already_at_the_version_is_left_alone(bump_tool, tmp_path,
                                                       capsys):
    bundle = make_old_bundle(tmp_path / "b", version=SCHEMA_VERSION)
    before = (bundle / "manifest.json").read_bytes()
    assert bump_tool.main([str(bundle)]) == 0
    assert (bundle / "manifest.json").read_bytes() == before
    assert f"already at {SCHEMA_VERSION}" in capsys.readouterr().out


def test_a_dry_run_writes_nothing(bump_tool, tmp_path, capsys):
    bundle = make_old_bundle(tmp_path / "b")
    before = (bundle / "manifest.json").read_bytes()
    assert bump_tool.main([str(bundle), "--dry-run"]) == 0
    assert (bundle / "manifest.json").read_bytes() == before
    assert f"would move {OLD} -> {SCHEMA_VERSION}" in capsys.readouterr().out


def test_recurse_walks_a_directory_of_bundles(bump_tool, tmp_path, capsys):
    root = tmp_path / "bundles"
    for name in ("R0045", "R0126", "R0214"):
        make_old_bundle(root / name)
    (root / ".DS_Store").parent.mkdir(parents=True, exist_ok=True)
    (root / ".hidden").mkdir()
    assert bump_tool.main([str(root), "--recurse"]) == 0
    out = capsys.readouterr().out
    assert out.count(f"{OLD} -> {SCHEMA_VERSION}") == 3
    assert ".hidden" not in out


def test_a_bundle_needing_more_than_a_bump_is_reported(bump_tool, tmp_path,
                                                       capsys):
    """The whole point of validating afterwards.

    A version bump is a migration only while the new version is a pure
    addition. When it is not, the integer moves and the bundle is still
    refused, which is the loud answer rather than a bundle declaring a
    conformance it does not have.
    """
    bundle = make_old_bundle(tmp_path / "b", figures=())
    raw = json.dumps({"schema_version": OLD, "id": "inv-01", "title": "T",
                      "exhibits": [{"label": "gone", "caption": "No png."}]})
    (bundle / "manifest.json").write_text(raw, encoding="utf-8")
    assert bump_tool.main([str(bundle)]) == 1
    err = capsys.readouterr().err
    assert "there is no figures/gone.png" in err
    assert "need more than a version bump" in err


@pytest.mark.parametrize("raw, expected", [
    ('{"id": "inv-01"}', "declares no schema_version"),
    ('{"schema_version": true, "id": "a"}', "is bool, not an integer"),
    ('{"schema_version": "2", "id": "a"}', "is str, not an integer"),
    ('{"schema_version": 2, "schema_version": 2, "id": "a"}',
     "writes schema_version 2 times"),
    ('not json at all', "is not valid JSON"),
    ('[1, 2, 3]', "must be a JSON object"),
])
def test_a_manifest_it_cannot_read_is_refused_not_guessed_at(bump_tool,
                                                             tmp_path,
                                                             capsys, raw,
                                                             expected):
    bundle = make_old_bundle(tmp_path / "b", raw=raw)
    before = (bundle / "manifest.json").read_bytes()
    assert bump_tool.main([str(bundle)]) == 1
    assert (bundle / "manifest.json").read_bytes() == before
    assert expected in capsys.readouterr().err


def test_a_schema_version_inside_a_string_is_not_a_declaration(bump_tool,
                                                               tmp_path):
    """A title may talk about schema_version without being one.

    Inside a JSON string a quote is escaped, so the bytes are
    `\\"schema_version\\"` and the pattern, which requires a bare quote on
    each side of the key, cannot reach it. That is why a textual edit is
    safe here: the only place an unescaped `"schema_version"` can appear
    is as a key.
    """
    title = 'On writing \\"schema_version\\": 9 into a title'
    raw = (f'{{"schema_version": {OLD}, "id": "inv-01",\n'
           f'  "title": "{title}",\n'
           f'  "exhibits": []}}')
    bundle = make_old_bundle(tmp_path / "b", raw=raw, figures=())
    assert bump_tool.main([str(bundle)]) == 0
    after = (bundle / "manifest.json").read_text(encoding="utf-8")
    assert f'"schema_version": {SCHEMA_VERSION}' in after
    # The mention inside the title is untouched, digit included.
    assert title in after


def test_a_missing_manifest_is_a_loud_failure(bump_tool, tmp_path, capsys):
    (tmp_path / "b").mkdir()
    assert bump_tool.main([str(tmp_path / "b")]) == 1
    assert "no manifest.json" in capsys.readouterr().err
