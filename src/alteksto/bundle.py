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
reimplemented by every reader. `table_files(path)` answers the same
question of `tables/`, the transcriptions an exhibit may carry beside its
crop, and `validate_table_html(source, where)` is what one of those files
has to be. That last one is public because the producing side needs it
too: a tool that renders a transcription refuses the same files this
refuses, rather than forming its own opinion of what a table is.

All of them work on the standard library alone, the table transcriptions
included: their structure is checked with `html.parser`, so enforcing the
format still costs a consumer no dependency. The page tools need pymupdf
and lxml; the contract needs nothing, so a consumer depends on this
package and carries no PDF library it never opens.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

SCHEMA_VERSION = 4

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

# The elements a table transcription may use. The list is short on purpose:
# it is everything needed to say what a printed table says, and nothing that
# carries presentation, scripting or a second document inside the first.
# `caption` is absent deliberately and reported by name below, because a
# caption is carried by text.md and the manifest and a crop that bakes the
# printed caption into the image invites an author to repeat it here.
_TABLE_ELEMENTS = frozenset({
    "table", "thead", "tbody", "tr", "th", "td",
    "sup", "sub", "br", "em", "strong",
})
# Elements a table's cells may contain, and which may nest in each other.
_INLINE_ELEMENTS = frozenset({"sup", "sub", "br", "em", "strong"})
_CELL_ELEMENTS = frozenset({"th", "td"})
_ROW_GROUPS = frozenset({"thead", "tbody"})
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

# supplements.json: the paper's identity, and the supplements it carries.
# No schema_version of its own; one bundle declares one version, in the
# manifest, and this file is part of that bundle rather than beside it.
_SUPPLEMENTS_FIELDS = ("id", "supplements")
# One supplement entry. `name` is the directory and the token a consumer
# asks for; `title` is what the paper calls it, which is what a consumer
# chooses by; `exhibits` is declared on exactly the manifest's terms.
_SUPPLEMENT_KEYS = ("name", "title", "exhibits")

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
    manifest_problems, declared, paper_id = _validate_manifest(root)
    figure_problems, present = _validate_figures(root)
    table_problems, transcribed = _validate_tables(root)
    supplement_problems, supplements = _validate_supplements(root, paper_id)
    problems.extend(manifest_problems)
    problems.extend(_validate_text(root))
    problems.extend(figure_problems)
    problems.extend(table_problems)
    problems.extend(supplement_problems)
    # The cross-checks run only when both sides are themselves well formed:
    # a malformed exhibits block or an unusable figures/ has already been
    # reported, and cross-checking against it would bury that report under
    # derived noise.
    if declared is not None and present is not None:
        problems.extend(_cross_check_exhibits(declared, present))
    if declared is not None and transcribed is not None:
        problems.extend(_cross_check_tables(declared, transcribed))
    if supplements:
        problems.extend(_validate_supplement_contents(root, supplements))
    if declared is not None and supplements:
        problems.extend(_cross_check_label_uniqueness(declared, supplements))
    return problems


def _validate_supplement_contents(root: Path, supplements) -> list[str]:
    """Each declared supplement's own text, figures and tables.

    A supplement directory is shaped like the bundle it sits in, so the
    same checks run over it with only a prefix changed: what is a crop,
    what is a transcription, and what binds them to a declaration are
    rules of the format, and a supplement does not get its own version of
    any of them. Only the declaring file differs, which is why the
    problems say supplements.json rather than manifest.json.
    """
    problems: list[str] = []
    for name in sorted(supplements):
        labels = supplements[name]
        supplement = root / "supplements" / name
        prefix = f"supplements/{name}/"
        figure_problems, present = _validate_figures(supplement, prefix)
        table_problems, transcribed = _validate_tables(supplement, prefix)
        problems.extend(_validate_supplement_text(supplement, prefix))
        problems.extend(figure_problems)
        problems.extend(table_problems)
        if present is not None:
            problems.extend(_cross_check_exhibits(
                labels, present, prefix, "supplements.json"))
        if transcribed is not None:
            problems.extend(_cross_check_tables(
                labels, transcribed, prefix, "supplements.json"))
    return problems


