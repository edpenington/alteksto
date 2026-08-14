"""Offline tests for tools/fetch_pmc.py against an invented JATS record.

The HTTP layer is monkeypatched: idconv and efetch answer from canned
bytes, and the tests assert on the routing, the etiquette parameters, the
markdown conversion, and the three loud outcomes (witness, definitive
miss, unanswered question).
"""

import json
from urllib.error import URLError

import pytest

from conftest import load_tool

# Enough invented body text to clear the abstract-only threshold.
BODY_FILLER = ("The invented cohort walked the reed beds each morning and "
               "recorded the water depth beside every nest platform. ") * 20

JATS = f"""<pmc-articleset><article>
  <front><article-meta>
    <title-group>
      <article-title>An invented ledger of reed beds</article-title>
    </title-group>
    <contrib-group>
      <contrib contrib-type="author">
        <name><surname>Heron</surname><given-names>Ana</given-names></name>
      </contrib>
      <contrib contrib-type="author">
        <name><surname>Sluice</surname><given-names>Bo</given-names></name>
      </contrib>
    </contrib-group>
    <abstract><p>An invented abstract of forty herons.</p></abstract>
  </article-meta></front>
  <body>
    <sec><title>Methods</title>
      <p>{BODY_FILLER}</p>
      <sec><title>Counting</title><p>Counts were made at dawn.</p></sec>
      <table-wrap>
        <label>Table 1</label>
        <caption><p>Invented counts by season</p></caption>
        <table><tbody><tr><td>Spring</td><td>40</td></tr></tbody></table>
        <table-wrap-foot><p>Counts exclude the pilot pond.</p></table-wrap-foot>
      </table-wrap>
    </sec>
    <sec><title>Results</title>
      <p>The count fell to twelve.<fig><label>Figure 1</label>
        <caption><p>Invented map of the reed beds</p></caption></fig></p>
    </sec>
  </body>
  <back><ref-list>
    <ref><mixed-citation>Heron A. Invented works. 2020.</mixed-citation></ref>
  </ref-list></back>
</article></pmc-articleset>"""

ABSTRACT_ONLY_JATS = """<pmc-articleset><article>
  <front><article-meta>
    <title-group><article-title>An invented stub</article-title></title-group>
    <abstract><p>Only this abstract exists.</p></abstract>
  </article-meta></front>
</article></pmc-articleset>"""


@pytest.fixture(scope="session")
def fetch_tool():
    return load_tool("fetch_pmc")


@pytest.fixture
def contact_email(monkeypatch):
    monkeypatch.setenv("ALTEKSTO_CONTACT_EMAIL", "test@example.invalid")


def wire(monkeypatch, fetch_tool, *, idconv: dict, jats: str):
    """Point the tool's HTTP layer at canned responses; return the URLs it
    asked for."""
    seen: list[str] = []

    def fake_http_get(url, *, contact_email, timeout=30):
        seen.append(url)
        if "idconv" in url:
            return json.dumps(idconv).encode("utf-8")
        return jats.encode("utf-8")

    monkeypatch.setattr(fetch_tool, "_http_get", fake_http_get)
    return seen


def test_a_found_paper_becomes_web_md(fetch_tool, tmp_path, monkeypatch,
                                      contact_email, capsys):
    wire(monkeypatch, fetch_tool,
         idconv={"records": [{"pmcid": "PMC7654321"}]}, jats=JATS)
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 0
    text = (tmp_path / "web.md").read_text(encoding="utf-8")
    assert "# An invented ledger of reed beds" in text
    assert "Ana Heron, Bo Sluice" in text
    assert "## Abstract" in text
    assert "## Methods" in text
    assert "### Counting" in text
    assert "## References" in text
    assert "- Heron A. Invented works. 2020." in text
    assert "PMC7654321" in capsys.readouterr().err


def test_floats_become_one_line_placeholders(fetch_tool, tmp_path,
                                             monkeypatch, contact_email):
    wire(monkeypatch, fetch_tool,
         idconv={"records": [{"pmcid": "PMC7654321"}]}, jats=JATS)
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 0
    text = (tmp_path / "web.md").read_text(encoding="utf-8")
    assert ("[TABLE: Table 1. Invented counts by season. "
            "Footnote: Counts exclude the pilot pond.]") in text
    # The figure sat mid-paragraph; the placeholder keeps its position and
    # gets a space, not a weld.
    assert ("The count fell to twelve. "
            "[FIGURE: Figure 1. Invented map of the reed beds.]") in text
    # No table cells: the web witness is not trusted on reflowed tables.
    assert "Spring" not in text


def test_ncbi_calls_carry_the_etiquette(fetch_tool, tmp_path, monkeypatch,
                                        contact_email):
    seen = wire(monkeypatch, fetch_tool,
                idconv={"records": [{"pmcid": "PMC7654321"}]}, jats=JATS)
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 0
    assert len(seen) == 2
    for url in seen:
        assert "tool=alteksto" in url
        assert "email=test%40example.invalid" in url


