"""Ranger feats, the third batch.

`ranger.py` and `ranger_b.py` hold the first two, and eighteen of the
twenty-seven rows in the tree that talk to a beast companion live across
the three files, eleven of them here. The beast exists now: `c.beast()`
reads it and its numbers come out of the `companion` table.

Eight of the eleven are one card printed eight times, once per beast
category, differing only in the last sentence -- so `_leash` is the two
sentences they share and the rider is the third. What none of them can
say is the middle one: "while your beast companion acts independently it
need not move adjacent to you". The beast takes no turn of its own, so
there is no independent mode and no leash to lengthen.

**An `x_` token is the extractor's, not a missing row.** Two feats here
name one -- `x_m1031a4`, `x_m5139a3` -- and neither matches a ref. The
race's own spec line resolves both: it reads "p6188 : You have the
x_m5139a3 power", and the trait is `rt:r8-bloodied-enemies`. Read the
race before concluding a racial thing is undeclared.

Four things this batch found that were thought to be gaps.

**Standing up is announced.** `actions.legal` offers a `stand`, and
performing it ends the prone effect with `why="stood up"` -- so
`ConditionEnded` says both that a creature stood and that it stood on
purpose. That is `f2391` outright, and it is also the clause
`fighter_b.f1322` dropped as `c.provokes_on_stand()`: with the event in
hand, `c.provoke` opens the window. `f2712` writes it.

**"Shift to a square adjacent to the enemy" is an instruction, not a
choice.** `c.shift(to=)` takes the square, and `World.reachable_squares`
gives the candidates, so `_shift_beside` narrows them rather than
handing the decider a free shift that may walk the other way.

**High crit is a weapon property like any other.** Six heavy blades in
the table carry it, so a row that asks for "a heavy blade with the high
crit property" can ask for both.

**The opportunity window is public and cancellable.** `_survive_provoking`
opens one per adjacent enemy with `why` naming the ranged row, so a
narrowed exemption `c.no_provoke` cannot express is a `Window.BEFORE`
watch that cancels the ones the card names. `f2406` writes it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    REF,
    SELF,
    Ability,
    ActionType,
    AttackDeclared,
    Cast,
    Condition,
    ConditionEnded,
    Gear,
    Hit,
    Keyword,
    Miss,
    Moved,
    OpportunityWindow,
    PowerUsed,
    Relation,
    SurgeSpent,
    Trigger,
    When,
    Window,
    World,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import between
from combat_engine.engine.query import squares

from .styles import used_one_of

#: "Forgo one die of that damage". The payout **is** announced -- the
#: rider pays through `c.damage(detail="cf:ranger-f1")` and `DamageRolled`
#: is a `Decision` carrying that detail -- but it arrives as one number
#: with the rider's modifiers folded into it, so one die has no price.
FORGO = ("c.forgo_damage()",)


def _holding(c: Cast, *groups: str, prop: str = "") -> bool:
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    carried = (*gear.melee, *([gear.ranged] if gear.ranged else ()))
    return any(
        w.group in groups and (not prop or prop in w.properties) for w in carried
    )


def _grip(c: Cast, *groups: str, hands: int) -> bool:
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(
        w.group in groups and w.two_handed == (hands == 2) for w in gear.melee
    )


def _wielding(*groups: str, hands: int = 0) -> Callable[[World, int], bool]:
    """`_grip` as a `(world, eid)` predicate, which is what
    `c.rolls_with(when=)` is handed -- the swap is laid once at the start of
    the fight and has to be re-asked on every roll, because the axe can be
    put down.
    """

    def holds(world: World, eid: int) -> bool:
        gear = world.get(eid, Gear)
        if gear is None:
            return False
        return any(
            w.group in groups and (not hands or w.two_handed == (hands == 2))
            for w in gear.melee
        )

    return holds


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _missed_my_quarry_charging(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A charge of mine that missed the quarry.

    `charge` rides on `Miss` as a plain attribute, the way `opportunity`
    does, so it is read with a default rather than declared. The quarry
    is a relation and `c.is_quarry` is the same question from a `Cast`;
    a predicate is handed the world instead.
    """
    return (
        ev.attacker == me
        and bool(getattr(ev, "charge", False))
        and world.relations.holds(Relation.QUARRY_OF, me, ev.target)
    )


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _my_melee_attack(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.attacker == me and p is not None and p.reach.kind == "melee"


def _quarry_hit_me_in_melee(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.target == me
        and p is not None
        and p.reach.kind == "melee"
        and world.relations.holds(Relation.QUARRY_OF, me, ev.attacker)
    )


def _thrown_shot(c: Cast, ref: str) -> bool:
    """Was that ranged power a thrown weapon's rather than a bow's?

    `thrown_by_hand` is the header field for a row printed "Ranged
    weapon" that a *melee* weapon is hurled with, and fifteen rows carry
    it. It is not the whole sentence: an ordinary ranged basic attack
    thrown from the hand carries no such flag, and the only thing that
    separates a javelin from an arrow there is what is being held -- no
    ranged weapon, and a melee one the table calls thrown.
    """
    p = get(ref)
    if p is None or not p.provokes_on():
        return False
    if p.thrown_by_hand:
        return True
    gear = c.world.get(c.me, Gear)
    if gear is None or gear.ranged is not None:
        return False
    return any(prop.endswith("thrown") for w in gear.melee for prop in w.properties)


def _martial_encounter(ref: str) -> bool:
    p = get(ref)
    return (
        p is not None
        and Keyword.MARTIAL in p.keywords
        and p.usage is ENCOUNTER
    )


def _my_ranger_attack(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.actor == me
        and p is not None
        and p.cls == "ranger"
        and p.attack is not None
    )


def _i_stood(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.target == me
        and ev.condition is Condition.PRONE
        and ev.why == "stood up"
    )


def _shift_beside(c: Cast, squares_: int, foe: int) -> bool:
    """Shift, but only into a square next to that enemy.

    `c.shift` with no `to=` hands the decider every reachable square,
    which for a row that says "to a square adjacent to the enemy" is a
    different power. Filtering first and naming the square is the
    printed instruction.
    """
    theirs = squares(c.world, foe)
    mine = squares(c.world, c.me)
    options = [
        sq for sq in c.world.reachable_squares(c.me, squares_)
        if sq not in mine and between({sq}, theirs) <= 1
    ]
    return bool(options) and c.shift(to=options[0])


# -- the quarry half, and the board ----------------------------------------


@power("f2390", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a ranger attack power",
       on=Trigger(PowerUsed, _my_ranger_attack, "you use a ranger power"))
def f2390(c: Cast) -> None:
    """"When you move as part of using a ranger attack power".

    `PowerUsed` is announced above the body, so the waiver is standing
    by the time the row's own movement happens -- which is the only
    reason this is sayable. It is held to the end of the turn rather
    than to the end of the move, because nothing marks where a power's
    movement stops; that costs the ranger rough ground it walked over
    later in the same turn, and no more.
    """
    c.ignores_difficult(on=c.me, until=When.EOT)


@power("f2391", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you stand up",
       on=Trigger(ConditionEnded, _i_stood, "you stand up"))
def f2391(c: Cast) -> None:
    """Standing is an action in the menu and it announces itself: the
    prone effect ends with `why="stood up"`, which separates getting up
    on purpose from an effect simply expiring."""
    c.shift(1)


@power("f2406", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make a melee attack",
       on=Trigger(AttackDeclared, _my_melee_attack, "you attack in melee"))
def f2406(c: Cast) -> None:
    """Thrown shots stop provoking once you have swung in melee.

    `c.no_provoke` was the wrong tool and the narrowing it could not
    make was dropped: it exempts the caster from one creature or from
    everybody and carries no gate on what the shot was made with. The
    window it cancels is public -- `_survive_provoking` opens one per
    adjacent enemy with `why` naming the ranged row -- so the veto is
    written out here with the gate the card prints.

    Declared on `AttackDeclared` rather than on a hit: the card says
    "whenever you make a melee attack", which a miss is.
    """
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        ref = ev.why.removesuffix(" is a ranged power")
        if ev.provoker == me and ref != ev.why and _thrown_shot(c, ref):
            ev.cancel(c.ref)

    c.watch(OpportunityWindow, veto, on=me, until=When.SONT,
            window=Window.BEFORE, label=f"{c.ref} thrown")


@power("f2439", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2439(c: Cast) -> None:
    """Melee feeds ranged and ranged feeds melee, against the one enemy.

    A trait with a watch rather than a declared trigger, because the row
    answers every hit for the rest of the fight and a declared trigger
    would fire the whole body once per event. The damage context carries
    `power`, so "the next *ranged* attack" is asked of that row's range
    line. `once=True`: it is the next attack, not every attack.

    Untiered, so the +4 and +6 rungs are out of scope; the heroic number
    is the whole of it here.
    """
    me = c.me

    def paid(ev: Any) -> None:
        if ev.attacker != me:
            return
        p = get(ev.power)
        if p is None:
            return
        want = "melee" if p.reach.kind == "ranged" else "ranged"
        foe = ev.target
        c.bonus(
            "damage", 2, on=me, until=When.EONT, once=True,
            when=lambda ctx: (
                ctx.get("target") == foe
                and (q := get(ctx.get("power", ""))) is not None
                and q.reach.kind == want
            ),
        )

    c.watch(Hit, paid, on=me, until=When.ENCOUNTER)


# -- the style feats, now that the associated lists resolve ----------------


@power("f2708", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy misses you, or you use an associated power",
       on=(Trigger(Miss, lambda w, me, ev: (
               ev.target == me
               and (p := get(ev.power)) is not None and p.reach.kind == "melee"
           ), "an enemy misses you in melee"),
           Trigger(PowerUsed, used_one_of("p4404", "p1521"),
                   "you use an associated power")))
def f2708(c: Cast) -> None:
    """Two printed clauses on two events, and the same shift either way
    -- one is worth a square and the other two, so the body has to know
    which fired. "Before your attack" is sayable because `PowerUsed` is
    announced above the body.

    The high crit narrowing was dropped on the claim that no weapon
    carries the property. Six heavy blades do -- it is a `Weapon`
    property like "versatile", loaded from the table -- so the row asks
    for the group *and* the property, as printed.
    """
    if not _holding(c, "heavy blade", prop="high crit"):
        return
    c.shift(1 if isinstance(c.trigger, Miss) else 2)


@power("f2712", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a one-handed axe")
def f2712(c: Cast) -> None:
    """Prone on a crit, a swing at it when it gets back up, and Strength in
    place of Dexterity on two rows.

    The stand half was once dropped as `c.provokes_on_stand()` by the
    fighter's f1322, and it need not be: the stand action ends the prone
    effect with `why="stood up"`, so `ConditionEnded` is the trigger and
    `c.provoke` is the window. `once=True` is "the first time".

    **The declared trigger became a watch** so that the standing swap has
    somewhere to be laid -- a body gated on `on=Trigger(...)` runs only when
    the trigger fires, and a swap that arrives after the first critical is
    every roll too late. See `ranger_b.f1309`, which is the same rewrite.

    This one goes the other way round from its siblings: **Strength in place
    of Dexterity**, because a ranger's own line is Dexterity and the axe is
    the Strength weapon.
    """
    for ref in ("p1419", "p4389"):
        c.rolls_with(ref, Ability.STR, when=_wielding("axe", hands=1))

    def crit(ev: Any) -> None:
        if not _i_crit(c.world, c.me, ev) or not _grip(c, "axe", hands=1):
            return
        _knock_down(c, ev.target)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=c.me)


def _knock_down(c: Cast, foe: int) -> None:
    """`f2712`'s payout: prone, and an opportunity attack on standing up."""
    me = c.me
    c.prone(on=foe)

    def stood(ev: Any) -> None:
        if (
            ev.target == foe
            and ev.condition is Condition.PRONE
            and ev.why == "stood up"
        ):
            c.provoke(me, on=foe, why=c.ref)

    c.watch(ConditionEnded, stood, on=foe, until=When.EONT, once=True)


@power("f2803", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you hit an enemy",
       on=Trigger(Hit, _i_hit, "you hit"))
def f2803(c: Cast) -> None:
    """Both clauses close the distance, and both name where the shift
    ends, so `_shift_beside` picks the square rather than the decider.
    One trigger with two branches: a row declared `on=` lays no standing
    modifiers, and neither half of this is one."""
    if not _holding(c, "scimitar"):
        return
    ev = c.trigger
    if ev.power in ("p10625", "p4385"):
        _shift_beside(c, 3, ev.target)
    elif _martial_encounter(ev.power):
        _shift_beside(c, 1, ev.target)
        c.push(1, on=ev.target)


# -- the rest, each gap named -----------------------------------------------


@power("f2398", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2398(c: Cast) -> None:
    """The racial attack bonus, raised against the quarry.

    The trait the card names has a row -- `rt:r8-bloodied-enemies`,
    which lays +1 `kind="racial"` gated on the target being bloodied.
    Two bonuses of one kind do not add and the larger wins, so
    "increases to +2" is a second racial bonus of 2 and not a second +1.

    Gated on bloodied as well as on the quarry, because the bonus this
    raises exists nowhere else: a quarry that is not bloodied never had
    the +1 for the card to increase.
    """
    me = c.me
    c.bonus(
        "attack", 2, kind="racial", on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            (foe := ctx.get("target")) is not None
            and c.bloodied(foe)
            and c.is_quarry(foe)
        ),
    )


@power("f2415", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=SELF,
       trigger="your quarry hits you with a melee attack",
       on=Trigger(Hit, _quarry_hit_me_in_melee,
                  "your quarry hits you in melee"))
def f2415(c: Cast) -> None:
    """The racial power, spent off the quarry's blow.

    `x_m5139a3` is an extractor token and matches no ref, which is what
    the old marker named. The race's own line is "p6188: you have the
    x_m5139a3 power", so p6188 *is* that power, it is written, and
    `c.use_power` uses it here at this row's action cost.

    At-will, because the limit the card prints is p6188's own encounter
    use and `c.use_power` spends it. An interrupt on `Hit` still pays:
    `Hit` is announced before the damage is rolled.
    """
    c.use_power("p6188")


@power("f2417", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("movement.step(per_square=True)",))
def f2417(c: Cast) -> None:
    """No opportunity attack for circling an enemy you are already
    beside -- which every creature on the board already has.

    `movement.step` opens the window only when the mover leaves the
    watcher's *reach*, never when it merely leaves a threatened square:
    `left` is computed against the destination, so a step from one
    square adjacent to an enemy to another provokes nothing from that
    enemy for anybody. `risk_along` and `_provokes_step` make the same
    test, so the interface and the pathfinder agree with it.

    Writing the row would grant a permission already held. The marker
    names the rule whose absence makes the feat free, the way f2462
    names the restriction it lifts, so the day the engine counts
    squares this is the row that exempts the ranger.
    """


@power("f2419", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss your quarry with a charge",
       on=Trigger(Miss, _missed_my_quarry_charging,
                  "you miss your quarry with a charge"))
def f2419(c: Cast) -> None:
    """A reroll of a missed charge against the quarry.

    The price is charged now: `c.expend_row("p6189")` spends the racial
    power without casting it, and returns False when there is none
    left, which is what stops the row rerolling every missed charge.
    The `ENCOUNTER` that stood in for that cap is gone -- the cap is
    p6189's own use, where the card puts it.

    The reroll mutates the live `AttackResult` and `resolve.attack`
    judges the defence again once the window closes, so `result.hit` is
    read back rather than `c.landed`, which is this row's own attack and
    there is not one.
    """
    if not c.expend_row("p6189"):
        return
    result = getattr(c.trigger, "result", None)
    if result is None or not c.reroll_attack():
        return
    if result.hit:
        c.damage(c.w(), on=c.trigger.target)


@power("f2428", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FORGO)
def f2428(c: Cast) -> None:
    """Trades one die of the class's extra damage for a slow.

    The payout is announced, which the old marker denied: `cf:ranger-f1`
    pays through `c.damage(..., detail="cf:ranger-f1")`, `DamageRolled`
    carries that detail, and it is a `Decision` whose `amount` a
    listener may write. What cannot be said is the price. The event
    holds one number with the rider's own modifier, the enhancement and
    every "damage" bonus already folded into it, so there is no die in
    it to take out and `c.quarry_damage()` only says what was rolled,
    not what it came up.
    """


@power("f2467", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FORGO)
def f2467(c: Cast) -> None:
    """The same trade as f2428, bought for a push instead of a slow."""


@power("f2462", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.quarry(nearest=False)",))
def f2462(c: Cast) -> None:
    """Lets the second-nearest enemy be named quarry.

    `c.quarry` takes whoever it is handed and `cf:ranger-f1` takes
    its target like any other row, so the restriction this feat lifts is
    not enforced anywhere -- writing the row would be granting a
    permission already held. Marked rather than left out, because the
    day the restriction arrives this is the row that relaxes it. The
    warlock's `c.curse(nearest=False)` is the same shape.
    """


@power("f2469", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_shift()",))
def f2469(c: Cast) -> None:
    """Two extra squares on a shift a martial encounter or daily power
    grants. Nothing adds to the distance somebody else's row moves you,
    and the shift is inside that row's body. `f2361` waits on the
    same."""


@power("f2473", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.low_light()",))
def f2473(c: Cast) -> None:
    """Low-light vision, and the whole benefit is that. There are no
    light levels, so there is nothing for the sight to see through --
    the same gap `skills.py` named from its other side."""


# -- the beast companion ----------------------------------------------------
#
# Eight of these are one card printed eight times, once per beast
# category, and they differ only in the last sentence. `_leash` is the
# first two sentences and the rider is the third.

#: The longer leash: "while your beast companion acts independently it
#: need not move adjacent to you but must remain within 10 squares".
#: There is no independent mode and no leash to lengthen -- the beast
#: takes no turn of its own -- so the sentence has nowhere to land.
LEASH = ("c.leash()",)


def _by_the_beast(c: Cast, ev: Any, *, charge: bool) -> int | None:
    """Was that hit the beast's own, of the kind this card names?

    `bmba` is the beast's printed melee basic attack and `mba` is the
    engine's, which a companion built without a block still uses -- both
    are melee basic attacks and the sentence means either.
    """
    from combat_engine.engine.basic import BEAST as BEAST_MBA
    from combat_engine.engine.basic import MELEE

    pet = c.beast()
    if pet is None or ev.attacker != pet:
        return None
    if charge:
        return pet if getattr(ev, "charge", False) else None
    return pet if ev.power in (BEAST_MBA, MELEE) else None


def _leash(ref: str, what: str, rider: Any, *, charge: bool = False) -> None:
    """Saves, the leash that cannot be said, and one rider on its attack."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, dropped=LEASH)
    def feat(c: Cast) -> None:
        pet = c.beast()
        if pet is None:
            return
        # Untyped: the card prints no word in front of "bonus".
        c.bonus("save", 2, on=pet, until=When.ENCOUNTER)
        busy = []

        def landed(ev: Hit) -> None:
            beast = _by_the_beast(c, ev, charge=charge)
            # A rider that swings again would see its own hit and swing
            # again forever; one of these grants an extra attack.
            if beast is None or busy:
                return
            busy.append(ev)
            try:
                rider(c, beast, ev.target)
            finally:
                busy.clear()

        c.watch(Hit, landed, on=c.me, until=When.ENCOUNTER)

    feat.__name__ = ref
    feat.__doc__ = (
        f"{what}\n\n    The leash is dropped: the beast takes no turn, so "
        "there is no\n    independent mode for the sentence to lengthen."
    )


def _immobilise(c: Cast, pet: int, foe: int) -> None:
    c.immobilized(on=foe, until=When.EOTNT)


def _shove(c: Cast, pet: int, foe: int) -> None:
    """Away from *the beast*, which is what the anchor argument is for."""
    at = next(iter(sorted(squares(c.world, pet))), None)
    c.push(2, on=foe, anchor=at)


def _expose(c: Cast, pet: int, foe: int) -> None:
    """"Grants combat advantage" names nobody, so it is everyone."""
    c.grants_advantage(on=foe, until=When.EONT, to="team")


def _seize(c: Cast, pet: int, foe: int) -> None:
    c.grab(on=foe, by=pet)


def _again(c: Cast, pet: int, foe: int) -> None:
    c.basic(who=pet, on=foe)


def _floor(c: Cast, pet: int, foe: int) -> None:
    c.prone(on=foe)


def _toll(c: Cast, pet: int, foe: int) -> None:
    """Five damage for walking off, measured against where it started.

    `Moved` is the only one of the three movement events that carries
    `from_`, which is what "moves away from" needs: the question is
    whether the step widened the gap, not whether it moved at all.
    """
    def gap(square: Any) -> int:
        here = next(iter(sorted(squares(c.world, pet))), None)
        if here is None or square is None:
            return 0
        return max(abs(here[0] - square[0]), abs(here[1] - square[1]))

    def walked(ev: Moved) -> None:
        if ev.actor == foe and gap(ev.to) > gap(ev.from_):
            c.flat(5, on=foe)

    c.watch(Moved, walked, on=foe, until=When.EOTNT, once=True)


def _stagger(c: Cast, pet: int, foe: int) -> None:
    c.slowed(on=foe, until=When.EOTNT)
    # "Its next attack roll", so the penalty is spent by one swing.
    c.penalty("attack", 2, on=foe, until=When.EOTNT, once=True)


_leash("f2402", "The beast pins what it hits.", _immobilise)
_leash("f2422", "The beast's charge shoves what it hits away from it.",
       _shove, charge=True)
_leash("f2425", "What the beast hits is open to everybody.", _expose)
_leash("f2447", "The beast holds on to what it hits.", _seize)
_leash("f2453", "The beast's charge swings a second time.", _again, charge=True)
_leash("f2461", "The beast puts what it hits on the ground.", _floor)
_leash("f2465", "What the beast hits pays for walking away from it.", _toll)
_leash("f2474", "What the beast hits is slowed and swings wide.", _stagger)


@power("f2464", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2464(c: Cast) -> None:
    """`p2483` and `p2484` are declared, so "also benefits from" has a
    pair of holds behind it. Restated rather than borrowed, for the
    reason `ranger_b.f1381` gives: `c.as_though_hit_by` runs the copied
    body with its own caster as the subject and would never reach the
    beast. Same card from the other page."""
    def share(ev: Any) -> None:
        pet = c.beast()
        if pet is None:
            return
        if ev.power == "p2483":
            c.bonus("damage", 2, on=pet, until=When.ENCOUNTER)
            c.regeneration(2, until=When.ENCOUNTER, on=pet, while_bloodied=True)
        elif ev.power == "p2484":
            c.bonus("speed", 2, on=pet, until=When.ENCOUNTER)
            c.bonus(AC, 1, on=pet, until=When.ENCOUNTER)
            c.bonus(REF, 1, on=pet, until=When.ENCOUNTER)

    c.watch(PowerUsed, share, on=c.me, until=When.ENCOUNTER,
            label=f"{c.ref} share")


@power("f2967", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2967(c: Cast) -> None:
    """The beast's critical hits carry the *ranger's* enhancement.

    Rolled with `c.flat(c.roll(...))` rather than handed to `c.damage`,
    because `c.damage` maxes its dice on a critical and this is the one
    place a critical is already true -- the extra dice are rolled, as
    every "per plus" rider is.
    """
    def crit(ev: Hit) -> None:
        pet = c.beast()
        plus = c.enhancement
        if pet is None or ev.attacker != pet or not ev.critical or plus < 1:
            return
        c.flat(c.roll(f"{plus}d6"), on=ev.target)

    c.watch(Hit, crit, on=c.me, until=When.ENCOUNTER)


@power("f2970", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2970(c: Cast) -> None:
    """The beast is patched up whenever its ranger is.

    `SurgeSpent` is emitted from every site that decrements a surge, so
    this sees a second wind and a leader's heal alike -- which is what
    "whenever you spend a healing surge" says. The skill training is a
    skill and belongs to no fight.
    """
    def spent(ev: SurgeSpent) -> None:
        pet = c.beast()
        if ev.actor != c.me or pet is None or not c.adjacent_to(pet, c.me):
            return
        c.heal(max(1, c.surge_value() // 2), on=pet)

    c.watch(SurgeSpent, spent, on=c.me, until=When.ENCOUNTER)
