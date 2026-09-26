"""Warlock, level 10: seeing the wrong half of the room.

The whole Effect is one operation and it is `c.see_unseen`: the invisible
become visible and everything else stops being. Written as a method rather
than here because the second sentence is a hold per creature and the way
back out is a drop cost, neither of which a body can assemble.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p1926",
    level=10,
    cls="warlock",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p1926(c: Cast) -> None:
    """"You can end this effect as a minor action" is the drop cost, the same
    door `c.form`'s `revert` opens."""
    c.see_unseen(until=When.ENCOUNTER, revert=ActionType.MINOR)
