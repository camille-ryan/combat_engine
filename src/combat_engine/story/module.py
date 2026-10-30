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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from combat_engine.engine.cast import TERRAIN_WORDS
from combat_engine.engine.skills import SKILLS

from .dc import BANDS
from .objective import KINDS as OBJECTIVES
from .objective import POSITIONS, Objective
from .objective import ROUNDS as OBJECTIVE_ROUNDS
from .objective import SHARE as OBJECTIVE_SHARE

#: What sort of thing a scene is. Four, and they are the four the module in
#: `modules/` is made of -- its outline has a heading for each.
#:
#: `rest` is a scene rather than a property of the edge between two, because a
#: module says where the party may rest and that is a decision with a position
#: in the story. `turns.short_rest` and `Party.rest` are what it runs.
KINDS = ("roleplay", "skill_challenge", "combat", "rest")

#: What shape a stated room may be. An octagon and an irregular chamber
#: need nothing new -- a cut corner is blocking squares, the same
#: mechanism a pillar already uses. #974.
ROOM_KINDS = ("rectangle", "octagon", "irregular")

#: The smallest room worth fighting in, and the largest the engine will
#: build. The printed table runs 6x8 to 10x16; the floor in use is 16x12,
#: so the ceiling is set by what exists rather than by the table.
ROOM_MIN, ROOM_MAX = 5, 24

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
    #: The round this line walks on. 1 is on the board before the first
    #: turn, which is what every line meant before arrivals existed. #962.
    at: int = 1
    #: Repeat every this many rounds from `at`. 0 is "once".
    #:
    #: The module's own wave prints *"at the start of each round, three
    #: more emerge"*, so a repeat is the shape it needs rather than a list
    #: of rounds.
    every: int = 0
    #: The last round a repeat may arrive on. **Required with `every`**, and
    #: refused without it: *"they keep coming until the building is
    #: a round cap, and unbounded reinforcements are an unbounded fight.
    until: int = 0
    #: Does this line earn XP. The module states its own cutoff -- only
    #: its earliest waves count toward the reward -- which is also what
    #: keeps a ten-round fight from being worth an arbitrary amount.
    worth: bool = True

    @property
    def arrives(self) -> bool:
        """Is this line a reinforcement rather than part of the opening board."""
        return self.at > 1 or bool(self.every)

    def due(self, round_now: int) -> bool:
        """Does this line walk on at the start of `round_now`."""
        if round_now < self.at:
            return False
        if round_now == self.at:
            return True
        if not self.every:
            return False
        if self.until and round_now > self.until:
            return False
        return (round_now - self.at) % self.every == 0


#: What a quest is, and what it is worth saying about one.
#:
#: The DMG lists quests first among what an adventure is made of, and sets a
#: level's budget as *"six to eight encounters, one major quest, and one
#: minor quest per character"* -- so a quest is a third of the level's XP
#: structure rather than decoration. The converted adventure prints two and
#: nothing carried either.
#:
#: > **Major quests** [...] are the main story arc. **Minor quests** are the
#: > subplots [...] Often, minor quests matter primarily to a particular
#: > character or perhaps a subset of the party.
QUEST_KINDS = ("major", "minor")

#: The states a quest moves through. **Not a boolean per quest**, which is
#: what #940's comment rules out:
#:
#: > *You can present quests that conflict with each other* -- so two active
#: > quests may be mutually exclusive, and completing one must be able to
#: > fail the other. A set of independent booleans cannot express that.
#:
#: `""` is a quest the module declares and has not offered yet, which is the
#: mid-combat grant the same comment names: *"the characters gain a minor
#: quest"* in a scene that is not a roleplay scene.
QUEST_STATES = ("", "open", "done", "failed")

#: What a scene may charge the party for losing it.
#:
#: Camille's ruling -- *"skill challenges should never prevent the plot from
#: progressing"* -- is DMG2's printed rule, and DMG2 answers the obvious
#: follow-up:
#:
#: > *focus the challenge on what the PCs' necessary victory costs them,
#: > rather than on winning or losing. On either a success or a failure, the
#: > characters will move on to the same obstacle. However, on a failure,
#: > they move on at a significant disadvantage.*
#:
#: So a loss costs something and the exit is unchanged. `on_failure` is still
#: there for the modules that branch; this is the option for the ones that
#: should not have to.
#:
#: **One mechanism for every kind, not one for challenges.** #975's own
#: comment makes the case: DMG2's three-position taxonomy -- clean, at a
#: cost, failed -- names *"fewer healing surges or daily powers"* for a
#: costly **combat** win and this body proposes the same list for a lost
#: challenge. Keying it on `Scene.kind` would build it twice.
COSTS = ("surge", "action point", "rest")

#: Environmental dangers and the Endurance DC each one imposes, printed.
#:
#: **Fixed numbers, not a level band.** `dc.py`'s table scales with level
#: because a skill challenge is pitched at the party; weather is not, and the
#: page prints one DC per condition. Reading these off `dc(level, band)`
#: would have made frigid cold easier for a stronger party, which is the
#: opposite of what the rule says.
#:
#: A separate vocabulary from `TERRAIN_WORDS`, which is what a *board* is
#: made of -- ice, snow, aquatic. A snowstorm a party walks through for eight
#: hours and a patch of ice they fight on are different facts. #971.
DANGERS = {
    "severe weather": 20,
    "high altitude": 21,
    "cold": 22,
    "heat": 22,
    "extreme altitude": 26,
    "frigid cold": 26,
    "stifling heat": 26,
}

