"""Monster abilities, level 13: the rest of the brutes.

`brutes.py` holds the seven stat blocks whose rows were already written; this
is the remaining nineteen, in ref order. A stat block's numbers load from
`game.db` and the attack and damage lines go in the header exactly as printed
-- `Attack(vs=AC, printed=18)`, `Damage("2d12", 13)` -- so the engine can take
the level back out and rescale. A minion's flat number says `kind=MINION`, a
limited-use line says `kind=LIMITED`.

The conventions of the twelve levels below are kept: a row filed under an
action heading that is plainly a **trait** is declared `ActionType.NONE` and
armed once when the fight starts; a stat block printing no range at all means
melee 1; a printed "10/20" takes the short range; and a helper written for an
earlier level is imported rather than copied.

Nine things this file had to settle.

**"Creatures in the burst" from a close area is `EACH_OTHER`, not
`EACH_CREATURE`.** The second is side "any" and catches the creature standing
at the centre, so every close burst and close blast here is declared
`EACH_OTHER` and only `m5741a4`, which is an *area* burst thrown up to twenty
squares away, is `EACH_CREATURE`.

**A printed "Recharge if the power misses" is a sentence on top of the die the
database files**, and the two only ever agree to hand the row back sooner.
`m1576a2` watches its own `Miss`; `m5684a2` has to count across the whole use
("misses **every** target") and so restores the row itself rather than through
a watch.

**"The target is knocked unconscious instead of slowed" is an `escalate`, and
it does not rewrite the live effect's conditions.** That tuple is read once on
the way in and once on the way out and never in between, so a rewrite would
strand the slow and never land the rest. `m1576a2` ends the first hold and
applies a second.

**"Until it escapes the grab" is not a duration.** `RelationCleared` carrying
`Relation.GRABBED_BY` is the one event that says a grab let go, so
`m2645a1`, `m5139a2` and `m6665a2` all run their holds to the end of the
encounter and take them off there. `Escaped` is the other half and says
whether an attempt succeeded, which is what "a creature that escapes shifts"
reads.

**A count that moves with the board is five gated untyped bonuses.**
`m5118a1` prints "+1 for each bloodied enemy within 10 squares (maximum +5)";
one `c.bonus` carries a fixed number, and untyped bonuses add, so the printed
line is five +1s each gated on there being that many.

**A recurring burn clocked on the *attacker's* turn is not `c.ongoing`.**
`m2529a0` and `m6665a2` both print damage at the start of the grabber's turn
with no saving throw against it; a save-ends burn ticks on the sufferer's turn
and a save ends it, which is a different card.

**A trample is `c.overrun` and nothing else** -- `c.move` refuses an occupied
square and reports nothing about what it crossed. On a huge or gargantuan
creature the generated boards can leave nobody beneath it, so `m5741a5` and
`m6665a3` can fire and report nothing; that is the board and not the row.

**Two rows' whole content is a creature the spec gives no ref for.**
`m6185a6` creates spawn of three kinds and `m6185a8` is three uses of it, so
both carry `etl.monster.summon_ref()`. `m5821a2` forbids attacking three
creatures the card names in prose and that have no ref either, which is
`spec.monster_ref()`.

**None of these rows spends a healing surge.** Each carries two at this tier
for a leader line to spend and none of them prints one, so none is spent and
none takes a second wind.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_04.brutes import _change_shape
from combat_engine.content.monsters.level_07.brutes import _aura
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_13.soldiers import _burn_and_hold
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Dropped,
    Effect,
    Escaped,
    Event,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    MoveEnd,
    Position,
    Powers,
    PowerUsed,
    Ranged,
    Relation,
    RelationCleared,
    Size,
    Square,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    World,
    ZoneEntered,
    ZoneExited,
    power,
    use,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, squares, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_melee,
    by_ranged,
    either,
    targets_me,
)

#: The five types `m5118a5` and `m5139a4` both answer.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _bloodied_gate(world: World, eid: int) -> bool:
    """A printed "must be bloodied" Requirement, as a header gate.

    Safe as a `requires=` on a chooseable row, unlike one on a trait: the row
    is offered or refused afresh every turn, and nothing arms it once.
    """
    health = world.get(eid, Health)
    return bool(health and health.bloodied)


def _elemental(world: World, me: int, ev: Event) -> bool:
    """One of the five types `m5118a5` and `m5139a4` print, landing on me."""
    return getattr(ev, "target", None) == me and any(
        kind in _ELEMENTS for kind in ev.types()
    )


def _elemental_guard(c: Cast, amount: int) -> None:
    """"Gains resist N to the triggering damage type ... or until it uses this
    again."

    The second clause is why the standing hold has to be found and ended: the
    row has two uses an encounter and the first resistance is replaced rather
    than added to. `c.resist` labels its hold `"<ref> resist"`, which is what
    makes it findable without keeping state between uses.

    The resistance is laid after the packet that triggered it has already come
    off, which is what the printed line says -- it is bought against the
    *next* one.
    """
    kinds = [kind for kind in c.trigger.types() if kind in _ELEMENTS]
    if not kinds:
        return
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == f"{c.ref} resist":
            c.world.effects.end(eff, "it used the row again")
    c.resist(amount, kinds[0], on=c.me, until=When.ENCOUNTER)


def _square_beside(c: Cast, foe: int, within: int) -> Square | None:
    """A free square next to that creature, close enough to step to.

    "Shifts to a square adjacent to the target" names a destination the
    engine's own chooser cannot be asked for -- `c.shift` picks through the
    world's decider, and `to=` is the only way to say where. Candidates are
    the ring around the creature's footprint, unoccupied, and inside the
    printed distance.
    """
    pos = c.world.get(foe, Position)
    if pos is None:
        return None
    here = c.here
    theirs = set(pos.squares)
    ring: set[Square] = set()
    for square in theirs:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                ring.add((square[0] + dx, square[1] + dy))
    free = [
        square
        for square in sorted(ring - theirs)
        if not c.in_squares({square})
        and max(abs(square[0] - here[0]), abs(square[1] - here[1])) <= within
    ]
    return free[0] if free else None


# ==========================================================================
# m1576
# ==========================================================================


@power(
    "m1576a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.insubstantial(except_=)",),
)
def m1576a0(c: Cast) -> None:
    """Half damage from everything is insubstantiality, and the printed
    exception is what the condition cannot carry: `Condition.INSUBSTANTIAL`
    exempts force only when the attacker's own row grants it, where this card
    exempts it outright.

    The suspension is exact and is the half worth having -- an acid, fire or
    radiant packet takes the hold off and the start of the next turn puts it
    back.
    """
    me, ref = c.me, c.ref
    burns = (DamageType.ACID, DamageType.FIRE, DamageType.RADIANT)
    shape: dict[str, Effect | None] = {
        "eff": c.insubstantial(on=me, until=When.ENCOUNTER)
    }

    def hurt(ev: DamageApplied) -> None:
        if ev.target != me or shape["eff"] is None:
            return
        if not any(kind in burns for kind in ev.types()):
            return
        c.world.effects.end(shape["eff"], ref)
        shape["eff"] = None

    def back(ev: TurnStart) -> None:
        if ev.actor == me and shape["eff"] is None:
            shape["eff"] = c.insubstantial(on=me, until=When.ENCOUNTER)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=f"{ref} off")
    c.watch(TurnStart, back, until=When.ENCOUNTER, on=me, label=f"{ref} on")


@power(
    "m1576a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d10", 10),
)
def m1576a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1576a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=Target("enemy", 1, label="one bloodied creature", bloodied=True),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("5d6", 12, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1576a2(c: Cast) -> None:
    """The first failed save ends the slow and applies the heavier hold; it does
    **not** edit the live effect's conditions, which are read once on the way
    in and once on the way out and never between, so a rewrite there would
    strand the slow and never land the rest. "If the target takes damage, the
    effect also ends" is a watch on that second hold.
    """
    me, ref = c.me, c.ref
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == ref)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()

    def out(eff: Effect) -> None:
        c.world.effects.end(eff, "the first save failed")
        hold = c.unconscious(until=When.SAVE_ENDS, on=victim)

        def woken(ev: DamageApplied) -> None:
            if ev.target == victim and hold is not None:
                c.world.effects.end(hold, "the target took damage")

        c.watch(
            DamageApplied, woken, until=When.SAVE_ENDS, on=victim, label=f"{ref} wakes"
        )

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=out)


# ==========================================================================
# m1598
# ==========================================================================


@power(
    "m1598a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 6),
)
def m1598a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m1598a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m1598a1(c: Cast) -> None:
    """"Escape ends" needs nothing said: a grab is cleared by an escape and by
    nothing else, so the printed duration is already what the engine does."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1598a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d10", 6, kind=LIMITED),
)
def m1598a2(c: Cast) -> None:
    """A row whose printed Effect *is* the charge. `charges=True` is what makes
    the reach be measured after the run; without it the row is refused whenever
    the target is further off than a sword, which is every situation a charge
    is for. `c.run_at` rather than `c.charge_at(c.ref)`, which would spend this
    very row again to make the swing.

    The rough ground is waived for this turn only, which is as long as the
    printed clause lasts.
    """
    if c.first:
        c.as_basic(c.ref, window="charge", until=When.ENCOUNTER)
    victim = c.target
    if victim is None:
        return
    c.ignores_difficult(on=c.me, until=When.EOT)
    if not c.adjacent(victim):
        c.run_at(victim)
    if c.strike():
        c.hit()


