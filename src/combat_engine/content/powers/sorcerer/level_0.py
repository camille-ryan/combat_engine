"""Sorcerer, level 0: the elemental at-wills and the four riders on them.

The four riders all print the same opening: "you can make one additional
creature a target of the triggering attack". Nothing can add a target to an
attack already declared -- `use` fixed the list before the row was offered --
so that sentence is dropped from all four and the rest of each is written.

They answer `AttackDeclared` rather than `PowerUsed`: the extra damage lands
on "each target hit by the attack", so the watch has to be armed before the
roll, and `AttackDeclared` is the only window a Free action gets that is
still in front of it. The damage is untyped rather than "of the type dealt
by the triggering attack", which the event does not carry.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Event,
    Hit,
    Keyword,
    Ranged,
    Trigger,
    Usage,
    When,
    World,
    get,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.ELEMENTAL, Keyword.IMPLEMENT]
MY_AT_WILL = "you use a sorcerer at-will attack power"


def _my_sorcerer_at_will(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.cls == "sorcerer" and p.usage is Usage.AT_WILL


def _extra(level: int) -> str:
    return "1d10" if level < 17 else ("2d10" if level < 27 else "3d10")


def _on_each_hit(c: Cast, fn: Callable[[Hit], None]) -> None:
    """"Each target hit by the attack": one watch, fired per landing blow,
    held to the end of the turn so a burst pays out on all of them."""

    def watcher(ev: Hit) -> None:
        if ev.attacker == c.me:
            fn(ev)

    c.watch(Hit, watcher, until=When.EOT, on=c.me, label=f"{c.ref} spell")


# -- the riders -------------------------------------------------------------


@power(
    "p16224",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
    once_per_round=True,
    trigger=MY_AT_WILL,
    on=Trigger(AttackDeclared, _my_sorcerer_at_will, MY_AT_WILL),
)
def p16224(c: Cast) -> None:
    dice = _extra(c.level)

    def sting(ev: Hit) -> None:
        c.damage(dice, on=ev.target)
        if c.level >= 17:
            c.slide(2, on=ev.target)
        if c.level >= 27:
            c.blinded(on=ev.target, until=When.EONT)

    _on_each_hit(c, sting)
    c.mode("fly", c.speed_of(), until=When.EOT, on=c.me)
    c.move(max(1, c.speed_of() // 2))


@power(
    "p16225",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
    once_per_round=True,
    trigger=MY_AT_WILL,
    on=Trigger(AttackDeclared, _my_sorcerer_at_will, MY_AT_WILL),
)
def p16225(c: Cast) -> None:
    dice = _extra(c.level)

    def sting(ev: Hit) -> None:
        c.damage(dice, on=ev.target)
        if c.level >= 17:
            c.immobilized(on=ev.target, until=When.EONT)

    _on_each_hit(c, sting)
    c.temp_hp(c.cha_mod, on=c.me)
    if c.level >= 27:
        c.resist(c.level // 2, until=When.EONT, on=c.me)


@power(
    "p16226",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
    once_per_round=True,
    trigger=MY_AT_WILL,
    on=Trigger(AttackDeclared, _my_sorcerer_at_will, MY_AT_WILL),
)
def p16226(c: Cast) -> None:
    """The 27th-level line makes the triggering attack deal half damage on a
    miss, which belongs to that attack's header and cannot be handed to it
    from here; it is left off."""
    dice = _extra(c.level)

    def sting(ev: Hit) -> None:
        c.damage(dice, on=ev.target)
        if c.level >= 17:
            c.ongoing(10, DamageType.FIRE, on=ev.target)

    _on_each_hit(c, sting)
    c.shift(max(1, c.speed_of() // 2))


@power(
    "p16227",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
    once_per_round=True,
    trigger=MY_AT_WILL,
    on=Trigger(AttackDeclared, _my_sorcerer_at_will, MY_AT_WILL),
)
def p16227(c: Cast) -> None:
    dice = _extra(c.level)

    def sting(ev: Hit) -> None:
        c.damage(dice, on=ev.target)
        if c.level >= 17:
            c.dazed(on=ev.target, until=When.EONT)
        if c.level >= 27:
            c.prone(on=ev.target)

    _on_each_hit(c, sting)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, until=When.EONT, on=c.me, kind="power")


# -- the at-wills -----------------------------------------------------------


@power(
    "p16222",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p16222(c: Cast) -> None:
    if c.strike():
        c.damage("1d12" if c.level < 21 else "2d12", c.cha_mod)


@power(
    "p16228",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p16228(c: Cast) -> None:
    if c.first:
        c.bonus(AC, 2, until=When.SONT, on=c.me, kind="power")
        c.bonus(REF, 2, until=When.SONT, on=c.me, kind="power")
    if c.strike():
        c.damage("1d8" if c.level < 21 else "2d8", c.cha_mod, dtype=DamageType.FIRE)


@power(
    "p16229",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p16229(c: Cast) -> None:
    if c.strike():
        c.damage("1d8" if c.level < 21 else "2d8", c.cha_mod)
        c.push(1)


@power(
    "p16230",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=FORT),
)
def p16230(c: Cast) -> None:
    """The rough ground is an Effect line, so it is laid once for the whole
    use rather than per target."""
    if c.first:
        c.zone(c.area(), difficult=True, until=When.EONT, label=f"{c.ref} ground")
    if c.strike():
        c.damage("1d6" if c.level < 21 else "2d6", c.cha_mod)


@power(
    "p16231",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p16231(c: Cast) -> None:
    if c.strike():
        c.damage("1d8" if c.level < 21 else "2d8", c.cha_mod, dtype=DamageType.THUNDER)
        c.slide(1)


@power(
    "p16232",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p16232(c: Cast) -> None:
    if c.strike():
        c.damage("1d8" if c.level < 21 else "2d8", c.cha_mod, dtype=DamageType.COLD)
        c.slowed(until=When.EONT)


@power(
    "p16233",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.ZONE],
    attack=Attack(CHA, vs=FORT),
)
def p16233(c: Cast) -> None:
    """`c.burns` is the printed "enters the zone or ends its turn there,
    once per turn" -- it bites everybody, which is what this line says."""
    if c.first:
        fire = c.zone(c.area(), until=When.SONT, label=f"{c.ref} fire")
        c.burns(fire, c.con_mod, DamageType.FIRE)
    if c.strike():
        c.damage("1d10" if c.level < 21 else "2d10", c.cha_mod)


@power(
    "p16234",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p16234(c: Cast) -> None:
    if c.strike():
        c.damage("1d8" if c.level < 21 else "2d8", c.cha_mod, dtype=DamageType.THUNDER)
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "p16235",
    level=0,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p16235(c: Cast) -> None:
    """The arc jumps to an enemy beside the one hit, which may be outside
    the blast -- so it is found by adjacency rather than taken off
    `c.targets`."""
    if not c.strike():
        return
    c.damage("1d8" if c.level < 21 else "2d8", dtype=DamageType.LIGHTNING)
    beside = [e for e in c.within(1, of=c.target, side="enemy") if e != c.target]
    if beside:
        c.flat(c.cha_mod, dtype=DamageType.LIGHTNING, on=beside[0])
