# alteksto

One paper PDF becomes one paper bundle: markdown full text, cropped
figures and tables, the tables also as text, and a manifest, faithful
to the page down to the characters. The bundle format is specified in
`docs/bundle.md`, enforced by `tools/validate_bundle.py`, and consumed
downstream by *meltiro* (github.com/edpenington/meltiro). What a good
bundle is, as distinct from a valid one, is in `docs/quality.md`: the
target every engine writes to, which the validator does not check.

The conversion is agentic, and the playbook is the product: an engine
holds the prompts that teach an agent what a good extraction looks like
and the best route to one, and the thin scripts those prompts rely on.
There is no deterministic pipeline. The agent drives, the scripts serve,
and the result is held to the page by two gates.

The format and the engines are separate on purpose. `src/alteksto` is
the format and nothing else: it imports the standard library, and a
consumer that reads and checks bundles installs that alone. Everything
that produces a bundle lives under `engines/`, one directory per engine,
each owning its playbook, its tools, its helpers and its agents, and
sharing nothing with the others but the contract and the target. The
engine shipped here is `engines/walk/`; the point of the arrangement
is that a second one can differ from it completely and still be held
to one target, `docs/quality.md`, and one check,
`tools/validate_bundle.py`.

## If you were asked to use alteksto

You are reading this because someone said "use alteksto on these
papers". Three things, in this order, and then stop reading:

1. **Clone it and build the venv** (see Quickstart, two commands), then
   work with the clone as your working directory. That is the whole
   setup: the `alteksto` skill and each engine's agent types are in this
   repository, so a session sitting in the clone already has them, and
   the skill carries the rest of this. Nothing is installed anywhere
   else, and `git pull` is the only update.

   Working in another repository and calling out to this one is the
   other case, and it is the one that needs `tools/install.sh`. See
   "Using alteksto from another project" below.

2. **One agent per paper.** Spawn one converter per paper, of the
   engine you are using: `prepare-paper-walk` for the engine shipped
   here. Then let it work. Converting one paper fills a context, so a
   caller who converts has spent the context the other papers needed.
   `docs/calling.md` is the whole contract for handing papers over:
   what you supply, what comes back, how to check it.

3. **A paper too large for one context is its own converter's problem.**
   It splits the work across subagents of its own and adjudicates
   between them. That decision happens inside one paper's run and never
   at your level.

The id a paper is converted under always comes from the caller, from
whatever registry already names these papers. alteksto never invents
one: `engines/walk/tools/stage.py` matches a downloaded PDF to a record
you supply, and says so loudly rather than guessing when it cannot.

## The walk engine's route

One engine's answer, not the only possible one.

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
  crop, and carries printed exhibit footnotes into the manifest. A
  table also gets its content as text, checked by rendering the
  transcription back to an image and holding it beside the crop, so a
  consumer can quote a cell instead of sending a model to read the
  rows off pixels.
- **Supplements**, when any were staged, are converted the same way
  and kept as their own thing: a supplement's prose never joins the
  article's text and its exhibits never join the article's manifest,
  so identifying a paper by those bytes survives a supplement being
  added later.
- **Gates** hold the result: `validate_bundle.py` proves the shape,
  a deterministic reference canary resolves any printed DOIs, and a
  fresh-context sweep reads the paper against the renders and reports
  what the conversion missed, invented, or distorted.

The full route, the witness precedence, and the catalogue of defects
real conversions produce live in `engines/walk/playbook/`, starting at
`engines/walk/playbook/00-route.md`. `engines/walk/README.md` describes
the engine as a whole.

## Quickstart

    python -m venv .venv
    .venv/bin/pip install -e ".[dev]"
    .venv/bin/python -m pytest

Producing a bundle needs an engine's page stack, `alteksto[walk]` for
the engine shipped here, which the `[dev]` extra above already pulls in
for every engine. Consuming one needs nothing: `alteksto.bundle`
enforces the whole format on the standard library alone, so a downstream
package depends on the plain name and carries no PDF library it never
opens.

The tests are fully offline: every PDF they read is invented and built
at test time, and OCR and web lookups are faked. The worked example in
`examples/` is a complete invented mini-paper with the bundle it should
produce committed beside it, shared by every engine so that comparing
two means comparing them on one paper. What a particular engine expects
on the way there is its own, under `engines/{engine}/example/`.

A real paper reaches `work/{id}/source.pdf` through
`engines/walk/tools/stage.py`, under an id its caller already has, and
`engines/walk/playbook/00-route.md` takes it from there. OCR needs
`MISTRAL_API_KEY` in `.env`, and the web witness a contact email in
`ALTEKSTO_CONTACT_EMAIL`; without either, the route continues with one
fewer witness and says so loudly.

## Using alteksto from another project

Working in this clone needs no installation. A project that keeps its
own papers, ids, and results, and calls out to alteksto without its
people ever opening this repository, does: its sessions cannot see a
skill or an agent type that lives here, so one command registers them
for the machine.

    tools/install.sh

It links the `alteksto` skill and every engine's agent types into
`~/.claude`, and records this clone's path as `ALTEKSTO_HOME` in
`~/.claude/settings.json`. Those are links rather than copies, so `git
pull` updates them; rerun the script after a pull that changes
dependencies, or after moving the clone.

It writes outside this repository, so it is deliberate rather than part
of the setup. It backs up any settings file it amends, keeps the keys
already there, overwrites nothing it did not create, and `--dry-run`
prints what it would do without doing it. `tools/install.sh
--uninstall` takes it all back, and takes back only what this checkout
registered: a link into a different checkout, a file somebody else
wrote, and an `ALTEKSTO_HOME` naming somewhere else are each named and
left alone.

What that project supplies is described in `docs/calling.md`: where its
PDFs are staged, which registry names them, and where finished bundles
are collected. alteksto never invents an id.

## What never enters git

`work/` and `bundles/` are gitignored from the first commit. Paper
PDFs and full texts are copyrighted, so no paper content is ever
committed; only invented papers live in the repository.
