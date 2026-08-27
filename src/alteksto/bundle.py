"""Paper bundle validation, enforcing docs/bundle.md.

This repository owns the bundle format; the specification lives in
docs/bundle.md and this module is its enforcement. Consumers of the
format (e.g. *meltiro*, *forfiltri*) accept what passes here.

`bundle_problems(path)` returns a list of strings, one per problem; an
empty list means the bundle is valid. Nothing is raised for a malformed
bundle, so one run reports everything the module found. That is every
problem it can state truthfully, which is deliberately not every problem
there may be: a cross-check is skipped when the declaration or directory
it would read is itself malformed, and a duplicate key ends its file's
report, because a problem derived from values that cannot be trusted is
a guess in the voice of a fact, and would bury the report of the fault
it grew from. Fixing that fault and running again surfaces whatever it
was hiding.

`figure_files(path)` answers the other question a consumer has to ask of
the directory: which files in it are exhibits, and what each is called.
That is a rule of the format too, so it is answered here rather than
reimplemented by every reader. `table_files(path)` answers the same
question of `tables/`, the transcriptions an exhibit may carry beside its
crop, and `table_html_problems(source, where)` is what one of those files
has to be. That last one is public because the producing side needs it
too: a tool that renders a transcription refuses the same files this
refuses, rather than forming its own opinion of what a table is.
`name_problem(value, ...)` is public for the same reason: a tool staging
a name refuses it in the format's own words, before a conversion runs on
it rather than at gate 1 after.

All of them work on the standard library alone, the table transcriptions
included: their structure is checked with `html.parser`, so enforcing the
format still costs a consumer no dependency. The page tools need pymupdf
and lxml; the contract needs nothing, so a consumer depends on this
package and carries no PDF library it never opens.
"""

from __future__ import annotations

import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

SCHEMA_VERSION = 5


# -------------------------- the rule for every name that becomes a path

def name_problem(value, what="name", where="", because=None):
    r"""Why a name may not become a path in a bundle, or None if it may.

    The id, an exhibit label and a supplement name each become a
    directory or a file stem, and this function notes any problems
    that would arise as a result

    `what` and `where` locate the name for its reader, and `because`
    says what this particular name is for.

    It uses `\Z`, not `$`: Python's `$` also matches immediately before a
    trailing newline, so `$` would accept "fig_01\n". The problem says
    `$` anyway, that being the form a reader knows, and the words beside
    it already exclude a newline.

    A leading dot is refused even though the pattern admits a dot
    anywhere: every directory walk, here and in a consumer, skips
    dot-leading entries as OS metadata, so a name starting with one
    would declare a file no reader ever sees, and the report about it
    would accuse a file that is really there of being missing.
    """
    head = " ".join(part for part in (where, what) if part)
    if not isinstance(value, str):
        return f"{head} must be a string, got {type(value).__name__}"
    if not re.match(r"^[A-Za-z0-9._-]+\Z", value):
        problem = (f"{head} {value!r} must match ^[A-Za-z0-9._-]+$ "
                   f"(letters, digits, dot, underscore, dash only)")
    elif not re.search(r"[A-Za-z0-9]", value):
        problem = (f"{head} {value!r} must contain at least one letter or "
                   f"digit")
        # One tail, not two. A caller that says what its name is for says
        # it better than this does, so this is only what is left when no
        # caller has.
        because = because or ("punctuation alone is not a name, and '.' "
                              "and '..' resolve to real directories")
    elif value.startswith("."):
        problem = (f"{head} {value!r} must not start with a dot; every "
                   f"directory walk skips dot-leading entries as OS "
                   f"metadata, so what this names would never be read")
    else:
        return None
    return f"{problem}: {because}" if because else problem


# ------------------------ the whole bundle, and reading its disk at all

def bundle_problems(path) -> list[str]:
    """Return the problems with the bundle at path.

    Empty list means valid. Never raises for a malformed bundle, and
    never blocks: the disk failing to read (permissions, pipes, links
    to nowhere) is not the bundle being malformed, but it is answered
    with a problem too, not an exception or a hang. The list is every
    problem this module can state truthfully; the module docstring says
    where it deliberately stops, and why.
    """
    root = Path(path)
    if not root.exists() and not root.is_symlink():
        return [f"bundle directory does not exist: {root}"]
    if not root.is_dir():
        return [f"bundle path is not a directory: {root}"]
    # Probed before any check reports, because an unreadable directory
    # would otherwise report every file in it as missing, which is
    # false: nothing could be read at all.
    try:
        entries = _list_directory(root)
    except OSError as exc:
        return [f"bundle directory could not be read: {exc}; nothing "
                f"in it can be checked"]

    problems: list[str] = _miscased_entry_problems(entries, _CONTRACT_ENTRIES)
    manifest_problems, declared, paper_id = _manifest_problems(root)
    figure_problems, present = _figure_problems(root)
    table_problems, transcribed = _table_problems(root)
    supplement_problems, supplements = _supplement_problems(root, paper_id)
    problems.extend(manifest_problems)
    problems.extend(_text_problems(root))
    problems.extend(figure_problems)
    problems.extend(table_problems)
    problems.extend(supplement_problems)
    # A cross-check runs only over sides that are themselves well formed:
    # a malformed exhibits block or an unusable figures/ has already been
    # reported, and cross-checking against it would bury that report under
    # derived noise.
    if declared is not None and present is not None:
        problems.extend(_exhibit_binding_problems(declared, present))
    if declared is not None and transcribed is not None:
        problems.extend(_table_binding_problems(declared, transcribed))
    if supplements:
        problems.extend(_supplement_contents_problems(root, supplements))
        # Label uniqueness reads the manifest only for the article's own
        # labels. When its exhibits block is malformed those labels are
        # unknown and their clashes wait, but a clash between two
        # supplements does not depend on the manifest at all, so the check
        # still runs with no article labels rather than being skipped with
        # the rest.
        problems.extend(_label_uniqueness_problems(
            declared if declared is not None else [], supplements))
    return problems


# The six entries the layout names, and the three a supplement holds.
# They are matched exactly, which is the whole reason this list exists:
# see _miscased_entry_problems.
_CONTRACT_ENTRIES = ("manifest.json", "text.md", "figures", "tables",
                     "supplements.json", "supplements")
_SUPPLEMENT_ENTRIES = ("text.md", "figures", "tables")


def _miscased_entry_problems(entries, contract, where="the bundle"):
    """Refuse an entry that is a contract name in the wrong case.

    A case-insensitive filesystem, which is the macOS default, keeps
    `Figures/` and answers to `figures/` as well, so a bundle built on
    one validates while every path this format promises is absent on a
    case-sensitive consumer. That is the same fault the exact `.png`
    suffix rule exists to stop, one level up, and it is worse: it is
    invisible on the machine that produced it.

    Only a name that differs from a contract name by case is refused. A
    bundle may carry its own paperwork beside the six, so `Notes.md` is
    nobody's business but the author's.
    """
    problems: list[str] = []
    present = {entry.name for entry in entries}
    folded = {name.lower(): name for name in present}
    for name in contract:
        held = folded.get(name)
        if held is not None and held != name:
            problems.append(
                f"{where} holds {held!r} where the format names "
                f"{name!r}; the names are matched exactly, so a "
                f"consumer on a case-sensitive filesystem would find "
                f"nothing at {name!r}")
    return problems


