#!/usr/bin/env bash
# Make this checkout usable from sessions working somewhere else.
#
# Working in the checkout needs none of this: the skill and the agent
# types are in the repository, so a session sitting here already has
# them. This script is for the other case, a project that keeps its own
# papers and ids and calls out to alteksto, whose sessions cannot see
# anything that lives here.
#
# It builds the virtual environment, then registers the skill and the
# two agent types under ~/.claude. The registrations are symlinks, so
# pulling this repository updates them; the checkout's location is
# passed separately, as ALTEKSTO_HOME in ~/.claude/settings.json, which
# is what lets the linked files stay free of any path from any one
# machine.
#
# It writes outside this repository, so it is run deliberately and never
# as a side effect of setting the project up. It is safe to run again,
# and overwrites nothing it did not create: an existing file where a
# link belongs stops the install with its name, and a settings file it
# amends is backed up first.
#
#     tools/install.sh [--dry-run] [--links-only]
#
#     --dry-run     print what it would do, change nothing
#     --links-only  skip the venv, for an environment managed elsewhere

set -euo pipefail

DRY_RUN=0
LINKS_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --links-only) LINKS_ONLY=1 ;;
        *) printf 'install: unknown option %s\n' "$arg" >&2; exit 2 ;;
    esac
done

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
# is the [tools] extra that [dev] already pulls in. --links-only skips
# this for an environment somebody else manages.
if [ "$LINKS_ONLY" = 1 ]; then
    say "skipping venv (--links-only)"
elif [ -x "${ROOT}/.venv/bin/python" ]; then
    say "venv present"
    run "${ROOT}/.venv/bin/pip" install --quiet -e "${ROOT}[dev]"
else
    say "building venv"
    run python3 -m venv "${ROOT}/.venv"
    run "${ROOT}/.venv/bin/pip" install --quiet --upgrade pip
    run "${ROOT}/.venv/bin/pip" install --quiet -e "${ROOT}[dev]"
fi

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

# What was linked has to resolve, or the registration is a silent
# nothing: a session finds no skill and no agent types, and reports no
# error, because an absent skill looks exactly like a skill nobody
# wrote. A link into a checkout that has moved, or that is sitting on a
# revision without these files, dies here rather than at the point of
# use.
if [ "$DRY_RUN" = 0 ]; then
    broken=0
    for path in "${CLAUDE_DIR}/skills/alteksto/SKILL.md" \
                "${CLAUDE_DIR}/agents/prepare-paper.md" \
                "${CLAUDE_DIR}/agents/sweep-paper.md"; do
        [ -e "${path}" ] || { say "BROKEN: ${path} resolves to nothing"; \
                              broken=1; }
    done
    if [ "$broken" = 1 ]; then
        say "the registration is incomplete; a session will find no"
        say "alteksto skill and say nothing about it"
        exit 1
    fi
    say "all three registrations resolve"
fi

say "done. In a new session, from any repository, say:"
say '  "use alteksto on the PDFs in <folder>"'
