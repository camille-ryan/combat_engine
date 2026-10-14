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
    """Four feats print a clause on this row: three of one kind, one of none.

    #550's convention: a feat naming one power has its clause written
    here, gated on `c.feat()`, rather than registering a rider from its
    own body. The feat rows stay declared.

    **The grouping comes from the compendium's bracket, and the first
    version of this docstring got it wrong.** A feat's category is printed
    in brackets after its name -- `[Arena Fighting]`, `[Lesser Style]`,
    `[Greater Style]`, or nothing -- and Camille's rule is **one Arena
    Fighting feat, one Lesser Style feat, and any number of unbracketed
    ones** per use of a power.

    So `f972`, `f3188` and `f3234` are **all** Arena Fighting and are one
    chain. The first version paired `f972` with `f1300` and left the other
    two as plain `if`s, which was wrong in both directions at once: it
    denied a clause the character is entitled to and allowed two it is
    not. I had inferred the families from the books rather than reading
    the bracket.

    `f1300` carries no bracket, so it stacks with whichever arena feat
    paid -- a plain `if`, outside the chain.

    **`c.declare` is called before `c.strike()`, and that is the printed
    rule**: "you must declare which of each type you are using before
    making the attack". So a character holding `f972` and `f3188` who
    declares `f972` and then does not crit gets **nothing** -- the
    declaration is not revisited once the die is read.

    The first version of this body put the applicability in each branch
    and fell through, so that character got the shift instead. More
    generous than the card, and `#554` was open about it until the verb
    landed. Do not move these tests back onto `c.feat`: that asks "is it
    held", which is true of every feat the character owns and cannot say
    which one is being applied.
    """
    arena = c.declare("Arena Fighting", "f972", "f3188", "f3234")
    if not c.strike():
        return
    c.damage(c.w(1), c.dex_mod)

    if arena == "f972" and c.crit:
        c.penalty(AC, 2, on=c.target, until=When.EONT)
    elif arena == "f3188":
        c.ignores_difficult(on=c.me, until=When.EOT)
        c.shift(2 if c.race_of(on=c.me) == "r4" else 1)
    elif arena == "f3234":
        c.push(1, on=c.target)

    # f1300 carries no bracket, so any number of its kind apply: a plain
    # `c.feat` outside the declaration, stacking with whichever arena feat
    # paid.
    if (c.feat("f1300") and c.con_mod > 0
            and any(c.is_(hold, on=c.target) for hold in _HELD_FAST)):
        c.flat(c.con_mod, on=c.target)


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
