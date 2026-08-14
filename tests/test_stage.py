"""Tests for the intake tool: the id comes from the caller, never the file.

Every PDF here is invented and built in tmp_path, and every registry is a
few invented records. The point most of these tests defend is that a
wrong id is worse than no id: an ambiguous match stages nothing.
"""

import json

import pymupdf
import pytest

from conftest import load_tool


@pytest.fixture(scope="session")
def stage_tool():
    return load_tool("stage")


def make_pdf(path, lines, pages=1):
    """A PDF whose first page prints the given lines."""
    doc = pymupdf.open()
    page = doc.new_page()
    for index, line in enumerate(lines):
        page.insert_text((72, 100 + 24 * index), line)
    for _ in range(pages - 1):
        doc.new_page().insert_text((72, 100), "Invented continuation.")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


HERONS = [
    "Counting herons in an invented reed bed",
    "Marsh, A. B.; Sluice, C. D.",
    "https://doi.org/10.1234/herons.2019",
    "2019",
]
WARDENS = [
    "Rostering wardens across an invented estuary",
    "Warden, E. F.; Estuary, G. H.",
    "https://doi.org/10.1234/wardens.2021",
    "2021",
]

REGISTRY = {
    "#1013": {"title": "Counting herons in an invented reed bed",
              "authors": "Marsh, A. B.; Sluice, C. D.",
              "doi": "https://dx.doi.org/10.1234/herons.2019",
              "year": "2019", "study_id": "Marsh 2019"},
    "#1702": {"title": "Rostering wardens across an invented estuary",
              "authors": "Warden, E. F.; Estuary, G. H.",
              "doi": "https://dx.doi.org/10.1234/wardens.2021",
              "year": "2021", "study_id": "Warden 2021"},
}


def write_registry(path, records=None, wrapper=None):
    data = REGISTRY if records is None else records
    if wrapper:
        data = {"_meta": {"count": len(data)}, wrapper: data}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_explicit_id_stages_under_that_id(stage_tool, tmp_path):
    pdf = make_pdf(tmp_path / "downloads" / "untitled (3).pdf", HERONS)
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--id", "#1013",
                            "--pdf", str(pdf)])

    assert code == 0
    assert (work / "#1013" / "source.pdf").is_file()


def test_missing_pdf_is_a_loud_failure(stage_tool, tmp_path, capsys):
    code = stage_tool.main(["--work", str(tmp_path / "work"), "--id", "x",
                            "--pdf", str(tmp_path / "absent.pdf")])

    assert code == 1
    assert "absent.pdf" in capsys.readouterr().err


def test_restaging_the_same_pdf_resumes(stage_tool, tmp_path, capsys):
    pdf = make_pdf(tmp_path / "in" / "paper.pdf", HERONS)
    work = tmp_path / "work"
    argv = ["--work", str(work), "--id", "#1013", "--pdf", str(pdf)]
    assert stage_tool.main(argv) == 0
    capsys.readouterr()

    assert stage_tool.main(argv) == 0
    assert "already staged" in capsys.readouterr().out


def test_a_different_pdf_under_a_staged_id_stops(stage_tool, tmp_path, capsys):
    work = tmp_path / "work"
    first = make_pdf(tmp_path / "in" / "one.pdf", HERONS)
    second = make_pdf(tmp_path / "in" / "two.pdf", WARDENS)
    assert stage_tool.main(["--work", str(work), "--id", "#1013",
                            "--pdf", str(first)]) == 0
    capsys.readouterr()

    code = stage_tool.main(["--work", str(work), "--id", "#1013",
                           "--pdf", str(second)])

    assert code == 1
    assert "different PDF" in capsys.readouterr().err


def test_map_file_stages_many(stage_tool, tmp_path):
    herons = make_pdf(tmp_path / "in" / "a.pdf", HERONS)
    wardens = make_pdf(tmp_path / "in" / "b.pdf", WARDENS)
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({"#1013": str(herons),
                                    "#1702": str(wardens)}), encoding="utf-8")
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--map-file", str(map_file)])

    assert code == 0
    assert (work / "#1013" / "source.pdf").is_file()
    assert (work / "#1702" / "source.pdf").is_file()


def test_registry_match_ignores_the_filename(stage_tool, tmp_path, capsys):
    """The file is named after the wrong paper; the page decides."""
    make_pdf(tmp_path / "staging" / "wardens-final-v2.pdf", HERONS)
    registry = write_registry(tmp_path / "registry.json")
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--from",
                            str(tmp_path / "staging"),
                            "--registry", str(registry)])

    assert code == 0
    assert (work / "#1013" / "source.pdf").is_file()
    assert not (work / "#1702").exists()
    assert "#1013" in capsys.readouterr().out


