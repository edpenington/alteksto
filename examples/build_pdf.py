#!/usr/bin/env python3
"""Build the worked example's invented mini-paper as {out_dir}/source.pdf.

Every particular is invented: the levels, the herons, the wardens, the
journal, the references, and the counts the statistics are arithmetic on.
No binary is committed, so the PDF is built from this file whenever it is
wanted, by the tests and by anyone running the playbook against the
example.

The paper is small enough to hold in the head and still carries the
hazards the route exists to handle: a running head and a page number on
every page, an author line with affiliation markers, headings at two
depths under the title, italic statistics the text layer marks with real
font flags, a word broken by a line-break hyphen, a table drawn with real
rules whose caption sits outside the crop and whose footnote belongs to
the exhibit, a figure carrying its own printed title and legend inside
the crop, a sentence that begins on page two and finishes on page three,
and a reference list with a DOI in it.

The prose is written once, here, in a two-character markup: a `*` pair
marks an italic run, and `~` marks the point where justification breaks a
word across a line, printing the hyphen. Nothing else is markup, so every
other character reaches the page exactly as written, and
examples/expected/bundle/text.md carries the same strings with the
hyphen breaks healed.

The layout is data before it is a PDF. `layout()` returns the three
sheets as lines, rules, and bars; `build()` draws them. Tests read the
data and hold the expected files against it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

# The page and its one text column, in points.
PAGE_WIDTH, PAGE_HEIGHT = 595.0, 842.0
LEFT, RIGHT = 90.0, 505.0
COLUMN = RIGHT - LEFT

# Base 14 fonts, so the text layer carries genuine italic and bold flags
# and dump_blocks emits the emphasis runs the walk reads.
PLAIN, ITALIC, BOLD = "helv", "tiit", "hebo"
_FONTS = {name: pymupdf.Font(name) for name in (PLAIN, ITALIC, BOLD)}

# The markup: `*` pairs italicise, `~` hyphenates across a line break.
EMPHASIS = "*"
BREAK = "~"

# ---------------------------------------------------------------- the paper

RUNNING_HEAD = "Journal of Invented Wetlands 12(3): 41-58"
PAGE_NUMBERS = ("41", "42", "43")
DOI = "10.5555/invented.2026.0041"
DOI_LINE = f"doi:{DOI}"

TITLE = ("Reed bed management and heron counts on the Marrow Levels: "
         "a three-season warden survey")
AUTHORS = "Ada Quill,1 Bartholomew Reeve,1,2 and Cordelia Marsh2"
AFFILIATIONS = (
    "1 Institute of Invented Wetlands, Fenmouth Field Station, Fenmouth",
    "2 Warden Training College, Saltrush",
)
CORRESPONDENCE = ("Correspondence: Ada Quill, Institute of Invented Wetlands, "
                  "Fenmouth (a.quill@example.invalid).")
ABSTRACT = (
    "We counted grey herons on the invented Marrow Levels across three "
    "seasons to ask whether reed bed management changes how many birds a "
    "warden sees. Twelve stations were walked at dawn on fixed dates, and "
    "counts were compared between cut and uncut compartments. Cut "
    "compartments held more herons in spring and fewer in autumn, and the "
    "seasonal difference was larger than the difference between observers. "
    "Count data of this kind is best read beside the management record for "
    "the same compartment."
)
KEYWORDS = "Keywords: herons, reed beds, wardens, counts, invented data"

INTRODUCTION = (
    "Herons are counted because they are easy to count. A bird standing at "
    "the edge of a reed bed at dawn is visible from the bank, and a warden "
    "with a notebook records it without disturbing the water. What the "
    "count means is harder. Numbers rise and fall with the season, with the "
    "weather, and with reed bed management carried out months earlier. "
    "Reeve *et al.* (1998) reported more herons in cut compartments than in "
    "uncut ones (*p* = 0.03). The compartments in that survey were not "
    "matched, the wardens were not blind to the management history, and no "
    "season other than spring was walked. This paper repeats the comparison "
    "with matched compart~ments, three seasons of counts, and two observers "
    "at every station.",

    "The Marrow Levels are a block of grazing marsh and reed bed held by an "
    "invented trust and walked by six wardens. Management is recorded "
    "compartment by compartment: the date of each cut, the height of each "
    "sluice, and the days on which water was let in or held back. A count "
    "without that record says only how many herons stood in the reeds on "
    "one morning.",
)

STUDY_SITE = (
    "Twelve counting stations were placed on the Marrow Levels, six in "
    "compartments cut in the previous winter and six in compartments left "
    "uncut for at least four years. Stations were at least 400 m apart and "
    "each looked over open water backed by reed. The compartments were "
    "matched in pairs by area and by distance from the tidal sluice, so "
    "that every cut compartment had an uncut neighbour of about the same "
    "size."
)

PROTOCOL = (
    "Each station was walked at dawn on fixed dates in April, July, and "
    "October. The warden stood still for two minutes before counting, then "
    "recorded every heron visible from the station in a single sweep, "
    "including birds in flight over the compartment. Counts were entered on "
    "paper in the field and copied into the invented register the same day.",

    "Two wardens walked each station independently on the same morning, and "
    "their counts were compared before either was entered. Where the two "
    "disagreed by more than two birds the station was walked again the "
    "following week. This happened at three stations, all of them in July, "
    "and in each case the second pair of counts agreed within one bird.",
)

# The unit that crosses the page join: it begins on page two and its last
# sentence finishes on page three.
ANALYSIS = (
    "Counts were summarised as a mean per station and season, and the cut "
    "and uncut means were compared within matched pairs. Because the counts "
    "are small integers and the pairs are few, we report the paired "
    "difference and its spread rather than a model. The spring difference "
    "was the largest of the three (*t* = 3.4, *p* = 0.02), and the autumn "
    "difference was of the opposite sign, a reversal the discussion returns "
    "to. Observer differences were smaller than seasonal differences at "
    "every station, so the counts reported below are station means with no "
    "observer term, and no station was counted at more than one time of day."
)

RESULTS = (
    "Cut compartments held more herons than uncut compartments in spring, "
    "by 1.7 birds per station, and fewer in autumn, by 1.4 birds per "
    "station. The summer difference was close to zero. Figure 1 shows the "
    "spring result pair by pair: the cut station stands above its uncut "
    "neighbour in every pair, and the gap is largest in the third. The two "
    "observers agreed within one bird at 33 of the 36 station visits."
)

DISCUSSION = (
    "Herons follow the water, and the water follows the sluice. A cut "
    "compartment in spring is shallow and open, and a bird standing in it "
    "can be seen from the bank; the same compartment in autumn is grown "
    "over. We read the seasonal reversal as a statement about visibility as "
    "much as about birds."
)

REFERENCES = (
    "Quill, A. and Marsh, C. (2004) Counting herons from the bank: a "
    "warden's handbook. Fenmouth: Institute of Invented Wetlands.",
    "Reeve, B., Quill, A. and Saltrush, D. (1998) Cutting, flooding and "
    "heron abundance on a lowland reed bed. Journal of Invented Wetlands, "
    "6(2), 88–104. doi:10.5555/invented.1998.0088",
    "Sedge, M. (2011) Observer agreement in dawn counts of wading birds. "
    "Warden Training College Reports, 3, 12–19.",
)

# Table 1: caption above the rules, footnote below them and inside the crop.
# The printed label and the caption are held apart because the bundle keeps
# them apart: the label becomes the sentinel's, and the manifest carries the
# caption alone.
TABLE_LABEL = "Table 1."
TABLE_CAPTION = ("Mean heron count per station by season and "
                 "compartment type.")
TABLE_HEADER = ("Season", "Cut", "Uncut", "Difference")
TABLE_ROWS = (
    ("April", "4.8", "3.1", "+1.7"),
    ("July", "2.6", "2.4", "+0.2"),
    ("October", "1.9", "3.3", "-1.4"),
)
TABLE_FOOTNOTE = ("Counts are station means over three dawn visits, "
                  "06:00–08:00. Differences are cut minus uncut.")
TABLE_COLUMNS = (94.0, 250.0, 330.0, 400.0)

# Figure 1: a printed title and a legend, both inside the crop, and a
# caption below it that is not.
FIGURE_TITLE = "Spring counts by matched pair"
FIGURE_LABEL = "Figure 1."
FIGURE_CAPTION = ("Mean heron count at each matched pair of stations in "
                  "spring, cut against uncut.")
FIGURE_AXIS_LABEL = "Matched pair"
FIGURE_LEGEND = ("cut", "uncut")
SPRING_CUT = (5.2, 4.4, 6.0, 3.8, 4.6, 5.0)
SPRING_UNCUT = (3.0, 3.4, 3.2, 3.6, 2.6, 3.0)

PAGE_COUNT = 3

# Supplement A: one page, printed separately from the paper and converted
# as its own thing. It carries the shape the paper's own table does not, a
# group header spanning two columns over a stub column spanning two rows,
# and one cell the survey left empty. Its running head differs from the
# paper's, which is how a reader tells the two documents apart and how the
# walk knows this furniture is not the article's.
SUPPLEMENT_NAME = "supplement_a"
SUPPLEMENT_TITLE = "Supplement A. Station counts by season and compartment"
SUPPLEMENT_HEAD = "Marrow Levels heron survey: supplementary material"
SUPPLEMENT_INTRO = (
    "Counts are given per station rather than pooled, so a reader can see "
    "the spread the means in Table 1 are drawn from. Station 4 was not "
    "walked in autumn because the causeway was flooded.")
SUPPLEMENT_TABLE_LABEL = "Table A1."
SUPPLEMENT_TABLE_CAPTION = ("Heron counts at each station, by season and "
                            "compartment type.")
SUPPLEMENT_GROUPS = ("Spring", "Autumn")
SUPPLEMENT_SUBHEAD = ("Cut", "Uncut")
SUPPLEMENT_STUB = "Station"
SUPPLEMENT_ROWS = (
    ("1", "5.2", "3.0", "1.8", "3.4"),
    ("2", "4.4", "3.4", "2.1", "3.1"),
    ("3", "6.0", "3.2", "2.4", "2.9"),
    ("4", "3.8", "3.6", "", ""),
)
SUPPLEMENT_FOOTNOTE = ("Counts are single dawn visits. Empty cells are "
                       "stations not walked in that season.")
SUPPLEMENT_COLUMNS = (94.0, 190.0, 260.0, 340.0, 410.0)

# ------------------------------------------------------------ the type sizes

HEAD_SIZE = 9.0
TITLE_SIZE, TITLE_LEAD = 15.0, 22.0
AUTHOR_SIZE = 11.0
AFFILIATION_SIZE, AFFILIATION_LEAD = 9.5, 13.0
ABSTRACT_SIZE, ABSTRACT_LEAD = 11.0, 16.0
SECTION_SIZE = 13.0
SUBSECTION_SIZE = 12.0
BODY_SIZE, BODY_LEAD = 12.0, 18.0
CAPTION_SIZE, CAPTION_LEAD = 10.5, 14.0
TABLE_SIZE = 10.0
TABLE_NOTE_SIZE = 9.0
FIGURE_TITLE_SIZE = 11.0
FIGURE_LABEL_SIZE = 9.0
REFERENCE_SIZE, REFERENCE_LEAD = 10.0, 13.5


# ------------------------------------------------------------------ the type

class Line:
    """One printed line: where its baseline sits and what it is made of.

    `pieces` are (text, font name) in printing order, so a line can change
    font inside itself the way an italicised statistic does. `role` says
    what the line is to the conversion: furniture is stripped, front
    matter and body reach text.md, a caption reaches it inside a sentinel,
    and exhibit lines belong to the crop and never to the text.
    """

    def __init__(self, page, x, y, size, role, pieces):
        self.page = page
        self.x = x
        self.y = y
        self.size = size
        self.role = role
        self.pieces = pieces

    @property
    def text(self) -> str:
        return "".join(text for text, _font in self.pieces)

    def __repr__(self) -> str:
        return (f"Line(page={self.page}, y={self.y}, role={self.role!r}, "
                f"text={self.text!r})")


class Sheet:
    """One page, collecting what is printed on it before anything is drawn."""

    def __init__(self, number):
        self.number = number
        self.lines: list = []
        self.rules: list = []
        self.bars: list = []

    def line(self, y, text, *, size, base=PLAIN, role="body", x=LEFT):
        """Place one unwrapped line and return the baseline it sits on."""
        self.lines.append(Line(self.number, x, y, size, role,
                               _pieces(text, base)))
        return y

    def paragraph(self, y, text, *, size, leading, base=PLAIN, role="body",
                  x=LEFT, width=COLUMN, limit=None):
        """Wrap and place a paragraph; see `place` for the return."""
        return self.place(wrap(text, base, size, width), y, size=size,
                          leading=leading, role=role, x=x, limit=limit)

    def place(self, wrapped, y, *, size, leading, role="body", x=LEFT,
              limit=None):
        """Place already wrapped lines from baseline y downwards.

        Returns the next free baseline and the lines that did not fit above
        `limit`, which is how the one unit that spans the page join hands
        its tail to the next sheet.
        """
        remaining = list(wrapped)
        while remaining:
            if limit is not None and y > limit:
                break
            self.lines.append(Line(self.number, x, y, size, role,
                                   remaining.pop(0)))
            y += leading
        return y, remaining

    def rule(self, x0, y0, x1, y1, *, width=0.8):
        """A drawn rule: a table's, or an axis of the figure."""
        self.rules.append((x0, y0, x1, y1, width))