#: *"Every eight hours within an area of environmental danger, the character
#: must succeed on an Endurance check."*
EXPOSURE_HOURS = 8

#: *"During the six hours that include extended rest, the character gets a
#: +2 bonus to Endurance checks because he's resting and not exerting
#: himself."*
SHELTERED = 2


#: How ready the opposition is when the party arrives. The DMG's four
#: monster-readiness states, and the two in the middle are the ones with a
#: consequence here: asleep or distracted and the defenders are **surprised**,
#: which is a free round for the party.
#:
#: **The Stealth contest is deliberately skipped.** The book offers it as the
#: fuller version -- the party member with the lowest Stealth rolls once for
#: the group, against passive Perception -- but a converted adventure *states*
#: in its prose that a creature is dozing by a fire rather than asking the DM
#: to roll for it. So the module says, and the printed modifiers that only
#: feed that contest (-5 asleep, -2 distracted) are **not** carried: a
#: modifier nothing consults is this project's commonest bug.
#:
#: `alert` is accepted and does nothing yet, which is said out loud rather
#: than implied -- its printed effects are active Perception each round,
#: prepared defences and the best positions, and none of those has a
#: mechanism here. #945.
READINESS = ("ready", "asleep", "distracted", "alert")

#: The states that hand the party a surprise round.
CAUGHT = ("asleep", "distracted")

#: What a timeline entry counts in. Scenes played and extended rests taken
#: are the two units the book's own examples use -- *"a festival day"*, *"the
#: night of the full moon"* -- and a tick per scene transition is the coarsest
#: thing that can express any of them. Deliberately **not** a real clock.
UNITS = ("scene", "rest")


@dataclass(frozen=True)
class Quest:
    """Why the party is doing any of this, and what finishes it.

    `done_when` is a **scene id or an affordance id**, both of which the
    module already names, so nothing new has to be invented for a quest to
    know when it is over.

    `offered_by` is the scene that grants it, for a quest the party does
    not start with. Any kind of scene may grant one.

    `fails` names other quests this one's completion ends -- the conflict
    case, which is why a quest has a state rather than a flag.

    `xp` is carried and **spent by nothing**: `Sheet` has no XP field and
    nothing in the story engine advances a character, which is #967. The
    figure is recorded so that award has something to read, the same way
    `Step.clean` waits for it.
    """

    id: str
    kind: str = "major"
    xp: int = 0
    done_when: str = ""
    offered_by: str = ""
    fails: tuple[str, ...] = ()
    says: str = ""


@dataclass(frozen=True)
class Cost:
    """What losing this scene costs, applied with the exit unchanged.

    `says` is shown **before** the scene runs, because DMG2's framing
    advice is to *"build tension by showing players the negative
    consequences of failure"* -- a cost discovered afterwards is a
    punishment, and one stated beforehand is a stake.
    """

    what: str = "surge"
    #: How many, per character.
    each: int = 1
    says: str = ""


@dataclass(frozen=True)
class Timed:
    """One timeline entry: a scene that happens *to* the party, on the clock.

    The DMG's structural tool for an adventure that is not a dungeon --
    events that fire whether or not the party went looking, and the half
    that makes it not railroading:

    > *events on the timeline could trigger **unless** the characters
    > manage to prevent them*

    So an entry carries both halves. `when` and `unit` are when it is due;
    `unless` is what cancels it, and is either a scene id the party has
    already played or a module flag that is non-zero. An entry with no
    `unless` is inevitable, which the book also allows -- a solar eclipse
    is nobody's fault.

    `says` is told to the players when the entry is announced, because
    DMG2 is explicit that a deadline is no use as pacing if it is a
    secret: *"Tell the players up front."*
    """

    when: int = 0
    scene: str = ""
    unit: str = "scene"
    #: A scene id already played, or a flag that is non-zero. Either
    #: cancels the entry for good.
    unless: str = ""
    says: str = ""


@dataclass(frozen=True)
class Grant:
    """Something the scene hands the party.

    `what` is the module's own word for it **or** the item ref, and
    `loot.find` takes either -- the same dual shape `Objective.foes` has.
    A converted module writes what the page printed; the tracked fixture
    writes the ref, because a name must not enter a tracked file.

    Any kind of scene may carry one. An adventure hands things over in a
    conversation, at the end of a fight and over a night's rest, so this
    is in no kind's `unused` list.
    """

    #: The module's word for the thing, or its item ref.
    what: str = ""
    count: int = 1


#: How many beats a roleplay scene runs before it gives up and takes its first
#: exit. A backstop, not a target -- a scene that has not resolved in six
#: exchanges is a scene the module did not finish writing, and a loop with no
#: bound is worse than an early exit.
MAX_BEATS = 6


