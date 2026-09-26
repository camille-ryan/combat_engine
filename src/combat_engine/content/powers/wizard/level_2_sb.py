"""Wizard, level 2: catching somebody who is falling.

`Fell` is a `Decision` announced before the creature lands, and it carries
the two things a printed exemption changes -- how much of the damage is
taken off, and whether the landing knocks it down. `c.cushion()` with no
number is the whole sentence: "takes no damage from the fall, and
consequently does not fall prone at the end of it".
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    FREE,
    NO_TARGET,
    Cast,
    Fell,
    Keyword,
    Ranged,
    World,
    power,
)
from combat_engine.engine.query import distance_between
from combat_engine.engine.triggers import Trigger

_SOMEBODY_FALLS = "you fall, or a creature within 10 squares of you falls"


def _falls_near_me(world: World, me: int, ev: Fell) -> bool:
    return ev.actor == me or distance_between(world, me, ev.actor) <= 10


@power(
    "p1213",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger=_SOMEBODY_FALLS,
    on=Trigger(Fell, _falls_near_me, _SOMEBODY_FALLS),
)
def p1213(c: Cast) -> None:
    c.cushion()
