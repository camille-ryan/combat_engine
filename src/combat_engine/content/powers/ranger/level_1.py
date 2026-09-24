"""Ranger, level 1.

Two notes that apply to most of the rows below.

A great many ranger powers print two attack lines at once -- "Strength vs.
AC (melee) or Dexterity vs. AC (ranged)" -- and the header can hold only
one. Every such row here is written as its **ranged** branch: the range line
becomes `Ranged(10)`, the keywords carry `Keyword.RANGED` so `c.w()` rolls
the bow rather than the blade, and the attack and damage lines take
Dexterity. The melee branch of those rows is not expressible yet.

The other recurring shape is "two attacks". That is just `c.strike()` twice
in the body, which works because the body is per-target: a row that spreads
its two attacks over one or two creatures asks `c.first and c.last` to find
out whether it is the only target and takes both shots if so.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Gear,
    Keyword,
    Melee,
    Ranged,
    UpTo,
    When,
    World,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons."

    `Gear` has no hands, so this counts what is carried: two weapons that are
    not fired is as close as the model gets to one in each fist.
    """
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _two_melee_or_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return gear.ranged is not None or _two_melee(world, eid)


@power(
    "p1505",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1505(c: Cast) -> None:
    # The Effect line -- moving away afterwards does not provoke from this
    # target -- has nowhere to go yet, so only the attack is here.
    if c.strike():
        c.damage(c.w(1), c.str_mod)


@power(
    "p917",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC, plus=2),
    requires=_two_melee_or_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p917(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p919",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p919(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    c.shift(1)  # "before or after": after is the half that can be taken here


@power(
    "p87",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_two_melee_or_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p87(c: Cast) -> None:
    """Two attacks, spread over one or two creatures.

    One target and both attacks go into it; two targets and each gets one.
    `c.first and c.last` is how a per-target body asks how many there are.
    """
    shots = 2 if (c.first and c.last) else 1
    for _ in range(shots):
        if c.strike():
            c.damage(c.w(1))


@power(
    "p1386",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p1386(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    c.shift(1 + c.wis_mod)


@power(
    "p1510",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p1510(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)


@power(
    "p2209",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_two_melee_or_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p2209(c: Cast) -> None:
    landed = 0
    for _ in range(2):
        if c.strike():
            landed += 1
            c.damage(c.w(1), c.dex_mod)
    if landed == 2:
        c.flat(c.wis_mod)


@power(
    "p843",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    trigger="an enemy makes a melee attack against you",
)
def p843(c: Cast) -> None:
    """The printed line is "make a basic attack", which nothing here can call.

    Written out longhand instead: the same roll and the same damage a ranged
    basic attack would make, with the Wisdom bonus the Special line grants.
    """
    c.shift(1)
    if c.attack(c.dex_ + c.wis_mod, AC):
        c.damage(c.w(1), c.dex_mod)


@power(
    "p851",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p851(c: Cast) -> None:
    for _ in range(2):
        if c.strike():
            c.damage(c.w(2), c.str_mod)
        else:
            c.half_damage(c.w(2), c.str_mod)


@power(
    "p393",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p393(c: Cast) -> None:
    """Off-hand first, then a step, then the main weapon regardless of the miss.

    Both `c.w()` calls roll the main weapon: the off-hand's own dice are not
    reachable, so the opening 1[W] is one die too large for a ranger whose
    hands hold different weapons.
    """
    if c.strike():
        c.damage(c.w(1))
    c.shift(1)
    if c.attack(c.str_, AC):
        c.damage(c.w(2), c.str_mod)
        c.weakened()


@power(
    "p868",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p868(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.slowed(until=When.SAVE_ENDS)
        c.ongoing(5)
    else:
        c.half_damage(c.w(2), c.dex_mod)
        c.slowed()


@power(
    "p2207",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p2207(c: Cast) -> None:
    """Two targets, one arrow each.

    The printed row rolls twice, keeps the better roll and applies that one
    result to both targets, and it wants the two of them within 3 squares of
    each other. Neither the shared roll nor the spacing can be said here, so
    each target is simply attacked on its own.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
