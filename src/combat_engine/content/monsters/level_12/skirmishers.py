"""Monster abilities, level 12: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=17)` and `Damage("2d4", 6)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the eleven levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; a stat block that prints no range at all means melee
1; a printed "Range 5/10" is a normal range and a long one and the normal
one is what `Range` holds; a printed critical line is the *extra* dice on
top of the maximum the engine already deals, added with `c.flat(c.roll(...))`
so it is rolled rather than maximised; and a helper written for an earlier
level is imported rather than copied.

Five things this file had to settle.

**"A spear attack or a javelin attack" is a choice of row and a choice of
target together.** Two of m2948's rows print it and each wants to know what
was picked and whether it landed, which `use` cannot say -- it reports
whether a row could be used. So `_either_swing` offers the legal pairs, uses
the row that prints the attack, and counts the hits off the bus.

**A death throe that leaves something behind outlives the creature by one
line of engine.** `Effects.bereave` ends everything a dead creature is the
source of that expires at the end of the encounter, and it runs *after*
`Dropped` is announced -- so a fire left burning by m3057a1 and m3058a3 is
swept away the instant it is lit. The zone's own effect is handed to the
zone entity as its source, which is the honest reading of a fire that is no
longer anybody's: nothing is faked, and the printed "lasts until the end of
the encounter" then means what it says.

**"When its next turn would occur" is the ghost slot.** `Encounter.advance`
ticks a dead creature's place in the order, which is exactly the printed
clock -- but only while something is still clocked on it, and `bereave` has
just cleared the corpse. So the hold that keeps the slot open is laid on the
*zone* and clocked on the dead creature: owned by the fire, measured against
its maker, and swept away by neither.

**A bonus "while bloodied" printed on the attack line is not a modifier.**
m678a1's "+17 vs AC (+19 while bloodied)" is one attack line with two
numbers, so the header keeps the printed 17 -- which is what rescales -- and
the two is handed to `c.strike(plus=...)` for the roll it belongs to. Two
modifiers of one kind do not add, and this way there is only ever one.

**"Immediately after hitting with a melee attack" is the log.** No event
carries "the attack that just resolved", and a Requirement is handed only
`(world, eid)`. `_just_hit_in_melee` reads backwards to the most recent
`Hit` or `Miss` and nothing earlier, which is what "immediately" means.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_06.skirmishers import _after_moving, _renew
from combat_engine.content.monsters.level_07.lurkers import _shift_beside
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.brutes import _is_bloodied
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe

#: The four defences, for a printed "+2 bonus to all defenses". Four
#: modifiers, because the engine holds each defence separately and one
#: named "all defenses" would be a bonus to nothing.
from combat_engine.content.monsters.level_10.lurkers import EVERY_DEFENCE
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
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
    Damage,
    DamageType,
    Dropped,
    Effect,
    Hit,
    Keyword,
    Melee,
    Miss,
    Movement,
    PowerUsed,
    Ranged,
    TurnStart,
    Usage,
    When,
    World,
    by_melee,
    distance,
    power,
    use,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, distance_between, enemies
from combat_engine.engine.triggers import Trigger, about_me


def _amphibious(c: Cast) -> None:
    """Breathes water, and fights better in it against those that cannot.

    The bonus is a gated modifier rather than a hold put on and taken off,
    because both halves of the printed condition -- where the fight is and
    what the victim is -- are read at the moment of the roll. Breathing
    itself is narrative: the engine has no drowning for it to prevent.
    """
    me = c.me

    def against_a_landlubber(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            c.terrain("aquatic")
            and victim is not None
            and not c.is_kind("aquatic", on=victim)
        )

    c.bonus(
        "attack", 2, until=When.ENCOUNTER, on=me, kind="untyped",
        when=against_a_landlubber,
    )
    c.note(f"{c.ref}: it can breathe underwater")


def _pyre(c: Cast, hatch: str = "") -> None:
    """The fire a dying elemental leaves behind, and what climbs out of it.

    Two things stand in the way of the printed sentence, and both are about
    the creature being dead by the time this runs.

    `Effects.bereave` ends everything a corpse is the *source* of that
    expires at the end of the encounter, and it runs after `Dropped` is
    announced -- so the zone would be lit and swept away in the same breath.
    The zone's own effect is therefore handed to the zone entity as its
    source: the fire belongs to itself once its maker is gone, which is what
    "lasts until the end of the encounter" has to mean here.

    "When the m3057's next turn would occur" is the ghost slot `Encounter`
    ticks for the dead, and it ticks only while something is still clocked
    on the corpse -- which `bereave` has just emptied. So a hold clocked on
    the dead creature is laid on the *zone*: owned by the fire, clocked on
    its maker, and therefore neither swept away nor forgotten. The slot then
    opens, the `TurnStart` announces it, and the printed sentence means what
    it says.

    The watch is spent by hand rather than with `once=True`, which reads
    "did the body do anything" off the length of the event log -- and
    `c.summon` emits nothing at all, so a once-only watch that summons never
    spends itself and hatches again every round. See the report.
    """
    me = c.me
    ground = c.area()
    zid = c.zone(ground, label=c.ref, until=When.ENCOUNTER)
    c.burns(zid, 5, DamageType.FIRE)
    held = dict(c.world.zones.all()).get(zid)
    if held is not None and held.effect is not None:
        held.effect.source = zid
    if not hatch:
        return
    c.world.effects.apply(zid, me, When.EONT, label=f"{c.ref} slot")
    armed: list[Effect] = []

    def hatching(ev: TurnStart) -> None:
        if ev.actor != me or not armed:
            return
        c.world.effects.end(armed[0], "it has hatched")
        free = sorted(
            sq
            for sq in ground
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
        )
        c.summon(hatch, at=free[0] if free else None)

    watch = c.watch(
        TurnStart, hatching, until=When.ENCOUNTER, on=zid, label=f"{c.ref} hatch"
    )
    watch.source = zid
    armed.append(watch)


def _either_swing(c: Cast, choices: dict[str, int]) -> tuple[int | None, bool]:
    """Swing one of two printed attacks and say who took it and whether it hit.

    Both the row and the target are the creature's choice, and the two are
    one decision: a spear reaches two squares and a javelin ten, so which
    rows are legal depends on who is being aimed at. `use` reports whether a
    row could be used and not whether it landed, so the hits are counted off
    the bus for as long as the swing is in the air -- the arrangement
    `_volley` settled three levels down.
    """
    me = c.me
    options = [
        (ref, foe)
        for ref, span in choices.items()
        for foe in sorted(c.enemies())
        if alive(c.world, foe) and c.distance(foe) <= span
    ]
    picked = c.choose(options, f"{c.ref}: which attack, and at whom") if options else None
    if picked is None:
        return None, False
    ref, victim = picked
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == ref:
            landed.append(ev.target)

    counter = c.watch(Hit, tally, until=When.EOT, on=me, label=f"{c.ref} tally")
    try:
        use(c.world, me, ref, targets=[victim], spend=False)
    finally:
        c.world.effects.end(counter, "the swing is over")
    return victim, victim in landed


def _fly_span(c: Cast) -> int:
    """How far "flies its speed" is, for a creature that has a fly speed."""
    moves = c.world.get(c.me, Movement)
    return (moves.modes.get("fly") if moves is not None else 0) or c.speed_of()


def _just_hit_in_melee(world: World, eid: int) -> bool:
    """Did the attack that just resolved land, and was it a melee one?

    "Usable immediately after hitting with a melee attack" is about the blow
    just struck and nothing earlier, and no event carries "the last attack".
    A Requirement is handed `(world, eid)` and no `Cast`, so the log is read
    backwards to the most recent outcome -- a `Hit` or a `Miss` -- and that
    one has to be this creature's and has to have landed.
    """
    for past in reversed(world.bus.log):
        if isinstance(past, Hit | Miss):
            return (
                isinstance(past, Hit)
                and past.attacker == eid
                and by_melee(world, eid, past)
            )
    return False


# ==========================================================================
# m2948
# ==========================================================================


#: The two attacks m2948 chooses between, with how far each reaches.
_M2948_SWINGS = {"m2948a0": 2, "m2948a1": 10}


@power(
    "m2948a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6),
)
def m2948a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2948a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 7),
)
def m2948a1(c: Cast) -> None:
    """Range 10/20: the header carries the short range, which is the only
    one `Range` holds and the one this can throw at without a penalty."""
    if c.strike():
        c.hit()


@power(
    "m2948a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m2948a2(c: Cast) -> None:
    """Either swing, with the hold and its aftereffect on top.

    Declared with no target: which row is used decides what is in range, so
    a target list chosen before the body runs would settle the choice the
    printed line leaves open.

    The Aftereffect hangs on the hold's own ending rather than on a clock --
    a save-ends effect that has been saved against is exactly when an
    aftereffect lands, and `on_end` is the only thing that fires then.

    The printed recharge is a sentence on top of the die the database files,
    and the two only ever agree to give the row back sooner.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    victim, landed = _either_swing(c, _M2948_SWINGS)
    if victim is None or not landed:
        return
    c.damage("2d6", on=victim, detail=c.ref)
    hold = c.immobilized(until=When.SAVE_ENDS, on=victim)
    if hold is not None:
        hold.on_end.append(lambda: c.slowed(until=When.SAVE_ENDS, on=victim))


