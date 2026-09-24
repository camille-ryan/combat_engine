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
    MoveEnd,
    MoveStart,
    OpportunityWindow,
)
from .grid import Square, distance, footprint, spread
from .query import adjacent, can_move, creatures, enemies, squares
from .types import Forced

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
        spent += 2 if sq in world.difficult() else 1
    pos = world.get(eid, Position)
    world.bus.emit(MoveEnd(actor=eid, at=pos.square if pos else (0, 0)))
    return spent


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
    if not can_move(world, eid):
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
    moved = 0
    for _ in range(amount):
        nxt = _forced_square(world, target, anchor, how)
        if nxt is None or not step(world, target, nxt, kind=how.value):
            break
        moved += 1
    return moved


def _forced_square(world: World, target: int, anchor: Square, how: Forced) -> Square | None:
    """The next square a forced move goes to.

    Push must end further from the anchor, pull must end nearer, and a slide
    may go anywhere. When several squares qualify the one that keeps the
    creature closest to where it started is taken, so a push travels in a
    straight line instead of drifting.
    """
    pos = world.get(target, Position)
    if pos is None:
        return None
    here = pos.square
    now = distance(here, anchor)
    options: list[Square] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == dy == 0:
                continue
            cand = (here[0] + dx, here[1] + dy)
            then = distance(cand, anchor)
            ok = {
                Forced.PUSH: then > now,
                Forced.PULL: then < now,
                Forced.SLIDE: True,
            }[how]
            if ok and _clear(world, target, footprint(cand, pos.size)):
                options.append(cand)
    if not options:
        return None
    # Straightest first: keep the same heading away from (or toward) the anchor.
    dx = (here[0] > anchor[0]) - (here[0] < anchor[0])
    dy = (here[1] > anchor[1]) - (here[1] < anchor[1])
    if how is Forced.PULL:
        dx, dy = -dx, -dy
    preferred = (here[0] + dx, here[1] + dy)
    if preferred in options:
        return preferred
    return sorted(options)[0]


# -- reachability -----------------------------------------------------------


def reachable(
    world: World, eid: int, budget: int, *, mode: str | None = None
) -> dict[Square, list[Square]]:
    """Every square reachable within `budget`, with a path to each.

    Plain Dijkstra over the eight steps, charging two for difficult terrain.
    It is what the UI highlights and what a monster's move picks from.

    A flyer's search passes over occupied squares but will not offer one as a
    destination, since it has to come down at the end of the turn anyway.
    """
    pos = world.get(eid, Position)
    if pos is None or budget <= 0:
        return {}
    overhead = mode_of(world, eid, mode) in OVERHEAD
    rough = world.difficult()
    start = pos.square
    best: dict[Square, int] = {start: 0}
    paths: dict[Square, list[Square]] = {start: []}
    frontier = [start]
    while frontier:
        frontier.sort(key=lambda s: best[s])
        here = frontier.pop(0)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == dy == 0:
                    continue
                nxt = (here[0] + dx, here[1] + dy)
                if not _clear(world, eid, footprint(nxt, pos.size), overhead=overhead):
                    continue
                cost = best[here] + (2 if nxt in rough else 1)
                if cost > budget or cost >= best.get(nxt, 1 << 30):
                    continue
                best[nxt] = cost
                paths[nxt] = [*paths[here], nxt]
                frontier.append(nxt)
    paths.pop(start, None)
    if overhead:
        paths = {
            sq: path
            for sq, path in paths.items()
            if _clear(world, eid, footprint(sq, pos.size))
        }
    return paths
