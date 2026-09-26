"""Fighter, level 6: the initiative check you did not like.

Two things that used to be true are not. `Triggers.arm` runs *before*
`_roll_initiative`, and `_roll_initiative` fills `encounter.order`
provisionally so the dispatcher has a room to offer the event to -- so a row
declared on `InitiativeRolled` hears the opening rolls. And `c.initiative`
moves a creature in the order after the die has landed, which is the only
thing a bonus to a roll that has happened can mean.

"You dislike the result" is a judgement: the row fires when somebody rolled
better, which is the only reading under which the +10 does anything.
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
    World,
    power,
)
from combat_engine.engine.components import Initiative
from combat_engine.engine.query import combatants


def rolled_behind(world: World, me: int, ev: Any) -> bool:
    """My own initiative roll, and somebody is ahead of me on it."""
    if getattr(ev, "actor", None) != me:
        return False
    mine = world.get(me, Initiative)
    if mine is None:
        return False
    return any(
        (world.get(other, Initiative) or Initiative()).rolled > mine.rolled
        for other in combatants(world)
        if other != me
    )


@power(
    "p1440",
    level=6,
    cls="fighter",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="you roll initiative and dislike the result",
    on=Trigger(InitiativeRolled, rolled_behind, "you roll initiative and dislike it"),
)
def p1440(c: Cast) -> None:
    c.initiative(10, on=c.me)
