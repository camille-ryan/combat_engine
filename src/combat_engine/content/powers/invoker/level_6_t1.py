"""Invoker, level 6: the daily that moves where your attacks come from."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    ONE_ALLY,
    Cast,
    Keyword,
    Ranged,
    When,
    power,
)


@power(
    "p10265",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p10265(c: Cast) -> None:
    """The proviso -- only while you have line of sight to the ally -- is
    checked where the square is borrowed, so it needs nothing here. The
    printed restriction to divine at-will and encounter attacks is dropped:
    the borrowed origin is read per range rather than per row, so every
    ranged or area attack the invoker makes uses it while it lasts."""
    ally = c.target
    if ally is not None:
        c.cast_from(ally, until=When.ENCOUNTER)
