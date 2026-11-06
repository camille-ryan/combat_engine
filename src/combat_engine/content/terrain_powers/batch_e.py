"""Terrain powers: five of the printed rows. `#1123`.

`batch_a` holds the account of the whole mechanism and is the file to read
first -- `Attack(level_plus=)`, `Check(skill, band)` as a header field, and
why a check rolled in a body is rolled once per target. Nothing is repeated
here that is said there.

**Every row in this batch is `usage=Usage.AT_WILL`, including the three
whose heading reads `Single-Use Terrain`**, and that is deliberate rather
than sloppy. The single use belongs to the **region**, not to the user:
`Zone.power_uses`, whose own note gives the argument -- *"a single-use
feature is spent for everybody once anybody uses it, and `Powers.used`
counts per creature, so the per-creature grain would let a second character
shove the same boulder down the same slope"*. A row declaring
`usage=Usage.ENCOUNTER` would put the limit on the wrong holder and read as
if it had been modelled. Counting it off the heading per row is `#1104`.

**Two of these three rows print a flat `Check:` DC rather than a band**, so
they take `Check(skill, dc=N)` and never touch `combat_engine.dc`. That is
the precedence `Check.dc` already states -- a stated number wins over a
band, because a band is lossy -- and it is also the global rule about never
deriving a number the page prints.

**What the harness cannot see, and it is worth knowing before reading a
green verdict here.** No board in the tree lays a zone carrying
`Zone.power`, so a body that has to *find its own region* reaches nothing
on the audit board: it rolls the header's check, returns, and reports
"fired and did something" on the skill check alone. `x2_125` in `batch_a`
is already in that state and so is `x2_147` below. The three rows whose
geometry comes off their own header -- `x2_143`, `x2_145`, `x2_156` -- do
not depend on the region and are really exercised.
"""

from __future__ import annotations

from combat_engine.engine.cast import Cast
from combat_engine.engine.dsl import (
    EACH_OTHER,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    Attack,
    Check,
    CloseBlast,
    Damage,
    Melee,
    power,
)
from combat_engine.engine.durations import When
from combat_engine.engine.grid import Square, distance, spread
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.types import (
    ActionType,
    Condition,
    DamageType,
    Defense,
    Usage,
)
from combat_engine.engine.zones import Zone


def _region(c: Cast) -> Zone | None:
    """The board region this row belongs to, by `Zone.power`.

    `batch_a`'s `x2_125` found its own with an inline generator; two rows
    here want the same lookup, which is the one case the global rule allows
    a helper for.

    It answers the **`Zone`** rather than its entity id, because what both
    callers want is `Zone.squares` -- `Zones` has `occupants(eid)` and no
    squares reader at all, so an id would have to be turned back into the
    component by hand at each site.
    """
    return next(
        (zone for _eid, zone in c.world.each(Zone) if zone.power == c.ref),
        None,
    )


@power("x2_143", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(2), target=EACH_OTHER,
       check=Check("athletics", dc=17),
       attack=Attack(printed=9, vs=Defense.FORT),
       damage=Damage("1d10", 3))
