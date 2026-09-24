"""Wizard, level 3: the encounter attacks.

Four evocations and nothing clever: each is an area or a pair of targets,
one attack roll per creature, and a rider the engine already has a word for.
"""

from __future__ import annotations

from combat_engine.engine import (
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    Ranged,
    UpTo,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1530",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p1530(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)


@power(
    "p173",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(INT, vs=WILL),
)
def p173(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.RADIANT)
        c.dazed()


@power(
    "p2272",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=FORT),
)
def p2272(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)


@power(
    "p435",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=REF),
)
def p435(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.COLD)
        c.immobilized()
    else:
        # The miss line still holds the target where it stands, slowly.
        c.slowed()
