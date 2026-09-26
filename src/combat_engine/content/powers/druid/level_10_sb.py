"""Druid, level 10: four of them, each spent separately.

Four `Item`s rather than one with four uses, because the printed line is
four objects -- they can be carried by four different creatures, and an
item belongs to one pair of hands.
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

_CHOICES = ("hit points", "a saving throw", "temporary hit points")


@power(
    "p9667",
    level=10,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p9667(c: Cast) -> None:
    def eat(eater: int) -> None:
        picked = c.choose(list(_CHOICES), f"{c.ref}: what it is eaten for")
        if picked == _CHOICES[1]:
            c.save(on=eater)
        elif picked == _CHOICES[2]:
            c.temp_hp(10, on=eater)
        else:
            c.heal(10, on=eater)

    for _ in range(4):
        c.give(fn=eat, on=c.me)
