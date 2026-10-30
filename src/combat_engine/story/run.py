"""Playing a module: one scene at a time, with the party carried between them.

The campaign loop. `story/__init__.py` fields one fight and `Party` already
survives several; this is what decides which fight, what happens between them,
and when the adventure is over.

## One step at a time, deliberately

`step` plays exactly one scene and returns. It does not loop, because three
different callers need to be in charge of the loop and none of them can be
written in terms of another: `--no-dm` prints and reads a menu, the model
narrates and calls tools between scenes (#794), and a headless run plays
straight through for an instrument. A `play` that owned the loop would have to
grow a callback for each of them.

## Where the seeds come from

Every scene derives its own stream from the campaign seed and the scene id --
`Random(f"{seed}:{module}:{scene}")`, the key shape `Party.of` already uses. So
a campaign replays, and **changing one scene does not move the dice in any
other**. A single stream threaded through the campaign would make adding a
conversation change the monsters in the fight after it.

## What a combat scene does not get yet

`terrain.dress` has no way to be told what sort of place a fight is in, so the
scene's `terrain` words are carried, printed, and **not yet applied**. That is
#539, whose open question is exactly this -- it offers `dress(words=)` with
"the caller says" as option (1), and this is the caller. Flagged in the step's
notes rather than silently dropped, because 54 `c.terrain()` gates in content
are waiting on it and a module that says a cellar is flooded should not look
like it worked.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

from combat_engine.engine import Ident, Side, Team
from combat_engine.engine.components import Condition, Conditions, Position
from combat_engine.engine.ecs import World
from combat_engine.engine.query import alive
from combat_engine.engine.turns import Encounter
from combat_engine.policy import install, take_turn
from combat_engine.policy.doctrine import DoctrinePolicy

from . import PARTY, PARTY_AT, Party, field_encounter, harvest, loot, tension
from . import beat as beat_mod
from . import formation as formation_mod
from . import table as table_mod
from . import xp as xp_mod
from .cast_list import resolve
from .challenge import Chooser
from .challenge import play as play_challenge
from .module import (
    CAUGHT,
    DANGERS,
    EXPOSURE_HOURS,
    SHELTERED,
    Module,
    Scene,
)
from .objective import watcher
from .reflavour import apply as apply_flavour
from .save import Campaign

#: A fight that has not finished by here is a grind, not a fight. The charter's
#: target is 7-8 rounds; this is the backstop, not the goal.
MAX_ROUNDS = 40

#: Where a campaign's own record goes, beside the per-fight transcripts.
#: Git-ignored, like everything in `logs/`.
def campaign_log(campaign: Campaign) -> Path:
    from combat_engine.transcript import LOGS

    return LOGS / f"{campaign.module}.campaign.jsonl"


def record_scene(campaign: Campaign, made: Step) -> str:
    """Append one scene to the campaign's record. Returns where it went.

    **Only fights were recorded and that was backwards.** `_fight` writes a
    2,000-event transcript that is already reproducible from its board seed,
    while a roleplay scene -- the part a person would actually re-read, and
    the part the model writes -- left nothing at all behind. #799.

    One line per scene rather than per beat, so a scene is a unit a reader
    can skim and `Step` goes in as it already is.
    """
    from combat_engine.transcript import LOGS

    LOGS.mkdir(parents=True, exist_ok=True)
    where = campaign_log(campaign)
    row = {
        "scene": made.scene.id,
        "kind": made.scene.kind,
        "name": made.scene.name,
        "outcome": made.outcome,
        # What the fight was judged on, so a log reads as a session rather
        # than as a list of wins. `""` for a scene that stated no objective.
        "objective": made.objective,
        "clean": made.clean,
        "next": made.next_id,
        "rounds": made.rounds,
        "surprised": made.surprised,
        "stood": made.stood,
        "enemies": made.enemies,
        "transcript": made.transcript,
        "notes": made.notes,
        "party": party_line(campaign),
        "beats": beat_mod.as_json(made.played) if made.played else [],
        # The module's own text, which is what a roleplay scene *is* when
        # nobody is playing it. Carried so a log reads as a session rather
        # than as a list of outcomes.
        "lines": made.lines,
    }
    with where.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    return str(where)


#: What wrote a line, so a reader can tell canon from dice from invention.
#:
#: **The split is the same one the graph draws between `page`, `earned`
#: and `invented`**, and it is not decoration: who wrote a line governs
#: how much it should be trusted. The adventure's prose is canon, a roll
#: is a fact the dice produced, and the DM's paragraph is a model's
#: invention that is allowed to be wrong. A reader shown all three in one
#: voice cannot tell them apart, which is the thing this whole component
#: spends its effort on. #930.
KINDS = ("scene", "recall", "roll", "mine", "dm", "note", "exit")


class Line(str):
    """A printed line that remembers what kind of thing it is.

    **A `str` subclass rather than a dataclass, deliberately.** `lines`
    is read in a dozen places that do `" ".join(...)`, `ln.strip()` and
    `print(ln)` -- in `play.py`, `dm.py`, the campaign log and nine
    drivers -- and every one of them keeps working unchanged against a
    string that happens to carry an attribute. A dataclass would have
    meant touching all of them to gain nothing a reader of the CLI can
    see.

    **The sharp edge, stated because it will bite somebody:** any
    transformation returns a plain `str` and drops the kind.
    `line.strip()` is text, not a `Line`. Carry the object until the last
    moment and read `.kind` off the original.
    """

    kind: str

    def __new__(cls, text: str, kind: str = "scene") -> Line:
        made = super().__new__(cls, text)
        made.kind = kind if kind in KINDS else "scene"
        return made


@dataclass
class Step:
    """What one scene did."""

    scene: Scene
    #: `"won"`, `"lost"`, `"done"` -- or `"skipped"` when nothing could be
    #: fielded. A roleplay scene is always `"done"`.
    outcome: str = "done"
    #: Where play goes next. Empty ends the module.
    next_id: str = ""
    #: Human-readable lines about what happened. The caller prints them.
    lines: list[Line] = field(default_factory=list)
    #: Things the reader should know that are not the story -- a budget clamp,
    #: a creature deferred, terrain not yet applied.
    notes: list[str] = field(default_factory=list)
    rounds: int = 0
    enemies: list[str] = field(default_factory=list)
    #: The objective kind this fight was judged on, or `""` when the scene
    #: stated none and the old win condition decided it.
    objective: str = ""
    #: The objective was met and nobody went down doing it. Recorded and not
    #: yet spent: the thing that would pay for it is the XP award, which does
    #: not exist (#967). Here now so that award has something to read.
    clean: bool = False
    #: Where the party actually stood when the fight began, in party
    #: order, read off the board after it was fielded.
    #:
    #: **Recorded because the wiring is otherwise invisible**: a driver can
    #: call `field_encounter(squares=)` directly and prove the squares
    #: work while `_fight` quietly passes none, which is exactly what a
    #: green plant showed. #994.
    stood: list[tuple[int, int]] = field(default_factory=list)
    #: How many of the opposition **actually carried SURPRISED** after
    #: `start`, counted off the board rather than from the list handed to
    #: it.
    #:
    #: **Recorded because the effect is otherwise unobservable**, which is
    #: this component's own rule: the condition lives on a board that does
    #: not outlive the fight, and all four readiness states finished the
    #: fixture fight in the same number of rounds -- so a driver asserting
    #: on the outcome could not tell a surprise round from none. #945.
    surprised: int = 0
    #: How the fight went, one phrase from `beat.FIGHTS`. Empty for any
    #: scene that is not a fight. #943.
    aftermath: str = ""
    #: Where the blow-by-blow went, for a combat scene. Empty otherwise.
    transcript: str = ""
    #: The beats, for a roleplay scene that had any. Empty otherwise.
    played: beat_mod.Playing | None = None

    #: Where a line goes the moment it happens, as well as into `lines`.
    #:
    #: **A scene is assembled and then printed, which is right for an
    #: instrument and unplayable by a person.** Driving the CLI by hand, the
    #: first thing it does is ask the human what their character says --
    #: before the scene text has been printed, because that text is sitting
    #: in `lines` waiting for the scene to finish. You answer three prompts
    #: blind and then read what you were answering.
    #:
    #: Set this and every line is out the moment it exists. `play.py` sets
    #: it when there is a terminal and nothing else does, so `check.py` and
    #: the drivers keep the batched behaviour they assert on.
    echo: Callable[[Line], None] | None = None

    def say(self, line: str, kind: str = "scene") -> None:
        made = Line(line, kind)
        self.lines.append(made)
        if self.echo is not None:
            self.echo(made)


#: Who joins when a module wants more than the standard four, in order.
#:
#: `story.PARTY` is defender, leader, striker, controller -- one of each role,
#: which is what a published encounter is built against. Past four, the next
#: ones double up a role rather than reaching for something exotic: a second
#: striker, then a second defender, then a second leader. A module asking for
#: six gets a party that still covers every role twice over, which is the
#: shape its own difficulty assumes.
EXTRAS = ["ranger", "paladin", "warlord", "warlock"]


def party_for(size: int) -> list[str]:
    """The classes a party of that size is built from.

    **`module.party_size` was validated, printed by `--validate`, and then
    read by nothing.** `begin` built `story.PARTY` -- a fixed four -- whatever
    the module said, so an adventure written for five 1st-level characters was
    played by four and its own weak-party guidance never applied. Found by
    converting a real module, where `--validate` printed "5 characters" and
    the run then fielded four.

    Clamped to at least one and at most the classes available, because a
    module is user-supplied data and `party_size: 0` should field somebody
    rather than raise three scenes later.
    """
    want = max(1, min(int(size or len(PARTY)), len(PARTY) + len(EXTRAS)))
    return [*PARTY, *EXTRAS][:want]


def begin(module: Module, *, seed: int = 0, pcs: list[str] | None = None) -> Campaign:
    """A fresh campaign at the module's opening scene."""
    party = Party.of(
        pcs or party_for(module.party_size), level=module.party_level, seed=seed,
    )
    return Campaign(
        module=module.id, seed=seed, scene=module.start,
        party=party, flags=dict(module.flags),
    )


