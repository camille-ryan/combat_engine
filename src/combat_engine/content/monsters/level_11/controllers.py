"""Monster abilities, level 11: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=WILL,
printed=14)` and `Damage("3d8", 3)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the ten levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block printing no range at all means melee 1; a **blast** reading "creatures
in the blast" is `EACH_CREATURE` and a **close burst** of the same wording is
`EACH_OTHER`; and a helper written for an earlier level is imported rather
than copied.

Seven readings this file had to settle.

**"+2 to the attack roll" bought after the die has landed.** `resolve.attack`
re-reads the *defence* once the `AttackRolled` window closes and nothing
else: the total is fixed by then, so a modifier applied in answer to a miss
adds to nothing. The one thing that still bites there is `c.autohit`, and it
is the same outcome as the printed +2 exactly when the roll fell within two
of the defence -- which is the only case where the +2 changes anything. So
m4908a0 is gated on those two numbers and then forces the hit.

**"Choose its target at random"** is `AttackDeclared.vs`'s neighbour: the
event carries a mutable `target` that `resolve.roll` reads back, which is
what `c.redirect` writes to for an interrupt. A save-ends hold can do the
same from a listener, and the pool is every creature inside the swinging
row's own printed reach.

**A zone that penalises whoever stands in it** is held per occupant and
diffed by `ZoneEntered`/`ZoneExited` -- the arrangement m137a0 settled on six
levels down. A zone's own fields can make squares rough or blind, and carry
no modifiers.

**"Up to 4 squares within range"** names no creature and no burst, so the
squares are chosen one at a time. The pool is sorted with the ones beside an
enemy first, which is what makes the engine's own pick -- the first option --
a sensible one on a board with nobody playing the monster.

**A cross-referenced id is read as the row every sentence plainly means.**
m442a3 spells its own slam as another stat block's; the same reading m4990a1
settled on a level down. The line it points at prints the same reach and the
same dice, one point of attack apart.

**"In direct contact with the ground"** is the flight question asked the
other way round, and `_airborne` is the only thing the engine has for it.

**Second wind cannot be forbidden.** `actions.legal` gates it on
`Powers.times("second-wind")` and never consults `Powers.forbidden`, so
`c.forbid` is silently useless there; spending the count is what the printed
line comes to. See the report.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_05.brutes import _is_bloodied
from combat_engine.content.monsters.level_05.skirmishers import _airborne, _reach_kind
from combat_engine.content.monsters.level_07.brutes import _crit_line
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.lurkers import _sweep
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_09.brutes import _regenerates, _volley
from combat_engine.content.monsters.level_10.brutes import _same_stock
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
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Defense,
    Effect,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    Powers,
    Ranged,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    ZoneEntered,
    power,
    spread,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import EffectExpired, ZoneExited
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    cover_between,
    creatures,
    distance_between,
    squares,
)
from combat_engine.engine.triggers import Trigger
from combat_engine.engine.types import Cover

#: The four defences, for a printed "a -2 penalty to all defenses".
EVERY_DEFENCE: tuple[Defense, ...] = (AC, FORT, REF, WILL)


def _softened(c: Cast, *, attack: int = 0, defences: int = 0) -> list[Mod]:
    """The modifier half of a printed "and takes a -N penalty to ..." line.

    Returned rather than applied, because every row printing one prints it
    under the same saving throw as something else -- and two effects are two
    saving throws against one printed sentence.
    """
    mods = []
    if attack:
        mods.append(Mod(what="attack", value=-attack, kind="untyped", label=c.ref))
    for defended in EVERY_DEFENCE if defences else ():
        mods.append(Mod(what=defended.value, value=-defences, kind="untyped", label=c.ref))
    return mods


def _held_and_softened(
    c: Cast,
    victim: int,
    *,
    conditions: tuple[Condition, ...] = (),
    ongoing: tuple[int, DamageType] | None = None,
    attack: int = 0,
    defences: int = 0,
) -> Effect:
    """"Save ends both" is one effect, whatever the two halves are."""
    return c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=conditions,
        ongoing=ongoing,
        mods=[(victim, m) for m in _softened(c, attack=attack, defences=defences)],
    )


def _ends_its_turn_in(c: Cast, zone: int, fn: Callable[[int], None]) -> Effect:
    """"Any creature that ends its turn in the zone ..." -- the commonest

    zone clause `c.burns` does not cover: that one bites on entering and on
    starting a turn, which are the other two moments.
    """
    me = c.me

    def measured(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(zone):
            fn(ev.actor)

    return c.watch(TurnEnd, measured, until=When.ENCOUNTER, on=me, label=f"{c.ref} lingers")


def _rough_squares(c: Cast, count: int, within: int, *, kind: str) -> int:
    """`count` squares within range, chosen one at a time, made hard going.

    The printed line names no creature and no burst, so there is no `Target`
    that picks them. The pool is sorted with the squares beside an enemy
    first: `World.decide` takes the head of the list when nobody is playing
    the monster, and that is the difference between a row that hampers
    somebody and one that roughs up empty floor.
    """
    beside_a_foe = {
        sq
        for foe in c.enemies()
        if c.distance(foe) <= within
        for sq in spread(squares(c.world, foe), 1)
    }
    pool = sorted(
        (sq for sq in spread(squares(c.world, c.me), within) if c.world.grid.passable(sq)),
        key=lambda sq: (sq not in beside_a_foe, sq),
    )
    picked: list[Any] = []
    for _ in range(count):
        left = [sq for sq in pool if sq not in picked]
        chosen = c.choose(left, f"{c.ref}: which square turns to broken ground")
        if chosen is None:
            break
        picked.append(chosen)
    if not picked:
        return 0
    return c.zone(picked, label=c.ref, until=When.ENCOUNTER, difficult=kind)


# ==========================================================================
# m216
# ==========================================================================


@power(
    "m216a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 4),
)
def m216a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m216a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d8", 6),
)
def m216a1(c: Cast) -> None:
    """It walks and then swings, so the victim is whoever it ends up beside.

    Declared with no target: the dispatcher aims a row before the body runs,
    and there is nobody adjacent to aim at until the four squares have been
    walked.
    """
    c.move(4)
    prey = _adjacent_foe(c, c.ref)
    if prey is not None and c.strike(on=prey):
        c.hit(on=prey)
        c.push(1, on=prey)
        c.prone(on=prey)


@power(
    "m216a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
)
def m216a2(c: Cast) -> None:
    """A fist of earth, and only one of them at a time.

    No damage line at all: the hold is the whole of the hit. "In direct
    contact with the ground" is the flight question asked the other way
    round, and a creature in the air is the only way the engine can say a
    creature is not standing on anything.

    The previous fist is let go as the new one closes rather than when the
    row is chosen, so a miss leaves the first victim held -- which is what
    "only against one creature at a time" comes to.
    """
    victim = c.target
    if victim is None or _airborne(c.world, victim):
        return
    if not c.strike(on=victim):
        return
    _sweep(c, c.ref, "the other fist crumbled")
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)


@power(
    "m216a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m216a3(c: Cast) -> None:
    """Four squares of broken ground, which need not touch each other.

    "The affected terrain must consist of earth or stone" is a property of
    the map the engine does not hold, so it is noted; every passable square
    is offered.
    """
    _rough_squares(c, 4, 10, kind="m216a3")
    c.note("m216a3: the squares have to be earth or stone")


# ==========================================================================
# m250
# ==========================================================================


@power(
    "m250a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d8", 6),
)
def m250a0(c: Cast) -> None:
    """"Save ends both" is one effect carrying the slow and the penalty."""
    if c.strike():
        c.hit()
        if c.target is not None:
            _held_and_softened(
                c, c.target, conditions=(Condition.SLOWED,), attack=2
            )


@power(
    "m250a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 3, dtype=DamageType.LIGHTNING),
)
def m250a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


def _swings_wild(c: Cast, victim: int, hold: Effect) -> None:
    """Its melee attacks land wherever they land.

    `AttackDeclared.target` is mutable and `resolve.roll` reads it back --
    that is what `c.redirect` writes to for an interrupt, and a save-ends
    hold can write to it from a listener for the same reason. The pool is
    everything inside the swinging row's own printed reach, which is what
    "all potential targets in range" means; a burst has no single target to
    move, so only a melee line is redirected.
    """
    me = c.me

    def scatter(ev: AttackDeclared) -> None:
        if ev.attacker != victim or hold.ended or _reach_kind(ev) != "melee":
            return
        p = get(ev.power)
        span = p.reach_of(getattr(ev, "branch", 0)).size if p else 1
        pool = sorted(
            w
            for w in creatures(c.world)
            if w != victim and alive(c.world, w) and distance_between(c.world, victim, w) <= span
        )
        if pool:
            ev.target = c.world.rng.choice(pool)

    hold.subs.append(c.world.bus.on(AttackDeclared, scatter, window=Window.BEFORE, owner=me))


@power(
    "m250a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m250a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.effect(f"{c.ref} confusion", until=When.SAVE_ENDS, on=victim)
    if hold is not None:
        _swings_wild(c, victim, hold)


@power(
    "m250a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("3d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m250a3(c: Cast) -> None:
    """The Effect line is printed beside the attack rather than under a hit,
    so the zone is laid on the first pass whether or not anybody was in it."""
    if c.first:
        zone = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)
        _ends_its_turn_in(c, zone, lambda who: c.dazed(until=When.EOTNT, on=who))
    if c.target is None:
        return
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m3080
# ==========================================================================

#: The label a web zone gives its squares, which is what the m3080's own
#: trait waives -- and the one m3081a2 a level down already waives.
_WEB = "web"


@power(
    "m3080a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m3080a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means.

    "Ongoing 10 necrotic and poison" is one burn of two types and an effect
    holds one, so the first printed type is kept -- the approximation every
    level below settled on for the same shape.

    Taking a second wind away is not `c.forbid`: `actions.legal` gates the
    option on `Powers.times("second-wind")` and never looks at
    `Powers.forbidden`, so forbidding it is silently nothing. Spending the
    count is the same sentence and it is the door the option actually reads.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.condition(
        Condition.DAZED, until=When.SAVE_ENDS, on=victim, ongoing=(10, DamageType.NECROTIC)
    )
    known = c.world.get(victim, Powers)
    if known is not None:
        known.note_use("second-wind", c.world.round)


@power(
    "m3080a1",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
)
def m3080a1(c: Cast) -> None:
    """No damage line: the hold and the softening are the whole of the hit.

    Vulnerability is held by the creature that has it rather than by the
    creature that inflicted it, so it cannot ride the hold's own effect; it
    is tied to it by the hold's ending instead, which is what makes the one
    printed saving throw end both.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    hold = c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)
    exposed = c.vulnerable(5, DamageType.NECROTIC, until=When.SAVE_ENDS, on=victim)
    if hold is not None and exposed is not None:
        hold.on_end.append(lambda: c.world.effects.end(exposed, "the webbing came away"))


