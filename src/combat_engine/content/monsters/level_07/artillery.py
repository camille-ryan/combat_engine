"""Monster abilities, level 7: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=REF,
printed=12)` and `Damage("2d8", 3)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

The conventions of the six levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits and are written as such; and a stat block that prints no
range at all means melee 1.

Five things this file had to settle.

**"Fire or radiant damage"** is one printed line with a choice in it rather
than two lines, and the header holds one damage type. So the choice is made
once, on the first target, and both shots are taken there -- the arrangement
level 5 settled on for a row printing "one weapon, twice". The header keeps
the first of the two types, which is what the card prints and what an
edition conversion rescales; the other branch is rolled in the body.

**A zone that burns for dice** rather than for a flat number: `c.burns`
takes an amount, so the dice are rolled once as the fire is set, which is
what the warlock's level-5 zone already does. The second half of the same
printed line -- damage for *starting a turn beside* it -- is not a zone
clause at all, so it is a `TurnStart` watch that reads the fire's square and
stops when the fire does.

**"Resist 5 to all damage"** is not resistance as the engine holds it, which
is per damage type; it is taken off the damage roll in the interrupt window,
which is the one moment the number exists and has not yet come off hit
points. Levels 3 and 5 both met this sentence and level 5 settled it.

**"While at least two others are within 5 squares"** and "adjacent to two or
more of them" are both gated modifiers rather than holds put on and taken
off: who is standing where changes every time anybody moves, and the gate is
asked at the moment the defence is read. The second of the two is a penalty
on somebody else's Will, so it carries a shared label and is installed once
per enemy -- two of these creatures beside the same target print one penalty
between them, not two.

**A minion's death throe that moves somebody into its own square.** The
square is still occupied when `Dropped` is announced -- `resolve._die` lifts
the body afterwards -- so `c.teleport` refuses it. `c.shift(share=True)` is
the op for moving *into* an occupied square and is what the line gets; see
the report for the teleport that would let it be written as printed.

Artillery first, then the minions, each group in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_03.controllers import _nonminion
from combat_engine.content.monsters.level_03.skirmishers import _free_square_beside
from combat_engine.content.monsters.level_06.brutes import (
    DEFENCES,
    _aura,
    _living,
    _same_row,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    INTERRUPT,
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
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Gear,
    Keyword,
    Melee,
    Position,
    Ranged,
    Square,
    Target,
    TurnStart,
    Usage,
    When,
    Window,
    World,
    distance,
    power,
    spread,
)
from combat_engine.engine.events import (
    DamageApplied,
    DamageRolled,
    Dropped,
    Event,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    adjacent,
    creatures,
    distance_between,
    squares,
)
from combat_engine.engine.triggers import Trigger, about_me
from combat_engine.engine.zones import Zone


def _has_javelin(world: World, eid: int) -> bool:
    """A printed "must be wielding a javelin", asked of `Gear` the way level
    5 asks its "must be wielding a shield"."""
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and (
        weapon.group == "javelin" or "javelin" in weapon.properties
    )


def _shrugs_off(c: Cast, amount: int, *, until: When) -> Effect:
    """"Resist N to all damage" for a while.

    Resistance in the engine is held per damage type and this is every kind
    of damage there is, so it comes off the roll instead -- in the interrupt
    window, the one moment the number exists and has not yet reached hit
    points. The arrangement levels 3 and 5 both needed and level 5 wrote.
    """
    me = c.me

    def shrug(ev: DamageRolled) -> None:
        if ev.target == me and ev.amount > 0:
            ev.amount = max(0, ev.amount - amount)

    return c.watch(
        DamageRolled, shrug, until=until, window=Window.BEFORE, on=me, label=c.ref
    )


def _felling_blow(world: World, ev: Event, victim: int) -> DamageApplied | None:
    """The damage that put that creature down.

    `Dropped` carries no source and no damage type, and it is emitted from
    inside the damage that caused it, so the attribution exists in exactly
    one place -- the log -- and the nearest earlier blow is the one to read.
    The same route level 6 takes to find who bloodied whom.
    """
    for past in reversed(world.bus.log[: ev.seq]):
        if isinstance(past, DamageApplied) and past.target == victim:
            return past
    return None


def _blink_to(c: Cast, who: int, spot: Square) -> bool:
    """Teleport a named creature to a named square, however far off it is.

    `c.teleport` takes a distance and these printed lines name only the
    destination, so the distance is measured rather than invented.
    """
    pos = c.world.get(who, Position)
    if pos is None:
        return False
    return c.teleport(max(1, distance(pos.square, spot)), who=who, to=spot)


# ==========================================================================
# Artillery
# ==========================================================================


# --------------------------------------------------------------------------
# m2987
# --------------------------------------------------------------------------


@power(
    "m2987a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.MELEE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 3, dtype=DamageType.RADIANT),
)
def m2987a0(c: Cast) -> None:
    """No range is printed where every other row on the block prints one,
    which the levels below settled means melee 1."""
    if c.strike():
        c.hit()


@power(
    "m2987a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 3, dtype=DamageType.RADIANT),
)
def m2987a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2987a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=Target("any", 2, label="One or two creatures"),
    keywords=[
        Keyword.FIRE,
        Keyword.IMPLEMENT,
        Keyword.RADIANT,
        Keyword.RANGED,
    ],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE, kind=LIMITED),
)
def m2987a2(c: Cast) -> None:
    """One choice of element for the whole shot, not one per target.

    "Fire or radiant" is a single printed line and the header holds a single
    damage type, so the choice is made once -- on the first target -- and
    both shots are taken there, which is how level 5 wrote a row printing
    "one weapon, twice". The header keeps the fire, so the card still prints
    a line that rescales; the radiant branch is rolled here.
    """
    if not c.first:
        return
    victims = [t for t in c.targets if t is not None]
    if not victims:
        return
    dtype = c.choose(
        [DamageType.FIRE, DamageType.RADIANT], "m2987a2: fire or radiant"
    )
    if dtype is None:
        return
    for who in victims:
        if not c.strike(on=who):
            continue
        if dtype is DamageType.FIRE:
            c.hit(on=who)
        else:
            c.damage("1d8", 3, dtype=DamageType.RADIANT, on=who)
        c.ongoing(5, dtype, on=who)


@power(
    "m2987a3",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.ZONE],
)
def m2987a3(c: Cast) -> None:
    """Away in a leap, and fire left standing where it was.

    A jump is a move in the engine, so the printed "jumps 3 and then moves
    its remaining speed" is the creature's whole speed spent in two goes.
    The defence bonus is a hold put on and taken off by hand: "during this
    movement" is a duration no `When` names, and a second move on the same
    turn is not covered by it.

    The fire is a `When.SUSTAIN` zone, which is what "lasts until the end of
    its next turn, Sustain Minor" is -- not sustaining it is what puts it
    out. It burns for dice rather than for a flat number, so the number is
    rolled once as it is set, as the warlock's level-5 zone already does.
    The clause about standing *beside* it is not a zone clause at all --
    `c.burns` bites on entering and on starting inside -- so it is a
    `TurnStart` watch that stops answering once the fire is gone. Being two
    squares high says nothing on a flat grid and is left out.
    """
    me = c.me
    start = c.here
    guards = [c.bonus(d, 4, until=When.EOT, on=me, kind="untyped") for d in DEFENCES]
    c.move(3)
    c.move(max(0, c.speed_of() - 3))
    for guard in guards:
        if guard is not None:
            c.world.effects.end(guard, "the move is over")

    blaze = c.zone(
        {start},
        label="m2987a3",
        until=When.SUSTAIN,
        blocks_sight=True,
        sustain=MINOR,
    )
    c.burns(blaze, c.roll("2d6") + 3, DamageType.FIRE)
    beside = spread({start}, 1) - {start}

    def singe(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or c.world.get(blaze, Zone) is None:
            return
        if squares(c.world, ev.actor) & beside:
            c.damage("1d6", 3, dtype=DamageType.FIRE, on=ev.actor, detail="m2987a3")

    c.watch(TurnStart, singe, until=When.ENCOUNTER, on=me, label="m2987a3 beside")


@power(
    "m2987a4",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT, Keyword.AREA],
    attack=Attack(vs=REF, printed=11),
    damage=Damage(
        "2d6", 3, dtype=DamageType.RADIANT, kind=LIMITED, half_on_miss=True
    ),
)
def m2987a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m2987a5",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2987a5(c: Cast) -> None:
    _shrugs_off(c, 5, until=When.EONT)


# --------------------------------------------------------------------------
# m720
# --------------------------------------------------------------------------


@power(
    "m720a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m720a0(c: Cast) -> None:
    """An aura 1 for the board to draw, with the penalty held per occupant:
    `_aura` diffs membership off `ZoneEntered` and `ZoneExited`, which are
    exactly the two moments the hold should go on and come off. The engine
    holds no flag for being alive, so "living" is asked of the type line."""
    _aura(
        c,
        1,
        lambda who: who in c.enemies() and _living(c, who),
        lambda who: c.penalty("attack", 2, until=When.ENCOUNTER, on=who),
    )


@power(
    "m720a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m720a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m720a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 5),
)
def m720a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m720a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 5, kind=LIMITED),
    requires=_has_javelin,
    requires_text="the m720 must be wielding a javelin",
)
def m720a3(c: Cast) -> None:
    """The Requirement names a weapon, and a monster is spawned with empty
    `Gear`, so nothing on a generated board can meet it -- which is a fact
    about the board rather than about the row, and the Requirement is
    written as printed."""
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m725
# --------------------------------------------------------------------------


@power(
    "m725a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4),
)
def m725a0(c: Cast) -> None:
    """No range printed, which means melee 1."""
    if c.strike():
        c.hit()


@power(
    "m725a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING),
)
def m725a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m725a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 4),
)
def m725a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(5)


@power(
    "m725a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID, Keyword.AREA],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m725a3(c: Cast) -> None:
    """"Save ends both" is one effect carrying the burn and the blindness,
    which is one saving throw; applied separately the victim would get two
    against a thing the card says is one."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.BLINDED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.ACID),
        )


