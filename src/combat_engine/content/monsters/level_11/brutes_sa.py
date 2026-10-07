"""Monster abilities, level 11: the rest of the brutes.

`brutes.py` holds the seven stat blocks this level already had; this file is
the other twenty-eight. A stat block's numbers load from `game.db` and the
printed lines go in the header verbatim -- `Attack(vs=AC, printed=16)`,
`Damage("3d10", 8)` -- so the engine can take the level term back out and
rescale a MM1 block onto MM3 maths.

The conventions of the eleven levels below are kept: a **trait** is a row
costing no action with no target, arming the watches that hold it for the
rest of the fight, and several rows the database files as standard actions
are plainly traits and written as such; a stat block printing no range at
all means melee 1; a printed "Effect (Immediate Interrupt)" is
`action=INTERRUPT` whatever the database's action column says; and a helper
written for an earlier level is imported rather than copied.

Nine things this file had to settle.

**Three blocks tell their own abilities under another block's id.** m5565's
five rows all name m147, m1591a2 names m100, and m5334a3 names m5333. In
each case the creature being described is the one whose rows these are --
the same shape `brutes.py` recorded for m4937a0 -- so nothing reaches across
and every row is filed under its own ref. m147's own rows are a level below
and are untouched.

**A parenthetical bloodied attack bonus is not written twice.** m4510 prints
"(+17 while bloodied)" on six attack lines and *also* prints a trait,
m4510a7, granting +2 to attack and damage while bloodied. Writing both would
pay the bonus twice over on every swing, so each attack row carries only its
base printed number and m4510a7 is the one thing that lifts it. The card's
own arithmetic disagrees with itself -- the parenthetical is one point where
the trait says two -- and the trait is the sentence that says what it does.

**"Until the grab ends" is a duration the engine has, through the grab.**
m115827a2's burn is applied for the encounter and ended from the grab's own
`on_end`, which is one hold governing the other rather than a saving throw
the card never printed.

**A sixth failed saving throw is reachable, so the whole track is written.**
m6643a0 steps slowed to immobilized to stunned on the first two failures and
then counts the rest; the sixth makes the stun last the encounter, which is
what "stunned for 4 hours" is worth on a board.

**A resistance that replaces itself needs a label, and `c.resist` has none.**
m5120a6 is "until the end of the encounter or until it uses this again", so
the entry is written onto `Defences` under a hold this file labels, exactly
as `brutes.py`'s `_take_resistances` reads one off -- `c.resist` builds its
own anonymous hold and a second use could not find the first.

**Two cards lost their defence in extraction.** m2085a1 prints "+12 vs ;"
and m947a1 prints "+12 vs ;", and m2085a1 prints its damage expression twice
over besides. Neither attack can be declared without inventing a defence, so
each row plays the sentence that survived intact and names the gap.

**A monster's gear is not modelled by name.** m3242a1's Requirement names the
blade in its hand and m4510a5's Effect says the axe comes back; both are the
line the creature swings with every turn, so there is nothing to gate and
nothing to return. The same reading `brutes.py` took for m355a1.

**Three blocks summon something no ref names.** m2237a4, m6086a4 -- the
spec prints no id for either -- and they are marked rather than guessed.
m6407a6 does print one, so it is written.

**"Uses X twice" is the row that prints X, used twice.** Its damage line
stays in one place, which is the point of the damage being header data.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.brutes import _is_kind
from combat_engine.content.monsters.level_05.brutes import _defences_down
from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_07.brutes import _crit_line, _damaged_a_foe
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.brutes import (
    SMALL_ENOUGH,
    _felled_by_me,
    _has_hold,
    _holding,
    _is_bloodied,
)
from combat_engine.content.monsters.level_09.brutes import (
    CAUTERISING,
    _dealt,
    _put_beside,
    _volley,
)
from combat_engine.content.monsters.level_09.skirmishers import (
    _WEAPON_RANGES,
    _holding_label,
)
from combat_engine.content.monsters.level_10.brutes import _same_stock
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Damage,
    DamageApplied,
    DamageType,
    Defences,
    Dropped,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    Position,
    Ranged,
    Stats,
    SurgeSpent,
    Target,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    power,
    targets_me,
    use,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    alive,
    creatures,
    distance_between,
    flanked_by,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, by_me

#: What m1070a1's printed Requirement asks of whoever is in the saddle. A
#: monster carries no feats, so the other half of that line is not tested.
_MOUNTED_RIDER_LEVEL = 11

#: The five types m5120a6 answers, and nothing else.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _qualified_rider(c: Cast) -> int | None:
    """Whoever is in the saddle, if the printed Requirement lets them ride.

    Asked at the moment rather than when the trait arms: a rider mounts and
    falls off mid-fight, and a hold handed out once would go to the wrong
    creature or to nobody.
    """
    rider = c.rider()
    if rider is None or team(c.world, rider) is not team(c.world, c.me):
        return None
    stats = c.world.get(rider, Stats)
    return rider if stats is not None and stats.level >= _MOUNTED_RIDER_LEVEL else None


def _each_of_my_turns(c: Cast, fn: Any, label: str = "") -> None:
    """Run that at the top of every one of this creature's turns, and now.

    The shape a standing clause takes when it is re-read rather than held:
    a Requirement that can become true later gets its chance, which is the
    whole reason `requires=` does not belong on a trait.
    """
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            fn()

    fn()
    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=label or c.ref)


def _toll_on_entering_turn(c: Cast, radius: int, fn: Any) -> int:
    """An aura for the board to draw, and a toll for starting a turn inside.

    Not the membership helper a level below: what these cards charge is paid
    once, at a turn's beginning, and what it lays keeps its own clock after
    that -- so occupancy is read off the ring at that moment rather than
    diffed by entry and exit.
    """
    me = c.me
    ring = c.aura(radius, until=When.ENCOUNTER)

    def began(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(ring):
            fn(ev.actor)

    c.watch(TurnStart, began, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")
    return ring


def _one_save_for_both(c: Cast, held: Effect | None, extra: Effect | None) -> None:
    """Tie a second hold to the first so one saving throw ends both.

    "Save ends both" is one printed sentence. Two save-ends holds would be
    two rolls, so the rider is laid for the encounter and torn down by the
    hold that carries the save.
    """
    if held is None or extra is None:
        return
    held.on_end.append(lambda: c.world.effects.end(extra, "the save ends both"))


def _quenched(c: Cast, types: tuple[DamageType, ...]) -> bool:
    """Is this creature's own damage rider switched off by a blow it took?

    Armed on first use and guarded by its own label, because the stat block
    files the clause on the attack row and prints no trait to hang it on.
    The hold is clocked on the caster, which is what "until the end of its
    next turn" means on a line about itself.
    """
    me, label = c.me, f"{c.ref} quenched"
    if not any(e.label == f"{label} watch" for e in c.world.effects.of(me)):

        def took(ev: DamageApplied) -> None:
            if ev.target == me and set(ev.types()) & set(types):
                c.effect(label, until=When.EONT, on=me)

        c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{label} watch")
    return _holding_label(c, label)


def _resist_until_replaced(c: Cast, dtype: DamageType, amount: int) -> None:
    """Resist one type until this row lays a different one, or the fight ends.

    `c.resist` builds an anonymous hold, so a second use has no way to find
    the first and the two would stack. The entry is written onto `Defences`
    under a label instead and handed back by the hold that took it, which is
    the shape `brutes.py` already reads a resistance off.
    """
    me, label = c.me, f"{c.ref} resist"
    for eff in list(c.world.effects.of(me)):
        if eff.label == label:
            c.world.effects.end(eff, "a newer element")
    shield = c.world.get(me, Defences)
    if shield is None:
        return
    had = shield.resist.get(dtype)
    shield.resist[dtype] = max(amount, had or 0)

    def give_back() -> None:
        if had is None:
            shield.resist.pop(dtype, None)
        else:
            shield.resist[dtype] = had

    c.world.effects.apply(me, me, When.ENCOUNTER, label=label, on_end=[give_back])


def _is_prone(c: Cast) -> Any:
    """A test for `_restricted_to`, which wants one of these per row."""
    return lambda who: c.is_(Condition.PRONE, on=who)


def _close_or_area(world: World, me: int, ev: Hit) -> bool:
    """Was the blow that landed a close or an area attack?

    `by_melee` counts a close burst as melee, which is right where it is used
    and exactly wrong here -- the range kind is read off the row instead.
    """
    return ev.target == me and _reach_kind(ev).split("_")[0] in ("close", "area")


def _weapon_blow(ev: Hit) -> bool:
    """Did a weapon land this? What "+1[W] or +1d8" has to ask."""
    from combat_engine.engine.dsl import get

    p = get(getattr(ev, "power", "") or "")
    return p is not None and Keyword.WEAPON in p.keywords


# ==========================================================================
# m1070
# ==========================================================================


@power(
    "m1070a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 5),
)
def m1070a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1070a1",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="the m1070 must be mounted by a friendly rider of 11th level or higher",
)
def m1070a1(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: nobody chooses to
    carry somebody.

    The Requirement is asked in the body and not in the header -- a trait
    whose `requires` is false when it arms is refused once and never armed
    again, and this one starts false in every fight the rider mounts during.
    Laid on the rider's own clock each turn so it goes when they fall off.
    """
    def saddle() -> None:
        rider = _qualified_rider(c)
        if rider is not None:
            c.resist(20, DamageType.NECROTIC, on=rider, until=When.EONT)

    _each_of_my_turns(c, saddle)


