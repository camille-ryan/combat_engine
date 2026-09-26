"""Assassin, level 10: the daily that pins one creature in your sight."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    ONE_CREATURE,
    Cast,
    CloseBurst,
    Keyword,
    power,
)


@power(
    "p13807",
    level=10,
    cls="assassin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW],
)
def p13807(c: Cast) -> None:
    """Knowing the direction and distance is narrative; the half with a
    consequence is that the target cannot be invisible to you, which is
    `of=` rather than a radius. The printed duration is the next extended
    rest, and the encounter is the longest clock the engine keeps."""
    c.truesight(of=c.target)
