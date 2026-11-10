"""Terrain powers, batch B: `x2_116` through `x2_120`.

**Read `batch_a` first.** It holds the whole account of the mechanism --
`Zone.power`, `actions._terrain`, `dsl.use(board=True)` -- and of the two
header fields these five rows lean on: `Attack(level_plus=N)` for the
printed `Attack: Level + 3` (`#1105`) and `Check(skill, band)` for a
printed `Check:` that gates the rest of the power (`#1106`). Nothing in
that account is repeated here.

**No row here declares its Requirement line.** All five print one -- *"you
must be adjacent to ..."*, *"within 5 squares of ..."* -- and that is the
region's business, not the row's: `Zone.power_reach` is the number and
`actions._terrain` is the gate, so a `requires=` here would be a second
copy of the same rule, measured from the caster instead of from the floor.
`batch_a` does the same for `x2_124`, whose card prints one too.

**And no row here declares a usage.** The printed heading is `Single-Use
Terrain` on four of the five and `At-Will Terrain` on `x2_120`, and
single-use is spent **for everybody** the moment anybody uses it --
`Zone.power_uses`, decremented in `perform`. `Usage.ENCOUNTER` is the wrong
shape for that: `Powers.used` counts per creature, so it would let a second
character shove the same thing down the same slope. So all five are
`AT_WILL` and the limit lives on the region, which is `Zone.power_uses`'s
own argument.

**Every target line here is an `other` pool, never an `any` one.** Three
rows print *"each creature in the blast"* and one prints *"one creature you
choose"*, and neither sentence means the creature setting the thing off --
but `Target("any", ...)`'s pool is `query.creatures`, which includes the
caster, and a close area is centred on the caster's own square. `lint.py`
names this for `EACH_CREATURE` and has no gate for the single-target
spelling, where it had to be read off `show.py`: `x2_120` was aiming at the
user until it was. See `EACH_OTHER`'s own comment in `dsl`.

What is new here, and the four markers, row by row:

* **`x2_116`** is the first row in the tree whose target line is a *path*:
  *"each creature whose space it enters"*, over `1d6` squares. Not an area,
  so `target=NO_TARGET` and the body walks `c.line` -- the idiom
  `monsters/level_04/artillery_sa._spirit_run` established for the same
  printed sentence. Finished, and like `x2_125` it needs a region carrying
  its ref before the body can run.
* **`x2_117`** prints a choice of two areas, which is `Range.alt` -- the
  field whose own docstring names the one other row printing *"close blast
  3 **or** area burst 3"*. Two clauses dropped: the gating swing is against
  an object with no defences to swing against (`Scenery.defences`), and
  the area is centred on that object rather than on the user
  (`c.area_origin()`). Aiming at the object is written -- #1216.
* **`x2_118`** prints `Check: Strength check (DC 20)`, which is an
  **ability** check and not a skill one -- `Check.skill` is validated
  against `engine.skills.SKILLS` and refuses it at declaration. The gate is
  rolled and honoured in the body instead, so the row plays exactly as
  printed; what is missing is the header *field*, which is what the page
  and the AI policy read without running anything.
* **`x2_119`** is the one row here needing no marker.
* **`x2_120`** prints a check the user may make with any of three skills.
  `Check.skill` holds one, where `Attack.ability` has taken a tuple for
  exactly this shape since the field existed.
"""

from __future__ import annotations

from combat_engine.engine.cast import Cast
from combat_engine.engine.dsl import (
    EACH_OTHER,
    NO_TARGET,
    PERSONAL,
    Attack,
    Check,
    CloseBlast,
    CloseBurst,
    Damage,
    Range,
    Target,
    power,
)
from combat_engine.engine.durations import When
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.types import Ability, ActionType, DamageType, Defense, Light, Usage
from combat_engine.engine.zones import Zone


@power("x2_116", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=PERSONAL, target=NO_TARGET,
       check=Check("athletics", "hard"),
       attack=Attack(level_plus=3, vs=Defense.FORT))
