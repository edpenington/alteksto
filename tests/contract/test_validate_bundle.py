"""Tests for the bundle validator against docs/bundle.md.

Every fixture is an invented bundle built in tmp_path. The helper builds
a minimal valid bundle; each test then breaks exactly one rule and
asserts the validator names it.
"""

import ast
import json
import os
import signal
import sys
import time
import tomllib
from pathlib import Path

import pytest

from alteksto.bundle import (SCHEMA_VERSION, _walk_objects, figure_files,
                             name_problem, supplement_dirs, table_files,
                             bundle_problems, table_html_problems)
from tests.support import REPO_ROOT, load_script


PNG_STUB = b"\x89PNG\r\n\x1a\n invented bytes; no check reads pixels"

# A correct transcription: a header row and two body rows, tiling 3 by 2.
# Tests that need a wrong one write it out beside the right one, so what
# the validator is being asked about is on the page.
TABLE_STUB = ("<table><thead><tr><th>Season</th><th>Count</th></tr></thead>"
              "<tbody><tr><td>April</td><td>4.8</td></tr>"
              "<tr><td>July</td><td>2.6</td></tr></tbody></table>")


def make_bundle(root, *, manifest=None, text="# An invented paper\n\nBody.",
                figures=(), tables=None):
    """A bundle directory; defaults form a minimal valid bundle.

    `tables` is a label -> markup map written under tables/. It is not
    derived from `figures` because a transcription is optional exhibit by
    exhibit, and most of what these tests ask about is what happens when
    the two directories disagree.
    """
    if manifest is None:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "id": "inv-01",
            "title": "An invented paper",
            "exhibits": [{"label": label, "caption": f"Caption for {label}"}
                         for label in figures],
        }
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(manifest),
                                        encoding="utf-8")
    if text is not None:
        (root / "text.md").write_text(text, encoding="utf-8")
    if figures:
        (root / "figures").mkdir(exist_ok=True)
        for label in figures:
            (root / "figures" / f"{label}.png").write_bytes(PNG_STUB)
    if tables:
        (root / "tables").mkdir(exist_ok=True)
        for label, markup in tables.items():
            (root / "tables" / f"{label}.html").write_text(markup,
                                                          encoding="utf-8")
    return root


def bundle_problems_must_return(bundle, seconds=10):
    """bundle_problems, failed rather than hung if it blocks.

    The contract is that it always returns. A regression that blocks
    (reading a FIFO, say) would otherwise hang the whole suite, so the
    tests that probe blocking shapes call it through this deadline.
    """
    if not hasattr(signal, "alarm"):
        return bundle_problems(bundle)

    def expired(signum, frame):
        raise AssertionError("bundle_problems did not return")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        return bundle_problems(bundle)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def test_a_minimal_bundle_is_valid(tmp_path):
    assert bundle_problems(make_bundle(tmp_path / "b")) == []


def test_a_bundle_with_exhibits_is_valid(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01", "figure_01"))
    assert bundle_problems(bundle) == []


def test_a_missing_directory_is_one_problem(tmp_path):
    problems = bundle_problems(tmp_path / "absent")
    assert len(problems) == 1 and "does not exist" in problems[0]


def test_missing_manifest_and_text_both_reported(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    problems = bundle_problems(root)
    assert any("manifest.json is missing" in p for p in problems)
    assert any("text.md is missing" in p for p in problems)


@pytest.mark.parametrize("held,names", [
    ("MANIFEST.JSON", "manifest.json"), ("Text.md", "text.md"),
    ("Figures", "figures"), ("Tables", "tables"),
    ("Supplements.json", "supplements.json"), ("SUPPLEMENTS", "supplements"),
])
def test_a_contract_entry_in_the_wrong_case_is_refused(tmp_path, held, names):
    """The trap this format is otherwise built to walk into.

    macOS is case-insensitive by default, so a bundle holding `Figures/`
    answers to `figures/` on the machine that produced it and holds
    nothing a case-sensitive consumer can find. That is the argument the
    exact `.png` suffix rule already rests on, one level up, and it is
    worse here: the crop rule at least fails on the author's own
    machine, while this one is invisible until the bundle travels.

    The rename is done on a bundle that is otherwise valid, so the only
    thing under test is the name.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB})
    add_supplement(bundle, "appendix_a")
    declare_supplements(bundle, [entry("appendix_a")])
    assert bundle_problems(bundle) == []
    (bundle / names).rename(bundle / held)
    problems = bundle_problems(bundle)
    assert any(repr(held) in p and repr(names) in p
               for p in problems), problems


def test_a_supplement_entry_in_the_wrong_case_is_refused(tmp_path):
    """A supplement is bundle-shaped, so it carries the same trap."""
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    add_supplement(bundle, "appendix_a")
    declare_supplements(bundle, [entry("appendix_a")])
    assert bundle_problems(bundle) == []
    supplement = bundle / "supplements" / "appendix_a"
    (supplement / "text.md").rename(supplement / "Text.md")
    problems = bundle_problems(bundle)
    assert any("supplements/appendix_a holds 'Text.md'" in p
               for p in problems), problems


def test_a_name_that_is_nobody_s_business_is_left_alone(tmp_path):
    """Only a contract name in the wrong case is refused.

    A bundle may carry its own paperwork beside the six entries, so a
    file whose name merely resembles nothing in the contract is not the
    format's affair however it is capitalised.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "Notes.md").write_text("mine\n", encoding="utf-8")
    (bundle / "README").write_text("mine\n", encoding="utf-8")
    assert bundle_problems(bundle) == []


@pytest.mark.skipif(os.name != "posix", reason="needs POSIX permissions")
@pytest.mark.parametrize("mode", [0, 0o444])
def test_an_unreadable_bundle_root_says_so_and_nothing_else(tmp_path, mode):
    """Nothing in it could be read, and every check knows nothing.

    An unreadable root used to report manifest.json and text.md as
    missing, which was false: both were there. Worse, iterdir raised
    PermissionError out of bundle_problems, which promises to raise for
    no input. The one true statement is that the directory could not be
    read, and anything beside it would be a guess in the voice of a
    fact. 0o444 is the sharper half: the listing works, but nothing
    listed can be reached, so a walk that stopped at the listing would
    still report every file as missing.
    """
    if os.geteuid() == 0:
        pytest.skip("root reads through permission bits")
    bundle = make_bundle(tmp_path / "b")
    os.chmod(bundle, mode)
    try:
        problems = bundle_problems_must_return(bundle)
    finally:
        os.chmod(bundle, 0o755)
    assert len(problems) == 1, problems
    assert "bundle directory could not be read" in problems[0]
    assert "missing" not in problems[0]


@pytest.mark.skipif(os.name != "posix", reason="needs symlinks")
def test_a_dangling_symlink_is_not_reported_as_missing(tmp_path):
    """'manifest.json is missing' is false of a link ls shows.

    The truth is that the link leads nowhere and holds nothing to read,
    and that is what the person has to fix: remove the link or restore
    its target, not create a file beside it.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "manifest.json").unlink()
    (bundle / "manifest.json").symlink_to(bundle / "nowhere")
    problems = bundle_problems(bundle)
    assert any("manifest.json is not a regular file" in p
               for p in problems), problems
    assert not any("manifest.json is missing" in p for p in problems)


def test_unknown_manifest_key_rejected(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["provenance"] = "not allowed"
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("unknown key: 'provenance'" in p
               for p in bundle_problems(bundle))


def test_schema_version_must_be_the_format_s_own_and_not_bool(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["schema_version"] = SCHEMA_VERSION - 1
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(f"schema_version must be {SCHEMA_VERSION}" in p
               for p in bundle_problems(bundle))
    manifest["schema_version"] = True
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("must be an integer" in p for p in bundle_problems(bundle))


@pytest.mark.parametrize("bad_id, expected", [
    ("has space", "must match"),
    ("a/b", "must match"),
    ("..", "at least one letter or digit"),
    ("", "non-empty"),
])
def test_bad_ids_are_rejected(tmp_path, bad_id, expected):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["id"] = bad_id
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(expected in p for p in bundle_problems(bundle))


@pytest.mark.parametrize("key", ["schema_version", "id", "title", "exhibits"])
def test_every_required_manifest_key_is_required(tmp_path, key):
    """Each of the four, named as missing rather than defaulted.

    A consumer reads these straight off the manifest once the verdict is in
    (`manifest["id"]` names its output directory, `manifest["exhibits"]` is
    the declaration it walks), so a key this stops requiring does not become
    an absent value downstream: it becomes a crash after the verdict said the
    bundle was fine.
    """
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    del manifest[key]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(f"missing required key: '{key}'" in p
               for p in bundle_problems(bundle))


def test_an_exhibit_entry_needs_a_label(tmp_path):
    # The other key a consumer indexes directly, one entry down.
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"caption": "Table 1."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("missing required key: 'label'" in p
               for p in bundle_problems(bundle))


@pytest.mark.parametrize("key, value, expected", [
    ("doi", 10.5555, "must be a string"),
    ("summary", ["not", "a", "string"], "must be a string"),
    ("summary", "   ", "non-empty"),
    ("title", "  ", "non-empty"),
    ("id", "", "non-empty"),
])
def test_a_present_value_is_still_typed(tmp_path, key, value, expected):
    # Optional does not mean unchecked. A consumer that reads `doi` as a
    # string, or shows `summary` to a model, gets a number or a list here
    # unless this holds.
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest[key] = value
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(key in p and expected in p for p in bundle_problems(bundle))


def test_an_exhibit_label_is_filename_and_citation_safe(tmp_path):
    """The label rule, checked where the cross-check cannot mask it.

    The crop is on disk under the offending name, so the declaration and the
    directory agree and the only thing left to object to is the label itself.
    It is a `figures/*.png` stem and the token a consumer cites, so a space,
    a separator or a pipe in it breaks both uses.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "figures").mkdir(exist_ok=True)
    (bundle / "figures" / "Table 1 | fleet.png").write_bytes(PNG_STUB)
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "Table 1 | fleet", "caption": "T1."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    problems = bundle_problems(bundle)
    assert any("must match" in p and "Table 1 | fleet" in p for p in problems)


def test_an_exhibit_label_of_punctuation_alone_is_rejected(tmp_path):
    """The half of the rule the label check skipped from the first commit.

    A label is not a directory, so it cannot traverse the way an id can:
    it always takes a suffix and stays a leaf. But it is the token text.md
    cites and the token a consumer asks for an exhibit by, and "-" is not
    a name. The crop sits on disk under the offending stem, so the
    cross-check has nothing to say and the label is all that is left to
    object to.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "figures").mkdir(exist_ok=True)
    (bundle / "figures" / "-.png").write_bytes(PNG_STUB)
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "-", "caption": "T1."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    problems = bundle_problems(bundle)
    assert any("at least one letter or digit" in p for p in problems), problems


@pytest.mark.parametrize("value, legal", [
    ("table_01", True), ("demo.001", True), ("a-b", True), ("_x1", True),
    ("1234", True), ("fig.01", True),
    (".", False), ("..", False), ("-", False), ("___", False),
    ("has space", False), ("a/b", False), ("fig_01\n", False),
    ("", False), (7, False), (".hidden01", False),
])
def test_the_name_rule_answers_for_every_shape_of_name(value, legal):
    """Both halves and both sides of each, on one call.

    `name_problem` is what the producing side asks before it stages a
    name and what the validator reports afterwards, so these are the
    same answers in both places by construction rather than by two
    functions agreeing.
    """
    assert (name_problem(value) is None) is legal, name_problem(value)


def test_the_name_rule_is_written_in_exactly_one_place():
    """Not the predicate: the pattern and the words it is reported in.

    The gap this closed existed because three sites in the validator
    each matched the pattern themselves and one matched only half of it,
    and a fourth copy sat in engines/walk/tools/stage.py, under a
    docstring promising the rule was imported rather than restated. So
    the check is on the character class itself, wherever it appears in
    Python this repository ships: one function holds it, and a fifth
    copy fails here rather than being noticed by a reviewer.

    docs/bundle.md states it too, and must: it is the specification, and
    this module is only its enforcement.
    """
    module = REPO_ROOT / "src" / "alteksto" / "bundle.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    holders = {node.name for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef)
               and any(isinstance(inner, ast.Constant)
                       and isinstance(inner.value, str)
                       and "A-Za-z0-9" in inner.value
                       for inner in ast.walk(node))}
    assert holders == {"name_problem"}, holders

    shipped = [path for root in ("src", "engines", "tools")
               for path in sorted((REPO_ROOT / root).rglob("*.py"))]
    restating = [path.relative_to(REPO_ROOT) for path in shipped
                 if "A-Za-z0-9" in path.read_text(encoding="utf-8")]
    assert restating == [module.relative_to(REPO_ROOT)], restating


def test_a_dotted_id_with_an_alphanumeric_is_allowed(tmp_path):
    # The positive half of the id rule: the character class admits dots, and
    # only an id with no letter or digit at all is refused.
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["id"] = "demo.001"
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert bundle_problems(bundle) == []


def test_a_dot_leading_label_is_refused_with_a_true_message(tmp_path):
    """A dot-leading label declares a file every walk skips.

    With figures/.hidden01.png genuinely on disk, the validator used to
    say there was no such file: every directory walk skips dot-leading
    entries as OS metadata, so the crop was invisible, the message was
    false, and following it could not fix the bundle. The name rule now
    refuses the leading dot itself, so the person is told the real rule
    and the walks' dotfile skip can no longer hide a legitimate name.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "figures").mkdir()
    (bundle / "figures" / ".hidden01.png").write_bytes(PNG_STUB)
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": ".hidden01", "caption": "H."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    problems = bundle_problems(bundle)
    assert any("must not start with a dot" in p for p in problems), problems
    assert not any("there is no figures/.hidden01.png" in p
                   for p in problems), problems


def test_a_dot_leading_id_is_refused(tmp_path):
    # '.hidden' matched the pattern and holds a letter, so it passed
    # clean, but as a directory name it is hidden OS metadata to every
    # reader. The rule that refuses a dot-leading label refuses it here
    # too, because the id becomes a path component the same way.
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["id"] = ".hidden"
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("must not start with a dot" in p
               for p in bundle_problems(bundle))


@pytest.mark.parametrize("entry, expected", [
    ({"label": "table_01", "caption": "  "}, "'caption' must be a non-empty"),
    ({"label": "  ", "caption": "T1."}, "'label' must be a non-empty"),
    ({"label": 1, "caption": "T1."}, "'label' must be a string"),
    ({"label": "table_01", "caption": ["T1."]}, "'caption' must be a string"),
])
def test_an_exhibit_entry_carries_non_empty_strings(tmp_path, entry, expected):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [entry]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(expected in p for p in bundle_problems(bundle))


@pytest.mark.parametrize("exhibits, expected", [
    ({"table_01": "Table 1."}, "'exhibits' must be a list"),
    (["table_01"], "exhibits[0] must be an object"),
])
def test_exhibits_is_a_list_of_objects(tmp_path, exhibits, expected):
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = exhibits
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any(expected in p for p in bundle_problems(bundle))


@pytest.mark.parametrize("exhibits", [
    {"table_01": "Table 1."},
    ["table_01"],
])
def test_a_shape_problem_states_the_whole_entry_contract(tmp_path, exhibits):
    """The shape messages state the contract with 'notes' in it. A message
    claiming an entry is exactly label and caption would send an author to
    delete a legitimate key the code below accepts."""
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = exhibits
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("optional non-empty 'notes'" in p
               for p in bundle_problems(bundle))


def test_a_malformed_exhibits_block_is_not_cross_checked(tmp_path):
    # The shape problem is the thing to fix. Cross-checking a declaration
    # that does not parse against the directory would bury it under derived
    # noise about crops nobody declared.
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "table_01"}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    problems = bundle_problems(bundle)
    assert any("missing required key: 'caption'" in p for p in problems)
    assert not any("not declared" in p for p in problems)


