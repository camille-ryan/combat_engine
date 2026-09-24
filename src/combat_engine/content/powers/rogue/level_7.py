"""Rogue, level 7: the encounter attacks.

Two want a light blade at reach 1; the other two want something that throws.
`p1481`'s requirement names "a crossbow, a light thrown weapon, or a sling",
and the engine's weapons carry no thrown flag -- what a thrown one has is a
`ranged` band -- so a light blade counts for it only when it has one. A
plain dagger therefore does not, which is the honest reading of a model
where nothing about that dagger says it leaves the hand.

One row carries a build rider on each leg of the rogue's fork: Strength on
`brawny` and Charisma on `trickster`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBlast,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    World,
    power,
)
from combat_engine.engine.query import hidden_from

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})
MISSILE_GROUPS = frozenset({"crossbow", "sling"})


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


def _rogue_missile(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    if weapon is None:
        return False
    return weapon.group in MISSILE_GROUPS or (
        weapon.is_light_blade and weapon.ranged is not None
    )


@power(
    "p1481",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_missile,
    requires_text="needs a crossbow, a light thrown weapon or a sling",
)
def p1481(c: Cast) -> None:
    """The blast already checks line of effect; "you can see" also rules out
    an enemy hidden from you."""
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p339",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p339(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        amount = c.str_mod if c.build("brawny") else 1
        c.penalty(AC, amount)
        c.penalty(REF, amount)


@power(
    "p977",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p977(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.blinded()


@power(
    "p982",
    level=7,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p982(c: Cast) -> None:
    """The miss line is a second swing at the same creature, not a rider, so
    it is another `c.strike` -- and the Charisma leg of the fork puts its
    bonus on that roll only."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    elif c.strike(plus=c.cha_mod if c.build("trickster") else 0):
        c.damage(c.w(1), c.dex_mod)