def _list_directory(directory: Path) -> list[Path]:
    """The directory's entries, sorted, or OSError when it cannot give
    them.

    Listing needs the directory readable and the stat through it needs
    it searchable, and a walk that goes on without both reports files
    that are present as missing, which is false and cannot be followed
    to a fix. The dot is joined as a string because pathlib normalizes
    a "." component away, and the path that leaves would stat the
    directory itself, a thing its parent's permissions govern.
    """
    children = sorted(directory.iterdir())
    os.stat(os.path.join(directory, "."))
    return children


def _read_utf8(path: Path, where: str):
    """Return (text, problem) for one file the format wants read.

    Reading the disk can fail in ways that are not the bundle being
    malformed, and every one of them must come back as a problem rather
    than an exception or a hang: bundle_problems never raises and never
    blocks. The shape is checked before the open, because opening a
    FIFO for reading blocks until something writes to it, and because a
    path that is not a regular file is a shape fault and is reported as
    one rather than in encoding words.
    """
    if path.is_dir():
        return None, f"{where} is a directory where the format needs a file"
    if not path.is_file():
        return None, (f"{where} is not a regular file that can be read "
                      f"(a pipe, socket, device or dangling link holds "
                      f"no text)")
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"{where} could not be read as UTF-8: {exc}"
    except OSError as exc:
        return None, f"{where} could not be read: {exc}"


# -------------------------------------------------------- manifest.json

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


def _manifest_problems(root: Path):
    """Return (problems, declared_labels, id) for manifest.json.

    declared_labels is the exhibits labels when the block is structurally
    sound, and None when it is missing or malformed (so the caller skips
    the cross-checks against figures/). The id comes back so that
    supplements.json can be held to declaring the same one.
    """
    problems: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.exists() and not manifest_path.is_symlink():
        return ["manifest.json is missing"], None, None
    raw, unread = _read_utf8(manifest_path, "manifest.json")
    if unread:
        return [unread], None, None
    try:
        data, duplicates = _parse_manifest(raw)
    except json.JSONDecodeError as exc:
        return [_json_problem("manifest.json", raw, exc)], None, None
    except ValueError:
        # JSONDecodeError is a ValueError and is caught above, so this
        # clause sees only a file json read as JSON and Python then
        # refused to build a value from. CPython's integer digit limit
        # is the known case: a literal of more than
        # sys.get_int_max_str_digits() digits raises a plain ValueError,
        # not a JSONDecodeError, from either parse site.
        # The interpreter's own words are not repeated here: they end by
        # naming the call that raises the limit, which is advice for
        # someone writing a reader and the wrong way round for someone
        # holding a bundle. No manifest field carries such a number, so
        # the fault is the file, not the reader's ceiling.
        return ["manifest.json holds a number too long to read; no "
                "manifest field carries a number of thousands of "
                "digits"], None, None
    except RecursionError:
        # The walk below carries its own queue so that depth cannot throw
        # out of it, but the parse runs first and json's scanner recurses in
        # C, at a depth that is a property of the interpreter rather than of
        # this format: 3.11 gives up where later versions keep going. Either
        # way bundle_problems answers with a problem, because it never
        # raises for a malformed bundle, and a manifest this deep is
        # malformed whatever the parser makes of it.
        return ["manifest.json is nested too deeply to parse; a manifest is "
                "a flat object with one list of exhibits in it"], None, None
    if not isinstance(data, dict):
        return [f"manifest.json must be a JSON object, got "
                f"{type(data).__name__}"], None, None

    # Nothing further is said about a file whose values cannot be known.
    # A check on a duplicated key reads whichever value the parse kept, so
    # `"schema_version": 5, "schema_version": 99` reports "got 99" about a
    # manifest that also says 5, and an id read this way travels on into the
    # comparison with supplements.json and accuses the wrong file. Every
    # duplicate in the file is named first, because the author has to open
    # it either way, and one run should show them all of it.
    if duplicates:
        return _duplicate_key_problems(data, duplicates), None, None

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
            exhibit_problems, labels = _exhibit_problems(value)
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
                problem = name_problem(
                    value, "id", "manifest.json",
                    "it is used directly as a filesystem path component")
                if problem:
                    problems.append(problem)
    manifest_id = data.get("id")
    if not isinstance(manifest_id, str):
        manifest_id = None
    return problems, declared_labels, manifest_id


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


def _json_problem(where: str, raw: str, exc) -> str:
    """One JSON parse failure, in the format's words not the decoder's.

    json's own message for a byte order mark ends by naming the codec
    that would accept the file, which is advice for someone writing a
    reader and the wrong way round for someone holding a bundle. The
    mark is named here instead. Every other parse failure keeps the
    decoder's line and column, which are the useful part of it.
    """
    if raw.startswith("\ufeff"):
        return (f"{where} starts with a byte order mark; JSON has no "
                f"place for one, so the file is not JSON until it is "
                f"taken off the front")
    return f"{where} is not valid JSON: {exc}"


def _duplicate_key_problems(data, duplicates,
                           where="manifest.json") -> list[str]:
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
    declared_in = where
    for where, node in _walk_objects(data, declared_in):
        keys = repeated.get(id(node))
        if keys is None:
            continue
        located.add(id(node))
        problems.extend(_duplicate_key_problem(where, key, declared_in)
                        for key in keys)
    for mapping, keys in duplicates:
        if id(mapping) in located:
            continue
        where = f"{declared_in} (in a value another duplicate key replaced)"
        problems.extend(_duplicate_key_problem(where, key, declared_in)
                        for key in keys)
    return problems


def _duplicate_key_problem(where: str, key: str,
                           declared_in: str = "manifest.json") -> str:
    return (f"{where} has a duplicate key: {key!r}; only the last value "
            f"survives the parse, so what {declared_in} declares here "
            f"cannot be recovered")