# ==========================================================================
# m1959
# ==========================================================================


@power(
    "m1959a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d8", 8, dtype=DamageType.NECROTIC),
)
def m1959a0(c: Cast) -> None:
    """The burn is save-ends and the fall is not, so they are two calls rather
    than one hold carrying both."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.NECROTIC)
        c.prone()


@power(
    "m1959a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8, dtype=DamageType.NECROTIC),
)
def m1959a1(c: Cast) -> None:
    """Two swings at one creature or at two; the card does not say, so a single
    target is struck twice -- the reading that loses nothing, and the only one
    the "if both attacks hit the same target" follow-up can happen under."""
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, victim):
            break
        if c.strike(on=victim):
            c.hit(on=victim)
            landed += 1
    if landed == 2 and alive(c.world, victim):
        use(c.world, c.me, "m1959a0", targets=[victim], spend=False)


_M1959_FELLED = "the m1959 reduces a creature to 0 hit points or fewer"


@power(
    "m1959a2",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    trigger=_M1959_FELLED,
    on=Trigger(Dropped, by_me, _M1959_FELLED),
)
def m1959a2(c: Cast) -> None:
    """"Targets the triggering creature", so the victim comes off the trigger
    and never from the chooser -- `Dropped` names the creature that fell in
    `actor` and whoever felled it in `source`, which is what `by_me` reads.

    No damage on the hit line at all, so nothing is dealt and the header
    declares none: the lost surge and the 79 hit points are the whole of it.
    """
    victim = getattr(c.trigger, "actor", None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.spend_surge(on=victim)
        c.heal(79, on=c.me)


@power(
    "m1959a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1959a3(c: Cast) -> None:
    """Filed under a standard action on the stat block and plainly a trait.

    Both halves hang on the m1959 itself: `crit_range` is read off the
    attacker, and the extra dice are *gated* on the victim rather than held on
    it, because the damage context carries `target`. The dice go in `dice=`
    rather than as a flat value, so they are rolled afresh on every blow.
    """
    me = c.me
    c.bonus("crit_range", 2, on=me, until=When.ENCOUNTER)

    def flattened(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.is_(Condition.PRONE, on=who)

    c.bonus("damage", 0, dice="2d8", on=me, until=When.ENCOUNTER, when=flattened)


# ==========================================================================
# m2073
# ==========================================================================


@power(
    "m2073a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 6),
)
def m2073a0(c: Cast) -> None:
    """"Large size or smaller" is a size comparison on the *victim*, which is
    `Size.order` -- the footprint is a property of the category and not its
    value, so the ordering is the only thing that compares."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.size_of(on=victim).order <= Size.LARGE.order:
        c.prone()


@power(
    "m2073a1",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=Target(
        "enemy", 1,
        label="prone targets only",
        conditions=frozenset({Condition.PRONE}),
    ),
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("3d8", 6),
)
def m2073a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()


@power(
    "m2073a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m2073a2(c: Cast) -> None:
    """Two of the row above it, at one creature or at two; the card does not
    say which, so a single target takes both."""
    victim = c.target
    if victim is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, victim):
            return
        use(c.world, c.me, "m2073a0", targets=[victim], spend=False)


@power(
    "m2073a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d10", 6, dtype=DamageType.POISON, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
)
def m2073a3(c: Cast) -> None:
    """One blow of two types, which the header cannot say: `Damage` takes a
    single `dtype`, so the poison half is declared and the necrotic half is
    the dropped clause. The burn beside it has the same shape and is carried
    on the same symbol.

    "Save ends both" is one hold carrying the burn and the condition together,
    which is what `_burn_and_hold` is for -- it also keeps the printed
    highest-only rule for ongoing damage of a type already standing.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _burn_and_hold(
        c, victim, 10, DamageType.POISON, conditions=(Condition.WEAKENED,)
    )


# ==========================================================================
# m2298
# ==========================================================================


@power(
    "m2298a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 1),
)
def m2298a0(c: Cast) -> None:
    """The splash catches both sides -- "each creature adjacent to the target"
    names no side -- and leaves the m2298 out, which is the reading every row
    of this shape takes: a brute does not sting itself for reaching."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.ongoing(10, DamageType.NECROTIC)
    for who in sorted(c.within(1, of=victim)):
        if who not in (victim, c.me) and alive(c.world, who):
            c.flat(5, dtype=DamageType.NECROTIC, on=who)


_M2298_HIT = "it is hit by a melee or a ranged attack"


