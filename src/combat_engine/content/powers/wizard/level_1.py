"""Wizard, level 1."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    EACH_ENEMY,
    FORT,
    INT,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Ranged,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1167",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=FORT),
)
def p1167(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.COLD)
        c.slowed()


@power(
    "p1166",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p1166(c: Cast) -> None:
    # An area burst rolls separately against everyone it catches, and the
    # body runs once per target, so there is no loop to write here.
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p463",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
)
def p463(c: Cast) -> None:
    # No attack roll at all: the damage simply happens.
    c.flat(2 + c.int_mod, dtype=DamageType.FORCE)
