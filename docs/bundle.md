# The paper bundle: format specification

This repository owns the paper bundle format. The specification below
is normative: `tools/validate_bundle.py` enforces it, the playbook
produces to it, and downstream consumers (*meltiro* first among them)
read it. The format evolves here, by a `schema_version` bump, and
consumers follow. A rule that tightens what was always malformed, and
so refuses nothing a correct bundle contains, does not move the
version: no bundle that was right becomes wrong.

The format is at `schema_version` 4. A bundle declares that version and
a consumer accepts it; a bundle declaring any other version is not a
bundle.

Versions 3 and 4 are both additions and nothing else. Version 3 added
`tables/`, the optional table transcriptions described below; version 4
added `supplements.json` and `supplements/`, the paper's supplementary
material carried as its own thing. A correct version 2 bundle becomes a
correct version 4 bundle by changing the integer, because everything
either version adds is optional. Neither bump is about what a producer
must now write. Both are about what a consumer may now rely on, which is
that these directories have been checked rather than ignored as the
paperwork any bundle is free to carry.

## Layout

One directory per paper, self-contained and human-authorable. Papers
are copyrighted, so bundles are never committed; they are produced and
consumed at run time.

    paper-bundle/
      manifest.json     (required)  identity and the exhibit declaration
      text.md           (required)  the paper's full text as markdown, UTF-8
      figures/          (optional)  cropped tables and figures, *.png only
      tables/           (optional)  table transcriptions, *.html only
      supplements.json  (optional)  what supplementary material is carried
      supplements/      (optional)  one directory per supplement

Extra files beside the six contract entries are ignored by consumers,
so a bundle may carry its own paperwork. Inside `figures/` and
`tables/`, nothing extra is tolerated: a file of the wrong kind or a
subdirectory is an error, and only hidden OS metadata (dotfiles) is
skipped.

## manifest.json

A single JSON object. Unknown keys are errors, at the top level and
inside each exhibit entry. So is a repeated key, at any depth. Python's
`json`, like most readers, keeps the last value of a repeated key and
drops the rest without a word, which makes it the one malformation no
check after the parse can report: the evidence is gone before anything
runs. It is refused during the parse, the last moment both values still
exist. Keys are compared after JSON string unescaping, so `\u0069d` and
`id` are the same key. Every repeated key in the file is named, with
its position, and the manifest's other rules are still checked: what
they say about the rest of the file is true whatever the duplicate
resolved to. The rule matters most on `id`, since a manifest declaring
it twice carries the paper into a consumer under whichever value
happened to come last.

| key | required | rule |
|---|---|---|
| schema_version | yes | the integer 4; a JSON boolean is not an integer |
| id | yes | non-empty string matching `^[A-Za-z0-9._-]+$` with at least one letter or digit |
| title | yes | non-empty string, the title as printed |
| exhibits | yes | list of exhibit entries; may be `[]` |
| doi | no | string |
| summary | no | non-empty string when present |

- The id names output directories in consumers, so it is restricted to
  filename-safe characters, and ids without any letter or digit (".",
  "..") are rejected as path hazards.
- `summary` is the paper's short identity for consumers that need one
  without reading the full text; the paper's abstract is the natural
  value. An empty string is a mistake, not a signal.

### Exhibit entries

Each entry carries `label` and `caption` (required, non-empty strings)
and optionally `notes` (non-empty string when present). No other keys.

- `label` is the stem of the exhibit's `figures/<label>.png`, of its
  `tables/<label>.html` where it has one, and the token consumers cite
  when pointing at the image, so it obeys the same filename-safe pattern
  as the id and must be unique within the bundle.
- `caption` is the exhibit's caption as the paper prints it.
- `notes` is the exhibit's printed footnote text, plain. The crop
  includes the footnote lines as printed (they are part of the
  exhibit); `notes` carries the same words as text so a consumer reads
  them without reading pixels. An exhibit with no footnote omits the
  key. Exhibit footnotes do not appear in text.md.
- `exhibits` is required even when empty: the author either enumerates
  the exhibits or explicitly asserts the paper has none. A bundle that
  quietly ships no crops for a paper full of tables is not expressible.

## text.md

Required, UTF-8, non-empty. The full text of the paper as markdown.
The contract checks shape only; the authoring conventions that make a
good text.md (heading depths mirroring the paper, exhibit sentinels,
emphasis as printed, character fidelity) are the playbook's
`quality.md`, and the reason they matter downstream is that extraction
evidence is quoted verbatim against this file, markdown syntax
included.

## figures/

Optional as a directory: absent means no images, and the manifest's
`exhibits` is what says whether that is correct. When present, every
file is a `.png` whose stem is a declared label.

`alteksto.bundle.figure_files(path)` answers which files those are, label
to path, so a consumer reads the directory the way the validator does
rather than reimplementing the rule above.