@power(
    "m2298a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
    trigger=_M2298_HIT,
    on=Trigger(Hit, both(targets_me, either(by_melee, by_ranged)), _M2298_HIT),
)
def m2298a1(c: Cast) -> None:
    """`Hit` carries `attacker` and `target` and no `actor`, so the predicate
    is `targets_me` and not `about_me`; the reach half of the printed line is
    `by_melee` or `by_ranged`, both of which read the row behind the event."""
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m2298a2",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m2298a2(c: Cast) -> None:
    """A hazard rather than a plain zone: the printed line hurts whoever enters
    it or starts a turn inside, which is what `c.hazard` already is, and the
    number is flat rather than a die.

    "The zone moves with the m2298" is a step-by-step follow on `Moved`, which
    is the only event that reports one step with **both ends** of it -- and both
    ends are what is needed. `c.move_zone(to=)` is measured from
    `min(zone.squares)`, the corner and not the centre, so handing it the
    creature's own square slides the burst off by its own radius; the delta
    between where the step started and where it ended is the only thing that
    keeps a burst centred. A zone cannot be moved nought squares either --
    `move_zone` refuses `squares_ <= 0` outright, which made the first spelling
    of this a follow that silently never moved.

    The printed duration is a pair of readings rather than a `When`: the hit
    points at the end of one turn are remembered and compared at the start of
    the next, and the mist goes when nothing has come off between the two.
    """
    from combat_engine.engine.zones import Zone

    me, ref = c.me, c.ref
    mist = c.hazard(
        c.area(),
        10,
        DamageType.NECROTIC,
        label=ref,
        until=When.ENCOUNTER,
        sustain=None,
    )
    seen: dict[str, int] = {}

    def follow(ev: Moved) -> None:
        if ev.actor != me:
            return
        zone = c.world.get(mist, Zone)
        if zone is None or not zone.squares:
            return
        dx, dy = ev.to[0] - ev.from_[0], ev.to[1] - ev.from_[1]
        step = max(abs(dx), abs(dy))
        if not step:
            return
        corner = min(zone.squares)
        c.move_zone(mist, step, to=(corner[0] + dx, corner[1] + dy))

    def mark(ev: TurnEnd) -> None:
        health = c.world.get(me, Health)
        if ev.actor == me and health is not None:
            seen["hp"] = health.hp

    def fade(ev: TurnStart) -> None:
        health = c.world.get(me, Health)
        if ev.actor != me or health is None or "hp" not in seen:
            return
        if health.hp >= seen["hp"]:
            c.dispel(mist)

    c.watch(Moved, follow, until=When.ENCOUNTER, on=me, label=f"{ref} drifts")
    c.watch(TurnEnd, mark, until=When.ENCOUNTER, on=me, label=f"{ref} marks")
    c.watch(TurnStart, fade, until=When.ENCOUNTER, on=me, label=f"{ref} fades")


# ==========================================================================
# m2529. A minion: its flat damage says `kind=MINION` because the creature is
# one, and its single hit point is in the database like every other number.
# ==========================================================================


@power(
    "m2529a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=8, dtype=DamageType.ACID, kind=MINION),
)
def m2529a0(c: Cast) -> None:
    """The recurring burn is clocked on the m2529's own turns, which
    `c.ongoing` cannot be: a save-ends burn ticks at the end of the sufferer's
    turn and a saving throw ends it, where this one is ended only by the grab
    being broken. So it is a watch, armed once however many creatures the
    m2529 takes hold of.
    """
    me, ref = c.me, c.ref
    if not c.strike():
        return
    c.hit()
    c.grab()

    def squeeze(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for held in sorted(c.grabbing(of=me)):
            c.flat(8, dtype=DamageType.ACID, on=held)

    label = f"{ref} burn"
    if not any(eff.label == label for eff in c.world.effects.of(me)):
        c.watch(TurnStart, squeeze, until=When.ENCOUNTER, on=me, label=label)


@power(
    "m2529a1",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(2),
    target=Target(
        side="enemy", count=1,
        label="a creature it is grabbing",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=15),
    damage=Damage(bonus=5, kind=MINION),
)
def m2529a1(c: Cast) -> None:
    """Hit and miss both let go, so the release is unconditional and only the
    throw hangs on the roll.

    `c.cure` and not `c.end_effect(carrying=Condition.GRABBED)`: a grab is held
    as a *relation* and the condition is only mirrored into the count, so the
    hold that carries it lists no conditions at all and `carrying=` never
    matches it. Driven on a board, that spelling left the creature grabbed.
    """
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()
    c.cure(Condition.GRABBED)


# ==========================================================================
# m2645
# ==========================================================================


@power(
    "m2645a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 5),
)
def m2645a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m2645a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("enemy", 2, max_size=Size.MEDIUM),
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=14),
)
def m2645a1(c: Cast) -> None:
    """No damage on the hit line -- the burn is the whole of it -- so the
    header declares none and the body never calls `c.hit`.

    "Automatically hits an immobilized creature" is asked *before* the roll
    rather than answered after it: `c.autohit` is for an attack being
    interrupted and there is no attack here until this row makes one.

    "Until it escapes the grab" is not a duration, so the hold runs to the end
    of the encounter and comes off from `RelationCleared`, the one event that
    says a grab let go. The step out is the printed line's other half and is
    read off `Escaped`, which reports failures too.

    "Can move normally while creatures are engulfed within it" needs nothing
    said -- a grabber's own movement is not restricted by the engine -- and
    `c.shares_space` is what lets the victim be pulled into the square at all.
    """
    me, ref = c.me, c.ref
    if c.first:
        c.shares_space(on=me, until=When.ENCOUNTER)
    victim = c.target
    if victim is None:
        return
    if not (c.is_(Condition.IMMOBILIZED, on=victim) or c.strike(on=victim)):
        return
    c.grab(on=victim)
    c.pull(c.distance(victim), on=victim, to=c.here)
    hold = c.condition(
        Condition.DAZED,
        until=When.ENCOUNTER,
        on=victim,
        ongoing=(15, DamageType.ACID),
    )

    def let_go(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.target != victim:
            return
        if hold is not None:
            c.world.effects.end(hold, "the grab ended")

    def out(ev: Escaped) -> None:
        if ev.holder == me and ev.actor == victim and ev.success:
            c.shift(1, who=victim)

    c.watch(RelationCleared, let_go, until=When.ENCOUNTER, on=me, label=f"{ref} holds")
    c.watch(Escaped, out, until=When.ENCOUNTER, on=me, label=f"{ref} out")


@power(
    "m2645a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2645a2(c: Cast) -> None:
    """Filed under a standard action on the stat block and plainly a trait.

    "Invisible until seen (Perception DC 29)" is per creature, so the hold is
    laid once for each enemy whose passive Perception does not reach the
    printed DC -- `c.invisible(to=)` is exactly that sentence, and anyone who
    does notice never had it. Passive rather than a rolled check because
    nothing on a board rolls one unbidden and the DC needs something to beat.

    "Creatures that fail to notice might walk into it" is the second half: the
    space is opened so a creature can end a move in it at all, and ending a
    move there unaware is the engulfing attack.
    """
    me, ref = c.me, c.ref
    c.shares_space(on=me, until=When.ENCOUNTER)
    unseen: list[Effect] = []
    for foe in sorted(c.enemies()):
        if c.passive("perception", of=foe) < 29:
            eff = c.invisible(to=foe, on=me, until=When.ENCOUNTER)
            if eff is not None:
                unseen.append(eff)

    def shows(ev: AttackDeclared) -> None:
        if ev.attacker != me:
            return
        for eff in list(unseen):
            c.world.effects.end(eff, "it attacked")
        unseen.clear()
        c.unhide()

    def walked_in(ev: MoveEnd) -> None:
        if ev.actor == me or ev.at not in squares(c.world, me):
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if c.passive("perception", of=ev.actor) < 29:
            use(c.world, me, "m2645a1", targets=[ev.actor], spend=False)

    c.watch(AttackDeclared, shows, until=When.ENCOUNTER, on=me, label=f"{ref} shows")
    c.watch(MoveEnd, walked_in, until=When.ENCOUNTER, on=me, label=f"{ref} swallows")


# ==========================================================================
# m3621
# ==========================================================================


@power(
    "m3621a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 3),
)
def m3621a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3621a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 7),
)
def m3621a1(c: Cast) -> None:
    """A printed "10/20" takes the short range, which is what the creature can
    actually throw without a penalty the engine does not model."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3621a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=UpTo(2),
)
def m3621a2(c: Cast) -> None:
    """"Two basic attacks" is `c.basic`, which is whichever row the board says
    this creature's basic attack actually is. At one creature or at two; the
    card does not say which, so a single target takes both."""
    victim = c.target
    if victim is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, victim):
            return
        c.basic(on=victim)


@power(
    "m3621a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=UpTo(3),
    requires=_bloodied_gate,
    requires_text="the m3621 must be bloodied",
)
def m3621a3(c: Cast) -> None:
    """Three swings spread over whoever was handed over, no creature taking
    more than two of them -- which is the one clause here the chooser cannot
    express, so the spread is done on the first call for the whole use."""
    if not c.first:
        return
    pool = [foe for foe in c.targets if alive(c.world, foe)]
    if not pool:
        return
    taken: dict[int, int] = {}
    for n in range(3):
        turn = n % len(pool)
        order = pool[turn:] + pool[:turn]
        victim = next(
            (
                foe
                for foe in order
                if taken.get(foe, 0) < 2 and alive(c.world, foe)
            ),
            None,
        )
        if victim is None:
            return
        taken[victim] = taken.get(victim, 0) + 1
        use(c.world, c.me, "m3621a0", targets=[victim], spend=False)


@power(
    "m3621a4",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m3621a4(c: Cast) -> None:
    """The row it uses carries its own "must be bloodied" Requirement, which is
    true by the time this trigger has fired."""
    c.use_power("m3621a3")
    c.move(c.speed_of())


_M3621_HURT = "it is damaged by an attack"


@power(
    "m3621a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3621_HURT,
    on=Trigger(DamageApplied, targets_me, _M3621_HURT),
)
def m3621a5(c: Cast) -> None:
    """"By an attack" is asked in the body rather than in the predicate.
    `DamageApplied` carries no `from_attack`; what it does carry is `detail`,
    which is the ref of the row that dealt the blow where one did and a short
    note ("ongoing", "coup de grace") where none did -- so a packet with a row
    behind it is the nearest reading of the printed sentence, and ongoing
    damage does not set the reaction off.
    """
    ev = c.trigger
    who = getattr(ev, "source", None)
    if who is None or who == c.me or not getattr(ev, "detail", ""):
        return
    if team(c.world, who) is team(c.world, c.me) or not alive(c.world, who):
        return
    c.charge_at(who)


@power(
    "m3621a6",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 3, kind=LIMITED),
)
def m3621a6(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10)


@power(
    "m3621a7",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m3621a7(c: Cast) -> None:
    """The charge is the printed Effect and belongs after every target has been
    resolved, so it is made on the last call and reads the board rather than a
    list kept between calls.

    The printed "recharges when first bloodied" is the sentence on top of the
    die the database files, and the two only agree to hand the row back sooner.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.prone()
    if not c.last:
        return
    down = [
        foe
        for foe in c.targets
        if alive(c.world, foe) and c.is_(Condition.PRONE, on=foe)
    ]
    if down:
        c.charge_at(down[0])


