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
    dropped=("c.cast_from(only=)",),
)
def p10265(c: Cast) -> None:
    """The proviso -- only while you have line of sight to the ally -- is
    checked where the square is borrowed, so it needs nothing here.

    The printed restriction to divine at-will and encounter attacks is
    dropped, and **the direction of the error is why it earns a marker**:
    `dsl.measured_from` reads the borrowed origin per *range*, not per
    row, so every ranged or area attack the invoker makes borrows it while
    the hold lasts. That is wider than the card, not narrower -- a daily
    and a non-divine attack both get an origin the printed line withholds.

    The sibling gaps are in the same verb and are each a different
    argument: `p10193` wants a distance proviso, `p10203` a square rather
    than a creature. Three symbols, one family."""
    ally = c.target
    if ally is not None:
        c.cast_from(ally, until=When.ENCOUNTER)