@dataclass(frozen=True)
class Try:
    """One of a challenge's skills, and what either result means.

    The challenge-side twin of an `Affordance`'s `win`/`lose`. Both are
    **facts** -- what is true because the roll went that way -- not
    narration: the DM is handed them to deliver, and may not state more.
    """

    skill: str
    win: str = ""
    lose: str = ""


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
class Person:
    """Somebody the module has, as opposed to somebody in one scene.

    > *Keep track of the way you have important NPCs act so you can
    > maintain consistency if the same character appears again.*

    We could not: `Npc` lived on a `Scene` and nowhere else, so the same
    person across three scenes was three independent entries and nothing
    made them agree. Voice and looks drifted, `wants` could contradict
    itself, and a name typo made a second person in silence.

    **The split is the one #944 settles in its own last paragraph**:
    `wants`, `voice` and `looks` are the person's and live here;
    `knows`, `hides` and `unseen` are the scene's and stay on `Npc`,
    because what somebody will tell you depends on where you meet them.

    This is also the half `story/graph.py` deliberately does not carry: a
    graph records what is *true* about a person, and how they are *played*
    is a presentation property rather than a fact.
    """

    name: str
    wants: str = ""
    voice: str = ""
    looks: str = ""


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
    #: in a single clause"* -- in the opening scene's read-aloud. Three scenes later the
    #: DM sees only that scene's text, which is somebody else's speech, so
    #: it had nothing about that character and guessed: *"Orsa nodded slightly, her
    #: eyes downcast"*, twice in one scene, for a character the player had
    #: read described as a man one scene earlier.
    #:
    #: `voice` is how they speak and was never meant to carry this. A
    #: description belongs on the person, not in the prose of whichever
    #: scene happened to introduce them.
    #:
    #: **Lead with the pronoun.** Measured, n=10 per arm, by exact search
    #: rather than a judge: the DM used a pronoun for a described character
    #: **2 of 10** times with the description written as prose, 4 of 10
    #: with no description at all, and **8 of 10** with "a man, he/him"
    #: first. The rest were vague constructions that avoid referring to
    #: the person.
    #:
    #: It is **not** a fix for a wrong pronoun, and the field does not
    #: claim to be: zero of thirty samples misgendered anybody, while live
    #: play produced it twice. The probe cannot reproduce it, which is true
    #: of every probe in this component.
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
    #: What this scene hands the party, applied when it plays. Any kind may
    #: carry one -- see `Grant` and `loot.hand_over`.
    grants: tuple[Grant, ...] = ()
    #: Environmental dangers the party is exposed to while this scene
    #: happens, from `DANGERS`. Any kind may carry them: a conversation on
    #: a mountainside is as cold as a fight on one.
    exposure: tuple[str, ...] = ()
    #: How long the scene takes, in hours. Only read when `exposure` is
    #: stated -- an Endurance check falls due every `EXPOSURE_HOURS`.
    hours: int = 0
    #: What losing this scene costs. Any kind may carry one -- see `Cost`.
    cost: tuple[Cost, ...] = ()

    # -- roleplay ------------------------------------------------------------
    #: Who is here to be talked to.
    npcs: tuple[Npc, ...] = ()
    #: What can be tried. An empty list makes the scene a read-aloud that
    #: advances, which is what every scene was before this existed.
    affordances: tuple[Affordance, ...] = ()
    #: Sensory details the DM may spend, **one per beat, each once**.
    #:
    #: The book's own model of scene text is an opening description plus a
    #: pool consumed as the scene runs, not one block re-presented every
    #: beat:
    #:
    #: > *You don't need to pile atmospheric details into your very first
    #: > description [...] listing a variety of details that might appear
    #: > to every sense, and break them out to add some flair to your
    #: > narratives as the adventure progresses.*
    #:
    #: Same shape as `Affordance.once` and `Playing.spent`, and the point
    #: is that a spent detail **leaves the prompt** -- so anything
    #: one-time stops being re-offered because it is no longer there to
    #: read, rather than because the DM was told not to repeat it. #936.
    details: tuple[str, ...] = ()
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
    #: How ready the opposition is -- see `READINESS`. `asleep` or
    #: `distracted` gives the party a surprise round.
    readiness: str = "ready"
    #: What the fight is *for*, when it is for something other than killing
    #: everything. `None` is the overwhelming majority and means the scene is
    #: fielded, played and judged exactly as it was before objectives existed
    #: -- see `story/objective.py` and `run._fight`.
    objective: Objective | None = None

    #: How big the room is, and what shape: `(width, height, kind)`, with
    #: `kind` one of `ROOM_KINDS`. Empty leaves the board the floor every
    #: fight has always been. #974.
    #:
    #: The printed table rolls one of ten chambers and **nine of them are
    #: smaller than that floor**, so a module that states its room is
    #: usually asking for a tighter fight than the default -- which is the
    #: point: a 6x8 chamber and a 10x16 hall are different fights with the
    #: same cast.
    room: tuple[int, int, str] = ()  # type: ignore[assignment]

    #: Creatures fighting **on the party's side**. #961.
    #:
    #: The imported adventure's encounter chapter is built on these: it
    #: says each of its encounters includes one or more allies, controlled
    #: by the players, and then prints a roster for every one of them --
    #: typically a handful of minion guards with map positions. Four of its
    #: encounters cannot be fielded as written without this.
    #:
    #: A `FoeSpec` on the other side, deliberately: the same `count`,
    #: `name`, `words`, `role` and `rank`, drawn by the same tiers, and
    #: arriving on the same schedule if the module says so. A second
    #: near-identical spec type would be a second set of rules to keep in
    #: step.
    #:
    #: **Not a companion character.** DMG2's companion is a party member
    #: built from formulas and it explicitly rules out the minions this
    #: fields -- *"minions are too weak to help out the party"*. That is
    #: #1015.
    allies: tuple[FoeSpec, ...] = ()

    # -- skill challenge ----------------------------------------------------
    complexity: int = 0
    #: Per-skill prose: what is now true because a check went that way.
    #: **The gap that blocked the beat loop on a challenge** (#932): an
    #: `Affordance` carries `win`/`lose` and `Director.react` is handed
    #: them and told to deliver them, which is what keeps the DM narrating
    #: the adventure rather than inventing it. A challenge's skills were
    #: bare strings with no text at all, so wiring the loop in would have
    #: given the DM a roll to narrate and nothing to narrate from.
    #:
    #: `primary` and `secondary` stay tuples of names, so every reader of
    #: them is unchanged; this sits alongside and is looked up by skill.
    tries: tuple[Try, ...] = ()
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

    def means(self, skill: str, *, won: bool) -> str:
        """What a check with this skill turning out that way means.

        Empty when the module said nothing, which is every challenge
        converted so far -- so a caller prints the roll and no more, which
        is exactly what it did before. #932.
        """
        for said in self.tries:
            if said.skill == skill.lower():
                return said.win if won else said.lose
        return ""

    def counts_toward(self, party_level: int) -> int:
        """How many encounters this scene is worth toward a milestone.

        The printed rule weights the count by level difference rather than
        taking every fight as one, and says so in as many words: an
        encounter **two or more levels lower** than the characters "is
        really easy, and it shouldn't contribute toward a milestone", while
        one **four or more levels higher** "should count as two
        encounters".

        So: 0, 1 or 2, and only a `combat` scene counts at all. The same
        page is explicit that a quest does not -- *"don't count a quest as
        an encounter for the purposes of earning action points"* -- and a
        conversation or a challenge is not an encounter either, which is
        what makes the `kind` test the rule rather than a shortcut.

        `level` falls back to the party's, which is the overwhelming
        majority of scenes and weighs 1.
        """
        if self.kind != "combat":
            return 0
        gap = (self.level or party_level) - party_level
        if gap <= -2:
            return 0
        return 2 if gap >= 4 else 1

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
    #: The people this module has, by name -- their `wants`, `voice` and
    #: `looks`, which travel between scenes. A scene naming one of them
    #: inherits those, and a scene that **contradicts** one is refused.
    #: Empty for every module written before this, which then behaves
    #: exactly as it did. #944.
    cast: tuple[Person, ...] = ()
    #: Why the party is doing any of this. Empty for every module written
    #: before this. #940.
    quests: tuple[Quest, ...] = ()
    #: Events that fire on the clock rather than on what the party did.
    #: Empty for every module converted so far, which is why nothing plays
    #: differently until one states an entry. See `Timed` and `run._due`.
    timeline: tuple[Timed, ...] = ()

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


