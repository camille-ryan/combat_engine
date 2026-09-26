"""Ardent, level 7: the at-will that spoils the target's damage rolls."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    Keyword,
    Melee,
    When,
    power,
)


@power(
    "p12958",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p12958(c: Cast) -> None:
    """The unaugmented line is 1[W] with no ability modifier; the rider is
    the whole point of it.

    Dropped augments: Augment 1 adds the Charisma modifier and halves the
    target's basic attacks; Augment 2 is 2[W] with a damage penalty.
    """
    if c.strike():
        c.damage(c.w())
        c.damage_disadvantage(until=When.SONT)