# ==========================================================================
# m115827
# ==========================================================================


@power(
    "m115827a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.max_height()",),
)
def m115827a0(c: Cast) -> None:
    """A ceiling on how high it may fly while it is carrying somebody.
    `c.height` reads the distance and `c.rise`/`c.hover` set it; nothing caps
    it, so the whole of this trait is the thing that is missing."""


@power(
    "m115827a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d10", 8),
)
def m115827a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115827a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 6),
)
def m115827a2(c: Cast) -> None:
    """"Until the grab ends, the target takes ongoing 5 damage" is one hold
    governing another: the burn is laid for the encounter and torn down from
    the grab's own `on_end`, so letting go stops it and no saving throw the
    card never printed is rolled.

    The escape DC has nowhere to go -- a grab is a relation here and the
    engine has no contest to put a number in.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if _holding(c.world, c.me):
        return
    hold = c.grab(on=victim, dc=19)
    burn = c.ongoing(5, on=victim, until=When.ENCOUNTER)
    if hold is not None and burn is not None:
        hold.on_end.append(lambda: c.world.effects.end(burn, "the grab ends"))


@power(
    "m115827a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 6),
)
def m115827a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115827a4",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115827a4(c: Cast) -> None:
    """Whoever it has hold of is read *before* the step, because the pull is
    what the flight does to them and the grab outlives the move.

    The captive is set down beside the creature rather than walked: a grabbed
    body has no movement of its own to spend, and `_put_beside` measures the
    footprint being moved rather than the caster's. Vertical pulling needs
    nothing of its own -- the board is flat and `c.height` rides along with
    the mover.
    """
    captive = sorted(_holding(c.world, c.me))
    for who in captive:
        c.no_provoke(from_=who, on=c.me, until=When.EOT)
    c.move(max(1, c.speed_of() // 2), at="fly")
    for who in captive:
        if not c.adjacent(who):
            _put_beside(c, who, c.me)


# ==========================================================================
# m1438
# ==========================================================================


_M1438_BLED = "the m1438 is first bloodied"


def _adjacent_demon(world: World, eid: int) -> bool:
    """A printed "an adjacent demon" asked from a header gate.

    Not a trait, so the Requirement is consulted at the moment of use and may
    safely live here. `_is_kind` is the gate-shaped form of `Cast.is_kind`,
    which is the only thing that reads a type line.
    """
    mine = team(world, eid)
    return any(
        other != eid
        and team(world, other) is mine
        and distance_between(world, eid, other) <= 1
        and _is_kind(world, other, "demon")
        for other in creatures(world)
    )


@power(
    "m1438a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 6),
)
def m1438a0(c: Cast) -> None:
    """Two expressions on one line and the header holds one, so the untyped
    half scales as data and the cold half is rolled beside it."""
    if c.strike():
        c.hit()
        c.damage("1d10", dtype=DamageType.COLD)


@power(
    "m1438a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d8", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m1438a1(c: Cast) -> None:
    """The card prints a blast and no target line at all, so the blast takes
    the enemies standing in it rather than everybody.

    "Slowed and takes a -2 penalty to attack rolls (save ends both)" is one
    printed sentence, so the penalty rides the condition's hold.
    """
    if not c.strike():
        return
    c.hit()
    held = c.condition(Condition.SLOWED, until=When.SAVE_ENDS)
    _one_save_for_both(c, held, c.penalty("attack", 2, until=When.ENCOUNTER))


@power(
    "m1438a2",
    level=11,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("4d10", 6, kind=LIMITED),
    trigger=_M1438_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M1438_BLED),
)
def m1438a2(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else. The trigger is about itself rather than about an
    attacker, so the row picks its own target the ordinary way."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1438a3",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    requires=_adjacent_demon,
    requires_text="an adjacent demon spurs the m1438 on",
    dropped=("c.spend_action(who, cost)",),
)
def m1438a3(c: Cast) -> None:
    """Goaded into one more swing, and it costs blood.

    The row belongs to the m1438 and the minor action belongs to the ally, so
    only one half of the price can be taken: `c.extra_action` puts the
    standard into the budget the turn is already spending, and there is no
    way to charge another creature for it.
    """
    c.damage("1d10", on=c.me)
    c.extra_action(ActionType.STANDARD, on=c.me)


# ==========================================================================
# m1472
# ==========================================================================


@power(
    "m1472a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 6),
)
def m1472a0(c: Cast) -> None:
    """The database files "sustain standard" against this line and the card
    gives it nothing to hold -- no condition, no zone, no grab -- so there is
    no effect for a sustain to carry and none is declared."""
    if c.strike():
        c.hit()


@power(
    "m1472a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d6", 6, kind=LIMITED),
)
def m1472a1(c: Cast) -> None:
    """The row *is* the charge, so `charges=True`: without it the engine
    measures reach before the run and refuses the row from exactly the
    distance a charge is for."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1472a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.cannot_attack(except_=)",),
)
def m1472a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it is what happens to
    the creature, not something it chooses.

    "The creature becomes immobilized" is the m1472 itself -- it stops to
    feed -- and is re-asked each turn, because a prone enemy stands up and
    the compulsion should lift with it. The +2 is gated rather than laid, so
    it is read at the roll against whoever is down at that moment.

    What is dropped is "cannot attack any target other than a prone enemy":
    `c.cannot_attack` bars everything or one named creature, and there is no
    form that leaves one class of target open.
    """
    me = c.me

    def feed() -> None:
        if any(c.is_(Condition.PRONE, on=foe) and c.distance(foe) <= 1 for foe in c.enemies()):
            c.immobilized(on=me, until=When.EONT)

    def on_the_floor(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.is_(Condition.PRONE, on=who)

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=on_the_floor)
    _each_of_my_turns(c, feed)


# ==========================================================================
# m1566
# ==========================================================================


_M1566_BIT = "the m1566 hits a target with its m1566a1"


def _m1566_landed(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power == "m1566a1"


@power(
    "m1566a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m1566a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1566a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m1566a1(c: Cast) -> None:
    """"Ongoing 5 poison damage and the target is immobilized (save ends
    both)" is one effect carrying both, which is one saving throw."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )


