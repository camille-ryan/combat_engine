"""Monster abilities, level 8, controllers -- the second sweep.

292 rows across 69 stat blocks, split in two: this file holds the first 35
blocks of `scripts/spec.py --monsters 8 --role controller`, 155 rows.
`controllers.py` holds the earlier sweep of this level and is untouched
here. Five of the 35 stat blocks in this slice print no abilities left to
decorate -- `m179`, `m2851`, `m2960`, `m3105`, `m346` -- they are the
earlier sweep's, in full.

Conventions, inherited from `level_07/controllers_sa.py` and this level's
own `controllers.py`:

* numbers load from `game.db`; the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it, whatever action the compendium's column claims;
* a card with no printed range at all is read `Melee(1)` against AC; against
  a non-AC defence it is read at the reach a sibling ranged row prints when
  one exists and the rider is otherwise ambiguous, and `Melee(1)` when the
  rider itself (a push, a prone, a grab) is a physical one -- said again at
  the row either way;
* a close burst or blast or area burst whose card names no target set takes
  **enemies**;
* "recharge" with no die and a prose condition is `usage=Usage.RECHARGE`
  with `recharge` left at its default and the condition armed as a watch
  that hands the use back -- `_hands_the_use_back`/`_rearms_when_bloodied`,
  both imported from `level_08/controllers.py`;
* "crit NdX+n" is the header's normal damage, auto-maxed by the engine on a
  critical, plus one more rolled die laid beside it with `c.flat(c.roll(...))`
  -- `level_08/controllers.py`'s own docstring calls this the one-step-worse
  shape of the same reading `level_07`'s high-crit rows use.

Two things the extraction lost outright, both named with the symbol that
already carries this exact gap elsewhere in the tree:

* **`m2245a0` and `m2783a3` print no attack line at all** -- a roll, a
  defence, nothing. The same defect as `#360`'s 98 rows and
  `level_04/lurkers_sa.py`'s `m815a3`: the conditions are laid outright
  because there is no `Hit` to gate them on. `dropped=("etl.monster.attack_line()",)`.
  `m4244a2` loses only the defence name -- "+12 vs or (whichever is lower)"
  -- and nothing to pick a defence from; that one is `todo=`, because its
  entire printed Effect is the attack it cannot make.
* **No printed name ever survives into this file.** `m2787a2`'s own card
  calls itself `m1034` mid-sentence -- the same shape `level_07/controllers_sa.py`
  reports for `m1108a2`/`m2781a1` -- and is read as "it" here, said again at
  the row.

Three symbols name gaps nothing else in this file's blocks share:

* **`c.wearing("heavy armor")` does not exist.** Nothing on `Cast` reads a
  creature's armour category, so every "+2 more if wearing heavy armor"
  clause on `m3447` is `dropped=` against this one symbol -- four rows, one
  gap.
* **`Weapon.rusting` does not exist.** `m3447a1`'s whole printed Effect is
  destroying a "rusting" item of a given level or lower, and nothing tags an
  item that way. `todo=`, because the attack has nothing left to aim once
  the tag it depends on is gone.
* **`c.grab(attackable=)` does not exist.** `m3300a3`'s card is the fact
  that its grab is two separate, independently attackable tentacles; the
  grab itself (`m3300a0`) already caps at two without this row's help, so
  what is missing is the tentacle being its own target. `todo=`.
* **`c.ignores_difficult(when=)` does not exist** -- confirmed absent the
  same way `level_02/minions_sa.py`'s `m115725a0` found it missing: the
  method takes a terrain `kind`, not a gate on *how* the creature is moving.
  `m3290a5` and `m3645a8` both print "ignores difficult terrain when it
  shifts" and are both `todo=` against it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.controllers_sa import _swing_reach
from combat_engine.content.monsters.level_03.brutes import NO_BIGGER_THAN_MEDIUM
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_07.controllers_sa import _no_sight_past
from combat_engine.content.monsters.level_08.controllers import (
    _hands_the_use_back,
    _rearms_when_bloodied,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
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
    MeleeOrRanged,
    Ranged,
    Target,
    UpTo,
    Usage,
    When,
    World,
    distance,
    power,
    spread,
)
from combat_engine.engine.components import Health, Movement, Powers
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Dropped,
    Hit,
    MoveEnd,
    PowerUsed,
    SavingThrow,
    SkillCheck,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    adjacent,
    allies,
    distance_between,
    enemies,
    has_combat_advantage,
    is_,
    scenery,
)
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, hits_me, targets_me
from combat_engine.engine.zones import Zone

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _enemy_closes_in(world: World, me: int, ev: AdjacencyGained) -> bool:
    """"An enemy moves to an adjacent square" -- the destination is adjacent,
    so this asks it where `MoveEnd` would have to recompute it by hand."""
    return ev.other == me and ev.actor in enemies(world, me)


def _slowed_enemy_closes_in(world: World, me: int, ev: AdjacencyGained) -> bool:
    return (
        ev.other == me
        and ev.actor in enemies(world, me)
        and is_(world, ev.actor, Condition.SLOWED)
    )


def _forced_basic_against_own_side(c: Cast, victim: int, *, times: int = 1) -> None:
    """A charmed or dazed creature compelled to swing at "a creature of
    <the caster>'s choice" -- read as one of its own allies, the printed
    trick of turning a foe against its own side.

    **The pool is narrowed to what the victim can reach.** It was every ally
    on the board, and `dsl.use` applies no reach check on an explicit target
    (#381), so a charmed creature swung at a friend across the map. The reach
    is the *victim's* basic attack, not this row's -- `c.reach` would answer
    for the charm. Where no ally is in reach there is no swing: the printed
    line grants the victim no movement.
    """
    for _ in range(times):
        span = _swing_reach(c, victim)
        pool = [
            a for a in allies(c.world, victim)
            if a != victim and distance_between(c.world, victim, a) <= span
        ]
        if not pool:
            return
        foe = c.choose(pool, f"{c.ref}: who does it attack") or pool[0]
        c.basic(who=victim, on=foe)


def _shift_closer(c: Cast, who: int, toward: int) -> None:
    """One square nearer, picked from free adjacent squares -- there is no
    "step toward" primitive, so the nearest-reducing neighbour is found by
    hand, the same shape `_free_squares_near` in `level_08/controllers.py`
    finds empty ones."""
    here = next(iter(squares_of(c.world, who)), None)
    there = next(iter(squares_of(c.world, toward)), None)
    if here is None or there is None:
        return
    options = [
        sq for sq in spread({here}, 1) - {here}
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if not options:
        return
    best = min(options, key=lambda sq: distance(sq, there))
    if distance(best, there) < distance(here, there):
        c.shift(1, who=who, to=best)


def _only_basic_attacks(c: Cast, victim: int, *, until: When) -> None:
    """"Can make only basic attacks" -- forbid every row but the one
    `Powers.basic` names."""
    known = c.world.get(victim, Powers)
    if known is None:
        return
    basic = known.basic
    for ref in known.all:
        if ref != basic:
            c.forbid(ref, on=victim, until=until)


# ==========================================================================
# m1081
# ==========================================================================


@power(
    "m1081a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4),
)
def m1081a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1081a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m1081a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1081a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.AREA],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m1081a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m1081a3",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
    trigger="an enemy moves to an adjacent square",
    on=Trigger(AdjacencyGained, _enemy_closes_in, "an enemy moves to an adjacent square"),
)
def m1081a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.push(4, on=foe)


# ==========================================================================
# m1084
# ==========================================================================


@power(
    "m1084a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4),
)
def m1084a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1084a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m1084a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1084a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
)
def m1084a2(c: Cast) -> None:
    """m1084a1 through the row that prints it, twice, so its line stays in
    one place."""
    victim = c.target
    if victim is None:
        return
    for _ in range(2):
        c.use_power("m1084a1", on=victim)


@power(
    "m1084a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.AREA],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m1084a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m1084a4",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
    trigger="an enemy moves to an adjacent square",
    on=Trigger(AdjacencyGained, _enemy_closes_in, "an enemy moves to an adjacent square"),
)
def m1084a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.push(4, on=foe)


@power(
    "m1084a5",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1084a5(c: Cast) -> None:
    c.restore_use("m1084a4", on=c.me)
    c.use_power("m1084a4")


# ==========================================================================
# m1085
# ==========================================================================


@power(
    "m1085a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4),
)
def m1085a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1085a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m1085a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1085a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.AREA],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m1085a2(c: Cast) -> None:
    """"Until the end of the cultist's next turn" is `it`'s own next turn
    -- `When.EONT`'s default, no override written."""
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m1085a3",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
    trigger="an enemy moves to an adjacent square",
    on=Trigger(AdjacencyGained, _enemy_closes_in, "an enemy moves to an adjacent square"),
)
def m1085a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.push(4, on=foe)


