#!/usr/bin/env python3
"""Move existing bundles to the schema_version this repository now declares.

The format evolves by a version bump, and a bundle declaring any other
version is not a bundle. So every bundle produced under an earlier version
stops validating the moment the format moves, whether or not anything about
it is actually wrong. Where the new version is a pure addition, as 3 and 4
both were, the whole of the migration is the integer: nothing else about a
correct bundle becomes incorrect.

This edits that integer and nothing else, textually rather than by
reserialising the manifest. A round trip through a JSON library would
reformat the file, reorder nothing but re-indent everything, and change
its bytes far beyond the one value that had to move. Those bytes are the
paper's identity to a consumer that hashes them, and the diff is what a
human reviews, so the edit is kept to the thing being changed.

What it will not do is pretend a bump is a migration when it is not. Each
bundle is validated after the edit, and one that does not come out valid
is reported with everything wrong with it. If a future version is not a
pure addition, that is where it shows: the integer will move and the
bundle will still be refused, which is the correct and loud answer rather
than a bundle declaring conformance it does not have.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from alteksto.bundle import SCHEMA_VERSION, validate_bundle

# The declaration as it is written, wherever the author put their spaces.
# Anchored on the key, and required to be unique in the file below, so this
# can never match some other object's idea of a schema_version.
_DECLARATION = re.compile(r'("schema_version"\s*:\s*)(-?\d+)')


class BumpError(Exception):
    """A bundle that cannot be bumped, with the reason a human needs."""


def bump_text(raw: str, target: int) -> tuple[str, int]:
    """Return (edited manifest text, the version it declared before).

    Raises BumpError rather than guessing whenever the file does not hold
    exactly one integer schema_version, because every other shape means
    the manifest is not what this tool thinks it is.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BumpError(f"manifest.json is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise BumpError(f"manifest.json must be a JSON object, got "
                        f"{type(data).__name__}")
    if "schema_version" not in data:
        raise BumpError("manifest.json declares no schema_version")
    current = data["schema_version"]
    if isinstance(current, bool) or not isinstance(current, int):
        raise BumpError(f"manifest.json schema_version is "
                        f"{type(current).__name__}, not an integer; this is "
                        f"a malformation to fix by hand, not a version to "
                        f"move")
    matches = _DECLARATION.findall(raw)
    if len(matches) != 1:
        raise BumpError(
            f"manifest.json writes schema_version {len(matches)} times; "
            f"the format refuses a repeated key, so fix that first")
    edited = _DECLARATION.sub(rf"\g<1>{target}", raw, count=1)
    # The edit is meant to move one value. Anything else having changed
    # means the substitution landed somewhere unintended, so the check is
    # on the parsed result rather than on trust in the pattern.
    after = json.loads(edited)
    if after.get("schema_version") != target:
        raise BumpError("the edit did not set schema_version; nothing "
                        "written")
    if {k: v for k, v in after.items() if k != "schema_version"} != \
            {k: v for k, v in data.items() if k != "schema_version"}:
        raise BumpError("the edit changed more than schema_version; "
                        "nothing written")
    return edited, current


def bump(bundle: Path, target: int, dry_run: bool) -> tuple[str, list[str]]:
    """Bump one bundle. Returns (what happened, problems that remain)."""
    manifest = bundle / "manifest.json"
    if not manifest.is_file():
        raise BumpError(f"no manifest.json in {bundle}")
    try:
        raw = manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BumpError(f"manifest.json could not be read as UTF-8: {exc}")
    edited, current = bump_text(raw, target)
    if current == target:
        return f"already at {target}", validate_bundle(bundle)
    if dry_run:
        return f"would move {current} -> {target}", []
    manifest.write_text(edited, encoding="utf-8")
    return f"{current} -> {target}", validate_bundle(bundle)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="bump_schema.py",
        description=f"Move bundles to schema_version {SCHEMA_VERSION}, "
                    f"editing that integer and nothing else.",
    )
    parser.add_argument("bundles", nargs="+", type=Path,
                        help="bundle directories, or directories of them "
                             "with --recurse")
    parser.add_argument("--recurse", action="store_true",
                        help="treat each argument as a directory of "
                             "bundles rather than as one bundle")
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would change and write nothing")
    args = parser.parse_args(argv)

    targets: list[Path] = []
    for given in args.bundles:
        if not args.recurse:
            targets.append(given)
            continue
        if not given.is_dir():
            print(f"bump-schema: not a directory: {given}", file=sys.stderr)
            return 1
        targets.extend(child for child in sorted(given.iterdir())
                       if child.is_dir() and not child.name.startswith("."))

    failed = invalid = 0
    for bundle in targets:
        try:
            action, problems = bump(bundle, SCHEMA_VERSION, args.dry_run)
        except BumpError as exc:
            failed += 1
            print(f"bump-schema: {bundle}: {exc}", file=sys.stderr)
            continue
        print(f"{bundle}\t{action}")
        if problems:
            invalid += 1
            for problem in problems:
                print(f"bump-schema: {bundle}: {problem}", file=sys.stderr)
    summary = f"{len(targets)} bundles, {failed} could not be bumped"
    if invalid:
        summary += (f", {invalid} do not validate at {SCHEMA_VERSION} and "
                    f"need more than a version bump")
    print(f"bump-schema: {summary}", file=sys.stderr)
    return 1 if (failed or invalid) else 0


if __name__ == "__main__":
    sys.exit(main())
