# Stage 2: acquire the sources

Four witnesses, each with an explicit role and an explicit trust. The
route rests on this table; do not average witnesses or "resolve
discrepancies" freely. When witnesses disagree, the render decides.

| source | role | trust |
|---|---|---|
| text layer (blocks.txt, blocks.json) | authoritative for characters | high when born-digital; void when scanned |
| OCR markdown (ocr/page_NN.md) | authoritative for structure: reading order, headings, tables, equations; its image bboxes seed figure crops | characters plausible but fallible |
| page renders (pages/page_NN.png) | ground truth for adjudication; drive the skeleton; source of figure crops | absolute, and never bulk-transcribed |
| web full text (web.md) | independent prose witness, cross-check only | high, but legitimately different from the PDF |

Acquire all four: the first three always (render, dump, OCR), the web
text opportunistically (`fetch_pmc.py` with the paper's DOI). A DOI that
is not in PMC, an abstract-only record, or a missing DOI means no web
witness: warn loudly, continue, and tell later stages it is absent.
Expect absence often; treat the web witness as a bonus, never a pillar.

## What each witness gets wrong

Learned from measurement, catalogued fully in quality.md; the short
version every stage should hold:

- **The text layer is character-exact and structure-blind.** Reading
  order does not follow the page (front matter after body text, floats
  and captions out of position, running heads anywhere). Tables are
  destroyed: one cell per line, headers interleaved, empty cells vanish
  without trace. Invisible characters are everywhere: soft hyphens at
  line breaks, zero-width spaces inside URLs, sub-visible typesetter
  text that can contradict the visible page. It can even drop a printed
  line silently. But the characters it does carry are exact, including
  the paper's own typos.
- **The OCR is structure-reliable and character-fallible.** Reading
  order, hyphen healing, and table structure are dependably right, and
  table cell values measure accurate. But it silently improves the
  source: typos corrected, words respaced, broken URLs rewritten
  plausibly, marker schemes renumbered. It corrupts high-entropy
  strings: digits in page ranges, author names, URL paths, DOIs. It can
  swap small glyphs with large meaning (a tilde becoming a minus). It
  cannot certify what the page says.
- **The web text, when present, is a character-exact prose witness**
  (it matched the PDF layer to the glyph in measurement, source typos
  included) and is the natural tiebreaker for references. It
  legitimately lacks back matter, keywords, and licenses, holds no
  table data, and may be a different version of the paper. Divergence
  from the PDF is information, not error.

## The precedence rule, sharpened

Characters come from the character source (per triage), structure from
the OCR, and every dispute goes to the render. One addition that
prevents a class of quiet damage: **when two witnesses disagree,
suspect the source is odd before choosing a winner.** The OCR corrects
and the layer preserves, so a disagreement often marks a genuine source
typo. Check the render; if the page prints the oddity, the oddity is
the truth and the bundle keeps it.

High-entropy strings (URLs, DOIs, author names, page ranges, numbers)
have no redundancy to survive OCR noise: for these the character source
wins outright unless the render shows otherwise.
