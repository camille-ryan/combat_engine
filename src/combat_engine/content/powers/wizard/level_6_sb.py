"""Wizard, level 6: staying in the air.

`c.hover` is the pair of things that make height hold: the creature is
lifted, and it is moving as something airborne, which is what stops the
engine settling it back onto the floor at the end of its next step. When
the hold ends it comes down safely, which is the printed last sentence.

"If some effect causes you to be more than 4 squares above the ground you
drop to 4" is left out: nothing else on the board can raise a creature, so
the clause has no subject.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    MOVE,
    PERSONAL,
    REF,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p32",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p32(c: Cast) -> None:
    hold = c.hover(4, until=When.SUSTAIN, sustain=MOVE)
    c.penalty(AC, 2, on=c.me, until=When.EONT)
    c.penalty(REF, 2, on=c.me, until=When.EONT)
    c.on_sustain(hold, lambda: c.rise(min(4, c.height() + 3)))
