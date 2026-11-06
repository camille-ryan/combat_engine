"""Terrain powers, batch C: six of the printed rows. `#1123`.

`batch_a` holds the mechanism's whole account -- `Attack(level_plus=N)`,
`Check(skill, band)` as a header field, why a check cannot be rolled in a
body, and how `Zone.power` offers a row to whoever stands near enough.
Read that file first; this one only records what is particular to these six.

Three things recur here and are worth saying once.

**The printed heading does not set `usage=`.** Four of these six read
`Single-Use Terrain` and two read `At-Will Terrain`, and that distinction
lives on the **region** rather than on the row: `Zone.power_uses` is spent
for everybody once anybody uses it, where a `Usage` is spent per creature,
so declaring `ENCOUNTER` here would let a second character topple the same
thing the same round. Every row below is `AT_WILL` and the limit is the
region's, which is `Zone.power_uses`' own documented reason for existing.

**The area is centred on the thing on the floor, not on the user.**
`actions._terrain` hands `perform` the nearest square of the region as
`Action.origin` and `dsl.use` passes it to `area_of`, so an `AreaBurst`
bursts under the feature and a `CloseBlast` is aimed from the user *toward*
it. That is why the two burst/blast rows here need no geometry in their
bodies, and it is also why `within=1` is enough on `x2_129`: the origin is
the nearest square of a region the user is already standing beside.

**`_region` is vacuous when there is no region**, and that is the one place
these rows differ from `x2_125`. A printed target line like *"each creature
standing on it"* or *"one creature within 3 squares of it"* is measured
against the region's squares, and `x2_125` returns outright when no region
carries its ref. The same gate here would leave four of the six doing
nothing on any board that did not lay the region -- which is every board
`audit.py` builds -- so the clause is read as a *narrowing* instead: with a
region it bites, and with none there is nothing for it to measure, because
the only thing that can offer one of these rows is a region carrying its
ref. The honest cost is that a row fired by something other than
`actions._terrain` reaches its whole declared envelope, and the envelope is
wider than the card.

One-half level damage is rolled in the body rather than declared, because
`Damage.bonus` is a flat number or an ability modifier named as a string and
*"one-half level"* is neither. Those rows are not rescalable, which
`Damage`'s own docstring names as the honest limit for a body that does
something its header cannot say.
"""

from __future__ import annotations

from combat_engine.engine.cast import Cast
from combat_engine.engine.components import Skills
from combat_engine.engine.dsl import (
    EACH_CREATURE,
    EACH_OTHER,
    ONE_CREATURE,
    AreaBurst,
    Attack,
    Check,
    CloseBlast,
    Damage,
    Ranged,
    UpTo,
    power,
)
from combat_engine.engine.durations import When
from combat_engine.engine.ecs import World
from combat_engine.engine.grid import spread
from combat_engine.engine.types import (
    ActionType,
    Condition,
    DamageType,
    Defense,
    Usage,
)
from combat_engine.engine.zones import Zone


def _region(c: Cast) -> Zone | None:
    """The board region that offers this row, found back by `Zone.power`.

    The same lookup `x2_125` writes inline and `actions.perform` writes
    again -- by ref rather than off anything carried in, because the board
    may have moved since the menu was drawn.
    """
    return next((z for _eid, z in c.world.each(Zone) if z.power == c.ref), None)


def _off_region(c: Cast, reach: int) -> bool:
    """Is the target further than `reach` squares from the region?

    `reach=0` is the printed *"standing on it"* and 1 is *"adjacent to it"*.

    **False when no region carries this ref**, which is the module
    docstring's third paragraph: the clause has nothing to measure and the
    row was raised by something other than `actions._terrain`.
    """
    region = _region(c)
    if region is None or not region.squares or c.target is None:
        return False
    near = spread(region.squares, reach) if reach else region.squares
    return c.target not in c.in_squares(near)


