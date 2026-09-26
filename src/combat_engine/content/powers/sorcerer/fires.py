"""Sorcerer: the two rows whose subject is a fire that is already burning.

A fire is `Scenery` -- a square, a size and a footprint, no hit points and
no side -- so neither row puts anything on the board; both read what is
there. "Nonliving" therefore needs no test: anything with a `Side` is a
creature and is not in this pool at all.

**"Of campfire size or larger" is a size category.** A campfire is Medium
and a torch is smaller, and `Size.squares` is 1 for Tiny, Small and Medium
alike -- so the comparison is `Size.order`, which is the only thing that can
tell those three apart.

**The Requirement is asked twice, of two different things.** `requires=` is
handed `(world, eid)` and gates whether the row may be used at all;
`query.scenery` answers it there and `c.scenery` answers the same question
inside the body, where the destination is chosen.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    SELF,
    STANDARD,
    Cast,
    CloseBurst,
    Keyword,
    Position,
    Size,
    When,
    World,
    power,
)
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import adjacent, scenery, squares

#: What the two rows mean by "campfire size". Anything below it is a torch.
CAMPFIRE = Size.MEDIUM


def _big_enough(world: World, fire: int) -> bool:
    pos = world.get(fire, Position)
    return pos is not None and pos.size.order >= CAMPFIRE.order


def _beside_a_fire(world: World, eid: int) -> bool:
    """The printed Requirement: adjacent to a fire of campfire size or larger."""
    return any(
        _big_enough(world, fire) and adjacent(world, eid, fire)
        for fire in scenery(world, "fire")
    )


@power(
    "p16241",
    level=6,
    cls="sorcerer",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL, Keyword.TELEPORTATION],
    requires=_beside_a_fire,
    requires_text="must be adjacent to a fire of campfire size or larger",
)
def p16241(c: Cast) -> None:
    """The destination is chosen among *squares* rather than among fires: a
    fire has eight neighbours and most of them are the wrong side of it,
    occupied, or further than ten squares off. The one being stepped out of
    is a legal destination too, which is why the caster's own square is the
    only one ruled out."""
    here = squares(c.world, c.me)
    spots = sorted(
        sq
        for fire in c.scenery("fire", within=10)
        if _big_enough(c.world, fire)
        for sq in spread(squares(c.world, fire), 1)
        if sq not in here
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and min(distance(mine, sq) for mine in here) <= 10
    )
    where = c.choose(spots, "which fire to step out of")
    if where is not None:
        c.teleport(10, to=where)


def _direct(c: Cast, fire: int) -> None:
    """The three options the card prints, chosen once per fire.

    Putting a fire out is the one that does not come back: `c.douse`
    despawns it, where expanding and relocating are undone by the control
    lapsing.
    """
    what = c.choose(["expand", "extinguish", "relocate"], "what to do with the fire")
    if what == "extinguish":
        c.douse(on=fire)
    elif what == "relocate":
        c.slide(2, on=fire)
    else:
        c.grow(on=fire)


@power(
    "p16244",
    level=10,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
)
def p16244(c: Cast) -> None:
    """One hold per fire, and it is the hold that does both jobs: keeping
    the fire under control, and putting it back where it was and the size it
    was when control lapses. "Expanded or relocated flames return to their
    normal size and location at the end of your next turn" is one sentence
    about letting go, so it is written once in `c.control` rather than as a
    clock per option.

    `NO_TARGET`, because the printed line has no Target -- the burst names
    what it catches inside the Effect, and fires are not in any target
    pool."""
    area = c.area()
    for fire in c.scenery("fire", loose=True):
        if not squares(c.world, fire) & area:
            continue
        hold = c.control(on=fire, until=When.SUSTAIN, sustain=MINOR)
        _direct(c, fire)
        c.on_sustain(hold, lambda held=fire: _direct(c, held))