# ==========================================================================
# m115704
# ==========================================================================


@power(
    "m115704a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m115704a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.may("slide the target 1 square", who=c.me):
            c.slide(1)


@power(
    "m115704a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
)
def m115704a1(c: Cast) -> None:
    victim = _restricted_to(c, 5, lambda f: c.is_(Condition.DAZED, on=f))
    if victim is None or not c.strike(on=victim):
        return
    c.slide(c.speed_of(victim), on=victim)
    _forced_basic_against_own_side(c, victim)


@power(
    "m115704a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
)
def m115704a2(c: Cast) -> None:
    if c.strike():
        c.dazed(until=When.SAVE_ENDS)


def _adjacent_to_tree_or_plant(world: World, eid: int) -> bool:
    return bool(
        scenery(world, "tree", within=1, of=eid) or scenery(world, "plant", within=1, of=eid)
    )


@power(
    "m115704a3",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    requires=_adjacent_to_tree_or_plant,
    requires_text="must be adjacent to a tree or a Large plant",
)
def m115704a3(c: Cast) -> None:
    """The destination is "a square adjacent to a tree or a Large plant
    within 8 squares" -- found by hand the same way `_free_squares_near`
    in `level_08/controllers.py` finds empty ones near the caster."""
    objs = c.scenery("tree", within=8, of=c.me) + c.scenery("plant", within=8, of=c.me)
    if not objs:
        return
    candidates: set[Any] = set()
    for obj in objs:
        candidates |= spread(squares_of(c.world, obj), 1)
    free = [
        sq for sq in candidates
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if not free:
        return
    dest = min(free, key=lambda sq: distance(c.here, sq))
    c.teleport(8, to=dest)


@power(
    "m115704a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m115704a4(c: Cast) -> None:
    """A disguise and an Insight DC, nothing a fight resolves."""
    c.note(f"{c.ref}: disguises itself as a Medium humanoid")


# ==========================================================================
# m115775
# ==========================================================================


@power(
    "m115775a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115775a0(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        foe = ev.target
        if foe is None:
            return
        count = sum(1 for a in allies(c.world, me) if a != me and adjacent(c.world, a, foe))
        if count >= 2:
            c.flat(5, on=foe)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m115775a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 11),
)
def m115775a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115775a2",
    level=8,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
)
def m115775a2(c: Cast) -> None:
    if c.first:
        _hands_the_use_back(c, Dropped, lambda ev: ev.actor in c.allies())
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.penalty("attack", 2, until=When.EONT)
        _forced_basic_against_own_side(c, victim, times=2)
    c.dazed(until=When.EONT, on=victim)


@power(
    "m115775a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=WILL, printed=11),
)
def m115775a3(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.SONT)
    if c.first:
        pool = [a for a in c.allies() if a != c.me and a in c.in_squares(c.area(), side="any")]
        if pool and c.may("let an ally in the burst make a basic attack", who=c.me):
            ally = c.choose(pool, f"{c.ref}: which ally attacks") or pool[0]
            c.basic(who=ally)


@power(
    "m115775a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m115775a4(c: Cast) -> None:
    ally = c.target
    if ally is not None and c.may("shift up to 2 squares", who=ally):
        c.shift(2, who=ally)


# ==========================================================================
# m115892
# ==========================================================================


@power(
    "m115892a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.MELEE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE),
)
def m115892a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m115892a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.FIRE, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.AREA],
    attack=Attack(vs=REF, printed=11),
)
def m115892a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.ongoing(10, DamageType.FIRE)
        if victim is None:
            return
        hold = c.effect(c.ref, until=When.EONT, on=victim)
        if hold is None:
            return
        start = distance_between(c.world, c.me, victim)

        def closer(ev: MoveEnd) -> None:
            if hold.ended or ev.actor != victim or ev.kind_ == "forced":
                return
            if distance_between(c.world, c.me, victim) < start:
                c.flat(10, dtype=DamageType.PSYCHIC, on=victim)
                c.world.effects.end(hold, "it moved closer")

        hold.subs.append(c.world.bus.on(MoveEnd, closer, owner=c.me))
    else:
        c.ongoing(5, DamageType.FIRE)


@power(
    "m115892a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
)
def m115892a2(c: Cast) -> None:
    was = c.here
    if c.first:
        c.teleport(10)
    victim = c.target
    if victim is not None and c.strike(on=victim):
        c.teleport(10, who=victim, to=was)


@power(
    "m115892a3",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.TELEPORTATION, Keyword.CLOSE],
    trigger="an enemy hits it",
    on=Trigger(Hit, hits_me, "an enemy hits it"),
)
def m115892a3(c: Cast) -> None:
    c.flat(5, dtype=DamageType.FIRE)
    if c.first:
        attacker = getattr(c.trigger, "attacker", None)
        if attacker is not None:
            c.swap(attacker, who=c.me)


