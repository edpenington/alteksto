"""Offline tests for engines/walk/tools/check_refs.py with a faked registrar."""

from urllib.error import HTTPError, URLError

import pytest

from tests.engines.walk.support import load_tool

TEXT = """# An invented ledger of reed beds

Body prose about herons.

## References

- 1. Heron A, Sluice B. Counting invented herons in spring. Wetland J. \
2020;12:53-9. https://doi.org/10.1000/heron.2020.001
- 2. Marsh C. The invented sluice and its closure. Wetland J. \
2021;13:101-9. https://doi.org/10.1000/marsh.2021.002.
- 3. Reed D. A vanished monograph. Old Press; 1999. \
https://doi.org/10.1000/gone.1999
"""

CSL = {
    "10.1000/heron.2020.001": {
        "title": "Counting invented herons in spring",
        "author": [{"family": "Heron", "given": "A"}],
        "issued": {"date-parts": [[2020]]},
        "page": "53-59",
    },
    # Resolves, but to a different work than the entry describes.
    "10.1000/marsh.2021.002": {
        "title": "An entirely different invented subject",
        "author": [{"family": "Fen", "given": "Z"}],
        "issued": {"date-parts": [[2018]]},
        "page": "700-9",
    },
}


@pytest.fixture(scope="session")
def refs_tool():
    return load_tool("check_refs")


@pytest.fixture
def fake_registrar(refs_tool, monkeypatch):
    monkeypatch.setattr(refs_tool, "PAUSE_SECONDS", 0)

    def resolve(doi, timeout):
        if doi in CSL:
            return CSL[doi]
        raise HTTPError(refs_tool.DOI_BASE + doi, 404, "Not Found",
                        None, None)

    monkeypatch.setattr(refs_tool, "_resolve", resolve)


def write_text(tmp_path, content=TEXT):
    path = tmp_path / "text.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_resolution_and_juxtaposition(refs_tool, tmp_path, fake_registrar,
                                      capsys):
    text = write_text(tmp_path)
    assert refs_tool.main([str(tmp_path), "--text", str(text)]) == 0
    report = (tmp_path / "refs-report.md").read_text(encoding="utf-8")
    assert "3 DOI(s) checked: 2 resolved" in report
    assert "1 unresolved" in report
    # Each resolved DOI shows the entry and the registrar record side by
    # side; no alignment verdict is computed.
    assert "- resolved 10.1000/heron.2020.001" in report
    assert "entry:" in report and "registrar:" in report
    assert "Counting invented herons in spring" in report
    # The wrong-work record is visible for the reading agent to judge.
    assert "An entirely different invented subject" in report
    assert "aligned" not in report.replace("misaligned", "")
    assert "- unresolved 10.1000/gone.1999" in report
    # The trailing full stop after the second DOI was stripped.
    assert "- resolved 10.1000/marsh.2021.002\n" in report


def test_the_registrar_record_shows_the_fields_to_judge_by(refs_tool,
                                                           tmp_path,
                                                           fake_registrar):
    # The record line carries author, year, title, and pages so the
    # reading agent can judge alignment, including the single-digit
    # differences; the tool itself computes nothing about them.
    text = write_text(tmp_path)
    assert refs_tool.main([str(tmp_path), "--text", str(text)]) == 0
    report = (tmp_path / "refs-report.md").read_text(encoding="utf-8")
    assert "Heron A. (2020). Counting invented herons in spring" in report
    assert "53-59" in report
    assert "eyeball" not in report


def test_no_references_heading_is_a_clean_nothing(refs_tool, tmp_path,
                                                  capsys):
    text = write_text(tmp_path, "# A paper\n\nProse without references.\n")
    assert refs_tool.main([str(tmp_path), "--text", str(text)]) == 0
    assert "no references heading" in capsys.readouterr().err
    assert "Nothing to check" in (tmp_path / "refs-report.md").read_text(
        encoding="utf-8")


def test_references_without_dois_is_a_clean_nothing(refs_tool, tmp_path,
                                                    capsys):
    text = write_text(tmp_path,
                      "# A paper\n\n## References\n\n- 1. Heron A. An "
                      "invented book. Old Press; 1999.\n")
    assert refs_tool.main([str(tmp_path), "--text", str(text)]) == 0
    assert "no DOIs" in capsys.readouterr().err


def test_network_failure_is_unanswered_and_exit_one(refs_tool, tmp_path,
                                                    monkeypatch, capsys):
    monkeypatch.setattr(refs_tool, "PAUSE_SECONDS", 0)

    def broken(doi, timeout):
        raise URLError("invented network failure")

    monkeypatch.setattr(refs_tool, "_resolve", broken)
    text = write_text(tmp_path)
    assert refs_tool.main([str(tmp_path), "--text", str(text)]) == 1
    assert "unanswered" in capsys.readouterr().err


def test_missing_text_file_fails(refs_tool, tmp_path, capsys):
    assert refs_tool.main([str(tmp_path), "--text",
                           str(tmp_path / "absent.md")]) == 1
    assert "text file missing" in capsys.readouterr().err