# ==========================================================================
# m4168. A minion.
# ==========================================================================


@power(
    "m4168a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=13, dtype=DamageType.ACID, kind=MINION),
)
def m4168a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5118
# ==========================================================================


@power(
    "m5118a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5118a0(c: Cast) -> None:
    """"Whenever one of its attacks bloodies an enemy" is a crossing, and
    `Bloodied` is emitted after the packet and names only the creature that
    bled -- nothing on it says whose blow did it. So the rider rides the
    damage: `ev.hp` is what is left, `ev.amount` is what came off, and the two
    added are what the creature had a moment ago.

    The cap is read rather than counted. `c.action_points` is what the creature
    could spend right now, which is the printed "only 1 at a time".
    """
    me, ref = c.me, c.ref

    def drew_blood(ev: DamageApplied) -> None:
        if ev.source != me or ev.amount <= 0 or ev.hp <= 0:
            return
        if team(c.world, ev.target) is team(c.world, me):
            return
        health = c.world.get(ev.target, Health)
        if health is None or not health.bloodied:
            return
        if ev.hp + ev.amount > health.max_hp // 2 and c.action_points(of=me) < 1:
            c.grant_action_point(1, on=me)

    c.watch(DamageApplied, drew_blood, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5118a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5118a1(c: Cast) -> None:
    """A count that moves with the board, which one `c.bonus` cannot carry: the
    value is fixed when the modifier is laid and the printed number changes
    every time somebody bleeds.

    Five untyped +1s, each gated on there being at least that many bloodied
    enemies within ten squares. Untyped bonuses add -- two of a *type* do not,
    the larger wins -- which is what makes the printed maximum of +5 come out
    right rather than +1 forever.
    """
    me = c.me

    def at_least(n: int) -> Any:
        def gate(ctx: dict[str, Any]) -> bool:
            return (
                sum(
                    1
                    for foe in c.within(10, of=me, side="enemy")
                    if c.bloodied(on=foe)
                )
                >= n
            )

        return gate

    for n in range(1, 6):
        c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=at_least(n))


@power(
    "m5118a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5118a2(c: Cast) -> None:
    """The halved speed, the -5 to attacks and the combat advantage handed out
    are the *whole* of what `Condition.SQUEEZING` is, and this card waives all
    three -- so the hold is taken off as it lands rather than three
    counterweights being written against it."""
    _squeezes_freely(c)


@power(
    "m5118a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m5118a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5118a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 10, kind=LIMITED),
)
def m5118a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)


_M5118_HURT = "it takes acid, cold, fire, lightning or thunder damage"


@power(
    "m5118a5",
    level=13,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5118_HURT,
    on=Trigger(DamageApplied, _elemental, _M5118_HURT),
)
def m5118a5(c: Cast) -> None:
    """"2/Encounter" is `uses=2` on an encounter row, not a second usage word.

    The resistance replaces whatever this row laid last time rather than
    adding to it, which is the printed "or until it uses this again".
    """
    _elemental_guard(c, 15)


# ==========================================================================
# m5139
# ==========================================================================


@power(
    "m5139a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 7),
)
def m5139a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5139a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m5139a1(c: Cast) -> None:
    """The slide comes before the fall, because the printed clause that follows
    asks where the target *ended* the movement.

    The Secondary Attack has no ref of its own to live in, so its printed
    total goes through `_secondary`, which takes the level back out the same
    way `Attack(printed=)` does. Its targets are the primary target's own
    allies, which on a board is whoever shares its team.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.slide(2, on=victim)
    c.prone(on=victim)
    mates = sorted(
        who
        for who in c.within(1, of=victim)
        if who not in (victim, c.me)
        and alive(c.world, who)
        and team(c.world, who) is team(c.world, victim)
    )
    for mate in mates:
        if _secondary(c, 16, FORT, mate):
            c.damage("1d10", on=mate)
            c.prone(on=mate)


def _not_grabbing(world: World, eid: int) -> bool:
    """The printed "must not have a creature grabbed" Requirement."""
    return not world.relations.targets(Relation.GRABBED_BY, eid)


@power(
    "m5139a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 10, kind=LIMITED),
    requires=_not_grabbing,
    requires_text="the m5139 must not have a creature grabbed",
)
def m5139a2(c: Cast) -> None:
    """The Aftereffect fires when the grab ends however it ends, so it hangs on
    `RelationCleared` rather than on `Escaped`: the second says somebody tried,
    the first says the hold is gone.

    The restraint runs to the end of the encounter and is taken off there too
    -- "while the m5139 has the target grabbed" is not a `When`.
    """
    me, ref = c.me, c.ref
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab(on=victim)
    hold = c.condition(Condition.RESTRAINED, until=When.ENCOUNTER, on=victim)

    def let_go(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.target != victim:
            return
        if ev.source != me:
            return
        if hold is not None:
            c.world.effects.end(hold, "the grab ended")
        c.prone(on=victim)
        c.flat(10, on=victim)

    c.watch(RelationCleared, let_go, until=When.ENCOUNTER, on=me, label=f"{ref} after")


@power(
    "m5139a3",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m5139a3(c: Cast) -> None:
    c.temp_hp(40, on=c.me)


_M5139_HURT = "it takes acid, cold, fire, lightning or thunder damage"


@power(
    "m5139a4",
    level=13,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5139_HURT,
    on=Trigger(DamageApplied, _elemental, _M5139_HURT),
)
def m5139a4(c: Cast) -> None:
    """The same shape as `m5118a5` at a smaller number."""
    _elemental_guard(c, 10)


# ==========================================================================
# m5684
# ==========================================================================


@power(
    "m5684a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5684a0(c: Cast) -> None:
    """`crit_range` is read off the attacker at the moment of the roll, which
    is what lets the printed condition be a gate rather than a hold that has
    to be laid and lifted every time the temporary hit points come and go."""
    me = c.me

    def shielded(ctx: dict[str, Any]) -> bool:
        health = c.world.get(me, Health)
        return bool(health and health.temp > 0)

    c.bonus("crit_range", 2, on=me, until=When.ENCOUNTER, when=shielded)


@power(
    "m5684a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d12", 13),
)
def m5684a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5684a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d12", 13, kind=LIMITED),
)
def m5684a2(c: Cast) -> None:
    """Every swing is made on the first call, because both printed clauses are
    about the use as a whole: "hits two or more targets" and "misses every
    target" cannot be counted one target at a time.

    The recharge is done here rather than through a watch for the same reason
    -- a `Miss` watch would hand the row back on the first miss, where the card
    asks for all of them.
    """
    if not c.first:
        return
    landed = 0
    for victim in c.targets:
        if not alive(c.world, victim):
            continue
        if c.strike(on=victim):
            c.hit(on=victim)
            landed += 1
    if landed >= 2:
        c.temp_hp(20, on=c.me)
    if landed == 0:
        known = c.world.get(c.me, Powers)
        if known is not None:
            known.restore(c.ref)


_M5684_BLED = "an enemy bloodies it"


@power(
    "m5684a3",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5684_BLED,
    on=Trigger(Bloodied, about_me, _M5684_BLED),
)
def m5684a3(c: Cast) -> None:
    """`Bloodied` carries `source`, so "an **enemy** bloodies it" is askable at
    all: the predicate says it was this creature that bled and the body says
    who did it.

    "To a square adjacent to the triggering enemy" names a destination the
    engine's chooser cannot be asked for, so the square is worked out and
    handed to `c.shift(to=)`. The +2 is a hold laid for the one swing and taken
    off again, because the printed bonus belongs to this use and no other.
    """
    me = c.me
    foe = getattr(c.trigger, "source", None)
    if foe is None or foe == me or team(c.world, foe) is team(c.world, me):
        return
    step = c.speed_of() + 2
    where = _square_beside(c, foe, step)
    if where is not None:
        c.shift(step, to=where)
    elif not c.adjacent(foe):
        c.run_at(foe)
    known = c.world.get(me, Powers)
    if known is not None:
        known.restore("m5684a2")
    aim = c.bonus("attack", 2, on=me, until=When.EOT)
    c.use_power("m5684a2")
    if aim is not None:
        c.world.effects.end(aim, "the swing is made")


# ==========================================================================
# m5741
# ==========================================================================


@power(
    "m5741a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5741a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m5741a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.cannot_attack(opportunity=)",),
)
def m5741a1(c: Cast) -> None:
    """Three of the four printed clauses land. "It cannot grab creatures" is
    the fourth and needs nothing: nothing on this stat block grabs, so the
    prohibition is already true of the engine.

    Not being able to make opportunity attacks is the dropped clause --
    `c.cannot_attack` bars a creature from attacking altogether or from
    attacking one creature, and has no way to bar one *kind* of attack.
    """
    me = c.me
    c.ignores_difficult(on=me, until=When.ENCOUNTER)
    c.no_provoke(on=me, until=When.ENCOUNTER)
    c.immune(Condition.SQUEEZING, on=me, until=When.ENCOUNTER)


@power(
    "m5741a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.in_vehicle()",),
    narrative=("skill:athletics",),
)
def m5741a2(c: Cast) -> None:
    """The one clause with a lever is the shared space, and it goes both ways
    exactly as `c.shares_space` does.

    The interior is the dropped half: two floors, a pair of doors that cut
    line of sight, ladders between them, and occupants who ride the thing as
    it moves. Nothing in the engine puts a creature *inside* another one, so
    there is no place for any of it to hang, and two rows below wait on the
    same thing.

    The climb is the narrative half. "Athletics DC 20 to climb it" is a check
    nothing on a board ever calls for -- the height is scenery, not a position
    the grid can hold -- so the DC narrows a circumstance that has no combat
    meaning rather than naming a gap anybody should close.
    """
    c.shares_space(on=c.me, until=When.ENCOUNTER)


@power(
    "m5741a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.in_vehicle()",),
)
def m5741a3(c: Cast) -> None:
    """The slow lands; the penalty on whoever is inside waits on the same thing
    `m5741a2` does.

    Armed as a watch *and* asked once on the spot, because a trait is armed at
    the start of the fight and the creature may already be bloodied when it
    gets there -- a watch alone would miss the crossing that had already
    happened.
    """
    me, ref = c.me, c.ref

    def slow() -> None:
        if not any(
            eff.label == f"{ref} slow" for eff in c.world.effects.of(me)
        ):
            c.effect(f"{ref} slow", on=me, until=When.ENCOUNTER)
            c.slowed(on=me, until=When.ENCOUNTER)

    def bled(ev: Bloodied) -> None:
        if ev.actor == me:
            slow()

    health = c.world.get(me, Health)
    if health is not None and health.bloodied:
        slow()
    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5741a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d12", 7, dtype=DamageType.FIRE, half_on_miss=True),
)
def m5741a4(c: Cast) -> None:
    """An *area* burst thrown up to twenty squares off, so `EACH_CREATURE` is
    right here where it would be wrong on a close area: the printed line
    catches both sides and the creature making it is never standing in its own
    blast.

    `half_on_miss=True` is declared data and no line of the engine reads it, so
    the Miss branch is written out.
    """
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE)
    else:
        c.hit(half=True)


@power(
    "m5741a5",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    once_per_round=True,
    reach=Melee(0),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d12", 6),
)
def m5741a5(c: Cast) -> None:
    """A trample. `c.overrun` is the only way to walk through an occupied
    square and say who was under it -- `c.move` refuses the square and reports
    nothing about what it passed.

    "Nonflying" is read off how far off the ground the creature is, and the
    fall happens whether the blow lands or not, which is what both printed
    lines say. "For the first time during this movement" is the set, so a
    creature crossed twice is only struck once.

    On a huge creature the generated boards can leave nobody beneath it, in
    which case the row fires and reports nothing; that is the board.
    """
    seen: set[int] = set()
    for victim in c.overrun():
        if victim in seen or not alive(c.world, victim) or c.height(on=victim) > 0:
            continue
        seen.add(victim)
        if c.strike(on=victim):
            c.hit(on=victim)
        c.prone(on=victim)


_M5741_FELLED = "it drops to 0 hit points"


@power(
    "m5741a6",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("4d10", 17, kind=LIMITED, half_on_miss=True),
    trigger=_M5741_FELLED,
    on=Trigger(Dropped, about_me, _M5741_FELLED),
    dropped=("c.in_vehicle()",),
)
def m5741a6(c: Cast) -> None:
    """A creature may answer its own downfall -- the dispatcher makes the
    exception for exactly this shape. Declared `FREE` because the printed line
    is "No Action", which is nearer a free action than any immediate one.

    The rubble is laid once for the whole use, off the squares the creature
    itself stood in. Whoever was inside falling prone waits on the same thing
    `m5741a2` does; everything else here plays.
    """
    if c.first:
        c.zone(squares(c.world, c.me), label=c.ref, until=When.ENCOUNTER, difficult=True)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    c.prone()


# ==========================================================================
# m5821
# ==========================================================================


@power(
    "m5821a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5821a0(c: Cast) -> None:
    """Getting up a day later is finished and deliberately inert: a fight is
    over long before, and `c.reanimate` is the *other* sentence -- a corpse
    back on the board inside this encounter, which this card does not say."""


@power(
    "m5821a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5821a1(c: Cast) -> None:
    """The same clock on somebody else's corpse, and inert for the same
    reason."""


@power(
    "m5821a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.monster_ref()",),
)
def m5821a2(c: Cast) -> None:
    """The whole of this row is a prohibition against attacking three
    creatures the card names in prose and gives no ref for. `c.cannot_attack`
    is the verb and it wants an entity; there is nothing on any board for it to
    point at, so the row has nothing it can do."""


@power(
    "m5821a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m5821a3(c: Cast) -> None:
    """It shoves and follows. The step names a destination rather than a
    distance, so the square is worked out and handed to `c.shift(to=)` -- a
    bare `c.shift(3)` goes wherever the world's decider likes, which is the
    one place the printed line does not allow."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.push(3, on=victim)
    where = _square_beside(c, victim, 3)
    if where is not None:
        c.shift(3, to=where)


@power(
    "m5821a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d10", 10, kind=LIMITED),
)
def m5821a4(c: Cast) -> None:
    """The heavier version of the row above, and the printed "Recharge when
    first bloodied" is the sentence on top of the die the database files."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.push(3, on=victim)
    c.prone(on=victim)
    where = _square_beside(c, victim, 3)
    if where is not None:
        c.shift(3, to=where)


# ==========================================================================
# m6139
# ==========================================================================


@power(
    "m6139a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6139a0(c: Cast) -> None:
    """The trait is what makes the melee row below legal for a creature holding
    the ranged one's weapon, and `c.as_basic` is the engine's word for "you can
    use this in place of a melee basic attack" -- which is what the printed
    sentence comes to."""
    c.as_basic("m6139a2", on=c.me, until=When.ENCOUNTER)


@power(
    "m6139a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6139a1(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m6139a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 10),
)
def m6139a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m6139a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d8", 8),
    dropped=("etl.monster.ability_text()",),
)
def m6139a3(c: Cast) -> None:
    """The attack plays in full. The printed Effect arrived as four words with
    no verb and no object -- it names the melee row and stops -- so there is no
    sentence to implement, and the gap is in the extracted text rather than in
    anything the engine is missing."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6139a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m6139a4(c: Cast) -> None:
    """Two of the melee row, at one creature or at two; the card does not say
    which, so a single target takes both."""
    victim = c.target
    if victim is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, victim):
            return
        use(c.world, c.me, "m6139a2", targets=[victim], spend=False)


