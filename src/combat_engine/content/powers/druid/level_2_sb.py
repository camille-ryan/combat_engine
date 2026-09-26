"""Druid, level 2: the one that leaves something behind.

`c.give` is the missing piece. The seed is spent by a creature that did not
make it, as an action of its own, and it pays out the *maker's* numbers --
so it is neither a granted row (which has no charges and would roll the
eater's surge value) nor an effect on anybody. It is an `Item`, and
`actions.legal` offers eating it to whoever is carrying it.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    power,
)


@power(
    "p13516",
    level=2,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p13516(c: Cast) -> None:
    """"Lasts until the end of your next extended rest" is longer than any
    duration the engine keeps, and an item nobody eats simply stays in the
    hand; the encounter ending takes the board with it either way."""
    c.spend_surge(on=c.me)
    worth = 10 + c.surge_value()
    c.give(fn=lambda eater: c.heal(worth, on=eater), on=c.me)
