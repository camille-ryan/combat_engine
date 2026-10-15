"""Monster abilities for the stat blocks printed inside an item's own entry.

Eleven blocks, twenty-six rows. These are not encounter monsters: each card
sits in the middle of an item's page, and the thing the item does is put the
creature on the board. The ETL pass that made them importable landed today,
so every ref here had a `monster` row in `game.db` and no content row at all
-- which `loader.spawn` turns into a creature with an empty `Powers.known`,
drawable and unable to attack. #601.

Conventions, inherited from the level sweeps:

* numbers -- hp, AC, the three other defences, speed, the movement modes --
  load from `game.db` and are never hand-written. What is transcribed is the
  ability's own attack line, `Attack(vs=AC, printed=N)` exactly as printed,
  with the engine taking the level term back out per `world.scaling`; and
  the damage line, which goes in the header as data so MM3 rescaling has
  something to rescale;
* a card printing no range at all is melee 1;
* a close burst whose card names no target set takes **enemies**;
* a **trait** costs no action and has no target whatever the compendium's
  action column claims. The six entries headed with the word for riding are
  traits for exactly that reason -- each prints a standing benefit and the
  parser sectioned it `standard`;
* "while mounted by a friendly rider of Nth level or higher" is asked
  **live**, never through `requires=`: a rider mounts and falls off
  mid-fight, and `requires=` on a trait is read once at the moment it arms
  and then never again (`docs/AUTHORING.md`'s warning about traits). So the
  benefits that ride on the rider are laid and lifted off `RelationSet` /
  `RelationCleared` -- see `_on_the_rider`.

Two of these cards print paragon rider levels on heroic mounts (9th and
10th level riders on level-1 blocks), which is a fact about the item they
belong to rather than an error.

One ruling, `m1179c0a1`. It imports as `+9 vs ; 1d10+4 damage..` -- a blank
attack defence and a doubled full stop -- followed by the sentence that is
the actual ability. The main session read the page: the ability is a shift,
the block's own melee attack, and another shift, and the `+9 vs ;` fragment
is **import junk rather than a second attack line**. Blank attack defences
run 5-11x the corpus rate in the magazine imports (#360), so a garbled card
from one is a bad import before it is a misreading. The row is written as
the three steps and carries no `defect=`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Movement,
    Relation,
    Size,
    Stats,
    When,
    World,
    power,
)
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.events import (
    DamageRolled,
    Dropped,
    Miss,
    MoveEnd,
    RelationCleared,
    RelationSet,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import adjacent, alive, creatures
from combat_engine.engine.triggers import Trigger, about_me

#: The four defences, for the cards that print "all defenses".
ALL_FOUR = (AC, FORT, REF, WILL)

#: "Medium size or smaller", which two of these cards narrow an effect to.
NO_BIGGER_THAN_MEDIUM = (Size.TINY, Size.SMALL, Size.MEDIUM)


def _on_the_rider(
    c: Cast,
    need: int,
    lay: Callable[[int], Sequence[Effect | None]],
) -> None:
    """Hold a standing benefit on whoever is in the saddle, while they are in it.

    The printed Requirement -- "a friendly rider of Nth level or higher" --
    is asked of whoever mounts rather than once when the trait arms, which
    is the whole reason this is a watch pair and not four lines in the body.
    A trait arms at the start of the fight; a rider that climbs on in round
    three would otherwise get nothing for the rest of the encounter, and a
    `requires=` would have refused the trait outright and never armed it
    again at all.

    `lay` is handed the rider and returns whatever it laid, so the benefit
    comes off again on dismount. Whoever is already up when the trait arms
    is caught at the end: the relation is routinely set while the board is
    being laid out, before any row runs.

    The level is read off `Stats`, which is where a creature's level lives
    -- `Ident` carries the ref and the role and no number.
    """
    me = c.me
    held: dict[int, list[Effect]] = {}

    def up(who: int) -> None:
        stats = c.world.get(who, Stats)
        if who in held or who not in c.allies():
            return
        if stats is None or stats.level < need:
            return
        held[who] = [eff for eff in lay(who) if eff is not None]

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == me:
            up(ev.target)

    def dismounted(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.RIDDEN_BY or ev.source != me:
            return
        for eff in held.pop(ev.target, []):
            c.world.effects.end(eff, "dismounted")

    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=me, label=f"{c.ref} on")
    c.watch(
        RelationCleared, dismounted, until=When.ENCOUNTER, on=me, label=f"{c.ref} off"
    )
    rider = c.rider()
    if rider is not None:
        up(rider)


def _ranged_or_area(ctx: dict[str, Any]) -> bool:
    """"Against all ranged and area attacks", which is two questions.

    `ctx["ranged"]` is `resolve._is_ranged`, and that answers for the
    *ranged* range line and nothing else -- an area burst reads False there,
    because the key exists to decide which attacks take cover from a body.
    So the area half is read off the attacking row's own range line instead.
    """
    if ctx.get("ranged"):
        return True
    row = REGISTRY.get(str(ctx.get("power") or ""))
    return row is not None and row.reach.kind in ("area_burst", "wall")


def _no_swim_speed(c: Cast, who: int) -> bool:
    """"A creature without a swim speed" -- a movement mode, not a keyword.

    `aquatic_edge` a level below asks `c.is_kind("aquatic")`, which is the
    creature's own type line; these two cards narrow by what it can *do*,
    and a creature can have the one without the other.
    """
    moves = c.world.get(who, Movement)
    return not (moves is not None and moves.modes.get("swim"))


def _in_the_water(c: Cast, who: int) -> Effect | None:
    """"While in water, a +2 bonus to attack rolls against creatures without
    a swim speed."

    `c.terrain` is asked inside the gate rather than once when the trait
    arms: it answers False in an ordinary fight, which is the whole reason
    the question is written out. Untyped -- a stat block prints a bare "+2
    bonus", and a racial bonus is a player-race idea that does not appear in
    one.
    """

    def against_a_walker(ctx: dict[str, Any]) -> bool:
        # `.get`, not `[...]`: not every context asking about an attack
        # bonus carries a target.
        victim = ctx.get("target")
        return (
            c.terrain("aquatic") and victim is not None and _no_swim_speed(c, victim)
        )

    return c.bonus("attack", 2, until=When.ENCOUNTER, on=who, when=against_a_walker)


# ==========================================================================
# m1171c0
# ==========================================================================


@power(
    "m1171c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m1171c0a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means."""
    if c.strike():
        c.hit()