def _walk_objects(root, where: str):
    """Every JSON object under root, with the position that names it.

    Positions read as this module's other problems do: `manifest.json` for
    the manifest itself, `manifest.json exhibits[3]` for an exhibit entry.
    The walk carries its own queue rather than recursing, so a manifest
    nested deeply enough to exhaust the interpreter's stack is still a
    reported problem and not an exception out of bundle_problems. Breadth
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


def _exhibit_problems(value, where="manifest.json"):
    """Every problem with an exhibits value, the manifest's or a
    supplement's.

    Returns (problems, labels): the declared labels in declaration order,
    and every problem with the block's shape. An empty list is valid and
    yields ([], []), the author's explicit assertion that the paper, or
    the supplement declaring it, contains no tables and no figures.
    """
    if not isinstance(value, list):
        return ([f"{where} key 'exhibits' must be a list of objects, each "
                 f"carrying 'label' and 'caption' plus optional non-empty "
                 f"'notes', got {type(value).__name__}"], [])
    problems: list[str] = []
    labels: list[str] = []
    seen: set[str] = set()
    declared_in = where
    for index, entry in enumerate(value):
        where = f"{declared_in} exhibits[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} must be an object carrying 'label' "
                            f"and 'caption' plus optional non-empty "
                            f"'notes', got {type(entry).__name__}")
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
        problem = name_problem(
            label, "label", where,
            "it is the stem of a figures/*.png file and the token "
            "consumers cite")
        if problem:
            problems.append(problem)
            continue
        if label in seen:
            problems.append(f"{where} label {label!r} is declared more than "
                            f"once; exhibit labels must be unique within a "
                            f"bundle")
            continue
        seen.add(label)
        labels.append(label)
    return problems, labels


# -------------------------------------------------------------- text.md

def _text_problems(root: Path) -> list[str]:
    text_path = root / "text.md"
    if not text_path.exists() and not text_path.is_symlink():
        return ["text.md is missing"]
    text, unread = _read_utf8(text_path, "text.md")
    if unread:
        return [unread]
    if not text.strip():
        return ["text.md is empty"]
    return []


# ------------------------------------------------------------- figures/

def figure_files(root) -> dict[str, Path]:
    """The crops a bundle supplies: label to path, ordered by label.

    Which files under figures/ are exhibits, and what each one is called,
    are rules of the format, so they are answered here once and read by
    everyone: by the validator below, and by a consumer loading a bundle it
    has already validated. Two enumerations of the same directory could
    disagree about a case-varying suffix or a dotfile, and the consumer's
    would win, putting a label in front of a reader that no check ever saw.

    It reports nothing and refuses nothing. A stray file is for bundle_problems
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
        if child.suffix == ".png":
            found[child.stem] = child
    return {label: found[label] for label in sorted(found)}


# The eight bytes every PNG file starts with. The check on a crop reads
# these and the file's size, never a pixel: it says whether the file is
# a PNG at all, which is the least a consumer opening figures/<label>.png
# relies on, and no more.
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _figure_problems(root: Path, prefix: str = ""):
    """Return (problems, present_labels) for the figures/ directory.

    `prefix` names where the directory sits when it is not the bundle's
    own, so a supplement's problems read `supplements/{name}/figures/`
    and point at the file an author has to open.

    present_labels is the label of every crop figure_files finds, and None
    when the directory itself is unusable (so the caller skips the
    cross-checks). What is a crop is that function's answer, not a second
    reading of the directory; what is left over is what is reported here.
    Each crop is then held to being a non-empty regular file starting
    with the PNG signature, because a zero-byte file, a GIF renamed, or
    a link to nothing would otherwise pass and fail in the consumer that
    was promised what passes here.
    """
    figures_dir = root / "figures"
    if not figures_dir.exists() and not figures_dir.is_symlink():
        return [], []
    if not figures_dir.is_dir():
        return [f"{prefix}figures exists but is not a directory: "
                f"{figures_dir}"], None
    try:
        children = _list_directory(figures_dir)
    except OSError as exc:
        return [f"{prefix}figures/ could not be read: {exc}; nothing "
                f"in it can be checked"], None
    problems: list[str] = []
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir():
            problems.append(f"{prefix}figures/ contains a subdirectory "
                            f"(only .png files allowed): {child.name}")
        elif child.suffix != ".png":
            problems.append(f"{prefix}figures/ contains a non-png file "
                            f"(the suffix must be exactly .png, "
                            f"lowercase): {child.name}")
    crops = figure_files(root)
    usable: list[str] = []
    for label, path in crops.items():
        where = f"{prefix}figures/{label}.png"
        # Asked before anything binds this label to a declaration, which
        # would otherwise tell the author to declare a stem no
        # declaration may carry, and earn them the name rule's refusal
        # for following the advice. A stem that can never be a label is
        # left out of what comes back, so the one fault is said once.
        stem_problem = name_problem(
            label, "stem", where,
            "a crop's stem is the label an exhibit is declared and cited"
            " under, so it obeys the rule every label obeys")
        if stem_problem:
            problems.append(stem_problem)
            continue
        usable.append(label)
        if not path.is_file():
            problems.append(f"{where} is not a regular file; a crop is "
                            f"an ordinary file holding a PNG image, and "
                            f"a pipe, socket or dangling link holds "
                            f"none")
            continue
        try:
            with path.open("rb") as crop:
                head = crop.read(len(_PNG_SIGNATURE))
        except OSError as exc:
            problems.append(f"{where} could not be read: {exc}")
            continue
        if not head:
            problems.append(f"{where} is empty; a crop is a PNG image, "
                            f"and an empty file holds none")
        elif head != _PNG_SIGNATURE:
            problems.append(f"{where} does not start with the PNG "
                            f"signature; whatever the file holds, it is "
                            f"not a PNG, and a consumer opening it as "
                            f"one fails")
    return problems, usable


def _exhibit_binding_problems(declared_labels, present_labels,
                              prefix="",
                              declared_in="manifest.json") -> list[str]:
    """Bind a declaration to its figures/. Both directions are hard
    errors; docs/bundle.md says why. `prefix` and `declared_in` name the
    directory and the file that declares it, so a supplement's problems
    say which supplement and point at supplements.json."""
    problems: list[str] = []
    declared = set(declared_labels)
    present = set(present_labels)
    for label in sorted(declared - present):
        # "no file named" rather than "there is no": on a case-insensitive
        # filesystem the path opens when the crop is `TABLE_01.PNG`, so
        # the flat claim is checkably false on the machine that built it,
        # and it is the name, not the path, that this binds.
        problems.append(
            f"{declared_in} declares exhibit {label!r} but no file in "
            f"{prefix}figures/ is named {label}.png")
    for label in sorted(present - declared):
        problems.append(
            f"{prefix}figures/{label}.png is not declared in "
            f"{declared_in} 'exhibits'; every supplied image must be "
            f"declared with its caption")
    return problems


# -------------------------------------------------------------- tables/

def table_files(root) -> dict[str, Path]:
    """The table transcriptions a bundle supplies: label to path, by label.

    The `tables/` answer to `figure_files`, and answered here for the same
    reason: which files in the directory are transcriptions, and which
    exhibit each belongs to, are rules of the format rather than a reading
    a consumer is left to invent. A bundle may supply none, some or all of
    its exhibits' transcriptions, so unlike `figures/` a label absent here
    is not a defect. It means the exhibit's content is its crop, which is
    what every exhibit meant before this directory existed.

    Absence is the only signal there is, and it is a strong one: a
    transcription reaches a bundle only by passing the checks in this
    module and the producing route's gates, so a file that is here has been
    vouched for and one that is not was never claimed. There is no field
    marking a weaker class, because a consumer cannot act on one.
    """
    tables_dir = Path(root) / "tables"
    if not tables_dir.is_dir():
        return {}
    found = {}
    for child in sorted(tables_dir.iterdir()):
        if child.name.startswith("."):
            continue  # hidden OS metadata (.DS_Store etc.) is not an asset
        if child.is_dir():
            continue
        if child.suffix == ".html":
            found[child.stem] = child
    return {label: found[label] for label in sorted(found)}


