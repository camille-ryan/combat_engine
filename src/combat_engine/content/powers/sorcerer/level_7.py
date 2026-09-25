"""Sorcerer, level 7: encounter attacks.

**"When you leave any creature's space, make the following attack"** is
`c.overrun`, which walks through whoever is in the way and says who that
was. Nothing else reports what a move passed through.

**"If the target is in the origin square of the burst"** reads `c.origin`,
which is where an area power was aimed and is `None` for everything else.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    NO_TARGET,
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
    Target,
    TurnStart,
    When,
    power,
)
from combat_engine.engine.query import squares

from .knives import dagger

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

#: p10321's d6 table, in printed order.
_SIX_TYPES = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
    DamageType.THUNDER,
)

#: p5278 pairs up whoever it hit, and the body runs once per target.
_struck: list[int] = []


@power(
    "p10321",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p10321(c: Cast) -> None:
    """The delayed bolt picks its victim when it lands rather than now --
    "one enemy within 3 squares of you" is measured at the start of the
    sorcerer's next turn, which is where the watch fires."""
    kind = _SIX_TYPES[c.roll("1d6") - 1]
    if not c.strike():
        return
    c.damage("1d10", c.cha_mod, dtype=kind)
    me = c.me

    def arcs(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        pool = sorted(f for f in c.enemies() if c.distance(f) <= 3)
        victim = c.choose(pool, f"{c.ref}: who it strikes") if pool else None
        if victim is not None:
            c.flat(10, dtype=kind, on=victim)

    c.watch(TurnStart, arcs, until=When.EONT, on=me, once=True, label=c.ref)


@power(
    "p12472",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p12472(c: Cast) -> None:
    """The Active Familiar clause -- prone for anyone shoved up against it
    -- is dropped: nothing in the engine is a familiar."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.push(2)


@power(
    "p13429",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13429(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        for d in (AC, FORT, REF, WILL):
            c.penalty(d, 2)


@power(
    "p3016",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p3016(c: Cast) -> None:
    """The whole row is its Effect: there is no target line for the move, and
    the attack is rolled once against each creature walked through.
    `c.overrun` is the only thing that reports who that was."""
    c.no_provoke(until=When.EOT)
    for victim in dict.fromkeys(c.overrun()):
        if c.strike(on=victim):
            c.damage("1d6", c.cha_mod, dtype=DamageType.LIGHTNING, on=victim)


@power(
    "p3165",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=WILL),
)
def p3165(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    pool = sorted(w for w in c.within(3, of=victim, side="any") if w != victim)
    other = c.choose(pool, f"{c.ref}: who it changes places with") if pool else None
    if other is not None:
        c.swap(other, who=victim)


@power(
    "p3176",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=REF),
)
def p3176(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.THUNDER)
        c.temp_hp(c.roll("1d6") + c.str_mod, on=c.me)


@power(
    "p3765",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p3765(c: Cast) -> None:
    """The Dragon Magic clause -- a Fortitude penalty on top -- goes with
    the fork."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.COLD)
        c.prone()


@power(
    "p3767",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p3767(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.THUNDER)
        c.condition(Condition.DEAFENED)


@power(
    "p3768",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=REF),
)
def p3768(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.FORCE)
        c.penalty("attack", 2)


@power(
    "p5278",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=REF),
)
def p5278(c: Cast) -> None:
    """The swap needs the whole list of the hit, so it is tallied per target
    and paid out on the last one. Everyone is moved once: the list is walked
    two at a time."""
    if c.first:
        _struck.clear()
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.LIGHTNING)
        if c.target is not None:
            _struck.append(c.target)
    if not c.last:
        return
    for a, b in zip(_struck[::2], _struck[1::2], strict=False):
        c.swap(b, who=a)


@power(
    "p5855",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p5855(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.THUNDER)
    if c.origin is not None and c.origin in squares(c.world, c.target):
        c.immobilized()
    else:
        c.slowed()


@power(
    "p6807",
    level=7,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=Target("enemy", 2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p6807(c: Cast) -> None:
    """The one place both printed types land: the bolt is lightning and the
    splash is fire, and the target takes each of them."""
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod, dtype=DamageType.LIGHTNING)
    splash = c.str_mod
    for near in c.within(1, of=victim, side="any"):
        c.flat(splash, dtype=DamageType.FIRE, on=near)
