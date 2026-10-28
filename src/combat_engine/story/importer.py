"""Getting an adventure you own out of a PDF and into a shape worth filling in.

The first half of a **hybrid** pipeline, and the division is Camille's call:
this extracts mechanically, a session fills in by hand. #789.

## Why not a parser

The obvious thing is to parse the PDF into a module. The module now in
`modules/` says why not, in one data point: it has twenty combat encounters
and **one of the twenty headings is misspelled**. A regex drops that encounter
silently and reports nineteen; nobody notices until the campaign skips a fight
three hours in. A reader does not make that mistake, and no amount of
tightening the pattern generalises to the next publisher's layout or the next
edition's vocabulary.

So this does the part a machine is better at -- splitting 154 pages into files,
pulling the embedded outline, and working out which pages each section spans --
and writes a brief asking for the part a machine is worse at. It also pulls
the adventure's italicised boxed text into `read-aloud.json` -- the half of
an adventure already written for the player, which plain extraction flattens
into the DM's prose and loses.

## What the outline buys

It is worth pulling separately from the text because a well-made PDF has the
structure already. That module's outline has **261 entries** in exactly the
shape the schema wants: chapter, then session, then encounter, with the same
five subsections under every encounter. `draft` turns it into a scene graph
with the ids, kinds, chapters and page ranges filled in and the prose left
blank, so the hand-written half is description and judgement rather than
transcription.

A PDF with no outline gets an empty draft and a brief that says so. That is a
worse starting point and still a working one.

## None of it is ours

Everything written here lands under `modules/<id>/`, which is git-ignored.
The pages are the publisher's prose, the draft carries their section titles,
and the brief quotes neither. This module writes files; it never puts any of
it anywhere a commit could reach.
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from combat_engine.db import ROOT

from .module import COMPLEXITY, DIFFICULTY, KINDS, RANKS, ROLES

#: Where an imported module lives. Git-ignored.
MODULES = ROOT / "modules"

#: An encounter heading. Tolerant on purpose -- see the module docstring: the
#: module in hand misspells one of its own. Used to *suggest* a scene kind in
#: the draft, never to decide anything, so a miss costs a hint and not a scene.
_ENCOUNTER = re.compile(r"^enc\w*t\w*r\s+([\w-]+)", re.I)
_CHALLENGE = re.compile(r"^skill\s+challenge\b", re.I)
_SESSION = re.compile(r"^session\s+(\d+)", re.I)
_CHAPTER = re.compile(r"^chapter\s+(\w+)", re.I)
_REST = re.compile(r"^rest(ing)?\b", re.I)


@dataclass
class Heading:
    """One outline entry: what it is called, how deep, and where it starts."""

    title: str
    depth: int
    page: int


def _slug(text: str, fallback: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return out[:48] or fallback


def read_outline(reader: object) -> list[Heading]:
    """Flatten a PDF's embedded outline, keeping the nesting depth."""
    found: list[Heading] = []

    def walk(items: object, depth: int) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            title = str(item.get("/Title", "")).strip()
            try:
                page = int(reader.get_destination_page_number(item))
            except Exception:
                page = -1
            if title:
                found.append(Heading(title=title, depth=depth, page=page))

    try:
        walk(reader.outline, 0)
    except Exception:
        return []
    return found


def kind_of(title: str) -> str:
    """The scene kind a heading suggests. `""` when it suggests none."""
    if _CHALLENGE.search(title):
        return "skill_challenge"
    if _ENCOUNTER.match(title.strip()):
        return "combat"
    if _REST.match(title.strip()):
        return "rest"
    if _SESSION.match(title.strip()) or _CHAPTER.match(title.strip()):
        return "roleplay"
    return ""


#: Shortest italic block worth calling read-aloud.
#:
#: An adventure sets three different things in italics and only one of them
#: is boxed text: the running head on every page, a power's one-line flavour
#: in a stat block ("Frigid water washes out, chilling all it touches."), and
#: the thing we want. Length separates them cleanly -- the real boxed text on
#: the module in hand runs 400-2,800 characters and the impostors run 20-65.
READ_ALOUD = 150


#: An x gap wider than this starts a new column.
#:
#: The module in hand sets boxed text in two columns whose line starts sit at
#: x=53.9 and x=316.4 -- a gutter of 262 -- and every other gap on the page
#: is a word space. Anything in the low hundreds separates the two cleanly.
GUTTER = 120


