# The paper bundle: format specification

This repository owns the paper bundle format. The specification below
is normative: `tools/validate_bundle.py` enforces it, the playbook
produces to it, and downstream consumers (*meltiro* first among them)
read it. The format evolves here, by a `schema_version` bump, and
consumers follow.

The format is at `schema_version` 2. A bundle declares that version and
a consumer accepts it; a bundle declaring any other version is not a
bundle.

## Layout

One directory per paper, self-contained and human-authorable. Papers
are copyrighted, so bundles are never committed; they are produced and
consumed at run time.

    paper-bundle/
      manifest.json    (required)  identity and the exhibit declaration
      text.md          (required)  the paper's full text as markdown, UTF-8
      figures/         (optional)  cropped tables and figures, *.png only

Extra files beside the three contract entries are ignored by consumers,
so a bundle may carry its own paperwork. Inside `figures/`, nothing
extra is tolerated: a non-png file or a subdirectory is an error, and
only hidden OS metadata (dotfiles) is skipped.

## manifest.json

A single JSON object. Unknown keys are errors, at the top level and
inside each exhibit entry.

| key | required | rule |
|---|---|---|
| schema_version | yes | the integer 2; a JSON boolean is not an integer |
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

- `label` is the stem of the exhibit's `figures/<label>.png` and the
  token consumers cite when pointing at the image, so it obeys the same
  filename-safe pattern as the id and must be unique within the bundle.
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

## What validation cannot see

No check reads the pixels or the prose. A crop that clips its header
row passes; a text.md with a fabricated paragraph passes; a paper full
of tables with an empty (but declared) exhibit list passes. Those are
held by the producing route's gates (the playbook) and by whoever reads
the bundle, not by this contract.