@power(
    "m1566a2",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M1566_BIT,
    on=Trigger(Hit, when=_m1566_landed, text=_M1566_BIT),
)
def m1566a2(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m1582
# ==========================================================================


_M1582_BLOODIED_ONE = "the m1582's attack bloodies an enemy"


@power(
    "m1582a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 7),
)
def m1582a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1582a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 7, kind=LIMITED),
)
def m1582a1(c: Cast) -> None:
    """Only the burn is printed as poison; the declared line is untyped, so
    the header carries no type and the ongoing names one."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1582a2",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1582_BLOODIED_ONE,
    on=Trigger(Bloodied, when=by_me, text=_M1582_BLOODIED_ONE),
)
def m1582a2(c: Cast) -> None:
    """`Bloodied` carries `source`, so "its attack bloodies an enemy" is a
    declared trigger and does not have to be re-derived off the damage.

    Declared with no target because the swing is m1582a0, which picks its
    own: the triggering enemy may have been the last one in reach.
    """
    use(c.world, c.me, "m1582a0", spend=False)


@power(
    "m1582a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1582a3(c: Cast) -> None:
    """Back up unless acid or fire put it down.

    `Dropped` says who struck the blow and not what with, so the type comes
    off the `DamageApplied` immediately before it -- the blow that crossed
    the line, and the only one that can be. `c.revives_unless` is the
    declaration that stops the policy writing the body off; the watch is what
    stands it up.

    Taken in the same window rather than deferred to its next turn as a move
    action: nothing in the engine owes a corpse an action, and a body that
    waits a round is one `threat_removed` has already discounted.
    """
    me = c.me
    risen: dict[str, int] = {"count": 0}
    c.revives_unless(*CAUTERISING, on=me)

    def rise(ev: Dropped) -> None:
        if ev.actor != me or risen["count"] or _dealt(c.world, ev, me, CAUTERISING):
            return
        risen["count"] += 1
        c.reanimate(on=me, hp=10)

    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1591
# ==========================================================================
#
# m1591a2's trigger sentence names its second half by an id belonging to
# another stat block. Nothing on that block is reached: the creature being
# described is this one, and the row is filed under this one's ref.


_M1591_BLED = "the m1591 is first bloodied"
_M1591_FELLED = "the m1591 is reduced to 0 hit points"


@power(
    "m1591a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 6),
)
def m1591a0(c: Cast) -> None:
    """The printed "crit 2d8 + 22" replaces the damage and is a roll, so it
    is dealt flat past the engine's own rule that a critical maxes declared
    dice.

    The necrotic ten is a second packet and is switched off by acid or fire
    for a turn. That watch is armed here, guarded by its own label: the stat
    block prints no trait to hang it on.
    """
    if not c.strike():
        return
    doused = _quenched(c, CAUTERISING)
    _crit_line(c, "2d8", 22)
    if not doused:
        c.flat(10, dtype=DamageType.NECROTIC)


@power(
    "m1591a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 6),
)
def m1591a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1591a2",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
    trigger=f"{_M1591_BLED} or {_M1591_FELLED}",
    on=(
        Trigger(Bloodied, when=about_me, text=_M1591_BLED),
        Trigger(Dropped, when=about_me, text=_M1591_FELLED),
    ),
)
def m1591a2(c: Cast) -> None:
    """Two printed sentences, so two declared triggers rather than one
    predicate reading both -- the card should show each.

    A triggered burst picks its own targets: the dispatcher only aims a
    single-creature row off the trigger.
    """
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


# ==========================================================================
# m2074
# ==========================================================================


_M2074_STRUCK_AT = "an enemy hits or misses the m2074"
_M2074_BLED = "the m2074 is first bloodied"
_M2074_LANDED = "the m2074 hits an enemy"


@power(
    "m2074a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 6),
)
def m2074a0(c: Cast) -> None:
    """The printed "crit 2d12 + 30" replaces the damage and is a roll."""
    if c.strike():
        _crit_line(c, "2d12", 30)


@power(
    "m2074a1",
    level=11,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d12", 6, kind=LIMITED),
    trigger=_M2074_STRUCK_AT,
    on=(
        Trigger(Hit, when=targets_me, text=_M2074_STRUCK_AT),
        Trigger(Miss, when=targets_me, text=_M2074_STRUCK_AT),
    ),
)
def m2074a1(c: Cast) -> None:
    """Hit or missed, the answer is the same, so both events are declared.

    The dispatcher aims a single-enemy row at whoever the event was about, so
    "targets the triggering enemy" needs nothing read off the trigger.
    """
    if c.strike():
        _crit_line(c, "2d12", 42)


@power(
    "m2074a2",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m2074a2(c: Cast) -> None:
    c.temp_hp(15, on=c.me)
    c.cure(Condition.MARKED, on=c.me)


@power(
    "m2074a3",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2074_LANDED,
    on=Trigger(Hit, when=by_me, text=_M2074_LANDED),
)
def m2074a3(c: Cast) -> None:
    """One extra die on a blow that has already landed.

    Which die depends on what swung, so the keyword is read off the row
    behind the event rather than assumed: a monster's `c.w()` is the line it
    is actually holding, and the psychic minor is the nonweapon half this
    card distinguishes. Dealt flat, because the extra is rolled and a
    critical would otherwise max it.
    """
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is None or team(c.world, victim) is team(c.world, c.me):
        return
    dice = c.w() if _weapon_blow(ev) else "1d8"
    c.flat(c.roll(dice), on=victim)


@power(
    "m2074a4",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2074_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2074_BLED),
)
def m2074a4(c: Cast) -> None:
    """Filed as a standard action and plainly a triggered one: nobody chooses
    to be wounded."""
    c.temp_hp(10, on=c.me)


@power(
    "m2074a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2074a5(c: Cast) -> None:
    """A second swing at a neighbour every time the first one lands.

    The victim is named explicitly: `c.basic`'s `who` is who swings and `on`
    is who is hit, and leaving the second off would aim the follow-up back at
    the creature already struck. "Another adjacent enemy" is read at the
    moment the blow lands, because who is crowding it changes with every
    step.
    """
    me, ref = c.me, c.ref
    swinging: dict[str, bool] = {"now": False}

    def again(ev: Hit) -> None:
        if ev.attacker != me or swinging["now"]:
            return
        if _reach_kind(ev) != "melee":
            return
        others = sorted(
            foe
            for foe in c.enemies()
            if foe != ev.target and c.adjacent(foe) and alive(c.world, foe)
        )
        if not others:
            return
        swinging["now"] = True
        try:
            c.penalty("attack", 2, until=When.EOT, on=me)
            c.basic(who=me, on=others[0])
        finally:
            swinging["now"] = False

    c.watch(Hit, again, until=When.ENCOUNTER, on=me, label=ref)


# ==========================================================================
# m2085
# ==========================================================================


@power(
    "m2085a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 5),
)
def m2085a0(c: Cast) -> None:
    """Three printed durations on one hit -- the damage, a save-ends burn and
    a grab that lasts until escape -- so the burn and the hold are separate
    effects rather than one carrying both."""
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.grab()


@power(
    "m2085a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    damage=Damage("2d6", 5),
    requires=_has_hold,
    requires_text="the m2085 must be grabbing a creature",
    dropped=("compendium.attack_defence",),
)
def m2085a1(c: Cast) -> None:
    """The card's attack line comes out of extraction as "+12 vs ;" with no
    defence at all, and its damage printed twice over in two different
    expressions. Neither can be declared without inventing a number, so the
    roll is named rather than guessed and what plays is the sentence that
    survived: it crushes whatever it already has hold of.

    "A grabbed target only" is narrower than any `Target` can say, so the
    Requirement carries the caster's half and the body picks.
    """
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m2085a1: which of them it crushes") if held else None
    if victim is not None:
        c.hit(on=victim)


@power(
    "m2085a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2085a2(c: Cast) -> None:
    """Flanking is recomputed rather than stored and changes with every step
    either creature takes, so the gate is read at the moment of the roll.
    `flanked_by` asks about the target first and the flanker second."""
    me = c.me

    def pinned(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and flanked_by(c.world, who, me)

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=pinned)


@power(
    "m2085a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2085a3(c: Cast) -> None:
    """The bonus is the allies' to spend, so it rides on each of them and is
    gated on who they are swinging at -- a modifier is read off the attacker,
    and one held here would never be consulted.

    Whoever is on its side when the trait arms is who gets it, which is the
    price of a modifier being a thing a creature carries.
    """
    me = c.me

    def its_prisoner(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and victim in _holding(c.world, me)

    for friend in sorted(c.allies()):
        if friend != me:
            c.bonus("attack", 2, until=When.ENCOUNTER, on=friend, when=its_prisoner)


# ==========================================================================
# m2237
# ==========================================================================


_M2237_FELLED = "the m2237 is reduced to 0 hit points"


@power(
    "m2237a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 5),
)
def m2237a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m2237a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m2237a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m2237a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=12),
    requires=_has_hold,
    requires_text="the m2237 must be grabbing a Medium or smaller creature",
    dropped=("c.swallowed()",),
)
def m2237a2(c: Cast) -> None:
    """Being inside the creature is written as what the card says it costs:
    restrained, and ten necrotic every time the turn comes round. The rest of
    being swallowed -- line of sight and effect only to the m2237, melee and
    close attacks only, and five off the escape check -- is what `c.swallowed`
    would be, and nothing expresses any of it.

    "Escape ends" has no duration either, so the hold is the save-ends one
    the engine does have.
    """
    held = sorted(
        who for who in _holding(c.world, c.me) if c.size_of(on=who) in SMALL_ENOUGH
    )
    victim = c.choose(held, "m2237a2: which of them it swallows") if held else None
    if victim is None or not c.strike(on=victim):
        return
    c.condition(
        Condition.RESTRAINED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(10, DamageType.NECROTIC),
    )


@power(
    "m2237a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m2237a3(c: Cast) -> None:
    """Two rows, one each against two different targets, through the rows
    that print them so their attack and damage lines stay in one place.

    Armed once for the whole use -- `c.first` -- because the pairing is the
    row's, not each target's.
    """
    if not c.first:
        return
    victims = list(c.targets[:2])
    for ref, who in zip(("m2237a0", "m2237a1"), victims + victims[-1:], strict=False):
        if alive(c.world, who):
            use(c.world, c.me, ref, targets=[who], spend=False)


@power(
    "m2237a4",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2237_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M2237_FELLED),
    todo=("etl.monster.summon_ref()",),
)
def m2237a4(c: Cast) -> None:
    """Four creatures spill out of it when it falls and the spec prints no id
    for any of them, so there is nothing to put on the board. Releasing what
    it had swallowed is the same sentence and waits on the same thing."""


# ==========================================================================
# m2297
# ==========================================================================


_M2297_FELLED = "the m2297 is reduced to 0 hit points"
_M2297_MISSED = "a melee attack misses the m2297"


def _missed_me_in_melee(world: World, me: int, ev: Miss) -> bool:
    return ev.target == me and _reach_kind(ev) == "melee"


@power(
    "m2297a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m2297a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.NECROTIC)


@power(
    "m2297a1",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC),
    trigger=_M2297_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M2297_FELLED),
)
def m2297a1(c: Cast) -> None:
    """A death throe, and a creature may answer its own downfall -- the
    dispatcher makes the exception for exactly this shape. A triggered burst
    picks its own targets."""
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m2297a2",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2297_MISSED,
    on=Trigger(Miss, when=_missed_me_in_melee, text=_M2297_MISSED),
)
def m2297a2(c: Cast) -> None:
    """"A melee attack" is the range kind read off the row, not `by_melee`,
    which counts a close burst as melee."""
    c.shift(1)


# ==========================================================================
# m3242
# ==========================================================================


_M3242_STRUCK = "a melee attack hits the m3242"


def _hit_me_in_melee(world: World, me: int, ev: Hit) -> bool:
    return ev.target == me and _reach_kind(ev) == "melee"


@power(
    "m3242a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 5),
)
def m3242a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3242a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 5),
)
def m3242a1(c: Cast) -> None:
    """The printed Requirement names the blade in its hand, and a monster's
    gear is not modelled by name -- it is the same line m3242a0 swings, so
    the row is left usable rather than gated on something nothing can answer.

    The Miss line is a second swing at somebody else, which is why it is
    written out instead of riding `half_on_miss`.
    """
    victim = c.target
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()
        return
    others = sorted(
        foe
        for foe in c.enemies()
        if foe != victim and c.adjacent(foe) and alive(c.world, foe)
    )
    if others:
        c.basic(who=c.me, on=others[0])


@power(
    "m3242a2",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
    trigger=_M3242_STRUCK,
    on=Trigger(Hit, when=_hit_me_in_melee, text=_M3242_STRUCK),
)
def m3242a2(c: Cast) -> None:
    """Declared with no target: "an adjacent enemy" is not necessarily the
    one that struck -- a reach weapon hits from two squares -- so the
    neighbour is picked here."""
    near = sorted(
        foe for foe in c.enemies() if c.adjacent(foe) and alive(c.world, foe)
    )
    if near:
        c.basic(who=c.me, on=near[0])


# ==========================================================================
# m3268
# ==========================================================================


_M3268_KILLED = "the m3268 drops an enemy to 0 hit points or fewer"
_M3268_BLED = "the m3268 is first bloodied"
_M3268_FELLED = "the m3268 is reduced to 0 hit points"


@power(
    "m3268a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 8),
)
def m3268a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3268a1",
    level=11,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 7),
)
def m3268a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3268a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 7),
)
def m3268a2(c: Cast) -> None:
    """A charge whose blow is this row's own line, and then a step and a
    second swing -- which is why the shift comes after the attack rather than
    before it: taken first it would walk out of the reach the charge bought.

    The basic attack names its victim, because `c.basic` without `on=` aims
    at the creature this row already hit.
    """
    if c.strike():
        c.hit()
        c.prone()
    c.shift(2)
    near = sorted(
        foe for foe in c.enemies() if c.adjacent(foe) and alive(c.world, foe)
    )
    if near:
        c.basic(who=c.me, on=near[0])


@power(
    "m3268a3",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger=_M3268_KILLED,
    on=Trigger(Dropped, when=_felled_by_me, text=_M3268_KILLED),
)
def m3268a3(c: Cast) -> None:
    """Thirty back, and not a healing surge: the card prints a number and a
    monster spends a surge only when its row says so."""
    c.heal(30, on=c.me)


@power(
    "m3268a4",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=f"{_M3268_BLED} or {_M3268_FELLED}",
    on=(
        Trigger(Bloodied, when=about_me, text=_M3268_BLED),
        Trigger(Dropped, when=about_me, text=_M3268_FELLED),
    ),
)
def m3268a4(c: Cast) -> None:
    """Two printed sentences, so two declared triggers. Declared with no
    target because by the second there may be nobody left in reach."""
    near = sorted(
        foe for foe in c.enemies() if c.adjacent(foe) and alive(c.world, foe)
    )
    if near:
        c.basic(who=c.me, on=near[0])


# ==========================================================================
# m3337
# ==========================================================================


@power(
    "m3337a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 1),
)
def m3337a0(c: Cast) -> None:
    """Two expressions on one line and the header holds one, so the untyped
    half scales as data and the five is a flat packet of lightning."""
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.LIGHTNING)


@power(
    "m3337a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.LIGHTNING],
)
def m3337a1(c: Cast) -> None:
    """Two swings of the row that prints them, and a secondary attack when
    both found the same creature.

    The printed Effect does not say whether the two land on one target or
    two, so the header takes up to two and a single target is bitten twice --
    the only reading under which "if both hit the same target" can be true.
    The secondary is a second roll, so its printed +14 is trimmed by hand the
    way `Attack.bonus_for` trims the header's.
    """
    victim = c.target
    if victim is None:
        return
    if _volley(c, "m3337a0", victim) and c.attack(
        c.world.scaling.trim(14, c.level), AC, on=victim
    ):
        c.grab(on=victim)


@power(
    "m3337a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    damage=Damage("2d10", 3),
    requires=_has_hold,
    requires_text="the m3337 must be grabbing a creature",
)
def m3337a2(c: Cast) -> None:
    """"No attack roll required" is the whole of why there is no attack in the
    header: it already has hold of the thing."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m3337a2: which of them it savages") if held else None
    if victim is not None:
        c.hit(on=victim)
        c.ongoing(5, DamageType.LIGHTNING, on=victim)


