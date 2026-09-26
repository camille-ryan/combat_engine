"""Runepriest, level 1.

The runic rows print a clause that applies in one of two rune states.
Nothing on the chassis holds that state, so `_rune` keeps it as a stance:
an unset state counts as the one the row asks for, and using a runic power
switches to the other, which is the printed feature.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
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
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    TurnEnd,
    When,
    ZoneEntered,
    power,
)

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DEFENCES = (AC, FORT, REF, WILL)

_DESTRUCTION = "rune:destruction"
_PROTECTION = "rune:protection"


def _in_rune(c: Cast, which: str) -> bool:
    """Is the caster in that rune state? An unset state counts as in it."""
    held = c.world.effects.stance_of(c.me)
    return held is None or which in held.label


def _rune(c: Cast, which: str) -> bool:
    """Read the rune state, then switch to the other one.

    Switching is what using a runic power does. The switch waits for the
    last target so every target of a blast reads the same state.
    """
    here = _in_rune(c, which)
    if c.last:
        c.stance(label=_PROTECTION if which == _DESTRUCTION else _DESTRUCTION)
    return here


@power(
    "p11354",
    level=1,
    cls="runepriest",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11354(c: Cast) -> None:
    """"Until you aren't adjacent to it" is dropped -- nothing ends an effect
    on a distance. The rune's "next attack" is one spend per ally rather than
    one across all of them: a gate cannot see what another ally has spent."""
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if c.strike():
        c.damage(0, c.str_mod)
        c.immobilized(until=When.EONT)
        if destruction and victim is not None:
            for ally in c.allies():
                c.bonus(
                    "damage",
                    c.wis_mod,
                    on=ally,
                    until=When.EONT,
                    once=True,
                    when=lambda ctx, v=victim: ctx.get("target") == v,
                )


@power(
    "p11355",
    level=1,
    cls="runepriest",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11355(c: Cast) -> None:
    """The larger opportunity-attack vulnerability rides on the attackers as
    a gated damage bonus: `c.vulnerable` has no gate, and only the damage
    context knows the hit was an opportunity attack."""
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    if not destruction or victim is None:
        return
    flat = 2 if c.level < 11 else 4 if c.level < 21 else 6
    against_oa = 5 if c.level < 11 else 7 if c.level < 21 else 10
    c.vulnerable(flat, until=When.EONT)
    for who in [c.me, *c.allies()]:
        c.bonus(
            "damage",
            against_oa - flat,
            on=who,
            until=When.EONT,
            when=lambda ctx, v=victim: bool(ctx.get("opportunity"))
            and ctx.get("target") == v,
        )


@power(
    "p11356",
    level=1,
    cls="runepriest",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11356(c: Cast) -> None:
    """The temporary hit points are paid when the ally swings at the target,
    which is the only moment "his next attack" names."""
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    if not destruction or victim is None:
        return

    def pay(ev: Any, v: int = victim) -> None:
        if ev.target == v:
            c.temp_hp(c.wis_mod, on=ev.attacker)

    for ally in c.allies():
        c.bonus(
            "damage",
            c.wis_mod,
            on=ally,
            until=When.EONT,
            once=True,
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )
        c.on_attack(pay, by=ally, until=When.EONT, once=True)


@power(
    "p11368",
    level=1,
    cls="runepriest",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11368(c: Cast) -> None:
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    if not destruction or victim is None:
        return

    def backlash(ev: Any, v: int = victim) -> None:
        near = [a for a in c.allies() if c.adjacent_to(c.me, a)]
        if ev.target != c.me and ev.target not in near:
            return
        if c.marked(on=v, by=ev.target):
            return
        c.flat(c.con_mod, on=v)

    c.on_attack(backlash, by=victim, until=When.EONT, once=True)


@power(
    "p11369",
    level=1,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p11369(c: Cast) -> None:
    """The resist 5 is dropped: `c.resist` cannot be pointed at one
    creature's attacks, and resist 5 to everything is a different power."""
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    if not destruction or victim is None:
        return

    def on_shift(ev: Any, v: int = victim) -> None:
        if ev.actor != v or ev.kind_ != "shift":
            return
        for who in [c.me, *[a for a in c.allies() if c.adjacent_to(c.me, a)]]:
            c.bonus(
                "attack",
                c.con_mod,
                on=who,
                until=When.EONT,
                once=True,
                when=lambda ctx, t=v: bool(ctx.get("opportunity"))
                and ctx.get("target") == t,
            )
            c.provoke(who, on=v, why="p11369")

    c.watch(MoveEnd, on_shift, until=When.EONT)


