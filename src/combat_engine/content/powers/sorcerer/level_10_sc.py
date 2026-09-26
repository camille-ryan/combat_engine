"""Sorcerer, level 10: the blow that lands on a second creature.

`c.also_hits` is the printed sentence. `c.redirect` moves the one blow and
`c.autohit` forces the one being answered; neither copies a blow that has
already landed. The damage has not been rolled when the `Hit` is announced,
so the copy is taken off the next roll that attack makes and dealt again, of
the same type -- re-running the row would be a different attack with a
different die, which is not what "the triggering attack" means.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    ONE_CREATURE,
    REACTION,
    Cast,
    CloseBurst,
    Hit,
    Keyword,
    Trigger,
    World,
    both,
    power,
    targets_me,
)

#: A close or area attack, read off the power the event names.
BURSTS = ("close_burst", "close_blast", "area_burst")


def by_burst(world: World, me: int, ev: Any) -> bool:
    """Was this an area or a close attack? The reach is on the power."""
    from combat_engine.engine.dsl import get

    p = get(getattr(ev, "power", ""))
    return p is not None and p.reach_of(getattr(ev, "branch", 0)).kind in BURSTS


@power(
    "p5281",
    level=10,
    cls="sorcerer",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE],
    trigger="you are hit by an area or a close attack",
    on=Trigger(Hit, both(targets_me, by_burst), "you are hit by an area or close attack"),
)
def p5281(c: Cast) -> None:
    c.also_hits()
