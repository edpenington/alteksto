"""Shared fixtures: tools loaded as modules, invented PDFs built at test
time.

The fixture rule: invented data only, and no binary is ever committed. The
source PDF each test reads is written fresh into tmp_path by pymupdf.
"""

import importlib.util
from pathlib import Path

import pymupdf
import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"

# Two single-line blocks on page one.
PAGE_ONE_LINES = (
    "An invented survey of reed beds counted forty herons in spring.",
    "The count fell to twelve when the invented sluice was closed.",
)
# One two-line block on page two, holding a line-break hyphen. The dump
# must keep the artefact exactly as the text layer holds it.
PAGE_TWO_TEXTBOX = ("The closure placed greater pres-\n"
                    "sure on the invented wardens.")


def load_tool(name: str):
    """Load tools/{name}.py as a module, scripts staying scripts."""
    spec = importlib.util.spec_from_file_location(name,
                                                 TOOLS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def render_pages_tool():
    return load_tool("render_pages")


@pytest.fixture(scope="session")
def dump_blocks_tool():
    return load_tool("dump_blocks")


@pytest.fixture
def work_dir(tmp_path):
    """A work directory holding an invented two-page source.pdf."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 120), PAGE_ONE_LINES[0])
    page.insert_text((72, 300), PAGE_ONE_LINES[1])
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 100, 520, 200), PAGE_TWO_TEXTBOX)
    # An invented image on page two, so the OCR tools have a bounding box
    # to report. The text dump filters image blocks, so the other tools
    # never see it.
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8))
    pixmap.clear_with(120)
    page.insert_image(pymupdf.Rect(300, 400, 380, 460), pixmap=pixmap)
    doc.save(tmp_path / "source.pdf")
    doc.close()
    return tmp_path
