"""Monster abilities, level 6: the brutes and the soldiers beside them.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=11)` and `Damage("2d10", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

Several rows here are printed under an action heading and are plainly
traits; those are declared `ActionType.NONE` and armed once when the fight
starts. A printed range of "15/30" takes the short range, which is what the
creature can actually shoot without a penalty the engine does not model.

Three shapes recur at this tier and are written once at the top: an aura
whose occupants carry a hold while they are inside it, a rider that only
applies on a charge, and a mount's row that answers what its rider did.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defense,
    Effect,
    Event,
    Health,
    Ident,
    Keyword,
    Melee,
    Mod,
    Powers,
    Ranged,
    Relation,
    Stats,
    Usage,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Dropped,
    Healed,
    Hit,
    Miss,
    MoveEnd,
    MoveStart,
    OpportunityWindow,
    PowerUsed,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    alive,
    distance_between,
    enemies,
    flanked_by,
    has_combat_advantage,
    is_,
    squares,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_charge,
    by_melee,
    leaves_me_out,
    targets_me,
)

#: The reaches that count as a melee attack, for the rows whose rider is on
#: "its melee attacks" rather than on one named row.
MELEE_KINDS = ("melee",)

#: The four defences, for the rows that move all of them at once.
DEFENCES = (Defense.AC, Defense.FORT, Defense.REF, Defense.WILL)

#: What a printed "living creature" rules out. The engine holds no flag for
#: being alive, so the question is put to the type line the way `c.is_kind`
#: reads it.
LIFELESS = ("undead", "construct")


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _living(c: Cast, who: int) -> bool:
    return not any(c.is_kind(word, on=who) for word in LIFELESS)


def _same_row(c: Cast, who: int, ref: str) -> bool:
    """Is that creature another of this stat block?

    By id. A body is never told what anything is called, and `c.is_kind`
    answers about type words -- reptile, undead -- which several different
    stat blocks share.
    """
    ident = c.world.get(who, Ident)
    return ident is not None and ident.ref == ref


def _melee_ctx(ctx: dict[str, Any]) -> bool:
    """Is the attack this modifier is being read for a melee one?

    The attack context carries `ranged`; the damage context does not, and a
    gate on a key the context has no entry for is silently false. Both carry
    the row's ref, so the reach is looked up from that instead.
    """
    p = get(ctx.get("power") or "")
    return p is not None and p.reach_of(ctx.get("branch", 0)).kind in MELEE_KINDS


def _somebody_is(*conditions: Condition) -> Callable[[World, int], bool]:
    """A printed target of "one immobilized creature", as a `requires`.

    `requires` is handed the caster and no target, so the nearest thing it
    can say is that *somebody* on the board qualifies. Which one is then the
    chooser's business, and the body checks the one actually aimed at.
    """

    def check(world: World, eid: int) -> bool:
        return any(
            any(is_(world, foe, cond) for cond in conditions)
            for foe in enemies(world, eid)
        )

    return check


def _bloodied_enemy(world: World, eid: int) -> bool:
    return any(_is_bloodied(world, foe) for foe in enemies(world, eid))


def _has_an_opening(world: World, eid: int) -> bool:
    """A printed target of "a creature granting combat advantage to it"."""
    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


def _not_wearing(label: str) -> Callable[[World, int], bool]:
    """A Requirement of "must be in <this> form", written as the absence of
    the other one.

    The stat block never says which shape it starts a fight in, so neither
    row is gated on a form being *present*: both are open until the polymorph
    row has actually picked one, and from then on exactly one of them is shut.
    """

    def check(world: World, eid: int) -> bool:
        return not any(eff.label == label for eff in world.effects.of(eid))

    return check


def _aura(
    c: Cast,
    radius: int,
    eligible: Callable[[int], bool],
    hold: Callable[[int], Effect | None],
) -> int:
    """An aura whose occupants carry a hold for as long as they are inside.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are exactly the two moments the hold should go on and
    come off. Whoever is already standing inside is caught at the end --
    making the aura refreshes membership before its id exists for a listener
    to recognise.
    """
    held: dict[int, Effect] = {}
    ring = c.aura(radius, until=When.ENCOUNTER)

    def take(who: int) -> None:
        if who in held or not eligible(who):
            return
        effect = hold(who)
        if effect is not None:
            held[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            take(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(ring):
        take(actor)
    return ring


def _presses_the_wounded(c: Cast, to_hit: int, to_hurt: int) -> None:
    """"Against bloodied enemies it gains ..." -- two gated modifiers.

    Whether the creature being swung at is bleeding is asked at the moment
    of the roll rather than stored: it changes with every blow, and both the
    attack and the damage context carry the target.
    """

    def bleeding(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.bloodied(who)

    c.bonus("attack", to_hit, until=When.ENCOUNTER, on=c.me, when=bleeding)
    c.bonus("damage", to_hurt, until=When.ENCOUNTER, on=c.me, when=bleeding)


def _recharge_on(c: Cast, event: type[Event], test: Callable[[Any], bool]) -> None:
    """Put this row back up when its printed line says so, not only on a die.

    The database files a plain 6+ where the stat block prints "Recharge when
    ...". The number stays in the header, because that is what
    `actions.recharge` rolls and what the card shows; this is the printed
    sentence on top of it, and the two only ever agree to make the row
    available sooner. Armed from the body, which is all that is needed: the
    row has to have been spent before there is anything to give back.
    """
    ref, me = c.ref, c.me
    label = f"{ref} recharge"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def back(ev: Event) -> None:
        known = c.world.get(me, Powers)
        if known is not None and test(ev):
            known.restore(ref)

    c.watch(event, back, until=When.ENCOUNTER, on=me, label=label)


def _rider_charged(world: World, me: int, ev: Hit) -> bool:
    """"A friendly rider of 6th level or higher hits with a charge attack."

    All four clauses are here because each is a separate question: who is in
    the saddle, whose side that creature is on, how high a level it is, and
    whether the blow was a charge -- which is what `charge` on the attack
    event is for, and could not be asked at all before it existed.
    """
    rider = ev.attacker
    if rider not in world.relations.targets(Relation.RIDDEN_BY, me):
        return False
    if team(world, rider) is not team(world, me) or not by_charge(world, me, ev):
        return False
    stats = world.get(rider, Stats)
    return stats is not None and stats.level >= 6


def _step_toward(c: Cast, victim: int) -> bool:
    """Shift one square, ending nearer that creature than it began.

    "Shifts toward the enemy" names a direction rather than a square, and no
    movement op will pick one -- so the reachable squares are filtered to the
    ones that are closer and the nearest of those is taken.
    """
    was = c.distance(victim)
    theirs = squares(c.world, victim)
    nearer = sorted(
        sq
        for sq in c.world.reachable_squares(c.me, 1)
        if min(distance(sq, s) for s in theirs) < was
    )
    return bool(nearer) and c.shift(to=nearer[0])


def _struck_by(world: World, ev: Event, victim: int) -> int | None:
    """Who landed the blow that caused this `Bloodied` or `Dropped`.

    Neither event carries a source, and both are emitted from inside the
    damage that caused them -- immediately after the `DamageApplied` that
    did it. So the attribution exists in exactly one place, which is the log,
    and the nearest earlier blow on that creature is the one to read.
    """
    for past in reversed(world.bus.log[: ev.seq]):
        if isinstance(past, DamageApplied) and past.target == victim:
            return past.source
    return None


# ==========================================================================
# Brutes
# ==========================================================================

# -- m109 -------------------------------------------------------------------


@power(
    "m109a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5),
)
def m109a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means."""
    if c.strike():
        c.hit()


