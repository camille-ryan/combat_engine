"""Avenger, level 9: daily attacks, first half.

Eleven of the twenty-three are the same swing under a different rider, and
each carries a Prerequisite naming a class feature the engine does not
model. A Prerequisite is not a build rider: the row is an ordinary power
with an entry requirement, so it is written ungated and the requirement is
simply not expressed. Those eleven are here; the rest are in `level_9_b.py`.

`_swing` is the shared attack line. `_oath_rider` is the shared sentence:
"until the end of the encounter, whenever you hit your oath of enmity
target with an avenger encounter attack power". Who is sworn is asked when
the blow lands rather than closed over -- half a dozen rows in this class
re-swear mid-fight -- and the hitting row's usage is read off the registry
with `get(ev.power)`, which is the only place a power's usage lives.

The four riders that print "deals 3 extra <type> damage" are paid as a
separate typed packet rather than as a `damage` modifier: a modifier adds a
number to whatever packet is already being rolled and cannot carry a type
of its own, so the type -- which is the whole of what those four rows are
for -- would be lost.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Ranged,
    Usage,
    When,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.query import squares as squares_of

from .oath import sworn

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
_DEFENCES = (AC, FORT, REF, WILL)


def beside(c: Cast, who: int) -> list[tuple[int, int]]:
    """Every empty square adjacent to a creature."""
    theirs = squares_of(c.world, who)
    return sorted(
        sq
        for sq in spread(theirs, 1) - theirs
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    )


def nearest(c: Cast, spots: list[tuple[int, int]]) -> tuple[int, int]:
    return min(spots, key=lambda sq: (distance(c.here, sq), sq))


def _swing(c: Cast) -> None:
    """The attack all eleven share, pull and miss line included."""
    victim = c.target
    if not c.strike():
        c.half_damage("2d12", c.wis_mod)
        return
    c.damage("2d12", c.wis_mod)
    if victim is None:
        return
    spots = beside(c, c.me)
    if spots:
        c.pull(4, on=victim, to=nearest(c, spots))
    else:
        c.pull(4, on=victim)


def _oath_rider(c: Cast, fn: Any) -> None:
    """"Whenever you hit your oath of enmity target with an avenger encounter
    attack power", for the rest of the fight."""
    me = c.me

    def landed(ev: Hit) -> None:
        if ev.attacker != me or not sworn(c.world, me, ev.target):
            return
        row = get(ev.power)
        if row is None or row.cls != "avenger" or row.usage is not Usage.ENCOUNTER:
            return
        fn(ev)

    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} oath")


def _extra(c: Cast, dtype: DamageType) -> None:
    """"Your avenger encounter attack powers deal 3 extra <type> damage
    against your oath of enmity target"."""
    _oath_rider(c, lambda ev: c.flat(3, dtype=dtype, on=ev.target))


@power(
    "p11682",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11682(c: Cast) -> None:
    _swing(c)
    if c.first:
        c.bonus("speed", 3, until=When.ENCOUNTER, on=c.me)


@power(
    "p11685",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11685(c: Cast) -> None:
    def shield(ev: Hit) -> None:
        for friend in sorted(a for a in c.allies() if c.can_see(a)):
            for defence in _DEFENCES:
                c.bonus(defence, 1, until=When.SONT, on=friend)

    _swing(c)
    _oath_rider(c, shield)


@power(
    "p11688",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=REF),
)
def p11688(c: Cast) -> None:
    def step(ev: Hit) -> None:
        if c.may("teleport 3 squares", who=c.me):
            c.teleport(3)

    _swing(c)
    _oath_rider(c, step)


@power(
    "p11691",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11691(c: Cast) -> None:
    """"Against your target" is gated on the attack context's `target`, so
    the ally keeps the bonus only while swinging at the sworn creature."""

    def opening(ev: Hit) -> None:
        friends = sorted(a for a in c.allies() if c.can_see(a))
        who = c.choose(friends, "who takes the opening") if friends else None
        if who is None:
            return
        quarry = ev.target
        c.bonus(
            "attack", 2, until=When.SONT, on=who,
            when=lambda ctx: ctx.get("target") == quarry,
        )

    _swing(c)
    _oath_rider(c, opening)


@power(
    "p11695",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=REF),
)
def p11695(c: Cast) -> None:
    _swing(c)
    _extra(c, DamageType.PSYCHIC)


@power(
    "p11698",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(WIS, vs=REF),
)
def p11698(c: Cast) -> None:
    """"3 extra lightning and thunder damage" is one packet of two types,
    which `DamageType` cannot hold. Dealt as the first of the two printed
    rather than as two packets, which would double it -- the same call
    `paladin/level_9.py` made for its necrotic and psychic row.
    """
    _swing(c)
    _extra(c, DamageType.LIGHTNING)


@power(
    "p11701",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p11701(c: Cast) -> None:
    def splash(ev: Hit) -> None:
        others = sorted(f for f in c.within(1, side="enemy") if f != ev.target)
        foe = c.choose(others, "who the light catches") if others else None
        if foe is not None:
            c.flat(max(0, c.wis_mod), dtype=DamageType.RADIANT, on=foe)

    _swing(c)
    _oath_rider(c, splash)


@power(
    "p11704",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11704(c: Cast) -> None:
    _swing(c)
    _oath_rider(
        c, lambda ev: c.resist(max(0, c.wis_mod), until=When.SONT, on=c.me)
    )


@power(
    "p11707",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p11707(c: Cast) -> None:
    _swing(c)
    _extra(c, DamageType.RADIANT)


@power(
    "p11710",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(WIS, vs=REF),
)
def p11710(c: Cast) -> None:
    _swing(c)
    _extra(c, DamageType.NECROTIC)


@power(
    "p11713",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.ILLUSION],
    attack=Attack(WIS, vs=REF),
)
def p11713(c: Cast) -> None:
    _swing(c)
    _oath_rider(c, lambda ev: c.invisible(on=c.me, until=When.SONT))
