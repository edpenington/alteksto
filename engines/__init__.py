"""The engines: each one a whole way of turning a paper PDF into a bundle.

An engine owns its playbook, its tools, its helpers and its agents, and
shares nothing with the others but the format contract in `src/alteksto`.
That is deliberate. A substrate shared between engines is the thing that
would quietly make the second engine look like the first, and the reason
to keep several is to compare processes that genuinely differ.

What every engine owes is the same and is the only thing checked across
them: the bundle it emits passes `tools/validate_bundle.py`.
"""
