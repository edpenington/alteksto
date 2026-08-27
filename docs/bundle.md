# The paper bundle: format specification

This repository owns the paper bundle format. The specification below
is normative: `tools/validate_bundle.py` enforces it, a converter
produces to it, and downstream consumers read it. The format evolves
here, by a `schema_version` bump, and consumers follow. The number
moves for any change to what counts as a bundle: what one may carry,
and what bundles are valid.

## Layout

One directory per paper, self-contained and human-authorable.

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

Those six names are matched exactly, and so are the three inside a
supplement. `Figures/` is not `figures/`. The rule is stated because
the common case is invisible without it: a case-insensitive filesystem,
which is the macOS default, answers to either spelling, so a bundle
built there validates while holding nothing a case-sensitive consumer
can open. A name that merely resembles none of the six is nobody's
business, so `Notes.md` beside them is fine.

## manifest.json

A single JSON object. Unknown keys are errors, at the top level and
inside each exhibit entry. So is a repeated key, at any depth. Python's
`json`, like most readers, keeps the last value of a repeated key and
drops the rest without a word, which makes it the one malformation no
check after the parse can report: the evidence is gone before anything
runs. It is refused during the parse, the last moment both values still
exist. Keys are compared after JSON string unescaping, so `\u0069d` and
`id` are the same key. Every repeated key in the file is named, with
its position, and nothing else is: a check on a duplicated key reads
whichever value the parse kept, so it would report a `schema_version`
the file may also state correctly, and carry an arbitrary `id` on into
the comparison with supplements.json to accuse the wrong file. The rule
matters most on `id`, since a manifest declaring it twice carries the
paper into a consumer under whichever value happened to come last.

| key | required | rule |
|---|---|---|
| schema_version | yes | the integer 5; a JSON boolean is not an integer |
| id | yes | non-empty string; the name rule below |
| title | yes | non-empty string, the title as printed |
| exhibits | yes | list of exhibit entries; may be `[]` |
| doi | no | string; may be empty where the paper prints none |
| summary | no | non-empty string when present |

- The id names output directories in consumers, so it is restricted to
  filename-safe characters, and ids without any letter or digit (".",
  "..") are rejected as path hazards.
- A leading dot is refused wherever this rule applies, though a dot
  elsewhere (`fig.01`) is fine. Every walk over a bundle, this
  validator's and a consumer's, skips dot-leading entries as OS
  metadata, so a dot-leading name would declare a file nothing ever
  reads, and the report about it would tell an author a file that is
  really there is missing.
- `summary` is the paper's short identity for consumers that need one
  without reading the full text; the paper's abstract is the natural
  value. An empty string is a mistake, not a signal.

### Exhibit entries

Each entry carries `label` and `caption` (required, non-empty strings)
and optionally `notes` (non-empty string when present). No other keys.

- `label` is the stem of the exhibit's `figures/<label>.png`, of its
  `tables/<label>.html` where it has one, and the token consumers cite
  when pointing at the image, so it obeys the whole of the id's rule,
  pattern and at least one letter or digit both, and must be unique
  within the bundle. It takes a suffix and stays a leaf, so it cannot
  traverse the way an id can; the second half is there because a label
  of punctuation alone is not a token anything can cite.
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
The contract checks shape only. The conventions that make a good
text.md (heading depths mirroring the paper, exhibit sentinels,
emphasis as printed, character fidelity) belong to the converter that
writes one, and differ between converters on purpose.

## figures/

Optional as a directory: absent means no images, and the manifest's
`exhibits` is what says whether that is correct. When present, every
file is a `.png` whose stem is a declared label.

The suffix is exactly `.png`, lowercase. `.PNG` is a stray file and is
refused as one. The rule is exact rather than case-insensitive because
this specification promises a consumer the literal path
`figures/<label>.png`: on a case-sensitive filesystem a case-insensitive
rule would validate a bundle whose promised path does not exist, and it
would let `x.png` and `x.PNG` sit side by side and merge into one label
with nothing said about the one that lost.

A crop is a non-empty regular file whose first eight bytes are the PNG
signature. That is not a check on the image: nothing here decodes a
pixel, and what the crop shows is beyond this contract. It is a check
that the file is one, so that "no problems" cannot be said over an empty
file, a JPEG that was renamed, or a symlink to nothing. Every supplement's
crops are held to the same rule.

`alteksto.bundle.figure_files(path)` answers which files those are, label
to path, so a consumer reads the directory the way the validator does
rather than reimplementing the rule above.

Two cross-checks bind declaration to directory, both hard errors:

- every declared label must have its `figures/<label>.png`;
- every `figures/*.png` must be declared with its caption.

