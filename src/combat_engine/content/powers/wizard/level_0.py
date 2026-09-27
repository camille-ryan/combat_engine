"""Wizard, level 0: the cantrips, the swordmage-ish features, and the
bladespells.

None of the four cantrips has a battlefield effect. They light a room, make
a noise, fetch a thing off a shelf, or produce a small harmless illusion --
the last of which says outright that it cannot deal damage, serve as a
weapon, or hinder a creature. So they carry `out_of_combat=True` rather than
an invented mechanic, and the body is a note: the effect is the fiction. The
three rows that swap one skill check for another, and the two that are pure
fiction, are written the same way.

The bladespells are "No Action" rows off a printed Trigger, which the
dispatcher answers in the reaction window. Their printed Special -- one
bladespell per triggering attack -- is not modelled: nothing counts uses
across a group within a single attack.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MELEE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Cast,
    DamageType,
    Defences,
    Gear,
    Hit,
    Keyword,
    MoveEnd,
    Ranged,
    Trigger,
    When,
    World,
    power,
)

ARCANE = [Keyword.ARCANE]


def _sword_hand(world: World, eid: int) -> bool:
    """A one-handed melee weapon, and nothing in the other hand."""
    gear = world.get(eid, Gear)
    if gear is None or gear.shield or gear.two_weapon:
        return False
    weapon = gear.main
    return (
        weapon is not None
        and not weapon.ranged
        and not weapon.two_handed
        and len(gear.held) == 1
    )


def _bladespell(world: World, me: int, ev: Hit) -> bool:
    return (
        ev.attacker == me
        and ev.power == MELEE
        and world.turn == me
        and _sword_hand(world, me)
    )


BLADESPELL = Trigger(
    Hit, _bladespell, "you hit an enemy with a one-handed melee basic attack"
)


@power(
    "p1217",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=ARCANE,
    out_of_combat=True,
)
def p1217(c: Cast) -> None:
    c.note("p1217: a sound, from a whisper to a shout, from a chosen square")


@power(
    "p1225",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=ARCANE,
    out_of_combat=True,
)
def p1225(c: Cast) -> None:
    c.note("p1225: bright light out to 4 squares, until the encounter ends")


@power(
    "p1227",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
    out_of_combat=True,
)
def p1227(c: Cast) -> None:
    c.note("p1227: a floating hand that carries one object of 20 pounds or less")


@power(
    "p1930",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(2),
    target=NO_TARGET,
    keywords=ARCANE,
    out_of_combat=True,
)
def p1930(c: Cast) -> None:
    c.note("p1930: one small harmless effect, three at a time")


# -- the checks one skill makes for another ----------------------------------


@power(
    "p12731",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p12731(c: Cast) -> None:
    c.note("p12731: an Arcana check settles a Diplomacy check instead")


@power(
    "p13971",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.SHADOW],
    out_of_combat=True,
)
def p13971(c: Cast) -> None:
    c.note("p13971: an Arcana check settles an Intimidate check instead")


@power(
    "p15851",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
    out_of_combat=True,
)
def p15851(c: Cast) -> None:
    c.note("p15851: an Arcana check settles a Stealth check instead")


@power(
    "p15850",
    level=0,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p15850(c: Cast) -> None:
    c.note("p15850: used during an extended rest -- a hint about a course of action")


@power(
    "p16272",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p16272(c: Cast) -> None:
    """Liquid is not a kind of square the grid has, so there is nothing to
    walk on: this is terrain the board does not model rather than an effect
    on the caster."""
    c.note("p16272: liquid surfaces hold you up, as difficult terrain, until EONT")


@power(
    "p16273",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    out_of_combat=True,
)
def p16273(c: Cast) -> None:
    c.note("p16273: a breeze carries 25 words or 6 seconds of sound to a known place")


# -- the two that touch a fight ---------------------------------------------


@power(
    "p13970",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.SHADOW],
)
def p13970(c: Cast) -> None:
    """"Reduced by 5, if any" -- so a creature with no necrotic resistance
    takes nothing from this, and never comes out vulnerable. `c.resist` with
    a negative amount is the only way to say a reduction, and its undo puts
    the original back when the turn ends."""
    foe = c.target
    if foe is None or not c.is_kind("undead"):
        return
    standing = c.world.get(foe, Defences)
    have = standing.resist.get(DamageType.NECROTIC, 0) if standing else 0
    if have > 0:
        c.resist(-min(5, have), DamageType.NECROTIC, on=foe, until=When.EOT)


@power(
    "p14285",
    level=0,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    requires=_sword_hand,
    requires_text="one-handed melee weapon, other hand empty",
)
def p14285(c: Cast) -> None:
    """"The effect ends if you stop fulfilling the requirement" is not
    written: a modifier cannot watch what is in a hand, and nothing puts a
    weapon down mid-fight."""
    c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power")
    c.bonus("damage", 5, on=c.me, until=When.EONT, kind="power")
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT, kind="power")


# -- the bladespells ---------------------------------------------------------


@power(
    "p14286",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE],
    trigger="you hit an enemy with a one-handed melee basic attack on your turn",
    on=BLADESPELL,
)
def p14286(c: Cast) -> None:
    c.damage(0, c.dex_mod, dtype=DamageType.FIRE)
    c.grants_advantage(until=When.EONT, to="team")


@power(
    "p14287",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.RADIANT],
    trigger="you hit an enemy with a one-handed melee basic attack on your turn",
    on=BLADESPELL,
)
def p14287(c: Cast) -> None:
    c.damage(0, c.dex_mod, dtype=DamageType.RADIANT)
    c.penalty("attack", 2, until=When.EONT)


@power(
    "p14288",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD],
    trigger="you hit an enemy with a one-handed melee basic attack on your turn",
    on=BLADESPELL,
)
def p14288(c: Cast) -> None:
    c.damage(0, c.dex_mod, dtype=DamageType.COLD)
    c.slowed(until=When.EOTNT)


@power(
    "p14289",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.LIGHTNING],
    trigger="you hit an enemy with a one-handed melee basic attack on your turn",
    on=BLADESPELL,
)
def p14289(c: Cast) -> None:
    """The second jolt is the same number again, so it is the amount dealt
    that is remembered rather than the modifier. `MoveEnd` is the right end
    here: the creature has to have moved for the sentence to be true."""
    foe = c.target
    if foe is None:
        return
    amount = c.damage(0, c.dex_mod, dtype=DamageType.LIGHTNING)

    def again(ev: MoveEnd) -> None:
        if ev.actor == foe:
            c.flat(amount, dtype=DamageType.LIGHTNING, on=foe)

    c.watch(MoveEnd, again, until=When.EONT, once=True)


@power(
    "p14290",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.NECROTIC],
    trigger="you hit an enemy with a one-handed melee basic attack on your turn",
    on=BLADESPELL,
)
def p14290(c: Cast) -> None:
    c.damage(0, c.dex_mod, dtype=DamageType.NECROTIC)
    struck = getattr(c.trigger, "target", None)
    if struck is not None and c.size_of().squares <= c.size_of(on=struck).squares:
        c.prone()


@power(
    "p14291",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE],
    trigger="you hit an enemy with a one-handed melee basic attack on your turn",
    on=BLADESPELL,
)
def p14291(c: Cast) -> None:
    c.damage(0, c.dex_mod, dtype=DamageType.FORCE)
    c.slide(3)