#: Trademark and copyright marks, and how many make a block the publisher's
#: own voice rather than the adventure's.
#:
#: Two. A credits line carries a mark per product named and the module in
#: hand prints three in 153 characters; the adventure's prose carries none in
#: 2,800. **This deliberately matches on the marks and not on the products
#: they follow**, because the products are names and a name must not enter a
#: tracked file -- the root `CLAUDE.md` rule applies to a filter pattern as
#: much as to a column.
CREDIT_MARKS = re.compile(r"[™®©]")
CREDIT_MARKS_MIN = 2


#: A page that grants permission to photocopy itself is a handout.
#:
#: The phrase is boilerplate rather than a name, which is what makes it
#: usable here. It marks the pre-generated character sheets and the rules
#: primer at the back of the module in hand -- pages 124, 125 and 131 --
#: whose italics are long enough to pass `READ_ALOUD` and are not prose.
HANDOUT = re.compile(r"permission is granted to photocopy", re.I)


def read_aloud(page: object) -> list[str]:
    """The italicised boxed text on one page: what the DM reads out.

    **This is the half of an adventure written for the player**, and nothing
    was pulling it. `extract` wrote `page.extract_text()`, which flattens
    every font to one plain string, so the one passage on the page that is
    already player-facing arrived indistinguishable from the DM's prose
    around it. Chapter 1 was then authored by paraphrasing the DM's text --
    both worse writing and the wrong voice, when the adventure had written
    the right words and the only signal saying so was being discarded.

    Three things have to be undone to read it back, and each was found by
    getting the output wrong:

    * **Every line is drawn twice**, at the same baseline and the same
      offset, so a naive join gives "Redolent with the smell of swamp,
      Redolent with the smell of swamp". Keying by `(y, x)` collapses the
      duplicate onto itself.
    * **Two columns interleave.** Sorting a row's runs by x alone reads
      straight across the gutter and produces a sentence from one column
      spliced into a sentence from the other -- which looked like prose and
      was gibberish. Columns are separated first, by `GUTTER`.
    * **Runs arrive in draw order.** Baseline descending, then x.

    Blocks split where the baseline jumps more than a line's height, so two
    boxes in one column stay apart.

    ## Two things that are italic and are not the adventure

    `READ_ALOUD` was the only filter and it is a length proxy, so two kinds
    of long italic block came through. **Neither is the one #909 was filed
    about** -- that issue says a stat block's power flavour concatenates
    into something long enough to pass, and a probe over the 80 blocks in
    hand found no such block at all. What it found instead:

    * **a credits line**, 153 characters, *identical on three pages*, naming
      the publisher's products. `CREDIT_MARKS`.
    * **the pre-generated character sheets and the rules primer** at the
      back, which are hundreds of characters of italic explaining what an
      ability score is. `HANDOUT`, which drops the whole page.

    Dropping a whole page is the bigger hammer and it is the right one: a
    page offering itself for photocopying is a form, and a form has no boxed
    text on it. The cost if a publisher ever puts a player's letter on such
    a page is that the letter is lost, which is recoverable by hand; the
    cost of keeping these is that they reach an authoring brief as the
    adventure's own words, which is not.

    Repetition looked like the cleaner signal and **is wrong**: three blocks
    repeat across pages here and one of them is a real item description,
    printed twice because the item appears twice.
    """
    runs: list[tuple[float, float, str]] = []

    def visit(text: str, _cm: object, tm: list, font: dict, _size: object) -> None:
        if not font or "Italic" not in str(font.get("/BaseFont", "")):
            return
        if text.strip():
            runs.append((round(tm[5], 1), round(tm[4], 1), text))

    page.extract_text(visitor_text=visit)
    if not runs:
        return []

    # Column bands: sorted x starts, cut wherever the gap is a gutter.
    xs = sorted({x for _, x, _ in runs})
    edges = [xs[0]]
    for near, far in pairwise(xs):
        if far - near > GUTTER:
            edges.append(far)

    def column(x: float) -> int:
        return max(i for i, edge in enumerate(edges) if x >= edge)

    cells: dict[tuple[int, float], dict[float, str]] = {}
    for y, x, text in runs:
        cells.setdefault((column(x), y), {})[x] = text

    out: list[str] = []
    for col in range(len(edges)):
        lines = [
            (y, "".join(cells[(col, y)][x] for x in sorted(cells[(col, y)])).strip())
            for (c, y) in sorted(cells, key=lambda k: -k[1]) if c == col
        ]
        block: list[tuple[float, str]] = []
        last: float | None = None
        for y, line in lines:
            if last is not None and abs(last - y) > 20 and block:
                out.append(_paragraphs(block))
                block = []
            block.append((y, line))
            last = y
        if block:
            out.append(_paragraphs(block))
    # The handout test reads every block, not only the long ones: the
    # permission line is one short sentence and is the thing that identifies
    # the page, so filtering by length first would throw away the evidence.
    if any(HANDOUT.search(b) for b in out):
        return []
    return [
        _mend(b) for b in out
        if len(b) >= READ_ALOUD
        and len(CREDIT_MARKS.findall(b)) < CREDIT_MARKS_MIN
    ]


