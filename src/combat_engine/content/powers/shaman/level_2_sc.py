"""Shaman, level 2: the row whose whole Effect is moving what you have made.

`c.move_zone` translates a zone's squares and refreshes the occupancy diff,
so everyone standing in it is told they have left and everyone the new
footprint covers is told they have arrived. `Zones` had no mover at all
before it.

The printed target is "each of your shaman conjurations and zones in the
burst". `c.my_zones` answers the zones; the spirit companion is the
conjuration a shaman always has, and `c.move_companion` is the only handle on
it. The burst is not filtered: a close burst 10 around the shaman reaches
every zone it is plausibly maintaining, and a zone's squares are not
something the target line can measure from here.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    Cast,
    CloseBurst,
    Keyword,
    power,
)


@power(
    "p3838",
    level=2,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def p3838(c: Cast) -> None:
    for zone in c.my_zones():
        c.move_zone(zone, 5)
    if c.companion() is not None:
        c.move_companion(5)
