"""Invoker, level 2: the wall that shelters whoever stands in it.

`Wall(5, 10)` is the printed range line and `c.wall` is what it raises:
five squares of `Grid.blocking`, so nothing walks through it and nothing
sees through it, with a zone laid over the same squares to carry the two
clauses that are about standing inside.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    MINOR,
    NO_TARGET,
    Cast,
    Keyword,
    Wall,
    When,
    power,
)
from combat_engine.engine.events import TurnStart


@power(
    "p2860",
    level=2,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Wall(5, 10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.CONJURATION],
)
def p2860(c: Cast) -> None:
    """One square high is nothing on a flat board. The temporary hit points
    are a watch rather than a zone feature: `c.grants_in` carries a modifier
    and there is no standing-in-a-zone payout at the start of a turn."""
    wall = c.wall(until=When.SUSTAIN, sustain=MINOR)
    if not wall:
        return
    c.grants_in(wall, AC, 1, side="ally", kind="power")

    def bless(ev: TurnStart) -> None:
        if ev.actor in c.world.zones.occupants(wall) and ev.actor in c.allies():
            c.temp_hp(5, on=ev.actor)

    c.watch(TurnStart, bless, until=When.ENCOUNTER, label=c.ref)