@power(
    "m2948a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m2948a3(c: Cast) -> None:
    """Eight squares with a swing somewhere in them.

    The swing goes first where there is anything in range, because the move
    picks its own destination and one taken first can leave every target
    behind; with nobody in range it moves and then looks, which is the same
    printed sentence read the other way round.

    The waiver is blanket rather than the two cases the card names -- moving
    away from its target, and the ranged attack -- because `c.no_provoke`
    names a creature or everybody and cannot name a reason. It is the
    reading level 11 settled on for the same shape.
    """
    waiver = c.no_provoke(until=When.EOT)
    try:
        if c.within(10, side="enemy"):
            _either_swing(c, _M2948_SWINGS)
            c.move(8)
        else:
            c.move(8)
            _either_swing(c, _M2948_SWINGS)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the run is over")


@power(
    "m2948a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
)
def m2948a4(c: Cast) -> None:
    """No damage line: the mark it puts on somebody is what the hit is.

    The extra die is a rider on its own hits rather than a damage modifier:
    a modifier would add to whatever packet was already being dealt and
    would be paid on everybody, and the printed line is about this creature's
    attacks against this one victim.

    The second half is left as a note. Cover and concealment are computed
    between two positions at the moment of the attack, and `ignore_cover` is
    an argument to one roll rather than a state a creature can be put into,
    so there is nothing to hang "cannot benefit from cover or concealment"
    on. The same sentence m2947a4 left a level down; see the report.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return

    def sharper(ev: Hit) -> None:
        if ev.attacker == me and ev.target == victim:
            c.damage("1d6", on=victim, detail=c.ref)

    c.watch(Hit, sharper, until=When.EONT, on=me, label=c.ref)
    c.note("m2948a4: the target cannot benefit from cover or concealment")


# ==========================================================================
# m3057
# ==========================================================================


_M3057_FELL = "the m3057 drops to 0 hit points"


@power(
    "m3057a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d4", 6, dtype=DamageType.FIRE),
)
def m3057a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The printed "crit 4d4 + 14" is the maximum of the ordinary line
    -- which `c.damage` already deals on a critical -- plus 4d4 on top, and
    the extra is rolled with `c.flat` because `c.damage` would maximise that
    too."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("4d4"), dtype=DamageType.FIRE)


@power(
    "m3057a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d8", 5, dtype=DamageType.FIRE),
    trigger=_M3057_FELL,
    on=Trigger(Dropped, when=about_me, text=_M3057_FELL),
)
def m3057a1(c: Cast) -> None:
    """A death throe. The dispatcher offers it to a creature that is no
    longer alive, which is the only way a row of this shape fires, and
    `Dropped` names its subject `actor`.

    The fire is lit once for the whole burst rather than once per target,
    which is what `c.first` is for.
    """
    if c.target is not None and c.strike():
        c.hit()
    if c.first:
        _pyre(c, "m3058")


@power(
    "m3057a2",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m3057a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: reaching for it as it
    goes past costs you.

    `opportunity` rides on the `Hit` as a plain attribute, which is the only
    place it is recorded -- gating on the row's ref instead would catch a
    standard-action basic and miss a creature whose opportunity attack is
    something else.
    """
    me = c.me

    def seared(ev: Hit) -> None:
        if ev.target == me and getattr(ev, "opportunity", False):
            c.damage("3d6", dtype=DamageType.FIRE, on=ev.attacker, detail=c.ref)

    c.watch(Hit, seared, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3058
# ==========================================================================


_M3058_FELL = "the m3058 drops to 0 hit points"


@power(
    "m3058a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 5),
)
def m3058a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The printed line types only the burn, so the header carries no
    damage type and a creature resistant to fire still takes the five."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m3058a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3058a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3058a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m3058a2(c: Cast) -> None:
    """A pass: it comes down on somebody at some point during the flight.

    Declared with no target, because a target list is chosen before the body
    runs and the creature it swings at may be ten squares away when it
    starts. Which of its two attacks it makes is its own choice, and the
    blast is used through `use` so its printed line stays in one place.

    "Its speed" is the fly speed where there is one, which for this creature
    there is; `c.speed_of` reads the legs and would be the wrong number.
    """
    me = c.me
    waiver = c.no_provoke(until=When.EOT)
    try:
        c.move(_fly_span(c))
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the pass is over")
    ref = c.choose(["m3058a0", "m3058a1"], "m3058a2: which attack") or "m3058a0"
    if ref == "m3058a1":
        use(c.world, me, ref, spend=False)
        return
    prey = _adjacent_foe(c, c.ref)
    if prey is not None:
        use(c.world, me, ref, targets=[prey], spend=False)


@power(
    "m3058a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d8", 5, dtype=DamageType.FIRE),
    trigger=_M3058_FELL,
    on=Trigger(Dropped, when=about_me, text=_M3058_FELL),
)
def m3058a3(c: Cast) -> None:
    """The same death throe as m3057a1 with nothing climbing out of it."""
    if c.target is not None and c.strike():
        c.hit()
    if c.first:
        _pyre(c)


# ==========================================================================
# m678
# ==========================================================================


def _beside_an_enemy(world: World, eid: int) -> bool:
    return any(distance_between(world, eid, foe) <= 1 for foe in enemies(world, eid))


@power(
    "m678a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m678a0(c: Cast) -> None:
    _amphibious(c)


@power(
    "m678a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5),
)
def m678a1(c: Cast) -> None:
    """One attack line with two numbers on it: the header keeps the printed
    17, which is what rescales, and the two more it swings with while
    bloodied goes to the roll it belongs to rather than becoming a modifier
    that something else could fail to stack with."""
    if c.strike(plus=2 if c.bloodied(c.me) else 0):
        c.hit()
        c.ongoing(5)


@power(
    "m678a2",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_beside_an_enemy,
    requires_text="the m678 must be adjacent to an enemy",
)
def m678a2(c: Cast) -> None:
    """Three squares that have to finish beside the same creature, which is
    what `_shift_beside` is for: `c.shift` with no `to` offers the decider
    every square in range and would wander off."""
    near = sorted(foe for foe in c.enemies() if c.adjacent(foe))
    victim = c.choose(near, "m678a2: which enemy it circles") if near else None
    if victim is not None:
        _shift_beside(c, victim, 3)


@power(
    "m678a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_bloodied,
    requires_text="the m678 must be bloodied",
)
def m678a3(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m76
# ==========================================================================


@power(
    "m76a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 4),
)
def m76a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m76a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4, kind=LIMITED),
)
def m76a1(c: Cast) -> None:
    """The printed "recharges after the use of m76a4" is a sentence on top
    of the die the database files, and the two only ever agree to give the
    row back sooner. `PowerUsed` is announced for every use, which is the
    only event that says a row was taken rather than that it landed."""
    me = c.me
    _recharge_on(c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m76a4")
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)


@power(
    "m76a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d4", 6),
)
def m76a2(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is the only one
    `Range` holds."""
    if c.strike():
        c.hit()


@power(
    "m76a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_just_hit_in_melee,
    requires_text="usable immediately after the m76 hits with a melee attack",
)
def m76a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m76a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m76a4(c: Cast) -> None:
    """Four modifiers, because "a +2 bonus to all defenses" is four numbers
    and the engine holds each defence separately -- one modifier named "all
    defenses" would be a bonus to nothing.

    The other half of the printed line is left as a note. The outcome of an
    attack is recomputed from `result.natural` and `result.total` once the
    windows have closed, and the only override on it is `result.forced`,
    which makes a blow *land*. There is nothing that makes one miss, and
    rigging the total would be faking a number the log then shows. See the
    report.
    """
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.EONT, on=c.me)
    c.note("m76a4: noncritical ranged attacks against it automatically miss")


@power(
    "m76a5",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m76a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: extra weight behind
    its blows for having covered ground.

    Measured the way the printed line measures it -- where the move ended
    against where it began, not how many squares were walked -- and read at
    the end of each move, which is the only moment both ends are known.

    The rider is *replaced* each time it is earned rather than laid beside
    its predecessor, which would pay the 2d8 twice, and it is dealt as its
    own packet rather than as a damage modifier so that the reach can be
    asked about: the printed line is about its melee attacks, and the damage
    context carries no reach of its own.
    """
    me = c.me
    held: list[Effect] = []

    def heavier(ev: Hit) -> None:
        if ev.attacker == me and _reach_kind(ev) == "melee":
            c.damage("2d8", on=ev.target, detail=c.ref)

    def far_enough(_kind: str, start: Any, end: Any, _steps: int) -> None:
        if start is None or c.turn_of() != me or distance(start, end) < 4:
            return
        _renew(
            c,
            held,
            lambda: c.watch(Hit, heavier, until=When.SONT, on=me, label=c.ref),
        )

    _after_moving(c, far_enough)
