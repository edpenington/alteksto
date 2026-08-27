"""Reading configuration that must not live in the repository.

Secrets and contact details arrive as environment variables. For
convenience a .env file (gitignored, at the repository root) supplies any
variable the environment does not; the environment always wins. The file
is never required: a variable set in neither place is simply absent, and
the tool that needs it says so loudly and stops.
"""

from __future__ import annotations

import os
from pathlib import Path


def read_var(name: str, env_file: Path) -> str | None:
    """os.environ[name], else the value in env_file, else None."""
    value = os.environ.get(name)
    if value:
        return value
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if sep and key.strip() == name:
            val = val.strip().strip('"').strip("'")
            return val or None
    return None
