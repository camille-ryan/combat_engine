"""Sorcerer, level 1: the first half of the attack rows.

Three things recur across the whole class and are settled once here.

**The forks are not modelled.** `chargen` derives one build, `standard`, so
a rider printed under Dragon Magic, Wild Magic, Storm Magic, Cosmic Magic or
Chaos Sorcerer has no leg to ask for. Where such a rider is the *whole* of a
row the row is left out and recorded; where it is one clause of a row that
works without it, the rest is written and the dropped clause is named in a
comment. Neither is an approximation: the base line is what the card prints
for everybody.

**One damage type per packet.** `DamageType` carries a single type, so a
line reading "cold and lightning damage" is dealt as the first printed type
and the second rides in the keywords, which is what every level below
settled on.

**A d6 table is rolled, not chosen.** `c.roll("1d6")` indexes a tuple of
types. The Cosmic and Chaos riders that let the sorcerer pick instead of
rolling are exactly the dropped clauses above.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    UpTo,
    When,
    power,
)

from .ground import beside
from .knives import dagger

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

#: The at-will d6 table, in printed order.
_SIX_TYPES = (
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.FORCE,
    DamageType.LIGHTNING,
    DamageType.RADIANT,
    DamageType.THUNDER,
)


@power(
    "p10319",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p10319(c: Cast) -> None:
    """"You can use this power as a ranged basic attack" is a property of the
    creature -- `Powers.basic` -- and not of the row, so there is no header
    field to declare it in. Written down and no more.
    """
    kind = _SIX_TYPES[c.roll("1d6") - 1]
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=kind)
        c.resist(5, kind, on=c.me, until=When.EONT)


@power(
    "p1163",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p1163(c: Cast) -> None:
    """One roll settles both the damage type and the rider, and the Miss
    line uses the same table -- so it is rolled before the attack and read
    twice rather than rolled twice."""
    face = c.roll("1d6")
    kind = (
        DamageType.RADIANT,
        DamageType.FIRE,
        DamageType.POISON,
        DamageType.LIGHTNING,
        DamageType.COLD,
        DamageType.PSYCHIC,
    )[face - 1]
    victim = c.target

    if c.strike():
        c.damage("3d10", c.cha_mod, dtype=kind)
    else:
        c.damage("1d10", dtype=kind)

    if face == 1:
        c.dazed(until=When.SAVE_ENDS)
    elif face == 2:
        for near in c.within(1, of=victim, side="any"):
            if near != victim:
                c.flat(c.dex_mod, dtype=DamageType.FIRE, on=near)
    elif face == 3:
        c.ongoing(5, DamageType.POISON)
    elif face == 4:
        c.slide(c.dex_mod)
    elif face == 5:
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.penalty(AC, 2, until=When.SAVE_ENDS)


@power(
    "p12465",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=FORT),
)
def p12465(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.FIRE)


@power(
    "p12466",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p12466(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.RADIANT)
        c.penalty(AC, 2)


@power(
    "p12467",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT, Keyword.ACID],
    attack=Attack(CHA, vs=REF),
)
def p12467(c: Cast) -> None:
    """The damage type is read off the die that was just rolled, which is
    `AttackResult.natural` -- and it decides the Miss line too, so the roll
    is kept rather than the hit alone.

    The Active Familiar rider -- 5 extra damage next to the familiar -- is
    dropped: nothing in the engine is a familiar.
    """
    shot = c.strike()
    kind = DamageType.ACID if shot.natural % 2 == 0 else DamageType.RADIANT
    if shot:
        c.damage("2d10", c.cha_mod, dtype=kind)
        c.push(c.dex_mod)
    else:
        c.half_damage("2d10", c.cha_mod, dtype=kind)


@power(
    "p13425",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13425(c: Cast) -> None:
    """The riposte is the whole Spell Source clause -- its size *and* its
    damage type both come off the fork -- and the fork is not modelled, so
    it is dropped and the weapon damage stands. "You can use this power in
    place of a melee basic attack" is a property of the creature rather
    than a header field; see p10319.
    """
    if c.strike():
        c.damage(c.w(), c.cha_mod)


@power(
    "p13426",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=AC),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13426(c: Cast) -> None:
    """The Effect line runs whatever the primary did, so the teleport and
    the secondary are outside the branch; only the advantage depends on the
    primary having landed."""
    landed = bool(c.strike())
    if landed:
        c.damage(c.w(), c.cha_mod)

    where = beside(c, c.target)
    if where is not None:
        c.teleport(20, to=where)
    if c.strike(advantage=True if landed else None):
        c.slowed()
        c.weakened()


@power(
    "p3005",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p3005(c: Cast) -> None:
    """The Storm Magic clause -- moving the Storm Power bonus from one
    packet to the other -- is dropped with the fork."""
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod, dtype=DamageType.LIGHTNING)
    pool = sorted(f for f in c.enemies() if f != victim and c.distance(f) <= 10)
    second = c.choose(pool, f"{c.ref}: who the arc jumps to") if pool else None
    if second is not None:
        c.flat(c.dex_mod, dtype=DamageType.LIGHTNING, on=second)


@power(
    "p3009",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=FORT),
)
def p3009(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.cha_mod)
        c.prone()


@power(
    "p3033",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p3033(c: Cast) -> None:
    """What follows the blindness -- "treats each creature more than 5
    squares away as having concealment" -- is not written on either branch:
    concealment is not modelled, and blinding everything further off would
    be a much stronger thing than the card prints."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.blinded()
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)


