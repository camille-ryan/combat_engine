"""Swordmage, level 0: the three aegis marks.

All three are the same row with a different punishment, so the shared half
is written once. Two parts of it are worth naming.

**The -2 is free.** `resolve._mark_penalty` already charges two to a marked
creature that leaves its marker out of the attack, and it judges that per
*power use* rather than per target -- which is the printed rule and is
exactly the printed aegis penalty. So `c.mark` is the whole of that clause
and a hand-rolled penalty on top would double it.

**"Until you use this power against another target"** is longer than any
duration in the enum, so the mark is taken for the encounter and `_release`
ends the previous one by hand -- the same shape as the avenger's oath.

The immediate action each punishment costs is not modelled: the engine has
no immediate-action budget, so each is latched to once a round, which is
what having one immediate action a round comes to.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.builds import on_leg
from combat_engine.engine import (
    AT_WILL,
    MINOR,
    ONE_CREATURE,
    Cast,
    CloseBurst,
    DamageRolled,
    Hit,
    Keyword,
    When,
    power,
)
from combat_engine.engine.query import distance_between

from . import beside

ARCANE = [Keyword.ARCANE]
ARCANE_TELEPORT = [Keyword.ARCANE, Keyword.TELEPORTATION]


def _release(c: Cast) -> None:
    """End whichever creature this aegis was on before."""
    for who in c.suffering(c.ref, include_self=True):
        for effect in list(c.world.effects.of(who)):
            if effect.source == c.me and c.ref in effect.label:
                c.world.effects.end(effect, "a new aegis")


def _aegis(c: Cast) -> int | None:
    """Mark the target for the fight, releasing the last one."""
    victim = c.target
    if victim is None:
        return None
    _release(c)
    c.mark(on=victim, until=When.ENCOUNTER)
    return victim


def _left_me_out(c: Cast, ev: Any, victim: int) -> bool:
    """The printed condition on all three punishments."""
    if getattr(ev, "attacker", None) != victim:
        return False
    if getattr(ev, "target", None) == c.me:
        return False
    return distance_between(c.world, c.me, victim) <= 10


@power(
    "p3322",
    level=0,
    cls="swordmage",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    requires=on_leg("assault"),
    keywords=ARCANE_TELEPORT,
)
def p3322(c: Cast) -> None:
    """"If no unoccupied space exists adjacent to the target, you can't use
    this immediate reaction" is why the square is found before anything
    moves: `beside` returning None is the printed refusal."""
    victim = _aegis(c)
    if victim is None:
        return
    me, last = c.me, {"round": -1}

    def punish(ev: Hit) -> None:
        if last["round"] == c.world.round or not _left_me_out(c, ev, victim):
            return
        landing = beside(c, victim)
        if landing is None or not c.may("answer the aegis", who=me):
            return
        last["round"] = c.world.round
        c.teleport(20, to=landing)
        c.basic(on=victim)

    c.watch(Hit, punish, until=When.ENCOUNTER, on=me, label=f"{c.ref} answer")


@power(
    "p3323",
    level=0,
    cls="swordmage",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    requires=on_leg("shielding"),
    keywords=ARCANE,
)
def p3323(c: Cast) -> None:
    """`DamageRolled` is the interrupt window the printed reduction needs --
    the number exists and has not been dealt. "To any one creature" is the
    packet being answered, which is one creature by construction."""
    victim = _aegis(c)
    if victim is None:
        return
    me, last = c.me, {"round": -1}
    step = 15 if c.level >= 21 else 10 if c.level >= 11 else 5

    def soften(ev: DamageRolled) -> None:
        if last["round"] == c.world.round or ev.source != victim:
            return
        if ev.target == me or distance_between(c.world, me, victim) > 10:
            return
        if not c.may("blunt the blow", who=me):
            return
        last["round"] = c.world.round
        c.reduce(step + c.con_mod, ev)

    c.watch(DamageRolled, soften, until=When.ENCOUNTER, on=me, label=f"{c.ref} answer")


@power(
    "p5736",
    level=0,
    cls="swordmage",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    requires=on_leg("ensnarement"),
    keywords=ARCANE_TELEPORT,
)
def p5736(c: Cast) -> None:
    """This one teleports the enemy rather than the swordmage, so the square
    wanted is one next to *me*; `beside` with no argument gives it. The
    printed rule that the combat advantage does not happen either when
    there is no such square falls out of the same guard."""
    victim = _aegis(c)
    if victim is None:
        return
    me, last = c.me, {"round": -1}

    def haul(ev: Hit) -> None:
        if last["round"] == c.world.round or not _left_me_out(c, ev, victim):
            return
        landing = beside(c)
        if landing is None or not c.may("haul it back", who=me):
            return
        last["round"] = c.world.round
        c.teleport(20, who=victim, to=landing)
        c.grants_advantage(on=victim, to="team", until=When.EONT)

    c.watch(Hit, haul, until=When.ENCOUNTER, on=me, label=f"{c.ref} answer")
