"""Sorcerer, level 10: the no-action that takes a turn through a stun."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Condition,
    Keyword,
    Trigger,
    TurnStart,
    When,
    World,
    both,
    power,
)
from combat_engine.engine.query import is_

_HELD = (Condition.STUNNED, Condition.DAZED, Condition.UNCONSCIOUS)


def _held_fast(world: World, me: int, ev: Any) -> bool:
    """The second half of the printed Trigger: not merely your turn starting
    but your turn starting under one of the three conditions."""
    return any(is_(world, me, cond) for cond in _HELD)


@power(
    "p10355",
    level=10,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="you start your turn stunned, dazed, or unconscious",
    on=Trigger(
        TurnStart,
        both(lambda w, me, ev: getattr(ev, "actor", None) == me, _held_fast),
        "you start your turn stunned, dazed, or unconscious",
    ),
)
def p10355(c: Cast) -> None:
    """Suppressed rather than cured, which is the difference the last
    sentence of the card insists on: the condition is still there at the end
    of the turn, with its save still to make and whatever applied it
    untouched."""
    c.ignore_condition(*_HELD, until=When.EOT)
