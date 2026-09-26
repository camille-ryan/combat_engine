"""Runepriest, level 6: the +10 to everybody's initiative.

The spec entry named `c.initiative` as the missing method and Issue #168 as
the gap. Both are closed: `Encounter.adjust_initiative` writes the component
the order is sorted on, and `c.initiative` is the way in.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    FREE,
    Cast,
    CloseBurst,
    InitiativeRolled,
    Keyword,
    Trigger,
    about_me,
    power,
)

ROLLED = "you roll initiative"


@power(
    "p11392",
    level=6,
    cls="runepriest",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(20),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE],
    trigger=ROLLED,
    on=Trigger(InitiativeRolled, about_me, ROLLED),
)
def p11392(c: Cast) -> None:
    """"Ranged sight" is written as `CloseBurst(20)`: there is no unbounded
    range kind, `area_of` clips to the board anyway, and a target line
    naming everybody needs an area to name them in -- a ranged line with an
    `EACH_ALLY` target could not be aimed at all.

    """
    c.initiative(10)
