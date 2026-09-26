"""Invoker, level 10: taking an ally's blow.

`c.redirect` reaches a resolved `Hit` now: the roll is not made again, the
live result is moved with the event, and `c.attack` reads that target back
before the body that rolled deals its damage. Moving the event alone moved
the announcement and left the damage on the creature that was spared, which
is why this row read as unwritable.

`ally_within` is no use here. It reads `ev.actor`, and a `Hit` has none --
its subject is `target` -- so the printed "an **ally** within 10 squares of
you is hit" needs its own predicate, the same reading `about_me` carries.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.powers.sorcerer.level_10_sc import by_burst
from combat_engine.engine import (
    DAILY,
    INTERRUPT,
    NO_TARGET,
    Cast,
    CloseBurst,
    Hit,
    Keyword,
    Trigger,
    World,
    both,
    power,
)
from combat_engine.engine.query import distance_between, team


def ally_hit_within(squares: int) -> Callable[[World, int, Any], bool]:
    """An ally -- not you -- within range, and it is the one being hit."""

    def check(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


@power(
    "p5193",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    trigger="an ally within 10 squares of you is hit by an area or a close attack",
    on=Trigger(
        Hit,
        both(ally_hit_within(10), by_burst),
        "an ally within 10 is hit by an area or close attack",
    ),
)
def p5193(c: Cast) -> None:
    c.redirect(to=c.me)
