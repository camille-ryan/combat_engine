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

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

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
from .query import (
    adjacent,
    alive,
    can_move,
    creatures,
    enemies,
    provoked_by_allies,
    squares,
)
from .types import Forced, Relation, Size

if TYPE_CHECKING:
    from collections.abc import Callable

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
    # **Asked here as well as in the search, and the second place is the one
    # that matters.** A route built any other way -- a scripted path, a
    # policy's own choice -- would otherwise walk through the square
    # `reachable` refused to offer. `World.barred` is empty on every board
    # that lays no such zone, so this costs a set construction per step
    # there and nothing else.
    if target & world.barred(eid, kind):
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
            # **`watchers` is already side-agnostic and this line is the
            # side test**, which is why "your allies provoke opportunity
            # attacks from you" is one condition here rather than a second
            # loop. `provoked_by_allies` fast-paths on an empty dict, so
            # the per-watcher-per-step cost this loop's note is about is
            # one `dict.get` when nobody holds the trait.
            if other not in foes and not provoked_by_allies(world, other, eid):
                continue
            reach = _threat(world, other, eid)
            # **Not `from_`**, which this function already binds to
            # `pos.square` for the `Moved` event it emits further down.
            # Shadowing it put a `frozenset` on every `Moved` in the tree
            # and diverged all 8 replay fixtures at once.
            threat_from = threatening_squares(world, other)
            left = (
                not (after_reach & threat_from) if reach == 1
                else not (spread(threat_from, reach) & target)
            )
            # **A flier provokes only from the square it started in.**
            # Camille's rule, and the mental model is that fliers "hop":
            # passing over a threatened square is not leaving one.
            # Only a watcher that had this flier in reach when it took
            # off, which is what the rule comes to once you notice this
            # engine provokes on *escaping reach* rather than per square
            # left -- see `_hop_provokes`, which is where that reasoning
            # and the measurement behind it live.
            #
            # **Not `Movement.passing`**: that is the *cost* half, keyed on
            # the square being entered, and a step-shaped flag cannot
            # express this one at all.
            if left and (mode != "fly" or _hop_provokes(world, eid, threat_from, reach)):
                # No `by`: a move is not a row, and **the absence is the
                # signal**. `f1302` prints "opportunity attacks provoked by
                # this movement" and `f2565` prints "that you provoke when
                # using a ranged or an area power"; `opportunity` alone
                # cannot tell those apart, which is what both of their
                # docstrings gave as the reason their clause was dropped.
                # `kind_` and `mode` are already here from #301. #880.
                window = OpportunityWindow(
                    actor=other, provoker=eid, why="moved away",
                    kind_=kind, mode=mode,
                )
                # **Saved and restored, not set and cleared.** Windows nest:
                # resolving one opportunity attack can move somebody and
                # open another, and a `finally` that writes None would hand
                # the outer window's remaining listeners no provocation at
                # all. Found by a plant that failed to go red because of it.
                prior = world.provocation
                world.provocation = window
                try:
                    world.bus.emit(window)
                finally:
                    world.provocation = prior

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
    # How the creature got here -- see `Moved`, which declares it with
    # `repr=False` so it reaches neither the wire nor a replay fixture.
    # Set on every emission, so `ev.kind_` is never missing.
    moved.kind_ = kind
    # And how many squares beyond its printed distance were spent getting
    # here. **Both are declared fields now**: `Moved`'s note used to say a
    # field "would reach the wire and every replay fixture", which `#1103`
    # made false -- `repr=False` keeps a field out of both. `0` unless a
    # caller lengthened the move *and* the decider spent what it was
    # given. #572, #1278.
    moved.stretched_ = stretched
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
            carried.stretched_ = 0
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


def over_a_wall(world: World, eid: int, square: Square) -> int:
    """How tall a stated wall this creature may cross here, or 0.

    **Camille's ruling on `#1365`, and it names exactly two cases**:

    > *"I think we can say flyers can pass over walls regardless of height,
    > but climbers can be assumed to start at the bottom and the height
    > does matter for climbing."*

    So a flier crosses any wall that states a height, and a creature with a
    **climb speed** crosses it too and pays the height -- `World.crossing`
    is where that price is charged. Everybody else is blocked exactly as
    before.

    **A climb SPEED, not an Athletics climb**, and that is a narrowing
    rather than an oversight. The page lets any creature climb, so reading
    "can it climb" would make every stated wall passable by everyone and
    turn a barrier into a toll -- a far bigger change than the ruling asks
    for, and one that would move every tactical board in the tree. The
    creatures the ruling is about are the ones that climb as a matter of
    course.

    **Keyed on a stated height, so rock is still rock.** A zone with no
    `height` answers 0 and the square stays impassable, which is why
    `drivers.sealed_space` is unaffected: nothing seals a room with a
    printed "4 squares high".

    Returns the height rather than a bool so the caller can price it; 0
    means "not crossable by this creature", which is also the answer for a
    square with no wall in it at all.
    """
    from .components import Movement

    tall = world.zones.height_at(square)
    if tall <= 0:
        return 0
    mv = world.get(eid, Movement)
    if mv is None:
        return 0
    if mv.modes.get("fly"):
        return tall
    if mv.modes.get("climb"):
        return tall
    # **"Can move over obstacles N squares high"** -- `c.steps_over`, which
    # is a third case and not one of the ruling's two: it is about a
    # creature's reach rather than how it travels, so it crosses a LOW wall
    # and is stopped by a tall one, where a flier crosses either.
    from .components import Mods

    mods = world.get(eid, Mods)
    if mods is not None and mods.items:
        over = mods.total("step_over", {})
        if over > 0 and tall <= over:
            return tall
    return 0