@power(
    "m1171c0a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="it must be mounted by a friendly rider of 9th level or higher",
)
def m1171c0a1(c: Cast) -> None:
    """A rider's bonus to every defence, and only while the block is airborne.

    Untyped: the card prints a bare "+1 bonus to all defenses". "While
    flying" is asked two ways because neither is the whole of it --
    `c.moving_as` is true during the flight and `c.height` is true of a
    creature that has gone up and stopped -- and it is asked inside the
    gate, so a landing takes the bonus away without the effect ending.
    """
    me = c.me

    def airborne(ctx: dict[str, Any]) -> bool:
        return c.moving_as("fly", on=me) or c.height(on=me) > 0

    _on_the_rider(
        c,
        9,
        lambda who: [
            c.bonus(d, 1, on=who, until=When.ENCOUNTER, when=airborne) for d in ALL_FOUR
        ],
    )


# ==========================================================================
# m1179c0
# ==========================================================================


@power(
    "m1179c0a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 4),
)
def m1179c0a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m1179c0a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1179c0a1(c: Cast) -> None:
    """A shift, the block's own melee attack, and a shift out again.

    The imported text opens with `+9 vs ; 1d10+4 damage..` -- a blank
    defence and a doubled stop -- and the main session read the page: that
    fragment is import junk, not a second attack line, so there is no
    `defect=` here and no attack in the header. Blank attack defences run
    5-11x the corpus rate in the magazine imports (#360), which is what
    makes the junk reading the likely one.

    The row declares no target of its own: `m1179c0a0` picks its own, which
    is what it would do on an ordinary turn, and it has to be picked
    **after** the first shift rather than before it. The first shift is
    aimed at the nearest enemy for the reason `c.overrun` documents -- with
    no decider installed a bare shift takes the lowest-sorted square, which
    walks away from everybody and leaves nothing in reach to swing at. The
    second names no direction, because the card does not.
    """
    foes = [f for f in c.enemies() if alive(c.world, f)]
    if foes:
        c.shift(1, toward=min(foes, key=lambda f: (c.distance(f), f)))
    c.use_power("m1179c0a0")
    c.shift(1)


# ==========================================================================
# m1663c0
# ==========================================================================


@power(
    "m1663c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 6),
)
def m1663c0a0(c: Cast) -> None:
    """"Reach 2" is the range line, so it is `Melee(2)` rather than a clause."""
    if c.strike():
        c.hit()


