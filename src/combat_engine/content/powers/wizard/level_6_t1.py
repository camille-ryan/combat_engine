"""Wizard, level 6: the minor action that lengthens your own shoves."""

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
    "p10145",
    level=6,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p10145(c: Cast) -> None:
    """`c.forces` is read off the creature doing the shoving, which is what
    "forced movement you cause" means -- the victim's own `"forced"`
    modifiers cannot say it. The Intimidate half is a skill check and the
    engine rolls none."""
    c.forces(2, until=When.EONT)
    c.note("p10145: +5 power bonus to Intimidate checks")