def test_not_in_pmc_is_a_definitive_miss(fetch_tool, tmp_path, monkeypatch,
                                         contact_email, capsys):
    wire(monkeypatch, fetch_tool, idconv={"records": [{}]}, jats=JATS)
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 0
    assert not (tmp_path / "web.md").exists()
    assert "not in PubMed Central" in capsys.readouterr().err


def test_an_abstract_only_record_is_a_definitive_miss(fetch_tool, tmp_path,
                                                      monkeypatch,
                                                      contact_email, capsys):
    wire(monkeypatch, fetch_tool,
         idconv={"records": [{"pmcid": "PMC7654321"}]},
         jats=ABSTRACT_ONLY_JATS)
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 0
    assert not (tmp_path / "web.md").exists()
    assert "abstract only" in capsys.readouterr().err


def test_a_failed_lookup_is_loud_and_unanswered(fetch_tool, tmp_path,
                                                monkeypatch, contact_email,
                                                capsys):
    def broken(url, *, contact_email, timeout=30):
        raise URLError("invented network failure")

    monkeypatch.setattr(fetch_tool, "_http_get", broken)
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 1
    assert "lookup failed" in capsys.readouterr().err


def test_unparseable_jats_is_loud_and_unanswered(fetch_tool, tmp_path,
                                                 monkeypatch, contact_email,
                                                 capsys):
    wire(monkeypatch, fetch_tool,
         idconv={"records": [{"pmcid": "PMC7654321"}]},
         jats="this is not xml")
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 1
    assert "failed to parse" in capsys.readouterr().err


def test_a_missing_contact_email_sends_nothing(fetch_tool, tmp_path,
                                               monkeypatch, capsys):
    monkeypatch.delenv("ALTEKSTO_CONTACT_EMAIL", raising=False)
    monkeypatch.setattr(fetch_tool, "ENV_FILE", tmp_path / "absent.env")
    called = wire(monkeypatch, fetch_tool, idconv={}, jats="")
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 1
    assert "ALTEKSTO_CONTACT_EMAIL" in capsys.readouterr().err
    assert called == []


def test_the_email_reads_from_the_env_file(fetch_tool, tmp_path,
                                           monkeypatch):
    monkeypatch.delenv("ALTEKSTO_CONTACT_EMAIL", raising=False)
    env_file = tmp_path / "invented.env"
    env_file.write_text("ALTEKSTO_CONTACT_EMAIL=file@example.invalid\n",
                        encoding="utf-8")
    monkeypatch.setattr(fetch_tool, "ENV_FILE", env_file)
    seen = wire(monkeypatch, fetch_tool,
                idconv={"records": [{"pmcid": "PMC7654321"}]}, jats=JATS)
    assert fetch_tool.main([str(tmp_path), "--doi", "10.1000/invented"]) == 0
    assert "email=file%40example.invalid" in seen[0]


def test_a_missing_work_directory_fails(fetch_tool, tmp_path, monkeypatch,
                                        contact_email, capsys):
    assert fetch_tool.main([str(tmp_path / "absent"),
                            "--doi", "10.1000/invented"]) == 1
    assert "not a work directory" in capsys.readouterr().err


# Conversion details observed to go wrong on real PMC records: structured
# JATS carries no interstitial text, so naive itertext joins fuse names
# and stacked footnote paragraphs into one run.

STRUCTURED_REF_JATS = """<pmc-articleset><article>
  <front><article-meta>
    <title-group><article-title>An invented stub</article-title></title-group>
  </article-meta></front>
  <back><ref-list>
    <ref>
      <label>1.</label>
      <element-citation>
        <person-group>
          <name><surname>Malone</surname><given-names>D</given-names></name>
          <name><surname>Fineberg</surname><given-names>NA</given-names></name>
        </person-group>
        <article-title>An invented usual care</article-title>
        <source>Invented J</source><year>2021</year>
        <fpage>1</fpage><lpage>9</lpage>
      </element-citation>
    </ref>
  </ref-list></back>
</article></pmc-articleset>"""

STACKED_FOOTNOTE_JATS = """<pmc-articleset><article>
  <body><sec><title>Results</title>
    <table-wrap>
      <label>Table 2</label>
      <caption><p>Invented outcomes</p></caption>
      <table-wrap-foot>
        <p>1 Median (IQR); n (%)</p>
        <p>2 Wilcoxon rank sum test</p>
      </table-wrap-foot>
    </table-wrap>
  </sec></body>
</article></pmc-articleset>"""


def test_structured_references_do_not_fuse(fetch_tool):
    text = fetch_tool.jats_to_markdown(STRUCTURED_REF_JATS.encode("utf-8"))
    assert ("- 1. Malone D Fineberg NA An invented usual care "
            "Invented J 2021 1 9") in text
    assert "MaloneD" not in text


def test_stacked_table_footnotes_do_not_fuse(fetch_tool):
    text = fetch_tool.jats_to_markdown(STACKED_FOOTNOTE_JATS.encode("utf-8"))
    assert "Footnote: 1 Median (IQR); n (%) 2 Wilcoxon rank sum test]" in text
    assert "(%)2 Wilcoxon" not in text
