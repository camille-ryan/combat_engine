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
    halved = False
    for c in active(world, eid):
        cap = rules(c).speed_cap
        if cap is not None:
            base = min(base, cap)
        halved = halved or rules(c).halve_speed
        if rules(c).cannot_move:
            return 0
    if halved:
        base //= 2
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


#: Roles whose whole point is to stay out of melee, whatever else they can
#: also do. Read alongside what a creature *can* reach with, because the two
#: answer different questions.
_STANDOFF = {"artillery", "controller", "lurker"}


def range_profile(world: World, eid: int) -> str:
    """What this creature can reach with: melee, ranged, hybrid, or none.

    Derived from its own declared rows rather than written down anywhere.
    A hand-applied tag would be one more thing to keep in step with the
    content, and the content already says it -- every row carries its reach
    in the header, which is exactly the point of the header being data.
    """
    from .components import Powers
    from .dsl import get

    known = world.get(eid, Powers)
    if known is None:
        return "none"
    near = far = False
    for ref in known.all:
        p = get(ref)
        if p is None or not p.is_attack:
            continue
        for branch in p.branches:
            kind = p.reach_of(branch).kind
            far = far or kind in ("ranged", "area_burst")
            near = near or kind in ("melee", "close_burst", "close_blast")
    if far and near:
        return "hybrid"
    return "ranged" if far else "melee" if near else "none"


def prefers_range(world: World, eid: int) -> bool:
    """Does this creature want to be *out* of melee?

    Capability alone does not say. Nearly every ranged monster also carries
    a melee basic, so by reach almost none of them are purely ranged -- at
    the heroic tier it is 44 melee and 25 hybrid, and not one pure shooter.
    What separates an artillery that happens to have claws from a brute
    that happens to throw something is the role it was written for, which
    the stat block already records.
    """
    from .components import Ident

    profile = range_profile(world, eid)
    if profile in ("melee", "none"):
        return False
    if profile == "ranged":
        return True
    ident = world.get(eid, Ident)
    if ident is None or not ident.ref.startswith("m"):
        return False
    from combat_engine.content.loader import load

    try:
        return (load(ident.ref).row.get("role") or "") in _STANDOFF
    except Exception:
        return False


def is_trap(world: World, eid: int) -> bool:
    from .components import Trap

    return world.get(eid, Trap) is not None


def is_conjuration(world: World, eid: int) -> bool:
    from .components import Conjuration

    return world.get(eid, Conjuration) is not None


def can_act(world: World, eid: int) -> bool:
    # A trap and a conjuration have no hit points to be unconscious about.
    # Without this they failed `conscious` and could never make the attack
    # they exist to make.
    if is_trap(world, eid) or is_conjuration(world, eid):
        return True
    return conscious(world, eid) and not any(rules(c).cannot_act for c in active(world, eid))


def can_react(world: World, eid: int) -> bool:
    return can_act(world, eid) and not any(rules(c).no_reactions for c in active(world, eid))


def takes_half(world: World, eid: int) -> bool:
    """Insubstantial: everything that reaches this creature is halved."""
    return any(rules(c).insubstantial for c in active(world, eid))


def can_shift(world: World, eid: int) -> bool:
    """A shift is barred separately from a walk, and by different powers."""
    return can_move(world, eid) and not any(rules(c).no_shift for c in active(world, eid))


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


def hidden_from(world: World, eid: int) -> set[int]:
    """Who cannot see this creature."""
    return set(world.relations.targets(Relation.HIDDEN_FROM, eid))


def cover_between(
    world: World, attacker: int, target: int, *, ranged: bool = False
) -> Cover:
    """The worst cover the target has, measured from the attacker's best square.

    Worked out at the moment of the attack by tracing corner to corner --
    `Grid.cover` does the drawing -- rather than stored anywhere, because
    cover is a fact about two positions and both of them move.

    **Terrain always blocks. Creatures block only a ranged attack, and only
    the target's own allies do.** Both halves of that were wrong: every
    creature on the board was counted, for every kind of attack, so a
    fighter in a melee got a cover penalty for the enemy standing beside its
    target, and the target's enemies were sheltering it from its friends.
    Somebody in your way is cover your side gave you.
    """
    theirs = squares(world, target)
    mine = squares(world, attacker)
    if not theirs or not mine:
        return Cover.NONE

    bodies: set[Square] = set()
    if ranged:
        side = team(world, target)
        bodies = {
            sq
            for other in creatures(world)
            if other not in (attacker, target)
            and alive(world, other)
            and team(world, other) is side
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
