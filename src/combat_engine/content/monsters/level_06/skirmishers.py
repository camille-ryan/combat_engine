"""Monster abilities, level 6: the ones that move, and the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=11)` and `Damage("2d8", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the five levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard or move
actions are plainly traits or immediate actions and are written as such; a
printed range of "5/10" takes the **normal** range; a stat block that prints
no range at all means melee 1; and a row that moves and swings takes the
swing first, because the movement picks its own destination and one taken
first can leave the target out of reach. The rows here that print the
movement first -- one that steps both before and after, and one that names
the order outright -- say so, and are written in the printed order.

Four things this level needed that the levels below did not. **What a
creature is doing rather than what it can do**: `Movement.using` is held
past the end of a move, so "Requirement: it must be climbing" is a real gate
at last -- `_climbing` is `Cast.moving_as` asked from a header, where there
is no `Cast` yet. **A move worth paying for**: three rows here pay out for
having moved and each wants a different half of the same fact, so
`_after_moving` gathers how it moved, where from, where to and how many
squares it covered, and hands all four to whoever asked. **A sustain that
also pays**: `c.on_sustain` is what a "Sustain Standard: 2d8 + 5 damage"
line needed, and the grab it keeps alive is applied on a `When.SUSTAIN`
clock so that not sustaining is what lets go. And **a restriction that is
really a Requirement on somebody else's row**: "it cannot use X or Y while
bloodied" is printed on a third row and is a gate on the other two, so it is
written where the engine re-asks it rather than as a hold one use installs.

The helpers that charge, that fly, that run at a named creature, that count
a crowd and that hold a lurker unseen were written for levels 2 to 5 and are
imported rather than copied.

Skirmishers first, then lurkers, each group in ref order.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from combat_engine.content.chargen import LIGHT
from combat_engine.content.monsters.level_02.skirmishers import (
    _advantage_rider,
    _beside_a_ward,
    _shed,
)
from combat_engine.content.monsters.level_03.skirmishers import (
    _an_enemy_is_poisoned,
    _grabbing,
    _is_bloodied,
    _poisoned,
)
from combat_engine.content.monsters.level_04.skirmishers import (
    _charge_rider,
    _guarded_move,
    _has_advantage,
    _struck,
)
from combat_engine.content.monsters.level_05.skirmishers import (
    _MELEE_KINDS,
    _charge,
    _fly_speed,
    _reach_kind,
    _run_at,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
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
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defense,
    Effect,
    Gear,
    Keyword,
    Melee,
    Movement,
    Position,
    Powers,
    Ranged,
    Relation,
    Square,
    Usage,
    When,
    Window,
    World,
    distance,
    get,
    power,
    use,
    would_hit_me,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageRolled,
    Hit,
    Moved,
    MoveEnd,
    MoveStart,
    RelationSet,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    distance_between,
    flanked_by,
    has_combat_advantage,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_ranged,
    either,
    targets_me,
)

#: How bad a rusting item is allowed to get, as the printed line caps it.
_RUST_FLOOR = -5


def _not_bloodied(world: World, eid: int) -> bool:
    return not _is_bloodied(world, eid)


def _climbing(world: World, eid: int) -> bool:
    """Is this creature climbing **right now**?

    `Cast.moving_as`, asked from a header where there is no `Cast` yet.
    `Movement.modes` only ever said what a creature *could* do, which made
    a printed "it must be climbing" true for anything with a climb speed at
    all; `Movement.using` is what it is doing, and `walk` holds it past the
    end of the move because a creature that climbed a wall is still on the
    wall when the power is used.
    """
    moves = world.get(eid, Movement)
    return moves is not None and moves.using == "climb"


def _after_moving(
    c: Cast, fn: Callable[[str, Square | None, Square, int], None]
) -> None:
    """Call `fn(kind, from_, to, steps)` at the end of every move it makes.

    Four rows here pay out for having moved and each wants a different half
    of the same fact: how it moved, how far it ended up from where it
    started, and how many squares it actually covered. `MoveEnd` carries
    only the arrival and `Moved` only one step, so the departure square is
    read off `MoveStart` -- which says *how* as well, and whose windows both
    run before the first step is taken.
    """
    me = c.me
    trip: dict[str, Any] = {"kind": "", "from": None, "steps": 0}

    def began(ev: MoveStart) -> None:
        if ev.actor != me:
            return
        here = c.world.get(me, Position)
        trip["kind"] = ev.kind_
        trip["steps"] = 0
        trip["from"] = here.square if here is not None else None

    def stepped(ev: Moved) -> None:
        if ev.actor == me:
            trip["steps"] += 1

    def ended(ev: MoveEnd) -> None:
        if ev.actor == me:
            fn(trip["kind"], trip["from"], ev.at, trip["steps"])

    c.watch(MoveStart, began, until=When.ENCOUNTER, on=me, label=f"{c.ref} from")
    c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label=f"{c.ref} steps")
    c.watch(MoveEnd, ended, until=When.ENCOUNTER, on=me, label=f"{c.ref} to")


def _renew(c: Cast, held: list[Effect], make: Callable[[], Effect | None]) -> None:
    """Replace a hold that a row keeps re-earning, rather than stacking it.

    "Until the end of its next turn" said again on the next move is one hold
    with a fresh clock, not two -- and two of these are damage riders, which
    would pay out twice.
    """
    for old in held:
        c.world.effects.end(old, "renewed")
    held.clear()
    fresh = make()
    if fresh is not None:
        held.append(fresh)


def _fiery_blows(c: Cast, pack: Iterable[int], amount: int, until: When) -> Effect:
    """`amount` more, as fire, on every melee blow these creatures land.

    A damage modifier would lose the type -- `c.bonus("damage", 5)` adds to
    whatever packet is already being dealt -- and the printed line says
    fire, which a resistance reads. So it is a rider on the `Hit`, dealt as
    its own packet.
    """
    who = set(pack)

    def rider(ev: Hit) -> None:
        if ev.attacker in who and _reach_kind(ev) in _MELEE_KINDS:
            c.flat(amount, dtype=DamageType.FIRE, on=ev.target)

    return c.watch(Hit, rider, until=until, on=c.me, label=c.ref)


def _mobbed(c: Cast, who: int | None, needed: int) -> bool:
    """Has that creature at least `needed` of the caster's allies beside it?

    `c.allies()` never includes the caster, which is what the printed count
    of "its allies" means.
    """
    return who is not None and (
        sum(1 for a in c.allies() if distance_between(c.world, a, who) <= 1) >= needed
    )


def _neighbours(c: Cast) -> int:
    """How many creatures of either side are standing next to the caster."""
    return len(c.within(1, side="other"))


def _in_heavy_armour(c: Cast, who: int | None) -> bool:
    """Chain, scale or plate. `chargen.LIGHT` names the other three."""
    if who is None:
        return False
    gear = c.world.get(who, Gear)
    return gear is not None and gear.armour not in LIGHT


def _worsen(c: Cast, who: int, what: str | Defense, label: str) -> None:
    """Stack one more point of a penalty that the printed line caps at five.

    Read back off the live effects rather than counted in a closure: the row
    is used again by a second creature of the same kind, and the cap is on
    the item rather than on the attacker.
    """
    carried = [e for e in c.world.effects.of(who) if e.label == label]
    if len(carried) >= abs(_RUST_FLOOR):
        return
    hold = c.penalty(what, 1, until=When.ENCOUNTER, on=who)
    if hold is not None:
        hold.label = label


# ==========================================================================
# Skirmishers
# ==========================================================================


# --------------------------------------------------------------------------
# m2850
# --------------------------------------------------------------------------


@power(
    "m2850a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m2850a0(c: Cast) -> None:
    """The step is on the hit line with the damage -- one printed clause --
    so it is taken only when the blow lands."""
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m2850a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 6),
    requires=_not_bloodied,
    requires_text="the m2850 must not be bloodied",
)
def m2850a1(c: Cast) -> None:
    """The Requirement is m2850a3's last sentence.

    "The m2850 cannot use its m2850a1 or m2850a2 while it is bloodied" is
    printed on a third row and is a standing gate on this one. Written as a
    Requirement rather than as a `c.forbid` installed by that row, because
    the restriction holds whether or not the row that prints it is ever
    used -- and because a Requirement is re-asked every time the power is
    offered, so it lifts by itself if the creature is healed.
    """
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m2850a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    requires=_not_bloodied,
    requires_text="the m2850 must not be bloodied",
)
def m2850a2(c: Cast) -> None:
    """A shot and then a run at whoever it hit.

    The shot is the row that prints it rather than a copy. `_charge` is a
    walk into reach plus a swing marked as one, which is what puts `charge`
    on the attack events and in both modifier contexts -- the flag every
    charge rider in the tree reads.
    """
    victim = c.target
    if victim is None:
        return
    use(c.world, c.me, "m2850a1", targets=[victim], spend=False)
    _charge(c, victim)


@power(
    "m2850a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="the m2850 must be bloodied",
)
def m2850a3(c: Cast) -> None:
    """Two swings for one action, each two worse to hit with.

    The penalty is a hold put on and taken off rather than `c.strike(plus=)`,
    because the swings are the row that prints them and `use` has no way to
    pass a number through to somebody else's attack roll.
    """
    docked = c.penalty("attack", 2, until=When.EOT, on=c.me)
    try:
        for _ in range(2):
            use(c.world, c.me, "m2850a0", targets=[c.target], spend=False)
    finally:
        if docked is not None:
            c.world.effects.end(docked, "both swings are taken")


# --------------------------------------------------------------------------
# m2895
# --------------------------------------------------------------------------


@power(
    "m2895a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 4),
)
def m2895a0(c: Cast) -> None:
    """One of the two rows in the tree whose movement is printed *before* the
    swing as well as after, so the usual order -- swing first, because a
    shift picks its own destination -- is not the printed one and is not
    taken. The acid is a second expression on the same hit, so it is rolled
    in the body and the header keeps the printed line that rescales."""
    c.shift(2)
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.ACID)
    c.shift(2)


@power(
    "m2895a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m2895a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2895a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2895a2(c: Cast) -> None:
    """The line it repeats is the row that prints it rather than a copy, so
    the damage stays in one place. The step is printed after both swings."""
    for _ in range(2):
        use(c.world, c.me, "m2895a1", targets=[c.target], spend=False)
    c.shift(2)


@power(
    "m2895a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2895a3(c: Cast) -> None:
    """A pass on the wing: the swing is taken first, for the reason the levels
    below give on their rows of this shape -- the flight picks its own
    destination and one taken first can leave the target out of reach.
    Leaving provokes nothing from the creature it struck, which is the
    printed exemption. `c.basic` is what "one melee basic attack" names,
    whichever of its own rows that turns out to be."""
    c.no_provoke(from_=c.target)
    c.basic(on=c.target)
    c.move(_fly_speed(c))


_M2895_FLANKED = "an enemy moves to a space where it flanks the m2895"


def _moved_into_flank(world: World, me: int, ev: Moved) -> bool:
    """Whoever just stepped is an enemy, and is now flanking me.

    `query.flanked_by` reads the board rather than a stored flag -- flanking
    is computed, never held -- so asking it in the reaction window asks about
    the square the mover has arrived in.
    """
    from combat_engine.engine.query import enemies

    return ev.actor in enemies(world, me) and flanked_by(world, me, ev.actor)


@power(
    "m2895a4",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
    trigger=_M2895_FLANKED,
    on=Trigger(Moved, when=_moved_into_flank, text=_M2895_FLANKED),
)
def m2895a4(c: Cast) -> None:
    """Filed as a move action and printed as an immediate reaction; the
    trigger line is what says which it is, so it is declared as one."""
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m2895a5",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d10", 4, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m2895a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


_M2895_BLOODIED = "the m2895 is first bloodied"


@power(
    "m2895a6",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2895_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M2895_BLOODIED),
)
def m2895a6(c: Cast) -> None:
    """`Powers.restore` is what a recharge is, so the breath comes back up and
    goes off at once. "First bloodied" needs no guard of its own --
    `Bloodied` is emitted on the crossing and nowhere else."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m2895a5")
    use(c.world, c.me, "m2895a5")


