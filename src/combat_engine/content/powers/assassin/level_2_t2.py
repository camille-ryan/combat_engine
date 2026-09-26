"""Assassin, level 2: a stance whose whole content is a cheaper shift."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    MOVE,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    power,
)


@power(
    "p12452",
    level=2,
    cls="assassin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.STANCE],
)
def p12452(c: Cast) -> None:
    """`c.shift_as` is a standing change to the action menu, not a shift now:
    nothing moves when the stance is entered."""
    c.stance()
    c.shift_as(MOVE, 2)
