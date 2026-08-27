---
name: alteksto
description: Convert paper PDFs into paper bundles (markdown full text, cropped figures, manifest) by spawning one converter agent per paper. Use whenever the request is to run or use alteksto on a PDF, on several PDFs, on a staging folder, or on a review's included papers, and when asked to install alteksto.
---

# Running alteksto

You are the caller, not the converter. Your job is to get each paper its
own agent and to report what came back. You do not read page renders,
you do not walk the text, and you do not open an engine's playbook,
which is the converter's manual and turns whoever reads it into a
converter.

Converting one paper fills a context. Spend yours on a paper and the
rest of the papers have no orchestrator left.

## 0. Pick the engine

alteksto keeps more than one way of converting a paper, one directory
per engine under `engines/`, listed in `engines/README.md`. They differ
in how they work and are compared by what they emit. Unless the user
named one, use walk, the engine this repository shipped with: its
converter is `prepare-paper-walk` and its tools are under
`engines/walk/tools/`.

Steps 1, 3 and 4 below are written for walk. Finding the checkout,
staging, and the converter's name all belong to the engine, so for any
other engine read `engines/{name}/README.md` and use what it names in
those three steps. Step 5 is the same whichever you called, because
checking the work is the format's side and not an engine's.

Say which engine you used when you report, because a bundle is only
comparable against another if both are named.

## 1. Find the checkout

The conversion runs inside the alteksto checkout, in three likely
states:

- **You are already in it**, if the working directory holds
  `engines/walk/playbook/00-route.md`. Nothing to find.
- **`ALTEKSTO_HOME` is set**, which is what `tools/install.sh` records.
  Use it.
- **Neither**, so it is not on this machine. Clone
  `https://github.com/edpenington/alteksto` somewhere the user agrees
  to, build the venv (`python -m venv .venv`, then
  `.venv/bin/pip install -e ".[dev]"`), and say where you put it. Only
  run `tools/install.sh` if this project will keep calling out to
  alteksto, because it writes to `~/.claude`; ask first.

Everything below runs with the checkout as the working directory and
`.venv/bin/python` as the interpreter. A checkout with no `.venv` has
not been set up: build it before staging anything.

## 2. Collect the four project facts

alteksto knows how to convert a paper. It cannot know these, so get them
from the project you are called in (its CLAUDE.md, its docs, or the
user) before staging anything:

- **the PDFs**: a staging directory, or specific files;
- **the id system**: the registry that already names these papers, and
  where it lives. Ids belong to the project. Never invent one, and never
  derive one from a filename;
- **where bundles are collected** afterwards, if not the checkout;
- **the DOI source**, usually the registry, which enables the web
  witness.

If the project has an id registry but you cannot find it, ask. Staging a
paper under a guessed id produces a bundle that is wrong in a way no
later stage can detect, because every stage after intake trusts the id.

## 3. Stage

With a registry, let the tool match files to records:

    .venv/bin/python engines/walk/tools/stage.py --from <staging dir> \
        --registry <registry.json> [--records <key>] --work work

With ids already in hand, say so directly:

    .venv/bin/python engines/walk/tools/stage.py --id <id> \
        --pdf <path> --work work
    .venv/bin/python engines/walk/tools/stage.py \
        --map-file <id-to-path.json> --work work

Read the exit code. `0` means every PDF is staged. `3` means some were
ambiguous and staged nothing: those are listed on stderr with their
scores, and they need a human decision, so report them and carry on with
the rest rather than guessing. `1` is a hard failure, named on stderr.

Stdout is one line per staged paper, `id`, source path, action. That
list is what you spawn from.

## 4. Spawn one converter per paper

One converter per staged id, of the engine you picked in step 0, in
waves of about four, because each converter renders pages, calls OCR,
and views crops. Give each one exactly this, filled in:

    Convert paper {id}. Your working directory is {checkout}; every path
    in the playbook is relative to it. The PDF is at
    work/{id}/source.pdf. DOI: {doi, or "unknown"}. Deliver
    bundles/{id}/ and report the path to work/{id}/sweep-report.md.

Then leave them alone. A paper too large for one context is handled by
its own converter splitting the work across subagents of its own; that
is its decision to make inside its run, and no concern of yours. One
paper failing is one paper failing: the others continue.

## 5. Collect and report

Per paper, two reads, neither of which needs the playbook:

    .venv/bin/python tools/validate_bundle.py bundles/{id}

and `work/{id}/sweep-report.md`, which lists what fresh eyes found and
what the converter did about each finding. Report a table: id,
validator result, sweep findings, anything the converter stopped on.
Then move the bundles to wherever the project collects them.

A sweep that found nothing says so explicitly, so an empty report file
is a converter that failed to report rather than a clean run. Say that
plainly rather than counting it as a pass.
