"""Psion, level 5: the dailies."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    INT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Damage,
    DamageType,
    Keyword,
    Ranged,
    Summon,
    TurnEnd,
    When,
    get,
    power,
)

PSIONIC_FORCE = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.FORCE]
PSIONIC_PSYCHIC = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC]


@power(
    "p11277",
    level=5,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.FORCE,
        Keyword.ZONE,
    ],
    attack=Attack(INT, vs=REF),
)
def p11277(c: Cast) -> None:
    if c.first:
        c.hazard(
            c.area(),
            c.wis_mod,
            DamageType.FORCE,
            until=When.SUSTAIN,
            sustain=MINOR,
        )
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.FORCE)


@power(
    "p11316",
    level=5,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=AC),
)
def p11316(c: Cast) -> None:
    """"Pushed into difficult terrain" is read off the live zones, which is
    where the engine keeps rough ground."""
    if c.strike():
        c.damage("3d12", c.int_mod, dtype=DamageType.FORCE)
        c.push(max(1, c.wis_mod))
        if c.there in c.world.zones.difficult_squares():
            c.prone()
    else:
        c.half_damage("3d12", c.int_mod, dtype=DamageType.FORCE)
        c.push(1)


@power(
    "p13322",
    level=5,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC_FORCE,
)
def p13322(c: Cast) -> None:
    """One hold per sphere, because `p13322b` expends them one at a time and
    a single hold could not be counted down. The +2 is gated on at least one
    of them still spinning rather than held for the encounter, which is the
    printed "while you have at least one" -- and it goes out by itself when
    the fourth is spent."""
    for _ in range(4):
        c.effect(c.ref, on=c.me, until=When.ENCOUNTER)

    def spinning(ctx: dict) -> bool:
        return any(eff.label == c.ref for eff in c.world.effects.of(c.me))

    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.ENCOUNTER, when=spinning)


@power(
    "p13324",
    level=5,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.ZONE,
    ],
    attack=Attack(INT, vs=REF),
)
def p13324(c: Cast) -> None:
    """The slow is hung off the zone's occupancy rather than off a copy of its
    squares, so sustaining the zone keeps the slow and letting it lapse stops
    it -- `c.watch` has no sustain cost of its own to pay."""
    if c.first:
        zone = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)

        def lingered(ev: TurnEnd) -> None:
            if ev.actor in c.world.zones.occupants(zone) and ev.actor in c.enemies():
                c.slowed(on=ev.actor, until=When.EONT)

        c.watch(TurnEnd, lingered, until=When.ENCOUNTER, label=c.ref)
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p13326",
    level=5,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.THUNDER,
        Keyword.TELEPORTATION,
    ],
    attack=Attack(INT, vs=FORT),
)
def p13326(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.THUNDER)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.THUNDER)
    if c.last:
        c.teleport(5)


@power(
    "p8235",
    level=5,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.CHARM,
    ],
    attack=Attack(INT, vs=WILL),
)
def p8235(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        c.half_damage("3d6", c.int_mod, dtype=DamageType.PSYCHIC)
        return
    c.damage("3d6", c.int_mod, dtype=DamageType.PSYCHIC)
    near = [x for x in c.within(1, of=victim, side="any") if x not in (victim, c.me)]
    if not near:
        return
    foe = c.choose(near, f"{c.ref}: whom the target strikes")
    if foe is not None:
        c.grant_attack(
            victim, on=foe, attack_bonus=c.cha_mod, damage_bonus=c.cha_mod
        )


@power(
    "p8236",
    level=5,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8236(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.dazed(until=When.EONT)


@power(
    "p13325",
    level=5,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.POISON],
    summon=Summon(
        speed=7,
        modes=("climb",),
        attack=Attack(INT, vs=REF),
        damage=Damage("1d8", "int"),
    ),
)
def p13325(c: Cast) -> None:
    """+4 to AC and +2 to Reflex only, so the two are handed out in
    the body -- `Summon.defences` is one offset across all four.

    Dropped: the grab on the standard command -- `Summon` declares an attack
    and a damage line and has nowhere to put a rider -- and the whole
    opportunity command with its ongoing poison. Augment 1 goes with the
    grab: a penalty to escaping a hold nothing ever applies would be a
    clause that can never come up."""
    stinger = c.summon_inline(get(c.ref).summon, at=c.origin)
    if stinger:
        c.bonus(AC, 4, on=stinger, until=When.ENCOUNTER)
        c.bonus(REF, 2, on=stinger, until=When.ENCOUNTER)
        # `Summon.modes` carries no speed, and the printed climb is slower
        # than the creature walks.
        c.mode("climb", 3, on=stinger, until=When.ENCOUNTER)
