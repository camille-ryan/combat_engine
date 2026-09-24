"""Monster abilities, level 4: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=9)` and `Damage("1d8", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

Three readings recur and are settled once.

A **blast or burst with no printed target line** is read as enemies. The
specs that mean everybody print "creatures in the blast" and the ones that
mean one side print "enemies in the burst"; where the line is silent, the
reading that does not set a monster on its own allies is the safe one.

**"First Failed Saving Throw" fires once.** `Effect.escalate` runs on every
failed save, so a row whose escalation leaves the effect standing clears the
callback as it runs; the level-2 shape got this for free by ending the
effect it escalated from.

**"If the target ends its next turn ..." is a `TurnEnd` watch on
`When.EOTNT`**, which fires on the boundary it expires at and is gone
afterwards, so nothing has to take it down by hand.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import settle
from combat_engine.content.monsters.level_03.controllers import (
    _nonminion,
    _same_stock,
    _vanish,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    Stats,
    Target,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    DamageApplied,
    DamageRolled,
    Dropped,
    Miss,
    TurnEnd,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, allies, distance_between
from combat_engine.engine.triggers import (
    Trigger,
    both,
    by_melee,
    targets_me,
)

#: The four defences, for the rows that move all of them at once.
DEFENCES = (AC, FORT, REF, WILL)


def _level_of(world: World, eid: int) -> int:
    """A creature's level, for a printed "of level 6 or lower". Anything with
    no stat block behind it is out of reach of that sentence."""
    stats = world.get(eid, Stats)
    return 99 if stats is None else stats.level


# --------------------------------------------------------------------------
# m135
# --------------------------------------------------------------------------


@power(
    "m135a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", dtype=DamageType.NECROTIC),
)
def m135a0(c: Cast) -> None:
    """"Loses a healing surge" is a surge spent for nothing, which is what
    `c.spend_surge` is: the pool drops and the creature is not healed."""
    if c.strike():
        c.hit()
        c.spend_surge()


@power(
    "m135a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 8, dtype=DamageType.NECROTIC),
)
def m135a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m135a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m135a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m135a3",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m135a3(c: Cast) -> None:
    """A destroyed ally put back on its feet.

    Written with no declared target because the dispatcher only offers live
    creatures, and every one of this row's is dead. "One-half its bloodied
    value" is a quarter of its maximum, which is `c.surge_value`.

    Nothing is done about "it can stand up as a free action": healing from
    below zero clears what dropping it imposed, and prone is one of those
    three, so it is already up.
    """
    fallen = sorted(
        a
        for a in allies(c.world, c.me)
        if not alive(c.world, a)
        and c.is_kind("undead", on=a)
        and _level_of(c.world, a) <= 6
        and _nonminion(c.world, a)
        and c.distance(to=a) <= 10
    )
    who = c.choose(fallen, "which of the fallen rises") if fallen else None
    if who is not None:
        c.heal(c.surge_value(of=who), on=who)


# --------------------------------------------------------------------------
# m2942
# --------------------------------------------------------------------------


@power(
    "m2942a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m2942a0(c: Cast) -> None:
    """No range printed where the next row prints Ranged 10, so this is the
    creature's melee attack."""
    if c.strike():
        c.hit()


@power(
    "m2942a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d4", 4, dtype=DamageType.PSYCHIC),
)
def m2942a1(c: Cast) -> None:
    """The swap is the escalation, and the daze survives it -- so the
    callback clears itself rather than leaning on the effect ending."""

    def blink(eff: Effect) -> None:
        eff.escalate = None
        c.swap(eff.owner)

    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, escalate=blink)


@power(
    "m2942a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("any", 1, label="One helpless or unconscious creature"),
    keywords=[Keyword.HEALING],
)
def m2942a2(c: Cast) -> None:
    """The printed target restriction lives in the `Target` label, which is
    prose: `coup_de_grace` is what enforces it, refusing outright for
    anything that is not actually helpless. The price is paid first either
    way, as printed. "Regains all of its hit points" is whatever it is
    currently down, so it is read off `c.missing`.
    """
    settle(c)
    if c.coup_de_grace() and not alive(c.world, c.target):
        c.heal(c.missing(on=c.me), on=c.me)


# --------------------------------------------------------------------------
# m3025
# --------------------------------------------------------------------------


