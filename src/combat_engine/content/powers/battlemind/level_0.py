"""Battlemind, level 0: the class features.

Four of the seven are free or immediate actions off a printed Trigger, so
each declares one -- `trigger=` alone is prose nothing reads. The two that
watch a move watch `MoveStart`: the printed line asks where the enemy is
*before* it goes, and by `MoveEnd` it is no longer adjacent.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    ENCOUNTER,
    FREE,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    Attack,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    MoveStart,
    Relation,
    Trigger,
    TurnStart,
    When,
    World,
    about_me,
    enemy_within,
    power,
    targets_me,
)
from combat_engine.engine.query import adjacent, team

from . import PSIONIC, teleport_beside

_WITHIN_10 = enemy_within(10)


def _mine(world: World, me: int, who: int | None) -> bool:
    """An enemy of mine that I have marked."""
    return (
        who is not None
        and who != me
        and team(world, who) is not team(world, me)
        and world.relations.holds(Relation.MARKED_BY, me, who)
    )


def _marked_shifts(world: World, me: int, ev: MoveStart) -> bool:
    return ev.kind_ == "shift" and _mine(world, me, ev.actor) and adjacent(world, me, ev.actor)


def _marked_hurts_ally(world: World, me: int, ev: DamageApplied) -> bool:
    """A marked neighbour dealt damage to somebody on my side who is not me."""
    victim = ev.target
    return (
        ev.amount > 0
        and victim != me
        and team(world, victim) is team(world, me)
        and _mine(world, me, ev.source)
        and adjacent(world, me, ev.source)
    )


def _first_turn(world: World, me: int, ev: TurnStart) -> bool:
    """An enemy's first turn of the fight, read as its turn in round 1."""
    return ev.round == 1 and _WITHIN_10(world, me, ev)


@power(
    "p10438",
    level=0,
    cls="battlemind",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=PSIONIC,
)
def p10438(c: Cast) -> None:
    """Base form. Augment 1 (one or two targets) is dropped: no power points.
    "Until you use this power again" is left to the mark's own duration --
    nothing can reach back and end the mark the last use laid."""
    c.mark(until=When.ENCOUNTER)


@power(
    "p10439",
    level=0,
    cls="battlemind",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    once_per_round=True,
    trigger="an adjacent enemy marked by you shifts",
    on=Trigger(MoveStart, _marked_shifts, "an adjacent enemy marked by you shifts"),
)
def p10439(c: Cast) -> None:
    c.shift(1)


@power(
    "p10440",
    level=0,
    cls="battlemind",
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.PSYCHIC, Keyword.FORCE],
    trigger="an adjacent enemy marked by you damages your ally with an attack "
    "that does not include you",
    on=Trigger(
        DamageApplied,
        _marked_hurts_ally,
        "an adjacent enemy marked by you damages your ally",
    ),
)
def p10440(c: Cast) -> None:
    """`DamageApplied` names its dealer `source`, which nothing the dispatcher
    reads picks up, so the target is taken off the event rather than trusted
    to the default aim. The printed line is force *and* psychic in one
    instance; a damage instance carries one type, so it lands as force."""
    ev = c.trigger
    foe = getattr(ev, "source", None)
    if foe is None:
        return
    c.flat(ev.amount, dtype=DamageType.FORCE, on=foe)


@power(
    "p10441",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p10441(c: Cast) -> None:
    """Usable while surprised is the printed Special; a free action off a
    declared trigger is not blocked by the condition, so nothing is needed."""
    c.move(3 + c.cha_mod)


@power(
    "p11155",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    trigger="an attack hits or misses you for the first time this encounter",
    on=[
        Trigger(Hit, targets_me, "an attack hits you"),
        Trigger(Miss, targets_me, "an attack misses you"),
    ],
)
def p11155(c: Cast) -> None:
    """"The first time during an encounter" is the once-per-encounter usage."""
    c.resist(3 + c.wis_mod, until=When.EONT)


@power(
    "p12418",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=PSIONIC,
    trigger="an enemy starts its first turn during an encounter",
    on=Trigger(TurnStart, _first_turn, "an enemy starts its first turn"),
)
def p12418(c: Cast) -> None:
    c.pull(max(0, c.cha_mod))
    c.mark(until=When.EONT)


@power(
    "p13024",
    level=0,
    cls="battlemind",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
    trigger="an enemy hits or misses you for the first time this encounter",
    on=[
        Trigger(Hit, targets_me, "an enemy hits you"),
        Trigger(Miss, targets_me, "an enemy misses you"),
    ],
)
def p13024(c: Cast) -> None:
    """The printed Special -- swinging at an enemy outside your reach -- is
    not written: the only header field that waives reach is `charges`, and
    this is not a charge. So the row is offered when the attacker is in
    reach, which a melee attacker always is."""
    foe = getattr(c.trigger, "attacker", None) or c.target
    if foe is None:
        return
    if c.strike(on=foe):
        c.damage(c.w(), c.con_mod, on=foe)
        teleport_beside(c, c.me, foe)
