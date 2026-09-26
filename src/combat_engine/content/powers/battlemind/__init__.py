"""Battlemind. Shared helpers for the class, and one note that covers it.

**Augmentation is not modelled.** Thirty-five of these rows print Augment 1
and Augment 2 clauses bought with power points, which the engine does not
have. Each of those is written in its base form -- the effect printed
before the first Augment line, which is a complete at-will on its own --
and the clauses that were dropped are named in that row's docstring.

The helpers are here because half the class lands somebody beside somebody
else, and "a square adjacent to you" is not the square a free-choice
decider picks.
"""

from __future__ import annotations

from combat_engine.engine import (
    Cast,
    Health,
    Keyword,
    Position,
    Square,
    World,
    spread,
)

PSIONIC = [Keyword.PSIONIC]
PSIONIC_WEAPON = [Keyword.PSIONIC, Keyword.WEAPON]


def bloodied(world: World, eid: int) -> bool:
    """"Requirement: You must be bloodied"."""
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def square_of(c: Cast, who: int) -> Square | None:
    pos = c.world.get(who, Position)
    return None if pos is None else pos.square


def beside(c: Cast, who: int) -> Square | None:
    """An unoccupied square next to `who`."""
    at = square_of(c, who)
    if at is None:
        return None
    for sq in sorted(spread({at}, 1)):
        if sq != at and c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def teleport_beside(c: Cast, mover: int, anchor: int) -> bool:
    """"Teleport the target to a square adjacent to you", and its mirror.

    The distance handed to `c.teleport` only has to be wide enough for the
    named square to be among the options; the square itself is the printed
    destination.
    """
    spot = beside(c, anchor)
    if spot is None:
        return False
    span = c.distance(mover) + c.distance(anchor) + 2
    return c.teleport(span, who=mover, to=spot)


def shift_beside(c: Cast, squares_: int, who: int) -> bool:
    """Shift up to `squares_`, landing adjacent to `who`."""
    at = square_of(c, who)
    if at is None:
        return False
    near = spread({at}, 1)
    options = [sq for sq in c.world.reachable_squares(c.me, squares_) if sq in near]
    if not options:
        return False
    return c.shift(squares_, to=sorted(options)[0])
