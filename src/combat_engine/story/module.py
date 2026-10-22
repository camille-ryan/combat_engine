"""What a published adventure looks like once it is a thing the engine can read.

A module is a **graph of scenes**. `story/__init__.py` can field one fight; this
is what says there are twenty of them, what sort of thing each one is, and which
one comes next. #789.

## It describes the scene, never the stat block

Every field here is edition-neutral on purpose, because the ask is to drop in
modules from other editions and have the engine pick appropriate 4e challenges.
So a combat scene says *four of something goblin-ish, skirmishers, a standard
fight* -- a count, some words, a role and a difficulty band. It does not say
`m1433`, and it does not say a hit-dice count or a challenge rating either.
Turning a published difficulty into a band is a judgement made **once, by
whoever converts the module**, because that reader can see the page; a
conversion table living in here would be wrong for some editions, silently, and
would go stale as more were added.

What reads these words is `story/cast_list.py`, and it tries the module's own
creature name against the localisation first -- for a 4e module that answers
almost everything (39 of 39 measured, #790) and the words are never consulted.
They are what the fallback has to work from when the name resolves to nothing,
which is every module from every other edition.

## JSON, hand-validated

A module is **user-supplied data**, dropped into a git-ignored directory by
somebody who owns the adventure. It is not code and must never be `exec`'d, so
it is JSON rather than a Python file -- which is a real departure from the rest
of the tree, where every row is hand-written Python, and the reason is that no
other data in this repository arrives from outside it.

Validation is hand-written for the same reason the rest of the project is: a
schema library would turn a wrong word into a stack trace about types, and what
an author needs is *which of the closed vocabularies they missed*. Every problem
in the file is collected and reported at once, because a converter fixing twenty
scenes should not have to run the validator twenty times.

## The vocabularies are closed, and that is the point

`terrain`, `primary`/`secondary`, `role`, `rank`, `kind` and `difficulty` are
all checked against sets the engine already owns. The precedent is
`Cast.TERRAIN_WORDS`, which became a closed set after #539 found seven gates
across six files asking for words no board would ever carry -- invisible,
because every gate was False anyway. A module naming `wet` instead of `aquatic`
would field a fight with no terrain and look exactly like one that worked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from combat_engine.engine.cast import TERRAIN_WORDS
from combat_engine.engine.skills import SKILLS

from .dc import BANDS

#: What sort of thing a scene is. Four, and they are the four the module in
#: `modules/` is made of -- its outline has a heading for each.
#:
#: `rest` is a scene rather than a property of the edge between two, because a
#: module says where the party may rest and that is a decision with a position
#: in the story. `turns.short_rest` and `Party.rest` are what it runs.
KINDS = ("roleplay", "skill_challenge", "combat", "rest")

#: How hard a fight is, as a multiplier on `story.budget(level)` -- which is
#: itself one standard monster per character, read off the database rather than
#: from a table here.
#:
#: Four bands rather than a number, because that is what a published adventure
#: prints and what a converter can judge from the page. A module that states an
#: XP figure outright can give `xp` instead and skip the band entirely.
DIFFICULTY = {"easy": 0.75, "standard": 1.0, "hard": 1.5, "deadly": 2.0}

#: The printed ranks. `story.WORTH` prices them.
RANKS = ("standard", "elite", "solo", "minion")

#: The printed roles, as the `monster` table spells them. `minion` appears in
#: that column too but is a rank here, which is the same split `loader.pick`
#: makes with its separate `rank=` and `minion=` arguments.
ROLES = ("soldier", "brute", "artillery", "skirmisher", "controller", "lurker")

#: `complexity -> (successes needed, moderate checks, hard checks)`.
#:
#: The printed table, read out of the compendium glossary rather than
#: remembered -- `select Txt from Glossary where Name = 'Skill Challenge
#: Complexity'`. The first draft of this had the success counts right and the
#: **DCs wrong**: it assumed every primary check rolls at moderate, and the
#: printed shape is a mix that escalates, from four moderate at complexity 1 to
#: eight moderate and four hard at complexity 5. A challenge built from
#: all-moderate checks is a materially easier thing than the one the book
#: describes, and it would have looked correct forever.
COMPLEXITY = {
    1: (4, 4, 0),
    2: (6, 5, 1),
    3: (8, 6, 2),
    4: (10, 7, 3),
    5: (12, 8, 4),
}

#: What a successful secondary skill check is worth. Both readings are printed
#: and a module says which it means; this is the default when it does not.
#:
#: **`bonus` is the default, and that is a measured call rather than a taste.**
#: With `success`, the fixture challenge was won 5 times out of 5 and three of
#: its four successes came from easy-DC secondary rolls -- the party finds its
#: best secondary, rolls at a DC nine levels easier, and the primary skills the
#: challenge is *about* barely come up. Capping each secondary at one use does
#: not fix it, because there are usually three of them and a complexity-1
#: challenge needs four successes.
#:
#: As a bonus to the next primary check, a secondary does what the word means:
#: it helps, from an angle, and the challenge is still decided on the skills it
#: named first.
SECONDARY_GRANTS = ("bonus", "success")

#: What a secondary success adds to the next primary check under `bonus`.
SECONDARY_BONUS = 2


class ModuleError(Exception):
    """A module file that cannot be played, with every reason at once."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        self.path = path
        self.problems = problems
        lines = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"{path}: {len(problems)} problem(s)\n{lines}")