def _trained(skill: str):  # noqa: ANN202
    """A `requires=` gate on a printed *"you must be trained in ..."* line.

    `Skills.trained` holds the words in lower case, which is what
    `skills.modifier` reads for its +5. A gate rather than
    `requires_text` alone: `usable` returns the text as the words a refusal
    prints, and with no callable beside it the row states a requirement it
    does not apply -- which is what `#236` found on seven assassin rows.
    """

    def gate(world: World, eid: int) -> bool:
        held = world.get(eid, Skills)
        return held is not None and skill in held.trained

    return gate


@power("x2_122", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(3), target=ONE_CREATURE,
       check=Check("athletics", "easy"),
       attack=Attack(level_plus=3, vs=Defense.REF))
def x2_122(c: Cast) -> None:
    """Kick a spray of particles into one creature's face.

    **One creature in a close blast 3**, which is a count and a shape that
    disagree, and both are printed: the blast is where the spray goes and
    the target line picks one creature out of it. `ONE_CREATURE` with
    `reach=CloseBlast(3)` is exactly that, and the blast is aimed from the
    user toward the region -- see the module docstring. No geometry in the
    body, so nothing here needs `_region`.

    **`c.bloodied()` with no argument asks about the target**, which is the
    printed *"if the target is bloodied"*. The caster is `on=c.me` and
    getting this the wrong way round is this component's commonest single
    mistake.

    **The harsher line is one `c.condition` call and not two.** *"Blinded
    and slowed (save ends both)"* is one hold with one saving throw; two
    calls would give the victim two saves and let it shake off half of a
    thing the card says is one. The gentler line is the plain
    `c.blinded`, which is the same verb with one condition in it.
    """
    if not c.strike():
        return
    if c.bloodied():
        c.condition(Condition.BLINDED, Condition.SLOWED, until=When.SAVE_ENDS)
    else:
        c.blinded(until=When.SAVE_ENDS)


@power("x2_123", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=Ranged(10), target=UpTo(2),
       check=Check("athletics", "moderate"),
       attack=Attack(level_plus=3, vs=Defense.REF),
       dropped=("dsl.Target.adjacent_to_each_other",))
