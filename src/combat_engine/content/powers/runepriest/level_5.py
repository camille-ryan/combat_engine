"""Runepriest, level 5."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    UpTo,
    When,
    get,
    power,
)

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


@power(
    "p11386",
    level=5,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(STR, vs=WILL),
)
def p11386(c: Cast) -> None:
    """"Leaving the zone costs enemies 2 extra squares" is dropped: a zone is
    difficult for everybody or nobody, and difficult ground is not the same
    cost. The rest of the zone -- the exposure -- is watched."""
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
    if not c.first:
        return
    zid = c.zone(c.area(), until=When.EONT, sustain=MINOR)

    def expose(ev: Any, z: int = zid) -> None:
        inside = c.world.zones.occupants(z)
        if ev.attacker not in c.enemies():
            return
        if ev.target in inside and ev.target in [c.me, *c.allies()]:
            c.grants_advantage(on=ev.attacker, until=When.SAVE_ENDS, to="allies")

    c.watch(AttackDeclared, expose, until=When.EONT)


@power(
    "p11387",
    level=5,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=WILL),
)
def p11387(c: Cast) -> None:
    """Everything after the damage is dropped. Both riders are gated on the
    *shape* of the attack coming in -- combat advantage and vulnerability to
    ranged and area attacks only -- and neither `c.grants_advantage` nor
    `c.vulnerable` takes a gate; nor can cover be waived for one creature."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p11388",
    level=5,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[*DIVINE_WEAPON, Keyword.FIRE],
    attack=Attack(STR, vs=AC),
)
def p11388(c: Cast) -> None:
    """One target burns; two are tied together, which needs both ids at once
    -- `c.targets` is the whole list the body is walking. The hold is what
    the saving throw ends, so the link reads it rather than a duration."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.FIRE)
    if not c.last:
        return
    pair = tuple(t for t in c.targets if t is not None)
    if len(pair) < 2:
        c.ongoing(5, DamageType.FIRE)
        return
    for who in pair:
        c.effect("p11388", on=who, until=When.SAVE_ENDS)

    def link(ev: Any, tied: tuple[int, ...] = pair) -> None:
        burning = c.suffering("p11388")
        if ev.target not in tied or ev.target not in burning:
            return
        p = get(ev.power)
        if p is None or p.reach.kind not in ("melee", "ranged"):
            return
        for other in tied:
            if other != ev.target and other in burning:
                c.flat(5, dtype=DamageType.FIRE, on=other)

    c.watch(Hit, link, until=When.ENCOUNTER)


@power(
    "p11389",
    level=5,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p11389(c: Cast) -> None:
    """The bonus grows by re-applying it larger: two bonuses of one kind do
    not add, the larger wins. It lives on the attackers, so it is the gate
    rather than the duration that ends it when the target saves."""
    victim = c.target
    kind = c.choose([DamageType.NECROTIC, DamageType.RADIANT], "which rune")
    kind = kind or DamageType.RADIANT
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=kind)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=kind)
    if victim is None:
        return
    c.effect("p11389", until=When.SAVE_ENDS)
    side = [c.me, *c.allies()]

    def grant(size: int, v: int = victim) -> None:
        for who in side:
            c.bonus(
                "damage",
                size,
                on=who,
                until=When.ENCOUNTER,
                when=lambda ctx, t=v: ctx.get("target") == t
                and t in c.suffering("p11389"),
            )

    grant(2)
    step = [2]

    def sharpen(ev: Any, v: int = victim) -> None:
        if ev.target != v or ev.attacker not in side:
            return
        if v not in c.suffering("p11389"):
            return
        step[0] += 1
        grant(step[0])

    c.watch(Hit, sharpen, until=When.ENCOUNTER)