@dataclass(frozen=True)
class FoeSpec:
    """One line of a scene's opposition: *four of something, roughly like this*.

    `name` is the module's own word for the creature and is the **only** field
    that usually matters -- `cast_list` looks it up in the localisation and for
    a 4e module it resolves. Everything below it is what the fallback works
    from, and what a module from another edition will be carrying instead.
    """

    count: int = 1
    #: What the module calls it. Lives only in the git-ignored module file;
    #: never written to `game.db`, never put in a spec.
    name: str = ""
    #: Origin, kind and keyword words -- matched against the creature's own
    #: `keywords`, `kind` and `origin` columns when the name does not resolve.
    words: tuple[str, ...] = ()
    role: str = ""
    rank: str = "standard"


#: How many beats a roleplay scene runs before it gives up and takes its first
#: exit. A backstop, not a target -- a scene that has not resolved in six
#: exchanges is a scene the module did not finish writing, and a loop with no
#: bound is worse than an early exit.
MAX_BEATS = 6


@dataclass(frozen=True)
class Affordance:
    """Something a character can try in this scene, and what it costs.

    **The thing that makes a small model usable.** Asked to decide freely
    which declared intents needed a check, `qwen2.5:7b` got one of three
    right and the wrong one broke an instruction that was in its prompt
    verbatim. Handed this list and asked to *match*, it got 3 of 3 across
    three runs at temperature 0. Classification against a closed set is a
    different task from open judgement, and a 7B is on the right side of the
    line for one and the wrong side for the other. #801.

    `win` and `lose` are the facts the DM may state afterwards. Everything
    else it may not -- which is the whole of how canon is held.
    """

    id: str
    #: **The words a player would type.** This is the only thing the matcher
    #: compares an intent against, so it is not a label ("insight") and it is
    #: not a note to the DM either -- it is the phrasing somebody at a
    #: keyboard would actually use, and listing two or three phrasings is
    #: normal and helps.
    #:
    #: The second half of that was learnt expensively. A tavern scene ran
    #: four beats in which **every one of eight intents matched `none`**,
    #: including "go to bed" three times, while an affordance to leave sat
    #: open the whole time. Its text was *"take the rooms and go, blind or
    #: otherwise"* -- where "blind or otherwise" means whether the party
    #: spotted the ambush waiting outside, which is a distinction the DM has
    #: and the player does not. Nobody types that.
    #:
    #: Replaying those exact strings against *"go to bed, turn in, take the
    #: room, or leave the tavern for the night"*, with nothing else changed,
    #: took it from 0 of 4 to 3 of 4 -- and the fourth, "check outside",
    #: correctly stayed `none`. **The matcher was right and the text was
    #: wrong**, which is worth knowing before anyone tunes the matcher: it
    #: scores 3 of 3 on a driver and 0 of 8 here, and the difference is the
    #: module.
    #:
    #: **Transitions are the worst offenders, every time.** Ending a scene
    #: is the thing most naturally described from outside it -- "stop asking
    #: and let the host come to his point", "cross the last of the ground to
    #: the well house". All five in the first chapter were written that way.
    what: str = ""
    skill: str = ""
    band: str = "moderate"
    #: The number the page printed, which **wins over `band`**. Zero means
    #: the module did not state one and the band is used.
    #:
    #: A band is a translation and translations lose. The adventure in hand
    #: prints 8, 12, 15 and 19 on its knowledge ladder; at level 1 the bands
    #: are 8, 12 and 19, so **15 has no band** and both rows carrying it had
    #: to be rounded up to hard -- making two facts meaningfully harder than
    #: the author set them. There is no reason to guess when the page says
    #: the number.
    #:
    #: It does not scale with the party's level, and that is the point: the
    #: module stated a number for the adventure it is. A band is what to
    #: reach for when it did not.
    dc: int = 0
    win: str = ""
    lose: str = ""
    #: Once each, like a challenge's secondary skills, so a party cannot
    #: grind one affordance until it lands.
    once: bool = True
    #: Taking this ends the scene and goes there. Empty leaves the scene
    #: running until `max_beats`.
    leads_to: str = ""

    @property
    def rolls(self) -> bool:
        """Does trying this put dice on the table?

        An affordance with no skill is a thing a character can simply do --
        open the door, hand over the money -- which still matters because it
        is a thing the module *said* they could do, and the DM may then speak
        to its `win` text.
        """
        return bool(self.skill)


