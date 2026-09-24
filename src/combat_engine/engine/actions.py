"""Everything a creature could legally do right now, as concrete choices.

Two callers need exactly this list and must never disagree about it: the
interface, which draws it, and a policy, which picks from it. So it is
computed once, here, and both read the same answer. A policy that could
choose something the interface would not offer is a policy that cheats.

An `Action` is fully determined -- power, targets, destination square, all of
it. Nothing is left to be resolved later, which is what lets a policy be
scored on the choice it actually made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .components import Health, Powers
from .dsl import aim_points, candidates, get, usable
from .grid import Square
from .query import alive, can_act, is_
from .types import ActionType, Condition, Usage

if TYPE_CHECKING:
    from .ecs import World
    from .turns import Encounter


@dataclass(frozen=True)
class Action:
    kind: str  # power | move | shift | stand | second_wind | sustain | end
    cost: ActionType
    ref: str = ""
    targets: tuple[int, ...] = ()
    dest: Square | None = None
    origin: Square | None = None
    #: What this acts on, when that is not the actor and not a square: a live
    #: effect for `sustain`, and later a conjuration to walk or command.
    #:
    #: Everything here used to be a thing the actor did to a target or a
    #: square, so "spend a minor to sustain e17" had no shape. Kept as a bare
    #: int rather than a union because the `kind` already says which of the
    #: two it is, and an Action is read far more often than it is built.
    subject: int | None = None
    #: Only for a rejected option: why the interface should grey it out.
    blocked: str = ""
    path: tuple[Square, ...] = field(default=(), repr=False)

    @property
    def available(self) -> bool:
        return not self.blocked

    def __str__(self) -> str:
        bits = [self.kind]
        if self.ref:
            bits.append(self.ref)
        if self.targets:
            bits.append("-> " + ",".join(str(t) for t in self.targets))
        if self.subject is not None:
            bits.append(f"on e{self.subject}")
        if self.dest:
            bits.append(f"@{self.dest}")
        if self.blocked:
            bits.append(f"({self.blocked})")
        return " ".join(bits)


def legal(
    world: World, encounter: Encounter, actor: int, *, include_blocked: bool = False
) -> list[Action]:
    """Every action `actor` may take. Deterministic order.

    With `include_blocked`, unusable powers come back carrying the reason, so
    the interface can grey a card and say why rather than hiding it.
    """
    out: list[Action] = []
    if not can_act(world, actor):
        return [Action(kind="end", cost=ActionType.NONE)]

    out.extend(_powers(world, encounter, actor, include_blocked))
    out.extend(_movement(world, encounter, actor))
    out.extend(_recovery(world, encounter, actor))
    out.extend(_sustaining(world, encounter, actor))
    out.append(Action(kind="end", cost=ActionType.NONE))
    return out


def _powers(world: World, encounter: Encounter, actor: int, include_blocked: bool) -> list[Action]:
    known = world.get(actor, Powers)
    if known is None:
        return []
    out: list[Action] = []
    for ref in known.all:
        p = get(ref)
        if p is None:
            continue
        if p.action is ActionType.NONE:
            continue  # a trait; armed at the start of the fight, never chosen
        if p.out_of_combat:
            # Declared on rows that light a torch or mend a cloak. The field
            # existed and only `audit.py` read it, so the four wizard
            # cantrips were offered as combat actions like anything else --
            # and got taken, because a policy picks from what it is given.
            continue
        ok, why = usable(world, actor, p)
        if not encounter.can_spend(actor, p.action):
            ok, why = False, "no action left"
        if not ok:
            if include_blocked:
                out.append(Action(kind="power", cost=p.action, ref=ref, blocked=why))
            continue
        out.extend(_aimings(world, actor, ref))
    return out


def _aimings(world: World, actor: int, ref: str) -> list[Action]:
    """One action per distinct way of aiming this power."""
    p = get(ref)
    if p is None:
        return []
    cost = p.action

    if not p.is_attack:
        return [Action(kind="power", cost=cost, ref=ref)]

    if p.reach.kind == "close_blast":
        # One option per place the blast can be laid down, keyed by the square
        # it is aimed at -- for a blast 3 that is the ring two squares out.
        out = []
        for aim in aim_points(world, actor, p):
            hit = candidates(world, actor, p, aim)
            if hit:
                out.append(
                    Action(kind="power", cost=cost, ref=ref, targets=tuple(hit), origin=aim)
                )
        return out

    if p.reach.kind == "area_burst":
        out = []
        for origin in _burst_origins(world, actor, p):
            hit = candidates(world, actor, p, origin)
            if hit:
                out.append(
                    Action(kind="power", cost=cost, ref=ref, targets=tuple(hit), origin=origin)
                )
        return out

    pool = candidates(world, actor, p)
    if p.target.everyone:
        return [Action(kind="power", cost=cost, ref=ref, targets=tuple(pool))] if pool else []
    if p.target.count == 1:
        return [Action(kind="power", cost=cost, ref=ref, targets=(t,)) for t in pool]
    # "Up to N creatures": offer the whole pool, capped. A policy that wants a
    # subset asks for one; the interface lets the player click them.
    return [Action(kind="power", cost=cost, ref=ref, targets=tuple(pool[: p.target.count]))]


def _burst_origins(world: World, actor: int, p) -> list[Square]:  # noqa: ANN001
    """Candidate origin squares for an area burst, capped to ones that land.

    `aim_points` is the authority on where the power may be centred -- it
    knows the range off the printed line -- and this keeps only the squares
    a creature is standing in. An area burst aimed at empty ground is legal
    and occasionally right, but offering every square within ten would swamp
    the interface and any policy alike.

    Narrowing without asking `aim_points` first is how an "area burst 1
    within 10" came to be offered twenty-one squares away.
    """
    from .query import creatures, squares

    legal_aims = set(aim_points(world, actor, p))
    out: set[Square] = set()
    for other in creatures(world):
        if not alive(world, other):
            continue
        out |= squares(world, other) & legal_aims
    return sorted(out)


def _movement(world: World, encounter: Encounter, actor: int) -> list[Action]:
    from .query import speed

    out: list[Action] = []
    if is_(world, actor, Condition.PRONE):
        return out  # stand up first; see `_recovery`
    if encounter.can_spend(actor, ActionType.MOVE):
        for dest, path in sorted(world.reachable_paths(actor, speed(world, actor)).items()):
            out.append(
                Action(
                    kind="move",
                    cost=ActionType.MOVE,
                    dest=dest,
                    path=tuple(path),
                )
            )
        # A shift is its own action: one square, and it provokes nothing.
        # Offered separately because walking to the same square and shifting
        # to it are different decisions with different consequences.
        from .movement import OVERHEAD, mode_of, reachable

        mode = mode_of(world, actor, None)
        step = reachable(world, actor, 1, mode="walk" if mode in OVERHEAD else None)
        for dest in sorted(step):
            out.append(
                Action(kind="shift", cost=ActionType.MOVE, dest=dest, path=(dest,))
            )
    return out


def _sustaining(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Keeping a sustained effect going, deliberately.

    Mostly you do not need this: an effect whose action is still unspent
    sustains itself at the end of your turn (`Effects._sustain_by_default`).
    It is here for the two cases where the default is not what you want --
    sustaining early, and choosing which of two effects gets the one minor
    you have.
    """
    out: list[Action] = []
    for eff in sorted(world.effects.live.values(), key=lambda e: e.id):
        if eff.source != actor or eff.sustain_cost is None:
            continue
        if eff.sustained >= world.round:
            continue  # already going this round
        if not encounter.can_spend(actor, eff.sustain_cost):
            continue
        out.append(
            Action(kind="sustain", cost=eff.sustain_cost, subject=eff.id, ref=eff.label)
        )
    return out


