#!/usr/bin/env bash
# Make this checkout usable from any session on this machine.
#
# Builds the virtual environment, then registers the skill and the two
# agent types under ~/.claude so that a session working in another
# repository can spawn a converter without knowing anything about this
# one. The registrations are symlinks, so pulling this repository
# updates them; the checkout's location is passed separately, as
# ALTEKSTO_HOME in ~/.claude/settings.json, which is what lets the
# linked files stay free of any path from this machine.
#
# Safe to run again. It overwrites nothing it did not create: an
# existing file where a link belongs stops the install with its name.
#
#     tools/install.sh [--dry-run]

set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_DIR="${HOME}/.claude"
SETTINGS="${CLAUDE_DIR}/settings.json"

say() { printf 'install: %s\n' "$1"; }
run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf 'install: would run: %s\n' "$*"
    else
        "$@"
    fi
}

say "checkout at ${ROOT}"

# The virtual environment. Producing a bundle needs the page stack, which
# is the [tools] extra that [dev] already pulls in.
if [ -x "${ROOT}/.venv/bin/python" ]; then
    say "venv present"
else
    say "building venv"
    run python3 -m venv "${ROOT}/.venv"
    run "${ROOT}/.venv/bin/pip" install --quiet --upgrade pip
fi
run "${ROOT}/.venv/bin/pip" install --quiet -e "${ROOT}[dev]"

# The registrations. A symlink pointing where we want it is already done;
# anything else in the way is the operator's file and is never removed.
link() {
    local target="$1" link_path="$2"
    if [ -L "${link_path}" ]; then
        if [ "$(readlink "${link_path}")" = "${target}" ]; then
            say "linked already: ${link_path}"
            return 0
        fi
        say "replacing stale link: ${link_path}"
        run rm "${link_path}"
    elif [ -e "${link_path}" ]; then
        say "REFUSING: ${link_path} exists and is not a link from here"
        say "move it aside and run this again"
        return 1
    fi
    run ln -s "${target}" "${link_path}"
    [ "$DRY_RUN" = 1 ] || say "linked ${link_path}"
}

run mkdir -p "${CLAUDE_DIR}/skills" "${CLAUDE_DIR}/agents"
link "${ROOT}/.claude/skills/alteksto" "${CLAUDE_DIR}/skills/alteksto"
link "${ROOT}/.claude/agents/prepare-paper.md" \
     "${CLAUDE_DIR}/agents/prepare-paper.md"
link "${ROOT}/.claude/agents/sweep-paper.md" \
     "${CLAUDE_DIR}/agents/sweep-paper.md"

# ALTEKSTO_HOME, merged into whatever settings.json already holds. The
# file is the operator's, so it is read, amended in memory, backed up,
# and written whole; a settings file that is not JSON stops the install
# rather than being replaced by one that is.
say "setting ALTEKSTO_HOME in ${SETTINGS}"
if [ "$DRY_RUN" = 1 ]; then
    say "would set ALTEKSTO_HOME=${ROOT}"
else
    python3 - "$SETTINGS" "$ROOT" <<'PY'
import json, shutil, sys
from pathlib import Path

settings_path, root = Path(sys.argv[1]), sys.argv[2]
settings = {}
if settings_path.is_file():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"install: {settings_path} is not valid JSON ({exc}); "
                 f"fix it or set ALTEKSTO_HOME by hand")
    shutil.copy2(settings_path, settings_path.with_suffix(".json.bak"))
env = settings.setdefault("env", {})
if env.get("ALTEKSTO_HOME") == root:
    print(f"install: ALTEKSTO_HOME already {root}")
else:
    env["ALTEKSTO_HOME"] = root
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n",
                             encoding="utf-8")
    print(f"install: ALTEKSTO_HOME={root}")
PY
fi

say "done. In a new session, from any repository, say:"
say '  "use alteksto on the PDFs in <folder>"'