def _clear(
    world: World,
    eid: int,
    target: set[Square] | frozenset[Square],
    *,
    overhead: bool = False,
    move: dict[str, Any] | None = None,
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
                and not _may_squeeze(world, eid, sq)
                # A wall that states a height is crossable by a flier and by
                # a climber -- `#1365`. Asked last of the three waivers
                # because it is the newest and the narrowest: it needs a
                # zone with `height` set, which nothing but a printed "N
                # squares high" supplies.
                and not over_a_wall(world, eid, sq)):
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
                and not may_enter(world, eid, who, move=move)):
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
    lent = lent_squares(world)
    out: set[int] = set()
    for other in creatures(world):
        if other == eid:
            continue
        # **No early exit on `Mods`.** This skipped every creature carrying no
        # modifiers, which was sound while a modifier was the only thing that
        # could stretch a reach and is wrong now that a weapon and a row can:
        # a creature with a glaive and no modifiers reaches two and was skipped.
        reach = _threat(world, other, eid)
        # **A lent square counts at reach 1 too**, which the `reach > 1`
        # fast path alone would skip -- and that is exactly the case
        # `p16099` prints: a caster five squares back threatens through its
        # guardians with an ordinary one-square reach. `before` covers a
        # creature standing next to the mover itself, so only the lent
        # squares need this extra arm.
        extra = lent.get(other, frozenset())
        if (
            (extra and spread(extra, reach) & mine)
            or (reach > 1 and spread(squares(world, other), reach) & mine)
        ):
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


def may_enter(world: World, mover: int, occupant: int, *,
              move: dict[str, Any] | None = None) -> bool:
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
    # **The move's own facts, when the caller knows them.** The context
    # named only the two participants, and three cards narrow on the
    # movement instead: "during this shift", "to shift 3 or more squares",
    # "when a <class> power allows you to shift". A gate handed only
    # `mover` and `occupant` cannot ask any of that, so `f3116` and
    # `f3320` were refused in play with the verb already in the tree.
    #
    # `kind` and `squares` come free -- `reachable` already takes the
    # first and the second is its own budget -- and `by` is threaded from
    # the row that asked for the move. Absent for a move nobody attributed,
    # so a gate narrowing on it answers False, which is the conservative
    # direction: no permission rather than a standing one.
    ctx = {"mover": mover, "occupant": occupant, **(move or {})}
    return mods.total("may_enter", ctx) > 0


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


#: The printed Athletics DC for swimming, by how rough the water is.
#: PHB p183's three-row table, read off the page rather than derived.
#:
#: **Not the level-and-band table**, and that is worth saying because `#949`
#: assumed it was and the assumption travelled: the swim DC does not scale
#: with level at all. `combat_engine/dc.py` is a different table serving a
#: different question.
SWIM_DC = {"calm": 10, "rough": 15, "stormy": 20}

#: What the water is like when nothing says. Calm is the kindest of the
#: three, which is the right default for a fight nobody described as rough:
#: it makes an unannounced aquatic fight no harder than the page's easiest
#: case rather than inventing difficulty.
DEFAULT_WATER = "calm"


def swim_dc(world: World) -> int:
    """How hard the water is to swim in. `Scene.terrain` supplies the word.

    **`Scene.ground` is not a field** and this docstring named it for as
    long as it existed, which sent a reader looking for the writer in the
    wrong place. `story.run.ground` is the *function* that writes
    `world.terrain`, and the name collision is presumably where it came
    from. #1060.

    The three words it keys on are in `cast.TERRAIN_WORDS`, so a scene can
    state one. They were not, until #1060 — the intersection was empty, and
    since `story.module` refuses any word outside that set, this loop could
    never take its first branch and every swim check rolled the calm DC.
    """
    terrain = getattr(world, "terrain", frozenset())
    for word in ("stormy", "rough", "calm"):
        if word in terrain:
            return SWIM_DC[word]
    return SWIM_DC[DEFAULT_WATER]


