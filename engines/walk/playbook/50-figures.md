# Stage 5: figures

Every exhibit in the skeleton becomes one cropped PNG in the bundle.
The loop is view, crop, inspect, adjust, trim: propose a region, cut
it, look at the result, and only accept what a reader could actually
use. Nothing in the bundle contract can see crop quality, so this stage
is where crop quality is decided.

## Proposals

- **Figures start from images.json.** The OCR's bboxes found every real
  figure in measurement, but they bound the artwork alone and the
  caption is part of the crop, so every one of them needs extending.
  Treat them as proposals, not answers:
  - Rescale first. Coordinates are in the page space images.json itself
    declares per page (its dimensions vary paper to paper and page to
    page, and never match the render DPI). Hand that page's declared
    width and height to crop.py as `--space` and the tool maps the
    boxes into render pixels. Never do the arithmetic by hand: a
    slightly wrong scale crops a plausible-looking wrong region.
  - Classify. Publisher logos, cover thumbnails, and badges arrive as
    proposals too; reject decorations against the skeleton's exhibit
    list.
  - Union panels. A multi-panel figure arrives as one bbox per panel,
    all sharing one caption. Pass the panels of one exhibit together,
    one `--box` each, and crop.py cuts their union. Then check the
    result against the render: overall titles, shared axis labels, and
    legends can sit outside every panel box, sometimes in the gaps
    between them. Extend until the whole printed figure is inside.
- **Tables get no proposals.** images.json never reports them. Locate a
  table from its skeleton page and the render, using the caption's and
  cells' blocks.json bboxes as the initial region where the layer has
  them (their space is the page size blocks.json records; pass that as
  `--space`).

## The loop

For each exhibit:

1. Crop the proposed region from the page render:

       python engines/walk/tools/crop.py work/{id}/pages/page_NN.png \
           --box X0 Y0 X1 Y1 --space W H \
           --out bundles/{id}/figures/{label}.png

   One `--box` per panel; the tool crops their union. `--space` names
   the space the boxes are given in (the page's images.json dimensions,
   or its blocks.json size in points); omit it when the boxes are
   already render pixels. Every crop is auto-trimmed, uniform margins
   cut back to a few pixels around the content, so a generous box
   costs nothing and clips nothing. A region that comes back blank is
   refused loudly: the proposal missed the exhibit, look at the render
   again.