def test_the_id_is_the_key_not_a_citation_label(stage_tool, tmp_path, capsys):
    """Records carry study_id ("Marsh 2019"); the id filed under is the key."""
    make_pdf(tmp_path / "staging" / "paper.pdf", HERONS)
    registry = write_registry(tmp_path / "registry.json")

    stage_tool.main(["--work", str(tmp_path / "work"), "--from",
                     str(tmp_path / "staging"), "--registry", str(registry)])

    out = capsys.readouterr().out
    assert "#1013" in out
    assert "Marsh 2019" not in out


def test_wrapped_registry_needs_records_key(stage_tool, tmp_path, capsys):
    make_pdf(tmp_path / "staging" / "paper.pdf", HERONS)
    registry = write_registry(tmp_path / "registry.json", wrapper="data")
    args = ["--work", str(tmp_path / "work"), "--from",
            str(tmp_path / "staging"), "--registry", str(registry)]

    assert stage_tool.main(args) == 1
    assert "--records" in capsys.readouterr().err

    assert stage_tool.main(args + ["--records", "data"]) == 0
    assert "#1013" in capsys.readouterr().out


def test_ambiguous_match_stages_nothing(stage_tool, tmp_path, capsys):
    """No DOI on the page and two near-identical titles: a human decides."""
    make_pdf(tmp_path / "staging" / "paper.pdf",
             ["A trial of invented wading birds", "2019"])
    registry = write_registry(tmp_path / "registry.json", records={
        "#1": {"title": "A trial of invented wading birds in spring",
               "year": "2019"},
        "#2": {"title": "A trial of invented wading birds in autumn",
               "year": "2019"},
    })
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--from",
                            str(tmp_path / "staging"),
                            "--registry", str(registry)])

    assert code == 3
    assert not any(work.glob("*/source.pdf")) if work.exists() else True
    assert "AMBIGUOUS" in capsys.readouterr().err


def test_two_pdfs_claiming_one_id_stage_neither(stage_tool, tmp_path, capsys):
    make_pdf(tmp_path / "staging" / "one.pdf", HERONS)
    make_pdf(tmp_path / "staging" / "two.pdf", HERONS)
    registry = write_registry(tmp_path / "registry.json")
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--from",
                            str(tmp_path / "staging"),
                            "--registry", str(registry)])

    assert code == 3
    assert not (work / "#1013").exists()
    assert "claimed by more than one PDF" in capsys.readouterr().err


def test_a_reference_list_does_not_decide_identity(stage_tool, tmp_path):
    """The other paper's DOI is printed, but on a later page."""
    doc = pymupdf.open()
    front = doc.new_page()
    for index, line in enumerate(HERONS):
        front.insert_text((72, 100 + 24 * index), line)
    for _ in range(stage_tool.IDENTITY_PAGES):
        doc.new_page().insert_text((72, 100), "Invented body text.")
    references = doc.new_page()
    references.insert_text((72, 100), "Warden, E. F. Rostering wardens across "
                                      "an invented estuary.")
    references.insert_text((72, 124), "https://doi.org/10.1234/wardens.2021")
    staging = tmp_path / "staging"
    staging.mkdir()
    doc.save(staging / "paper.pdf")
    doc.close()
    registry = write_registry(tmp_path / "registry.json")
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--from", str(staging),
                            "--registry", str(registry)])

    assert code == 0
    assert (work / "#1013" / "source.pdf").is_file()
    assert not (work / "#1702").exists()


@pytest.mark.parametrize("bad", ["../escaped", "a/b", "/etc/passwd", "",
                                 "  ", "..", "10.1234/herons.2019"])
def test_an_id_that_is_a_path_is_refused(stage_tool, tmp_path, capsys, bad):
    """An id names one directory; anything else escapes the work root."""
    pdf = make_pdf(tmp_path / "in" / "paper.pdf", HERONS)
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--id", bad, "--pdf", str(pdf)])

    assert code == 1
    assert "stage:" in capsys.readouterr().err
    assert not (tmp_path / "escaped").exists()
    assert not any(work.rglob("source.pdf")) if work.exists() else True


