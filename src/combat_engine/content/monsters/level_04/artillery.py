"""Monster abilities, level 4: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=9)` and `Damage("1d10", 4)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

Three things this file had to settle.

**"Against creatures that have no cover"** gates a trait on a fact about two
positions, so it cannot be an effect put on and taken off. The attack half
is a modifier with a gate, which `resolve.attack` asks as it assembles the
roll; the extra die is a `Hit` watch, because a modifier's value is an `int`
and this one is `1d6`.

**A delayed rider keyed to the target's own next turn** -- "if it does not
end its next turn 4 squares from where it started" -- is two watches and the
square recorded between them. Nothing else can answer "where it started its
turn": the turn is the only thing that marks that point, and by the time the
rider is read the creature has moved.

**A saving throw to avoid a condition** is rolled against the effect that
has just been applied. `Effects.apply` installs everything before it
announces `ConditionApplied`, and ending the effect from that announcement
is supported, so the throw is made there and a success takes the hold off
again before anybody sees it.
"""

from __future__ import annotations

from typing import Any

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
    ONE_OTHER_ALLY,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Defences,
    Keyword,
    Melee,
    Position,
    Ranged,
    Square,
    UpTo,
    Usage,
    When,
    distance,
    get,
    power,
)
from combat_engine.engine.events import ConditionApplied, Dropped, Hit, TurnEnd, TurnStart
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import cover_between
from combat_engine.engine.triggers import Trigger, about_me, both, by_me

#: What a printed "close or area attack" covers. Asked off the power in the
#: registry, because an event carries the ref and not the range.
_SPREADS = ("close_blast", "close_burst", "area_burst")


def _reach_of(ref: str) -> str:
    p = get(ref)
    return p.reach.kind if p is not None else ""


# --------------------------------------------------------------------------
# m119
# --------------------------------------------------------------------------


@power(
    "m119a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m119a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m119a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC),
)
def m119a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


_M119_DOWN = "the m119 is reduced to 0 hit points"


@power(
    "m119a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC),
    trigger=_M119_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M119_DOWN),
)
def m119a2(c: Cast) -> None:
    """The printed line names no targets at all, only the burst. Enemies,
    as the other death bursts in the tree read it -- the creature at the
    centre is already dead and `EACH_CREATURE` would catch it."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m168
# --------------------------------------------------------------------------


@power(
    "m168a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m168a0(c: Cast) -> None:
    """Shoots better at anybody standing in the open, and hits harder.

    Cover is a fact about two positions and both of them move, so neither
    half can be settled now. The attack is a gated modifier, asked as the
    roll is put together. The damage cannot be: a modifier's value is an
    `int` and the printed line is a die, so it is a `Hit` watch that rolls
    the extra die itself -- `Hit` is announced before the damage is, so the
    two land together.
    """
    me = c.me

    def in_the_open(who: int | None, ref: str) -> bool:
        if who is None or _reach_of(ref) != "ranged":
            return False
        return cover_between(c.world, me, who, ranged=True) is Cover.NONE

    c.bonus(
        "attack",
        2,
        until=When.ENCOUNTER,
        on=me,
        when=lambda ctx: in_the_open(ctx.get("target"), ctx.get("power") or ""),
    )

    def harder(ev: Hit) -> None:
        if ev.attacker == me and in_the_open(ev.target, ev.power):
            c.damage("1d6", on=ev.target)

    c.watch(Hit, harder, until=When.ENCOUNTER, on=me, label="m168a0")


@power(
    "m168a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m168a1(c: Cast) -> None:
    """Gives a square back to every shove, whoever is doing the shoving."""
    c.resist_forced(1)


@power(
    "m168a2",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m168a2(c: Cast) -> None:
    """Keeps its feet, on a save.

    The throw is made against the prone hold itself the moment it is
    announced -- `Effects.apply` has installed everything by then and a
    listener may end it -- so a success takes the condition off before the
    creature has been knocked down in any readable sense.

    Prone it lays on itself is left alone: the printed trigger is an attack
    knocking it down, and the only mark of that on `ConditionApplied` is who
    the source was.
    """
    me = c.me

    def brace(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE or ev.source == me:
            return
        for eff in c.world.effects.of(me):
            if Condition.PRONE in eff.conditions:
                c.world.effects.save(eff)
                return

    c.watch(ConditionApplied, brace, until=When.ENCOUNTER, on=me, label="m168a2")


@power(
    "m168a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m168a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m168a4",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 3),
)
def m168a4(c: Cast) -> None:
    """The printed range is 30/60; `Range` holds one number and the engine
    has no long-range penalty to apply, so the normal band is what is
    written."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m2832
# --------------------------------------------------------------------------


@power(
    "m2832a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 4, dtype=DamageType.THUNDER),
)
def m2832a0(c: Cast) -> None:
    """Bloodied is asked after the damage lands, so the hit that bloodies is
    the hit that knocks down."""
    if c.strike():
        c.hit()
        if c.bloodied():
            c.prone()