#: A line this much shorter than the column's measure may end a paragraph.
SHORT = 0.85


def _paragraphs(block: list[tuple[float, str]]) -> str:
    """Put the paragraph breaks back, from where the lines run short.

    **The box is set justified with no indent** -- every line in it starts at
    the same x -- so the only thing left saying where a paragraph ended is
    that its last line does not reach the measure. Without this the opening
    read-aloud arrives as one 986-character wall, which is legible on a page
    and is not legible in a terminal.

    Length alone is not enough and says so twice on the first page tried.
    One line describing a character runs 50 characters against a 65
    measure and **begins** a paragraph; another opening a list of tasks
    does the same. Both are short because the font is
    proportional and character count is a poor proxy for width.

    What separates them is punctuation: a line that *ends* a paragraph ends a
    sentence. Short **and** closing is right on all nine real breaks on that
    page and rejects both impostors.
    """
    widest = max(len(line) for _, line in block)
    paras: list[list[str]] = [[]]
    for _, line in block:
        paras[-1].append(line)
        short = len(line) < widest * SHORT
        if short and line.rstrip().endswith((".", "?", "!", "\u201d", '"')):
            paras.append([])
    return "\n\n".join(
        " ".join(" ".join(p).split()) for p in paras if any(p)
    )


def _mend(text: str) -> str:
    """Undo what the typesetter did to words, as far as is safe.

    **Only the unambiguous half.** A hyphen with a space after it inside a
    word is always a line break -- "apart- ment", "vis- ible", "scoun-
    drels" -- because a real hyphenated compound has no space, so joining is
    safe and there is no English word it damages.

    **The `fl` ligature is left alone, deliberately.** It comes out as two
    characters with a space between them -- "f loor", "half ling", "f lash"
    -- and the obvious rule, join "f l" into "fl", also turns "of large"
    into "oflarge" and "if left" into "ifleft". There is no way to tell the
    two apart from the text alone, and silently corrupting a correct phrase
    to fix a broken one is the worse trade. The author sees it and fixes it
    by hand; `BRIEF.md` says to look for it.
    """
    return re.sub(r"(\w)- (\w)", r"\1\2", text)