def test_a_superseded_doi_does_not_match_its_successors_page(stage_tool,
                                                             tmp_path):
    """A .pub2 update prints a DOI that starts with the original's."""
    make_pdf(tmp_path / "staging" / "paper.pdf",
             ["An invented Cochrane review, updated",
              "https://doi.org/10.1002/14651858.CD001234.pub2", "2021"])
    registry = write_registry(tmp_path / "registry.json", records={
        "#OLD": {"title": "A quite different superseded invented title",
                 "doi": "10.1002/14651858.CD001234", "year": "2009"},
    })
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--from",
                            str(tmp_path / "staging"),
                            "--registry", str(registry)])

    assert code == 3
    assert not (work / "#OLD").exists()


def test_the_doi_still_matches_its_own_page(stage_tool, tmp_path):
    """The boundary check must not reject the DOI the page really prints."""
    make_pdf(tmp_path / "staging" / "paper.pdf",
             ["An invented Cochrane review, updated",
              "doi: 10.1002/14651858.CD001234.pub2.", "2021"])
    registry = write_registry(tmp_path / "registry.json", records={
        "#NEW": {"title": "An invented Cochrane review, updated",
                 "doi": "10.1002/14651858.CD001234.pub2", "year": "2021"},
    })
    work = tmp_path / "work"

    assert stage_tool.main(["--work", str(work), "--from",
                            str(tmp_path / "staging"),
                            "--registry", str(registry)]) == 0
    assert (work / "#NEW" / "source.pdf").is_file()


def test_two_records_sharing_a_doi_are_ambiguous(stage_tool, tmp_path, capsys):
    """Registry order must not decide which of a tied pair wins."""
    make_pdf(tmp_path / "staging" / "paper.pdf", HERONS)
    registry = write_registry(tmp_path / "registry.json", records={
        "#1013": dict(REGISTRY["#1013"]),
        "#9999": dict(REGISTRY["#1013"]),
    })
    work = tmp_path / "work"

    code = stage_tool.main(["--work", str(work), "--from",
                            str(tmp_path / "staging"),
                            "--registry", str(registry)])

    assert code == 3
    assert not (work / "#1013").exists()
    assert not (work / "#9999").exists()
    assert "AMBIGUOUS" in capsys.readouterr().err


def test_a_list_registry_without_ids_says_so(stage_tool, tmp_path, capsys):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(
        [{"covidence_id": "#1013", "title": "Counting herons in a reed bed",
          "doi": "10.1234/herons.2019"}]), encoding="utf-8")
    make_pdf(tmp_path / "staging" / "paper.pdf", HERONS)

    code = stage_tool.main(["--work", str(tmp_path / "work"), "--from",
                            str(tmp_path / "staging"),
                            "--registry", str(registry)])

    assert code == 1
    error = capsys.readouterr().err
    assert "'id' field" in error
    assert "--records" not in error


def test_skipped_registry_records_are_reported(stage_tool, tmp_path, capsys):
    make_pdf(tmp_path / "staging" / "paper.pdf", HERONS)
    registry = write_registry(tmp_path / "registry.json", records={
        "#1013": dict(REGISTRY["#1013"]),
        "#dud": {"journal": "An invented journal"},
    })

    stage_tool.main(["--work", str(tmp_path / "work"), "--from",
                     str(tmp_path / "staging"), "--registry", str(registry)])

    assert "skipped 1 registry record" in capsys.readouterr().err


def test_a_map_file_value_that_is_not_a_path_fails_loudly(stage_tool,
                                                          tmp_path, capsys):
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({"#1013": 5}), encoding="utf-8")

    code = stage_tool.main(["--work", str(tmp_path / "work"),
                            "--map-file", str(map_file)])

    assert code == 1
    assert "rather than a path" in capsys.readouterr().err


def test_surnames_split_on_commas_and_hyphens(stage_tool):
    assert stage_tool.surnames("Smith J, Jones K, Brown L") == {
        "smith", "jones", "brown"}
    assert stage_tool.surnames("Marsh, A. B.; Sluice, C. D.") == {
        "marsh", "sluice"}
    assert stage_tool.surname_printed("smith-jones", {"smith", "wardens"})


def test_mode_flags_are_exclusive(stage_tool, tmp_path):
    with pytest.raises(SystemExit):
        stage_tool.main(["--id", "x", "--pdf", "y", "--map-file", "z"])


def test_normalise_doi_strips_the_resolver(stage_tool):
    assert stage_tool.normalise_doi("https://dx.doi.org/10.1/A") == "10.1/a"
    assert stage_tool.normalise_doi("doi: 10.1/a") == "10.1/a"
