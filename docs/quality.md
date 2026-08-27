# Quality

`docs/bundle.md` specifies the paper bundle format and
`tools/validate_bundle.py` enforces it. Neither checks a bundle against
the document it was made from. This document describes the principles
and conventions of accurate, consistent and high quality conversion of
input papers to paper bundles. No check enforces them: they are the
point of reference for assessing human and agentic bundle generation,
and the target every *alteksto* engine writes to. Where an engine's
playbook and this document disagree, this document is the target and
the playbook has not caught up.

A bundle holds `text.md`, `manifest.json`, a crop per exhibit in
`figures/{label}.png`, a transcription in `tables/{label}.html` for
each table whose characters can be read, and, where the paper has
supplementary material, `supplements.json` and each supplement's own
prose, crops and transcriptions under `supplements/`; `docs/bundle.md`
has the whole contract. An exhibit is a table or a figure, or one
page's part of one. Its crop is its image, its sentinel is the line in
`text.md` that marks its place in the reading order, and its label is
the stem of its files.

A supplement's own `text.md`, crops and transcriptions are judged by
the same rules, minus the front matter it does not have. Its prose
never joins the article's `text.md` and its exhibits never join the
manifest. Its `title` in `supplements.json` is what the paper calls
it, as printed, its labels carry its name as a prefix
(`supplement_3_table_01`), and a supplement that prints no prose has
no `text.md`.

A high quality bundle meets the following principles:

- **Faithful**: the content in the bundle is identical to the content
  in the input document, including errors, typos and formatting.
- **Complete**: all substantive elements of the input document are
  included in the bundle, regardless of their perceived value.
- **Predictable**: the document's content is arranged in a reliable
  and consistent way, following conventions that hold across documents
  and make the result human- and machine-readable.

## Faithful

What the paper prints is what the bundle carries, minus the characters
that layout and typesetting introduced, plus the markup for headings,
lists, emphasis, superscripts, subscripts and mathematics, and the
sentinels that stand for exhibits.

- **Characters are the paper's.** Typos, odd spacing in names, and
  inconsistent capitalisation are transcribed as printed. En dashes
  stay in numeric ranges. Line-break hyphens are healed and lexical
  hyphens stay, because the first is the typesetter's and the second is
  the word's. Soft hyphens, zero-width spaces, and other invisible
  characters do not exist in the bundle.
- **Superscripts and subscripts are carried**, in `text.md` in
  pandoc's syntax (`effective^5–7^`, `Smith^1^`, `10^3^`, `CO~2~`) and
  in a transcription as `<sup>` and `<sub>`. Citation markers,
  footnote markers, affiliation markers, exponents and chemical
  subscripts are one thing here, and flattened they are
  indistinguishable from an ordinary digit.
- **Emphasis is the paper's.** Bold and italic are carried where the
  paper prints them and never added where it does not. Inline math
  stays in plain characters where the printed characters allow
  (*p* < 0.001, *r* = -0.34); LaTeX, in `$...$`, only where neither
  those nor a superscript can say it.
- **The source's defects are preserved.** Papers contain typos,
  garbled reference entries, broken URLs, statistics that differ
  between caption and body, and captions describing fewer panels than
  the figure shows. These are the paper's, not the conversion's. The
  bundle carries them. Correcting the source is fabrication.
- **Nothing is invented.** No text or heading the paper does not
  print, no helpful additions.
- **A crop holds the whole exhibit and nothing else.** Every panel,
  the axis labels including any in the gutter between panels, the
  printed footnote lines, and the caption. Nothing from the
  neighbouring column or the exhibit above comes with it. An exhibit
  cut across a page join is cropped once per page, each part an
  exhibit of its own, and never stitched into an image the paper does
  not print.
- **A figure's content is its pixels.** Text inside a figure is never
  transcribed, in `text.md` or anywhere else.
