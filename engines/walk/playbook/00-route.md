# The route

This file is the converter's manual, and it addresses the agent
converting one paper. If you have papers to hand off rather than a
paper to convert, `docs/calling.md` is the whole calling contract:
spawn one converter per paper and stop reading here.

One paper PDF becomes one paper bundle: markdown full text, cropped
figures and tables, a manifest, passing validate-bundle against the
format this repo owns (docs/bundle.md). The conversion runs in six
stages, with a seventh that runs only when there is supplementary
material to convert:

    triage -> acquire -> skeleton -> walk -> figures -> [supplements] -> gates

Each stage has its own file in this directory. Supplements are
`55-supplements.md`, between figures and gates: the gates cover the
whole bundle, supplements included, so they run last. `quality.md` describes
what a good bundle looks like and catalogues the defects to expect; read
it before starting and hold it in mind throughout.

## The shape of a run

Everything intermediate lives in the paper's work directory and never in
the bundle:

    work/{id}/
      source.pdf           the input; the run fails without it
      triage.json          stage 1's classification
      pages/page_NN.png    150 DPI renders, the ground truth
      blocks.json          text layer: page sizes in points, then records
                           (page, index, bbox, text)
      blocks.txt           text layer flattened, page marker lines
      ocr/page_NN.md       OCR markdown per page
      ocr/images.json      OCR image bboxes per page, with page dimensions
      ocr/meta.json        OCR usage and cost
      web.md               PMC full text, when it exists
      skeleton.json        stage 3's inventory, the coverage contract
      exhibit_dumps/       raw text-layer blocks under each crop region
      table_renders/       each table transcription drawn, for comparison
                           against its crop
      supplements/{name}/  one per staged supplement, holding its own
                           source.pdf and the same intermediates again,
                           plus declaration.json, what it holds
      refs-report.md       the reference canary's verdicts
      sweep-report.md      the fresh-context sweep's findings

The bundle lands in `bundles/{id}/` as `manifest.json`, `text.md`,
`figures/*.png`, and `tables/*.html` for the table exhibits whose
content was transcribed and checked, exactly per the contract (see
quality.md). A paper with supplementary material also carries
`supplements.json` and one `supplements/{name}/` per supplement.

## Rules that span every stage

- **Re-entrancy.** Every stage checks for its own output first. If the
  output exists and passes the stage's sanity checks, validate it and
  move on rather than redoing it. A half-finished run resumes where it
  stopped.
- **Loud failures.** A missing input fails the run with a message naming
  what is missing. A missing witness (no web text, no usable OCR) is
  warned loudly and worked around: the route continues with one fewer
  witness and later stages are told which witnesses exist.
- **The renders are ground truth.** Every disagreement between text
  witnesses is settled by looking at the page image, not by preferring
  a witness on reputation.
- **One converter per paper; the sweep is the fresh eyes.** A paper
  gets a converter of its own, and that converter does the whole
  conversion in its own context: it reads its own renders, walks every
  unit, views its own crops, and batches independent reads into
  parallel tool calls in the same turn. Fresh eyes are the sweep's
  job, once, at the end, and cheap determinism (the emphasis runs, the
  validator, the canary) guards the middle. This rule governs what
  happens inside one paper and says nothing about how many papers run
  at once: many papers means many converters, one each, working in
  parallel and never in the caller's own context. Splitting a single
  paper across subagents is the fallback for a paper too large for one
  context; when splitting, the driver never reads a page image, works
  in text only, and subagents deliver their reports as files in the
  work directory (the driver reads files, never waits on messages).
- **Preserve the source, defects included.** Papers contain typos,
  garbled references, and mismatched statistics. The bundle transcribes
  what the paper prints. Correcting the source, however tempting, is
  fabrication.
- **Nothing copyrighted leaves the work tree.** Work directories and
  bundles are gitignored; paper text never enters a commit.

## The toolbelt

Each tool does one thing to one work directory and exits. Run them
through the project venv, from the checkout root, and type the paths as
written: this engine's tools are its own and live beside this playbook,
while the validator belongs to the format rather than to any engine and
sits at the root.

    python engines/walk/tools/stage.py --id ID --pdf PATH
        [--supplement NAME] --work work
    python engines/walk/tools/render_pages.py work/{id} [--dpi 150]
    python engines/walk/tools/dump_blocks.py work/{id}
    python engines/walk/tools/ocr.py work/{id} [--transport fake]
    python engines/walk/tools/fetch_pmc.py work/{id} --doi DOI
    python engines/walk/tools/crop.py work/{id}/pages/page_NN.png
        --box X0 Y0 X1 Y1 [--box ...] [--space W H]
        --out bundles/{id}/figures/{label}.png
    python engines/walk/tools/render_table.py
        bundles/{id}/tables/{label}.html
        --out work/{id}/table_renders/{label}.png [--rotate 90]
    python engines/walk/tools/assemble_supplements.py work/{id}
        --bundle bundles/{id}
    python engines/walk/tools/check_refs.py work/{id}
        --text bundles/{id}/text.md

    python tools/validate_bundle.py bundles/{id}

Their failure modes are their own; each says what went wrong on stderr
and exits nonzero when it could not do its job.
