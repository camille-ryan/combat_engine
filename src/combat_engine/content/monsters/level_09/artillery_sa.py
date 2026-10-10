"""Monster abilities, level 9, artillery.

92 rows across 17 stat blocks. `artillery.py` holds the earlier sweep of
this level and is not touched here. Five blocks in the brief print no
abilities at all (m141, m211, m3004, m3094, m5054) and so have nothing to
decorate.

Conventions, inherited from the earlier sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's action column claims;
* a card with no printed range at all is melee 1;
* a close burst, blast or area naming no target set takes enemies, except
  where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`;
* a range band "X/Y" takes the larger number as the single `Ranged`/
  `MeleeOrRanged` value, matching the one precedent already in the tree;
* a blow of two damage types rolled as one keeps the first in the header
  and is marked `dropped=("Damage(dtypes=)",)`; two separately named
  amounts of different types are a header blow plus a second `c.flat`,
  needing no marker;
* a Hit/Miss pair that deals the *same* amount either way is written by
  calling the header's own `c.hit()` unconditionally and gating only the
  extra rider on whether the attack actually landed.

Several cards in this brief carry a flavour name where another entry's
own ref happens to sit, read as the spec tool's extraction noise and
treated as this row's own attack throughout, never as a cross-reference.
Two creatures name something summoned that this spec gave no ref for;
finding one would mean reading the printed name the spec already
stripped, so both are `todo=("Cast.summon(ref=)",)`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
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
    Keyword,
    Melee,
    Mod,
    Ranged,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Hit,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import is_ as query_is
from combat_engine.engine.triggers import Trigger, about_me, by_me, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

_M4213_WARDS: dict[int, int] = {}
_M5559_RAY_OPTIONS = [
    "charm", "wounding", "sleep", "telekinesis", "slowing",
    "radiant", "terror", "petrifying", "death", "disintegrate",
]


def _m5559_ray(c: Cast, pick: str, victim: int) -> None:
    """Ten printed options, each its own roll and effect with no ref of
    its own -- the two-rays shape from level 5, scaled up. The Death
    Ray's second failed save is the one step with nowhere to go: nothing
    here kills a creature outright, only damage can take it to 0."""
    if pick == "charm":
        if _secondary(c, 14, WILL, victim):
            c.condition(Condition.DOMINATED, until=When.EONT, on=victim)
    elif pick == "wounding":
        if _secondary(c, 14, FORT, victim):
            c.damage("2d10", 6, dtype=DamageType.NECROTIC, on=victim)
    elif pick == "sleep":
        if _secondary(c, 14, WILL, victim):

            def worsen(eff: Any, v: int = victim) -> None:
                c.world.effects.end(eff, "fell asleep")
                c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=v)

            c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim, escalate=worsen)
    elif pick == "telekinesis":
        if _secondary(c, 14, FORT, victim):
            c.slide(4, on=victim)
    elif pick == "slowing":
        if _secondary(c, 14, REF, victim):
            c.damage("3d6", 5, dtype=DamageType.NECROTIC, on=victim)
            c.slowed(until=When.SAVE_ENDS, on=victim)
    elif pick == "radiant":
        if _secondary(c, 14, WILL, victim):
            c.damage("1d6", 5, dtype=DamageType.RADIANT, on=victim)
            c.blinded(until=When.SAVE_ENDS, on=victim)
    elif pick == "terror":
        if _secondary(c, 14, WILL, victim):
            c.damage("2d8", 5, dtype=DamageType.PSYCHIC, on=victim)
            c.push(c.speed_of(victim), on=victim)
    elif pick == "petrifying":
        if _secondary(c, 14, FORT, victim):

            def worsen(eff: Any, v: int = victim) -> None:
                c.world.effects.end(eff, "turned to stone")
                c.condition(Condition.PETRIFIED, until=When.SAVE_ENDS, on=v)

            c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim, escalate=worsen)
    elif pick == "death":
        if not _secondary(c, 14, FORT, victim):
            return
        c.damage("2d8", 10, dtype=DamageType.NECROTIC, on=victim)
        if c.bloodied(on=victim):
            c.dazed(until=When.SAVE_ENDS, on=victim)
    elif pick == "disintegrate" and _secondary(c, 14, FORT, victim):
        c.damage("1d8", 5, on=victim)
        c.ongoing(10, on=victim)


def _conscious_enemy_near_start(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or ev.ghost or team(world, who) is team(world, me):
        return False
    if distance_between(world, me, who) > 5:
        return False
    return not query_is(world, me, Condition.UNCONSCIOUS)


def _recharge_when_ward_damaged(c: Cast) -> None:
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def hurt(ev: DamageApplied) -> None:
        ward = _M4213_WARDS.get(me)
        if ward is not None and ev.target == ward and team(c.world, ev.source) is not team(
            c.world, me
        ):
            c.restore_use(ref, on=me)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=label)


# ==========================================================================
# m1118
# ==========================================================================


@power(
    "m1118a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 0, dtype=DamageType.NECROTIC),
)
def m1118a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1118a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("4d4", 4, dtype=DamageType.FORCE),
)
def m1118a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1118a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m1118a2(c: Cast) -> None:
    """The primary target is the row's own header; the two secondary
    targets are rolled separately against the same defence, near the
    primary rather than wherever the chooser would otherwise send them."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
    near = [f for f in c.enemies() if f != victim and distance_between(c.world, victim, f) <= 10]
    near.sort(key=lambda f: distance_between(c.world, victim, f))
    for extra in near[:2]:
        if _secondary(c, 10, REF, extra):
            c.damage("1d6", 6, dtype=DamageType.LIGHTNING, on=extra)


