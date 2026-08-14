# Calling alteksto

This page is for an agent or a session that has papers to convert and
wants bundles back. It is the whole contract. You do not need to read
`playbook/` to call this, and you should not: the playbook is the
converter's manual, written to the agent doing one paper, and reading
it tends to talk a caller into doing the conversion itself.

## The rule

One paper, one converter agent. A caller stages inputs, spawns an
agent of type `prepare-paper` per paper, and reads results off disk.
A caller never converts a paper in its own context, however few the
papers are: the conversion wants a full context per paper for renders
and crops, and a caller that starts one has nothing left for the rest.

## What you supply

Per paper, before spawning anything:

- an id, which names everything downstream and must be unique across
  the papers you are converting;
- the PDF at `work/{id}/source.pdf`, which the converter fails without;
- the DOI, when known, which enables the web witness. Without it the
  run continues with one fewer witness and says so.

The converter's working directory is this checkout, and every path it
uses is relative to it. A caller working in another repository sets
that working directory when it spawns, and keeps its own paths out of
the prompt.

## What you get

`bundles/{id}/`, holding `manifest.json`, `text.md`, and
`figures/*.png`, specified in `docs/bundle.md`. Everything
intermediate stays in `work/{id}/` and never enters the bundle.

The run is done when the bundle passes validation and every finding of
the closing sweep is repaired or explained in
`work/{id}/sweep-report.md`.

## Checking the work

Two reads, neither of which needs the playbook:

    python tools/validate_bundle.py bundles/{id}

and `work/{id}/sweep-report.md`, which lists what fresh eyes found and
what the converter did about each finding. The validator proves the
bundle is well-formed and says nothing about fidelity; the sweep
report is where fidelity is argued. A sweep that found nothing says so
explicitly, so an empty file is a failure to report rather than a
clean run.

## Papers in parallel

Papers are independent as long as their ids differ, because the id
namespaces both the work directory and the bundle. Spawn them
together. Nothing is shared between two papers' runs, and nothing
should be: another paper's text appearing in a draft is the worst
defect this pipeline can produce.

## When a run fails

A converter stops loudly on a missing input, a failed stage check, or
an exhibit count mismatch, and says which. That is a report to act on
rather than something to retry blindly: a second run over the same
broken input fails the same way. Every stage is re-entrant, so once
the cause is fixed a fresh converter on the same id resumes from the
work already on disk instead of starting over.
