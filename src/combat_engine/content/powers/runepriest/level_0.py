"""Runepriest, level 0: the class feature.

The burst grows from 5 squares to 10 at 11th level and 15 at 21st, and the
number of uses from two to three at 16th. Both are header data read before
the body runs, so the heroic printing is declared and the growth is left
here in prose. The extra healing dice are the part the body can carry.

The damage bonus is not conditional -- this row is the one rune's printing
of the feature, so it always pays out.
"""

from __future__ import annotations

from combat_engine.engine import *


@power(
    "p11353",
    level=0,
    cls="runepriest",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
    uses=2,
    once_per_round=True,
)
def p11353(c: Cast) -> None:
    who = c.target
    if who is None:
        return
    if c.may("spend a healing surge", who=who):
        c.surge(on=who)
        dice = sum(lv <= c.level for lv in (6, 11, 16, 21, 26))
        if dice:
            c.heal(c.roll(f"{dice}d6"), on=who)
    step = 2 + 2 * sum(lv <= c.level for lv in (11, 21))
    for friend in dict.fromkeys([c.me, *c.within(5, side="ally")]):
        c.bonus("damage", step, on=friend, until=When.EONT, kind="power")
