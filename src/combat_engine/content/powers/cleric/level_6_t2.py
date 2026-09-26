"""Cleric, level 6: a hold kept but not felt."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    Cast,
    Condition,
    Keyword,
    Ranged,
    When,
    power,
)


@power(
    "p3681",
    level=6,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p3681(c: Cast) -> None:
    """"Ignores the effects of" is not `c.cure`: the conditions stay on the
    creature, so a save-ends hold is still owed its saving throw and an aura
    that laid one does not simply lay it again. `c.ignore_condition`
    suppresses them for a duration, which is the printed sentence, and it
    catches the ones that arrive during the window too."""
    c.ignore_condition(
        Condition.IMMOBILIZED,
        Condition.RESTRAINED,
        Condition.SLOWED,
        until=When.EONT,
    )
