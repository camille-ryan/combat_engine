"""Psion, level 10: the wall that can be knocked down.

The one row that makes a barrier a *body* rather than terrain: it has fifty
hit points, anything aimed at it hits, and breaking it is worth doing
because of what happens next. `c.wall(hp=)` spawns a `Barrier` -- targetable
like a companion, and subtracted out of `query.combatants` for the same
reason, so it takes no turn and does not decide the fight.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    NO_TARGET,
    STANDARD,
    Cast,
    DamageType,
    Keyword,
    Wall,
    When,
    power,
)
from combat_engine.engine.events import Dropped
from combat_engine.engine.grid import spread
from combat_engine.engine.query import squares


@power(
    "p13344",
    level=10,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Wall(5, 10),
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC, Keyword.FORCE, Keyword.CONJURATION],
)
def p13344(c: Cast) -> None:
    """"Phasing creatures cannot move through it" comes free: phasing reads
    `Grid.blocking` like everything else and the wall is in it."""
    wall = c.wall(hp=50, until=When.SUSTAIN, sustain=MINOR)
    if not wall:
        return
    body = c.barrier(wall)
    if body is None:
        return
    # The squares are taken now: by the time the wall falls the body has
    # been despawned, and asking where it was would find nothing.
    area = spread(squares(c.world, body), 2)

    def collapse(ev: Dropped) -> None:
        if ev.actor != body:
            return
        for who in c.in_squares(area):
            if who == body:
                continue
            c.flat(10, dtype=DamageType.FORCE, on=who)
            c.prone(on=who)

    c.watch(Dropped, collapse, until=When.ENCOUNTER, label=c.ref)
