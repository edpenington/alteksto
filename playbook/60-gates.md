# Stage 6: gates

Two gates, in order. The first is mechanical, the second is fresh eyes.
The skeleton already guards omission; the sweep guards invention and
distortion.

## Gate 1: validate-bundle

Run the repo's own validator (it enforces `docs/bundle.md`, the format
this repo owns) over the finished bundle:

    python tools/validate_bundle.py bundles/{id}

Fix what it names and run it again, in a loop, until it passes clean.
Typical failures and their fixes: a declared label without its PNG or a
PNG without its declaration (the figure stage miscounted; go back to
it); an unknown manifest key (only the contract's keys exist); a
missing required key (id, title, exhibits, schema_version).

Validation says nothing about text fidelity or crop quality. Passing
gate 1 means the bundle is well-formed, nothing more.

## The reference canary

Between the gates, run the deterministic canary:

    python tools/check_refs.py work/{id} --text bundles/{id}/text.md

It resolves every DOI in the references through the registrar and lays
the returned record (title, authors, year, pages) beside the entry as
converted. This measures the conversion of the whole text, not the
references for their own sake: references are the densest,
highest-entropy strings in a paper, so they are where conversion errors
concentrate and where a clean bill means the most. The deterministic
part stops at resolution and juxtaposition; whether each record reads
like its entry is the sweep's judgement, single digits included. An
unresolved DOI or a record that reads wrong is a flag for
adjudication, not a verdict; the paper may misprint its own
references, and the render decides as always. Papers whose references carry no DOIs get a canary that says
nothing, loudly.

The report lands in `work/{id}/refs-report.md` and is handed to the
sweep.

## Gate 2: the fresh-context sweep

A new agent with no conversation history (the sweep-paper agent) gets
the checkout you are working in, named in its prompt exactly as yours
named it, the paper's id, and:

- the bundle's text.md,
- the page renders,
- the text-layer dump blocks.json with its emphasis runs,
- the skeleton,
- triage.json (so it knows which witness was the character source),
- refs-report.md (the canary's findings, each to be adjudicated
  against the render).

It reads the bundle afresh in the standing shape: text first
against the layer and its emphasis runs, every crop viewed, renders
sampled (the front-matter page and the reference pages by default,
plus any targeted questions in its brief), escalating to further
renders only where text cannot settle a suspicion, with independent
reads batched into parallel tool calls. It reports discrepancies to
`work/{id}/sweep-report.md`. It finds; it does not fix. Its brief:

- **Omission**: skeleton units, exhibits, footnotes, or reference
  entries not honoured in the final text; paragraphs visibly on the
  page and absent from the draft.
- **Invention**: text in the draft that no render shows; headings the
  paper does not print; "helpful" additions.
- **Distortion**: numbers, names, and high-entropy strings that differ
  from the page; sentences whose meaning drifted in reconciliation;
  seams that dropped or doubled words.
- **Source oddities**: before flagging an apparent typo as a
  conversion error, check the render. What the page prints is correct
  by definition; note it as `source` rather than `defect` so nobody
  "fixes" it later.

The driver reads the report, repairs confirmed defects in the bundle
(through the walk's machinery for text, the figure loop for crops),
reruns gate 1 if anything changed, and records what was repaired and
what was judged `source` at the bottom of the sweep report. A sweep
that finds nothing is recorded too; silence is not evidence of a pass.

The run ends here. The bundle is done when gate 1 passes clean and
every sweep finding is either repaired or explained.