@power(
    "p11370",
    level=1,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p11370(c: Cast) -> None:
    destruction = _rune(c, _DESTRUCTION)
    if c.strike():
        extra = c.wis_mod if destruction else 0
        c.damage(c.w(), c.str_mod + extra, dtype=DamageType.THUNDER)
        if destruction:
            c.grants_advantage(until=When.EONT, to="allies")


@power(
    "p11371",
    level=1,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11371(c: Cast) -> None:
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike() or victim is None:
        return
    c.damage(c.w(), c.str_mod)
    for ally in c.allies():
        c.bonus(
            "damage",
            2,
            on=ally,
            until=When.EONT,
            when=lambda ctx, v=victim: ctx.get("target") == v, kind="untyped")
    if not destruction:
        return
    near = c.within(5, side="ally")
    pick = c.choose(near, "an ally to guide") if near else None
    if pick is not None:
        c.bonus(
            "attack",
            4,
            on=pick,
            until=When.SONT,
            once=True,
            when=lambda ctx, v=victim: ctx.get("target") == v, kind="power")


@power(
    "p11372",
    level=1,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p11372(c: Cast) -> None:
    destruction = _rune(c, _DESTRUCTION)
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.FIRE)
    if c.first and destruction:
        for ally in c.in_squares(c.area(), side="ally"):
            c.bonus("damage", 3, on=ally, until=When.EONT, kind="power")


@power(
    "p11373",
    level=1,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p11373(c: Cast) -> None:
    """Damage is typed fire; `c.damage` takes one type, and nothing retypes
    the caster's later attacks or enlarges the hit points her powers grant,
    so those two thirds of the Effect line are dropped."""
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.FIRE)
        c.blinded(until=When.EONT)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.FIRE)
    if c.first:
        c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER)


@power(
    "p11374",
    level=1,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11374(c: Cast) -> None:
    """"Cannot shift" is `c.rooted`. The Effect's "and deals no damage on a
    miss" is dropped: a `Miss` does not say whether the power had a miss
    line, so the rune punishes every miss made next to the caster."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.slowed(until=When.SAVE_ENDS)
        c.rooted(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod)
        c.slowed(until=When.EONT)
        c.rooted(until=When.EONT)
    if victim is None:
        return

    def punish(ev: Any, v: int = victim) -> None:
        if ev.target == v and c.adjacent(v):
            c.flat(c.str_mod, on=v)

    c.watch(Miss, punish, until=When.ENCOUNTER)


@power(
    "p11375",
    level=1,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(STR, vs=AC),
)
def p11375(c: Cast) -> None:
    """The zone's bonus is handed out on entry and to whoever is already
    standing in it; it runs its duration rather than ending when a creature
    walks back out, which nothing on the surface can say."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(), c.str_mod, dtype=DamageType.RADIANT)
    if not c.first:
        return
    area = c.area()
    zid = c.zone(area, until=When.EONT, sustain=MINOR)
    for who in [c.me, *c.in_squares(area, side="ally")]:
        for defence in DEFENCES:
            c.bonus(defence, 2, on=who, until=When.EONT, kind="power")

    def ward(ev: Any, z: int = zid) -> None:
        if ev.zone != z or ev.actor not in [c.me, *c.allies()]:
            return
        for defence in DEFENCES:
            c.bonus(defence, 2, on=ev.actor, until=When.EONT, kind="power")

    c.watch(ZoneEntered, ward, until=When.EONT)


@power(
    "p11376",
    level=1,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p11376(c: Cast) -> None:
    """The printed choice of damage type is a real choice, so it is offered.
    "This effect ends if the ally ends his turn not adjacent" is dropped --
    an effect cannot end itself on somebody else's geometry."""
    victim = c.target
    kind = c.choose([DamageType.NECROTIC, DamageType.RADIANT], "which rune")
    kind = kind or DamageType.RADIANT
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=kind)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=kind)
    near = c.within(5, side="ally")
    mate = c.choose(near, "the ally the rune binds it to") if near else None
    if mate is None or victim is None:
        return

    def tether(ev: Any, v: int = victim, m: int = mate) -> None:
        if ev.actor != v or ev.ghost:
            return
        if not c.adjacent_to(m, v):
            c.flat(5, dtype=kind, on=v)

    c.watch(TurnEnd, tether, until=When.ENCOUNTER)