@dataclass(frozen=True)
class Lore:
    """Something a character may simply know, rolled for when a scene opens.

    **Nobody declares this.** An affordance is matched against a stated
    intent; this fires on its own, because recalling what you know about a
    stolen jewel is not a thing you announce. Every character rolls their
    own check and each who passes learns it independently -- which is how a
    table does it, and which makes the interesting output *who* knew rather
    than whether anybody did.

    That reframing is forced by the arithmetic. With five characters rolling
    at level 1, the chance somebody passes is **100% at easy and 97-100% at
    moderate**; only hard stays a real question, at 52-89% depending on the
    skill. So a band here does not withhold anything and must not be used to
    try: it decides how likely the party is to have it and, through that,
    whose mouth it comes out of. **A fact that must stay unavailable gets no
    `Lore` row at all** -- it belongs to an NPC who knows it, or to an
    affordance that prises it out of them.

    This is the shape the source material is already in. 78 of 143 DC sites
    in the module in hand gate a fact rather than an action, most of them
    written as a skill heading with a ladder of numbered facts beneath it.
    """

    fact: str
    skill: str
    band: str = "moderate"
    #: The number the page printed, which **wins over `band`**. Zero means
    #: the module did not state one and the band is used.
    #:
    #: A band is a translation and translations lose. The adventure in hand
    #: prints 8, 12, 15 and 19 on its knowledge ladder; at level 1 the bands
    #: are 8, 12 and 19, so **15 has no band** and both rows carrying it had
    #: to be rounded up to hard -- making two facts meaningfully harder than
    #: the author set them. There is no reason to guess when the page says
    #: the number.
    #:
    #: It does not scale with the party's level, and that is the point: the
    #: module stated a number for the adventure it is. A band is what to
    #: reach for when it did not.
    dc: int = 0

    #: Rolled once per campaign rather than once per visit. A thing you
    #: either know or do not is not re-rolled because you walked back in.
    once: bool = True
    #: The affordance that has to be **won** before this is even rolled for.
    #: Empty means it fires when the scene opens, which is most of it.
    #:
    #: **For knowledge the module gates behind doing something**, which it
    #: routinely does: the adventure's tavern ladder is introduced as
    #: *"checks around the taverns that evening"*, so those eight facts are
    #: what you learn by going and asking, not what you walk into dinner
    #: knowing. Authored without this, all eight fired in the opening beat
    #: as a stack of eight "You know:" lines before the player had typed a
    #: word -- an exposition dump, and mistimed on top.
    #:
    #: Same shape and same reason as `Npc.unseen`: the gate is an affordance
    #: that must be *won*, because a failed check reveals nothing.
    after: str = ""