@power(
    "m3025a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m3025a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3025a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m3025a1(c: Cast) -> None:
    """"Already dazed" is asked before this row's own daze lands, or every
    hit would qualify. "As long as it remains dazed" is tied to the daze
    this row applied -- a longer-lasting one it was already carrying is not
    something the engine can measure the weakness against.
    """
    already = c.is_(Condition.DAZED)
    if not c.strike():
        return
    c.hit()
    hold = c.dazed(until=When.SAVE_ENDS)
    if not already or hold is None:
        return
    sapped = c.weakened(until=When.SAVE_ENDS)
    if sapped is not None:
        hold.on_end.append(lambda: c.world.effects.end(sapped, "no longer dazed"))


@power(
    "m3025a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=8),
)
def m3025a2(c: Cast) -> None:
    """A burst that picks one creature out of itself, as printed. No damage
    at all -- the whole of the hit is the penalty."""
    if c.strike():
        c.penalty("attack", 2, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m3040
# --------------------------------------------------------------------------


@power(
    "m3040a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 3),
)
def m3040a0(c: Cast) -> None:
    """The slide is an Effect line, so it happens whether or not the blow
    landed."""
    if c.strike():
        c.hit()
    c.slide(1)


@power(
    "m3040a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("2d8", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m3040a1(c: Cast) -> None:
    """"Nonplants in the blast" catches its own side as readily as anybody
    else's, so the target is every creature and the exemption is asked of
    each one -- before the roll, since a plant is never attacked at all."""
    if c.is_kind("plant"):
        return
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m3040a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
)
def m3040a2(c: Cast) -> None:
    """Chosen in the body rather than declared: `ONE_ALLY` would have let the
    dispatcher pick whichever friend was nearest, plant or not."""
    grove = sorted(
        a for a in c.within(5, side="ally") if a != c.me and c.is_kind("plant", on=a)
    )
    friend = c.choose(grove, "which plant ally stirs") if grove else None
    if friend is not None:
        c.shift(1, who=friend)


_M3040_STRUCK = "the m3040 is hit while one of its own kind is within 5 squares"


def _m3040_struck(world: World, me: int, ev: DamageRolled) -> bool:
    """"Hit by an attack", read off the damage rather than off the `Hit`.

    The half this row hands its neighbour is damage too, and without the
    test for an attack the two of them pass the same blow back and forth,
    halving it, until it reaches nothing.
    """
    dealt = get(getattr(ev, "detail", "") or "")
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and dealt is not None
        and dealt.attack is not None
        and any(
            alive(world, a)
            and _same_stock(world, a, me)
            and distance_between(world, me, a) <= 5
            for a in allies(world, me)
        )
    )


@power(
    "m3040a3",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3040_STRUCK,
    on=Trigger(DamageRolled, when=_m3040_struck, text=_M3040_STRUCK),
)
def m3040a3(c: Cast) -> None:
    """Both take half, which means the blow is split rather than reduced.

    Declared on `DamageRolled` rather than on the printed `Hit`: that event
    is the seam the engine keeps mutable for exactly this, and an attack
    that lands for nothing has no halves to share. A free action, so it
    resolves in the reaction window -- which is still before the number is
    read back off the event.
    """
    ev = c.trigger
    total = getattr(ev, "amount", 0)
    if total <= 0:
        return
    kin = sorted(
        a
        for a in c.allies()
        if alive(c.world, a) and _same_stock(c.world, a, c.me) and c.distance(to=a) <= 5
    )
    friend = c.choose(kin, "which of its own kind shares the blow") if kin else None
    if friend is None:
        return
    ev.amount = total // 2
    c.flat(total // 2, dtype=getattr(ev, "dtype", DamageType.UNTYPED), on=friend)


# --------------------------------------------------------------------------
# m3086
# --------------------------------------------------------------------------


@power(
    "m3086a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m3086a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3086a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3086a1(c: Cast) -> None:
    """The zone is laid once for the whole power, not once per target."""
    if c.first:
        c.zone(c.area(), until=When.EONT, blocks_sight=True)
    if c.strike():
        c.hit()


_M3086_HURT = "the m3086 takes damage"


@power(
    "m3086a2",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M3086_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M3086_HURT),
)
def m3086a2(c: Cast) -> None:
    _vanish(c)


# --------------------------------------------------------------------------
# m4927
# --------------------------------------------------------------------------

#: The two shapes m4927a4 chooses between, and the prefix its hold is
#: labelled with so the three attacks can read which one is in force.
_SHAPES = ("jackal", "human")
_SHAPE_LABEL = "m4927a4 "


def _in_shape(word: str):  # noqa: ANN202
    """A printed Requirement naming one of the two forms.

    A creature that has not changed shape yet is in whatever shape it was
    found in, which the stat block does not say -- so an undeclared form
    rules out none of the attacks. Once it has changed, the hold is the
    answer.
    """

    def gate(world: World, eid: int) -> bool:
        for effect in world.effects.of(eid):
            if effect.label.startswith(_SHAPE_LABEL):
                return effect.label.endswith(word)
        return True

    return gate


@power(
    "m4927a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
    requires=_in_shape("jackal"),
    requires_text="the m4927 must be in its jackal shape",
)
def m4927a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4927a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
    requires=_in_shape("human"),
    requires_text="the m4927 must be in its human shape",
)
def m4927a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4927a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.THUNDER),
    requires=_in_shape("jackal"),
    requires_text="the m4927 must be in its jackal shape",
)
def m4927a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4927a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.SLEEP],
    attack=Attack(vs=WILL, printed=7),
)
def m4927a3(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the sleep.

    The extra saving throw is rolled against *this* hold rather than through
    `c.save`, which takes the first save-ends effect it finds and would shake
    off something else the creature happened to be carrying. The watch lives
    on the encounter clock and is torn down with the sleep, so it cannot
    outlast it and a second casting does not inherit the first one's
    listener.
    """
    if not c.strike():
        return
    hold = c.unconscious(until=When.SAVE_ENDS)
    if hold is None:
        return
    victim = c.target

    def rouse(ev: DamageApplied) -> None:
        if ev.target == victim and not hold.ended:
            c.world.effects.save(hold)

    seen = c.watch(DamageApplied, rouse, until=When.ENCOUNTER, on=victim, label=c.ref)
    hold.on_end.append(lambda: c.world.effects.end(seen, "no longer asleep"))


@power(
    "m4927a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m4927a4(c: Cast) -> None:
    """Two shapes and nothing else: the statistics do not change, so all the
    form is for is the Requirement on the three attacks above.

    Both of the printed endings are written. Using it again ends the shape it
    was in, which `c.form` does not do for itself -- a polymorph is not a
    stance, and this one is printed as one. Dropping to 0 hit points ends it
    too, which is a watch that goes out with the shape.
    """
    for effect in list(c.world.effects.of(c.me)):
        if effect.label.startswith(_SHAPE_LABEL):
            c.world.effects.end(effect, "it changed shape again")
    shape = c.choose(list(_SHAPES), "which shape") or _SHAPES[0]
    hold = c.form(until=When.ENCOUNTER, revert=None, label=f"{_SHAPE_LABEL}{shape}")

    def slump(ev: Dropped) -> None:
        if ev.actor == c.me and not hold.ended:
            c.world.effects.end(hold, "it dropped")

    seen = c.watch(Dropped, slump, until=When.ENCOUNTER, on=c.me, label=c.ref)
    hold.on_end.append(lambda: c.world.effects.end(seen, "the shape is gone"))


# --------------------------------------------------------------------------
# m5033
# --------------------------------------------------------------------------


@power(
    "m5033a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m5033a0(c: Cast) -> None:
    """Ending a turn in it, not entering it or starting there, so this is a
    `TurnEnd` watch rather than `c.hazard`, whose teeth bite at the other two
    moments. Who is inside is asked of the aura as the turn ends."""
    ring = c.aura(3, until=When.ENCOUNTER)

    def press(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)
        for defence in DEFENCES:
            c.penalty(defence, 2, on=ev.actor, until=When.EOTNT)

    c.watch(TurnEnd, press, until=When.ENCOUNTER, on=c.me, label="m5033a0")


@power(
    "m5033a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 5),
)
def m5033a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5033a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.AREA],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 3, kind=LIMITED),
)
def m5033a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5033a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5033a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m5033a4",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d10", 5, kind=LIMITED),
)
def m5033a4(c: Cast) -> None:
    """The echo is measured at the end of the target's next turn, from the
    m5033 as it stands then -- both of them may have walked since."""
    if not c.strike():
        return
    c.hit()
    victim = c.target

    def echo(ev: TurnEnd) -> None:
        if ev.actor == victim and not ev.ghost and c.distance(to=victim) <= 5:
            c.flat(5, dtype=DamageType.THUNDER, on=victim)

    c.watch(TurnEnd, echo, until=When.EOTNT, on=victim, label=c.ref)


# --------------------------------------------------------------------------
# m728
# --------------------------------------------------------------------------


@power(
    "m728a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m728a0(c: Cast) -> None:
    """"Adjacent" is adjacent to the m728, which is the only creature the
    printed line has to measure from. `c.grant_attack` with no `ref` rolls
    whatever that creature's own basic attack is -- which for this monster is
    this row, so the miss hands the swing on exactly once and no further.
    """
    if c.strike():
        c.hit()
        return
    beside = sorted(a for a in c.within(1, side="ally") if a != c.me)
    friend = c.choose(beside, "which ally swings") if beside else None
    if friend is None:
        return
    reachable = sorted(c.within(1, of=friend, side="enemy"))
    foe = c.choose(reachable, "the ally makes a basic attack") if reachable else None
    if foe is not None:
        c.grant_attack(friend, on=foe)


_M728_MISSED_MELEE = "the m728 is missed by a melee attack"


@power(
    "m728a1",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M728_MISSED_MELEE,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M728_MISSED_MELEE),
)
def m728a1(c: Cast) -> None:
    """"Up to two" is offered twice and may be declined, rather than taking
    the nearest two: which ally is worth moving is the whole decision."""
    c.shift(1)
    pool = sorted(a for a in c.allies() if alive(c.world, a) and c.can_see(a))
    for _ in range(2):
        if not pool:
            return
        friend = c.choose(pool, "which ally slips away too", optional=True)
        if friend is None:
            return
        pool.remove(friend)
        c.shift(1, who=friend)


@power(
    "m728a2",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m728a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Gated on the wound
    rather than put on and taken off as hit points move: the gate is asked
    when the defence is read, so nothing has to watch the health bar."""

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(on=c.me)

    for defence in DEFENCES:
        c.bonus(defence, 3, on=c.me, until=When.ENCOUNTER, when=hurt)
