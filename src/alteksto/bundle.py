"""Paper bundle validation, enforcing docs/bundle.md.

This repository owns the bundle format; the specification lives in
docs/bundle.md and this module is its enforcement. Consumers of the
format (*meltiro* first among them) accept what passes here.

`validate_bundle(path)` returns EVERY problem as a list of strings; an
empty list means the bundle is valid. Nothing is raised for a malformed
bundle, so a caller can report all problems at once.

`figure_files(path)` answers the other question a consumer has to ask of
the directory: which files in it are exhibits, and what each is called.
That is a rule of the format too, so it is answered here rather than
reimplemented by every reader.

Both work on the standard library alone. The page tools need pymupdf and
lxml; the contract needs nothing, so a consumer depends on this package
and carries no PDF library it never opens.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_VERSION = 2

# `\Z`, not `$`: in Python `$` also matches immediately before a trailing
# newline, so `^[A-Za-z0-9._-]+$` would accept "1234\n". Both values this
# pattern guards break on a newline: the id becomes a filesystem path
# component, and a label becomes both a figures/*.png stem and the token
# consumers cite, neither of which can round-trip with a newline in it.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+\Z")
# The id is used verbatim as a path component downstream, so an id that is
# all punctuation is a path-traversal hazard: "." and ".." resolve to real
# directories. At least one letter or digit is required.
_ID_ALNUM = re.compile(r"[A-Za-z0-9]")
# An exhibit label names a file under figures/, so it obeys the same
# filename-safe rule; a separator can never appear in one.
_LABEL_PATTERN = _ID_PATTERN

# Manifest field contract: name -> (required?, type, allow_empty?). `str`
# covers the JSON string type; bool is deliberately not a valid int (see
# _is_int) so `schema_version: true` is rejected. `exhibits` has its own
# validator and no emptiness flag: an empty list is a legitimate assertion
# that the paper has no tables and no figures.
_MANIFEST_FIELDS = {
    "schema_version": (True, "int", None),
    "id": (True, "str", False),
    "title": (True, "str", False),
    "exhibits": (True, "exhibits", None),
    "doi": (False, "str", True),
    # Optional, but empty-if-present is a mistake, not a signal.
    "summary": (False, "str", False),
}

# The key set of one exhibits entry: label and caption required, notes
# optional (the exhibit's printed footnote text, non-empty when present),
# nothing else accepted, on the same terms as the manifest's own key
# contract.
_EXHIBIT_KEYS = ("label", "caption")
_EXHIBIT_OPTIONAL_KEYS = ("notes",)


def _is_int(value) -> bool:
    """True for a genuine JSON integer. Rejects bool (a Python int
    subclass) so `schema_version: true` does not sneak through."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_bundle(path) -> list[str]:
    """Return a list of ALL problems with the bundle at path.

    Empty list means valid. Never raises for a malformed bundle.
    """
    root = Path(path)
    if not root.exists():
        return [f"bundle directory does not exist: {root}"]
    if not root.is_dir():
        return [f"bundle path is not a directory: {root}"]

    problems: list[str] = []
    manifest_problems, declared = _validate_manifest(root)
    figure_problems, present = _validate_figures(root)
    problems.extend(manifest_problems)
    problems.extend(_validate_text(root))
    problems.extend(figure_problems)
    # The cross-checks run only when both sides are themselves well formed:
    # a malformed exhibits block or an unusable figures/ has already been
    # reported, and cross-checking against it would bury that report under
    # derived noise.
    if declared is not None and present is not None:
        problems.extend(_cross_check_exhibits(declared, present))
    return problems


def _validate_manifest(root: Path):
    """Return (problems, declared_labels) for manifest.json.

    declared_labels is the exhibits labels when the block is structurally
    sound, and None when it is missing or malformed (so the caller skips
    the cross-checks against figures/).
    """
    problems: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return ["manifest.json is missing"], None
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"manifest.json could not be read as UTF-8: {exc}"], None
    try:
        data, duplicates = _parse_manifest(raw)
    except json.JSONDecodeError as exc:
        return [f"manifest.json is not valid JSON: {exc}"], None
    if not isinstance(data, dict):
        return [f"manifest.json must be a JSON object, got "
                f"{type(data).__name__}"], None

    problems.extend(_duplicate_key_problems(data, duplicates))

    for key in data:
        if key not in _MANIFEST_FIELDS:
            problems.append(f"manifest.json has unknown key: {key!r}")

    declared_labels = None
    for name, (required, ptype, allow_empty) in _MANIFEST_FIELDS.items():
        if name not in data:
            if required:
                problems.append(f"manifest.json is missing required key: "
                                f"{name!r}")
            continue
        value = data[name]
        if ptype == "exhibits":
            exhibit_problems, labels = _validate_exhibits(value)
            problems.extend(exhibit_problems)
            if not exhibit_problems:
                declared_labels = labels
        elif ptype == "int":
            if not _is_int(value):
                problems.append(f"manifest.json key {name!r} must be an "
                                f"integer, got {type(value).__name__}")
                continue
            if name == "schema_version" and value != SCHEMA_VERSION:
                problems.append(f"manifest.json schema_version must be "
                                f"{SCHEMA_VERSION}, got {value}")
        elif ptype == "str":
            if not isinstance(value, str):
                problems.append(f"manifest.json key {name!r} must be a "
                                f"string, got {type(value).__name__}")
                continue
            if allow_empty is False and not value.strip():
                problems.append(f"manifest.json key {name!r} must be a "
                                f"non-empty string")
            if name == "id" and value.strip():
                if not _ID_PATTERN.match(value):
                    problems.append(
                        f"manifest.json id {value!r} must match "
                        f"^[A-Za-z0-9._-]+$ (letters, digits, dot, "
                        f"underscore, dash only)")
                elif not _ID_ALNUM.search(value):
                    problems.append(
                        f"manifest.json id {value!r} must contain at least "
                        f"one letter or digit; ids like '.' or '..' are "
                        f"rejected because the id is used directly as a "
                        f"filesystem path component")
    return problems, declared_labels


