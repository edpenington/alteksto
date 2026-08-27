"""Helpers any test may use, whichever side of the contract it tests."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(rel_path: str):
    """Load a repository script as a module, scripts staying scripts.

    The path is relative to the repository root and its directories go
    into the module name, so two engines' tools that share a filename
    never collide in sys.modules.
    """
    path = REPO_ROOT / rel_path
    name = rel_path.removesuffix(".py").replace("/", ".")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
