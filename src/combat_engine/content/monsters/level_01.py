"""Monster abilities, level 1.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack line is written exactly as printed -- `Attack(vs=AC, printed=6)` --
and `engine/scaling.py` takes the level back out of it, so these read the
same as the page they came from however the treadmill is set.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Keyword,
    Melee,
    Usage,
    When,
    power,
)


@power(
    "m145a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
)
def m145a0(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", 5)
        # The disease is a save at the end of the fight, not during it, so
        # it hangs on the encounter clock and rolls once when that runs out.
        c.condition(until=When.ENCOUNTER, save_mod=0)


@power(
    "m280a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=4),
)
def m280a0(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", 4)


@power(
    "m1063a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=4),
)
def m1063a0(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", 4)


@power(
    "m206a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
)
def m206a0(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", 2)


@power(
    "m206a1",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=4),
)
def m206a1(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", 1, dtype=DamageType.FIRE)