def _table_problems(root: Path, prefix: str = ""):
    """Return (problems, transcribed_labels) for the tables/ directory.

    transcribed_labels is the label of every transcription table_files
    finds, and None when the directory itself is unusable, so the caller
    skips the cross-check the way it does for figures/.
    """
    tables_dir = root / "tables"
    if not tables_dir.exists() and not tables_dir.is_symlink():
        return [], []
    if not tables_dir.is_dir():
        return [f"{prefix}tables exists but is not a directory: "
                f"{tables_dir}"], None
    try:
        children = _list_directory(tables_dir)
    except OSError as exc:
        return [f"{prefix}tables/ could not be read: {exc}; nothing "
                f"in it can be checked"], None
    problems: list[str] = []
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir():
            problems.append(f"{prefix}tables/ contains a subdirectory "
                            f"(only .html files allowed): {child.name}")
        elif child.suffix != ".html":
            problems.append(f"{prefix}tables/ contains a non-html file "
                            f"(the suffix must be exactly .html, "
                            f"lowercase): {child.name}")
    transcriptions = table_files(root)
    for label, path in transcriptions.items():
        where = f"{prefix}tables/{label}.html"
        source, unread = _read_utf8(path, where)
        if unread:
            problems.append(unread)
            continue
        problems.extend(table_html_problems(source, where))
    return problems, list(transcriptions)


def _table_binding_problems(declared_labels, transcribed_labels,
                            prefix="",
                            declared_in="manifest.json") -> list[str]:
    """Bind tables/ to the manifest's declaration, in the one direction
    that is an error.

    A declared exhibit without a transcription is the ordinary case and
    says nothing; a transcription without a declared exhibit is a file
    claiming to be an exhibit's content when the bundle vouches for no such
    exhibit, which is the same fault as an undeclared crop and refused on
    the same grounds. The crop itself is already required by the figures/
    cross-check, so a transcription can never stand alone in front of a
    reader with no image behind it.
    """
    declared = set(declared_labels)
    return [
        f"{prefix}tables/{label}.html is not declared in {declared_in} "
        f"'exhibits'; a transcription belongs to a declared exhibit, and "
        f"its label names which one"
        for label in sorted(set(transcribed_labels) - declared)
    ]


# ---------------------------------------- what a transcription may hold

# Elements a table's cells may contain, and which may nest in each other.
_INLINE_ELEMENTS = frozenset({"sup", "sub", "br", "em", "strong"})
_CELL_ELEMENTS = frozenset({"th", "td"})
_ROW_GROUPS = frozenset({"thead", "tbody"})
# The elements a table transcription may use. The list is short on purpose:
# it is everything needed to say what a printed table says, and nothing that
# carries presentation, scripting or a second document inside the first.
# `caption` is absent deliberately and reported by name below, because a
# caption is carried by text.md and the manifest and a crop that bakes the
# printed caption into the image invites an author to repeat it here.
# The whitelist is the union of the sets above, plus the two elements that
# are only themselves, so it cannot drift from the sets that classify what
# is in it.
_TABLE_ELEMENTS = (frozenset({"table", "tr"}) | _ROW_GROUPS
                   | _CELL_ELEMENTS | _INLINE_ELEMENTS)
# `br` is the only element written in the self-closing form; every other
# element in the whitelist is opened and closed.
_VOID_ELEMENTS = frozenset({"br"})
# Elements named in a problem when they appear, rather than being reported
# as merely unknown, because each is a thing an author plausibly reaches for
# and the reason it is refused is not guessable from a whitelist.
_TABLE_ELEMENT_NOTES = {
    "caption": "the exhibit's caption is carried by text.md and the "
               "manifest, never repeated here",
    "tfoot": "the exhibit's printed footnote is the manifest's 'notes'; a "
             "totals row is an ordinary row of tbody",
    "colgroup": "column styling is presentation, and the transcription "
                "carries content only",
    "col": "column styling is presentation, and the transcription carries "
           "content only",
    "style": "a transcription carries no styling",
    "script": "a transcription carries no scripting",
    "img": "a transcription carries no images; the crop is the image",
    "a": "a link is presentation here; the printed characters are the "
         "content",
}
# Attributes each element may carry. Everything else, `style` and `class`
# included, is refused: they say how a table looks, and how it looks is what
# the crop is for.
_TABLE_ATTRIBUTES = {
    "th": frozenset({"colspan", "rowspan", "scope"}),
    "td": frozenset({"colspan", "rowspan"}),
}
# An upper bound on one span. No printed table spans a thousand columns, and
# without a bound a malformed `rowspan="99999999"` would have the grid below
# allocate until the process died. A bundle is input, so it gets a limit.
_SPAN_LIMIT = 1000
# And an upper bound on the grid those spans describe, which the span limit
# alone does not give: twenty cells of `colspan="1000"` beside one
# `rowspan="1000"` is a 26 KB file describing twenty million positions, and
# walking them to report the holes is work a bundle should not be able to
# ask for. Gate 1 runs this on every conversion and `render_table.py` runs
# it before it draws, so the bound is what keeps both cheap. No printed
# exhibit comes near it.
_GRID_LIMIT = 100_000


def table_html_problems(source: str, where: str) -> list[str]:
    """Every problem with one transcription's markup and structure.

    Two questions are asked, and the second is the one worth the machinery.
    The first is whether the file uses only what the format allows: the
    whitelisted elements, three attributes, one table and no document
    around it. The second is whether the cells tile a rectangle exactly,
    which is what makes a transcription checkable at all. A dropped cell,
    a colspan one too small, or two cells claiming one position all leave
    the grid holed or overlapped, and those are precisely the errors that
    slide a value into the wrong column while reading perfectly plausibly.
    Both are answered without looking at a single character of content: no
    check here knows whether the numbers are the paper's, which is the
    round trip's job and then the sweep's.
    """
    # A byte order mark survives a UTF-8 read and is not a character the
    # exhibit prints, so it is dropped rather than reported as text outside
    # a cell, which is a true statement that helps nobody.
    source = source.lstrip("\ufeff")
    if not source.strip():
        return [f"{where} is empty; an exhibit with no transcription omits "
                f"the file rather than supplying an empty one"]
    parser = _TableHTMLParser(where)
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:  # noqa: BLE001 - any parse fault is a problem
        return parser.problems + [f"{where} could not be parsed as HTML: "
                                  f"{exc}"]
    return parser.finish()


