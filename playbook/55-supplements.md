# Stage 5b: supplements

A paper's supplementary material is converted as its own thing and kept
out of the article. It reaches the bundle as `supplements/{name}/`, a
directory shaped like the bundle around it, declared in
`supplements.json`.

This stage runs only when supplements were staged. Nothing is fetched
here: a supplement arrives at
`work/{id}/supplements/{name}/source.pdf` because a caller put it
there, the same way the article did (`docs/calling.md`). A paper whose
supplement nobody staged has no supplements, and that is not this
stage's problem to notice.

## Why it is separate rather than appended

Two reasons, and the first constrains what you may do here more than it
looks.

- **A screening decision must not be re-identified by a supplement
  arriving.** A review may judge eligibility from the article and
  extract data from the supplement, in that order, and that order is
  only available while the article's identity does not move when the
  supplement lands. So `text.md` and `manifest.json` are the article's
  and stay exactly what they were: a supplement's prose never joins
  `text.md`, its exhibits never join the manifest, and its sentinels
  never appear in the article's text. Appending would be less work and
  would silently invalidate work already done downstream.
- **They are different artefacts.** A supplement is often not reviewed
  to the article's standard, is versioned separately, and can be
  revised after publication. Keeping them apart is what lets a
  consumer say which of the two a claim rests on.

## What a supplement gets

The same route, minus the parts that belong to a paper and not to a
supplement:

- **Triage** as usual: a supplement is born-digital or scanned like
  anything else, and which it is decides the character source.
- **Sources** without the web witness. A supplement has no DOI of its
  own, so there is no PMC lookup to make; render the pages and dump the
  text layer as ever, and OCR on the same terms as the article.
- **Skeleton** over the supplement's own pages, as its own inventory.
- **Walk** into `bundles/{id}/supplements/{name}/text.md`, on every
  rule in `quality.md`. **A supplement that prints no prose writes no
  text.md at all**: it is optional here where it is required for the
  article, and inventing one means inventing the prose. A supplement
  that is a run of data tables and nothing else is the common case.
- **Figures**, exactly as stage 50 describes, into
  `bundles/{id}/supplements/{name}/figures/`, transcriptions into
  `.../tables/`. The crop loop, the transcription rules and the render
  comparison are the same; nothing about them is relaxed here.
- **No reference canary.** It measures a paper's reference list, and a
  supplement does not have one of its own.

## Labels carry the supplement's name

An exhibit label is unique across the whole bundle, not merely within
the supplement, because a consumer cites an exhibit by its label alone
and looks it up in one flat map. So a supplement's exhibits are
labelled with its name in front:

    supplement_3_table_01, appendix_a_figure_02

`Table 1` of the article and `Table 1` of Supplement 3 are two exhibits
and must not both be `table_01`. The validator refuses a collision, but
it refuses it at the end of the run: label them this way from the
skeleton on and it never arises.

## The declaration

When a supplement is finished, write what it holds to
`work/{id}/supplements/{name}/declaration.json`:

    {
      "name": "supplement_3",
      "title": "Supplement 3. Characteristics of included studies",
      "exhibits": [
        {"label": "supplement_3_table_01", "caption": "..."}
      ]
    }

`title` is what the paper calls the supplement, as printed. It is what
a consumer choosing between supplements chooses on, so "Supplement 3"
alone is thin and the printed heading is right. `exhibits` is on
exactly the manifest's terms, `label` and `caption` plus `notes` where
the exhibit prints a footnote, and `[]` when the supplement holds no
tables or figures at all.

Then assemble, once, after every supplement is done:

    python tools/assemble_supplements.py work/{id} --bundle bundles/{id}

It collects every declaration into `bundles/{id}/supplements.json` and
takes the paper's id from the bundle's own manifest, so the two cannot
disagree. It writes nothing when there are no declarations.

Do not hand-write `supplements.json`, and in particular do not have two
supplements write into it. The route runs one converter per paper-like
unit, so supplements can be in flight at once, and two writers on one
file is a race whose loser vanishes without a word. Each writes its own
declaration; the assembly is the only thing that touches the shared
file, and it runs when nothing else is running.

## One converter or several

Convert the supplements yourself, in sequence, and that is usually the
end of it: most are a few pages.

A supplement large enough to crowd the article out of your context is
the case for a converter of its own, on the route's standing terms: one
paper-like unit per agent, the driver works in text only and never
reads a page image, and the subagent delivers through a file in the
work directory, which here is exactly the declaration above. That the
handoff is already a file is why this splits cleanly.

## Outputs

- `bundles/{id}/supplements/{name}/` holding `text.md` where the
  supplement prints prose, `figures/*.png`, and `tables/*.html`.
- `work/{id}/supplements/{name}/declaration.json` for each, and the
  supplement's own intermediates beside it, on the same terms as the
  article's: renders, dumps, skeleton, exhibit dumps, table renders.
- `bundles/{id}/supplements.json`, assembled.

Before leaving the stage, count as stage 50 does, once per supplement:
skeleton exhibits, crops on disk, and declared exhibits match one to
one to one. Then check the labels: every one carries its supplement's
name, and no label appears twice anywhere in the bundle.