def test_a_byte_order_mark_is_named_not_prescribed_around(tmp_path):
    """The one JSON fault whose own message teaches the way round it.

    json says "Unexpected UTF-8 BOM (decode using utf-8-sig)", which is
    advice for someone writing a reader, and the wrong way round for
    someone holding a bundle: the fault is the file. The mark is named
    here instead, and no codec is.
    """
    bundle = make_bundle(tmp_path / "b")
    raw = (bundle / "manifest.json").read_text(encoding="utf-8")
    (bundle / "manifest.json").write_bytes(
        b"\xef\xbb\xbf" + raw.encode("utf-8"))
    problems = bundle_problems(bundle)
    assert len(problems) == 1, problems
    assert "byte order mark" in problems[0]
    assert "utf-8-sig" not in problems[0]
    assert "decode using" not in problems[0]


@pytest.mark.parametrize("raw, expected", [
    ("{not json", "not valid JSON"),
    ('["a", "list"]', "must be a JSON object"),
])
def test_a_manifest_that_is_not_an_object_is_one_problem(tmp_path, raw,
                                                         expected):
    # Reported, not raised: a consumer takes the verdict and reads the
    # manifest afterwards, so a file that cannot be read as an object has to
    # come back as a problem rather than as an exception out of the parse.
    bundle = make_bundle(tmp_path / "b")
    (bundle / "manifest.json").write_text(raw, encoding="utf-8")
    problems = bundle_problems(bundle)
    assert len(problems) == 1 and expected in problems[0]


def test_a_number_of_thousands_of_digits_is_a_problem_not_a_crash(tmp_path):
    """The one parse fault that escaped both guards, at both sites.

    CPython refuses to build an int past its digit limit with a plain
    ValueError, which is neither a JSONDecodeError nor a RecursionError,
    so it raised out of bundle_problems and cracked the CLI open. The
    file is malformed in every way that matters, so it comes back as a
    problem like the rest.
    """
    digits = "1" * 5000
    bundle = make_bundle(tmp_path / "b")
    (bundle / "manifest.json").write_text(
        f'{{"schema_version": {digits}}}', encoding="utf-8")
    problems = bundle_problems(bundle)
    assert len(problems) == 1, problems
    assert "manifest.json holds a number too long to read" in problems[0]

    bundle2 = make_bundle(tmp_path / "b2")
    (bundle2 / "supplements.json").write_text(
        f'{{"id": {digits}}}', encoding="utf-8")
    problems = bundle_problems(bundle2)
    assert any("supplements.json holds a number too long to read" in p
               for p in problems), problems


def test_a_duplicated_manifest_key_is_rejected(tmp_path):
    """The manifest is written as text, because `json.dumps` cannot
    produce the file this rule is about: a duplicate key exists only in
    the bytes, and a Python dict has already lost it.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "manifest.json").write_text(
        f'{{"schema_version": {SCHEMA_VERSION}, '
        f'"id": "inv-01", "title": "An invented paper", '
        '"id": "inv-02", "exhibits": []}', encoding="utf-8")
    problems = bundle_problems(bundle)
    assert len(problems) == 1
    assert "manifest.json has a duplicate key: 'id'" in problems[0]


def test_a_duplicated_key_inside_an_exhibit_is_located(tmp_path):
    # The hook runs on every object in the document, not just the root, and
    # the problem says which entry, as every other exhibit problem does.
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "manifest.json").write_text(
        f'{{"schema_version": {SCHEMA_VERSION}, '
        f'"id": "inv-01", "title": "An invented paper", '
        '"exhibits": [{"label": "table_01", "caption": "Herons at dawn", '
        '"caption": "Herons at dusk"}]}', encoding="utf-8")
    problems = bundle_problems(bundle)
    assert len(problems) == 1
    assert ("manifest.json exhibits[0] has a duplicate key: 'caption'"
            in problems[0])


def test_every_duplicate_is_named_and_nothing_else_is(tmp_path):
    """A duplicate hides no other duplicate, and ends the report there.

    Every duplicate is named because the parser finishes an exhibit entry
    before the object holding it, so reporting the first one it finds would
    name the caption and never reach the id, the key this rule exists for.
    The id is written three times to pin that a key is one problem however
    often it repeats.

    Nothing else is named, because nothing else can be said honestly. A
    check on a duplicated key reads whichever value the parse kept, and the
    unknown key here would be reported beside a schema_version complaint
    about a number the file may also state correctly. The author has to
    open the file whatever it says; it says the one thing that is true.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "manifest.json").write_text(
        f'{{"schema_version": {SCHEMA_VERSION}, '
        f'"id": "inv-01", "id": "inv-02", '
        '"id": "inv-03", "warden": "not a manifest key", '
        '"exhibits": [{"label": "table_01", "caption": "Herons at dawn", '
        '"caption": "Herons at dusk"}]}', encoding="utf-8")
    problems = bundle_problems(bundle)
    named = [p for p in problems if "duplicate key" in p]
    assert len(named) == 2
    assert "manifest.json has a duplicate key: 'id'" in named[0]
    assert ("manifest.json exhibits[0] has a duplicate key: 'caption'"
            in named[1])
    assert problems == named
    assert not any("unknown key: 'warden'" in p for p in problems)
    assert not any("missing required key: 'title'" in p for p in problems)