# --------------------------------------------------------------- the markup

def _pieces(text, base=PLAIN):
    """The line's (text, font) pieces, `*` pairs read as italic runs."""
    if text.count(EMPHASIS) % 2:
        raise ValueError(f"unbalanced {EMPHASIS!r} in {text!r}")
    pieces = [(part, ITALIC if index % 2 else base)
              for index, part in enumerate(text.split(EMPHASIS)) if part]
    return _merge(tuple(pieces))


def _merge(pieces):
    """Fuse neighbouring pieces that share a font, so a run is one piece."""
    merged: list = []
    for text, font in pieces:
        if merged and merged[-1][1] == font:
            merged[-1] = (merged[-1][0] + text, font)
        else:
            merged.append((text, font))
    return tuple(merged)


def _words(text, base):
    """The paragraph as (pieces, forced break) words.

    A word is a tuple of pieces because a word can change font inside
    itself: `(*p*` is a plain bracket followed by an italic letter. A word
    carrying the hyphenation marker becomes two words, the first ending in
    the hyphen the page prints and flagged as ending its line.
    """
    words: list = []
    current: list = []
    for chunk, font in _pieces(text, base):
        parts = chunk.split(" ")
        for index, part in enumerate(parts):
            if index and current:
                words.append(tuple(current))
                current = []
            if part:
                current.append((part, font))
    if current:
        words.append(tuple(current))

    broken: list = []
    for word in words:
        head = _hyphenate(word)
        if head is None:
            broken.append((word, False))
        else:
            first, rest = head
            broken.append((first, True))
            broken.append((rest, False))
    return broken