A crop's stem obeys the label rule before either of those runs. A stem
no declaration could carry would otherwise be told to declare itself,
and an author following that advice earns the name rule's refusal for
doing so.

The first catches a manifest promising an image that is not there; the
second catches a stray or misnamed crop, which would otherwise become a
citable image no one vouched for.

## tables/

Optional as a directory, and optional exhibit by exhibit: absent means
no exhibit carries a transcription. When present, every file is a `.html`
whose stem is a declared label. The suffix is exactly `.html`,
lowercase, on the same terms and for the same reasons as `.png`.

A transcription is the exhibit's content as text, beside the crop and
never instead of it. The crop remains required for every declared
exhibit, and it remains what the exhibit *is*: a transcription is a
reading of it, offered so that a consumer can quote a cell, slice a
column, or hand a model rows rather than pixels. So where the two
disagree, the transcription is what is wrong. The exception is a crop
cut from the wrong region, which only the printed page settles, and
which a producer settles before either file is written. No check
compares the two, and the page is not in the bundle to compare them
against: a consumer that has to choose, chooses the crop.

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
  what the crop is for. A span's value is ASCII digits naming a whole
  number of at least one, so the forms HTML tolerates and reinterprets
  (`0`, a sign, a decimal point, surrounding space, digits from another
  script) are refused rather than guessed at. An attribute written with
  no value is refused, and an attribute written twice is refused: a
  parser keeps the first and silently drops the rest, which is a value
  in the file that nothing will ever read.
- **Every element is opened and closed**, `<br>` excepted, which is the
  one void element a cell may carry. The self-closing form of anything
  else is refused, because HTML gives `<td/>` no meaning and parsers
  disagree about what follows it.
- **A byte order mark at the start of the file is ignored.** It is
  ignored here and fatal in `manifest.json`, which is not an
  inconsistency: JSON has no place for one and this format does not
  invent one, while HTML has always tolerated it and refusing it would
  refuse files that every consumer reads correctly.
- **An empty file is not a transcription.** An exhibit with nothing to
  transcribe omits the file; a `tables/<label>.html` that exists says
  the exhibit's content is in it.
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
nothing would ever read it. `supplements` must itself be a directory,
and a file of that name is refused in those words rather than reported
as every declared supplement being absent, which is the same fault said
once instead of once per supplement.

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
  too thin to choose on. A non-empty string, as the manifest's is.
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

## What the validator promises

`alteksto.bundle.bundle_problems(path)` returns a list of strings, one
per problem, and an empty list means valid. Three promises hold for any
input at all, a hostile one included:

- **It never raises.** Not for a malformed bundle, and not for a disk
  that will not cooperate. A directory that cannot be listed, a file
  where a directory belongs, a symlink to nothing, a JSON number too
  long for the interpreter to build: each is answered with a problem.
- **It never blocks.** A path that is not a regular file is refused as
  one before anything opens it, so a pipe or a device named `text.md`
  cannot leave a run waiting forever. Not returning would be worse than
  raising, because nothing downstream could tell it apart from slow.
- **Every problem it reports is true of the file it names.** This is the
  one that costs something. Where a check would have to read a value it
  cannot trust, it does not run: a cross-check is skipped when either
  side is malformed, a manifest with a repeated key ends its own report,
  and an unreadable directory is one problem rather than a claim about
  each file it might have held. So a report is not always complete, and
  fixing what it names and running again is part of using it. A problem
  derived from a guess reads exactly like one derived from a fact, and
  would bury the fault it grew from.

The words a problem uses matter as much as the rule behind it. A
problem names the file, says what is wrong with it, and says why the
rule exists, so that an author can act on it without reading this
document. It never quotes an interpreter's advice about how to make the
reader accept the file, because that is the wrong way round: the fault
is the bundle.

## What validation cannot see

A bundle is not checked for self-containment. A `text.md` that is a
symlink to somewhere outside the bundle validates, and travels as a
dangling link. Two things the parse tolerates are worth naming too: a
JSON literal of `NaN` or `Infinity`, which Python's reader accepts and
this format's typing then refuses on other grounds, so such a file
never validates but is never called invalid JSON either.

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
alike. Those are held by whatever checks a converter runs on its own
way to a bundle, and by whoever reads the bundle, not by this contract.

The transcription is the place where that gap matters most, because
text invites quoting in a way an image does not. What closes it is the
producing side: the structural check here, then a render of the
transcription compared against the crop, then the fresh-context sweep.
Both are the producing side's to arrange, and how an engine arranges them
is its own business. A bundle reaches a consumer having been through all
three, which is what makes "the file exists" mean something.