@power(
    "m1118a3",
    level=9,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.POISON],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d12", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m1118a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON))
    else:
        c.hit(half=True)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1118a4",
    level=9,
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1118a4(c: Cast) -> None:
    c.teleport(10)


# ==========================================================================
# m1583
# ==========================================================================


@power(
    "m1583a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m1583a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1583a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 5),
)
def m1583a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1583a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 5),
)
def m1583a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1583a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=3,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m1583a3(c: Cast) -> None:
    """"Requires javelin" is equipment, not tracked."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None and _secondary(c, 12, FORT, victim):
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)


# ==========================================================================
# m1920
# ==========================================================================


@power(
    "m1920a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m1920a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1920a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(8),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=12),
)
def m1920a1(c: Cast) -> None:
    """No damage line at all -- the whole of the hit is the lost surge
    and the second target's psychic payout."""
    victim = c.target
    if victim is None or not c.strike():
        return
    lost = c.surge_value(of=victim)
    c.spend_surge(on=victim)
    other = next((f for f in c.enemies() if f != victim and c.distance(f) <= 8), None)
    if other is not None and _secondary(c, 10, WILL, other):
        c.flat(lost, dtype=DamageType.PSYCHIC, on=other)


@power(
    "m1920a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d10", 4, dtype=DamageType.LIGHTNING, half_on_miss=True),
)
def m1920a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


# ==========================================================================
# m2075
# ==========================================================================


