"""Artificer, level 6: a span laid over whatever is in the way.

The printed sentence is a *removal* -- "as though it were normal terrain,
even if it normally contains no terrain, difficult terrain, challenging
terrain or hindering terrain" -- and a zone could only ever add. `c.floor`
is the overlay that answers all three questions at once; the map underneath
is untouched, so the chasm is still a chasm when the span lapses.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    STANDARD,
    ActionType,
    Cast,
    Keyword,
    Ranged,
    Square,
    When,
    distance,
    power,
    spread,
)
from combat_engine.engine.dsl import NO_TARGET


def _in_range(c: Cast, reach: int) -> list[Square]:
    """Every square on the board within range, nearest first.

    Not filtered for standing room: the whole point of the span is that it
    goes where the ground does not.
    """
    grid = c.world.grid
    here = c.here
    return sorted(
        (sq for sq in spread({here}, reach) if grid.inside(sq)),
        key=lambda sq: (distance(here, sq), sq),
    )


@power(
    "p4143",
    level=6,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
)
def p4143(c: Cast) -> None:
    """"Connects the two chosen squares by the shortest path" is `c.line`,
    the board's own straight run, so the span is whatever squares that
    crosses and no arithmetic is done here.

    The far end is offered farthest-first, because a span between two
    squares beside each other is worth nothing and an engine with nobody
    playing takes the first answer.
    """
    spots = _in_range(c, 20)
    start = c.choose(spots, "one end of the span")
    if start is None:
        return
    span = 2 + c.int_mod
    far = [sq for sq in reversed(spots) if sq != start and distance(start, sq) <= span]
    end = c.choose(far, "the other end of the span")
    if end is None:
        return
    c.floor(c.line(start, end), until=When.SUSTAIN, sustain=ActionType.MINOR)
