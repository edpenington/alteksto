# The route

One paper PDF becomes one paper bundle: markdown full text, cropped
figures and tables, a manifest, passing validate-bundle against the
format this repo owns (docs/bundle.md). The conversion runs in six
stages:

    triage -> acquire -> skeleton -> walk -> figures -> gates

Each stage has its own file in this directory. `quality.md` describes
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
      refs-report.md       the reference canary's verdicts
      sweep-report.md      the fresh-context sweep's findings

The bundle lands in `bundles/{id}/` as `manifest.json`, `text.md`, and
`figures/*.png`, exactly per the contract (see quality.md).

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
- **One context converts; the sweep is the fresh eyes.** The
  conversion runs in a single context by default: the converter reads
  its own renders, walks every unit, views its own crops, and batches
  independent reads into parallel tool calls in the same turn. Fresh
  eyes are the sweep's job, once, at the end, and cheap determinism
  (the emphasis runs, the validator, the canary) guards the middle.
  Delegation is the fallback for a paper too large for one context;
  when delegating, the driver never reads a page image, works in text
  only, and subagents deliver their reports as files in the work
  directory (the driver reads files, never waits on messages).
- **Preserve the source, defects included.** Papers contain typos,
  garbled references, and mismatched statistics. The bundle transcribes
  what the paper prints. Correcting the source, however tempting, is
  fabrication.
- **Nothing copyrighted leaves the work tree.** Work directories and
  bundles are gitignored; paper text never enters a commit.

## The toolbelt

Each tool does one thing to one work directory and exits. Run them
through the project venv.

    python tools/render_pages.py work/{id} [--dpi 150]
    python tools/dump_blocks.py work/{id}
    python tools/ocr.py work/{id} [--transport fake]
    python tools/fetch_pmc.py work/{id} --doi DOI
    python tools/crop.py work/{id}/pages/page_NN.png --box X0 Y0 X1 Y1
        [--box ...] [--space W H] --out bundles/{id}/figures/{label}.png
    python tools/validate_bundle.py bundles/{id}
    python tools/check_refs.py work/{id} --text bundles/{id}/text.md

Their failure modes are their own; each says what went wrong on stderr
and exits nonzero when it could not do its job.