def _hyphenate(word):
    """Split a word at its `~` marker, printing the hyphen; None if none."""
    for index, (text, font) in enumerate(word):
        if BREAK in text:
            head, tail = text.split(BREAK, 1)
            return (word[:index] + ((head + "-", font),),
                    ((tail, font),) + word[index + 1:])
    return None


def _join(words, base):
    """One line's pieces from its words, spaces taking the run's own font.

    The space inside an italic phrase is italic, so `*et al.*` stays one
    emphasis run in the dump rather than arriving as two.
    """
    pieces: list = []
    for index, word in enumerate(words):
        if index:
            before, after = pieces[-1][1], word[0][1]
            pieces.append((" ", before if before == after else base))
        pieces.extend(word)
    return _merge(tuple(pieces))


def _measure(pieces, size):
    return sum(_FONTS[font].text_length(text, fontsize=size)
               for text, font in pieces)


# A little more than the base 14 fonts actually use above and below the
# baseline, so a box drawn from these covers the ink rather than clipping
# it. Good enough to ask whether a crop region holds a line, which is all
# it is for.
ASCENDER, DESCENDER = 1.1, 0.35


def line_box(line):
    """The line's ink box, near enough to test what a crop covers."""
    return (line.x,
            line.y - line.size * ASCENDER,
            line.x + _measure(line.pieces, line.size),
            line.y + line.size * DESCENDER)


