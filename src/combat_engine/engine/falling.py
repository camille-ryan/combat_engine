"""How far off the ground a creature is, and what landing costs.

The board was flat and had no notion of down, so six printed rows whose
whole trigger is "you fall" had nothing to answer. There are three pieces
and they are deliberately small:

* `Position.height` -- squares above the board's own level. Everybody is at
  0 until something lifts them.
* `Grid.elevation` -- where the floor of a square is. Absent means 0. A
  square that has been sunk has a floor below the rest of the board, and
  walking into one is the commonest way to fall.
* `Fell` -- announced **before** the creature lands, so an interrupt can
  arrest the drop outright (`c.cancel()`) or merely soften it. Both halves
  are printed on real rows and both are read back off the event here.

**A fall is `FALL_DIE` per ten feet**, and a square is five -- so it is one
die per *two* squares, not per square. Written per square first, which made
every fall in the game twice as lethal as the rule and would have read as
a balance problem rather than a units mistake. Landing knocks the creature
prone, which four of the six rows that print an exemption confirm ("takes
no damage from the fall, and consequently does not fall prone").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .components import Movement, Position
from .durations import When
from .events import Fell, Note
from .types import Condition, DamageType

if TYPE_CHECKING:
    from .ecs import World

#: Per ten feet fallen. `SQUARES_PER_DIE` is the conversion, and it is
#: separate so the number and the unit cannot drift apart again.
FALL_DIE = "1d10"
SQUARES_PER_DIE = 2

#: Ways of moving that do not fall. Climbing is one of them: a creature on
#: a wall is holding on, which is the state an arrested fall leaves it in.
AIRBORNE = ("fly", "hover", "levitate", "climb")


#: Who is in the middle of a fall. An interrupt that answers `Fell` runs
#: *inside* the announcement, and two of the rows that answer one move the
#: creature -- so the step it takes would start a second fall from the
#: height the first one has not come down from yet.
_FALLING: set[tuple[int, int]] = set()


def airborne(world: World, eid: int) -> bool:
    mv = world.get(eid, Movement)
    return mv is not None and mv.using in AIRBORNE


def height(world: World, eid: int) -> int:
    """How far above the floor of its own square this creature is."""
    pos = world.get(eid, Position)
    if pos is None:
        return 0
    return pos.height - world.grid.floor(pos.square)


def lift(world: World, eid: int, squares: int) -> int:
    """Raise a creature off the ground without moving it sideways."""
    pos = world.get(eid, Position)
    if pos is None:
        return 0
    pos.height = world.grid.floor(pos.square) + max(0, squares)
    world.bus.emit(Note(text=f"{eid} is {squares} squares up"))
    return pos.height


def drop(world: World, eid: int, squares: int = 0, *, by: int = 0, safe: bool = False) -> int:
    """The fall itself. Returns the damage actually taken.

    `squares` defaults to however far off the ground the creature is.
    `safe` is the printed "you descend to the ground without taking falling
    damage", which is a landing rather than a fall and announces no `Fell`.
    """
    pos = world.get(eid, Position)
    if pos is None:
        return 0
    key = (id(world), eid)
    if key in _FALLING:
        return 0
    floor = world.grid.floor(pos.square)
    far = squares if squares else pos.height - floor
    if far <= 0:
        return 0
    if safe:
        pos.height = floor
        world.bus.emit(Note(text=f"{eid} descends {far} squares safely"))
        return 0

    _FALLING.add(key)
    try:
        ev = world.bus.emit(Fell(actor=eid, squares=far, from_=by))
        if ev.cancelled:
            # It caught itself. The height is unchanged -- it is still up
            # there -- so it stops *falling*, or the next square it is slid
            # to drops it all over again.
            mv = world.get(eid, Movement)
            if mv is not None:
                mv.using = "climb"
            world.bus.emit(Note(text=f"{eid} catches itself {far} squares up"))
            return 0
        # Read back off the event, not off the locals: an interrupt softens
        # a fall by changing these, and the emitter is the one that acts.
        pos.height = floor
        dice = ev.squares // SQUARES_PER_DIE
        rolled = sum(world.rng.roll(FALL_DIE).total for _ in range(dice))
        hurt = max(0, rolled - ev.soften)
        if hurt:
            from .resolve import deal_damage

            deal_damage(
                world, by or eid, eid, hurt, DamageType.UNTYPED, "fall",
                from_attack=False,
            )
        if ev.prone:
            world.effects.apply(
                eid, by or eid, When.ENCOUNTER, label="fall",
                conditions=[Condition.PRONE],
            )
        return hurt
    finally:
        _FALLING.discard(key)


#: What an edge save has to beat -- the printed saving-throw number, and the
#: same one `Cast.save` uses. Named rather than inlined for the reason
#: `SQUARES_PER_DIE` is: a number and the rule it comes from must not drift.
SAVE_BEATS = 10


def catches_itself(
    world: World, eid: int, into: tuple[int, int], *,
    bonus: int = 0, power: str = "",
) -> bool:
    """Can this creature avoid being forced over an edge? PHB p284.

    > *"**Catching Yourself:** If a power or a bull rush forces you over a
    > precipice or into a pit, you can immediately make a saving throw to
    > avoid going over the edge. This saving throw works just like a normal
    > saving throw, except you make it as soon as you reach the edge, not at
    > the end of your turn."*

    True means it caught itself and **does not move**; False means it goes
    over and the fall follows from `ground` as it always did.

    **Scoped to forced movement, which is what the rule says.** Walking off
    a ledge of your own accord gets no save -- the printed sentence names a
    power or a bull rush -- so this is called from `movement.forced` and not
    from `step`. Putting it in `drop` instead would have handed the save to
    every voluntary fall in the game, which is the more generous reading and
    not the printed one.

    `when_="edge"` on the event is the printed distinction, and it is the
    whole reason that field exists (#671): the throw is taken *now*, not at
    the end of the turn, so a row reading "a bonus to saving throws made at
    the start of your turn" must not pay out on it. The one content reader
    of `when_` tests for `"early"` explicitly, so it is unaffected.

    **Any drop down is an edge**, however shallow. A one-square step down
    deals no damage -- `SQUARES_PER_DIE` is 2 -- but the printed rule is
    about whether you went *over*, not about how far, so the save is offered
    and the damage follows separately. Gating it on a damaging height would
    be inventing a threshold the page does not print.
    """
    from .events import SavingThrow
    from .resolve import _mods

    pos = world.get(eid, Position)
    if pos is None or airborne(world, eid):
        # A flyer is where it means to be; there is no edge to go over.
        return False
    if world.grid.floor(into) >= world.grid.floor(pos.square):
        return False
    natural = world.rng.roll("1d20").total
    plus = bonus + _mods(
        world, eid, "save",
        {"actor": eid, "label": "falling", "conditions": frozenset(),
         "ongoing": False, "dtype": None, "keywords": frozenset(),
         "when_": "edge", "granted_via": power},
    )
    return world.bus.emit(
        SavingThrow(
            actor=eid, against="falling", natural=natural, bonus=plus,
            saved=natural + plus >= SAVE_BEATS, when_="edge",
            # **`()` and not `frozenset()`, which is `#1120`.** A
            # frozenset is not JSON-serialisable and `EventDTO.model_dump`
            # keeps it, so `json.dumps` raises in the SSE generator and the
            # log panel goes blank -- *even when it is empty*, which is
            # what made this one invisible. A falling save is rare enough
            # that no fixture and no pinned day rolls one.
            granted_via=power, keywords=(),
        )
    ).saved


def ground(world: World, eid: int) -> int:
    """Settle a creature onto the floor of the square it is standing in.

    Called at the end of every step. Walking off a ledge -- or into a square
    somebody has sunk -- leaves the creature standing above its own floor,
    and that is a fall. A flyer is not settled; it is where it means to be.
    """
    pos = world.get(eid, Position)
    if pos is None or airborne(world, eid):
        return 0
    floor = world.grid.floor(pos.square)
    if pos.height < floor:
        pos.height = floor  # walked up out of a hollow
        return 0
    return drop(world, eid)
