"""Runepriest, level 3."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Trigger,
    When,
    both,
    not_me,
    power,
    targets_my_side,
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
    "p11382",
    level=3,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p11382(c: Cast) -> None:
    """The rune clause -- the ally's next attack goes against Reflex if that
    is lower than AC -- is dropped: nothing can move an attack's defence."""
    victim = c.target
    _rune(c, _DESTRUCTION)
    if not c.strike() or victim is None:
        return
    c.damage(c.w(), c.str_mod, dtype=DamageType.RADIANT)
    near = [a for a in c.allies() if c.adjacent_to(victim, a)]
    hidden = c.choose(near, "the ally it loses sight of") if near else None
    if hidden is not None:
        c.invisible(on=hidden, to=victim, until=When.EONT)


@power(
    "p11383",
    level=3,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p11383(c: Cast) -> None:
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    if not destruction or victim is None:
        return

    def opening(ev: Any, v: int = victim) -> None:
        friends = [c.me, *[a for a in c.allies() if c.adjacent_to(v, a)]]
        who = c.choose(friends, "who takes the opening")
        if who is not None:
            c.provoke(who, on=v, why="p11383")

    c.on_attack(opening, by=victim, until=When.EOTNT, once=True)


@power(
    "p11384",
    level=3,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11384(c: Cast) -> None:
    """The bonus counts the ally's allies next to the target when the rune is
    placed; a modifier's value is fixed and cannot be recounted per attack."""
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    if not destruction or victim is None:
        return
    side = [c.me, *c.allies()]
    for ally in c.allies():
        crowd = [x for x in side if x != ally and c.adjacent_to(victim, x)]
        if crowd:
            c.bonus(
                "attack",
                len(crowd),
                on=ally,
                until=When.EONT,
                when=lambda ctx, v=victim: ctx.get("target") == v, kind="power")


@power(
    "p11385",
    level=3,
    cls="runepriest",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=FORT),
    trigger="an enemy makes an attack roll against your ally",
    on=Trigger(
        AttackDeclared,
        both(not_me, targets_my_side),
        "an enemy attacks somebody on your side",
    ),
)
def p11385(c: Cast) -> None:
    """`targets_my_side` is the closest declared predicate: it also fires when
    the attack is aimed at the caster, which the printed trigger excludes."""
    victim = getattr(c.trigger, "attacker", None)
    if victim is None:
        victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if victim is None or not c.strike(on=victim):
        return
    c.blinded(on=victim, until=When.EOT)
    if destruction:
        c.flat(c.con_mod, dtype=DamageType.RADIANT, on=victim)


@power(
    "p15990",
    level=3,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p15990(c: Cast) -> None:
    protection = _rune(c, _PROTECTION)
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.push(1)
    if not c.first:
        return
    bonus = c.wis_mod if protection else 0
    c.save(on=c.me, bonus=bonus)
    near = c.within(5, side="team")
    mate = c.choose(near, "the ally who shakes it off with you") if near else None
    if mate is not None:
        c.save(on=mate, bonus=bonus)
