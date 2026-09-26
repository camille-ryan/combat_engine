"""Warden, level 2: a thicket that shelters the people standing in it."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    NO_TARGET,
    STANDARD,
    Cast,
    CloseBurst,
    Keyword,
    When,
    power,
)


@power(
    "p5109",
    level=2,
    cls="warden",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p5109(c: Cast) -> None:
    """Not `c.zone(blocks_sight=True)`, which is blocking terrain: that blinds
    both sides and gives the creature inside it nothing. `c.cover_in` is cover
    carried by whoever stands in the zone, and it takes the larger with a
    pillar rather than adding to it."""
    plants = c.zone(c.area(), until=When.ENCOUNTER)
    c.cover_in(plants)
