"""Paladin, level 1 -- and the one class feature that is not already written.

`p805`, `p1566` and `p1747` are the paladin's other features and live in
`content/features/defenders.py`, declared there before this file existed. A
ref may only be declared once, so they are not repeated here.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    DAILY,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Target,
    When,
    power,
)
from combat_engine.engine.events import AttackDeclared

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


def _marked_by_me(c: Cast) -> bool:
    """"If you marked the target" -- by *you*, not by whoever got there first.

    `c.is_(Condition.MARKED)` answers a different question: it is true of a
    creature the fighter next to you marked, and these powers pay out on your
    own mark only.
    """
    if c.target is None:
        return False
    return c.world.relations.holds(Relation.MARKED_BY, c.me, c.target)


# -- at-will ----------------------------------------------------------------


@power(
    "p1567",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p1567(c: Cast) -> None:
    if c.strike():
        bonus = c.str_mod + (c.wis_mod if _marked_by_me(c) else 0)
        c.damage(c.w(1), bonus, dtype=DamageType.RADIANT)


@power(
    "p833",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p833(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.cha_mod)
        c.temp_hp(c.wis_mod, on=c.me)


@power(
    "p835",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p835(c: Cast) -> None:
    """The more of them there are, the better this swings.

    The header's attack line is the printed one, for the card and for a
    policy to read; the body rolls its own, because the bonus is a count of
    the board and the header is data.
    """
    if c.attack(c.str_ + len(c.within(1, side="enemy")), AC):
        c.damage(c.w(1), c.str_mod)


@power(
    "p836",
    level=1,
    cls="paladin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p836(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.cha_mod)
        if _marked_by_me(c):
            c.penalty("attack", 2)


# -- encounter --------------------------------------------------------------


@power(
    "p218",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p218(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.mark()
        others = [e for e in c.within(1, side="enemy") if e != c.target]
        for _ in range(max(0, c.wis_mod)):
            if not others:
                break
            who = c.choose(others, "who else do you mark")
            others.remove(who)
            c.mark(on=who)


@power(
    "p358",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p358(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod + c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p684",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(CHA, vs=AC),
)
def p684(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        c.penalty("attack", c.wis_mod)


@power(
    "p755",
    level=1,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p755(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
    if c.first:
        # The Effect line lands whether the swing did or not.
        friends = [a for a in c.within(5, side="ally") if a != c.me]
        if friends:
            c.bonus(AC, c.wis_mod, on=c.choose(friends, "who gets the warding"))


# -- daily ------------------------------------------------------------------


@power(
    "p2258",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p2258(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    # Hit or miss, somebody nearby gets to spend a surge.
    friends = [a for a in c.within(5, side="ally") if a != c.me]
    hurt = [a for a in friends if c.wounded(a)]
    if hurt or friends:
        c.surge(on=c.choose(hurt or friends, "who spends a healing surge"))


@power(
    "p1268",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(CHA, vs=WILL),
)
def p1268(c: Cast) -> None:
    """Attacking costs it, once a round, until it shakes this off.

    Hit and miss leave the same arrangement behind at different sizes, so the
    watcher is written once and the die is the only difference.
    """
    hit = c.strike()
    if hit:
        c.damage("3d8", c.cha_mod)
    else:
        c.half_damage("3d8", c.cha_mod)

    victim, die = c.target, "1d8" if hit else "1d4"
    struck: dict[int, int] = {}

    def recoil(ev: AttackDeclared) -> None:
        if ev.attacker != victim or c.world.turn != victim:
            return  # its own attacks, on its own turn
        if struck.get(victim) == c.world.round:
            return  # once per round, and no more
        struck[victim] = c.world.round
        c.flat(c.world.rng.roll(die).total, on=victim)

    c.watch(AttackDeclared, recoil, until=When.SAVE_ENDS, label=f"{c.ref} recoil")


@power(
    "p1273",
    level=1,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p1273(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.penalty(AC, 2, until=When.SAVE_ENDS)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.RADIANT)
    c.dazed()  # both lines daze, so it sits outside the branch


# -- class feature ----------------------------------------------------------


@power(
    "p1746",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    # "One creature in the burst", and it means it: this is spent on a
    # friend nine times in ten. `ONE_CREATURE` is the *enemy* pool, which
    # would make the power unusable for the only thing it is ever for.
    target=Target("any", 1),
    keywords=[Keyword.DIVINE],
)
def p1746(c: Cast) -> None:
    """A saving throw, out of turn, with the paladin's presence behind it.

    The bonus is granted as a modifier and then the save is rolled, because
    a save is the one roll the caster cannot ask for directly.
    """
    saves = [e for e in c.world.effects.of(c.target) if e.when is When.SAVE_ENDS]
    if not saves:
        c.note("nothing to save against")
        return
    c.bonus("save", c.cha_mod, until=When.SOTNT)
    c.world.effects.save(c.choose(saves, "which effect do you shake off"))
