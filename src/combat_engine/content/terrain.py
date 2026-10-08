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

from combat_engine.engine import AC, FORT, REF, WILL, DamageType, World
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

#: The word a trap block prints for what it attacks, to the enum. A block
#: that names something else -- or names nothing, which 226 of them do -- is
#: Reflex, which is what a trap attacks when the page does not say.
_DEFENCES = {"ac": AC, "fortitude": FORT, "reflex": REF, "will": WILL}


def printed_trap(level: int, pick: Random | None = None) -> dict | None:
    """A printed trap worth this board's level, or None if the table is unread.

    Bounded by level so a level-1 floor cannot arm a paragon-tier trap, and
    **drawn from every eligible row** rather than taking the first: a
    deterministic pick gave every board in the game the same trap, which is
    the shape of the bug this whole change is about -- one invented answer
    standing in for 631 real ones.

    `pick` is the board's own generator, so a board is still reproducible
    from its seed. Without one the lowest eligible row is taken, which is
    what a caller with no seed deserves and is at least in range.

    Rows whose Hit line named no dice are excluded: they would fall back to
    the invented curve for half their numbers.

    Returns a plain dict rather than a component, so `arm` stays the only
    thing that knows which columns it wants.
    """
    from combat_engine.db import game

    try:
        rows = list(game().execute(
            "SELECT ref, level, perception_dc, attack, defence, damage FROM trap "
            "WHERE attack IS NOT NULL AND level IS NOT NULL "
            "AND damage IS NOT NULL AND level <= ? ORDER BY level DESC, ref",
            (max(1, level),),
        ))
    except Exception:            # no database, or a build without the table
        return None
    if not rows:
        return None
    # Within a tier rather than across all of them: a level-10 board should
    # not arm a level-1 pit just because the draw landed there.
    top = rows[0]["level"]
    tier = [r for r in rows if r["level"] >= min(top, max(1, level - 2))]
    chosen = pick.choice(tier) if pick is not None else tier[0]
    return dict(chosen)


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
                arm(world, sq, level=level, pick=pick)

    world.bus.on(RoundStart, lay, once=True)


def arm(world: World, square: Square, *, level: int = 1, ref: str = "trap",
        pick: Random | None = None) -> int:
    """Put a trap in `square` and have it attack whoever steps on it.

    Deliberately **not** in the occupancy index: a trap that owned its
    square could never be walked into, and being walked into is the whole
    of how it goes off. `EnterSquare` rather than a `Zone` for the same
    kind of reason -- a zone belongs to a caster and lives on an effect's
    duration, and nobody cast this.

    **The numbers come off the printed row.** They used to come off the
    monster curve, and this docstring used to explain why -- "the ETL keeps
    traps as names only, so a trap has a level and nothing else". That was
    true and is not: the compendium's 631-row `Trap` table is imported now,
    and `printed_trap` picks one worth this board's level. The curve is kept
    only as the fallback for a tree with no database built.

    One attack, then `sprung` stays set: a plate that goes off and does not
    reset is what the flag was written for, and a trap that fires every time
    something crosses it grinds a creature down for walking.
    """
    printed = printed_trap(level, pick)
    eid = world.spawn(
        Ident(ref=printed["ref"] if printed else f"t:{ref}"),
        Position(square=square),
        Trap(
            ref=printed["ref"] if printed else ref,
            perception_dc=printed["perception_dc"] if printed else None,
        ),
    )
    trap = world.need(eid, Trap)
    # **Off the row where there is one.** These three numbers were invented
    # -- `level + 5` to hit, `1d10 + level` damage, Reflex always -- because
    # the `Trap` table was never imported and this had nothing to read. It
    # does now, and the attack bonus is stored as printed so `world.scaling`
    # takes the level back out of it exactly as it does for a monster.
    bonus = printed["attack"] if printed and printed["attack"] is not None else level + 5
    hurts = printed["damage"] if printed and printed["damage"] else f"1d10+{level}"
    against = _DEFENCES.get((printed or {}).get("defence") or "", REF)

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
        if attack(world, eid, ev.actor, bonus, against, power=trap.ref):
            hurt = world.rng.roll(hurts).total
            world.damage(eid, ev.actor, hurt, DamageType.UNTYPED, detail=trap.ref)

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