def _parse_manifest(raw):
    """Parse manifest.json, collecting every key an object declares twice.

    Python's json keeps the last value of a repeated key and drops the rest
    without a word, which makes a duplicate the one malformation nothing
    after the parse can report: the evidence is gone before any check runs,
    and a manifest declaring `id` twice would validate clean under whichever
    value came last.

    So the parse collects duplicates rather than resolving them silently.
    The hook json calls with each object's (key, value) pairs runs for every
    object at every depth, so a duplicate inside an exhibit entry is caught
    alongside one at the top level, and every duplicate in the file is
    collected rather than the first the parser happens to finish.

    Returns (data, duplicates): the manifest as a plain parse builds it,
    last value winning, and one (object, repeated keys) pair per object that
    repeats a key. Validation goes on over that object, so the file's other
    problems are still reported in the same pass and the duplicate says
    which of its values cannot be trusted.
    """
    duplicates = []

    def collect(pairs):
        mapping = {}
        repeated = []
        for key, value in pairs:
            if key in mapping and key not in repeated:
                repeated.append(key)
            mapping[key] = value
        if repeated:
            duplicates.append((mapping, repeated))
        return mapping

    return json.loads(raw, object_pairs_hook=collect), duplicates


def _duplicate_key_problems(data, duplicates) -> list[str]:
    """One problem per key an object declares twice, saying where it is.

    The hook cannot say that itself: json hands it an object's pairs and
    nothing about the key that object hangs from. So the parsed manifest is
    walked afterwards and each collected object matched by identity, which
    names `manifest.json exhibits[3]` the way every other problem here does,
    rather than leaving an author to hunt a bare key through a file every
    tool they own accepts. However many times a key repeats, it is one
    problem: the file states it more than once, which is the whole of what
    is wrong.

    An object the walk cannot reach is one that a duplicate elsewhere
    dropped, so it is reported without a position. The duplicate that
    dropped it is reported too.
    """
    if not duplicates:
        return []
    repeated = {id(mapping): keys for mapping, keys in duplicates}
    problems: list[str] = []
    located: set[int] = set()
    for where, node in _walk_objects(data, "manifest.json"):
        keys = repeated.get(id(node))
        if keys is None:
            continue
        located.add(id(node))
        problems.extend(_duplicate_key_problem(where, key) for key in keys)
    for mapping, keys in duplicates:
        if id(mapping) in located:
            continue
        where = "manifest.json (in a value another duplicate key replaced)"
        problems.extend(_duplicate_key_problem(where, key) for key in keys)
    return problems


def _duplicate_key_problem(where: str, key: str) -> str:
    return (f"{where} has a duplicate key: {key!r}; only the last value "
            f"survives the parse, so what the manifest declares here "
            f"cannot be recovered")


def _walk_objects(root, where: str):
    """Every JSON object under root, with the position that names it.

    Positions read as this module's other problems do: `manifest.json` for
    the manifest itself, `manifest.json exhibits[3]` for an exhibit entry.
    The walk carries its own queue rather than recursing, so a manifest
    nested deeply enough to exhaust the interpreter's stack is still a
    reported problem and not an exception out of validate_bundle. Breadth
    first, which for the shapes this format allows is the order the file
    reads.
    """
    queue = [(where, root)]
    cursor = 0
    while cursor < len(queue):
        position, node = queue[cursor]
        cursor += 1
        if isinstance(node, dict):
            yield position, node
            queue.extend((f"{position} {key}", value)
                         for key, value in node.items())
        elif isinstance(node, list):
            queue.extend((f"{position}[{index}]", item)
                         for index, item in enumerate(node))


