"""Offline tests for tools/render_pages.py on an invented PDF."""

import pymupdf

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_renders_one_png_per_page(render_pages_tool, work_dir):
    assert render_pages_tool.main([str(work_dir)]) == 0
    pages = sorted((work_dir / "pages").glob("page_*.png"))
    assert [p.name for p in pages] == ["page_01.png", "page_02.png"]
    for page in pages:
        assert page.read_bytes()[:8] == PNG_MAGIC


def test_dpi_scales_the_render(render_pages_tool, work_dir):
    assert render_pages_tool.main([str(work_dir), "--dpi", "72"]) == 0
    low = pymupdf.Pixmap(str(work_dir / "pages" / "page_01.png"))
    assert render_pages_tool.main([str(work_dir), "--dpi", "144"]) == 0
    high = pymupdf.Pixmap(str(work_dir / "pages" / "page_01.png"))
    assert (high.width, high.height) == (low.width * 2, low.height * 2)


def test_stale_renders_are_deleted(render_pages_tool, work_dir):
    pages = work_dir / "pages"
    pages.mkdir()
    stale = pages / "page_99.png"
    stale.write_bytes(b"stale bytes from an earlier run")
    assert render_pages_tool.main([str(work_dir)]) == 0
    assert not stale.exists()
    assert len(list(pages.glob("page_*.png"))) == 2


def test_missing_work_directory_fails(render_pages_tool, tmp_path, capsys):
    assert render_pages_tool.main([str(tmp_path / "absent")]) == 1
    assert "not a work directory" in capsys.readouterr().err


def test_missing_source_pdf_fails(render_pages_tool, tmp_path, capsys):
    assert render_pages_tool.main([str(tmp_path)]) == 1
    assert "source PDF missing" in capsys.readouterr().err


def test_unreadable_pdf_fails(render_pages_tool, tmp_path, capsys):
    (tmp_path / "source.pdf").write_bytes(b"this is not a pdf")
    assert render_pages_tool.main([str(tmp_path)]) == 1
    assert "unreadable PDF" in capsys.readouterr().err


def test_out_of_range_dpi_fails_before_rendering(render_pages_tool, work_dir,
                                                 capsys):
    assert render_pages_tool.main([str(work_dir), "--dpi", "0"]) == 1
    assert "--dpi" in capsys.readouterr().err
    assert not (work_dir / "pages").exists()