# ==========================================================================
# m4036
# ==========================================================================


_M4036_FELLED = "the m4036 is reduced to 0 hit points"


@power(
    "m4036a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 7, dtype=DamageType.THUNDER, kind=MINION),
)
def m4036a0(c: Cast) -> None:
    """A minion's flat number says so with `kind=MINION`, and its single hit
    point is in the database like every other number here."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.THUNDER)


@power(
    "m4036a1",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER],
    trigger=_M4036_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4036_FELLED),
)
def m4036a1(c: Cast) -> None:
    """No attack roll printed, and the burst takes both sides -- "each
    non-elemental creature" is the only filter, and it is asked of the
    creature rather than of its side."""
    if not c.is_kind("elemental"):
        c.flat(10, dtype=DamageType.THUNDER)


# ==========================================================================
# m4510
# ==========================================================================
#
# Six attack lines print "(+N while bloodied)" and m4510a7 is the trait that
# lifts them. Only the base number is written on each row; writing the
# parenthetical as well would pay the increase twice on every swing.


_M4510_SURGED = "an adjacent enemy spends a healing surge"


def _neighbour_surged(world: World, me: int, ev: SurgeSpent) -> bool:
    who = ev.actor
    if who == me or team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 1


@power(
    "m4510a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d12", 6),
)
def m4510a0(c: Cast) -> None:
    """The printed "crit 2d12 + 30" replaces the damage and is a roll. The
    Miss line is a flat six rather than half the damage, so it is written out
    and `half_on_miss` is not declared."""
    if c.strike():
        _crit_line(c, "2d12", 30)
    else:
        c.flat(6)


@power(
    "m4510a1",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
)
def m4510a1(c: Cast) -> None:
    """No damage on the hit at all: the whole of it is what the target pays
    for swinging back, which is `c.on_attack` gated on who is being swung at
    rather than a damage modifier -- a modifier is read off the attacker and
    this one has to be read off its victim."""
    victim = c.target
    if victim is None or not c.strike():
        return
    me, ref = c.me, c.ref

    def recoil(ev: Any) -> None:
        if getattr(ev, "target", None) == me:
            c.damage("1d8", 5, dtype=DamageType.PSYCHIC, on=victim, detail=ref)

    c.on_attack(recoil, by=victim, until=When.SAVE_ENDS, label=ref)
    c.effect(ref, until=When.SAVE_ENDS, on=victim)


@power(
    "m4510a2",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 3, dtype=DamageType.FIRE, kind=LIMITED),
)
def m4510a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4510a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d12", 6, kind=LIMITED, half_on_miss=True),
)
def m4510a3(c: Cast) -> None:
    """"Recharges when bloodied" is a board state rather than a die. The
    number stays in the header, because that is what the card shows and what
    `actions.recharge` rolls; the printed sentence sits on top of it and the
    two only ever agree to give the row back sooner.

    The crit line replaces the damage, so the Miss branch is written out
    rather than left to the declared flag.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        _crit_line(c, "3d12", 42)
        c.ongoing(5)
    else:
        c.hit(half=True)


@power(
    "m4510a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d12", 10, kind=LIMITED, half_on_miss=True),
)
def m4510a4(c: Cast) -> None:
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        _crit_line(c, "3d12", 46)
    else:
        c.hit(half=True)


@power(
    "m4510a5",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=20),
    damage=Damage("1d12", 6, kind=LIMITED),
)
def m4510a5(c: Cast) -> None:
    """"His axe returns to him" needs nothing: a monster's gear is not
    modelled by name, so throwing it never took it away and there is nothing
    to come back. The same reading m355a1 took of its Requirement."""
    if c.strike():
        _crit_line(c, "2d12", 18)
        c.stunned(until=When.EOTNT)


