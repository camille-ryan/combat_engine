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
from combat_engine.engine.components import Powers
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.types import ActionType

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

    **The equipment clause is written and its marker was stale against a
    ruling already in the tree.** `p14192` carried the same symbol, settled
    the same sentence, and removed it: `c.form` needs no `keeps_gear=`,
    because the half with combat meaning is sayable today and the rest was
    already ruled to have none.

    What has combat meaning here is the **item powers of what is held**. An
    item's own rows go into `Powers.known` while it is carried
    (`Magic.powers`), and an item row is one whose header says
    `cls="item"` -- which is how `f1362b` asks and how `p14192` wrote the
    same clause. `c.forbid` takes a row away without spending it, so it
    comes back with the shape. A **Property** is `action=NONE` and is not a
    power, so it is left alone.

    *"You cannot make attacks"* is already `c.cannot_attack` above, which
    subsumes the weapon half of *"cannot hold ... any object"* -- a bat
    with a longsword in its claw could not swing it either way.

    The rest of the sentence is inventory bookkeeping with no combat
    consequence -- items in hand being dropped, worn gear not coming off,
    a container's contents out of reach -- which is the reading `p5032` and
    `f1857` settled for this identical printed paragraph, and `p14192`
    followed. No symbol, because there is nothing for one to wait for.
    `#1306`.
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
    carried = c.world.get(me, Powers)
    for ref in sorted(carried.known if carried is not None else ()):
        row = REGISTRY.get(ref)
        if row is None or row.cls != "item" or row.action is ActionType.NONE:
            continue
        ends_with(c, shape, c.forbid(ref, on=me, until=When.ENCOUNTER))
