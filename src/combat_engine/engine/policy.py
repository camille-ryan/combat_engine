"""Who decides. Monsters need one of these; characters may use one too.

A policy answers three different questions and it is worth keeping them
apart, because a learned policy will be good at the first long before it is
trusted with the third:

* `act` -- which of the legal actions to take on its turn;
* `decide` -- a choice *inside* a power, like where a shift lands;
* `react` -- whether to spend an opportunity or immediate action.

Nothing here knows any rules. `actions.legal` produces the options and this
only ranks them, which means a policy cannot do something the interface would
not have offered.

**Making policies rather than writing them.** The engine is deterministic and
the event log is complete, so a fight is a labelled example: `features()`
turns a `(state, action)` pair into a flat dict of numbers, `LinearPolicy`
consumes weights over exactly those names, and `Memory` learns what a power
is worth by watching what it did rather than by being told. That is the whole
loop -- play fights, record features and outcomes, fit weights, play again --
and it needs nothing written per power, which is the point.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from .actions import Action, legal, perform
from .components import Health, Side
from .dsl import get
from .events import DamageApplied, Event, OpportunityWindow, PowerUsed
from .query import alive, distance_between, enemies, is_
from .types import ActionType, Condition, Team, Usage

if TYPE_CHECKING:
    from .ecs import World
    from .turns import Encounter


class Policy(Protocol):
    def act(
        self, world: World, encounter: Encounter, actor: int, options: list[Action]
    ) -> Action: ...

    def decide(
        self, world: World, actor: int, kind: str, options: list[Any], prompt: str
    ) -> Any: ...

    def react(
        self, world: World, encounter: Encounter, actor: int, window: Event
    ) -> Action | None: ...


# --------------------------------------------------------------------------
# What a policy sees
# --------------------------------------------------------------------------


def features(
    world: World, encounter: Encounter, actor: int, action: Action
) -> dict[str, float]:
    """A flat, named view of one candidate action.

    Every name here is stable and every value is a number, so the same dict
    feeds a hand-tuned weighting and a fitted one. Add a feature and both get
    it; nothing has to be re-declared per power.
    """
    f: dict[str, float] = defaultdict(float)
    f["is_power"] = float(action.kind == "power")
    f["is_move"] = float(action.kind == "move")
    f["is_stand"] = float(action.kind == "stand")
    f["is_second_wind"] = float(action.kind == "second_wind")
    f["is_end"] = float(action.kind == "end")
    f["targets"] = float(len(action.targets))

    me = world.get(actor, Health)
    if me is not None:
        f["my_hp_fraction"] = me.hp / max(1, me.max_hp)
        f["i_am_bloodied"] = float(me.bloodied)
        f["my_surges"] = float(me.surges)

    p = get(action.ref) if action.ref else None
    if p is not None:
        f["usage_at_will"] = float(p.usage is Usage.AT_WILL)
        f["usage_encounter"] = float(p.usage is Usage.ENCOUNTER)
        f["usage_daily"] = float(p.usage is Usage.DAILY)
        f["costs_standard"] = float(p.action is ActionType.STANDARD)
        f["range"] = float(p.reach.size)
        f["declares_attack"] = float(p.attack is not None)

        chances = [p.hit_chance(world, actor, t) for t in action.targets]
        if chances:
            f["hit_chance"] = sum(chances) / len(chances)
            f["expected_hits"] = sum(chances)

    hurt = 0.0
    nearly = 0.0
    for t in action.targets:
        health = world.get(t, Health)
        if health is None:
            continue
        hurt += 1.0 - health.hp / max(1, health.max_hp)
        nearly += float(health.bloodied)
    f["target_damage_taken"] = hurt
    f["targets_bloodied"] = nearly

    foes = [e for e in enemies(world, actor) if alive(world, e)]
    if foes:
        f["nearest_enemy"] = float(min(distance_between(world, actor, e) for e in foes))
        f["enemies_left"] = float(len(foes))
    if action.kind == "move" and action.dest is not None and foes:
        after = min(
            max(abs(action.dest[0] - x), abs(action.dest[1] - y))
            for e in foes
            for (x, y) in [_square(world, e)]
        )
        f["closes_distance"] = f.get("nearest_enemy", 0.0) - after
    return dict(f)


def _allies_of(world: World, eid: int) -> list[int]:
    """Whose side the *target of a push* is on -- that is, the pusher's foes.

    A push is aimed at an enemy, so the creatures it should be driven away
    from are that enemy's own allies.
    """
    from .query import allies, enemies

    foes = enemies(world, eid)
    return allies(world, foes[0]) if foes else []


def _square(world: World, eid: int) -> tuple[int, int]:
    from .components import Position

    pos = world.get(eid, Position)
    return pos.square if pos else (0, 0)


# --------------------------------------------------------------------------
# Learning what a power is worth
# --------------------------------------------------------------------------


@dataclass
class Memory:
    """What powers have actually done, learned from logs.

    A body is code, so nothing can read how much damage a power deals without
    running it. This watches fights instead: every `DamageApplied` is credited
    to whichever power was in flight, and the running mean is what a scorer
    uses. Costs nothing per power and improves with every fight played.
    """

    damage: dict[str, float] = field(default_factory=dict)
    uses: dict[str, int] = field(default_factory=dict)

    def observe(self, log: list[Event]) -> None:
        current = ""
        pending: dict[str, int] = defaultdict(int)
        for ev in log:
            if isinstance(ev, PowerUsed):
                current = ev.power
                self.uses[current] = self.uses.get(current, 0) + 1
            elif isinstance(ev, DamageApplied) and current:
                pending[current] += ev.amount
        for ref, total in pending.items():
            n = max(1, self.uses.get(ref, 1))
            seen = self.damage.get(ref, 0.0)
            self.damage[ref] = seen + (total / n - seen) / n

    def worth(self, ref: str, default: float = 5.0) -> float:
        return self.damage.get(ref, default)


# --------------------------------------------------------------------------
# The default
# --------------------------------------------------------------------------

#: Hand-set weights over `features`. A fitted policy replaces this dict and
#: nothing else, which is the point of scoring through named features.
WEIGHTS: dict[str, float] = {
    "is_power": 6.0,
    # Ending the turn is mildly bad; moving is mildly bad too, so a move has
    # to earn itself through `closes_distance`. Make ending much worse than
    # moving and the creature shuffles every turn it cannot attack, which is
    # what the first version of these numbers did.
    "is_end": -2.0,
    "is_move": -1.0,
    "is_stand": 3.0,
    "is_second_wind": 0.0,
    "expected_hits": 4.0,
    "hit_chance": 3.0,
    "targets": 1.5,
    "targets_bloodied": 3.0,
    "target_damage_taken": 1.0,
    "usage_daily": -3.0,
    "usage_encounter": -0.5,
    "closes_distance": 2.0,
    "nearest_enemy": -0.1,
}


@dataclass
class LinearPolicy:
    """Scores actions as a weighted sum over `features`.

    The default weights are hand-set and deliberately unsubtle. Fit a better
    dict from recorded fights and pass it in; nothing else changes.
    """

    weights: dict[str, float] = field(default_factory=lambda: dict(WEIGHTS))
    memory: Memory | None = None
    #: Keeps a daily in hand until the fight is going badly.
    desperate_at: float = 0.4

    def score(self, world: World, encounter: Encounter, actor: int, action: Action) -> float:
        f = features(world, encounter, actor, action)
        total = sum(self.weights.get(k, 0.0) * v for k, v in f.items())
        if self.memory is not None and action.ref:
            total += self.memory.worth(action.ref, 5.0) * f.get("expected_hits", 0.0) * 0.4
        if f.get("usage_daily") and f.get("my_hp_fraction", 1.0) < self.desperate_at:
            total += 6.0
        if f.get("is_second_wind") and f.get("my_hp_fraction", 1.0) < 0.3:
            total += 12.0
        return total

    def act(
        self, world: World, encounter: Encounter, actor: int, options: list[Action]
    ) -> Action:
        usable = [a for a in options if a.available] or options
        # Sorting by the string as well keeps two runs of a seed identical
        # when several actions score the same.
        return max(usable, key=lambda a: (self.score(world, encounter, actor, a), str(a)))

    def decide(
        self, world: World, actor: int, kind: str, options: list[Any], prompt: str
    ) -> Any:
        """Choices inside a power.

        Movement choices are aimed: a shift goes toward the nearest enemy if
        the creature is trying to reach one and away if it is hurt. Anything
        else takes the first option, which is sorted, so it is stable rather
        than arbitrary.
        """
        if kind in ("push", "pull", "slide") and options and _is_square(options[0]):
            # Where to shove somebody. Away from its friends, which is the
            # point of a push -- it is worth more than the square of damage
            # it came with. Ties break in sorted order, so a seed replays.
            mates = [
                a
                for a in _allies_of(world, actor)
                if alive(world, a)
            ]
            if not mates:
                return options[0]

            def isolation(sq: Any) -> tuple[int, Any]:
                return (
                    min(
                        max(abs(sq[0] - x), abs(sq[1] - y))
                        for m in mates
                        for (x, y) in [_square(world, m)]
                    ),
                    sq,
                )

            return max(options, key=isolation)

        if kind in ("shift", "move", "teleport") and options and _is_square(options[0]):
            health = world.get(actor, Health)
            retreat = health is not None and health.hp < health.max_hp * 0.35
            foes = [e for e in enemies(world, actor) if alive(world, e)]
            if not foes:
                return options[0]

            def reach(sq: Any) -> int:
                return min(
                    max(abs(sq[0] - x), abs(sq[1] - y))
                    for e in foes
                    for (x, y) in [_square(world, e)]
                )

            return max(options, key=reach) if retreat else min(options, key=reach)
        return options[0]

    def react(
        self, world: World, encounter: Encounter, actor: int, window: Event
    ) -> Action | None:
        """Take an opportunity attack whenever one is on offer.

        Deliberately blunt. Declining is occasionally right and a fitted
        policy can learn when; always taking it is the right default because
        the failure mode of the alternative -- silently never reacting -- is
        invisible in a log.
        """
        if not isinstance(window, OpportunityWindow):
            return None
        if not encounter.can_spend(actor, ActionType.OPPORTUNITY):
            return None
        if is_(world, actor, Condition.DAZED) or is_(world, actor, Condition.STUNNED):
            return None
        options = [
            a
            for a in _opportunity_options(world, encounter, actor, window.provoker)
            if a.available
        ]
        if not options:
            return None
        return max(options, key=lambda a: (self.score(world, encounter, actor, a), str(a)))


def _is_square(value: Any) -> bool:
    return isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, int) for v in value)


def _opportunity_options(
    world: World, encounter: Encounter, actor: int, provoker: int
) -> list[Action]:
    """Opportunity attacks available against one provoker.

    A creature's opportunity attack is its melee basic attack unless it has a
    power that says otherwise, so this is every declared opportunity-action
    power that can reach, plus the basic.
    """
    from .components import Powers
    from .dsl import candidates
    from .dsl import usable as is_usable

    out: list[Action] = []
    known = world.get(actor, Powers)
    if known is None:
        return out

    refs = [r for r in known.all if (p := get(r)) and p.action is ActionType.OPPORTUNITY]
    refs.append(known.opportunity or known.basic)

    for ref in dict.fromkeys(refs):
        p = get(ref)
        if p is None:
            continue
        ok, _ = is_usable(world, actor, p)
        if ok and provoker in candidates(world, actor, p):
            out.append(
                Action(kind="power", cost=ActionType.OPPORTUNITY, ref=ref, targets=(provoker,))
            )
    return out


# --------------------------------------------------------------------------
# Plumbing
# --------------------------------------------------------------------------


def install(
    world: World,
    encounter: Encounter,
    policies: dict[Team, Policy],
    *,
    default: Policy | None = None,
) -> None:
    """Route the engine's questions to whichever policy owns the creature.

    A team with no policy falls back to `default`, so a session can hand the
    characters to a human interface and leave the monsters on a policy
    without either side knowing about the other.
    """
    fallback = default or LinearPolicy()

    def owner(eid: int) -> Policy:
        side = world.get(eid, Side)
        return policies.get(side.team, fallback) if side else fallback

    def decide(actor: int, kind: str, options: list[Any], prompt: str) -> Any:
        return owner(actor).decide(world, actor, kind, options, prompt)

    world.decider = decide

    def on_window(ev: OpportunityWindow) -> None:
        choice = owner(ev.actor).react(world, encounter, ev.actor, ev)
        if choice is not None:
            perform(world, encounter, ev.actor, choice)

    world.bus.on(OpportunityWindow, on_window)


def take_turn(
    world: World, encounter: Encounter, actor: int, policy: Policy, *, cap: int = 12
) -> None:
    """Play one creature's whole turn.

    `cap` stops a policy that keeps choosing a free action from spinning. It
    is a guard against a bug, not a rule, so hitting it is worth noticing.
    """
    from .actions import recharge

    recharge(world, actor)
    for _ in range(cap):
        options = legal(world, encounter, actor)
        choice = policy.act(world, encounter, actor, options)
        if choice.kind == "end":
            return
        if not perform(world, encounter, actor, choice):
            return
        if not alive(world, actor):
            return
