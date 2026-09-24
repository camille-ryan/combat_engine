"""Ranger, level 7: the encounter attacks.

Two of the four are the two-attack shape the level 1 file sets out, and both
print *different* dice for the two swings -- 2[W] then 1[W] -- so the hand
and the multiplier travel together rather than the loop rolling the same
line twice. One target takes both; two targets take one each, the first the
heavier.

`p920` prints "Ranged weapon" as its whole range line, which is a bow in
hand, so it is declared with a requirement of one: a two-blade ranger owns
none and would otherwise be offered the row and roll a short sword at twenty
squares.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
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
    World,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _two_swings(c: Cast, *, hands: bool) -> None:
    """2[W] then 1[W], spread over one or two creatures.

    `hands` is whether the second blow comes from the off-hand -- true for
    the pair of blades, false for two shots from the same bow.
    """
    heavy = (2, "main")
    light = (1, "off" if hands else "main")
    alone = c.first and c.last
    swings = [heavy, light] if alone else [heavy] if c.first else [light]
    for dice, hand in swings:
        if c.strike():
            c.damage(c.w(dice, hand=hand), c.attack_mod)


@power(
    "p1418",
    level=7,
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
def p1418(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.push(max(0, c.wis_mod))
        c.prone()


@power(
    "p1419",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p1419(c: Cast) -> None:
    """"Ignore any penalties from cover or concealment (but not superior
    cover or total concealment)" -- the engine's cover penalty is the whole
    of what `ignore_cover` drops, and superior cover is not modelled apart
    from it, so the parenthesis has nothing left to exclude.
    """
    if c.strike(plus=c.wis_mod, ignore_cover=True):
        c.damage(c.w(2), c.attack_mod)


@power(
    "p848",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p848(c: Cast) -> None:
    _two_swings(c, hands=True)


@power(
    "p920",
    level=7,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p920(c: Cast) -> None:
    """No `requires_text`, deliberately: `chargen.build_for` picks the build
    that can hold a row by looking for the word "requirement" in the refusal,
    and a custom message hides it -- so spelling this one out handed the row
    to the two-blade ranger, who owns no bow."""
    _two_swings(c, hands=False)