def wrap(text, base, size, width):
    """Greedily wrap the marked-up text to the column, one line at a time."""
    lines: list = []
    current: list = []

    def flush():
        line = _join(current, base)
        if _measure(line, size) > width:
            raise ValueError(f"line {line!r} does not fit {width} points at "
                             f"{size} point; shorten the word or the column")
        lines.append(line)

    for word, forced in _words(text, base):
        if current and _measure(_join(current + [word], base), size) > width:
            flush()
            current = []
        current.append(word)
        if forced:
            flush()
            current = []
    if current:
        flush()
    return lines


# --------------------------------------------------------------- the layout

def layout():
    """The three sheets of the paper, as data."""
    two, tail = _page_two()
    return (_page_one(), two, _page_three(tail))


def _furniture(sheet):
    """The running head and the page number, printed on every page."""
    sheet.line(60.0, RUNNING_HEAD, size=HEAD_SIZE, role="furniture")
    number = PAGE_NUMBERS[sheet.number - 1]
    centre = (PAGE_WIDTH - _FONTS[PLAIN].text_length(
        number, fontsize=HEAD_SIZE)) / 2
    sheet.line(780.0, number, size=HEAD_SIZE, role="furniture", x=centre)


def _page_one():
    sheet = Sheet(1)
    _furniture(sheet)
    y, _ = sheet.place(wrap(TITLE, BOLD, TITLE_SIZE, COLUMN), 104.0,
                       size=TITLE_SIZE, leading=TITLE_LEAD, role="front")
    y = sheet.line(y + 12.0, AUTHORS, size=AUTHOR_SIZE, role="front")
    y += 20.0
    for affiliation in AFFILIATIONS:
        y = sheet.line(y, affiliation, size=AFFILIATION_SIZE,
                       role="front") + AFFILIATION_LEAD
    y = sheet.line(y + 18.0, "Abstract", size=SECTION_SIZE, base=BOLD,
                   role="heading")
    y, _ = sheet.paragraph(y + 24.0, ABSTRACT, size=ABSTRACT_SIZE,
                           leading=ABSTRACT_LEAD, role="front")
    y = sheet.line(y + 10.0, KEYWORDS, size=ABSTRACT_SIZE, role="front")
    y = sheet.line(y + 32.0, "1. Introduction", size=SECTION_SIZE, base=BOLD,
                   role="heading")
    y += 24.0
    for paragraph in INTRODUCTION:
        y, _ = sheet.paragraph(y, paragraph, size=BODY_SIZE,
                               leading=BODY_LEAD)
        y += 8.0
    _check_fits(y, 726.0, "page one's introduction")
    # The correspondence note, ruled off at the foot of the page as
    # journals print one. It is front matter, not furniture.
    sheet.rule(LEFT, 730.0, LEFT + 150.0, 730.0, width=0.6)
    sheet.line(744.0, CORRESPONDENCE, size=AFFILIATION_SIZE, role="front")
    sheet.line(780.0, DOI_LINE, size=HEAD_SIZE, role="furniture")
    return sheet


