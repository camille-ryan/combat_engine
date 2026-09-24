"""Moving, and everything that watches something move.

Adjacency is **derived here and nowhere else**. Every step diffs the set of
creatures the mover is next to and emits `AdjacencyGained` / `AdjacencyLost`,
so opportunity attacks, aura entry and exit, and "when a creature moves
adjacent to you" all hang off two events instead of each re-scanning the
board. Anything that cares about being next to something subscribes to those
two and is correct for free.

An opportunity attack interrupts the move, so the window is opened *while the
mover is still in the square it is leaving*. Resolve it after the step and
the attack lands in the wrong place.

**The board is two-dimensional even though flight is not.** A creature with a
mode that goes over or under the ground -- flying, swimming, burrowing --
passes straight through squares an enemy is standing in, and only needs a
free square to *land* in. That is the whole of the third dimension here: a
transit right, not a coordinate. Provoking is untouched by it, because
passing through a square never provoked in the first place; leaving a
threatened one does, and it still does in the air.

A flyer **lands at the end of its turn**. So the free-square requirement is
not checked per move -- a creature may spend a move action and stop over an
enemy's head, then spend another -- it is checked once, when the turn ends,
and `settle` puts anything still overlapping into the nearest square it fits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .components import Position
from .events import (
    AdjacencyGained,
    AdjacencyLost,
    EnterSquare,
    ForcedMove,
    LeaveSquare,
    Moved,
    MoveEnd,
    MoveStart,
    OpportunityWindow,
)
from .grid import Square, distance, footprint, neighbours, spread
from .query import adjacent, alive, can_move, creatures, enemies, squares
from .types import Forced, Size

if TYPE_CHECKING:
    from .ecs import World

#: Moves that never provoke an opportunity attack.
_SAFE = {"shift", "teleport", "push", "pull", "slide", "place"}

#: Modes that leave the ground, and so pass over whoever is standing on it.
#: Teleport is not one of them -- it has no path to pass along, so it has to
#: arrive somewhere it fits.
OVERHEAD = {"fly", "swim", "burrow"}


def place(world: World, eid: int, square: Square) -> None:
    """Put a creature on the board without any of this firing. Setup only."""
    pos = world.need(eid, Position)
    pos.square = square
    world.grid.lift(eid)
    world.grid.place(eid, footprint(square, pos.size))


def _neighbours(world: World, eid: int) -> set[int]:
    return {o for o in creatures(world) if o != eid and adjacent(world, eid, o)}


def step(world: World, eid: int, to: Square, *, kind: str = "walk", mode: str = "walk") -> bool:
    """Move one square. Returns False if the square could not be entered.

    The order matters: leaving is announced from the old square, the
    opportunity window opens while the mover is still standing there, and
    only then does the mover actually arrive.
    """
    pos = world.get(eid, Position)
    if pos is None:
        return False
    target = footprint(to, pos.size)
    overhead = mode in OVERHEAD
    if not _clear(world, eid, target, overhead=overhead):
        return False

    before = _neighbours(world, eid)
    from_ = pos.square

    for sq in sorted(pos.squares):
        world.bus.emit(LeaveSquare(actor=eid, square=sq))

    if kind not in _SAFE:
        after_reach = spread(target, 1)
        leaving = {o for o in before if not (after_reach & squares(world, o))}
        for other in sorted(leaving):
            if other in enemies(world, eid):
                world.bus.emit(OpportunityWindow(actor=other, provoker=eid, why="moved away"))

    world.grid.lift(eid)
    pos.square = to
    if not _occupied(world, eid, target):
        # Overhead and directly above somebody: stay out of the occupancy
        # index until `settle` puts the creature down at the end of its turn.
        world.grid.place(eid, target)

    for sq in sorted(target):
        world.bus.emit(EnterSquare(actor=eid, square=sq))

    world.bus.emit(Moved(actor=eid, from_=from_, to=to))

    after = _neighbours(world, eid)
    for other in sorted(after - before):
        world.bus.emit(AdjacencyGained(actor=eid, other=other))
        world.bus.emit(AdjacencyGained(actor=other, other=eid))
    for other in sorted(before - after):
        world.bus.emit(AdjacencyLost(actor=eid, other=other))
        world.bus.emit(AdjacencyLost(actor=other, other=eid))
    return pos.square != from_


def _clear(
    world: World,
    eid: int,
    target: set[Square] | frozenset[Square],
    *,
    overhead: bool = False,
) -> bool:
    """Can `eid` be in these squares? Terrain always blocks; a creature only
    blocks somebody moving along the ground."""
    for sq in target:
        if not world.grid.passable(sq):
            return False
        who = world.grid.occupant(sq)
        if who is not None and who != eid and not overhead:
            return False
    return True


def _occupied(world: World, eid: int, target: set[Square] | frozenset[Square]) -> bool:
    return any(
        (who := world.grid.occupant(sq)) is not None and who != eid for sq in target
    )


def mode_of(world: World, eid: int, mode: str | None) -> str:
    """Resolve the mode a creature is moving with, defaulting to its best.

    A creature that can fly flies, because that is what makes its printed
    speed line mean anything without every caller having to ask.
    """
    from .components import Movement

    if mode is not None:
        return mode
    mv = world.get(eid, Movement)
    if mv is None:
        return "walk"
    for candidate in ("fly", "swim", "burrow"):
        if mv.modes.get(candidate):
            return candidate
    return "walk"


def walk(
    world: World, eid: int, path: list[Square], *, kind: str = "walk", mode: str | None = None
) -> int:
    """Walk a path one square at a time. Returns how many squares were covered.

    Difficult terrain costs an extra square, so the budget is spent here
    rather than checked by the caller.
    """
    if not can_move(world, eid):
        return 0
    mode = mode_of(world, eid, mode)
    world.bus.emit(MoveStart(actor=eid, kind_=kind))
    spent = 0
    for sq in path:
        if not step(world, eid, sq, kind=kind, mode=mode):
            break
        spent += 2 if sq in world.difficult(eid) else 1
    pos = world.get(eid, Position)
    world.bus.emit(MoveEnd(actor=eid, at=pos.square if pos else (0, 0)))
    return spent


def risk_along(world: World, eid: int, path: list[Square]) -> str:
    """What walking this path would cost you that is not movement.

    Answered here because it is a rule, and the page is not allowed to know
    any. It asks the same two questions `step` asks while it is moving --
    who am I leaving, and what am I walking into -- without moving anybody.

    Returns a short reason, or "" when the way is clear. A reason rather
    than a flag because the interface shows it: "provokes" and "crosses a
    zone" are different warnings and a player weighs them differently.
    """
    pos = world.get(eid, Position)
    if pos is None or not path:
        return ""

    foes = [o for o in enemies(world, eid) if alive(world, o)]
    where = {o: squares(world, o) for o in foes}
    at = pos.square
    hostile: set[Square] = set()
    for _zid, zone in world.zones.all():
        if zone.owner in where:
            hostile |= zone.squares

    for nxt in path:
        here_reach = spread(footprint(at, pos.size), 1)
        next_space = footprint(nxt, pos.size)
        # Leaving a square somebody threatens, and not staying in their
        # reach, is what opens the window -- the same test `step` makes.
        for foe in foes:
            if (here_reach & where[foe]) and not (spread(next_space, 1) & where[foe]):
                return "provokes an opportunity attack"
        if next_space & hostile:
            return "walks into an enemy zone"
        at = nxt
    return ""


def settle(world: World, eid: int) -> bool:
    """Put a creature down at the end of its turn.

    A flyer may stop over an enemy's head mid-turn; it may not still be there
    when the turn ends. The nearest square it fits in wins, and ties are
    broken in sorted order so two runs of a seed land it in the same place.
    """
    pos = world.get(eid, Position)
    if pos is None or _clear(world, eid, pos.squares):
        if pos is not None:
            world.grid.place(eid, pos.squares)
        return False
    here = pos.square
    for radius in range(1, max(world.grid.width, world.grid.height)):
        ring = sorted(
            sq
            for sq in spread({here}, radius)
            if distance(sq, here) == radius and _clear(world, eid, footprint(sq, pos.size))
        )
        if ring:
            world.bus.emit(MoveStart(actor=eid, kind_="land"))
            step(world, eid, ring[0], kind="place", mode="walk")
            world.bus.emit(MoveEnd(actor=eid, at=ring[0]))
            return True
    return False


def shift(world: World, eid: int, to: Square, *, mode: str | None = None) -> bool:
    """A shift is a move that does not provoke. One square unless a power says otherwise."""
    from .query import can_shift

    if not can_shift(world, eid):
        return False
    world.bus.emit(MoveStart(actor=eid, kind_="shift"))
    moved = step(world, eid, to, kind="shift", mode=mode_of(world, eid, mode))
    pos = world.get(eid, Position)
    world.bus.emit(MoveEnd(actor=eid, at=pos.square if pos else (0, 0)))
    return moved


def teleport(world: World, eid: int, to: Square) -> bool:
    world.bus.emit(MoveStart(actor=eid, kind_="teleport"))
    moved = step(world, eid, to, kind="teleport", mode="walk")
    pos = world.get(eid, Position)
    world.bus.emit(MoveEnd(actor=eid, at=pos.square if pos else (0, 0)))
    return moved


# -- forced movement --------------------------------------------------------


def forced(
    world: World,
    source: int,
    target: int,
    how: Forced,
    amount: int,
    *,
    anchor: Square | None = None,
    to: Square | None = None,
) -> int:
    """Push, pull or slide `target` up to `amount` squares.

    `anchor` is what the movement is measured against. It defaults to the
    source's square, which is right for most powers and wrong for the ones
    that say "away from the zone" or "toward the ally" -- those pass their
    own, which is why this is a parameter rather than a lookup.

    Forced movement never provokes, and stops dead the first square it cannot
    enter rather than trying to route around it.
    """
    pos = world.get(target, Position)
    if pos is None or amount <= 0:
        return 0
    if anchor is None:
        src = world.get(source, Position)
        anchor = src.square if src else pos.square

    world.bus.emit(ForcedMove(source=source, target=target, how=how, squares=amount))
    if to is not None:
        # A row that names the square it wants. Still one step at a time, so
        # everything that watches a move still sees each of them.
        return sum(
            1 for _ in range(amount) if step(world, target, to, kind=how.value)
        )
    moved = 0
    for _ in range(amount):
        nxt = _forced_square(world, source, target, anchor, how)
        if nxt is None or not step(world, target, nxt, kind=how.value):
            break
        moved += 1
    return moved


def forced_squares(
    world: World, target: int, anchor: Square, how: Forced
) -> list[Square]:
    """Every square this step of a forced move could legally go to.

    Push must end further from the anchor, pull must end nearer, and a slide
    may go anywhere. Directly away from the anchor there are normally
    **three** of them -- the straight step and the two diagonals either side
    -- and which one is taken is the pusher's choice, not a detail. Driving
    somebody into a wall, off a ledge, or out of their ally's reach is the
    whole reason to take a power that pushes.
    """
    pos = world.get(target, Position)
    if pos is None:
        return []
    here = pos.square
    now = distance(here, anchor)
    out: list[Square] = []
    for cand in neighbours(here):
        then = distance(cand, anchor)
        ok = {
            Forced.PUSH: then > now,
            Forced.PULL: then < now,
            Forced.SLIDE: True,
        }[how]
        if ok and _clear(world, target, footprint(cand, pos.size)):
            out.append(cand)
    return sorted(out)


def _forced_square(
    world: World, source: int, target: int, anchor: Square, how: Forced
) -> Square | None:
    """Where this step of a forced move goes, asking whoever is pushing.

    The choice belongs to the creature applying the movement, so it goes
    through `world.decide` like any other. The first version picked the
    straightest square and never asked, which quietly turned every push in
    the game into a single fixed line.
    """
    options = forced_squares(world, target, anchor, how)
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    return world.decide(source, how.value, options, f"{how.value} to which square")


# -- reachability -----------------------------------------------------------


def reachable(
    world: World, eid: int, budget: int, *, mode: str | None = None
) -> dict[Square, list[Square]]:
    """Every square reachable within `budget`, with a path to each.

    Dijkstra over the eight steps, charging two for difficult terrain, and
    **ranked by three things in order**: what it costs, what it costs you
    that is not movement, and how straight it looks.

    The third matters more than it sounds. Distance here is Chebyshev, so a
    diagonal costs the same as a step sideways and a great many routes tie
    on price. Whichever the search happened to reach first then won -- and
    since the neighbours were walked in sorted order that was reliably the
    one bearing up and left, so the drawn path wandered out to a corner and
    came back rather than going where the crow goes. Nothing was wrong with
    it except that no player would ever have chosen it.

    A flyer's search passes over occupied squares but will not offer one as a
    destination, since it has to come down at the end of the turn anyway.
    """
    pos = world.get(eid, Position)
    if pos is None or budget <= 0:
        return {}
    overhead = mode_of(world, eid, mode) in OVERHEAD
    rough = world.difficult(eid)
    start = pos.square
    threat = _threatened_from(world, eid)

    # (movement spent, squares walked under threat). Lexicographic, so a
    # safer route wins outright and only a tie on safety is settled by cost.
    best: dict[Square, tuple[int, int]] = {start: (0, 0)}
    came: dict[Square, list[Square]] = {start: []}
    frontier = [start]
    while frontier:
        frontier.sort(key=lambda s: best[s])
        here = frontier.pop(0)
        spent, risked = best[here]
        for nxt in sorted(neighbours(here)):
            if not _clear(world, eid, footprint(nxt, pos.size), overhead=overhead):
                continue
            step_cost = 2 if nxt in rough else 1
            score = (spent + step_cost, risked + _provokes_step(threat, here, nxt, pos.size))
            if score[0] > budget:
                continue
            known = best.get(nxt)
            if known is not None and score > known:
                continue
            if known is not None and score == known:
                came[nxt].append(here)      # another equally good way in
                continue
            best[nxt] = score
            came[nxt] = [here]
            frontier.append(nxt)

    paths = {sq: _straightest(start, sq, came) for sq in came if sq != start}
    if overhead:
        paths = {
            sq: path
            for sq, path in paths.items()
            if _clear(world, eid, footprint(sq, pos.size))
        }
    return paths


def _threatened_from(world: World, eid: int) -> dict[int, frozenset[Square]]:
    """Which squares each living enemy is standing in, for the threat test."""
    return {
        foe: squares(world, foe)
        for foe in enemies(world, eid)
        if alive(world, foe)
    }


def _provokes_step(
    threat: dict[int, frozenset[Square]], here: Square, nxt: Square, size: Size
) -> int:
    """Does stepping from one square to the next open an opportunity window?

    The same test `step` makes while moving: somebody adjacent before, and
    out of reach after.
    """
    if not threat:
        return 0
    before = spread(footprint(here, size), 1)
    after = spread(footprint(nxt, size), 1)
    return int(any(
        (before & where) and not (after & where) for where in threat.values()
    ))


def _straightest(start: Square, dest: Square, came: dict[Square, list[Square]]) -> list[Square]:
    """Rebuild one of the equally good routes -- the one nearest the line.

    Every predecessor recorded for a square reached it for the same price
    and the same risk, so the choice between them is free and may as well
    be made on looks. Walked backwards from the destination, because only
    then is there a line to be near: the straight one from start to *here*.
    """
    path: list[Square] = []
    node = dest
    seen = {dest}
    while node != start:
        options = [p for p in came.get(node, ()) if p not in seen]
        if not options:
            break
        node = min(options, key=lambda p: (_off_line(start, dest, p), p))
        seen.add(node)
        path.append(node)
    path.reverse()
    return [*path[1:], dest] if path and path[0] == start else [*path, dest]


def _off_line(a: Square, b: Square, p: Square) -> int:
    """Twice the triangle's area -- how far `p` sits off the line `a`-`b`.

    An integer, and monotonic in the perpendicular distance, which is all a
    tie-break needs. No square roots and no floats to compare.
    """
    return abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1]))


def costs(world: World, eid: int, budget: int, *, mode: str | None = None) -> dict[Square, int]:
    """What reaching each square actually costs, in squares of movement.

    Same search as `reachable`, reported the other way round. A caller that
    wants to know *why* a square is expensive -- difficult terrain, a detour
    round a wall -- compares this against the straight-line distance.
    """
    pos = world.get(eid, Position)
    if pos is None:
        return {}
    rough = world.difficult(eid)
    out: dict[Square, int] = {}
    for sq, path in reachable(world, eid, budget, mode=mode).items():
        out[sq] = sum(2 if step in rough else 1 for step in path)
    return out