def _as_objective(raw: Any, where: str,
                  problems: list[str]) -> Objective | None:
    """What the fight is for, or `None` when the scene does not say.

    **`None` and `{"kind": "defeat_all"}` are different answers** and both are
    legal. The first means no watcher is built and `_fight` keeps its original
    win condition; the second means the watcher runs and has to agree with it.
    Collapsing them would have made the no-objective control in `drivers.py`
    untestable, because there would be no way to field a fight that did *not*
    go through the new code.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        problems.append(
            f"{where}: an objective must be an object, got {type(raw).__name__}")
        return None
    kind = str(raw.get("kind", "defeat_all")).strip().lower()
    if kind not in OBJECTIVES:
        problems.append(
            f"{where}: objective {kind!r} is not one of {', '.join(OBJECTIVES)}")
        return None
    position = str(raw.get("position", "")).strip().lower()
    if kind == "hold":
        if not position:
            # Defaulted rather than refused: the party spawns in the west, so
            # it defends its own end. `objective.py` explains the placement.
            position = "west"
        if position not in POSITIONS:
            problems.append(
                f"{where}: position {position!r} is not one of "
                f"{', '.join(POSITIONS)}")
            position = ""
    elif position:
        problems.append(f"{where}: objective {kind!r} takes no position")
    rounds = raw.get("rounds", OBJECTIVE_ROUNDS)
    if not isinstance(rounds, int) or rounds < 1:
        problems.append(f"{where}: objective rounds must be a positive integer")
        rounds = OBJECTIVE_ROUNDS
    share = raw.get("share", OBJECTIVE_SHARE)
    if not isinstance(share, int | float) or not 0 < float(share) < 1:
        problems.append(f"{where}: objective share must be between 0 and 1")
        share = OBJECTIVE_SHARE
    harder, easier = bool(raw.get("harder")), bool(raw.get("easier"))
    if harder and easier:
        # Refused rather than cancelled out, because an author who wrote both
        # meant one of them and a silent no-op hides which.
        problems.append(f"{where}: an objective cannot be both harder and easier")
        harder = easier = False
    foes = tuple(str(f).strip() for f in raw.get("foes", ()) if str(f).strip())
    if kind == "defeat_foe" and not foes:
        problems.append(f"{where}: defeat_foe needs at least one ref in foes")
    elif kind != "defeat_foe" and foes:
        problems.append(f"{where}: objective {kind!r} takes no foes")
    leaks = raw.get("leaks", 0)
    if not isinstance(leaks, int) or leaks < 0:
        problems.append(f"{where}: objective leaks must be a whole number")
        leaks = 0
    return Objective(
        kind=kind, foes=foes, share=float(share), rounds=rounds,
        position=position, leaks=leaks, harder=harder, easier=easier,
        says=str(raw.get("says", "")).strip(),
    )


def _as_room(
    raw: Any, where: str, problems: list[str],
) -> tuple[int, int, str]:
    """A stated chamber, or `()` for the floor every fight has used. #974."""
    if raw is None:
        return ()  # type: ignore[return-value]
    if not isinstance(raw, dict):
        problems.append(
            f"{where}: a room must be an object with width and height, got "
            f"{type(raw).__name__}")
        return ()  # type: ignore[return-value]
    size = []
    for side in ("width", "height"):
        got = raw.get(side)
        if not isinstance(got, int) or not ROOM_MIN <= got <= ROOM_MAX:
            problems.append(
                f"{where}: room {side} must be an integer between "
                f"{ROOM_MIN} and {ROOM_MAX}, got {got!r}")
            return ()  # type: ignore[return-value]
        size.append(got)
    kind = str(raw.get("kind", "rectangle")).strip().lower()
    if kind not in ROOM_KINDS:
        problems.append(
            f"{where}: room kind {kind!r} is not one of "
            f"{', '.join(ROOM_KINDS)}")
        return ()  # type: ignore[return-value]
    return (size[0], size[1], kind)


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

    def whole(key: str, floor: int = 0) -> int:
        got = raw.get(key, 0)
        if not isinstance(got, int) or got < floor:
            problems.append(
                f"{where}: {key} must be an integer of at least {floor}, "
                f"got {got!r}")
            return 0
        return got

    at = whole("at") or 1
    if "at" in raw and (not isinstance(raw["at"], int) or raw["at"] < 1):
        problems.append(f"{where}: at must be round 1 or later, got {raw['at']!r}")
        at = 1
    every = whole("every")
    until = whole("until")
    # **A repeat must be capped.** The module's own wave stops on either a
    # landmark being destroyed or a round cap -- the round cap is the half
    # this can express, and without it a wave fields a creature every round until
    # `MAX_ROUNDS`, which is an unbounded fight and, if it earned XP, an
    # unbounded reward.
    if every and not until:
        problems.append(
            f"{where}: a repeating wave needs `until` -- reinforcements with "
            "no last round are an unbounded fight")
    if until and not every:
        problems.append(
            f"{where}: `until` only means something with `every`; a wave "
            "that arrives once arrives on `at`")
    if until and every and until < at:
        problems.append(
            f"{where}: until {until} is before at {at}, so this wave never "
            "arrives")
    return FoeSpec(
        count=count, name=str(raw.get("name", "")).strip(),
        words=words, role=role, rank=rank,
        at=at, every=every, until=until,
        worth=bool(raw.get("worth", True)),
    )


