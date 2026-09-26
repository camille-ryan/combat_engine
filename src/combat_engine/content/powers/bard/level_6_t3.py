"""Bard, level 6: the opening-round initiative shove.

The spec entry said `InitiativeRolled.rolled` is a copy the sort never reads
and that no `Cast` method writes the component. `c.initiative` was added for
exactly that and goes through `Encounter.adjust_initiative`, which writes
`Initiative.rolled` and splices the creature back into a live order.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ActionType,
    Cast,
    CloseBurst,
    InitiativeRolled,
    Keyword,
    Trigger,
    about_me,
    power,
)

ROLLED = "you roll initiative"
ON_INITIATIVE = Trigger(InitiativeRolled, about_me, ROLLED)


@power(
    "p3121",
    level=6,
    cls="bard",
    usage=DAILY,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
    trigger=ROLLED,
    on=ON_INITIATIVE,
)
def p3121(c: Cast) -> None:
    """`about_me` is right here where it usually is not: `InitiativeRolled`
    names its subject `actor`, so the caster's own roll is what arms it.

    `EACH_ALLY`'s pool includes the caster, so "you and each ally" needs no
    second line for the bard.
    """
    c.initiative(5)