@power(
    "m4510a6",
    level=11,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    trigger=_M4510_SURGED,
    on=Trigger(SurgeSpent, when=_neighbour_surged, text=_M4510_SURGED),
)
def m4510a6(c: Cast) -> None:
    """`SurgeSpent` is emitted from every site that decrements a surge, which
    is the only place this trigger can be read. The dispatcher aims a
    single-enemy row at whoever the event was about."""
    c.basic(who=c.me, on=c.target)


@power(
    "m4510a7",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.fight_on_at_zero()",),
)
def m4510a7(c: Cast) -> None:
    """Two gated modifiers rather than two holds put on and taken off, so
    hit points crossing back and forth are read at the roll. This is the
    sentence the six attack lines' "(+N while bloodied)" parentheticals come
    from, and it is written here once.

    What is dropped is "he does not die or fall unconscious until the end of
    his next turn": `c.revives_unless` only declares the fact for the policy
    and `c.reanimate` raises a corpse at one hit point, which is a different
    card -- nothing lets a creature keep acting below zero.
    """
    me = c.me

    def bleeding(_ctx: dict[str, Any]) -> bool:
        return _is_bloodied(c.world, me)

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=bleeding)
    c.bonus("damage", 2, until=When.ENCOUNTER, on=me, when=bleeding)

    def toll(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor == me and _is_bloodied(c.world, me):
            c.flat(5, on=me)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m5120
# ==========================================================================


_M5120_SCORCHED = "the m5120 takes acid, cold, fire, lightning or thunder damage"


def _element_on_me(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and bool(set(ev.types()) & set(_ELEMENTS))


@power(
    "m5120a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5120a0(c: Cast) -> None:
    """A gated damage modifier, so the extra rides the blow it belongs to and
    is read when the damage is rolled rather than when the trait arms."""
    me = c.me

    def on_the_floor(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.is_(Condition.PRONE, on=who)

    c.bonus("damage", 7, until=When.ENCOUNTER, on=me, when=on_the_floor)


@power(
    "m5120a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 5),
)
def m5120a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5120a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    requires=_is_bloodied,
    requires_text="the m5120 must be bloodied",
)
def m5120a2(c: Cast) -> None:
    """Two swings through the row that prints them, so its attack and damage
    lines stay in one place."""
    for _ in range(2):
        c.use_power("m5120a1", on=c.target)


@power(
    "m5120a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d10", 9, kind=LIMITED),
)
def m5120a3(c: Cast) -> None:
    """The printed Effect *is* a charge, so `charges=True` -- the row swings
    this line in place of a basic attack and is otherwise refused from every
    distance a charge is for."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5120a4",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("3d8", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5120a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5120a5",
    level=11,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
)
def m5120a5(c: Cast) -> None:
    """No damage line at all: the fall is the whole of the hit."""
    if c.strike():
        c.prone()


@power(
    "m5120a6",
    level=11,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5120_SCORCHED,
    on=Trigger(DamageApplied, when=_element_on_me, text=_M5120_SCORCHED),
)
def m5120a6(c: Cast) -> None:
    """It learns the last thing that hurt it, and only one at a time.

    "Until the end of the encounter or until it uses this again" cannot be
    `c.resist`, whose hold is anonymous: a second use would have no way to
    find the first and the two would stack. The entry is written under a
    label instead and handed back by the hold that took it.
    """
    ev = c.trigger
    kinds = [k for k in _ELEMENTS if k in set(getattr(ev, "types", lambda: ())())]
    if kinds:
        _resist_until_replaced(c, kinds[0], 10)


# ==========================================================================
# m5170
# ==========================================================================


_M5170_FELLED = "the m5170 drops to 0 hit points for the first time"


@power(
    "m5170a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5170a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m5170a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.speed_while_squeezing()", "c.no_advantage(squeezing=)"),
)
def m5170a1(c: Cast) -> None:
    """Squeezing is three things and this card waives all three; one of them
    can be said.

    The -5 is a number and is cancelled by a number of the same size, gated
    on the condition so nothing has to remember to put it back.
    `Condition.SQUEEZING` carries neither a speed modifier nor an advantage
    grant for the other two to override -- the halved speed is applied by the
    movement code and the grant is read off the condition table by
    `query.grants_ca`, which has no modifier hook.
    """
    me = c.me

    def folded(_ctx: dict[str, Any]) -> bool:
        return c.is_(Condition.SQUEEZING, on=me)

    c.bonus("attack", 5, until=When.ENCOUNTER, on=me, kind="untyped", when=folded)


@power(
    "m5170a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("", 10, dtype=DamageType.ACID, kind=MINION),
)
def m5170a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5170a3",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5170_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M5170_FELLED),
)
def m5170a3(c: Cast) -> None:
    """One of its own gets up as this one goes down.

    "A dead m5170 within 10 squares" is read off the entity list rather than
    `c.allies`, which filters out the dead -- and the dead are the only
    candidates this row has. `_same_stock` compares the ref the loader
    spawned each from, which is the only thing saying two creatures are the
    same sort.

    "The first time" needs a guard, because `Dropped` is emitted for dying as
    well as for dead and a minion can be put down more than once in a fight
    if something raises it.
    """
    me = c.me
    if _holding_label(c, f"{c.ref} spent"):
        return
    corpses = sorted(
        other
        for other in creatures(c.world)
        if other != me and not alive(c.world, other) and _same_stock(c.world, me, other)
    )
    for other in corpses:
        if c.reanimate(on=other, team=team(c.world, me)):
            c.effect(f"{c.ref} spent", until=When.ENCOUNTER, on=me)
            _put_beside(c, other, me)
            return


# ==========================================================================
# m5334
# ==========================================================================


_M5334_FELLED = "the m5334 drops to 0 hit points"


@power(
    "m5334a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5334a0(c: Cast) -> None:
    """Whoever it has hold of is read before each step, because the drag is
    what the movement does to them and the grab outlives the move.

    `Moved` is the one movement event carrying both ends of a step, so the
    captive is set down beside where the creature finished. The opportunity
    attack the printed line waives is laid at the same moment -- a hold with
    no duration to wait for, since it is spent inside the step.
    """
    me, ref = c.me, c.ref

    def drag(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        for who in sorted(_holding(c.world, me)):
            c.no_provoke(from_=who, on=me, until=When.EOT)
            if not c.adjacent(who):
                _put_beside(c, who, me)

    c.watch(Moved, drag, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5334a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("", 10, kind=MINION),
)
def m5334a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _hands_empty(world: World, eid: int) -> bool:
    """The printed Requirement on m5334a2: not already holding somebody."""
    return not _holding(world, eid)


@power(
    "m5334a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("", 10, kind=MINION),
    requires=_hands_empty,
    requires_text="the m5334 must not have a creature grabbed",
)
def m5334a2(c: Cast) -> None:
    """Whether it has hold of anybody changes with every escape, so the gate
    is a function rather than a remembered flag."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5334a3",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=14),
    trigger=_M5334_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M5334_FELLED),
)
def m5334a3(c: Cast) -> None:
    """The card names the domination by an id belonging to another stat
    block; what it describes is the ordinary condition, so the condition is
    what is applied and nothing reaches across.

    No damage line at all: the hold is the whole of the hit.
    """
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


# ==========================================================================
# m5385
# ==========================================================================


@power(
    "m5385a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m5385a0(c: Cast) -> None:
    """An aura 2 for the board to draw, and a toll for starting a turn in it.

    Not the membership helper: what this charges is paid once at a turn's
    beginning and what it lays keeps its own clock after that. "Until the end
    of its next turn" is the *enemy's* clock, which is `When.EOTNT`.
    """

    def toll(who: int) -> None:
        _defences_down(c, who, 2, When.EOTNT)
        if _is_bloodied(c.world, who):
            c.flat(5, dtype=DamageType.POISON, on=who)

    _toll_on_entering_turn(c, 2, toll)


@power(
    "m5385a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d6", 6),
)
def m5385a1(c: Cast) -> None:
    """"Ongoing 5 poison damage and a -2 penalty to attack rolls (save ends
    both)" is one printed sentence, so the penalty rides the burn's hold."""
    if not c.strike():
        return
    c.hit()
    held = c.condition(until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON))
    _one_save_for_both(c, held, c.penalty("attack", 2, until=When.ENCOUNTER))