@power(
    "m3080a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=REF, printed=15),
)
def m3080a2(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit. The squares carry
    the web label, which is what this creature's own trait waives."""
    if c.first:
        c.zone(c.area(), label=c.ref, until=When.ENCOUNTER, difficult=_WEB)
    if c.target is None:
        return
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3080a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3080a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Said twice, once per
    word, which is how `c.ignores_difficult` takes a printed list."""
    c.ignores_difficult(_WEB, until=When.ENCOUNTER)
    c.ignores_difficult("swarm", until=When.ENCOUNTER)


# ==========================================================================
# m420
# ==========================================================================


@power(
    "m420a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 3),
)
def m420a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The printed "crit 2d8 + 11" *replaces* the damage and is a roll,
    so it is dealt flat, past the engine's own rule that a critical maxes the
    declared dice.

    The secondary is a second attack line against a different defence, so it
    cannot live in the header; its printed +12 is trimmed by hand the way
    `Attack.bonus_for` trims the header's.
    """
    if not c.strike():
        return
    _crit_line(c, "2d8", 11)
    victim = c.target
    if victim is None:
        return
    if c.attack(c.world.scaling.trim(12, c.level), FORT, on=victim):
        c.ongoing(5, DamageType.POISON, on=victim)


@power(
    "m420a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m420a1(c: Cast) -> None:
    """"Grants combat advantage to all of its enemies" is the whole of this
    creature's side, which is what `to="allies"` names."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "m420a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(5, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=14),
)
def m420a2(c: Cast) -> None:
    """No damage line: the hold is the whole of the hit."""
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


# ==========================================================================
# m442
# ==========================================================================


@power(
    "m442a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
)
def m442a0(c: Cast) -> None:
    """An aura 2 for the board to draw, and the toll taken at the end of a
    turn -- which is neither of the two moments `c.burns` covers."""
    ring = c.aura(2, until=When.ENCOUNTER)
    me = c.me

    def snap(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(5, dtype=DamageType.LIGHTNING, on=ev.actor)

    c.watch(TurnEnd, snap, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m442a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m442a1(c: Cast) -> None:
    """Regeneration, written out: the engine holds no such thing, and "has at
    least 1 hit point" is `hp > 0` rather than `alive`."""
    _regenerates(c, 10)


@power(
    "m442a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 6),
)
def m442a2(c: Cast) -> None:
    """The lightning is a second packet rather than part of the declared
    line: the header's damage is untyped and only the rider is lightning, and
    how much of it there is depends on the m442's own health."""
    if not c.strike():
        return
    c.hit()
    c.damage("3d8" if c.bloodied(c.me) else "1d8", dtype=DamageType.LIGHTNING)


@power(
    "m442a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.LIGHTNING],
)
def m442a3(c: Cast) -> None:
    """Two swings of the row that prints them.

    The card spells the swing as another stat block's id. That row prints the
    same reach and the same dice one point of attack apart, and the creature
    every sentence here plainly means is this one -- so it is this creature's
    own slam that is used twice, the reading m4990a1 settled on a level down.

    The printed Effect does not say whether the two land on one creature or
    two, so the header takes up to two and a single target is hit twice.
    """
    if c.target is not None:
        _volley(c, "m442a2", c.target)


@power(
    "m442a4",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d8", 13, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m442a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M442_SHOCKED = "a lightning effect deals damage to the m442"


def _shocked(world: World, me: int, ev: DamageApplied) -> bool:
    """"A lightning effect deals damage to the m442."

    `about_me` reads `ev.actor` and `DamageApplied` names its subject
    `target`, so it would be false here forever. The damage event is the only
    place the *type* of a packet can be read.
    """
    return ev.target == me and ev.amount > 0 and ev.dtype is DamageType.LIGHTNING


@power(
    "m442a5",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M442_SHOCKED,
    on=Trigger(DamageApplied, when=_shocked, text=_M442_SHOCKED),
)
def m442a5(c: Cast) -> None:
    """Filed as a free action and printed as an immediate reaction; the
    engine's `FREE` is the one the card's action line names."""
    c.heal(10, on=c.me)


# ==========================================================================
# m4869
# ==========================================================================


@power(
    "m4869a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4869a0(c: Cast) -> None:
    """Underwater is a property of the fight, which `c.terrain` asks, and the
    target's type line says whether it belongs there. Both are asked as the
    roll is made rather than now, because a fight can move into the water.
    Breathing is not a rule the engine holds and is noted."""
    me = c.me

    def out_of_its_element(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return c.terrain("aquatic") and who is not None and not c.is_kind("aquatic", on=who)

    c.bonus(
        "attack", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=out_of_its_element
    )
    c.note("m4869a0: it breathes underwater")


@power(
    "m4869a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4869a1(c: Cast) -> None:
    """Cold water cracks it, and the crack closes over the next blow.

    "The next attack that hits it" is a clock the duration enum cannot say,
    so the hold carries the printed one -- the end of its next turn -- and is
    torn down by the first damage to land on it afterwards. The packet that
    armed it is let past by sequence number: the listener is attached inside
    that event's own window and would otherwise spend the vulnerability on
    the cold that caused it.
    """
    me = c.me

    def chilled(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0 or ev.dtype is not DamageType.COLD:
            return
        exposed = c.vulnerable(5, until=When.EONT, on=me)
        if exposed is None:
            return

        def spent(later: DamageApplied) -> None:
            if later.target == me and later.seq > ev.seq and not exposed.ended:
                c.world.effects.end(exposed, "the next blow has landed")

        exposed.subs.append(c.world.bus.on(DamageApplied, spent, owner=me))

    c.watch(DamageApplied, chilled, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4869a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6"),
)
def m4869a2(c: Cast) -> None:
    """The burn carries this row's ref as its label rather than `c.ongoing`'s
    "ongoing 10", because the minor action below has to find the creatures
    this row in particular is still gripping."""
    if not c.strike():
        return
    c.hit()
    if c.target is not None:
        c.world.effects.apply(
            c.target, c.me, When.SAVE_ENDS, label=c.ref, ongoing=(10, DamageType.UNTYPED)
        )


@power(
    "m4869a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d6", 7, kind=LIMITED),
)
def m4869a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m4869a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4869a4(c: Cast) -> None:
    """Everyone still caught in the current, dragged two squares."""
    for caught in c.suffering("m4869a2"):
        c.slide(2, on=caught)


# ==========================================================================
# m4908
# ==========================================================================


@power(
    "m4908a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4908a0(c: Cast) -> None:
    """Pay in blood and the blow lands after all.

    The printed +2 cannot be applied as a bonus. `resolve.attack` re-reads
    the **defence** once the `AttackRolled` window closes and reads the total
    off the result untouched, so a modifier raised in answer to a miss adds
    to nothing -- which is the same trap `m4774a3`'s docstring describes from
    the other side. `c.autohit` is the one thing that still bites there, and
    it is the same outcome as the +2 exactly when the roll fell short by two
    or less, which is the only case where the +2 changes anything.

    A natural 1 is let past: it misses whatever the total says, so the bonus
    could never have bought it.
    """
    me = c.me
    ring = c.aura(5, until=When.ENCOUNTER)

    def press(ev: AttackRolled) -> None:
        ally = ev.attacker
        if ally == me or ally not in c.allies() or ev.natural == 1:
            return
        if ally not in c.world.zones.occupants(ring) or _reach_kind(ev) != "melee":
            return
        result = getattr(ev, "result", None)
        if result is None or result.hit or ev.total + 2 < ev.defence:
            return
        if not c.may("take 5 damage to land the blow", who=ally):
            return
        c.flat(5, on=ally)
        c.autohit(ev)

    c.watch(AttackRolled, press, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4908a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 5),
)
def m4908a1(c: Cast) -> None:
    """The victim turns on whoever it is standing next to.

    The m4908 picks, which is what "a creature of the m4908's choice" says,
    and the pool is whatever the victim can actually reach -- a granted basic
    attack against somebody across the room is not a swing at all.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    beside = sorted(
        w
        for w in creatures(c.world)
        if w != victim and alive(c.world, w) and distance_between(c.world, victim, w) <= 1
    )
    prey = c.choose(beside, f"{c.ref}: who the charmed creature swings at")
    if prey is not None:
        c.grant_attack(victim, on=prey)


@power(
    "m4908a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=14),
)
def m4908a2(c: Cast) -> None:
    """No damage line: the domination is the whole of the hit."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


_M4908_THRALL = "m4908a3 thrall"


@power(
    "m4908a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
)
def m4908a3(c: Cast) -> None:
    """A hold that costs its bearer the first blow it lands each turn.

    "Recharge when no creature is affected by this power" is a sentence on
    top of the die the database files, and it is the hold's own ending that
    announces it -- `EffectExpired` carries the effect's printed form, which
    is the only place its label can be read after it is gone.

    Both printed ways out are hung on the hold: the fight ending, and this
    creature or one of its own aiming at the target. The second is read off
    `AttackDeclared` rather than a hit, because the printed word is
    "attacks".
    """
    me = c.me
    _recharge_on(
        c,
        EffectExpired,
        lambda ev: _M4908_THRALL in ev.what and not c.suffering(_M4908_THRALL, by=me),
    )
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    hold = c.effect(_M4908_THRALL, until=When.ENCOUNTER, on=victim)
    if hold is None:
        return
    struck: dict[int, int] = {}

    def toll(ev: Hit) -> None:
        if ev.attacker != victim or hold.ended or c.world.turn != victim:
            return
        if struck.get(victim) == c.world.round:
            return
        struck[victim] = c.world.round
        c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    def freed(ev: AttackDeclared) -> None:
        if hold.ended or ev.target != victim:
            return
        if ev.attacker == me or ev.attacker in c.allies():
            c.world.effects.end(hold, "its own side went for the target")

    hold.subs.append(c.world.bus.on(Hit, toll, owner=me))
    hold.subs.append(c.world.bus.on(AttackDeclared, freed, owner=me))


@power(
    "m4908a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=14),
    requires=_is_bloodied,
    requires_text="the m4908 must be bloodied",
)
def m4908a4(c: Cast) -> None:
    """Its pain is shared for the rest of the fight.

    No damage line on the hit: the link is the whole of it. The ten squares
    are measured when the m4908 is hurt rather than when the link is made,
    which is what "while the target is within 10 squares" reads.
    """
    me, ref = c.me, c.ref
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == ref)
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return

    def echo(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0 or not alive(c.world, victim):
            return
        if distance_between(c.world, me, victim) <= 10:
            c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(DamageApplied, echo, until=When.ENCOUNTER, on=me, label=f"{ref} echo")


# ==========================================================================
# m5020
# ==========================================================================


@power(
    "m5020a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5020a0(c: Cast) -> None:
    """Unseen by every enemy whose line to it is well enough blocked.

    There are no skill checks in the engine, so the printed Stealth check is
    taken as made wherever it could have been tried -- the arrangement
    `_conceal` settled on eight levels down, narrowed to the printed cover:
    superior, not any. Asked at the top of each of its turns, because what is
    in the way changes as the fight moves.
    """
    me = c.me

    def creep(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for foe in c.enemies():
            if not c.is_hidden(from_=foe) and cover_between(c.world, foe, me) is Cover.SUPERIOR:
                c.hide(from_=foe)

    c.watch(TurnStart, creep, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5020a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m5020a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5020a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d6", 9, dtype=DamageType.FORCE),
)
def m5020a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5020a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d6", 5, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m5020a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m5020a4",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("1d10", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5020a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.cannot_attack(until=When.SAVE_ENDS)


@power(
    "m5020a5",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m5020a5(c: Cast) -> None:
    """A murk its own kind see through.

    "Lightly obscured" is concealment, which the engine does not hold at all
    -- `blocks_sight` is a wall rather than a haze, and using it here would
    cut the line of sight the second half of this row depends on. So the
    zone is plain and the obscurement is noted.

    "Any m5020" is two creatures off the same stat block, which is `Ident.ref`
    and nothing else. The opening is against creatures standing outside the
    zone, which is what the printed line narrows it to.
    """
    me = c.me
    zone = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)

    def peer(ev: TurnStart) -> None:
        if ev.ghost or not _same_stock(c.world, me, ev.actor):
            return
        inside = c.world.zones.occupants(zone)
        if ev.actor not in inside:
            return
        for foe in sorted(f for f in c.enemies() if f not in inside):
            c.grants_advantage(on=foe, to=ev.actor, until=When.EOT)

    c.watch(TurnStart, peer, until=When.ENCOUNTER, on=me, label=c.ref)
    c.note("m5020a5: the zone is lightly obscured")


# ==========================================================================
# m5051
# ==========================================================================


@power(
    "m5051a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d6", 9, dtype=DamageType.THUNDER),
)
def m5051a0(c: Cast) -> None:
    """The rider is for a target that was already reeling, so the state is
    asked before the blow rather than after it."""
    reeling = c.is_(Condition.BLINDED) or c.is_(Condition.DEAFENED)
    if c.strike():
        c.hit()
        if reeling:
            c.dazed(until=When.SAVE_ENDS)


@power(
    "m5051a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d6", 6, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5051a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)


@power(
    "m5051a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d6", 6, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5051a2(c: Cast) -> None:
    """The printed recharge is a sentence on top of the die the database
    files, and the two only ever agree to make the row available sooner."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


_M5051_MURK = "m5051a3 murk"


@power(
    "m5051a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=AreaBurst(3, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m5051a3(c: Cast) -> None:
    """A zone's own fields make squares rough or blind and carry no
    modifiers, so the penalties are held per occupant and diffed by the two
    events that say who is standing in it -- the arrangement m137a0 settled
    on six levels down.

    "Or until it uses this power again" is the old zone ended before the new
    one is laid. Ending it emits a `ZoneExited` for everybody inside, which
    is what takes the old holds off; the listeners come down afterwards so
    they are still there to hear it.
    """
    me = c.me
    for zid, zone in c.world.zones.all():
        if zone.owner == me and zone.label == c.ref:
            c.world.zones.end(zid, "it was laid again")
    _sweep(c, f"{c.ref} in", "the murk moved")
    _sweep(c, f"{c.ref} out", "the murk moved")

    held: dict[int, Effect] = {}
    zone_id = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)

    def cow(who: int) -> None:
        if who in held or who not in c.enemies():
            return
        held[who] = c.world.effects.apply(
            who,
            me,
            When.ENCOUNTER,
            label=_M5051_MURK,
            mods=[(who, m) for m in _softened(c, attack=2, defences=2)],
        )

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone_id:
            cow(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == zone_id else None
        if effect is not None:
            c.world.effects.end(effect, "left the murk")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(zone_id):
        cow(actor)
