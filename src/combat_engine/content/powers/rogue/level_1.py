"""Rogue, level 1.

One note applies to several rows. A good half of the rogue's list prints
"Melee or Ranged weapon" over a Requirement of "a crossbow, a light blade,
or a sling", and the header holds one range. Every such row here is written
as its **melee** branch -- `Melee(1)`, the light blade's dice -- which is
what the class's gear in `chargen.py` has in hand. The attack line is
Dexterity either way, so only the range is lost.

Two rows carry a build rider (a bonus for one of the rogue's two tactics).
Nothing in the model records which build a rogue took, so those rows are the
base line only.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    When,
    World,
    power,
)
from combat_engine.engine.events import AttackDeclared, Hit

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    """"A crossbow, a light blade, or a sling" -- the rogue's own three."""
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


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


@power(
    "p653",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p653(c: Cast) -> None:
    """The riposte is armed whether or not the opening attack lands.

    It is not a basic attack -- the printed line names Strength vs. AC
    outright -- so it is rolled longhand. The latch is kept here rather than
    with `once=True`, which would burn the trigger on an attack aimed at
    somebody else.
    """
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    victim = c.target
    if victim is None:
        return
    spent: list[bool] = []

    def riposte(ev: AttackDeclared) -> None:
        if spent or ev.target != c.me or not c.adjacent(victim):
            return
        spent.append(True)
        if c.attack(c.str_, AC, on=victim):
            c.damage(c.w(1), c.str_mod, on=victim)

    c.on_attack(riposte, by=victim, until=When.SONT, label=f"{c.ref} riposte")


@power(
    "p971",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p971(c: Cast) -> None:
    """The walk is an Effect line, so it happens once and before the roll."""
    if c.first:
        c.move(2)
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p1385",
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
def p1385(c: Cast) -> None:
    # One build adds Strength to the damage roll; no build to read.
    if c.strike():
        c.damage(c.w(2), c.dex_mod)


@power(
    "p1482",
    level=1,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=REF),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p1482(c: Cast) -> None:
    """The trade of places is an Effect line: a miss still gets it.

    `c.swap` moves both at once, which is the same end state as the printed
    "the ally slides 1 and you shift 1" and cannot end with the two of them
    stacked.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    if c.first:
        beside_me = [a for a in c.within(1, side="ally") if a != c.me]
        if beside_me:
            partner = c.choose(beside_me, "who you trade places with")
            if partner is not None:
                c.swap(partner)


@power(
    "p1483",
    level=1,
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
def p1483(c: Cast) -> None:
    # One build lengthens the slide to Charisma; no build to read.
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.slide(1)


@power(
    "p1422",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p1422(c: Cast) -> None:
    """"Save ends both" becomes two save-ends effects.

    They are saved against separately here, where the printed row clears both
    on one roll -- the nearest the duration model gets.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.slowed(until=When.SAVE_ENDS)
        c.grants_advantage(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.dex_mod)
        c.grants_advantage()


@power(
    "p1495",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p1495(c: Cast) -> None:
    """The standing arrangement is an Effect line, so a miss leaves it behind.

    Armed after the opening attack, which is why that hit does not pay twice.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.slide(1)
    if victim is None:
        return

    def nudge(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.slide(1, on=victim)

    c.watch(Hit, nudge, until=When.ENCOUNTER, label=f"{c.ref} nudge")
