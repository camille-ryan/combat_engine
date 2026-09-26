"""Seeker, level 6: shooting past the weapon's normal range."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p11480",
    level=6,
    cls="seeker",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
)
def p11480(c: Cast) -> None:
    """Long range is the weapon's second number, not the row's: `resolve`
    charges 2 for a weapon shot past the first one, and this is the waiver.
    Nothing stops the shot going further than the second, here or anywhere --
    no board is that wide."""
    c.ignores_long_range(until=When.EONT)
