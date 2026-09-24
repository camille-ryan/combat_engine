"""Cleric, level 1: the powers that are not at-will."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    When,
    power,
)


@power(
    "p891",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def p891(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
        c.mark()
        # "you or one ally within 5" -- the caster is in the pool, and is
        # usually the right answer when the caster is the one who is hurt.
        nearby = [a for a in c.within(5, side="ally")]
        if nearby:
            c.surge(on=c.choose(nearby, "who spends a healing surge"))


@power(
    "p890",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.FEAR, Keyword.IMPLEMENT],
    attack=Attack(WIS, vs=WILL),
)
def p890(c: Cast) -> None:
    if c.strike():
        # It runs, and this is explicitly *not* forced movement, so it
        # provokes on the way out -- which is the whole point of the power.
        c.flee(c.speed_of() + c.cha_mod)


@power(
    "p1455",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
    uses=2,
    once_per_round=True,
)
def p1455(c: Cast) -> None:
    """The Special line -- twice a fight, but not twice in one round."""
    hurt = [a for a in c.within(5, side="ally") if c.wounded(a)]
    if not hurt:
        return
    who = c.choose(hurt, "who is healed")
    if c.surge(on=who):
        c.heal(c.world.rng.roll("1d6").total, on=who)


@power(
    "p913",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.IMPLEMENT],
    attack=Attack(WIS, vs=WILL),
)
def p913(c: Cast) -> None:
    if c.strike():
        c.weakened(until=When.EOTNT)
    if c.first:
        # The Effect line lands once, whatever the attacks did.
        for friend in [c.me, *c.within(3, side="ally")]:
            c.heal(5, on=friend)