@dataclass(frozen=True)
class Npc:
    """Somebody in the scene for the model to play.

    `knows` is what they may say. **`hides` is withheld from the prompt
    entirely** rather than included with an instruction not to reveal it:
    a 7B told a secret and told not to tell it is a 7B one unlucky sample
    away from telling it, and the cheapest way to keep a secret from a model
    is not to give it one.
    """

    name: str
    wants: str = ""
    knows: tuple[str, ...] = ()
    hides: tuple[str, ...] = ()
    voice: str = ""
    #: Who they physically are, in the page's own words. **Because scene
    #: text does not travel and a recurring character does.**
    #:
    #: The adventure introduces one as *"a thin, bald human friar named
    #: Venn"* -- in the opening scene's read-aloud. Three scenes later the
    #: DM sees only that scene's text, which is somebody else's speech, so
    #: it had nothing about Venn and guessed: *"Venn nodded slightly, her
    #: eyes downcast"*, twice in one scene, for a character the player had
    #: read described as a man one scene earlier.
    #:
    #: `voice` is how they speak and was never meant to carry this. A
    #: description belongs on the person, not in the prose of whichever
    #: scene happened to introduce them.
    looks: str = ""
    #: The affordance that has to be **won** before this person is in the
    #: scene at all. Empty means they are there from the first beat, which
    #: is almost everybody.
    #:
    #: **`hides` hides facts; this hides the person**, and the gap between
    #: those two cost a whole scene. A watcher planted in a tavern -- whose
    #: entire function is to be noticed by a Perception check, bolt, and
    #: lead to an ambush -- was in the cast list from beat one, so the DM
    #: gave him a friendly speaking line in all four beats. He greeted the
    #: party, complimented the room, and "slipped away unnoticed" three
    #: times while remaining at the door. His `wants` said *not to be
    #: noticed*. Nothing could act on that, because a name in the cast list
    #: is an invitation to write them a line.
    #:
    #: The player's verdict was the plainest statement of the bug: *"who is
    #: he and why do I care?"* -- which is exactly right, because the reveal
    #: that was supposed to make him matter never fired, and he had been
    #: chatting pleasantly for four beats before it would have.
    unseen: str = ""


@dataclass(frozen=True)
class Scene:
    """One beat of the adventure, and where it can lead.

    One dataclass for all four kinds rather than four classes, because the
    graph wants a single node type and the fields a kind does not use are
    simply empty. `kind` is what decides which of them are read, and `_check`
    is what refuses a scene that fills in the wrong ones -- a `rest` scene with
    a foe list is an authoring mistake and should not play as an empty fight.
    """

    id: str
    kind: str
    name: str = ""
    #: The module's own prose for this scene, **written for the DM** --
    #: because that is what an adventure is made of. It routinely states the
    #: plot: who is lying, what they actually want, what is waiting in the
    #: next room. Only the DM prompt sees it.
    brief: str = ""
    #: What a character standing here can see, hear and be told. This is the
    #: half that is printed and the half the companions are given.
    #:
    #: **It falls back to `brief`, and the fallback is a known hazard rather
    #: than a convenience.** Every module converted before this field existed
    #: has only a brief, so defaulting keeps them playing exactly as they did
    #: -- and chapter 1 of the local module opened by printing, in its own
    #: words, that the friendly friar serves a snake god and means to set two
    #: enemies on each other. That is the whole chapter, read out before
    #: anybody speaks, and then handed to four companions who proceed to play
    #: characters who know it.
    #:
    #: `Npc.hides` was built against exactly this and works: the friar's three
    #: secrets sit in `hides` and never reach a prompt. The brief handed them
    #: over regardless. A careful mechanism on one field is worth nothing while
    #: the field beside it is unguarded. #805.
    sets: str = ""
    #: Which chapter and session of the published adventure this came from.
    #: Carried for reporting only -- the graph is what plays.
    chapter: str = ""
    #: Scene ids this one may lead to. The first is the default. An empty tuple
    #: ends the module.
    exits: tuple[str, ...] = ()

    # -- roleplay ------------------------------------------------------------
    #: Who is here to be talked to.
    npcs: tuple[Npc, ...] = ()
    #: What can be tried. An empty list makes the scene a read-aloud that
    #: advances, which is what every scene was before this existed.
    affordances: tuple[Affordance, ...] = ()
    #: What a character may already know, rolled for when the scene opens.
    lore: tuple[Lore, ...] = ()
    max_beats: int = MAX_BEATS

    # -- combat ------------------------------------------------------------
    difficulty: str = "standard"
    #: Overrides `difficulty` when the module prints a real XP figure.
    xp: int = 0
    terrain: tuple[str, ...] = ()
    foes: tuple[FoeSpec, ...] = ()
    tactics: str = ""

    # -- skill challenge ----------------------------------------------------
    complexity: int = 0
    #: The level the DCs are read at. Defaults to the party's when 0.
    level: int = 0
    primary: tuple[str, ...] = ()
    secondary: tuple[str, ...] = ()
    #: `"bonus"` or `"success"` -- see `SECONDARY_GRANTS`.
    secondary_grants: str = "bonus"
    #: Where success and failure lead. Both fall back to `exits` when empty,
    #: so a challenge that only gates flavour needs neither.
    on_success: str = ""
    on_failure: str = ""

    # -- rest ---------------------------------------------------------------
    extended: bool = False

    def affordance(self, wanted: str) -> Affordance | None:
        """One by id, or `None`. `"none"` is a legal answer and means nothing."""
        return next((a for a in self.affordances if a.id == wanted), None)

    @property
    def seen(self) -> str:
        """What is shown and what the companions are told.

        One accessor rather than `scene.sets or scene.brief` at each of the
        three call sites, because the whole bug was that the three sites did
        not agree about who they were writing for.
        """
        return self.sets or self.brief

    @property
    def share(self) -> float:
        """What fraction of a standard encounter's budget this fight is worth."""
        return DIFFICULTY.get(self.difficulty, 1.0)

    @property
    def needs(self) -> int:
        """Successes this challenge wants before three failures."""
        return COMPLEXITY.get(self.complexity, (0, 0, 0))[0]

    @property
    def bands(self) -> tuple[str, ...]:
        """The DC band of each primary check, in order, moderate first.

        The printed mix laid out as a sequence, so a challenge escalates: the
        hard checks are the last ones, which is where a party is already
        carrying failures. `challenge.py` reuses the final band once the
        sequence runs out, because failures mean more checks get rolled than
        the table lists.
        """
        _, moderate, hard = COMPLEXITY.get(self.complexity, (0, 0, 0))
        return ("moderate",) * moderate + ("hard",) * hard