def _as_quest(raw: Any, where: str, problems: list[str]) -> Quest | None:
    """One quest. Its scene and affordance ids are checked in `parse`."""
    if not isinstance(raw, dict):
        problems.append(f"{where}: a quest must be an object")
        return None
    ident = str(raw.get("id", "")).strip()
    if not ident:
        problems.append(f"{where}: a quest needs an id")
        return None
    kind = str(raw.get("kind", "major")).strip().lower() or "major"
    if kind not in QUEST_KINDS:
        problems.append(
            f"{where}: quest {ident!r} is {kind!r}; it must be one of "
            f"{', '.join(QUEST_KINDS)}"
        )
        kind = "major"
    xp = raw.get("xp", 0)
    if not isinstance(xp, int) or isinstance(xp, bool) or xp < 0:
        problems.append(
            f"{where}: quest {ident!r} has xp {xp!r}; it must be a "
            "non-negative integer"
        )
        xp = 0
    done = str(raw.get("done_when", "")).strip()
    if not done:
        problems.append(
            f"{where}: quest {ident!r} has no `done_when`, so nothing could "
            "ever complete it -- name the scene or affordance that does"
        )
        return None
    return Quest(
        id=ident, kind=kind, xp=xp, done_when=done,
        offered_by=str(raw.get("offered_by", "")).strip(),
        fails=tuple(str(f).strip() for f in raw.get("fails", ())
                    if str(f).strip()),
        says=str(raw.get("says", "")).strip(),
    )


def _as_cost(raw: Any, where: str, problems: list[str]) -> Cost | None:
    """One `cost` entry. The vocabulary is closed, like every other here."""
    if not isinstance(raw, dict):
        problems.append(f"{where}: a cost must be an object")
        return None
    what = str(raw.get("what", "")).strip().lower()
    if what not in COSTS:
        problems.append(
            f"{where}: cost {what!r} is not one of {', '.join(COSTS)}"
        )
        return None
    each = raw.get("each", 1)
    if not isinstance(each, int) or isinstance(each, bool) or each < 1:
        problems.append(
            f"{where}: cost {what!r} has each {each!r}; it is how many per "
            "character and must be a positive integer"
        )
        each = 1
    return Cost(what=what, each=each,
                says=str(raw.get("says", "")).strip())