@power(
    "m2832a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING),
)
def m2832a1(c: Cast) -> None:
    """A charge that goes off unless the target runs from where it stood.

    "Where it started its turn" is only knowable at the start of that turn,
    so the square is recorded then and read back at the end of it. Both
    watches are held for the encounter and ended by hand once the turn they
    were waiting for has been had: a duration that runs out *at* the end of
    a turn cannot be relied on to outlive the end of that turn.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    began: dict[str, Square | None] = {"at": None}

    def mark(ev: TurnStart) -> None:
        if ev.actor != victim:
            return
        pos = c.world.get(victim, Position)
        began["at"] = pos.square if pos else None

    def settle(ev: TurnEnd) -> None:
        if ev.actor != victim or began["at"] is None:
            return
        pos = c.world.get(victim, Position)
        if pos is None or distance(pos.square, began["at"]) < 4:
            c.damage("3d6", 6, dtype=DamageType.LIGHTNING, on=victim)
        c.world.effects.end(opened, "spent")
        c.world.effects.end(closed, "spent")

    opened = c.watch(TurnStart, mark, until=When.ENCOUNTER, on=victim, label="m2832a1 start")
    closed = c.watch(TurnEnd, settle, until=When.ENCOUNTER, on=victim, label="m2832a1 end")


_M2832_DOWN = "the m2832 drops to 0 hit points"


@power(
    "m2832a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", dtype=DamageType.LIGHTNING),
    trigger=_M2832_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M2832_DOWN),
)
def m2832a2(c: Cast) -> None:
    """Lightning *and* thunder: the header keeps the first of the two printed
    types, which is what the resistance check reads, and both keywords carry
    the rest."""
    if c.strike():
        c.hit()
        c.push(3)
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m292
# --------------------------------------------------------------------------


@power(
    "m292a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d8"),
)
def m292a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m292a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d4", 4, dtype=DamageType.FORCE),
)
def m292a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m292a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m292a2(c: Cast) -> None:
    """Three separate attacks against three different creatures, which is
    `UpTo(3)` and a body that rolls once for whichever one it is called
    for."""
    if c.strike():
        c.hit()


@power(
    "m292a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.AREA],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m292a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m329
# --------------------------------------------------------------------------


@power(
    "m329a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m329a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m329a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 6, dtype=DamageType.FIRE),
)
def m329a1(c: Cast) -> None:
    """A miss splashes whoever is standing next to the one it missed. The
    printed line says creatures, not enemies, so its own side is splashed
    too; only the creature aimed at is left out, having already been missed.
    """
    if c.strike():
        c.hit()
        return
    for near in c.within(1, of=c.target):
        if near != c.target:
            c.damage("1d6", dtype=DamageType.FIRE, on=near)


# --------------------------------------------------------------------------
# m4790
# --------------------------------------------------------------------------


@power(
    "m4790a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage(bonus=4, kind=MINION),
)
def m4790a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4790a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=7),
    damage=Damage(bonus=4, kind=MINION),
)
def m4790a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4790a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=7),
    damage=Damage(bonus=6, kind=MINION),
)
def m4790a2(c: Cast) -> None:
    """A minion's once-a-fight shot. `MINION` rather than `LIMITED`: the
    number is printed flat because the creature is a minion, not because the
    power is limited, and that is what decides how it rescales."""
    if c.strike():
        c.hit()
        c.prone()


# --------------------------------------------------------------------------
# m5027
# --------------------------------------------------------------------------


@power(
    "m5027a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8"),
)
def m5027a0(c: Cast) -> None:
    """The swing is the ally's own free action, so it is offered rather than
    done to it, and `c.grant_attack` with no `ref` rolls whatever that
    creature's basic attack actually is."""
    if not c.strike():
        return
    c.hit()
    beside = [a for a in c.within(1, of=c.target, side="ally") if a != c.me]
    friend = c.choose(sorted(beside), "an ally makes a melee basic attack")
    if friend is not None:
        c.grant_attack(friend, on=c.target, attack_bonus=4)


@power(
    "m5027a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 7),
)
def m5027a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)


@power(
    "m5027a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.AREA],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m5027a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m5027a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.IMPLEMENT, Keyword.AREA],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("3d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m5027a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5027a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
)
def m5027a4(c: Cast) -> None:
    """"One ally within 5 squares" excludes the m5027 itself, which is what
    `ONE_OTHER_ALLY` is for; the duration is the ally's next turn, not the
    leader's."""
    c.bonus("attack", 2, until=When.EOTNT)


def _by_spread(world: Any, me: int, ev: Any) -> bool:
    return _reach_of(getattr(ev, "power", "")) in _SPREADS


_M5027_SPREAD_HIT = "the m5027 hits an enemy with a close or an area attack"


@power(
    "m5027a5",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M5027_SPREAD_HIT,
    on=Trigger(Hit, when=both(by_me, _by_spread), text=_M5027_SPREAD_HIT),
)
def m5027a5(c: Cast) -> None:
    """The enemy left exposed is the one whose hit fired this.

    The printed line is "one enemy of its choice that was hit by the
    attack", and a `Hit` carries one target rather than the whole list -- so
    the choice is between the creature that triggered this and nobody. It is
    a choice the row would almost always make anyway.
    """
    c.teleport(3)
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.grants_advantage(on=foe, until=When.EONT, to="allies")


# --------------------------------------------------------------------------
# m361
# --------------------------------------------------------------------------


@power(
    "m361a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage(bonus=5, kind=MINION),
)
def m361a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4996
# --------------------------------------------------------------------------


@power(
    "m4996a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage(bonus=2, dtype=DamageType.POISON, kind=MINION),
)
def m4996a0(c: Cast) -> None:
    """Vulnerability that stacks with itself, smaller each time after the
    first. `c.vulnerable` already adds to what is there, so the printed
    "increase it by 2" is the same call with a different number -- and which
    number is which is read off the target's own defences."""
    if not c.strike():
        return
    c.hit()
    guard = c.world.get(c.target, Defences)
    already = guard.vulnerable.get(DamageType.POISON, 0) if guard else 0
    c.vulnerable(2 if already else 5, DamageType.POISON, until=When.EONT)