@dataclass(frozen=True)
class Module:
    """A whole adventure: every scene, and which one opens it."""

    id: str
    scenes: dict[str, Scene] = field(default_factory=dict)
    start: str = ""
    party_level: int = 1
    party_size: int = 4
    #: Recorded so a reader knows what was converted. **Nothing branches on
    #: it** -- see the module docstring. It is provenance, not a switch.
    edition: str = ""
    #: Campaign resources the adventure names, and their starting values --
    #: a reputation score, a body count, a door left unlocked. The module in
    #: `modules/` counts one of these and spends it on rewards.
    flags: dict[str, int] = field(default_factory=dict)

    def scene(self, scene_id: str) -> Scene:
        return self.scenes[scene_id]

    def next_of(self, scene: Scene, chose: str = "") -> str:
        """Where play goes from here. `""` ends the module.

        A choice is honoured only if the scene actually lists it, which is the
        same refusal `dm.py`'s `advance` tool makes -- a campaign that can jump
        anywhere is not a campaign.
        """
        if chose and chose in scene.exits:
            return chose
        return scene.exits[0] if scene.exits else ""


def _as_foe(raw: Any, where: str, problems: list[str]) -> FoeSpec:
    if not isinstance(raw, dict):
        problems.append(f"{where}: a foe must be an object, got {type(raw).__name__}")
        return FoeSpec()
    count = raw.get("count", 1)
    if not isinstance(count, int) or count < 1:
        problems.append(f"{where}: count must be a positive integer, got {count!r}")
        count = 1
    role = str(raw.get("role", "")).strip().lower()
    if role and role not in ROLES:
        problems.append(f"{where}: role {role!r} is not one of {', '.join(ROLES)}")
    rank = str(raw.get("rank", "standard")).strip().lower()
    if rank not in RANKS:
        problems.append(f"{where}: rank {rank!r} is not one of {', '.join(RANKS)}")
        rank = "standard"
    words = tuple(str(w).strip().lower() for w in raw.get("words", ()) if str(w).strip())
    return FoeSpec(
        count=count, name=str(raw.get("name", "")).strip(),
        words=words, role=role, rank=rank,
    )


def _as_npc(raw: Any, where: str, problems: list[str]) -> Npc | None:
    if not isinstance(raw, dict):
        problems.append(f"{where}: an npc must be an object")
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        problems.append(f"{where}: an npc needs a name")
        return None
    def lines(key: str) -> tuple[str, ...]:
        got = raw.get(key, ())
        if isinstance(got, str):
            got = [got]
        return tuple(str(x).strip() for x in got if str(x).strip())
    return Npc(
        name=name, wants=str(raw.get("wants", "")).strip(),
        knows=lines("knows"), hides=lines("hides"),
        voice=str(raw.get("voice", "")).strip(),
        looks=str(raw.get("looks", "")).strip(),
        unseen=str(raw.get("unseen", "")).strip(),
    )


