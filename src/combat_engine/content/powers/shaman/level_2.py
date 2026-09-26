"""Shaman, level 2 utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    STANDARD,
    ActionType,
    AreaBurst,
    Cast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Keyword,
    Ranged,
    Trigger,
    When,
    about_me,
    power,
)
from combat_engine.engine.ecs import World
from combat_engine.engine.events import InitiativeRolled
from combat_engine.engine.query import distance_between, team

PRIMAL = [Keyword.PRIMAL]


def ally_damaged_within_10(world: World, me: int, ev: Any) -> bool:
    """An ally -- not me -- within 10 squares is about to take damage."""
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    if team(world, who) != team(world, me):
        return False
    return distance_between(world, me, who) <= 10


@power(
    "p3832",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p3832(c: Cast) -> None:
    """"As if he or she had spent a healing surge" -- the hit points arrive,
    the surge stays in the pool, so this is a heal and not `c.surge`."""
    mate = c.target
    if mate is not None:
        c.heal(c.surge_value(of=mate), on=mate)


@power(
    "p3834",
    level=2,
    cls="shaman",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PRIMAL,
    trigger="an ally within 10 squares of you takes damage",
    on=Trigger(
        DamageRolled,
        ally_damaged_within_10,
        "an ally within 10 squares of you takes damage",
    ),
)
def p3834(c: Cast) -> None:
    """Halving the blow in flight: the rolled amount is cut on the event
    itself -- an interrupt is before it lands -- and the other half is dealt
    to me. An odd number leaves the larger half with the ally."""
    ev = c.trigger
    amount = max(0, getattr(ev, "amount", 0))
    if amount <= 0:
        return
    mine = amount // 2
    ev.amount = amount - mine
    if mine:
        c.flat(mine, dtype=getattr(ev, "dtype", DamageType.UNTYPED), on=c.me)


@power(
    "p5394",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(5, 10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p5394(c: Cast) -> None:
    ring = c.zone(c.area(), until=When.ENCOUNTER)
    for mate in c.allies():
        c.bonus(
            "attack", 1, on=mate, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx, w=mate: w in c.world.zones.occupants(ring),
        )


@power(
    "p9748",
    level=2,
    cls="shaman",
    usage=DAILY,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=PRIMAL,
    trigger="you roll initiative at the beginning of an encounter",
    on=Trigger(
        InitiativeRolled, about_me, "you roll initiative at the start of a fight"
    ),
)
def p9748(c: Cast) -> None:
    """Drawing a weapon is not modelled -- everybody starts a fight armed --
    so the slide is the whole of it."""
    c.slide(3)