def _recovery(world: World, encounter: Encounter, actor: int) -> list[Action]:
    out: list[Action] = []
    if (
        is_(world, actor, Condition.PRONE)
        and not is_(world, actor, Condition.PINNED)
        and encounter.can_spend(actor, ActionType.MOVE)
    ):
        out.append(Action(kind="stand", cost=ActionType.MOVE))
    health = world.get(actor, Health)
    known = world.get(actor, Powers)
    if (
        health is not None
        and health.surges > 0
        and known is not None
        and known.times("second-wind") == 0
        and encounter.can_spend(actor, ActionType.STANDARD)
    ):
        out.append(Action(kind="second_wind", cost=ActionType.STANDARD))
    return out


# --------------------------------------------------------------------------
# Doing it
# --------------------------------------------------------------------------


def perform(world: World, encounter: Encounter, actor: int, action: Action) -> bool:
    """Spend the action and carry it out. False if it was not available."""
    from .durations import When
    from .events import Note
    from .movement import walk

    if action.kind == "end":
        return True
    if not encounter.spend(actor, action.cost):
        return False

    if action.kind == "power":
        from .dsl import use

        return use(
            world,
            actor,
            action.ref,
            targets=list(action.targets) or None,
            origin=action.origin,
            spend=True,
            opportunity=action.cost is ActionType.OPPORTUNITY,
        )

    if action.kind == "move":
        walk(world, actor, list(action.path))
        return True

    if action.kind == "shift":
        from .movement import shift

        shift(world, actor, action.dest)
        return True

    if action.kind == "stand":
        for eff in world.effects.of(actor):
            if Condition.PRONE in eff.conditions:
                world.effects.end(eff, "stood up")
        world.bus.emit(Note(text=f"{actor} stands"))
        return True

    if action.kind == "sustain":
        eff = world.effects.live.get(action.subject or -1)
        if eff is None:
            return False
        world.effects.sustain(eff)
        world.bus.emit(Note(text=f"{eff.label or eff} sustained"))
        return True

    if action.kind == "second_wind":
        health = world.need(actor, Health)
        known = world.get(actor, Powers)
        if known is not None:
            known.note_use("second-wind", world.round)
        from .resolve import spend_surge

        spend_surge(world, actor)
        world.heal(actor, actor, health.surge_value)
        from .cast import Cast

        Cast(world=world, me=actor, ref="second-wind", target=actor).bonus(
            "ac", 2, until=When.SONT, on=actor, kind="untyped"
        )
        return True

    return False


def recharge(world: World, actor: int) -> None:
    """Roll for any recharge power the creature has spent.

    Monsters only -- nothing a character carries recharges on a die.
    """
    known = world.get(actor, Powers)
    if known is None:
        return
    for ref in sorted(known.spent):
        p = get(ref)
        if p is None or p.usage is not Usage.RECHARGE or p.recharge <= 0:
            continue
        if world.rng.d20().total >= p.recharge:
            known.restore(ref)