def x2_123(c: Cast) -> None:
    """Bring the top-heavy column down across one or two creatures.

    The printed target line is *"one or two creatures, which must be
    adjacent to each other; one of the creatures must also be adjacent to"*
    the region -- two constraints, and `Target` can say neither. It caps a
    count and filters a side; it cannot say that the two chosen must stand
    together. `dsl.Target.adjacent_to_each_other` is the symbol
    `p8239`'s Augment 1 already waits on for the same sentence, reused
    rather than re-minted.

    **The region half is implemented, and it narrows rather than widens.**
    Each target must stand within 1 square of the region, where the card
    requires that of only *one* of the two and lets the second be merely
    adjacent to the first. So this is stricter than print on that clause,
    which is the safe direction to be wrong in, and the loose clause is the
    one carrying the marker.

    `Ranged(10)` is an aiming envelope and not a printed range -- the card
    prints none, the way `x2_125`'s does not -- and the region is the real
    bound, which is the gate above.

    One-half level damage in the body: see the module docstring.
    """
    if _off_region(c, 1):
        return
    if c.strike():
        c.damage("1d10", c.level // 2)
        c.dazed(until=When.SAVE_ENDS)


@power("x2_127", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=Ranged(3), target=ONE_CREATURE,
       check=Check("arcana", dc=13),
       attack=Attack(printed=6, vs=Defense.REF),
       damage=Damage("1d4", dtype=DamageType.FIRE),
       requires=_trained("arcana"),
       requires_text="you must be trained in Arcana",
       dropped=("Check.sticks", "query.attacked_with()"))
def x2_127(c: Cast) -> None:
    """Talk a blob of molten rock into going somewhere else.

    **The one row of the six that is two actions on one card, and the
    engine's `action=` is one value.** The printed heading is a *minor*
    action to make the Arcana check, and the Success line then says *"you
    can use this terrain power automatically until the end of the encounter.
    Each use counts as a standard action."* So the cheap action buys the
    understanding once and every attack after it is a standard action.

    Declared `STANDARD` with the check rolled every time, which is the
    **weaker** of the two readings available: a character pays a standard
    action and re-rolls Arcana for each attack, where the card charges one
    minor action and then nothing. Declaring `MINOR` would have been
    strictly stronger than print -- an attack for a minor action, all
    encounter -- and the standard action is what the card attaches to the
    attacking use, which is the use with combat meaning. `Check.sticks` is
    the field that would close it: a won check that is not rolled again for
    the rest of the encounter.

    **`query.attacked_with()` is the other half of the Requirement**, which
    reads *"you must ... have seen a creature be attacked with this terrain
    power"*. Nothing asks whether a ref has attacked anybody on this board,
    and implementing it as written would leave the row dead: in print the
    feature attacks on its own first and a character then learns to aim it,
    and nothing here makes a region attack unprompted. So the gate is the
    trained-in-Arcana half alone, which is more permissive than print, and
    the missing half is named.

    **`Attack(printed=6)` for a printed flat `+6`.** Not `level_plus=`,
    which the other five rows take and which this card does not print, and
    not `plus=`, which needs an ability a patch of molten rock has not got.
    The honest cost is that `printed=` means "a finished total with a level
    inside it", so `scaling.trim` takes the *user's* level back out under a
    non-default `world.scaling` -- exact under `FULL`, which is as published,
    and wrong under `BOUNDED`. `Attack` has no field for a flat bonus that
    is nobody's level.

    **`audit.py` reports this row UNUSED and that is the gate working.**
    The board it builds trains six skills and arcana is not among them on
    any seed, so `usable` refuses with the printed words and the body never
    runs there. Proved by hand instead: with `arcana` added to
    `Skills.trained` and a region carrying this ref, the row hits, deals its
    `1d4` and lays `ongoing 3` on 2 of 4 seeds, and with the region moved
    out of reach it rolls the check and stops -- a positive and a negative
    control on the same board. A row correctly refused by a printed
    Requirement is `audit.py`'s own *"a Requirement the board cannot meet"*
    bucket, and an excuse there belongs to whoever owns that instrument.

    The damage is declarable here -- a flat `1d4` with no half-level term --
    so it goes in the header as data and `c.hit()` applies it, which keeps
    the row rescalable. The burn is its own `c.ongoing`: *"1d4 fire damage
    plus ongoing 3 fire damage (save ends)"* is a blow and then a hold, and
    only the hold takes the save.
    """
    if _off_region(c, 3):
        return
    if c.strike():
        c.hit()
        c.ongoing(3, DamageType.FIRE)


@power("x2_129", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=AreaBurst(1, 1), target=EACH_CREATURE,
       attack=Attack(level_plus=3, vs=Defense.REF),
       dropped=("Zone.defences",))
def x2_129(c: Cast) -> None:
    """Cut the rope and let the heavy thing overhead come down.

    **No `check=`, because the card prints no skill check.** What it prints
    instead is two ways in: a *ranged attack against the thing itself*,
    whose defences are level + 5, or -- *"alternatively"* -- a standard
    action to cut the chain holding it up while adjacent to either. The
    second is printed as an automatic success and is what this row is, which
    is why the action cost is a standard action and the adjacency is left to
    `Zone.power_reach`.

    `Zone.defences` is the first way in. A region carries squares, a ref, a
    use count and a reach, and nothing that can be attacked -- so there is
    no defence for a ranged attack to beat and no hit points for it to take
    off. Naming the field rather than a verb, because
    `terrain.put` can already stand a destructible thing in a room: what is
    missing is the number on this region, not a way to shoot at it.

    **`AreaBurst(1, 1)` is the printed *"area burst 1 beneath it"*.** The
    burst's centre is `Action.origin`, which `actions._terrain` sets to the
    nearest square of the region -- so it bursts under the feature and not
    under the user, which is the whole reason that field exists. `within=1`
    is the printed adjacency: the origin is a square the user is already
    standing beside.

    The Effect line is laid under `c.first`, because a body runs once per
    target and the rubble is laid once per use. It is laid before the
    attacks rather than after them so that a use catching nobody still
    leaves the ground rough, which is what *"the area where it fell becomes
    difficult terrain"* says and does not condition on a hit.

    `until=When.ENCOUNTER` because the card gives the rubble no end. That is
    the longest clock the engine has, not a reading of the sentence.
    """
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER)
    if c.target is None:
        return
    if c.strike():
        c.damage("2d8", c.level // 2)
    else:
        c.half_damage("2d8", c.level // 2)


@power("x2_130", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=Ranged(10), target=EACH_CREATURE,
       check=Check("athletics", "moderate"),
       attack=Attack(level_plus=3, vs=Defense.REF),
       dropped=("Zone.depth",))
def x2_130(c: Cast) -> None:
    """Heave on the rickety span and put whoever is on it over the side.

    **`EACH_CREATURE`, which is the pool that includes the caster**, and the
    card says so outright: *"each creature standing on it (including you, if
    applicable)"*. `EACH_OTHER` is the pool that leaves the user out and
    would have been the wrong one by exactly the creature the parenthesis is
    about.

    The target line is the region's own squares, which no `Range` can
    name, so `Ranged(10)` is the envelope and `_off_region(c, 0)` is the
    bound -- *standing on*, so reach 0 and the region's squares themselves.
    Same arrangement as `x2_123` and for the same reason.

    **`Zone.depth` is the second half of the hit line.** *"The target is
    knocked prone. If the target is already prone, it falls off"* -- and a
    region records nothing about what is underneath it, so there is no
    distance to fall. `falling.drop` exists and takes a number of squares;
    the card prints none, calling it only *"a deep gap"*, so the gap is in
    what the region knows rather than in the vocabulary. Inventing a depth
    here would be inventing a damage expression.

    **Read before the condition is applied, not after.** `c.prone()` would
    make `c.is_(Condition.PRONE)` true for every target, so asking
    afterwards would answer the question the card asks with the answer this
    row just wrote.
    """
    if _off_region(c, 0):
        return
    already = c.is_(Condition.PRONE)
    if c.strike() and not already:
        c.prone()


@power("x2_131", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(3), target=EACH_OTHER,
       check=Check("athletics", "hard"),
       attack=Attack(level_plus=3, vs=Defense.REF))
def x2_131(c: Cast) -> None:
    """Shoulder the sagging stonework over and bury whatever it lands on.

    The printed target is *"each creature in a close blast 3 in the
    direction it fell"*. `CloseBlast(3)` is measured from the user and aimed
    at the region, which `area_of` does with `Action.origin` -- so the
    squares are the ones between the user and the thing coming down. That is
    an approximation of *"the direction it fell"* and it is stated here
    rather than marked, because the user is standing against the thing by
    the Requirement and so the two directions differ by less than a square.

    **`EACH_OTHER` and not `EACH_CREATURE`**, which is the pool that leaves
    the user out. The card says only *"each creature in a close blast 3"*,
    with none of `x2_130`'s parenthesis about including you, and `lint.py`
    refuses the `any` pool on a close area for exactly that reason. It is
    moot on the grid -- a blast does not cover the square it is thrown
    from -- and the declaration is what a reader and the AI policy see.

    **The Effect line covers two areas and the card names both** -- the
    squares the thing used to stand in, and the area of the blast, both
    becoming difficult terrain. So it is `c.area()` unioned with the
    region's own squares,
    laid once under `c.first`, before the attacks and unconditional on a
    hit -- the same reasoning as `x2_129`, which prints the shorter version
    of the same sentence.

    The rubble is laid even with no region on the board, with the blast
    alone: that is the module docstring's third paragraph, and it is the one
    place here where the vacuous reading loses half a clause rather than a
    gate.
    """
    if c.first:
        region = _region(c)
        buried = region.squares if region is not None else frozenset()
        c.zone(c.area() | buried, difficult=True, until=When.ENCOUNTER)
    if c.target is None:
        return
    if c.strike():
        c.damage("1d10", c.level // 2)
        c.prone()
    else:
        c.half_damage("1d10", c.level // 2)
