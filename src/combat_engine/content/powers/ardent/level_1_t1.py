"""Ardent, level 1: the at-will whose rider is an opportunity-attack leash.

Every at-will on this page prints an Augment 1 and an Augment 2 line. The
engine has no power points, so what is written is the unaugmented line and
the docstring names the clauses dropped.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.query import creatures


@power(
    "p12932",
    level=1,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSIONIC, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p12932(c: Cast) -> None:
    """"Cannot make opportunity attacks against any creature other than you"
    is an immunity handed to everybody *else* on the board, which is why it
    is a loop and not one call: the leash is the caster being the only
    exception. Enemies of the target are in the loop too, since the printed
    line says any creature.

    Dropped augments: Augment 1 bars its opportunity attacks outright;
    Augment 2 dazes it instead.
    """
    if not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    victim = c.target
    if victim is None:
        return
    for other in creatures(c.world):
        if other != c.me:
            c.no_provoke(from_=victim, on=other, until=When.EONT)
