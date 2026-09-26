"""Assassin, level 6: a stance that buys a shift for a minor action."""

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
    "p9430",
    level=6,
    cls="assassin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.STANCE],
)
def p9430(c: Cast) -> None:
    """One square, but for a minor rather than a move -- `actions.legal` reads
    the cost back off the grant, so the cheaper action is the whole row."""
    c.stance()
    c.shift_as(MINOR, 1)
