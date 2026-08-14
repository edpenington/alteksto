#!/usr/bin/env python3
"""Check a text's reference DOIs against the DOI registrar.

This is a conversion-quality canary for the whole text, not a check of
the references for their own sake. References are the hardest text in a
paper to convert: dense, high-entropy strings where errors look
plausible. A DOI that resolves, with a registrar record that reads like
the entry printed around it, is strong evidence that entry survived
conversion character-intact; an unresolved one marks a spot to
adjudicate against the render, remembering that papers misprint their
own references too.

The deterministic part stops at resolution and juxtaposition: each
resolved DOI's registrar record is laid beside the entry as converted,
and judging whether they align is the reading agent's job, because
registrar metadata legitimately differs from printed citations
(abbreviated titles, online-first years) and any threshold would flag
style as damage.

Reads the references section of the given text file, resolves each DOI
through doi.org content negotiation (CSL JSON, registrar-agnostic), and
writes {work_dir}/refs-report.md. Nothing is auto-corrected.

Exit 0 when the question was answered, including "no DOIs to check";
exit 1 when it was not (bad inputs, or network errors left lookups
unanswered).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from alteksto import __version__
from alteksto.env import read_var

EMAIL_VAR = "ALTEKSTO_CONTACT_EMAIL"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DOI_BASE = "https://doi.org/"
CSL_ACCEPT = "application/vnd.citationstyles.csl+json"

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\[\]]+")
_TRAILING_PUNCT = ".,;:!?)]}>\"'"
REFS_HEADING = re.compile(r"^#{1,6}\s+references\b",
                          re.IGNORECASE | re.MULTILINE)

# Pause between registrar calls; politeness, not protocol.
PAUSE_SECONDS = 0.3


def _user_agent() -> str:
    email = read_var(EMAIL_VAR, ENV_FILE)
    contact = f" (mailto:{email})" if email else ""
    return f"alteksto/{__version__}{contact}"


def references_section(text: str) -> str | None:
    """The text from the references heading to the end, or None.

    Anything after the heading is sampled; a stray DOI in back matter is
    harmless to a canary.
    """
    match = REFS_HEADING.search(text)
    return text[match.end():] if match else None


def find_dois(section: str) -> list[str]:
    """Every distinct DOI in the section, trailing punctuation stripped,
    in order of first appearance."""
    found: list[str] = []
    seen: set[str] = set()
    for match in DOI_RE.finditer(section):
        doi = match.group(0).rstrip(_TRAILING_PUNCT)
        if doi.lower() not in seen:
            seen.add(doi.lower())
            found.append(doi)
    return found


def entry_for(section: str, doi: str) -> str:
    """The reference entry holding the DOI: its line, per the one-item-
    per-entry convention of quality.md."""
    for line in section.splitlines():
        if doi in line:
            return line
    return ""


def _resolve(doi: str, timeout: float) -> dict:
    """CSL JSON for a DOI from doi.org content negotiation. Raises
    HTTPError (404/410 mean the DOI does not resolve) or URLError."""
    request = Request(DOI_BASE + doi,
                      headers={"Accept": CSL_ACCEPT,
                               "User-Agent": _user_agent()})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def registrar_record(csl: dict) -> str:
    """The registrar's metadata as one readable citation-shaped line, for
    the reading agent to hold beside the entry as converted."""
    authors = csl.get("author") or []
    names = ", ".join(
        " ".join(part for part in (a.get("family"), a.get("given")) if part)
        for a in authors[:3] if isinstance(a, dict))
    if len(authors) > 3:
        names += ", et al"
    date_parts = (csl.get("issued") or {}).get("date-parts") or []
    year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""
    pieces = [piece for piece in (
        names,
        f"({year})" if year else "",
        csl.get("title") or "",
        csl.get("container-title") or "",
        csl.get("volume") or "",
        csl.get("page") or "",
    ) if piece]
    return ". ".join(pieces) if pieces else "(registrar returned no fields)"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_refs.py",
        description="Resolve the reference DOIs in a text and compare "
                    "registrar metadata against each entry: a conversion "
                    "quality canary.",
    )
    parser.add_argument("work_dir", type=Path,
                        help="the paper's work directory (the report "
                             "lands here)")
    parser.add_argument("--text", type=Path, required=True,
                        help="the text to check, usually the bundle's "
                             "text.md")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="per-lookup timeout in seconds (default 30)")
    args = parser.parse_args(argv)

    if not args.work_dir.is_dir():
        print(f"check-refs: not a work directory: {args.work_dir}",
              file=sys.stderr)
        return 1
    if not args.text.is_file():
        print(f"check-refs: text file missing: {args.text}",
              file=sys.stderr)
        return 1
    text = args.text.read_text(encoding="utf-8")

    report_path = args.work_dir / "refs-report.md"
    lines = [f"# Reference canary: {args.text}", ""]

    section = references_section(text)
    dois = find_dois(section) if section is not None else []
    if section is None or not dois:
        reason = ("no references heading found" if section is None
                  else "no DOIs in the references section")
        lines += [f"Nothing to check: {reason}. The canary says nothing "
                  f"about this paper either way.", ""]
        report_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"check-refs: {reason}; nothing checked -> {report_path}",
              file=sys.stderr)
        return 0

    counts = {"resolved": 0, "unresolved": 0, "unanswered": 0}
    findings: list[str] = []
    for index, doi in enumerate(dois):
        if index:
            time.sleep(PAUSE_SECONDS)
        entry = entry_for(section, doi)
        try:
            csl = _resolve(doi, args.timeout)
        except HTTPError as exc:
            if exc.code in (404, 410):
                counts["unresolved"] += 1
                findings += [
                    f"- unresolved {doi}: HTTP {exc.code}. Either the "
                    f"conversion corrupted the DOI or the paper prints it "
                    f"wrong; adjudicate against the render.",
                    f"  entry: {entry.strip()}", ""]
            else:
                counts["unanswered"] += 1
                findings += [f"- unanswered {doi}: HTTP {exc.code}.", ""]
            continue
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            counts["unanswered"] += 1
            findings += [f"- unanswered {doi}: {exc!r}.", ""]
            continue
        counts["resolved"] += 1
        findings += [f"- resolved {doi}",
                     f"  entry:     {entry.strip()}",
                     f"  registrar: {registrar_record(csl)}", ""]

    summary = (f"{len(dois)} DOI(s) checked: {counts['resolved']} resolved, "
               f"{counts['unresolved']} unresolved, "
               f"{counts['unanswered']} unanswered.")
    lines += [summary, "",
              "Resolution is the deterministic part. Whether each "
              "registrar record reads like its entry is the reading "
              "agent's judgement; the references themselves are not the "
              "point, the conversion of the whole text is.", ""]
    lines += findings
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"check-refs: {summary} -> {report_path}", file=sys.stderr)
    if counts["unanswered"]:
        print(f"check-refs: {counts['unanswered']} lookup(s) went "
              f"unanswered (network); the canary is incomplete",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
