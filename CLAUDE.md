# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

This repo converts paper PDFs into paper bundles (markdown text,
cropped figures, manifest). Two things live here and the boundary
between them is the point:

- **the format**, in `src/alteksto`, which is `bundle.py` and nothing
  else. Standard library only. `docs/bundle.md` specifies it and
  `tools/validate_bundle.py` is its one CLI. Deterministic.
- **the engines**, one directory each under `engines/`, which produce
  bundles. Agentic: an engine's playbook holds the prompts, which are
  the product, and its tools are the thin scripts they rely on. There is
  no deterministic pipeline.

An engine owns its playbook, tools, lib and agents, and shares nothing
with the other engines but the format. That is deliberate: shared
producer code would quietly make the next engine resemble the last, and
the reason to keep several is to compare processes that differ. The
dependency runs one way, engine to format, never back.

The engine shipped here is `engines/walk/`. Start at
`engines/walk/playbook/00-route.md` to convert a paper;
`engines/walk/playbook/quality.md` says what the work must come out as.
Start at `docs/calling.md` instead to have papers converted: one
`prepare-paper-walk` agent per paper, and the playbook stays unread.

## Working rules

- Python venv at `.venv/`; run everything through it.
- Tests must not need the network; OCR and PMC calls are mocked or faked.
- Strict inputs, loud failures: a missing id or an unreadable PDF fails; a
  failed PMC lookup warns loudly and continues with one fewer witness. No
  failure is ever silent.
- Work on branches; changes are reviewed via PRs before merge.
- Every commit published here is signed. If signing fails, stop and ask
  for 1Password to be unlocked; never commit unsigned to get past it.
- `work/` and `bundles/` are gitignored; no paper PDFs or full texts are
  ever committed (copyright).
- Playbook, README, and tool language stays generic: any paper PDF, never a
  particular review, corpus, or study.
- A new engine is a new directory under `engines/`, with its own
  playbook, tools, lib, agents and extra in pyproject, its own tests
  under `tests/engines/{name}/`, and its agents named for it. It copies
  what it needs from another engine rather than importing it. Only its
  own code and its own tests import from it. Elsewhere its name appears
  just where something has to name a default: `pyproject.toml`,
  `tools/install.sh`, the skill, and the docs telling a caller which
  converter to spawn.
- `src/alteksto` holds the format and nothing else. Anything a producer
  needs belongs to an engine. A test reads this off the files, and CI
  proves it against a wheel installed with no page stack present.
- The bundle format is owned here: `docs/bundle.md` is the
  specification, `tools/validate_bundle.py` enforces it, and *meltiro*
  (github.com/edpenington/meltiro) consumes it. The emitted bundle must
  pass validate-bundle. Intermediates stay in `work/`, never in the
  bundle.

## Writing style

- Plain declarative prose everywhere: README, docstrings, comments,
  commits, issues. No em-dashes; use commas, colons, parentheses, or
  separate sentences.
- Italicise or code-format lowercase project names (*alteksto*, *meltiro*).
