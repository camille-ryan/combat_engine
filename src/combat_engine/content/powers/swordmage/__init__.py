"""Swordmage: the shared sentences this class prints over and over.

Three trigger predicates and one square-finder live here because the class
says each of them in a dozen rows and none of the ready-made predicates in
`engine.triggers` says it.

* "an ally is hit" reads `ev.target`, where `ally_within` reads the
  *attacker* -- so the stock predicate measures the wrong creature on a
  `Hit` and is silently false or silently true for the wrong reason.
* "by an enemy you have marked" is a relation, not a field on any event.
* "you teleport an enemy next to you on your turn" and "you teleport" are
  `MoveEnd.kind_`, which nothing ready-made looks at.

All four are exact, not approximations; they are named here rather than
written as a lambda per row so that a mistake in one is a mistake in one
place. The `Cast` methods they want adding centrally are in the report.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import Cast, Relation, Usage, World
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import Square, distance, spread
from combat_engine.engine.query import distance_between, squares, team

Predicate = Callable[[World, int, Any], bool]


def square_of(world: World, who: int) -> Square | None:
    here = squares(world, who)
    return min(here) if here else None


def beside(c: Cast, who: int | None = None) -> Square | None:
    """A free square next to `who`, the caster by default.

    "Teleport the target to a square adjacent to you" names its destination,
    and `c.teleport` without `to=` lets the decider pick anywhere in range.
    """
    anchor = c.here if who is None else square_of(c.world, who)
    if anchor is None:
        return None
    for sq in sorted(spread({anchor}, 1)):
        if sq == anchor:
            continue
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


# -- predicates -------------------------------------------------------------


def by_my_mark(world: World, me: int, ev: Any) -> bool:
    """Whoever caused this is marked by me."""
    who = getattr(ev, "attacker", None)
    if who is None:
        who = getattr(ev, "source", None)
    return who is not None and world.relations.holds(Relation.MARKED_BY, me, who)


def ally_target_within(radius: int) -> Predicate:
    """An ally of mine -- not me -- was on the receiving end, within range."""

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= radius

    return check


def teleported_beside_me(world: World, me: int, ev: Any) -> bool:
    """An enemy finished a teleport next to me, on my turn."""
    if getattr(ev, "kind_", "") != "teleport" or world.turn != me:
        return False
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 1


def i_teleported(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "kind_", "") == "teleport"


def moves_away_from_me(world: World, me: int, ev: Any) -> bool:
    """An enemy's step took it further from me. `Moved` carries both ends."""
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    here = square_of(world, me)
    end, start = getattr(ev, "to", None), getattr(ev, "from_", None)
    if here is None or end is None or start is None:
        return False
    return distance(end, here) > distance(start, here)


def my_at_will_missed(world: World, me: int, ev: Any) -> bool:
    """I used one of my class's at-will attacks and it did not land."""
    if getattr(ev, "attacker", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.cls == "swordmage" and p.usage is Usage.AT_WILL
