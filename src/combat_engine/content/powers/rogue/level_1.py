"""Rogue, level 1.

One note applies to several rows. A good half of the rogue's list prints
"Melee or Ranged weapon" over a Requirement of "a crossbow, a light blade,
or a sling", and those are declared `MeleeOrRanged` -- both branches, each
offered as its own option. Dexterity attacks either way, so unlike the
ranger these rows need no second attack line; what differs is the range,
the weapon rolled, and whether firing provokes.

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
    Condition,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
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


#: The four holds `f1300`'s clause on `p704` names together. Written here
#: rather than imported from the feat's own file: under #550 the clause
#: lives in `p704`'s body, so the data it reads lives beside it. The same
#: four are still listed in `feats/general_h.py` for the row's three
#: un-migrated powers, and the duplication is the price of migrating one
#: power at a time -- it goes when `f1300`'s last power moves.
_HELD_FAST = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


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
    """Four feats print a clause on this row, and they are two kinds.

    #550's convention: a feat naming one power has its clause written
    here, gated on `c.feat()`, rather than registering a rider from its
    own body. The feat rows stay declared.

    **`f972` and `f1300` are exclusive to each other.** Both are of the
    printed category a character may apply only one of to a single use of
    a power -- Camille's ruling -- so they are one `if`/`elif` chain and
    not two tests. The engine cannot check this for itself: a feat's
    category is part of its printed name, and names are not in tracked
    files, so the chain is written by hand from the two names in a
    brief's glossary. **Do not split it back into two `if`s.**

    Each branch carries its own applicability, which is the ordering that
    matters: `f972` pays on a critical hit only and `f1300` only against
    a held target, so a character holding both gets whichever can
    actually do something. When *both* apply the first wins, which is
    arbitrary -- the card gives the choice to the player. #554.

    **`f3188` and `f3234` are not of that category and stack**, with each
    other and with whichever of the two above paid out. Their own
    standing bonuses stay in their own bodies; only the clause that rides
    this row's hit is here.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.dex_mod)

    if c.feat("f972") and c.crit:
        c.penalty(AC, 2, on=c.target, until=When.EONT)
    elif (c.feat("f1300") and c.con_mod > 0
            and any(c.is_(hold, on=c.target) for hold in _HELD_FAST)):
        c.flat(c.con_mod, on=c.target)

    if c.feat("f3188"):
        c.ignores_difficult(on=c.me, until=When.EOT)
        c.shift(2 if c.race_of(on=c.me) == "r4" else 1)
    if c.feat("f3234"):
        c.push(1, on=c.target)


@power(
    "p970",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
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
        # `as_="riposte"` so the counter can be told from the opening blow:
        # both carry this row's `power`, and two feats print a clause about
        # the counter alone.
        if c.attack(c.str_, AC, on=victim, as_="riposte"):
            c.damage(c.w(1), c.str_mod, on=victim)

    c.on_attack(riposte, by=victim, until=When.SONT, label=f"{c.ref} riposte")


@power(
    "p971",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
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
    reach=MeleeOrRanged(1, 20, by_weapon=True),
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
    reach=MeleeOrRanged(1, 20, by_weapon=True),
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
    reach=MeleeOrRanged(1, 20, by_weapon=True),
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