def x2_116(c: Cast) -> None:
    """Shove it, and it runs `1d6` squares through whoever is in the way.

    **The target line is a path, not an area, and that is why this row is
    `NO_TARGET`.** *"Each creature whose space it enters"* cannot be a
    `Target`: the set is decided by where the thing rolls, which is decided
    by a die and by a choice, and both happen after targeting. `c.line` is
    the path and `c.in_squares` is who is standing in it -- the idiom
    `monsters/level_04/artillery_sa._spirit_run` is written in, for the same
    printed sentence, and `m4621a2` declares `target=NO_TARGET` for it too.

    `PERSONAL` rather than a `Ranged(6)` that would cover the same ground,
    because `dsl.PROVOKING_KINDS` holds `ranged`: the shove is a thing you
    do to something you are standing next to, and declaring it ranged would
    open an opportunity window the card does not print.

    **It starts from the region's own square**, which is why the body opens
    the way `x2_125`'s does. The printed Requirement puts the user
    *adjacent* to the feature, so the user's square is the wrong origin --
    and nothing else on the board records where the thing is. Like
    `x2_125`, the body therefore does nothing until something lays a region
    carrying this ref; that is `#1104`, not a gap in this row.

    `c.roll("1d6")` and the ring at exactly that distance: the page prints
    the die, so the die is rolled rather than a distance being picked. The
    destination is the decider's, ordered by how many creatures the run
    crosses so that `World.decide` taking the head of the list picks the run
    the card is for -- again `_spirit_run`'s arrangement.

    **The path stops at the first square it cannot enter**, which is the
    printed *"stopping after moving ..."* read honestly: a run of six
    squares through a wall is not six squares. The `[1:]` is the square it
    started in -- the thing is already there, so it does not *enter* it.

    `side="other"` and not `"any"`: `_side("any")` is `query.creatures`,
    which **includes the caster**, and a shover standing in the line of
    their own shove is not what the card is about. Allies are in, which is
    the printed *"each creature"*.

    `2d10 + c.stats.half_level` in the body rather than a `Damage` header,
    because `Damage.bonus` resolves an int or a named **ability modifier**
    and one-half level is neither. That costs the MM3 conversion, which is
    an honest limit and the one `Damage`'s own docstring names; it costs
    nothing else here, since a patch of ground is on no monster's curve.

    The miss line is a destination and not a distance -- *"out of its
    path"* -- so it goes through `c.slide(to=)`, which exists for exactly
    the sentence that names where rather than how far.
    """
    feature = next(
        (zone for _eid, zone in c.world.each(Zone) if zone.power == c.ref),
        None,
    )
    if feature is None or not feature.squares:
        return
    start = min(feature.squares, key=lambda sq: (distance(sq, c.here), sq))
    far = c.roll("1d6")
    ring = [
        sq
        for sq in spread({start}, far) - spread({start}, far - 1)
        if c.world.grid.passable(sq)
    ]
    if not ring:
        return
    ring.sort(key=lambda sq: (-len(c.in_squares(c.line(start, sq), side="other")), sq))
    dest = c.choose(ring, f"{c.ref}: where it runs") or ring[0]
    path: list[tuple[int, int]] = []
    for sq in c.line(start, dest)[1:]:
        if not c.world.grid.passable(sq):
            break
        path.append(sq)
    crossed = frozenset(path)
    for victim in c.in_squares(crossed, side="other"):
        if c.strike(on=victim):
            c.damage("2d10", c.stats.half_level, on=victim)
            c.prone(on=victim)
            continue
        mine = squares_of(c.world, victim)
        away = sorted(
            sq
            for sq in spread(mine, 1) - mine
            if sq not in crossed
            and c.world.grid.passable(sq)
            and c.world.grid.occupant(sq) is None
        )
        if away:
            picked = c.choose(away, f"{c.ref}: out of its path") or away[0]
            c.slide(1, on=victim, to=picked)


@power("x2_117", level=1, usage=Usage.AT_WILL, action=ActionType.MINOR,
       reach=Range("close_blast", 3, alt=Range("close_burst", 1)),
       target=EACH_OTHER,
       attack=Attack(printed=13, vs=Defense.FORT),
       damage=Damage("1d10", 3),
       dropped=("Scenery.defences", "c.area_origin()"))
