"""Rogue, level 10: utility, and every row of it printed behind a skill.

The Prerequisite lines gate *taking* these at character creation rather than
using them, so none is declared as a `requires` -- the reading `level_2.py`
settled. `p1396`'s **Requirement** is a different thing and is declared:
that one is checked every time the row is used.

`p1509` is its Thievery check and nothing else, so it carries
`out_of_combat=True`.

`p1515` has no check to succeed on either, but what the check buys is a
thing the board holds: the grab comes off. So it is written as the outcome
rather than declared inert.

`p142` costs one clause. The printed way out of it is the target spending a
standard action on an attack against the rogue, and granting a creature an
attack it does not have needs a row to grant -- `c.grant_row` takes a ref
and there is none for this. It is written down rather than approximated.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    Cast,
    Condition,
    Keyword,
    Melee,
    Relation,
    When,
    World,
    power,
)
from combat_engine.engine.query import adjacent, hidden_from
from combat_engine.engine.query import squares as squares_of

MARTIAL = [Keyword.MARTIAL]

#: What holds a creature in place well enough that escaping it is a thing
#: you roll for: a grab, or being tied down.
_HELD = (Condition.GRABBED, Condition.RESTRAINED)


def _is_hidden(world: World, eid: int) -> bool:
    return bool(hidden_from(world, eid))


@power(
    "p1396",
    level=10,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_is_hidden,
    requires_text="must be hidden",
)
def p1396(c: Cast) -> None:
    """Nothing in this engine gives a hiding creature away for walking --
    only attacking does, in `resolve.attack` -- so "you remain hidden during
    the move" is held by reasserting it against whoever could not see the
    rogue when it set off, rather than left to luck.

    The printed Stealth check and the square with cover to end in are both
    skill, and the model has neither, so the move is unfiltered.
    """
    unseeing = sorted(hidden_from(c.world, c.me))
    c.move(c.speed_of())
    for watcher in unseeing:
        c.hide(from_=watcher)


@power(
    "p142",
    level=10,
    cls="rogue",
    usage=DAILY,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
)
def p142(c: Cast) -> None:
    """Into the target's square, and carried wherever it goes.

    `c.ride` is "when the target moves, you move with it" exactly:
    `movement.step` carries a mount's passengers, and quietly, which is
    right -- the rogue is being taken along rather than moving.

    The only way into an occupied square is a shift, which provokes nothing,
    so the printed "provoking opportunity attacks as normal" is opened by
    hand against the enemies whose reach the rogue is leaving.
    """
    victim = c.target
    if victim is None:
        return
    seat = sorted(squares_of(c.world, victim))
    watching = [f for f in c.enemies() if adjacent(c.world, c.me, f)]
    if not seat or not c.shift(to=seat[0], share=True):
        return
    for foe in watching:
        if not adjacent(c.world, c.me, foe):
            c.provoke(foe, on=c.me, why=c.ref)
    c.ride(on=victim)
    c.grants_advantage(on=victim, until=When.ENCOUNTER, to=c.me)
    me = c.me
    c.penalty(
        "attack",
        4,
        on=victim,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == me,
    )


@power(
    "p1509",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p1509(c: Cast) -> None:
    c.note("p1509: no -10 on the next attempt to pick a pocket in a fight")


@power(
    "p1515",
    level=10,
    cls="rogue",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1515(c: Cast) -> None:
    """Whatever is holding the rogue stops holding it.

    A grab is a relation held up by an effect, so ending the effect is the
    escape; a relation left standing without one is cleared after, because
    nothing else would ever come to.
    """
    for effect in list(c.world.effects.of(c.me)):
        held = any(card in _HELD for card in effect.conditions)
        bound = any(
            kind is Relation.GRABBED_BY and target == c.me
            for kind, _source, target in effect.relations
        )
        if held or bound:
            c.world.effects.end(effect, c.ref)
    for grabber in c.world.relations.sources(Relation.GRABBED_BY, c.me):
        c.world.relations.clear(Relation.GRABBED_BY, grabber, c.me, c.ref)
