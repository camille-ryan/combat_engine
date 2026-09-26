"""Battlemind, level 6: throwing the weapon without letting go of it."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p2633",
    level=6,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
)
def p2633(c: Cast) -> None:
    """"Choose a weapon you are holding" is dropped: nothing records which
    weapon a melee swing was made with, so the choice would narrow the effect
    by a fact no later roll could be checked against. The weapon coming back
    to your hand is flavour on a thing that never left it."""
    c.as_ranged(10, until=When.EONT)