@power(
    "m5385a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m5385a2(c: Cast) -> None:
    """Two swings through the row that prints them."""
    for _ in range(2):
        c.use_power("m5385a1", on=c.target)


@power(
    "m5385a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("4d10", 3, kind=LIMITED),
)
def m5385a3(c: Cast) -> None:
    """Bloodied swaps the duration rather than adding a second condition, so
    one call carries both conditions and the clock is picked first -- two
    separate holds would be two saving throws where the card prints one."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    bleeding = victim is not None and _is_bloodied(c.world, victim)
    c.condition(
        Condition.WEAKENED,
        Condition.SLOWED,
        until=When.SAVE_ENDS if bleeding else When.EONT,
    )


# ==========================================================================
# m5556
# ==========================================================================


_M5556_SHOT = "an enemy within 10 squares hits the m5556 with a ranged or area attack"


def _shot_at_me(world: World, me: int, ev: Hit) -> bool:
    if ev.target != me or distance_between(world, me, ev.attacker) > 10:
        return False
    return _reach_kind(ev).split("_")[0] in ("ranged", "area")


@power(
    "m5556a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 5),
)
def m5556a0(c: Cast) -> None:
    """One creature or two, and against a single one the declared line is
    rolled twice -- which is what "it can make this attack twice against that
    creature" says, and the reason the header takes up to two.

    "If it has fewer than two creatures grabbed" is counted off the hold
    relation rather than remembered, because a grab ends between one swing
    and the next. The escape DC has nowhere to go: a grab is a relation here
    and there is no contest to put a number in.
    """
    victim = c.target
    if victim is None:
        return
    for _ in range(2 if c.first and c.last else 1):
        if not alive(c.world, victim):
            return
        if c.strike(on=victim):
            c.hit(on=victim)
            if len(_holding(c.world, c.me)) < 2:
                c.grab(on=victim, dc=19)


@power(
    "m5556a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("5d8", 13),
    requires=_has_hold,
    requires_text="the m5556 must be grabbing a creature",
)
def m5556a1(c: Cast) -> None:
    """"One creature grabbed by the m5556" is narrower than any `Target` can
    say, so the Requirement carries the caster's half and the body picks."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m5556a1: which of them it dashes down") if held else None
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.prone(on=victim)
    c.escape(on=victim, auto=True)


@power(
    "m5556a2",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5556_SHOT,
    on=Trigger(Hit, when=_shot_at_me, text=_M5556_SHOT),
)
def m5556a2(c: Cast) -> None:
    """The run is at the creature that shot, which is read off the trigger
    rather than off `ev.targets`: an immediate reaction declared with no
    target has none to read."""
    who = getattr(c.trigger, "attacker", None)
    if who is not None and alive(c.world, who):
        c.charge_at(who)


# ==========================================================================
# m5565
# ==========================================================================
#
# All five of this block's rows tell their story under an id belonging to a
# stat block a level below. The creature being described is this one, so each
# row is filed under its own ref and nothing on the other block is reached.


_M5565_LAPSED = "m5565a0 lapsed"
_M5565_MISSED = "an enemy misses the m5565 with a melee attack"


@power(
    "m5565a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m5565a0(c: Cast) -> None:
    """An odd die goes through the image; an even one finds the creature.

    The `Hit` is answered in its interrupt window and the *result* is cleared
    rather than the event cancelled: `resolve.attack` reads `result.hit` back
    in the resolve callback and emits a `Miss` in the `Hit`'s place when the
    two disagree, so every rider hung on the hit goes with it.

    "A melee or a ranged attack" is those two range kinds and no others --
    `by_melee` counts a close burst as melee, which would let this trait turn
    aside a blast.
    """
    me, ref = c.me, c.ref

    def veil(ev: Hit) -> None:
        if ev.target != me or _reach_kind(ev) not in _WEAPON_RANGES:
            return
        result = getattr(ev, "result", None)
        if result is None or _holding_label(c, _M5565_LAPSED):
            return
        if result.natural % 2:
            result.hit = False
        else:
            c.effect(_M5565_LAPSED, until=When.SONT, on=me)

    c.watch(Hit, veil, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=ref)


@power(
    "m5565a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5565a1(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m5565a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d8", 3),
)
def m5565a2(c: Cast) -> None:
    """"Can push" is an option the creature always takes: a monster's row has
    nobody to ask."""
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5565a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d10", 8),
)
def m5565a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5565a4",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    trigger=_M5565_MISSED,
    on=Trigger(Miss, when=_missed_me_in_melee, text=_M5565_MISSED),
)
def m5565a4(c: Cast) -> None:
    """The dispatcher aims a single-enemy row at whoever the event was about,
    so "the triggering enemy" needs nothing read off the trigger."""
    c.push(1)


# ==========================================================================
# m5906
# ==========================================================================


@power(
    "m5906a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.terrain('natural world')",),
)
def m5906a0(c: Cast) -> None:
    """Every hit point back at the top of each turn, as long as it is not yet
    down -- "has at least 1 hit point" is `hp > 0` and not `alive`, which is
    the printed sentence saying it does not knit itself together once felled.

    "While in the natural world" is dropped: `c.terrain` answers words the
    encounter sets and there is no plane among them, so gating on one would
    make the trait false in every fight instead of in the few the card means.
    """
    me = c.me

    def knit(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.heal(max(1, health.max_hp - health.hp), on=me)

    c.watch(TurnStart, knit, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5906a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5906a1(c: Cast) -> None:
    """Four conditions it cannot take, forced movement it does not feel, and
    ground that does not slow it. "Challenging terrain" is difficult terrain
    by another name here, so `c.ignores_difficult` with no `kind` covers
    both."""
    me = c.me
    c.immune(
        Condition.IMMOBILIZED,
        Condition.RESTRAINED,
        Condition.SLOWED,
        Condition.PRONE,
        on=me,
        until=When.ENCOUNTER,
    )
    c.immovable(on=me, until=When.ENCOUNTER)
    c.ignores_difficult(on=me, until=When.ENCOUNTER)


@power(
    "m5906a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d6", 5),
)
def m5906a2(c: Cast) -> None:
    """Prone is asked *before* the fall, which is what "if the target is
    already prone" means -- after it, every hit would qualify."""
    if not c.strike():
        return
    down = c.is_(Condition.PRONE)
    c.hit()
    if down:
        c.dazed(until=When.EONT)
    else:
        c.prone()


@power(
    "m5906a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
)
def m5906a3(c: Cast) -> None:
    """Two swings through the row that prints them."""
    for _ in range(2):
        c.use_power("m5906a2", on=c.target)


@power(
    "m5906a4",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d8", 10, half_on_miss=True),
)
def m5906a4(c: Cast) -> None:
    """The printed target is "creatures in the blast", which is both sides.
    The Miss line slides as well as halving, so the branch is written out --
    `half_on_miss` is declared data and no line of the engine reads it."""
    if c.strike():
        c.hit()
        c.slide(4)
        c.prone()
    else:
        c.hit(half=True)
        c.slide(2)


@power(
    "m5906a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5906a5(c: Cast) -> None:
    """Walking through whoever is in the way is `c.overrun`, which is the
    printed line and reports who was trampled, so "each time it enters an
    enemy space for the first time" is the list it hands back -- each name
    once, which is what "for the first time" asks for."""
    for who in c.overrun():
        if team(c.world, who) is not team(c.world, c.me) and alive(c.world, who):
            use(c.world, c.me, "m5906a2", targets=[who], spend=False)


@power(
    "m5906a6",
    level=11,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.dismount()",),
)
def m5906a6(c: Cast) -> None:
    """It shakes, and whoever is holding on rolls for it.

    "Creature's choice" of skill is settled by which of the two that creature
    is actually better at -- `c.passive` is ten plus the modifier, which is
    the only thing a monster's chooser has to go on, and rolling both would
    be two checks where the card gives one.

    Letting go of a grab is `c.escape(auto=True)` aimed at the m5906, since
    it is the grabbed one here. Getting a rider out of the saddle has no
    counterpart -- `c.ride` gets on and nothing gets off -- so that half is
    named.
    """
    me = c.me
    rider = c.rider()
    holders = sorted(set(c.grabbed_by(on=me)))
    for who in holders:
        skill = max(
            ("acrobatics", "athletics"), key=lambda s: c.passive(s, of=who)
        )
        if not c.check(skill, 19, who=who):
            c.escape(on=me, auto=True)
            c.fall(1, on=who)
            _put_beside(c, who, me)
    if rider is not None:
        skill = max(
            ("acrobatics", "athletics"), key=lambda s: c.passive(s, of=rider)
        )
        if not c.check(skill, 19, who=rider):
            c.fall(1, on=rider)
            _put_beside(c, rider, me)


# ==========================================================================
# m6055
# ==========================================================================


_M6055_FLOORED = "the m6055 knocks an enemy prone"


def _i_knocked_one_down(world: World, me: int, ev: ConditionApplied) -> bool:
    """`ConditionApplied` names its subject `target`, so `about_me` is false
    on it forever -- the source is read explicitly instead."""
    if ev.source != me or ev.condition is not Condition.PRONE:
        return False
    theirs = team(world, ev.target)
    return theirs is not None and theirs is not team(world, me)


@power(
    "m6055a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d12", 5),
)
def m6055a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6055a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one prone enemy",
        conditions=frozenset({Condition.PRONE}),
    ),
    keywords=[Keyword.FEAR, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d12", 10),
)
def m6055a1(c: Cast) -> None:
    """"+2 bonus to all defences" prints no type word, so the bonus is untyped
    and `kind=` is left off."""
    if not c.strike():
        return
    c.hit()
    for shield in ("ac", "fort", "ref", "will"):
        c.bonus(shield, 2, until=When.EONT, on=c.me)