@power(
    "m2895a7",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=7),
)
def m2895a7(c: Cast) -> None:
    """No damage at all -- the hold is the whole of the hit, and what follows
    it. The Aftereffect begins when the stun ends, and the end of an effect
    is the only moment that can be seen, so it is hung there."""
    if not c.strike():
        return
    victim = c.target
    held = c.stunned(until=When.EONT)
    if held is not None and victim is not None:
        held.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# --------------------------------------------------------------------------
# m297
# --------------------------------------------------------------------------


def _its_prey(c: Cast, who: int | None) -> bool:
    """Somebody m297a2 is allowed to aim at: poisoned, or on its ground."""
    return _poisoned(c, who) or _beside_a_ward(c, who)


def _guarded_enemy(c: Cast) -> bool:
    """Is any enemy standing in the area this creature is set to guard?"""
    return any(_beside_a_ward(c, foe) for foe in c.enemies())


def _poisoned_or_guarded(world: World, eid: int) -> bool:
    from combat_engine.engine import Cast as _Cast

    if _an_enemy_is_poisoned(world, eid):
        return True
    probe = _Cast(world=world, me=eid, ref="m297a2")
    return _guarded_enemy(probe)


@power(
    "m297a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m297a0(c: Cast) -> None:
    """Inside its own ground the charm is always up and never particular.

    Two waivers, and they live in two places. "Even if the target isn't
    taking ongoing poison damage" is a per-target restriction, so it is
    m297a2's own body that reads the aura as an alternative. "Even
    if the power hasn't recharged" is a usage gate, and `Powers.restore` is
    what a recharge *is* -- so it is handed back at the top of each of this
    creature's turns for as long as somebody is standing in what it guards.
    """
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or not _guarded_enemy(c):
            return
        known = c.world.get(me, Powers)
        if known is not None:
            known.restore("m297a2")

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label="m297a0")


