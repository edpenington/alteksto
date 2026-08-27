#!/usr/bin/env python3
"""Assemble a bundle's supplements.json from each supplement's own declaration.

One supplement is converted as its own paper-like unit, and whoever
converts it writes what it found to
`work/{id}/supplements/{name}/declaration.json`: the supplement's printed
title and its exhibits. This tool collects those into the one
`bundles/{id}/supplements.json` the format asks for.

The indirection exists for a reason worth stating. The route's rule is one
converter per paper-like unit, so several supplements of one paper can be
in flight at once, and the format wants a single declaration file at the
bundle root. Having each converter write into that shared file is a race
with a silent loser: two writers, one file, and the supplement that
finished first is simply not in it. Each writing its own file and this
assembling them afterwards is the same result without the race, and it
makes a half-finished run resumable, because the declarations that exist
are the supplements that are done.

The paper's id is read from the bundle's own manifest rather than taken as
an argument, so the two cannot disagree: the format requires them equal,
and there is no way to spell them differently here.

Writes nothing when there are no declarations, which is the ordinary case:
a paper with no supplementary material has no supplements.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# What one supplement's declaration carries. `name` is required and checked
# against the directory it was found in: a declaration copied to the wrong
# supplement is otherwise undetectable, and it would label one supplement's
# exhibits with another's title.
DECLARATION_KEYS = ("name", "title", "exhibits")


def _reject_duplicates(pairs):
    """A json object_pairs_hook that refuses a key stated twice.

    The format refuses a repeated key in manifest.json and in
    supplements.json, because the last value silently wins and the others
    are gone before any check runs. A declaration is the one route the
    playbook tells a converter to use, so resolving a duplicate quietly
    here would launder past that rule exactly the values no later check
    can contradict: a title, a caption, or an exhibits list that a second
    one replaced.
    """
    mapping = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError(f"declares {key!r} twice; only the last value "
                             f"survives a parse, so what was meant here "
                             f"cannot be recovered")
        mapping[key] = value
    return mapping


def read_declaration(path: Path, expected_name: str) -> dict:
    """One declaration, or a ValueError naming what is wrong with it."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path} could not be read as UTF-8: {exc}")
    try:
        data = json.loads(raw, object_pairs_hook=_reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}")
    except ValueError as exc:
        raise ValueError(f"{path} {exc}")
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object, got "
                         f"{type(data).__name__}")
    for key in DECLARATION_KEYS:
        if key not in data:
            raise ValueError(f"{path} is missing required key: {key!r}")
    for key in sorted(data):
        if key not in DECLARATION_KEYS:
            raise ValueError(f"{path} has unknown key: {key!r} (a "
                             f"declaration carries "
                             f"{', '.join(DECLARATION_KEYS)})")
    if data["name"] != expected_name:
        raise ValueError(
            f"{path} declares name {data['name']!r} but sits in "
            f"{expected_name!r}; the directory is the supplement's name, so "
            f"a declaration that disagrees with it belongs somewhere else")
    if not isinstance(data["exhibits"], list):
        raise ValueError(f"{path} key 'exhibits' must be a list, got "
                         f"{type(data['exhibits']).__name__}")
    return {key: data[key] for key in DECLARATION_KEYS}


def collect(work_dir: Path) -> list[dict]:
    """Every supplement declaration under the work directory, by name.

    Sorted, so one paper assembles identically on every filesystem and a
    rerun writes the same bytes.
    """
    supplements_dir = work_dir / "supplements"
    if not supplements_dir.is_dir():
        return []
    try:
        children = sorted(supplements_dir.iterdir())
    except OSError as exc:
        raise ValueError(f"{supplements_dir} could not be read: {exc}")
    found = []
    for child in children:
        if child.name.startswith(".") or not child.is_dir():
            continue
        declaration = child / "declaration.json"
        if not declaration.exists():
            raise ValueError(
                f"{child} has no declaration.json; a supplement that has "
                f"been converted says what it holds, and one that has not "
                f"is not finished")
        if not declaration.is_file():
            # There but not a file, so "has not been converted" would be a
            # confident and wrong diagnosis of what is in front of it.
            raise ValueError(f"{declaration} is not a file")
        found.append(read_declaration(declaration, child.name))
    return sorted(found, key=lambda entry: entry["name"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="assemble_supplements.py",
        description="Collect each supplement's declaration into the "
                    "bundle's supplements.json.",
    )
    parser.add_argument("work_dir", type=Path,
                        help="the paper's work directory, work/{id}")
    parser.add_argument("--bundle", type=Path, required=True,
                        help="the bundle to write into, bundles/{id}")
    args = parser.parse_args(argv)

    if not args.work_dir.is_dir():
        print(f"assemble-supplements: no work directory: {args.work_dir}",
              file=sys.stderr)
        return 1
    manifest_path = args.bundle / "manifest.json"
    if not manifest_path.is_file():
        print(f"assemble-supplements: no manifest at {manifest_path}; the "
              f"bundle's own identity is what the supplements carry",
              file=sys.stderr)
        return 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        paper_id = manifest["id"]
    except (json.JSONDecodeError, KeyError, OSError,
            UnicodeDecodeError) as exc:
        print(f"assemble-supplements: could not read the id from "
              f"{manifest_path}: {exc}", file=sys.stderr)
        return 1

    try:
        supplements = collect(args.work_dir)
    except ValueError as exc:
        print(f"assemble-supplements: {exc}", file=sys.stderr)
        return 1

    out = args.bundle / "supplements.json"
    if not supplements:
        print(f"assemble-supplements: {args.work_dir} declares no "
              f"supplements; nothing written", file=sys.stderr)
        return 0
    out.write_text(
        json.dumps({"id": paper_id, "supplements": supplements}, indent=2,
                   ensure_ascii=False) + "\n",
        encoding="utf-8")
    names = ", ".join(entry["name"] for entry in supplements)
    print(f"assemble-supplements: {out} <- {len(supplements)} "
          f"({names})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