@power(
    "m6055a2",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6055_FLOORED,
    on=Trigger(ConditionApplied, when=_i_knocked_one_down, text=_M6055_FLOORED),
)
def m6055a2(c: Cast) -> None:
    """Declared with no target: m6055a1's own target line admits only a prone
    enemy, which is the creature this trigger just put there.

    The five it costs comes off first, because the printed Effect spends the
    blood before the swing.
    """
    c.flat(5, on=c.me)
    use(c.world, c.me, "m6055a1", spend=False)


# ==========================================================================
# m6086
# ==========================================================================


_M6086_STRUCK = "an enemy hits the m6086"
_M6086_SPLASHED = "a close or an area attack hits the m6086"


@power(
    "m6086a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6086a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and a toll for starting a turn in
    it."""
    _toll_on_entering_turn(c, 1, lambda who: c.flat(10, on=who))


@power(
    "m6086a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.squeeze_through()",),
)
def m6086a1(c: Cast) -> None:
    """A swarm's three habits: it shares its square, it will not be shoved,
    and it pours through gaps.

    `c.shares_space(difficult=True)` is both halves of the first sentence --
    anyone may stand in its square and it costs them. The second is
    `c.resist_forced` gated on how the shove arrived, because "by melee or
    ranged attacks" leaves close and area ones working.

    Squeezing through any opening one of its creatures fits is dropped:
    `Condition.SQUEEZING` is a state a creature is put into and nothing asks
    whether a gap is passable for it at all.
    """
    me = c.me
    c.shares_space(on=me, until=When.ENCOUNTER, difficult=True)

    def shoved_by_a_swing(ctx: dict[str, Any]) -> bool:
        from combat_engine.engine.dsl import get

        p = get(ctx.get("power") or "")
        return p is not None and p.reach.kind in _WEAPON_RANGES

    c.resist_forced(99, on=me, until=When.ENCOUNTER, when=shoved_by_a_swing)


@power(
    "m6086a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 13),
)
def m6086a2(c: Cast) -> None:
    """"One creature and each creature in the m6086's space" is one declared
    target and a list the body adds to: `Target` counts and filters by side
    and cannot say "and also whoever is standing inside me". Added once for
    the whole use -- `c.first` -- or each arrival would be added again per
    target."""
    if c.first:
        for who in sorted(c.in_squares([c.here], side="any")):
            if who != c.me and who != c.target:
                c.add_target(who)
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m6086a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6086a3(c: Cast) -> None:
    """"Recharge when first bloodied" is a board state rather than a die; the
    number stays in the header because that is what the card shows."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    c.shift(c.speed_of())


@power(
    "m6086a4",
    level=11,
    usage=AT_WILL,
    once_per_round=True,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6086_STRUCK,
    on=Trigger(Hit, when=targets_me, text=_M6086_STRUCK),
    todo=("etl.monster.summon_ref()",),
)
def m6086a4(c: Cast) -> None:
    """Pieces of it break off and act on their own, and the spec prints no id
    for the thing they are -- so there is nothing to put on the board. The
    d4 and the worthless experience are the same sentence and wait on the
    same thing."""


@power(
    "m6086a5",
    level=11,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M6086_SPLASHED,
    on=Trigger(Hit, when=_close_or_area, text=_M6086_SPLASHED),
)
def m6086a5(c: Cast) -> None:
    """The blow is softened rather than stopped, which only an interrupt can
    do -- `c.halve` answers the damage that has been rolled and not yet
    dealt."""
    c.halve(c.trigger)


# ==========================================================================
# m6087
# ==========================================================================


_M6087_SMELT_BLOOD = "an enemy within 3 squares is bloodied by an attack"


def _neighbour_bled(world: World, me: int, ev: Bloodied) -> bool:
    who = ev.actor
    if who == me or team(world, who) is team(world, me):
        return False
    return ev.source is not None and distance_between(world, me, who) <= 3


@power(
    "m6087a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("", 11, kind=MINION),
)
def m6087a0(c: Cast) -> None:
    """"Melee 0" is written as printed: it reaches only what shares its
    square, which is where m6087a1 puts it."""
    if c.strike():
        c.hit()


@power(
    "m6087a1",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6087_SMELT_BLOOD,
    on=Trigger(Bloodied, when=_neighbour_bled, text=_M6087_SMELT_BLOOD),
    dropped=("c.shift(into_space=)",),
)
def m6087a1(c: Cast) -> None:
    """`Bloodied` carries `source`, so "by an attack" is the difference
    between a blow and a burn ticking somebody past the line.

    Landing *in* the triggering enemy's square is what is dropped: `c.shift`
    takes a destination and the grid refuses an occupied one, and nothing
    makes an exception for a Tiny creature the way the printed line does. The
    shift still happens, so the row plays and ends up beside its victim.
    """
    who = getattr(c.trigger, "actor", None)
    if who is None or not alive(c.world, who):
        return
    here = c.world.get(who, Position)
    if here is None or not c.shift(3, to=here.square):
        c.shift(3)


# ==========================================================================
# m6142
# ==========================================================================


@power(
    "m6142a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("", 12, kind=MINION),
)
def m6142a0(c: Cast) -> None:
    """"Or 14 if the target is prone" is a second expression, so the larger
    one is dealt by hand -- the header holds the number the card leads with,
    which is what `cards.py` checks and what a rescaling reads."""
    if not c.strike():
        return
    if c.is_(Condition.PRONE):
        c.flat(14)
    else:
        c.hit()


@power(
    "m6142a1",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m6142a1(c: Cast) -> None:
    """An Effect line with no attack roll in it: the shove simply happens."""
    c.push(1)


# ==========================================================================
# m6407
# ==========================================================================


_M6407_FELLED = "the m6407 drops to 0 hit points"


@power(
    "m6407a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.deny_space()",),
)
def m6407a0(c: Cast) -> None:
    """"An enemy cannot enter its space by any means" is the whole of the
    trait and there is nothing to say it with. `c.shares_space` is the
    opposite operation and has no negative form, and the exemption the card
    is actually buying -- against teleport, against phasing, against a
    creature two sizes smaller -- is exactly what the grid's own rule already
    allows."""


@power(
    "m6407a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.swap_initiative(a, b)",),
)
def m6407a1(c: Cast) -> None:
    """"Surprised" is a condition the engine carries, so "cannot be
    surprised" is an immunity and is exact.

    Rearranging the order is not: `c.swap_initiative` trades the caster's own
    slot for an ally's, and this card moves two other creatures.
    """
    c.immune(Condition.SURPRISED, on=c.me, until=When.ENCOUNTER)


@power(
    "m6407a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6407a2(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m6407a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d12", 11),
)
def m6407a3(c: Cast) -> None:
    """One creature or two, and nothing rides on which: the card prints no
    clause that cares, so each target takes the declared line once."""
    if c.strike():
        c.hit()


@power(
    "m6407a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d8", 9, kind=LIMITED, half_on_miss=True),
)
def m6407a4(c: Cast) -> None:
    """The printed target is "creatures in the burst", which is both sides."""
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m6407a5",
    level=11,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=14),
)
def m6407a5(c: Cast) -> None:
    """No damage line at all: the opening is the whole of the hit, and it is
    granted to everybody rather than to the caster -- the card names nobody,
    which is what `to="all"` means."""
    if c.strike():
        c.grants_advantage(until=When.SAVE_ENDS, to="team")


@power(
    "m6407a6",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6407_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M6407_FELLED),
)
def m6407a6(c: Cast) -> None:
    """Three of them step out of what it was, and the spec does print the id,
    so they are summoned rather than named as a gap.

    `c.summon` makes one creature per call, which is three calls; it puts
    each in the initiative order as well, and acting on this creature's own
    count is as near as that gets. Worth no experience is a scoring line and
    not a combat one.
    """
    for _ in range(3):
        c.summon("m6405", team=team(c.world, c.me))


# ==========================================================================
# m6536
# ==========================================================================


#: m6536a0's three bands, highest roll last. Read by the trait and by
#: nothing else.
_M6536_BANDS = ((10, "m6536a5"), (17, "m6536a4"), (20, "m6536a3"))


