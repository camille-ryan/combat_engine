"""Barbarian, level 0: the class features.

Four of the five answer the same printed Trigger -- "your attack reduces an
enemy to 0 hit points" -- which is `Dropped` with `by_me`: the event carries
`source`, so the sentence is declarable rather than approximated off
`DamageApplied`, which announces before the creature is down.

`p15848` is the odd one. It belongs to a defender aura the chassis has no
ref for, so "an enemy subject to your defender aura" is written as "an enemy
standing in an aura of mine". Its shift half is declared on `MoveStart`, not
`MoveEnd`: the enemy has to still be inside the aura for the row to be true,
and an opportunity action resolves in the interrupt window anyway.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.query import team

PRIMAL = [Keyword.PRIMAL]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
DEFENCES = (AC, FORT, REF, WILL)
DROPPED = Trigger(Dropped, by_me, "your attack reduces an enemy to 0 hit points")


def _in_my_aura(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None) or getattr(ev, "attacker", None)
    if who is None or who == me:
        return False
    return any(
        z.owner == me and z.aura and who in world.zones.occupants(zid)
        for zid, z in world.zones.all()
    )


def _shifts_in_my_aura(world: World, me: int, ev: MoveStart) -> bool:
    return ev.kind_ == "shift" and _in_my_aura(world, me, ev)


def _swings_past_me(world: World, me: int, ev: AttackDeclared) -> bool:
    """...and makes an attack that targets an ally of yours, not you."""
    if not _in_my_aura(world, me, ev) or not leaves_me_out(world, me, ev):
        return False
    return team(world, ev.target) is team(world, me)


@power(
    "p15848",
    level=0,
    cls="barbarian",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="an enemy in your aura shifts, or attacks an ally of yours and not you",
    on=(
        Trigger(MoveStart, _shifts_in_my_aura, "an enemy in your aura shifts"),
        Trigger(AttackDeclared, _swings_past_me, "it attacks an ally of yours, not you"),
    ),
)
def p15848(c: Cast) -> None:
    """The printed "...or an ally who has an active defender aura" is dropped:
    nothing on the chassis says which allies have one."""
    ev = c.trigger
    victim = getattr(ev, "actor", None) or getattr(ev, "attacker", None)
    if victim is None:
        return
    dice = 1 + (c.level >= 11) + (c.level >= 21)
    if c.basic(on=victim):
        c.damage(f"{dice}d8", on=victim)
    elif c.level >= 21:
        c.half_damage(f"{dice}d8", on=victim)


@power(
    "p4809",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="your attack reduces an enemy to 0 hit points",
    on=DROPPED,
)
def p4809(c: Cast) -> None:
    fallen = getattr(c.trigger, "actor", None)
    prey = [e for e in c.enemies() if e != fallen]
    if prey:
        c.charge_at(c.choose(prey, "who to run at"))


@power(
    "p4932",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.FEAR],
    trigger="your attack reduces an enemy to 0 hit points",
    on=DROPPED,
)
def p4932(c: Cast) -> None:
    for d in DEFENCES:
        c.penalty(d, 2, until=When.EONT)


@power(
    "p5249",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=PRIMAL_WEAPON,
    trigger="your attack reduces an enemy to 0 hit points",
    on=DROPPED,
)
def p5249(c: Cast) -> None:
    """No target in the header: the shift comes first and the victim is
    chosen from where it leaves you, so letting the dispatcher aim the row at
    the creature that just fell would be aiming it at a corpse."""
    c.shift(2)
    near = [e for e in c.within(1, side="enemy") if c.can_see(e)]
    if near:
        c.damage(c.w(hand="off"), on=c.choose(near, "who the off hand catches"))


@power(
    "p9556",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.FEAR],
    trigger="your attack reduces an enemy to 0 hit points",
    on=DROPPED,
)
def p9556(c: Cast) -> None:
    c.push(1)
