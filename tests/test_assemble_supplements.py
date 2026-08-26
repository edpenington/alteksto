"""Offline tests for tools/assemble_supplements.py on invented declarations.

The tool exists because the route runs one converter per paper-like unit,
so several supplements of one paper can be in flight while the format
wants one declaration file at the bundle root. Each converter writes its
own; this collects them. What is asserted here is that the collection is
deterministic, that it refuses a declaration it cannot trust, and that
what it writes is what the format accepts.
"""

import json

import pytest

from alteksto.bundle import SCHEMA_VERSION, validate_bundle
from conftest import load_tool

PNG_STUB = b"\x89PNG\r\n\x1a\n invented bytes; no check reads pixels"


@pytest.fixture(scope="session")
def assemble_tool():
    return load_tool("assemble_supplements")


def make_paper(tmp_path, paper_id="R0126"):
    """A work directory and a bundle, both minimal and both valid."""
    work = tmp_path / "work" / paper_id
    bundle = tmp_path / "bundles" / paper_id
    (bundle / "figures").mkdir(parents=True)
    (bundle / "text.md").write_text("# An invented paper\n\nBody.",
                                    encoding="utf-8")
    (bundle / "manifest.json").write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "id": paper_id,
        "title": "An invented paper", "exhibits": []}), encoding="utf-8")
    work.mkdir(parents=True)
    return work, bundle


def declare(work, name, title=None, exhibits=(), **overrides):
    root = work / "supplements" / name
    root.mkdir(parents=True, exist_ok=True)
    payload = {"name": name, "title": title or f"{name}, as printed",
               "exhibits": list(exhibits)}
    payload.update(overrides)
    (root / "declaration.json").write_text(json.dumps(payload),
                                           encoding="utf-8")
    return root


def supplement_in_bundle(bundle, name, labels=()):
    root = bundle / "supplements" / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "text.md").write_text("# Supplement\n\nProse.", encoding="utf-8")
    if labels:
        (root / "figures").mkdir(exist_ok=True)
        for label in labels:
            (root / "figures" / f"{label}.png").write_bytes(PNG_STUB)
    return root


def test_it_assembles_what_the_format_accepts(assemble_tool, tmp_path):
    work, bundle = make_paper(tmp_path)
    declare(work, "supplement_3",
            title="Supplement 3. Characteristics of included studies",
            exhibits=[{"label": "supplement_3_table_01",
                       "caption": "Characteristics."}])
    supplement_in_bundle(bundle, "supplement_3",
                         labels=("supplement_3_table_01",))
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 0
    # The point of the tool: what it wrote is a valid bundle, judged by the
    # contract rather than by reading the JSON back and agreeing with it.
    assert validate_bundle(bundle) == []


def test_the_id_comes_from_the_manifest_and_cannot_disagree(assemble_tool,
                                                            tmp_path):
    work, bundle = make_paper(tmp_path, paper_id="R0045")
    declare(work, "appendix_a")
    supplement_in_bundle(bundle, "appendix_a")
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 0
    written = json.loads((bundle / "supplements.json").read_text())
    assert written["id"] == "R0045"


def test_supplements_are_written_in_a_fixed_order(assemble_tool, tmp_path):
    """Sorted, so one paper assembles identically on every filesystem."""
    work, bundle = make_paper(tmp_path)
    for name in ("supplement_3", "appendix_a", "supplement_1"):
        declare(work, name)
        supplement_in_bundle(bundle, name)
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 0
    written = json.loads((bundle / "supplements.json").read_text())
    assert [s["name"] for s in written["supplements"]] == [
        "appendix_a", "supplement_1", "supplement_3"]


def test_a_rerun_writes_the_same_bytes(assemble_tool, tmp_path):
    work, bundle = make_paper(tmp_path)
    declare(work, "appendix_a")
    supplement_in_bundle(bundle, "appendix_a")
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 0
    first = (bundle / "supplements.json").read_bytes()
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 0
    assert (bundle / "supplements.json").read_bytes() == first


