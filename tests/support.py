"""Helpers any test may use, whichever side of the contract it tests."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The worked example is shared: comparing two engines means giving them
# one input and holding the results against one target. What an engine
# expects on the way there lives with that engine.
EXAMPLES = REPO_ROOT / "examples"


def load_script(rel_path: str):
    """Load a repository script as a module, scripts staying scripts.

    The path is relative to the repository root and its directories go
    into the module name, so two engines' tools that share a filename are
    told apart in a traceback. Nothing is registered in sys.modules: each
    call returns a fresh module, as loading a script twice should.
    """
    path = REPO_ROOT / rel_path
    name = rel_path.removesuffix(".py").replace("/", ".")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        # spec_from_file_location answers None for anything Python does not
        # recognise as a module, and module_from_spec then dies on it with
        # nothing in the message about the path that caused it.
        raise ValueError(f"not a loadable Python module: {rel_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
