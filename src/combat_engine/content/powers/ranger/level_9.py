"""Ranger, level 9: the daily attacks.

`p459` prints "Ranged 1" and then says the attack does not provoke, which is
the header's `no_provoke` rather than anything the body does. Its ranged
reach on a row carrying `Keyword.WEAPON` is already a bow in hand, so no
Requirement of its own is declared.

`p384` prints its move inside the attack line -- "at any point during your
move" -- and a body starts after the power is aimed, so the walk is taken
first and the two swings follow it. The printed freedom to shoot halfway
through is the one clause that does not survive.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    EACH_ENEMY,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Gear,
    Keyword,
    MeleeOrRanged,
    Ranged,
    UpTo,
    World,
    power,
)
from combat_engine.engine.query import hidden_from

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


@power(
    "p160",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p160(c: Cast) -> None:
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p384",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p384(c: Cast) -> None:
    """Two swings over one or two creatures, both 3[W]: one target takes
    both, two take one each. `c.attack_mod` is what keeps the damage line on
    the branch actually being used -- Strength in reach, Dexterity at range.
    """
    if c.first:
        c.move(c.speed_of(c.me))
    shots = 2 if (c.first and c.last) else 1
    for _ in range(shots):
        if c.strike():
            c.damage(c.w(3), c.attack_mod)
        else:
            c.half_damage(c.w(3), c.attack_mod)


@power(
    "p459",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    no_provoke=True,
)
def p459(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(4), c.dex_mod)
    else:
        c.half_damage(c.w(4), c.dex_mod)


@power(
    "p714",
    level=9,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p714(c: Cast) -> None:
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