_M6139_WIN = "it or an ally within 10 squares bloodies an enemy or drops one"


def _by_my_side(world: World, me: int, ev: Event) -> bool:
    """Whoever caused this is me or an ally of mine within ten squares, and the
    creature it happened to is not on my side.

    `Bloodied` and `Dropped` both carry `source`, which is what makes "it **or
    an ally** bloodies an enemy" declarable rather than routed off a damage
    packet with the threshold worked out again by hand.
    """
    from combat_engine.engine.query import distance_between

    who = getattr(ev, "source", None)
    actor = getattr(ev, "actor", None)
    if who is None or actor is None:
        return False
    mine = team(world, me)
    if team(world, who) is not mine or team(world, actor) is mine:
        return False
    return who == me or distance_between(world, me, who) <= 10


@power(
    "m6139a5",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    trigger=_M6139_WIN,
    on=(
        Trigger(Bloodied, _by_my_side, _M6139_WIN),
        Trigger(Dropped, _by_my_side, _M6139_WIN),
    ),
)
def m6139a5(c: Cast) -> None:
    """Two printed triggers, so two declared ones -- bloodying and dropping are
    different events and declaring half of it would look finished.

    "The triggering creature" is the one that *did* it, which is `source`, and
    is why the row is `NO_TARGET`: the chooser would hand over an enemy.
    """
    who = getattr(c.trigger, "source", None)
    if who is None or not alive(c.world, who):
        return
    c.bonus("damage", 5, on=who, until=When.ENCOUNTER, once=True)