# ==========================================================================
# m1800
# ==========================================================================


@power(
    "m1800a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 4),
)
def m1800a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1800a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON, Keyword.AREA],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d4", 4),
)
def m1800a1(c: Cast) -> None:
    """"Requires a number of daggers equal to the enemies in the burst" is
    its own carried gear, not a fight-state fact -- the same reasoning
    `chargen.meets` gets for a prerequisite."""
    if c.strike():
        c.hit()


@power(
    "m1800a2",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(10),
    target=Target(side="ally", count=1),
)
def m1800a2(c: Cast) -> None:
    if c.target is not None:
        c.shift(1, who=c.target)


# ==========================================================================
# m1812
# ==========================================================================


@power(
    "m1812a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
)
def m1812a0(c: Cast) -> None:
    """"2d6+5, or 2d6+7 while bloodied (crit 1d6+17, or 1d6+19)" is two
    expressions: the bonus swaps on bloodied, and `c.damage` auto-maxing the
    base on a crit already lands the "+17"/"+19" half, so the extra crit die
    is laid beside it rather than folded in."""
    if not c.strike():
        return
    bonus = 7 if c.bloodied(on=c.me) else 5
    c.damage("2d6", bonus)
    if c.crit:
        c.flat(c.roll("1d6"))


@power(
    "m1812a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
)
def m1812a1(c: Cast) -> None:
    """Printed band "5/10" -- the shorter number."""
    if not c.strike():
        return
    bonus = 7 if c.bloodied(on=c.me) else 5
    c.damage("2d6", bonus)
    if c.crit:
        c.flat(c.roll("1d6"))


@power(
    "m1812a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
)
def m1812a2(c: Cast) -> None:
    """Three swings of `m1812a1`, each at a different target -- the chosen
    target first, then the nearest enemies that are not it."""
    chosen = c.target
    pool = sorted(
        (f for f in c.enemies() if f != chosen),
        key=lambda f: distance_between(c.world, c.me, f),
    )
    targets = ([chosen] if chosen is not None else []) + pool
    for foe in targets[:3]:
        c.use_power("m1812a1", on=foe)


@power(
    "m1812a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
)
def m1812a3(c: Cast) -> None:
    """"Requires a short sword" is carried gear, not asked mid-fight."""
    if not c.strike():
        return
    bonus = 7 if c.bloodied(on=c.me) else 5
    c.damage("2d6", bonus)
    if c.crit:
        c.flat(c.roll("1d6"))
    c.prone()


@power(
    "m1812a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=12),
)
def m1812a4(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: c.is_(Condition.PRONE, on=f))
    if victim is None or not c.strike(on=victim):
        return
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)


@power(
    "m1812a5",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(1, 5),
    target=NO_TARGET,
)
def m1812a5(c: Cast) -> None:
    if c.first:
        ring = c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)

        def caltrop(ev: ZoneEntered) -> None:
            if ev.zone == ring:
                c.flat(4 + c.roll("1d6"), on=ev.actor)

        c.watch(ZoneEntered, caltrop, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} zone")


