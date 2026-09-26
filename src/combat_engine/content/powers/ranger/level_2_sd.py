"""Ranger, level 2: squeezing through somewhere narrow on a mount.

The three things the card says squeezing stops costing -- the -5 to attack
rolls, the combat advantage granted, and moving at half speed -- are
*exactly* the three lines of `conditions.RULES[Condition.SQUEEZING]`, so
the printed sentence is the condition being suppressed rather than any of
its consequences being unpicked one at a time. `c.ignore_condition` is that
suppression: the creature is still squeezing, and still fits where a
squeezing creature fits, which is the half the card keeps.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    SELF,
    Cast,
    CloseBurst,
    Companion,
    Condition,
    Keyword,
    When,
    World,
    power,
)


def _beast_of(world: World, eid: int) -> int | None:
    for other in world.having(Companion):
        comp = world.get(other, Companion)
        if comp.owner == eid and comp.kind == "beast":
            return other
    return None


def has_beast_companion(world: World, eid: int) -> bool:
    """"Prerequisite: You must have a horse beast companion."

    A companion's breed is not modelled -- `Companion.kind` says beast,
    spirit or familiar and nothing finer -- so the gate is the part of the
    requirement the engine can answer.
    """
    return _beast_of(world, eid) is not None


@power(
    "p13697",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=SELF,
    keywords=[Keyword.MARTIAL],
    requires=has_beast_companion,
    requires_text="you must have a beast companion you can ride",
)
def p13697(c: Cast) -> None:
    """The companion is the second target and is not in the ally pool -- a
    companion never is -- so it is named here rather than in the header.

    "While you are mounted on your beast companion" is not re-checked.
    Nothing announces mounting or dismounting, so a gate on it could only be
    read once anyway, and the whole duration is one turn.
    """
    c.ignore_condition(Condition.SQUEEZING, on=c.me, until=When.EONT)
    beast = _beast_of(c.world, c.me)
    if beast is not None:
        c.ignore_condition(Condition.SQUEEZING, on=beast, until=When.EONT)
