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
and writes a brief asking for the part a machine is worse at.

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
    for i, page in enumerate(reader.pages):
        (pages / f"{i:04d}.txt").write_text(page.extract_text() or "")
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

**Every scene** -- `brief` is what the DM would read out or paraphrase, in your
own words or the page's. `name` is already set from the heading; fix it if the
heading was a label rather than a title. Correct `exits`: the draft chains
scenes in document order, which is right for a linear adventure and wrong
wherever the adventure branches.

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