@power(
    "m1812a6",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1812a6(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not by_melee(c.world, me, ev):
            return
        foe = ev.target
        if foe is None:
            return
        count = sum(1 for a in allies(c.world, me) if a != me and adjacent(c.world, a, foe))
        if count >= 2:
            c.flat(5, on=foe)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1987
# ==========================================================================


@power(
    "m1987a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
)
def m1987a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1987a1",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
)
def m1987a1(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m1987a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d12", 8, kind=LIMITED),
)
def m1987a2(c: Cast) -> None:
    if c.first:
        _hands_the_use_back(c, Bloodied, lambda ev: adjacent(c.world, c.me, ev.actor))
    victim = _restricted_to(c, 2, lambda f: has_combat_advantage(c.world, c.me, f))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.spend_surge(on=victim)
    c.weakened(until=When.SAVE_ENDS, on=victim)
    c.heal(29, on=c.me)


@power(
    "m1987a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1987a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1987a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m1987a4(c: Cast) -> None:
    """A disguise ending on its own attack or on being hit -- flavour, and
    nothing a fight resolves on."""
    c.note(f"{c.ref}: adopts the appearance of a living humanoid")


@power(
    "m1987a5",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m1987a5(c: Cast) -> None:
    me = c.me
    hold = c.insubstantial(on=me, until=When.ENCOUNTER)
    if hold is None:
        return
    moves = c.world.get(me, Movement)
    had_fly = moves.modes.get("fly") if moves else None
    if moves is not None:
        moves.modes["fly"] = 8
    phase = c.phasing(on=me, until=When.ENCOUNTER)

    def end_it() -> None:
        if not hold.ended:
            c.world.effects.end(hold, "it attacked, or was stunned or fell unconscious")
        if phase is not None and not phase.ended:
            c.world.effects.end(phase, "it attacked, or was stunned or fell unconscious")
        if moves is not None:
            if had_fly is None:
                moves.modes.pop("fly", None)
            else:
                moves.modes["fly"] = had_fly

    def used(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power != c.ref:
            end_it()

    def stunned_or_down(ev: ConditionApplied) -> None:
        if ev.target == me and ev.condition in (Condition.STUNNED, Condition.UNCONSCIOUS):
            end_it()

    hold.subs.append(c.world.bus.on(PowerUsed, used, owner=me))
    hold.subs.append(c.world.bus.on(ConditionApplied, stunned_or_down, owner=me))


# ==========================================================================
# m2234
# ==========================================================================


@power(
    "m2234a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m2234a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2234a1",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=Target(side="ally", count=1),
)
def m2234a1(c: Cast) -> None:
    ally = c.target
    if ally is None or not c.is_kind("undead", on=ally):
        return
    if c.choose(["basic attack", "move"], f"{c.ref}: what does it do") == "move":
        c.bonus("speed", 2, on=ally, until=When.EOT)
        c.extra_action(MOVE, on=ally)
    else:
        c.bonus("attack", 2, on=ally, until=When.EOT, once=True)
        c.basic(who=ally)


# ==========================================================================
# m2243
# ==========================================================================


@power(
    "m2243a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m2243a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m2243a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON, Keyword.CLOSE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m2243a1(c: Cast) -> None:
    """"Requires m2243a0" is this creature's own hands being full, not a
    fight-state fact."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2243a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m2243a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    if c.first:
        pool = [
            a for a in c.allies()
            if c.is_kind("undead", on=a) and distance_between(c.world, c.me, a) <= 5
        ]
        if c.is_kind("undead", on=c.me):
            pool.append(c.me)
        if pool:
            who = c.choose(pool, f"{c.ref}: who gains the temporary hit points") or pool[0]
            c.temp_hp(10, on=who)


@power(
    "m2243a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
)
def m2243a3(c: Cast) -> None:
    if c.first:
        me = c.me
        _hands_the_use_back(c, Hit, lambda ev: ev.attacker == me and ev.power == "m2243a2")
    if not c.strike():
        return
    victim = c.target
    if victim is not None:
        c.teleport(5, who=victim)
        c.dazed(until=When.EONT, on=victim)


@power(
    "m2243a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m2243a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.weakened(until=When.EONT, on=foe)


# ==========================================================================
# m2245
# ==========================================================================


@power(
    "m2245a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    damage=Damage("1d12", 5),
    dropped=("etl.monster.attack_line()",),
)
def m2245a0(c: Cast) -> None:
    """No attack bonus survived extraction at all -- the same defect as
    `#360`'s 98 rows, one step worse: there the defence alone is gone. The
    damage and the push are laid outright rather than gated on a `Hit` that
    cannot be rolled."""
    c.hit()
    victim = c.target
    if victim is not None and c.size_of(on=victim) in NO_BIGGER_THAN_MEDIUM:
        c.push(1, on=victim)


@power(
    "m2245a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
)
def m2245a1(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target

    def worse(eff: Effect) -> None:
        if victim is not None:
            c.unconscious(until=When.SAVE_ENDS, on=victim)

    c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim, escalate=worse)


@power(
    "m2245a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.PSYCHIC, Keyword.MELEE],
    damage=Damage("2d10", 4, dtype=DamageType.PSYCHIC),
)
def m2245a2(c: Cast) -> None:
    """"Affects an unconscious target only" with no attack line at all is
    a roll-less effect, the same shape as any other automatic hit -- there
    is nothing to roll against a helpless creature."""
    victim = _restricted_to(c, 2, lambda f: c.is_(Condition.UNCONSCIOUS, on=f))
    if victim is None:
        return
    c.hit(on=victim)
    c.heal(10, on=c.me)


@power(
    "m2245a3",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m2245a3(c: Cast) -> None:
    c.note(f"{c.ref}: disguises itself as an elderly Medium or Large humanoid")


@power(
    "m2245a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m2245a4(c: Cast) -> None:
    """Sustain Standard, which `c.insubstantial` cannot carry -- applied
    through `Effects.apply` directly, the fly mode hung on it, the same
    shape `level_08/controllers.py`'s own Sustain Standard row uses."""
    me = c.me
    hold = c.world.effects.apply(
        me, me, When.SUSTAIN, label=c.ref, sustain_cost=STANDARD,
        conditions=[Condition.INSUBSTANTIAL],
    )
    if hold is None:
        return
    moves = c.world.get(me, Movement)
    if moves is None:
        return
    had_fly = moves.modes.get("fly")
    moves.modes["fly"] = 8

    def restore() -> None:
        if had_fly is None:
            moves.modes.pop("fly", None)
        else:
            moves.modes["fly"] = had_fly

    hold.on_end.append(restore)


# ==========================================================================
# m2783
# ==========================================================================


@power(
    "m2783a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 6),
)
def m2783a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2783a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=lambda world, eid: bool((h := world.get(eid, Health)) and h.bloodied),
    requires_text="usable only while bloodied",
)
def m2783a1(c: Cast) -> None:
    if c.target is not None:
        c.basic(on=c.target)
    c.heal(22, on=c.me)


@power(
    "m2783a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d10", 6),
)
def m2783a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2783a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    damage=Damage("1d10", 6),
    dropped=("etl.monster.attack_line()",),
)
def m2783a3(c: Cast) -> None:
    """No attack line survived extraction -- the same defect `m2245a0`
    carries, laid outright rather than gated on a `Hit`."""
    c.hit()
    c.slowed(until=When.SAVE_ENDS)


@power(
    "m2783a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m2783a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


# ==========================================================================
# m2787
# ==========================================================================


@power(
    "m2787a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 0),
)
def m2787a0(c: Cast) -> None:
    bonus = 2 if c.opportunity else 0
    if c.strike(plus=bonus):
        c.hit()
        c.damage("1d8", 0, dtype=DamageType.RADIANT)
        c.slide(2)


@power(
    "m2787a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC),
)
def m2787a1(c: Cast) -> None:
    """"Cannot take standard, immediate, or opportunity actions" is read as
    `c.cannot_attack` -- broader than the three named action types, but in
    practice those three are how a creature on this board would use any of
    them."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.cannot_attack(on=victim, until=When.EONT)


@power(
    "m2787a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 0),
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit by an attack"),
)
def m2787a2(c: Cast) -> None:
    """"Requires a quarterstaff" is carried gear. The card's own text names
    itself `m1034` mid-sentence -- read as "it", the same shape
    `level_07/controllers_sa.py` reports for `m1108a2`/`m2781a1`."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.prone(on=foe)
    if c.may("shift 1 square", who=c.me):
        c.shift(1)
    mate = next((a for a in c.allies() if a != c.me), None)
    if mate is not None and c.may("shift 1 square closer to the target", who=mate):
        _shift_closer(c, mate, foe)


def _would_fail_attack(world: World, me: int, ev: AttackRolled) -> bool:
    return ev.attacker in ({me} | set(allies(world, me))) and ev.total < ev.defence


def _would_fail_save(world: World, me: int, ev: SavingThrow) -> bool:
    return ev.actor in ({me} | set(allies(world, me))) and ev.natural + ev.bonus < 10


def _would_fail_check(world: World, me: int, ev: SkillCheck) -> bool:
    return ev.actor in ({me} | set(allies(world, me))) and bool(ev.dc) and ev.total < ev.dc


@power(
    "m2787a3",
    level=8,
    usage=Usage.RECHARGE,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it or an ally would fail an attack roll, a saving throw, or a check",
    on=[
        Trigger(AttackRolled, _would_fail_attack, "it or an ally would fail an attack roll"),
        Trigger(SavingThrow, _would_fail_save, "it or an ally would fail a saving throw"),
        Trigger(SkillCheck, _would_fail_check, "it or an ally would fail a check"),
    ],
)
def m2787a3(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    ev = c.trigger
    if isinstance(ev, AttackRolled):
        ev.result.total += c.roll("1d6")
    elif isinstance(ev, (SavingThrow, SkillCheck)):
        ev.bonus += c.roll("1d6")


# ==========================================================================
# m3285
# ==========================================================================


@power(
    "m3285a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d8", 7, dtype=DamageType.NECROTIC),
)
def m3285a0(c: Cast) -> None:
    """No range printed against Fortitude; read at the reach `a1` prints."""
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


@power(
    "m3285a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RADIANT, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.RADIANT),
)
def m3285a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.effect(c.ref, until=When.EOTNT, on=victim)
    if hold is None:
        return

    def check(ev: TurnEnd) -> None:
        if hold.ended or ev.actor != victim or ev.ghost:
            return
        if distance_between(c.world, c.me, victim) <= 3:
            c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    hold.subs.append(c.world.bus.on(TurnEnd, check, owner=c.me))


@power(
    "m3285a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3285a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    hold = c.dazed(until=When.SAVE_ENDS, on=victim)
    if hold is not None and victim is not None:
        hold.on_end.append(lambda v=victim: c.penalty("attack", 2, on=v, until=When.SAVE_ENDS))


# ==========================================================================
# m3287
# ==========================================================================


@power(
    "m3287a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m3287a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m3287a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON, Keyword.CLOSE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7, kind=LIMITED),
)
def m3287a1(c: Cast) -> None:
    """"Requires a m3287a0" is carried gear. "+13 against immobilized
    targets" is +2 over the printed +11."""
    bonus = 2 if c.is_(Condition.IMMOBILIZED) else 0
    if c.strike(plus=bonus):
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3287a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.HEALING, Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d10", 0, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3287a2(c: Cast) -> None:
    """"Grants combat advantage to all attackers" has no "everyone" word on
    `c.grants_advantage` -- `to="team"` is the practical reading, since only
    this creature's own side is ever attacking the target."""
    victim = c.target
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
        c.grants_advantage(until=When.SAVE_ENDS, to="team")
    if c.first:
        pool = [c.me] + [a for a in c.allies() if a in c.in_squares(c.area(), side="any")]
        for who in pool:
            c.heal(5, on=who)
    _ = victim


@power(
    "m3287a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3287a3(c: Cast) -> None:
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER, kind="racial",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m3287a4",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit by an attack"),
)
def m3287a4(c: Cast) -> None:
    c.reroll_attack()


# ==========================================================================
# m3290
# ==========================================================================


@power(
    "m3290a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m3290a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3290a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m3290a1(c: Cast) -> None:
    """Printed band "15/30" -- the shorter number."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m3290a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(3),
    keywords=[Keyword.THUNDER, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d8", 3, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m3290a2(c: Cast) -> None:
    """"Requires a shortbow" is carried gear."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3290a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 12),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 4, kind=LIMITED),
)
def m3290a3(c: Cast) -> None:
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3290a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3290a4(c: Cast) -> None:
    c.reroll_attack()


@power(
    "m3290a5",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignores_difficult(when=)",),
)
def m3290a5(c: Cast) -> None:
    """Rough ground ignored *when it shifts*, and not otherwise;
    `c.ignores_difficult` takes a terrain `kind`, not a gate on how the
    creature is moving. Confirmed absent against `scripts/vocab.py`."""


@power(
    "m3290a6",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3290a6(c: Cast) -> None:
    mount = c.mount()
    if mount is not None:
        c.grant_row("m3290a5", on=mount, until=When.ENCOUNTER)


# ==========================================================================
# m3300
# ==========================================================================


@power(
    "m3300a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 5),
)
def m3300a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if len(c.grabbing(of=c.me)) < 2:
            c.grab()


@power(
    "m3300a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m3300a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3300a2",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=12),
)
def m3300a2(c: Cast) -> None:
    victim = _restricted_to(c, 2, lambda f: f in c.grabbing(of=c.me))
    if victim is None or not c.strike(on=victim):
        return
    c.slide(2, on=victim)


@power(
    "m3300a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.grab(attackable=)",),
)
def m3300a3(c: Cast) -> None:
    """The grab itself (`m3300a0`) already caps at two without this row's
    help. What is missing is the tentacle being its own target -- attackable
    separately, its own defences, releasing the grab without harming the
    m3300 when it is hit. Confirmed absent against `cast.py`."""


@power(
    "m3300a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m3300a4(c: Cast) -> None:
    me = c.me

    def bite(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.grabbing(of=me):
            return
        c.flat(10, dtype=DamageType.NECROTIC, on=ev.actor)
        c.temp_hp(10, on=me)

    c.watch(TurnStart, bite, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3377
# ==========================================================================


@power(
    "m3377a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d4", 4),
)
def m3377a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3377a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d6", 6, dtype=DamageType.FORCE),
)
def m3377a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.teleport(1, who=victim)


@power(
    "m3377a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("3d8", 6, kind=LIMITED),
)
def m3377a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mate = next((a for a in c.allies() if distance_between(c.world, c.me, a) <= 10), None)
    if mate is not None:
        c.swap(mate, who=victim)


@power(
    "m3377a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=WILL, printed=10),
)
def m3377a3(c: Cast) -> None:
    if c.strike():
        victim = c.target
        hold = c.condition(Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS, on=victim)
        if hold is not None and victim is not None:
            hold.on_end.append(lambda v=victim: c.slowed(until=When.SAVE_ENDS, on=v))


# ==========================================================================
# m3447
# ==========================================================================


@power(
    "m3447a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 6),
    dropped=('c.wearing("heavy armor")',),
)
def m3447a0(c: Cast) -> None:
    """"2 squares if wearing heavy armor" cannot be asked -- nothing on
    `Cast` reads a creature's armour category. The 1-square slide plays."""
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m3447a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RELIABLE, Keyword.RANGED],
    todo=("Weapon.rusting",),
)
def m3447a1(c: Cast) -> None:
    """Which items are "rusting", and of what level, is not a fact anything
    on `Cast` or `Weapon` carries -- confirmed absent against both. The
    whole printed Effect is destroying that item, so there is nothing left
    to aim once the tag it depends on is gone."""


@power(
    "m3447a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d10", 6, kind=LIMITED),
    dropped=('c.wearing("heavy armor")',),
)
def m3447a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m3447a3",
    level=8,
    usage=Usage.RECHARGE,
    action=STANDARD,
    reach=Ranged(5),
    target=Target(side="ally", count=1),
)
def m3447a3(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    ally = c.target
    if ally is None:
        return
    c.slide(5, on=ally)
    c.bonus("attack", 2, on=ally, until=When.EOT, once=True, kind="power")
    c.basic(who=ally)


@power(
    "m3447a4",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 6),
    dropped=('c.wearing("heavy armor")',),
)
def m3447a4(c: Cast) -> None:
    """"If wearing heavy armor" for the Aftereffect cannot be asked. The
    base slow plays."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m3447a5",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d8", 5, kind=LIMITED),
    dropped=('c.wearing("heavy armor")',),
)
def m3447a5(c: Cast) -> None:
    """"Plus 4 more if wearing heavy armor" cannot be asked."""
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m3469
# ==========================================================================


@power(
    "m3469a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.FIRE),
)
def m3469a0(c: Cast) -> None:
    """A push-and-prone rider reads as a physical, melee strike rather than
    the ranged distance `a1` borrows."""
    if c.strike():
        c.damage("1d6", 5, dtypes=(DamageType.FIRE, DamageType.NECROTIC))
        c.push(2)
        c.prone()


@power(
    "m3469a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.FIRE),
)
def m3469a1(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("1d6", 5, dtypes=(DamageType.FIRE, DamageType.NECROTIC))
    c.slide(2)
    victim = c.target
    if victim is None:
        return
    for which in ALL_DEFENCES:
        c.penalty(which, 2, on=victim, until=When.EONT)


@power(
    "m3469a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3469a2(c: Cast) -> None:
    for _ in range(2):
        c.basic()


@power(
    "m3469a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d10", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3469a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    c.ongoing(10, DamageType.FIRE)
    c.prone()
    if victim is None:
        return
    me = c.me

    def tick(ev: DamageApplied) -> None:
        if ev.target == victim and ev.dtype == DamageType.FIRE and ev.detail == c.ref:
            c.temp_hp(5, on=me)

    c.watch(DamageApplied, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} feed")


@power(
    "m3469a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.TELEPORTATION, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m3469a4(c: Cast) -> None:
    """"If it leaves its space" and "while it remains" are the same
    window -- one effect ends the other when either fires first."""
    victim = c.target
    if not c.strike():
        c.hit(half=True)
    else:
        c.hit()
        if victim is not None:
            hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
            if hold is not None:
                veil = c.conceal(on=victim, until=When.SAVE_ENDS)
                start = next(iter(squares_of(c.world, victim)), None)

                def left(ev: MoveEnd) -> None:
                    if hold.ended or ev.actor != victim or ev.at == start:
                        return
                    c.flat(5 + c.roll("2d6"), dtype=DamageType.PSYCHIC, on=victim)
                    c.world.effects.end(hold, "it left its space")
                    if veil is not None:
                        c.world.effects.end(veil, "it left its space")

                hold.subs.append(c.world.bus.on(MoveEnd, left, owner=c.me))
    if c.first and c.may("teleport into the burst area", who=c.me):
        dest = next(iter(c.area()), None)
        if dest is not None:
            c.teleport(0, to=dest)


@power(
    "m3469a5",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.TELEPORTATION],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m3469a5(c: Cast) -> None:
    c.restore_use("m3469a4", on=c.me)
    c.use_power("m3469a4")


# ==========================================================================
# m3472
# ==========================================================================


@power(
    "m3472a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m3472a0(c: Cast) -> None:
    """One shared bonus for whichever of m3472 and her allies hits the
    target next -- a `Hit` watch rather than a per-creature `c.bonus`, so it
    is spent once across the whole side rather than once each."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me
    pool = {me, *c.allies()}
    hold = c.effect(c.ref, until=When.ENCOUNTER, on=victim)
    if hold is None:
        return

    def first_hit(ev: Hit) -> None:
        if hold.ended or ev.attacker not in pool or ev.target != victim:
            return
        c.flat(3, on=victim)
        c.world.effects.end(hold, "the bonus was spent")

    hold.subs.append(c.world.bus.on(Hit, first_hit, owner=me))