@power(
    "m2075a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m2075a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2075a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m2075a1(c: Cast) -> None:
    """No printed attack bonus at all -- read as automatic, the way a
    no-roll rider elsewhere in the tree is."""
    c.damage("2d8", 5)


@power(
    "m2075a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("3d6", 5, kind=LIMITED),
)
def m2075a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


_M2075_HIT = "it hits with an attack"


@power(
    "m2075a3",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2075_HIT,
    on=Trigger(Hit, by_me, _M2075_HIT),
)
def m2075a3(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    row = get(getattr(c.trigger, "power", "") or "")
    if row is not None and Keyword.WEAPON in row.keywords:
        c.flat(c.roll(c.w()), on=victim)
    else:
        c.flat(c.roll("1d8"), on=victim)


_M2075_BLOODIED = "it is first bloodied"


@power(
    "m2075a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2075_BLOODIED,
    on=Trigger(Bloodied, about_me, _M2075_BLOODIED),
)
def m2075a4(c: Cast) -> None:
    c.temp_hp(5, on=c.me)


# ==========================================================================
# m2095
# ==========================================================================


@power(
    "m2095a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m2095a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2095a1",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m2095a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.flat(c.roll("1d8") + 5, dtype=DamageType.NECROTIC)


@power(
    "m2095a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d10", 6, dtype=DamageType.FIRE, kind=LIMITED),
)
def m2095a2(c: Cast) -> None:
    """The fire half lands whether the attack hits or misses -- the card's
    own Miss line repeats the Hit line exactly -- so the header's damage
    is paid unconditionally and only the acid burn asks whether it hit."""
    landed = bool(c.strike())
    c.hit()
    if landed:
        c.ongoing(10, DamageType.ACID, until=When.SAVE_ENDS)


@power(
    "m2095a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("Relation.POSSESSING",),
)
def m2095a3(c: Cast) -> None:
    """The self-damage and the recharge choice both play. Becoming
    unattached from its host when this damage would kill it has nowhere
    to go -- nothing in the relation vocabulary names a host a creature
    is possessing, so there is no bond here to end."""
    c.flat(10, on=c.me)
    choice = c.choose(["m2095a1", "m2095a2"], f"{c.ref}: recharge which") or "m2095a1"
    c.restore_use(choice, on=c.me)


@power(
    "m2095a4",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m2095a4(c: Cast) -> None:
    c.teleport(5)


@power(
    "m2095a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignore_condition(redirect=)",),
)
def m2095a5(c: Cast) -> None:
    """Swapping the daze or stun's normal effect for a forced attack on
    its nearest ally has no hook -- `c.ignore_condition` only ever waives
    a condition for a turn, it does not replace what the condition makes
    the creature do. Locking `a3` out while that state holds would need
    the same conditional reach and is left with it."""


# ==========================================================================
# m3601
# ==========================================================================


@power(
    "m3601a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d4", 0),
)
def m3601a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3601a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 5),
)
def m3601a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3601a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
)
def m3601a2(c: Cast) -> None:
    targets = c.targets[:2]
    for victim in targets:
        c.use_power("m3601a1", on=victim)


@power(
    "m3601a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=16),
)
def m3601a3(c: Cast) -> None:
    if c.strike():
        c.slide(1)


@power(
    "m3601a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("3d8", 5, kind=LIMITED, half_on_miss=True),
)
def m3601a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M3601_DAMAGED = "it takes damage"


@power(
    "m3601a5",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M3601_DAMAGED,
    on=Trigger(DamageApplied, targets_me, _M3601_DAMAGED),
)
def m3601a5(c: Cast) -> None:
    me = c.me
    veil = c.invisible(on=me, until=When.EONT)
    if veil is None:
        return

    def attacked(ev: AttackDeclared) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    c.watch(AttackDeclared, attacked, until=When.EONT, on=me, label=f"{c.ref} veil")


@power(
    "m3601a6",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("TurnStart.initiative",),
)
def m3601a6(c: Cast) -> None:
    """Becoming hidden off a Stealth check made *at initiative*, on
    having cover or concealment at that exact moment, has no hook -- there
    is no event for when initiative is rolled, only for when a creature's
    own turn starts, so there is no moment to ask this at."""


# ==========================================================================
# m3791
# ==========================================================================


@power(
    "m3791a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m3791a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3791a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d4", 4),
)
def m3791a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m3791a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m3791a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        c.use_power("m3791a1", on=victim)
        if c.landed:
            hits += 1
    if hits == 2:
        c.ongoing(10, on=victim, until=When.SAVE_ENDS)
        c.condition(Condition.RESTRAINED, until=When.EONT, on=victim)


_M3791_DOWN = "it drops to 0 hit points"