def test_a_repeated_key_is_not_confused_with_a_repeated_value(tmp_path):
    # A guard against a false positive, so it passes with or without the
    # rule: two exhibits carrying the same caption text is ordinary (two
    # panels of one figure often print alike), and the rule is about one
    # object carrying one key twice.
    bundle = make_bundle(tmp_path / "b", figures=("table_01", "table_02"))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [
        {"label": "table_01", "caption": "Heron counts by reed bed"},
        {"label": "table_02", "caption": "Heron counts by reed bed"},
    ]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert bundle_problems(bundle) == []


def _deeply_nested_manifest(root, depth):
    bundle = make_bundle(root)
    (bundle / "manifest.json").write_text(
        f'{{"schema_version": {SCHEMA_VERSION}, '
        f'"id": "inv-01", "title": "An invented paper", '
        '"id": "inv-02", "exhibits": [], "warden": '
        + "[" * depth + "]" * depth + '}',
        encoding="utf-8")
    return bundle


def test_the_walk_carries_its_own_queue_rather_than_the_stack():
    """Depth costs the walk nothing, which is why it has a queue.

    Asked of `_walk_objects` directly and on a structure built in Python
    rather than parsed, because through `bundle_problems` the question
    cannot be asked at all: json's scanner is itself bounded by the
    recursion limit on some supported interpreters, so a manifest deeper
    than that limit never reaches the walk, and raising the limit to get
    it there would raise it for a recursive walk too and prove nothing.
    """
    deep = []
    cursor = deep
    for _ in range(5000):
        nested = []
        cursor.append(nested)
        cursor = nested
    assert sys.getrecursionlimit() < 5000
    found = list(_walk_objects({"warden": deep}, "manifest.json"))
    assert found and found[0][0] == "manifest.json"


def test_a_duplicate_is_located_inside_a_nested_manifest(tmp_path):
    bundle = _deeply_nested_manifest(tmp_path / "b", 50)
    problems = bundle_problems(bundle)
    assert any("duplicate key: 'id'" in p for p in problems)


def test_a_manifest_too_deep_for_the_parser_reports_rather_than_raises(
        tmp_path):
    # Deeper than json's own scanner tolerates on some supported
    # interpreters, and how deep that is belongs to the interpreter rather
    # than to this format. So the assertion is the one that holds on all of
    # them: problems come back, and nothing is raised. Which problems
    # depends on whether the parse finished, and the duplicate can only be
    # named when it did.
    bundle = _deeply_nested_manifest(tmp_path / "b", 5000)
    problems = bundle_problems(bundle)
    assert problems
    assert any("duplicate key: 'id'" in p or "nested too deeply" in p
               for p in problems), problems