@power(
    "m725a4",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m725a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: folding into a gap
    costs this creature nothing. Half speed, the attack penalty and the
    combat advantage it hands out are the whole of what
    `Condition.SQUEEZING` is, and the printed line waives all three."""
    _squeezes_freely(c)


# ==========================================================================
# The minions. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# ==========================================================================


# --------------------------------------------------------------------------
# m288
# --------------------------------------------------------------------------


@power(
    "m288a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage(bonus=6, kind=MINION),
)
def m288a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m288a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m288a1(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: braver in a crowd.

    Who is standing within five squares changes every time anybody moves, so
    this is a gated modifier asked as each defence is looked up rather than
    a bonus put on and taken off. The gate ignores the context entirely --
    it is about the board, not about the attack -- and "another of these" is
    an `Ident` match, because `c.is_kind` answers about type words that
    several stat blocks share.
    """
    me = c.me

    def a_crowd(_ctx: dict[str, Any]) -> bool:
        return (
            sum(
                1
                for a in c.allies()
                if a != me
                and _same_row(c, a, "m288")
                and distance_between(c.world, a, me) <= 5
            )
            >= 2
        )

    for defence in DEFENCES:
        c.bonus(defence, 2, until=When.ENCOUNTER, on=me, when=a_crowd)


# --------------------------------------------------------------------------
# m421
# --------------------------------------------------------------------------


@power(
    "m421a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage(bonus=5, kind=MINION),
)
def m421a0(c: Cast) -> None:
    """A secondary attack is a second attack line and a row carries one, so
    the printed +9 is trimmed by hand the way `Attack.bonus_for` trims the
    header's -- the row still moves with whatever scaling the fight is on.
    The header keeps the primary, which is what a policy forecasts from."""
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(9, c.level), FORT):
        c.ongoing(2, DamageType.POISON)


