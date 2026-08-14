# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

This repo converts paper PDFs into paper bundles (markdown text,
cropped figures, manifest). The conversion is agentic: `playbook/`
holds the prompts, which are the product, and `tools/` holds the thin
scripts they rely on. There is no deterministic pipeline. Start at
`playbook/00-route.md` to convert a paper; `playbook/quality.md` says
what the work must come out as. Start at `docs/calling.md` instead to
have papers converted: one `prepare-paper` agent per paper, and the
playbook stays unread.

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