def extract(pdf: Path, into: Path) -> tuple[int, list[Heading]]:
    """Split a PDF into per-page text files and pull its outline.

    Returns the page count and the outline. Raises `SystemExit` with the
    install line when `pypdf` is absent, because that is a setup problem and
    not a bug.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit(
            "reading a PDF needs pypdf, which is an optional dependency.\n"
            "Run: uv sync --extra modules\n"
            "Or convert the adventure to .txt or .md yourself and pass that "
            "instead -- the rest of the import does not care which it was."
        ) from None

    reader = PdfReader(str(pdf))
    pages = into / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    boxed: dict[str, list[str]] = {}
    for i, page in enumerate(reader.pages):
        (pages / f"{i:04d}.txt").write_text(page.extract_text() or "")
        found = read_aloud(page)
        if found:
            boxed[str(i)] = found
    (into / "read-aloud.json").write_text(
        json.dumps(boxed, indent=2, ensure_ascii=False) + "\n")
    outline = read_outline(reader)
    (into / "outline.json").write_text(
        json.dumps(
            [{"title": h.title, "depth": h.depth, "page": h.page} for h in outline],
            indent=2,
        )
        + "\n"
    )
    return len(reader.pages), outline


def extract_text(source: Path, into: Path) -> tuple[int, list[Heading]]:
    """The same, for an adventure that is already text. No outline to pull."""
    pages = into / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    (pages / "0000.txt").write_text(source.read_text(errors="replace"))
    (into / "outline.json").write_text("[]\n")
    return 1, []


def _unsummarise(scenes: list[dict]) -> tuple[list[dict], list[str]]:
    """Drop the scenes an adventure's summary section invents.

    An adventure opens by listing every session by name, and the heading
    walk makes a scene out of each of those as well as out of the real
    section later in the book. On the module in hand that was **10 of 65**
    -- and the cost is not tidiness: a converter can fill in the summary
    copy, whose `_pages` points at a one-page overview with none of the
    detail, and the result **validates and plays**, just thinly. The
    phantom also sits in the middle of the graph, so the party walks
    through a scene that is a table of contents.

    **For a duplicated title, the later copy is the real one.** Checked
    against the module before being relied on: the first copies start on
    pages 8, 9 and 34, and every scene starting on 8 or 9 is a duplicate,
    as are 4 of the 6 on 34 -- those are the summary pages. Two signals I
    tried first do not work. Width does not: `session-2` has both copies
    one page wide. Nor does "the wider one is real": one pair runs (34,35)
    then (36,36), with the *summary* copy wider.

    A real adventure that revisits a location under the same heading would
    lose the first visit here. That is why the names are returned rather
    than discarded -- `BRIEF.md` prints them, and restoring one is an edit
    to the draft. A silently shorter list reads as "the adventure has 55
    scenes", which is a different claim from "we removed 10 we believe are
    duplicates".
    """
    seen: dict[str, int] = {}
    for i, scene in enumerate(scenes):
        seen[scene["id"]] = i
    kept = [s for i, s in enumerate(scenes) if seen[s["id"]] == i]
    dropped = sorted({s["name"] for i, s in enumerate(scenes)
                      if seen[s["id"]] != i})
    return kept, dropped


def draft(module_id: str, outline: list[Heading], total_pages: int) -> dict:
    """A scene graph from the outline, with every judgement left blank.

    Only headings that suggest a kind become scenes; the rest become the
    `pages` hint on whichever scene they fall under, which is what tells the
    reader where to look. Scenes are chained in document order, because that
    is the order a published adventure is written in and a converter correcting
    one edge is doing less work than one drawing the whole graph.
    """
    scenes: list[dict] = []
    chapter = ""
    for i, head in enumerate(outline):
        if _CHAPTER.match(head.title.strip()):
            chapter = head.title.strip()
        kind = kind_of(head.title)
        if not kind:
            continue
        ends = next(
            (h.page for h in outline[i + 1:] if kind_of(h.title) and h.page > head.page),
            total_pages,
        )
        scene: dict = {
            "id": _slug(head.title, f"scene-{len(scenes)}"),
            "kind": kind,
            "name": head.title.strip(),
            "chapter": chapter,
            "sets": "",
            "brief": "",
            "_pages": f"{head.page}-{max(ends - 1, head.page)}",
            "exits": [],
        }
        if kind == "combat":
            scene |= {"difficulty": "standard", "terrain": [], "foes": [], "tactics": ""}
        elif kind == "skill_challenge":
            scene |= {
                "complexity": 1, "level": 0,
                "primary": [], "secondary": [], "secondary_grants": "bonus",
                "on_success": "", "on_failure": "",
            }
        elif kind == "rest":
            scene |= {"extended": False}
        scenes.append(scene)

    scenes, phantom = _unsummarise(scenes)

    for a, b in itertools.pairwise(scenes):
        a["exits"] = [b["id"]]

    return {
        "id": module_id,
        "_dropped": phantom,
        "edition": "",
        "party_level": 1,
        "party_size": 5,
        "start": scenes[0]["id"] if scenes else "",
        "flags": {},
        "scenes": scenes,
    }


BRIEF = """# Converting `{module_id}`

`{pages}` pages of text are in `pages/`, one file per page. The PDF's own
outline is in `outline.json`. A skeleton with the ids, kinds and page ranges
already filled in is in `module.draft.json` -- **{scenes} scenes** found.
{dropped}

Your job is to turn the draft into `module.json`. Read the pages a scene
covers (its `_pages` hint) and fill in what a machine could not.

