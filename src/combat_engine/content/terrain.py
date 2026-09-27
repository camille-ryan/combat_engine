"""Dressing a board with something to fight over.

Every real board in the repository is bare. `Grid` has carried
`blocking`, `difficult` and `elevation` for a long time, `api/render`
already ships the first two to the client, and the only board that ever
sets any of them is the audit harness. So cover, concealment, hiding and
difficult terrain were all modelled and none of them ever came up in a
fight.

Laid from the encounter's own seed, so a board is reproducible from the
same two numbers everything else is: the fight is still decided by one
generator and `--seed 7` is still `--seed 7`.

Deliberately sparse. The point is that cover exists somewhere, not that
the room is a maze -- a board too full of it stops the two sides ever
meeting, which is its own kind of wrong fight.
"""

from __future__ import annotations

from random import Random

from combat_engine.engine import World
from combat_engine.engine.grid import Square


def dress(world: World, seed: int, *, density: float = 0.06) -> None:
    """Put pillars and rough ground on an otherwise empty floor.

    `density` is the share of squares that become something, split
    roughly two to one between rough going and hard cover.
    """
    pick = Random(seed ^ 0x7E44A1)
    width, height = world.grid.width, world.grid.height
    # The two starting bands are left clear. A pillar dropped on top of a
    # creature at setup leaves it Position-present and index-absent --
    # `grid.place` refuses to overwrite, and says so now, but the honest
    # fix is not to put one there.
    spare = {sq for sq in _band(0, 4, height) } | {sq for sq in _band(width - 4, width, height)}
    for _ in range(int(width * height * density)):
        sq = (pick.randrange(width), pick.randrange(height))
        if sq in spare or world.grid.occupant(sq) is not None:
            continue
        if pick.random() < 0.34:
            world.grid.blocking.add(sq)
        else:
            world.grid.difficult[sq] = "rubble"


def _band(lo: int, hi: int, height: int) -> set[Square]:
    return {(x, y) for x in range(lo, hi) for y in range(height)}