# Where the table sits on page two, and where the prose has to stop.
TABLE_CAPTION_Y = 396.0
TABLE_TOP_RULE_Y = 414.0
TABLE_HEADER_Y = 430.0
TABLE_HEADER_RULE_Y = 438.0
TABLE_FIRST_ROW_Y = 454.0
TABLE_ROW_LEAD = 16.0
TABLE_BOTTOM_RULE_Y = 496.0
TABLE_FOOTNOTE_Y = 512.0
TABLE_RULE_RIGHT = 470.0


def _page_two():
    sheet = Sheet(2)
    _furniture(sheet)
    y = sheet.line(100.0, "2. Methods", size=SECTION_SIZE, base=BOLD,
                   role="heading")
    y = sheet.line(y + 28.0, "2.1 Study site", size=SUBSECTION_SIZE,
                   base=BOLD, role="heading")
    y, _ = sheet.paragraph(y + 24.0, STUDY_SITE, size=BODY_SIZE,
                           leading=BODY_LEAD)
    y = sheet.line(y + 12.0, "2.2 Counting protocol", size=SUBSECTION_SIZE,
                   base=BOLD, role="heading")
    y, _ = sheet.paragraph(y + 24.0, PROTOCOL[0], size=BODY_SIZE,
                           leading=BODY_LEAD)
    _check_fits(y, TABLE_CAPTION_Y, "page two above the table")
    _draw_table(sheet)
    y, _ = sheet.paragraph(TABLE_FOOTNOTE_Y + 26.0, PROTOCOL[1],
                           size=BODY_SIZE, leading=BODY_LEAD)
    y = sheet.line(y + 12.0, "2.3 Analysis", size=SUBSECTION_SIZE, base=BOLD,
                   role="heading")
    # The one unit that spans the page join: what does not fit above the
    # foot of page two opens page three, mid-sentence.
    _, tail = sheet.paragraph(y + 24.0, ANALYSIS, size=BODY_SIZE,
                              leading=BODY_LEAD, limit=750.0)
    if not tail:
        raise ValueError("the analysis paragraph no longer spans the page "
                         "join; the example needs that seam")
    return sheet, tail


