# Stage 3: skeleton

Before any prose is written, an inventory of everything the paper
contains: ordered sections with page spans, every table, every figure,
every footnote, the reference count. This is the coverage contract. The
dominant silent failure of one-shot conversion is omission, a dropped
paragraph or a missing table row, and omission is exactly what an
unstructured "just convert it" pass cannot prove it avoided. Everything
downstream is checked against the skeleton: the walk must produce every
unit, the figure stage must crop every exhibit, the sweep reads it.

## Who builds it

The converter, as its first full read of the paper: every page render
beside the OCR markdown for that page, returned as `skeleton.json`
and sanity-checked before the walk begins. When the conversion
is delegated, a dedicated subagent builds it instead and the driver
receives the file without reading a page image itself; for a very
long paper, chunk by page range and merge, each chunk's builder still
reading its every page.

The builder works from renders first, OCR second: the OCR proposes
headings and captions, the render confirms them and reveals what the OCR
missed. images.json is consulted only as a hint that a page carries
figure content; it never defines the exhibit list, because tables never
appear in it and multi-panel figures appear as fragments.

## What it contains

    {
      "id": "...",
      "page_count": N,
      "units": [
        {
          "index": 1,
          "kind": "front_matter" | "section" | "references" | "back_matter",
          "title": "Methods",
          "depth": 2,
          "pages": [3, 5],
          "opening_words": "first five or so words of the unit",
          "closing_words": "last five or so words of the unit",
          "notes": "optional: continues mid-sentence across a float, etc."
        }
      ],
      "reference_count": N,
      "exhibits": [
        {
          "label": "table_01",
          "kind": "table" | "figure",
          "printed": "Table 1",
          "caption": "the caption exactly as printed",
          "pages": [4],
          "panels": 1,
          "footnote": true,
          "bbox_proposals": 0
        }
      ],
      "page_footnotes": [
        {"page": 1, "kind": "correspondence" | "affiliations" | "other",
         "words": "first few words"}
      ]
    }

Rules for the builder:

- Units are the paper's sections in reading order, at the paper's own
  granularity. `depth` is the target heading depth in the bundle,
  mirroring the paper's own nesting (the rule is in quality.md); fix it
  here from the renders, because OCR heading levels are erratic and the
  walk needs one authority.
- `opening_words` and `closing_words` come from the render. They are
  the seam checks: the walk uses them to verify no unit lost
  its edges.
- Count the references by eye from the renders (`reference_count`); the
  walk's references unit is checked against it.
- Exhibits: every table and every figure, numbered as the paper numbers
  them (`table_01` for Table 1); unnumbered exhibits get the next free
  number in order of appearance. Count panels of multi-panel figures.
  Note whether the exhibit has footnote text. Record how many bboxes
  images.json proposes for its pages (zero is normal for tables).
- The skeleton's caption is a draft read from pixels, good enough to
  identify the exhibit. Its characters are not final: the walk verifies
  them against the character source when it emits the sentinel, and the
  manifest later copies the sentinel, not this file. The footnote flag
  says text exists; the footnote's words are transcribed by the figure
  stage into the manifest's notes, never here and never by the walk.
- Page footnotes are inventoried so front matter and back matter can
  claim them deliberately; footnotes are what reading-order scrambles
  drop most easily.

## Acceptance checks before the walk

Pages covered from 1 to page_count with no gaps between consecutive
units; depths start at a single depth-1 unit (the title) or the mapping
in quality.md; every exhibit has a label, caption, and page; the
reference count is present if a references unit exists. The converter
fixes a skeleton of its own that fails these before walking; a
delegated skeleton goes back to its subagent with the failure named.
