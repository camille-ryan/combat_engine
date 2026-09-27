"""Ardent, level 1: the at-will whose rider is an opportunity-attack leash.

Every at-will on this page prints an Augment 1 and an Augment 2 line, bought
with power points through `augment`.
"""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
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

    Augment 1 is the same loop with the caster left in it, which is what
    "cannot make opportunity attacks" comes to. Augment 2 drops the leash
    and dazes instead.
    """
    spent = augment(c)
    if not c.strike():
        return
    c.damage(c.w(), c.cha_mod)
    victim = c.target
    if victim is None:
        return
    if spent == 2:
        c.dazed(until=When.EONT)
        return
    for other in creatures(c.world):
        if other != c.me or spent:
            c.no_provoke(from_=victim, on=other, until=When.EONT)
