"""Battlemind, level 1: the at-will that shrugs a mark off.

The spec entry said nothing strips a standing condition and that a mark is a
Relation rather than a Condition, so the line needed both halves. `c.cure`
does both -- `durations.Effects.cure` clears the relational ones through
`relations` and the held ones through the effect that carries them -- and
`c.immune` is the second sentence.
"""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
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

    Augment 1 frees your allies within 5 as well; Augment 2 frees only you
    and adds immobilised to the list.
    """
    spent = augment(c)
    if not c.strike():
        return
    c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod)
    shrugged = (Condition.MARKED, Condition.SLOWED)
    if spent == 2:
        shrugged = (Condition.IMMOBILIZED, *shrugged)
    freed = [c.me]
    if spent == 1:
        freed += [a for a in c.within(5, side="ally") if a != c.me]
    for who in freed:
        c.cure(*shrugged, on=who)
        c.immune(*shrugged, on=who, until=When.EONT)
