"""Ranger, level 10: the utility that needs a beast companion."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    NO_TARGET,
    REACTION,
    Cast,
    CloseBurst,
    Keyword,
    World,
    power,
)
from combat_engine.engine.events import ConditionApplied
from combat_engine.engine.query import distance_between as _gap
from combat_engine.engine.triggers import Trigger, about_my_companion

MARTIAL = [Keyword.MARTIAL]

_BEAST_SADDLED = (
    "your beast companion takes an effect a save can end, within 20 squares of you"
)


def _beast_saved_ends(world: World, me: int, ev: ConditionApplied) -> bool:
    """`about_my_companion` is the right half of this -- `ConditionApplied`
    names its subject `target`, which that predicate reads -- and the rest
    is the duration and the distance."""
    if not about_my_companion(world, me, ev):
        return False
    if "save" not in ev.duration:
        return False
    return _gap(world, me, ev.target) <= 20


@power(
    "p4414",
    level=10,
    cls="ranger",
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(20),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger=_BEAST_SADDLED,
    on=Trigger(ConditionApplied, when=_beast_saved_ends, text=_BEAST_SADDLED),
)
def p4414(c: Cast) -> None:
    """Only a condition announces itself, so a save-ends effect with no
    condition attached -- ongoing damage on its own -- does not fire this.

    The printed Target is the beast, which is not a creature the targeting
    machinery offers, so it is reached through `c.companion()`.
    """
    beast = c.companion()
    if beast is not None:
        c.save(on=beast, bonus=c.wis_mod)