@power(
    "m3791a3",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M3791_DOWN,
    on=Trigger(Dropped, about_me, _M3791_DOWN),
    attack=Attack(vs=REF, printed=12),
    damage=Damage("4d6", 4, half_on_miss=True),
)
def m3791a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m3791a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(1, 12),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("4d6", 4, kind=LIMITED, half_on_miss=True),
)
def m3791a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m3791a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("durations.ctx(origin=)",),
)
def m3791a5(c: Cast) -> None:
    """The penalty plays, laid on whoever this creature damages. Narrowing
    it to effects from a *fey-origin* creature's own powers specifically is
    the part with nowhere to ask -- the save context's `keywords` reads a
    row's declared `Keyword`s, which name damage types and tags and never
    a creature's origin."""
    me = c.me

    def hurt(ev: DamageApplied) -> None:
        if ev.source == me and ev.target is not None:
            c.penalty("save", 2, on=ev.target, until=When.ENCOUNTER)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=f"{c.ref} curse")


# ==========================================================================
# m4213
# ==========================================================================


@power(
    "m4213a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 3),
)
def m4213a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4213a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.POISON),
)
def m4213a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4213a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d6", 5, dtype=DamageType.POISON, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m4213a2(c: Cast) -> None:
    _recharge_when_ward_damaged(c)
    if c.strike():
        c.hit()


