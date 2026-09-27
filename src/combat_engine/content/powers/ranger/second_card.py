"""Ranger: the second stat block, where the card prints two.

Both are the beast's half of a row the ranger swings: "Minor Action, Melee
beast 1, Beast's attack bonus vs. AC". `beast_sb` settled how that is
said -- `Attack(by="companion")` rolls the beast's line and
`Melee(1, from_="companion")` measures from its square -- so all that was
missing was the grant, and each parent now leaves a hold under its own ref.

**Usage is the parent's stated rate rather than this card's column**: both
print "once per turn until the end of the encounter", which is at will with
`once_per_round`, and a daily would let the beast be commanded once a day.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.content.powers.cards import active
from combat_engine.engine import *

from .beast_sb import _has_beast

MARTIAL = [Keyword.MARTIAL]


def _commanded(ref: str) -> Callable[[World, int], bool]:
    """Both halves of the printed line: the grant, and a beast to command.

    Without the second an attack rolled `by="companion"` falls back to the
    ranger's own numbers, which is the thing `beast_sb` exists to stop.
    """
    granted = active(ref)

    def check(world: World, eid: int) -> bool:
        return granted(world, eid) and _has_beast(world, eid)

    return check


@power(
    "p12501b",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_commanded("p12501"),
    requires_text="the p12501 power must be active",
    once_per_round=True,
)
def p12501b(c: Cast) -> None:
    """No damage line at all -- the printed Hit is the fall and nothing
    else."""
    if c.strike():
        c.prone()


@power(
    "p12504b",
    level=9,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=AC, by="companion"),
    requires=_commanded("p12504"),
    requires_text="the p12504 power must be active",
    once_per_round=True,
)
def p12504b(c: Cast) -> None:
    if c.strike():
        c.slide(1)
