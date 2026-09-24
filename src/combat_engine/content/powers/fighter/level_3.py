"""Fighter, level 3: encounter attacks."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    power,
)
from combat_engine.engine.query import hidden_from

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


@power(
    "p200",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p200(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if c.wielding("polearm") or c.wielding("heavy blade"):
            c.immobilized()


@power(
    "p2176",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=4),
)
def p2176(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)


#: The weapon clause on `p268`, which also wants Dexterity 15.
_THIRD_SWING = ("flail", "light blade", "spear")


@power(
    "p268",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p268(c: Cast) -> None:
    """Two swings, and a third for the right weapon and enough Dexterity.

    The third is offered against anything in reach, which is how "either the
    target or a different creature" reads once the first two have landed --
    a target that died to them is simply not in the pool any more.
    """
    for _ in range(2):
        if c.strike():
            c.damage(c.w(1))
    # `c.dex_` is the attack bonus; the printed line wants the raw score.
    if c.stats.score(DEX) < 15 or not any(c.wielding(group) for group in _THIRD_SWING):
        return
    pool = c.within(1, side="enemy")
    who = c.choose(pool, "who the third swing catches") if pool else None
    if who is not None and c.strike(on=who):
        c.damage(c.w(1), on=who)


@power(
    "p291",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p291(c: Cast) -> None:
    """The burst already checks line of effect. "You can see" rules out one
    more thing that does not: an enemy hidden from you."""
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(1), c.str_mod)


@power(
    "p622",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p622(c: Cast) -> None:
    if c.strike():
        heavy = any(c.wielding(group) for group in ("axe", "hammer", "mace"))
        c.damage(c.w(2), c.str_mod + (c.con_mod if heavy else 0))


@power(
    "p634",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p634(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