# --------------------------------------------------------------------------
# m4876
# --------------------------------------------------------------------------


#: One penalty between them, however many of these are crowding a creature.
_M4876_HUDDLE = "m4876a0 will"


def _hemmed_in(c: Cast, who: int) -> bool:
    """Has that creature two or more of this stat block standing beside it?"""
    return (
        sum(
            1
            for a in creatures(c.world)
            if _same_row(c, a, "m4876") and adjacent(c.world, a, who)
        )
        >= 2
    )


@power(
    "m4876a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4876a0(c: Cast) -> None:
    """Surrounded by enough of them and the mind goes first.

    A gated modifier rather than a hold put on and taken off, for m288a1's
    reason: who is standing beside whom changes every time anything moves,
    and the gate is asked at the moment the Will is read. The count is of
    **every** one of these on the board rather than of this one's friends,
    which is what the printed line says -- so the penalty carries a shared
    label and a second of these crowding the same creature adds nothing.
    """
    for foe in c.enemies():
        if any(eff.label == _M4876_HUDDLE for eff in c.world.effects.of(foe)):
            continue
        hold = c.penalty(
            WILL,
            2,
            until=When.ENCOUNTER,
            on=foe,
            when=lambda _ctx, who=foe: _hemmed_in(c, who),
        )
        if hold is not None:
            hold.label = _M4876_HUDDLE


@power(
    "m4876a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage(bonus=7, kind=MINION),
)
def m4876a1(c: Cast) -> None:
    """A blow, and a friend arriving beside whoever took it.

    "Within 6 squares" is measured from this creature, which is the only
    thing the sentence names. The arrival square is picked here because
    `c.teleport` will not pick one and an occupied square is simply refused;
    the distance is measured for the same reason.
    """
    victim = c.target
    if not c.strike():
        return
    c.hit()
    spot = _free_square_beside(c, victim) if victim is not None else None
    kin = sorted(
        a
        for a in c.allies()
        if _same_row(c, a, "m4876") and distance_between(c.world, c.me, a) <= 6
    )
    if spot is None or not kin:
        return
    mate = c.choose(kin, "m4876a1: which one steps in")
    if mate is not None:
        _blink_to(c, mate, spot)


_M4876_DOWN = "the m4876 drops to 0 hit points"


@power(
    "m4876a2",
    level=7,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M4876_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M4876_DOWN),
)
def m4876a2(c: Cast) -> None:
    """Something bigger arrives in the space it is vacating.

    The square is still occupied when this runs -- `Dropped` is announced
    before `resolve._die` lifts the body -- so `c.teleport` refuses it and
    `c.shift(share=True)`, which is the op for moving *into* an occupied
    square, is what the line gets. See the report.

    Declared with no target rather than with the ally: `use` skips a target
    that the dispatcher aimed at, and this row aims itself.
    """
    kin = sorted(
        a
        for a in c.allies()
        if _nonminion(c.world, a) and distance_between(c.world, c.me, a) <= 6
    )
    if not kin:
        return
    mate = c.choose(kin, "m4876a2: who is pulled in")
    if mate is not None:
        c.shift(who=mate, to=c.here, share=True)


