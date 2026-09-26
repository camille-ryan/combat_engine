"""Psion, level 2: both halves of one printed trigger.

"You take falling damage **or** an attack knocks you prone" is two events,
so it is two `Trigger`s. The second cannot be refused -- `ConditionApplied`
is announced after the condition is on you -- so the prone is taken off
again instead, which is the same board a square later and is what the
printed sentence is worth. The falling half is a real interrupt: `Fell` is
a `Decision` and both of its readable fields are set here.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    INTERRUPT,
    PERSONAL,
    SELF,
    Cast,
    Condition,
    Fell,
    Keyword,
    World,
    power,
)
from combat_engine.engine.events import ConditionApplied
from combat_engine.engine.triggers import Trigger, about_me

_FALL_OR_PRONE = "you take falling damage, or an attack knocks you prone"


def _knocked_prone(world: World, me: int, ev: ConditionApplied) -> bool:
    return ev.target == me and ev.condition is Condition.PRONE


@power(
    "p13314",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
    trigger=_FALL_OR_PRONE,
    on=[
        Trigger(Fell, about_me, "you take falling damage"),
        Trigger(ConditionApplied, _knocked_prone, "an attack knocks you prone"),
    ],
)
def p13314(c: Cast) -> None:
    ev = c.trigger
    if isinstance(ev, Fell):
        c.cushion(c.level)
        ev.prone = False
    else:
        c.cure(Condition.PRONE, on=c.me)