Then: `uv run scripts/play.py --validate modules/{module_id}/module.json`

It reports every problem at once and prints the whole of any closed
vocabulary you miss, so you should not need this file to look a word up.

## What to fill in

**Every scene** -- two descriptions, and getting them the wrong way round is
the most expensive mistake available in this file.

* `sets` is **what a character standing there can see, hear and be told.**
  This is the one that gets printed and the one the party's own companions
  are given.

  **Look in `read-aloud.json` before writing a word of it.** An adventure
  sets its player-facing boxed text in italics, and the import pulls every
  such block out, keyed by page -- so for most scenes the right `sets` is
  already written, by the people who wrote the adventure, in the voice it
  is meant to be read in. Match it to the scene by `_pages`. On the module
  in hand that covered **11 of 15** scenes in the first chapter.

  The first pass at this file did not have that, and chapter 1 was authored
  by paraphrasing the DM's prose instead: worse writing, wrong voice, and
  one brief that spanned a whole session so the party discussed a cave they
  had not reached. Paraphrase only where there is no box.

  Two things to fix by hand when you copy a block. The `fl` ligature comes
  out split -- "f loor", "half ling", "f lash" -- and is left that way on
  purpose, because the rule that joins it also turns "of large" into
  "oflarge". And a page with two boxes gives you two blocks: check you took
  the right one.
* `brief` is **what the DM needs to run it**, which is usually the page as
  written: who is lying, what they actually want, what is waiting in the
  next room.

A page of an adventure is written for the DM, so copying it into `brief`
alone is the natural thing to do -- and then `sets` falls back to it and the
scene opens by printing the plot. That is not hypothetical: the first chapter
of the first module converted here began by announcing that its friendly
patron served a dark god and meant to set two enemies on each other, before
anybody had spoken a line. Write both, every time.

`name` is already set from the heading; fix it if the heading was a label
rather than a title. Correct `exits`: the draft chains scenes in document
order, which is right for a linear adventure and wrong wherever the adventure
branches.

**Describe every recurring character with `looks`.** Scene text does not
travel: the adventure described one NPC in the opening read-aloud, and three
scenes later the DM saw only that scene's prose -- somebody else's speech --
so it had nothing to go on and wrote *"Orsa nodded slightly, her eyes
downcast"*, twice, for a man the player had read described one scene
earlier. `voice` is how they speak and was never meant to carry this.

**One entry per person, even when the page serves them as a pair.** Two
servants under one `npcs` entry read naturally and then broke three things
that reason by name: the DM is offered the cast as an enum when choosing
who answers, `looks` describes one person, and any check asking "is this
name in the scene" cannot match half of a conjunction -- which reported
eight false leaks against a clean playthrough.

**One name per character, and the page's own.** A character who appears in
two scenes must carry the same `name` in both, taken from the adventure's
text. Written with role words instead -- "the friar", "the spy" -- a player
dined with a named host and then spoke to "the friar" in the very next
scene, and "the friar" was ambiguous on top, because the read-aloud gives
that title to a different character entirely.

There is **no gate for this**: an NPC's name being findable in the scene's
own prose passes for every entry in the module, since "friar" and "spy" are
in the text as role words. It is on the author to read across scenes.

**A combat scene** -- `foes` is the important part, one entry per line of
opposition:

    {{"count": 4, "name": "<what the page calls it>", "words": ["..."],
      "role": "skirmisher", "rank": "standard"}}

`name` is what does the work. If the adventure is 4e, the name almost always
resolves straight to a written creature -- measured on the module in hand,
39 of 39 did -- and nothing else in the entry is consulted. Write it exactly
as the page prints it, singular or plural, either is fine.

`words`, `role` and `rank` are the fallback for when it does not resolve, which
is every adventure from another edition. `words` are what the creature *is*:
origin, type, keywords. They are matched against the database first and used to
reflavour something of the right shape second, so write what you would tell a
player, not a mechanic.

Also set `difficulty` ({difficulty}) from how the page pitches the fight, or
`xp` if it states a number outright. `terrain` takes only: {terrain}.
`tactics` is the page's own guidance and is carried for the DM to read.

**A skill challenge** -- `complexity` {complexity_lo}-{complexity_hi}, and
`primary`/`secondary` from the skills the page lists. Only these are skills:

{skills}