class _TableHTMLParser(HTMLParser):
    """The whitelist and the grid, in one pass over a transcription.

    `html.parser` is lenient by design: it accepts a tag that is never
    closed and a closing tag matching nothing open, and reports neither.
    That leniency is the thing to guard against here rather than a
    convenience to lean on, so this class keeps its own stack and says so
    when the markup does not balance. What it refuses, it refuses by name.

    The grid is the second half and the reason the rest is worth having.
    Cells are placed the way a reader lays them out, left to right along a
    row and skipping positions an earlier rowspan already claimed, and
    every position a cell covers is recorded. A correct table covers its
    rectangle exactly once: a hole is a cell that went missing or a span
    one too small, and an overlap is two cells claiming one position.
    Both read perfectly plausibly on the page, and both move a value into
    a column it does not belong in.
    """

    def __init__(self, where: str):
        super().__init__(convert_charrefs=True)
        self.where = where
        self.problems: list[str] = []
        self.stack: list[str] = []
        self.seen_table = False
        self.second_table = False
        self.rows_opened = 0
        self.row_index = -1
        self.column = 0
        self.cells = 0
        self.cells_in_row = 0
        self.empty_rows: list[int] = []
        self.occupied: dict[tuple[int, int], bool] = {}
        self.grid_overflowed = False

    # -- reporting -----------------------------------------------------

    def _problem(self, message: str) -> None:
        self.problems.append(f"{self.where} {message}")

    @staticmethod
    def _at(row, column=None) -> str:
        """A grid position, phrased so a reader can find it.

        The grid is built 0-based with thead rows in the row count, and
        neither is how a person reads a printed table, so a bare index
        sends them to the wrong row. Every message that names a position
        counts from 1 and says what the count includes.
        """
        place = f"row {row + 1}"
        if column is not None:
            place = f"{place} column {column + 1}"
        return f"{place} (counted from 1, thead rows included)"

    # -- element events ------------------------------------------------

    def handle_starttag(self, tag, attrs):
        self._check_element(tag, attrs)
        if tag not in _VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        # Only a whitelisted element earns the self-closing complaint.
        # For a refused one the refusal below is the whole answer, and
        # saying every other element is opened and closed beside it
        # would teach an author to write the refused element that way
        # and be refused again.
        miswritten = (tag in _TABLE_ELEMENTS
                      and tag not in _VOID_ELEMENTS)
        if miswritten:
            self._problem(f"writes <{tag}/> in the self-closing form; only "
                          f"<br> is written that way, and every other "
                          f"element is opened and closed")
        self._check_element(tag, attrs)
        if miswritten:
            # Read on as HTML5 reads it: the stray slash on a non-void
            # element means nothing, so the element is open and what
            # follows is inside it. Treating it as closed would move a
            # cell's own text outside the cell and report nesting
            # faults the author never wrote.
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in _VOID_ELEMENTS:
            self._problem(f"closes </{tag}>, which is written <{tag}> "
                          f"alone and never closed")
            return
        if not self.stack:
            self._problem(f"closes </{tag}> with no element open")
            return
        if self.stack[-1] != tag:
            self._problem(f"closes </{tag}> while <{self.stack[-1]}> is "
                          f"still open; the markup does not nest")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        if tag == "tr" and self.cells_in_row == 0:
            self.empty_rows.append(self.row_index)
        self.stack.pop()

    def handle_data(self, data):
        if not data.strip():
            return
        if not any(tag in _CELL_ELEMENTS for tag in self.stack):
            shown = " ".join(data.split())
            if len(shown) > 40:
                shown = shown[:40] + "..."
            self._problem(f"has text outside any cell: {shown!r}; every "
                          f"character a transcription carries belongs to "
                          f"a cell")

    def handle_comment(self, data):
        self._problem("carries an HTML comment; a transcription is the "
                      "table and nothing beside it")

    def handle_decl(self, decl):
        self._problem("carries a document declaration; the file is one "
                      "<table> element, not an HTML document")

    def handle_pi(self, data):
        self._problem("carries a processing instruction; the file is one "
                      "<table> element, not an HTML document")

    def unknown_decl(self, data):
        """A marked section, `<![CDATA[...]]>` chief among them.

        The base class drops these without a word, which would make the
        content invisible here and leave the grid a claim about this
        parser's reading rather than about the file. It is worse than
        invisible: `html.parser` ends a marked section at `]]>` and the
        HTML5 bogus-comment rule ends it at the first `>`, so the same
        bytes can give this parser and a consumer's different cells.

        Only `<![CDATA[` reaches here. Every other marked section form is
        routed to the bogus-comment path and refused there instead, so
        the prohibition is complete even though this handler sees one
        shape of it.
        """
        self._problem("carries a marked section (<![...]>); the file is "
                      "one <table> element, and parsers disagree about "
                      "where a marked section ends")

    # -- the rules -----------------------------------------------------

    def _check_element(self, tag, attrs):
        if tag not in _TABLE_ELEMENTS:
            note = _TABLE_ELEMENT_NOTES.get(tag)
            reason = f" ({note})" if note else ""
            self._problem(f"uses <{tag}>, which a transcription may not "
                          f"carry{reason}")
            return
        self._check_position(tag)
        values = self._check_attributes(tag, attrs)
        if tag == "tr":
            self.rows_opened += 1
            self.row_index += 1
            self.column = 0
            self.cells_in_row = 0
        elif tag in _CELL_ELEMENTS:
            # Counted when written, not when placed. A cell outside any
            # row is already reported by _check_position, and saying the
            # file has no cells on top of that would be false of the
            # file and would advise omitting a transcription that has
            # content in it.
            self.cells += 1
            self._place_cell(tag, values)

    def _check_position(self, tag):
        parent = self.stack[-1] if self.stack else None
        if tag == "table":
            if self.seen_table:
                self._problem("holds more than one <table>; a "
                              "transcription is one exhibit, so it is one "
                              "table")
                self.second_table = True
            elif parent is not None:
                self._problem(f"opens <table> inside <{parent}>; the file "
                              f"is a single table at its root")
            self.seen_table = True
        elif tag in _ROW_GROUPS:
            if parent != "table":
                self._problem(f"opens <{tag}> inside "
                              f"<{parent or 'nothing'}>; it belongs "
                              f"directly in <table>")
        elif tag == "tr":
            if parent != "table" and parent not in _ROW_GROUPS:
                self._problem(f"opens <tr> inside <{parent or 'nothing'}>; "
                              f"a row belongs in <table>, <thead> or "
                              f"<tbody>")
        elif tag in _CELL_ELEMENTS:
            if parent != "tr":
                self._problem(f"opens <{tag}> inside "
                              f"<{parent or 'nothing'}>; a cell belongs in "
                              f"<tr>")
        elif tag in _INLINE_ELEMENTS:
            if not any(open_tag in _CELL_ELEMENTS
                       for open_tag in self.stack):
                self._problem(f"uses <{tag}> outside any cell; it marks up "
                              f"a cell's own characters")

    def _check_attributes(self, tag, attrs) -> dict:
        allowed = _TABLE_ATTRIBUTES.get(tag, frozenset())
        values: dict[str, str] = {}
        # Tracked apart from `values`, which holds only what was allowed
        # and valued: a repeat of a refused or bare attribute is still a
        # repeat, and a parser still drops it.
        seen: set[str] = set()
        for name, value in attrs:
            if name in seen:
                self._problem(f"repeats the {name!r} attribute on <{tag}>; "
                              f"a parser keeps the first and drops the "
                              f"rest, so say it once")
                continue
            seen.add(name)
            if name not in allowed:
                if allowed:
                    self._problem(
                        f"gives <{tag}> the attribute {name!r}; it may "
                        f"carry only {', '.join(sorted(allowed))}")
                else:
                    self._problem(f"gives <{tag}> the attribute {name!r}; "
                                  f"it carries no attributes")
                continue
            if value is None:
                # `html.parser` hands a bare attribute (`<td colspan>`)
                # through with None for its value.
                self._problem(f"gives <{tag}> {name} with no value; a "
                              f"bare attribute says nothing, so give it "
                              f"a value or leave it out")
                continue
            values[name] = value
        scope = values.get("scope")
        if "scope" in values and scope not in ("col", "row", "colgroup",
                                               "rowgroup"):
            shown = scope if len(scope) <= 40 else scope[:40] + "..."
            self._problem(f"gives <{tag}> scope={shown!r}; scope is col, "
                          f"row, colgroup or rowgroup")
        return values

    def _span(self, tag, values, name) -> int:
        """One span attribute as a positive integer, defaulting to 1."""
        if name not in values:
            return 1
        raw = values[name]
        # `isdigit` is true of superscript and non-Latin digits, and `int`
        # disagrees with it on both: "\u00b2" raises where this said it
        # would not, and "\u0662" converts to 2 where a renderer reading
        # HTML's ASCII-only rule for a non-negative integer reads 1. Either
        # way the grid this validates is not the grid a consumer lays out.
        # Shown truncated, as text outside a cell is: a value written as
        # five thousand characters is the fault, not something the
        # problem string repeats in full.
        shown = raw if len(raw) <= 40 else raw[:40] + "..."
        if not (raw.isascii() and raw.isdigit()):
            self._problem(f"gives <{tag}> {name}={shown!r}; a span is a "
                          f"positive whole number")
            return 1
        # Judged by digit count before int() sees the value: CPython
        # refuses to convert thousands of digits, and its ValueError
        # quotes advice about raising the reader's limit when the fault
        # is the file. Leading zeros are stripped first, so a legal span
        # padded with them stays legal, and what is converted below is
        # always short enough to convert.
        digits = raw.lstrip("0")
        if len(digits) > len(str(_SPAN_LIMIT)):
            self._problem(f"gives <{tag}> {name}={shown!r}, beyond the "
                          f"{_SPAN_LIMIT} this format allows for one span")
            return 1
        span = int(digits) if digits else 0
        if span < 1:
            self._problem(f"gives <{tag}> {name}={shown!r}; a span is at "
                          f"least 1")
            return 1
        if span > _SPAN_LIMIT:
            self._problem(f"gives <{tag}> {name}={shown!r}, beyond the "
                          f"{_SPAN_LIMIT} this format allows for one span")
            return 1
        return span

    def _place_cell(self, tag, values) -> None:
        colspan = self._span(tag, values, "colspan")
        rowspan = self._span(tag, values, "rowspan")
        if self.row_index < 0:
            return  # a cell outside any row; _check_position said so
        if self.grid_overflowed:
            return
        # Bounded here rather than after the parse, because the positions
        # are written as they are read: one cell carrying both spans at
        # their ceiling claims a million of them, so a file of a few
        # hundred bytes could otherwise cost gigabytes before anything got
        # the chance to say the grid was too large.
        if len(self.occupied) + rowspan * colspan > _GRID_LIMIT:
            self.grid_overflowed = True
            self._problem(f"claims more than {_GRID_LIMIT} cell positions; "
                          f"no printed exhibit is this size, so the spans "
                          f"are wrong rather than the table being large")
            return
        column = self.column
        while (self.row_index, column) in self.occupied:
            column += 1
        clash = None
        for down in range(rowspan):
            for across in range(colspan):
                position = (self.row_index + down, column + across)
                if position in self.occupied and clash is None:
                    clash = position
                self.occupied[position] = True
        if clash is not None:
            self._problem(f"has two cells covering {self._at(*clash)}; a "
                          f"span reaches across a cell that is already "
                          f"there")
        self.column = column + colspan
        self.cells_in_row += 1

    # -- the verdict ---------------------------------------------------

    def finish(self) -> list[str]:
        """Every problem, the ones only the whole file can show included."""
        problems = list(self.problems)
        if self.stack:
            still_open = ", ".join(f"<{tag}>" for tag in self.stack)
            problems.append(f"{self.where} never closes {still_open}")
        if not self.seen_table:
            problems.append(f"{self.where} contains no <table>; a "
                            f"transcription is one table element")
            return problems
        # A grid that overflowed stopped placing cells, so its holes,
        # empty rows and overhangs would describe the truncated parse
        # and not the file. The overflow problem already says what to
        # fix.
        if self.grid_overflowed:
            return problems
        # A second <table> was refused, but its rows and cells were
        # still read into the one grid, so a grid verdict here would
        # describe a table the file does not contain. The refusal
        # carries the fault.
        if self.second_table:
            return problems
        if not self.cells:
            problems.append(f"{self.where} has no cells; an exhibit with "
                            f"nothing to transcribe omits the file")
            return problems
        # Reported up to a handful, then counted, for the reason holes
        # are: past the first few it is the same mangling seen again,
        # and thousands of lines of it would bury the file's other
        # problems rather than adding to them.
        shown_empty = self.empty_rows[:5]
        for row in shown_empty:
            problems.append(f"{self.where} writes no cells in "
                            f"{self._at(row)}; "
                            f"every row carries at least one. A row whose "
                            f"positions are all claimed by spans from "
                            f"above prints nothing, so no exhibit has one, "
                            f"and keeping one to be covered is how a row "
                            f"that went missing gets hidden")
        if len(self.empty_rows) > len(shown_empty):
            problems.append(f"{self.where} writes no cells in "
                            f"{len(self.empty_rows) - len(shown_empty)} "
                            f"further rows")
        problems.extend(self._overhang_problems())
        problems.extend(self._grid_problems())
        return problems

    def _overhang_problems(self) -> list[str]:
        """A rowspan claiming rows the table never writes.

        A reader clips a rowspan to the rows that exist. Taking it at its
        word instead would make the table as tall as the span says, and
        then a row that went missing can be hidden by widening the rowspan
        above it: the grid tiles perfectly and the data is gone. That is
        the worst thing this parser could do, because bumping a span is
        exactly what an author reaches for to silence a hole.
        """
        rows = self.rows_opened
        beyond = sorted({row for row, _ in self.occupied if row >= rows})
        if not beyond:
            return []
        return [f"{self.where} has a rowspan reaching "
                f"{self._at(beyond[0])} when "
                f"the table writes {rows} rows; a span cannot claim rows "
                f"that are not there, so either the span is longer than "
                f"the exhibit prints or a row is missing"]

    def _grid_problems(self) -> list[str]:
        """The positions the occupancy map is left without a cell.

        Reported up to a handful, then counted. Past the first few, a hole
        is nearly always the same dropped cell seen again on later rows,
        and a hundred lines of it would bury the file's other problems
        rather than adding to them.
        """
        rows = self.rows_opened
        within = [position for position in self.occupied
                  if position[0] < rows]
        columns = max((column for _, column in within), default=-1) + 1
        if not rows or not columns:
            return []
        # Bounded before it is walked. Without this a file well under a
        # kilobyte can describe tens of millions of positions, and the walk
        # below would be the whole cost of validating the bundle.
        if rows * columns > _GRID_LIMIT:
            return [f"{self.where} describes a {rows} by {columns} grid, "
                    f"beyond the {_GRID_LIMIT} positions this format "
                    f"allows; no printed exhibit is this size, so the "
                    f"spans are wrong rather than the table being large"]
        if len(within) == rows * columns:
            return []
        # A row already reported empty holes every column spans do not
        # reach, and each of those holes is the empty row said again, one
        # message per column. The empty-row problem carries the fault, so
        # its holes are not repeated; a hole in a row that does have cells
        # is its own fault and stays.
        empty = set(self.empty_rows)
        holes = [(row, column)
                 for row in range(rows)
                 for column in range(columns)
                 if row not in empty
                 and (row, column) not in self.occupied]
        if not holes:
            return []
        shown = holes[:5]
        problems = [
            f"{self.where} leaves {self._at(row, column)} uncovered; the "
            f"cells of a {rows} by {columns} table cover every position "
            f"exactly once, so a hole is a cell that is missing or a span "
            f"that is one too small"
            for row, column in shown]
        if len(holes) > len(shown):
            problems.append(f"{self.where} leaves {len(holes) - len(shown)} "
                            f"further positions uncovered")
        return problems