def swims(world: World, eid: int) -> int | None:
    """How far this creature may swim this round, or None if it is not.

    DMG p44's movement bullet, second half -- *"a creature without a swim
    speed must use the athletics skill to swim, as described in the Player's
    Handbook"* -- and PHB p183's Swim entry, which is what that points at:

    > *"**Success:** You swim at one-half your speed… **Fail by 4 or Less:**
    > Stay where you are and lose the rest of your move action… **Fail by 5
    > or More:** Sink 1 square and risk suffocation by drowning…
    > **Swim Speed:** While swimming, creatures that have a swim speed use
    > that speed and do not make Athletics checks to swim."*

    `None` means *this is not a swim* -- dry land, or a creature with a swim
    speed, which the page exempts outright. A number is the budget, and 0 is
    a failed check rather than an absent one; `query.speed` keeps the two
    apart, because a creature that cannot move is not the same as one this
    rule has nothing to say about.

    **Once a round, cached on the creature, which is Camille's ruling:**

    > *"Athletics check determines swim speed for the round. It's not per
    > square."*

    The page says *"part of a move action"*, and a round is where that lands
    once there is one move action in it. The cache is what makes the ruling
    true rather than approximately true: `query.speed` is consulted many
    times while a menu is drawn, and rolling per call would give a creature a
    different speed in the menu from the one it moves at -- and would burn a
    d20 per call, moving every other roll in the fight.

    **Sinking is the one printed clause with nowhere to go**, and it is
    dropped deliberately rather than quietly: Camille ruled this a 2D plane,
    so "sink 1 square" has no axis to move along. What survives is the part
    that has meaning here -- the failed swimmer does not move. The drowning
    risk belongs to a rule about suffocation that does not exist yet.
    """
    from .components import Movement
    from .skills import check

    if "aquatic" not in getattr(world, "terrain", frozenset()):
        return None
    mv = world.get(eid, Movement)
    if mv is None:
        return None
    if mv.modes.get("swim"):
        return None                      # the page exempts it from the check
    if mv.swim_round == world.round:
        return mv.swim_squares
    dc = swim_dc(world)
    got = check(world, eid, "athletics", dc, purpose="swim")
    # Half speed on a success, and **the land speed halved** -- there is no
    # swim speed to halve, which is the whole premise of this branch.
    mv.swim_round = world.round
    mv.swim_squares = max(0, mv.speed // 2) if got.success else 0
    return mv.swim_squares


def climbs(world: World, eid: int) -> int | None:
    """How far this creature may climb this round, or None if it is not.

    PHB p183's Climb entry, which is the Swim entry's own page and the same
    shape:

    > *"**DC:** See the table... If you can brace yourself between two
    > surfaces, you get a +5 bonus to your check. **Success:** You climb at
    > one-half your speed. **Fail by 4 or Less:** You stay where you started
    > and lose the rest of your move action, but you don't fall.
    > **Fail by 5 or More:** You fall... **Climb Speed:** While climbing,
    > creatures that have a climb speed... do not make Athletics checks to
    > climb."*

    So `None` means *this is not a climb* -- a square that is not a climbable
    surface, or a creature with a climb speed, which the page exempts
    outright. A number is the budget, and **0 is a failed check** rather than
    an absent one, exactly as in `swims`: `query.speed` keeps the two apart
    because a creature that cannot move is not one this rule is silent about.

    **Cached per round**, which is Camille's ruling about the swim check --
    *"Athletics check determines swim speed for the round. It's not per
    square."* Quoted there about swimming; applied here because the page
    gives both skills the same *"part of a move action"* line, and the cache
    is what keeps a menu draw from rolling a fresh d20 per call.

    **The difference from swimming is the failure**, and it is the one clause
    that needed anything new: a bad swim sinks, which Camille ruled
    unexpressible on a 2D plane, and a bad climb **falls**, which is
    expressible today -- `falling.drop` exists, it has catch-hold, and
    `Position.height` is where the creature was. So the printed band is
    honoured rather than dropped.

    What is **not** here is the page's *"Uses Movement"* clause -- counting
    the climbed squares against the move and the extra square each costs.
    That is integration with `reachable` and the move budget, and `swims`
    draws its boundary in the same place. #1300.
    """
    from . import falling
    from .components import Movement, Position
    from .grid import CLIMB_BRACED
    from .skills import check

    where = world.get(eid, Position)
    mv = world.get(eid, Movement)
    if where is None or mv is None:
        return None
    dc = world.grid.climb_dc.get(where.square)
    if dc is None:
        return None                      # not a climbable surface
    if mv.modes.get("climb"):
        return None                      # the page exempts it from the check
    if mv.climb_round == world.round:
        return mv.climb_squares
    braced = CLIMB_BRACED if _braced_between(world, where.square) else 0
    got = check(world, eid, "athletics", dc, bonus=braced, purpose="climb")
    mv.climb_round = world.round
    # Half speed on a success, and the **land** speed halved: there is no
    # climb speed to halve, which is the premise of this branch.
    mv.climb_squares = max(0, mv.speed // 2) if got.success else 0
    # **Fail by five or more and the creature falls**, which is the whole of
    # the difference from `swims`. Asked off the margin rather than off
    # `success`, because the page gives failure two bands and only the wider
    # one falls -- a creature four short stays on the wall.
    if not got.success and dc - got.total >= 5:
        # No `by=`: that parameter is the **creature** that caused the fall,
        # and a failed grip was caused by nobody. `squares` is left out too,
        # so `drop` uses however far off the ground the creature is, which is
        # the page's "you fall from your current height".
        falling.drop(world, eid)
    return mv.climb_squares


def _braced_between(world: World, square: Square) -> bool:
    """Is this surface square between two climbable ones?

    *"If you can brace yourself between two surfaces, you get a +5 bonus"*,
    read as the printed thing it describes: a chimney, so climbable squares
    on **opposite** sides. Two neighbours on the same side are one surface
    with a bend in it and buy nothing.
    """
    x, y = square
    held = world.grid.climb_dc
    return (
        ((x - 1, y) in held and (x + 1, y) in held)
        or ((x, y - 1) in held and (x, y + 1) in held)
    )


def _hop_provokes(world: World, eid: int, stands: frozenset | set, reach: int) -> bool:
    """Does a flier owe this watcher its window.

    **Only if the watcher threatened the square the flight began in.**
    Camille's rule is that a flier *"ignores opportunity attacks except on
    the first square they leave"* -- the mental model being that fliers
    hop -- and that sentence does not translate into a per-step test,
    because this engine does not provoke per square left.

    What it provokes on is **escaping a watcher's reach**: `step`'s `left`
    is "nothing the watcher threatens touches where I am going", so a
    creature walking away from an adjacent enemy provokes on whichever
    step carries it out of range, which is usually not the first. Measured
    on a nine-square lane with watchers beside the 1st, 5th and 9th
    squares: both windows opened mid-route, neither on step one.

    So a per-step flag got this wrong in the most expensive direction --
    it suppressed **every** flier window, since a flier's escape is never
    on the step the flag allows. That is a far stronger rule than the one
    printed, and it reads as working.

    The faithful test is about the *start of the move* rather than the
    step: a watcher that had the flier in reach when it took off gets its
    attack, and anything the flier merely passed over gets nothing. That
    is the same shape as the cost half -- the start and the landing square
    are what count -- and it needs no new state, because `walk` already
    records where the move began for the Stealth clause.

    **One square, not a footprint.** `went_from` is a single square, so a
    large flier is judged by its origin square alone. Honest and narrow:
    the alternative is storing the whole take-off footprint for a case no
    row in the tree asks about.

    **`stands` is where the watcher *is*, not what it threatens**, which
    is the shape `threatening_squares` returns and cost a wrong reading
    here: testing the start square against it directly asks whether the
    flier took off from inside the watcher's own body, which is false for
    every ordinary board, so the rule waived everything. `left` above has
    the same asymmetry -- it spreads whichever side is cheaper -- so the
    reach is spread here too.
    """
    mv = world.get(eid, Movement)
    if mv is None or mv.went_from is None:
        # Nothing recorded where this began -- a bare `step` rather than a
        # `walk`. Fail toward the ordinary rule rather than a waiver.
        return True
    return mv.went_from in spread(stands, reach)


def mode_of(world: World, eid: int, mode: str | None) -> str:
    """Resolve the mode a creature is moving with, defaulting to its best.

    A creature that can fly flies, because that is what makes its printed
    speed line mean anything without every caller having to ask.

    **An aquatic fight reorders that preference**, which is DMG p.45's
    movement bullet -- *"creatures move using their swim speed"* -- and the
    fourth of the four this function's issue is about. A creature with both a
    fly and a swim speed flew underwater, because `fly` was simply tested
    first: 100 fieldable rows carry a swim speed and the ordering was the only
    thing between them and it. The number has been in `monster.modes` and in
    `Movement.modes` all along; #1024 was filed on the belief it was missing
    and closed when the column was found.

    **Only the ordering.** The same bullet's other half -- *"a creature
    without a swim speed must use the Athletics skill to swim"* -- is not
    here, so a creature with no swim speed still moves at its land speed in
    water. That is a skill check gating movement, which is a different seam
    from the grid, and it stays on #949 rather than being smuggled in behind
    a tuple. So this is a narrowing of the wrong answer, not the printed rule
    in full.
    """
    from .components import Movement

    if mode is not None:
        return mode
    mv = world.get(eid, Movement)
    if mv is None:
        return "walk"
    order = ("fly", "swim", "burrow")
    if "aquatic" in getattr(world, "terrain", frozenset()):
        order = ("swim", "fly", "burrow")
    for candidate in order:
        if mv.modes.get(candidate):
            return candidate
    return "walk"


def walk(
    world: World, eid: int, path: list[Square], *, kind: str = "walk",
    mode: str | None = None,
    prefer: Callable[[list[Square]], list[Square]] | None = None,
) -> int:
    """Walk a path one square at a time. Returns how many squares were covered.

    Difficult terrain costs an extra square, so the budget is spent here
    rather than checked by the caller.

    **A move already under way can be lengthened**, which it could not be
    before: `Movement.lengthened` is squares handed to the move *in
    flight*, and when the path runs out this picks a further destination
    and keeps going. `f820` prints *"for that move"* on a trigger that
    fires **during** it -- being caught on the way out -- and `m2341a4`
    prints the extra square owed for a missed opportunity attack. Both
    had carried a marker saying a move under way cannot be lengthened.

    **Done here and not by calling `walk` twice**, which was the first
    design and is wrong in four places at once: a second call emits a
    second `MoveStart` and a second `MoveEnd`, so a row reading *"when
    you end your move"* fires twice; `mv.went` is zeroed at the start, so
    the Stealth distance would restart mid-move; and
    `free_difficult_left` would hand out the per-move allowance of free
    rough going again. One move action is one `walk`.

    **And it does not terminate.** Proven by planting it: pointing the
    continuation at `walk` gives a `RecursionError`, because each nested
    call announces its own `MoveStart` and a row whose clause fires there
    grants again. The bound below cannot help -- each recursion gets a
    fresh one.

    `prefer` is the caller's ordering over destinations, so a
    continuation obeys the same `toward`/`away_from` the first leg did --
    `c.move`'s own reason, and the thing 13 rows were measured getting
    wrong when the order was left to `sorted`. #1514.
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
    # **The in-flight grant is cleared BEFORE `MoveStart` is announced**,
    # not beside the other per-move counters below, and the difference is
    # load-bearing: a handler on `MoveStart` is inside the printed window
    # ("during that movement"), so clearing after the emit would wipe the
    # one grant a row of that shape had just made. A grant left over from
    # an earlier move -- a hit taken while standing still, say -- dies
    # here, which is the leak this has to stop. #1514.
    stale = world.get(eid, Movement)
    if stale is not None:
        stale.lengthened_in_flight = 0
    # The return is read. "You can cancel that movement as an immediate
    # interrupt" is a printed line on several rows, and the event was
    # emitted and thrown away -- the fourth time this session that a
    # cancellable event had no reader.
    # `path[-1]` and not the first step: this fires once for the whole
    # move action, so the destination is where the creature is going to
    # end up. An empty path has no destination rather than a false one.
    if world.bus.emit(MoveStart(
        actor=eid, kind_=kind, to=path[-1] if path else None,
    )).cancelled:
        return 0
    # `spent` is computed at the bottom now: the per-step total lives in
    # `spent_box` so a leg helper can add to it across legs.
    # Held past the end of the move, not just during it. "Requirement: the
    # creature must be climbing" is checked when a power is *used*, and the
    # creature is standing still at that moment -- a flag that only held
    # mid-step would be false exactly when the question gets asked. A
    # creature that climbed a wall is still on the wall; `settle` puts a
    # flyer down at the end of its turn and clears it there.
    mv = world.get(eid, Movement)
    if mv is not None:
        mv.using = "" if mode == "walk" else mode
        # **How far this move action goes, for the Stealth rule.** Zeroed
        # here rather than per turn because the card says "during that
        # action", so a second move action starts counting again. #784.
        mv.went = 0
        mv.went_kind = kind
        # **And where it started**, for the clause that asks how far the
        # creature ended up rather than how far it walked. Taken here
        # rather than from the first step, because a move that is cancelled
        # or blocked still started somewhere and the two must agree.
        start = world.get(eid, Position)
        mv.went_from = start.square if start is not None else None
        # **The per-move allowance of free rough going, reset here.**
        # *"You ignore 1 square of difficult terrain when you move"* is a
        # budget on a **path**, so this is the one place it can start
        # again -- `World.crossing` prices a step at a time and is shared
        # with `reachable`, whose Dijkstra would have spent the budget on
        # routes nobody takes.
        mv.free_difficult_left = mv.free_difficult
    # **Hoisted, and it was being rebuilt per square.** `world.difficult`
    # was called inside this loop, so a creature's waivers and every live
    # zone were re-resolved for every square it walked. `crossing` resolves
    # them once and prices the step, which is also what lets a tax on the way
    # *out* be charged here: the loop never knew which square it was leaving.
    price = world.crossing(eid, kind)
    frm = mv.went_from if mv is not None else None
    if frm is None:
        at = world.get(eid, Position)
        frm = at.square if at is not None else None
    # **A flier hops**, which is Camille's rule and three things at once:
    # it ignores rough going, hazards and opportunity attacks on the
    # squares it passes *over*, and pays all three on the square it stops
    # on. `Movement.passing` carries it -- see that field -- and is set
    # around each step rather than for the whole move, so the last square
    # is priced and suffered normally.
    #
    # The square it starts from needs nothing: cost and hazards are paid on
    # **entering** a square and the creature is already in that one.
    #
    # Set before `step`, because `step` is what opens the opportunity
    # window and what moves the creature into the zone that burns it.
    spent_box = [0]

    def cover(leg: list[Square]) -> bool:
        """Walk one leg. False if a step was refused, which ends the move.

        Everything in here was the body of a single `for`; it is a
        function so a lengthened move can run it again without a second
        `MoveStart`. `frm` and `spent` are the only state that crosses a
        leg boundary, which is why they are `nonlocal` and boxed.
        """
        nonlocal frm
        hops = mode == "fly" and len(leg) > 1
        last = len(leg) - 1
        # **The printed exception**, hoisted for the same reason `price`
        # is: five rows lay a zone that is rough going *even for
        # creatures that fly*, and without this the general rule would
        # silently invert them. Empty on any board laying no such zone.
        # See `Zone.difficult_in_flight`.
        sticky = world.zones.catches_fliers() if hops else frozenset()
        for n, sq in enumerate(leg):
            # The square this creature will not stop on, which is what
            # the cost and hazard waivers key on -- both are paid on
            # *entering* a square, so the one it lands on is `n == last`
            # and pays in full.
            #
            # The provocation half is **not** here: it is provoked by
            # leaving, and by escaping a watcher's reach rather than per
            # square, so no per-step flag can carry it. `step` tests
            # `went_from` instead.
            over = hops and n != last
            if mv is not None:
                mv.passing = over
            if not step(world, eid, sq, kind=kind, mode=mode):
                if mv is not None:
                    mv.passing = False
                return False
            # **The cost waiver is the one the exception narrows, and the
            # hazard waiver above is not.** The printed sentence is about
            # difficult *terrain*, so a zone that both slows and burns
            # still waives its damage for a flier passing over and
            # charges for the ground.
            step_cost = 1 if (over and sq not in sticky) else price(frm, sq)
            # **The per-move allowance, spent here and only here.** A
            # square that cost extra for being rough costs one less while
            # the budget lasts -- *"you ignore 1 square of difficult
            # terrain when you move"*. Charged against the surcharge
            # rather than the whole step, so a zone that taxes a crossing
            # for a different reason still charges it.
            #
            # `price(frm, sq) - 1` is the comparison rather than
            # `sq in world.rough()`, because `crossing` is the one owner
            # of what a step costs and a second opinion here is the
            # disagreement that function exists to prevent.
            if (mv is not None and mv.free_difficult_left > 0
                    and step_cost > 1 and not over):
                step_cost -= 1
                mv.free_difficult_left -= 1
            spent_box[0] += step_cost
            frm = sq
            # Squares entered, not budget spent -- `spent` charges 2 for
            # rough ground and the printed penalty counts squares.
            if mv is not None:
                mv.went += 1
        return True

    going = cover(path)
    # **The move in flight grows here**, once each leg finishes, so a row
    # that reacted to something *during* the move is read after it has
    # had the chance to react. Bounded rather than `while True`: a handler
    # that grants a square on every `MoveStart` of its own making would
    # otherwise walk the creature off the board, and no printed card
    # lengthens one move more than a handful of times. Reaching the bound
    # drops the remaining grant, which is the safe direction.
    for _again in range(8):
        if not going or mv is None or mv.lengthened_in_flight <= 0:
            break
        further, mv.lengthened_in_flight = mv.lengthened_in_flight, 0
        onward = world.reachable_paths(eid, further)
        if not onward:
            break
        choices = sorted(onward)
        if prefer is not None:
            choices = prefer(choices)
        where = world.decide(
            eid, "move", choices, f"lengthened by {further}",
        )
        leg = onward.get(where) if isinstance(onward, dict) else None
        if not leg:
            break
        going = cover(leg)
    spent = spent_box[0]
    # **Cleared before `MoveEnd`**, not after: `Zones.refresh` is
    # subscribed to that event, so a `ZoneEntered` can still be announced
    # from inside the emit below -- and the creature has landed by then.
    # Both the normal exit and the blocked one above already leave this
    # false; this is the belt, and it is cheap.
    #
    # A flag that outlived its move would make a flier standing in a
    # hazard immune to it, which is the half of Camille's rule that keeps
    # the other half honest.
    if mv is not None:
        mv.passing = False
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
    where = {o: threatening_squares(world, o) for o in foes}
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
            world.bus.emit(MoveStart(actor=eid, kind_="land", to=ring[0]))
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
    # The route is computed below, so the destination is spelled the
    # same way here: an explicit `path` ends where it ends, and a bare
    # `to` is its own destination.
    if world.bus.emit(MoveStart(
        actor=eid, kind_="shift", to=path[-1] if path else to,
    )).cancelled:
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
    if world.bus.emit(
        MoveStart(actor=eid, kind_="teleport", to=to)
    ).cancelled:
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
    avoid: Callable[[World, Square], bool] | None = None,
) -> int:
    """Push, pull or slide `target` up to `amount` squares.

    `anchor` is what the movement is measured against. It defaults to the
    source's square, which is right for most powers and wrong for the ones
    that say "away from the zone" or "toward the ally" -- those pass their
    own, which is why this is a parameter rather than a lookup.

    Forced movement never provokes, and stops dead the first square it cannot
    enter rather than trying to route around it.

    `avoid` is a destination the printed line forbids -- see
    `_forced_square`. It is **not** consulted when `to` names the square
    outright: a row that says where the creature ends up is not asking
    which squares are allowed, and no card prints both.
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

        # **`target` and `source`, not only `how` and `power`.** Neither
        # side could ask *who*, so "when you push an undead creature, one
        # extra square" lengthened every shove the character made --
        # `i3169x1`, written, firing, and stronger than print. `target` is
        # the conventional key every content gate reads; `source` is here
        # for symmetry, since the `"forced"` side has the same blindness
        # about who is doing the shoving and no row needs that today. #748.
        ctx = {
            "how": how.value,
            "power": power,
            "target": ev.target,
            "source": ev.source,
        }
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
            if (moved >= amount
                    or _over_an_edge(world, target, sq, power)
                    or _into_hindering(world, target, sq, power)):
                break
            if not step(world, target, sq, kind=how.value):
                break
            moved += 1
        return moved
    moved = 0
    # **The budget can grow, once.** `i3318p1` prints *"when forced
    # movement moves a creature into the zone, that forced movement
    # increases by 1 square"*, which is a property of where the shove
    # ENDS and so of the zone -- not of either creature. See
    # `Zone.extends_forced`; the row's marker asked for a parameter on
    # the shover's side, which cannot work because a zone does not know
    # who will do the shoving.
    #
    # Measured against the regions the creature is **already** in, so a
    # creature standing in such a zone and shoved further along it gains
    # nothing: it is not being moved *into* anything. Same reading of
    # "enters" as `i3320p1`.
    budget = amount
    already = _extending_zones(world, world.need(target, Position).square)
    stretched = False
    while moved < budget:
        nxt = _forced_square(world, source, target, anchor, how, avoid)
        if (nxt is None
                or _over_an_edge(world, target, nxt, power)
                or _into_hindering(world, target, nxt, power)):
            break
        if not step(world, target, nxt, kind=how.value):
            break
        moved += 1
        if not stretched:
            gained = {z: n for z, n in _extending_zones(world, nxt).items()
                      if z not in already}
            if gained:
                # The largest, not the sum: two overlapping zones each
                # printing "1 extra square" is one entry into hindering
                # ground, and `Zone.extra_cost` takes the larger of two
                # prices for the same reason.
                budget += max(gained.values())
                stretched = True
    return moved


def _extending_zones(world: World, square: Square) -> dict[int, int]:
    """Which zones over that square lengthen a shove that ends in them.

    `{zone id: extra squares}`, empty for every ordinary square -- which
    is the common case by far, since this is asked once per step of every
    push, pull and slide in the game.
    """
    return {eid: zone.extends_forced
            for eid, zone in world.zones.all()
            if zone.extends_forced and square in (zone.squares or ())}


def _into_hindering(
    world: World, target: int, into: Square, power: str
) -> bool:
    """Did the shoved creature save against being put in hindering terrain?

    > *"**hindering terrain:** Forced movement can force targets into
    > hindering terrain. Targets forced into hindering terrain receive a
    > saving throw immediately before entering the unsafe square they are
    > forced into. Success leaves the target prone at the edge of the
    > square before entering the unsafe square."*
    >
    > -- Dungeon Master's Guide, page 43

    Read off the page rather than from an issue's quote, and the second
    sentence is why that mattered: the printed success does not merely
    stop the creature, it leaves it **prone**. A reading from memory
    would have stopped it and left it standing, which is stronger than
    print for the creature in exactly the way a house rule should not be.

    True stops the forced movement where it stands, which is
    `_over_an_edge`'s contract one function down and the same printed
    timing -- *"immediately before entering"*, so the throw is taken
    before the step and a save taken after would have to put the creature
    back.

    `when_="edge"` for `catches_itself`'s reason: the throw is taken
    **now** and not at the end of the turn, so a row paying out on
    "saving throws made at the start of your turn" must not reach it.

    False on a failure, and the creature enters -- whatever the terrain
    does to it then is the zone's own business. #1545.
    """
    from .durations import When
    from .events import SavingThrow
    from .falling import SAVE_BEATS
    from .query import hindering_at
    from .resolve import _mods
    from .types import Condition

    if not hindering_at(world, into):
        # The common case by far: this sits in the inner loop of every
        # push, pull and slide in the game, so the cheap test comes first
        # and nothing is rolled on clear ground.
        return False
    natural = world.rng.roll("1d20").total
    plus = _mods(
        world, target, "save",
        # The same keys `catches_itself` passes, and for the reason its
        # note gives: a gate subscripting an absent key raises inside the
        # kernel. A terrain save is against no effect.
        {"actor": target, "label": "hindering", "conditions": frozenset(),
         "ongoing": False, "dtype": None, "dtypes": (),
         "keywords": frozenset(), "effect": None,
         "when_": "edge", "granted_via": power, "granted_by": -1},
    )
    saved = world.bus.emit(
        SavingThrow(
            actor=target, against="hindering terrain", natural=natural,
            bonus=plus, saved=natural + plus >= SAVE_BEATS, when_="edge",
            granted_via=power, keywords=(),
        )
    ).saved
    if saved and not _keeps_its_feet(world, target):
        # **Prone, which is the printed success.** The creature is left at
        # the edge -- it has not stepped, so it is already in the last
        # square before the unsafe one and only the condition is owed.
        world.effects.apply(
            target, target, When.ENCOUNTER, label="prone",
            conditions=[Condition.PRONE], by=power,
        )
    return saved


#: The `Mods` key `c.keeps_its_feet` writes and `_keeps_its_feet` reads.
#: **Defined here and imported by `Cast`**, not spelled in both: the
#: reader owns the name, and a modifier key hand-kept in two files is the
#: shape `#492` is about. `cast.py` already imports from this module at
#: module level, so the direction is the one that works -- `movement`
#: cannot import `Cast`.
EDGE_PRONE_WAIVED = "edge_prone_waived"


def _keeps_its_feet(world: World, target: int) -> bool:
    """Has this creature bought back the printed prone? `c.keeps_its_feet`.

    One card does: `i2494x1`, *"on a save, you don't fall prone"*. Its
    own docstring predicted this reader -- *"the day the prone lands this
    row goes red and gets its opt-out"* -- and `#1545` is the day, since
    nothing laid a prone here before it.

    Asked only on a success, so it costs nothing on a failed save and
    nothing at all on clear ground: the `hindering_at` test above has
    already returned for every ordinary square, which matters because
    this sits in the inner loop of every push, pull and slide.

    The save itself is **not** waived -- the card buys back the
    consequence, not the throw, and the forced movement still stops.
    """
    from .components import Mods
    from .resolve import _mods

    if world.get(target, Mods) is None:
        return False
    return bool(_mods(world, target, EDGE_PRONE_WAIVED, {"actor": target}))


def _over_an_edge(
    world: World, target: int, into: Square, power: str
) -> bool:
    """Did the shoved creature catch itself at the edge? PHB p284.

    **Checked before the step, in both loops, and that is the printed
    timing**: *"you make it as soon as you reach the edge"*. A save taken
    after the step would have to put the creature back, and the fall would
    already have been announced.

    True stops the forced movement where it stands. Returning the *save*
    rather than its opposite would read better here and would be wrong at
    the call sites, which is why the name is about the edge and not about
    the throw.

    Only a drop qualifies, and `catches_itself` decides that -- so a shove
    across flat ground rolls nothing, which matters because this sits in the
    inner loop of every push, pull and slide in the game. #949.
    """
    from .falling import catches_itself

    return catches_itself(world, target, into, power=power)


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
    world: World, source: int, target: int, anchor: Square, how: Forced,
    avoid: Callable[[World, Square], bool] | None = None,
) -> Square | None:
    """Where this step of a forced move goes, asking whoever is pushing.

    The choice belongs to the creature applying the movement, so it goes
    through `world.decide` like any other. The first version picked the
    straightest square and never asked, which quietly turned every push in
    the game into a single fixed line.

    **`avoid` is a square the card forbids, and it is filtered here rather
    than left to the decider.** *"But not into hindering terrain"* is a
    rule and not advice: enforcing it in the policy would let any other
    decider -- a player, a headless run -- break the printed line. With
    every option forbidden the step stops, which is what forced movement
    does against any square it cannot enter.
    """
    options = forced_squares(world, target, anchor, how)
    if avoid is not None:
        options = [sq for sq in options if not avoid(world, sq)]
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    return world.decide(source, how.value, options, f"{how.value} to which square")


# -- reachability -----------------------------------------------------------


def reachable(
    world: World, eid: int, budget: int, *, mode: str | None = None,
    kind: str = "walk", share: bool = False, by: str = "",
    granted_by: int = -1,
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
    # it cannot reach at one while walking, and `World.crossing` is where that
    # difference is read -- hoisted out of the loop, since it resolves the
    # waivers and the taxing zones once for the whole search and leaves a
    # membership test per step.
    price = world.crossing(eid, kind, granted_by=granted_by)
    # Ground that refuses this kind of move outright, which is a different
    # question from what it costs -- see `World.barred`.
    shut = world.barred(eid, kind)
    start = pos.square
    threat = _threatened_from(world, eid)

    # **How many squares of rough going are free on this path.**
    # `Movement.free_difficult`, and it is read here rather than inside
    # `price` for the reason `c.ignores_difficult` records: the budget
    # belongs to a **path**, and a counter in the shared pricing closure
    # would be spent by every route this search merely considers.
    #
    # Zero for every creature nothing has given one, and the whole
    # layering below collapses to the ordinary search when it is -- so
    # this costs one component read on the hot path and nothing else.
    moves = world.get(eid, Movement)
    free = max(0, moves.free_difficult) if moves is not None else 0

    # (movement spent, squares walked under threat). Lexicographic, so a
    # safer route wins outright and only a tie on safety is settled by cost.
    #
    # **Keyed on (square, waivers spent) when there is a budget**, which
    # is a layered search over `free + 1` copies of the board: arriving
    # somewhere having spent a waiver is a different state from arriving
    # having kept it, and the cheaper of the two is not always the one
    # worth keeping. With `free == 0` there is one layer and the key is
    # the square, which is exactly what this was.
    best: dict[tuple[Square, int], tuple[int, int]] = {(start, 0): (0, 0)}
    came: dict[tuple[Square, int], list[tuple[Square, int]]] = {(start, 0): []}
    frontier = [(start, 0)]
    while frontier:
        frontier.sort(key=lambda s: best[s])
        node = frontier.pop(0)
        here, used = node
        spent, risked = best[node]
        # A linked square is one step away like any neighbour. `step` never
        # asked whether a destination was adjacent to where the mover stood,
        # so the search is the only place a rift has to be known about.
        for nxt in sorted(set(neighbours(here)) | world.grid.links.get(here, frozenset())):
            if nxt in shut:
                continue
            if not _clear(world, eid, footprint(nxt, pos.size),
                          overhead=overhead or share,
                          move={"kind": kind, "squares": budget, "by": by}):
                continue
            full = price(here, nxt)
            # Both ways of entering a rough square: pay for it, or spend
            # one of the waivers. The search keeps whichever turns out
            # better further on rather than deciding here, which is the
            # whole reason the state carries `used`.
            options = [(full, used)]
            if free and used < free and full > 1:
                options.append((full - 1, used + 1))
            for step_cost, now_used in options:
                score = (spent + step_cost,
                         risked + _provokes_step(threat, here, nxt, pos.size))
                if score[0] > budget:
                    continue
                ahead = (nxt, now_used)
                known = best.get(ahead)
                if known is not None and score > known:
                    continue
                if known is not None and score == known:
                    came[ahead].append(node)   # another equally good way in
                    continue
                best[ahead] = score
                came[ahead] = [node]
                frontier.append(ahead)

    # **One answer per square, taken from the layer that reached it most
    # cheaply.** A square may be in several layers -- reached with a
    # waiver spent and without -- and a caller wants the cost, not the
    # bookkeeping. Ties break on the fewest waivers spent, so a route
    # that costs the same keeps the budget for later.
    #
    # **The comparison is a guard the frontier ordering makes hard to
    # reach, and that is measured rather than assumed.** `frontier` is
    # re-sorted by cost on every pop, so a square's cheaper layer is
    # normally inserted first and `kept is None` alone would answer the
    # same -- replacing the test with that changed no assertion in
    # `drivers.one_square_of_rough_going_is_free`. It is kept because the
    # ordering does not make it *impossible*: a node popped later can
    # relax a neighbour below a sibling layer inserted earlier, and
    # `best` iterates in insertion order. Deleting a guard on the
    # strength of one board is how a search starts answering the second
    # best price.
    arrived: dict[Square, tuple[Square, int]] = {}
    for node_, score in best.items():
        sq_, used_ = node_
        kept = arrived.get(sq_)
        if kept is None or (score, used_) < (best[kept], kept[1]):
            arrived[sq_] = node_
    came_sq: dict[Square, list[Square]] = {
        sq_: [frm for frm, _ in came[node_]]
        for sq_, node_ in arrived.items()
    }
    paths = {sq: _straightest(start, sq, came_sq)
             for sq in came_sq if sq != start}
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
        # **Within the radius of ANY anchor.** `leash_of` answers a set
        # since `#1297`: one anchor is a set of one, so every
        # single-anchor row is unchanged, and `p13318`'s primary target is
        # tethered to *"one or more"* secondaries rather than to whichever
        # was hit first -- which would be a tighter cage than it prints.
        held, radius = tie
        paths = {
            sq: path
            for sq, path in paths.items()
            if any(grid_distance(sq, one) <= radius for one in held)
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


def lent_squares(world: World) -> dict[int, frozenset[Square]]:
    """Which extra squares each creature threatens from, by owner.

    One walk over the conjurations rather than one per watcher, because
    `step`'s own comment measures what the alternative costs: "asking each
    watcher separately turned a full audit from 84 seconds into 331 -- the
    cost is per watcher per step, and a fight takes thousands of steps".

    Empty in every fight with no conjuration lending a square, which is
    almost all of them, and then `threatening_squares` is a plain read.
    """
    from .components import Conjuration, Mods

    out: dict[int, frozenset[Square]] = {}
    for other, conj in world.each(Conjuration):
        lent = world.get(other, Mods)
        if lent is None or not lent.items:
            continue
        if lent.total("threatens_from") <= 0:
            continue
        out[conj.by] = out.get(conj.by, frozenset()) | squares(world, other)
    return out


def threatening_squares(world: World, eid: int) -> frozenset[Square]:
    """The squares this creature threatens **from** -- its own, plus any
    conjuration of its that lends its square for the purpose.

    *"You can make opportunity attacks through each guardian as if you
    occupied its square"* -- `p16099`, three guardians. `c.conjure` lays the
    marker with `threatens=True` and this is the one reader, so the three
    places that ask where a watcher threatens from cannot drift apart.

    **That drift is why this is a function and not three expressions.** The
    preview loop's own comment records the last time they disagreed: "the
    hardcoded 1 here made this preview disagree with `step`, which has
    always spread by the watcher's reach. A creature with a reach weapon
    provoked in play and not in the preview the policy scores against."

    Cheap in the ordinary case: one `World.each` over conjurations, which is
    empty in most fights, and the creature's own squares otherwise
    unchanged.
    """
    return squares(world, eid) | lent_squares(world).get(eid, frozenset())


def _threatened_from(world: World, eid: int) -> dict[int, frozenset[Square]]:
    """Which squares each living enemy threatens from, for the threat test."""
    return {
        foe: threatening_squares(world, foe)
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
    price = world.crossing(eid, kind)
    moves = world.get(eid, Movement)
    free = max(0, moves.free_difficult) if moves is not None else 0
    out: dict[Square, int] = {}
    for sq, path in reachable(world, eid, budget, mode=mode, kind=kind).items():
        # Paired with the square each step leaves, since a tax can be on the
        # way out -- `pos.square` is where the first step starts from.
        steps = [
            price(frm, to)
            for frm, to in zip([pos.square, *path], path, strict=False)
        ]
        # **The per-move allowance, spent greedily on the dearest steps.**
        # Each waiver saves exactly one square of movement whichever rough
        # step it is spent on, so spending them on the first ones found is
        # as good as any other order -- and `reachable` has already
        # decided this path is the cheapest, so the two agree.
        #
        # Without this, `costs` reported 2 for a square the search had
        # reached at 1, which is the kind of disagreement `World.crossing`
        # exists to make impossible.
        left = free
        total = 0
        for cost in steps:
            if left > 0 and cost > 1:
                cost -= 1
                left -= 1
            total += cost
        out[sq] = total
    return out