def x2_117(c: Cast) -> None:
    """Break it and the fragments fly: a blast or a burst, the user's pick,
    and the ground it covers stays rough for the rest of the fight.

    **The printed choice of two areas is `Range.alt`**, which is the field
    for it and whose own docstring names the only other row in the tree
    printing one -- *"close blast 3 **or** area burst 3 within 10"*, where
    the caster picks and each half is offered as its own menu entry.
    `dsl.branches_for` makes both reachable; `c.area()` answers for
    whichever was used, which is what the Effect line below needs.

    **Two clauses dropped, and they are two different gaps.**

    `Scenery.defences` is the printed `Check:`, which is not a skill
    check at all: it is a melee basic attack against the feature itself, at
    a stated **AC of 5** -- a number the card gives, so nothing has to be
    derived; what is missing is anywhere to put it. `p465`'s note has the
    measured reason that cannot be
    written -- a scenery object carries no `Defences` and no `Health`, so
    there is nothing for an attack roll to beat. Dropping it makes the row
    **stronger than print**, which is worth saying plainly; it is a very
    small amount stronger, because a creature that qualifies for this row
    swings at a 5 and essentially never misses.

    `c.area_origin()` is the other half: the page centres the area on the
    feature's square, and nothing moves a declared area's origin --
    `i1531p1` carries the same symbol for the same sentence. The user is
    adjacent to the feature, so the header's own origin is one square out.
    Not computed by hand instead: the target set comes from
    `dsl.candidates` off the header reach, so an area the body drew itself
    would cover squares the engine never targeted.

    `Attack(printed=13)` because the page prints a finished total with no
    ability named and no level to add -- the same reading a stat block's
    line gets. Under the default scaling `Scaling.trim` returns it
    unchanged; under an opt-in preset it is rescaled against the *user's*
    level rather than the feature's, which is the nearest thing a
    level-less number can be given.

    The Effect is laid on `c.last` rather than `c.first`: the printed line
    is one region for the whole use, and difficult going is read by
    movement rather than by an attack roll, so either end of the use gives
    the same board -- `c.last` is chosen to match `x2_119`, where the order
    does change the rolls. With no creature caught the body still runs once
    with no target, and `c.last` is true then, so the ground is still
    spoiled.
    """
    if c.strike():
        c.hit()
    if c.last:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER)


@power("x2_118", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(3), target=EACH_OTHER,
       attack=Attack(printed=18, vs=Defense.REF),
       dropped=("dsl.Check(ability=)",))
def x2_118(c: Cast) -> None:
    """Tip it over and the coals go everywhere: a blast, and whoever is in
    it burns until they shake it off.

    **The printed gate is an ability check, which the header cannot hold.**
    The page prints `Check: Strength check (DC 20)`, and `Check.skill` is
    validated against `engine.skills.SKILLS` at declaration -- rightly, a
    misspelling there is a check that cannot be rolled and therefore reads
    as a pass. A Strength check is not an Athletics check: Athletics adds
    the +5 for training that `skills.check` applies and this roll does not,
    so naming the skill would be a substitution and not a translation.
    `skills.ability_check` exists for precisely this distinction and says
    why in its own docstring.

    So the gate is rolled in the body, **once**, and the whole power is
    abandoned on a failure -- which is what the header field does and is
    the entire content of `#1106`. That needs the body to resolve every
    target in one call rather than once each, because a body that runs per
    target cannot stop the next one; `powers/monk/level_1.p13221` is the
    established shape for that and is written in here. The row therefore
    plays exactly as printed.

    What is dropped is the header *declaration*. `Attack` and `Check` sit
    in the header so the page and the AI policy can read a row **without
    running it**, and a gate living in the body is invisible to both: the
    menu cannot say the use might come to nothing, and `cards.py` compares
    the printed `Check:` line against a field that is empty here.
    `dsl.Check(ability=)` is the symbol -- one field beside `skill`,
    resolved through `Cast.ability_check` the way `band` already resolves
    through `combat_engine.dc.dc`.

    `Attack(printed=18)`: see `x2_117`, same reading and same caveat.

    `c.ongoing(10, FIRE)` takes `When.SAVE_ENDS` by default, which is the
    printed *"(save ends)"*. Ten is the page's number and the only one
    here; the card rolls no dice at all on a hit.
    """
    if not c.first:
        return
    if not c.ability_check(Ability.STR, 20):
        return
    for victim in list(c.targets):
        if c.strike(on=victim):
            c.ongoing(10, DamageType.FIRE, on=victim)


@power("x2_119", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(3), target=EACH_OTHER,
       check=Check("athletics", "easy"),
       attack=Attack(level_plus=3, vs=Defense.FORT))