# ------------------------------------ supplements.json and supplements/

# supplements.json: the paper's identity, and the supplements it carries.
# No schema_version of its own; one bundle declares one version, in the
# manifest, and this file is part of that bundle rather than beside it.
_SUPPLEMENTS_FIELDS = ("id", "supplements")
# One supplement entry. `name` is the directory and the token a consumer
# asks for; `title` is what the paper calls it, which is what a consumer
# chooses by; `exhibits` is declared on exactly the manifest's terms.
_SUPPLEMENT_KEYS = ("name", "title", "exhibits")


def supplement_dirs(root) -> dict[str, Path]:
    """The supplements a bundle carries: name to path, ordered by name.

    The `supplements/` answer to `figure_files`, and answered here for the
    same reason. A supplement's own assets are read by handing its path
    back to `figure_files` and `table_files`, which is why a supplement
    directory is shaped like the bundle around it: the functions that read
    one read the other unchanged.
    """
    supplements_dir = Path(root) / "supplements"
    if not supplements_dir.is_dir():
        return {}
    found = {}
    for child in sorted(supplements_dir.iterdir()):
        if child.name.startswith("."):
            continue  # hidden OS metadata (.DS_Store etc.) is not a supplement
        if child.is_dir():
            found[child.name] = child
    return {name: found[name] for name in sorted(found)}