@power(
    "m1663c0a1",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m1663c0a1(c: Cast) -> None:
    """The card names no target set for the burst, which means enemies.

    The size narrowing is asked of each one as the burst resolves, not of
    the row: `Target` filters on side, count and size, and a creature too
    big to go down still takes the damage.
    """
    if c.strike():
        c.hit()
        if c.size_of(c.target) in NO_BIGGER_THAN_MEDIUM:
            c.prone()


# ==========================================================================
# m1664c0
# ==========================================================================


@power(
    "m1664c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6, dtype=DamageType.POISON),
)
def m1664c0a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1664c0a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="it must be mounted by a friendly rider of 10th level or higher",
)
def m1664c0a1(c: Cast) -> None:
    """Swimming away from somebody gives them no opening.

    Narrowed twice, because `c.no_provoke` with no gate shuts every window
    this creature opens -- a wider rule than the card prints. The gate reads
    `ctx["mode"]`, the mode of the step that opened the window, and
    `ctx["why"]`, which is `"moved away"` for a window a move opened and
    something else for one a ranged attack opened.

    **The riders' half needs nothing and is not missing.** `movement.walk`
    carries a passenger to the mount's new square *quietly* and says so in
    its own comment -- "being carried past somebody provokes nothing" -- so
    the engine already gives every rider the immunity this card narrows to
    swimming. There is nothing to lay on them and no clause to drop.
    """
    me = c.me

    def swimming_away(ctx: dict[str, Any]) -> bool:
        return ctx.get("mode") == "swim" and ctx.get("why") == "moved away"

    _on_the_rider(
        c,
        10,
        lambda _who: [
            c.no_provoke(on=me, until=When.ENCOUNTER, when=swimming_away)
        ],
    )


# ==========================================================================
# m1804c0
# ==========================================================================


@power(
    "m1804c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 7),
)
def m1804c0a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1804c0a1",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.overrun(during_charge=)",),
)
def m1804c0a1(c: Cast) -> None:
    """A charge's own movement is a straight run at the target, and nothing
    in `Cast` lets a trait swap a walk *through* an occupied square in for
    it: `c.overrun` is a move a body makes for itself, and a charge's walk
    is `actions.execute`'s. `c.rider()` and the level gate would be
    trivial; there is nothing for them to arm. Same gap as `m1460a1` and
    `m1064a2`, and the same symbol.
    """


# ==========================================================================
# m1925c0
# ==========================================================================


@power(
    "m1925c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m1925c0a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1925c0a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="it must be mounted by a friendly rider of 5th level or higher",
)
def m1925c0a1(c: Cast) -> None:
    """The bonus is the rider's, so it rides on the rider and comes off when
    they dismount. Untyped: the card prints a bare "+5 bonus". Gated on
    `ctx["charge"]`, which the damage context carries -- `resolve.deal_damage`
    sets it beside `opportunity`.
    """
    _on_the_rider(
        c,
        5,
        lambda who: [
            c.bonus(
                "damage",
                5,
                on=who,
                until=When.ENCOUNTER,
                when=lambda ctx: bool(ctx.get("charge")),
            )
        ],
    )


# ==========================================================================
# m1932c0
# ==========================================================================


@power(
    "m1932c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m1932c0a0(c: Cast) -> None:
    """The block's only ability, and the whole of it."""
    if c.strike():
        c.hit()


# ==========================================================================
# m1933c0
# ==========================================================================


@power(
    "m1933c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 4),
)
def m1933c0a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1933c0a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="it must be mounted by a friendly rider of 6th level or higher",
)
def m1933c0a1(c: Cast) -> None:
    """Both halves: the concealment, and the sidestep when a blow misses.

    `c.conceal` rather than four bonuses to defences, because concealment
    and cover do not add -- `resolve.attack` takes the larger -- and a row
    that hand-rolled the defences would stack with cover where the printed
    rule says it must not. The narrowing is in the gate; see
    `_ranged_or_area` for why `ctx["ranged"]` alone is not it.

    The shift goes to the mount whichever of the two was missed, which is
    what the card says, and it is held by the same hold as the concealment
    so a dismount takes both away.
    """
    me = c.me

    def lay(who: int) -> list[Effect | None]:
        def sidestep(ev: Miss) -> None:
            if ev.target in (me, who):
                c.shift(1)

        return [
            c.conceal(on=me, until=When.ENCOUNTER, when=_ranged_or_area),
            c.conceal(on=who, until=When.ENCOUNTER, when=_ranged_or_area),
            c.watch(Miss, sidestep, until=When.ENCOUNTER, on=me, label=c.ref),
        ]

    _on_the_rider(c, 6, lay)


@power(
    "m1933c0a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ride(size=)",),
)
def m1933c0a2(c: Cast) -> None:
    """The card waives a restriction this engine does not impose. `c.ride`
    sets `Relation.RIDDEN_BY` for anybody who asks and reads no footprint at
    all -- there is no size rule anywhere in `movement`, `actions` or
    `relations` -- so the exception has nothing to except and a row written
    as a no-op would read as finished. The marker is the size gate on
    riding, which is what has to exist before the waiver means anything.
    """


