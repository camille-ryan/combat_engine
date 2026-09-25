"""Sorcerer, level 3: encounter attacks.

Nothing new in shape. Two notes that apply to the whole level:

**"Cold and lightning damage"** is dealt as the first printed type and the
second rides in the keywords -- one packet carries one `DamageType`.

**Fork riders** (Dragon Magic, Wild Magic, Storm Magic, Chaos Sorcerer) are
dropped, each named where it falls; see `level_1.py` for why.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    UpTo,
    When,
    distance,
    power,
    spread,
)

from .ground import ringing
from .knives import dagger

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p10320",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=FORT),
)
def p10320(c: Cast) -> None:
    """"It must be teleported that many squares away from its original
    location" is a distance the destination has to hit exactly, so the
    square is named rather than left to `c.teleport`'s own offer -- which
    takes anything within the range.

    The Chaos Sorcerer clause -- choosing d4, d6 or d8 -- goes with the fork.
    """
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod)

    far = c.roll("1d6")
    was = c.there
    room = sorted(
        sq
        for sq in spread({was}, far)
        if distance(sq, was) == far
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) in (None, victim)
    )
    where = c.choose(room, f"{c.ref}: where it comes out") if room else None
    if where is not None:
        c.teleport(far, who=victim, to=where)

    for near in c.within(1, of=victim, side="any"):
        if near != victim:
            c.flat(5, dtype=DamageType.THUNDER, on=near)


@power(
    "p12469",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p12469(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
        c.slowed()


@power(
    "p13427",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13427(c: Cast) -> None:
    """No ability modifier on the damage line, which is what the card
    prints for a minor action."""
    if c.strike():
        c.damage(c.w(2), dtype=DamageType.LIGHTNING)


@power(
    "p16511",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p16511(c: Cast) -> None:
    """No ability modifier on the damage line, as printed."""
    if c.strike():
        c.damage("2d10", dtype=DamageType.COLD)
        c.push(1)
        c.prone()


@power(
    "p3010",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CHA, vs=FORT),
)
def p3010(c: Cast) -> None:
    """The second bite is hung off the target's own next turn start rather
    than dealt now. The Dragon Magic splash goes with the fork."""
    victim = c.target
    if not c.strike():
        return
    c.damage("2d10", c.cha_mod, dtype=DamageType.ACID)
    bite = c.str_mod

    def later(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == victim:
            c.flat(bite, dtype=DamageType.ACID, on=victim)

    c.watch(TurnStart, later, until=When.EOTNT, on=victim, once=True, label=c.ref)


@power(
    "p3012",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p3012(c: Cast) -> None:
    """The Storm Magic clause -- a flight bought by declining every slide --
    goes with the fork."""
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.THUNDER)
        c.slide(c.dex_mod)


@power(
    "p3013",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.THUNDER],
    attack=Attack(CHA, vs=REF),
)
def p3013(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.COLD)


@power(
    "p3163",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=REF),
)
def p3163(c: Cast) -> None:
    """The Wild Magic clause -- stripping resistances on an even roll --
    goes with the fork."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.FORCE)


@power(
    "p3174",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p3174(c: Cast) -> None:
    """The concealment is not written -- concealment is not modelled, and
    hiding outright is a stronger thing than the card prints."""
    if c.strike():
        c.damage("2d6", c.cha_mod)


@power(
    "p3749",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p3749(c: Cast) -> None:
    """The ring is laid around the sorcerer and stays where it was laid:
    `c.hazard` makes a zone, and a zone does not follow anybody."""
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.FIRE)
    if not c.first:
        return
    ring = ringing(c, c.me)
    if ring:
        c.hazard(
            ring, "1d6", DamageType.FIRE,
            label=c.ref, until=When.SONT, sustain=None,
        )


@power(
    "p3753",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=REF),
)
def p3753(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.COLD)
        c.slowed()


@power(
    "p5269",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(CHA, vs=REF),
)
def p5269(c: Cast) -> None:
    """Two packets of two types, which is the one case where both printed
    types are actually dealt."""
    victim = c.target
    if not c.strike():
        return
    c.damage("2d10", c.cha_mod, dtype=DamageType.LIGHTNING)
    for near in c.within(1, of=victim, side="any"):
        if near != victim:
            c.flat(c.cha_mod, dtype=DamageType.THUNDER, on=near)


@power(
    "p5270",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p5270(c: Cast) -> None:
    """The Dragon Magic clause -- a bigger penalty off Strength -- goes with
    the fork, so the printed -2 stands."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.POISON)
        c.penalty(FORT, 2)


@power(
    "p5271",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=FORT),
)
def p5271(c: Cast) -> None:
    """The Wild Magic slide goes with the fork."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.FORCE)
        c.immobilized()
