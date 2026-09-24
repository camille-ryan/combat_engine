"""Rogue, level 3: the encounter attack powers.

Three of the four want a light blade and reach one square. The fourth
prints "Melee or Ranged weapon" over the rogue's own three weapon groups and
is `MeleeOrRanged`; Dexterity attacks on either branch, so there is no
second attack line, and what differs is the range, the weapon rolled and
whether firing provokes.

One row carries a build rider. The two legs of the rogue's fork are named
`brawny` and `trickster` here, and the Charisma one is the leg that rider
belongs to, so `c.build("trickster")` is what asks for it.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    When,
    World,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


@power(
    "p1387",
    level=3,
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
def p1387(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.grants_advantage()


@power(
    "p1480",
    level=3,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=WILL),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1480(c: Cast) -> None:
    """The trade of places is the printed slide-and-shift in one move.

    `c.swap` moves both at once, which is the same end state and cannot
    leave the two of them stacked. The second shift is the free one, and the
    Charisma leg of the fork lengthens it.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        victim = c.target
        if victim is not None:
            c.swap(victim)
        c.shift(c.cha_mod if c.build("trickster") else 1)


@power(
    "p209",
    level=3,
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
def p209(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.prone()


@power(
    "p550",
    level=3,
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
def p550(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.bonus(AC, c.cha_mod, on=c.me, until=When.SONT)
