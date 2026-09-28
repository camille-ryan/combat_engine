"""Dressing a board with something to fight over.

Every real board in the repository is bare. `Grid` has carried
`blocking`, `difficult` and `elevation` for a long time, `api/render`
already ships the first two to the client, and the only board that ever
sets any of them is the audit harness. So cover, concealment, hiding and
difficult terrain were all modelled and none of them ever came up in a
fight.

Laid from the encounter's own seed, so a board is reproducible from the
same two numbers everything else is: the fight is still decided by one
generator and `--seed 7` is still `--seed 7`.

Deliberately sparse. The point is that cover exists somewhere, not that
the room is a maze -- a board too full of it stops the two sides ever
meeting, which is its own kind of wrong fight.

Traps are laid here too, for the same reason and under the same rule.
`Trap` was a component nothing ever constructed, so the rows that give a
bonus to defences against one, and the row that arms the traps in an
area, were asking about a thing no board had.
"""

from __future__ import annotations

from random import Random

from combat_engine.engine import REF, DamageType, World
from combat_engine.engine.components import Health, Ident, Position, Trap
from combat_engine.engine.events import EnterSquare, RoundStart
from combat_engine.engine.grid import Square
from combat_engine.engine.resolve import attack

#: What rough going is made of. `Grid.difficult` carries a label and
#: `c.ignores_difficult(kind)` reads it, so a board where every rough
#: square says the same word leaves a row that is at home in mud with
#: nothing to be at home in. Weighted, so the labelled kinds are the
#: exception a row can be exempt from rather than the whole floor.
_ROUGH = ("rubble", "rubble", "mud", "shallow water")


def dress(world: World, seed: int, *, density: float = 0.06, level: int = 1) -> None:
    """Put pillars, rough ground and the odd trap on an empty floor.

    `density` is the share of squares that become something, split
    roughly two to one between rough going and hard cover. `level` is
    what a trap on this board is worth; boards are built before anybody
    is spawned, so nothing here can work it out for itself.
    """
    pick = Random(seed ^ 0x7E44A1)
    width, height = world.grid.width, world.grid.height
    # The two starting bands are left clear. A pillar dropped on top of a
    # creature at setup leaves it Position-present and index-absent --
    # `grid.place` refuses to overwrite, and says so now, but the honest
    # fix is not to put one there.
    spare = {sq for sq in _band(0, 4, height) } | {sq for sq in _band(width - 4, width, height)}
    for _ in range(int(width * height * density)):
        sq = (pick.randrange(width), pick.randrange(height))
        if sq in spare or world.grid.occupant(sq) is not None:
            continue
        if pick.random() < 0.34:
            world.grid.blocking.add(sq)
        else:
            world.grid.difficult[sq] = pick.choice(_ROUGH)

    # Not every board, and never more than two. A trap is one square the
    # fight has to route around and one attack nobody rolled for, which is
    # the same argument the scatter above makes about cover: a floor with
    # several of them stops the two sides meeting rather than making the
    # crossing cost something.
    chosen = [_open(world, pick, spare) for _ in range(pick.choice((0, 1, 1, 2)))]

    # Laid when the fight starts rather than here. A board is dressed
    # before anybody is standing on it -- which is why the occupancy check
    # above can never fire -- so this is the first moment the floor can be
    # asked whether a square is free. It also keeps a trap's entity id
    # behind every creature's, and an id that shuffles the whole roster is
    # a diff nobody can read.
    def lay(_: RoundStart) -> None:
        for sq in chosen:
            if sq is not None and world.grid.occupant(sq) is None:
                arm(world, sq, level=level)

    world.bus.on(RoundStart, lay, once=True)


def arm(world: World, square: Square, *, level: int = 1, ref: str = "trap") -> int:
    """Put a trap in `square` and have it attack whoever steps on it.

    Deliberately **not** in the occupancy index: a trap that owned its
    square could never be walked into, and being walked into is the whole
    of how it goes off. `EnterSquare` rather than a `Zone` for the same
    kind of reason -- a zone belongs to a caster and lives on an effect's
    duration, and nobody cast this.

    The numbers come off the monster curve because there is no row to read
    them from: the ETL keeps traps as names only, so a trap has a level and
    nothing else. One attack, then `sprung` stays set: a plate that goes
    off and does not reset is what the flag was written for, and a trap
    that fires every time something crosses it grinds a creature down for
    walking.
    """
    eid = world.spawn(
        Ident(ref=f"t:{ref}"),
        Position(square=square),
        Trap(ref=ref),
    )
    trap = world.need(eid, Trap)

    def stepped(ev: EnterSquare) -> None:
        if trap.sprung or ev.square != square:
            return
        # Health is what tells a creature from the scenery and the zones,
        # which also walk through squares.
        if world.get(ev.actor, Health) is None:
            return
        trap.sprung = True
        # Through `resolve.attack` with the trap itself as the attacker, so
        # `is_trap(ctx["attacker"])` is true for the rows that ask and an
        # attack bonus hung on the trap by a power is read like anyone
        # else's.
        if attack(world, eid, ev.actor, level + 5, REF, power=f"t:{ref}"):
            hurt = world.rng.roll(f"1d10+{level}").total
            world.damage(eid, ev.actor, hurt, DamageType.UNTYPED, detail=f"t:{ref}")

    world.bus.on(EnterSquare, stepped, owner=eid)
    return eid


def _open(world: World, pick: Random, spare: set[Square]) -> Square | None:
    """A free square to put something in, or None if the floor is busy."""
    width, height = world.grid.width, world.grid.height
    for _ in range(32):
        sq = (pick.randrange(width), pick.randrange(height))
        if sq in spare or sq in world.grid.blocking:
            continue
        if sq in world.grid.difficult or world.grid.occupant(sq) is not None:
            continue
        return sq
    return None


def _band(lo: int, hi: int, height: int) -> set[Square]:
    return {(x, y) for x in range(lo, hi) for y in range(height)}