@power(
    "m3472a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d8", 5, dtype=DamageType.FORCE),
)
def m3472a1(c: Cast) -> None:
    """"Away from the primary target" reads, in context, as away from
    m3472's own square -- the burst's point of origin and the only fixed
    point every hit creature shares, which `c.push`'s own default already
    is."""
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m3472a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3472a2(c: Cast) -> None:
    for _ in range(2):
        c.basic()


@power(
    "m3472a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING, Keyword.CLOSE],
)
def m3472a3(c: Cast) -> None:
    ally = c.target
    if ally is None:
        return
    hold = c.bonus(AC, 1, on=ally, until=When.ENCOUNTER)
    if hold is not None:
        c.endable(hold, cost=FREE, then=lambda a=ally: c.temp_hp(10, on=a))


@power(
    "m3472a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d10", 5, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3472a4(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.slide(2, on=victim)
    hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def slammed(ev: Hit) -> None:
        if hold.ended or ev.target != victim:
            return
        c.slide(2, on=victim)

    hold.subs.append(c.world.bus.on(Hit, slammed, owner=c.me))


@power(
    "m3472a5",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit by an attack"),
)
def m3472a5(c: Cast) -> None:
    pool = [
        f for f in (*c.allies(), *c.enemies())
        if f != c.me and c.is_kind("construct", on=f) and distance_between(c.world, c.me, f) <= 5
    ]
    if not pool:
        return
    picked = c.choose(pool, f"{c.ref}: swap with") or pool[0]
    if c.swap(picked):
        c.redirect(to=picked)


@power(
    "m3472a6",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m3472a6(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    c.teleport(5)


# ==========================================================================
# m3476
# ==========================================================================


@power(
    "m3476a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.FIRE),
)
def m3476a0(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", 5, dtypes=(DamageType.FIRE, DamageType.NECROTIC))
        c.push(2)
        c.prone()


@power(
    "m3476a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.FIRE),
)
def m3476a1(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("1d6", 5, dtypes=(DamageType.FIRE, DamageType.NECROTIC))
    c.slide(2)
    victim = c.target
    if victim is None:
        return
    for which in ALL_DEFENCES:
        c.penalty(which, 2, on=victim, until=When.EONT)


@power(
    "m3476a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3476a2(c: Cast) -> None:
    for _ in range(2):
        c.basic()


@power(
    "m3476a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3476a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    c.ongoing(10, DamageType.FIRE)
    c.prone()
    if victim is None:
        return
    me = c.me

    def tick(ev: DamageApplied) -> None:
        if ev.target == victim and ev.dtype == DamageType.FIRE and ev.detail == c.ref:
            c.temp_hp(5, on=me)

    c.watch(DamageApplied, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} feed")


@power(
    "m3476a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.TELEPORTATION, Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m3476a4(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        c.hit(half=True)
    else:
        c.hit()
        if victim is not None:
            hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
            if hold is not None:
                veil = c.conceal(on=victim, until=When.SAVE_ENDS)
                start = next(iter(squares_of(c.world, victim)), None)

                def left(ev: MoveEnd) -> None:
                    if hold.ended or ev.actor != victim or ev.at == start:
                        return
                    c.flat(5 + c.roll("2d6"), dtype=DamageType.PSYCHIC, on=victim)
                    c.world.effects.end(hold, "it left its space")
                    if veil is not None:
                        c.world.effects.end(veil, "it left its space")

                hold.subs.append(c.world.bus.on(MoveEnd, left, owner=c.me))
    if c.first and c.may("teleport into the burst area", who=c.me):
        dest = next(iter(c.area()), None)
        if dest is not None:
            c.teleport(0, to=dest)


@power(
    "m3476a5",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION, Keyword.ILLUSION, Keyword.PSYCHIC],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m3476a5(c: Cast) -> None:
    c.restore_use("m3476a4", on=c.me)
    c.use_power("m3476a4")


# ==========================================================================
# m3645
# ==========================================================================


@power(
    "m3645a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 6, dtype=DamageType.COLD),
)
def m3645a0(c: Cast) -> None:
    """"Requires a staff" is carried gear. "Crit 2d10+18" is the auto-maxed
    base (12+6=18) plus one extra rolled die, the same shape every high-crit
    row in this file uses."""
    if not c.strike():
        return
    c.damage("2d6", 6, dtype=DamageType.COLD)
    if c.crit:
        c.flat(c.roll("2d10"), dtype=DamageType.COLD)
    victim = c.target
    if victim is None:
        return
    c.slowed(until=When.EONT, on=victim)
    c.penalty(FORT, 2, on=victim, until=When.EONT)


@power(
    "m3645a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d8", 6, dtype=DamageType.NECROTIC),
)
def m3645a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    was = victim is not None and c.bloodied(on=victim)
    c.damage("2d8", 6, dtype=DamageType.NECROTIC)
    if c.crit:
        c.flat(c.roll("2d10"), dtype=DamageType.NECROTIC)
    c.temp_hp(4, on=c.me)
    if victim is not None and not was and c.bloodied(on=victim):
        c.weakened(until=When.EONT, on=victim)


@power(
    "m3645a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d10", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3645a2(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.damage("2d10", 6, dtype=DamageType.NECROTIC)
    if c.crit:
        c.flat(c.roll("2d10"), dtype=DamageType.NECROTIC)
    if victim is None:
        return
    c.ongoing(10, DamageType.NECROTIC)
    hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    me = c.me
    start = {"dist": distance_between(c.world, me, victim)}

    def track(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost:
            start["dist"] = distance_between(c.world, me, victim)

    def gate(ev: SavingThrow) -> None:
        if hold.ended or ev.actor != victim:
            return
        if distance_between(c.world, me, victim) <= start["dist"]:
            c.unsave(ev)

    hold.subs.append(c.world.bus.on(TurnStart, track, owner=me))
    hold.subs.append(c.world.bus.on(SavingThrow, gate, owner=me))


@power(
    "m3645a3",
    level=8,
    usage=Usage.DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.POISON),
    dropped=("c.reanimate(dominated=)",),
)
def m3645a3(c: Cast) -> None:
    """"Can move the cloud 3 squares as a move action" is this same row
    used again once the burst already stands -- the shape
    `level_07/controllers.py`'s `m2294a3` uses. "A living creature reduced
    to 0 hit points rises dominated, basic attacks only, cured by healing"
    is its own chain past what `c.reanimate` can say -- confirmed absent of
    a way to raise a creature already charmed. The burn, the cover, and the
    crit die all play."""
    me = c.me
    standing = [z for z in c.my_zones() if (b := c.world.get(z, Zone)) and b.label == c.ref]
    if standing:
        if c.first:
            c.move_zone(standing[0], 3)
        return
    if c.first:
        ring = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR, label=c.ref)
        c.cover_in(ring, side="any")
        squares_ = frozenset(c.area())

        def burn(who: int) -> None:
            c.flat(4 + c.roll("1d8"), dtype=DamageType.POISON, on=who)

        def entered(ev: ZoneEntered) -> None:
            if ev.zone == ring:
                burn(ev.actor)

        def started(ev: TurnStart) -> None:
            if not ev.ghost and ev.actor in c.in_squares(squares_, side="any"):
                burn(ev.actor)

        c.watch(ZoneEntered, entered, until=When.SUSTAIN, on=me, label=f"{c.ref} zone")
        c.watch(TurnStart, started, until=When.SUSTAIN, on=me, label=f"{c.ref} zone")
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("2d10"), dtype=DamageType.POISON)


@power(
    "m3645a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3645a4(c: Cast) -> None:
    c.reroll_attack()


@power(
    "m3645a5",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3645a5(c: Cast) -> None:
    c.temp_hp(22, on=c.me)


@power(
    "m3645a6",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m3645a6(c: Cast) -> None:
    c.move(c.speed_of(c.me))
    c.insubstantial(until=When.SONT, on=c.me)
    c.phasing(until=When.SONT, on=c.me)


@power(
    "m3645a7",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3645a7(c: Cast) -> None:
    c.no_provoke(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: "is a ranged power" in ctx.get("why", ""),
    )


@power(
    "m3645a8",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignores_difficult(when=)",),
)
def m3645a8(c: Cast) -> None:
    """Same gap as `m3290a5` -- rough ground ignored only while shifting,
    and the method has no gate to narrow it to that."""


# ==========================================================================
# m3652
# ==========================================================================


@power(
    "m3652a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m3652a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3652a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d10", 7, dtype=DamageType.FIRE),
)
def m3652a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3652a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3652a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m3652a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3652a3(c: Cast) -> None:
    """A death throe, not a revival with a tracked condition -- the trigger
    cancels the drop outright and arms the frenzy in its place, rather than
    `c.revives_unless` (which answers "would the policy write this off",
    nothing more)."""
    me = c.me
    risen = {"done": False}

    def frenzy(ev: Dropped) -> None:
        if ev.actor != me or risen["done"]:
            return
        risen["done"] = True
        c.reanimate(on=me, hp=1)
        _only_basic_attacks(c, me, until=When.ENCOUNTER)
        c.bonus(
            "damage", 0, on=me, until=When.ENCOUNTER, dice="1d6",
            when=lambda ctx: not ctx.get("ranged"),
        )

        def failing(turn_ev: TurnEnd) -> None:
            if turn_ev.actor != me or turn_ev.ghost:
                return
            if not c.save(on=me):
                c.flat(999, on=me)

        def finished(hit_ev: Hit) -> None:
            if hit_ev.target == me and hit_ev.critical:
                c.flat(999, on=me)

        c.watch(TurnEnd, failing, until=When.ENCOUNTER, on=me, label=f"{c.ref} throe")
        c.watch(Hit, finished, until=When.ENCOUNTER, on=me, label=f"{c.ref} finished")

    c.watch(Dropped, frenzy, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3652a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m3652a4(c: Cast) -> None:
    c.teleport(5)


@power(
    "m3652a5",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=Target(side="ally", count=1),
)
def m3652a5(c: Cast) -> None:
    if c.target is not None:
        c.shift(1, who=c.target)


@power(
    "m3652a6",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m3652a6(c: Cast) -> None:
    c.note(f"{c.ref}: alters its form to appear as any Medium humanoid")


# ==========================================================================
# m3763
# ==========================================================================


@power(
    "m3763a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m3763a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3763a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 7, dtype=DamageType.COLD),
)
def m3763a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m3763a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d6", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3763a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    me = c.me
    pos: dict[str, Any] = {}

    def mark_start(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost:
            pos["at"] = next(iter(squares_of(c.world, victim)), None)

    def check(ev: TurnEnd) -> None:
        if hold.ended or ev.actor != victim or ev.ghost:
            return
        here = next(iter(squares_of(c.world, victim)), None)
        if pos.get("at") == here:
            c.flat(10, dtype=DamageType.PSYCHIC, on=victim)

    hold.subs.append(c.world.bus.on(TurnStart, mark_start, owner=me))
    hold.subs.append(c.world.bus.on(TurnEnd, check, owner=me))


@power(
    "m3763a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 7, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m3763a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


# ==========================================================================
# m4244
# ==========================================================================


@power(
    "m4244a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 3),
)
def m4244a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m4244a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 6, kind=LIMITED),
    requires=lambda world, eid: bool((h := world.get(eid, Health)) and h.bloodied),
    requires_text="usable only while bloodied",
)
def m4244a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4244a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    requires=lambda world, eid: bool((h := world.get(eid, Health)) and h.bloodied),
    requires_text="usable only while bloodied",
    todo=("compendium.attack_defence", "c.aura(shrinks=)"),
)
def m4244a2(c: Cast) -> None:
    """Both defence names are gone -- "+12 vs or (whichever is lower)" --
    and unlike `m3094a1`'s version of this same defect, neither survives to
    anchor the header. Picking one would be an invented number the policy
    reads as printed, so nothing here is rolled. The second gap is its own:
    the aura this card shrinks by one square per use, and recharge-locks
    once it is gone, is not one of this file's rows, and `c.aura` has no
    shrinking radius regardless."""


@power(
    "m4244a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4244a3(c: Cast) -> None:
    c.resist(5, None, on=c.me, until=When.EONT)


# ==========================================================================
# m4254
# ==========================================================================


@power(
    "m4254a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 8),
)
def m4254a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EOTNT)


@power(
    "m4254a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d4", 8, dtype=DamageType.FORCE),
)
def m4254a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m4254a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=12),
)
def m4254a2(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    hold = c.condition(Condition.DOMINATED, until=When.EOTNT, on=victim)
    if hold is not None and victim is not None:
        hold.on_end.append(lambda v=victim: c.dazed(until=When.SAVE_ENDS, on=v))


@power(
    "m4254a3",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 6, dtype=DamageType.FORCE),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m4254a3(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.push(5, on=foe)
    c.stunned(until=When.SAVE_ENDS, on=foe)


@power(
    "m4254a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.AREA],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m4254a4(c: Cast) -> None:
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m4254a5",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def m4254a5(c: Cast) -> None:
    c.shift(2 * c.speed_of(c.me))


# ==========================================================================
# m4294
# ==========================================================================


@power(
    "m4294a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 2),
)
def m4294a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.flat(5, dtype=DamageType.POISON, on=victim)
    c.slowed(until=When.SAVE_ENDS, on=victim)
    for who in c.within(1, of=victim, side="any"):
        if who != victim:
            c.flat(5, dtype=DamageType.POISON, on=who)
            c.slowed(until=When.SAVE_ENDS, on=who)


@power(
    "m4294a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 2),
)
def m4294a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.effect(c.ref, until=When.SONT, on=victim)
    if hold is None:
        return
    start = next(iter(squares_of(c.world, victim)), None)

    def track(ev: MoveEnd) -> None:
        if hold.ended or ev.actor != victim:
            return
        if ev.kind_ == "shift":
            c.flat(5, on=victim)
            c.world.effects.end(hold, "it shifted")
            return
        if ev.kind_ != "forced" and start is not None and distance(start, ev.at) > 3:
            c.flat(5, on=victim)
            c.world.effects.end(hold, "it moved too far")

    hold.subs.append(c.world.bus.on(MoveEnd, track, owner=c.me))


@power(
    "m4294a2",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=10),
    requires=lambda world, eid: bool((h := world.get(eid, Health)) and h.bloodied),
    requires_text="usable only while bloodied",
)
def m4294a2(c: Cast) -> None:
    """No damage line at all -- the Hit clause is the flee and the Miss
    clause is the same grant, so only the flee is conditional on landing."""
    victim = c.target
    if c.strike() and victim is not None:
        c.flee(c.speed_of(victim), on=victim)
    if victim is not None:
        c.grants_advantage(on=victim, until=When.SAVE_ENDS)


# ==========================================================================
# m4326
# ==========================================================================


@power(
    "m4326a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m4326a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EOTNT)
        c.slide(1)


@power(
    "m4326a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 3),
)
def m4326a1(c: Cast) -> None:
    """Printed band "15/30" -- the shorter number."""
    if not c.strike():
        return
    c.hit()
    _no_sight_past(c, 3, until=When.EONT)


@power(
    "m4326a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4326a2(c: Cast) -> None:
    for _ in range(2):
        c.basic()


@power(
    "m4326a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=Target(side="enemy", count=2),
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4326a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.slowed(until=When.SAVE_ENDS)
    victim = c.target
    if victim is None:
        return
    rim = max(c.area(), key=lambda sq: distance(c.here, sq), default=None)
    if rim is not None:
        c.slide(3, on=victim, to=rim)


@power(
    "m4326a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4326a4(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    me = c.me
    standing = [z for z in c.my_zones() if (b := c.world.get(z, Zone)) and b.label == c.ref]
    if standing:
        if c.first:
            c.move_zone(standing[0], 3)
        return
    if c.first:
        ring = c.zone(c.area(), until=When.EONT, label=c.ref, sustain=MINOR)
        squares_ = frozenset(c.area())

        def apply_zone_effects(who: int) -> None:
            c.condition(Condition.DEAFENED, Condition.SLOWED, until=When.EONT, on=who)

        def entered(ev: ZoneEntered) -> None:
            if ev.zone == ring and ev.actor in c.enemies():
                c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)
                apply_zone_effects(ev.actor)

        def started(ev: TurnStart) -> None:
            if (
                not ev.ghost
                and ev.actor in c.enemies()
                and ev.actor in c.in_squares(squares_, side="any")
            ):
                c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)
                apply_zone_effects(ev.actor)

        c.watch(ZoneEntered, entered, until=When.EONT, on=me, label=f"{c.ref} zone")
        c.watch(TurnStart, started, until=When.EONT, on=me, label=f"{c.ref} zone")
    if c.strike():
        c.hit()


@power(
    "m4326a5",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    trigger="a slowed enemy moves or shifts to a square adjacent to m4326",
    on=Trigger(
        AdjacencyGained, _slowed_enemy_closes_in,
        "a slowed enemy moves or shifts to a square adjacent to it",
    ),
    attack=Attack(vs=FORT, printed=11),
)
def m4326a5(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.immobilized(on=foe)


@power(
    "m4326a6",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m4326a6(c: Cast) -> None:
    c.note(f"{c.ref}: alters its form to appear as any Medium humanoid, including a unique one")


@power(
    "m4326a7",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4326a7(c: Cast) -> None:
    c.mode("climb", 6, on=c.me, until=When.EONT)
