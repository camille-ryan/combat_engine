"""Psion, level 10: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    Ranged,
    Trigger,
    When,
    Window,
    World,
    get,
    power,
    spread,
)

PSIONIC = [Keyword.PSIONIC]

_SPREAD_OUT = ("close_burst", "close_blast", "area_burst")
_SEIZED = (Condition.DAZED, Condition.DOMINATED, Condition.STUNNED)


def _splashed_me(world: World, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return ev.target == me and p is not None and p.reach.kind in _SPREAD_OUT


def _seized_me(world: World, me: int, ev: Any) -> bool:
    return ev.target == me and ev.condition in _SEIZED


@power(
    "p11324",
    level=10,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p11324(c: Cast) -> None:
    """Hover and the altitude limit are not modelled; the fly speed is."""
    c.mode("fly", c.speed_of(), until=When.ENCOUNTER, on=c.me)


@power(
    "p13342",
    level=10,
    cls="psion",
    usage=DAILY,
    action=MOVE,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
)
def p13342(c: Cast) -> None:
    """The square "within 20 squares of you" is where the caster lands, chosen
    through the decider; everybody else then arrives within 3 of it. Doing it
    in that order is what keeps one chosen square for the whole power without
    re-asking per target."""
    if c.first:
        c.teleport(20, who=c.me)
    if c.target is None or c.target == c.me:
        return
    for sq in sorted(spread({c.here}, 3)):
        if c.teleport(25, who=c.target, to=sq):
            break


@power(
    "p13343",
    level=10,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="you are hit by a close or an area attack",
    on=Trigger(Hit, _splashed_me, "you are hit by a close or an area attack"),
)
def p13343(c: Cast) -> None:
    """Halving *one* attack is a one-shot listener on the damage roll, before
    it lands. `c.insubstantial` would halve everything else that reached you
    in the same turn too."""
    spent = [False]

    def soften(ev: DamageRolled) -> None:
        if ev.target == c.me and not spent[0]:
            spent[0] = True
            ev.amount = ev.amount // 2

    c.watch(
        DamageRolled,
        soften,
        until=When.EOT,
        window=Window.BEFORE,
        on=c.me,
        label=c.ref,
    )


@power(
    "p8243",
    level=10,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=PSIONIC,
)
def p8243(c: Cast) -> None:
    victim = c.target
    gain = 5 + c.cha_mod

    def fed(ev: DamageApplied) -> None:
        if (
            ev.target == victim
            and ev.dtype is DamageType.PSYCHIC
            and c.distance(victim) <= 10
        ):
            c.temp_hp(gain, on=c.me)

    c.watch(DamageApplied, fed, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "p8244",
    level=10,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    trigger="an effect dazes, dominates, or stuns you",
    on=Trigger(
        ConditionApplied, _seized_me, "an effect dazes, dominates, or stuns you"
    ),
)
def p8244(c: Cast) -> None:
    """`ConditionApplied` is announced with the condition already on you --
    it names its subject `target`, so `targets_me` rather than `about_me` --
    and the event carries no `cancel`. So "if you save, the effect doesn't
    affect you" is the saving throw itself, which ends the hold it beat."""
    c.save(on=c.me)
