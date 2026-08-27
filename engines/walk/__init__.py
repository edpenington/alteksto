"""The walk engine: an agentic conversion that walks the paper unit by unit.

Six stages, and a seventh that runs only when there is supplementary
material: triage, acquire, skeleton, walk, figures, [supplements], gates.
The text layer, the OCR and the PMC record are independent witnesses, and
the page render settles every dispute between them.

`engines/walk/playbook/00-route.md` is the converter's manual and the
entry point.
"""
