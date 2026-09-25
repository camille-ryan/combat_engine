"""Two questions about squares that several sorcerer rows ask.

`beside` is "a square adjacent to the target", which four teleports print
and which `c.teleport` cannot answer on its own -- given no `to` it offers
every square in range and adjacency is not one of the filters.

`ringing` is the ring of squares around a creature, which is what "any
enemy that enters a square adjacent to it" lays its hazard over.
"""

from __future__ import annotations

from combat_engine.engine import Cast, Square, spread
from combat_engine.engine.query import squares


def ringing(c: Cast, who: int) -> frozenset[Square]:
    """Every square adjacent to `who`, the creature's own space left out."""
    theirs = squares(c.world, who)
    return frozenset(spread(theirs, 1) - theirs)


def beside(c: Cast, who: int | None) -> Square | None:
    """A free square next to `who`, chosen rather than taken."""
    if who is None:
        return None
    room = sorted(
        sq
        for sq in ringing(c, who)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) in (None, c.me)
    )
    return c.choose(room, f"{c.ref}: where you land") if room else None