def _as_timed(raw: Any, where: str, problems: list[str]) -> Timed | None:
    """One timeline entry. Its `scene` and `unless` are checked in `parse`,
    which is the only place that knows every scene id and flag."""
    if not isinstance(raw, dict):
        problems.append(f"{where}: a timeline entry must be an object")
        return None
    scene = str(raw.get("scene", "")).strip()
    if not scene:
        problems.append(f"{where}: a timeline entry needs a 'scene' to fire")
        return None
    when = raw.get("when", 0)
    if not isinstance(when, int) or isinstance(when, bool) or when < 1:
        problems.append(
            f"{where}: when is {when!r}; it is which tick the entry is due "
            "on and must be a positive integer"
        )
        return None
    unit = str(raw.get("unit", "scene")).strip().lower()
    if unit not in UNITS:
        problems.append(
            f"{where}: unit {unit!r} is not one of {', '.join(UNITS)}"
        )
        unit = "scene"
    return Timed(
        when=when, scene=scene, unit=unit,
        unless=str(raw.get("unless", "")).strip(),
        says=str(raw.get("says", "")).strip(),
    )


def _as_grant(raw: Any, where: str, problems: list[str]) -> Grant | None:
    """One `grants` entry.

    Deliberately **not** resolved here. `_as_scene` runs at validation time
    and must work with no database -- `--validate` is the one command a
    converter runs before anything is built -- so whether the word matches
    an item is `loot.find`'s question at grant time, and an unmatched one
    is reported there rather than refused here.
    """
    if not isinstance(raw, dict):
        problems.append(f"{where}: a grant must be an object")
        return None
    what = str(raw.get("what", "")).strip()
    if not what:
        problems.append(f"{where}: a grant needs a 'what' -- an item ref, or "
                        "the module's own word for the thing")
        return None
    count = raw.get("count", 1)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        problems.append(
            f"{where}: grant {what!r} has count {count!r}; it must be a "
            "positive integer"
        )
        count = 1
    return Grant(what=what, count=count)


def _as_person(raw: Any, where: str, problems: list[str]) -> Person | None:
    """One cast entry: the half of a character that travels."""
    if not isinstance(raw, dict):
        problems.append(f"{where}: a cast entry must be an object")
        return None
    name = str(raw.get("name", "")).strip()
    if not name:
        problems.append(f"{where}: a cast entry needs a name")
        return None
    return Person(
        name=name,
        wants=str(raw.get("wants", "")).strip(),
        voice=str(raw.get("voice", "")).strip(),
        looks=str(raw.get("looks", "")).strip(),
    )


