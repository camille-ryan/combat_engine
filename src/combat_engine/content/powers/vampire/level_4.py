"""Vampire, level 4.

One row, and the same surge trade `level_3.py` describes -- here it raises
the bonus rather than buying a second target, so it is asked before the hold
is laid rather than before the roll.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Health,
    Keyword,
    When,
    power,
)

from . import next_check


@power(
    "p13858",
    level=4,
    cls="vampire",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p13858(c: Cast) -> None:
    """Two of the three things the card names are skills and the third is a
    raw **ability** check, which is a different roll read under a different
    modifier key: `ability:str`, totalled by `skills.ability_check` and never
    by `skills.modifier`. Folding it into a skill key would have put the
    bonus on nothing.

    No `against=` -- the card names no creature, and an ability check carries
    no target to gate on anyway.
    """
    health = c.world.get(c.me, Health)
    amount = 5
    if (
        health is not None
        and health.surges > 0
        and c.may("lose a healing surge for a bigger bonus", who=c.me)
        and c.spend_surge()
    ):
        amount = 10
    next_check(
        c, amount, "skill:athletics", "skill:endurance", "ability:str",
        until=When.EOT,
    )
