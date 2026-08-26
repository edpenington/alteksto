# Quality: what a good bundle looks like

Two halves: the contract and conventions the bundle must satisfy, and
the catalogue of defects that real conversions produce. The route files
(00 to 60) say how to work; this file says what the work must come out
as.

## The contract

The bundle format is this repository's to define. The normative
specification is `docs/bundle.md`, and `tools/validate_bundle.py`
enforces it; downstream consumers (*meltiro* first among them) accept
what passes here. The load-bearing points:

- `bundles/{id}/` holds `manifest.json`, `text.md`, `figures/*.png`,
  and optionally `tables/*.html`. Nothing else is read; extra files are
  ignored.
- The manifest carries `schema_version` (4), `id`, `title`, `exhibits`,
  and optionally `doi` and `summary`. Unknown keys are rejected. Each
  exhibit entry is `{"label", "caption"}` plus optional `notes` (the
  exhibit's printed footnote text); every declared label must have its
  PNG and every PNG its declaration.
- A table exhibit may also carry its content as text in
  `tables/{label}.html`, checked structurally by the validator and
  against the crop by the figure stage. It is beside the crop, never
  instead of it. There is no marker for a transcription that was not
  attempted or could not be trusted: the file is there or it is not.
- Supplementary material is its own thing: `supplements.json` declares
  it and `supplements/{name}/` holds it, each shaped like the bundle
  around it. A supplement's prose never joins `text.md` and its
  exhibits never join the manifest, so the article's identity does not
  move when a supplement lands. Exhibit labels are unique across the
  whole bundle, which is why a supplement's carry its name.
- Extraction evidence is later quoted **verbatim** against text.md,
  markdown syntax included. The formatting rules below keep those
  quotes predictable: what the paper prints is what text.md carries,
  and what text.md carries is what a quote must reproduce.
- No check can see crop quality or text fidelity. The gates and this
  playbook are where those are held; the validator only proves shape.

The manifest's `summary` is filled with the paper's abstract when the
paper has one (it is the paper's short identity for consumers that need
one without reading the full text); `doi` when known; `title` exactly
as printed.

## Formatting rules for text.md

- **Heading depth mirrors the paper.** The paper title is the single
  `#` and the paper's top level sections are `##`; beyond that, each
  nesting step the paper prints is one more `#`, following the paper's
  own conventions. Heading text is transcribed as printed, section
  numbers included. Headings are neither invented nor dropped:
  material the paper prints without a heading flows unheaded in its
  reading position. The skeleton records each unit's depth by this
  rule (the renders show the nesting; OCR levels are unreliable); the
  walk obeys the skeleton.
- **Emphasis is the paper's.** Bold and italic are transcribed where
  the paper prints them and never added where it does not. The text
  layer's font flags are the witness: blocks.json lists each block's
  styled runs, and in measurement they matched every hand-verified
  count exactly, so carry emphasis where the runs mark it and consult
  the render only when a run looks wrong (flags can miss synthetic
  italics). Do not audit styling beyond that: a missed italic run is a
  minor defect, not worth a pixel hunt. Downstream evidence is quoted
  verbatim, markdown included, so an italicised statistic is quoted
  with its asterisks; the contract owns that consequence and accepts
  it. Inline math stays in plain characters where the printed
  characters allow (p < 0.001, r = -0.34); LaTeX only where plain
  characters cannot say it, and then consistently.
- **Characters are the paper's.** Typos, odd spacing in names,
  inconsistent capitalisation: transcribe as printed. En dashes stay
  in numeric ranges. Line-break hyphens are healed; lexical hyphens
  stay. Soft hyphens, zero-width spaces, and other invisible
  characters do not exist in the bundle.
- **No page furniture.** Running heads, footers, page numbers, page
  markers, publisher badges, and "downloaded from" boilerplate never
  appear. Paragraphs read continuously across page and column joins.
- **Exhibits are sentinels in the text, crops in figures/.** At the
  exhibit's position in reading order:

      [TABLE 2. Caption exactly as printed.]

  The sentinel's number and caption match the manifest entry. Table
  content never appears in text.md: the crop is the exhibit, and a
  table's content is transcribed to `tables/{label}.html` instead,
  where a consumer can find it without it landing in the middle of
  the prose a quote is checked against. The exhibit's footnote lines
  are part of the exhibit: the crop includes them and the manifest's
  `notes` carries their text, and they never appear beside the
  sentinel. Figure-internal text is never transcribed, in text.md or
  anywhere else: a figure's content is its pixels.
- **Footnotes land where they belong.** Author, correspondence, and
  affiliation notes join front matter; exhibit footnotes belong to the
  exhibit (crop and manifest `notes`, see above); a genuine content
  footnote is placed at the end of the section that references it,
  marked `Footnote:`.
- **References** are one markdown list item per entry, in the paper's
  own citation style, characters exact.
- **Front matter** is title, authors (with affiliation markers as
  printed), then abstract and keywords if present. Licensing and
  submission boilerplate stays out.

## The defect catalogue

Every entry below was observed in real conversions. Symptoms first,
then the witness that causes them.

### Defects the text layer causes

- Front matter scrambled: title and abstract emitted after body text;
  captions detached from their exhibits; running heads wedged anywhere
  in the stream, including mid-table.
- Tables flattened one cell per line; multi-line headers interleaved by
  visual line or fused across columns; **empty cells vanish without a
  trace**, silently shifting values between columns.
- Invisible damage: soft hyphens inside words, zero-width spaces inside
  URLs, sub-visible typesetter text carrying wrong metadata (a wrong
  copyright year was observed), font-local ligature substitution (ff
  rendered as a Greek letter).
- Justified lines exploding one word per line; references split into
  fragment blocks; statistics split across line breaks ("p =" ending a
  line).
- A printed line can be missing entirely, with no error signal.

### Defects the OCR causes

- **Silent improvement of the source**: typos corrected, words
  respaced, broken URLs rewritten into plausible wrong ones,
  affiliation marker schemes renumbered. The OCR's reading is never
  evidence of what the page prints.
- High-entropy corruption, references worst: digits changed in page
  ranges, letters changed in author names, URL path segments rewritten,
  an S read as a 5.
- Small glyphs with large meaning: a tilde read as a minus turns
  "approximately 0.6" into "negative 0.6"; an icon hallucinated as a
  character on every page; two-tier bullet markers collapsed to one.
- Structure noise: running heads kept as body text; heading levels
  erratic within one document; front and back matter promoted to
  section level; an in-plot figure title promoted to a document
  heading.
- Table edge cases: spanning group headers flattened or attached to the
  wrong column; footnote markers fused into counts ("N = 2,0891");
  exhibit footnotes absorbed as table rows. Cell values themselves
  measure reliable.
- Emphasis attrition: italics and bold fade in and out across pages of
  one document in the OCR (an et al. italicised on page one, plain
  thereafter), and first-draft emissions drop them too. The layer's
  emphasis runs in blocks.json are the cheap guard; the render is the
  tiebreak, not the primary source. Note the runs cover furniture too
  (an italic running head), which the walk strips by pattern as ever.
- Floats interposed at page joins: a sentence spanning the page break
  resumes after whole tables, so naive concatenation splices a table
  into mid-sentence.

### Defects the crop proposals cause

- Multi-panel figures fragmented into per-panel boxes whose union still
  misses the printed title, a shared axis label sitting in the gutter
  between panels, or a rotated axis label.
- Decorations proposed as figures: publisher logos, cover thumbnails.
- Tables never proposed at all.
- Per-page coordinate spaces that never match the render's DPI.

### Defects a transcription causes

- Empty cells dropped rather than transcribed as empty, sliding every
  value after them one column left. The grid check catches this only
  when the row ends short; a row that also gained a cell tiles
  perfectly and is wrong.
- The printed caption transcribed as a header row, because the crop
  shows it: journals often print it directly above the top rule.
  Footnote lines transcribed as a final row for the same reason.
- Spanning group headers given the wrong `colspan`, so the header sits
  over the wrong columns while every cell is individually correct.
- A rowspan widened to silence a reported hole. The validator refuses a
  span reaching past the last row for exactly this reason: it makes the
  complaint go away and leaves the missing row missing, and the right
  and wrong versions draw identically, so the render cannot catch it.
- Footnote markers fused into counts ("N = 2,0891") when the marker is
  read off the layer rather than seen as a superscript on the crop.
- Numbers silently improved: a range tidied, a decimal aligned, a
  thousands separator added where the paper prints none.

### Defects the web witness causes

- Structured references fused or duplicated by conversion; tables and
  figures present only as placeholders; back matter absent. Prose,
  when present, measures character-exact.

### Defects the source itself causes

- Garbled reference entries, broken URLs, misspelled words, statistics
  that differ between caption and body, a caption describing fewer
  panels than the figure shows. **These are not conversion defects.**
  The render proves them; the bundle preserves them; the sweep labels
  them `source` so nobody fixes them into fabrication.
