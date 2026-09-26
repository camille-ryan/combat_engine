"""Battlemind, level 6: the one that answers being caught out.

Two triggers rather than one. Nothing in the engine *announces* a surprise
round, so being surprised is readable in two different moments: the
condition arriving, which is `ConditionApplied`, and a round beginning with
it already standing, which is `RoundStart`. A row declared on only the
first can never fire in a fight whose surprise was set up before the
triggers were armed, and one declared on only the second answers a beat
late. Declaring both is the printed sentence.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Condition,
    ConditionApplied,
    Event,
    Keyword,
    RoundStart,
    Trigger,
    When,
    World,
    power,
)
from combat_engine.engine.query import is_

_SURPRISED = "you are surprised"


def _caught_out(world: World, me: int, ev: ConditionApplied) -> bool:
    """The moment the condition lands. `targets_me` reads the right field on
    this event and `about_me` would be false forever, but the condition has
    to be named as well."""
    return ev.target == me and ev.condition is Condition.SURPRISED


def _still_surprised(world: World, me: int, ev: Event) -> bool:
    """A round that begins with the battlemind surprised, for a fight whose
    surprise was arranged before anything was watching."""
    return is_(world, me, Condition.SURPRISED)


@power(
    "p13050",
    level=6,
    cls="battlemind",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
    trigger=_SURPRISED,
    on=(
        Trigger(ConditionApplied, _caught_out, _SURPRISED),
        Trigger(RoundStart, _still_surprised, _SURPRISED),
    ),
)
def p13050(c: Cast) -> None:
    """"One creature adjacent to you", not one enemy: the mark is worth
    laying on whatever is standing there, and the card does not say which
    side it is on."""
    c.cure(Condition.SURPRISED, on=c.me)
    c.shift(c.speed_of() // 2)
    beside = [x for x in c.within(1) if x != c.me]
    pick = c.choose(beside, "mark one creature adjacent to you")
    if pick is not None:
        c.mark(on=pick, until=When.EONT)