- **A table transcription says what its crop shows and does not
  improve it.** No range tidied, no decimal aligned, no thousands
  separator added where the paper prints none, no empty cell dropped
  rather than transcribed as empty, and no span widened to cover a
  cell that went missing. A table whose characters cannot be read gets
  no transcription: a missing file is honest and a guessed one is not.
- **The manifest carries the paper's own identity.** `title` exactly
  as printed, `doi` where the paper prints one, and `summary` the
  paper's abstract where it has one, so a consumer can identify the
  article without reading `text.md`.

## Complete

Everything the paper prints is somewhere in the bundle, furniture
aside, and the rules below say where.

- **Every unit is present.** Every section, paragraph, exhibit,
  footnote, and reference entry.
- **Exhibit footnotes belong to the exhibit.** The crop includes an
  exhibit's printed footnote lines and the manifest's `notes` carries
  their text. They never appear in `text.md`.
- **Content footnotes are placed.** A genuine content footnote goes at
  the end of the section that references it, opening with the marker
  the paper prints. The same marker stands in the prose where the
  paper prints it.
- **Front matter is grouped, never scattered through the prose.**
  Title, authors with their affiliation markers as printed, then
  abstract and keywords where present. Author emails, correspondence and
  affiliation notes join the front matter, or stay in back matter
  where the paper prints them there. None of them interrupts
  contiguous prose, and each is carried in full. A journal's citation
  line in the header or footer band is furniture; in the article's own
  front matter it is carried with it. Licensing and submission
  boilerplate stays out.
- **Page furniture is excluded.** Running heads, footers, page
  numbers, publisher badges, and "downloaded from" boilerplate never
  appear, and paragraphs read continuously across page and column
  joins.

## Predictable

What a conversion recovers is the contiguous text a paper had before it
was laid out. Layout decisions carry no authorial information: where a
float lands on a page, where a paragraph breaks across a column, where
a page ends. Where a rule undoes a layout decision it picks one way of
doing it, so that two conversions of the same paper land in the same
place and a consumer reading two bundles does not have to learn two
shapes. Where a rule could reasonably have gone either way, it went
one way and is written down.

- **Heading depth mirrors the paper.** The paper title is the single
  `#` and the paper's top level sections are `##`; beyond that, each
  nesting step the paper prints is one more `#`, following the paper's
  own conventions. Heading text is transcribed as printed, section
  numbers included. Headings are neither invented nor dropped:
  material the paper prints without a heading flows unheaded in its
  reading position.
- **An exhibit is a sentinel in the text and a crop in `figures/`.**
  The sentinel's form is

      [TABLE 2. Caption exactly as printed.]

  with the paper's word for the exhibit in capitals, its number as the
  paper prints it, and the caption matching the manifest entry.
- **A sentinel sits at a paragraph boundary, never inside a
  paragraph.** Where the page prints an exhibit inside a paragraph, the
  sentinel goes after that paragraph, and it never crosses a heading:
  an exhibit printed in one section does not migrate into the next.
- **An exhibit cut across a page join is a separate exhibit per page.**
  The first page's crop carries the plain label and each later page's
  crop appends its place in the exhibit's run of pages, `table_02_p2`
  for the second page of `table_02`. Each part has its own manifest
  entry, with the caption its page prints; a page that prints no
  caption line repeats the first part's, since every entry carries
  one. A table part's transcription is its own `tables/{label}.html`,
  read from its own crop. One sentinel serves every part, matching the
  first part's entry.
- **Table content never appears in `text.md`.** The crop is the
  exhibit, and a table's content, where its characters can be read,
  goes to `tables/{label}.html`.
- **The caption is part of the crop**, above a table or below a figure
  as the journal prints it, and carried as text in the sentinel and
  the manifest entry as well. A crop that clips its caption at either
  end is wrong. A continuation page's crop carries the caption line
  its page prints, where it prints one, and never the first page's.
  The caption is not a row: a caption printed directly above the top
  rule is still the caption, and transcribing it as a header row is a
  defect.
- **References are one markdown list item per entry**, in the paper's
  own citation style, characters exact.
