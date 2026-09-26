"""Bard, level 6: the burst that buys the party a cheaper shift."""

from __future__ import annotations

from combat_engine.engine import (
    EACH_ALLY,
    ENCOUNTER,
    MINOR,
    Cast,
    CloseBurst,
    Keyword,
    When,
    power,
)


@power(
    "p5690",
    level=6,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
)
def p5690(c: Cast) -> None:
    """"You and each ally in the burst" is the ally side, which includes the
    caster. Nothing happens now -- it is a line in each target's action menu
    until the end of your next turn."""
    c.grant_action("shift", MINOR, until=When.EONT)
