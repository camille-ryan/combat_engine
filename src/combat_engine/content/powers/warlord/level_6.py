"""Warlord, level 6: utility. Nothing here rolls an attack of its own.

Two rows answer something the bus emits and both declare it with `on=`.
Neither printed line has a ready-made predicate: `ally_within` reads the
event's `actor` and falls back to its `target`, and on an `AttackDeclared`
the creature that swung is `attacker` -- so the charging ally and the ally
who just took a blow are each written out here.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    REACTION,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageApplied,
    Event,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    World,
    by_charge,
    power,
)
from combat_engine.engine.dsl import ANY_CREATURE
from combat_engine.engine.grid import distance
from combat_engine.engine.query import adjacent, distance_between, squares, team

MARTIAL = [Keyword.MARTIAL]

_ALLY_CHARGES = "an ally within 10 squares of you charges a creature"
_SOMEBODY_NEAR_IS_HURT = "you or an ally adjacent to you takes damage"


def _ally_charges_within(squares: int) -> Callable[[World, int, Event], bool]:
    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or who == me or not by_charge(world, me, ev):
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def _me_or_adjacent_ally_hurt(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "target", None)
    if who is None or getattr(ev, "amount", 0) <= 0:
        return False
    if who == me:
        return True
    return team(world, who) is team(world, me) and adjacent(world, me, who)


@power(
    "p1140",
    level=6,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
)
def p1140(c: Cast) -> None:
    """A flat number, not a surge: nobody's pool is touched by this one."""
    c.heal(10 + c.cha_mod)


@power(
    "p1141",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger=_ALLY_CHARGES,
    on=Trigger(AttackDeclared, when=_ally_charges_within(10), text=_ALLY_CHARGES),
)
def p1141(c: Cast) -> None:
    """Interrupted before the charge rolls, so the damage bonus is in place
    for it; the push and the follow-up shift wait for the hit.

    The bonus is gated on `charge` rather than given `once=True`. A
    once-only bonus is spent on `AttackRolled`, which is announced before
    the damage is rolled -- so a *damage* bonus written that way is taken
    away a moment before anything reads it. The gate says the printed
    sentence exactly and survives the ordering.

    "Then shift up to 2 squares to a square adjacent to the creature" names
    its destination, and `c.shift` only picks one through the decider -- so
    the square is chosen here from those that are both reachable and
    adjacent, the way `p1120` picks where a slid ally ends up.
    """
    ev = c.trigger
    ally = getattr(ev, "attacker", None) or c.target
    victim = getattr(ev, "target", None)
    if ally is None or victim is None:
        return
    c.bonus(
        "damage",
        c.int_mod,
        on=ally,
        until=When.EOT,
        when=lambda ctx: bool(ctx.get("charge")),
    )

    def follow_through(landed: Hit) -> None:
        if landed.attacker != ally or landed.target != victim:
            return
        c.push(2, on=victim, by=ally)
        held = squares(c.world, victim)
        where = [
            sq
            for sq in c.world.reachable_squares(ally, 2)
            if any(distance(sq, at) <= 1 for at in held)
        ]
        spot = c.choose(where, "where the charger ends up")
        if spot is not None:
            c.shift(to=spot, who=ally)

    c.watch(Hit, follow_through, until=When.EOT, once=True, label=f"{c.ref} follow")


@power(
    "p1143",
    level=6,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p1143(c: Cast) -> None:
    c.bonus("speed", 2, until=When.ENCOUNTER)


@power(
    "p3244",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
    trigger=_SOMEBODY_NEAR_IS_HURT,
    on=Trigger(DamageApplied, when=_me_or_adjacent_ally_hurt, text=_SOMEBODY_NEAR_IS_HURT),
)
def p3244(c: Cast) -> None:
    """"The character who takes the damage" is read off the event.

    The dispatcher only re-aims a row whose printed target is a single
    *enemy*, so this one would otherwise have healed whoever the targeting
    happened to pick.
    """
    who = getattr(c.trigger, "target", None) or c.target
    if who is not None and c.may("spend a healing surge", who=who):
        c.surge(on=who, bonus=c.cha_mod)
