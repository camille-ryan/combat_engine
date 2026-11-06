"""Terrain powers, batch D: six rows the board owns. `#1123`.

`batch_a` holds the account of the mechanism and must be read first. What
is new here, and is new because `batch_a`'s two rows did not need it:

* **Four of the six print an area**, where `x2_125` prints one creature,
  and the four **split two ways on whether the user is in it.** The two
  bursts are `EACH_CREATURE` -- `candidates`' `"any"` pool, which includes
  the caster -- and each of them prints a clause that is *about* the caster
  being caught (`x2_133`'s duck, `x2_142`'s bonus), so the card settles it
  rather than the geometry. The two blasts are `EACH_OTHER`, because a
  close blast touches the user's space without covering it and so can never
  catch them. `lint._close_area_hits_itself` is the gate, it names the two
  bursts, and its waiver list is `CATCHES_ITSELF` in `scripts/lint.py` --
  which is an instrument rather than content, so the two refs are reported
  up for adding there rather than added from here.
* **Two print a flat number where the other rows print a band.**
  `Check(skill, dc=N)` and `Attack(printed=N)` are those, and both are the
  printed figure untouched -- see each row.
* **Two are not a standard action**: one `free` and one `move`. Read off
  the brief's header, which is the header-is-data rule working in the
  direction it is usually quoted in reverse.

**One seam is worth knowing before reading the four area rows, and it is
not fixable from here.** `actions._terrain` says *"the attack comes out of
the feature, not out of the user"* and hands `dsl.area_of` an `Action.origin`
-- the nearest square of the region -- for exactly that. `area_of` honours
it for `area_burst` and for the *aim* of a `close_blast`, and **ignores it
for `close_burst`**, which spreads from the user's own squares. So a burst
printed *centred on the feature* is centred on the user instead, and a blast
*out from the feature* starts at the user and merely points at it.

For a burst the error is bounded at one square, because every one of these
rows prints *"you must be adjacent to"* and so the user is never further
from the feature than that.

**For a close blast it is not an error of one square -- it is total, and it
was found by driving the rows rather than by reading them.** `candidates`
refuses an `origin` that is not in `aim_points`, and for a `close_blast`
those are `grid.blast_placements` -- *"for a Medium caster and a blast 3 the
keys come out as exactly the ring of squares two away"*, in that function's
own words. `actions._terrain` hands the **nearest** square of the region,
which under an adjacency requirement is one away and therefore never in that
ring. Driven on a board: `candidates` returns **[]** for all eight squares
around the user, so `x2_134` and `x2_135` resolve with `targets: []`, roll
nothing, and report a successful use.

Handed a legal aim point instead -- any of the ring two out -- both rows
catch three creatures and pay out in full, so the bodies are right and the
door is not. Nothing is worked around here: the rows declare the printed
reach, and a row that chose its own origin would be a second opinion about
aiming, which is the disagreement `#381` and `#894` are both about. The gap
is `actions._terrain`'s choice of origin against `aim_points`' contract, it
is reported up, and it is not confined to this file -- every close-blast
terrain row in the other batches has it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine.cast import Cast
from combat_engine.engine.dsl import (
    EACH_CREATURE,
    EACH_OTHER,
    PERSONAL,
    SELF,
    Attack,
    Check,
    CloseBlast,
    CloseBurst,
    Damage,
    keywords_of,
    power,
)
from combat_engine.engine.dsl import get as _row
from combat_engine.engine.durations import When
from combat_engine.engine.events import DamageRolled, Moved, PowerResolved
from combat_engine.engine.grid import Square, distance
from combat_engine.engine.query import allies
from combat_engine.engine.types import (
    ActionType,
    Condition,
    DamageType,
    Defense,
    Keyword,
    Usage,
)
from combat_engine.engine.zones import Zone


#: The "per tier" ladder: 1 in the heroic tier, 2 in paragon, 3 in epic.
#: Written out rather than taken from the heroic value alone because the
#: printed words are a formula covering all three, and honouring it costs a
#: line. Same shape as `feats/general._tier`.
def _tiers(level: int) -> int:
    return 1 if level < 11 else (2 if level < 21 else 3)


def _region_of(c: Cast) -> frozenset[Square]:
    """The squares of the feature this row belongs to, or an empty set.

    `x2_125`'s idiom: the zone is found back by ref rather than carried on
    the `Action`, which is `actions._terrain`'s own stated choice.
    """
    for _eid, zone in c.world.each(Zone):
        if zone.power == c.ref:
            return zone.squares
    return frozenset()


@power("x2_133", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBurst(2), target=EACH_CREATURE,
       check=Check("athletics", "hard"),
       attack=Attack(level_plus=3, vs=Defense.REF))
def x2_133(c: Cast) -> None:
    """Tip the thing over and let what is on it mix: a burst of burning fumes.

    `usage=AT_WILL` although the heading reads `Single-Use Terrain`, and
    that is not an oversight. `usable`'s own note says the single-use limit
    *"is not here at all, because it is a property of the feature:
    `Zone.power_uses`, decremented by `perform`"* -- a spent feature is
    spent for everybody, where a usage on this header would be counted per
    creature by `Powers.times` and let a second user tip the same thing
    over again. All six rows in this file declare `AT_WILL` for that reason,
    whichever heading they print.

    **"Ongoing 5 ... per tier" is the one derived number in this file and it
    is a printed formula rather than a printed total.** 5 at heroic, 10 at
    paragon, 15 at epic; `_tiers` is the ladder and nothing is invented. A
    row writing the heroic 5 flat would be silently wrong above 10th level,
    which is the direction that does not announce itself.

    `dtypes=` and not two `c.ongoing` calls: the printed line is one burn
    that is both types, so it ticks for five and takes **one** saving throw.
    Two calls would tick for ten and need two saves, which `c.ongoing`'s own
    docstring records as the bug it was built to end.

    **The duck is a real election and `c.may` is the verb for it**, asked of
    the user, since it is the user's standard action and the user's skin.
    Two things about it are deliberate:

    * It is only reached on the user's **own** iteration. `EACH_CREATURE` is
      the `"any"` pool, which includes the caster, and the printed sentence
      is about nobody else.
    * **The prone lands after the use resolves, not here**, which is the
      whole reason `_ducks` exists. `Condition.PRONE` carries `attack=-2`
      (`conditions.py`), the body runs once per creature caught, and
      `c.strike` rolls as the **user** -- so dropping prone on an iteration
      that is not the last would quietly take two off the feature's attack
      against everybody after it. A `PowerResolved` watch is the printed
      *"as part of the standard action"* with none of that: the action is
      over, the rolls are made, and the user is on the floor.
    """
    if c.target == c.me and c.may("drop flat rather than be caught in it",
                                  who=c.me):
        _ducks(c)
        return
    if c.strike():
        c.ongoing(5 * _tiers(c.level),
                  dtypes=(DamageType.FIRE, DamageType.POISON))


def _ducks(c: Cast) -> None:
    """Go prone once the use has finished resolving. See `x2_133`."""
    me = c.me

    def down(ev: Any) -> None:
        if ev.power == c.ref and ev.actor == me:
            c.prone(on=me)

    c.watch(PowerResolved, down, until=When.EOT, on=me, once=True,
            label=f"{c.ref} ducks")


@power("x2_134", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(3), target=EACH_OTHER,
       check=Check("athletics", "moderate"),
       attack=Attack(level_plus=3, vs=Defense.REF))
def x2_134(c: Cast) -> None:
    """Pull the hanging thing down on whoever is standing under it.

    One `c.condition` carrying **both** conditions rather than
    `c.blinded()` and `c.slowed()` beside each other. The printed line ends
    them together on one event, and two effects would be two things to end
    and two ways to end up holding half of it.

    **The duration is the one judgement in this row.** *"Until it is no
    longer underneath"* is neither a `When` nor a saving throw: it is the
    creature getting itself out. So the encounter clock is the outer bound
    and the real end is a `Moved` watch on the victim, which is the idiom
    `x2_124` uses and the event `x2_124` settled on -- `MoveStart` fires for
    a walk that is then **refused**, and a slowed, blinded creature is
    exactly the one whose attempted walk may come to nothing.

    What that reading costs, stated rather than hidden: the thing lands in a
    blast 3, so a creature could in principle take its two slowed squares
    and still be under the far end of it. A body cannot tell -- the blast's
    footprint is computed in `dsl.area_of` from an `Action.origin` that
    reaches neither `Cast` nor this body, and the victim's own square is the
    only part of the cover a row can see. The first move is the proxy, and
    it is the right answer for every victim the near end caught.

    `once=True` on the watch and the hold is ended by id, so a second step
    cannot end it twice.

    **Driven, and the first attempt at driving it lied.** A step onto an
    occupied square returns 0 from `walk`, the creature never leaves, and
    the hold reads as still standing -- which looks exactly like a watch
    that does not fire. Stepped somewhere free, `blinded` goes False on the
    `Moved`. The control has to assert the move landed; this one did not,
    once.
    """
    if not c.strike():
        return
    caught = c.condition(Condition.BLINDED, Condition.SLOWED,
                         until=When.ENCOUNTER)
    if caught is None:
        return
    victim = c.target
    spent: list[bool] = []

    def crawls_out(ev: Any) -> None:
        if spent or ev.actor != victim:
            return
        spent.append(True)
        c.world.effects.end(caught, "it is no longer underneath")

    c.watch(Moved, crawls_out, until=When.ENCOUNTER, on=victim, once=True,
            label=f"{c.ref} underneath")


@power("x2_135", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBlast(3), target=EACH_OTHER,
       check=Check("athletics", dc=23),
       attack=Attack(printed=16, vs=Defense.REF))
def x2_135(c: Cast) -> None:
    """Shove the standing vessel over and spill what is smoking in it.

    **Two flat numbers, and each goes in the field that means "as printed".**

    `Check(..., dc=23)` rather than a band: `Check.dc`'s own docstring says
    *"a stated DC, which wins over the band"*, and it exists because a band
    is lossy. 2 of the 24 printed rows state one outright and this is one of
    them -- nothing is read out of `combat_engine/dc.py` here.

    `Attack(printed=16)` rather than `level_plus=`: the page prints a
    finished total, which is what `printed=` means, where `level_plus=` is
    for the 14 rows printing *"Level + 3"* and would add a level this line
    does not mention. The number is untouched under the default scaling --
    `Scaling.trim` is the identity at `FULL` -- and moves with the preset
    under `bounded` or `half`, which is the whole point of declaring it as
    data. `ability=` would be wrong twice over, adding a proficiency and an
    ability score the thing on the floor has not got.

    One burn of two types for `x2_133`'s reason, and a flat 10 with no tier
    ladder, because this page prints a total and not a formula.
    """
    if c.strike():
        c.ongoing(10, dtypes=(DamageType.FIRE, DamageType.POISON))


@power("x2_140", level=1, usage=Usage.AT_WILL, action=ActionType.FREE,
       reach=PERSONAL, target=SELF,
       dropped=("etl.power.arcane_defiling",))
def x2_140(c: Cast) -> None:
    """Let the growing thing nearby soak the damage your own power deals your
    allies.

    The one row of the 24 whose requirement is a distance rather than
    adjacency -- *"within 5 squares of"* -- which `Zone.power_reach`'s
    docstring already names as the row a boolean could not have held. That
    is the feature's field and not this header's; nothing here needs to
    repeat it.

    `target=SELF` and not `NO_TARGET`. The body is about the user alone, and
    a `NO_TARGET` row gets `c.target is None`, which turns every defaulted
    call into a call on nobody -- the component file's named certainty.
    `SELF` gives one iteration with `c.target == c.me`, which is also
    `x2_124`'s shape.

    **What is written: the necrotic half.** A `DamageRolled` watch over the
    user's own blows, kept to blows landing on an **ally** -- `query.allies`
    excludes the caster, which is the printed word -- and to blows that are
    necrotic. Necrotic is asked twice, of the keyword line of whatever row
    `DamageRolled.detail` names and of the blow's own types, because *"a
    necrotic power"* is the keyword and the damage type is the same claim
    read off the roll; either answering is the card's sentence.

    `c.reduce` for the whole amount, which is the entire combat meaning of
    *"the feature takes that damage instead"*: nothing on a board holds a
    terrain feature's hit points, the card gives it none, and the
    consequence a fight can observe is that the ally takes nothing.
    `c.absorb` is the verb for moving a blow and it needs a creature to move
    it **to**; there is no such entity, and `c.place_scenery()` -- which
    would make one -- is itself a symbol three rows are already waiting on.

    **What is not written, and why the marker says so in those words.** The
    other half of the printed disjunction is the user's own defiling, and
    `#878` measured that it cannot be watched: **0** `Power` and **0**
    `ClassFeature` rows in the compendium name it, and the only two rows
    whose names mention it at all are paragon powers that *consume* it. So
    the symbol in `dropped=` is honest about what is absent and will not
    arrive, and it is `dropped=` rather than `defect=` because the necrotic
    half plays -- `defect=` refuses the whole row, which `content/CLAUDE.md`
    allows *"only when nothing survives"*. The three rows that moved from a
    symbol to `defect=` over this had nothing else on their cards.
    """
    me = c.me

    def soaked(ev: Any) -> None:
        if ev.source != me or ev.amount <= 0:
            return
        if ev.target not in allies(c.world, me):
            return
        row = _row(ev.detail) if ev.detail else None
        by_keyword = row is not None and Keyword.NECROTIC in keywords_of(
            c.world, me, row)
        if not (by_keyword or DamageType.NECROTIC in ev.types()):
            return
        c.reduce(ev.amount, ev)

    c.watch(DamageRolled, soaked, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} soaked")


@power("x2_141", level=1, usage=Usage.AT_WILL, action=ActionType.MOVE,
       reach=PERSONAL, target=SELF,
       check=Check("athletics", "moderate"),
       dropped=("Zone.path",))
def x2_141(c: Cast) -> None:
    """Swing across on the hanging line, and jump off the far end of the arc.

    A `move` action, read off the brief's header. The printed `Failure: you
    do not move, and your move action ends` needs nothing written: the
    header `Check` is rolled once in `dsl.use` before any body runs, a
    failure runs no body at all, and the action was already spent -- which
    is `#1106`'s *"an attempt that came to nothing, not a refusal"*.

    **`c.walk_toward` and not `c.move`.** The arc has no vote in it: the
    printed success moves you from one named square to another along a named
    path, so the compelled verb is the right one and `c.move`'s trip through
    `World.decide` is the wrong shape. It is still the creature's own move,
    so it provokes on the way, which is the printed sentence.

    The second Athletics check is the printed jump at the end, offered
    rather than taken because the card says *"you can"*. The result over ten
    is a running start, which is the whole of what a running start means --
    the same reading `p11208b` and `p11226b` carry, and the standing and
    running jumps differ by that halving and nothing else.

    **`dropped=("Zone.path",)`, and it is one gap rather than three.** The
    printed Effect hands the geometry to the DM: a starting square, a path,
    an ending square, and whether the line runs both ways. None of that
    reaches a column -- `Zone` carries `squares`, `power`, `power_uses` and
    `power_reach`, and no ordered path -- so the ending square here is read
    as the square of the region furthest from where the swinger stands.
    That stand-in is what the row plays on, and the three clauses it cannot
    honour are all downstream of the same missing field:

    * the path is the walk's own shortest route, not the declared arc;
    * *"you can let go at any point during this movement"* has no arc to let
      go of, so it is not offered;
    * the jump is undirected, where the card says it must go the way the
      arc was travelling -- `c.jump` takes `toward`/`away_from` as creatures
      and no square, so even the stand-in cannot be passed to it.

    Stated at this length because the alternative was a row that looked
    finished: the swing, the provoking and the jump all fire, and nothing
    about a green verdict would have said the arc was invented.
    """
    region = _region_of(c)
    if not region:
        return
    here = c.here
    landing = max(sorted(region), key=lambda sq: distance(here, sq))
    if landing == here:
        return
    c.walk_toward(landing, distance(here, landing), on=c.me)
    if c.here != landing:
        return
    if not c.may("jump at the end of the swing", who=c.me):
        return
    c.jump(int(c.check("athletics")) // 10)


@power("x2_142", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=CloseBurst(1), target=EACH_CREATURE,
       check=Check("athletics", dc=17),
       attack=Attack(printed=11, vs=Defense.REF),
       damage=Damage("1d6", 4),
       dropped=("Power.check_alt",))
def x2_142(c: Cast) -> None:
    """Knock the heavy growth down off the trunk onto everybody under it.

    `Check(..., dc=17)` and `Attack(printed=11)` are both the printed
    figures, for the reasons `x2_135` sets out. The damage goes in the
    header as `Damage` -- data, so `c.hit()` pays it and the expression can
    be rescaled -- and the daze is `EONT`, the printed *"end of your next
    turn"*.

    **The +5 is laid on the defence the card names, not subtracted from the
    attack.** `c.strike(plus=-5)` would come out to the same number, and it
    would be the printed +5 written on the wrong side of the comparison --
    invisible to anything reading modifiers, and wrong the moment a second
    clause touches either side. Untyped, because the line prints no type
    word in front of "bonus", and given back as soon as the roll is made:
    the bonus is *"against the attack"*, so it must not be standing when the
    next creature in the burst is rolled against.

    It is reached only on the user's own iteration, which is the printed
    condition -- *"if the attacking creature is also a target"* -- and is
    reachable at all because `EACH_CREATURE` is the `"any"` pool.

    **`dropped=("Power.check_alt",)`.** The card offers two ways to bring
    the growth down: the Athletics check, or a melee attack roll against the
    same number. `Check` holds one skill and one DC, and the roll is made in
    `dsl.use` before the body, so there is nowhere for the second route to
    go -- moving the check into the body to get it would lose the gating
    that `#1106` built the field for, and would roll it once per creature in
    the burst. The symbol is named after `Power.action_alt`, which is the
    same shape of gap and already has rows waiting on it. Everything else on
    the card plays; a user with a poor Athletics and a good swing simply has
    the harder of the two routes.
    """
    if c.target != c.me:
        if c.strike():
            c.hit()
            c.dazed(until=When.EONT)
        return
    ducked = c.bonus(Defense.REF, 5, on=c.me, until=When.EOT, kind="untyped")
    try:
        landed = c.strike()
    finally:
        if ducked is not None:
            c.world.effects.end(ducked, "the attack is resolved")
    if landed:
        c.hit()
        c.dazed(until=When.EONT)