def x2_119(c: Cast) -> None:
    """Kick it up: everyone in the blast is blinded, and the air stays
    unbreathable for the rest of the fight.

    Finished, and the only row in this file needing no marker.

    **The Effect is laid on `c.last`, and that is load-bearing here rather
    than tidy.** *"Heavily obscured"* is total concealment, which is -5 to
    attacks made through it; laid on `c.first` it would stand over the
    remaining squares of this very blast and penalise the rest of **this
    use's own rolls**, which the card does not do -- the Hit and the Effect
    are one simultaneous result. `x2_117` follows suit for consistency,
    where it makes no difference.

    With no creature in the blast the body still runs once with no target,
    and `c.last` is true on that call (`index` 0, `targets` empty), so the
    air is still spoiled -- which is right: the Effect line is not
    conditional on hitting anybody.

    `obscured=Light.DARK` and **not** `blocks_sight`, which `c.zone`'s own
    docstring warns against: sight-blocking is terrain that blinds both
    sides and stops line of effect, where the printed words grade the
    *light*. No `exempt=`, either -- eight cards in the tree print a cloud
    that spares the creature who made it and this one does not.

    `dc(c.level, ...)` is not called here, unlike `x2_124`: the band is a
    **header** field now, so `dsl.use` indexes `combat_engine.dc` itself
    before any target is walked. `x2_124` rolls its own only because it
    predates `#1106`.

    `c.blinded()` takes `When.EONT` by default, which is the printed
    *"until the end of your next turn"* -- the user's turn, and the caster
    is whose clock `EONT` means.
    """
    if c.strike():
        c.blinded()
    if c.last:
        c.zone(c.area(), obscured=Light.DARK, until=When.ENCOUNTER)


@power("x2_120", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBurst(5), target=Target("other", 1),
       check=Check("arcana", "hard"),
       attack=Attack(level_plus=3, vs=Defense.REF),
       dropped=("dsl.Check(skills=)",))
def x2_120(c: Cast) -> None:
    """Set it off at one creature in the burst.

    The only `At-Will Terrain` heading in this file, so nothing is spent by
    using it: `uses` is 0 in the table and the region keeps no count. See
    the module docstring for why every row here is `AT_WILL` regardless.

    **`Target("other", 1)`, which took three tries to get right.** The
    printed Target is *"one creature you choose"*, naming no side, so
    `ONE_CREATURE` is wrong -- it is `side="enemy"` and would refuse an ally
    the card allows. `ANY_CREATURE` is wrong the other way and **silently**:
    its pool is `query.creatures`, which includes the caster, and a close
    burst is centred on the caster's own square -- `show.py` duly reported
    `targets=[1]`, the user setting the thing off at themselves. That is the
    same fault `EACH_OTHER`'s comment describes one constant up, and
    `lint.py` catches it for the `everyone=True` constants only, so the
    single-target spelling has no gate and had to be read off the events.
    `powers/monk/second_card_1` and `races/powers_a` spell it this way too.

    **The marker is `dsl.Check(skills=)` and NOT `(skill=tuple)`, which is
    the shape it was first written as.** `blocked._one` resolves a marker by
    *parameter name*: it parses `dsl.Check(skill=tuple)` as the parameter
    `skill`, which already exists, so the type qualifier is invisible and
    `todo.py` reported the symbol **ARRIVED on the day the row landed** --
    red, on a gap that had not moved. The plural names a parameter that
    does not exist, so it resolves False today and goes red the day it
    lands, which is the one job that instrument has.

    Measured: exactly **1 marker in 848** had the type-qualifier shape, and
    it was this one, so this is a badly-named marker rather than a hole in
    the convention. The mirror of `#1118`, where a marker naming a dict key
    could *never* resolve: this one could never fail to.

    A close burst with a single target is the printed shape and
    `candidates` serves it; `powers/battlemind/level_0` has it twice.

    **The check is three skills and the header holds one.** The page prints
    a check the user may make with any of three, taking whichever they are
    best at -- which is the same printed shape `Attack.ability` has taken a
    tuple for since the field existed, resolved to *"whichever of them this
    creature is best at, which is the pick a player makes and the only one
    that can be made without asking mid-roll"*. `Check.skill` has no such
    form, so the row rolls the first of the three and is strictly weaker
    than print for anyone trained in one of the other two -- up to the
    whole +5 of a training, which is why this is a marker and not a note.
    `dsl.Check(skill=tuple)` is the symbol, and it is the same one line
    `Attack.ability` already carries.

    `2d6 + c.stats.half_level` in the body for the reason `x2_116` gives:
    `Damage.bonus` is an int or a named ability modifier and one-half level
    is neither.
    """
    if c.strike():
        c.damage("2d6", c.stats.half_level, dtype=DamageType.LIGHTNING)
