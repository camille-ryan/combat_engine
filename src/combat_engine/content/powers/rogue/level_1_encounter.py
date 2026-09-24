"""Rogue, level 1: the powers that are not at-will."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    CloseBlast,
    Gear,
    Keyword,
    Melee,
    When,
    World,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


@power(
    "p1382",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1382(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.dazed()


@power(
    "p163",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a crossbow, a light thrown weapon or a sling",
)
def p163(c: Cast) -> None:
    # Damage either way; only a hit blinds.
    if c.strike():
        c.flat(c.dex_mod)
        c.blinded(until=When.EONT)
    else:
        c.flat(c.dex_mod)
