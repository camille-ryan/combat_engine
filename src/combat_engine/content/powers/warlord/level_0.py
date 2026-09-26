"""Warlord, level 0: the opening the class gets before anybody has moved."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    ONE_ALLY,
    ActionType,
    Cast,
    CloseBurst,
    InitiativeRolled,
    Keyword,
    Trigger,
    about_me,
    power,
)


@power(
    "p10887",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(3),
    target=ONE_ALLY,
    keywords=[Keyword.MARTIAL],
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p10887(c: Cast) -> None:
    """`about_me`, not `targets_me`: `InitiativeRolled` names its subject
    `actor`. The shift is the target's own, so its speed is the one read."""
    who = c.target
    if who is None:
        return
    c.shift(max(1, c.speed_of(who) // 2), who=who)