def _validate_manifest(root: Path):
    """Return (problems, declared_labels, id) for manifest.json.

    declared_labels is the exhibits labels when the block is structurally
    sound, and None when it is missing or malformed (so the caller skips
    the cross-checks against figures/). The id comes back so that
    supplements.json can be held to declaring the same one.
    """
    problems: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return ["manifest.json is missing"], None, None
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"manifest.json could not be read as UTF-8: "
                f"{exc}"], None, None
    try:
        data, duplicates = _parse_manifest(raw)
    except json.JSONDecodeError as exc:
        return [f"manifest.json is not valid JSON: {exc}"], None, None
    except RecursionError:
        # The walk below carries its own queue so that depth cannot throw
        # out of it, but the parse runs first and json's scanner recurses in
        # C, at a depth that is a property of the interpreter rather than of
        # this format: 3.11 gives up where later versions keep going. Either
        # way validate_bundle answers with a problem, because it never
        # raises for a malformed bundle, and a manifest this deep is
        # malformed whatever the parser makes of it.
        return ["manifest.json is nested too deeply to parse; a manifest is "
                "a flat object with one list of exhibits in it"], None, None
    if not isinstance(data, dict):
        return [f"manifest.json must be a JSON object, got "
                f"{type(data).__name__}"], None, None

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
        problems.extend(_duplicate_key_problem(where, key) for key in keys)
    for mapping, keys in duplicates:
        if id(mapping) in located:
            continue
        where = f"{declared_in} (in a value another duplicate key replaced)"
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


def _validate_exhibits(value, where="manifest.json"):
    """Validate an exhibits value, the manifest's or a supplement's.

    Returns (problems, labels): the declared labels in declaration order,
    and every problem with the block's shape. An empty list is valid and
    yields ([], []), the author's explicit assertion that the paper
    contains no tables and no figures.
    """
    if not isinstance(value, list):
        return ([f"{where} key 'exhibits' must be a list of "
                 f"{{label, caption}} objects, got "
                 f"{type(value).__name__}"], [])
    problems: list[str] = []
    labels: list[str] = []
    seen: set[str] = set()
    declared_in = where
    for index, entry in enumerate(value):
        where = f"{declared_in} exhibits[{index}]"
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


def _cross_check_exhibits(declared_labels, present_labels, prefix="",
                          declared_in="manifest.json") -> list[str]:
    """Bind a declaration to its figures/. Both directions are hard
    errors; docs/bundle.md says why. `prefix` and `declared_in` name the
    directory and the file that declares it, so a supplement's problems
    say which supplement and point at supplements.json."""
    problems: list[str] = []
    declared = set(declared_labels)
    present = set(present_labels)
    for label in sorted(declared - present):
        problems.append(
            f"{declared_in} declares exhibit {label!r} but there is no "
            f"{prefix}figures/{label}.png")
    for label in sorted(present - declared):
        problems.append(
            f"{prefix}figures/{label}.png is not declared in "
            f"{declared_in} 'exhibits'; every supplied image must be "
            f"declared with its caption")
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
        if child.suffix.lower() == ".html":
            found[child.stem] = child
    return {label: found[label] for label in sorted(found)}


