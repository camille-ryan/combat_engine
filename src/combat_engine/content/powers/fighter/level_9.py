"""Fighter, level 9: daily attacks.

Two close bursts that print "each enemy you can see", which is one clause
more than the burst already checks -- an enemy hidden from the fighter is in
the burst and is not a target.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.query import hidden_from

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


@power(
    "p1092",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p1092(c: Cast) -> None:
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p1437",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1437(c: Cast) -> None:
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.slide(1)
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p1438",
    level=9,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.HEALING, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p1438(c: Cast) -> None:
    """"Hit points equal to your healing surge value" is not a surge: nobody's
    pool is touched. `c.surge_value` defaults to the target, so the fighter
    has to be named on both halves of the line."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.heal(c.surge_value(of=c.me), on=c.me)
