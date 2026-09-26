"""Sorcerer level 6: a second swing at the one the action point paid for."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    NO_TARGET,
    PERSONAL,
    Cast,
    Keyword,
    Miss,
    Trigger,
    both,
    by_action_point,
    by_me,
    power,
)


@power(
    "p5852",
    level=6,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger="you spend an action point to make an attack and miss",
    on=Trigger(
        Miss,
        both(by_me, by_action_point),
        "you spend an action point to make an attack and miss",
    ),
)
def p5852(c: Cast) -> None:
    """Reroll the miss with Strength on top.

    A free action, so it answers in the reaction window -- after the `Miss`
    has been announced. `resolve.attack` re-announces the outcome when a
    listener changes it, which is what makes a reroll of this shape reach
    the riders of the row that swung.
    """
    c.reroll_attack(bonus=c.str_mod)
