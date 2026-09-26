"""Ranger, level 2: a patch of ground the party crosses for nothing.

The printed Move Action moves the zone up to 5 squares. A zone's squares are
fixed when it is made and nothing relocates one, so that half is not written.
The pit clause goes with it: a pit is not a thing the board has.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    NO_TARGET,
    AreaBurst,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p13597",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p13597(c: Cast) -> None:
    """`c.ignores_difficult` is board-wide, so writing this as that would
    exempt the party everywhere -- a different rule, and the reason the row
    was left out rather than approximated. `c.ignores_difficult_in` is the
    same grant bounded by the zone: taken on entering, given back on
    leaving."""
    ground = c.zone(c.area(), until=When.ENCOUNTER)
    c.ignores_difficult_in(ground)
