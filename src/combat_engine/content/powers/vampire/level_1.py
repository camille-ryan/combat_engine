"""Vampire, level 1: three at-wills and the daily.

Each at-will prints a `Level 21:` line doubling its dice, which is the
ordinary at-will upgrade and is written as a branch on `c.level` -- the shape
`avenger/level_1.py` and `warlock/level_0.py` both use for an implement die.

Two of the three roll Dexterity and the third rolls Charisma, so there is no
class-wide ability to settle here and each header names its own.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    CHA,
    DAILY,
    DEX,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    When,
    power,
)


@power(
    "p13850",
    level=1,
    cls="vampire",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(CHA, vs=WILL, plus=2),
)
def p13850(c: Cast) -> None:
    """The pull is part of the Hit line, so it is inside the branch."""
    if c.strike():
        c.damage(
            "2d6" if c.level >= 21 else "1d6", c.cha_mod, dtype=DamageType.PSYCHIC
        )
        c.pull(3)


@power(
    "p13851",
    level=1,
    cls="vampire",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.SHADOW],
    attack=Attack(DEX, vs=FORT),
)
def p13851(c: Cast) -> None:
    """The temporary hit points read Charisma while the attack reads
    Dexterity, which is the card and not a slip."""
    if c.strike():
        c.damage(
            "2d8" if c.level >= 21 else "1d8", c.dex_mod, dtype=DamageType.NECROTIC
        )
        c.temp_hp(2 + c.cha_mod, on=c.me)


@power(
    "p13852",
    level=1,
    cls="vampire",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=REF),
    basic="melee",
)
def p13852(c: Cast) -> None:
    """`basic="melee"` is the Special line, and it is the header's job rather
    than the body's: "can be used as a melee basic attack" is true for
    everybody holding the card, so `basic_options` offers the row and
    `resolve._is_basic` lets a basic-attack modifier find it without anything
    running. #522.

    The push is a printed "you can", so it is offered rather than taken.
    """
    if c.strike():
        c.damage("2d10" if c.level >= 21 else "1d10", c.dex_mod)
        if c.may("push it a square", who=c.me):
            c.push(1)


@power(
    "p13854",
    level=1,
    cls="vampire",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.SHADOW, Keyword.TELEPORTATION],
    attack=Attack(DEX, vs=FORT),
)
def p13854(c: Cast) -> None:
    """The Effect line resolves once and after the Hit and Miss lines, so it
    hangs on `c.last` rather than on `c.first`.

    "You teleport to a square in the blast" is `into=`, which filters what
    counts as a destination at all rather than preferring one -- so a blast
    with no free square in it is a teleport that does not happen, which is
    what `c.teleport` already answers for an unreachable board.

    `c.last` is True with an empty target list as well as on the final
    creature, so a blast that catches nobody still teleports: `max(0, len -
    1)` is 0 and `index` is 0. That is the printed reading -- the Effect line
    is not conditional on hitting anything.
    """
    if c.strike():
        c.damage("3d6", c.dex_mod)
        c.ongoing(5)
    else:
        c.half_damage("3d6", c.dex_mod)
    if not c.last:
        return
    blast = c.area()
    c.teleport(3, into=lambda sq: sq in blast)
    c.invisible(on=c.me, until=When.EONT)