def test_exhibit_entries_take_label_caption_and_optional_notes(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "table_01",
                             "caption": "Caption",
                             "notes": "Invented footnote: counts exclude "
                                      "the pilot pond."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert bundle_problems(bundle) == []
    manifest["exhibits"] = [{"label": "table_01",
                             "caption": "Caption",
                             "footnote": "not allowed"}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("unknown key: 'footnote'" in p
               for p in bundle_problems(bundle))
    manifest["exhibits"] = [{"label": "table_01"}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("missing required key: 'caption'" in p
               for p in bundle_problems(bundle))


def test_empty_notes_is_a_mistake_not_a_signal(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "table_01", "caption": "Caption",
                             "notes": "   "}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("'notes' must be a non-empty string" in p
               for p in bundle_problems(bundle))


def test_duplicate_labels_are_rejected(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [
        {"label": "table_01", "caption": "First"},
        {"label": "table_01", "caption": "Second"},
    ]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("more than once" in p for p in bundle_problems(bundle))


def test_empty_text_md_is_invalid(tmp_path):
    bundle = make_bundle(tmp_path / "b", text="   \n")
    assert any("text.md is empty" in p for p in bundle_problems(bundle))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
def test_a_fifo_at_text_md_cannot_block_validation(tmp_path):
    """Opening a FIFO for reading blocks until something writes to it.

    A validator that read it would never return, and not returning is
    worse than raising: nothing downstream ever gets a verdict. So the
    shape of every path is checked before any open, and a FIFO is
    refused unopened.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "text.md").unlink()
    os.mkfifo(bundle / "text.md")
    problems = bundle_problems_must_return(bundle)
    assert any("text.md is not a regular file" in p
               for p in problems), problems


def test_a_directory_at_text_md_is_a_shape_fault_not_an_encoding_one(
        tmp_path):
    """A shape fault says the shape.

    This used to report 'could not be read as UTF-8: [Errno 21] Is a
    directory', which sends a person hunting an encoding fault in a
    thing that has no bytes to decode. What they have to change is the
    shape: replace the directory with a file.
    """
    bundle = make_bundle(tmp_path / "b")
    (bundle / "text.md").unlink()
    (bundle / "text.md").mkdir()
    problems = bundle_problems(bundle)
    assert any("text.md is a directory" in p for p in problems), problems
    assert not any("UTF-8" in p for p in problems), problems


def test_cross_check_both_directions(tmp_path):
    # Declared but no PNG.
    bundle = make_bundle(tmp_path / "declared", figures=("table_01",))
    (bundle / "figures" / "table_01.png").unlink()
    assert any("no file in figures/ is named table_01.png" in p
               for p in bundle_problems(bundle))
    # PNG but not declared.
    bundle2 = make_bundle(tmp_path / "stray")
    (bundle2 / "figures").mkdir()
    (bundle2 / "figures" / "figure_09.png").write_bytes(PNG_STUB)
    assert any("figure_09.png is not declared" in p
               for p in bundle_problems(bundle2))


def test_a_crop_whose_stem_can_never_be_a_label_says_so(tmp_path):
    """The fault is the file's name, so the problem is about the name.

    Read only as an undeclared crop, this earns "every supplied image
    must be declared with its caption", and an author who follows that
    advice writes a label the name rule then refuses. One fault, said
    once, in the words that lead to the fix.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "figures" / "tabl\u00e9_01.png").write_bytes(PNG_STUB)
    problems = bundle_problems(bundle)
    assert len(problems) == 1, problems
    assert "stem" in problems[0] and "^[A-Za-z0-9._-]+$" in problems[0]
    assert "must be declared with its caption" not in problems[0]


def test_figures_rejects_non_png_and_subdirs(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "figures" / "notes.txt").write_text("stray")
    (bundle / "figures" / "sub").mkdir()
    problems = bundle_problems(bundle)
    assert any("non-png" in p for p in problems)
    assert any("subdirectory" in p for p in problems)


def test_a_png_suffix_must_be_exactly_lowercase(tmp_path):
    """The path a consumer is promised is literally figures/<label>.png.

    Read case-insensitively, a .PNG crop validated clean while the
    promised path did not exist on a case-sensitive filesystem, and
    x.png beside x.PNG merged into one label with no report at all. So
    the suffix is exact, and a .PNG file is named as the thing to
    rename.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    crop = bundle / "figures" / "table_01.png"
    data = crop.read_bytes()
    crop.unlink()
    (bundle / "figures" / "table_01.PNG").write_bytes(data)
    problems = bundle_problems(bundle)
    assert any("table_01.PNG" in p and "lowercase" in p
               for p in problems), problems
    assert any("no file in figures/ is named table_01.png" in p
               for p in problems), problems


def test_a_crop_beside_its_uppercase_twin_is_not_a_silent_merge(tmp_path):
    """The worst outcome of the case-insensitive read, closed.

    Two files held one label and nothing was reported, so whichever a
    consumer's own enumeration preferred won. Now the .png file is the
    crop and the .PNG file is refused by name. Only a case-sensitive
    filesystem can hold the two files at once, so anywhere else the
    fault cannot be built and the test skips.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "figures" / "table_01.PNG").write_bytes(PNG_STUB)
    names = {child.name for child in (bundle / "figures").iterdir()}
    if "table_01.PNG" not in names or "table_01.png" not in names:
        pytest.skip("needs a case-sensitive filesystem")
    problems = bundle_problems(bundle)
    assert any("table_01.PNG" in p for p in problems), problems
    assert list(figure_files(bundle)) == ["table_01"]


def test_a_crop_that_is_not_a_png_is_refused(tmp_path):
    """Eight bytes and a size, never a pixel.

    A zero-byte file and a GIF renamed .png both passed with zero
    problems, and the module docstring promises a consumer accepts what
    passes here. The two faults read differently because they are fixed
    differently: an empty file was never exported at all, and wrong
    bytes were exported as the wrong format.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01", "figure_01"))
    (bundle / "figures" / "table_01.png").write_bytes(b"")
    (bundle / "figures" / "figure_01.png").write_bytes(b"GIF89a junk")
    problems = bundle_problems(bundle)
    assert any("figures/table_01.png is empty" in p
               for p in problems), problems
    assert any("figures/figure_01.png does not start with the PNG "
               "signature" in p for p in problems), problems


@pytest.mark.skipif(os.name != "posix", reason="needs symlinks")
def test_a_crop_that_is_not_a_regular_file_is_refused(tmp_path):
    """A dangling link named .png held a label and passed clean.

    A FIFO in the same place would have blocked the read forever.
    Neither is a file a consumer can open, so both are refused by shape
    before any byte is read.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    crop = bundle / "figures" / "table_01.png"
    crop.unlink()
    crop.symlink_to(bundle / "nowhere")
    problems = bundle_problems(bundle)
    assert any("figures/table_01.png is not a regular file" in p
               for p in problems), problems


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
def test_a_fifo_named_as_a_crop_cannot_block_validation(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    crop = bundle / "figures" / "table_01.png"
    crop.unlink()
    os.mkfifo(crop)
    problems = bundle_problems_must_return(bundle)
    assert any("figures/table_01.png is not a regular file" in p
               for p in problems), problems


@pytest.mark.skipif(os.name != "posix", reason="needs POSIX permissions")
def test_an_unreadable_figures_directory_is_reported_not_raised(tmp_path):
    """An unreadable directory is not a malformed bundle, but it is
    still answered with a problem: iterdir used to raise
    PermissionError out of bundle_problems, which promises to raise for
    no input. And nothing is claimed about what the directory holds,
    because nothing could be read to claim it."""
    if os.geteuid() == 0:
        pytest.skip("root reads through permission bits")
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    os.chmod(bundle / "figures", 0)
    try:
        problems = bundle_problems_must_return(bundle)
    finally:
        os.chmod(bundle / "figures", 0o755)
    assert any("figures/ could not be read" in p for p in problems), problems
    assert not any("no figures/table_01.png" in p for p in problems), problems


def test_hidden_files_in_figures_are_ignored(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "figures" / ".DS_Store").write_bytes(b"junk")
    assert bundle_problems(bundle) == []


def test_extra_files_beside_the_contract_are_ignored(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    (bundle / "paperwork.txt").write_text("allowed")
    assert bundle_problems(bundle) == []


class TestFigureFiles:
    """The enumeration a consumer reads instead of writing its own."""

    def test_it_answers_label_to_path_in_label_order(self, tmp_path):
        bundle = make_bundle(tmp_path / "b",
                             figures=("table_02", "fig_01", "table_01"))
        found = figure_files(bundle)
        assert list(found) == ["fig_01", "table_01", "table_02"]
        assert found["fig_01"] == bundle / "figures" / "fig_01.png"

    def test_it_skips_what_validation_skips(self, tmp_path):
        # Hidden OS metadata is not an asset, and the two readings agree
        # about that: a consumer that enumerated it would carry a label no
        # check ever saw.
        bundle = make_bundle(tmp_path / "b", figures=("table_01",))
        (bundle / "figures" / ".DS_Store").write_bytes(b"junk")
        assert bundle_problems(bundle) == []
        assert list(figure_files(bundle)) == ["table_01"]

    def test_no_figures_directory_is_no_crops(self, tmp_path):
        bundle = make_bundle(tmp_path / "b")
        assert not (bundle / "figures").exists()
        assert figure_files(bundle) == {}

    def test_it_refuses_nothing_itself(self, tmp_path):
        # A stray file is bundle_problems's to reject. This reports the
        # crops beside it rather than raising, so a caller that has already
        # taken the verdict gets what it came for.
        bundle = make_bundle(tmp_path / "b", figures=("table_01",))
        (bundle / "figures" / "notes.txt").write_text("x", encoding="utf-8")
        assert any("non-png" in p for p in bundle_problems(bundle))
        assert list(figure_files(bundle)) == ["table_01"]

    def test_it_reads_the_suffix_exactly(self, tmp_path):
        # The agreement this function exists for, now on an exact
        # suffix: a .PNG file is not a crop here, and validation refuses
        # it by name, so no consumer ever meets a label whose promised
        # path figures/<label>.png does not exist on a case-sensitive
        # filesystem. Reading the suffix case-insensitively also merged
        # x.png and x.PNG into one label with no report at all.
        bundle = make_bundle(tmp_path / "b", figures=("table_01",))
        (bundle / "figures" / "table_02.PNG").write_bytes(PNG_STUB)
        assert list(figure_files(bundle)) == ["table_01"]
        assert any("table_02.PNG" in p for p in bundle_problems(bundle))


# ------------------------------------------------------- tables/

# A table shape that must pass, and the printed table it stands for. Every
# one of these is a real arrangement a journal prints, and the suite is as
# interested in these as in the broken ones below: a check with no negative
# cases eventually refuses everything, and the shapes most likely to be
# refused by accident are the awkward ones this format exists to carry.
CORRECT_TABLES = {
    "a plain grid": TABLE_STUB,
    "rows directly in table, no row groups":
        "<table><tr><th>Season</th><th>Count</th></tr>"
        "<tr><td>April</td><td>4.8</td></tr></table>",
    "a spanning group header over a rowspan stub":
        '<table><thead>'
        '<tr><th rowspan="2" scope="col">Study</th>'
        '<th colspan="2" scope="colgroup">Intervention</th></tr>'
        '<tr><th scope="col">n</th><th scope="col">Mean</th></tr></thead>'
        '<tbody><tr><td>Ashby 2019</td><td>142</td><td>12.4</td></tr>'
        '</tbody></table>',
    "an empty cell, which is a value the paper prints":
        "<table><tr><th>Study</th><th>Mean</th></tr>"
        "<tr><td>Brune 2021</td><td></td></tr></table>",
    "a footnote marker as a superscript":
        "<table><tr><th>Study</th><th>n</th></tr>"
        "<tr><td>Brune 2021<sup>a</sup></td><td>2,089</td></tr></table>",
    "emphasis and a line break inside a cell":
        "<table><tr><th>Outcome</th><th>Result</th></tr>"
        "<tr><td><em>N</em> = 1,227</td>"
        "<td>12.4<br>(3.1)</td></tr></table>",
    "a row header with scope=row":
        '<table><tr><th scope="col">Season</th><th scope="col">n</th></tr>'
        '<tr><th scope="row">April</th><td>142</td></tr></table>',
    "a continuation page, repeating its header and carrying one row":
        "<table><thead><tr><th>Study</th><th>n</th></tr></thead>"
        "<tbody><tr><td>Calder 2023</td><td>310</td></tr></tbody></table>",
    "one cell, which is all some exhibits are":
        "<table><tr><td>None reported</td></tr></table>",
    "a rowspan reaching the last row, leaving that row one cell":
        '<table><tr><td rowspan="2">Cut</td><td>4.8</td></tr>'
        '<tr><td>3.1</td></tr></table>',
}


@pytest.mark.parametrize("shape", sorted(CORRECT_TABLES))
def test_a_correct_transcription_passes_clean(tmp_path, shape):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": CORRECT_TABLES[shape]})
    assert bundle_problems(bundle) == []


@pytest.mark.parametrize("markup, expected", [
    # The grid. Each of these reads plausibly and puts a value in the wrong
    # column, which is the whole reason the tiling is checked.
    ('<table><tr><th>Study</th><th colspan="2">Cut</th></tr>'
     '<tr><td>Ashby</td><td>4.8</td></tr></table>',
     "leaves row 2 column 3 (counted from 1, thead rows included) "
     "uncovered"),
    ('<table><tr><th>Study</th><th>Cut</th><th>Uncut</th></tr>'
     '<tr><td>Ashby</td><td>4.8</td></tr></table>',
     "leaves row 2 column 3 (counted from 1, thead rows included) "
     "uncovered"),
    # A rowspan one too long does not collide: the next row's cells skip
    # the position it claimed and the row runs one wide, so the fault
    # surfaces as a hole. An overlap needs a span that starts on a free
    # position and then reaches across a claimed one.
    ('<table><tr><td rowspan="2">Cut</td><td>4.8</td></tr>'
     '<tr><td>3.1</td><td>2.4</td></tr></table>',
     "leaves row 1 column 3 (counted from 1, thead rows included) "
     "uncovered"),
    ('<table><tr><td>a</td><td rowspan="2">b</td></tr>'
     '<tr><td colspan="3">c</td></tr></table>',
     "two cells covering row 2 column 2"),
    # The whitelist.
    ("<table><caption>Table 1.</caption><tr><td>a</td></tr></table>",
     "the exhibit's caption is carried by text.md"),
    ('<table><tfoot><tr><td>Total</td></tr></tfoot></table>',
     "the exhibit's printed footnote is the manifest's 'notes'"),
    ("<table><tr><td><table><tr><td>a</td></tr></table></td></tr></table>",
     "holds more than one <table>"),
    ("<table><tr><td>a</td></tr></table><table><tr><td>b</td></tr></table>",
     "holds more than one <table>"),
    ("<div><table><tr><td>a</td></tr></table></div>",
     "uses <div>, which a transcription may not carry"),
    ("<!DOCTYPE html><table><tr><td>a</td></tr></table>",
     "carries a document declaration"),
    ("<table><!-- checked --><tr><td>a</td></tr></table>",
     "carries an HTML comment"),
    # Attributes.
    ('<table><tr><td class="num">a</td></tr></table>',
     "gives <td> the attribute 'class'"),
    ('<table><tr><td style="text-align:right">a</td></tr></table>',
     "gives <td> the attribute 'style'"),
    ('<table><tr colspan="2"><td>a</td></tr></table>',
     "gives <tr> the attribute 'colspan'"),
    ('<table><tr><td scope="row">a</td></tr></table>',
     "gives <td> the attribute 'scope'"),
    ('<table><tr><th scope="middle">a</th></tr></table>',
     "scope='middle'"),
    ('<table><tr><td colspan="2" colspan="3">a</td><td>b</td></tr></table>',
     "repeats the 'colspan' attribute on <td>; a parser keeps the first"),
    ('<table><tr><td colspan>a</td></tr></table>',
     "gives <td> colspan with no value"),
    # A repeat of a bare attribute is still a repeat: a parser reads the
    # bare first occurrence, so the valued one never takes effect.
    ('<table><tr><td colspan colspan="2">a</td><td>b</td></tr></table>',
     "repeats the 'colspan' attribute"),
    # Spans that are not spans.
    ('<table><tr><td colspan="0">a</td></tr></table>',
     "colspan='0'"),
    ('<table><tr><td colspan="two">a</td></tr></table>',
     "colspan='two'"),
    ('<table><tr><td colspan="-1">a</td></tr></table>',
     "colspan='-1'"),
    ('<table><tr><td rowspan="5000">a</td></tr></table>',
     "beyond the 1000 this format allows"),
    # Structure and balance.
    ("<table><tr><td>a</td></tr>", "never closes <table>"),
    ("<table><tr><td>a</tr></td></table>",
     "closes </tr> while <td> is still open"),
    ("<table><tr><td>a</td></tr>oops</table>",
     "has text outside any cell: 'oops'"),
    ("<table><td>a</td></table>", "opens <td> inside <table>"),
    ("<table><tr><td>a</td></tr><td>b</td></table>",
     "opens <td> inside <table>"),
    ("<table><thead><td>a</td></thead></table>",
     "opens <td> inside <thead>"),
    ("<table><tr><td/></tr></table>", "writes <td/> in the self-closing"),
    ("<table></table>", "has no cells"),
    ("<table><tr><td>a</td></tr><tr></tr></table>",
     "writes no cells in row 2"),
    ("not a table at all", "contains no <table>"),
    ("<sup>a</sup>", "uses <sup> outside any cell"),
])
def test_a_broken_transcription_is_named(tmp_path, markup, expected):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": markup})
    problems = bundle_problems(bundle)
    assert any(expected in problem for problem in problems), problems
    assert all(problem.startswith("tables/table_01.html")
               for problem in problems), problems


def test_an_empty_transcription_is_not_a_transcription(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": "   \n"})
    assert any("is empty" in p for p in bundle_problems(bundle))


def test_a_misplaced_cell_is_not_also_an_empty_table():
    """A cell outside any row is one fault, and it is not "no cells".

    The file wrote a cell; the position problem says where it went
    wrong. Adding that the file has no cells and should be omitted is
    false of the file and advises deleting a transcription that has
    content in it. Cells are counted when written, not when the grid
    can place them, and a table with nothing written at all still says
    so.
    """
    for markup in ("<table><td>a</td></table>",
                   "<table><thead><td>a</td></thead></table>",
                   "<table><tbody><td>a</td></tbody></table>"):
        problems = table_html_problems(markup, "t.html")
        assert any("a cell belongs in <tr>" in p
                   for p in problems), problems
        assert not any("has no cells" in p for p in problems), problems
    problems = table_html_problems("<table><tr></tr></table>", "t.html")
    assert any("has no cells" in p for p in problems), problems


def test_a_refused_element_self_closed_is_one_problem():
    """One fault, one problem, and no message teaching a way round.

    Told that every element but <br> is opened and closed, an author
    holding <img/> writes <img></img> and is refused again. For an
    element outside the whitelist the refusal is the whole answer, so
    the self-closing complaint is kept for whitelisted elements only.
    """
    problems = table_html_problems(
        "<table><tr><td><img/></td></tr></table>", "t.html")
    assert any("uses <img>" in p for p in problems), problems
    assert not any("self-closing" in p for p in problems), problems


def test_a_second_table_ends_the_grid_verdicts():
    """The refusal carries the fault; a verdict would narrate fiction.

    A nested table's rows and cells land in the outer table's grid, so
    every hole, overhang and empty row judged after it describes a
    table the file does not contain: a 1 by 2 table holding a 1 by 2
    table was reported as a holed 2 by 3. The one refusal is the
    answer, the way an overflowed grid already answers with its one
    problem.
    """
    nested = ('<table><tr><td><table><tr><td>a</td><td>b</td></tr>'
              '</table></td><td>c</td></tr></table>')
    beside = ('<table><tr><td>a</td></tr></table>'
              '<table><tr><td>b</td></tr></table>')
    for markup in (nested, beside):
        problems = table_html_problems(markup, "t.html")
        assert len(problems) == 1, problems
        assert "holds more than one <table>" in problems[0]


def test_a_self_closed_cell_keeps_its_text_and_its_close():
    """The stray slash is the fault, not what follows it.

    HTML5 reads <td/> as <td>: the slash means nothing, the element is
    open, and the text after it is inside the cell. Read as closed
    instead, the same file also earned "text outside any cell" and a
    nesting complaint for its own </td>, both false of the file. The
    complaint about the form is the whole answer.
    """
    markup = "<table><tr><td/>a</td><td>b</td></tr></table>"
    problems = table_html_problems(markup, "t.html")
    assert len(problems) == 1, problems
    assert "writes <td/> in the self-closing form" in problems[0]


def test_a_holed_grid_reports_its_position_and_stops_counting(tmp_path):
    """Five holes are named and the rest are counted.

    A table that lost its first column holes every row, and a hundred
    lines saying so would bury whatever else the file gets wrong.
    """
    rows = "".join("<tr><td>a</td></tr>" for _ in range(12))
    markup = f'<table><tr><th colspan="2">Wide</th></tr>{rows}</table>'
    problems = bundle_problems(make_bundle(tmp_path / "b",
                                           figures=("table_01",),
                                           tables={"table_01": markup}))
    named = [p for p in problems if "uncovered" in p and "further" not in p]
    assert len(named) == 5
    assert any("leaves 7 further positions uncovered" in p
               for p in problems), problems


def test_a_grid_position_is_counted_as_a_reader_counts():
    """A position names where to look, so it uses the reader's count.

    The grid is built 0-based with thead rows in the row numbering, and
    a person holding the printed table counts neither way: told "row 0,
    column 2" against a table with a header, they look in the wrong
    place. Every position is 1-based, counts thead rows, and says so,
    because an unstated basis is ambiguous even when it is the right one.
    """
    markup = ('<table><thead><tr><th>Study</th><th>n</th></tr></thead>'
              '<tbody><tr><td>Ashby</td></tr></tbody></table>')
    problems = table_html_problems(markup, "t.html")
    assert any("leaves row 2 column 2 (counted from 1, thead rows "
               "included) uncovered" in p for p in problems), problems


def test_a_transcription_is_optional_exhibit_by_exhibit(tmp_path):
    bundle = make_bundle(tmp_path / "b",
                         figures=("table_01", "figure_01"),
                         tables={"table_01": TABLE_STUB})
    assert bundle_problems(bundle) == []


def test_a_bundle_may_transcribe_nothing(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    assert bundle_problems(bundle) == []
    assert table_files(bundle) == {}


def test_a_transcription_needs_a_declared_exhibit(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB,
                                 "table_09": TABLE_STUB})
    problems = bundle_problems(bundle)
    assert any("tables/table_09.html is not declared" in p
               for p in problems), problems
    assert not any("table_01" in p for p in problems), problems


def test_a_transcription_never_stands_in_for_a_crop(tmp_path):
    """A transcribed exhibit still owes its PNG.

    The figures cross-check is what enforces it, so this is a test of the
    two rules together: nothing reaches a reader as text alone.
    """
    bundle = make_bundle(tmp_path / "b", tables={"table_01": TABLE_STUB})
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = [{"label": "table_01", "caption": "A table."}]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert any("no file in figures/ is named table_01.png" in p
               for p in bundle_problems(bundle))


def test_tables_rejects_non_html_and_subdirs(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB})
    (bundle / "tables" / "notes.txt").write_text("stray", encoding="utf-8")
    (bundle / "tables" / "old").mkdir()
    problems = bundle_problems(bundle)
    assert any("contains a non-html file" in p for p in problems), problems
    assert any("contains a subdirectory" in p for p in problems), problems


def test_an_html_suffix_must_be_exactly_lowercase(tmp_path):
    """The tables/ half of the exact-suffix rule.

    The promised path is tables/<label>.html, and a .HTML file is not
    that path on a case-sensitive filesystem, for the same reason a
    .PNG crop is not figures/<label>.png.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB})
    transcription = bundle / "tables" / "table_01.html"
    markup = transcription.read_text(encoding="utf-8")
    transcription.unlink()
    (bundle / "tables" / "table_01.HTML").write_text(markup,
                                                     encoding="utf-8")
    problems = bundle_problems(bundle)
    assert any("table_01.HTML" in p and "lowercase" in p
               for p in problems), problems
    assert table_files(bundle) == {}


def test_hidden_files_in_tables_are_ignored(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB})
    (bundle / "tables" / ".DS_Store").write_bytes(b"\x00")
    assert bundle_problems(bundle) == []


def test_tables_that_is_not_a_directory_is_one_problem(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "tables").write_text("not a directory", encoding="utf-8")
    problems = bundle_problems(bundle)
    assert any("tables exists but is not a directory" in p
               for p in problems), problems


def test_a_transcription_must_be_utf8(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                         tables={"table_01": TABLE_STUB})
    (bundle / "tables" / "table_01.html").write_bytes(b"<table>\xff</table>")
    assert any("could not be read as UTF-8" in p
               for p in bundle_problems(bundle))


class TestTableFiles:
    """`table_files` is the directory's reading, and consumers use it."""

    def test_it_maps_label_to_path_sorted(self, tmp_path):
        bundle = make_bundle(tmp_path / "b",
                             figures=("table_02", "table_01"),
                             tables={"table_02": TABLE_STUB,
                                     "table_01": TABLE_STUB})
        found = table_files(bundle)
        assert list(found) == ["table_01", "table_02"]
        assert found["table_01"].name == "table_01.html"

    def test_an_absent_directory_is_no_transcriptions(self, tmp_path):
        assert table_files(make_bundle(tmp_path / "b")) == {}

    def test_it_skips_dotfiles_and_other_suffixes(self, tmp_path):
        bundle = make_bundle(tmp_path / "b", figures=("table_01",),
                             tables={"table_01": TABLE_STUB})
        (bundle / "tables" / ".DS_Store").write_bytes(b"\x00")
        (bundle / "tables" / "notes.txt").write_text("x", encoding="utf-8")
        assert list(table_files(bundle)) == ["table_01"]


# ------------------------------------ what a wrong table must not survive

def test_a_rowspan_may_not_reach_past_the_last_row(tmp_path):
    """The way round the tiling rule, closed.

    A row that went missing leaves a hole, and the obvious move for
    silencing a hole is to widen the rowspan above it. That tiles
    perfectly and the row is still gone, and the two files draw
    identically, so the render cannot catch it either.
    """
    printed = ("<table><tr><th>Season</th><th>n</th></tr>"
               "<tr><td>April</td><td>142</td></tr>"
               "<tr><td>July</td><td>88</td></tr></table>")
    assert table_html_problems(printed, "t.html") == []
    hidden = ('<table><tr><th>Season</th><th>n</th></tr>'
              '<tr><td rowspan="2">April</td>'
              '<td rowspan="2">142</td></tr></table>')
    problems = table_html_problems(hidden, "t.html")
    assert any("rowspan reaching row 3 (counted from 1, thead rows "
               "included) when the table writes 2 rows" in p
               for p in problems), problems


def test_an_overhanging_rowspan_does_not_invent_rows_to_complain_about(
        tmp_path):
    """The diagnostics stay coherent: two rows written, two rows judged."""
    markup = ('<table><tr><td>a</td></tr>'
              '<tr><td rowspan="3">b</td><td>c</td></tr></table>')
    problems = table_html_problems(markup, "t.html")
    assert any("2 by 2 table" in p for p in problems), problems
    # The overhang names row 3 as the first row past the end; no hole is
    # invented there, and nothing names row 4.
    assert not any("uncovered" in p and "row 3" in p
                   for p in problems), problems
    assert not any("row 4" in p for p in problems), problems


def test_an_empty_row_may_not_be_covered_by_a_widened_span(tmp_path):
    """The other half of the bypass, and the one the message used to teach.

    Deleting the row and widening the span above it is refused by the
    overhang rule. Keeping the row empty and widening the span is the
    same data loss for one edit less, and the two files draw identically,
    so nothing downstream can tell them apart. The earlier wording told
    an author to do exactly this.
    """
    printed = ("<table><tr><th>Season</th><th>n</th></tr>"
               "<tr><td>April</td><td>142</td></tr>"
               "<tr><td>July</td><td>88</td></tr></table>")
    assert table_html_problems(printed, "t.html") == []
    hidden = ('<table><tr><th>Season</th><th>n</th></tr>'
              '<tr><td rowspan="2">April</td><td rowspan="2">142</td></tr>'
              '<tr></tr></table>')
    problems = table_html_problems(hidden, "t.html")
    assert any("writes no cells in row 3" in p for p in problems), problems


def test_an_empty_row_is_one_problem_not_a_problem_per_column():
    """One fault gives one problem.

    An empty row not covered by spans also holes every column it has,
    and each of those holes is the empty row said again: a ten-column
    table would report the one missing row eleven times. The empty-row
    problem carries the fault, so its holes are not repeated. A hole in
    a row that does have cells is its own fault and stays reported.
    """
    markup = ("<table><tr><th>Season</th><th>n</th></tr>"
              "<tr></tr>"
              "<tr><td>April</td><td>142</td></tr></table>")
    problems = table_html_problems(markup, "t.html")
    assert len(problems) == 1, problems
    assert "writes no cells in row 2" in problems[0]
    holed = ("<table><tr><th>Season</th><th>n</th></tr>"
             "<tr></tr>"
             "<tr><td>April</td></tr></table>")
    problems = table_html_problems(holed, "t.html")
    assert any("writes no cells in row 2" in p for p in problems), problems
    assert any("leaves row 3 column 2" in p for p in problems), problems


def test_a_run_of_empty_rows_is_capped_like_holes():
    """Five are named and the rest are counted, as holes are.

    A transcription mangled into thousands of empty rows is one
    mangling, and thousands of copies of the same problem would bury
    whatever else the file gets wrong, which is the flood the hole cap
    already stops.
    """
    markup = ("<table><tr><td>a</td></tr>" + "<tr></tr>" * 200
              + "</table>")
    problems = table_html_problems(markup, "t.html")
    named = [p for p in problems if "writes no cells in row" in p]
    assert len(named) == 5, problems[:7]
    assert any("writes no cells in 195 further rows" in p
               for p in problems), problems[-2:]


def test_the_occupancy_is_bounded_as_it_is_built(tmp_path):
    """The limit has to bite during the parse, not after it.

    Positions are written as the cells are read, so one cell carrying both
    spans at their ceiling claims a million of them. Checking the
    rectangle afterwards left a four hundred byte file costing gate 1
    gigabytes before anything got to say the grid was too large.
    """
    markup = ("<table><tr>"
              + '<td colspan="1000" rowspan="1000">x</td>' * 10
              + "</tr></table>")
    started = time.perf_counter()
    problems = table_html_problems(markup, "t.html")
    assert time.perf_counter() - started < 1.0
    assert any("claims more than 100000 cell positions" in p
               for p in problems), problems
    # And nothing else, because a grid that overflowed stopped placing
    # cells and is not also an empty table.
    assert len(problems) == 1, problems


def test_a_grid_beyond_the_limit_is_refused_cheaply(tmp_path):
    """A sub-kilobyte file may not buy tens of millions of positions.

    Gate 1 runs the validator on every conversion and render_table.py runs
    it before it draws, so unbounded work here is unbounded work there.
    """
    row = "<tr>" + '<td colspan="1000">x</td>' * 20 + "</tr>"
    markup = "<table>" + row * 30 + "</table>"
    started = time.perf_counter()
    problems = table_html_problems(markup, "t.html")
    assert time.perf_counter() - started < 2.0
    assert any("100000 cell positions" in p for p in problems), problems


def test_a_real_table_of_five_hundred_rows_is_not_near_the_limit(tmp_path):
    markup = ("<table>"
              + "".join(f"<tr><td>Row {n}</td><td>{n}</td></tr>"
                        for n in range(500))
              + "</table>")
    assert table_html_problems(markup, "t.html") == []


def test_a_marked_section_is_refused_rather_than_dropped(tmp_path):
    """`html.parser` drops these silently, and parsers disagree on them.

    The second case reads as one cell here and as two under libxml2, so
    accepting it would make the tiling verdict a claim about one parser
    rather than about the file.
    """
    for markup in ("<table><tr><td>4.8<![CDATA[ hidden ]]></td>"
                   "<td>3.1</td></tr></table>",
                   "<table><tr><td>A<![CDATA[</td><td>]]>B</td></tr></table>"):
        problems = table_html_problems(markup, "t.html")
        assert any("marked section" in p for p in problems), (markup,
                                                              problems)


@pytest.mark.parametrize("span", ["²", "٢"])
def test_a_span_that_is_not_an_ascii_number_is_refused(span):
    """`isdigit` is true of both and `int` agrees with neither usefully.

    The superscript raises inside the parse, and the Arabic-Indic digit
    converts to 2 here while a renderer reading HTML's ASCII-only rule
    reads 1. Either way the grid validated is not the grid laid out.
    """
    markup = f'<table><tr><td colspan="{span}">a</td></tr></table>'
    problems = table_html_problems(markup, "t.html")
    assert any("a span is a positive whole number" in p
               for p in problems), problems


def test_a_bad_span_does_not_abort_the_rest_of_the_file():
    """The module promises every problem at once, so it owes them here."""
    markup = ('<table><tr><td colspan="²">a</td></tr>'
              '<tr><td style="x">b</td></tr></table>')
    problems = table_html_problems(markup, "t.html")
    assert any("a span is a positive whole number" in p for p in problems)
    assert any("the attribute 'style'" in p for p in problems), problems


def test_a_span_of_thousands_of_digits_is_the_format_s_refusal():
    """CPython refuses to convert more than 4300 digits, loudly.

    Left to int(), the ValueError aborts the parse, calls a file that
    parsed fine unparseable, ends the report there, and quotes
    sys.set_int_max_str_digits(), which is advice about making the
    reader accept the file when the fault is the file. The digits are
    counted before anything converts, and the refusal is the same one
    every oversized span gets. Leading zeros are not counted, so a
    legal span padded with them stays legal.
    """
    markup = ('<table><tr><td colspan="' + "9" * 5000 + '">a</td>'
              '<td style="x">b</td></tr></table>')
    problems = table_html_problems(markup, "t.html")
    assert any("beyond the 1000 this format allows" in p
               for p in problems), [p[:80] for p in problems]
    assert not any("could not be parsed" in p for p in problems), problems
    # The report continues past the refusal.
    assert any("the attribute 'style'" in p for p in problems), problems
    padded = ('<table><tr><td colspan="' + "0" * 5000 + '2">a</td>'
              '<td>b</td></tr></table>')
    assert table_html_problems(padded, "t.html") == []


def test_a_gigantic_attribute_value_is_not_quoted_whole():
    """What a problem shows of a value is capped, as stray text is.

    The value being five thousand characters is the fault; a problem
    string repeating all of them buries the rest of the report under
    the thing it is reporting.
    """
    for attr in ('colspan="' + "9" * 5000 + '"',
                 'colspan="' + "0" * 5000 + '"',
                 'scope="' + "x" * 5000 + '"'):
        markup = f"<table><tr><th {attr}>a</th></tr></table>"
        problems = table_html_problems(markup, "t.html")
        assert problems, attr
        assert all(len(p) < 200 for p in problems), [p[:80]
                                                     for p in problems]


def test_a_bare_attribute_is_said_in_words():
    """`html.parser` hands a valueless attribute through as None.

    `<td colspan>` is a mistake made in HTML, so the answer names it in
    HTML's terms: Python's repr of None describes nothing the author
    wrote and points at nothing they can change.
    """
    for markup in ('<table><tr><td colspan>a</td></tr></table>',
                   '<table><tr><th scope>a</th></tr></table>'):
        problems = table_html_problems(markup, "t.html")
        assert any("with no value" in p for p in problems), problems
        assert not any("None" in p for p in problems), problems


def test_a_byte_order_mark_is_not_content(tmp_path):
    """It survives a UTF-8 read and the exhibit does not print it."""
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "tables").mkdir()
    (bundle / "tables" / "table_01.html").write_text("﻿" + TABLE_STUB,
                                                     encoding="utf-8")
    assert bundle_problems(bundle) == []


def test_table_html_problems_is_the_rule_a_tool_can_reuse():
    """The transcription rule is public, and it is the same rule.

    An engine that draws a transcription refuses what the format refuses
    by calling this, rather than forming its own opinion of what a table
    is. If this ever stops being importable such a tool grows a second
    definition, which is the drift the function exists to prevent.
    """
    assert table_html_problems(TABLE_STUB, "t.html") == []
    problems = table_html_problems("<p>not a table</p>", "t.html")
    assert problems and all(p.startswith("t.html") for p in problems)


def test_every_void_element_is_classified_as_inline():
    """A void element is written alone and never pushed on the stack.

    The parser's stack logic assumes a void element is a cell's own
    markup, so one that were not also inline would either be refused as
    unknown while the void rules name it, or would skip the placement
    checks entirely. The whitelist is derived from the classifying sets,
    and this is the one relation the derivation does not force.
    """
    from alteksto.bundle import _INLINE_ELEMENTS, _VOID_ELEMENTS
    assert _VOID_ELEMENTS <= _INLINE_ELEMENTS


def test_a_named_refusal_is_never_also_whitelisted():
    """A note is the reason an element is refused, nothing else.

    The notes are read only when the whitelist has refused an element,
    so an element holding both a note and a place in the whitelist would
    be accepted while carrying the text of its own refusal, and one of
    the two would have to be a mistake.
    """
    from alteksto.bundle import _TABLE_ELEMENTS, _TABLE_ELEMENT_NOTES
    assert not set(_TABLE_ELEMENT_NOTES) & _TABLE_ELEMENTS


# -------------------------------------------- supplements.json and supplements/

def add_supplement(bundle, name, *, labels=(), title=None, text="# S\n\nProse.",
                   tables=None):
    """Put a supplement's directory in place. The declaration is separate,
    because most of what these tests ask is what happens when the two
    disagree."""
    root = bundle / "supplements" / name
    root.mkdir(parents=True, exist_ok=True)
    if text is not None:
        (root / "text.md").write_text(text, encoding="utf-8")
    if labels:
        (root / "figures").mkdir(exist_ok=True)
        for label in labels:
            (root / "figures" / f"{label}.png").write_bytes(PNG_STUB)
    if tables:
        (root / "tables").mkdir(exist_ok=True)
        for label, markup in tables.items():
            (root / "tables" / f"{label}.html").write_text(markup,
                                                           encoding="utf-8")
    return root


def declare_supplements(bundle, entries, paper_id="inv-01"):
    (bundle / "supplements.json").write_text(
        json.dumps({"id": paper_id, "supplements": entries}),
        encoding="utf-8")


def entry(name, labels=(), title=None):
    return {"name": name, "title": title or f"{name}, as printed",
            "exhibits": [{"label": label, "caption": f"Caption for {label}"}
                         for label in labels]}


def test_a_bundle_with_a_supplement_is_valid(tmp_path):
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    add_supplement(bundle, "supplement_3",
                   labels=("supplement_3_table_01",),
                   tables={"supplement_3_table_01": TABLE_STUB})
    declare_supplements(bundle, [entry("supplement_3",
                                       ("supplement_3_table_01",))])
    assert bundle_problems(bundle) == []
    assert list(supplement_dirs(bundle)) == ["supplement_3"]


def test_a_supplement_of_tables_alone_writes_no_text(tmp_path):
    """Optional here where it is required for the article: a supplement
    that prints no prose would have to have some invented for it."""
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    add_supplement(bundle, "appendix_a", labels=("appendix_a_table_01",),
                   text=None)
    declare_supplements(bundle, [entry("appendix_a",
                                       ("appendix_a_table_01",))])
    assert bundle_problems(bundle) == []


def test_a_supplement_may_hold_no_exhibits(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    declare_supplements(bundle, [entry("appendix_a")])
    assert bundle_problems(bundle) == []


def test_two_supplements_are_ordinary(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    add_supplement(bundle, "supplement_3", labels=("supplement_3_fig_01",))
    declare_supplements(bundle, [entry("appendix_a"),
                                 entry("supplement_3",
                                       ("supplement_3_fig_01",))])
    assert bundle_problems(bundle) == []
    assert list(supplement_dirs(bundle)) == ["appendix_a", "supplement_3"]


def test_a_fault_in_a_later_supplement_is_reported(tmp_path):
    """Every declared supplement is walked against the one reading of
    supplements/, so a fault in the second is as loud as a fault in the
    first. A rebound loop variable once ended the walk's sight after one
    supplement, and every supplement sorting later validated in silence.
    """
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    root = add_supplement(bundle, "supplement_3")
    (root / "figures").mkdir()
    (root / "figures" / "sneaked_in.png").write_bytes(PNG_STUB)
    declare_supplements(bundle, [entry("appendix_a"),
                                 entry("supplement_3",
                                       ("supplement_3_fig_01",))])
    problems = bundle_problems(bundle)
    assert any("no file in supplements/supplement_3/figures/ is named "
               "supplement_3_fig_01.png" in p for p in problems), problems
    assert any("supplements/supplement_3/figures/sneaked_in.png is not "
               "declared" in p for p in problems), problems


def test_a_supplement_directory_needs_its_declaration(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    problems = bundle_problems(bundle)
    assert any("there is no supplements.json" in p for p in problems), problems


def test_a_declaration_needs_its_directory(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    declare_supplements(bundle, [entry("appendix_a")])
    problems = bundle_problems(bundle)
    assert any("no directory in supplements/ is named appendix_a" in p
               for p in problems), problems


def test_an_undeclared_supplement_directory_is_refused(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    add_supplement(bundle, "sneaked_in")
    declare_supplements(bundle, [entry("appendix_a")])
    problems = bundle_problems(bundle)
    assert any("supplements/sneaked_in/ is not declared" in p
               for p in problems), problems


def test_the_declaration_carries_the_paper_s_own_id(tmp_path):
    """A declaration copied between bundles is otherwise undetectable."""
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    declare_supplements(bundle, [entry("appendix_a")], paper_id="inv-99")
    problems = bundle_problems(bundle)
    assert any("is not the manifest's 'inv-01'" in p for p in problems), problems


def test_a_declaration_of_no_supplements_is_a_mistake(tmp_path):
    """Absence is the assertion, so an empty list is a second place to
    keep in step and says nothing the missing file does not."""
    bundle = make_bundle(tmp_path / "b")
    declare_supplements(bundle, [])
    problems = bundle_problems(bundle)
    assert any("declares no supplements" in p for p in problems), problems


@pytest.mark.parametrize("mutate, expected", [
    (lambda e: e.pop("title"), "missing required key: 'title'"),
    (lambda e: e.pop("name"), "missing required key: 'name'"),
    (lambda e: e.pop("exhibits"), "missing required key: 'exhibits'"),
    (lambda e: e.update(warden="a heron"), "unknown key: 'warden'"),
    (lambda e: e.update(title=""), "key 'title' must be a non-empty string"),
    (lambda e: e.update(name="a/b"), "must match ^[A-Za-z0-9._-]+$"),
    (lambda e: e.update(title=7), "key 'title' must be a string"),
])
def test_a_supplement_entry_is_name_title_and_exhibits(tmp_path, mutate,
                                                       expected):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    declared = entry("appendix_a")
    mutate(declared)
    declare_supplements(bundle, [declared])
    problems = bundle_problems(bundle)
    assert any(expected in p for p in problems), problems


@pytest.mark.parametrize("value", [None, 0, False, "", {}, "supplement_a"])
def test_supplements_must_be_a_list_whatever_else_it_is(tmp_path, value):
    """`null` in particular, which read as an absent key and said nothing.

    An absent key and an explicit null both come back None from a lookup,
    and only one of them has already been reported, so the null case
    returned a malformed verdict with no problem attached. Every check
    downstream is guarded on that verdict, so a bundle whose supplements
    were wrong five ways validated clean.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    add_supplement(bundle, "ghost", labels=("table_01",))
    (bundle / "supplements.json").write_text(
        json.dumps({"id": "inv-01", "supplements": value}), encoding="utf-8")
    problems = bundle_problems(bundle)
    assert problems
    assert any("'supplements' must be a list" in p or
               "declares no supplements" in p for p in problems), problems


def test_a_supplement_name_may_not_be_a_path_component(tmp_path):
    """`..` resolves to the bundle root, where the article's own files are.

    The pattern alone allows it, which is why the id carries a second
    check. Without it the walk below reads the article's figures/ and
    tables/ and reports them as this supplement's undeclared files, at a
    path no author can open.
    """
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    (bundle / "supplements.json").write_text(
        json.dumps({"id": "inv-01",
                    "supplements": [{"name": "..", "title": "S",
                                     "exhibits": []}]}), encoding="utf-8")
    problems = bundle_problems(bundle)
    assert any("must contain at least one letter or digit" in p
               for p in problems), problems
    assert not any("supplements/../" in p for p in problems), problems


def test_a_declared_supplement_with_no_directory_reports_once(tmp_path):
    """Not once per exhibit: the module's own discipline is that a report
    is not buried under noise derived from it."""
    bundle = make_bundle(tmp_path / "b")
    declare_supplements(bundle, [entry("absent_one",
                                       tuple(f"absent_one_table_{n:02d}"
                                             for n in range(6)))])
    problems = bundle_problems(bundle)
    assert len(problems) == 1, problems
    assert "no directory in supplements/ is named absent_one" in problems[0]


def test_supplements_that_is_not_a_directory_is_one_problem(tmp_path):
    """The fault figures/ and tables/ name in the same words. One file
    displaces every declared supplement's directory at once, so naming
    the file is the whole report; a missing-directory line per declared
    name would be noise derived from it."""
    bundle = make_bundle(tmp_path / "b")
    (bundle / "supplements").write_text("not a directory", encoding="utf-8")
    declare_supplements(bundle, [entry("appendix_a")])
    problems = bundle_problems(bundle)
    assert len(problems) == 1, problems
    assert "supplements exists but is not a directory" in problems[0]


def test_a_file_named_supplements_needs_no_declaration_to_be_refused(
        tmp_path):
    """As a file named figures or tables would be. There is nothing to
    cross-check, but the name the format reserves is taken, and a bundle
    that later declares a supplement has nowhere to put it."""
    bundle = make_bundle(tmp_path / "b")
    (bundle / "supplements").write_text("not a directory", encoding="utf-8")
    problems = bundle_problems(bundle)
    assert problems == ["supplements exists but is not a directory: "
                        f"{bundle / 'supplements'}"]


def test_a_loose_file_under_supplements_is_refused_undeclared_too(tmp_path):
    """It is neither a supplement nor a supplement's asset either way."""
    bundle = make_bundle(tmp_path / "b")
    (bundle / "supplements").mkdir()
    (bundle / "supplements" / "notes.txt").write_text("stray",
                                                      encoding="utf-8")
    problems = bundle_problems(bundle)
    assert any("supplements/ contains a file" in p for p in problems), problems


def test_an_empty_supplements_directory_declares_nothing(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    (bundle / "supplements").mkdir()
    assert bundle_problems(bundle) == []


def test_a_duplicate_key_problem_names_the_file_it_is_in(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    (bundle / "supplements.json").write_text(
        '{"id": "inv-01", "id": "inv-01", "supplements": '
        '[{"name": "appendix_a", "title": "A", "exhibits": []}]}',
        encoding="utf-8")
    problems = bundle_problems(bundle)
    assert any("what supplements.json declares here" in p
               for p in problems), problems


def test_a_supplement_name_is_declared_once(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    declare_supplements(bundle, [entry("appendix_a"), entry("appendix_a")])
    problems = bundle_problems(bundle)
    assert any("declared more than once" in p for p in problems), problems


def test_supplements_holds_directories_only(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    declare_supplements(bundle, [entry("appendix_a")])
    (bundle / "supplements" / "notes.txt").write_text("stray",
                                                      encoding="utf-8")
    problems = bundle_problems(bundle)
    assert any("supplements/ contains a file" in p for p in problems), problems


def test_a_duplicate_key_in_the_declaration_is_refused(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a")
    (bundle / "supplements.json").write_text(
        '{"id": "inv-01", "id": "inv-02", "supplements": '
        '[{"name": "appendix_a", "title": "A", "exhibits": []}]}',
        encoding="utf-8")
    problems = bundle_problems(bundle)
    assert any("supplements.json has a duplicate key: 'id'" in p
               for p in problems), problems


# ------------------------------------------- one label, one exhibit

def test_a_supplement_may_not_reuse_an_article_label(tmp_path):
    """A consumer's whole citation is the label, looked up in a flat map,
    so two exhibits with one name resolve to whichever loaded second."""
    bundle = make_bundle(tmp_path / "b", figures=("table_01",))
    add_supplement(bundle, "appendix_a", labels=("table_01",))
    declare_supplements(bundle, [entry("appendix_a", ("table_01",))])
    problems = bundle_problems(bundle)
    assert any("which manifest.json already declares" in p
               for p in problems), problems


def test_two_supplements_may_not_share_a_label(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a", labels=("shared_01",))
    add_supplement(bundle, "supplement_3", labels=("shared_01",))
    declare_supplements(bundle, [entry("appendix_a", ("shared_01",)),
                                 entry("supplement_3", ("shared_01",))])
    problems = bundle_problems(bundle)
    assert any("which supplement 'appendix_a' already declares" in p
               for p in problems), problems


def test_a_supplement_label_clash_outlives_a_malformed_manifest(tmp_path):
    """A clash between two supplements does not depend on the manifest's
    exhibits, so a fault there must not hide it. Only the article's own
    clashes wait for the manifest: with its block malformed the article's
    labels are unknown, and a clash claimed against them would be a
    guess."""
    bundle = make_bundle(tmp_path / "b")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["exhibits"] = "not a list"
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    add_supplement(bundle, "appendix_a", labels=("shared_01",))
    add_supplement(bundle, "supplement_3", labels=("shared_01",))
    declare_supplements(bundle, [entry("appendix_a", ("shared_01",)),
                                 entry("supplement_3", ("shared_01",))])
    problems = bundle_problems(bundle)
    assert any("which supplement 'appendix_a' already declares" in p
               for p in problems), problems
    assert not any("manifest.json already declares" in p for p in problems)


# ------------------------------------- a supplement's own assets

def test_a_supplement_s_exhibits_are_bound_to_its_own_figures(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a", labels=("appendix_a_table_02",))
    declare_supplements(bundle, [entry("appendix_a",
                                       ("appendix_a_table_01",))])
    problems = bundle_problems(bundle)
    assert any("no file in supplements/appendix_a/figures/ is named "
               "appendix_a_table_01.png" in p for p in problems), problems
    assert any("supplements/appendix_a/figures/appendix_a_table_02.png is "
               "not declared" in p for p in problems), problems


def test_a_supplement_s_transcription_is_held_to_the_same_rules(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a", labels=("appendix_a_table_01",),
                   tables={"appendix_a_table_01":
                           '<table><tr><th colspan="2">Wide</th></tr>'
                           '<tr><td>a</td></tr></table>'})
    declare_supplements(bundle, [entry("appendix_a",
                                       ("appendix_a_table_01",))])
    problems = bundle_problems(bundle)
    assert any("supplements/appendix_a/tables/appendix_a_table_01.html "
               "leaves row 2 column 2 (counted from 1, thead rows "
               "included) uncovered" in p
               for p in problems), problems


def test_a_supplement_s_figures_directory_takes_pngs_only(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    root = add_supplement(bundle, "appendix_a",
                          labels=("appendix_a_table_01",))
    (root / "figures" / "notes.txt").write_text("stray", encoding="utf-8")
    declare_supplements(bundle, [entry("appendix_a",
                                       ("appendix_a_table_01",))])
    problems = bundle_problems(bundle)
    assert any("supplements/appendix_a/figures/ contains a non-png file" in p
               for p in problems), problems


def test_a_supplement_s_crop_is_held_to_the_png_signature(tmp_path):
    """The article's content check, at the supplement's path.

    A supplement's figures/ is read by the same function with only a
    prefix changed, so a zero-byte or renamed file there is refused on
    the article's terms and named where it sits.
    """
    bundle = make_bundle(tmp_path / "b")
    root = add_supplement(bundle, "appendix_a",
                          labels=("appendix_a_table_01",))
    (root / "figures" / "appendix_a_table_01.png").write_bytes(b"%PDF-1.4")
    declare_supplements(bundle, [entry("appendix_a",
                                       ("appendix_a_table_01",))])
    problems = bundle_problems(bundle)
    assert any("supplements/appendix_a/figures/appendix_a_table_01.png "
               "does not start with the PNG signature" in p
               for p in problems), problems


def test_a_supplement_s_figures_may_not_be_a_file(tmp_path):
    """The article's report, at the supplement's path. The walk keeps
    going: bundle_problems never raises for a malformed bundle, and an
    unusable figures/ in one supplement says nothing about the next."""
    bundle = make_bundle(tmp_path / "b")
    root = add_supplement(bundle, "appendix_a")
    (root / "figures").write_text("not a directory", encoding="utf-8")
    add_supplement(bundle, "supplement_3")
    declare_supplements(bundle, [entry("appendix_a"), entry("supplement_3")])
    problems = bundle_problems(bundle)
    assert problems == ["supplements/appendix_a/figures exists but is not a "
                        f"directory: {root / 'figures'}"]


def test_a_supplement_s_tables_may_not_be_a_file(tmp_path):
    """The article's report again, for the other asset directory."""
    bundle = make_bundle(tmp_path / "b")
    root = add_supplement(bundle, "appendix_a")
    (root / "tables").write_text("not a directory", encoding="utf-8")
    declare_supplements(bundle, [entry("appendix_a")])
    problems = bundle_problems(bundle)
    assert problems == ["supplements/appendix_a/tables exists but is not a "
                        f"directory: {root / 'tables'}"]


def test_an_empty_supplement_text_is_a_mistake_not_a_signal(tmp_path):
    bundle = make_bundle(tmp_path / "b")
    add_supplement(bundle, "appendix_a", text="   \n")
    declare_supplements(bundle, [entry("appendix_a")])
    problems = bundle_problems(bundle)
    assert any("supplements/appendix_a/text.md is empty" in p
               for p in problems), problems


class TestSupplementDirs:
    def test_it_maps_name_to_path_sorted(self, tmp_path):
        bundle = make_bundle(tmp_path / "b")
        add_supplement(bundle, "supplement_3")
        add_supplement(bundle, "appendix_a")
        found = supplement_dirs(bundle)
        assert list(found) == ["appendix_a", "supplement_3"]
        assert found["appendix_a"].name == "appendix_a"

    def test_an_absent_directory_is_no_supplements(self, tmp_path):
        assert supplement_dirs(make_bundle(tmp_path / "b")) == {}

    def test_a_supplement_s_own_assets_read_with_the_bundle_s_readers(
            self, tmp_path):
        """The directory is bundle-shaped so these work on it unchanged."""
        bundle = make_bundle(tmp_path / "b")
        root = add_supplement(bundle, "appendix_a",
                              labels=("appendix_a_table_01",),
                              tables={"appendix_a_table_01": TABLE_STUB})
        assert list(figure_files(root)) == ["appendix_a_table_01"]
        assert list(table_files(root)) == ["appendix_a_table_01"]


def test_the_contract_costs_a_consumer_nothing_to_install():
    """A package that only reads and checks bundles depends on this one,
    and gets the standard library and no more.

    Both halves are asserted because either alone would let the promise
    rot: a runtime dependency added to pyproject would land a page stack
    in every consumer's environment, and an import added anywhere in the
    package would break a plain install at the one moment it matters.
    Neither fault is visible to a suite that runs with an engine's extra
    installed, as this one always does, so both are read off the files.

    Every module the package holds is read, rather than a list of the
    ones that exist today. A file added beside `bundle.py` is on the path
    an importer executes, and a list of names would not know about it. A
    relative import counts as much as importing by name, and is the shape
    a refactor is most likely to introduce.

    This is why the engines live outside the package entirely. Producing
    a bundle needs pymupdf and lxml; the contract needs neither, and an
    engine depends on the contract rather than sitting inside it.

    Reading the source is the cheap guard, run on every change. The
    expensive one is real: the `contract-is-installable-alone` job in CI
    installs the built wheel where the page stack genuinely is not present
    and validates a bundle there.
    """
    declared = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert declared["project"]["dependencies"] == []

    package = REPO_ROOT / "src" / "alteksto"
    modules = sorted(package.rglob("*.py"))
    # The glob finding nothing would pass every assertion below it.
    assert {module.name for module in modules} >= {"__init__.py", "bundle.py"}

    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    # A relative import reaches a sibling in this package
                    # and can reach nothing else, and the glob reads that
                    # sibling on its own turn. Recording it here would
                    # refuse a stdlib-only module the guard has already
                    # cleared.
                    continue
                else:
                    imported.add(node.module.split(".")[0])
        assert imported <= set(sys.stdlib_module_names), (
            module.relative_to(package).as_posix(),
            sorted(imported - set(sys.stdlib_module_names)))


def test_the_cli_reports_and_exits_nonzero(tmp_path, capsys):
    tool = load_script("tools/validate_bundle.py")
    good = make_bundle(tmp_path / "good")
    bad = tmp_path / "bad"
    bad.mkdir()
    assert tool.main([str(good)]) == 0
    assert tool.main([str(good), str(bad)]) == 1
    err = capsys.readouterr().err
    assert "valid" in err and "manifest.json is missing" in err