@power(
    "p3034",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(CHA, vs=FORT),
)
def p3034(c: Cast) -> None:
    """A zone plus a `TurnStart` watch rather than `c.hazard`: the printed
    bite is only for a creature *starting* its turn inside, and a hazard
    also bites on entry.

    "As a move action, you can move the zone 3 squares" is not written --
    `c.zone` takes no speed and nothing offers moving one, the same gap the
    other three zone rows of this class record.
    """
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.THUNDER)
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)
        c.slide(c.dex_mod)

    if not c.first:
        return
    area = c.area()
    if not area:
        return
    wind = c.zone(area, label=c.ref, until=When.EONT)
    bite = c.cha_mod

    def gust(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(wind):
            c.flat(bite, dtype=DamageType.THUNDER, on=ev.actor)

    c.watch(TurnStart, gust, until=When.EONT, on=c.me, label=f"{c.ref} wind")


@power(
    "p3035",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=REF),
)
def p3035(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.COLD)
        c.ongoing(5, DamageType.COLD)
    else:
        c.half_damage("1d10", c.cha_mod, dtype=DamageType.COLD)


@power(
    "p3162",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p3162(c: Cast) -> None:
    """The Wild Magic clause -- a slide instead of the push on an even roll
    -- is dropped with the fork."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.push(1)


@power(
    "p3171",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p3171(c: Cast) -> None:
    """The Dragon Magic clause -- 3 squares instead of 1 against a bloodied
    target -- is dropped with the fork."""
    if c.strike():
        c.damage("1d10", c.cha_mod)
        c.push(1)


@power(
    "p3172",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.FEAR],
    attack=Attack(CHA, vs=FORT),
)
def p3172(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.THUNDER)
        c.penalty("attack", 2)


@power(
    "p3701",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p3701(c: Cast) -> None:
    """The Dragon Magic clause -- a scorch on the next enemy to hit you --
    is dropped with the fork."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.FIRE)


@power(
    "p3705",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p3705(c: Cast) -> None:
    """"Can be used as a ranged basic attack" -- see p10319."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.COLD)
        c.push(1)


@power(
    "p3716",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CHA, vs=REF),
)
def p3716(c: Cast) -> None:
    """"The target can't gain combat advantage against any creature" has no
    shape here -- `c.cannot_be_flanked` closes one route to it and nothing
    denies the advantage itself -- so the clause is not written. The Dragon
    Magic concealment goes with the fork.
    """
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.ACID)
