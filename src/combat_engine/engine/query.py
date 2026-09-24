"""Facts derived from the board, asked rather than stored.

Combat advantage is the reason this module exists. A dozen unrelated things
grant it -- flanking, prone, blinded, stunned, a power that says so -- and
storing a flag means every one of them has to remember to take it back. So
nothing stores it; it is recomputed from the board whenever an attack asks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .components import (
    Conditions,
    Defenses,
    Health,
    Mods,
    Movement,
    Position,
    Side,
    Stats,
)
from .conditions import rules
from .grid import Square, between, spread
from .types import Condition, Cover, Defense, Relation, Team

if TYPE_CHECKING:
    from .ecs import World


def creatures(world: World) -> list[int]:
    return list(world.having(Health, Position))


def squares(world: World, eid: int) -> frozenset[Square]:
    pos = world.get(eid, Position)
    return pos.squares if pos else frozenset()


def team(world: World, eid: int) -> Team | None:
    side = world.get(eid, Side)
    return side.team if side else None


def allies(world: World, eid: int) -> list[int]:
    """Allies never include the creature itself."""
    mine = team(world, eid)
    return [o for o in creatures(world) if o != eid and mine is not None and team(world, o) is mine]


def enemies(world: World, eid: int) -> list[int]:
    mine = team(world, eid)
    if mine is None:
        return []
    return [
        o
        for o in creatures(world)
        if team(world, o) is not None and team(world, o) is not mine and alive(world, o)
    ]


def alive(world: World, eid: int) -> bool:
    h = world.get(eid, Health)
    return h is not None and h.hp > h.dying_at


def conscious(world: World, eid: int) -> bool:
    return alive(world, eid) and not is_(world, eid, Condition.UNCONSCIOUS)


def is_(world: World, eid: int, c: Condition) -> bool:
    conds = world.get(eid, Conditions)
    return conds is not None and conds.has(c)


def active(world: World, eid: int) -> list[Condition]:
    conds = world.get(eid, Conditions)
    return conds.active if conds else []


def distance_between(world: World, a: int, b: int) -> int:
    return between(squares(world, a), squares(world, b))


def adjacent(world: World, a: int, b: int) -> bool:
    return bool(spread(squares(world, a), 1) & squares(world, b))


# -- numbers ----------------------------------------------------------------


def speed(world: World, eid: int) -> int:
    mv = world.get(eid, Movement)
    if mv is None:
        return 0
    base = mv.speed
    mods = world.get(eid, Mods)
    if mods is not None:
        base += mods.total("speed")
    for c in active(world, eid):
        cap = rules(c).speed_cap
        if cap is not None:
            base = min(base, cap)
        if rules(c).cannot_move:
            return 0
    return max(0, base)


def level_term(world: World, eid: int, scale: str) -> int:
    """What this creature's level is worth, under the current setting."""
    stats = world.get(eid, Stats)
    level = stats.level if stats else 1
    if scale == "pc":
        return world.scaling.pc(level)
    if scale == "monster":
        return world.scaling.monster(level)
    return 0


def defence(world: World, eid: int, d: Defense, ctx: dict | None = None) -> int:
    """A defence as the attacker sees it: base, level, modifiers, conditions.

    The stored value has no level in it -- see `engine/scaling.py` -- so this
    is the one place a defence gains one, and turning scaling off turns it
    off everywhere at once.
    """
    defs = world.need(eid, Defenses)
    base = defs.base(d) + level_term(world, eid, defs.scale)
    mods = world.get(eid, Mods)
    if mods is not None:
        base += mods.total(d.value, ctx or {})
    for c in active(world, eid):
        base += rules(c).defences.get(d, 0)
    return base


def attack_penalty(world: World, eid: int) -> int:
    """What the attacker's own conditions cost it, before modifiers."""
    return sum(rules(c).attack for c in active(world, eid))


def deals_half(world: World, eid: int) -> bool:
    return any(rules(c).weakened for c in active(world, eid))


def can_act(world: World, eid: int) -> bool:
    return conscious(world, eid) and not any(rules(c).cannot_act for c in active(world, eid))


def can_react(world: World, eid: int) -> bool:
    return can_act(world, eid) and not any(rules(c).no_reactions for c in active(world, eid))


def can_move(world: World, eid: int) -> bool:
    return can_act(world, eid) and not any(rules(c).cannot_move for c in active(world, eid))


# -- combat advantage -------------------------------------------------------


def grants_ca(world: World, eid: int) -> bool:
    """True when the creature grants combat advantage to everyone."""
    return any(rules(c).grants_ca for c in active(world, eid))


def flanked_by(world: World, target: int, attacker: int) -> bool:
    """Is `target` flanked by `attacker` and one of its allies?

    Both flankers must be able to attack -- a stunned ally standing in the
    right square is furniture, and the printed rule says so.
    """
    if not adjacent(world, attacker, target) or not can_act(world, attacker):
        return False
    space = squares(world, target)
    for mate in allies(world, attacker):
        if mate == target or not can_act(world, mate) or not adjacent(world, mate, target):
            continue
        for a in squares(world, attacker):
            for b in squares(world, mate):
                if world.grid.flanks(a, b, space):
                    return True
    return False


def has_combat_advantage(world: World, attacker: int, target: int) -> bool:
    if grants_ca(world, target):
        return True
    if world.relations.holds(Relation.GRANTS_CA_TO, target, attacker):
        return True
    if world.relations.holds(Relation.HIDDEN_FROM, attacker, target):
        return True
    return flanked_by(world, target, attacker)


def cover_between(world: World, attacker: int, target: int) -> Cover:
    """The worst cover the target has, measured from the attacker's best square.

    Creatures other than the two involved grant cover; terrain always does.
    """
    theirs = squares(world, target)
    mine = squares(world, attacker)
    if not theirs or not mine:
        return Cover.NONE
    bodies = {
        sq
        for other in creatures(world)
        if other not in (attacker, target)
        for sq in squares(world, other)
    }
    best = Cover.SUPERIOR
    for src in mine:
        for dst in theirs:
            best = min(best, world.grid.cover(src, dst, blockers=bodies))
    return best


def line_of_effect(world: World, a: int, b: int) -> bool:
    return any(
        world.grid.line_of_effect(src, dst)
        for src in squares(world, a)
        for dst in squares(world, b)
    )