@power(
    "m109a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m109a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# -- m144 -------------------------------------------------------------------


@power(
    "m144a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m144a0(c: Cast) -> None:
    """The whole rider is on a charge, which the engine now says out loud.

    The extra damage is a gated modifier rather than a second blow, so it
    meets resistance as part of the same hit -- `charge` is a key the damage
    context carries, which is what makes the gate readable at all. The shove
    and the fall cannot ride a modifier, so they hang off the `Hit` instead,
    and both are announced before the damage lands, which is the order the
    card reads in.
    """
    me = c.me
    c.bonus(
        "damage", 5, until=When.ENCOUNTER, on=me, when=lambda ctx: bool(ctx.get("charge"))
    )

    def trample(ev: Hit) -> None:
        if ev.attacker != me or not by_charge(c.world, me, ev):
            return
        c.push(2, on=ev.target)
        c.prone(on=ev.target)

    c.watch(Hit, trample, until=When.ENCOUNTER, on=me, label="m144a0")


@power(
    "m144a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 4),
)
def m144a1(c: Cast) -> None:
    """Prone swaps the expression rather than adding to it, so the header keeps
    the printed line that rescales and the larger one is rolled here.

    Whether the target was down is read *before* the swing: m144a0 knocks a
    charged target prone as the hit is announced, and asking afterwards would
    let one blow pay itself the bonus for its own trip.
    """
    down = c.is_(Condition.PRONE)
    if not c.strike():
        return
    if down:
        c.damage("2d10", 9)
    else:
        c.hit()


_M144_RIDER = "a friendly rider of 6th level or higher on the m144 hits with a charge"


@power(
    "m144a2",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M144_RIDER,
    on=Trigger(Hit, when=_rider_charged, text=_M144_RIDER),
)
def m144a2(c: Cast) -> None:
    """m144a1 at whoever the rider just rode down.

    Declared with no target: the dispatcher aims a triggered row at the
    creature the event names as its attacker, and here that is the rider --
    an ally. The one worth biting is the rider's victim, which is read off
    the trigger.
    """
    who = getattr(c.trigger, "target", None)
    if who is not None:
        use(c.world, c.me, "m144a1", targets=[who], spend=False)


_M144_DOWN = "the m144 drops to 0 hit points"


@power(
    "m144a3",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M144_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M144_DOWN),
)
def m144a3(c: Cast) -> None:
    """One last bite, at whoever is still standing next to it.

    The trigger is handed on to the row being used. A death throe is allowed
    past the "can it act?" gate only because `use` can see the event it is
    answering, and a nested call that dropped the event would be refused for
    the very reason this row exists.
    """
    who = next(iter(sorted(c.within(1, side="enemy"))), None)
    if who is not None:
        use(c.world, c.me, "m144a1", targets=[who], spend=False, trigger=c.trigger)


# -- m194 -------------------------------------------------------------------


@power(
    "m194a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d12", 5),
)
def m194a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m194a1",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
    requires=_bloodied_enemy,
    requires_text="the target must be bloodied",
)
def m194a1(c: Cast) -> None:
    """The printed target is a creature that is already bleeding, which no
    `Target` can say -- so `requires` carries the half about the board and
    the header takes one enemy, and the body aims at whoever within reach is
    actually bloodied. Aiming is not the chooser's to get wrong here: a row
    that may only be used against one kind of creature is not a choice of
    target, it is a restriction on one."""
    victim = c.target if c.target is not None and c.bloodied(c.target) else None
    if victim is None:
        victim = next((f for f in sorted(c.within(1, side="enemy")) if c.bloodied(f)), None)
    if victim is not None and c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m194a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m194a2(c: Cast) -> None:
    """Two gates rather than one, because +3 *replaces* +1 rather than adding
    to it -- so each is written as the case the other is not, and they can
    never both be live at once.

    Who is crowding the victim changes every time anything moves, so the
    count is taken at the moment of the roll. The caster is left out: the
    printed line is about its allies. "Another of these" is an `Ident.ref`
    and nothing else says it -- `c.is_kind` answers about type words, which
    several stat blocks share.

    "Stacks with combat advantage" needs nothing said: the engine adds the
    +2 for an opening separately, and a `power` modifier does not displace it.
    """
    me = c.me

    def mob(ctx: dict[str, Any]) -> list[int]:
        who = ctx.get("target")
        if who is None or not _melee_ctx(ctx):
            return []
        return [a for a in c.within(1, of=who, side="ally") if a != me]

    def alone(ctx: dict[str, Any]) -> bool:
        friends = mob(ctx)
        return bool(friends) and not any(_same_row(c, a, "m194") for a in friends)

    def in_company(ctx: dict[str, Any]) -> bool:
        return any(_same_row(c, a, "m194") for a in mob(ctx))

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=alone)
    c.bonus("attack", 3, until=When.ENCOUNTER, on=me, when=in_company)


