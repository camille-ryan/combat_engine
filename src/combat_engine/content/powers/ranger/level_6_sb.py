"""Ranger, level 6: shooting a falling creature onto a ledge.

The save is the printed one -- "the creature can attempt a saving throw to
avoid falling farther" -- and succeeding cancels the `Fell` outright, which
is what an interrupt on a `Decision` is for. The slide then puts it on the
surface beside it.

"Or to a vertical surface that the creature now climbs" is the destination
rather than a second effect, and which square that is belongs to the
slide's decider; no climb speed is granted, because none is printed.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    INTERRUPT,
    NO_TARGET,
    Cast,
    Fell,
    Keyword,
    Ranged,
    World,
    power,
)
from combat_engine.engine.components import Gear
from combat_engine.engine.grid import spread
from combat_engine.engine.query import distance_between, squares
from combat_engine.engine.triggers import Trigger

_FALLS_BY_A_WALL = "a creature in range falls and has a wall or floor within 1 square"


def _bow_in_hand(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    fired = gear.ranged
    return fired is not None and fired.group in ("bow", "crossbow")


def _falls_by_a_wall(world: World, me: int, ev: Fell) -> bool:
    if distance_between(world, me, ev.actor) > 10:
        return False
    theirs = squares(world, ev.actor)
    return any(sq in world.grid.blocking for sq in spread(theirs, 1) - theirs)


@power(
    "p10702",
    level=6,
    cls="ranger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10, by_weapon=True),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    requires=_bow_in_hand,
    requires_text="you must be wielding a bow or a crossbow",
    trigger=_FALLS_BY_A_WALL,
    on=Trigger(Fell, _falls_by_a_wall, _FALLS_BY_A_WALL),
)
def p10702(c: Cast) -> None:
    who = getattr(c.trigger, "actor", None)
    if who is None:
        return
    if c.save(on=who, bare=True):
        c.cancel()
        c.slide(1, on=who)