def _agree(scene_id: str, npcs: tuple[Npc, ...], cast: dict[str, Person],
           problems: list[str]) -> tuple[Npc, ...]:
    """Fill a scene's npcs from the cast, and refuse a contradiction.

    **Inherit when the scene is silent, refuse when it disagrees.** The
    alternative -- preferring one side -- is how the drift in #944 stayed
    invisible: whichever value won, the other was written down and
    ignored, and nothing said so. A module that means to change somebody
    changes the cast entry.

    A name not in the cast is left alone rather than refused, because a
    walk-on who appears once is legitimate and a cast is not required to
    be exhaustive. What that costs is the typo case: a misspelling makes a
    walk-on rather than a complaint. Said out loud here because #944 hoped
    the refusal would fall out for free, and it only does if the cast is
    exhaustive -- which would refuse every one-scene character.
    """
    # No `if not cast` fast path: with an empty cast every npc takes the
    # walk-on branch and comes back unchanged, so the guard changed
    # nothing -- a plant that removed it stayed green. Fifth dead guard of
    # this shape on this branch.
    out: list[Npc] = []
    for who in npcs:
        known = cast.get(who.name)
        if known is None:
            out.append(who)
            continue
        for field_ in ("wants", "voice", "looks"):
            mine = getattr(who, field_)
            theirs = getattr(known, field_)
            if mine and theirs and mine != theirs:
                problems.append(
                    f"scene {scene_id!r}: npc {who.name!r} sets {field_} to "
                    f"{mine!r} and the cast says {theirs!r} -- change the "
                    "cast entry rather than contradicting it here"
                )
        out.append(replace(
            who,
            wants=who.wants or known.wants,
            voice=who.voice or known.voice,
            looks=who.looks or known.looks,
        ))
    return tuple(out)


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

    # **Both forms accepted**: a bare skill name, which is what every
    # converted scene holds, or an object carrying what either result
    # means. Mixing them in one list is fine -- a module adding prose to
    # the two skills the page describes should not have to rewrite the
    # other four.
    def _skills(key: str) -> tuple[tuple[str, ...], list[Try]]:
        names: list[str] = []
        said: list[Try] = []
        for item in raw.get(key, ()):
            if isinstance(item, dict):
                skill = str(item.get("skill", "")).strip().lower()
                if not skill:
                    problems.append(
                        f"{where}: a {key} entry has no skill: {item!r}")
                    continue
                names.append(skill)
                said.append(Try(
                    skill=skill,
                    win=str(item.get("win", "")).strip(),
                    lose=str(item.get("lose", "")).strip()))
                continue
            if str(item).strip():
                names.append(str(item).strip().lower())
        return tuple(names), said

    primary, primary_says = _skills("primary")
    secondary, secondary_says = _skills("secondary")
    tries = tuple(primary_says + secondary_says)
    for skill in (*primary, *secondary):
        if skill not in SKILLS:
            problems.append(
                f"{where}: {skill!r} is not a skill. Known: {', '.join(sorted(SKILLS))}"
            )
    seen_twice = {s for s in (*primary, *secondary)
                  if (primary + secondary).count(s) > 1}
    if seen_twice:
        # A skill listed twice is two different DCs for one skill, and
        # `band_of` answers with the primary -- so the secondary entry is
        # silently dead, along with any prose on it.
        problems.append(
            f"{where}: {', '.join(sorted(seen_twice))} listed more than "
            "once across primary and secondary")

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
    if tries and kind != "skill_challenge":
        problems.append(
            f"{where}: a {kind} scene states what a skill check means, but "
            "only a skill_challenge rolls them")

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
    allies = tuple(
        _as_foe(a, where, problems) for a in raw.get("allies", ())
    )
    room = _as_room(raw.get("room"), where, problems)
    if room and kind != "combat":
        problems.append(
            f"{where}: a {kind} scene states a room, but only a combat "
            "scene builds a board")
    if allies and kind != "combat":
        problems.append(
            f"{where}: a {kind} scene lists allies, but only a combat scene "
            "fields anybody")
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
    details = tuple(
        str(d).strip() for d in raw.get("details", ()) or () if str(d).strip()
    )
    beats = raw.get("max_beats", MAX_BEATS)
    if not isinstance(beats, int) or beats < 1:
        problems.append(f"{where}: max_beats must be a positive integer")
        beats = MAX_BEATS
    exposure = tuple(
        str(w).strip().lower() for w in raw.get("exposure", ()) or ()
        if str(w).strip()
    )
    for word in exposure:
        if word not in DANGERS:
            problems.append(
                f"{where}: exposure {word!r} is not one of "
                f"{', '.join(sorted(DANGERS))}"
            )
    hours = raw.get("hours", 0)
    if not isinstance(hours, int) or isinstance(hours, bool) or hours < 0:
        problems.append(
            f"{where}: hours is {hours!r}; it is how long the scene takes "
            "and must be a non-negative integer"
        )
        hours = 0
    if exposure and not hours:
        problems.append(
            f"{where}: states exposure {list(exposure)} and no hours, so no "
            "Endurance check would ever fall due -- say how long it takes"
        )
    cost = tuple(
        c for c in (
            _as_cost(r, f"{where} cost {i + 1}", problems)
            for i, r in enumerate(raw.get("cost", ()) or ())
        ) if c is not None
    )
    readiness = str(raw.get("readiness", "ready")).strip().lower() or "ready"
    if readiness not in READINESS:
        problems.append(
            f"{where}: readiness {readiness!r} is not one of "
            f"{', '.join(READINESS)}"
        )
        readiness = "ready"
    objective = _as_objective(raw.get("objective"), where, problems)
    grants = tuple(
        g for g in (
            _as_grant(r, f"{where} grant {i + 1}", problems)
            for i, r in enumerate(raw.get("grants", ()) or ())
        ) if g is not None
    )
    if kind == "combat" and not foes:
        problems.append(f"{where}: a combat scene needs at least one foe line")

    # **A field the kind does not use is an authoring mistake, not a default.**
    # A rest scene carrying a foe list plays as a rest and silently drops the
    # fight; a roleplay scene carrying a complexity never counts a success.
    # Both read exactly like a scene that works, which is why they are refused.
    unused = {
        "roleplay": ("foes", "terrain", "complexity", "primary", "secondary",
                     "objective", "readiness"),
        # `details` is roleplay-only: nothing else runs beats to spend them.
        "skill_challenge": ("foes", "terrain", "affordances", "objective",
                            "readiness", "details"),
        "combat": ("complexity", "primary", "secondary", "affordances",
                   "details"),
        "rest": ("foes", "terrain", "complexity", "primary", "secondary",
                 "affordances", "npcs", "lore", "objective", "readiness",
                 "details"),
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
        grants=grants,
        exposure=exposure,
        hours=hours,
        cost=cost,
        npcs=npcs,
        affordances=affordances,
        details=details,
        lore=lore,
        max_beats=beats,
        difficulty=difficulty,
        xp=int(raw.get("xp", 0) or 0),
        terrain=terrain,
        foes=foes,
        allies=allies,
        room=room,
        tactics=str(raw.get("tactics", "")),
        readiness=readiness,
        objective=objective,
        complexity=complexity,
        level=int(raw.get("level", 0) or 0),
        primary=primary,
        secondary=secondary,
        tries=tries,
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

    cast_list = tuple(
        c for c in (
            _as_person(r, f"cast entry {i + 1}", problems)
            for i, r in enumerate(raw.get("cast", ()) or ())
        ) if c is not None
    )
    cast = {c.name: c for c in cast_list}
    if len(cast) != len(cast_list):
        problems.append(
            "the cast names somebody twice, so a scene naming them could "
            "inherit either entry"
        )

    scenes: dict[str, Scene] = {}
    order: list[str] = []
    for i, raw_scene in enumerate(raw.get("scenes", ())):
        scene = _as_scene(raw_scene, i, problems)
        if scene is None:
            continue
        if scene.npcs:
            scene = replace(
                scene, npcs=_agree(scene.id, scene.npcs, cast, problems))
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

    flags = {
        str(k): int(v) for k, v in (raw.get("flags") or {}).items()
        if isinstance(v, int)
    }

    timeline = tuple(
        t for t in (
            _as_timed(r, f"timeline entry {i + 1}", problems)
            for i, r in enumerate(raw.get("timeline", ()) or ())
        ) if t is not None
    )
    for i, entry in enumerate(timeline):
        where = f"timeline entry {i + 1}"
        if entry.scene not in scenes:
            problems.append(
                f"{where}: fires {entry.scene!r}, which is not a scene"
            )
        # **`unless` is a scene id or a flag, and a typo in it is the worst
        # kind of mistake here**: an entry whose cancel condition can never
        # be true is an inevitable event wearing an escape hatch, and it
        # would play as though the party simply never managed to stop it.
        if entry.unless and entry.unless not in scenes and entry.unless not in flags:
            problems.append(
                f"{where}: unless {entry.unless!r} is neither a scene nor a "
                "declared flag, so nothing could ever cancel this entry"
            )

    # Unreachable scenes are reported, not refused: a converter working through
    # a long module has half a graph for a while, and `--validate` is the tool
    # that should tell them which half.
    #
    # **A timeline's own scenes are roots.** Nothing exits to them by
    # construction -- that is what being on the clock means -- so without
    # this every timed event reported "nothing leads to it" and the one
    # genuine orphan would be lost among them.
    if start in scenes:
        roots = [start, *(t.scene for t in timeline if t.scene in scenes)]
        seen, stack = set(roots), list(roots)
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

    # **A challenge no harder than the party is numerous.** DMG2:
    #
    # > *As a guideline, make skill challenge complexity no higher than 1
    # > above the number of characters in the party.*
    #
    # So a party of two should not face a complexity-4 challenge. Checked
    # here rather than in `_as_scene` because the party size is the
    # module's and a scene does not know it -- which is why the harder
    # refusal (a complexity outside the table) has existed for longer than
    # this easier one. #939.
    quests = tuple(
        q for q in (
            _as_quest(r, f"quest {i + 1}", problems)
            for i, r in enumerate(raw.get("quests", ()) or ())
        ) if q is not None
    )
    by_id = {q.id: q for q in quests}
    if len(by_id) != len(quests):
        problems.append("the module names the same quest twice")
    affordances = {
        a.id for s in scenes.values() for a in s.affordances
    }
    for quest in quests:
        where = f"quest {quest.id!r}"
        if quest.done_when not in scenes and quest.done_when not in affordances:
            problems.append(
                f"{where}: `done_when` is {quest.done_when!r}, which is "
                "neither a scene nor an affordance in this module"
            )
        if quest.offered_by and quest.offered_by not in scenes:
            problems.append(
                f"{where}: `offered_by` is {quest.offered_by!r}, which is "
                "not a scene in this module"
            )
        # **The trivially redundant case.** DMG2: *"don't reward the
        # characters twice for the same actions [...] 'defeat ten
        # encounters of your level' isn't a quest."* A quest finished by
        # the very scene that grants it is paid for arriving, which is the
        # clearest instance and the only one checkable without walking
        # every path. The general case -- a goal the scenes it spans
        # satisfy anyway -- is a reachability question and is left on the
        # issue.
        if quest.offered_by and quest.offered_by == quest.done_when:
            problems.append(
                f"{where}: granted and completed by the same scene "
                f"{quest.done_when!r}, so it pays the party for arriving"
            )
        for other in quest.fails:
            if other not in by_id:
                problems.append(
                    f"{where}: fails {other!r}, which is not a quest in "
                    "this module"
                )
            elif other == quest.id:
                problems.append(f"{where}: fails itself")

    size = int(raw.get("party_size", 4) or 4)
    for scene in scenes.values():
        # No `kind != "skill_challenge"` guard: `complexity` is in every
        # other kind's `unused` list, so a non-challenge scene is refused
        # for carrying one at all and always has 0 here. A plant that
        # removed the guard changed nothing -- sixth dead guard of this
        # shape on this branch.
        if scene.complexity > size + 1:
            problems.append(
                f"scene {scene.id!r}: complexity {scene.complexity} for a "
                f"party of {size} -- the printed guideline is no higher "
                f"than one above the party's number, so {size + 1} is the "
                "most this module should ask for"
            )

    level = raw.get("party_level", 1)
    if not isinstance(level, int) or not 1 <= level <= 30:
        problems.append(f"party_level must be 1-30, got {level!r}")
        level = 1

    if problems:
        raise ModuleError(path, problems)
    return Module(
        id=module_id, scenes=scenes, start=start,
        party_level=level,
        party_size=size,
        edition=str(raw.get("edition", "")).strip(),
        flags=flags,
        cast=cast_list,
        quests=quests,
        timeline=timeline,
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