# ==========================================================================
# m6146. The three forms this stat block gates its rows on arrived from the
# extractor as refs -- its own among them -- so they are keyed here by the
# three plain words the card's own list comes to: the beast, the walking shape
# and the hybrid of the two. Which rows belong to which is read off what each
# one swings: the weapon rows want the walking shape, the biting rows want the
# beast, and the hybrid is allowed both.
# ==========================================================================

_M6146_SHAPE = "m6146a6 "
_M6146_SHAPES = ("beast", "humanoid", "hybrid")


def _in_either_shape(prefix: str, *words: str) -> Any:
    """A printed Requirement naming two of a shapechanger's three forms.

    `_in_shape` takes one word and these cards name two. A creature that has
    not changed shape yet is in whatever shape it was found in, which the stat
    block does not say, so an undeclared form rules out no attack.
    """

    def gate(world: World, eid: int) -> bool:
        for effect in world.effects.of(eid):
            if effect.label.startswith(prefix):
                return effect.label[len(prefix) :] in words
        return True

    return gate


@power(
    "m6146a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6146a0(c: Cast) -> None:
    """"m6146 and any ally in the aura" puts the creature itself in, so
    eligibility is the whole team rather than `c.allies`.

    The bonus is gated on the victim rather than held on it: the damage context
    carries `target`, which is the one place "against bloodied targets" can be
    asked at the moment it pays.
    """
    me = c.me

    def eligible(who: int) -> bool:
        return team(c.world, who) is team(c.world, me)

    def hold(who: int) -> Effect | None:
        def at_the_hurt(ctx: dict[str, Any]) -> bool:
            victim = ctx.get("target")
            return victim is not None and c.bloodied(on=victim)

        return c.bonus("damage", 5, on=who, until=When.ENCOUNTER, when=at_the_hurt)

    _aura(c, 5, eligible, hold)


@power(
    "m6146a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m6146a1(c: Cast) -> None:
    """Regeneration lands, including the printed "and has at least 1 hit
    point", which is what regeneration already is. The silver that switches it
    off for a turn does not: nothing marks a weapon as silver, so there is
    nothing for a suspension to read."""
    c.regeneration(10, on=c.me, until=When.ENCOUNTER)


@power(
    "m6146a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 10),
    requires=_in_either_shape(_M6146_SHAPE, "humanoid", "hybrid"),
    requires_text="the m6146 must not be in its beast form",
)
def m6146a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6146a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 13),
    requires=_in_either_shape(_M6146_SHAPE, "beast", "hybrid"),
    requires_text="the m6146 must not be in its walking form",
    dropped=("c.contract(ref)",),
)
def m6146a3(c: Cast) -> None:
    """The bite lands. The disease is the dropped clause: the card names a
    track by ref and the engine holds no diseases, no stages and nothing that
    rolls a saving throw at the end of an encounter."""
    if c.strike():
        c.hit()


