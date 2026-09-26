"""Wizard, level 10: wearing the familiar's shape, and a hole in the floor.

Two rows that both reach past the body for something the engine had to be
taught. The shape is `c.form`, which already takes the ways of moving and
the cost of stepping out of it; the rift is `c.link`, which is new and is
**movement only** -- see its docstring, and the report that came with it.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Keyword,
    Movement,
    Ranged,
    Square,
    When,
    distance,
    power,
    spread,
)
from combat_engine.engine.dsl import NO_TARGET

ARCANE = [Keyword.ARCANE]


def _open_squares(c: Cast, reach: int) -> list[Square]:
    """Unoccupied squares a creature could stand in, within range."""
    grid = c.world.grid
    here = c.here
    return sorted(
        (
            sq
            for sq in spread({here}, reach)
            if grid.passable(sq) and grid.occupant(sq) is None
        ),
        key=lambda sq: (distance(here, sq), sq),
    )


@power(
    "p10424",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
)
def p10424(c: Cast) -> None:
    """Three clauses, and one of them has nothing to point at.

    "The movement modes and speed of your familiar" is read off the
    familiar's own `Movement`: the modes are granted, and the walking speed
    is not a mode, so it is the difference between the two -- the same way
    the druid's small shapes write "your speed becomes 2".

    "Special senses" is the clause with no referent. A creature carries no
    list of senses in this engine, so there is nothing to copy across;
    `c.truesight` and the rest are things a power grants, not things a
    familiar has.

    "Can change back or forth as a minor action" is both halves. `revert`
    is the way out, and the way back in is this row again -- so dropping
    the shape hands its use back. It is handed back when the fight ends
    too, which costs nothing: nothing uses a daily after that.
    """
    pet = c.familiar()
    if pet is None:
        return
    moves = c.world.get(pet, Movement)
    shape = c.form(
        modes=dict(moves.modes) if moves is not None else None,
        until=When.ENCOUNTER,
        revert=ActionType.MINOR,
    )
    mine, theirs = c.speed_of(), c.speed_of(pet)
    holds = [c.cannot_attack(on=c.me, until=When.ENCOUNTER)]
    if theirs > mine:
        holds.append(c.bonus("speed", theirs - mine, on=c.me, until=When.ENCOUNTER))
    elif theirs < mine:
        holds.append(c.penalty("speed", mine - theirs, on=c.me, until=When.ENCOUNTER))
    for hold in holds:
        if hold is not None:
            shape.on_end.append(
                lambda h=hold: c.world.effects.end(h, "the form ended")
            )
    shape.on_end.append(lambda: c.restore_use(c.ref, on=c.me))


@power(
    "p1543",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=ARCANE,
)
def p1543(c: Cast) -> None:
    """"Two unoccupied squares in range", and the pair is the whole power --
    a rift between two squares beside each other is worth nothing. So the
    near end is offered nearest-first and the far end farthest-first, which
    is the only ordering that makes an engine with nobody playing pick a
    pair worth having.

    "For movement only" is exactly what `c.link` says and no more.
    """
    spots = _open_squares(c, 20)
    near = c.choose(spots, "one end of the rift")
    if near is None:
        return
    far = c.choose([sq for sq in reversed(spots) if sq != near], "the other end")
    if far is None:
        return
    c.link(near, far, until=When.SUSTAIN, sustain=ActionType.MINOR)
