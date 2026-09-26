"""Assassin, level 9: a wall of darkness that bites.

`blocks_sight` is for everybody, where the printed line exempts the caster.
The engine keeps one grade of obscurity and no way to say who it is dark
for, which is the same limit `wizard/level_10` records; the alternative was
leaving the row out over the smaller half of its text.

The move-action teleport "to another square in the wall or adjacent to it"
is dropped: `c.grant_action` can hand out a teleport for a move action but
cannot say where it may land, and a teleport 5 that goes anywhere is a
different power.
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


@power(
    "p9438",
    level=9,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Wall(5, 10),
    target=NO_TARGET,
    keywords=[
        Keyword.SHADOW,
        Keyword.IMPLEMENT,
        Keyword.COLD,
        Keyword.CONJURATION,
        Keyword.TELEPORTATION,
    ],
)
def p9438(c: Cast) -> None:
    wall = c.wall(blocks_sight=True, until=When.SUSTAIN, sustain=MINOR)
    if not wall:
        return
    bite = "1d6"
    if c.dex_mod > 0:
        bite = f"1d6+{c.dex_mod}"
    elif c.dex_mod < 0:
        bite = f"1d6-{abs(c.dex_mod)}"
    c.burns(wall, bite, DamageType.COLD)
