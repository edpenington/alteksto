"""Helpers for the walk engine's tests, and the invented paper they read.

The fixture rule: invented data only, and no binary is ever committed.
The source PDF each test reads is written fresh into tmp_path.
"""

import pymupdf

from tests.support import REPO_ROOT, load_script

ENGINE = REPO_ROOT / "engines" / "walk"
# Where this engine records what it should arrive at on the shared worked
# example, which `tests.support.EXAMPLES` names.
WALK_EXAMPLE = ENGINE / "example"

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
    """Load engines/walk/tools/{name}.py as a module."""
    return load_script(f"engines/walk/tools/{name}.py")


def build_source_pdf(work_dir):
    """Write an invented two-page source.pdf into work_dir."""
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
    doc.save(work_dir / "source.pdf")
    doc.close()
    return work_dir
