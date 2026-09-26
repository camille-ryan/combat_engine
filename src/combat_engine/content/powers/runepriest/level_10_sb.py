"""Runepriest, level 10: a one-shot somebody else expends.

The same shape as the druid\'s seed -- an `Item` a creature carries and
spends a minor action on -- with a rider that lands on whoever spent it
rather than on whoever made it. "+5 power bonus to all defenses" is
`kind="power"`, which is what stops it stacking with another of its kind.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    MINOR,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p15993",
    level=10,
    cls="runepriest",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p15993(c: Cast) -> None:
    worth = c.surge_value()

    def read(reader: int) -> None:
        c.heal(worth, on=reader)
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, 5, on=reader, until=When.EOTNT, kind="power")

    c.spend_surge(on=c.me)
    c.give(fn=read, on=c.me)
