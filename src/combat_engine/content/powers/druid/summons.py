"""What a summoned animal does on a round nobody gave it an order.

Ten of the class's summoning rows print an Instinctive Effect, and every
one of them ends with the same two clauses: attack an adjacent enemy if it
can, otherwise move its speed to a square next to one. That tail is
`hunt`, written once; each row keeps its own first choice above it, which
is the half the cards disagree about.

The move is written out here rather than left to `c.move`, which picks its
destination through the world's decider -- with none installed that is the
lowest-numbered reachable square, so a creature told to close on somebody
reliably walked away from everybody. The same trap `c.overrun` documents.

An instinctive attack is the creature's own attack line, riders and all:
`then` is where the rider goes. The two rows that print a charge instead
say "using its attack as a melee basic attack", which drops nothing --
`c.command(charge=True)` is that swing.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import Cast
from combat_engine.engine.grid import spread
from combat_engine.engine.movement import walk
from combat_engine.engine.query import distance_between, speed, squares


def nearest(c: Cast, who: int, pool: list[int] | None = None) -> list[int]:
    """`pool`, or every enemy, ordered by how far it is from `who`.

    Measured from the creature rather than from its summoner, which is the
    only measurement the printed clauses ever make: "the nearest bloodied
    creature **it** can charge".
    """
    return sorted(
        c.enemies() if pool is None else pool,
        key=lambda f: (distance_between(c.world, who, f), f),
    )


def walk_beside(c: Cast, who: int, target: int, *, gap: int = 1) -> bool:
    """Walk `who` its speed to a square within `gap` of `target`.

    Shortest path first, the way `actions._charges` chooses one. True if
    it is within `gap` afterwards, which includes having been there
    already and not needing to move.
    """
    if distance_between(c.world, who, target) <= gap:
        return True
    near = spread(squares(c.world, target), gap)
    paths = c.world.reachable_paths(who, speed(c.world, who))
    best = min(
        (
            (len(path), dest, path)
            for dest, path in paths.items()
            if dest in near and path
        ),
        default=None,
    )
    if best is None:
        return False
    walk(c.world, who, list(best[2]))
    return True


def close_on(c: Cast, who: int, *, gap: int = 1) -> int | None:
    """"It moves its speed to a square adjacent to an enemy."

    Nearest first, and on to the next one when that square cannot be
    reached. Returns the enemy it ended up beside, or None if it could
    not get near any of them.
    """
    for foe in nearest(c, who):
        if walk_beside(c, who, foe, gap=gap):
            return foe
    return None


def hunt(c: Cast, who: int, *, then: Callable[[int], None] | None = None) -> None:
    """"It attacks an adjacent enemy if it can. Otherwise, it moves its
    speed to a square adjacent to an enemy."

    The tail of nearly every printed Instinctive Effect in the class.
    `then` is the rider the creature's attack line carries -- the
    instinctive attack is that attack, so the rider comes with it.
    """
    beside = nearest(c, who, c.within(1, of=who, side="enemy"))
    if not beside:
        close_on(c, who)
        return
    if c.command(who, on=beside[0]) and then is not None:
        then(beside[0])