def _supplement_problems(root: Path, manifest_id):
    """Return (problems, declared) for supplements.json and supplements/.

    declared is {name: labels} when the declaration is structurally sound,
    and None when it is missing or malformed, so the caller skips the
    cross-checks against the directories the way it does for figures/.
    An empty dict is the ordinary case: most papers have no supplement.
    """
    declaration = root / "supplements.json"
    supplements_dir = root / "supplements"
    try:
        if supplements_dir.is_dir():
            _list_directory(supplements_dir)
        present = supplement_dirs(root)
        stray = _stray_supplement_files(root)
    except OSError as exc:
        # An unreadable supplements/ is unusable the way a file at its
        # path is: present becomes None so nothing below claims to know
        # what the directory holds.
        present = None
        stray = [f"supplements/ could not be read: {exc}; nothing in "
                 f"it can be checked"]
    if ((supplements_dir.exists() or supplements_dir.is_symlink())
            and not supplements_dir.is_dir()):
        # The fault figures/ and tables/ report in the same words: the
        # name the format reserves for a directory is held by a file.
        # present becomes None so the declared names are not each also
        # reported as missing the directory this file displaces.
        stray.append(f"supplements exists but is not a directory: "
                     f"{supplements_dir}")
        present = None
    if not declaration.exists() and not declaration.is_symlink():
        if present:
            return ([f"supplements/ holds {', '.join(sorted(present))} but "
                     f"there is no supplements.json; a supplement reaches a "
                     f"consumer through the declaration or not at all"]
                    + stray, None)
        # A supplements/ directory holding no supplement is not a
        # declaration of anything, but a loose file in it is refused on the
        # same terms it would be with a declaration beside it.
        return stray, {}
    raw, unread = _read_utf8(declaration, "supplements.json")
    if unread:
        return [unread] + stray, None
    try:
        data, duplicates = _parse_manifest(raw)
    except json.JSONDecodeError as exc:
        return [_json_problem("supplements.json", raw, exc)] + stray, None
    except ValueError:
        # As in the manifest's parse: JSONDecodeError is caught above,
        # and what reaches here is a value Python refused to build,
        # CPython's integer digit limit being the known case.
        return ["supplements.json holds a number too long to read; no "
                "field of this file carries a number of thousands of "
                "digits"] + stray, None
    except RecursionError:
        return (["supplements.json is nested too deeply to parse"]
                + stray), None
    if not isinstance(data, dict):
        return [f"supplements.json must be a JSON object, got "
                f"{type(data).__name__}"] + stray, None

    problems = _duplicate_key_problems(data, duplicates, "supplements.json")
    problems.extend(stray)
    # As with the manifest, on the same terms. The reports about the
    # directory stand: they are read off the disk, not out of the
    # declaration, so a duplicate says nothing about them either way.
    if duplicates:
        return problems, None
    for key in data:
        if key not in _SUPPLEMENTS_FIELDS:
            problems.append(f"supplements.json has unknown key: {key!r}")
    for name in _SUPPLEMENTS_FIELDS:
        if name not in data:
            problems.append(f"supplements.json is missing required key: "
                            f"{name!r}")

    given_id = data.get("id")
    if "id" in data:
        if not isinstance(given_id, str):
            problems.append(f"supplements.json key 'id' must be a string, "
                            f"got {type(given_id).__name__}")
        elif manifest_id is not None and given_id != manifest_id:
            # A declaration copied between bundles is otherwise undetectable,
            # and it would attach one paper's supplements to another paper.
            problems.append(
                f"supplements.json id {given_id!r} is not the manifest's "
                f"{manifest_id!r}; the supplements belong to the paper the "
                f"bundle is of, and carry its identity rather than one of "
                f"their own")

    # `in`, not `.get`: an explicit null and an absent key both come back
    # None from a lookup, and only one of them has already been reported.
    # Read as a lookup, `"supplements": null` was accepted in silence.
    if "supplements" in data:
        entry_problems, declared = _supplement_entry_problems(
            data["supplements"])
        problems.extend(entry_problems)
    else:
        declared = None
    if declared is None:
        return problems, None

    if present is not None:
        for name in sorted(set(declared) - set(present)):
            problems.append(f"supplements.json declares supplement {name!r} "
                            f"but no directory in supplements/ is named "
                            f"{name}")
        for name in sorted(set(present) - set(declared)):
            problems.append(f"supplements/{name}/ is not declared in "
                            f"supplements.json; a supplement a consumer can "
                            f"read is one the bundle vouches for")
    return problems, declared