def _stream(campaign: Campaign, scene: Scene, what: str = "") -> Random:
    """One scene's own dice. See the module docstring."""
    return Random(f"{campaign.seed}:{campaign.module}:{scene.id}:{what}")


def seed_for(campaign: Campaign, scene: Scene, what: str) -> int:
    """A scene's seed for something that wants an int rather than a stream.

    **`hash()` must not appear anywhere near this.** The first version of
    `_fight` seeded its board with `campaign.seed + abs(hash(scene.id)) %
    100000`, and `hash()` on a `str` is salted per process -- so the same
    campaign on the same seed fielded different monsters and played different
    fights in every new interpreter. Measured: three runs of one chapter gave
    5.5, 4.5 and 6.0 rounds a fight, and one of the three wiped the party
    where the others finished comfortably.

    It survived the determinism check because that check ran both campaigns
    **in one process**, where `hash()` is stable for the life of the
    interpreter. The probe could not see the thing it was written to see.

    `Random(str)` is seeded from the string's bytes and is stable across
    processes, which `drivers.py campaign_replays` now asserts by running a
    whole campaign in a *subprocess* twice.
    """
    return _stream(campaign, scene, what).randrange(1 << 30)


def _enemy_eids(world: World) -> list[int]:
    """Spawned enemies in spawn order, which is the order the refs went in.

    Entity ids are handed out in sequence, so sorting by id recovers the order
    `field_encounter` spawned the pool in -- which is what lets a flavour be
    matched to the creature it was built for. Matching by ref instead would
    pick the wrong one whenever a scene fields two of the same creature under
    different flavours.
    """
    return sorted(
        eid for eid, side in world.each(Side) if side.team is Team.ENEMY
    )


def _win(scene: Scene, step: Step) -> None:
    """Hand the party the fight without playing it. God mode.

    **For testing the story half without the combat half in the way.** The
    AI policy is the weak part of the engine right now, and a campaign that
    loses a fight in chapter 1 stops -- so every attempt to read four
    scenes of conversation was costing four fights and often ending early.

    Nothing is fielded, nothing is rolled, nothing is harvested: the board
    is never built. That is the point of it rather than a shortcut -- a fast
    fake fight would still spend powers and surges through `harvest`, and
    the party would arrive at the next conversation quietly weaker, which
    is the exact failure this component is warned about.

    **It is loud.** The note goes in `Step.notes`, which the CLI prints, and
    `play.py` says so in its banner. A silent god mode is the quietly-weaker
    party inverted, and a transcript that does not admit its victories were
    free is worse than no transcript.
    """
    step.outcome = "won"
    step.rounds = 0
    called = sum(f.count for f in scene.foes)
    step.say(f"God mode: {called} foe(s) not fielded. The party wins.",
             "note")
    step.notes.append(
        f"{scene.id}: GOD MODE -- the fight was skipped, not played. "
        "No damage, no powers spent, no surges. Nothing here is evidence "
        "about combat."
    )


