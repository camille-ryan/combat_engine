"""Moving, and everything that watches something move.

Adjacency is **derived here and nowhere else**. Every step diffs the set of
creatures the mover is next to and emits `AdjacencyGained` / `AdjacencyLost`,
so opportunity attacks, aura entry and exit, and "when a creature moves
adjacent to you" all hang off two events instead of each re-scanning the
board. Anything that cares about being next to something subscribes to those
two and is correct for free.

An opportunity attack interrupts the move, so the window is opened *while the
mover is still in the square it is leaving*. Resolve it after the step and
the attack lands in the wrong place.

**The board is two-dimensional even though flight is not.** A creature with a
mode that goes over or under the ground -- flying, swimming, burrowing --
passes straight through squares an enemy is standing in, and only needs a
free square to *land* in. That is the whole of the third dimension here: a
transit right, not a coordinate. Provoking is untouched by it, because
passing through a square never provoked in the first place; leaving a
threatened one does, and it still does in the air.

A flyer **lands at the end of its turn**. So the free-square requirement is
not checked per move -- a creature may spend a move action and stop over an
enemy's head, then spend another -- it is checked once, when the turn ends,
and `settle` puts anything still overlapping into the nearest square it fits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .components import Movement, Position
from .events import (
    AdjacencyGained,
    AdjacencyLost,
    EnterSquare,
    ForcedMove,
    LeaveSquare,
    Moved,
    MoveEnd,
    MoveStart,
    Note,
    OpportunityWindow,
)
from .grid import Square, distance, footprint, neighbours, spread
from .grid import distance as grid_distance
from .query import adjacent, alive, can_move, creatures, enemies, squares
from .types import Forced, Relation, Size

if TYPE_CHECKING:
    from .ecs import World

#: Moves that never provoke an opportunity attack.
_SAFE = {"shift", "teleport", "push", "pull", "slide", "place", "swap"}

#: The kinds of going whose cost is actually priced against difficult
#: terrain, which is what `Movement.ignores_when` can be keyed on. A
#: teleport or a forced slide pays nothing for terrain at all, so an
#: exemption scoped to one would be a modifier nothing consults -- this
#: component's commonest bug. `Cast.ignores_difficult` refuses anything
#: outside this set rather than accepting it quietly.
PRICED_KINDS = frozenset({"walk", "shift", "charge", "run"})

#: Modes that leave the ground, and so pass over whoever is standing on it.
#: Teleport is not one of them -- it has no path to pass along, so it has to
#: arrive somewhere it fits.
OVERHEAD = {"fly", "swim", "burrow"}


def place(world: World, eid: int, square: Square) -> None:
    """Put a creature on the board without any of this firing. Setup only."""
    pos = world.need(eid, Position)
    pos.square = square
    # An explicit footprint is about *where a thing was laid*, so putting
    # it somewhere else discards it. `place` means "at this square, at
    # this size"; keeping the old spans would have `Position.squares`
    # name the squares it used to fill.
    pos.spans = frozenset()
    world.grid.lift(eid)
    if not world.grid.place(eid, footprint(square, pos.size)):
        # Somebody is already indexed there. `grid.place` refuses rather
        # than overwriting -- overwriting *unindexes* the sitting tenant
        # -- so without this the newcomer stands in a square the grid
        # does not know it is in, and cover, blocking and occupancy all
        # read the wrong answer until it next moves.
        world.bus.emit(Note(text=f"{eid} placed on an occupied square {square}"))


def _neighbours(world: World, eid: int) -> set[int]:
    return {o for o in creatures(world) if o != eid and adjacent(world, eid, o)}


def step(
    world: World,
    eid: int,
    to: Square,
    *,
    kind: str = "walk",
    mode: str = "walk",
    through: bool = False,
    stretched: int = 0,
) -> bool:
    """Move one square. Returns False if the square could not be entered.

    The order matters: leaving is announced from the old square, the
    opportunity window opens while the mover is still standing there, and
    only then does the mover actually arrive.
    """
    pos = world.get(eid, Position)
    if pos is None:
        return False
    # **An explicit footprint travels with the thing.** `step` recomputed
    # `footprint(to, size)` and never touched `spans`, so a five-square
    # wall that was slid kept naming its old five squares to cover,
    # line of effect, flanking and targeting while occupying one new
    # square in the index -- the two disagreed in both directions at
    # once. A `Barrier` carries `Health`, so it is in the target pool and
    # any burst that pushes can reach it.
    if pos.spans:
        dx, dy = to[0] - pos.square[0], to[1] - pos.square[1]
        target = frozenset((x + dx, y + dy) for x, y in pos.spans)
    else:
        target = footprint(to, pos.size)
    # `through` is trampling and melding: entering a square somebody else is
    # standing in. Terrain still blocks, which is what `overhead` already
    # means to `_clear`.
    overhead = mode in OVERHEAD or through
    if not _clear(world, eid, target, overhead=overhead):
        return False

    before = _neighbours(world, eid)
    # Everyone who *threatens* the mover, which is not the same as everyone
    # adjacent to it. Extending reach only in the second half of the test
    # meant a watcher was consulted solely on steps where it had been
    # adjacent beforehand -- and one step cannot carry a mover from
    # adjacent to more than two squares off, so `c.threatens(2)` turned
    # opportunity attacks off entirely instead of extending them.
    watchers = before | _reachers(world, eid)
    from_ = pos.square

    for sq in sorted(pos.squares):
        world.bus.emit(LeaveSquare(actor=eid, square=sq))

    if kind not in _SAFE:
        # How far each watcher threatens is asked of the watcher, below.
        # It was a ring fixed at one square around the destination, so "it
        # can make opportunity attacks against enemies within 2 squares"
        # had nowhere to go -- the row that wanted it watched `Moved` and
        # fired a beat after the engine's own window, which interrupts.
        # The common ring, computed once. Almost nothing has extended reach,
        # and asking each watcher separately turned a full audit from 84
        # seconds into 331 -- the cost is per watcher per step, and a fight
        # takes thousands of steps.
        after_reach = spread(target, 1)
        foes = enemies(world, eid)
        for other in sorted(watchers):
            if other not in foes:
                continue
            reach = _threat(world, other, eid)
            if reach == 1:
                left = not (after_reach & squares(world, other))
            else:
                left = not (spread(squares(world, other), reach) & target)
            if left:
                world.bus.emit(
                    OpportunityWindow(actor=other, provoker=eid, why="moved away",
                                      kind_=kind, mode=mode)
                )

    world.grid.lift(eid)
    pos.square = to
    if pos.spans:
        pos.spans = target
    if not _occupied(world, eid, target):
        # Overhead and directly above somebody: stay out of the occupancy
        # index until `settle` puts the creature down at the end of its turn.
        world.grid.place(eid, target)

    for sq in sorted(target):
        world.bus.emit(EnterSquare(actor=eid, square=sq))

    moved = Moved(actor=eid, from_=from_, to=to)
    # How the creature got here, as a plain attribute -- see `Moved`. Set on
    # every emission, so `ev.kind_` is never missing.
    moved.kind_ = kind
    # And how many squares beyond its printed distance were spent getting
    # here, the same way and for the reason `Moved`'s note gives: a field
    # would reach the wire and every replay fixture, and this is not a
    # change in how a fight resolves. `0` unless a caller lengthened the
    # move *and* the decider spent what it was given. #572.
    moved.stretched_ = stretched  # ty: ignore[unresolved-attribute]
    world.bus.emit(moved)

    # A mount carries its rider. Set after the mount has arrived, so the
    # rider is put down in the square the mount is actually standing in --
    # and quietly, because the rider is being carried rather than moving,
    # and being carried past somebody provokes nothing.
    for passenger in world.relations.targets(Relation.RIDDEN_BY, eid):
        seat = world.get(passenger, Position)
        if seat is not None and seat.square != to:
            world.grid.lift(passenger)
            seat.square = to
            # Deliberately **not** indexed: the mount was put in these
            # squares a moment ago, so `grid.place` would refuse anyway
            # and a rider is a sharer like a flyer overhead. Saying so
            # here stops it reading as a write that silently failed.
            del seat
            carried = Moved(actor=passenger, from_=from_, to=to)
            carried.kind_ = kind
            # **Zero, and not the mount's number.** `stretched_` is "squares
            # this creature spent beyond what its own card printed", and a
            # rider spent nothing -- it was carried. Set rather than left off,
            # because `Moved`'s note promises the attribute is never missing,
            # and a `getattr(ev, "stretched_", 0)` reader would be reading the
            # default where there is a real answer.
            carried.stretched_ = 0  # ty: ignore[unresolved-attribute]
            world.bus.emit(carried)

    # Whatever it stepped into, it now stands on the floor of. A square that
    # has been sunk has its floor below the rest of the board, so this is
    # where walking off a ledge becomes a fall -- see `engine/falling.py`.
    if world.grid.floor(to) != 0 or pos.height != 0:
        from .falling import ground

        ground(world, eid)

    after = _neighbours(world, eid)
    for other in sorted(after - before):
        world.bus.emit(AdjacencyGained(actor=eid, other=other, mover=eid))
        world.bus.emit(AdjacencyGained(actor=other, other=eid, mover=eid))
    for other in sorted(before - after):
        # `mover=eid` on both, exactly as the gained pair above: whoever
        # moved is the same creature whichever end is reading. Without it
        # "when an enemy moves away from it" also fired on the creature's
        # own retreat, and "enters or leaves my reach" could not be written
        # as one rule. #368.
        world.bus.emit(AdjacencyLost(actor=eid, other=other, mover=eid))
        world.bus.emit(AdjacencyLost(actor=other, other=eid, mover=eid))
    return pos.square != from_


def overrun(world: World, eid: int, to: Square, *, kind: str = "walk") -> list[int]:
    """Walk to a square, going straight through anybody in the way.

    Returns everyone whose space was entered, in the order they were
    trampled, so the body can attack each one. The mover must end somewhere
    free -- the trample ends where it can stand -- and the walk stops at the
    last square it could.
    """
    entered: list[int] = []
    pos = world.get(eid, Position)
    if pos is None:
        return entered
    for sq in _line(pos.square, to)[1:]:
        under = {
            who
            for s in footprint(sq, pos.size)
            if (who := world.grid.occupant(s)) is not None and who != eid
        }
        if not step(world, eid, sq, kind=kind, through=True):
            break
        for who in sorted(under):
            if who not in entered:
                entered.append(who)
    # It cannot finish standing on somebody, so shuffle into the nearest
    # free square. That is the printed rule rather than a convenience.
    if _occupied(world, eid, pos.squares):
        _retreat(world, eid)
    return entered


def _retreat(world: World, eid: int) -> bool:
    """Shuffle out of an occupied square into the nearest free one."""
    pos = world.get(eid, Position)
    if pos is None:
        return False
    for sq in sorted(spread(pos.squares, 1)):
        if _clear(world, eid, footprint(sq, pos.size)) and sq != pos.square:
            return step(world, eid, sq, kind="teleport")
    return False


def _line(a: Square, b: Square) -> list[Square]:
    """Every square from a to b, diagonals counting as one step."""
    out = [a]
    x, y = a
    while (x, y) != b:
        x += (b[0] > x) - (b[0] < x)
        y += (b[1] > y) - (b[1] < y)
        out.append((x, y))
    return out


def _clear(
    world: World,
    eid: int,
    target: set[Square] | frozenset[Square],
    *,
    overhead: bool = False,
) -> bool:
    """Can `eid` be in these squares? Terrain always blocks; a creature only
    blocks somebody moving along the ground."""
    ghost = phasing(world, eid)
    for sq in target:
        # Phasing walks through earth and rock. It still has to *stop*
        # somewhere legal, which `settle` enforces -- this only says the
        # wall is not a wall on the way past.
        #
        # **A porous blocker is narrower than phasing**, and that narrowness
        # is the whole of what two cards print: "can enter and move through a
        # porous obstacle that would otherwise prevent movement (such as a
        # door or a cracked window)". Granting `c.phasing` would let the
        # creature leave through a solid wall, which the card does not say.
        # `Grid.porous` records which blockers have a gap and
        # `c.squeeze_through` is the permission. #674.
        if (not world.grid.passable(sq) and not ghost
                and not _may_squeeze(world, eid, sq)):
            return False
        who = world.grid.occupant(sq)
        if who is None or who == eid:
            continue
        # **"Cannot enter by any means" beats the waivers**, which is the
        # whole of what the clause adds -- see `blocks_entry`.
        #
        # **The order is a style choice and not a correctness one, and a
        # plant proved my first claim about it false.** I had written that
        # this must be asked *before* `overhead or ghost`; moving it after
        # left `drivers.sealed_space` green, correctly, because both
        # branches return independently and a phasing mover simply skips
        # the second one. Recorded rather than quietly fixed: the plant
        # that stays green is evidence about something, and here it was
        # evidence about the comment.
        if blocks_entry(world, who, eid):
            return False
        # **Two questions, not one.** `shares_space` is the occupant's
        # property and `may_enter` is the mover's; a creature gets through
        # if either says so. Asked in that order because the occupant's is
        # the cheaper read and the commoner case. #626.
        if (not (overhead or ghost)
                and not shares_space(world, who)
                and not may_enter(world, eid, who)):
            return False
    return True


def _reachers(world: World, eid: int) -> set[int]:
    """Creatures with extended reach that covers `eid`.

    Only creatures carrying a modifier are considered, because the ordinary
    ring is already in `_neighbours` and walking every creature on the board
    per step is what took a full audit from 84 seconds to 331 the first time
    reach became a modifier.
    """

    mine = squares(world, eid)
    out: set[int] = set()
    for other in creatures(world):
        if other == eid:
            continue
        # **No early exit on `Mods`.** This skipped every creature carrying no
        # modifiers, which was sound while a modifier was the only thing that
        # could stretch a reach and is wrong now that a weapon and a row can:
        # a creature with a glaive and no modifiers reaches two and was skipped.
        reach = _threat(world, other, eid)
        if reach > 1 and spread(squares(world, other), reach) & mine:
            out.add(other)
    return out


def _threat(world: World, eid: int, against: int | None = None) -> int:
    """How far this creature threatens, in squares.

    `against` is **who is walking past**, and it is what makes a `when=` gate
    on a threat zone able to say anything about them. Without it the context
    handed to `mods.total` was `{}`, so `c.threatens(when=)` -- which landed
    with #425 -- could read the threatener's own state and nothing else. The
    one row in the tree whose printed threat clause is about the *target*
    rather than the threatener could not be written at all. #443.

    Passed as `target`, not a new key: `resolve`'s attack context already
    calls the creature being swung at that, and the creature walking past a
    threat zone is exactly the prospective target. The threatener is
    `attacker` for the same reason. A gate reads whichever it means.

    `None` when nobody in particular is walking past -- `reachable`'s preview
    asks how far a creature threatens in the abstract -- and a gate that
    needs a target gets `None` and should answer False rather than guess.

    Three things can stretch it and only the first was read: a `"reach"`
    modifier, **the weapon in its hand**, and **the reach of the row it would
    swing**. An opportunity attack is made with the basic attack, so that row's
    range is the range threatened -- which is also why asking the basic alone is
    not a simplification: a reach on some other card is not what the swing uses.

    `Weapon.reach` was read by nothing in the engine at all, so a glaive
    threatened one square; 12 of 117 printed weapons reach further than one. A
    monster's reach is on its row and was equally unread here, so a reach-2
    monster did not threaten at two either.

    Still cheap, which matters -- this is asked once per watcher per step. Two
    component lookups and one registry lookup, no iteration over what a creature
    knows.
    """
    from .components import Mods

    mods = world.get(eid, Mods)
    # **Reach does not threaten, and that is the printed rule.** The compendium's
    # Reach entry: "With a reach weapon, a creature can make melee attacks against
    # enemies that are 2 squares away ... **Even so, the wielder can make
    # opportunity attacks only against enemies adjacent to it** and can flank only
    # enemies adjacent to it."
    #
    # So this used to read the weapon in hand and the basic attack's own range, and
    # was wrong for **every** reach wielder. Camille caught it. It is wrong for
    # monsters too: of 938 that print a Reach of 2 or more, only **76** have
    # threatening reach -- the separate ability that *does* extend it, and the only
    # thing that should.
    #
    # Nothing sets `threatening_reach` yet, so this is adjacency for everybody
    # today. The 76 want the flag off their blocks and that is #306; being wrong
    # for 76 monsters is better than for 938 plus the whole party.
    ctx = {"attacker": eid, "target": against}
    if mods is not None and mods.items and mods.total("threatening_reach", ctx) > 0:
        return max(1, 1 + mods.total("reach", ctx))
    return 1


def phasing(world: World, eid: int) -> bool:
    """Can this creature move through solid things?"""
    from .components import Movement

    mv = world.get(eid, Movement)
    return bool(mv and "phasing" in mv.modes)


def shares_space(world: World, eid: int) -> bool:
    """Does this creature let others stand where it stands?

    The occupancy half of `c.shares_space`. Read off `Mods` rather than off
    `Movement.modes`, because it is not a way of moving -- `mode_of` picks
    the best mode a creature has and a creature cannot travel by being
    shared -- and because the printed lines give it a duration.
    """
    from .components import Mods

    mods = world.get(eid, Mods)
    return bool(mods and mods.items and mods.total("shares_space", {}) > 0)


def _may_squeeze(world: World, eid: int, sq: Square) -> bool:
    """May this creature pass a blocker with a gap in it? See `Grid.porous`.

    Gated through `Mods` on the kind of gap, so "a door or a cracked window"
    is a predicate on one mechanism rather than a second mechanism -- the
    arrangement `may_enter` above uses for the creature in the way, and
    `world.difficult` uses for the sort of going.

    An empty kind in the permission means any gap at all, which is what both
    printed rows mean: neither names a sort, they name the property.
    """
    from .components import Mods

    kind = world.grid.porous.get(sq)
    if kind is None:
        return False
    mods = world.get(eid, Mods)
    if mods is None or not mods.items:
        return False
    return mods.total("may_squeeze", {"gap": kind}) > 0


def may_enter(world: World, mover: int, occupant: int) -> bool:
    """Has **this mover** a standing permission to enter that creature's
    square?

    The mover's side of the question `shares_space` asks of the occupant,
    and the two are not interchangeable. That one is *"anyone may stand in
    this creature's square"*, laid on the creature being entered. Three
    monster traits print the other sentence -- *"the m6654 can enter
    enemies' spaces during its movement"* -- and `m6654a1`'s docstring has
    the measurement of what happens if the mirror is used anyway:

        shares_space(me)              True
        I enter the foe's square      False   <- the printed clause
        the foe enters my square      True    <- printed nowhere

    So it opened the creature's own square to the whole board and left it as
    unable to step through anybody as before: a row both weaker and stronger
    than its card at once. #626.

    **Not `c.overrun`, which is a stated move** -- handed a destination,
    walks a line, reports who it crossed. These are standing properties that
    must hold for moves *other* rows and the AI policy take. `m4306a1`
    prints the stated move and is written with `c.overrun`, so the
    distinction is already load-bearing in the tree.

    Gated through `Mods`, so the narrowing `m5808a0` prints -- Medium or
    Small **enemies** only -- is a predicate on one mechanism rather than a
    second mechanism. The context names the two participants, the
    convention `query.immune_to` states.
    """
    from .components import Mods

    mods = world.get(mover, Mods)
    if mods is None or not mods.items:
        return False
    return mods.total("may_enter", {"mover": mover, "occupant": occupant}) > 0


def blocks_entry(world: World, eid: int, mover: int) -> bool:
    """"An enemy cannot enter this creature's space by any means."

    Eight stat blocks print that sentence word for word -- `m5623a1`,
    `m5624a1`, `m5625a0`, `m5626a1`, `m6403a1`, `m6404a1`, `m6405a1`,
    `m6406a1` -- and it is the exact opposite of `c.shares_space`, so it is
    stored the same way and read in the same places.

    **"By any means" is about the waivers, which is the only thing it can
    be about.** An occupied square is already closed: `_clear` refuses it,
    `_can_stop` refuses it and `_occupied` reports it. What the clause adds
    is that the two things which normally open one do not work here --
    phasing through the creature, and the creature having been made
    shareable by something else.

    **It does not beat `overhead`, and that is a reading rather than an
    oversight.** `overhead` is this engine's two-dimensional stand-in for a
    flyer passing *above* a ground creature, and in the printed rules that
    is not entering its space at all. Blocking it here would make the
    clause say something stronger than the card, on the strength of a
    modelling choice. Teleport needs no handling either: it has no path to
    check, so only its destination is tested and that goes through
    `_can_stop`, which the plain occupancy rule already closes.

    **Enemies only**, as printed. `side` is asked of the mover rather than
    assumed, so an ally walking past is governed by the ordinary rule.
    """
    from .components import Mods
    from .query import team as side_of

    mods = world.get(eid, Mods)
    if not (mods and mods.items and mods.total("blocks_entry", {}) > 0):
        return False
    # **Two `team` reads and not `query.enemies`**, which walks every
    # creature on the board. This sits inside `_clear`, which runs per
    # square of every candidate destination -- the same cost argument
    # `_reachers`' docstring records from the time reach became a modifier
    # and an audit went from 84 seconds to 331.
    mine, theirs = side_of(world, eid), side_of(world, mover)
    return mine is not None and theirs is not None and mine is not theirs


def _occupied(world: World, eid: int, target: set[Square] | frozenset[Square]) -> bool:
    return any(
        (who := world.grid.occupant(sq)) is not None
        and who != eid
        and not shares_space(world, who)
        for sq in target
    )


def mode_of(world: World, eid: int, mode: str | None) -> str:
    """Resolve the mode a creature is moving with, defaulting to its best.

    A creature that can fly flies, because that is what makes its printed
    speed line mean anything without every caller having to ask.
    """
    from .components import Movement

    if mode is not None:
        return mode
    mv = world.get(eid, Movement)
    if mv is None:
        return "walk"
    for candidate in ("fly", "swim", "burrow"):
        if mv.modes.get(candidate):
            return candidate
    return "walk"


def walk(
    world: World, eid: int, path: list[Square], *, kind: str = "walk", mode: str | None = None
) -> int:
    """Walk a path one square at a time. Returns how many squares were covered.

    Difficult terrain costs an extra square, so the budget is spent here
    rather than checked by the caller.
    """
    if not can_move(world, eid):
        return 0
    # A walk and a shift are barred by different rows, and `step` is shared
    # with both -- so the bar is checked here, where the kind is known.
    #
    # **A charge is a walk for this.** `can_walk` is "it cannot use move actions to
    # walk or run", and a creature that cannot walk cannot run at somebody either --
    # so when the charge started passing `kind="charge"` (#301) this test had to
    # widen or the bar would have been skipped.
    #
    # The card is `c.no_walk`, which lays the modifier this reads, and
    # `c.immobilized`, which stops both kinds of going. **Not `c.cannot_shift`**, which is
    # no_walk's mirror -- it bars the *shift* and leaves the walk -- so a rooted
    # creature charges, correctly, and always did. Camille caught me naming it here
    # as the hazard; measured, `can_walk` is True under `rooted` and False under
    # `immobilized`, and the charge covers 0 squares under the second.
    from .query import can_walk

    if kind in ("walk", "charge") and not can_walk(world, eid):
        return 0
    mode = mode_of(world, eid, mode)
    # The return is read. "You can cancel that movement as an immediate
    # interrupt" is a printed line on several rows, and the event was
    # emitted and thrown away -- the fourth time this session that a
    # cancellable event had no reader.
    if world.bus.emit(MoveStart(actor=eid, kind_=kind)).cancelled:
        return 0
    spent = 0
    # Held past the end of the move, not just during it. "Requirement: the
    # creature must be climbing" is checked when a power is *used*, and the
    # creature is standing still at that moment -- a flag that only held
    # mid-step would be false exactly when the question gets asked. A
    # creature that climbed a wall is still on the wall; `settle` puts a
    # flyer down at the end of its turn and clears it there.
    mv = world.get(eid, Movement)
    if mv is not None:
        mv.using = "" if mode == "walk" else mode
    for sq in path:
        if not step(world, eid, sq, kind=kind, mode=mode):
            break
        spent += 2 if sq in world.difficult(eid, kind) else 1
    pos = world.get(eid, Position)
    world.bus.emit(MoveEnd(actor=eid, at=pos.square if pos else (0, 0), kind_=kind))
    return spent


def risk_along(world: World, eid: int, path: list[Square]) -> str:
    """What walking this path would cost you that is not movement.

    Answered here because it is a rule, and the page is not allowed to know
    any. It asks the same two questions `step` asks while it is moving --
    who am I leaving, and what am I walking into -- without moving anybody.

    Returns a short reason, or "" when the way is clear. A reason rather
    than a flag because the interface shows it: "provokes" and "crosses a
    zone" are different warnings and a player weighs them differently.
    """
    pos = world.get(eid, Position)
    if pos is None or not path:
        return ""

    foes = [o for o in enemies(world, eid) if alive(world, o)]
    where = {o: squares(world, o) for o in foes}
    at = pos.square
    hostile: set[Square] = set()
    for _zid, zone in world.zones.all():
        if zone.owner in where:
            hostile |= zone.squares

    # Each foe's own reach, read once rather than per step: the hardcoded 1 here
    # made this preview disagree with `step`, which has always spread by the
    # watcher's reach. A creature with a reach weapon provoked in play and not in
    # the preview the policy scores against.
    spans = {foe: _threat(world, foe, eid) for foe in foes}
    for nxt in path:
        next_space = footprint(nxt, pos.size)
        # Leaving a square somebody threatens, and not staying in their
        # reach, is what opens the window -- the same test `step` makes.
        for foe in foes:
            span = spans[foe]
            here_reach = spread(footprint(at, pos.size), span)
            if (here_reach & where[foe]) and not (spread(next_space, span) & where[foe]):
                return "provokes an opportunity attack"
        if next_space & hostile:
            return "walks into an enemy zone"
        at = nxt
    return ""


def settle(world: World, eid: int) -> bool:
    """Put a creature down at the end of its turn.

    A flyer may stop over an enemy's head mid-turn; it may not still be there
    when the turn ends. The nearest square it fits in wins, and ties are
    broken in sorted order so two runs of a seed land it in the same place.
    """
    mv = world.get(eid, Movement)
    if mv is not None and mv.using == "fly":
        mv.using = ""       # it comes down; it is not flying any more
    pos = world.get(eid, Position)
    if pos is None or _clear(world, eid, pos.squares):
        if pos is not None:
            world.grid.place(eid, pos.squares)
        return False
    here = pos.square
    for radius in range(1, max(world.grid.width, world.grid.height)):
        ring = sorted(
            sq
            for sq in spread({here}, radius)
            if distance(sq, here) == radius and _clear(world, eid, footprint(sq, pos.size))
        )
        if ring:
            world.bus.emit(MoveStart(actor=eid, kind_="land"))
            step(world, eid, ring[0], kind="place", mode="walk")
            world.bus.emit(MoveEnd(actor=eid, at=ring[0]))
            return True
    return False


def shift(
    world: World, eid: int, to: Square, *, mode: str | None = None,
    share: bool = False, stretched: int = 0, path: list[Square] | None = None,
) -> bool:
    """A shift is a move that does not provoke. One square unless a power says otherwise.

    `share` is for the handful of things that move *into* somebody else's
    square rather than beside it -- a creature that melds with its target.

    **`path` walks the squares in between, and two rows need that.** This
    called `step` once -- one jump to the destination -- so a multi-square
    shift entered no square between where it started and where it ended, and
    "during this shift you can move through the target's space" had no moment
    to happen in. `f2105b` prints that clause and `p12426b` charges damage
    "the first time you enter an enemy's space during the shift", which is an
    `EnterSquare` per square crossed and nothing less. `step` emits one
    already; it was never being asked more than once. #684.

    No path means the old single jump, so every caller naming a destination
    outright -- "shift into the square the target left" -- is unchanged.

    Two details the shape of this decides:

    * **`stretched` is charged once, on the last step.** It is the difference
      between the printed distance and the square actually taken, and
      `Moved.stretched_` reporting it per square would report the whole
      stretch for every square crossed.
    * **`share` applies to the last square only.** Along the way, entering an
      occupied square is governed by `may_enter`, which `_clear` consults and
      which `c.may_enter(when=)` is the writer for (#673). On the *final*
      square it means something else -- ending on top of somebody, which only
      a melding power may do.
    """
    from .query import can_shift

    if not can_shift(world, eid):
        return False
    if world.bus.emit(MoveStart(actor=eid, kind_="shift")).cancelled:
        return False
    route = list(path) if path else [to]
    walked = mode_of(world, eid, mode)
    moved = False
    for i, square in enumerate(route):
        last = i == len(route) - 1
        if not step(world, eid, square, kind="shift", mode=walked,
                    through=share and last,
                    stretched=stretched if last else 0):
            break
        moved = True
    pos = world.get(eid, Position)
    world.bus.emit(MoveEnd(actor=eid, at=pos.square if pos else (0, 0), kind_="shift"))
    return moved


def teleport(world: World, eid: int, to: Square, *, share: bool = False,
             stretched: int = 0) -> bool:
    # Reads the answer, like `walk` and `shift`. A row that stops movement
    # can then decide for itself whether a teleport counts, by looking at
    # `ev.kind_` -- which is a choice it cannot make if this is ignored.
    if world.bus.emit(MoveStart(actor=eid, kind_="teleport")).cancelled:
        return False
    moved = step(world, eid, to, kind="teleport", mode="walk", through=share,
                 stretched=stretched)
    pos = world.get(eid, Position)
    world.bus.emit(MoveEnd(actor=eid, at=pos.square if pos else (0, 0), kind_="teleport"))
    return moved


# -- forced movement --------------------------------------------------------


def forced(
    world: World,
    source: int,
    target: int,
    how: Forced,
    amount: int,
    *,
    anchor: Square | None = None,
    to: Square | None = None,
    power: str = "",
) -> int:
    """Push, pull or slide `target` up to `amount` squares.

    `anchor` is what the movement is measured against. It defaults to the
    source's square, which is right for most powers and wrong for the ones
    that say "away from the zone" or "toward the ally" -- those pass their
    own, which is why this is a parameter rather than a lookup.

    Forced movement never provokes, and stops dead the first square it cannot
    enter rather than trying to route around it.
    """
    pos = world.get(target, Position)
    if pos is None or amount <= 0:
        return 0
    if anchor is None:
        src = world.get(source, Position)
        anchor = src.square if src else pos.square

    shove = ForcedMove(source=source, target=target, how=how, squares=amount)
    shove.power = power

    # The shove is negotiated, so the agreed distance is worked out inside
    # the callback, which is handed the event and cannot see `amount`. A
    # listener may refuse the shove outright ("cannot be pushed, pulled or
    # slid") or shorten it ("moves 1 square fewer"), and both used to be
    # written against a local that nothing read back.
    agreed = 0

    def settle(ev: ForcedMove) -> None:
        nonlocal agreed
        from .resolve import _mods

        ctx = {"how": how.value, "power": power}
        # Two sides to a shove, and only the shoved one was read. The
        # creature resisting shortens it with `"forced"`; the creature
        # doing it lengthens it with `"forcing"` -- "your pushes move the
        # target 1 extra square" is a feat and a magic-item line, not a
        # one-off, so it needs a key of its own rather than a negative
        # `"forced"` on somebody else.
        resists = _mods(world, ev.target, "forced", ctx)
        shoves = _mods(world, ev.source, "forcing", ctx)
        agreed = max(0, ev.squares + shoves - resists)

    if world.bus.emit(shove, settle).cancelled or agreed <= 0:
        return 0
    amount = agreed
    if to is not None:
        # A row that names the square it wants. **Actually** one step at a
        # time: `step` has no adjacency check, so passing `to` straight in
        # jumped the whole distance in a single move -- a pull 2 would drag
        # a creature across the board -- and then called `step` against the
        # square it was already standing in for every remaining point,
        # announcing a Leave/Enter/Moved for a square nobody left.
        moved = 0
        for sq in _line(world.need(target, Position).square, to)[1:]:
            if moved >= amount or not step(world, target, sq, kind=how.value):
                break
            moved += 1
        return moved
    moved = 0
    for _ in range(amount):
        nxt = _forced_square(world, source, target, anchor, how)
        if nxt is None or not step(world, target, nxt, kind=how.value):
            break
        moved += 1
    return moved


def forced_squares(
    world: World, target: int, anchor: Square, how: Forced
) -> list[Square]:
    """Every square this step of a forced move could legally go to.

    Push must end further from the anchor, pull must end nearer, and a slide
    may go anywhere. Directly away from the anchor there are normally
    **three** of them -- the straight step and the two diagonals either side
    -- and which one is taken is the pusher's choice, not a detail. Driving
    somebody into a wall, off a ledge, or out of their ally's reach is the
    whole reason to take a power that pushes.
    """
    pos = world.get(target, Position)
    if pos is None:
        return []
    here = pos.square
    now = distance(here, anchor)
    out: list[Square] = []
    for cand in neighbours(here):
        then = distance(cand, anchor)
        ok = {
            Forced.PUSH: then > now,
            Forced.PULL: then < now,
            Forced.SLIDE: True,
        }[how]
        if ok and _clear(world, target, footprint(cand, pos.size)):
            out.append(cand)
    return sorted(out)


def _forced_square(
    world: World, source: int, target: int, anchor: Square, how: Forced
) -> Square | None:
    """Where this step of a forced move goes, asking whoever is pushing.

    The choice belongs to the creature applying the movement, so it goes
    through `world.decide` like any other. The first version picked the
    straightest square and never asked, which quietly turned every push in
    the game into a single fixed line.
    """
    options = forced_squares(world, target, anchor, how)
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    return world.decide(source, how.value, options, f"{how.value} to which square")


# -- reachability -----------------------------------------------------------


def reachable(
    world: World, eid: int, budget: int, *, mode: str | None = None,
    kind: str = "walk", share: bool = False,
) -> dict[Square, list[Square]]:
    """Every square reachable within `budget`, with a path to each.

    Dijkstra over the eight steps, charging two for difficult terrain, and
    **ranked by three things in order**: what it costs, what it costs you
    that is not movement, and how straight it looks.

    The third matters more than it sounds. Distance here is Chebyshev, so a
    diagonal costs the same as a step sideways and a great many routes tie
    on price. Whichever the search happened to reach first then won -- and
    since the neighbours were walked in sorted order that was reliably the
    one bearing up and left, so the drawn path wandered out to a corner and
    came back rather than going where the crow goes. Nothing was wrong with
    it except that no player would ever have chosen it.

    A flyer's search passes over occupied squares but will not offer one as a
    destination, since it has to come down at the end of the turn anyway.

    `share` is the mover asking for the opposite: a creature that melds with
    the one it stands on wants exactly the square the flyer filter removes.
    It waives occupancy in both places -- along the path and at the stop --
    and waives nothing else. Off by default, so no existing caller moves.
    #527.
    """
    pos = world.get(eid, Position)
    if pos is None or budget <= 0:
        return {}
    overhead = mode_of(world, eid, mode) in OVERHEAD
    # Priced as the sort of move it is. A creature exempt from difficult
    # terrain only while shifting reaches a square at one square of cost that
    # it cannot reach at one while walking, and this is the only place that
    # difference can be read -- the exemption is spent here, not in `step`.
    rough = world.difficult(eid, kind)
    start = pos.square
    threat = _threatened_from(world, eid)

    # (movement spent, squares walked under threat). Lexicographic, so a
    # safer route wins outright and only a tie on safety is settled by cost.
    best: dict[Square, tuple[int, int]] = {start: (0, 0)}
    came: dict[Square, list[Square]] = {start: []}
    frontier = [start]
    while frontier:
        frontier.sort(key=lambda s: best[s])
        here = frontier.pop(0)
        spent, risked = best[here]
        # A linked square is one step away like any neighbour. `step` never
        # asked whether a destination was adjacent to where the mover stood,
        # so the search is the only place a rift has to be known about.
        for nxt in sorted(set(neighbours(here)) | world.grid.links.get(here, frozenset())):
            if not _clear(world, eid, footprint(nxt, pos.size),
                          overhead=overhead or share):
                continue
            step_cost = 2 if nxt in rough else 1
            score = (spent + step_cost, risked + _provokes_step(threat, here, nxt, pos.size))
            if score[0] > budget:
                continue
            known = best.get(nxt)
            if known is not None and score > known:
                continue
            if known is not None and score == known:
                came[nxt].append(here)      # another equally good way in
                continue
            best[nxt] = score
            came[nxt] = [here]
            frontier.append(nxt)

    paths = {sq: _straightest(start, sq, came) for sq in came if sq != start}
    # **Moving through a body is not standing in one.** A flyer's destinations
    # were already filtered this way; a phasing creature's were not, and
    # `_clear` waives occupancy for a ghost as readily as for a flyer -- so the
    # occupied square was offered as somewhere to stop.
    #
    # It was invisible while the destination list went to `World.decide`
    # unranked, because the occupied square was rarely first. `toward=` made it
    # the default: aimed at a creature, that square is the nearest one and so
    # the first taken, and a row that leaps at a victim landed on top of it.
    # 79 content rows call `c.phasing`. #392.
    if overhead or share or phasing(world, eid):
        paths = {
            sq: path
            for sq, path in paths.items()
            if _can_stop(world, eid, footprint(sq, pos.size), share=share)
        }
    # **A tether, applied to the destinations rather than to the search.**
    # Fourteen rows print "cannot move more than N squares from ...", and
    # filtering here means a square beyond the leash is never offered -- the
    # UI cannot draw it and `policy/` cannot score it. Filtering the search
    # instead would also forbid *passing* through a far square to reach a
    # near one, which no card says. #512.
    from .query import leash_of

    tie = leash_of(world, eid)
    if tie is not None:
        held, radius = tie
        paths = {
            sq: path
            for sq, path in paths.items()
            if grid_distance(sq, held) <= radius
        }
    # **And the same filter reversed**, which is "cannot move closer to the
    # X (save ends)" -- seven rows, and none of them could be written. Here
    # rather than as a penalty for the same reason the tether is here, and
    # here rather than in the search for the same one: passing through a
    # nearer square to reach a farther one is not moving closer, and no card
    # forbids it.
    #
    # This is also what makes the printed word **"willingly"** right on the
    # four rows that print it: a push, a pull or a slide does not come
    # through `reachable`, so a creature can still be shoved towards the
    # thing it may not approach. `m6026a3` depends on that -- it pushes the
    # target three squares and *then* forbids the approach. #728.
    from .query import kept_away_from

    keep = kept_away_from(world, eid)
    if keep is not None:
        anchor, now = keep
        paths = {
            sq: path
            for sq, path in paths.items()
            if grid_distance(sq, anchor) >= now
        }
    return paths


def _can_stop(world: World, eid: int, target: frozenset[Square], *,
              share: bool = False) -> bool:
    """May `eid` *end* a move in these squares?

    `_clear` answers the neighbouring question -- may it be here on the way
    past -- and for a flyer or a phasing creature the two part company: both
    cross what neither may stand in. So this asks occupancy and terrain with
    **no** waiver for either, which is what the flyer filter was already doing
    by calling `_clear` without `overhead=`.

    `shares_space` is still honoured: a flyer directly above somebody and a
    creature melded with its target are the two things that legitimately end a
    move in an occupied square.

    **`share` is the other half of that sentence, and it was missing.**
    `shares_space` is the *occupant's* property -- "anybody may stand in my
    square" -- and the ten rows printing "it can move into an occupied
    square" are claims about the **mover**. Nothing read the second kind
    here, so a melding shift was never offered the square it was about.
    Terrain is unaffected: a creature that walks into bodies still cannot
    walk into a wall. #527.
    """
    for sq in target:
        if not world.grid.passable(sq):
            return False
        who = world.grid.occupant(sq)
        if who is None or who == eid or share:
            continue
        if not shares_space(world, who):
            return False
    return True


def _threatened_from(world: World, eid: int) -> dict[int, frozenset[Square]]:
    """Which squares each living enemy is standing in, for the threat test."""
    return {
        foe: squares(world, foe)
        for foe in enemies(world, eid)
        if alive(world, foe)
    }


def _provokes_step(
    threat: dict[int, frozenset[Square]], here: Square, nxt: Square, size: Size
) -> int:
    """Does stepping from one square to the next open an opportunity window?

    The same test `step` makes while moving: somebody adjacent before, and
    out of reach after.
    """
    if not threat:
        return 0
    before = spread(footprint(here, size), 1)
    after = spread(footprint(nxt, size), 1)
    return int(any(
        (before & where) and not (after & where) for where in threat.values()
    ))


def _straightest(start: Square, dest: Square, came: dict[Square, list[Square]]) -> list[Square]:
    """Rebuild one of the equally good routes -- the one nearest the line.

    Every predecessor recorded for a square reached it for the same price
    and the same risk, so the choice between them is free and may as well
    be made on looks. Walked backwards from the destination, because only
    then is there a line to be near: the straight one from start to *here*.
    """
    path: list[Square] = []
    node = dest
    seen = {dest}
    while node != start:
        options = [p for p in came.get(node, ()) if p not in seen]
        if not options:
            break
        node = min(options, key=lambda p: (_off_line(start, dest, p), p))
        seen.add(node)
        path.append(node)
    path.reverse()
    return [*path[1:], dest] if path and path[0] == start else [*path, dest]


def _off_line(a: Square, b: Square, p: Square) -> int:
    """Twice the triangle's area -- how far `p` sits off the line `a`-`b`.

    An integer, and monotonic in the perpendicular distance, which is all a
    tie-break needs. No square roots and no floats to compare.
    """
    return abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1]))


def costs(
    world: World, eid: int, budget: int, *, mode: str | None = None,
    kind: str = "walk",
) -> dict[Square, int]:
    """What reaching each square actually costs, in squares of movement.

    Same search as `reachable`, reported the other way round. A caller that
    wants to know *why* a square is expensive -- difficult terrain, a detour
    round a wall -- compares this against the straight-line distance.
    """
    pos = world.get(eid, Position)
    if pos is None:
        return {}
    rough = world.difficult(eid, kind)
    out: dict[Square, int] = {}
    for sq, path in reachable(world, eid, budget, mode=mode, kind=kind).items():
        out[sq] = sum(2 if step in rough else 1 for step in path)
    return out
