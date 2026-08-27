# Stage 4: the walk

The draft is assembled unit by unit against the skeleton. By default
one converter does the whole walk in its own context: it holds
the witnesses, the skeleton, and the growing draft, reads each unit's
page renders itself with independent reads batched into parallel tool
calls, and applies the acceptance checks below to its own units
before appending, recording in its run report anything it had to fix.
Delegation, one subagent per unit under a driver that never reads
pixels, is the fallback for a paper too large for one context; its
machinery is at the end of this file.

## What the walk must handle

Every one of these was observed, not assumed; quality.md holds the full
catalogue.

- **Seams.** Sentences continue across page joins, and whole tables can
  sit interposed at the join in the OCR stream. Begin from the previous
  unit's tail: if the tail ends mid-sentence, the unit opens with its
  completion, floats stepped over. Never re-emit the tail; never lose
  the completion.
- **Running heads, footers, page numbers.** Both witnesses carry them,
  at unstable positions. Learn the paper's header pattern (the strings
  repeat verbatim page to page) and strip by pattern, not position.
  They never enter the draft.
- **Hyphens and invisible characters.** Line-break hyphens in the layer
  are healed by reading; genuine hyphens stay. Soft hyphens and
  zero-width spaces do not survive into the draft. URLs come out whole,
  characters from the layer.
- **Floats.** Where the skeleton places an exhibit in this unit, emit
  its sentinel (format in quality.md) at its reading position. The
  caption is parsed here, by whoever walks this unit, from the
  witnesses like any other unit text: the skeleton's caption identifies the
  exhibit, but its characters are verified against the character source
  before the sentinel is emitted, because the sentinel is what the
  manifest will copy. The exhibit's footnote text is not the draft's
  business: it belongs to the exhibit, and the figure stage transcribes
  it into the manifest's notes. Table content is not transcribed into
  the draft; the crop carries it. Figure-internal text (axis labels,
  in-plot values) is never transcribed into running text.
- **References.** Characters from the character source, entry shape
  from the OCR, one list item per entry, count matched to the
  skeleton's reference_count. High-entropy strings (names, page
  ranges, DOIs, URLs) are exactly the layer's unless the render says
  otherwise. The web witness confirms disputed entries when present.
- **Emphasis.** Carry bold and italic where the layer's emphasis runs
  mark them (quality.md); the runs cover furniture too, which is
  stripped like any furniture. Consult the render only when a run
  looks wrong. A missed run is a minor defect: do not spend pixel
  passes hunting styling.
- **Source oddities.** A witness disagreement often marks a source
  typo. The render settles it; what the page prints, the draft keeps,
  and the report notes it so the sweep does not re-litigate it.

## Acceptance checks before appending

- Heading present at the skeleton's target depth, no extra headings
  invented, none dropped.
- The unit opens where the skeleton's opening words say and closes on
  its closing words (allowing for healed hyphenation).
- No page marker lines, header strings, or witness artefacts in the
  markdown.
- Exhibit sentinels present for exactly the exhibits the skeleton
  places in this unit, with no footnote text beside them (exhibit
  footnotes belong to the figure stage).

In a single-context walk the converter applies these to its own unit
and fixes what fails before appending; a unit it cannot make pass
stops the run loudly. Accepted units are appended to
`work/{id}/draft.md`; the assembled draft becomes the bundle's
text.md at the end of the walk.

## Delegating the walk (fallback)

When a paper outgrows one context, the walk falls back to the delegated
shape: one driver holds the compact text witnesses, the skeleton, and
the growing draft; one subagent per unit reads the page images. The
driver never does. For each unit, in order, the driver prepares the
unit package:

- the unit's skeleton entry (title, target depth, pages, opening and
  closing words, notes);
- the page renders the unit spans (usually one or two);
- the text-layer slice for those pages, cut mechanically from
  blocks.txt at the page marker lines, with the emphasis runs those
  pages carry in blocks.json beside it;
- the OCR slice, the ocr/page_NN.md files for those pages;
- the web.md slice when the witness exists, located by section heading;
- the closing lines of the previous unit as already accepted, so the
  seam joins without overlap or loss;
- the standing rules: the precedence table and the formatting rules
  (20-sources.md and quality.md, summarised in the subagent prompt).

The subagent reconciles the witnesses under precedence with the render
as adjudicator and returns the unit's markdown plus a short report:
disagreements it settled and how, source oddities the render
confirmed, anything it could not read. The driver applies the
acceptance checks above; a unit that fails goes back to its subagent
once with the failure named, and a second failure stops the run
loudly rather than papering over it.

Units may be walked in parallel where their pages do not overlap, but
the seam check happens at append time in order, and any seam repair is
done by the driver asking the later unit's subagent to re-open with the
corrected tail.
