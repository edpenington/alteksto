# Stage 1: triage

Classify the PDF before trusting anything. The classification assigns
which witness is authoritative for characters for the rest of the run,
and it is recorded so a resumed run does not re-decide it.

## Classify

Run `render_pages.py` and `dump_blocks.py` if their outputs do not
already exist, then judge:

- **Born-digital, healthy layer.** The dump reports a plausible block
  count (tens of blocks per page for a text page) and the text reads as
  language. This is the common case.
- **Scanned or void layer.** The dump reports the text layer is empty,
  or near-empty against pages that visibly carry text. `dump_blocks.py`
  says this loudly itself.
- **Misencoded layer.** Blocks exist but the characters are wrong:
  mojibake, wrong glyphs for ligatures, symbol soup. Spot this by
  reading a few paragraphs of blocks.txt; confirm against the render
  at the skeleton build later if unsure. Font-level damage can
  be local (one font wrong, body text fine); note where it lives rather
  than condemning the whole layer.

## Record

Write `work/{id}/triage.json`:

    {
      "classification": "born_digital" | "scanned" | "misencoded",
      "character_source": "text_layer" | "ocr",
      "notes": "anything local: which font is damaged, which pages are image-only",
      "page_count": N
    }

## Consequences

- Born-digital: the text layer is authoritative for characters; OCR is
  authoritative for structure; the standard precedence in 20-sources.md
  applies unchanged.
- Scanned or misencoded: OCR becomes the character source too, and every
  downstream stage treats the layer as absent or as damaged where noted.
  OCR characters are fallible (see quality.md), so the walk leans harder
  on the renders and flags low-confidence passages rather than guessing.
- Image-only pages inside an otherwise healthy PDF (a scanned appendix,
  a figure-only page) get noted per page, not per document.
