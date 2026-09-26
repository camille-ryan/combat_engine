"""Sorcerer, level 2: a wall you can get through, slowly.

`solid=False`, because the printed line is "a creature must swim to move
through the wall" -- so the squares stay out of `Grid.blocking` and are
rough going instead. What still makes it a wall is `blocks_sight`, which is
the engine's only door to cover from terrain and comes out as the superior
cover the card gives against attacks made through it.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    NO_TARGET,
    Cast,
    DamageType,
    Keyword,
    Wall,
    When,
    power,
)
from combat_engine.engine.events import ZoneEntered


@power(
    "p16238",
    level=2,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=Wall(5, 10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
)
def p16238(c: Cast) -> None:
    """The Athletics DC is a check nothing here rolls, so swimming through is
    difficult terrain. The Special doubles the wall beside open water, which
    `c.terrain` is exactly the question for."""
    wall = c.wall(
        10 if c.terrain("aquatic") else 5,
        solid=False,
        blocks_sight=True,
        difficult="water",
        until=When.SUSTAIN,
        sustain=MINOR,
    )
    if not wall:
        return

    def soak(ev: ZoneEntered) -> None:
        if ev.zone == wall:
            c.vulnerable(5, DamageType.COLD, until=When.EOTNT, on=ev.actor)

    c.watch(ZoneEntered, soak, until=When.ENCOUNTER, label=c.ref)
