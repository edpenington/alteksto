# alteksto

One paper PDF becomes one paper bundle: markdown full text, cropped
figures and tables, and a manifest, faithful to the page down to the
characters. The bundle format is specified in `docs/bundle.md`,
enforced by `tools/validate_bundle.py`, and consumed downstream by
*meltiro* (github.com/edpenington/meltiro).

The conversion is agentic, and the playbook is the product: `playbook/`
holds the prompts that teach an agent what a good extraction looks
like and the best route to one, and `tools/` holds the thin scripts
the prompts rely on. There is no deterministic pipeline. The agent
drives, the scripts serve, and the result is held to the page by two
gates.

## If you were asked to use alteksto

You are reading this because someone said "use alteksto on these
papers". Three things, in this order, and then stop reading:

1. **Install it**, once per machine. Clone this repository and run
   `tools/install.sh`. That builds the venv and registers the `alteksto`
   skill and the `prepare-paper` and `sweep-paper` agent types under
   `~/.claude`, so that a session working in any other repository can
   spawn a converter. After it, the skill carries the rest of this and
   you need no part of the repository in your head.

2. **One agent per paper.** Spawn a `prepare-paper` agent per paper and
   let it work. Converting one paper fills a context, so doing it
   yourself costs you the context you need to run the others, and doing
   it for several papers in a row is the mistake this paragraph exists
   to prevent. `docs/calling.md` is the whole contract for handing
   papers over: what you supply, what comes back, how to check it.

3. **A paper too large for one context is its own converter's problem.**
   It splits the work across subagents of its own and adjudicates
   between them. That decision happens inside one paper's run and never
   at your level.

The id a paper is converted under always comes from the caller, from
whatever registry already names these papers. alteksto never invents
one: `tools/stage.py` matches a downloaded PDF to a record you supply,
and says so loudly rather than guessing when it cannot.

## The route

    triage -> acquire -> skeleton -> walk -> figures -> gates

- **Triage** classifies the PDF before trusting anything: born digital
  with a healthy text layer, or scanned.
- **Acquire** collects the witnesses: the raw text layer (the
  character authority), OCR markdown (the structure authority),
  150 DPI page renders (the ground truth that settles every dispute),
  and a web full text when one exists.
- **Skeleton** inventories every section, exhibit, and footnote from
  the renders before any prose is written. This is the coverage
  contract the rest of the run is checked against.
- **Walk** assembles the text unit by unit against the skeleton,
  reconciling the witnesses under explicit precedence: line-break
  hyphens healed, page furniture stripped, emphasis carried from the
  layer's font flags, and the source's own defects preserved, because
  correcting a paper is fabrication.
- **Figures** crops every exhibit from the renders, inspects each
  crop, and carries printed exhibit footnotes into the manifest.
- **Gates** hold the result: `validate_bundle.py` proves the shape,
  a deterministic reference canary resolves any printed DOIs, and a
  fresh-context sweep reads the paper against the renders and reports
  what the conversion missed, invented, or distorted.

Each paper gets a converter agent of its own, which does that paper in
a single context, and a second agent sweeps it with fresh eyes; a
delegated fallback exists for a paper too large for one context. Many
papers means many converters, one each, rather than one agent working
through a list. The full route, the witness precedence, and the
catalogue of defects real conversions produce live in `playbook/`,
starting at `playbook/00-route.md`.

## Quickstart

    tools/install.sh
    .venv/bin/python -m pytest

`install.sh` builds the venv, installs the package, registers the skill
and the two agent types under `~/.claude`, and records this checkout's
path as `ALTEKSTO_HOME` in `~/.claude/settings.json`. It overwrites
nothing it did not create, `--dry-run` shows what it would do, and
running it again is how a moved checkout is re-registered. Working on
the repository itself needs none of that, only the venv:

    python -m venv .venv
    .venv/bin/pip install -e ".[dev]"

Producing a bundle needs the page stack, `alteksto[tools]`, which the
`[dev]` extra above already pulls in. Consuming one needs nothing:
`alteksto.bundle` enforces the whole format on the standard library
alone, so a downstream package depends on the plain name and carries no
PDF library it never opens.

The tests are fully offline: every PDF they read is invented and built
at test time, and OCR and web lookups are faked. The worked example in
`examples/` is a complete invented mini-paper with its expected
skeleton, bundle, and crop regions committed beside it, and
`examples/README.md` walks the route over it stage by stage.

To convert a real paper, place it at `work/{id}/source.pdf` with
`tools/stage.py` and follow `playbook/00-route.md`. To have papers
converted rather than to convert one yourself, `docs/calling.md` is the
whole calling contract, and reading `playbook/` is neither needed nor
wanted. OCR needs
`MISTRAL_API_KEY` in `.env`, and the web witness a contact email in
`ALTEKSTO_CONTACT_EMAIL`; without either, the route continues with one
fewer witness and says so loudly.

## What never enters git

`work/` and `bundles/` are gitignored from the first commit. Paper
PDFs and full texts are copyrighted, so no paper content is ever
committed; only invented papers live in the repository.
