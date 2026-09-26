"""Battlemind, level 6: one daily that refuses three conditions."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Condition,
    Keyword,
    When,
    power,
)


@power(
    "p13048",
    level=6,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
)
def p13048(c: Cast) -> None:
    """`c.immune` refuses a condition on the way in, which is the printed
    sentence -- `c.cure` would strip what is standing and let the next one
    land."""
    c.immune(
        Condition.SLOWED,
        Condition.IMMOBILIZED,
        Condition.RESTRAINED,
        until=When.ENCOUNTER,
        on=c.me,
    )