Two cross-checks bind declaration to directory, both hard errors:

- every declared label must have its `figures/<label>.png`;
- every `figures/*.png` must be declared with its caption.

The first catches a manifest promising an image that is not there; the
second catches a stray or misnamed crop, which would otherwise become a
citable image no one vouched for.

## tables/

Optional as a directory, and optional exhibit by exhibit: absent means
no exhibit carries a transcription, which is what every exhibit meant
before this directory existed. When present, every file is a `.html`
whose stem is a declared label.

A transcription is the exhibit's content as text, beside the crop and
never instead of it. The crop remains required for every declared
exhibit, and it remains what the exhibit *is*: a transcription is a
reading of it, offered so that a consumer can quote a cell, slice a
column, or hand a model rows rather than pixels. Where the two
disagree, the page decides, then the crop.

`alteksto.bundle.table_files(path)` answers which files those are, label
to path, the way `figure_files` does for crops.

### What one file holds

Exactly one `<table>` element and nothing around it: no document, no
declaration, no comment, no marked section. That last one is named
because parsers disagree about where a marked section ends, so the same
bytes could give the validator and a consumer different cells. Within
it:

- **Elements**: `table`, `thead`, `tbody`, `tr`, `th`, `td`, and inside
  a cell `sup`, `sub`, `br`, `em`, `strong`. Nothing else. `caption` is
  refused by name, because the caption is carried by text.md and the
  manifest and repeating it here would give a consumer two of them.
  `tfoot` is refused for the same reason: the printed footnote is the
  manifest's `notes`.
- **Attributes**: `colspan` and `rowspan` on a cell, `scope` on a `th`
  (`col`, `row`, `colgroup` or `rowgroup`). No others, `style` and
  `class` included: they say how a table looks, and how it looks is
  what the crop is for.
- **The grid must tile exactly.** Laying the cells out row by row, each
  taking the next free position and claiming the positions its spans
  cover, every position in the table's rectangle is covered exactly
  once. A hole is a cell that went missing or a span one too small; an
  overlap is two cells claiming one position. This is the rule that
  makes a transcription worth having: both faults read plausibly and
  both put a value in a column it does not belong in, and neither is
  visible to a reader of the markup.
- **Every row carries at least one cell**, and **a span may not reach
  past the last row.** Together these close the way round the rule
  above, which is to silence a hole by widening the rowspan over it.
  That tiles perfectly, the missing row stays missing, and the two
  files draw identically, so the render cannot tell them apart either.
  One rule alone is not enough: with only the second, the row is kept
  and emptied instead of deleted, which is the same loss for one edit
  less. A row whose positions are all claimed from above prints
  nothing, so no exhibit has one.
- **Limits.** One span is at most 1000, and a table at most 100,000
  cell positions. No printed exhibit approaches either. The second is
  counted as the cells are read rather than from the finished
  rectangle, because the positions are recorded as they are claimed: a
  single cell carrying both spans at their ceiling claims a million of
  them, so a file of a few hundred bytes could otherwise cost the
  validator that gates every conversion gigabytes before anything was
  in a position to call the grid too large.
- **Cell text is the characters the exhibit prints**, on the same terms
  text.md holds the paper's: transcribed as printed, typos included. A
  cell the exhibit leaves empty is an empty cell here, never a dash
  invented to fill it and never dropped, because dropping it is what
  slides the rest of the row sideways.
- **Rows are in reading order** whatever the page's orientation. A
  landscape table set sideways is transcribed as it reads, not as it
  sits on the sheet.

### The cross-check

One direction is an error: every `tables/*.html` must have its label
declared in `exhibits`. A declared exhibit with no transcription is the
ordinary case and says nothing at all.

The asymmetry is the point. A transcription that names no declared
exhibit is content nobody vouched for, refused on the same grounds as a
stray crop. But a bundle is free to transcribe all, some or none of its
exhibits, and there is no field marking a transcription as provisional
or unchecked. A file is here or it is not, and one that is here has
passed this contract and the producing route's gates. A consumer that
finds no file learns that the crop is the content, which it can act on;
a consumer told the file exists but is not to be trusted could not.

## supplements.json and supplements/

Optional, and absent together: no `supplements.json` and no
`supplements/` means the bundle carries the article alone, which is what
every bundle carried before this version.

A supplement directory with no `supplements.json` beside it is an error,
and so is a declaration naming a supplement that is not there. An empty
`supplements/` directory declares nothing and is nothing, so it is not an
error on its own. `supplements/` holds directories and nothing else: a
loose file in it is refused whether or not there is a declaration beside
it, because it is neither a supplement nor a supplement's asset and
nothing would ever read it.

