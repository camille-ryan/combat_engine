"""Two printed instructions the fighter's later books repeat, written once.

"Shift up to N squares **to a square adjacent to an enemy**" and its walking
twin are a filter on the destination, not a free move: handed to the world's
mover the fighter would happily step into the open, which is the one thing
the row exists to stop. So the squares are picked here and named outright.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    Cast,
    Condition,
    Effect,
    MoveEnd,
    Square,
    When,
    ZoneEntered,
    distance,
    spread,
)
from combat_engine.engine.events import ZoneExited
from combat_engine.engine.movement import walk
from combat_engine.engine.query import adjacent, team
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.zones import Zone


def beside_me(c: Cast, who: int) -> Square | None:
    """A free square next to the fighter, for "to a square adjacent to you".

    The creature's own squares count as free -- a slide of one that ends
    where it started is still a legal answer to the printed line.
    """
    mine = squares_of(c.world, c.me)
    theirs = squares_of(c.world, who)
    options = sorted(
        sq
        for sq in spread(mine, 1) - mine
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and (c.world.grid.occupant(sq) is None or sq in theirs)
    )
    if not options:
        return None
    anchor = min(theirs)
    return min(options, key=lambda sq: (distance(sq, anchor), sq))


def next_to_a_foe(c: Cast) -> frozenset[Square]:
    """Every square that touches an enemy."""
    out: set[Square] = set()
    for foe in c.enemies():
        theirs = squares_of(c.world, foe)
        out |= spread(theirs, 1)
    return frozenset(out)


def close_by_shift(c: Cast, steps: int) -> bool:
    """"Shift up to `steps` squares to a square adjacent to an enemy".

    Standing still satisfies the printed line when the fighter is already
    beside somebody, but it is not what the row is *for* -- so the squares
    on offer are the ones it can actually move to, and staying put is what
    happens when there are none.
    """
    wanted = next_to_a_foe(c)
    here = squares_of(c.world, c.me)
    options = sorted(
        sq for sq in c.world.reachable_squares(c.me, steps) if sq in wanted and sq not in here
    )
    where = c.choose(options, f"{c.ref}: where to end up") if options else None
    return where is not None and c.shift(steps, to=where)


def close_by_walk(c: Cast, steps: int) -> int:
    """The same instruction for a walk, which provokes where a shift does not."""
    wanted = next_to_a_foe(c)
    here = squares_of(c.world, c.me)
    paths = c.world.reachable_paths(c.me, steps)
    options = sorted(sq for sq in paths if sq in wanted and sq not in here)
    where = c.choose(options, f"{c.ref}: where to end up") if options else None
    return walk(c.world, c.me, paths[where]) if where is not None else 0


def ends_when_apart(c: Cast, held: Effect | None, victim: int) -> None:
    """"... until you are no longer adjacent to the target."

    A second ending on top of whatever duration the hold already has, so it
    is a watcher hung on the effect rather than a clock.
    """
    if held is None:
        return
    me = c.me

    def strayed(ev: MoveEnd) -> None:
        if ev.actor in (me, victim) and not adjacent(c.world, me, victim):
            c.world.effects.end(held, "no longer adjacent")

    held.subs.append(c.world.bus.on(MoveEnd, strayed, owner=me))


def stand(c: Cast, who: int) -> bool:
    """Get up. `actions.perform` ends the prone effects and so does this --
    there is no standing flag, only the hold that put the creature down."""
    got_up = False
    for effect in list(c.world.effects.of(who)):
        if Condition.PRONE in effect.conditions:
            c.world.effects.end(effect, "stood up")
            got_up = True
    return got_up


def aura_ring(c: Cast, stance: Effect, *, side: str, give: Any) -> None:
    """An aura 1 that puts modifiers on whoever is inside and takes them off
    again, hung on the stance so taking another ends it.

    The aura's own ending unsubscribes the pair before it announces the
    exits, so the modifiers come off from `on_end` rather than from there.
    """
    me = c.me
    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER)
    held = c.world.get(ring, Zone)
    given: dict[int, list[Effect]] = {}

    def wanted(who: int) -> bool:
        if who == me:
            return False
        same = team(c.world, who) is team(c.world, me)
        return same if side == "ally" else not same

    def cover(who: int) -> None:
        if who in given or not wanted(who):
            return
        given[who] = [e for e in give(who) if e is not None]

    def uncover(who: int) -> None:
        for effect in given.pop(who, []):
            c.world.effects.end(effect, "stepped away")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            cover(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == ring:
            uncover(ev.actor)

    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(ZoneExited, exited),
    ]
    def cleanup() -> None:
        for who in list(given):
            uncover(who)

    def furl() -> None:
        if c.world.get(ring, Zone) is not None:
            c.world.zones.end(ring, "stance ended")

    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
        held.effect.on_end.append(cleanup)
    stance.on_end.append(furl)
    for who in c.world.zones.occupants(ring):
        cover(who)