@power(
    "m6146a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    requires=_in_either_shape(_M6146_SHAPE, "beast", "hybrid"),
    requires_text="the m6146 must not be in its walking form",
)
def m6146a4(c: Cast) -> None:
    """The step is between the two bites, which is what makes the second one
    reach a creature the first could not -- so it goes where the printed order
    puts it rather than before them both."""
    if not c.first:
        return
    pool = [foe for foe in c.targets if alive(c.world, foe)]
    if not pool:
        return
    use(c.world, c.me, "m6146a3", targets=[pool[0]], spend=False)
    c.shift(6)
    second = pool[1] if len(pool) > 1 else pool[0]
    if alive(c.world, second):
        use(c.world, c.me, "m6146a3", targets=[second], spend=False)


@power(
    "m6146a5",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    requires=_in_either_shape(_M6146_SHAPE, "humanoid", "hybrid"),
    requires_text="the m6146 must not be in its beast form",
)
def m6146a5(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, victim):
            return
        use(c.world, c.me, "m6146a2", targets=[victim], spend=False)


@power(
    "m6146a6",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m6146a6(c: Cast) -> None:
    """Three shapes and nothing else: the statistics do not change, so all the
    form is for is the Requirement on the four rows above it. A polymorph is
    not a stance, so whatever was worn before is ended by hand."""
    _change_shape(c, _M6146_SHAPE, _M6146_SHAPES)


@power(
    "m6146a7",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
)
def m6146a7(c: Cast) -> None:
    """"Each target that has a bite attack" is read literally off what each
    ally knows: the card names the row by ref and that is the only thing on a
    board that answers to it. The swing is the ally's own free action, so
    nothing is spent for it.

    Declared with no target because the printed burst catches allies and
    `EACH_ALLY` would put the m6146 itself in the temporary hit points, which
    "allies in the burst" does not mean.
    """
    me = c.me
    for friend in sorted(c.within(5, side="ally")):
        if friend == me or not alive(c.world, friend):
            continue
        c.temp_hp(15, on=friend)
        known = c.world.get(friend, Powers)
        if known is None or "m6146a3" not in known.all:
            continue
        near = sorted(
            (foe for foe in c.enemies() if c.adjacent_to(foe, friend)),
            key=lambda foe: (c.distance(foe), foe),
        )
        if near:
            use(c.world, friend, "m6146a3", targets=[near[0]], spend=False)


# ==========================================================================
# m6155
# ==========================================================================


@power(
    "m6155a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 12),
)
def m6155a0(c: Cast) -> None:
    """Prone *swaps* the dice rather than adding to them, so the header keeps
    the printed line that rescales and the larger expression is rolled in the
    body."""
    victim = c.target
    if victim is None or not c.strike():
        return
    if c.is_(Condition.PRONE, on=victim):
        c.damage("3d10", 15)
    else:
        c.hit()


@power(
    "m6155a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 12, kind=LIMITED),
)
def m6155a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.prone()


# ==========================================================================
# m6185
# ==========================================================================


@power(
    "m6185a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6185a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m6185a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m6185a1(c: Cast) -> None:
    """Not an aura: the printed reach is line of sight, which has no radius,
    and the moment is the start of a turn rather than entering anything. So the
    watch is on `TurnStart` and asks `c.can_see`, which is line of effect and
    actually visible.

    "Non-aberrant" is read off the creature's own type words, which is also why
    the m6185 is never caught by its own trait.
    """
    me, ref = c.me, c.ref

    def looked(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or not alive(c.world, ev.actor):
            return
        if "aberrant" in c.kinds_of(on=ev.actor):
            return
        if c.can_see(ev.actor):
            c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)

    c.watch(TurnStart, looked, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m6185a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6185a2(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m6185a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d12", 12),
)
def m6185a3(c: Cast) -> None:
    """The grab lands; the printed escape DC does not. `c.grab` takes no DC and
    an escape is rolled against the grabber's own defences, so a card naming a
    number has nowhere to put it."""
    if c.strike():
        c.hit()
        c.grab(dc=20)


@power(
    "m6185a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=UpTo(3),
)
def m6185a4(c: Cast) -> None:
    """Three of the row above, spread over whoever was handed over: the card
    puts no limit on how many land on one creature, unlike the m3621's."""
    if not c.first:
        return
    pool = [foe for foe in c.targets if alive(c.world, foe)]
    if not pool:
        return
    for n in range(3):
        victim = pool[n % len(pool)]
        if alive(c.world, victim):
            use(c.world, c.me, "m6185a3", targets=[victim], spend=False)


@power(
    "m6185a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("3d6", 4, kind=LIMITED),
)
def m6185a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10)


@power(
    "m6185a6",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("etl.monster.summon_ref()",),
)
def m6185a6(c: Cast) -> None:
    """The whole of this row is a creature to put on the board, and the card
    offers a choice of three kinds that the spec gives no ref for. `c.summon`
    takes a ref and there is nothing to hand it, so the row has nothing it can
    do -- the caps, the square and the bloodied allowance are all about a
    creature that cannot be made."""


@power(
    "m6185a7",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
)
def m6185a7(c: Cast) -> None:
    """Flat rather than ongoing: the printed line is one payment now, with no
    saving throw and no clock of its own."""
    for held in sorted(c.grabbing()):
        if alive(c.world, held):
            c.flat(10, dtype=DamageType.ACID, on=held)


@power(
    "m6185a8",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
    todo=("etl.monster.summon_ref()",),
)
def m6185a8(c: Cast) -> None:
    """Three uses of `m6185a6`, which cannot be used: the same missing ref, and
    there is nothing else in this row to play."""


# ==========================================================================
# m6665
# ==========================================================================


@power(
    "m6665a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6665a0(c: Cast) -> None:
    """"During the same turn" is read as the moment one of the two named rows
    is used, which is when the grant has to be made. `PowerUsed` is announced
    *before* the body runs and nothing here depends on what the body did, so it
    is the right event.

    The two rows named are the single stomp and the trample run; the doubled
    row is two uses of the first and announces itself as well, so the set is
    checked rather than the word.
    """
    me, ref = c.me, c.ref
    named = ("m6665a1", "m6665a3")

    def stamped(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power not in named:
            return
        up = c.rider()
        if up is None or not alive(c.world, up):
            return
        near = sorted(
            (
                foe
                for foe in c.enemies()
                if alive(c.world, foe) and c.adjacent_to(foe, up)
            ),
            key=lambda foe: (c.distance(foe), foe),
        )
        if near:
            c.grant_attack(up, on=near[0])

    c.watch(PowerUsed, stamped, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m6665a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 13),
)
def m6665a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6665a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    dropped=("c.cannot_stand()",),
)
def m6665a2(c: Cast) -> None:
    """Two of the row above, and the follow-up needs to know whether both
    landed on one creature -- so the swings go through `c.use_power`, which
    leaves the borrowed row's result in `c.result` for `c.landed` to read.
    A bare `use` would resolve on a `Cast` of its own and say nothing back.

    The burn is clocked on nothing at all: "ongoing 25 until the grab ends" has
    no saving throw, so it runs to the end of the encounter and comes off from
    `RelationCleared` with the two prohibitions this creature takes on for
    holding somebody.

    The escape DC and "the target cannot stand up" are the dropped clauses --
    `c.grab` takes no DC, and nothing takes the stand-up action away from a
    creature that has it.
    """
    me, ref = c.me, c.ref
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, victim):
            break
        c.use_power("m6665a1", on=victim, spend=False)
        if c.landed:
            landed += 1
    if landed < 2 or not alive(c.world, victim):
        return
    if not c.may("take hold of the target"):
        return
    c.grab(on=victim, dc=20)
    burn = c.ongoing(25, on=victim, until=When.ENCOUNTER)
    barred = c.forbid("m6665a3", on=me, until=When.ENCOUNTER)
    rooted = c.no_walk(on=me, until=When.ENCOUNTER)

    def let_go(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.target != victim:
            return
        if ev.source != me:
            return
        for eff in (burn, barred, rooted):
            if eff is not None:
                c.world.effects.end(eff, "the grab ended")

    c.watch(RelationCleared, let_go, until=When.ENCOUNTER, on=me, label=f"{ref} holds")


@power(
    "m6665a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="the m6665 must not have taken a move action this turn",
    dropped=("query.moved_this_turn(world, eid)",),
)
def m6665a3(c: Cast) -> None:
    """Twice its speed is two trample runs: `c.overrun` walks one speed and
    says who was under it, and it is the only way through an occupied square.

    "Any enemy that attacked it during the move grants combat advantage for the
    attack" is laid *as the swing happens* rather than taken as a set at the
    start -- a window the card leaves open is stale the moment it is
    snapshotted, and the printed clause pays on the very next stomp.

    The Requirement is the dropped clause and is deliberately not a
    `requires=`: nothing asks whether a move action has already gone this turn,
    and a `requires=` that is false when a trait is armed refuses the row for
    the whole fight. Here it would simply be false always.
    """
    me, ref = c.me, c.ref

    def noted(ev: AttackDeclared) -> None:
        if ev.target == me and ev.attacker != me:
            c.grants_advantage(on=ev.attacker, to="me", once=True, until=When.EOT)

    watch = c.watch(AttackDeclared, noted, until=When.EOT, on=me, label=f"{ref} saw")
    seen: set[int] = set()
    for _ in range(2):
        for victim in c.overrun():
            if victim in seen or not alive(c.world, victim):
                continue
            seen.add(victim)
            if c.may("stomp the creature underfoot"):
                c.use_power("m6665a1", on=victim, spend=False)
    c.world.effects.end(watch, "the run is over")
    c.end_turn()


# ==========================================================================
# m984
# ==========================================================================


@power(
    "m984a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 7),
)
def m984a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M984_CLAWED = "it hits with a m984a0 attack"


def _my_m984a0(world: World, me: int, ev: Event) -> bool:
    """This creature's own m984a0 landing, which is the printed trigger."""
    return (
        getattr(ev, "attacker", None) == me and getattr(ev, "power", "") == "m984a0"
    )


@power(
    "m984a1",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 7),
    trigger=_M984_CLAWED,
    on=Trigger(Hit, _my_m984a0, _M984_CLAWED),
)
def m984a1(c: Cast) -> None:
    """The row the trigger names is the one the card calls a claw, which is the
    only standard melee attack on the stat block.

    `NO_TARGET`: the creature struck comes off the trigger, and `Hit` names it
    in `target`.
    """
    victim = getattr(c.trigger, "target", None)
    if victim is None or not alive(c.world, victim):
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m984a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m984a2(c: Cast) -> None:
    """The second swing needs to know the first one landed, so it goes through
    `c.use_power`, which leaves the borrowed row's result where `c.landed` can
    read it.

    "A different target within reach and adjacent to the first" is two
    conditions on the same creature and both are asked: reach from the m984,
    adjacency to whoever was clawed.
    """
    victim = c.target
    if victim is None:
        return
    c.use_power("m984a0", on=victim, spend=False)
    if not c.landed:
        return
    near = sorted(
        foe
        for foe in c.enemies()
        if foe != victim
        and alive(c.world, foe)
        and c.distance(foe) <= 2
        and c.adjacent_to(foe, victim)
    )
    if near and c.may("claw the second creature"):
        c.use_power("m984a0", on=near[0], spend=False)


@power(
    "m984a3",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=14),
)
def m984a3(c: Cast) -> None:
    """No damage on the hit line, so the header declares none and nothing is
    dealt.

    "Grants combat advantage to all attackers" is `to="team"`, and that is
    exact in play rather than an approximation: the relation names one
    beneficiary at a time, and everybody who would ever attack this creature is
    on the m984's side of the board. The same reading carries the sight: the
    concealment half is `c.no_cover` on the target, and the invisibility half is
    `c.truesight(of=)` laid on each of the attackers, which is where the engine
    reads "cannot become invisible to you" from.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.grants_advantage(on=victim, to="team", until=When.EONT)
    c.no_cover(on=victim, until=When.EONT)
    for who in [c.me, *c.allies()]:
        c.truesight(of=victim, on=who, until=When.EONT)


@power(
    "m984a4",
    level=13,
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(4, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC, half_on_miss=True),
)
def m984a4(c: Cast) -> None:
    """`half_on_miss=True` is declared data that no line of the engine reads,
    so the Miss branch is written out -- and the card says the daze is *not*
    carried on a miss, which is the whole reason the two branches differ."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m984a5",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m984a5(c: Cast) -> None:
    """The dark is a zone that blocks sight, and the printed exemption for the
    m984 itself is the dropped clause: `c.zone(blocks_sight=True)` blocks it for
    everybody or for nobody.

    The blinding is per occupant and is kept up as creatures walk in and out,
    which is what "any creature entirely within the area" means for a zone
    standing still while the fight moves through it. The m984 is left out of
    that half, which the engine *can* say.
    """
    me, ref = c.me, c.ref
    dark = c.zone(c.area(), label=ref, until=When.EONT, blocks_sight=True)
    held: dict[int, Effect] = {}

    def take(who: int) -> None:
        if who == me or who in held:
            return
        eff = c.blinded(on=who, until=When.EONT)
        if eff is not None:
            held[who] = eff

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == dark:
            take(ev.actor)

    def left(ev: ZoneExited) -> None:
        eff = held.pop(ev.actor, None) if ev.zone == dark else None
        if eff is not None:
            c.world.effects.end(eff, "left the dark")

    c.watch(ZoneEntered, entered, until=When.EONT, on=me, label=f"{ref} in")
    c.watch(ZoneExited, left, until=When.EONT, on=me, label=f"{ref} out")
    for actor in c.world.zones.occupants(dark):
        take(actor)
