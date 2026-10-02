"""Invoker, level 5: the dailies."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Ranged,
    Summon,
    Trigger,
    TurnEnd,
    UpTo,
    When,
    both,
    by_melee,
    by_ranged,
    either,
    enemy_target_within,
    get,
    power,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


@power(
    "p11044",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(WIS, vs=REF),
)
def p11044(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("4d6", c.wis_mod, dtype=DamageType.LIGHTNING)
        c.penalty("attack", 2, until=When.SAVE_ENDS)
    else:
        c.half_damage("4d6", c.wis_mod, dtype=DamageType.LIGHTNING)

    def crackle(ev: TurnEnd, who: int = victim) -> None:
        if ev.actor != who and ev.actor in c.within(1, of=who, side="enemy"):
            c.damage("1d6", c.con_mod, dtype=DamageType.THUNDER, on=ev.actor)

    c.watch(TurnEnd, crackle, until=When.EONT)


@power(
    "p11289",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(5),
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p11289(c: Cast) -> None:
    """The ongoing damage is a table read off how many targets were hit, so
    it cannot be settled until the last target has been rolled for: the
    creatures hit are collected on the cast and paid out on `c.last`. Only
    the two-target line of that table is printed in the spec, so only that
    one is written. "Fire and radiant" is one number of two types and
    damage carries one, so it is dealt as radiant."""
    struck: list[int] = getattr(c, "struck_here", [])
    c.struck_here = struck
    if c.strike():
        c.damage("1d4", c.wis_mod, dtype=DamageType.RADIANT)
        if c.target is not None:
            struck.append(c.target)
    else:
        c.damage(0, c.wis_mod, dtype=DamageType.RADIANT)
    if c.last and len(struck) == 2:
        for who in struck:
            c.ongoing(10, DamageType.RADIANT, on=who)


@power(
    "p12302",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p12302(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod + c.int_mod, dtype=DamageType.PSYCHIC)
        if c.is_kind("shapechanger"):
            c.dazed(until=When.SAVE_ENDS)
        else:
            c.dazed(until=When.EONT)


@power(
    "p2873",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p2873(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.push(c.con_mod if c.build("wrath") else 2)
    else:
        c.half_damage("2d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.push(1)


@power(
    "p2874",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(WIS, vs=REF),
)
def p2874(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.FORCE)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("1d6", c.wis_mod, dtype=DamageType.FORCE)
        c.slowed(until=When.EONT)


@power(
    "p2877",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=FORT),
)
def p2877(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.RADIANT)
        c.blinded(until=When.SAVE_ENDS)
        if c.build("preservation"):
            c.dazed(until=When.EONT)
    else:
        c.half_damage("1d8", c.wis_mod, dtype=DamageType.RADIANT)
        c.blinded(until=When.EONT)


@power(
    "p5192",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*DIVINE_IMPLEMENT, Keyword.CONJURATION],
)
def p5192(c: Cast) -> None:
    """The blade occupies its square and moves 5 when sustained, which is
    what `c.conjure` already means. The interrupt that jumps the blade next
    to an enemy and swings is `p5192b`, which reads the standing blade as
    its Requirement."""
    c.conjure(at=c.origin, until=When.SUSTAIN, sustain=MINOR, speed=5)


@power(
    "p7172",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
    trigger="an enemy within 5 squares of you is damaged by a melee or a ranged attack",
    on=Trigger(
        DamageApplied,
        both(enemy_target_within(5), either(by_melee, by_ranged)),
        "an enemy within 5 squares is damaged by a melee or ranged attack",
    ),
)
def p7172(c: Cast) -> None:
    """The triggering creature is the one *damaged*, which the dispatcher
    cannot pick out -- it looks for an attacker -- so the swing is aimed by
    hand at the event's target."""
    victim = getattr(c.trigger, "target", None) or c.target
    c.dazed(on=c.me, until=When.EONT)
    if victim is None:
        return
    if c.strike(on=victim):
        c.condition(
            Condition.DAZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED),
            on=victim,
        )
    else:
        c.ongoing(5, on=victim)


@power(
    "p7173",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p7173(c: Cast) -> None:
    """The encounter-long rider is a watch on `Hit` rather than a gated
    damage bonus: the damage context carries no advantage flag, so a
    `when=` on it would be silently false forever."""
    if c.first:

        def press(ev: Hit) -> None:
            result = getattr(ev, "result", None)
            if result is None or not result.advantage:
                return
            if ev.attacker != c.me and ev.attacker not in c.within(5, side="ally"):
                return
            if ev.target in c.enemies():
                c.flat(c.con_mod, on=ev.target)

        c.watch(Hit, press, until=When.ENCOUNTER)
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.grants_advantage(until=When.SAVE_ENDS, to="team")
        c.cannot_shift(until=When.SAVE_ENDS)


@power(
    "p7174",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p7174(c: Cast) -> None:
    """"You grant combat advantage" with nobody named means to everybody,
    and the relation holds one beneficiary at a time, so it is granted once
    per enemy."""
    if c.first:
        for foe in c.enemies():
            c.grants_advantage(on=c.me, until=When.SONT, to=foe)
    if c.strike():
        c.damage("2d8", c.wis_mod)
        c.blinded(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.wis_mod)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p7175",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p7175(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.RADIANT)
        if len(c.targets) == 1:
            c.dazed(until=When.SAVE_ENDS)
        else:
            c.dazed(until=When.EOTNT)
    else:
        c.half_damage("2d6", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p7176",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p7176(c: Cast) -> None:
    """"Fire and radiant" is dealt as radiant -- one number, and damage
    carries one type. "Heavily obscured" is a zone that blocks sight."""
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER, blocks_sight=True)
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.RADIANT)
        c.prone()
    else:
        c.half_damage("2d6", c.wis_mod, dtype=DamageType.RADIANT)
        c.push(1)


@power(
    "p11288",
    level=5,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=DIVINE_IMPLEMENT,
    summon=Summon(
        speed=6,
        attack=Attack(WIS, vs=FORT, plus=1),
        damage=Damage("1d12", "wis"),
    ),
)
def p11288(c: Cast) -> None:
    """+2 to AC and Reflex only, so the two are handed out in the body --
    `Summon.defences` is one offset across all four.

    Dropped: the run-in that the standard command opens with and its prone
    rider, the +2 to speed while charging, and the shift on the opportunity
    command."""
    lion = c.summon_inline(get(c.ref).summon, at=c.origin)
    if lion:
        c.bonus(AC, 2, on=lion, until=When.ENCOUNTER)
        c.bonus(REF, 2, on=lion, until=When.ENCOUNTER)