def _draw_table(sheet):
    sheet.line(TABLE_CAPTION_Y, f"{TABLE_LABEL} {TABLE_CAPTION}",
               size=CAPTION_SIZE, role="caption")
    sheet.rule(LEFT, TABLE_TOP_RULE_Y, TABLE_RULE_RIGHT, TABLE_TOP_RULE_Y)
    for column, cell in zip(TABLE_COLUMNS, TABLE_HEADER):
        sheet.line(TABLE_HEADER_Y, cell, size=TABLE_SIZE, role="exhibit",
                   x=column)
    sheet.rule(LEFT, TABLE_HEADER_RULE_Y, TABLE_RULE_RIGHT,
               TABLE_HEADER_RULE_Y, width=0.5)
    for index, row in enumerate(TABLE_ROWS):
        for column, cell in zip(TABLE_COLUMNS, row):
            sheet.line(TABLE_FIRST_ROW_Y + index * TABLE_ROW_LEAD, cell,
                       size=TABLE_SIZE, role="exhibit", x=column)
    sheet.rule(LEFT, TABLE_BOTTOM_RULE_Y, TABLE_RULE_RIGHT,
               TABLE_BOTTOM_RULE_Y)
    sheet.line(TABLE_FOOTNOTE_Y, TABLE_FOOTNOTE, size=TABLE_NOTE_SIZE,
               role="exhibit")


# Where the figure sits on page three.
FIGURE_TITLE_Y = 328.0
FIGURE_AXIS_Y = 418.0
FIGURE_AXIS_X = 130.0
FIGURE_RIGHT = 470.0
FIGURE_TICK_Y = 430.0
FIGURE_LABEL_Y = 444.0
FIGURE_CAPTION_Y = 470.0
FIGURE_SCALE = 13.0
FIGURE_PAIR_STEP = 55.0
FIGURE_BAR = 18.0


def _page_three(tail):
    sheet = Sheet(3)
    _furniture(sheet)
    y, _ = sheet.place(tail, 96.0, size=BODY_SIZE, leading=BODY_LEAD)
    y = sheet.line(y + 14.0, "3. Results", size=SECTION_SIZE, base=BOLD,
                   role="heading")
    y, _ = sheet.paragraph(y + 24.0, RESULTS, size=BODY_SIZE,
                           leading=BODY_LEAD)
    _check_fits(y, FIGURE_TITLE_Y, "page three above the figure")
    _draw_figure(sheet)
    y, _ = sheet.paragraph(FIGURE_CAPTION_Y, f"{FIGURE_LABEL} {FIGURE_CAPTION}",
                           size=CAPTION_SIZE, leading=CAPTION_LEAD,
                           role="caption")
    y = sheet.line(y + 16.0, "4. Discussion", size=SECTION_SIZE, base=BOLD,
                   role="heading")
    y, _ = sheet.paragraph(y + 24.0, DISCUSSION, size=BODY_SIZE,
                           leading=BODY_LEAD)
    y = sheet.line(y + 14.0, "References", size=SECTION_SIZE, base=BOLD,
                   role="heading")
    y += 24.0
    for reference in REFERENCES:
        y, _ = sheet.paragraph(y, reference, size=REFERENCE_SIZE,
                               leading=REFERENCE_LEAD)
        y += 6.0
    _check_fits(y, 770.0, "page three's reference list")
    return sheet


