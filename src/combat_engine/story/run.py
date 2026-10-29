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
from combat_engine.engine.ecs import World
from combat_engine.engine.turns import Encounter
from combat_engine.policy import install, take_turn
from combat_engine.policy.doctrine import DoctrinePolicy

from . import PARTY, Party, field_encounter, harvest
from . import beat as beat_mod
from . import table as table_mod
from .cast_list import resolve
from .challenge import Chooser
from .challenge import play as play_challenge
from .module import Module, Scene
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
        "next": made.next_id,
        "rounds": made.rounds,
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
    dressed = resolve(
        scene, party_level=module.party_level, draw=draw,
        party_size=len(campaign.party.sheets),
        stated_size=module.party_size,
    )
    step.notes += dressed.notes
    if not dressed.refs:
        step.outcome = "skipped"
        step.say("Nothing written could be fielded for this scene.", "note")
        return


    board_seed = seed_for(campaign, scene, "fight")
    fielded = field_encounter(
        board_seed,
        module.party_level,
        enemies=dressed.refs,
        party=campaign.party,
    )
    world = fielded.world

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
    encounter.start()
    while not encounter.finished and world.round <= MAX_ROUNDS:
        actor = world.turn
        if actor is None:
            break
        take_turn(world, encounter, actor, policy)
        encounter.advance()

    if written is not None:
        written.flush()
    harvest(world, campaign.party)
    step.rounds = world.round
    step.enemies = list(dressed.refs)
    won = encounter.winner is Team.PC if encounter.winner is not None else False
    step.outcome = "won" if won else "lost"

    shown = []
    for eid, flavour in zip(_enemy_eids(world), dressed.flavours, strict=False):
        ident = world.get(eid, Ident)
        shown.append(flavour.name or (ident.ref if ident else "?"))
    step.say(f"Against: {', '.join(shown)}", "note")
    step.say(f"{step.outcome.title()} in {step.rounds} rounds.", "note")


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
        scene, table, party_level=module.party_level, choose=choose)
    table.strike()
    for made in run.attempts:
        step.say(f"  {made}", "roll")
    step.say(run.tally, "note")
    step.outcome = "won" if run.won else "lost"


def step(
    campaign: Campaign, module: Module, *,
    choice: str = "", choose: Chooser | None = None, record: bool = True,
    director: beat_mod.Director | None = None,
    ask_human: beat_mod.AskHuman = beat_mod.silent,
    narrate: Callable[[str], None] | None = None,
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
        campaign.party.rest(extended=scene.extended)
        made.say(
            "Extended rest: everything back."
            if scene.extended
            else "Short rest: encounter powers back, surges spent to heal.",
            "note",
        )

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

    campaign.visited.append(scene.id)
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
        bits.append(f"{sheet.cls} {hp}hp/{surges}s{flag}")
    return "   ".join(bits)