def _supplement_entry_problems(value):
    """Return (problems, declared) for the declaration's supplements list.

    declared is {name: labels}, and None when the block is malformed enough
    that cross-checking it against the directories would bury the report
    under derived noise.
    """
    problems: list[str] = []
    if not isinstance(value, list):
        problems.append(f"supplements.json key 'supplements' must be a list "
                        f"of {{name, title, exhibits}} objects, got "
                        f"{type(value).__name__}")
        return problems, None
    if not value:
        # Unlike the manifest's exhibits, an empty list here asserts
        # nothing: a paper with no supplements has no supplements.json,
        # which is the same statement without a file to keep in step.
        problems.append("supplements.json declares no supplements; a paper "
                        "with none omits the file")
        return problems, None
    declared: dict[str, list[str]] = {}
    malformed = False
    for index, entry in enumerate(value):
        where = f"supplements.json supplements[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} must be an object with 'name', "
                            f"'title' and 'exhibits', got "
                            f"{type(entry).__name__}")
            malformed = True
            continue
        for key in sorted(entry):
            if key not in _SUPPLEMENT_KEYS:
                problems.append(f"{where} has unknown key: {key!r} (a "
                                f"supplement carries 'name', 'title' and "
                                f"'exhibits')")
        for key in ("name", "title"):
            if key not in entry:
                problems.append(f"{where} is missing required key: {key!r}")
                malformed = True
            elif not isinstance(entry[key], str):
                problems.append(f"{where} key {key!r} must be a string, got "
                                f"{type(entry[key]).__name__}")
                malformed = True
            elif not entry[key].strip():
                problems.append(f"{where} key {key!r} must be a non-empty "
                                f"string")
                malformed = True
        if "exhibits" not in entry:
            problems.append(f"{where} is missing required key: 'exhibits'")
            malformed = True
            continue
        entry_problems, labels = _exhibit_problems(entry["exhibits"], where)
        problems.extend(entry_problems)
        if entry_problems:
            malformed = True
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        # The sharpest case of the rule's second half: named "..", a
        # supplement would send every check below to the bundle root, where
        # it reads the article's own figures and reports them as this
        # supplement's undeclared files.
        problem = name_problem(
            name, "name", where,
            "it names a supplements/ directory and is the token a consumer "
            "asks for a supplement by")
        if problem:
            problems.append(problem)
            malformed = True
            continue
        if name in declared:
            problems.append(f"{where} name {name!r} is declared more than "
                            f"once; supplement names must be unique within "
                            f"a bundle")
            malformed = True
            continue
        declared[name] = labels
    return problems, (None if malformed else declared)


def _stray_supplement_files(root: Path) -> list[str]:
    """Anything under supplements/ that is not a supplement."""
    supplements_dir = root / "supplements"
    if not supplements_dir.is_dir():
        return []
    return [f"supplements/ contains a file (each supplement is a "
            f"directory): {child.name}"
            for child in sorted(supplements_dir.iterdir())
            if not child.name.startswith(".") and not child.is_dir()]


def _supplement_contents_problems(root: Path, supplements) -> list[str]:
    """Each declared supplement's own text, figures and tables.

    A supplement directory is shaped like the bundle it sits in, so the
    same checks run over it with only a prefix changed: what is a crop,
    what is a transcription, and what binds them to a declaration are
    rules of the format, and a supplement does not get its own version of
    any of them. Only the declaring file differs, which is why the
    problems say supplements.json rather than manifest.json.
    """
    problems: list[str] = []
    try:
        present = supplement_dirs(root)
    except OSError:
        # Already reported where supplements/ was first listed; the walk
        # over its contents has nothing it can read.
        return []
    for name in sorted(supplements):
        if name not in present:
            continue  # already reported, as declared with no directory or
            # as supplements/ itself not being a directory, and walking on
            # would report every one of the supplement's exhibits again
        labels = supplements[name]
        supplement = root / "supplements" / name
        prefix = f"supplements/{name}/"
        try:
            entries = _list_directory(supplement)
        except OSError as exc:
            # As at the bundle root: an unreadable directory would
            # otherwise report its every file as missing.
            problems.append(f"{prefix} could not be read: {exc}; "
                            f"nothing in it can be checked")
            continue
        problems.extend(_miscased_entry_problems(
            entries, _SUPPLEMENT_ENTRIES, prefix.rstrip("/")))
        figure_problems, cropped = _figure_problems(supplement, prefix)
        table_problems, transcribed = _table_problems(supplement, prefix)
        problems.extend(_supplement_text_problems(supplement, prefix))
        problems.extend(figure_problems)
        problems.extend(table_problems)
        if cropped is not None:
            problems.extend(_exhibit_binding_problems(
                labels, cropped, prefix, "supplements.json"))
        if transcribed is not None:
            problems.extend(_table_binding_problems(
                labels, transcribed, prefix, "supplements.json"))
    return problems


def _supplement_text_problems(root: Path, prefix: str) -> list[str]:
    """A supplement's text.md, which unlike the article's is optional.

    A supplement that is nothing but data tables prints no prose, and
    inventing a text.md for it would mean inventing the prose. When one is
    there it is held to what the article's is held to: UTF-8 and not
    empty.
    """
    text_path = root / "text.md"
    if not text_path.exists() and not text_path.is_symlink():
        return []
    text, unread = _read_utf8(text_path, f"{prefix}text.md")
    if unread:
        return [unread]
    if not text.strip():
        return [f"{prefix}text.md is empty; a supplement with no prose "
                f"omits the file rather than supplying an empty one"]
    return []


# ---------------------------- one label, one exhibit, across the bundle

def _label_uniqueness_problems(article_labels, supplements) -> list[str]:
    """One label, one exhibit, across the whole bundle.

    A consumer cites an exhibit by its label alone: the filename stem is
    the citation token, and the map it looks the image up in is flat. So
    an article `table_01` and a supplement `table_01` are two images with
    one name, and whichever the consumer loaded second is the one the
    citation resolves to. Nothing downstream is in a position to notice,
    which is why it is settled here, where every label in the bundle is
    visible at once. Prefixing a supplement's labels with its name is the
    convention that keeps them apart.
    """
    seen = {label: "manifest.json" for label in article_labels}
    problems: list[str] = []
    for name in sorted(supplements):
        for label in supplements[name]:
            if label in seen:
                problems.append(
                    f"supplement {name!r} declares exhibit {label!r}, which "
                    f"{seen[label]} already declares; a label is a "
                    f"consumer's whole citation, so one label is one "
                    f"exhibit across the bundle and its supplements")
                continue
            seen[label] = f"supplement {name!r}"
    return problems