def x2_143(c: Cast) -> None:
    """Shove it over: it fills a 2-by-2 space, which stays rough ground.

    **`CloseBlast(2)` is the printed 2-square-by-2-square space**, and it is
    aimed off the *region* rather than off the user: `actions._terrain`
    passes the zone's square as `Action.origin` precisely because these
    cards say "in the direction it falls", and `dsl.area_of` reads it. So a
    blast 2 is the printed footprint and its direction is the one the aiming
    chose, which is the printed "chosen by the attacking creature".

    **`EACH_OTHER` and not `EACH_ENEMY`.** The card says *each creature in
    the affected space* -- a thing toppling over does not read sides, and
    `EACH_ENEMY` would have let the user bring it down on an ally for free.
    `EACH_OTHER` is everybody but the user, which is where
    `lint._close_area_hits_itself` puts a close area and is right here for a
    second reason: the user picks the direction, so a user caught by its own
    shove is a choice nobody would make. The one case it loses is a user
    standing *inside* the printed footprint anyway -- see `x2_156`, where
    that is likelier.

    `Check("athletics", dc=17)` and no band: the page prints the number
    outright, so `Check.dc` takes it and `combat_engine.dc` is not asked.
    `Attack(printed=9)` for the same reason -- a finished total, level
    inside it, which is what `world.scaling.trim` exists to take back out.

    **The prone is unconditional and the damage is not.** `Hit:` carries the
    damage; the knock-down and the rough ground are both on the `Effect:`
    line, which pays out whether the attack landed or not. Writing the prone
    inside the `c.strike()` branch is the natural mistake here and would
    have dropped it on every miss.

    `if c.first` on the zone because the body runs once per creature caught
    and the ground is churned once -- and `c.area()` rather than a
    hand-walked footprint, so the squares the zone covers are exactly the
    squares the attack was aimed at.
    """
    if c.first:
        area = c.area()
        if area:
            c.zone(area, difficult=True, until=When.ENCOUNTER)
    if c.strike():
        c.hit()
    c.prone()


@power("x2_144", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       check=Check("athletics", "moderate"),
       attack=Attack(level_plus=3, vs=Defense.REF))
def x2_144(c: Cast) -> None:
    """Work somebody one square sideways, into the part that holds on.

    The slide is the whole premise of the attack -- *"you slide the creature
    1 square into the x2_144 square adjacent to it. You then make the
    following attack against that creature"* -- so it goes first and names
    its destination: `c.slide(1, to=)`, whose own docstring is about exactly
    this failure, a row that means "into a named square" sliding somebody
    the stated distance *away*.

    **The destination is a square of the region adjacent to the target**,
    which is the printed wording and is read off `Zone` rather than guessed:
    `world.zones` holds the squares and `query.squares` holds the target's.
    Sorted before the pick, because a `min` over a set is not stable across
    runs and a replay fixture compares event for event.

    **The attack is not gated on the slide landing.** A region with no
    square beside the target is a board on which the printed Check -- *"to
    maneuver one creature adjacent to you and to the x2_144 into a x2_144
    square"* -- had nothing to maneuver anybody into, and the card still
    reads "you then make the following attack". Gating it the other way
    would also make the row silent on every board that lays no region at
    all, which today is all of them; see the module docstring.

    The hold and its Aftereffect are both `save ends`, and the second hangs
    off the first with `c.aftereffect` -- not `escalate=`, which is its
    mirror and pays out on a *failed* save instead of when the hold is
    over. `victim` is bound before the lambda: by the time an aftereffect
    lands, `c.target` is whatever the board is doing next.
    """
    here = squares_of(c.world, c.target) if c.target is not None else frozenset()
    region = _region(c)
    if here and region is not None:
        beside = sorted(
            sq for sq in region.squares
            if any(distance(sq, mine) <= 1 for mine in here)
        )
        if beside:
            c.slide(1, to=beside[0])
    if not c.strike():
        return
    victim = c.target
    held = c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    c.aftereffect(
        held,
        lambda: c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim),
    )


@power("x2_145", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(3), target=EACH_OTHER,
       check=Check("athletics", dc=21),
       attack=Attack(printed=9, vs=Defense.REF),
       damage=Damage("2d8", 4, half_on_miss=True),
       dropped=("escape.attempt(dc=)",),
       wants="an escape check against a printed DC made by a creature "
             "nothing is holding, so a pin under fallen stone can be got "
             "out of; `escape.attempt` returns False with no `holders`")