**List every primary skill the page lists and do not trim them.** This is the
single thing that decides whether a challenge is playable: with two primaries
a challenge the party is ill-suited to is a cliff, and with four or five that
span a party it is a ladder. Measured on the fixture, the win rate by
complexity went from 82/17/7/5/2 percent to 100/55/37/15/7 on that change
alone.

`secondary_grants` is `bonus` (a secondary success is +2 to the next primary
check) or `success` (it counts outright). Default `bonus`; use `success` only
where the page plainly says a secondary check earns one.

`on_success` and `on_failure` are scene ids. Leave both empty if the adventure
carries on regardless.

**A roleplay scene** -- this is where the adventure actually gets played, so
it needs two things the page will give you if you look for them.

`npcs` is who is there to talk to:

    {{"name": "the friar", "wants": "the party to take the job and not ask
      who benefits", "voice": "warm, generous, never hurried",
      "knows": ["the informant was taken openly, which reads as bait",
                "he will pay a healing poultice each"],
      "hides": ["he serves a snake god", "he wants the banker destroyed"]}}

`knows` is what they may say out loud. **`hides` is never shown to the model
at all** -- it is recorded so the thing stays written down and so a later
scene can move it into `knows`, not so the model can be told to keep a
secret. A small model given a secret and told not to tell it is one unlucky
sample away from telling it.

`affordances` is what a character can *try* here.

**Write `what` in the words a player would type**, not as a label and not
as a note to yourself. It is the only text the matcher sees. A scene once
ran four beats with every intent unmatched -- "go to bed", three times --
because the affordance to leave read "take the rooms and go, blind or
otherwise", and "blind or otherwise" is a distinction the DM has and the
player does not. Two or three phrasings separated by semicolons is normal.

**Check the transitions hardest.** Ending a scene is the thing most
naturally written from outside it, and in the first chapter converted here
all five were wrong that way.

The shape:

    {{"id": "read-friar", "what": "study him for signs he is hiding
      something", "skill": "insight", "band": "hard",
      "win": "he is holding something back about the banker",
      "lose": "nothing, and he notices the staring",
      "once": true, "leads_to": ""}}

This is the single most important thing you will write, and it is worth
knowing why. The model is **not** asked to decide what needs a check -- asked
to do that it got one of three right and called "ask a willing host a
question" an intimidate check. It is asked to *match* a declared intent
against this list or to "none", which it did 3 of 3 at temperature 0. So the
quality of the scene is the quality of this list.

Write one per thing the page says a character could attempt. `what` is a
sentence a reader would recognise, not a label -- the matcher compares an
intent against *that*, never against the id. `win` and `lose` are the only
facts the DM may state afterwards, so write them as facts rather than as
outcomes: "he names the two guards on the stair", not "the party learns
more". `skill` only where there is real uncertainty; a thing a character can
simply do gets no skill and still belongs in the list, because it tells the
model that doing it is a thing this scene supports.

`lore` is what a character may **already know**, rolled for when the scene
opens. Nobody declares it; everyone rolls their own check and whoever passes
learns it -- the player hears it directly, a companion tells them.

    {{"fact": "the jewel was stolen from the temple long ago",
      "skill": "history", "dc": 15}}

**This is the single easiest thing to harvest and the page has it in bulk.**
An adventure writes a skill heading and hangs numbered facts off it:

    History
      DC 12: <fact>
      DC 15: <fact>
      DC 19: <fact>

Measured on the module in hand: **78 of its 143 DC sites gate a fact** like
this rather than an action, and most are in exactly that ladder form. Copy
the sentence, take the skill from the heading above, take the number.

**Gate it with `after` when the page gates it.** An adventure usually says
how knowledge is come by -- *"checks around the taverns that evening"* -- and
that is a condition, not decoration. Name the affordance that earns it:

    {{"fact": "...", "skill": "streetwise", "dc": 12,
      "after": "check-his-reputation"}}

Without it, every row fires the moment the scene opens. Authored that way,
the eight tavern facts arrived as eight stacked "You know:" lines before the
player had typed a word -- an exposition dump, and in the wrong place, since
the party had not gone anywhere to ask.

**Use the printed DC, not a band.** `dc` wins; `band` is the fallback for a
page that stated no number. Bands are lossy -- this adventure prints 15s,
and at level 1 the bands are 8, 12 and 19, so translating cost two facts a
rounding up to hard.

