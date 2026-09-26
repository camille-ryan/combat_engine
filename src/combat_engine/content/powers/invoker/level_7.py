"""Invoker, level 7: the encounter attacks."""

from __future__ import annotations

from combat_engine.engine import (
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
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
    Condition,
    DamageType,
    Keyword,
    Ranged,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    enemy_within,
    power,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


@power(
    "p10094",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p10094(c: Cast) -> None:
    if c.strike():
        c.dazed(until=When.EONT)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p11045",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=FORT),
)
def p11045(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.LIGHTNING)
        c.dazed(until=When.EONT)


@power(
    "p11292",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p11292(c: Cast) -> None:
    """The affliction is a named hold with no content of its own, so
    `c.suffering` can find everyone carrying it and the contagion has
    something to read."""
    if c.first:

        def spread(ev: TurnStart) -> None:
            if ev.ghost:
                return
            sick = [s for s in c.suffering("plague", include_self=True) if s != ev.actor]
            if not any(c.adjacent_to(s, ev.actor) for s in sick):
                return
            c.dazed(on=ev.actor, until=When.SOTNT)
            c.effect(f"{c.ref} plague", until=When.SOTNT, on=ev.actor)

        c.watch(TurnStart, spread, until=When.EONT)
    if c.strike():
        c.dazed(until=When.EONT)
        c.effect(f"{c.ref} plague", until=When.EONT)


@power(
    "p11293",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p11293(c: Cast) -> None:
    """The choice is the target's, and refusing it is the default: an
    engine with nobody playing would otherwise always look away and the
    attack would never be rolled."""
    victim = c.target
    if victim is None:
        return
    if c.may("look away and be blinded", who=victim, default=False):
        c.blinded(on=victim, until=When.EONT)
        return
    if c.strike():
        c.damage("3d6", c.wis_mod, dtype=DamageType.RADIANT)
        c.flee(c.speed_of(victim), on=victim)


@power(
    "p16498",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
    trigger="an enemy ends its turn within 5 squares of you",
    on=Trigger(TurnEnd, enemy_within(5), "an enemy ends its turn within 5 squares"),
)
def p16498(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.wis_mod)
        c.slowed(until=When.EOTNT)


@power(
    "p2869",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL, plus=5),
)
def p2869(c: Cast) -> None:
    """Dropping prone is offered before the roll and declining is the
    default, so a board with nobody answering still rolls the attack."""
    victim = c.target
    if victim is None:
        return
    if not c.is_(Condition.PRONE, on=victim) and c.may(
        "drop prone", who=victim, default=False
    ):
        c.prone(on=victim)
    if c.is_(Condition.PRONE, on=victim):
        if c.build("wrath"):
            c.damage("1d6", dtype=DamageType.PSYCHIC, on=victim)
        return
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.PSYCHIC)


@power(
    "p2871",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p2871(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.THUNDER)
        c.push(1 + c.int_mod if c.build("preservation") else 1)


@power(
    "p2872",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p2872(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 2, until=When.EOTNT)


@power(
    "p7181",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p7181(c: Cast) -> None:
    """Written to the erratum printed with the row: burst 1, and 1d6."""
    if c.first and c.build("wrath") and c.con_mod > 0:
        for mate in c.in_squares(c.area(), side="ally"):
            c.bonus("attack", c.con_mod, on=mate, kind="power", until=When.EONT)
    if c.strike():
        c.damage("1d6", c.wis_mod)
        c.vulnerable(5, until=When.EONT)


@power(
    "p7182",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p7182(c: Cast) -> None:
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                c.slide(1 + c.int_mod, on=mate)
    if c.strike():
        c.damage("1d6", c.wis_mod)
        c.slowed(until=When.EONT)


@power(
    "p7183",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER, Keyword.FEAR],
    attack=Attack(WIS, vs=FORT),
)
def p7183(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.THUNDER)
        c.penalty("attack", c.int_mod if c.build("preservation") else 2, until=When.EONT)


@power(
    "p7184",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p7184(c: Cast) -> None:
    """The covenant's -2 is a save modifier on the burn itself rather than
    a penalty to every throw the creature makes, which is what the printed
    line says and what `Effect.save_mod` is for."""
    if c.first:
        c.dazed(on=c.me, until=When.EONT)
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.RADIANT)
        burn = c.ongoing(5, DamageType.FIRE)
        if burn is not None and c.build("malediction"):
            burn.save_mod = -2


@power(
    "p7185",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE, Keyword.CONJURATION],
)
def p7185(c: Cast) -> None:
    """Two halves of one sentence: who started its turn near the symbols,
    and who was still near them when the turn ended. The aura is what
    "within 5 squares of the symbols" means once they can be moved."""
    symbols = c.conjure(at=c.origin, until=When.EONT, sustain=None)
    ring = c.aura(5, on=symbols, until=When.EONT)
    stayed: set[int] = set()

    def note(ev: TurnStart, z: int = ring) -> None:
        near = ev.actor in c.world.zones.occupants(z)
        if not ev.ghost and near and ev.actor in c.enemies():
            stayed.add(ev.actor)

    def scorch(ev: TurnEnd, z: int = ring) -> None:
        if ev.actor not in stayed:
            return
        stayed.discard(ev.actor)
        if ev.actor in c.world.zones.occupants(z):
            c.flat(10 + c.wis_mod, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnStart, note, until=When.EONT)
    c.watch(TurnEnd, scorch, until=When.EONT)
