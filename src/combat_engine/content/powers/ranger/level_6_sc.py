"""Ranger, level 6: taking the surprise off a few of your allies.

"At the start of a surprise round in which any allies are surprised" is a
Trigger written into the Effect line, and it is read the way the warlord's
level 2 daily reads it: nothing announces a surprise round, so what one
*is* is a round that begins with somebody still surprised.

"Ranged sight" is not a range the header can spell. `Ranged(20)` is the
longest the engine has and stands in for it; every ally the row can reach
on any board the engine draws is inside it.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ActionType,
    Cast,
    Condition,
    Event,
    Keyword,
    Ranged,
    RoundStart,
    Target,
    Trigger,
    World,
    power,
)
from combat_engine.engine.query import allies, is_

_SURPRISE = "a surprise round begins with an ally of yours surprised"


def _allies_surprised(world: World, me: int, ev: Event) -> bool:
    return any(is_(world, x, Condition.SURPRISED) for x in allies(world, me))


@power(
    "p924",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(20),
    target=Target("ally", 99, everyone=True, label="Allies you can see"),
    keywords=[Keyword.MARTIAL],
    trigger=_SURPRISE,
    on=Trigger(RoundStart, _allies_surprised, _SURPRISE),
)
def p924(c: Cast) -> None:
    """"A number of allies equal to your Wisdom modifier" is a cap on a pool
    the header cannot express -- the count is not known until the row runs --
    so every surprised ally is a target and the body takes the first few.
    Sorted by entity id, which is the same order every other pool here comes
    in, so the same allies are picked on a re-run.
    """
    who = c.target
    if who is None or not c.is_(Condition.SURPRISED, on=who):
        return
    caught = sorted(a for a in c.allies() if c.is_(Condition.SURPRISED, on=a))
    if who in caught[: max(c.wis_mod, 0)]:
        c.cure(Condition.SURPRISED, on=who)