def x2_145(c: Cast) -> None:
    """Topple it: a blast 3 where it falls, and whoever it lands on is under it.

    `half_on_miss=True` is data for the card and `c.hit(half=True)` is the
    miss line, which is the pairing `m5648a2`'s note already states.

    **The miss slide is computed, not chosen.** The Miss line -- *"half
    damage, and x2_145 slides the target to the nearest unoccupied square
    adjacent to the area of the blast"*, with the ref standing where the
    card prints its own name -- names its square, so the ring around
    `c.area()` is filtered to squares that are on the board, passable and
    empty, and the nearest of them is handed to `c.slide(to=)`. The
    distance is the real one rather than 1: a creature at the back of a
    blast 3 is three squares from the ring, and a 1-square slide would
    have left it inside the rubble.

    **Superior cover, not partial, and `on=c.target` is load-bearing.**
    `c.cover(superior=True)` is the printed word and `c.cover()` is a
    different number. `c.cover` is one of the handful of verbs that default
    to the **caster** rather than to `c.target` -- its own note says so,
    "every printed line says you" -- and this card is the other way round:
    *"the target has superior cover"*. Written bare, the +5 landed on the
    creature doing the shoving, three times over, and the row still reported
    finished. Caught by reading the events, not by a verdict.

    **The pin is harsher than print and carries the marker for it.** The
    card says the target *"cannot stand up until it makes a DC 15 escape
    check"*. `c.prone(held=)` lays `Condition.PINNED` for a window, and the
    window the engine has for this is `When.ESCAPE` -- which
    `Effects._on_escape` only ever ends on a successful `Escaped` **matching
    a grab**, and `escape.attempt` returns False at once for a creature with
    no `holders`. Nobody is holding this one; a stone is. So `When.ESCAPE`
    here would be a hold with no exit wearing the right keyword, which is
    this component's named failure mode, and `When.SAVE_ENDS` would swap a
    printed flat DC for a saving throw -- a different mechanism and a
    derived number.

    The honest shape is the encounter clock, which is `batch_a`'s own
    reading of a condition with no turn boundary, plus `dropped=` naming the
    gap one layer down: it is `escape.attempt`'s `if not held: return
    False`, not a missing `Cast` verb. Until it lands, a creature caught
    under this stays down for the fight.
    """
    area = c.area()
    if c.first and area:
        c.zone(area, difficult=True, until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        c.prone(held=When.ENCOUNTER)
        c.cover(superior=True, until=When.ENCOUNTER, on=c.target)
        return
    c.hit(half=True)
    here = squares_of(c.world, c.target) if c.target is not None else frozenset()
    if not area or not here:
        return
    grid = c.world.grid
    ring = sorted(
        sq for sq in spread(area, 1) - area
        if grid.inside(sq) and grid.passable(sq) and grid.occupant(sq) is None
    )
    if not ring:
        return
    mine = min(sorted(here))
    spot: Square = min(ring, key=lambda sq: (distance(sq, mine), sq))
    c.slide(max(1, distance(spot, mine)), to=spot)


@power("x2_147", level=1, usage=Usage.AT_WILL, action=ActionType.MOVE,
       reach=PERSONAL, target=SELF,
       check=Check("athletics", "moderate"),
       dropped=("Zone.path", "c.running_start()"))
def x2_147(c: Cast) -> None:
    """Swing across on it, from the near end of the region to the far one.

    **A move action, off the header and not off the template.** 19 of the 24
    printed rows are standard and this is one of the two that are not, which
    is why `actions._terrain` prices the entry from `Power.action`.

    **The crossing is `c.link`, which is the verb this card was waiting
    for.** *"You move from the starting square to its ending square along
    the path"* over *"a deep chasm"* is not a walk -- there is no floor
    between the ends -- and it is not `c.teleport` or `c.jump` either,
    because the printed line says *"this movement provokes opportunity
    attacks"* and both of those skip the way over. `c.link(a, b)` makes the
    two ends one step apart for `movement.reachable` and nothing else, so
    `c.walk_toward` crosses in a single ordinary step, provoking as a step
    does. The link is taken back immediately: it belongs to the swing, not
    to the board.

    **The printed failure is the header's, and costs nothing extra.**
    *"Failure: you do not move, and your move action ends"* is exactly what
    a failed `Check` already does -- `dsl.use` runs no body, reports the
    power used and spends the action. See `Check`.

    **Two clauses are dropped and neither is a guess.**

    * `Zone.path` -- the region records a set of squares and no *path*: no
      starting square, no travel, no ending square, and the card's own
      `Special:` line says the DM supplies all three. So the ends are taken
      as the region's two extremes, which is the best a square set can say,
      and *"you can let go from x2_147 at any point during this
      movement"* -- the ref standing where the card prints its own name --
      has no midpoint to let go at.
    * `c.running_start()` -- *"you can make an Athletics check to jump at
      the end of the swing, treating it as a jump with a running start"*.
      `rt:r51-t1` is already waiting on that symbol, so this reuses it
      rather than minting a synonym; `c.jump` takes a distance and no
      run-up, and the row also needs a direction `c.jump` cannot be given
      (`c.jump(to=)`, `m5355a3`).

    What is left is the swing itself, which is the clause the card is about.
    """
    region = _region(c)
    here = squares_of(c.world, c.me)
    if region is None or not here:
        return
    mine = min(sorted(here))
    path = sorted(region.squares)
    if not path:
        return
    start = min(path, key=lambda sq: (distance(sq, mine), sq))
    end = max(path, key=lambda sq: (distance(sq, start), sq))
    if end == start:
        return
    bridge = c.link(start, end, until=When.EOT)
    try:
        c.walk_toward(end, 1, on=c.me)
    finally:
        if bridge is not None:
            c.world.effects.end(bridge, "the swing ended")


@power("x2_156", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(3), target=EACH_OTHER,
       check=Check("thievery", "hard"),
       attack=Attack(printed=7, vs=Defense.FORT),
       damage=Damage("1d8", 4, dtype=DamageType.POISON),
       dropped=("Zone.breach_hp",),
       wants="a region with hit points and defences, so the printed second "
             "route -- 10 damage to one of its squares, all defences 10 -- "
             "sets the power off instead of the skill check")
def x2_156(c: Cast) -> None:
    """Breach it and it bursts: a blast 3 of poison, and nobody in it can see.

    **The header numbers come off the printed text and not off the
    extracted columns, and here the two disagree.** `terrain.x2_156` holds
    `damage = '10'` with no `attack_flat` and no `defence`, because the
    importer read the breach threshold -- *"otherwise deal 10 damage to a
    square of x2_156"*, the ref standing where the card prints its own
    name -- as the power's damage and then found no
    `Attack:` line to pair it with. The card's attack is `+7 vs. Fortitude`
    for `1d8 + 4` poison, and that is what the header says. Referred up;
    see the final report on `#1123`.

    `Check("thievery", "hard")` is a band, so the DC comes off
    `combat_engine.dc` at the user's level -- the header does that, and
    this is the one `thievery` row of the 24.

    **The second route to setting it off is dropped, with the symbol one
    layer down.** The card offers *either* the Thievery check *or* 10 points
    of damage to a square of the region, all defences 10. A `Check` holds one
    skill and a region has no hit points, no defences and nothing that can be
    aimed at -- `terrain.put` makes a `Scenery` with `Health`, but nothing
    ties a `Scenery` to a region's `Zone.power`. So the skill route plays and
    the attack route is named rather than approximated.

    The Requirement -- *"adjacent to it if you use the Thievery skill"* --
    is `Zone.power_reach`, not a body line, and 20 of the 24 rows are the
    same. It is not written here for the same reason `x2_124` does not write
    it.

    **`EACH_OTHER` is the one place this batch is narrower than its card.**
    The printed Target is *"creatures in the blast"* and the Requirement
    puts the user **adjacent to the thing that bursts**, so a blast 3 off
    `Action.origin` really does cover the user and the card really does
    catch it. `lint._close_area_hits_itself` reports `EACH_CREATURE` on any
    close area as a fault and keeps its ten genuine exceptions in
    `CATCHES_ITSELF`; that list is an instrument's and not a row's, so this
    row takes the safe pool and the exception is referred up rather than
    written here.
    """
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
