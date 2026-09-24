"""Cleric, level 6: utility. No attack roll anywhere in the level.

Three of the four are healing said three different ways -- a surge with a
rider, a surge's worth without spending one, and a second wind handed back
-- so the whole file is `c.surge`, `c.surge_value` and `Powers.restore`.

`p952` is a lamp. It lights a room and it adds to two skills, and this
engine has neither light nor skills, so it is declared inert the way the
cantrips in `wizard/level_0.py` are rather than given a conjuration's
square, which the printed line does not claim.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    STANDARD,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    Powers,
    Ranged,
    power,
)
from combat_engine.engine.dsl import ANY_CREATURE

DIVINE = [Keyword.DIVINE]
DIVINE_HEALING = [Keyword.DIVINE, Keyword.HEALING]


@power(
    "p1410",
    level=6,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=DIVINE_HEALING,
)
def p1410(c: Cast) -> None:
    """A printed "can": the surge is the target's, so the target is asked."""
    if c.may("spend a healing surge", who=c.target):
        c.surge(bonus=c.cha_mod)


@power(
    "p652",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=DIVINE_HEALING,
)
def p652(c: Cast) -> None:
    """"As if it had spent two" -- twice the number, and no surge leaves the
    pool. `c.surge` would take them; `c.surge_value` is the same arithmetic
    for free, which is the whole distinction the line is drawing."""
    c.heal(2 * c.surge_value(of=c.target))


@power(
    "p949",
    level=6,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=DIVINE,
)
def p949(c: Cast) -> None:
    """A second wind is a once-per-encounter *use*, counted in `Powers`, so
    giving it back is `restore` on that counter -- the same door
    `actions.legal` reads when it decides whether to offer one."""
    known = c.world.get(c.target, Powers)
    if known is None:
        return
    known.restore("second-wind")
    c.note(f"p949: {c.target} can take a second wind again")


@power(
    "p952",
    level=6,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.CONJURATION],
    out_of_combat=True,
)
def p952(c: Cast) -> None:
    c.note("p952: a lamp, bright to 5 squares, walked with a minor action")