@power(
    "m297a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m297a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m297a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=9),
    requires=_poisoned_or_guarded,
    requires_text="a creature must be poisoned or inside the m297's aura",
)
def m297a2(c: Cast) -> None:
    """Only into a creature already carrying poison -- or standing in the
    ground this thing is set over, which is m297a0's waiver.

    The printed restriction is per target and the header's `target` field
    cannot say so: `requires` carries the half about the board, and the
    aim is narrowed here. Narrowed rather than refused -- a target line
    names the pool a power may be aimed into, so a caller handing it a
    creature the line does not allow is picking from the wrong list, and
    the pick is made again through the decider instead.

    "Save ends both" is one effect with two conditions and exactly one
    saving throw; applied separately the victim would get two against a
    thing the card says is one.
    """
    victim = c.target
    if not _its_prey(c, victim):
        victim = c.choose(
            [
                foe
                for foe in c.enemies()
                if _its_prey(c, foe) and c.can_see(foe) and c.distance(foe) <= 10
            ],
            "m297a2: which creature",
        )
    if victim is None:
        return
    if c.strike(on=victim):
        c.condition(
            Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS, on=victim
        )


@power(
    "m297a3",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m297a3(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m2977
# --------------------------------------------------------------------------


@power(
    "m2977a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 4),
)
def m2977a0(c: Cast) -> None:
    """No range is printed, which the levels below settled means melee 1. The
    caster's own step comes after the shove, so it is not measured from a
    square it has already left."""
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()
        c.shift(1)


@power(
    "m2977a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    damage=Damage("", 5, kind=LIMITED),
)
def m2977a1(c: Cast) -> None:
    """No attack roll: the flat number is the whole of it, and it stays in the
    header as data so it rescales with everything else.

    The guard is not resistance -- resistance is held per damage type and
    this is every weapon blow whatever it is made of -- so the halving is
    taken off the damage roll in the interrupt window, which is the one
    moment the number exists and has not yet come off hit points. Armed
    once for the whole burst rather than once per creature caught in it.
    """
    c.hit()
    if not c.first:
        return
    me = c.me

    def half(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        p = get(ev.detail)
        if p is not None and Keyword.WEAPON in p.keywords:
            ev.amount //= 2

    c.watch(
        DamageRolled,
        half,
        until=When.EONT,
        window=Window.BEFORE,
        on=me,
        label="m2977a1 guard",
    )


@power(
    "m2977a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", kind=LIMITED),
)
def m2977a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m2977a3",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2977a3(c: Cast) -> None:
    _advantage_rider(c, "1d6")


# --------------------------------------------------------------------------
# m2991
# --------------------------------------------------------------------------


@power(
    "m2991a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m2991a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m2991a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 7),
)
def m2991a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2991a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m2991a2(c: Cast) -> None:
    """Close, step away, throw. The printed line names its own order and it
    is not the usual one, so it is kept: the second half is a ranged row and
    the step is what buys it the room.

    The thrown half picks its own target, because after two squares the one
    it just closed with is rarely the one it wants.
    """
    use(c.world, c.me, "m2991a0", targets=[c.target], spend=False)
    c.shift(2)
    use(c.world, c.me, "m2991a1", spend=False)


@power(
    "m2991a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m2991a3(c: Cast) -> None:
    """The ally moves before it swings, which is the printed order and also
    the useful one -- the step is what puts something in its reach. Who the
    ally swings at is chosen after the step for the same reason, and falls
    back to this row's own target when nothing is closer."""
    if not c.strike():
        return
    c.hit()
    mate = c.choose(c.allies(), "m2991a3: which ally swings")
    if mate is None:
        return
    c.shift(1, who=mate)
    near = [foe for foe in c.enemies() if distance_between(c.world, mate, foe) <= 1]
    c.grant_attack(mate, on=near[0] if near else c.target)


# --------------------------------------------------------------------------
# m3009
# --------------------------------------------------------------------------


@power(
    "m3009a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
)
def m3009a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3009a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3009a1(c: Cast) -> None:
    """The swing is taken before the step, for the reason the levels below
    give: the shift picks its own destination and one taken first can leave
    the target out of reach. The blade is the row that prints it."""
    use(c.world, c.me, "m3009a0", targets=[c.target], spend=False)
    c.shift(3)


@power(
    "m3009a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 3),
)
def m3009a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3009a4",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3009a4(c: Cast) -> None:
    """An extra die for having covered ground, measured as the printed line
    measures it: where it ended against where the move began, not how many
    squares it walked. Dice rather than a flat number, so it is rolled as
    the blow lands instead of riding along as a damage modifier -- and it is
    every attack it makes, which is what the printed line says."""
    me = c.me
    held: list[Effect] = []

    def rider(ev: Hit) -> None:
        if ev.attacker == me:
            c.damage("1d6", on=ev.target, detail="m3009a4")

    def far_enough(_kind: str, start: Square | None, end: Square, _steps: int) -> None:
        if start is None or distance(start, end) < 4:
            return
        _renew(
            c,
            held,
            lambda: c.watch(
                Hit, rider, until=When.SONT, on=me, label="m3009a4 reach"
            ),
        )

    _after_moving(c, far_enough)


# --------------------------------------------------------------------------
# m3062
# --------------------------------------------------------------------------


@power(
    "m3062a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m3062a1(c: Cast) -> None:
    """Armour eaten a point at a time, to a floor of five.

    "Heavy armour" is chain, scale or plate -- `chargen.LIGHT` names the
    other three and `Gear.armour` is the only place a creature says which it
    wears. A rusting piece is kept as a stack of one-point penalties under a
    shared label rather than as a counter, because the cap is on the item
    and a second creature of this kind eats the same armour.

    The step is an Effect line rather than part of the hit, so it is taken
    whether or not the claw lands -- and taken after it, because a shift
    picks its own destination.
    """
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and _in_heavy_armour(c, victim):
            _worsen(c, victim, AC, "m3062a1 rust")
    c.shift(1)


# --------------------------------------------------------------------------
# m3091
# --------------------------------------------------------------------------


@power(
    "m3091a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m3091a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m3091a1",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3091a1(c: Cast) -> None:
    """"Takes a move action" is a move: there is no second thing a move
    action buys that this creature has, so it is written as the walk."""
    c.move(c.speed_of())


@power(
    "m3091a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3091a2(c: Cast) -> None:
    """Harder to catch on the way past, once it is properly moving.

    Squares *covered*, not distance ended up at -- the printed line says
    "moves 2 squares or more" -- so the steps are counted rather than the
    two ends compared. A gate on the modifier rather than something put on
    and taken off, because the attack context carries `opportunity`.
    """
    me = c.me
    held: list[Effect] = []

    def moved(_kind: str, _start: Square | None, _end: Square, steps: int) -> None:
        if steps < 2:
            return
        _renew(
            c,
            held,
            lambda: c.bonus(
                AC,
                4,
                until=When.SONT,
                on=me,
                kind="untyped",
                when=lambda ctx: bool(ctx.get("opportunity")),
            ),
        )

    _after_moving(c, moved)


@power(
    "m3091a3",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3091a3(c: Cast) -> None:
    """An extra die on anything it lands at a run.

    Read off the `Hit`, which carries `charge` the way it carries
    `opportunity`. The second printed clause -- that the charge does not end
    its turn -- has nowhere to go: `actions.perform` empties the budget
    after the attack resolves and emits nothing afterwards, so there is no
    moment a row could hand the turn back in.
    """
    _charge_rider(c, "1d8")


# --------------------------------------------------------------------------
# m404
# --------------------------------------------------------------------------


@power(
    "m404a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 3),
)
def m404a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m404a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m404a1(c: Cast) -> None:
    """Six squares, three swings, and nobody hit twice.

    The six are spent two at a time between the swings rather than all at
    once, because "at any points during his move" is what makes three
    separate targets reachable and a single step to one destination is not.
    The row declares no targets: the route decides whom it catches, and the
    set of who has already been swung at is the printed "only once".
    """
    struck: set[int] = set()
    for _ in range(3):
        c.shift(2)
        victim = next(
            (
                foe
                for foe in c.enemies()
                if foe not in struck and distance_between(c.world, c.me, foe) <= 2
            ),
            None,
        )
        if victim is None:
            continue
        struck.add(victim)
        for hit in _struck(c, "m404a0", 1, victim):
            c.damage("1d6", dtype=DamageType.NECROTIC, on=hit, detail="m404a1")


@power(
    "m404a2",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m404a2(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


# --------------------------------------------------------------------------
# m408
# --------------------------------------------------------------------------


@power(
    "m408a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m408a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m408a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m408a1(c: Cast) -> None:
    """No damage: the four penalties are the whole of the hit. A creature that
    cannot hear it is skipped before the roll rather than after, which is
    what "are immune" means."""
    if c.is_(Condition.DEAFENED):
        return
    if not c.strike():
        return
    for d in (AC, FORT, REF, WILL):
        c.penalty(d, 2, until=When.EONT)


@power(
    "m408a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m408a2(c: Cast) -> None:
    """Arriving out of nowhere beside somebody is worth one blow.

    Which sort of move it was is read off `MoveStart`, which is the only
    event that says -- `MoveEnd` carries the arrival and nothing about how
    it was reached. Both halves are spent by the next attack against that
    one creature and both run out with the turn, so the advantage is granted
    `once` and the extra die is a watch that ends when it pays.
    """
    me = c.me

    def arrived(kind: str, _start: Square | None, _end: Square, _steps: int) -> None:
        if kind != "teleport":
            return
        for foe in c.enemies():
            if not c.adjacent(foe):
                continue
            c.grants_advantage(until=When.EOT, on=foe, once=True)

            def rider(ev: Hit, foe: int = foe) -> None:
                if ev.attacker == me and ev.target == foe:
                    c.damage("1d6", on=foe, detail="m408a2")

            c.watch(
                Hit, rider, until=When.EOT, on=me, once=True, label="m408a2 opening"
            )

    _after_moving(c, arrived)


# --------------------------------------------------------------------------
# m429
# --------------------------------------------------------------------------


@power(
    "m429a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m429a0(c: Cast) -> None:
    """The heavier line is a second expression rather than a rider on the
    first, so it is rolled in the body and the header keeps the printed one
    that rescales. Whether it had the drop is read off the roll that was
    just made: asking the board afterwards answers "no" for a creature that
    struck from concealment, and for a one-shot grant it has already been
    spent."""
    if not c.strike():
        return
    if c.result is not None and c.result.advantage:
        c.damage("3d6", 7)
    else:
        c.hit()


@power(
    "m429a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.POISON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m429a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


_M429_MARKED = "the m429 is marked by an enemy"


def _marked_me(world: World, me: int, ev: RelationSet) -> bool:
    """A mark landed on me. `about_me` will not say it -- `RelationSet` names
    its subject `target` -- and `targets_me` alone would also answer yes to
    being grabbed, cursed or hidden from."""
    return ev.kind_ is Relation.MARKED_BY and ev.target == me


@power(
    "m429a2",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M429_MARKED,
    on=Trigger(RelationSet, when=_marked_me, text=_M429_MARKED),
)
def m429a2(c: Cast) -> None:
    """Off the hook and three squares away.

    `_shed` drops the relation *and* the effect carrying it, since either
    one left behind keeps half the mark alive. Naming the triggering enemy
    is unnecessary: `Relations.set` displaces an older mark rather than
    stacking, so there is only ever one to shed.
    """
    _shed(c, Relation.MARKED_BY)
    c.shift(3)


# --------------------------------------------------------------------------
# m4794
# --------------------------------------------------------------------------


@power(
    "m4794a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4794a0(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m4794a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m4794a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4794a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4794a2(c: Cast) -> None:
    """Two swings with a step after each, in the printed order -- the step is
    printed after the attack here, which is also the order the levels below
    take for their own reasons."""
    for _ in range(2):
        use(c.world, c.me, "m4794a1", targets=[c.target], spend=False)
        c.shift(2)


@power(
    "m4794a3",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_climbing,
    requires_text="the m4794 must be climbing",
)
def m4794a3(c: Cast) -> None:
    """Off the wall and across the room.

    The Requirement is about what the creature is *doing*, which is what
    `Movement.using` holds and what `_climbing` reads; having a climb speed
    is a different question and is not this one. The flight is granted for
    the turn rather than assumed, because `movement.mode_of` picks the best
    mode a creature has and this one has no fly speed of its own.
    """
    c.mode("fly", 5, until=When.EOT)
    c.move(5)


# --------------------------------------------------------------------------
# m4916
# --------------------------------------------------------------------------


@power(
    "m4916a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m4916a0(c: Cast) -> None:
    """Fire on the blade once it has built up some speed.

    Measured from where the *turn* began rather than from where the move
    did, which is what the printed line says and which a creature splitting
    its movement across two actions would otherwise dodge. The square is
    taken at the top of each of its own turns -- and once when the trait
    arms, because a trait is armed before initiative is rolled and a
    creature dragged across the board before its own first turn would
    otherwise be measured against nothing at all.
    """
    me = c.me
    here = c.world.get(me, Position)
    began: list[Square | None] = [here.square if here is not None else None]
    held: list[Effect] = []

    def dawn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        at = c.world.get(me, Position)
        began[0] = at.square if at is not None else None

    def moved(_kind: str, _start: Square | None, end: Square, _steps: int) -> None:
        if began[0] is None or distance(began[0], end) < 3:
            return
        _renew(c, held, lambda: _fiery_blows(c, [me], 5, When.EONT))

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label="m4916a0 dawn")
    _after_moving(c, moved)


@power(
    "m4916a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m4916a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4916a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8"),
)
def m4916a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m4916a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m4916a3(c: Cast) -> None:
    """The same fire, handed round.

    Who is in range is settled when the power goes off rather than asked
    again -- a grant is made to the allies standing there, and one that
    walks away afterwards keeps it, which is how a printed grant reads. The
    caster is not one of its own allies and is left out.
    """
    pack = [a for a in c.within(5, side="ally") if a != c.me]
    if pack:
        _fiery_blows(c, pack, 5, When.EONT)


# --------------------------------------------------------------------------
# m664
# --------------------------------------------------------------------------


@power(
    "m664a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m664a0(c: Cast) -> None:
    """Five more on anybody the pack has closed around.

    A gated damage modifier rather than a watch on the hit: the damage
    context carries `target`, so the gate can count the neighbours at the
    moment the blow lands, and the printed line adds a flat number rather
    than dice.
    """
    c.bonus(
        "damage",
        5,
        until=When.ENCOUNTER,
        on=c.me,
        kind="untyped",
        when=lambda ctx: _mobbed(c, ctx.get("target"), 2),
    )


@power(
    "m664a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m664a1(c: Cast) -> None:
    """The heavier line is a second expression rather than a rider, so it is
    rolled in the body and the header keeps the printed one that rescales."""
    hurt = c.bloodied(on=c.me)
    if not c.strike():
        return
    if hurt:
        c.damage("2d6", 9)
    else:
        c.hit()


@power(
    "m664a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m664a2(c: Cast) -> None:
    """The charge *is* this row, rather than a rider on an ordinary one.

    A charge made by `actions.perform` swings once and there is no moment
    afterwards at which a second swing could be added -- the budget is
    emptied and nothing is emitted. So the row that prints the doubling is
    written as the charge: the run-in, then two swings both marked as one,
    which is what buys the printed +1 and what every charge rider reads.
    """
    victim = c.target
    if victim is None or not _run_at(c, victim):
        return
    for _ in range(2):
        use(
            c.world, c.me, "m664a1", targets=[victim], spend=False, charge=True
        )


@power(
    "m664a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m664a3(c: Cast) -> None:
    """The swing is taken first, for the reason the levels below give: the
    walk picks its own destination and one taken first can leave the target
    out of reach. Leaving provokes nothing from the creature it struck,
    which is the printed exemption."""
    c.no_provoke(from_=c.target)
    use(c.world, c.me, "m664a1", targets=[c.target], spend=False)
    c.move(4)


# ==========================================================================
# Lurkers
# ==========================================================================


# --------------------------------------------------------------------------
# m102
# --------------------------------------------------------------------------


@power(
    "m102a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m102a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m102a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 5),
    requires=_has_advantage,
    requires_text="the target must be granting combat advantage to the m102",
)
def m102a1(c: Cast) -> None:
    """A hold that has to be paid for every turn to keep.

    The printed restriction is per target and the header's `target` field
    cannot say so: `requires` carries the half about the board, and the aim
    is narrowed here rather than refused, for the reason m297a2 gives.

    The grab is applied on a `When.SUSTAIN` clock rather than through
    `c.grab`, whose hold runs to the end of the fight: "Sustain Standard"
    means that *not* sustaining is what lets go, and the sustain cost is
    what puts the option in front of whoever is playing it. `c.on_sustain`
    carries the other half of the printed line -- the damage -- which the
    clock refreshing on its own would have dropped.
    """
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        victim = c.choose(
            [
                foe
                for foe in c.enemies()
                if c.adjacent(foe) and has_combat_advantage(c.world, c.me, foe)
            ],
            "m102a1: which creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    held = c.world.effects.apply(
        victim,
        c.me,
        When.SUSTAIN,
        label="m102a1 grab",
        sustain_cost=STANDARD,
        relations=[(Relation.GRABBED_BY, c.me, victim)],
    )
    c.on_sustain(held, lambda: c.damage("2d8", 5, on=victim, detail="m102a1"))


@power(
    "m102a2",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m102a2(c: Cast) -> None:
    """One extra die, spent on the first blow it lands with the drop.

    `once` on `c.watch` means "fire once", not "live for one event": it is
    spent only when the body actually did something, so a hit on a target
    that was not caught out does not burn it. Whether the attack had combat
    advantage is read off the roll rather than asked of the board, which
    answers no for a blow struck from concealment.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.attacker == me and result is not None and result.advantage:
            c.damage("1d6", on=ev.target, detail="m102a2")

    c.watch(Hit, rider, until=When.EONT, on=me, once=True, label="m102a2")


_M102_SWUNG_AT = "an enemy attacks the m102's AC or Reflex while it is grabbing"


def _at_my_guard(world: World, me: int, ev: AttackDeclared) -> bool:
    return ev.vs in (Defense.AC, Defense.REF)


@power(
    "m102a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    requires=_grabbing,
    requires_text="the m102 must be grabbing a creature",
    trigger=_M102_SWUNG_AT,
    on=Trigger(
        AttackDeclared,
        when=both(targets_me, either(by_melee, by_ranged), _at_my_guard),
        text=_M102_SWUNG_AT,
    ),
)
def m102a3(c: Cast) -> None:
    """The prisoner takes it instead.

    `c.redirect` only works on the declaration, before the die is down --
    after that there is a result and moving the blow would mean rolling it
    again -- which is exactly why this is printed as an interrupt. The
    creature being held cannot be used as a shield against itself, so an
    attack made by the prisoner is left alone.
    """
    ev = c.trigger
    attacker = getattr(ev, "attacker", None)
    shield = next(
        (
            who
            for who in c.world.relations.targets(Relation.GRABBED_BY, c.me)
            if who != attacker
        ),
        None,
    )
    if shield is not None:
        c.redirect(to=shield)


# --------------------------------------------------------------------------
# m2929
# --------------------------------------------------------------------------


@power(
    "m2929a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m2929a0(c: Cast) -> None:
    """A Perception check against a thing that looks like scenery, and nothing
    else -- declared inert rather than given an invented mechanic."""
    c.note("m2929a0: with its shell closed it passes for a boulder; DC 28 to tell")


@power(
    "m2929a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m2929a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2929a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m2929a2(c: Cast) -> None:
    """Both halves are this row's own attack line, so the second is another
    `c.strike` rather than a second row -- the Effect line says "one more
    attack", not "uses <something>"."""
    landed = 0
    for _ in range(2):
        if c.strike():
            c.hit()
            landed += 1
    if landed == 2:
        c.grab()


@power(
    "m2929a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_CREATURE,
    attack=Attack(vs=FORT, printed=9),
)
def m2929a3(c: Cast) -> None:
    """Everybody down, and then it shuts.

    The shell is a `c.form`: some conditions, and a printed action cost to
    step back out of it, which is exactly what `revert` is for.
    `Condition.IMMOBILIZED` is the whole of "its speed is 0" -- there is no
    other consequence of a speed of nought -- and the four defence bonuses
    hang on the form so that opening drops them together.

    The bonus is gated rather than granted, because the printed line excepts
    whatever it is holding and who that is changes while the shell is shut;
    the defence is read through the attack context, which carries
    `attacker`.

    Two sentences are left unsaid. Line of effect is computed from the grid
    and nothing can make one creature an exception to it, so "no line of
    effect to any creature other than the one it has grabbed" is not
    written; and the prisoner is already in the shell's own square, so
    "appears in a space adjacent if it escapes" needs nothing.
    """
    if c.strike():
        c.prone()
    if not c.first:
        return
    me = c.me
    shell = c.form(
        conditions=(Condition.IMMOBILIZED,),
        until=When.ENCOUNTER,
        revert=MINOR,
        label="m2929a3 shell",
    )

    def outside(ctx: dict[str, Any]) -> bool:
        held = c.world.relations.targets(Relation.GRABBED_BY, me)
        return ctx.get("attacker") not in held

    for d in (AC, FORT, REF, WILL):
        guard = c.bonus(
            d, 5, until=When.ENCOUNTER, on=me, kind="untyped", when=outside
        )
        if guard is not None:
            shell.on_end.append(
                lambda g=guard: c.world.effects.end(g, "the shell opened")
            )
    for prisoner in c.world.relations.targets(Relation.GRABBED_BY, me):
        c.shift(who=prisoner, to=c.here, share=True)


# --------------------------------------------------------------------------
# m405
# --------------------------------------------------------------------------


@power(
    "m405a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 3),
)
def m405a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m405a1",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m405a1(c: Cast) -> None:
    """A rider on every blow it lands out of the dark, so a trait rather than
    an action. Asked of the relation at the moment of the `Hit`, which is
    readable because `resolve.attack` clears `HIDDEN_FROM` *after* the hit
    is announced -- asking the board any later answers no for every creature
    that struck unseen."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if c.world.relations.holds(Relation.HIDDEN_FROM, me, ev.target):
            c.blinded(until=When.EONT, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m405a1")


@power(
    "m405a2",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m405a2(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


@power(
    "m405a3",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    requires=_not_bloodied,
    requires_text="the m405 must not be bloodied",
)
def m405a3(c: Cast) -> None:
    """Gone, and then gone somewhere else. The veil is raised first because
    the whole point of it is the walk it covers; walking does not give a
    creature away here -- only attacking does, in `resolve.attack` -- so the
    clock is the only thing that ends it."""
    c.invisible(until=When.EOT)
    c.move(c.speed_of())


# --------------------------------------------------------------------------
# m5008
# --------------------------------------------------------------------------


@power(
    "m5008a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 4),
)
def m5008a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5008a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 2),
)
def m5008a1(c: Cast) -> None:
    """A lighter blow bought with a guard and a reloaded trick.
    `Powers.restore` is what recharging is, and it works on an encounter row
    as readily as on a recharge one -- the count of uses is the same field."""
    if not c.strike():
        return
    c.hit()
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 5, until=When.EONT, on=c.me, kind="untyped")
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m5008a4")


@power(
    "m5008a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d6", 2, dtype=DamageType.PSYCHIC),
)
def m5008a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5008a3",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5008a3(c: Cast) -> None:
    """A jump is a move in the engine -- there is no separate op -- so "this
    movement does not provoke opportunity attacks" is the whole of what the
    printed line adds."""
    _guarded_move(c, c.speed_of())


_M5008_LANDED = "the m5008 hits with m5008a0 or m5008a2"


def _with_either_blade(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power in ("m5008a0", "m5008a2")


@power(
    "m5008a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
    trigger=_M5008_LANDED,
    on=Trigger(Hit, when=_with_either_blade, text=_M5008_LANDED),
)
def m5008a4(c: Cast) -> None:
    """The extra dice go to whoever the triggering attack hit, and are dealt
    as their own packet rather than folded into the blow -- which is how
    every other rider in the tree shows in the log."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("2d6", dtype=DamageType.PSYCHIC, on=victim)


# --------------------------------------------------------------------------
# m674
# --------------------------------------------------------------------------


def _m674_secondary(c: Cast) -> None:
    """The follow-up both of its weapons print.

    A second roll against a different defence cannot live in the header, so
    its printed +8 is trimmed by hand the way `Attack.bonus_for` trims the
    header's. "Save ends both" is one effect carrying the burn, which is one
    saving throw rather than two.
    """
    if c.attack(c.world.scaling.trim(8, c.level), FORT):
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(3, DamageType.POISON)
        )


@power(
    "m674a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m674a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        _m674_secondary(c)


@power(
    "m674a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m674a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        _m674_secondary(c)


@power(
    "m674a3",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m674a3(c: Cast) -> None:
    """Harder to pin down the more of a crowd there is.

    Two gates rather than one growing number, because the printed line is a
    step function and a modifier has one value. Asked at the moment a
    defence is read, since who is standing next to it changes every time
    anything moves; `c.within(1, side="other")` counts both sides, which is
    what "one creature adjacent to it" says.
    """
    me = c.me
    for d in (AC, REF):
        c.bonus(
            d, 2, until=When.ENCOUNTER, on=me, kind="untyped",
            when=lambda _ctx: _neighbours(c) == 1,
        )
        c.bonus(
            d, 4, until=When.ENCOUNTER, on=me, kind="untyped",
            when=lambda _ctx: _neighbours(c) >= 2,
        )


@power(
    "m674a4",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m674a4(c: Cast) -> None:
    """A gate rather than something put on and taken off, because the attack
    context carries `opportunity`. Racial, so it does not displace the power
    bonus m674a3 hands out against the same defence."""
    c.bonus(
        AC,
        2,
        until=When.ENCOUNTER,
        on=c.me,
        kind="racial",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


_M674_STRUCK = "an attack would hit the m674"


@power(
    "m674a5",
    level=6,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M674_STRUCK,
    on=Trigger(AttackRolled, when=would_hit_me, text=_M674_STRUCK),
)
def m674a5(c: Cast) -> None:
    """The new number stands whatever it is, so `keep="new"` rather than
    "worst".

    Answered on `AttackRolled` rather than on `Hit`: the die is down and the
    total is known, but `resolve.attack` reads the defence and recomputes
    the hit once this window closes, which is the only point at which a
    reroll can still turn the blow aside. `would_hit_me` is the printed
    "when hit" asked one beat earlier.
    """
    c.reroll_attack(keep="new")
