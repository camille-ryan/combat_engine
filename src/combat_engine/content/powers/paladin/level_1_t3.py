"""Paladin, level 1: the feature that takes a condition off somebody.

Written now because `c.cure` exists. The spec entry said nothing strips a
standing condition and named `c.cure` as the gap; the method had been added
for the battlemind's "you are no longer marked or slowed" and nobody came
back for this one.
"""

from __future__ import annotations

from combat_engine.engine import (
    ANY_CREATURE,
    DAILY,
    MINOR,
    Cast,
    Condition,
    Keyword,
    Melee,
    power,
)

REMOVABLE = (
    Condition.BLINDED,
    Condition.DAZED,
    Condition.DEAFENED,
    Condition.SLOWED,
    Condition.STUNNED,
    Condition.WEAKENED,
)


@power(
    "p7240",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=[Keyword.DIVINE],
    once_per_round=True,
)
def p7240(c: Cast) -> None:
    """Only a condition the target actually has is offered, so the choice is
    never between six things five of which do nothing.

    The printed Special is a per-day count equal to the paladin's Wisdom
    modifier. `uses` in the header is a constant and there is no expression
    for it, so the row carries `once_per_round=True` -- the half of the
    Special that is a rule rather than a number -- and is otherwise a daily.
    """
    standing = [k for k in REMOVABLE if c.is_(k)]
    if not standing:
        return
    chosen = c.choose(standing, "which condition to remove")
    if chosen is not None:
        c.cure(chosen)
