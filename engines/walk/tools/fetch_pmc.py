#!/usr/bin/env python3
"""Fetch a paper's PubMed Central full text as a cross-check witness.

Resolves a DOI to a PMCID through NCBI idconv, fetches the JATS XML
through efetch, converts it to markdown, and writes {work_dir}/web.md.
The web text is an independent witness: the version of record as PMC
holds it, which can legitimately differ from the PDF (preprint against
version of record, reflowed tables). Tables and figures are reduced to
one-line placeholders carrying label, caption, and footnote, because
reflowed cells are not comparable character for character and the OCR is
the structural witness for them.

Outcomes, all loud:

    exit 0, web.md written    the witness is in place
    exit 0, no web.md         the answer is a definitive no: the DOI is
                              not in PMC, or the record is abstract-only;
                              the route continues with one fewer witness
    exit 1                    the question went unanswered: bad inputs, a
                              failed lookup or fetch, unparseable XML, or
                              no contact email

NCBI etiquette: every call sends a contact email and a tool name. The
email arrives as ALTEKSTO_CONTACT_EMAIL, read from the environment first
and then from the .env file at the repository root.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lxml import etree

from alteksto import __version__

# This engine's own helpers, which are not an installed package: only the
# format contract is. These tools run as scripts from the checkout, so the
# repository root goes on the path before the engine imports resolve.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from engines.walk.lib.env import read_var

NCBI_TOOL = "alteksto"
EMAIL_VAR = "ALTEKSTO_CONTACT_EMAIL"
ENV_FILE = REPO_ROOT / ".env"
IDCONV_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# A JATS <body> under this many characters is an abstract-only record in
# body clothing; trusting it would drop most of the paper.
MIN_BODY_CHARS = 1000

_COLLAPSE_WS = re.compile(r"\s+")


def _user_agent(contact_email: str) -> str:
    return f"alteksto/{__version__} ({contact_email})"


def _http_get(url: str, *, contact_email: str, timeout: int = 30) -> bytes:
    request = Request(url,
                      headers={"User-Agent": _user_agent(contact_email)})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def doi_to_pmcid(doi: str, *, contact_email: str) -> str | None:
    """NCBI idconv: DOI to PMCID.

    Returns the PMCID ('PMC1234567'), or None when the DOI is genuinely
    not in PubMed Central. Raises on lookup failure (network, HTTP,
    malformed response); the caller distinguishes a failed lookup from a
    genuine miss by catching the exception.
    """
    url = IDCONV_URL + "?" + urlencode({
        "ids": doi, "format": "json", "tool": NCBI_TOOL,
        "email": contact_email,
    })
    data = json.loads(_http_get(url, contact_email=contact_email))
    record = (data.get("records") or [None])[0]
    return record.get("pmcid") if record else None


def fetch_jats(pmcid: str, *, contact_email: str) -> bytes:
    """efetch JATS XML for a PMCID. Returns raw XML bytes."""
    url = EFETCH_URL + "?" + urlencode({
        "db": "pmc", "id": pmcid.replace("PMC", ""), "rettype": "xml",
        "tool": NCBI_TOOL, "email": contact_email,
    })
    return _http_get(url, contact_email=contact_email, timeout=60)


def _flat_text(el) -> str:
    """All text under an element on one line, whitespace collapsed."""
    return _COLLAPSE_WS.sub(" ", "".join(el.itertext())).strip()


def _spaced_text(el) -> str:
    """All text under an element, one space at every fragment boundary.

    itertext() yields adjacent fragments with nothing between them, so
    structured JATS (an element-citation's name parts, a footnote's
    stacked paragraphs) fuses into "MaloneDFineberg". Joining fragments
    with spaces and collapsing runs keeps words apart at the cost of an
    occasional extra space, which a witness document tolerates. Prose
    keeps using _flat_text, where inline markup must not gain spaces.
    """
    return _COLLAPSE_WS.sub(" ", " ".join(el.itertext())).strip()


def _ref_text(ref) -> str:
    """One reference entry as a line of text.

    A formatted citation (mixed-citation) reads well as it stands. A
    structured one (element-citation) carries no interstitial text, so
    it takes the spaced join. A ref with neither falls back to the
    spaced join of everything but its label, which the caller emits.
    """
    mixed = ref.find(".//mixed-citation")
    if mixed is not None:
        return _flat_text(mixed)
    cite = ref.find(".//element-citation")
    if cite is not None:
        return _spaced_text(cite)
    label = ref.find("label")
    if label is not None:
        parts = [_spaced_text(child) for child in ref
                 if child is not label and isinstance(child.tag, str)]
        return " ".join(part for part in parts if part)
    return _spaced_text(ref)


def _find_text(el, path: str) -> str:
    found = el.find(path)
    return _flat_text(found) if found is not None else ""


def _placeholder(kind: str, el) -> str:
    """One line standing in for a float: label, caption, footnote.

    The web text is trusted least on floats (PMC reflows tables), so the
    cells are dropped and the float keeps only the parts that are
    comparable across witnesses: its identity and its wording.
    """
    label = _find_text(el, "label") or _find_text(el, ".//label")
    caption_el = el.find(".//caption")
    caption = _flat_text(caption_el) if caption_el is not None else ""
    footnote = ""
    for foot_el in el.findall(".//table-wrap-foot"):
        footnote = _spaced_text(foot_el)
        if footnote:
            break
    parts = []
    for piece in (label, caption):
        piece = piece.strip()
        if piece:
            if piece[-1] not in ".!?":
                piece += "."
            parts.append(piece)
    if footnote:
        parts.append(f"Footnote: {footnote}")
    inner = " ".join(parts)
    return f"[{kind.upper()}: {inner}]" if inner else f"[{kind.upper()}]"


def _lead_space(el, parent) -> str:
    """A space when the text right before a float does not end in one.

    A float can sit inside a <p>, so the text preceding it would run
    straight into the placeholder ("... of the analyses.[TABLE: ...").
    """
    previous = el.getprevious()
    before = (previous.tail if previous is not None else parent.text) or ""
    return " " if before and not before[-1].isspace() else ""


def _replace_floats(root) -> None:
    """Swap every <table-wrap> and <fig> for a placeholder <p> in place,
    so a float keeps its position in the reading order wherever JATS put
    it (mid-paragraph, end of section, floats-group)."""
    for kind, tag in (("table", "table-wrap"), ("figure", "fig")):
        for el in list(root.iter(f"{{*}}{tag}")) + list(root.iter(tag)):
            parent = el.getparent()
            if parent is None:
                continue
            placeholder = etree.Element("p")
            placeholder.text = (_lead_space(el, parent)
                                + _placeholder(kind, el))
            placeholder.tail = el.tail or ""
            parent.replace(el, placeholder)


def jats_to_markdown(xml_bytes: bytes) -> str:
    """Convert JATS XML to markdown.

    - the article title becomes `#`, the author line follows it
    - <abstract> becomes `## Abstract`
    - <sec> becomes `## title`, one `#` deeper per nesting level
    - <table-wrap> and <fig> become one-line placeholders (_placeholder)
    - <ref-list> becomes a `## References` list
    """
    root = etree.fromstring(xml_bytes)
    _replace_floats(root)
    articles = root.findall(".//article") or [root]
    out: list[str] = []

    def emit_sec(sec, depth: int = 2) -> None:
        title = _find_text(sec, "title")
        if title:
            out.append(f"{'#' * min(depth, 6)} {title}")
        for child in sec:
            if not isinstance(child.tag, str):
                continue
            tag = etree.QName(child).localname
            if tag == "title":
                continue
            elif tag == "sec":
                emit_sec(child, depth=depth + 1)
            elif tag == "list":
                for item in child.findall("list-item"):
                    out.append(f"- {_flat_text(item)}")
            else:
                text = _flat_text(child)
                if text:
                    out.append(text)

    for art in articles:
        title = _find_text(art, ".//article-meta//article-title")
        if title:
            out.append(f"# {title}")
        authors = []
        for contrib in art.findall(
                ".//article-meta//contrib[@contrib-type='author']"):
            surname = contrib.find(".//surname")
            given = contrib.find(".//given-names")
            if surname is not None:
                name = ((_flat_text(given) + " " if given is not None
                         else "") + _flat_text(surname))
                authors.append(name.strip())
        if authors:
            out.append(", ".join(authors))
        for ab in art.findall(".//article-meta//abstract"):
            out.append("## Abstract")
            for child in ab:
                if not isinstance(child.tag, str):
                    continue
                if etree.QName(child).localname == "sec":
                    emit_sec(child, depth=3)
                else:
                    text = _flat_text(child)
                    if text:
                        out.append(text)
        body = art.find(".//body")
        if body is not None:
            for child in body:
                if not isinstance(child.tag, str):
                    continue
                if etree.QName(child).localname == "sec":
                    emit_sec(child, depth=2)
                else:
                    text = _flat_text(child)
                    if text:
                        out.append(text)
        # JATS allows floats to live in <floats-group> outside <body>. The
        # pre-pass already turned them into placeholder <p> elements, so
        # they only need emitting somewhere.
        floats = art.find(".//floats-group")
        if floats is not None:
            for child in floats:
                if not isinstance(child.tag, str):
                    continue
                text = _flat_text(child)
                if text:
                    out.append(text)
        ref_list = art.find(".//ref-list")
        if ref_list is not None:
            out.append("## References")
            for ref in ref_list.findall(".//ref"):
                label = _find_text(ref, "label")
                body = _ref_text(ref)
                entry = (f"{label} {body}" if label
                         and not body.startswith(label) else body)
                out.append(f"- {entry}")
    return "\n\n".join(part for part in out if part.strip()) + "\n"


def jats_has_body(xml_bytes: bytes) -> bool:
    """True if the JATS XML contains a non-trivial <body>.

    PMC records sometimes carry only abstract and metadata; trusting one
    would drop most of the paper, so a real body is required. Parse errors
    propagate: an unreadable record is a loud failure, not a body-less
    one.
    """
    root = etree.fromstring(xml_bytes)
    body = root.find(".//body")
    if body is None:
        return False
    return len("".join(body.itertext()).strip()) >= MIN_BODY_CHARS


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="fetch_pmc.py",
        description="Fetch the PubMed Central full text for a DOI into "
                    "{work_dir}/web.md, or say loudly why not.",
    )
    parser.add_argument("work_dir", type=Path,
                        help="the paper's work directory")
    parser.add_argument("--doi", required=True,
                        help="the paper's DOI, e.g. 10.1000/invented.2020")
    args = parser.parse_args(argv)

    if not args.work_dir.is_dir():
        print(f"fetch-pmc: not a work directory: {args.work_dir}",
              file=sys.stderr)
        return 1
    contact_email = read_var(EMAIL_VAR, ENV_FILE)
    if not contact_email:
        print(f"fetch-pmc: {EMAIL_VAR} is not set, in the environment or "
              f"in {ENV_FILE}; NCBI etiquette wants a contact email on "
              f"every call, so nothing was sent", file=sys.stderr)
        return 1

    try:
        pmcid = doi_to_pmcid(args.doi, contact_email=contact_email)
    except Exception as exc:
        print(f"fetch-pmc: the PMCID lookup failed ({exc!r}); the web "
              f"witness is unavailable and the route continues with one "
              f"fewer witness", file=sys.stderr)
        return 1
    if not pmcid:
        print(f"fetch-pmc: DOI {args.doi} is not in PubMed Central; the "
              f"route continues with one fewer witness", file=sys.stderr)
        return 0
    try:
        xml = fetch_jats(pmcid, contact_email=contact_email)
    except Exception as exc:
        print(f"fetch-pmc: the JATS fetch for {pmcid} failed ({exc!r}); "
              f"the web witness is unavailable and the route continues "
              f"with one fewer witness", file=sys.stderr)
        return 1
    try:
        has_body = jats_has_body(xml)
    except Exception as exc:
        print(f"fetch-pmc: the JATS XML for {pmcid} failed to parse "
              f"({exc!r}); the web witness is unavailable and the route "
              f"continues with one fewer witness", file=sys.stderr)
        return 1
    if not has_body:
        print(f"fetch-pmc: the PubMed Central record {pmcid} has no "
              f"full-text body (abstract only); the route continues with "
              f"one fewer witness", file=sys.stderr)
        return 0
    try:
        markdown = jats_to_markdown(xml)
    except Exception as exc:
        print(f"fetch-pmc: converting the JATS XML for {pmcid} failed "
              f"({exc!r}); the web witness is unavailable and the route "
              f"continues with one fewer witness", file=sys.stderr)
        return 1

    web_path = args.work_dir / "web.md"
    web_path.write_text(markdown, encoding="utf-8")
    print(f"fetch-pmc: {pmcid} for DOI {args.doi}, {len(markdown)} chars "
          f"-> {web_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