def _stated_dc(raw: Any, where: str, what: str,
               problems: list[str]) -> int:
    """The DC the page printed, or 0. One reader for both callers.

    A negative or non-integer DC is refused rather than coerced: a module
    carrying `"dc": "hard"` has made a category mistake, and silently
    reading it as 0 would fall back to the band and look like it worked.
    """
    got = raw.get("dc", 0)
    if got in (0, None, ""):
        return 0
    if not isinstance(got, int) or isinstance(got, bool) or got < 1:
        problems.append(
            f"{where}: {what} has dc {got!r}; a stated DC is a positive "
            "integer, or leave it out and the band is used"
        )
        return 0
    return got


def _as_lore(raw: Any, where: str, problems: list[str]) -> Lore | None:
    if not isinstance(raw, dict):
        problems.append(f"{where}: a lore entry must be an object")
        return None
    fact = str(raw.get("fact", "")).strip()
    if not fact:
        problems.append(f"{where}: a lore entry needs a 'fact'")
        return None
    skill = str(raw.get("skill", "")).strip().lower()
    if skill not in SKILLS:
        # **A lore row without a skill is refused, where an affordance
        # without one is fine.** An affordance with no skill is a thing a
        # character may simply do; lore with no skill is a fact nobody
        # rolls for, which is not knowledge-you-might-have, it is just a
        # sentence -- and it would arrive every scene for everybody.
        problems.append(
            f"{where}: lore {fact[:40]!r} needs a skill to recall it by; "
            f"one of: {', '.join(sorted(SKILLS))}"
        )
        return None
    band = str(raw.get("band", "moderate")).strip().lower()
    if band not in BANDS:
        problems.append(
            f"{where}: lore {fact[:40]!r} has band {band!r}; "
            f"one of: {', '.join(BANDS)}"
        )
        band = "moderate"
    return Lore(fact=fact, skill=skill, band=band,
                dc=_stated_dc(raw, where, f"lore {fact[:30]!r}", problems),
                once=bool(raw.get("once", True)),
                after=str(raw.get("after", "")).strip())


def _as_affordance(raw: Any, where: str, problems: list[str]) -> Affordance | None:
    if not isinstance(raw, dict):
        problems.append(f"{where}: an affordance must be an object")
        return None
    aid = str(raw.get("id", "")).strip()
    if not aid:
        problems.append(f"{where}: an affordance needs an id")
        return None
    what = str(raw.get("what", "")).strip()
    if not what:
        # **The matcher reads this, not the id.** An affordance with no
        # description gives the model a bare slug to compare an intent
        # against, which is the condition the measurement in #801 was *not*
        # taken under -- so it would be shipping on evidence that does not
        # cover it.
        problems.append(
            f"{where}: affordance {aid!r} needs a 'what' -- the matcher "
            "compares an intent against that sentence, not against the id"
        )
    skill = str(raw.get("skill", "")).strip().lower()
    if skill and skill not in SKILLS:
        problems.append(
            f"{where}: affordance {aid!r} names {skill!r}, which is not a "
            f"skill. Known: {', '.join(sorted(SKILLS))}"
        )
    band = str(raw.get("band", "moderate")).strip().lower()
    if band not in BANDS:
        problems.append(
            f"{where}: affordance {aid!r} has band {band!r}, not one of "
            f"{', '.join(BANDS)}"
        )
        band = "moderate"
    if skill and not (raw.get("win") or raw.get("lose")):
        # A roll with no stated consequence is a die thrown for nothing, and
        # the DM has no fact to speak to afterwards.
        problems.append(
            f"{where}: affordance {aid!r} rolls {skill} and says what neither "
            "winning nor losing does"
        )
    return Affordance(
        id=aid, what=what, skill=skill, band=band,
        dc=_stated_dc(raw, where, f"affordance {aid!r}", problems),
        win=str(raw.get("win", "")).strip(),
        lose=str(raw.get("lose", "")).strip(),
        once=bool(raw.get("once", True)),
        leads_to=str(raw.get("leads_to", "")).strip(),
    )


