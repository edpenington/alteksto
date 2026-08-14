---
name: prepare-paper
description: Convert one paper PDF in work/{id}/ into a validated paper bundle in bundles/{id}/, following the playbook. One paper per run.
---

You convert one paper PDF into one paper bundle. The playbook is the
instruction set; this file only wires it together.

Read, in order, before acting: `playbook/00-route.md`,
`playbook/quality.md`, then each stage file as you reach its stage
(10-triage, 20-sources, 30-skeleton, 40-walk, 50-figures, 60-gates).

Inputs: the paper's id (the work directory name). `work/{id}/source.pdf`
must exist; fail loudly if it does not. The DOI, if known, enables the
web witness.

Standing rules, from the playbook, that bear repeating because they are
easy to drift from mid-run:

- Every stage is re-entrant: validate existing outputs rather than
  redoing them.
- The conversion runs in your one context by default: you read
  the renders yourself, walk every unit, view your own crops, and
  batch independent reads into parallel tool calls in the same turn.
  Delegate only when the paper outgrows one context, and then never
  read a page image yourself: subagents hold the pixels and you
  adjudicate through them.
- The render decides every witness dispute, read by whoever holds the
  pixels.
- Preserve the source, defects included.
- A missing witness is one fewer witness, said loudly, never a stop.
  A missing input, a failed stage check, or an exhibit count mismatch
  is a stop, said loudly.
- Subagents deliver through files: name the exact output path under
  `work/{id}/` in every subagent's prompt and read that file. Never
  block waiting on a message from a subagent.
- Everything a subagent drafts lives under this paper's `work/{id}/`,
  never in a shared scratch location: concurrent runs overwrite each
  other there, and another paper's text in a draft is the worst defect
  this pipeline can produce.
- Tools that finish in seconds (the validator, the canary) run in the
  foreground; a background wait with no wake-up strands the run.

The run is done when gate 1 passes clean and every sweep finding is
repaired or explained in the sweep report.
