# The worked example

One invented mini-paper, three pages, small enough to hold in the head
and still carrying the hazards the route exists to handle. Agent runs
against it are manual; the toolbelt runs against it in CI, as
`tests/test_example.py`.

Nothing here is a real paper. The levels, the herons, the wardens, the
journal, and the references are all invented, which is why this
directory can live in git when `work/` and `bundles/` cannot.

## Building it

    python examples/build_pdf.py work/example --supplement

writes `work/example/source.pdf` and, with `--supplement`,
`work/example/supplements/supplement_a/source.pdf` where a staged
supplement would sit. A work directory like any other from there on. No PDF is committed: `build_pdf.py` is the source, and the
binary is built whenever it is wanted.

## What is committed

    build_pdf.py            the paper and its supplement, as the code
                            that prints them
    expected/skeleton.json  the inventory stage 3 should arrive at
    expected/bundle/        text.md, manifest.json, tables/ and
                            supplements/, the bundle to match
    expected/crops.json     the crop region for each exhibit, the
                            supplement's under its own key

`expected/bundle/tables/table_01.html` is the printed table as text,
the transcription a correct figure stage arrives at. The paper's own
table is plain, so the supplement prints the harder shape: a group
header spanning two columns over a stub spanning two rows, and two
cells the survey left empty. The ways a grid can fail to tile are
covered by `tests/test_validate_bundle.py`, where a wrong table can be
written down beside the right one.

`expected/bundle/supplements/` and `expected/bundle/supplements.json`
are Supplement A converted as its own thing. Its prose is in its own
text.md and its exhibit is declared in supplements.json, so neither the
paper's text.md nor its manifest moves when the supplement is added,
which is what lets a consumer identify the article by those bytes
whether or not the supplement is there yet.

There is no `expected/bundle/figures/`, because a PNG is a binary.
`crops.json` records each exhibit's page and box instead, so a run cuts
the same pixels from its own 150 DPI render and compares those.

## The hazards it plants

- a running head and a page number on every page, and a DOI in the page
  one footer that the manifest carries and text.md does not;
- an author line with affiliation markers, and a correspondence note
  printed at the foot of page one, both of them front matter;
- headings at two depths under the title;
- italic statistics (`et al.`, `p`, `t`) set in real italic fonts, so
  the layer's flags make `dump_blocks.py` emit the emphasis runs;
- a word broken across a line break, `compart-` then `ments`;
- Table 1, drawn with real rules, its caption above the crop and its
  printed footnote line inside it;
- Figure 1, drawn as vector art, its own printed title and legend
  inside the crop and its caption below, outside;
- a sentence that begins on page two and finishes on page three;
- three references, one of them printing a DOI.

## The run, as the playbook now shapes it

One context converts and the sweep is the fresh eyes. The
expected files are the checkpoints to compare against, stage by stage.

1. **Triage.** Render and dump. The layer is healthy and reads as
   language, so the paper is `born_digital` and the text layer is the
   character source.
2. **Witnesses.** OCR offline with `--transport fake`. There is no PMC
   record for an invented DOI, so the run warns loudly and continues
   with one fewer witness. The fake transport reports image blocks, and
   this paper's figure is vector art, so `images.json` proposes nothing
   at all: both exhibits are located from the render, which is the path
   every table takes anyway.
3. **Skeleton.** Ten units over three pages, two exhibits, three
   references. Against `expected/skeleton.json`: the page spans cover 1
   to 3 with no gaps, there is a single depth 1 unit, and unit 7 carries
   the note that it crosses the page join.
4. **Walk.** Unit by unit against the skeleton. The two seams that
   matter are the float interposed inside 2.2 and the mid-sentence join
   between pages two and three, where page two ends "of the opposite
   sign, a". Against `expected/bundle/text.md`: character-faithful to
   what the page prints, the hyphen healed, the furniture gone, the
   emphasis carried, the exhibits standing as sentinels.
5. **Figures.** Two crops. Against `expected/crops.json` for the
   regions, and the manifest for the entries: the table's printed
   footnote becomes its `notes`, and the figure, having none, omits the
   key.
6. **Gates.** `validate_bundle.py` passes clean on the assembled
   bundle. The reference canary is the one step the example cannot
   answer, its DOI being invented: it resolves nothing, loudly, which
   is the case the stage describes. Then the sweep reads the bundle
   fresh and reports.