@power(
    "m6536a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6536a0(c: Cast) -> None:
    """One of three rows at a time, and the die says which.

    Written as bans on the other two rather than a grant of the chosen one:
    all three are its own rows and `c.forbid` is the operation that takes one
    away. The holds are kept in the closure so a new roll can end the old
    ones -- laid on a duration instead they would overlap the roll that
    replaced them, and two bans on one row is one row too many.

    "When he rolls initiative" is when the trait arms, which is the only
    moment in a fight that is.
    """
    me = c.me
    bans: list[Effect] = []

    def roll_for_it() -> None:
        for eff in bans:
            c.world.effects.end(eff, "a new roll")
        bans.clear()
        n = c.roll("1d20")
        chosen = next(ref for cap, ref in _M6536_BANDS if n <= cap)
        for _, ref in _M6536_BANDS:
            if ref == chosen:
                continue
            held = c.forbid(ref, on=me, until=When.ENCOUNTER)
            if held is not None:
                bans.append(held)

    def at_end(ev: TurnEnd) -> None:
        if ev.actor == me and not ev.ghost:
            roll_for_it()

    roll_for_it()
    c.watch(TurnEnd, at_end, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6536a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d12", 9),
)
def m6536a1(c: Cast) -> None:
    """A critical replaces the damage with a flat 33 and two rolls, and then
    pays half of it again a turn later.

    Both halves are dealt flat: the critical line is rolled, and the engine's
    own rule maxes declared dice, which would read the wrong number off this
    header. The second packet is hung on the caster's next turn beginning,
    which is the clock the card names.
    """
    if not c.strike():
        return
    if not c.crit:
        c.hit()
        return
    victim = c.target
    c.flat(33 + c.roll("2d12") + c.roll("3d10"))
    if victim is None:
        return
    me, ref = c.me, c.ref

    def later(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not alive(c.world, victim):
            return
        c.flat(c.roll("2d12") + c.roll("3d10"), on=victim)

    c.watch(TurnStart, later, until=When.SONT, once=True, on=me, label=f"{ref} crit")


@power(
    "m6536a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d8", 10, dtype=DamageType.FIRE),
)
def m6536a2(c: Cast) -> None:
    """"Melee 10" is written as printed. It is a strange line and the levels
    below have met it twice; what it means is a reach of ten rather than a
    ranged attack, and rewriting it as `Ranged(10)` would change which
    keywords and which opportunity rules the row plays under."""
    if c.strike():
        c.hit()


@power(
    "m6536a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
)
def m6536a3(c: Cast) -> None:
    """A melee blow, and then a chain that walks until it misses.

    The secondary is a second roll against a different defence, so its
    printed +14 is trimmed by hand the way `Attack.bonus_for` trims the
    header's. Each link is centred on whoever was hit last and a creature
    already struck is not offered again -- otherwise a run of hits against
    the only enemy in range never ends.
    """
    victim = c.target
    c.use_power("m6536a1", on=victim)
    bonus = c.world.scaling.trim(14, c.level)
    struck: set[int] = set()
    centre = victim if victim is not None else c.me
    while True:
        near = sorted(
            foe
            for foe in c.enemies()
            if foe not in struck
            and alive(c.world, foe)
            and distance_between(c.world, centre, foe) <= 10
        )
        if not near:
            return
        foe = near[0]
        if not c.attack(bonus, REF, on=foe):
            return
        c.damage("1d8", 5, dtype=DamageType.LIGHTNING, on=foe)
        struck.add(foe)
        centre = foe


@power(
    "m6536a4",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m6536a4(c: Cast) -> None:
    """Declared with no target because the caster is not an ally of himself
    and the printed burst takes allies: the list is read off the ring here
    and he is added to it by name."""
    me = c.me
    c.teleport(10, who=me)
    for friend in sorted(c.within(1, side="ally")):
        if friend != me:
            c.teleport(10, who=friend)


@power(
    "m6536a5",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.COLD],
)
def m6536a5(c: Cast) -> None:
    """Extra dice on the *next* attack, which is not a duration -- so it is a
    one-shot watch that spends itself on the first melee blow to land rather
    than a modifier, which could not hold dice anyway."""
    me, ref = c.me, c.ref

    def bite(ev: Hit) -> None:
        if ev.attacker != me or _reach_kind(ev) != "melee":
            return
        c.damage("1d6", dtype=DamageType.COLD, on=ev.target, detail=ref)

    c.watch(Hit, bite, until=When.ENCOUNTER, once=True, on=me, label=ref)


# ==========================================================================
# m6643
# ==========================================================================


#: m6643a0's track, each step naming what the next failure brings. The
#: sixth failure is the end of it and is held for the fight.
_M6643_TRACK = (Condition.SLOWED, Condition.IMMOBILIZED, Condition.STUNNED)


def _m6643_step(c: Cast, who: int, stage: int, failures: int) -> None:
    """One rung of the poison's ladder.

    `escalate` runs on a *failed* save and is handed the effect, so the step
    ends the hold it came from and applies the next one -- two holds at once
    would be two saving throws against one printed sentence.

    The first two failures change the condition and the rest only count;
    the sixth makes the stun last the encounter, which is what "stunned for
    4 hours" is worth on a board that ends with the fight.
    """
    condition = _M6643_TRACK[min(stage, len(_M6643_TRACK) - 1)]
    if failures >= 6:
        c.condition(condition, until=When.ENCOUNTER, on=who)
        return

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "the poison deepens")
        _m6643_step(c, who, stage + 1, failures + 1)

    c.condition(condition, until=When.SAVE_ENDS, on=who, escalate=worsen)


@power(
    "m6643a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("", 4, kind=MINION),
)
def m6643a0(c: Cast) -> None:
    """Two expressions on the hit and the header holds the untyped one, so
    the poison five is a flat packet beside it."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.flat(5, dtype=DamageType.POISON)
    _m6643_step(c, victim, 0, 0)


# ==========================================================================
# m6664
# ==========================================================================


@power(
    "m6664a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6664a0(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m6664a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 12),
)
def m6664a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6664a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m6664a2(c: Cast) -> None:
    """Two swings through the row that prints them."""
    for _ in range(2):
        c.use_power("m6664a1", on=c.target)


@power(
    "m6664a3",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6664a3(c: Cast) -> None:
    """Standing tall buys a square of reach and a square of threat, and both
    come down when it moves -- so the holds are torn off the first step it
    takes rather than waiting for the printed duration to run.

    `c.reach` with a ref sets how far one row carries; `c.threatens` is the
    opportunity window, which is a different question and needs its own
    call.
    """
    me, ref = c.me, c.ref
    holds = [
        c.bonus("reach", 1, until=When.SONT, on=me),
        c.threatens(3, on=me, until=When.SONT),
    ]

    def down_again(ev: Any) -> None:
        if getattr(ev, "actor", None) != me:
            return
        for held in holds:
            if held is not None:
                c.world.effects.end(held, "it drops back down")

    c.watch(Moved, down_again, until=When.SONT, once=True, on=me, label=ref)


# ==========================================================================
# m941
# ==========================================================================


_M941_NEIGHBOUR_BLED = "an adjacent creature is bloodied"


def _neighbour_bloodied(world: World, me: int, ev: Bloodied) -> bool:
    who = ev.actor
    return who != me and distance_between(world, me, who) <= 1


@power(
    "m941a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 6),
)
def m941a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m941a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 3),
)
def m941a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10)


@power(
    "m941a2",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 3),
    trigger=_M941_NEIGHBOUR_BLED,
    on=Trigger(Bloodied, when=_neighbour_bloodied, text=_M941_NEIGHBOUR_BLED),
)
def m941a2(c: Cast) -> None:
    """"An adjacent creature" is either side, which is why the predicate
    compares distance and not teams -- only the burst narrows to enemies, and
    that is the card's own target line.

    A triggered burst picks its own targets: the dispatcher only aims a
    single-creature row off the trigger.
    """
    if c.strike():
        c.hit()


# ==========================================================================
# m947
# ==========================================================================


@power(
    "m947a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 6),
)
def m947a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m947a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    dropped=("compendium.attack_defence",),
)
def m947a1(c: Cast) -> None:
    """The card's declared attack comes out of extraction as "+12 vs ;" with
    no defence at all, so that half cannot be declared without inventing a
    number and is named instead. What plays is the sentence that survived
    intact: two basic attacks, one each against two different targets.

    Each swing names its victim, because `c.basic` without `on=` aims at the
    target being iterated, which on a two-target row is friendly-fire-shaped
    bookkeeping at best.
    """
    if not c.first:
        return
    for who in c.targets[:2]:
        if alive(c.world, who):
            c.basic(who=c.me, on=who)


@power(
    "m947a2",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m947a2(c: Cast) -> None:
    """Ten back for every melee blow that finds somebody already bleeding.

    Asked on `DamageApplied`, which is where attribution and the row that
    dealt it both live -- `detail` carries the ref, and the reach is a
    property of the row rather than of anything the event says. Bloodied is
    read after the blow, which is what "damages a bloodied foe" means when a
    hit can do the bloodying itself.
    """
    me = c.me

    def feed(ev: DamageApplied) -> None:
        if not _damaged_a_foe(c.world, me, ev):
            return
        from combat_engine.engine.dsl import get

        p = get(ev.detail or "")
        if p is None or p.reach.kind != "melee":
            return
        if _is_bloodied(c.world, ev.target):
            c.heal(10, on=me)

    c.watch(DamageApplied, feed, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m947a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m947a3(c: Cast) -> None:
    """`opportunity` rides on both the attack and the damage context, so both
    halves can be gated rather than held and taken off."""
    me = c.me

    def an_opening(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity"))

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=an_opening)
    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=an_opening)


@power(
    "m947a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m947a4(c: Cast) -> None:
    """The printed reach is two squares and the window is widened to match
    it: `c.threatens` sets the distance and nothing else, which is the whole
    of this trait."""
    c.threatens(2, on=c.me, until=When.ENCOUNTER)
