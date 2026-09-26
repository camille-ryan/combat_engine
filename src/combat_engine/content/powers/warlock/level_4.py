"""Warlock, level 4.

One row, and its whole printed Effect happens away from the fight: a Tiny
invisible conjuration is sent off to find a thing or map a place over the
course of up to an hour, and returns to report. It cannot open a door, it
cannot notice anything, and it never touches the board -- so it is declared
inert rather than given a combat effect it does not have, the shape
`wizard/level_0.py` settled for the cantrips.
"""

from __future__ import annotations

from combat_engine.engine import *


@power(
    "p13641",
    level=4,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
    out_of_combat=True,
)
def p13641(c: Cast) -> None:
    c.note("p13641: an unseen Tiny spirit scouts or searches for up to an hour")
