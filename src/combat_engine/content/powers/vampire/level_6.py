"""Vampire, level 6.

One row, and it is a polymorph -- the first of the two in this class. The
other is in `level_10.py` and the two differ in every clause but "you cannot
attack", so nothing is shared between them beyond `ends_with`.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MOVE,
    PERSONAL,
    SELF,
    STANDARD,
    Cast,
    Keyword,
    Size,
    When,
    power,
)

from . import ends_with


@power(
    "p13860",
    level=6,
    cls="vampire",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH, Keyword.SHADOW],
    dropped=("c.form(keeps_gear=)",),
)
def p13860(c: Cast) -> None:
    """Tiny, speed 2, fly 8, no attacks, and a move action back out.

    A **walking** speed is not a movement mode, so the two movement clauses
    are written differently: the flight goes through `modes=` and the speed
    is the difference between what this character has and the 2 the card
    prints. That split is `wizard/level_10_sc.py`'s and is there for the same
    reason -- `c.mode` grants a mode and cannot set the base speed.

    `revert=MOVE` is the printed way out, so the shape carries its own
    `drop_cost` and `actions._dropping` offers it to the creature it is on,
    which here is the caster.

    Dropped: the equipment clause -- "you cannot hold or carry any object"
    and "your equipment becomes part of this form". Worn gear goes on working
    while what is held does not, and nothing suspends half of what a creature
    carries. `themes/batch_f.py`'s `p14192` is the same sentence and the same
    gap, so the symbol is already in the tree.
    """
    me = c.me
    shape = c.form(modes={"fly": 8}, until=When.ENCOUNTER, revert=MOVE, label=c.ref)
    slower = c.speed_of(me) - 2
    ends_with(
        c,
        shape,
        c.resize(Size.TINY, on=me, until=When.ENCOUNTER),
        c.cannot_attack(on=me, until=When.ENCOUNTER),
        c.penalty("speed", slower, on=me, until=When.ENCOUNTER) if slower > 0 else None,
    )