# ==========================================================================
# m2022c0
# ==========================================================================


@power(
    "m2022c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m2022c0a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2022c0a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="it must be mounted by a friendly rider of 9th level or higher",
)
def m2022c0a1(c: Cast) -> None:
    """Two clauses, both the rider's.

    The extra die is "when he or she attacks **after** this block charges",
    which is the mount's run and not the rider's -- so it is read off
    `MoveEnd.kind_`, the only place that says what a walk was. `actions`
    walks a charge with `kind="charge"`, and the rider's own `charge` key
    would have answered for the wrong creature entirely. Two watches rather
    than a gated damage bonus, because the window the card opens is "the
    next blow after the run" and a modifier cannot spend itself.

    The water clause is the same sentence `m2022c0a2` prints about itself,
    laid on the rider instead.
    """
    me = c.me

    def lay(who: int) -> list[Effect | None]:
        ran: list[int] = []

        def charged(ev: MoveEnd) -> None:
            if ev.actor == me and ev.kind_ == "charge":
                ran.append(ev.seq)

        def spur(ev: DamageRolled) -> None:
            if ran and ev.source == who:
                ran.clear()
                ev.amount += c.roll("1d10")

        return [
            c.watch(MoveEnd, charged, until=When.ENCOUNTER, on=me, label=c.ref),
            c.watch(
                DamageRolled, spur, until=When.ENCOUNTER, on=me, label=f"{c.ref} spur"
            ),
            _in_the_water(c, who),
        ]

    _on_the_rider(c, 9, lay)


@power(
    "m2022c0a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2022c0a2(c: Cast) -> None:
    """Standing, and about the block itself, so no rider is asked for -- the
    compendium sectioned it `standard` and it is a trait like the rest."""
    _in_the_water(c, c.me)


# ==========================================================================
# m3111c0
# ==========================================================================


@power(
    "m3111c0a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4),
)
def m3111c0a0(c: Cast) -> None:
    """A flat 4 with no dice, which is what the card prints.

    **Not `kind=MINION`**, even though the block has 1 hit point: the role
    column is empty, and `kind` is what MM3 rescaling divides by, so
    claiming it would halve a number nobody printed as a minion's.
    """
    if c.strike():
        c.hit()


# ==========================================================================
# m3263c0
# ==========================================================================


def _beside_a_creature(world: World, eid: int) -> bool:
    """The printed Requirement. A module-level gate, because `requires=` is
    handed `(world, eid)` and no `Cast` -- and safe on this row, which is a
    move action asked at the moment it is taken rather than a trait armed
    once at the start of the fight.
    """
    return any(
        other != eid and alive(world, other) and adjacent(world, eid, other)
        for other in creatures(world)
    )


@power(
    "m3263c0a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage(bonus=9, dtype=DamageType.NECROTIC, kind=MINION),
)
def m3263c0a0(c: Cast) -> None:
    """A minion's fixed damage, declared as data so MM3 scales it as one."""
    if c.strike():
        c.hit()


@power(
    "m3263c0a1",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    requires=_beside_a_creature,
    requires_text="it must be adjacent to a creature",
)
def m3263c0a1(c: Cast) -> None:
    """A blink to somebody else's elbow.

    `toward=` rather than a square: it names the creature to arrive beside
    and lets `_nearest_first` pick the square, which is the printed line.
    Handed no square and no `toward` the decider takes the lowest-sorted
    candidate on the board, which is the trap `c.overrun` documents.

    Prefers a creature it is **not** already next to -- blinking to where it
    already stands is a legal reading of the card and a wasted move action
    -- and an enemy over an ally, since the card is a move into contact.
    """
    reachable = [o for o in c.within(6, side="any") if o != c.me]
    pool = [o for o in reachable if not c.adjacent(o)] or reachable
    if not pool:
        return
    foes = set(c.enemies())
    c.teleport(6, toward=min(pool, key=lambda o: (o not in foes, c.distance(o), o)))


@power(
    "m3263c0a2",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    damage=Damage(bonus=9, dtype=DamageType.NECROTIC, kind=MINION),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m3263c0a2(c: Cast) -> None:
    """No attack roll, so the damage is the header's and `c.hit` applies it
    to each creature the burst caught.

    `EACH_OTHER` rather than `EACH_CREATURE`: the burst is centred on a
    creature that has already dropped, and the printed line is "each
    creature adjacent to it". "Is destroyed" needs nothing -- the hit points
    are gone by the time `Dropped` announces it, which is also why this
    declares on that event and does not try to `c.cancel` anything.
    """
    c.hit()
