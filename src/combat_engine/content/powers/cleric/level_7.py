"""Cleric, level 7: encounter attacks.

Two implement rows at range and two weapon rows in reach. The only judgement
in the file is `p898`'s pool: "you and each ally adjacent to the target" is
the caster plus whoever else is standing next to it, and the surge is a
printed "can", so each of them is asked separately.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    power,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


@power(
    "p537",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p537(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.RADIANT)
        c.blinded()


@power(
    "p897",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=WILL),
)
def p897(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.immobilized()


@power(
    "p898",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p898(c: Cast) -> None:
    """The surge is each creature's own, so each one is asked for itself.

    The caster is put in the pool by hand rather than trusted to fall out of
    "allies adjacent to the target": it is named separately on the printed
    line, and a cleric with reach could be swinging from two squares away.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    victim = c.target
    if victim is None:
        return
    pool = {c.me, *c.within(1, of=victim, side="ally")}
    for friend in sorted(pool):
        if c.may("spend a healing surge", who=friend):
            c.surge(on=friend, bonus=c.cha_mod)


@power(
    "p899",
    level=7,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p899(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)
        c.penalty("attack", c.cha_mod)