A fact is read out to a player, so write it as the thing that is true, not
as the page's instruction to the DM. The page says *"the character discovers
that the host has a stellar reputation"*; the fact is *"the host has a
stellar
reputation"*.

**And nothing you need withheld goes here.** With five characters rolling,
an easy row is known 100% of the time and a moderate one 97-100%; only hard
is a real question. A band cannot keep a secret. A fact that must stay out
of reach belongs to an NPC's `knows`, or behind an affordance.

`leads_to` on an affordance ends the scene and goes there -- use it for the
one that moves the story on. `max_beats` (default 6) is the backstop when
nothing does.

**A rest scene** -- `extended: true` only for a full night. Five minutes is
`false`.

**The module** -- `party_level`, `party_size`, `edition`, and `start` if the
adventure does not open at its first scene. `flags` are any campaign-level
resources it counts: `{{"renown": 0}}`.

## What to leave out

`_pages` is a note to you and is ignored by the loader. Delete the key or
leave it; either is fine.

Do not invent mechanics the page does not state. A creature you cannot find a
word for gets `words: []` and is fielded on role and rank alone -- that is
working as intended, not a gap.

**Only roles are {roles}, and only ranks are {ranks}.** Role is a preference
and never excludes a creature, so guess it if the page implies one.
"""


def _dropped_note(dropped: list[str]) -> str:
    if not dropped:
        return ""
    rows = "\n".join(f"* {name}" for name in dropped)
    return (
        f"\n**{len(dropped)} scene(s) were dropped as duplicates** of a "
        "later section -- an adventure's summary lists every session by "
        "name and the heading walk makes a scene out of each. The copy on "
        "the later pages was kept. If one of these is a real scene the "
        "party visits twice, add it back:\n\n" + rows + "\n"
    )


def write_brief(into: Path, module_id: str, pages: int, scenes: int,
                dropped: list[str] | None = None) -> Path:
    """The instructions a session reads before filling the draft in.

    `dropped` names the scenes `_unsummarise` removed. **Printed, never
    implied**: a shorter list on its own reads as "the adventure has this
    many scenes", which is a different claim from "we removed these
    because we believe they are duplicates", and the second is the one
    that is true. If one of them is a real scene, restoring it is an edit
    to the draft and the author has to be able to see it was taken.
    """
    from combat_engine.engine.cast import TERRAIN_WORDS
    from combat_engine.engine.skills import SKILLS

    listed = sorted(SKILLS)
    text = BRIEF.format(
        module_id=module_id,
        pages=pages,
        scenes=scenes,
        dropped=_dropped_note(dropped or []),
        difficulty=", ".join(sorted(DIFFICULTY)),
        terrain=", ".join(sorted(TERRAIN_WORDS)),
        complexity_lo=min(COMPLEXITY),
        complexity_hi=max(COMPLEXITY),
        skills="\n".join(
            "    " + "  ".join(f"{s:<14}" for s in listed[i:i + 4])
            for i in range(0, len(listed), 4)
        ),
        roles=", ".join(ROLES),
        ranks=", ".join(RANKS),
    )
    where = into / "BRIEF.md"
    where.write_text(text)
    return where


@dataclass
class Imported:
    """What an import produced."""

    into: Path
    pages: int
    headings: int
    scenes: int
    draft: Path
    brief: Path


def run_import(source: str | Path, module_id: str) -> Imported:
    """Split an adventure up and write a draft and a brief beside it."""
    src = Path(source)
    if not src.exists():
        raise SystemExit(f"{src} is missing.")
    assert KINDS  # the vocabularies the brief quotes come from `module`
    into = MODULES / Path(module_id).name
    into.mkdir(parents=True, exist_ok=True)

    if src.suffix.lower() == ".pdf":
        pages, outline = extract(src, into)
    else:
        pages, outline = extract_text(src, into)

    skeleton = draft(Path(module_id).name, outline, pages)
    draft_path = into / "module.draft.json"
    draft_path.write_text(json.dumps(skeleton, indent=2) + "\n")
    brief = write_brief(into, Path(module_id).name, pages,
                        len(skeleton["scenes"]),
                        skeleton.get("_dropped") or [])
    return Imported(
        into=into, pages=pages, headings=len(outline),
        scenes=len(skeleton["scenes"]), draft=draft_path, brief=brief,
    )