def test_a_paper_with_no_supplements_gets_no_file(assemble_tool, tmp_path,
                                                  capsys):
    work, bundle = make_paper(tmp_path)
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 0
    assert not (bundle / "supplements.json").exists()
    assert "declares no supplements" in capsys.readouterr().err


def test_a_supplement_that_never_finished_is_a_stop(assemble_tool, tmp_path,
                                                    capsys):
    """A directory with no declaration is work in progress, and writing
    the file without it would quietly ship a paper missing a supplement."""
    work, bundle = make_paper(tmp_path)
    declare(work, "appendix_a")
    (work / "supplements" / "supplement_3").mkdir(parents=True)
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 1
    assert "has no declaration.json" in capsys.readouterr().err
    assert not (bundle / "supplements.json").exists()


def test_a_declaration_in_the_wrong_directory_is_a_stop(assemble_tool,
                                                        tmp_path, capsys):
    work, bundle = make_paper(tmp_path)
    root = work / "supplements" / "appendix_a"
    root.mkdir(parents=True)
    (root / "declaration.json").write_text(
        json.dumps({"name": "supplement_3", "title": "T", "exhibits": []}),
        encoding="utf-8")
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 1
    assert "belongs somewhere else" in capsys.readouterr().err


@pytest.mark.parametrize("payload, expected", [
    ({"title": "T", "exhibits": []}, "missing required key: 'name'"),
    ({"name": "appendix_a", "exhibits": []}, "missing required key: 'title'"),
    ({"name": "appendix_a", "title": "T"}, "missing required key: 'exhibits'"),
    ({"name": "appendix_a", "title": "T", "exhibits": [], "warden": 1},
     "unknown key: 'warden'"),
    ({"name": "appendix_a", "title": "T", "exhibits": {}},
     "key 'exhibits' must be a list"),
])
def test_a_malformed_declaration_is_named(assemble_tool, tmp_path, capsys,
                                          payload, expected):
    work, bundle = make_paper(tmp_path)
    root = work / "supplements" / "appendix_a"
    root.mkdir(parents=True)
    (root / "declaration.json").write_text(json.dumps(payload),
                                           encoding="utf-8")
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 1
    assert expected in capsys.readouterr().err


def test_a_bundle_with_no_manifest_is_a_loud_failure(assemble_tool, tmp_path,
                                                     capsys):
    work, bundle = make_paper(tmp_path)
    (bundle / "manifest.json").unlink()
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 1
    assert "no manifest" in capsys.readouterr().err


def test_a_duplicate_key_in_a_declaration_is_refused(assemble_tool, tmp_path,
                                                     capsys):
    """The one route the playbook tells a converter to use.

    supplements.json refuses a repeated key because the last value wins
    and the rest are gone before any check runs. Resolving one quietly
    here would launder past that rule exactly the values nothing later
    can contradict: a title, a caption, an exhibits list a second one
    replaced.
    """
    work, bundle = make_paper(tmp_path)
    root = work / "supplements" / "supp_a"
    root.mkdir(parents=True)
    (root / "declaration.json").write_text(
        '{"name": "supp_a", "title": "Supplement A. Station counts", '
        '"title": "draft heading, replace me", "exhibits": []}',
        encoding="utf-8")
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 1
    assert "declares 'title' twice" in capsys.readouterr().err
    assert not (bundle / "supplements.json").exists()


def test_a_declaration_that_is_there_but_unreadable_is_not_called_missing(
        assemble_tool, tmp_path, capsys):
    """"Has not been converted" would be a confident and wrong diagnosis."""
    work, bundle = make_paper(tmp_path)
    root = work / "supplements" / "supp_a"
    (root / "declaration.json").mkdir(parents=True)
    assert assemble_tool.main([str(work), "--bundle", str(bundle)]) == 1
    err = capsys.readouterr().err
    assert "is not a file" in err
    assert "has no declaration.json" not in err