def _validate_tables(root: Path, prefix: str = ""):
    """Return (problems, transcribed_labels) for the tables/ directory.

    transcribed_labels is the label of every transcription table_files
    finds, and None when the directory itself is unusable, so the caller
    skips the cross-check the way it does for figures/.
    """
    tables_dir = root / "tables"
    if not tables_dir.exists():
        return [], []
    if not tables_dir.is_dir():
        return [f"{prefix}tables exists but is not a directory: "
                f"{tables_dir}"], None
    problems: list[str] = []
    for child in sorted(tables_dir.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            problems.append(f"{prefix}tables/ contains a subdirectory "
                            f"(only .html files allowed): {child.name}")
        elif child.suffix.lower() != ".html":
            problems.append(f"{prefix}tables/ contains a non-html file "
                            f"(only .html files allowed): {child.name}")
    transcriptions = table_files(root)
    for label, path in transcriptions.items():
        where = f"{prefix}tables/{label}.html"
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{where} could not be read as UTF-8: {exc}")
            continue
        problems.extend(validate_table_html(source, where))
    return problems, list(transcriptions)


def _cross_check_tables(declared_labels, transcribed_labels, prefix="",
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


def validate_table_html(source: str, where: str) -> list[str]:
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

    # -- element events ------------------------------------------------

    def handle_starttag(self, tag, attrs):
        self._check_element(tag, attrs)
        if tag not in _VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag not in _VOID_ELEMENTS:
            self._problem(f"writes <{tag}/> in the self-closing form; only "
                          f"<br> is written that way, and every other "
                          f"element is opened and closed")
        self._check_element(tag, attrs)

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
            self._place_cell(tag, values)

    def _check_position(self, tag):
        parent = self.stack[-1] if self.stack else None
        if tag == "table":
            if self.seen_table:
                self._problem("holds more than one <table>; a "
                              "transcription is one exhibit, so it is one "
                              "table")
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
        for name, value in attrs:
            if name in values:
                self._problem(f"repeats the {name!r} attribute on <{tag}>; "
                              f"only the last would survive a parse")
                continue
            if name not in allowed:
                if allowed:
                    self._problem(
                        f"gives <{tag}> the attribute {name!r}; it may "
                        f"carry only {', '.join(sorted(allowed))}")
                else:
                    self._problem(f"gives <{tag}> the attribute {name!r}; "
                                  f"it carries no attributes")
                continue
            values[name] = value
        scope = values.get("scope")
        if "scope" in values and scope not in ("col", "row", "colgroup",
                                               "rowgroup"):
            self._problem(f"gives <{tag}> scope={scope!r}; scope is col, "
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
        if raw is None or not (raw.isascii() and raw.isdigit()):
            self._problem(f"gives <{tag}> {name}={raw!r}; a span is a "
                          f"positive whole number")
            return 1
        span = int(raw)
        if span < 1:
            self._problem(f"gives <{tag}> {name}={raw!r}; a span is at "
                          f"least 1")
            return 1
        if span > _SPAN_LIMIT:
            self._problem(f"gives <{tag}> {name}={raw!r}, beyond the "
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
            self._problem(f"has two cells covering row {clash[0]} column "
                          f"{clash[1]}; a span reaches across a cell that "
                          f"is already there")
        self.column = column + colspan
        self.cells += 1
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
        # Before the cell count, because a grid that overflowed stopped
        # placing cells and would otherwise also be reported as empty,
        # which is true of the parse and not of the file.
        if self.grid_overflowed:
            return problems
        if not self.cells:
            problems.append(f"{self.where} has no cells; an exhibit with "
                            f"nothing to transcribe omits the file")
            return problems
        for row in self.empty_rows:
            problems.append(f"{self.where} writes no cells in row {row}; "
                            f"every row carries at least one. A row whose "
                            f"positions are all claimed by spans from "
                            f"above prints nothing, so no exhibit has one, "
                            f"and keeping one to be covered is how a row "
                            f"that went missing gets hidden")
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
        return [f"{self.where} has a rowspan reaching row {beyond[0]} when "
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
        holes = [(row, column)
                 for row in range(rows)
                 for column in range(columns)
                 if (row, column) not in self.occupied]
        if not holes:
            return []
        shown = holes[:5]
        problems = [
            f"{self.where} leaves row {row} column {column} uncovered; the "
            f"cells of a {rows} by {columns} table cover every position "
            f"exactly once, so a hole is a cell that is missing or a span "
            f"that is one too small"
            for row, column in shown]
        if len(holes) > len(shown):
            problems.append(f"{self.where} leaves {len(holes) - len(shown)} "
                            f"further positions uncovered")
        return problems


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


def _validate_supplements(root: Path, manifest_id):
    """Return (problems, declared) for supplements.json and supplements/.

    declared is {name: labels} when the declaration is structurally sound,
    and None when it is missing or malformed, so the caller skips the
    cross-checks against the directories the way it does for figures/.
    An empty dict is the ordinary case: most papers have no supplement.
    """
    declaration = root / "supplements.json"
    present = supplement_dirs(root)
    if not declaration.exists():
        if present:
            return ([f"supplements/ holds {', '.join(sorted(present))} but "
                     f"there is no supplements.json; a supplement reaches a "
                     f"consumer through the declaration or not at all"],
                    None)
        return [], {}
    try:
        raw = declaration.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"supplements.json could not be read as UTF-8: {exc}"], None
    try:
        data, duplicates = _parse_manifest(raw)
    except json.JSONDecodeError as exc:
        return [f"supplements.json is not valid JSON: {exc}"], None
    except RecursionError:
        return ["supplements.json is nested too deeply to parse"], None
    if not isinstance(data, dict):
        return [f"supplements.json must be a JSON object, got "
                f"{type(data).__name__}"], None

    problems = _duplicate_key_problems(data, duplicates, "supplements.json")
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

    declared = _validate_supplement_entries(data.get("supplements"), problems)
    if declared is None:
        return problems, None

    for name in sorted(set(declared) - set(present)):
        problems.append(f"supplements.json declares supplement {name!r} but "
                        f"there is no supplements/{name}/")
    for name in sorted(set(present) - set(declared)):
        problems.append(f"supplements/{name}/ is not declared in "
                        f"supplements.json; a supplement a consumer can "
                        f"read is one the bundle vouches for")
    supplements_dir = root / "supplements"
    if supplements_dir.is_dir():
        for child in sorted(supplements_dir.iterdir()):
            if child.name.startswith(".") or child.is_dir():
                continue
            problems.append(f"supplements/ contains a file (each supplement "
                            f"is a directory): {child.name}")
    return problems, declared


def _validate_supplement_entries(value, problems):
    """Validate the declaration's supplements list; returns {name: labels}.

    None when the block is malformed enough that cross-checking it against
    the directories would bury the report under derived noise.
    """
    if value is None:
        return None
    if not isinstance(value, list):
        problems.append(f"supplements.json key 'supplements' must be a list "
                        f"of {{name, title, exhibits}} objects, got "
                        f"{type(value).__name__}")
        return None
    if not value:
        # Unlike the manifest's exhibits, an empty list here asserts
        # nothing: a paper with no supplements has no supplements.json,
        # which is the same statement without a file to keep in step.
        problems.append("supplements.json declares no supplements; a paper "
                        "with none omits the file")
        return None
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
        entry_problems, labels = _validate_exhibits(entry["exhibits"], where)
        problems.extend(entry_problems)
        if entry_problems:
            malformed = True
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if not _LABEL_PATTERN.match(name):
            problems.append(
                f"{where} name {name!r} must match ^[A-Za-z0-9._-]+$ "
                f"(letters, digits, dot, underscore, dash only): it names a "
                f"supplements/ directory and is the token a consumer asks "
                f"for a supplement by")
            malformed = True
            continue
        if name in declared:
            problems.append(f"{where} name {name!r} is declared more than "
                            f"once; supplement names must be unique within "
                            f"a bundle")
            malformed = True
            continue
        declared[name] = labels
    return None if malformed else declared


def _cross_check_label_uniqueness(article_labels, supplements) -> list[str]:
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


def _validate_supplement_text(root: Path, prefix: str) -> list[str]:
    """A supplement's text.md, which unlike the article's is optional.

    A supplement that is nothing but data tables prints no prose, and
    inventing a text.md for it would mean inventing the prose. When one is
    there it is held to what the article's is held to: UTF-8 and not
    empty.
    """
    text_path = root / "text.md"
    if not text_path.exists():
        return []
    try:
        text = text_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{prefix}text.md could not be read as UTF-8: {exc}"]
    if not text.strip():
        return [f"{prefix}text.md is empty; a supplement with no prose "
                f"omits the file rather than supplying an empty one"]
    return []


def _validate_figures(root: Path, prefix: str = ""):
    """Return (problems, present_labels) for the figures/ directory.

    `prefix` names where the directory sits when it is not the bundle's
    own, so a supplement's problems read `supplements/{name}/figures/`
    and point at the file an author has to open.

    present_labels is the label of every crop figure_files finds, and None
    when the directory itself is unusable (so the caller skips the
    cross-checks). What is a crop is that function's answer, not a second
    reading of the directory; what is left over is what is reported here.
    """
    figures_dir = root / "figures"
    if not figures_dir.exists():
        return [], []
    if not figures_dir.is_dir():
        return [f"{prefix}figures exists but is not a directory: "
                f"{figures_dir}"], None
    problems: list[str] = []
    for child in sorted(figures_dir.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            problems.append(f"{prefix}figures/ contains a subdirectory "
                            f"(only .png files allowed): {child.name}")
        elif child.suffix.lower() != ".png":
            problems.append(f"{prefix}figures/ contains a non-png file "
                            f"(only .png files allowed): {child.name}")
    return problems, list(figure_files(root))
