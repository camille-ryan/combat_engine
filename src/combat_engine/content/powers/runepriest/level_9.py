"""Runepriest, level 9."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Dropped,
    Keyword,
    Melee,
    TurnStart,
    When,
    ZoneEntered,
    power,
)

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DEFENCES = (AC, FORT, REF, WILL)


@power(
    "p11399",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11399(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if victim is None:
        return

    def rush(ev: Any, v: int = victim) -> None:
        if ev.ghost or ev.actor not in c.allies():
            return
        if not c.adjacent_to(v, ev.actor):
            return
        if c.may("swing at it for free", who=ev.actor):
            c.basic(who=ev.actor, on=v)

    c.watch(TurnStart, rush, until=When.EONT)


@power(
    "p11400",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=FORT),
    attack_alt=Attack(STR, vs=WILL),
)
def p11400(c: Cast) -> None:
    """The second half of this row is a power of its own on the page. It is
    the alternate attack line here, rolled from a square in the target's
    space when the target falls, which is what the printed origin means."""
    victim = c.target
    kind = c.choose([DamageType.NECROTIC, DamageType.RADIANT], "which rune")
    kind = kind or DamageType.RADIANT
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=kind)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=kind)
    if victim is None:
        return

    def verge(ev: Any, v: int = victim) -> None:
        if ev.actor != v:
            return
        c.branch = 1
        try:
            for e in c.within(3, of=v, side="enemy"):
                if c.strike(on=e, from_=v):
                    c.dazed(on=e, until=When.SAVE_ENDS)
        finally:
            c.branch = 0

    c.watch(Dropped, verge, until=When.ENCOUNTER)


@power(
    "p11402",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11402(c: Cast) -> None:
    """The Effect is dropped: nothing can make an attack miss creatures it
    has already been declared against -- `c.autohit` has no counterpart."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)


@power(
    "p11403",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(STR, vs=FORT),
)
def p11403(c: Cast) -> None:
    """The zone's resist is dropped -- `c.resist` cannot be gated on the
    shape of the attack coming in. Its AC bonus is handed out on entry and
    runs its duration rather than ending when somebody steps out."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.RADIANT)
        c.push(4)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.RADIANT)
        c.push(1)
    if not c.first:
        return
    area = c.area()
    zid = c.zone(area, until=When.EONT, sustain=MINOR)
    for who in [c.me, *c.in_squares(area, side="ally")]:
        c.bonus(AC, 2, on=who, until=When.EONT, kind="power")

    def ward(ev: Any, z: int = zid) -> None:
        if ev.zone == z and ev.actor in [c.me, *c.allies()]:
            c.bonus(AC, 2, on=ev.actor, until=When.EONT, kind="power")

    c.watch(ZoneEntered, ward, until=When.EONT)


@power(
    "p15992",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=WILL),
)
def p15992(c: Cast) -> None:
    """The Effect line is not conditional on the hit, so it is applied to
    every target. The hold is what the saving throw ends; the watch reads it
    each time rather than carrying a duration of its own."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if victim is None:
        return
    c.effect("p15992", until=When.SAVE_ENDS)

    def jolt(ev: Any, v: int = victim) -> None:
        if v in c.suffering("p15992"):
            c.flat(5, dtype=DamageType.LIGHTNING, on=v)

    c.on_attack(jolt, by=victim, until=When.ENCOUNTER)


@power(
    "p16499",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p16499(c: Cast) -> None:
    """The aura's bonus is handed out on entry and to whoever is already
    standing in it, and runs the aura's duration."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    if not c.first:
        return
    ring = c.aura(1, until=When.EONT)
    for ally in c.within(1, side="ally"):
        for defence in DEFENCES:
            c.bonus(defence, 2, on=ally, until=When.EONT, kind="power")

    def ward(ev: Any, z: int = ring) -> None:
        if ev.zone != z or ev.actor not in c.allies():
            return
        for defence in DEFENCES:
            c.bonus(defence, 2, on=ev.actor, until=When.EONT, kind="power")

    c.watch(ZoneEntered, ward, until=When.EONT)
