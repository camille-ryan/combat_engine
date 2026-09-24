"""Paladin, level 3: encounter attacks."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    Keyword,
    Melee,
    UpTo,
    power,
)

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


@power(
    "p1243",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1243(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.mark()


@power(
    "p1568",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(CHA, vs=WILL),
)
def p1568(c: Cast) -> None:
    """The allies' healing is its own sentence and carries no "if you are
    bloodied", so bloodied friends are picked up whether the paladin is
    hurt or not. Only the caster's own line waits on being bloodied.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.cha_mod)
    amount = 5 + c.wis_mod
    if c.bloodied(on=c.me):
        c.heal(amount, on=c.me)
    for friend in c.within(5, side="ally"):
        if friend != c.me and c.bloodied(on=friend):
            c.heal(amount, on=friend)


@power(
    "p2259",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2259(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.push(max(0, c.wis_mod))


@power(
    "p754",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,  # the healing keyword was errata'd off this row
    attack=Attack(CHA, vs=AC),
)
def p754(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        amount = 5 + c.wis_mod
        for friend in c.within(5, side="ally"):  # the ally pool has the caster in it
            c.temp_hp(amount, on=friend)
