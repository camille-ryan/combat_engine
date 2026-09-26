"""Seeker level 10."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.seeker import (
    PRIMAL,
    free_near,
    rough_for_enemies,
    square_of,
    while_in,
)
from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    Cast,
    CloseBurst,
    Condition,
    Health,
    Keyword,
    Trigger,
    When,
    World,
    power,
    targets_me,
)
from combat_engine.engine.events import DamageApplied, Dropped, TurnStart
from combat_engine.engine.grid import spread
from combat_engine.engine.query import team


def dropped_a_real_one(world: World, me: int, ev: Any) -> bool:
    """"You drop a nonminion enemy to 0 hit points with an attack."

    `query.enemies` filters out the dead, so the side is compared directly --
    by the time this is asked the creature is no longer in it.
    """
    if getattr(ev, "source", None) != me:
        return False
    hp = world.get(ev.actor, Health)
    if hp is not None and hp.max_hp <= 1:
        return False
    return team(world, ev.actor) is not team(world, me)


@power(
    "p11486",
    level=10,
    cls="seeker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.STANCE],
)
def p11486(c: Cast) -> None:
    """Earth and stone are one capability here -- `c.phasing` is moving
    through whatever is in the way -- so the printed pair of speeds collapses
    to it. The stance holds it, and taking another puts it away."""
    form = c.stance(label=c.ref)
    while_in(c, form, c.phasing(on=c.me, until=When.ENCOUNTER))


@power(
    "p11487",
    level=10,
    cls="seeker",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p11487(c: Cast) -> None:
    """The square left behind is the anchor for the return, so it is taken
    before the removal rather than read back afterwards."""
    left = c.here
    reach = c.speed_of()
    c.condition(Condition.REMOVED, on=c.me, until=When.SONT)

    def back(ev: TurnStart) -> None:
        if ev.actor != c.me or left is None:
            return
        spots = [
            sq
            for sq in sorted(spread({left}, reach))
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
        ]
        if spots:
            c.teleport(reach, who=c.me, to=c.choose(spots) or spots[0])

    c.watch(TurnStart, back, until=When.SONT)


@power(
    "p12793",
    level=10,
    cls="seeker",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.TELEPORTATION],
    trigger="you drop a nonminion enemy to 0 hit points with an attack",
    on=Trigger(
        Dropped,
        dropped_a_real_one,
        "you drop a nonminion enemy to 0 hit points with an attack",
    ),
)
def p12793(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    spot = free_near(c, square_of(c, foe))
    if spot:
        c.teleport(20, who=c.me, to=spot[0])


@power(
    "p9523",
    level=10,
    cls="seeker",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.POLYMORPH],
    trigger="you are damaged by an attack",
    on=Trigger(DamageApplied, targets_me, "you are damaged by an attack"),
)
def p9523(c: Cast) -> None:
    """The landing is not written: the form runs out at the start of the next
    turn and nothing in this engine makes a creature fall, so there is no
    fall to be spared."""
    speed = c.speed_of()
    c.form(modes={"fly": speed}, until=When.SONT, revert=None, label=c.ref)
    c.insubstantial(on=c.me, until=When.SONT)
    c.cannot_attack(on=c.me, until=When.SONT)
    c.no_provoke(until=When.SONT)
    c.move(speed)


@power(
    "p9524",
    level=10,
    cls="seeker",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p9524(c: Cast) -> None:
    """The cover half is dropped: cover is traced between two positions at
    the moment of an attack and no held modifier reaches it."""
    rough_for_enemies(c, spread({c.here}, 2), until=When.SUSTAIN, sustain=MINOR)
