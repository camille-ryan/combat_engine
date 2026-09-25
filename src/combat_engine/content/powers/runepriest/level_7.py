"""Runepriest, level 7."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    TurnEnd,
    When,
    by_opportunity,
    power,
)

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]

_DESTRUCTION = "rune:destruction"
_PROTECTION = "rune:protection"


def _in_rune(c: Cast, which: str) -> bool:
    """Is the caster in that rune state? An unset state counts as in it."""
    held = c.world.effects.stance_of(c.me)
    return held is None or which in held.label


def _rune(c: Cast, which: str) -> bool:
    """Read the rune state, then switch to the other one, as using a runic
    power does. The switch waits for the last target so every target of a
    burst reads the same state."""
    here = _in_rune(c, which)
    if c.last:
        c.stance(label=_PROTECTION if which == _DESTRUCTION else _DESTRUCTION)
    return here


@power(
    "p11394",
    level=7,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=REF),
)
def p11394(c: Cast) -> None:
    """The second half of this row is a power in its own right on the page,
    with its own id; here it is the same attack line rolled from a square in
    the target's space -- `from_` -- when the target attacks. Its own rune
    clause is read then, by which time the state has switched."""
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike() or victim is None:
        return
    c.damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)
    if destruction:
        c.flat(c.con_mod, dtype=DamageType.LIGHTNING)

    def crack(ev: Any, v: int = victim) -> None:
        protection = _in_rune(c, _PROTECTION)
        for e in c.within(1, of=v, side="enemy"):
            if e == v:
                continue
            if c.strike(on=e, from_=v):
                c.damage(0, c.str_mod, dtype=DamageType.LIGHTNING, on=e)
                if protection:
                    c.slide(2, on=e)

    c.on_attack(crack, by=victim, until=When.EONT, once=True)


@power(
    "p11396",
    level=7,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE],
    attack=Attack(STR, vs=AC),
)
def p11396(c: Cast) -> None:
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod, dtype=DamageType.FIRE)
    if not destruction or victim is None:
        return

    def sear(ev: Any, v: int = victim) -> None:
        if by_opportunity(c.world, c.me, ev):
            c.flat(5 + c.con_mod, dtype=DamageType.FIRE, on=v)

    c.on_attack(sear, by=victim, until=When.EONT)


@power(
    "p11397",
    level=7,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=WILL),
)
def p11397(c: Cast) -> None:
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    if not destruction or victim is None:
        return

    def shove(ev: Any, v: int = victim) -> None:
        if ev.ghost or ev.actor not in c.allies():
            return
        if not c.adjacent_to(v, ev.actor):
            return
        if c.may("push it a square", who=ev.actor):
            c.push(1, on=v, by=ev.actor)

    c.watch(TurnEnd, shove, until=When.EONT)


@power(
    "p11398",
    level=7,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=WILL),
)
def p11398(c: Cast) -> None:
    """"The first time any of your allies hits" is spent by hand rather than
    with `once`, which would be spent by the first hit on anybody."""
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    if not destruction or victim is None:
        return
    spent: list[int] = []

    def turn(ev: Any, v: int = victim) -> None:
        if spent or ev.target != v or ev.attacker not in c.allies():
            return
        foes = [e for e in c.within(1, of=v, side="enemy") if e != v]
        pick = c.choose(foes, "whom it turns on") if foes else None
        if pick is None:
            return
        spent.append(1)
        c.grant_attack(v, on=pick)

    c.watch(Hit, turn, until=When.EONT)