def _draw_figure(sheet):
    """A small bar chart with its own printed title, legend, and labels."""
    sheet.line(FIGURE_TITLE_Y, FIGURE_TITLE, size=FIGURE_TITLE_SIZE,
               base=BOLD, role="exhibit", x=FIGURE_AXIS_X)
    # The legend rides on the title's line, to the right of it.
    swatch = FIGURE_RIGHT - 92.0
    for index, label in enumerate(FIGURE_LEGEND):
        top = FIGURE_TITLE_Y - 8.0
        left = swatch + index * 46.0
        sheet.bars.append((left, top, left + 9.0, top + 8.0, index == 0))
        sheet.line(FIGURE_TITLE_Y, label, size=FIGURE_LABEL_SIZE,
                   role="exhibit", x=left + 13.0)
    sheet.rule(FIGURE_AXIS_X, FIGURE_AXIS_Y, FIGURE_RIGHT, FIGURE_AXIS_Y)
    sheet.rule(FIGURE_AXIS_X, FIGURE_AXIS_Y - 6 * FIGURE_SCALE,
               FIGURE_AXIS_X, FIGURE_AXIS_Y)
    for tick in (0, 2, 4, 6):
        label = str(tick)
        width = _FONTS[PLAIN].text_length(label, fontsize=FIGURE_LABEL_SIZE)
        sheet.line(FIGURE_AXIS_Y - tick * FIGURE_SCALE + 3.0, label,
                   size=FIGURE_LABEL_SIZE, role="exhibit",
                   x=FIGURE_AXIS_X - 6.0 - width)
    for index, (cut, uncut) in enumerate(zip(SPRING_CUT, SPRING_UNCUT)):
        centre = FIGURE_AXIS_X + 20.0 + index * FIGURE_PAIR_STEP
        sheet.bars.append((centre - FIGURE_BAR - 1.0,
                           FIGURE_AXIS_Y - cut * FIGURE_SCALE,
                           centre - 1.0, FIGURE_AXIS_Y, True))
        sheet.bars.append((centre + 1.0,
                           FIGURE_AXIS_Y - uncut * FIGURE_SCALE,
                           centre + FIGURE_BAR + 1.0, FIGURE_AXIS_Y, False))
        label = str(index + 1)
        width = _FONTS[PLAIN].text_length(label, fontsize=FIGURE_LABEL_SIZE)
        sheet.line(FIGURE_TICK_Y, label, size=FIGURE_LABEL_SIZE,
                   role="exhibit", x=centre - width / 2)
    width = _FONTS[PLAIN].text_length(FIGURE_AXIS_LABEL,
                                      fontsize=FIGURE_LABEL_SIZE)
    sheet.line(FIGURE_LABEL_Y, FIGURE_AXIS_LABEL, size=FIGURE_LABEL_SIZE,
               role="exhibit",
               x=(FIGURE_AXIS_X + FIGURE_RIGHT - width) / 2)


def _check_fits(y, limit, what):
    """Stop loudly when prose has grown into a float's space.

    `y` is the baseline the next line would take, so the flow has stopped
    clear of the float exactly when it has not reached the float's own
    first baseline.
    """
    if y > limit:
        raise ValueError(f"{what} runs to {y:.0f} points, past the {limit:.0f} "
                         f"the layout leaves it; shorten the prose or move "
                         f"the float")


# ---------------------------------------------------------------- the paper

def _draw(document, sheets) -> None:
    """Put the laid-out sheets on the pages of an open document."""
    for sheet in sheets:
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        for x0, y0, x1, y1, width in sheet.rules:
            page.draw_line((x0, y0), (x1, y1), color=(0, 0, 0), width=width)
        for x0, y0, x1, y1, filled in sheet.bars:
            page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=(0, 0, 0),
                           fill=(0.55, 0.55, 0.55) if filled else (1, 1, 1),
                           width=0.8)
        writer = pymupdf.TextWriter(page.rect)
        for line in sheet.lines:
            x = line.x
            for text, font in line.pieces:
                writer.append((x, line.y), text, font=_FONTS[font],
                              fontsize=line.size)
                x += _FONTS[font].text_length(text, fontsize=line.size)
        writer.write_text(page)


