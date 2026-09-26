"""Invoker, level 2: the party-wide initiative shove.

Same gap and same answer as the bard's: `c.initiative` writes the component
the sort reads, which is what `InitiativeRolled.rolled` could not do.
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

ROLLED = "you and your allies roll initiative at the beginning of an encounter"


@power(
    "p3397",
    level=2,
    cls="invoker",
    usage=DAILY,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE],
    trigger=ROLLED,
    on=Trigger(InitiativeRolled, about_me, ROLLED),
)
def p3397(c: Cast) -> None:
    """The printed trigger names everybody's roll; the invoker's own is the
    one that can be declared, and it is the one that happens once."""
    c.initiative(2 + c.int_mod)
