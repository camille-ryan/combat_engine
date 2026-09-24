"""Rogue, level 1."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DEX,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    World,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


@power(
    "p704",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p704(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p970",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p970(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod + c.cha_mod)
