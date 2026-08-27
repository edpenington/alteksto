#!/usr/bin/env bash
# Make this checkout usable from sessions working somewhere else.
#
# Working in the checkout needs none of this: the skill and the agent
# types are in the repository, so a session sitting here already has
# them. This script is for the other case, a project that keeps its own
# papers and ids and calls out to alteksto, whose sessions cannot see
# anything that lives here.
#
# It builds the virtual environment, then registers the skill and each
# engine's agent types under ~/.claude. The registrations are symlinks,
# so pulling this repository updates them; the checkout's location is
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
#     --uninstall   remove what this checkout registered, and nothing else

set -euo pipefail

DRY_RUN=0
LINKS_ONLY=0
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --links-only) LINKS_ONLY=1 ;;
        --uninstall) UNINSTALL=1 ;;
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

# An engine's agents carry its name, because asking for a conversion
# means asking a particular engine for one. A second engine adds its own
# pair here; nothing else in this script knows how many there are.
LINK_PATHS=("${CLAUDE_DIR}/skills/alteksto"
            "${CLAUDE_DIR}/agents/prepare-paper-walk.md"
            "${CLAUDE_DIR}/agents/sweep-paper-walk.md")
LINK_TARGETS=("${ROOT}/.claude/skills/alteksto"
              "${ROOT}/engines/walk/agents/prepare-paper.md"
              "${ROOT}/engines/walk/agents/sweep-paper.md")

# Names this checkout registered before an engine's agents carried its
# name. The rename left them pointing at files that have moved into the
# engine, so an install predating it leaves two dead links behind that
# nothing else here would mention: they are not in LINK_PATHS, so the
# removal below does not take them back and the health check does not
# read them. Only a link into this checkout is ours to drop; one naming
# somewhere else belongs to that install.
LEGACY_PATHS=("${CLAUDE_DIR}/agents/prepare-paper.md"
              "${CLAUDE_DIR}/agents/sweep-paper.md")

drop_legacy() {
    local path target
    for path in "${LEGACY_PATHS[@]}"; do
        [ -L "${path}" ] || continue
        target="$(readlink "${path}")"
        case "${target}" in
            "${ROOT}"/*)
                run rm "${path}"
                [ "$DRY_RUN" = 1 ] || say "removed stale name: ${path}"
                ;;
            *) say "left alone (points elsewhere): ${path}" ;;
        esac
    done
}

# Removal takes back exactly what this checkout registered. A link
# pointing at some other checkout belongs to that one, a real file
# belongs to whoever wrote it, and an ALTEKSTO_HOME naming somewhere
# else is somebody else's install: each is named and left alone.
if [ "$UNINSTALL" = 1 ]; then
    removed=0
    for index in "${!LINK_PATHS[@]}"; do
        path="${LINK_PATHS[$index]}"
        target="${LINK_TARGETS[$index]}"
        if [ -L "${path}" ]; then
            if [ "$(readlink "${path}")" = "${target}" ]; then
                run rm "${path}"
                [ "$DRY_RUN" = 1 ] || say "removed ${path}"
                removed=$((removed + 1))
            else
                say "left alone (points elsewhere): ${path}"
            fi
        elif [ -e "${path}" ]; then
            say "left alone (not a link): ${path}"
        fi
    done
    drop_legacy
    if [ "$DRY_RUN" = 1 ]; then
        say "would remove ${removed} of ${#LINK_PATHS[@]} registrations"
    else
        say "${removed} of ${#LINK_PATHS[@]} registrations removed"
    fi

    if [ -f "${SETTINGS}" ] && [ "$DRY_RUN" = 0 ]; then
        python3 - "$SETTINGS" "$ROOT" <<'PY'
import json, shutil, sys
from pathlib import Path

settings_path, root = Path(sys.argv[1]), sys.argv[2]
try:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    sys.exit(f"install: {settings_path} is not valid JSON ({exc}); "
             f"remove ALTEKSTO_HOME by hand")
env = settings.get("env")
if not isinstance(env, dict) or "ALTEKSTO_HOME" not in env:
    print("install: no ALTEKSTO_HOME to remove")
elif env["ALTEKSTO_HOME"] != root:
    print(f"install: left alone, ALTEKSTO_HOME names {env['ALTEKSTO_HOME']}")
else:
    shutil.copy2(settings_path, settings_path.with_suffix(".json.bak"))
    del env["ALTEKSTO_HOME"]
    if not env:
        del settings["env"]
    settings_path.write_text(json.dumps(settings, indent=2) + "\n",
                             encoding="utf-8")
    print("install: removed ALTEKSTO_HOME")
PY
    elif [ "$DRY_RUN" = 1 ]; then
        say "would remove ALTEKSTO_HOME from ${SETTINGS}"
    fi

    say "done. Sessions outside this checkout no longer see the alteksto"
    say "skill or its agent types. Working in the checkout is unaffected."
    exit 0
fi

# The virtual environment. Producing a bundle needs an engine's page
# stack, which is the extra that [dev] already pulls in for every engine.
# --links-only skips this for an environment somebody else manages.
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
drop_legacy
for index in "${!LINK_PATHS[@]}"; do
    link "${LINK_TARGETS[$index]}" "${LINK_PATHS[$index]}"
done

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
settings, existed = {}, settings_path.is_file()
if existed:
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"install: {settings_path} is not valid JSON ({exc}); "
                 f"fix it or set ALTEKSTO_HOME by hand")
# The operator's file, so its shape is checked rather than assumed: a
# settings file that is not an object, or whose env is not one, is
# theirs to explain, and guessing at it would discard whatever it means.
if not isinstance(settings, dict):
    sys.exit(f"install: {settings_path} is not a JSON object; "
             f"set ALTEKSTO_HOME by hand")
env = settings.get("env", {})
if not isinstance(env, dict):
    sys.exit(f"install: {settings_path} has an 'env' that is not an object; "
             f"set ALTEKSTO_HOME by hand")

if env.get("ALTEKSTO_HOME") == root:
    print(f"install: ALTEKSTO_HOME already {root}")
else:
    # Backed up only when something is about to change, so that a rerun
    # that writes nothing cannot overwrite the backup of the file as it
    # stood before any of this.
    if existed:
        shutil.copy2(settings_path, settings_path.with_suffix(".json.bak"))
    env["ALTEKSTO_HOME"] = root
    settings["env"] = env
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
    checks=("${CLAUDE_DIR}/skills/alteksto/SKILL.md"
            "${LINK_PATHS[@]:1}")
    for path in "${checks[@]}"; do
        [ -e "${path}" ] || { say "BROKEN: ${path} resolves to nothing"; \
                              broken=1; }
    done
    if [ "$broken" = 1 ]; then
        say "the registration is incomplete; a session will find no"
        say "alteksto skill and say nothing about it"
        exit 1
    fi
    say "all ${#checks[@]} registrations resolve"
fi

say "done. In a new session, from any repository, say:"
say '  "use alteksto on the PDFs in <folder>"'
