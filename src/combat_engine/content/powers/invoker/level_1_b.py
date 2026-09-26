"""Invoker, level 1: the rest of the encounter rows, and the dailies."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
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
    Defense,
    Keyword,
    Miss,
    Ranged,
    Summon,
    TurnEnd,
    TurnStart,
    UpTo,
    When,
    get,
    power,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


@power(
    "p5188",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p5188(c: Cast) -> None:
    """The Effect line is once for the whole burst, so it sits behind
    `c.first` -- which also means it needs at least one enemy caught, the
    standing limitation of an Effect line on a targeted row."""
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.bonus("ac", 2, on=mate, kind="power", until=When.EONT)
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p7154",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p7154(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.THUNDER)
        c.push(c.int_mod if c.build("preservation") else 1)


@power(
    "p7155",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=REF),
)
def p7155(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.LIGHTNING)
        size = c.con_mod if c.build("wrath") else 1
        for d in Defense:
            c.penalty(d, size, until=When.EONT)


@power(
    "p7156",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=UpTo(2, "other"),
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p7156(c: Cast) -> None:
    if c.first:
        c.dazed(on=c.me, until=When.EONT)
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)
        c.pull(3)
        if c.build("malediction"):
            c.prone()


@power(
    "p7157",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p7157(c: Cast) -> None:
    """No damage on the hit itself -- the whole payload is the penalty and
    the sting on a miss."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.penalty("attack", 2, until=When.EONT)
    hurt = 5 + (c.wis_mod if c.build("malediction") else 0)

    def flinch(ev: Miss, who: int = victim, amount: int = hurt) -> None:
        if ev.attacker == who:
            c.flat(amount, dtype=DamageType.PSYCHIC, on=who)

    c.watch(Miss, flinch, until=When.EONT, on=victim)


@power(
    "p11283",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.FEAR, Keyword.ZONE],
    attack=Attack(WIS, vs=WILL),
)
def p11283(c: Cast) -> None:
    """The zone's penalties are held by each enemy and gated on standing in
    the zone, which is how an enemy that walks in later picks them up and
    how they all lapse when the zone goes. Moving the zone as part of a move
    action is not written: nothing can relocate a zone's squares."""
    if c.first:
        light = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)
        for foe in c.enemies():
            for what in ("attack", "save", *Defense):
                c.penalty(
                    what,
                    2,
                    on=foe,
                    until=When.ENCOUNTER,
                    when=lambda ctx, w=foe, z=light: w
                    in c.world.zones.occupants(z),
                )

        def snuff(ev: TurnEnd, z: int = light) -> None:
            if ev.actor == c.me and c.me in c.world.zones.occupants(z):
                c.world.zones.end(z, "the caster ended a turn inside it")

        c.watch(TurnEnd, snuff, until=When.ENCOUNTER)
    if c.strike():
        c.ongoing(10, DamageType.RADIANT)
    else:
        c.flat(5, dtype=DamageType.RADIANT)


@power(
    "p2856",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p2856(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.RADIANT)
        c.on_attack(
            lambda ev, who=victim: c.flat(5, dtype=DamageType.RADIANT, on=who),
            by=victim,
            until=When.EONT,
        )
    else:
        c.half_damage("1d6", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p2875",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
)
def p2875(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.FIRE)
        c.ongoing(10, DamageType.FIRE)
    else:
        c.half_damage("1d10", c.wis_mod, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)


@power(
    "p5189",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5189(c: Cast) -> None:
    if c.strike():
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.EONT)


@power(
    "p7158",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p7158(c: Cast) -> None:
    """"Any ally within 5 squares of it" is read from the target's side of
    the fight: the creature punished is the one wearing the crown, and the
    creatures whose wounds set it off are its own. The hold is the watch
    itself, so a save ends both halves at once."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.RADIANT)

    def echo(ev: DamageApplied, who: int = victim) -> None:
        if ev.target != who and ev.target in c.within(5, of=who, side="enemy"):
            c.flat(5, dtype=DamageType.RADIANT, on=who)

    c.watch(
        DamageApplied, echo, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} crown"
    )


@power(
    "p7159",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=UpTo(2, "other"),
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p7159(c: Cast) -> None:
    if c.first:
        c.ongoing(5, on=c.me)
    dice = "2d8" if len(c.targets) == 1 else "1d8"
    if c.strike():
        c.damage(dice, c.wis_mod)
        c.ongoing(10)
    else:
        c.half_damage(dice, c.wis_mod)
        c.ongoing(5)


@power(
    "p7160",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE, Keyword.COLD, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p7160(c: Cast) -> None:
    """"Cold and fire" is one number of two types and damage carries one
    type, so it is dealt as fire throughout. The zone bites on starting a
    turn inside it and not on entering, which is what is printed --
    `c.hazard` would add the entry half."""
    if c.first:
        hail = c.zone(c.area(), until=When.EONT)

        def chill(ev: TurnStart, z: int = hail) -> None:
            if not ev.ghost and ev.actor in c.world.zones.occupants(z):
                c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

        c.watch(TurnStart, chill, until=When.EONT)
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.FIRE)


@power(
    "p7161",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p7161(c: Cast) -> None:
    if c.first:
        c.dazed(on=c.me, until=When.EONT)
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.THUNDER)
        c.stunned(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.wis_mod, dtype=DamageType.THUNDER)
        c.dazed(until=When.EONT)


@power(
    "p7162",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(WIS, vs=REF),
)
def p7162(c: Cast) -> None:
    """"Save ends both" is one effect carrying the daze and the burn, so
    one throw clears them together."""
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.THUNDER)
        c.condition(
            Condition.DAZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.LIGHTNING),
        )
    else:
        c.half_damage("1d8", c.wis_mod, dtype=DamageType.THUNDER)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p11282",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=DIVINE_IMPLEMENT,
    summon=Summon(
        speed=6,
        attack=Attack(WIS, vs=REF),
        damage=Damage("2d12", "wis"),
    ),
)
def p11282(c: Cast) -> None:
    """The printed bonus is to AC alone and `Summon.defences` is one offset
    across all four, so it is handed out in the body.

    Dropped: the mark rider on the standard command, and the whole opportunity
    command, which rolls a different defence for no damage -- the header carries
    one attack line and `c.command` rolls it."""
    angel = c.summon_inline(get(c.ref).summon, at=c.origin)
    if angel:
        c.bonus(AC, 2, on=angel, until=When.ENCOUNTER)


@power(
    "p3314",
    level=1,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.FIRE, Keyword.IMPLEMENT],
    summon=Summon(
        speed=6,
        modes=("fly",),
        attack=Attack(WIS, vs=REF),
        damage=Damage("1d8", "wis", dtype=DamageType.FIRE),
    ),
)
def p3314(c: Cast) -> None:
    """Its standard command is a close burst 1 and its opportunity command a
    melee 1 off the same numbers; `c.command` rolls one target, so the burst's
    spread is dropped and the shared line is what the header carries."""
    c.summon_inline(get(c.ref).summon, at=c.origin)
