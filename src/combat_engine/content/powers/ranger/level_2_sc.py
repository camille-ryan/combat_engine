"""Ranger, level 2: three more on the quarry rider.

`cf:ranger-f1` no longer closes over its dice: `extra_damage` pays
`c.total("cf:ranger-f1 damage")` on top of them, so "add 3 to the extra
damage you deal with Hunter's Quarry" is a modifier under that name and
nothing else. A plain +3 against the quarry would be strictly more than
printed -- it would pay on every attack rather than on the once-a-round
rider.

The trigger is the opening roll. `Triggers.arm` runs before
`_roll_initiative`, which fills `encounter.order` provisionally, so a row
declared on `InitiativeRolled` is offered one; and every roll is made before
the first is announced, so "higher than any other combatant's" is a question
the predicate can actually answer.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    InitiativeRolled,
    Keyword,
    Trigger,
    When,
    World,
    power,
)
from combat_engine.engine.components import Initiative
from combat_engine.engine.query import combatants


def won_initiative(world: World, me: int, ev: Any) -> bool:
    """My own roll, and nobody else's is as high."""
    if getattr(ev, "actor", None) != me:
        return False
    mine = world.get(me, Initiative)
    if mine is None:
        return False
    return all(
        (world.get(other, Initiative) or Initiative()).rolled < mine.rolled
        for other in combatants(world)
        if other != me
    )


@power(
    "p4382",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
    trigger="your initiative check beats every other combatant's",
    on=Trigger(InitiativeRolled, won_initiative, "you roll the highest initiative"),
)
def p4382(c: Cast) -> None:
    c.stance(label="p4382")
    c.bonus("cf:ranger-f1 damage", 3, on=c.me, until=When.STANCE, kind="untyped")