@power(
    "m4213a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m4213a3(c: Cast) -> None:
    """"An ally or object" -- only the ally half is reachable: `Target`
    offers creatures, and there is nothing on this board to aim at a
    plain object instead."""
    ward = c.target
    if ward is None:
        return
    me = c.me
    _M4213_WARDS[me] = ward

    def extra(ctx: dict[str, Any]) -> bool:
        w = _M4213_WARDS.get(me)
        if w is None:
            return False
        nearest = min(c.enemies(), key=lambda f: distance_between(c.world, w, f), default=None)
        return ctx.get("target") == nearest

    c.bonus("damage", 0, dice="2d6", on=me, until=When.ENCOUNTER, when=extra)


@power(
    "m4213a4",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4213a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m4213a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4213a5(c: Cast) -> None:
    me = c.me
    for which in ALL_DEFENCES:
        c.bonus(
            which, 2, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )


# ==========================================================================
# m4398
# ==========================================================================


@power(
    "m4398a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
)
def m4398a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d6") + 4, dtype=DamageType.LIGHTNING)


@power(
    "m4398a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
)
def m4398a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4398a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m4398a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m4398a0", on=victim)
    c.use_power("m4398a1", on=victim)
    c.use_power("m4398a1", on=victim)


@power(
    "m4398a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    no_provoke=True,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d8", 7, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m4398a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if not c.strike(on=victim):
        c.hit(on=victim, half=True)
        c.penalty("attack", 2, on=victim, until=When.EONT)
        return
    c.hit(on=victim)

    def stage3(eff: Any) -> None:
        c.world.effects.end(eff, "second failed save")
        c.condition(Condition.BLINDED, until=When.SAVE_ENDS, on=victim)

    def stage2(eff: Any) -> None:
        c.world.effects.end(eff, "first failed save")
        c.sight_range(3, on=victim, until=When.SAVE_ENDS)
        mod = Mod(what="attack", value=-2, kind="untyped", label=f"{c.ref} stage2")
        c.world.effects.apply(
            victim, c.me, When.SAVE_ENDS, label=f"{c.ref} stage2",
            mods=[(victim, mod)], escalate=stage3,
        )

    mod = Mod(what="attack", value=-2, kind="untyped", label=c.ref)
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref, mods=[(victim, mod)], escalate=stage2,
    )


_M4398_BLOODIED = "it is first bloodied"


@power(
    "m4398a4",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4398_BLOODIED,
    on=Trigger(Bloodied, about_me, _M4398_BLOODIED),
)
def m4398a4(c: Cast) -> None:
    c.restore_use("m4398a3", on=c.me)
    victim = next(iter(c.enemies()), None)
    if victim is not None:
        c.use_power("m4398a3", on=victim)


def _hit_by_nonadjacent(world: World, me: int, ev: Any) -> bool:
    attacker = getattr(ev, "attacker", None)
    return getattr(ev, "target", None) == me and attacker is not None and (
        distance_between(world, me, attacker) > 1
    )


_M4398_FAR_HIT = "it is hit by an attack from a nonadjacent creature"


@power(
    "m4398a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    trigger=_M4398_FAR_HIT,
    on=Trigger(Hit, _hit_by_nonadjacent, _M4398_FAR_HIT),
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING),
)
def m4398a5(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m4398a6",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=13),
)
def m4398a6(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    c.slide(5, on=victim)
    held = c.dazed(on=victim, until=When.SAVE_ENDS)
    if held is not None:
        held.on_end.append(lambda v=victim: c.prone(on=v))


@power(
    "m4398a7",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.LIGHTNING],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
    dropped=("Cast.forbid(action=)",),
)
def m4398a7(c: Cast) -> None:
    """The flight itself plays, through `c.flee`. Blocking immediate and
    opportunity actions specifically for the save-ends window has
    nowhere to attach -- `c.forbid` takes a row's ref, not an action
    type, so there is no way to lock out a whole category of action
    rather than one power."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    label = f"{c.ref} fled"
    c.effect(label, until=When.SAVE_ENDS, on=victim)
    me = c.me

    def run_away(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim:
            return
        if any(e.label == label for e in c.world.effects.of(victim)):
            c.flee(c.speed_of(victim), on=victim)

    c.watch(TurnStart, run_away, until=When.SAVE_ENDS, on=me, label=f"{c.ref} {victim} flee")


# ==========================================================================
# m5336
# ==========================================================================


@power(
    "m5336a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5336a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def toll(who: int) -> None:
        if who != me and team(c.world, who) is not team(c.world, me):
            boosted = any(e.label == "m5336a6 surge" for e in c.world.effects.of(me))
            c.flat(10 if boosted else 5, on=who)

    def entered(ev: Any) -> None:
        if ev.zone == ring:
            toll(ev.actor)

    def start(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            toll(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} enter")
    c.watch(TurnStart, start, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")


@power(
    "m5336a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 5),
)
def m5336a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5336a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d10", 6, dtype=DamageType.POISON),
)
def m5336a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5336a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
)
def m5336a3(c: Cast) -> None:
    for victim in c.targets[:2]:
        c.use_power("m5336a2", on=victim)


@power(
    "m5336a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d10", 6, dtype=DamageType.POISON),
    dropped=("c.immovable(except_ref=)",),
)
def m5336a4(c: Cast) -> None:
    """The immobilize plays. "Cannot be pulled, pushed, or slid except by
    its own `a5`" needs a carve-out `c.immovable` cannot make -- it
    refuses every forced move alike, which would also block the one row
    this card means to leave open."""
    if not c.strike():
        return
    c.hit()
    c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m5336a5",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5336a5(c: Cast) -> None:
    victim = next((f for f in c.enemies() if c.is_(Condition.IMMOBILIZED, on=f)), None)
    if victim is not None:
        c.pull(5, on=victim)


_M5336_HURT = "it is damaged by an attack"


@power(
    "m5336a6",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5336_HURT,
    on=Trigger(DamageApplied, targets_me, _M5336_HURT),
    dropped=("Usage.RECHARGE(when=)",),
)
def m5336a6(c: Cast) -> None:
    _recharge_when_bloodied(c)
    me = c.me
    c.slowed(until=When.EONT, on=me)
    c.cannot_attack(on=me, until=When.EONT)
    c.bonus(AC, 5, on=me, until=When.EONT)
    c.effect(f"{c.ref} surge", until=When.EONT, on=me)


# ==========================================================================
# m5559
# ==========================================================================


@power(
    "m5559a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5559a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m5559a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5559a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5559a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    no_provoke=True,
    todo=("Cast.kill()",),
)
def m5559a2(c: Cast) -> None:
    for victim in c.targets[:2]:
        pick = c.choose(_M5559_RAY_OPTIONS, f"{c.ref}: which ray") or "wounding"
        _m5559_ray(c, pick, victim)


@power(
    "m5559a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    no_provoke=True,
)
def m5559a3(c: Cast) -> None:
    """Requirement: bloodied, asked in the body -- an active row offered
    fresh each turn, so a stale `requires=` has nothing to kill here."""
    if not c.bloodied(c.me):
        return
    for victim in c.targets[:3]:
        pick = c.choose(_M5559_RAY_OPTIONS, f"{c.ref}: which ray") or "wounding"
        _m5559_ray(c, pick, victim)


@power(
    "m5559a4",
    level=9,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=12),
    todo=("Cast.forbid(usage=)",),
)
def m5559a4(c: Cast) -> None:
    """"Cannot use encounter or daily attack powers" names a whole usage
    category rather than one ref -- `c.forbid` only ever takes a single
    power's ref, so nothing here can say it."""


_M5559_NEARBY_START = "an enemy starts its turn within 5 squares of it, and it is conscious"


@power(
    "m5559a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=NO_TARGET,
    trigger=_M5559_NEARBY_START,
    on=Trigger(TurnStart, _conscious_enemy_near_start, _M5559_NEARBY_START),
)
def m5559a5(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    pick = c.choose(_M5559_RAY_OPTIONS, f"{c.ref}: which ray") or "wounding"
    _m5559_ray(c, pick, foe)


# ==========================================================================
# m5909
# ==========================================================================


@power(
    "m5909a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5909a0(c: Cast) -> None:
    c.ignores_difficult("shift", on=c.me, until=When.ENCOUNTER)


@power(
    "m5909a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 10),
)
def m5909a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5909a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 8),
)
def m5909a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5909a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d8", 8, kind=LIMITED, half_on_miss=True),
)
def m5909a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(to="team", until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.grants_advantage(to="team", until=When.EONT)


_M5909_ROLLED = "it makes an attack roll"


@power(
    "m5909a4",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5909_ROLLED,
    on=Trigger(AttackRolled, by_me, _M5909_ROLLED),
)
def m5909a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m6094
# ==========================================================================


@power(
    "m6094a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m6094a0(c: Cast) -> None:
    me = c.me
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def echo(ev: DamageApplied) -> None:
        if ev.target != me or DamageType.PSYCHIC not in ev.types():
            return
        for foe in c.enemies():
            if c.in_my_aura(foe):
                c.flat(5, dtype=DamageType.PSYCHIC, on=foe)

    c.watch(DamageApplied, echo, until=When.ENCOUNTER, on=me, label=f"{c.ref} echo")


@power(
    "m6094a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6094a1(c: Cast) -> None:
    me = c.me

    def try_saves(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if Condition.STUNNED in eff.conditions or Condition.DOMINATED in eff.conditions:
                c.world.effects.save(eff)

    c.watch(TurnStart, try_saves, until=When.ENCOUNTER, on=me, label=f"{c.ref} resist")


@power(
    "m6094a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 6),
)
def m6094a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6094a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("1d10", 9, dtype=DamageType.PSYCHIC),
)
def m6094a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.slide(2, on=victim)
        c.grants_advantage(on=victim, to="team", until=When.EONT)


@power(
    "m6094a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d8", 11, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m6094a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.slowed(until=When.EONT)


_M6094_DROPS = "it drops below 1 hit point from an attack that does not deal psychic damage"


@power(
    "m6094a5",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6094_DROPS,
    on=Trigger(Dropped, about_me, _M6094_DROPS),
    todo=("Cast.summon(ref=)",),
)
def m6094a5(c: Cast) -> None:
    """A second creature is meant to appear here. Finding its ref would
    mean reading the printed name this spec already stripped, so there
    is no ref to summon with."""


# ==========================================================================
# m6230
# ==========================================================================


@power(
    "m6230a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6230a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def slow(who: int) -> None:
        if who != me and team(c.world, who) is not team(c.world, me):
            c.slowed(on=who, until=When.SONT)

    def entered(ev: Any) -> None:
        if ev.zone == ring:
            slow(ev.actor)

    def start(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            slow(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} enter")
    c.watch(TurnStart, start, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")


@power(
    "m6230a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6230a1(c: Cast) -> None:
    """The card's own extraction noise swapped one of the two named
    surfaces for this creature's own ref, leaving only "mud" readable --
    written for the one word the spec actually kept."""
    c.ignores_difficult("mud", on=c.me, until=When.ENCOUNTER)


@power(
    "m6230a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 8),
)
def m6230a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m6230a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d6", 5),
)
def m6230a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m6230a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d8", 5, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m6230a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if not c.strike():
        return
    c.hit()
    c.prone()
    victim = c.target
    if victim is None:
        return
    existing = next(
        (e for e in c.world.effects.of(victim) if e.ongoing and e.ongoing[1] is DamageType.UNTYPED),
        None,
    )
    if existing is not None:
        amount, dtype = existing.ongoing
        existing.ongoing = (amount + 5, dtype)
    else:
        c.ongoing(5, on=victim)


@power(
    "m6230a5",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    dropped=("c.terrain(square=)",),
)
def m6230a5(c: Cast) -> None:
    """Landing specifically on a square of its own named terrain has
    nowhere to ask -- `c.terrain` reads a property of the whole
    encounter, not of one square, so there is no per-square check this
    destination constraint could run against."""
    c.teleport(10)


# ==========================================================================
# m6286
# ==========================================================================


@power(
    "m6286a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6286a0(c: Cast) -> None:
    c.ignores_difficult("shift", on=c.me, until=When.ENCOUNTER)


@power(
    "m6286a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 9),
)
def m6286a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6286a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 7),
)
def m6286a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6286a3",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6286a3(c: Cast) -> None:
    if not any(c.adjacent(f) for f in c.enemies()):
        return
    c.shift(c.speed_of())
    foe = next(iter(c.enemies()), None)
    if foe is not None:
        c.use_power("m6286a2", on=foe)


_M6286_ROLLED = "it makes an attack roll"


@power(
    "m6286a4",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6286_ROLLED,
    on=Trigger(AttackRolled, by_me, _M6286_ROLLED),
)
def m6286a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m6440
# ==========================================================================


@power(
    "m6440a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6440a0(c: Cast) -> None:
    from combat_engine.content.monsters.level_02.artillery_sa import _saves_off_prone

    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


@power(
    "m6440a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 10),
)
def m6440a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6440a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d10", 7, dtype=DamageType.COLD),
)
def m6440a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.COLD))


@power(
    "m6440a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 10, dtype=[DamageType.FIRE, DamageType.NECROTIC], kind=LIMITED),
)
def m6440a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    if not c.first:
        return
    me = c.me
    zone = c.zone(c.area(), until=When.EONT, sustain=MINOR, label=c.ref)

    def toll(ev: TurnEnd) -> None:
        if (
            not ev.ghost
            and ev.actor in c.world.zones.occupants(zone)
            and team(c.world, ev.actor) is not team(c.world, me)
        ):
            c.flat(5, dtypes=(DamageType.FIRE, DamageType.NECROTIC), on=ev.actor)

    c.watch(TurnEnd, toll, until=When.EONT, on=me, label=f"{c.ref} zone toll")


_M6440_HIT = "it is hit by an attack"


@power(
    "m6440a4",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6440_HIT,
    on=Trigger(Hit, targets_me, _M6440_HIT),
)
def m6440a4(c: Cast) -> None:
    me = c.me
    c.bonus(AC, 4, kind="power", on=me, until=When.EONT)
    c.bonus(REF, 4, kind="power", on=me, until=When.EONT)


# ==========================================================================
# m6443
# ==========================================================================


@power(
    "m6443a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6443a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m6443a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("", 8, kind=MINION),
)
def m6443a1(c: Cast) -> None:
    """"Of a random type, determined by rolling a d4" is a real roll, not
    a choice -- `c.roll` decides it, rather than handing the AI a pick
    among options the card gives it no say over."""
    if not c.strike():
        return
    roll = c.roll("1d4")
    element = {
        1: DamageType.COLD, 2: DamageType.FIRE, 3: DamageType.NECROTIC, 4: DamageType.RADIANT,
    }[roll]
    c.damage("", 8, dtype=element)