def _as_scene(raw: Any, index: int, problems: list[str]) -> Scene | None:
    where = f"scene {index}"
    if not isinstance(raw, dict):
        problems.append(f"{where}: must be an object, got {type(raw).__name__}")
        return None
    scene_id = str(raw.get("id", "")).strip()
    if not scene_id:
        problems.append(f"{where}: needs an id")
        return None
    where = f"scene {scene_id!r}"

    kind = str(raw.get("kind", "")).strip().lower()
    if kind not in KINDS:
        problems.append(f"{where}: kind {kind!r} is not one of {', '.join(KINDS)}")
        return None

    terrain = tuple(str(w).strip().lower() for w in raw.get("terrain", ()) if str(w).strip())
    for word in terrain:
        if word not in TERRAIN_WORDS:
            problems.append(
                f"{where}: terrain {word!r} is not a terrain word. "
                f"Known: {', '.join(sorted(TERRAIN_WORDS))}"
            )

    difficulty = str(raw.get("difficulty", "standard")).strip().lower()
    if difficulty not in DIFFICULTY:
        problems.append(
            f"{where}: difficulty {difficulty!r} is not one of "
            f"{', '.join(sorted(DIFFICULTY))}"
        )
        difficulty = "standard"

    primary = tuple(str(s).strip().lower() for s in raw.get("primary", ()) if str(s).strip())
    secondary = tuple(
        str(s).strip().lower() for s in raw.get("secondary", ()) if str(s).strip()
    )
    for skill in (*primary, *secondary):
        if skill not in SKILLS:
            problems.append(
                f"{where}: {skill!r} is not a skill. Known: {', '.join(sorted(SKILLS))}"
            )

    complexity = raw.get("complexity", 0)
    if not isinstance(complexity, int) or complexity < 0:
        problems.append(f"{where}: complexity must be an integer, got {complexity!r}")
        complexity = 0
    if kind == "skill_challenge" and complexity not in COMPLEXITY:
        problems.append(
            f"{where}: a skill challenge needs a complexity in "
            f"{min(COMPLEXITY)}-{max(COMPLEXITY)}, got {complexity}"
        )
    if kind == "skill_challenge" and not primary:
        problems.append(f"{where}: a skill challenge needs at least one primary skill")

    grants = str(raw.get("secondary_grants", "bonus")).strip().lower()
    if grants not in SECONDARY_GRANTS:
        problems.append(
            f"{where}: secondary_grants {grants!r} is not one of "
            f"{', '.join(SECONDARY_GRANTS)}"
        )
        grants = "bonus"
    overlap = set(primary) & set(secondary)
    if overlap:
        problems.append(
            f"{where}: {', '.join(sorted(overlap))} listed as both primary and "
            "secondary -- it would roll at two DCs"
        )

    foes = tuple(
        _as_foe(f, where, problems) for f in raw.get("foes", ())
    )
    npcs = tuple(
        n for n in (_as_npc(x, where, problems) for x in raw.get("npcs", ()))
        if n is not None
    )
    affordances = tuple(
        a for a in
        (_as_affordance(x, where, problems) for x in raw.get("affordances", ()))
        if a is not None
    )
    lore = tuple(
        x for x in (_as_lore(y, where, problems) for y in raw.get("lore", ()))
        if x is not None
    )
    seen_ids = [a.id for a in affordances]
    for aid in sorted({a for a in seen_ids if seen_ids.count(a) > 1}):
        problems.append(f"{where}: two affordances share the id {aid!r}")
    if "none" in seen_ids:
        # The matcher's enum carries "none" for "this just happens", so an
        # affordance called that would be unreachable *and* would silently
        # swallow every intent the model meant to leave alone.
        problems.append(
            f"{where}: an affordance may not be called 'none' -- the matcher "
            "uses that word for an intent that needs no roll"
        )
    # **An `unseen` naming nothing leaves the person out of the scene for
    # good**, silently -- the worst shape of bug this file can emit, since
    # the scene plays and the character simply never appears.
    for row in lore:
        if row.after and row.after not in seen_ids:
            problems.append(
                f"{where}: lore {row.fact[:40]!r} waits on {row.after!r}, "
                "which is not an affordance here"
            )
    for person in npcs:
        if person.unseen and person.unseen not in seen_ids:
            problems.append(
                f"{where}: npc {person.name!r} is unseen until "
                f"{person.unseen!r}, which is not an affordance here"
            )
    beats = raw.get("max_beats", MAX_BEATS)
    if not isinstance(beats, int) or beats < 1:
        problems.append(f"{where}: max_beats must be a positive integer")
        beats = MAX_BEATS
    if kind == "combat" and not foes:
        problems.append(f"{where}: a combat scene needs at least one foe line")

    # **A field the kind does not use is an authoring mistake, not a default.**
    # A rest scene carrying a foe list plays as a rest and silently drops the
    # fight; a roleplay scene carrying a complexity never counts a success.
    # Both read exactly like a scene that works, which is why they are refused.
    unused = {
        "roleplay": ("foes", "terrain", "complexity", "primary", "secondary"),
        "skill_challenge": ("foes", "terrain", "affordances"),
        "combat": ("complexity", "primary", "secondary", "affordances"),
        "rest": ("foes", "terrain", "complexity", "primary", "secondary",
                 "affordances", "npcs", "lore"),
    }[kind]
    for name in unused:
        if raw.get(name):
            problems.append(f"{where}: a {kind} scene must not carry {name!r}")

    return Scene(
        id=scene_id, kind=kind,
        name=str(raw.get("name", "")).strip(),
        brief=str(raw.get("brief", "")),
        sets=str(raw.get("sets", "")),
        chapter=str(raw.get("chapter", "")).strip(),
        exits=tuple(str(e).strip() for e in raw.get("exits", ()) if str(e).strip()),
        npcs=npcs,
        affordances=affordances,
        lore=lore,
        max_beats=beats,
        difficulty=difficulty,
        xp=int(raw.get("xp", 0) or 0),
        terrain=terrain,
        foes=foes,
        tactics=str(raw.get("tactics", "")),
        complexity=complexity,
        level=int(raw.get("level", 0) or 0),
        primary=primary,
        secondary=secondary,
        secondary_grants=grants,
        on_success=str(raw.get("on_success", "")).strip(),
        on_failure=str(raw.get("on_failure", "")).strip(),
        extended=bool(raw.get("extended", False)),
    )