# -- m233 -------------------------------------------------------------------


@power(
    "m233a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m233a0(c: Cast) -> None:
    """Bloodied swaps the expression rather than adding to it, so the header
    keeps the printed line that rescales and the larger one is rolled here."""
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("1d8", 8)
    else:
        c.hit()


_M233_SCENT = "the m233 hits a bloodied enemy with a melee attack"


def _bit_a_bleeding_one(world: World, me: int, ev: Hit) -> bool:
    return (
        ev.attacker == me
        and by_melee(world, me, ev)
        and ev.target in enemies(world, me)
        and _is_bloodied(world, ev.target)
    )


@power(
    "m233a1",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 2),
    trigger=_M233_SCENT,
    on=Trigger(Hit, when=_bit_a_bleeding_one, text=_M233_SCENT),
)
def m233a1(c: Cast) -> None:
    """A second set of jaws into the same target.

    Declared with no target and aimed off the trigger: the dispatcher points
    a triggered row at whoever the event names, and here that is the m233
    itself. The bite is a melee hit on a bloodied enemy and so answers its own
    printed trigger; `use` refuses a row already in flight, which is what
    keeps one bite from becoming an unbounded number of them.
    """
    who = getattr(c.trigger, "target", None)
    if who is None or not c.strike(on=who):
        return
    if c.bloodied(c.me):
        c.damage("1d6", 4, on=who)
    else:
        c.hit(on=who)


@power(
    "m233a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m233a2(c: Cast) -> None:
    """Who is crowding the victim changes every time anything moves, so the
    gate is read at the moment the damage is rolled rather than stored. The
    caster is left out of the count: the printed line is about its allies."""
    me = c.me

    def mobbed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or not _melee_ctx(ctx):
            return False
        return sum(1 for a in c.within(1, of=who, side="ally") if a != me) >= 2

    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=mobbed)


# -- m3032 ------------------------------------------------------------------

#: The two shapes m3032a4 offers, and the labels the attack rows read their
#: Requirement off.
_M3032_BEAST = "m3032a4 beast"
_M3032_HUMANOID = "m3032a4 humanoid"


@power(
    "m3032a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 6),
    requires=_not_wearing(_M3032_BEAST),
    requires_text="the m3032 must be in its humanoid shape",
)
def m3032a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3032a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 6),
    requires=_not_wearing(_M3032_HUMANOID),
    requires_text="the m3032 must be in its beast shape",
)
def m3032a1(c: Cast) -> None:
    """The bloodied half of m3032a3 lives here rather than there: it changes
    the number *this* row deals, and a trait cannot reach into another row's
    ongoing damage without reproducing the line in two places.

    The contagion is a disease track the engine has no model of, so it is
    noted rather than invented.
    """
    if not c.strike():
        return
    c.hit()
    c.ongoing(10 if c.bloodied(c.me) else 5)
    c.note("m3032a1: the target is exposed to this stat block's disease")


_M3032_DOWN = "the m3032 drops to 0 hit points"


