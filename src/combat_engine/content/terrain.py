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
from combat_engine.engine.components import (
    Defenses,
    Health,
    Ident,
    Initiative,
    Position,
    Scenery,
    Trap,
)
from combat_engine.engine.durations import When
from combat_engine.engine.events import EnterSquare, RoundStart, TurnStart
from combat_engine.engine.grid import Square
from combat_engine.engine.movement import place
from combat_engine.engine.resolve import attack
from combat_engine.engine.traps import suppressed
from combat_engine.engine.types import Size

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
            "SELECT ref, level, perception_dc, attack, defence, damage, "
            "initiative, disable_skill, disable_dc FROM trap "
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


def dress(
    world: World, seed: int, *, density: float = 0.06, level: int = 1,
    traps: int | None = None,
) -> None:
    """Put pillars, rough ground and the odd trap on an empty floor.

    `density` is the share of squares that become something, split
    roughly two to one between rough going and hard cover. `level` is
    what a trap on this board is worth; boards are built before anybody
    is spawned, so nothing here can work it out for itself.

    `traps` caps how many are armed, and the caller is `story.cast_list`,
    which is the only thing that knows there is an **encounter budget**.
    Left `None` -- arcade mode, where there is no budget -- the draw below
    stands exactly as it did. #958.
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
    #
    # **The draw happens either way**, even when the caller has capped it
    # to nothing: it is one of this dresser's `pick` calls, and skipping
    # it would move every random decision after it, so two boards that
    # differ only in how much budget was left would differ in their rough
    # ground too. Drawn, then cut.
    how_many = pick.choice((0, 1, 1, 2))
    if traps is not None:
        how_many = min(how_many, max(0, traps))
    chosen = [_open(world, pick, spare) for _ in range(how_many)]

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


def printed_region(level: int = 1, pick: Random | None = None) -> dict | None:
    """A printed hindering region worth this board's tier, or None. `#1039`.

    **The region half of the table, which had no reader at all.** `#1039`
    and `#458` are both about this: 145 terrain rows are in `game.db` and
    before this the whole package read the table in **zero** places -- the
    one `FROM terrain` in the tree was a driver rule counting rows. The trap
    half has had `printed_trap` -> `arm` for a while; the region half had
    nothing, so a printed region could not reach a board by any route.

    **Only the rows that carry damage**, which is 47 of the 121 fantastic
    rows, because `hindering` is the one `Zone` field a database column can
    fill on its own. The other 74 want either a mechanism that does not
    exist yet or a `narrative=` marker, and `#1039`'s comment thread has the
    row-by-row read -- six of the residue are one modifier seam, eight are
    flavour, and two are genuinely novel. Nothing here guesses at them.

    **Bounded by tier, not level**, because that is the column the table
    has: `damage_tier` is 1 for heroic, and a heroic board must not lay a
    paragon region. The root rule is *"the level band does not cross a tier
    boundary"* and this is the same arithmetic one table over.

    `pick` is the board's own generator, so a board stays reproducible from
    its seed; without one the lowest eligible row is taken, which is what a
    caller with no seed deserves and is at least in range. Both choices are
    `printed_trap`'s, deliberately -- the two halves of one table should not
    draw differently.

    Returns a plain dict, so `lay` stays the only thing that knows which
    columns it wants. Again `printed_trap`'s shape.
    """
    from combat_engine.db import game

    tier = max(1, min(3, (max(1, level) + 9) // 10))
    try:
        rows = list(game().execute(
            "SELECT ref, effect, damage, damage_type, damage_tier "
            "FROM terrain "
            "WHERE kind = 'fantastic terrain' "
            "  AND damage IS NOT NULL AND damage != '' "
            "  AND damage_tier IS NOT NULL AND damage_tier <= ? "
            "ORDER BY damage_tier DESC, ref",
            (tier,),
        ))
    except Exception:            # no database, or a build without the table
        return None
    if not rows:
        return None
    return dict(pick.choice(rows) if pick is not None else rows[0])


def lay(world: World, row: dict, squares: set[Square] | frozenset[Square],
        *, until: When = When.ENCOUNTER) -> int:
    """Put a printed region on the floor as a hindering zone. `#1039`.

    **The first casterless `hindering` zone, and it needed an engine move to
    work at all.** `c.zone(hindering=)` wired its burn in `Cast._hinders`,
    which only a row could reach -- so laying one from here would have
    recorded the field and burned nobody, which is this component's named
    *silently false* failure. The handlers now live in `Zones._burns` and
    take the damage policy from the caller. Measured before moving it:
    **zero** content rows call `c.zone(hindering=)`, so `#952`'s facility
    had no caller and this is its first.

    `owner=0`, because nobody laid it. That is not a sentinel creature: it
    is read back only for `deal_damage`'s source, and the floor burning you
    has no attacker. `label` is the **ref**, so the burn is attributed to
    the printed row rather than to a card.

    **`damage_type` may name two types** -- one row prints a region dealing
    damage of two kinds at once -- and this passes the column through
    unchanged. `Zones._burns` falls back to untyped on a word it does not
    recognise rather than raising, which is the right side to fail on for a
    database string: a region that burns untyped is nearer the printed row
    than one that refuses to exist. The two-type case is **not** modelled
    here and wants `deal_damage`'s `dtypes=`, which this path has no way to
    reach yet.
    """
    return world.zones.create(
        0,
        str(row.get("ref") or "terrain"),
        frozenset(squares),
        until,
        hindering=str(row.get("damage") or ""),
        hindering_type=str(row.get("damage_type") or ""),
    )


#: An object's AC, Fortitude and Reflex by size, with its base hit points.
#: **DMG page 65, the "Object Properties" table, read in `resources/` and
#: transcribed cell for cell** rather than derived from anything:
#:
#:     Size        AC/Reflex  Fortitude  base HP  example
#:     Tiny            10         5         5     bottle, book
#:     Small            8         8        10     treasure chest
#:     Medium           5        10        20     door, statue
#:     Large            4        12        40     wagon, vault door
#:     Huge             3        15       100     big statue
#:     Gargantuan       2        20       200     even bigger statue
#:
#: **AC and Reflex are ONE column on the page**, which is why they are one
#: value here rather than two that happen to agree: an object neither
#: parries nor dodges, so the page prices both the same.
#:
#: **And the page prints no Will.** `Defenses.base` answers 10 for a key it
#: does not hold, so an attack against an object's Will reads 10 -- a
#: number the page does not give. Recorded rather than invented: the
#: printed table has three columns and this holds three, and a row aiming
#: at an object's Will is a case 4e does not price.
#:
#: The hit points are **not** applied by `put()`, whose `hp` is the
#: caller's for the reason its own docstring gives -- a module or an
#: objective states what a thing can take. They are kept here because the
#: table is one table and splitting it invites a second transcription.
OBJECT_DEFENCES: dict[Size, tuple[int, int, int]] = {
    Size.TINY: (10, 5, 5),
    Size.SMALL: (8, 8, 10),
    Size.MEDIUM: (5, 10, 20),
    Size.LARGE: (4, 12, 40),
    Size.HUGE: (3, 15, 100),
    Size.GARGANTUAN: (2, 20, 200),
}


def object_defences(size: Size) -> Defenses:
    """The printed defences for an object of that size, flat.

    `scale="none"` is the whole reason this is a component rather than a
    curve: the page gives one number per size and no level term, so
    neither the character build-up nor the monster take-out applies.
    `engine/scaling.py` reads that field.

    **Five rows waited on this and every one said the same thing** --
    *"a `Scenery` carries no defences, so there is nothing for an attack
    against it to roll against: `query.defence` opens
    `world.need(eid, Defenses)`"*. Aiming at an object was already written
    (`Target(objects=True)` unions `query.scenery` into the pool and
    `loose=` is the printed word); what was missing was something to hit.

    An unknown size falls back to Medium -- the middle row and the
    commonest printed example, a door -- rather than raising, because a
    spawner that cannot name a size should still produce a thing that can
    be attacked.
    """
    ac_ref, fort, _hp = OBJECT_DEFENCES.get(size, OBJECT_DEFENCES[Size.MEDIUM])
    return Defenses(values={AC: ac_ref, REF: ac_ref, FORT: fort}, scale="none")


def put(world: World, square: Square, *, kind: str = "object",
        hp: int = 0, size: Size = Size.MEDIUM, fastened: bool = False,
        solid: bool = True, by: int = 0, ref: str = "") -> int:
    """Stand something in the room that no power put there. #988.

    A crate, a statue, a barricade. `Scenery` has been declared and
    documented since `#714` and **constructed nowhere** -- zero call sites
    outside its own definition, which is what `#988` is filed about and
    what kept four encounter objectives unbuildable: destroy the thing,
    carry the thing, escort a ward, protect another.

    **`hp` is what makes it destructible, and it is opt-in.** With `hp=0`
    the thing has no `Health`, which is `Scenery`'s documented default --
    *"no turn, no initiative slot, no vote on whether the fight is over,
    and nothing can attack it"*. A statue nobody can break is the common
    case and costs nothing.

    With `hp`, it gets `Health` so it can be aimed at and broken -- and
    `query.combatants` subtracts `Scenery` for exactly that reason, the
    fourth subtraction after a companion, a barrier and a conjuration.
    Without that subtraction a crate with hit points lands in the
    initiative roster and is asked what it wants to do.

    **No `Side`, ever.** That is what keeps it out of
    `Encounter.winner`'s reckoning: `team()` answers `None` for a thing
    with no side and `None` is discarded, so a crate left standing cannot
    stop a fight ending.

    `hp` is the caller's, not a curve: the printed DCs for breaking a thing
    are **flat rather than by level** -- 16 for a wooden door at every tier
    -- so there is no level maths to apply here and inventing one would be
    the fabrication this repo keeps warning about. A module or an
    objective states what the thing can take.
    """
    bits: list[object] = [
        Ident(ref=ref or f"scenery:{kind}"),
        Position(square=square, size=size),
        Scenery(kind=kind, fastened=fastened, by=by),
        # **The printed defences, so the thing can be attacked at
        # all.** Five rows carried `Scenery.defences` and each said
        # the same: aiming at an object was written and there was
        # nothing to roll against. DMG page 65, by size. #1233.
        object_defences(size),
    ]
    if hp > 0:
        bits.append(Health(hp=hp, max_hp=hp, dies_at_zero=True))
    eid = world.spawn(*bits)
    if solid:
        place(world, eid, square)
    else:
        # **The square is where it is, not something it owns** -- the
        # conjuration spawner's words, and the same distinction: a crate
        # blocks its square, a campfire is stood in. Setting `Position`
        # without indexing `grid.occupants` is the whole difference, and
        # indexing is what the index is for -- `Position.square` alone
        # leaves `squares_of` empty while the position names the square.
        world.need(eid, Position).square = square
    return eid


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

    **Two kinds, which is DMG2's first design decision about a trap** and
    now the split this function makes. The book:

        Single-Shot Traps: single-shot traps attack once and are done.
          [...] Being attacked every round as long as you stand in a square
          is not a single-shot trap.
        Ongoing Attack Traps: these traps continually attack the targets
          while they are in the area.

    So the printed `Initiative` modifier decides which this row is, and it
    is a signal rather than a rule of ours: a block that prints one is
    saying it acts on its own count. 90 of the drawable rows print one.

    * **no modifier** -- the single-shot case. One `EnterSquare` attack and
      then `sprung` stays set: a plate that goes off and does not reset is
      what the flag was written for, and a trap that fires every time
      something crosses it grinds a creature down for walking. Unchanged.
    * **a modifier** -- an `Initiative`, a slot in the order, and an attack
      on its own turn against whoever is standing in its square.

    **The geometry is the book's, not invented.** An ongoing trap's area is
    in `trap.spec` as prose and is unparsed, so there is no column to read
    -- but DMG2's own example of the category *is* "attacked every round as
    long as you stand in a square", so the square it occupies is the area it
    names. `_TRAP_AREA` would be a guessed number and this is a quoted one.

    `sprung` is deliberately not consulted on that branch: an ongoing trap
    is defined by not being done after one attack.
    """
    printed = printed_trap(level, pick)
    eid = world.spawn(
        Ident(ref=printed["ref"] if printed else f"t:{ref}"),
        Position(square=square),
        Trap(
            ref=printed["ref"] if printed else ref,
            perception_dc=printed["perception_dc"] if printed else None,
            # The printed countermeasure, off the same row and read the same
            # way as the Perception DC: absent means it cannot be disarmed,
            # not that it is easy to. #955.
            disable_skill=(printed["disable_skill"] or "") if printed else "",
            disable_dc=printed["disable_dc"] if printed else None,
            # **Only the printed expression, never the fallback.** `hurts`
            # below falls back to an invented `1d10+level` when there is no
            # row; storing that here would hand `policy/` a number the book
            # never printed and no way to tell. Empty says "unpriced", which
            # is a reading the hazard term can act on. #981.
            damage=(printed["damage"] or "") if printed else "",
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

    def strike(victim: int) -> None:
        # Through `resolve.attack` with the trap itself as the attacker, so
        # `is_trap(ctx["attacker"])` is true for the rows that ask and an
        # attack bonus hung on the trap by a power is read like anyone
        # else's.
        if attack(world, eid, victim, bonus, against, power=trap.ref):
            hurt = world.rng.roll(hurts).total
            world.damage(eid, victim, hurt, DamageType.UNTYPED, detail=trap.ref)

    ticks = printed.get("initiative") if printed else None
    if ticks is None:
        def stepped(ev: EnterSquare) -> None:
            if trap.sprung or ev.square != square:
                return
            # **A delayed or disabled trap effectively isn't there** -- DMG
            # p84's own words -- so the plate does not go off and `sprung`
            # stays clear, which is what lets the trap work again if the
            # delay lapses. #955.
            if suppressed(world, eid):
                return
            # Health is what tells a creature from the scenery and the
            # zones, which also walk through squares.
            if world.get(ev.actor, Health) is None:
                return
            trap.sprung = True
            strike(ev.actor)

        world.bus.on(EnterSquare, stepped, owner=eid)
        return eid

    # **The ongoing case.** An `Initiative` is what puts it in the order --
    # `query.turn_takers` tests for exactly that -- and the modifier is
    # stored as printed so `level_term` takes the level back out of it the
    # way it does for a monster.
    world.add(eid, Initiative(bonus=ticks))
    # **And it has to `join`, or the slot never exists.** `dress` lays its
    # traps from a `RoundStart` watcher -- deliberately, so the floor can be
    # asked whether a square is free -- and `start` rolls initiative
    # *before* the first `RoundStart` fires. So a trap armed the normal way
    # arrives after the order is built and was absent from it: measured, and
    # the component was right there in the world with nobody calling on it.
    #
    # `join` is the door already built for exactly this ("anything spawned
    # mid-fight was simply absent from the order before this, which meant it
    # never got a turn at all"), and it rolls the initiative off the
    # component laid above. Guarded on a *started* encounter because `arm`
    # is also called directly, before one exists.
    enc = getattr(world, "encounter", None)
    if enc is not None and getattr(enc, "started", False):
        enc.join(eid)

    def each_turn(ev: TurnStart) -> None:
        if ev.actor != eid or ev.ghost:
            return
        # Same suppression as the plate above. An ongoing trap keeps its
        # initiative slot while delayed -- the page takes it out of
        # commission, not out of the order -- so this declines on the turn
        # rather than leaving the order.
        if suppressed(world, eid):
            return
        # Whoever is standing in it, and nobody if the square is empty.
        # The trap is deliberately absent from the occupancy index -- see
        # above -- so this reads the creature on top of it rather than the
        # trap itself.
        victim = world.grid.occupant(square)
        if victim is None or world.get(victim, Health) is None:
            return
        strike(victim)

    world.bus.on(TurnStart, each_turn, owner=eid)
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
