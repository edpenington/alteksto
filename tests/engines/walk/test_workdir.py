"""Unit tests for the shared work-directory contract."""

import pytest

from engines.walk.lib.workdir import (MAX_DPI, MIN_DPI, PAGE_MARKER_RE, dpi_error,
                              open_source_pdf, page_marker)


def test_page_marker_round_trips():
    match = PAGE_MARKER_RE.match(page_marker(7))
    assert match and match.group(1) == "7"


def test_page_marker_regex_refuses_prose():
    assert PAGE_MARKER_RE.match("on page 7 the authors report") is None


def test_dpi_error_accepts_the_bounds():
    assert dpi_error(MIN_DPI) is None
    assert dpi_error(150) is None
    assert dpi_error(MAX_DPI) is None


@pytest.mark.parametrize("bad", [0, -150, MAX_DPI + 1])
def test_dpi_error_rejects_out_of_range(bad):
    assert "must be from" in dpi_error(bad)


@pytest.mark.parametrize("bad", [None, 150.0, "150", True])
def test_dpi_error_rejects_non_integers(bad):
    assert "must be an integer" in dpi_error(bad)


def test_open_source_pdf_names_a_missing_directory(tmp_path):
    with pytest.raises(ValueError, match="not a work directory"):
        open_source_pdf(tmp_path / "absent")


def test_open_source_pdf_names_a_missing_pdf(tmp_path):
    with pytest.raises(ValueError, match="source PDF missing"):
        open_source_pdf(tmp_path)


def test_open_source_pdf_names_an_unreadable_pdf(tmp_path):
    (tmp_path / "source.pdf").write_bytes(b"this is not a pdf")
    with pytest.raises(ValueError, match="unreadable PDF"):
        open_source_pdf(tmp_path)


def test_open_source_pdf_returns_an_open_document(work_dir):
    doc = open_source_pdf(work_dir)
    try:
        assert len(doc) == 2
    finally:
        doc.close()
