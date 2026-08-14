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

    python -m venv .venv
    .venv/bin/pip install -e ".[dev]"
    .venv/bin/python -m pytest

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

To convert a real paper, place it at `work/{id}/source.pdf` and follow
`playbook/00-route.md`. To have papers converted rather than to
convert one yourself, `docs/calling.md` is the whole calling contract,
and reading `playbook/` is neither needed nor wanted. OCR needs
`MISTRAL_API_KEY` in `.env`, and the web witness a contact email in
`ALTEKSTO_CONTACT_EMAIL`; without either, the route continues with one
fewer witness and says so loudly.

## What never enters git

`work/` and `bundles/` are gitignored from the first commit. Paper
PDFs and full texts are copyrighted, so no paper content is ever
committed; only invented papers live in the repository.
