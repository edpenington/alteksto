# The engines

One directory per engine, each a whole way of turning a paper PDF into a
paper bundle. They differ in how they work, and they are compared by what
they emit: the bundle passes `tools/validate_bundle.py`, or it does not.

    walk/   An agentic conversion that walks the paper unit by unit
            against the page renders, with the text layer, the OCR and
            the PMC record as witnesses and the render settling every
            dispute. Converter: `prepare-paper-walk`. The engine this
            repository shipped with, and the right default when there is
            no reason to want another.

An engine owns its playbook, its tools, its helpers, its agents and its
example expectations, and shares nothing with the others but the format
contract in `src/alteksto`. That is deliberate. A substrate shared
between engines is what would quietly make the next one resemble the
last, and the reason to keep several is to compare processes that
genuinely differ. An engine may read the format and never change it.

Staging is the engine's own, because what an engine wants on disk before
it starts is part of how it works. A caller reads the engine's README for
its staging tool and its converter, and `docs/calling.md` for everything
after that, which is the same for all of them.

What adding an engine involves is in CLAUDE.md.
