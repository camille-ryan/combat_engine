"""Warlock, level 2: the utilities.

All four are personal, and none attacks. `p380` and `p1299` print a skill
bonus and nothing else, and this engine has no checks for them to modify, so
they are declared inert with `out_of_combat=True` -- the cantrips in
`wizard/level_0.py` are the same shape -- rather than given a combat effect
they do not have.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    MOVE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Cast,
    Keyword,
    When,
    power,
)

ARCANE = [Keyword.ARCANE]


@power(
    "p1299",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p1299(c: Cast) -> None:
    c.note("p1299: a +5 power bonus to one social check this encounter")


@power(
    "p380",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p380(c: Cast) -> None:
    # Printed with the Illusion keyword, which the engine's list does not
    # carry; the Arcane keyword is the whole of what can be declared.
    c.note("p380: a +5 power bonus to going unnoticed, until your next turn ends")


@power(
    "p729",
    level=2,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p729(c: Cast) -> None:
    c.temp_hp(5 + c.con_mod, on=c.me)


@power(
    "p750",
    level=2,
    cls="warlock",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p750(c: Cast) -> None:
    # Printed with the Teleportation keyword, which the engine's list does
    # not carry. "All defenses" is the four of them, one bonus each.
    c.teleport(3)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT)
