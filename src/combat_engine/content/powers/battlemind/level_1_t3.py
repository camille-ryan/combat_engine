"""Battlemind, level 1: the at-will that shrugs a mark off.

The spec entry said nothing strips a standing condition and that a mark is a
Relation rather than a Condition, so the line needed both halves. `c.cure`
does both -- `durations.Effects.cure` clears the relational ones through
`relations` and the held ones through the effect that carries them -- and
`c.immune` is the second sentence.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    Condition,
    Keyword,
    Melee,
    When,
    power,
)


@power(
    "p13026",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON],
    attack=Attack(CON, vs=AC),
)
def p13026(c: Cast) -> None:
    """`on=c.me` on both: curing and immunity are done *to* somebody and so
    follow `c.target`, and here the creature freed is the battlemind, not
    the one it just hit.

    The two Augment lines are dropped -- nothing in the engine holds power
    points, so there is no number to spend and no way to pick a leg.
    """
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.cure(Condition.MARKED, Condition.SLOWED, on=c.me)
        c.immune(Condition.MARKED, Condition.SLOWED, on=c.me, until=When.EONT)
