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
    REF,
    STANDARD,
    STR,
    Attack,
    AttackDeclared,
    AttackRolled,
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
from combat_engine.engine.query import defence as defence_of

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
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.RUNIC],
    attack=Attack(STR, vs=AC),
)
def p11382(c: Cast) -> None:
    """**The rune clause is written now, and "nothing can move an attack's
    defence" was false.** `c.attacks_defence` is the standing form of
    exactly that sentence -- its docstring opens *"your weapon attacks
    target Reflex instead of AC"* and notes that "the engine has always
    allowed this and the rows said it did not". `c.retarget_defence` is
    the in-flight form, for an interrupt. #1341.

    Three parts of the printed clause, each its own argument rather than
    folded together:

    * "**if the ally's next attack ... is against AC**" is `from_=AC`,
      so an attack already aimed elsewhere is left alone;
    * "**if that defence is lower**" is asked of the target at read time,
      because a Reflex that is only lower while something else holds
      should stop qualifying when that ends;
    * "**against the target**" is the `when=` gate, so the ally's swing at
      somebody else keeps its own defence.

    "**Next**" is latched by ending the hold on the ally's first attack
    roll -- `c.attacks_defence` takes no `once=`, and without the latch
    the clause would move every attack the ally made until the end of the
    turn rather than one.
    """
    victim = c.target
    destruction = _rune(c, _DESTRUCTION)
    if not c.strike() or victim is None:
        return
    c.damage(c.w(), c.str_mod, dtype=DamageType.RADIANT)
    near = [a for a in c.allies() if c.adjacent_to(victim, a)]
    hidden = c.choose(near, "the ally it loses sight of") if near else None
    if hidden is None:
        return
    c.invisible(on=hidden, to=victim, until=When.EONT)
    if not destruction:
        return
    moved = c.attacks_defence(
        REF,
        from_=AC,
        on=hidden,
        until=When.EONT,
        when=lambda ctx: ctx.get("target") == victim
        and defence_of(c.world, victim, REF)
        < defence_of(c.world, victim, AC),
    )
    if moved is None:
        return

    def spend(ev: AttackRolled) -> None:
        if ev.attacker == hidden:
            c.world.effects.end(moved, "the next attack was made")

    moved.subs.append(c.world.bus.on(AttackRolled, spend, owner=c.me))


@power(
    "p11383",
    level=3,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING, Keyword.RUNIC],
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
    keywords=[*DIVINE_WEAPON, Keyword.RUNIC],
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
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.RUNIC],
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
    keywords=[*DIVINE_WEAPON, Keyword.FEAR, Keyword.RUNIC],
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
