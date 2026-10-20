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

from dataclasses import dataclass, field
from random import Random

from combat_engine.engine import Ident, Side, Team
from combat_engine.engine.turns import Encounter
from combat_engine.policy import install, take_turn
from combat_engine.policy.doctrine import DoctrinePolicy

from . import PARTY, Party, field_encounter, harvest
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
    lines: list[str] = field(default_factory=list)
    #: Things the reader should know that are not the story -- a budget clamp,
    #: a creature deferred, terrain not yet applied.
    notes: list[str] = field(default_factory=list)
    rounds: int = 0
    enemies: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        self.lines.append(line)


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


def _enemy_eids(world: object) -> list[int]:
    """Spawned enemies in spawn order, which is the order the refs went in.

    Entity ids are handed out in sequence, so sorting by id recovers the order
    `field_encounter` spawned the pool in -- which is what lets a flavour be
    matched to the creature it was built for. Matching by ref instead would
    pick the wrong one whenever a scene fields two of the same creature under
    different flavours.
    """
    return sorted(
        eid for eid, side in world.each(Side) if side.team is Team.ENEMY  # type: ignore[attr-defined]
    )


def _fight(campaign: Campaign, module: Module, scene: Scene, step: Step) -> None:
    """Field a combat scene, dress it, play it out, and harvest the wear."""
    draw = _stream(campaign, scene, "cast")
    dressed = resolve(
        scene, party_level=module.party_level, draw=draw,
        party_size=len(campaign.party.sheets),
    )
    step.notes += dressed.notes
    if not dressed.refs:
        step.outcome = "skipped"
        step.say("Nothing written could be fielded for this scene.")
        return

    if scene.terrain:
        step.notes.append(
            f"{scene.id}: the module calls for "
            f"{', '.join(scene.terrain)} and terrain.dress cannot yet be told "
            "what sort of place a fight is in -- see #539"
        )

    fielded = field_encounter(
        campaign.seed + abs(hash(scene.id)) % 100000,
        module.party_level,
        enemies=dressed.refs,
        party=campaign.party,
    )
    world = fielded.world
    for eid, flavour in zip(_enemy_eids(world), dressed.flavours, strict=False):
        apply_flavour(world, eid, flavour)

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

    harvest(world, campaign.party)
    step.rounds = world.round
    step.enemies = list(dressed.refs)
    won = encounter.winner is Team.PC if encounter.winner is not None else False
    step.outcome = "won" if won else "lost"

    shown = []
    for eid, flavour in zip(_enemy_eids(world), dressed.flavours, strict=False):
        ident = world.get(eid, Ident)
        shown.append(flavour.name or (ident.ref if ident else "?"))
    step.say(f"Against: {', '.join(shown)}")
    step.say(f"{step.outcome.title()} in {step.rounds} rounds.")


def _challenge(campaign: Campaign, module: Module, scene: Scene, step: Step,
               choose: Chooser | None) -> None:
    """Run a skill challenge on a board with nobody to fight on it."""
    seed = _stream(campaign, scene, "challenge").randrange(1 << 30)
    table = table_mod.lay(campaign.party, seed=seed)
    run = play_challenge(
        scene, table, party_level=module.party_level, choose=choose)
    table.strike()
    for made in run.attempts:
        step.say(f"  {made}")
    step.say(run.tally)
    step.outcome = "won" if run.won else "lost"


def step(
    campaign: Campaign, module: Module, *,
    choice: str = "", choose: Chooser | None = None,
) -> Step:
    """Play the scene the campaign is on and advance it.

    `choice` names which exit to take and is honoured **only if the scene
    lists it** -- the same refusal `dm.py`'s tool makes. A campaign that can
    jump anywhere is not a campaign.
    """
    if campaign.finished:
        raise SystemExit("this campaign is over.")
    scene = module.scene(campaign.scene)
    made = Step(scene=scene)

    if scene.brief:
        made.say(scene.brief)

    if scene.kind == "combat":
        _fight(campaign, module, scene, made)
    elif scene.kind == "skill_challenge":
        _challenge(campaign, module, scene, made, choose)
    elif scene.kind == "rest":
        campaign.party.rest(extended=scene.extended)
        made.say(
            "Extended rest: everything back."
            if scene.extended
            else "Short rest: encounter powers back, surges spent to heal."
        )

    # Where next. A challenge routes on its result when the module says so;
    # everything else takes the named exit or the first one.
    if scene.kind == "skill_challenge" and (scene.on_success or scene.on_failure):
        wanted = scene.on_success if made.outcome == "won" else scene.on_failure
        made.next_id = wanted or module.next_of(scene, choice)
    else:
        made.next_id = module.next_of(scene, choice)

    campaign.visited.append(scene.id)
    campaign.scene = made.next_id
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
