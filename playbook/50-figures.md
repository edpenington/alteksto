# Stage 5: figures

Every exhibit in the skeleton becomes one cropped PNG in the bundle.
The loop is view, crop, inspect, adjust, trim: propose a region, cut
it, look at the result, and only accept what a reader could actually
use. Nothing in the bundle contract can see crop quality, so this stage
is where crop quality is decided.

## Proposals

- **Figures start from images.json.** The OCR's bboxes found every real
  figure in measurement, and their crops excluded captions correctly.
  But treat them as proposals, not answers:
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

       python tools/crop.py work/{id}/pages/page_NN.png \
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
   same way. Is the caption outside (it lives in text.md)? Is anything
   foreign inside (neighbouring text, the next exhibit)? For edges too
   fine to trust by eye, a row and column ink profile of the render
   settles where content starts and stops.
3. Adjust the region and re-crop until both answers are right. A crop
   spanning a full-width exhibit on a two-column page commonly needs
   widening; a panel union commonly needs a title strip added above.

An exhibit spanning multiple pages becomes one crop per page part only
if the parts cannot be joined sensibly; prefer the meaningful whole.

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
- The exhibit's raw text-layer dump (the blocks its region covers) is
  saved to `work/{id}/exhibit_dumps/{label}.txt`. It stays out of the
  bundle; it exists so the sweep and any later audit can search what
  the pixels say without re-reading them.

Before leaving the stage, count: skeleton exhibits, crops on disk, and
manifest entries must match one to one to one. A mismatch is a loud
stop, not a shrug.