def parse(raw: dict, path: Path) -> Module:
    """A `Module` from already-decoded JSON. Raises `ModuleError`."""
    problems: list[str] = []
    module_id = str(raw.get("id", "")).strip()
    if not module_id:
        problems.append("the module needs an id")

    scenes: dict[str, Scene] = {}
    order: list[str] = []
    for i, raw_scene in enumerate(raw.get("scenes", ())):
        scene = _as_scene(raw_scene, i, problems)
        if scene is None:
            continue
        if scene.id in scenes:
            problems.append(f"scene {scene.id!r}: declared twice")
            continue
        scenes[scene.id] = scene
        order.append(scene.id)

    if not scenes:
        problems.append("the module has no scenes")

    start = str(raw.get("start", "")).strip() or (order[0] if order else "")
    if start and start not in scenes:
        problems.append(f"start {start!r} is not a scene in this module")

    # **Every edge resolves, and that is checked here rather than at play
    # time.** A dangling exit is a campaign that stops dead three hours in,
    # which is the worst possible moment to discover a typo.
    for scene in scenes.values():
        edges = [*scene.exits, scene.on_success, scene.on_failure]
        edges += [a.leads_to for a in scene.affordances]
        for exit_id in edges:
            if exit_id and exit_id not in scenes:
                problems.append(f"scene {scene.id!r}: exit {exit_id!r} is not a scene")

    # Unreachable scenes are reported, not refused: a converter working through
    # a long module has half a graph for a while, and `--validate` is the tool
    # that should tell them which half.
    if start in scenes:
        seen, stack = {start}, [start]
        while stack:
            here = scenes[stack.pop()]
            onward = [*here.exits, here.on_success, here.on_failure]
            onward += [a.leads_to for a in here.affordances]
            for exit_id in onward:
                if exit_id in scenes and exit_id not in seen:
                    seen.add(exit_id)
                    stack.append(exit_id)
        for orphan in order:
            if orphan not in seen:
                problems.append(f"scene {orphan!r}: nothing leads to it")

    level = raw.get("party_level", 1)
    if not isinstance(level, int) or not 1 <= level <= 30:
        problems.append(f"party_level must be 1-30, got {level!r}")
        level = 1

    flags = {
        str(k): int(v) for k, v in (raw.get("flags") or {}).items()
        if isinstance(v, int)
    }

    if problems:
        raise ModuleError(path, problems)
    return Module(
        id=module_id, scenes=scenes, start=start,
        party_level=level,
        party_size=int(raw.get("party_size", 4) or 4),
        edition=str(raw.get("edition", "")).strip(),
        flags=flags,
    )


def load(path: str | Path) -> Module:
    """Read and validate a module file."""
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"{path} is missing.")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ModuleError(path, [f"not valid JSON: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise ModuleError(path, ["the top level must be an object"])
    return parse(raw, path)
