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

Per paper: an id, the PDF, and the DOI when known. The DOI enables the
web witness, and without it the run continues with one fewer witness
and says so.

The id is yours and alteksto never invents one. It comes from whatever
registry already names these papers, a review's export or a
spreadsheet, and it is what every stage after intake trusts: a paper
converted under another paper's id is wrong in a way no later stage can
detect, because nothing downstream re-examines the question.

## Staging

`tools/stage.py` puts a PDF at `work/{id}/source.pdf`, which is where
the converter looks. When you already know which file is which:

    python tools/stage.py --id ID --pdf PATH --work work
    python tools/stage.py --map-file id-to-path.json --work work

When you have a folder of downloads and a registry that names the
papers, it matches them for you, scoring each file's front matter
against the records:

    python tools/stage.py --from DIR --registry FILE [--records KEY] \
        --work work

It stages the confident matches and prints one line per paper on
stdout, `id`, source path, action, which is the list you spawn from.
Exit `0` is everything staged, `3` is some ambiguous and staged
nothing, `1` is a hard failure. An ambiguous match is reported with its
scores and needs a decision from you: restage it by id once you know
which paper it is.

## Spawning

One agent of type `prepare-paper` per staged id, in waves of about
four, because each converter renders pages, calls OCR, and views crops.
The converter works inside this checkout and every path in the playbook
is relative to it, so a caller working in another repository names the
checkout in the prompt and keeps its own paths out:

    Convert paper {id}. Your working directory is {checkout}; every path
    in the playbook is relative to it. The PDF is at
    work/{id}/source.pdf. DOI: {doi, or "unknown"}. Deliver
    bundles/{id}/ and report the path to work/{id}/sweep-report.md.

Then leave them to it. A paper too large for one context is handled by
its own converter splitting the work across subagents of its own and
adjudicating between them, which is a decision inside that paper's run
and not one you make or oversee.

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