def build(out_dir) -> Path:
    """Write the mini-paper to {out_dir}/source.pdf and return the path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    _draw(document, layout())
    path = out_dir / "source.pdf"
    document.save(path)
    document.close()
    return path


def supplement_layout():
    """The one sheet of Supplement A, as data."""
    sheet = Sheet(1)
    sheet.line(60.0, SUPPLEMENT_HEAD, size=HEAD_SIZE, role="furniture")
    y = sheet.line(96.0, SUPPLEMENT_TITLE, size=SECTION_SIZE, base=BOLD,
                   role="heading")
    y, _ = sheet.paragraph(y + 22.0, SUPPLEMENT_INTRO, size=BODY_SIZE,
                           leading=BODY_LEAD)
    _draw_supplement_table(sheet, y + 30.0)
    return (sheet,)


def _draw_supplement_table(sheet, top) -> None:
    """The spanning-header table, drawn with real rules.

    Two header rows: the group names span the pair of columns under each,
    and the stub head sits beside them across both rows. That is the shape
    a transcription needs colspan and rowspan for, and the shape the
    paper's own table does not have.
    """
    sheet.line(top, f"{SUPPLEMENT_TABLE_LABEL} {SUPPLEMENT_TABLE_CAPTION}",
               size=CAPTION_SIZE, role="caption")
    rule_y = top + 12.0
    sheet.rule(LEFT, rule_y, RIGHT, rule_y)
    group_y = rule_y + 16.0
    sheet.line(group_y, SUPPLEMENT_STUB, size=TABLE_SIZE, role="exhibit",
               x=SUPPLEMENT_COLUMNS[0])
    for index, group in enumerate(SUPPLEMENT_GROUPS):
        sheet.line(group_y, group, size=TABLE_SIZE, role="exhibit",
                   x=SUPPLEMENT_COLUMNS[1 + index * 2])
        # The span rule under each group name, which is what says the name
        # belongs to both columns beneath it rather than to one.
        left = SUPPLEMENT_COLUMNS[1 + index * 2] - 6.0
        right = SUPPLEMENT_COLUMNS[2 + index * 2] + 44.0
        sheet.rule(left, group_y + 5.0, right, group_y + 5.0, width=0.5)
    sub_y = group_y + 16.0
    for index in range(len(SUPPLEMENT_GROUPS) * len(SUPPLEMENT_SUBHEAD)):
        sheet.line(sub_y, SUPPLEMENT_SUBHEAD[index % 2], size=TABLE_SIZE,
                   role="exhibit", x=SUPPLEMENT_COLUMNS[1 + index])
    head_rule_y = sub_y + 6.0
    sheet.rule(LEFT, head_rule_y, RIGHT, head_rule_y, width=0.5)
    for row_index, row in enumerate(SUPPLEMENT_ROWS):
        y = head_rule_y + 16.0 + row_index * TABLE_ROW_LEAD
        for column, cell in zip(SUPPLEMENT_COLUMNS, row):
            if not cell:
                continue  # the survey printed nothing here, so nothing is drawn
            sheet.line(y, cell, size=TABLE_SIZE, role="exhibit", x=column)
    bottom = head_rule_y + 16.0 + len(SUPPLEMENT_ROWS) * TABLE_ROW_LEAD
    sheet.rule(LEFT, bottom, RIGHT, bottom)
    sheet.line(bottom + 14.0, SUPPLEMENT_FOOTNOTE, size=TABLE_NOTE_SIZE,
               role="exhibit")


def build_supplement(out_dir) -> Path:
    """Write Supplement A to {out_dir}/source.pdf and return the path.

    A separate document, because that is what it is: a caller stages it
    under the paper it belongs to and it is converted as its own
    paper-like unit, never folded into the article.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    _draw(document, supplement_layout())
    path = out_dir / "source.pdf"
    document.save(path)
    document.close()
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_pdf.py",
        description="Build the worked example's invented mini-paper as "
                    "{out_dir}/source.pdf, and optionally its "
                    "supplement.",
    )
    parser.add_argument("out_dir", type=Path,
                        help="the directory to write source.pdf into, "
                             "usually a work directory")
    parser.add_argument("--supplement", action="store_true",
                        help="also write Supplement A to "
                             "{out_dir}/supplements/" + SUPPLEMENT_NAME
                             + "/source.pdf, where a staged supplement "
                               "would sit")
    args = parser.parse_args(argv)
    path = build(args.out_dir)
    print(f"build-pdf: {PAGE_COUNT} pages -> {path}", file=sys.stderr)
    if args.supplement:
        # Where a staging tool's --supplement would have put it, so the work
        # directory looks like one a caller staged rather than one this
        # script invented a shape for.
        supplement = build_supplement(
            args.out_dir / "supplements" / SUPPLEMENT_NAME)
        print(f"build-pdf: 1 page -> {supplement}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
