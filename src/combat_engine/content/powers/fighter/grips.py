"""The four printed Requirement lines the later books hang on the fighter.

Every one of them is a question about what is in the fighter's hands, and
between Martial Power and Heroes of the Fallen Lands about forty rows ask
one. Written once here rather than four times per level file.

`hand_free` is the judgement call. `Gear` has no count of hands: it has a
list of weapons and a shield flag, and `Gear.two_weapon` already treats the
shield as occupying the off hand. So a hand is free when nothing is in it --
no shield, no second weapon, and not a two-hander needing both.
"""

from __future__ import annotations

from combat_engine.engine import Cast, Gear, World


def has_shield(world: World, eid: int) -> bool:
    """"Requirement: You must be using a shield"."""
    gear = world.get(eid, Gear)
    return gear is not None and gear.shield


def two_melee(world: World, eid: int) -> bool:
    """"Requirement: You must be wielding two melee weapons"."""
    gear = world.get(eid, Gear)
    return gear is not None and gear.two_weapon


def two_handed(world: World, eid: int) -> bool:
    """"Requirement: You must be wielding a two-handed weapon"."""
    gear = world.get(eid, Gear)
    return gear is not None and gear.main is not None and gear.main.two_handed


def hand_free(world: World, eid: int) -> bool:
    """"Requirement: You must have a hand free"."""
    gear = world.get(eid, Gear)
    if gear is None:
        return True
    if gear.shield or len(gear.melee) > 1:
        return False
    return gear.main is None or not gear.main.two_handed


def light_blade(world: World, eid: int) -> bool:
    """"Requirement: You must be wielding a light blade"."""
    gear = world.get(eid, Gear)
    return gear is not None and gear.main is not None and gear.main.is_light_blade


def reach_weapon(world: World, eid: int) -> bool:
    """"Requirement: You must be wielding a reach weapon"."""
    gear = world.get(eid, Gear)
    return gear is not None and gear.main is not None and "reach" in gear.main.properties


#: The three weapon groups the later fighter rows keep naming together.
HEAVY = ("axe", "hammer", "mace")


def heavy_rider(c: Cast) -> int:
    """"If you're wielding an axe, a hammer, or a mace, ... your Constitution
    modifier." One weapon is in hand, so the three are one question."""
    return c.con_mod if any(c.wielding(group) for group in HEAVY) else 0