A supplement is the paper's supplementary material, converted as its own
thing and kept out of the article. That separation is the whole point of
the shape, and it is worth saying why, because merging the two would be
less work.

- **A screening decision must not be re-identified by a supplement
  arriving.** A review may reasonably judge eligibility from the article
  and extract data from the supplement, in that order. That order is
  only available if the article's identity does not move when the
  supplement lands. `manifest.json` and `text.md` are the article's and
  stay byte for byte what they were, so a consumer that hashes them, as
  the screening side does, is untouched. A consumer that reads the whole
  bundle, as the extraction side does, sees the addition and should.
- **They are different artefacts.** A supplement is often not reviewed
  to the article's standard, is versioned separately, and can be revised
  after publication. A bundle that merged them could not say which of
  the two a given claim rests on, and for anything that quotes a
  supplement verbatim that distinction is the claim.

### supplements.json

A single JSON object. Unknown keys are errors, and so is a repeated key,
on exactly the manifest's terms and for the same reason.

| key | required | rule |
|---|---|---|
| id | yes | the manifest's `id`, character for character |
| supplements | yes | non-empty list of supplement entries |

- The `id` is checked against the manifest's because a declaration
  copied between bundles is otherwise undetectable, and it would attach
  one paper's supplements to another paper. A supplement has no identity
  of its own: no DOI, no title page, no existence apart from the article
  it belongs to.
- There is no `schema_version` here. One bundle declares one version,
  in the manifest, and this file is part of that bundle rather than a
  document beside it.
- An empty list is an error, not an assertion. A paper with no
  supplements omits the file, which says the same thing without a second
  place to keep in step.

Each entry carries `name`, `title` and `exhibits`. No other keys.

- `name` names `supplements/<name>/` and is the token a consumer asks
  for a supplement by, so it obeys the whole of the id's rule, pattern
  and at least one letter or digit both, and must be unique within the
  bundle. The second half is not decoration: the name is used directly
  as a path component, so a supplement named `..` would otherwise send
  every check below it to the bundle root and report the article's own
  crops as that supplement's undeclared files.
- `title` is what the paper calls the supplement, as printed
  ("Supplement 3. Characteristics of included studies"). It is what a
  consumer choosing between supplements chooses on, and `name` alone is
  too thin to choose on.
- `exhibits` is declared on exactly the manifest's terms, `label` and
  `caption` and optional `notes`, and may be `[]` when the supplement
  holds no tables or figures.

### supplements/<name>/

Shaped like the bundle around it, minus the identity it does not have:

    supplements/<name>/
      text.md     (optional)  the supplement's prose, UTF-8, non-empty
      figures/    (optional)  its crops, on the bundle's rules
      tables/     (optional)  its transcriptions, on the bundle's rules

`text.md` is optional here where it is required at the top level,
because a supplement that is nothing but data tables prints no prose and
inventing one would mean inventing the prose. `figures/` and `tables/`
are held to what the bundle's own are held to, and bound to the
supplement's declaration in `supplements.json` the same way and in the
same directions.

`alteksto.bundle.supplement_dirs(path)` answers which supplements a
bundle carries, name to path. Handing one of those paths to
`figure_files` or `table_files` reads that supplement's assets, which is
why the directory is shaped this way: the functions that read a bundle
read a supplement unchanged.

### One label, one exhibit, across the whole bundle

An exhibit label must be unique across the article and every supplement,
not merely within each. A consumer cites an exhibit by its label alone,
the filename stem being the whole of the citation, and looks it up in
one flat map. An article `table_01` and a supplement `table_01` are then
two images with one name, and the citation resolves to whichever was
loaded second. Nothing downstream is placed to notice, so it is refused
here, where every label in the bundle is visible at once. Prefixing a
supplement's labels with its name (`supplement_3_table_01`) is the
convention that keeps them apart.

## What validation cannot see

No check reads the pixels or the prose. A crop that clips its header
row passes; a text.md with a fabricated paragraph passes; a paper full
of tables with an empty (but declared) exhibit list passes. A
transcription whose grid tiles perfectly while every number in it is
invented passes too, and so does one attached to an exhibit that is a
photograph. The tiling rule is narrower than it sounds in one specific
way worth knowing: it catches a cell that leaves its row short, but a
cell dropped and absorbed by a neighbour's `colspan` still tiles, and
cell merging is a common way a table is misread. That one is the
render's to catch, because a merged cell and two cells do not draw
alike. Those are held by the producing route's gates (the
playbook) and by whoever reads the bundle, not by this contract.

The transcription is the place where that gap matters most, because
text invites quoting in a way an image does not. What closes it is the
producing side: the structural check here, then a render of the
transcription compared against the crop
(`tools/render_table.py`), then the fresh-context sweep. A bundle
reaches a consumer having been through all three, which is what makes
"the file exists" mean something.
