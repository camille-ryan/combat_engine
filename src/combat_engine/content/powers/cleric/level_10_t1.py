"""Cleric, level 10: the daily that grants truesight."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    ONE_ALLY,
    Cast,
    Keyword,
    Ranged,
    power,
)


@power(
    "p7100",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p7100(c: Cast) -> None:
    """"You or one ally" is the ally side, which the caster is part of, so
    the sense goes on `c.target` rather than on its own default."""
    c.truesight(5, on=c.target)
