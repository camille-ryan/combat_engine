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
        for item in items:  # type: ignore[attr-defined]
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            title = str(item.get("/Title", "")).strip()
            try:
                page = int(reader.get_destination_page_number(item))  # type: ignore[attr-defined]
            except Exception:
                page = -1
            if title:
                found.append(Heading(title=title, depth=depth, page=page))

    try:
        walk(reader.outline, 0)  # type: ignore[attr-defined]
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
    """
    runs: list[tuple[float, float, str]] = []

    def visit(text: str, _cm: object, tm: list, font: dict, _size: object) -> None:
        if not font or "Italic" not in str(font.get("/BaseFont", "")):
            return
        if text.strip():
            runs.append((round(tm[5], 1), round(tm[4], 1), text))

    page.extract_text(visitor_text=visit)  # type: ignore[attr-defined]
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
    return [_mend(b) for b in out if len(b) >= READ_ALOUD]


#: A line this much shorter than the column's measure may end a paragraph.
SHORT = 0.85


def _paragraphs(block: list[tuple[float, str]]) -> str:
    """Put the paragraph breaks back, from where the lines run short.

    **The box is set justified with no indent** -- every line in it starts at
    the same x -- so the only thing left saying where a paragraph ended is
    that its last line does not reach the measure. Without this the opening
    read-aloud arrives as one 986-character wall, which is legible on a page
    and is not legible in a terminal.

    Length alone is not enough and says so twice on the first page tried. "A
    thin, bald human friar named Venn approached you" is 50 characters
    against a 65 measure and **begins** a paragraph; so does "First, I want
    you to go to the prison grotto". Both are short because the font is
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

    for a, b in itertools.pairwise(scenes):
        a["exits"] = [b["id"]]

    return {
        "id": module_id,
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

`affordances` is what a character can *try* here:

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


def write_brief(into: Path, module_id: str, pages: int, scenes: int) -> Path:
    """The instructions a session reads before filling the draft in."""
    from combat_engine.engine.cast import TERRAIN_WORDS
    from combat_engine.engine.skills import SKILLS

    listed = sorted(SKILLS)
    text = BRIEF.format(
        module_id=module_id,
        pages=pages,
        scenes=scenes,
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
    brief = write_brief(into, Path(module_id).name, pages, len(skeleton["scenes"]))
    return Imported(
        into=into, pages=pages, headings=len(outline),
        scenes=len(skeleton["scenes"]), draft=draft_path, brief=brief,
    )