2. View the crop. Ask: is every row, column, panel, label, legend,
   footnote line, and the exhibit's whole printed extent inside? The
   exhibit's footnote lines are part of the exhibit and belong in the
   crop (the OCR's figure proposals do not include them; extend). A
   table's full-width border rules are part of the table: journals
   often print the top rule directly under the caption, and in
   measurement every table box drawn from the content down clipped it
   by a couple of pixels, so check the top rule is inside. A figure's
   own printed title above the plot area is part of the figure the
   same way. Is the caption inside, and inside whole? The caption is
   part of the exhibit and belongs in the crop, above a table or below
   a figure as the journal prints it, and a crop that clips it at
   either end is wrong: a caption sliced down its left edge reads as
   a fragment and is worse than one left out. It is carried as text as
   well, in the sentinel and the manifest, so a consumer never has to
   read it off the pixels. Is anything foreign inside (neighbouring
   text, the next exhibit)? For edges too
   fine to trust by eye, a row and column ink profile of the render
   settles where content starts and stops.
3. Adjust the region and re-crop until both answers are right. A crop
   spanning a full-width exhibit on a two-column page commonly needs
   widening; a panel union commonly needs a title strip added above.

An exhibit spanning multiple pages becomes one crop per page part only
if the parts cannot be joined sensibly; prefer the meaningful whole.

## Transcribing a table

Every table exhibit also gets its content as text, in
`bundles/{id}/tables/{label}.html`. Figures do not: a figure's content
is its pixels, and describing them here is invention, the same rule
that keeps figure-internal text out of text.md.

The two witnesses divide cleanly, and mixing them up is how a
transcription goes wrong:

- **Characters come from the exhibit's text-layer dump**
  (`work/{id}/exhibit_dumps/{label}.txt`), the same source and the same
  standard as the walk's. Transcribe what the exhibit prints, typos
  included.
- **Structure comes from the crop**, viewed. The layer flattens tables
  one cell per line, interleaves multi-line headers, and drops empty
  cells without a trace, so it can say what the characters are and
  never which cell they sit in. Read the arrangement off the image.

Write it as the format specifies (`docs/bundle.md`): one `<table>`,
whitelisted elements only, `colspan` and `rowspan` where the exhibit
prints spanning or stacked headers. Three things are worth naming
because each is a defect that reads perfectly plausibly:

- **An empty cell stays an empty cell.** `<td></td>`, never a dash
  invented to fill it and never omitted, because omitting it slides
  every value after it one column left.
- **The caption is not a row.** The caption is inside the crop by
  rule, and often printed inside the table's own frame; in the
  transcription it appears neither as a row nor as a heading, because
  it is already carried as text in the sentinel and the manifest. The
  footnote lines under the table are inside the crop too, and they are
  the manifest's `notes`.
- **A footnote marker stays a marker.** A superscript on a count is
  `<sup>a</sup>`, not a digit fused onto the number.

Then check it, in this order:

1. Structure, deterministically. `render_table.py` refuses to draw a
   transcription that does not pass the format's own checks, so a
   failure here is a dropped cell or a span one too small, named with
   its position. Fix it before spending a look on it.

       python engines/walk/tools/render_table.py \
           bundles/{id}/tables/{label}.html \
           --out work/{id}/table_renders/{label}.png

   A table printed sideways gets `--rotate 90` (or 270), so the render
   turns to match a crop that came off the page rotated. The
   transcription itself is always written in reading order.
2. Content, by eye. View the render beside the crop and ask one
   question: do they say the same thing in the same arrangement? Same
   cells in the same positions, same header structure and spans, same
   characters including markers and dashes, the same cells empty. The
   render will not look like the journal's typesetting, and it is not
   meant to: the face is different, the rules are uniform, nothing is
   shaded. Appearance is not what is being compared.
3. Fix and repeat until they agree.

A table whose characters cannot be trusted, and there will be some,
does not get a guessed transcription. Delete the file and move on: the
crop is the content, exactly as it was before this stage could do
anything else. A missing transcription is honest and a wrong one is
not, and nothing downstream can tell a wrong one from a right one.

## Outputs

- `bundles/{id}/figures/{label}.png` for every skeleton exhibit, labels
  exactly as the skeleton assigns them (`table_01`, `figure_02`).
- The manifest's `exhibits` array: one entry per crop, `label` and
  `caption` plus `notes` when the exhibit has footnote text. The
  caption is copied from the exhibit's sentinel in text.md, which the
  walk already reconciled character by character; the skeleton's
  pixel-read caption is never the manifest's source. The notes are
  transcribed here: characters from the exhibit's text-layer dump (the
  character source for the region), shape confirmed by viewing the
  crop, which includes the footnote lines. An exhibit without footnote
  text omits the key. The contract accepts nothing else per exhibit,
  and validate-bundle binds labels to files both ways.
- `bundles/{id}/tables/{label}.html` for every table exhibit whose
  content could be transcribed and checked, and no file at all for the
  ones that could not. There is no key or marker recording which is
  which: a file that is there has been through the checks above, and
  absence means the crop is the content.
- The exhibit's raw text-layer dump (the blocks its region covers) is
  saved to `work/{id}/exhibit_dumps/{label}.txt`. It stays out of the
  bundle; it exists so the sweep and any later audit can search what
  the pixels say without re-reading them.
- `work/{id}/table_renders/{label}.png`, the render each transcription
  was checked against. It stays out of the bundle and is handed to the
  sweep.

Before leaving the stage, count: skeleton exhibits, crops on disk, and
manifest entries must match one to one to one. A mismatch is a loud
stop, not a shrug. Transcriptions are counted separately and against a
different standard: every table exhibit either has one or was recorded
in the run's notes as untranscribable, and every file in `tables/`
belongs to a declared exhibit.
