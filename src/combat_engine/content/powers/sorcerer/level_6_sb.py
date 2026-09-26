"""Sorcerer, level 6: one square of ground, up or down.

The first row with anything to say about elevation. Raised, the square is
blocking terrain -- which is the printed "the area below it is filled with
solid rock". Sunk, its floor is below the rest of the board, and walking in
or being shoved in is a fall of that depth, which is what makes `Fell`
something a fight can actually produce.

"This power cannot be used to harm a creature, and any such use causes the
power to fail" is honoured by only offering squares nobody is standing in.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    Cast,
    Keyword,
    Ranged,
    When,
    power,
)
from combat_engine.engine.grid import spread

_RAISE = "raise it"
_SINK = "sink it"


@power(
    "p16240",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
)
def p16240(c: Cast) -> None:
    """Twenty feet up and ten feet down are four squares and two."""
    grid = c.world.grid
    spots = sorted(
        sq
        for sq in spread({c.here}, 5)
        if grid.passable(sq) and grid.occupant(sq) is None and sq != c.here
    )
    where = c.choose(spots, f"{c.ref}: which square")
    if where is None:
        return
    which = c.choose([_RAISE, _SINK], f"{c.ref}: up or down")
    if which == _SINK:
        c.terraform(where, sink=2)
    else:
        c.terraform(where, raise_=4)

    def restore() -> None:
        grid.elevation.pop(where, None)
        if which != _SINK:
            grid.blocking.discard(where)

    hold = c.effect(f"{c.ref} ground", until=When.ENCOUNTER, on=c.me)
    if hold is not None:
        hold.on_end.append(restore)
