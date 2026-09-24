"""Wizard, level 1: the powers that are not at-will."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    INT,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Keyword,
    When,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p159",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p159(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p185",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p185(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.COLD)
    if c.first:
        # The burst leaves the ground frozen behind it. `hazard` carries the
        # whole "enters or starts its turn there, once per turn" clause.
        c.hazard(c.area(), 5, DamageType.COLD, until=When.SUSTAIN)