def _fight(
    campaign: Campaign, module: Module, scene: Scene, step: Step,
    *, record: bool = True,
) -> None:
    """Field a combat scene, dress it, play it out, and harvest the wear.

    `record` writes a transcript per fight into git-ignored `logs/`, the way
    `api/session.py` already does for a fight played over HTTP. It was not
    here at first and the omission cost real time: a campaign wiped its party
    and there was nothing to read back but the summary line, so the only way
    to see what happened was to play it again -- which, while the seeding was
    broken, did not give the same fight twice.
    """
    draw = _stream(campaign, scene, "cast")
    rested = rested_since_the_last_fight(campaign, module)
    pitch = tension.pitch(campaign.record, rested=rested)
    dressed = resolve(
        scene, party_level=module.party_level, draw=draw,
        party_size=len(campaign.party.sheets),
        stated_size=module.party_size,
        pitch=pitch,
    )
    if pitch != 1.0 and not scene.xp:
        for line in (tension.says(campaign.record, fight=True),
                     tension.why(campaign.record, rested=rested)):
            if line:
                step.say(line, "note")
    elif pitch != 1.0 and scene.xp:
        step.say(
            "The party's record would have moved this fight's size, but "
            "the module states its XP outright, so it is left alone.",
            "note",
        )
    step.notes += dressed.notes
    # **The dead stay dead on a revisit.** `Campaign.cleared` holds what this
    # scene's fight killed last time, per ref, and those creatures come off
    # the roster before anything is spawned. Without it a scene the module
    # routes back to fielded its whole cast again and the party walked into a
    # room it had cleared. #970.
    #
    # Subtracted in step across `refs` *and* `flavours`, which run parallel
    # and are zipped together twice below -- dropping a ref without its
    # flavour would reflavour the survivors as whatever died.
    standing = campaign.cleared.get(scene.id) or {}
    if standing:
        keep_refs, keep_flavours, gone = survivors(
            dressed.refs, dressed.flavours, standing)
        if gone:
            dressed.refs = keep_refs
            dressed.flavours = keep_flavours
            step.say(
                f"Already cleared: {len(gone)} creature(s) killed here "
                "before and not fielded again.",
                "note",
            )
    if not dressed.refs:
        step.outcome = "skipped"
        step.say(
            "Nothing left to field here -- the party cleared this scene."
            if standing
            else "Nothing written could be fielded for this scene.",
            "note",
        )
        return


    board_seed = seed_for(campaign, scene, "fight")
    # **Where the party is standing, which nobody could choose before.**
    # Empty `formation` resolves to the single column the placement has
    # always used, so a campaign that says nothing is unchanged. #994.
    standing = formation_mod.squares(
        len(campaign.party.sheets), PARTY_AT,
        formation_mod.Formation(
            bands=tuple(campaign.formation), spread=campaign.spread),
    )
    fielded = field_encounter(
        board_seed,
        module.party_level,
        enemies=dressed.refs,
        party=campaign.party,
        squares=standing,
    )
    world = fielded.world
    # Off the board, not from the list handed in -- the same correction
    # `surprised` needed, for the same reason.
    step.stood = [
        spot.square
        for eid in sorted(e for e, s in world.each(Side) if s.team is Team.PC)
        if (spot := world.get(eid, Position)) is not None
    ]

    # **What sort of place the fight is in, which nothing ever said.**
    # `World.terrain` was initialised empty and never written to, so all
    # 70 `c.terrain()` gates in content were false in every fight -- the
    # engine's signature failure, silently false, at the largest scale
    # measured (#539).
    #
    # This is option (1) from that issue: **the caller says.** A module
    # states the ground under every encounter, drawn from the same closed
    # `TERRAIN_WORDS` the gate validates against, so nothing here invents
    # a number or rolls a table -- it applies what the adventure printed.
    # The parked half is `content.terrain.dress`, which arranges blocking
    # squares and rough going and is a separate, balance-affecting call.
    # These are just the words.
    said = ground(world, scene)
    if said:
        step.notes.append(
            f"{scene.id}: fought in {said} -- riders that only apply in "
            "that sort of place are live"
        )

    for eid, flavour in zip(_enemy_eids(world), dressed.flavours, strict=False):
        apply_flavour(world, eid, flavour)

    written = None
    if record:
        from combat_engine.transcript import Transcript

        # Attached before `start()`, for the reason `api/session.py` gives:
        # initiative and the traits armed at the top of round one belong in
        # the file, and a transcript that begins on round two is a transcript
        # of the wrong fight.
        written = Transcript.open(
            f"{campaign.module}-{len(campaign.visited):02d}-{scene.id}",
            {
                "campaign": campaign.module,
                "scene": scene.id,
                # **The board's seed, not the campaign's.** `transcript.py`
                # builds a "re-run" line out of this field, and the campaign
                # seed would make that line name a fight nobody played. The
                # honest re-run for a campaign fight is
                # `play.py --play <module> --seed <campaign_seed>`, because
                # the party walks in already worn -- which no single-fight
                # command can reproduce.
                "seed": board_seed,
                "campaign_seed": campaign.seed,
                "level": module.party_level,
                "pcs": [sheet.cls for sheet in campaign.party.sheets],
                "enemies": list(dressed.refs),
                "flavours": [str(f) for f in dressed.flavours],
            },
        )
        written.attach(world)
        step.transcript = str(written.path)

    encounter = Encounter(world)
    policy = DoctrinePolicy()
    install(world, encounter, {}, default=policy)
    # Attached before `start()`, which is the same reason the transcript is:
    # the watcher counts the opposition at the first round boundary and a
    # trait armed at the top of round one can already have killed somebody.
    # **The module's own word for each creature, which is what a
    # `defeat_foe` objective is written against.** `Reflavour.name` is exactly
    # that -- "what the module calls it" -- and it runs parallel to `refs`,
    # which is the same pairing the flavour loop above relies on. Without this
    # an author would have to know the draw answered `m258`, and could not.
    #
    # Handed over **before** the fight, because the watcher consults it at
    # every round boundary to decide whether it is done.
    named = {
        ref: flavour.name
        for ref, flavour in zip(dressed.refs, dressed.flavours, strict=False)
        if flavour.name
    }
    watch = watcher(world, scene.objective, len(campaign.party.sheets),
                    named=named)
    # **How many milestones the party brings in.** A fact about the day, so
    # a board that knows only its own fight cannot derive it -- which is why
    # `c.milestone()` answered 0 in every story fight until now while arcade
    # mode had it. Set before `encounter.start()` arms anything, the same
    # placement and the same reason as `api/day.py`: a trait that reads it
    # at arming has to get the right number. #968.
    world.milestones = campaign.milestones
    if world.milestones:
        # **Said out loud, which is what makes it checkable.** The number is
        # otherwise invisible: it is read by traits at arming, inside a world
        # that does not outlive the fight, so nothing above could tell a
        # board that got it from one that did not. This component's own rule
        # is that an unobservable effect gets an event rather than a harness
        # that diffs state. It is also a thing a player should be told -- an
        # action point and any milestone trait are live this fight.
        step.say(
            f"The party brings in {world.milestones} milestone(s), so a "
            "milestone trait is live this fight.",
            "note",
        )
    # **Who did not see the party coming.** The engine has had the surprise
    # round since `Encounter.start(surprised=)` -- `Condition.SURPRISED`
    # grants combat advantage and stops the creature acting -- and nothing
    # in `story/` or `api/` had ever passed it, so every campaign fight
    # began with both sides equally ready and a module could not say
    # otherwise. The adventure's own read-aloud describes a creature dozing
    # by a fire. #945.
    #
    # **A free round is a real swing in a fight the budget sized for a fair
    # start**, so it is printed rather than applied quietly: this is a
    # balance lever as much as a narrative one.
    caught = (
        [eid for eid in _enemy_eids(world)]
        if scene.readiness in CAUGHT else []
    )
    encounter.start(surprised=caught)
    # **Counted off the board after `start`, not from the list before it.**
    # Recording `len(caught)` was recording what this function *meant* to
    # do: a plant that computed the list and then called `start()` with no
    # argument left the count at 3 and every assertion green. So this asks
    # the creatures, which is the only version that can tell an intention
    # from an effect. #945.
    step.surprised = sum(
        1 for eid in caught
        if (held := world.get(eid, Conditions)) is not None
        and held.has(Condition.SURPRISED)
    )
    if step.surprised:
        step.say(
            f"The opposition is {scene.readiness}: {step.surprised} "
            "creature(s) are surprised and lose the first round.",
            "note",
        )
    while not encounter.finished and world.round <= MAX_ROUNDS:
        if watch is not None and watch.resolved:
            # **The third exit from the loop.** A fight has always ended when
            # a side was wiped or the round cap ran out; an objective with a
            # duration, or one that is satisfied with the opposition still
            # standing, has to end the moment it is decided. Checked at the
            # top rather than in the `while` condition so that a watcher
            # resolving mid-round still finishes the round it is in -- the
            # watcher only ever updates on `RoundEnd`, so this is the first
            # moment after it.
            break
        actor = world.turn
        if actor is None:
            break
        take_turn(world, encounter, actor, policy)
        encounter.advance()

    if written is not None:
        written.flush()
    harvest(world, campaign.party)
    # **Record what this fight killed, so a revisit does not raise it.**
    # Read off the board rather than from the bus log: the question is which
    # creatures are down *now*, which is a state, and `query.alive` is the
    # engine's own answer to it -- `hp > dying_at`, with the character floor
    # the same reader uses everywhere else.
    #
    # Counted per ref and accumulated, because a scene fielding four of the
    # same creature that lost three must field one next time. #970.
    fallen: dict[str, int] = {}
    for eid in _enemy_eids(world):
        who = world.get(eid, Ident)
        if who is not None and not alive(world, eid):
            fallen[who.ref] = fallen.get(who.ref, 0) + 1
    record_fallen(campaign.cleared, scene.id, fallen)
    # **The round the fight stopped in, and for an objective that is not the
    # same number.** `world.round` has already rolled over by the time the
    # loop head sees `watch.resolved`, so a `survive` objective for two rounds
    # reported `rounds=3` beside a verdict line reading "2 of 2" -- two
    # numbers for one fight, which is how a reader loses faith in both. The
    # watcher's own count is the authority when there is one.
    step.rounds = watch.rounds if watch is not None and watch.resolved \
        else world.round
    step.enemies = list(dressed.refs)
    objective_line = ""
    if watch is None:
        # **Bit for bit what this did before objectives existed**, which is
        # the whole of the compatibility story: a module that states no
        # objective never builds a watcher and never reaches the branch
        # below. `drivers.py no_objective` is the control for it.
        won = encounter.winner is Team.PC if encounter.winner is not None else False
        step.outcome = "won" if won else "lost"
    else:
        verdict = watch.verdict(
            winner=encounter.winner, fielded=tuple(dressed.refs))
        step.objective = scene.objective.kind if scene.objective else ""
        step.clean = verdict.clean
        step.outcome = "won" if verdict.met else "lost"
        asked = (scene.objective.says if scene.objective else "") or step.objective
        # Held, not said, so it can be printed **after** the cast and the
        # result. Said here it came out above "Against:" -- the verdict on a
        # fight before the fight, which reads backwards.
        objective_line = f"Objective -- {asked}: {verdict.why}."

    shown = []
    for eid, flavour in zip(_enemy_eids(world), dressed.flavours, strict=False):
        ident = world.get(eid, Ident)
        shown.append(flavour.name or (ident.ref if ident else "?"))
    step.say(f"Against: {', '.join(shown)}", "note")
    # **How it went, in one phrase from a closed set.** The fight reported
    # `Won in 4 rounds` and sent the blow-by-blow to a transcript nobody
    # reads during play, so a whole encounter of narration material went
    # nowhere. Derived off two printed states -- bloodied, and down -- and
    # read from the sheets, which `harvest` has already written. #943.
    # The `0 <` keeps somebody face-down out of the bloodied count, which
    # **no plant can redden** and is kept anyway: `aftermath` ranks down
    # above bloodied, so a character counted as both cannot change the
    # phrase today. It is the count being a correct count, and the thing
    # that would silently go wrong if that ranking were ever reordered.
    bloodied = sum(
        1 for sheet in campaign.party.sheets
        if sheet.hp is not None and sheet.max_hp
        and 0 < sheet.hp <= sheet.max_hp // 2)
    floored = sum(
        1 for sheet in campaign.party.sheets
        if sheet.hp is not None and sheet.hp <= 0)
    step.aftermath = beat_mod.aftermath(
        step.outcome == "won", bloodied, floored)
    step.say(
        f"{step.outcome.title()} in {step.rounds} rounds -- "
        f"{step.aftermath}.",
        "note",
    )
    # **Handed to the next conversation's DM**, which is the only reader it
    # has: a derived phrase nothing reads is the same as no phrase, which
    # is what #934 found `Known.near` doing for the whole of its life.
    # Spent on use, like `campaign.denied`, so it colours the scene after
    # the fight and not every scene after that.
    campaign.aftermath = step.aftermath
    if objective_line:
        step.say(objective_line, "note")


def _carried(campaign: Campaign) -> str:
    """What the party walks into this conversation carrying, and spend it.

    **Spent on read, like `campaign.denied`**, and read at the top of
    every roleplay scene rather than where the beats start -- a scene with
    nothing to play returns early, and holding the phrase past it would
    have the DM opening on a battle two scenes back. A flag nothing clears
    is this component's own recorded failure shape.
    """
    held = campaign.aftermath
    campaign.aftermath = ""
    if not held:
        return ""
    return (
        f"The fight just before this was {held}. Use it for the mood and "
        "for how people carry themselves; it is not something anybody "
        "announces."
    )


def actors_for(campaign: Campaign) -> list[beat_mod.Actor]:
    """The party as the beat loop sees them: who they are and who plays them.

    Position is the join, which is the same thing `harvest` and `_wear` match
    on and for the same reason -- a `Sheet` carries no id, because an id
    belongs to a world and a sheet outlives one.

    **An unconscious character is not an actor.** `hp` at or below zero is
    somebody face-down on the floor, and the loop happily had them
    declaring intents, speaking, and rolling skill checks -- a rogue at
    0 hp with no surges left talked his way through two scenes. Nothing
    went red for it; it reads as correct, which is this component's
    failure mode exactly (#808).

    `hp is None` means full and untouched -- the sheets carry no number
    until a fight harvests one -- so the test has to be explicit about
    that or the whole party is silent before the first battle.
    """
    out = []
    for slot, sheet in enumerate(campaign.party.sheets):
        if sheet.hp is not None and sheet.hp <= 0:
            continue
        who = campaign.persona(slot)
        out.append(beat_mod.Actor(
            slot=slot, name=who.name or sheet.cls.title(), cls=sheet.cls,
            control=campaign.controls(slot), voice=who.voice, wants=who.wants,
        ))
    return out


def down(campaign: Campaign) -> list[str]:
    """Who is out of it, by name. Printed so the silence is explained.

    A character who simply stops speaking reads as a bug. Saying they are
    down reads as the game.
    """
    return [campaign.persona(slot).name or sheet.cls.title()
            for slot, sheet in enumerate(campaign.party.sheets)
            if sheet.hp is not None and sheet.hp <= 0]


#: The adventure's own graph, read once per process. Built by
#: `scripts/ingest.py` and absent until somebody runs it, which is the
#: normal case -- a module with no graph plays exactly as it did.
_CANON: dict[str, object] = {}


def _canon(module: Module) -> object | None:
    """What the pages say, or `None` if this module has not been ingested."""
    if module.id not in _CANON:
        from combat_engine.db import ROOT
        from combat_engine.story import graph as graph_mod
        where = ROOT / "modules" / module.id / "graph.json"
        _CANON[module.id] = graph_mod.load(where) if where.exists() else None
    return _CANON[module.id]


def _told(campaign: Campaign) -> object:
    """What this table has established, loaded from beside its save.

    A separate file from the canon and a separate layer in play: an
    invention belongs to one campaign and must not leak into another's
    world, nor into the adventure as shipped.
    """
    from combat_engine.story import graph as graph_mod
    from combat_engine.story.save import SAVES
    return graph_mod.load(SAVES / f"{campaign.module}.told.json")


def _roleplay(campaign: Campaign, module: Module, scene: Scene, step: Step,
              director: beat_mod.Director | None,
              ask_human: beat_mod.AskHuman) -> None:
    """Play a roleplay scene out, if the module gave it anything to play.

    **A scene with nothing written to do stays what it was**: its brief,
    printed, and on. That was every scene in every module converted so far,
    so the old behaviour is the default rather than a fallback -- and a
    module only pays for beats where its author wrote something.

    **There are three such things, and this guard knew two.** `lore` is also
    something to play, and a scene carrying only lore returned here before
    `_recall` was ever reached, so its facts never rolled and the player was
    never told them -- silently, because a scene that prints its `sets` and
    moves on is exactly what a scene with nothing to do looks like.
    Isolated by adding one NPC to an otherwise identical scene: 0 recall
    lines against 3. It did not bite only because the one converted module
    puts all 8 of its lore rows on a scene that has NPCs. #918.
    """
    # **Read before the early return, so it is spent either way.** The
    # phrase is about the fight immediately before this scene; held past a
    # scene with nothing to play it would have the DM opening on a battle
    # two scenes back. A scene nobody narrates drops it, which is right --
    # nobody was asked.
    carried = _carried(campaign)
    if not (scene.affordances or scene.npcs or scene.lore):
        return
    # Said once, at the top of the scene, so a character who never speaks
    # reads as down rather than as broken.
    if (out := down(campaign)):
        step.say(f"  ({', '.join(out)} cannot speak.)", "note")
    seed = seed_for(campaign, scene, "beats")
    table = table_mod.lay(campaign.party, seed=seed)
    def tell(made: beat_mod.Beat) -> None:
        # **The player's own recall, before anything else in the beat and
        # in their own second person.** It is what their character already
        # knew walking in, so it comes first, and it is not handed to the
        # DM -- a fact routed through the model comes back in somebody
        # else's mouth, paraphrased, which is the whole reason the
        # companion half is separate.
        # **Ordered by how many of the party knew it, and headed with a
        # count.** `Lore.after` stopped the tavern ladder firing before the
        # player had spoken; it did not stop it arriving all at once, and
        # measured over 25 seeds the unlocking beat delivers **7.7 of the
        # 8 rows** -- all eight in 17 of 25. Eight unheaded lines is a wall
        # a reader cannot rank. #912.
        #
        # **Nothing is capped.** Each row is rolled against its own DC, so
        # the number arriving is the dice and the party's skills rather
        # than a number to pick, and `scripts/CLAUDE.md` is explicit that a
        # silent cap reads as having covered everything.
        #
        # **Ordered by the page's DC, not by how many of us rolled well.**
        # Both were tried. The party's knower-count is tempting -- over 25
        # seeds 28 facts were known by one character of five and 14 by all
        # five, so it separates -- but it is **this run's dice**, so the
        # same scene reads in a different order every campaign and a
        # fixture cannot pin it. The DC is the **author's** statement of
        # how obscure a thing is, it is stable, and on this adventure it is
        # literally a printed ladder: 8, 12, 12, 12, 12, 15, 15, 19. Walking
        # it upwards is the escalating detail the page intends, and it ends
        # on the one somebody had to be good to dig up.
        #
        # **Sorted on the DC alone, and the tier order is the page's.**
        # Knower-count was the obvious tiebreak and is the same mistake one
        # level down: four of these rows are DC 12, so a dice-dependent
        # tiebreak reorders the tier every campaign -- measured, two seeds
        # sharing seven facts printed them in different orders. `sorted` is
        # stable and `_recall` walks `scene.lore` in order, so a one-key
        # sort leaves each tier in the order the adventure prints it.
        #
        # Knower-count still says what the DC cannot, in the "only" below.
        delivered = [knew for knew in made.recalled if knew.knew]
        if len(delivered) > 1:
            step.say(f"  Between you, {len(delivered)} things are already "
                     f"known -- common talk first:", "recall")
        for knew in sorted(delivered, key=lambda r: r.dc):
            # **Only one knower is said out loud**, because that is the
            # fact a reader should weigh: it took the one character who is
            # good at this, and on a reread it is why they are in the party.
            alone = len(knew.knew) == 1
            if knew.mine and alone:
                step.say(f"    Only you know: {knew.fact}", "recall")
            elif knew.mine:
                step.say(f"    You know: {knew.fact}", "recall")
            # **A companion's recall is printed too, attributed.** It
            # still goes to the DM, which says it in their voice -- but
            # the DM was the only path and it drops roughly a quarter
            # of what it is handed (#809). A fact the dice earned
            # reaching nobody is the one loss a player is never owed,
            # and a restatement is the cheap failure to prefer.
            elif alone:
                step.say(f"    Only {knew.knew[0][1]} knows: {knew.fact}", "recall")
            else:
                step.say(f"    {knew.knew[0][1]} knows: {knew.fact}", "recall")
        # **A companion's intent is not printed.** It goes to the DM, which
        # writes it into the paragraph below -- so what a reader sees is one
        # piece of prose in which those things happened, not four captioned
        # declarations and then a reply to them. The person's own line is
        # printed because they typed it and it is theirs.
        for intent in made.intents:
            if not intent.played:
                step.say(f"  {intent}", "mine")
        if made.reaction:
            step.say(f"  {made.reaction}", "dm")
        # The dice after the prose, not before it: a roll is the result of
        # the moment and reads as one. Before, it pre-announced the outcome
        # of a paragraph nobody had read yet.
        #
        # **And the fact beside the roll, because the DM is not a reliable
        # courier.** Playing it found the single successful roll of a scene
        # earning "nobody here has been in the keep long, and that looks
        # less like coincidence than selection" -- which reached the DM and
        # not the player, who saw a passed Insight check and a paragraph of
        # pleasantries. #809 measured that at 6 facts in 20 across the
        # board; in play it eats the ones the dice paid for, which are the
        # only ones a player is owed.
        #
        # So an earned fact is printed, exactly as the player's own lore
        # recall already is, and for the same reason: a fact routed through
        # a model arrives paraphrased, in somebody else's mouth, or not at
        # all. The DM's paragraph is colour on top. That makes delivery
        # true by construction rather than by prompt, and the worst case
        # becomes a harmless restatement instead of a lost payoff.
        for ruling in made.rulings:
            if ruling.affordance != "none":
                step.say(str(ruling), "roll")
                if ruling.fact and not ruling.exit:
                    step.say(f"    {ruling.fact}", "dm")
        # After the reaction, because it is the scene closing rather than
        # anybody answering. The DM is not given it -- #807.
        if made.exit_line:
            step.say(f"  {made.exit_line}", "exit")

    # Said as each beat lands rather than after the scene, so a person
    # playing sees beat 1 before being asked about beat 2. With no echo set
    # this is the same list in the same order, which is what the drivers
    # and `check.py` assert on.
    playing = beat_mod.play_scene(
        scene, table, actors_for(campaign),
        director or beat_mod.Director(scripted=True),
        ask_human=ask_human, party_level=module.party_level,
        after=tell, asked=set(campaign.recalled),
        canon=_canon(module), told=_told(campaign),
        carried=carried,
    )
    # Back onto the campaign, so a `once` row stays rolled across a revisit
    # and across a save. `Playing` does not survive the scene.
    campaign.recalled = sorted(playing.asked)
    _keep(campaign, scene, playing)
    table.strike()
    step.played = playing
    if playing.leads_to:
        step.next_id = playing.leads_to


def ground(world: World, scene: Scene) -> str:
    """Tell the world what sort of place this is. Returns what it was told.

    **A named function because the note alone could not prove the write.**
    Inline, the only observable was a `Step` note, and a note built from
    `scene.terrain` reads identically to one built from `world.terrain` --
    so the break that stopped writing to the world and kept the note left
    every assertion green. Pulled out, the driver can read `world.terrain`
    and ask `Cast.terrain` directly, which is the thing content depends on.

    Option (1) of #539: the caller says, and a module is the caller. The
    words come from the same closed `TERRAIN_WORDS` the gate validates
    against, refused at load if they do not, so nothing here invents one.
    """
    # No early return for a scene that names no ground. **It was there and
    # breaking it changed nothing**, which is a dead line rather than an
    # untested one: the union with an empty set is a no-op and joining an
    # empty set gives `""`, so the caller writes no note either way.
    world.terrain |= set(scene.terrain)
    return ", ".join(sorted(world.terrain))


def _keep(campaign: Campaign, scene: Scene,
          playing: beat_mod.Playing) -> None:
    """Write down what the table established, so it binds from now on.

    **Camille's ruling is that invention is wanted and contradiction is
    not**, and nothing here could hold the DM to its own word because
    nothing was written down: a man given a knighthood in one paragraph
    had no history at all by the next scene.

    What is kept is the DM's reply, against each thing the player asked
    about that had **nothing on record**. A subject that already had facts
    is not re-recorded -- the DM was told not to contradict those and
    storing its paraphrase beside them would blur the two.

    The reply is stored whole rather than summarised. A summary is a
    second model call and a second chance to drift; the paragraph is what
    was actually said at the table, which is the thing a later beat has to
    agree with.
    """
    from combat_engine.story import graph as graph_mod
    from combat_engine.story.save import SAVES

    told = playing.told
    if told is None:
        return
    added = 0
    for beat in playing.beats:
        if not beat.reaction:
            continue
        for st in beat.standing:
            if st.facts or st.knows == "not at all":
                continue
            told.remember(st.about, beat.reaction.strip(),
                          where=scene.id)
            added += 1
    if added:
        graph_mod.save(told, SAVES / f"{campaign.module}.told.json")
        step_note = (f"{scene.id}: {added} thing(s) the DM made up are now "
                     "on record and cannot be contradicted")
        campaign.log.append(step_note)


def _challenge(campaign: Campaign, module: Module, scene: Scene, step: Step,
               choose: Chooser | None) -> None:
    """Run a skill challenge on a board with nobody to fight on it."""
    seed = _stream(campaign, scene, "challenge").randrange(1 << 30)
    table = table_mod.lay(campaign.party, seed=seed)
    run = play_challenge(
        scene, table, party_level=module.party_level, choose=choose,
        record=campaign.record)
    table.strike()
    if tension.footing(campaign.record):
        step.say(tension.says(campaign.record), "note")
    meant_already: set[str] = set()
    for made in run.attempts:
        step.say(f"  {made}", "roll")
        # **What the roll meant, when the module said.** The challenge
        # printed five mechanical lines and a tally and nothing else: the
        # fires were never described going out or spreading. #932.
        #
        # Only for a roll that counted -- a refused skill did not happen,
        # so neither its success nor its failure text is true.
        #
        # **And each sentence once.** The text is a *fact* -- what is now
        # true because the roll went that way -- and a fact does not
        # become true again on the second success with the same skill. The
        # probe printed one brazier toppling into the sand three times,
        # which reads as three braziers.
        if made.rolled:
            meant = scene.means(made.skill, won=made.success)
            if meant and meant not in meant_already:
                meant_already.add(meant)
                step.say(f"    {meant}", "scene")
    step.say(run.tally, "note")
    step.outcome = "won" if run.won else "lost"


def survivors(
    refs: list[str], flavours: list, cleared: dict[str, int],
) -> tuple[list[str], list, list[str]]:
    """Take the already-dead off a roster. Returns `(refs, flavours, gone)`.

    **A named function rather than six lines inside `_fight`, and the
    reason is that the six lines were untestable.** `cast_list` never
    returns the same ref twice for a generated roster -- measured across
    five seeds -- so through `_fight` the count-per-ref behaviour is
    indistinguishable from a set of cleared scenes, and a plant that
    replaced the decrement with nothing stayed green. The distinction is
    the whole point of the field: a scene fielding three of one creature
    that lost two must field **one**, which "this scene is cleared" cannot
    say. #970.

    `refs` and `flavours` run parallel and are zipped together twice
    downstream, so both are filtered in step -- dropping a ref without its
    flavour would dress a survivor as whatever died.
    """
    budget = dict(cleared)
    keep_refs: list[str] = []
    keep_flavours: list = []
    gone: list[str] = []
    for ref, flavour in zip(refs, flavours, strict=False):
        if budget.get(ref, 0) > 0:
            budget[ref] -= 1
            gone.append(ref)
        else:
            keep_refs.append(ref)
            keep_flavours.append(flavour)
    return keep_refs, keep_flavours, gone


def record_fallen(
    cleared: dict[str, dict[str, int]], scene_id: str, fallen: dict[str, int],
) -> None:
    """Add a fight's dead to what this scene has already lost.

    **Accumulated, not replaced**, so a scene cleared over two visits stays
    clear. Named for the same reason `survivors` is: through `_fight` no ref
    dies twice, so a plant that overwrote the tally could not be caught.
    """
    if not fallen:
        return
    book = cleared.setdefault(scene_id, {})
    for ref, count in fallen.items():
        book[ref] = book.get(ref, 0) + count


def quests(campaign: Campaign, module: Module, scene: Scene,
           made: Step) -> None:
    """Offer, complete and fail the module's quests. #940.

    The DMG lists quests first among what an adventure is made of and the
    converted adventure prints two; nothing carried either, so both
    awarded nothing and nothing recorded whether the party had done them.

    Three things happen here, in this order:

    * a quest whose `offered_by` is this scene becomes **open**, which may
      be any kind of scene -- the module grants one mid-combat, so keying
      this on a roleplay scene would miss it;
    * an **open** quest whose `done_when` matches this scene, or an
      affordance the party won in it, becomes done;
    * every quest that one `fails` becomes failed, which is why a quest
      has a state rather than a flag.

    **Said out loud**, because the point of carrying a quest is that the
    player can see it: *"don't be shy about letting the players know what
    their quests are [...] that avoids searching for the fun."*

    The XP is **not** awarded: `Sheet` has no XP field and nothing in the
    story engine advances a character. That is #967, and the figure is
    carried so the award has something to read.
    """
    if not module.quests:
        return
    won = {r.affordance for r in (made.played.beats[-1].rulings
                                  if made.played and made.played.beats
                                  else []) if r.won}
    if made.played is not None:
        won |= set(made.played.found)

    for quest in module.quests:
        state = campaign.quests.get(quest.id, "")
        if not state and quest.offered_by == scene.id:
            campaign.quests[quest.id] = state = "open"
            made.say(
                quest.says or f"New {quest.kind} quest: {quest.id}.",
                "note",
            )
        elif not state and not quest.offered_by:
            # A quest the party starts with is open from the first scene
            # it could be finished in, which keeps a module that states no
            # `offered_by` working without a separate "start" hook.
            campaign.quests[quest.id] = state = "open"

        if state != "open":
            continue
        if quest.done_when != scene.id and quest.done_when not in won:
            continue
        campaign.quests[quest.id] = "done"
        # **The module's own figure wins, and divides by its kind.** An
        # adventure prints a quest's XP, so a stated number is better
        # evidence than the printed rate -- but *how* it divides is the
        # rule's to decide, not the module's: a major quest pays each
        # character the stated figure whatever the party's size, and a
        # minor one is split. #967.
        paid = xp_mod.for_quest(quest.kind, scene.level or module.party_level)
        if quest.xp:
            paid = xp_mod.Award(
                "quest",
                each=quest.xp if quest.kind == "major" else 0,
                total=quest.xp,
                why=f"the module's own figure for {quest.id}",
            )
        got = xp_mod.pay(campaign.party.sheets, paid)
        made.say(
            f"Quest done: {quest.id} ({got.each} XP each -- {paid.why}).",
            "note",
        )
        for other in quest.fails:
            if campaign.quests.get(other) == "open":
                campaign.quests[other] = "failed"
                made.say(
                    f"Quest failed: {other} -- finishing {quest.id} ruled "
                    "it out.",
                    "note",
                )


def reward(campaign: Campaign, module: Module, scene: Scene,
           made: Step) -> None:
    """Pay what the scene was worth, and say when somebody is ready. #967.

    > *Experience points (XP) are the fundamental reward of the game, just
    > as encounters are the building blocks of adventures and campaigns.
    > Every encounter comes with an experience reward to match its
    > difficulty.*

    Three sources pay here -- a combat encounter, a skill challenge, and
    DMG2's drama reward -- and the fourth, a quest, pays in `quests` above
    because that is where a quest is completed.

    **An encounter has to be overcome, and overcoming is not killing.**
    *"Killing, routing, or capturing"* all count, so this reads
    `made.outcome` rather than who was left standing: #964 put the scene's
    objective behind that word, and hanging the award off a wiped board
    would refuse XP to a party that achieved exactly what the module asked
    for.

    **And a risk of failure is what makes something an encounter at all**:

    > *Remember that an encounter, by definition, has a risk of failure. If
    > that risk isn't present, it's not an encounter, and the characters
    > don't earn XP.*

    Which is why god mode pays **nothing**: `_win` fields no creatures and
    rolls nothing, so there is no opposition to be worth anything and no
    risk to have run. That falls out of `made.enemies` being empty rather
    than being special-cased, and it is the right answer rather than a
    convenient one.

    **`Step.clean` is deliberately not read.** #964 recorded it saying the
    thing that would pay for it is this award -- and nothing printed pays
    more for a clean win. An encounter is worth its monsters whether or not
    anybody went down. Inventing a bonus here would be this component's own
    warned-against failure, so the field stays unspent and this paragraph
    is why.
    """
    level = scene.level or module.party_level
    earned: list[xp_mod.Award] = []

    if scene.kind == "combat" and made.outcome == "won" and made.enemies:
        total = xp_mod.for_creatures(made.enemies)
        earned.append(xp_mod.Award(
            "encounter", each=0, total=total,
            why=f"{len(made.enemies)} creatures overcome",
        ))
    elif scene.kind == "skill_challenge" and made.outcome == "won":
        # **A lost challenge pays nothing, which is a reading and not a
        # quotation.** The page prices a challenge as monsters of its level
        # and says an encounter with no risk of failure earns nothing; it
        # does not print what a *failed* challenge is worth. Camille's
        # ruling that a lost challenge must not stop the plot is honoured
        # by `charge` -- the party moves on and pays a cost -- and paying
        # full XP for losing would make the cost the only difference
        # between winning and not.
        earned.append(xp_mod.Award(
            "challenge", each=0,
            total=xp_mod.for_challenge(level, scene.complexity),
            why=f"complexity {scene.complexity} at level {level}",
        ))
    if campaign.drama and made.played is not None:
        drama = xp_mod.drama(made.played, level)
        if drama is not None:
            earned.append(drama)

    for award in earned:
        if award.total <= 0:
            continue
        got = xp_mod.pay(campaign.party.sheets, award)
        made.say(
            f"{award.source.capitalize()}: {got.each} XP each "
            f"({award.why}).",
            "note",
        )

    # **Said once, when it is crossed, and never applied.** A line every
    # scene from here on would be noise, and applying a level is #1013 --
    # re-dealing a pinned hand is `chargen`'s to own.
    for i, sheet in enumerate(campaign.party.sheets):
        if not xp_mod.ready(sheet) or i in campaign.advanced:
            continue
        campaign.advanced.append(i)
        made.say(
            f"{sheet.cls} has {sheet.xp} XP and needs "
            f"{xp_mod.to_advance(sheet.level)} for level {sheet.level + 1} "
            "-- advancement is not implemented (#1013), so the character "
            "keeps playing at this level.",
            "note",
        )


def charge(campaign: Campaign, scene: Scene, made: Step) -> None:
    """Charge what losing this scene cost, with the exit unchanged. #975.

    Camille's ruling -- *"skill challenges should never prevent the plot
    from progressing"* -- was honoured, and that was the whole problem: a
    lost challenge progressed **identically** to a won one. `on_failure`
    is a scene id, so a module could branch or say nothing, and the
    imported one does not branch.

    DMG2's answer is the same scene and a worse party:

    > *On either a success or a failure, the characters will move on to the
    > same obstacle. However, on a failure, they move on at a significant
    > disadvantage.*

    **Charged on a loss of any kind of scene**, not on a challenge, which
    is #975's own comment's recommendation: DMG2's taxonomy names *"fewer
    healing surges or daily powers"* for a costly **combat** win and the
    body proposes the same list for a lost challenge, so keying this on
    `Scene.kind` would build it twice.

    A `rest` cost is the one that is not a number: it denies the *next*
    short rest rather than taking something now, which is why it sets a
    flag on the campaign instead of touching a sheet.
    """
    # No `or not scene.cost`: the loop below is empty for a scene
    # that declares none, so the extra test was dead -- a plant that
    # removed it changed nothing, which is how I found out.
    if made.outcome != "lost":
        return
    for item in scene.cost:
        if item.what == "rest":
            campaign.denied = True
            made.say(
                "Lost: the party presses on without the chance to catch "
                "their breath -- the next short rest is denied.",
                "note",
            )
            continue
        for sheet in campaign.party.sheets:
            if item.what == "surge":
                have = sheet.surges
                if have is None or have <= 0:
                    continue
                sheet.surges = max(0, have - item.each)
            elif item.what == "action point":
                sheet.action_points = max(
                    0, sheet.action_points - item.each)
        made.say(
            f"Lost: {item.each} {item.what}"
            f"{'s' if item.each != 1 else ''} each -- the party moves on "
            "to the same obstacle at a disadvantage.",
            "note",
        )


def stake(scene: Scene, made: Step) -> None:
    """Say what losing will cost, **before** it is played. #975.

    DMG2's framing advice is to *"build tension by showing players the
    negative consequences of failure"*. A cost discovered afterwards is a
    punishment; one stated beforehand is a stake, and that is the whole
    difference between the two.
    """
    for item in scene.cost:
        if item.says:
            made.say(item.says, "note")
        elif item.what == "rest":
            # Not per character, so not "1 rest(s) each" -- a denied rest
            # is one thing the party loses together.
            made.say("Losing this will cost the party their next rest.",
                     "note")
        else:
            made.say(
                f"Losing this will cost {item.each} {item.what}"
                f"{'s' if item.each != 1 else ''} each.",
                "note",
            )


def weather(campaign: Campaign, module: Module, scene: Scene,
            made: Step) -> None:
    """Spend the party's surges on the hours they stood in the cold. #971.

    **A healing surge could only be lost to a fight**, and the printed rules
    have another way to spend one. Six content rows across six files already
    say so in their own docstrings -- a racial trait that is wholly inert, a
    level-4 daily with an empty body, a marked item power, and two monster
    traits that note there is no rule for them to switch off.

    > *Every eight hours within an area of environmental danger, the
    > character must succeed on an Endurance check. Each time a character
    > fails, he loses one healing surge. If a character has no healing
    > surges left when he fails a check, he loses hit points equal to his
    > level.*

    Three things the printed text decides and this follows:

    * **One check per danger**, not one per scene: *"if two or more
      environmental dangers apply at the same time (such as climbing a
      mountain in a snowstorm), characters make Endurance checks against
      each danger."*
    * **A check every eight hours**, so the hours are what the module
      states and the number of checks falls out of them.
    * **+2 while sheltered**, because an extended rest is *"resting and not
      exerting himself"* -- which makes a cold night cheaper than a cold
      day's march, and is the only reason the rest kind is consulted here.

    **Not deprivation.** The rule of three -- three weeks without food,
    three days without water, three minutes without air -- is the other half
    of #971 and is left there, because it needs a surge pool that remembers
    *why* a surge went: one lost to deprivation does not come back until the
    character eats, drinks or breathes, and `Sheet.surges` is a single
    integer that cannot say that.
    """
    if not scene.exposure or scene.hours <= 0:
        return
    spells = scene.hours // EXPOSURE_HOURS
    if spells <= 0:
        made.say(
            f"{scene.hours}h of {', '.join(scene.exposure)}: under "
            f"{EXPOSURE_HOURS}h, so no Endurance check falls due.",
            "note",
        )
        return
    eased = SHELTERED if scene.kind == "rest" else 0

    # **Rolled on the board, applied after it is struck.** `Table.strike`
    # calls `harvest`, which writes the board's `Health.surges` back onto
    # every sheet -- so a surge subtracted while the board was live would be
    # overwritten by the board that never knew about it. Collect, strike,
    # then spend. Finding that out first saved a silent no-op.
    failures: list[tuple[int, str, int]] = []
    board = table_mod.lay(campaign.party, seed=seed_for(campaign, scene, "cold"))
    try:
        for danger in scene.exposure:
            target = DANGERS[danger] - eased
            for _ in range(spells):
                for slot in range(len(campaign.party.sheets)):
                    if not board.check(slot, "endurance", target):
                        failures.append((slot, danger, target))
    finally:
        board.strike()

    # **The total, not the per-danger count.** One check every eight hours
    # *against each danger*, so a party on a mountain in a snowstorm rolls
    # twice as often as one on a still mountain -- and stating the product
    # is what makes that observable. A note saying only `spells` passed a
    # plant that rolled against the first danger and ignored the rest.
    told = (f"{scene.hours}h of {', '.join(scene.exposure)}: "
            f"{spells * len(scene.exposure)} Endurance check(s) each")
    made.say(told + (f", +{eased} while sheltered." if eased else "."), "note")
    for slot, danger, target in failures:
        sheet = campaign.party.sheets[slot]
        left = sheet.surges or 0
        if left > 0:
            sheet.surges = left - 1
            made.say(
                f"{sheet.cls} fails Endurance {target} against {danger} "
                "and spends a healing surge.",
                "note",
            )
        else:
            # Damage equal to level, which is the printed consequence of
            # having nothing left to spend.
            hurt = sheet.level
            sheet.hp = (sheet.max_hp if sheet.hp is None else sheet.hp) - hurt
            made.say(
                f"{sheet.cls} fails Endurance {target} against {danger} "
                f"with no surges left and takes {hurt} damage.",
                "note",
            )


def rested_since_the_last_fight(campaign: Campaign, module: Module) -> bool:
    """Has the party had a rest since their last fight? #947.

    Walks back through `visited` and answers on whichever comes first: a
    rest means yes, a fight means no. Neither means this is their first
    fight and they arrived fresh.

    **Short or extended, both count.** The sidebar's phrase is *"the
    benefit of a short rest"* and an extended rest is strictly more, so
    distinguishing them here would make a night's sleep count for less
    than five minutes.

    Needs no new bookkeeping, which is what the issue noticed: `visited`
    already holds the sequence and the module already knows each kind.
    """
    for scene_id in reversed(campaign.visited):
        scene = module.scenes.get(scene_id)
        if scene is None:
            continue
        if scene.kind == "rest":
            return True
        if scene.kind == "combat":
            return False
    return True


def _already_rested(campaign: Campaign, module: Module) -> bool:
    """Has an extended rest happened with nothing since? #993.

    An extended rest is **once per day** with a printed lockout -- *"After
    you finish an extended rest, you have to wait 12 hours before you can
    begin another one"* -- and nothing bounded it, so a campaign of three
    consecutive rest scenes took all three in silence.

    **Scenes, not hours.** `Campaign.clock` counts scenes played and rests
    taken and is deliberately not a real clock (#965), so the literal
    twelve hours cannot be expressed. This is the coarser rule the issue
    proposed instead: a second extended rest waits until *something has
    happened*. It catches the only shape a module is likely to produce and
    it is what keeps the milestone counter from being reset at will.

    **A short rest does not unlock one**, which is why this walks past a
    `rest` scene rather than stopping at it: a short rest is five minutes
    and the lockout is twelve hours, so a party cannot launder an extended
    rest through one.

    Derived from `visited` rather than counted into a field. There is
    exactly one source of truth that way, and the alternative -- a
    `since_rest` counter -- is another number to keep in step with the
    thing it describes.
    """
    for scene_id in reversed(campaign.visited):
        scene = module.scenes.get(scene_id)
        if scene is None:
            continue
        if scene.kind == "rest":
            if scene.extended:
                return True
            continue
        return False
    return False


def _due(campaign: Campaign, module: Module, made: Step) -> str:
    """The timeline scene that fires now, or `""`. #965.

    Checked at a scene transition, **ahead of the scene's own exit**: an
    event on the clock happens *to* the party, so a scene the module would
    have gone to next waits its turn rather than being skipped. The entry
    is marked fired either way, so a timed event lands once.

    Three things this gets right and a simpler version would not:

    * **`unless` is read before `when`.** An entry the party has already
      prevented is retired without ever being due, so cancelling a thing
      early does not leave it pending for the rest of the campaign.
    * **A cancelled entry is announced too.** *"The ritual never happens --
      you saw to that"* is the payoff for having prevented it, and a
      silent cancellation is indistinguishable from an entry that was
      never written.
    * **The earliest due entry wins**, not the first in the file, so a
      module's timeline can be written in any order.
    """
    clock = campaign.clock
    ready: list[tuple[int, int, object]] = []
    for i, entry in enumerate(module.timeline):
        key = f"{entry.when}{entry.unit}:{entry.scene}"
        if key in campaign.fired:
            continue
        # Prevented: a scene the party played, or a flag they moved.
        stopped = (
            entry.unless
            and (entry.unless in campaign.visited
                 or campaign.flags.get(entry.unless, 0))
        )
        if stopped:
            campaign.fired.append(key)
            made.say(
                f"Prevented: {entry.scene} will not happen -- "
                f"{entry.unless} saw to that.",
                "note",
            )
            continue
        if clock.get(entry.unit, 0) >= entry.when:
            ready.append((entry.when, i, entry))
    if not ready:
        return ""
    ready.sort(key=lambda row: (row[0], row[1]))
    entry = ready[0][2]
    campaign.fired.append(f"{entry.when}{entry.unit}:{entry.scene}")
    if entry.says:
        made.say(entry.says, "note")
    made.say(
        f"On the clock: {entry.scene} happens now ({entry.when} "
        f"{entry.unit}{'' if entry.when == 1 else 's'} in).",
        "note",
    )
    return entry.scene


def step(
    campaign: Campaign, module: Module, *,
    choice: str = "", choose: Chooser | None = None, record: bool = True,
    director: beat_mod.Director | None = None,
    ask_human: beat_mod.AskHuman = beat_mod.silent,
    narrate: Callable[[Line], None] | None = None,
    god: bool = False,
) -> Step:
    """Play the scene the campaign is on and advance it.

    `choice` names which exit to take and is honoured **only if the scene
    lists it** -- the same refusal `dm.py`'s tool makes. A campaign that can
    jump anywhere is not a campaign.
    """
    if campaign.finished:
        raise SystemExit("this campaign is over.")
    scene = module.scene(campaign.scene)
    made = Step(scene=scene, echo=narrate)

    # One line per paragraph. The read-aloud text an adventure prints is
    # several paragraphs and `importer.read_aloud` keeps the breaks, so
    # saying it as a single line puts a bare newline in the middle of an
    # indented block and loses the indent for everything after it.
    for paragraph in scene.seen.split("\n\n"):
        if paragraph.strip():
            made.say(paragraph.strip(), "scene")

    stake(scene, made)

    if scene.kind == "roleplay":
        _roleplay(campaign, module, scene, made, director, ask_human)
    elif scene.kind == "combat":
        if god:
            _win(scene, made)
        else:
            _fight(campaign, module, scene, made, record=record)
    elif scene.kind == "skill_challenge":
        _challenge(campaign, module, scene, made, choose)
    elif scene.kind == "rest":
        # **An extended rest the lockout refuses becomes a short one, and
        # says so.** The printed rule stops another extended rest beginning;
        # it says nothing against the five minutes of a short one, and a
        # party that stopped to rest getting *nothing* would be inventing a
        # harsher rule than the page. Refusing outright is the other
        # defensible reading -- what is not defensible is doing it silently,
        # which is how three rests in a row passed unremarked. #993.
        refused = scene.extended and _already_rested(campaign, module)
        # **A rest a lost scene denied.** The flag is spent here rather
        # than lingering: one rest is forfeited, not every rest after it.
        # A flag nothing clears is a party that never rests again. #975.
        denied = campaign.denied
        campaign.denied = False
        if denied:
            made.say(
                "Refused: the scene the party lost cost them this rest, "
                "so nothing comes back.",
                "note",
            )
        else:
            campaign.party.rest(extended=scene.extended and not refused)
        if denied:
            pass
        elif refused:
            made.say(
                "Refused: an extended rest is once per day and the party "
                "has had one with nothing since, so this is a short rest "
                "-- encounter powers back, surges spent to heal.",
                "note",
            )
        elif scene.extended:
            # **The reset, which is the half that makes the counter mean
            # anything.** The printed rule counts encounters *between*
            # extended rests, and `Party.rest` already drops unspent action
            # points back to one -- so without this the count would run for
            # the whole module and every later fight would claim milestones
            # the party had rested away. #968.
            campaign.encounters = 0
            #: The other unit a timeline entry can be due in. Counted here
            #: rather than derived from `visited`, because deriving it would
            #: need the module to ask which of those scenes were extended.
            campaign.rests += 1
        if not refused and not denied:
            # The refusal note above already says what the party got, so
            # this would otherwise print "Extended rest: everything back"
            # directly underneath a line saying they did not get one.
            made.say(
                "Extended rest: everything back."
                if scene.extended
                else "Short rest: encounter powers back, surges spent to heal.",
                "note",
            )

    # **Count the encounter and pay the milestone, after the scene played.**
    # Weighted by the printed rule rather than flat -- see
    # `Scene.counts_toward`. Counted whatever the outcome: the page says
    # "encounters the characters complete", a fight they lost ends the
    # campaign anyway, and crediting only wins would make a hard-won draw
    # worth less than a walkover. #968.
    before = campaign.milestones
    campaign.encounters += scene.counts_toward(module.party_level)
    if campaign.milestones > before:
        for sheet in campaign.party.sheets:
            sheet.action_points += campaign.milestones - before
        made.say(
            f"Milestone {campaign.milestones}: an action point each, "
            f"{campaign.encounters} encounters since the last extended rest.",
            "note",
        )

    quests(campaign, module, scene, made)
    reward(campaign, module, scene, made)
    charge(campaign, scene, made)

    # **The hours the scene took, before the grant and after the body.**
    # A scene that spends a surge on the weather has to do it whatever kind
    # of scene it is -- a conversation on a mountainside is as cold as a
    # fight on one -- so this sits outside the kind dispatch. #971.
    weather(campaign, module, scene, made)

    # **After the body, so a fight's grant is a reward rather than a loan.**
    # Unconditional on the outcome, which is the smallest honest version:
    # the page hands the poultice over in the conversation itself, and
    # making it depend on winning would be inventing a rule the module does
    # not print. #935.
    for note in loot.hand_over(campaign.party.sheets, scene.grants):
        made.say(note, "note")

    # Where next. A challenge routes on its result when the module says so;
    # everything else takes the named exit or the first one.
    if made.next_id:
        # A roleplay scene left through an affordance's `leads_to`, which the
        # module wrote and the model could not have chosen.
        pass
    elif scene.kind == "skill_challenge" and (scene.on_success or scene.on_failure):
        wanted = scene.on_success if made.outcome == "won" else scene.on_failure
        made.next_id = wanted or module.next_of(scene, choice)
    else:
        made.next_id = module.next_of(scene, choice)

    # **The record the next scene is pitched from.** Appended after the
    # scene is decided and before the next one is chosen, so a campaign
    # reloaded mid-module pitches from the same history. #977.
    if made.outcome in tension.DECIDED:
        campaign.record.append(made.outcome)
    campaign.visited.append(scene.id)
    # **The timeline, after the tick and instead of the scene's own exit.**
    # `visited` is appended first because the scene just played is part of
    # the count an entry is due against.
    #
    # The override **replaces** the exit rather than deferring it, and that
    # is a real limitation worth stating rather than discovering: a timed
    # scene has to carry its own `exits`, and a module that wants to return
    # to the interrupted thread says so by exiting back to it. Remembering
    # the displaced exit would need another piece of campaign state and a
    # rule for what happens when the timed scene has exits of its own,
    # which is more than the first version of this should decide. #965.
    timed = _due(campaign, module, made)
    if timed:
        made.next_id = timed
    campaign.scene = made.next_id
    if record:
        record_scene(campaign, made)
    campaign.note(
        f"{scene.id} ({scene.kind}): {made.outcome}"
        + (f", {made.rounds} rounds" if made.rounds else "")
    )
    return made


def party_line(campaign: Campaign) -> str:
    """One line on how the party is holding up."""
    bits = []
    for sheet in campaign.party.sheets:
        hp = "full" if sheet.hp is None else str(sheet.hp)
        surges = "full" if sheet.surges is None else str(sheet.surges)
        flag = " DOWN" if sheet.down else ""
        # Carried items, as a count rather than a list of refs: the line is
        # read between scenes to spot a number that moved when nothing
        # should have moved it, and four refs in it would bury the hp.
        held = sum(sheet.carried.values())
        bag = f"/{held}i" if held else ""
        bits.append(f"{sheet.cls} {hp}hp/{surges}s{bag}{flag}")
    return "   ".join(bits)
