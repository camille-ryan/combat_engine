"""Monk, level 6: the utility that answers the class's own feature row.

Its printed Trigger names a power, and a name is not something this repo
reads -- but the ids are. The feature is the class's level 0 row, printed
once per tradition, so the trigger is declared against all five: a monk
carries whichever one its tradition gave it and the row has to answer that
one.

"Each enemy that was not damaged by" the feature is read as "was not a
target of it". `PowerUsed` carries the targets and is announced before the
damage exists, and a creature the feature was aimed at and missed is not
what the sentence is about -- the feature does not roll.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    Trigger,
    World,
    power,
)
from combat_engine.engine.events import PowerUsed

#: The class feature, once per tradition. All five are the same trigger and
#: the same slot; a monk has exactly one of them.
FLURRY = ("p11207", "p13123", "p16131", "p16132", "p7448")

_USED_IT = "you use your class's level 0 feature row"


def _used_my_feature(world: World, me: int, ev: PowerUsed) -> bool:
    return ev.actor == me and ev.power in FLURRY


@power(
    "p11222",
    level=6,
    cls="monk",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
    trigger=_USED_IT,
    on=Trigger(PowerUsed, _used_my_feature, _USED_IT),
)
def p11222(c: Cast) -> None:
    spared = set(getattr(c.trigger, "targets", ()) or ())
    for foe in c.within(2, side="enemy"):
        if foe not in spared:
            c.push(1, on=foe)
