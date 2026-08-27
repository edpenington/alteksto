# The walk engine

One way of turning a paper PDF into a paper bundle, and the first one
this repository had. An agent converts the paper by walking it unit by
unit against the page renders, holding several witnesses side by side
and letting the render settle every dispute between them.

    triage -> acquire -> skeleton -> walk -> figures -> [supplements] -> gates

The playbook is the product. `engines/walk/playbook/00-route.md` is the
converter's manual and the entry point, and
`engines/walk/playbook/quality.md` says what a good bundle looks like
and catalogues the defects real conversions produce. The scripts in
`tools/` are thin and serve the agent, which drives.

## What is here

    playbook/     the prompts: the route, one file per stage, and quality.md
    tools/        the thin scripts the prompts call
    lib/          what those scripts share: the work directory and its page
                  markers, and reading a key from the environment
    agents/       the converter and the sweep, each named for this engine:
                  prepare-paper-walk and sweep-paper-walk
    example/      the intermediates this engine should arrive at on the
                  worked example in examples/

## What it depends on

The format contract, `alteksto.bundle`, and nothing from any other
engine. That is the rule for every engine here: the bundle it emits
passes `tools/validate_bundle.py`, and how it got there is its own
business. The dependency runs one way, so an engine may read the format
but never change it.

Its page stack is `alteksto[walk]`: pymupdf to open a PDF and read a
page, lxml to parse the JATS the web witness returns.

## Running it

One agent of type `prepare-paper-walk` per paper. `docs/calling.md` is
the calling contract, and the `alteksto` skill carries it for a session
that arrives with papers rather than with a paper. A caller never reads
this playbook: reading it turns the reader into a converter, and a
converter has spent the context the other papers needed.

The toolbelt is listed in `engines/walk/playbook/00-route.md`. Every
path there is relative to the checkout root, never to this directory,
and is typed as written.

## The witnesses

What makes this engine what it is, and where a different engine would
most obviously diverge:

- **the text layer** (`blocks.json`, `blocks.txt`), authoritative for
  characters and never for their order;
- **the OCR** (`ocr/page_NN.md`), authoritative for structure, reading
  order, headings and tables, its characters plausible but fallible,
  its image boxes seeding the figure crops;
- **the page renders** (`pages/page_NN.png`), the ground truth, read by
  whoever holds the pixels, and never bulk-transcribed;
- **the web full text** (`web.md`) when PMC has one, an independent
  prose witness that may legitimately differ from the PDF.

A missing witness is one fewer witness, said loudly. A missing input is
a stop.
