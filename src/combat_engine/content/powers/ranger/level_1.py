"""Ranger, level 1.

Two notes that apply to most of the rows below.

A great many ranger powers print two attack lines at once -- "Strength vs.
AC (melee) or Dexterity vs. AC (ranged)". Those are `MeleeOrRanged`, with
`attack_alt` carrying the second line, and each branch is offered as its
own option: the melee one reaches 1 square, swings what is in hand and
provokes nothing; the ranged one reaches 20, fires the bow and opens an
opportunity window. The damage line reads `c.attack_mod`, which is the
modifier of whichever ability that branch attacks with, rather than naming
Dexterity and quietly being half right.

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
    MeleeOrRanged,
    Ranged,
    UpTo,
    When,
    World,
    power,
)
from combat_engine.engine.events import AttackDeclared
from combat_engine.engine.triggers import Trigger, both, by_melee, targets_me

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_MELEE_AGAINST_YOU = "an enemy makes a melee attack against you"


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


def _has_ranged(world: World, eid: int) -> bool:
    """The ranged half of "two melee weapons or a ranged weapon".

    The printed Requirement is the two branches' requirements joined by
    "or", so checking it whole said yes to both branches when only one was
    true -- a two-blade ranger carrying no bow was offered the ranged
    branch, and an archer holding one blade was offered the melee one.
    """
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


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
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC, plus=2),
    attack_alt=Attack(DEX, vs=AC, plus=2),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p917(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.attack_mod)


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
    reach=MeleeOrRanged(1, 20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p87(c: Cast) -> None:
    """Two attacks, spread over one or two creatures.

    One target and both attacks go into it; two targets and each gets one.
    `c.first and c.last` is how a per-target body asks how many there are.

    The melee branch is main weapon then off-hand, as printed; the ranged
    branch is two shots from the same bow, so `hand` only matters on the
    branch that has two hands in it.
    """
    shots = 2 if (c.first and c.last) else 1
    for swing in range(shots):
        hand = "off" if (swing and c.branch == 0) else "main"
        if c.strike():
            c.damage(c.w(1, hand=hand), c.attack_mod)


@power(
    "p1386",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p1386(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
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
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p2209(c: Cast) -> None:
    """Two swings, and a bonus if both land.

    Main weapon then off-hand in melee, two shots at range -- the printed
    line names the hands only for the branch that uses two.
    """
    landed = 0
    for swing in range(2):
        hand = "off" if (swing and c.branch == 0) else "main"
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand=hand), c.attack_mod)
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
    trigger=_MELEE_AGAINST_YOU,
    on=Trigger(AttackDeclared, when=both(targets_me, by_melee), text=_MELEE_AGAINST_YOU),
)
def p843(c: Cast) -> None:
    """The printed line is "make a basic attack", which nothing here can call.

    Written out longhand instead: the same roll and the same damage a ranged
    basic attack would make, with the Wisdom bonus the Special line grants.

    The printed line shoots *the triggering enemy*, and this does not: the
    body takes whatever `use` aims it at, which with two enemies in reach is
    the wrong one. Left as written -- the fix belongs in the dispatcher,
    which knows the event and hands it over as `c.trigger`.
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
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p868(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
        c.slowed(until=When.SAVE_ENDS)
        c.ongoing(5)
    else:
        c.half_damage(c.w(2), c.attack_mod)
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
