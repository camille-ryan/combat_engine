"""Swordmage, level 10: the daily stance that sees the unseen nearby."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    power,
)


@power(
    "p3147",
    level=10,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p3147(c: Cast) -> None:
    """Awareness within five squares, hidden or invisible, is truesight with
    a radius on it. The second printed sentence is a disclaimer -- it does
    not negate cover or concealment -- and this grants neither, so nothing
    has to be taken back."""
    c.truesight(5)