# --------------------------------------------------------------------------
# m4917
# --------------------------------------------------------------------------


@power(
    "m4917a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage(bonus=7, kind=MINION),
)
def m4917a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M4917_DOWN = "the m4917 drops to 0 hit points"


@power(
    "m4917a1",
    level=7,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage(bonus=5, dtype=DamageType.FIRE, kind=MINION),
    trigger=_M4917_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M4917_DOWN),
)
def m4917a1(c: Cast) -> None:
    """It goes up, and takes the run first if fire is what lit it.

    The row declares no targets and gathers them itself: the dispatcher
    picks a burst's targets before the body runs, and the printed line moves
    the creature *before* the attack -- which is the whole point of the run,
    and would be wasted on a set of targets chosen from where it was
    standing. The reach stays in the header, where the card and the policy
    read it.

    Whether fire did it is read off the log: `Dropped` carries no damage
    type, and the blow that caused it is the nearest earlier one.
    """
    blow = _felling_blow(c.world, c.trigger, c.me) if c.trigger is not None else None
    if blow is not None and blow.dtype is DamageType.FIRE:
        c.move(c.speed_of())
    for who in sorted(c.within(1, side="other")):
        if c.strike(on=who):
            c.hit(on=who)


# --------------------------------------------------------------------------
# m5046
# --------------------------------------------------------------------------


@power(
    "m5046a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5046a0(c: Cast) -> None:
    """Starting a turn in it, not entering it, so a `TurnStart` watch against
    the aura's occupants rather than anything on the zone itself -- `c.burns`
    is the hostile half of that shape and it deals damage rather than holds
    a creature."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def clog(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slowed(until=When.EOTNT, on=ev.actor)

    c.watch(TurnStart, clog, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5046a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage(bonus=7, kind=MINION),
)
def m5046a1(c: Cast) -> None:
    if c.strike():
        c.hit()