@power(
    "m3032a2",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M3032_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M3032_DOWN),
)
def m3032a2(c: Cast) -> None:
    """"Either attack" is a real choice and has to be offered as one -- but
    whichever shape it is wearing has shut one of the two, so the other is
    taken rather than the throe going to waste.

    The trigger is handed on to the row being used: a death throe is allowed
    past the "can it act?" gate only because `use` can see the event it is
    answering.
    """
    who = next(iter(sorted(c.within(1, side="enemy"))), None)
    if who is None:
        return
    first = c.choose(["m3032a1", "m3032a0"], "m3032a2") or "m3032a1"
    order = [first, "m3032a0" if first == "m3032a1" else "m3032a1"]
    for ref in order:
        if use(c.world, c.me, ref, targets=[who], spend=False, trigger=c.trigger):
            return


@power(
    "m3032a3",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3032a3(c: Cast) -> None:
    """Four modifiers on one gate, because "+2 to all defences" is four
    numbers and the engine holds each defence separately.

    Being bloodied is asked inside the gate rather than once when the trait
    arms: hit points cross back and forth, and a defence is read again after
    the roll has been announced, which is where this has to be right.
    """
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(me)

    for d in DEFENCES:
        c.bonus(d, 2, until=When.ENCOUNTER, on=me, when=hurt)


@power(
    "m3032a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m3032a4(c: Cast) -> None:
    """Either shape, and taking one ends the other.

    The form carries no conditions and no movement modes: the printed line
    changes what the creature looks like and nothing else, so all it is here
    is the label m3032a0 and m3032a1 read their Requirement off. `c.form`
    does not displace a previous form the way `c.stance` displaces a stance,
    so the old shape is ended by hand.
    """
    for eff in list(c.world.effects.of(c.me)):
        if eff.label in (_M3032_BEAST, _M3032_HUMANOID):
            c.world.effects.end(eff, "it changed shape again")
    shape = c.choose([_M3032_BEAST, _M3032_HUMANOID], "which shape") or _M3032_BEAST
    c.form(until=When.ENCOUNTER, revert=MINOR, label=shape)


# -- m4888 ------------------------------------------------------------------


@power(
    "m4888a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4888a0(c: Cast) -> None:
    """An aura 1 for the board to draw, biting at the start of a turn.

    Not `c.hazard`, which also catches whoever walks in and whoever ends a
    turn there; this line does neither. The aura is read by distance rather
    than by membership because the printed sentence is about anybody at all,
    either side, and the hold is a fresh one each turn rather than something
    carried while inside.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def chill(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or not _living(c, ev.actor):
            return
        if c.distance(ev.actor) <= 1:
            c.slowed(until=When.EONT, on=ev.actor)

    c.watch(TurnStart, chill, until=When.ENCOUNTER, on=me, label="m4888a0")


@power(
    "m4888a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d12", 6),
)
def m4888a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4888a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d12", 4),
    requires=_somebody_is(Condition.IMMOBILIZED),
    requires_text="the target must be immobilized",
)
def m4888a2(c: Cast) -> None:
    """The Effect line says the attack below is made twice, so the declared
    line is rolled twice rather than the row being used twice."""
    if not c.is_(Condition.IMMOBILIZED):
        return
    for _ in range(2):
        if c.strike():
            c.hit()


@power(
    "m4888a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d12", 7, kind=LIMITED),
    requires=_somebody_is(Condition.IMMOBILIZED, Condition.UNCONSCIOUS),
    requires_text="the target must be immobilized or unconscious",
)
def m4888a3(c: Cast) -> None:
    """The printed recharge on top of the die the database files for it: this
    row comes back the moment it misses, and the watch is armed before the
    swing so it is listening when that happens."""
    me = c.me
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == "m4888a3")
    if not (c.is_(Condition.IMMOBILIZED) or c.is_(Condition.UNCONSCIOUS)):
        return
    if c.strike():
        c.hit()


_M4888_DOWN = "the m4888 drops to 0 hit points"


@power(
    "m4888a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d12", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
    trigger=_M4888_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M4888_DOWN),
)
def m4888a4(c: Cast) -> None:
    """The printed target is "living creatures in the burst", which the
    header cannot say -- so the burst takes the enemies in it and the body
    drops the ones that are past caring."""
    if c.target is None or not _living(c, c.target):
        return
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


# -- m705 -------------------------------------------------------------------


@power(
    "m705a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m705a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m705a1",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m705a1(c: Cast) -> None:
    _presses_the_wounded(c, 1, 2)


@power(
    "m705a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage(bonus=8, kind=MINION),
)
def m705a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m705a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage(bonus=8, kind=MINION),
)
def m705a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# -- m85 --------------------------------------------------------------------


@power(
    "m85a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 6),
)
def m85a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m85a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 6),
)
def m85a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# -- m881 -------------------------------------------------------------------


@power(
    "m881a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 6),
)
def m881a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m881a1",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m881a1(c: Cast) -> None:
    """The burning and the penalty are one effect with one saving throw, as
    printed: "save ends both". `c.ongoing` and `c.penalty` would have been
    two, and the target would have shrugged off half of it at a time."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} venom",
        ongoing=(2, DamageType.POISON),
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
    )


# ==========================================================================
# Soldiers
# ==========================================================================

# -- m114 -------------------------------------------------------------------


@power(
    "m114a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4, dtype=DamageType.COLD),
)
def m114a0(c: Cast) -> None:
    """The hold and the burning are two printed durations -- one on the
    m114's clock, one on a saving throw -- so they are two effects."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
        c.ongoing(5, DamageType.COLD)


_M114_DOWN = "the m114 is reduced to 0 hit points"


@power(
    "m114a1",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 2, dtype=DamageType.COLD),
    trigger=_M114_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M114_DOWN),
)
def m114a1(c: Cast) -> None:
    """The card prints a burst and no target line at all, so the burst takes
    the enemies standing in it rather than everybody."""
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m114a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m114a2(c: Cast) -> None:
    """A gated damage modifier, so the extra rides the blow it belongs to and
    meets the same resistance -- which is also why nothing here names a type:
    a modifier has none, and every attack this stat block makes is cold."""
    me = c.me

    def held(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.is_(Condition.IMMOBILIZED, on=who)

    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=held)


# -- m3084 ------------------------------------------------------------------


@power(
    "m3084a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 6),
)
def m3084a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m3084a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
)
def m3084a1(c: Cast) -> None:
    """A feud, with no attack roll anywhere in it: three separate holds, all
    of them on the one creature's clock and all of them ending together.

    Whether the target attacked the m3084 is answered off `PowerUsed` rather
    than off each `AttackDeclared`: an attack is announced once per target,
    so a burst that caught the m3084 would have read as three attacks, two of
    which left it out. `PowerUsed` is once per use and carries the whole
    target list, which is exactly the printed question.

    "The target's allies" are this creature's enemies, since `c.within` names
    sides from the caster's point of view and there is no other vantage.
    """
    victim = c.target
    if victim is None:
        return
    me = c.me
    c.no_provoke(from_=victim, until=When.ENCOUNTER)
    swung = [False]

    def noticed(ev: PowerUsed) -> None:
        p = get(ev.power)
        if ev.actor == victim and p is not None and p.is_attack and me in ev.targets:
            swung[0] = True

    def ignored(ev: TurnEnd) -> None:
        if ev.actor != victim or ev.ghost:
            return
        if not swung[0]:
            c.flat(5, on=victim)
        swung[0] = False

    def crowd(ev: TurnStart) -> None:
        if ev.actor != victim or ev.ghost:
            return
        for friend in c.within(1, of=victim, side="enemy"):
            if friend != victim:
                c.flat(5, on=friend)

    c.watch(PowerUsed, noticed, until=When.ENCOUNTER, on=me, label="m3084a1 watched")
    c.watch(TurnEnd, ignored, until=When.ENCOUNTER, on=me, label="m3084a1 slighted")
    c.watch(TurnStart, crowd, until=When.ENCOUNTER, on=me, label="m3084a1 crowd")


@power(
    "m3084a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3084a2(c: Cast) -> None:
    """A rider on the *next* swing, which is not a duration -- so it is armed
    as a watch on the hit that spends itself rather than as a bonus, which an
    attack roll would spend whether or not it landed.

    The printed recharge sits on top of the die the database files: this row
    comes back the first time the m3084 is bloodied.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)

    def press(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m3084a0":
            return
        c.dazed(until=When.EONT, on=ev.target)
        c.prone(on=ev.target)

    c.watch(Hit, press, until=When.ENCOUNTER, on=me, once=True, label="m3084a2")


_M3084_BLOOD = "the m3084 bloodies an enemy or drops one to 0 hit points or fewer"


def _felled_by_me(world: World, me: int, ev: Event) -> bool:
    """Sides are compared directly rather than through `enemies`, which
    filters out the dead -- and a creature that has just dropped is exactly
    what the second half of this trigger is about, so asking that way made
    the kill half of the line silently false."""
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    theirs = team(world, who)
    if theirs is None or theirs is team(world, me):
        return False
    return _struck_by(world, ev, who) == me


@power(
    "m3084a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3084_BLOOD,
    on=[
        Trigger(Bloodied, when=_felled_by_me, text="the m3084 bloodies an enemy"),
        Trigger(Dropped, when=_felled_by_me, text="or drops one to 0 hit points"),
    ],
)
def m3084a3(c: Cast) -> None:
    """Two printed triggers, so two are declared: `on=` takes a sequence and
    the row answers whichever happened. "First bloodied" needs no guard --
    `Bloodied` is emitted on the crossing and nowhere else.

    Declared with no target at all: the beneficiary is the m3084, and a row
    that took itself as a target would be aimed by the dispatcher at the
    creature that just went down.
    """
    c.temp_hp(c.roll("1d8") + 2, on=c.me)


# -- m321 -------------------------------------------------------------------


@power(
    "m321a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m321a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m321a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m321a1(c: Cast) -> None:
    """m321a0 through the row that prints it, so its damage line stays in one
    place -- and `use` reports that a power went off rather than that it hit,
    so the hit that opens the secondary attack is counted off the bus.

    The secondary is a second roll against a different defence and cannot
    live in a header; its printed +9 is trimmed by hand the way
    `Attack.bonus_for` trims the header's.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m321a0":
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=me)
    try:
        use(c.world, me, "m321a0", targets=[victim], spend=False)
    finally:
        c.world.bus.off(sub)
    if victim not in landed:
        return
    if c.attack(c.world.scaling.trim(9, c.level), REF, on=victim):
        c.slowed(until=When.SAVE_ENDS, on=victim)


_M321_SLIPPED = "an adjacent enemy shifts"


def _neighbour_shifts(world: World, me: int, ev: MoveStart) -> bool:
    return (
        ev.kind_ == "shift"
        and ev.actor != me
        and ev.actor in enemies(world, me)
        and distance_between(world, me, ev.actor) <= 1
    )


@power(
    "m321a2",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M321_SLIPPED,
    on=Trigger(MoveStart, when=_neighbour_shifts, text=_M321_SLIPPED),
)
def m321a2(c: Cast) -> None:
    """Follow it.

    `MoveStart` is emitted *before* the step, and an immediate reaction is
    the after-window of the event that offered it -- so at the moment this
    row runs the enemy has not moved and "toward" names a square it is
    already standing next to. The step is therefore hung on that creature's
    `MoveEnd`, which is the first moment there is anywhere to follow to, and
    is spent as soon as it fires.
    """
    who = getattr(c.trigger, "actor", None)
    if who is None:
        return
    holder: list[Effect] = []

    def follow(ev: MoveEnd) -> None:
        if ev.actor != who:
            return
        _step_toward(c, who)
        if holder:
            c.world.effects.end(holder[0], "spent")

    holder.append(
        c.watch(MoveEnd, follow, until=When.EOT, on=c.me, label="m321a2 follow")
    )


@power(
    "m321a3",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    requires=_is_bloodied,
    requires_text="the m321 must be bloodied",
)
def m321a3(c: Cast) -> None:
    """Regeneration written out, because the engine holds no such thing, and
    a damage bonus that outlasts it.

    The two halves have different endings -- the bonus runs to the end of the
    encounter or until the creature is knocked out, the healing only while it
    is still bleeding -- so they are two holds rather than one, and being
    bloodied is asked as each turn comes round.
    """
    me = c.me
    gain = c.bonus("damage", 2, until=When.ENCOUNTER, on=me)

    def regenerate(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.bloodied(me):
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.heal(2, on=me)

    def out(ev: ConditionApplied) -> None:
        if ev.target == me and ev.condition is Condition.UNCONSCIOUS and gain is not None:
            c.world.effects.end(gain, "rendered unconscious")

    c.watch(TurnStart, regenerate, until=When.ENCOUNTER, on=me, label="m321a3")
    c.watch(ConditionApplied, out, until=When.ENCOUNTER, on=me, label="m321a3 out")


# -- m397 -------------------------------------------------------------------


@power(
    "m397a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m397a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m397a1",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m397a1(c: Cast) -> None:
    _presses_the_wounded(c, 1, 2)


@power(
    "m397a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m397a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m397a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m397a3(c: Cast) -> None:
    if c.strike():
        c.hit()


_M397_SLIPPED = "an enemy flanked by the m397 shifts"


def _flanked_enemy_shifts(world: World, me: int, ev: MoveStart) -> bool:
    return (
        ev.kind_ == "shift"
        and ev.actor != me
        and ev.actor in enemies(world, me)
        and flanked_by(world, ev.actor, me)
    )


@power(
    "m397a4",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M397_SLIPPED,
    on=Trigger(MoveStart, when=_flanked_enemy_shifts, text=_M397_SLIPPED),
)
def m397a4(c: Cast) -> None:
    """An interrupt on the start of the shift, which is the window in which
    the enemy is still where it was -- and still flanked, which is the whole
    of what opened this."""
    if c.target is not None:
        c.basic(on=c.target)


# -- m4710 ------------------------------------------------------------------


@power(
    "m4710a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4710a0(c: Cast) -> None:
    """Not `c.no_provoke`, which waives the window unconditionally: the
    printed line waives it only while the creature is on a wall, and
    `c.moving_as` is what asks what it is *doing*. `Movement.modes` only ever
    said what it could do, which would have made this true all the time.
    """
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        if ev.provoker == me and c.moving_as("climb"):
            ev.cancel("m4710a0")

    c.watch(
        OpportunityWindow,
        veto,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m4710a0",
    )


@power(
    "m4710a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 7),
)
def m4710a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4710a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4710a2(c: Cast) -> None:
    """m4710a1 through the row that prints it, so its damage line stays in one
    place, and then away up the wall."""
    if c.target is not None:
        use(c.world, c.me, "m4710a1", targets=[c.target], spend=False)
    c.shift(3)


@power(
    "m4710a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d10", 9),
    requires=_somebody_is(Condition.PRONE),
    requires_text="the target must be prone",
)
def m4710a3(c: Cast) -> None:
    """The printed restriction is per target and `Target` cannot say it, so
    `requires` carries the half about the board and the body checks the one
    actually aimed at."""
    if not c.is_(Condition.PRONE):
        return
    if c.strike():
        c.hit()
        c.temp_hp(10, on=c.me)


# -- m474 -------------------------------------------------------------------


@power(
    "m474a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 5),
)
def m474a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m474a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m474a1(c: Cast) -> None:
    """A basic attack rather than a named row: `c.basic` swings whatever this
    creature's basic actually is, which for a monster is one of its own rows.

    It reports that a power went off and not that it hit, so the hit that
    buys the slide and the step is counted off the bus. "The m474 or an ally"
    is a real choice and is offered as one.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me:
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=me)
    try:
        c.basic(on=victim)
    finally:
        c.world.bus.off(sub)
    if victim not in landed:
        return
    c.slide(1, on=victim)
    movers = sorted({me, *(a for a in c.within(10, side="ally") if a != me)})
    who = c.choose(movers, "m474a1: who steps")
    if who is not None:
        c.shift(1, who=who)


@power(
    "m474a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m474a2(c: Cast) -> None:
    """Who is standing beside the victim changes every time anything moves,
    so the gate is read at the moment of the roll rather than stored."""
    me = c.me

    def beside(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or not _melee_ctx(ctx):
            return False
        return any(a != me for a in c.within(1, of=who, side="ally"))

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=beside)


@power(
    "m474a3",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_bloodied,
    requires_text="the m474 must be bloodied",
)
def m474a3(c: Cast) -> None:
    c.temp_hp(18, on=c.me)


# -- m4779 ------------------------------------------------------------------


@power(
    "m4779a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m4779a0(c: Cast) -> None:
    """Both riders are read off the cast rather than watched for: `c.charge`
    and `c.opportunity` are what `use` raises for those two ways of swinging,
    and this row *is* the creature's basic attack, so its own opportunity
    attack comes through here and nowhere else."""
    if not c.strike():
        return
    c.hit()
    c.mark()
    if c.charge:
        c.push(1)
    if c.opportunity:
        c.prone()


_M4779_SLIPPED = "an enemy marked by the m4779 shifts"


def _marked_enemy_shifts(world: World, me: int, ev: MoveStart) -> bool:
    return (
        ev.kind_ == "shift"
        and ev.actor != me
        and world.relations.holds(Relation.MARKED_BY, me, ev.actor)
    )


@power(
    "m4779a1",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M4779_SLIPPED,
    on=Trigger(MoveStart, when=_marked_enemy_shifts, text=_M4779_SLIPPED),
)
def m4779a1(c: Cast) -> None:
    """An interrupt resolves before the step, which is why the trigger watches
    the start of the shift rather than the adjacency it loses."""
    if c.target is not None:
        use(c.world, c.me, "m4779a0", targets=[c.target], spend=False)


_M4779_RIDER = "a friendly rider of 6th level or higher on the m4779 hits with a charge"


@power(
    "m4779a2",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M4779_RIDER,
    on=Trigger(Hit, when=_rider_charged, text=_M4779_RIDER),
)
def m4779a2(c: Cast) -> None:
    """The target of the charge, not of anything this creature did -- read off
    the trigger, because the dispatcher would aim a triggered row at the
    rider instead."""
    who = getattr(c.trigger, "target", None)
    if who is not None:
        c.push(1, on=who)


# -- m4902 ------------------------------------------------------------------


@power(
    "m4902a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4902a0(c: Cast) -> None:
    """An aura 1 for the board to draw, with the bonus held per occupant.

    "Allies within the aura" leaves the caster out, and the `ally` pool puts
    it in -- so it is dropped here.
    """
    me = c.me
    _aura(
        c,
        1,
        lambda who: who != me and who in c.allies(),
        lambda who: c.bonus(Defense.AC, 2, until=When.ENCOUNTER, on=who),
    )


@power(
    "m4902a1",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4902a1(c: Cast) -> None:
    """The printed line counts allies *of this stat block*, not allies at
    large -- which is an `Ident.ref` and nothing else says it, since
    `c.is_kind` answers about type words several stat blocks share. The
    caster is left out: the count is of its friends."""
    me = c.me

    def mobbed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or not _melee_ctx(ctx):
            return False
        return (
            sum(
                1
                for a in c.within(1, of=who, side="ally")
                if a != me and _same_row(c, a, "m4902")
            )
            >= 2
        )

    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=mobbed)


@power(
    "m4902a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 6),
)
def m4902a2(c: Cast) -> None:
    """Bloodied swaps the expression rather than adding to it, so the header
    keeps the printed line that rescales and the larger one is rolled here."""
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("1d8", 10)
    else:
        c.hit()


@power(
    "m4902a3",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
)
def m4902a3(c: Cast) -> None:
    """A mark that burns whoever looks away, and lasts the fight.

    "Or until the m4902 uses this power again" is the previous mark ended by
    hand, together with the watch it carried -- both are labelled off this
    ref, so one sweep takes the pair.

    The burn answers `PowerUsed` rather than each `AttackDeclared`: an attack
    is announced once per target, so a burst would have paid out once for
    every creature it caught. `PowerUsed` fires once per use and carries the
    whole target list, which is what "does not include the m4902" is asking.
    """
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref
    for eff in list(c.world.effects.live.values()):
        if eff.source == me and eff.label.startswith(ref):
            c.world.effects.end(eff, "the m4902 used it again")

    def scorch(ev: PowerUsed) -> None:
        p = get(ev.power)
        if ev.actor != victim or p is None or not p.is_attack:
            return
        if me not in ev.targets:
            c.flat(10, dtype=DamageType.FIRE, on=victim)

    hold = c.mark(until=When.ENCOUNTER, on=victim)
    burn = c.watch(PowerUsed, scorch, until=When.ENCOUNTER, on=me, label=f"{ref} burn")
    if hold is not None:
        hold.on_end.append(lambda: c.world.effects.end(burn, "the mark ended"))


_M4902_MISSED = "an enemy misses the m4902 with a melee attack"


@power(
    "m4902a4",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(1),
    target=NO_TARGET,
    trigger=_M4902_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M4902_MISSED),
)
def m4902a4(c: Cast) -> None:
    """One of its friends takes the opening.

    "One ally adjacent to the triggering enemy" leaves the m4902 itself out,
    and the `ally` pool puts it in -- so it is dropped here, and which of the
    rest swings is a real choice.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    beside = sorted(a for a in c.within(1, of=who, side="ally") if a != c.me)
    if not beside:
        return
    friend = c.choose(beside, "m4902a4: who swings")
    if friend is not None:
        c.grant_attack(friend, on=who)


# -- m4988 ------------------------------------------------------------------


@power(
    "m4988a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 9),
)
def m4988a0(c: Cast) -> None:
    """An Effect line, so the mark is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m4988a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m4988a1(c: Cast) -> None:
    """Range 15/30: the header carries the short range, which is the only one
    the engine measures. An Effect line, so the mark is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m4988a2",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m4988a2(c: Cast) -> None:
    """The printed line is unqualified, so the opening is granted to this
    creature's whole side rather than to itself alone -- and it is handed out
    before the blink, which is the order the card reads in and the only order
    in which anybody is still adjacent."""
    for foe in c.within(1, side="enemy"):
        c.grants_advantage(until=When.EONT, on=foe, to="allies")
    c.teleport(2)


_M4988_IGNORED = "an enemy marked by the m4988 within 5 squares attacks somebody else"


def _marked_enemy_looks_away(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "attacker", None)
    if who is None or not world.relations.holds(Relation.MARKED_BY, me, who):
        return False
    if not leaves_me_out(world, me, ev):
        return False
    return distance_between(world, me, who) <= 5


@power(
    "m4988a3",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger=_M4988_IGNORED,
    on=Trigger(AttackDeclared, when=_marked_enemy_looks_away, text=_M4988_IGNORED),
)
def m4988a3(c: Cast) -> None:
    """`leaves_me_out` is the predicate, not `ev.target != me`: an attack is
    announced once per target, so a burst that caught the m4988 still passed
    a per-announcement test on every other target's row. `among` carries the
    whole target list of the one use, which is the only thing that answers it.
    """
    who = getattr(c.trigger, "attacker", None) or c.target
    if who is None:
        return
    c.flat(5, dtype=DamageType.PSYCHIC, on=who)
    c.dazed(until=When.EOTNT, on=who)


_M4988_BLED = "the m4988 is first bloodied"


@power(
    "m4988a4",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4988_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M4988_BLED),
)
def m4988a4(c: Cast) -> None:
    """"First bloodied" needs no guard -- `Bloodied` is emitted on the
    crossing and nowhere else."""
    me = c.me
    c.temp_hp(10, on=me)
    c.penalty("attack", 2, until=When.ENCOUNTER, on=me)
    c.bonus("damage", 4, until=When.ENCOUNTER, on=me)


# -- m719 -------------------------------------------------------------------


@power(
    "m719a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m719a0(c: Cast) -> None:
    """An aura 1 for the board to draw, with the penalty held per occupant."""
    _aura(
        c,
        1,
        lambda who: who in c.enemies() and _living(c, who),
        lambda who: c.penalty("attack", 2, until=When.ENCOUNTER, on=who),
    )


@power(
    "m719a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d4", 4),
)
def m719a1(c: Cast) -> None:
    """An Effect line, so the mark is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m719a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 9),
)
def m719a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m719a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m719a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m719a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("3d6", 4),
    requires=_has_an_opening,
    requires_text="the target must be granting combat advantage to the m719",
)
def m719a4(c: Cast) -> None:
    """The printed target is a creature that is already giving itself away,
    which no `Target` can say -- so `requires` carries the half about the
    board and the body aims at whoever within reach actually qualifies. A row
    that may only be used against one kind of creature is not a choice of
    target, it is a restriction on one.

    "Regains half the normal hit points from healing" has no seam to hang on:
    `resolve.heal` puts the hit points on and *then* announces `Healed`, and
    `Healed` is a notification rather than a `Decision`, so nothing can reduce
    the number on the way in. What is left is to take the surplus back as the
    healing lands, which produces the printed total and is the only place a
    rule about somebody else's healing can reach. See the report.
    """
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        victim = next(
            (
                f
                for f in sorted(c.within(1, side="enemy"))
                if has_combat_advantage(c.world, c.me, f)
            ),
            None,
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)

    def stanch(ev: Healed) -> None:
        if ev.target != victim or ev.amount <= 0 or not alive(c.world, victim):
            return
        health = c.world.get(victim, Health)
        if health is not None:
            health.hp = max(1, health.hp - (ev.amount - ev.amount // 2))

    c.watch(Healed, stanch, until=When.EONT, on=victim, label=f"{c.ref} stanched")