def _validate_exhibits(value):
    """Validate the manifest's exhibits value.

    Returns (problems, labels): the declared labels in declaration order,
    and every problem with the block's shape. An empty list is valid and
    yields ([], []), the author's explicit assertion that the paper
    contains no tables and no figures.
    """
    if not isinstance(value, list):
        return ([f"manifest.json key 'exhibits' must be a list of "
                 f"{{label, caption}} objects, got "
                 f"{type(value).__name__}"], [])
    problems: list[str] = []
    labels: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(value):
        where = f"manifest.json exhibits[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} must be an object with exactly "
                            f"'label' and 'caption', got "
                            f"{type(entry).__name__}")
            continue
        for key in sorted(entry):
            if key not in _EXHIBIT_KEYS + _EXHIBIT_OPTIONAL_KEYS:
                problems.append(f"{where} has unknown key: {key!r} (an "
                                f"exhibit carries 'label' and 'caption', "
                                f"plus optional 'notes')")
        if "notes" in entry:
            notes = entry["notes"]
            if not isinstance(notes, str):
                problems.append(f"{where} key 'notes' must be a string, "
                                f"got {type(notes).__name__}")
            elif not notes.strip():
                problems.append(f"{where} key 'notes' must be a non-empty "
                                f"string when present")
        for key in _EXHIBIT_KEYS:
            if key not in entry:
                problems.append(f"{where} is missing required key: {key!r}")
                continue
            if not isinstance(entry[key], str):
                problems.append(f"{where} key {key!r} must be a string, got "
                                f"{type(entry[key]).__name__}")
            elif not entry[key].strip():
                problems.append(f"{where} key {key!r} must be a non-empty "
                                f"string")
        label = entry.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        if not _LABEL_PATTERN.match(label):
            problems.append(
                f"{where} label {label!r} must match ^[A-Za-z0-9._-]+$ "
                f"(letters, digits, dot, underscore, dash only): it is the "
                f"stem of a figures/*.png file and the token consumers "
                f"cite")
            continue
        if label in seen:
            problems.append(f"{where} label {label!r} is declared more than "
                            f"once; exhibit labels must be unique within a "
                            f"bundle")
            continue
        seen.add(label)
        labels.append(label)
    return problems, labels


def _cross_check_exhibits(declared_labels, present_labels) -> list[str]:
    """Bind the manifest's declaration to figures/. Both directions are
    hard errors; docs/bundle.md says why."""
    problems: list[str] = []
    declared = set(declared_labels)
    present = set(present_labels)
    for label in sorted(declared - present):
        problems.append(
            f"manifest.json declares exhibit {label!r} but there is no "
            f"figures/{label}.png")
    for label in sorted(present - declared):
        problems.append(
            f"figures/{label}.png is not declared in manifest.json "
            f"'exhibits'; every supplied image must be declared with its "
            f"caption")
    return problems


def _validate_text(root: Path) -> list[str]:
    text_path = root / "text.md"
    if not text_path.exists():
        return ["text.md is missing"]
    try:
        text = text_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"text.md could not be read as UTF-8: {exc}"]
    if not text.strip():
        return ["text.md is empty"]
    return []


def figure_files(root) -> dict[str, Path]:
    """The crops a bundle supplies: label to path, ordered by label.

    Which files under figures/ are exhibits, and what each one is called,
    are rules of the format, so they are answered here once and read by
    everyone: by the validator below, and by a consumer loading a bundle it
    has already validated. Two enumerations of the same directory could
    disagree about a case-varying suffix or a dotfile, and the consumer's
    would win, putting a label in front of a reader that no check ever saw.

    It reports nothing and refuses nothing. A stray file is validate_bundle's
    to reject; a missing figures/ is the no-images case, and the manifest's
    exhibits is what says whether that is correct. The ordering is by label
    rather than by directory order, so one bundle enumerates identically on
    every filesystem.
    """
    figures_dir = Path(root) / "figures"
    if not figures_dir.is_dir():
        return {}
    found = {}
    for child in sorted(figures_dir.iterdir()):
        if child.name.startswith("."):
            continue  # hidden OS metadata (.DS_Store etc.) is not an asset
        if child.is_dir():
            continue
        if child.suffix.lower() == ".png":
            found[child.stem] = child
    return {label: found[label] for label in sorted(found)}


def _validate_figures(root: Path):
    """Return (problems, present_labels) for the figures/ directory.

    present_labels is the label of every crop figure_files finds, and None
    when the directory itself is unusable (so the caller skips the
    cross-checks). What is a crop is that function's answer, not a second
    reading of the directory; what is left over is what is reported here.
    """
    figures_dir = root / "figures"
    if not figures_dir.exists():
        return [], []
    if not figures_dir.is_dir():
        return [f"figures exists but is not a directory: {figures_dir}"], None
    problems: list[str] = []
    for child in sorted(figures_dir.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            problems.append(f"figures/ contains a subdirectory (only .png "
                            f"files allowed): {child.name}")
        elif child.suffix.lower() != ".png":
            problems.append(f"figures/ contains a non-png file (only .png "
                            f"files allowed): {child.name}")
    return problems, list(figure_files(root))
