"""Monster abilities, level 7, brutes -- the second wave.

`brutes.py` holds the earlier sweep of this level and is not touched here;
the split is by *when* the work was done. 37 stat blocks, 142 rows.

Conventions, inherited from `brutes.py`'s own docstring and the level-5/6
sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms what holds it;
* a card with no printed range is melee 1;
* a close burst or blast whose card names no target set takes enemies,
  except where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- the Miss branch is written by
  hand every time it is declared;
* a printed "(crit NdX + n)" line is a high-crit rider -- a fresh roll of
  the named dice plus a flat number, not the engine's own double-dice
  default -- so it is always paid by hand (`_crit_line`), never by calling
  `c.hit()` and trusting the automatic max;
* several blocks print one ability's attack line leaking into the next
  ("+7 vs ; 1d10+4 damage.."), which is the spec tool's own extraction
  noise and not a printed sentence;
* the extraction's three-part header (`type / action / usage`) is
  sometimes out of order on a triggered row -- the parenthetical prose
  beside it is trusted first, since that is the actual parsed sentence and
  the triple is derived from the same raw columns the conventions above
  already distrust.

Helpers are imported from `level_07/brutes.py` and the levels below it
rather than written twice: `_is_bloodied`, `_crit_line`, `_crowded`,
`_aura`, `_bites`, `_run_at` and `DEFENCES` from this level's first wave;
`_recharge_on` and `_mobbed_by` from the level-6 wave; `_squeezes_freely`,
`_secondary`, `_crit_drops_it`, `_saves_off_prone` and
`_recharge_when_bloodied` from further down, each already built for the
exact shape a card here repeats.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.forms import _shapechange, _shapes
from combat_engine.content.monsters.level_01.artillery_sa import (
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_02.artillery_sa import _saves_off_prone
from combat_engine.content.monsters.level_02.soldiers_sa import _crit_drops_it
from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_06.brutes import _recharge_on
from combat_engine.content.monsters.level_06.brutes_sa import _grabbing_count, _mobbed_by
from combat_engine.content.monsters.level_07.brutes import (
    DEFENCES,
    _aura,
    _crit_line,
    _is_bloodied,
    _run_at,
)
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
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
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
    Effect,
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
    spread,
)
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    Dropped,
    Escaped,
    Hit,
    Miss,
    Moved,
    PowerUsed,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    alive,
    creatures,
    distance_between,
    enemies,
    flanked_by,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, would_hit_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _ridden_by_seventh_level(world: World, me: int) -> bool:
    """"While mounted by a friendly rider of 7th level or higher."

    Checked live rather than through `requires=` on the trait that reads
    it: the rider mounts mid-fight, so a Requirement gating the trait
    itself would be evaluated once, before anyone is in the saddle, and
    refused for good.
    """
    for rider in world.relations.targets(Relation.RIDDEN_BY, me):
        if team(world, rider) is team(world, me):
            stats = world.get(rider, Stats)
            if stats is not None and stats.level >= 7:
                return True
    return False


def _hit_me_adjacent(world: World, me: int, ev: Hit) -> bool:
    attacker = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and attacker is not None
        and attacker in enemies(world, me)
        and distance_between(world, me, attacker) <= 1
    )


def _flanked_me_by_move(world: World, me: int, ev: Moved) -> bool:
    return ev.actor in enemies(world, me) and flanked_by(world, me, ev.actor)


def _adjacent_bloodied_became(world: World, me: int, ev: Bloodied) -> bool:
    return ev.actor in enemies(world, me) and distance_between(world, me, ev.actor) <= 1


def _kin_dropped_nearby(ref: str, radius: int) -> Any:
    """"An ally who also has this trait drops to 0 hit points within N
    squares." `ref` names the shared stat block by its own id -- the ally
    is read off `Ident.ref`, since there is no other handle on "shares this
    trait" a board can ask."""

    def check(world: World, me: int, ev: Dropped) -> bool:
        victim = ev.actor
        if victim is None or victim == me or team(world, victim) is not team(world, me):
            return False
        ident = world.get(victim, Ident)
        if ident is None or ident.ref != ref:
            return False
        return distance_between(world, me, victim) <= radius

    return check


def _ongoing_amount(c: Cast, victim: int, dtype: DamageType) -> int:
    """The strongest ongoing burn of that type already on the creature, or 0."""
    best = 0
    for eff in c.world.effects.of(victim):
        if eff.ongoing and eff.ongoing[1] is dtype:
            best = max(best, eff.ongoing[0])
    return best


# ==========================================================================
# m1192
# ==========================================================================


@power(
    "m1192a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4, dtype=DamageType.COLD),
)
def m1192a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None and _secondary(c, 8, FORT, victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)


@power(
    "m1192a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m1192a1(c: Cast) -> None:
    """Two slams, each through the row that prints one so the cold damage
    and the immobilize secondary stay in one place."""
    victim = c.target
    if victim is not None:
        c.use_power("m1192a0", on=victim)
        c.use_power("m1192a0", on=victim)


@power(
    "m1192a2",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=10),
)
def m1192a2(c: Cast) -> None:
    """"Targets an immobilized creature" is asked of the body, not the
    header -- `Target` has no such filter -- and where the chooser aims this
    at somebody who does not qualify, `_restricted_to` aims it at one in
    reach who does rather than throwing the row away. `Target.kind` is the
    gap, as it is for the 112 other rows of this shape.

    The damage split is read off `DamageRolled`, the one moment a blow is
    a number and not yet a wound: half comes off this creature and lands
    on whoever it is holding, which is what "the grabbed creature takes
    the other half" means when the attack is the one landing on *this*
    creature and not on the target of this row.
    """
    victim = _restricted_to(c, 1, lambda f: c.is_(Condition.IMMOBILIZED, on=f))
    if victim is None:
        return
    if not c.strike(on=victim):
        return
    c.grab()
    me = c.me

    def burn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim or victim not in c.grabbing(of=me):
            return
        c.flat(10, dtype=DamageType.COLD, on=victim)

    def split(ev: DamageRolled) -> None:
        if ev.target != me or victim not in c.grabbing(of=me):
            return
        taken = c.halve(ev)
        if taken:
            c.flat(taken, dtype=ev.dtype, on=victim)

    c.watch(TurnStart, burn, until=When.ENCOUNTER, on=me, label=f"{c.ref} burn")
    c.watch(
        DamageRolled, split, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} split",
    )


_M1192_BLED = "the m1192 is first bloodied"


@power(
    "m1192a3",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d6", 5, dtype=DamageType.COLD, kind=LIMITED),
    trigger=_M1192_BLED,
    on=Trigger(Bloodied, about_me, _M1192_BLED),
)
def m1192a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EOTNT, on=c.target)
    if c.first:
        c.zone(spread({c.here}, 2), difficult=True, until=When.ENCOUNTER, label=c.ref)
        c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m1804
# ==========================================================================


@power(
    "m1804a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d12", 8),
)
def m1804a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1804a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d12", 10, kind=LIMITED),
)
def m1804a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m1804a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.bull_rush()",),
)
def m1804a2(c: Cast) -> None:
    """Nothing plays: there is no bull rush action in the engine for this
    trait to lengthen the push of."""


@power(
    "m1804a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1804a3(c: Cast) -> None:
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


# ==========================================================================
# m1810
# ==========================================================================


def _m1810_bloodied_hit(c: Cast, hit_bonus: int, crit_bonus: int, hurt_bonus: int) -> None:
    hurt = c.bloodied(c.me)
    if c.crit:
        c.flat(c.roll("1d12") + (crit_bonus + 2 if hurt else crit_bonus))
    elif hurt:
        c.damage("1d12", hurt_bonus)
    else:
        c.hit()


@power(
    "m1810a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d12", 8),
)
def m1810a0(c: Cast) -> None:
    if c.strike():
        _m1810_bloodied_hit(c, 8, 20, 10)


@power(
    "m1810a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 8, kind=LIMITED),
)
def m1810a1(c: Cast) -> None:
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("1d6", 10)
    else:
        c.hit()
    c.prone()


@power(
    "m1810a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d12", 8),
)
def m1810a2(c: Cast) -> None:
    if c.strike():
        _m1810_bloodied_hit(c, 8, 20, 10)
        c.push(2)


@power(
    "m1810a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1810a3(c: Cast) -> None:
    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=_mobbed_by(c, 2))


# ==========================================================================
# m2027
# ==========================================================================


@power(
    "m2027a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5),
)
def m2027a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2027a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
)
def m2027a1(c: Cast) -> None:
    if c.strike():
        victim = c.target
        c.grab()
        if victim is not None:
            c.penalty("escape", 5, on=victim, until=When.ENCOUNTER)


_M2027_DOWN = "the m2027 is reduced to 0 hit points"


@power(
    "m2027a2",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("4d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
    trigger=_M2027_DOWN,
    on=Trigger(Dropped, about_me, _M2027_DOWN),
)
def m2027a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m2027a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2027a3(c: Cast) -> None:
    _crit_drops_it(c)


# ==========================================================================
# m2058
# ==========================================================================


@power(
    "m2058a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d12", 5),
)
def m2058a0(c: Cast) -> None:
    if not c.strike():
        return
    if c.crit:
        c.flat(c.roll("1d12") + 17)
        c.flat(c.roll("1d6") + 16, dtype=DamageType.LIGHTNING)
    else:
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.LIGHTNING)


_M2058_HIT = "it is hit by an adjacent enemy"


@power(
    "m2058a1",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    trigger=_M2058_HIT,
    on=Trigger(Hit, _hit_me_adjacent, _M2058_HIT),
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d12", 5),
)
def m2058a1(c: Cast) -> None:
    """"Plus lightning damage" with no die of its own named -- the one roll
    this stat block ever gives a lightning rider is the 1d6 on its own
    basic attack, so the counterswing reuses that number."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.damage("1d6", 0, dtype=DamageType.LIGHTNING, on=foe)
        c.push(1, on=foe)


@power(
    "m2058a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="the m2058 must be bloodied",
)
def m2058a2(c: Cast) -> None:
    c.basic()
    c.heal(42, on=c.me)


@power(
    "m2058a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.THUNDER, Keyword.WEAPON],
)
def m2058a3(c: Cast) -> None:
    me = c.me

    def reward(ev: Hit) -> None:
        if ev.attacker != me or not c.bloodied(on=ev.target):
            return
        c.flat(5, dtype=DamageType.THUNDER, on=ev.target)
        c.heal(10, on=me)

    c.watch(Hit, reward, until=When.ENCOUNTER, on=me, label="m2058a3")


# ==========================================================================
# m2332
# ==========================================================================


@power(
    "m2332a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("", 4, kind=MINION),
)
def m2332a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(3, DamageType.FIRE)


# ==========================================================================
# m3457
# ==========================================================================


@power(
    "m3457a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m3457a0(c: Cast) -> None:
    """"Plus 4 damage to another enemy adjacent to it" -- adjacent to the
    caster, not to the target, which is what "the m3457" names."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.prone()
    victim = c.target
    other = next((e for e in c.within(1, side="enemy") if e != victim), None)
    if other is not None:
        c.flat(4, on=other)


def _arm_m3457a1_recharge(c: Cast) -> None:
    """Recharges after a use of `m3457a2` hits two or more targets in that
    one use -- counted by hand, since a generic "it landed a hit" watch
    would fire on the first and never wait for the second."""
    me, ref = c.me, "m3457a1"
    label = f"{ref} recharge"
    if any(e.label == label for e in c.world.effects.of(me)):
        return
    tally = {"n": 0}

    def reset(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "m3457a2":
            tally["n"] = 0

    def count(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m3457a2":
            return
        tally["n"] += 1
        if tally["n"] >= 2:
            known = c.world.get(me, Powers)
            if known is not None:
                known.restore(ref)

    c.watch(PowerUsed, reset, until=When.ENCOUNTER, on=me, label=f"{label} reset")
    c.watch(Hit, count, until=When.ENCOUNTER, on=me, label=label)


@power(
    "m3457a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 9, kind=LIMITED),
    charges=True,
)
def m3457a1(c: Cast) -> None:
    """The printed Effect is the charge itself, so the flag goes up by
    hand and `_run_at` walks."""
    _arm_m3457a1_recharge(c)
    victim = c.target
    if victim is None:
        return
    c.bonus(AC, 3, on=c.me, until=When.EOT)
    c.charge = True
    try:
        _run_at(c, victim)
        if c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)
    finally:
        c.charge = False


@power(
    "m3457a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m3457a2(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d8", 14)
    else:
        c.flat(4)


@power(
    "m3457a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3457a3(c: Cast) -> None:
    me = c.me

    def gain(ev: Hit) -> None:
        if ev.attacker != me:
            return
        p = get(ev.power or "")
        if p is not None and p.reach.kind == "melee":
            c.temp_hp(4, on=me)

    c.watch(Hit, gain, until=When.ENCOUNTER, on=me, label="m3457a3")


# ==========================================================================
# m3466
# ==========================================================================


@power(
    "m3466a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 1, dtype=DamageType.NECROTIC),
)
def m3466a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    existing = _ongoing_amount(c, victim, DamageType.NECROTIC)
    c.ongoing(10 if existing >= 5 else 5, DamageType.NECROTIC, on=victim)


# ==========================================================================
# m3468
# ==========================================================================


@power(
    "m3468a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("", 2, dtype=DamageType.NECROTIC, kind=MINION),
)
def m3468a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


_M3468_DOWN = "the m3468 is reduced to 0 hit points"


@power(
    "m3468a1",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    trigger=_M3468_DOWN,
    on=Trigger(Dropped, about_me, _M3468_DOWN),
)
def m3468a1(c: Cast) -> None:
    if c.strike():
        c.ongoing(5, DamageType.FIRE)


# ==========================================================================
# m3777 / m3792
# ==========================================================================


def _m377x_no_provoke_and_dash(c: Cast) -> None:
    me = c.me
    c.no_provoke(on=me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("charge")))

    def dash(ev: Any) -> None:
        if getattr(ev, "attacker", None) == me and bool(getattr(ev, "charge", False)):
            c.shift(3, who=me)

    c.watch(Hit, dash, until=When.ENCOUNTER, on=me, label=f"{c.ref} dash")
    c.watch(Miss, dash, until=When.ENCOUNTER, on=me, label=f"{c.ref} dash m")


def _m377x_charge_fire(c: Cast) -> None:
    me = c.me
    tally = {"n": 0}

    def reset(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            tally["n"] = 0

    def moved(ev: Moved) -> None:
        if ev.actor == me and getattr(ev, "kind_", "") == "charge":
            tally["n"] += 1

    def rider(ev: Hit) -> None:
        if ev.attacker == me and bool(getattr(ev, "charge", False)) and tally["n"]:
            c.flat(2 * tally["n"], dtype=DamageType.FIRE, on=ev.target)

    c.watch(TurnStart, reset, until=When.ENCOUNTER, on=me, label=f"{c.ref} reset")
    c.watch(Moved, moved, until=When.ENCOUNTER, on=me, label=f"{c.ref} tally")
    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=f"{c.ref} fire")


@power(
    "m3777a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 6),
)
def m3777a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3777a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3777a1(c: Cast) -> None:
    _m377x_no_provoke_and_dash(c)


@power(
    "m3777a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m3777a2(c: Cast) -> None:
    _m377x_charge_fire(c)


@power(
    "m3792a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 6),
)
def m3792a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3792a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3792a1(c: Cast) -> None:
    _m377x_no_provoke_and_dash(c)


@power(
    "m3792a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m3792a2(c: Cast) -> None:
    _m377x_charge_fire(c)


# ==========================================================================
# m3835
# ==========================================================================


@power(
    "m3835a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3835a0(c: Cast) -> None:
    """Checked at the hit rather than through `requires=`: nobody is in the
    saddle when the fight starts, and a Requirement on the trait itself
    would be refused once and never armed again."""
    me = c.me

    def bonus(ev: Hit) -> None:
        rider = ev.attacker
        if rider not in c.world.relations.targets(Relation.RIDDEN_BY, me):
            return
        if not bool(getattr(ev, "charge", False)) or not _ridden_by_seventh_level(c.world, me):
            return
        c.flat(10, on=ev.target)

    c.watch(Hit, bonus, until=When.ENCOUNTER, on=me, label="m3835a0")


@power(
    "m3835a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 7),
)
def m3835a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3835a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 7),
)
def m3835a2(c: Cast) -> None:
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)
            c.prone(on=caught)


# ==========================================================================
# m3993 / m4148
# ==========================================================================


def _dragon_a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("2d6", 0, dtype=DamageType.LIGHTNING)


def _dragon_a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _dragon_a2(c: Cast, claw_ref: str) -> None:
    victim = c.target
    if victim is not None:
        c.use_power(claw_ref, on=victim)
        c.use_power(claw_ref, on=victim)


def _dragon_a3(c: Cast, bite_ref: str) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.use_power(bite_ref, on=foe)


def _dragon_a4_secondary(c: Cast) -> None:
    """"If it hit at least one target" is read off the log rather than
    tracked across the per-target calls the burst already makes -- the
    body runs once per target and has no other shared place to keep a
    running tally."""
    if not c.last:
        return
    recent = c.world.bus.log[-50:]
    if not any(isinstance(e, Hit) and e.attacker == c.me and e.power == c.ref for e in recent):
        return
    spare = next(
        (f for f in c.enemies() if f not in c.targets and distance_between(c.world, c.me, f) <= 10),
        None,
    )
    if spare is not None and _secondary(c, 8, REF, spare):
        c.damage("2d8", 4, dtype=DamageType.LIGHTNING, on=spare)
        c.push(1, on=spare)


def _dragon_a5(c: Cast, breath_ref: str) -> None:
    c.restore_use(breath_ref, on=c.me)
    c.use_power(breath_ref)


def _dragon_a6(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    eff = c.stunned(until=When.EONT, on=victim)
    if eff is None or victim is None:
        return

    def after(ev: ConditionEnded, v: int = victim) -> None:
        if ev.condition is Condition.STUNNED and ev.target == v:
            c.penalty("attack", 2, on=v, until=When.SAVE_ENDS)

    c.watch(
        ConditionEnded, after, until=When.ENCOUNTER, on=c.me, once=True,
        label=f"{c.ref} {victim}",
    )


def _dragon_a7(c: Cast) -> None:
    """"While bloodied and completely submerged in water" -- the engine has
    no per-square depth, so `c.terrain("aquatic")` stands in for the
    submersion half and the bloodied half is asked directly."""
    if not (c.bloodied(c.me) and c.terrain("aquatic")):
        return
    c.heal(74, on=c.me)
    c.bonus("attack", 2, on=c.me, until=When.EONT)


@power(
    "m3993a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 6),
)
def m3993a0(c: Cast) -> None:
    _dragon_a0(c)


@power(
    "m3993a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 8),
)
def m3993a1(c: Cast) -> None:
    _dragon_a1(c)


@power(
    "m3993a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m3993a2(c: Cast) -> None:
    _dragon_a2(c, "m3993a1")


_M3993_FLANKED = "an enemy moves to a space where it flanks the m3993"


@power(
    "m3993a3",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M3993_FLANKED,
    on=Trigger(Moved, _flanked_me_by_move, _M3993_FLANKED),
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d12", 6),
)
def m3993a3(c: Cast) -> None:
    _dragon_a3(c, "m3993a0")


@power(
    "m3993a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m3993a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
    else:
        c.hit(half=True)
    _dragon_a4_secondary(c)


_M3993_BLED = "the m3993 is first bloodied"


@power(
    "m3993a5",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3993_BLED,
    on=Trigger(Bloodied, about_me, _M3993_BLED),
)
def m3993a5(c: Cast) -> None:
    _dragon_a5(c, "m3993a4")


@power(
    "m3993a6",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m3993a6(c: Cast) -> None:
    _dragon_a6(c)


@power(
    "m3993a7",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3993a7(c: Cast) -> None:
    _dragon_a7(c)


@power(
    "m4148a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 6),
)
def m4148a0(c: Cast) -> None:
    _dragon_a0(c)


@power(
    "m4148a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 8),
)
def m4148a1(c: Cast) -> None:
    _dragon_a1(c)


@power(
    "m4148a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m4148a2(c: Cast) -> None:
    _dragon_a2(c, "m4148a1")


_M4148_FLANKED = "an enemy moves to a space where it flanks the m4148"


@power(
    "m4148a3",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M4148_FLANKED,
    on=Trigger(Moved, _flanked_me_by_move, _M4148_FLANKED),
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d12", 6),
)
def m4148a3(c: Cast) -> None:
    _dragon_a3(c, "m4148a0")


@power(
    "m4148a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m4148a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
    else:
        c.hit(half=True)
    _dragon_a4_secondary(c)


_M4148_BLED = "the m4148 is first bloodied"


@power(
    "m4148a5",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4148_BLED,
    on=Trigger(Bloodied, about_me, _M4148_BLED),
)
def m4148a5(c: Cast) -> None:
    _dragon_a5(c, "m4148a4")


@power(
    "m4148a6",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
)
def m4148a6(c: Cast) -> None:
    _dragon_a6(c)


@power(
    "m4148a7",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m4148a7(c: Cast) -> None:
    _dragon_a7(c)


# ==========================================================================
# m3996
# ==========================================================================


@power(
    "m3996a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 6),
)
def m3996a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3996a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3996a1(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m3996a0", on=victim)
        c.use_power("m3996a0", on=victim)


_M3996_HURT = "the m3996 is first bloodied, and again when it drops to 0 hit points"


@power(
    "m3996a2",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    trigger=_M3996_HURT,
    on=[
        Trigger(Bloodied, about_me, "the m3996 is first bloodied"),
        Trigger(Dropped, about_me, "and again when it drops to 0 hit points"),
    ],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("3d8", 6),
)
def m3996a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3996a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m3996a3(c: Cast) -> None:
    """"Can make only one slam attack against each creature" is read off
    `c.overrun`'s own return: it reports every square entered once, in
    order, so a creature trampled twice in one move already appears only
    once to attack. The speed is approximated at its ordinary value --
    the printed "plus 2" has no door in `c.overrun` to add it through."""
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)


@power(
    "m3996a4",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3996a4(c: Cast) -> None:
    """A second, lower-threshold recharge roll stacked on top of the
    ordinary one rather than a replacement of it -- there is no hook into
    `actions.recharge`'s own die to lower the threshold it compares
    against, only the same manual restore `_recharge_on` already uses for
    a conditional recharge."""
    me = c.me

    def better_odds(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.bloodied(me):
            return
        known = c.world.get(me, Powers)
        if known is not None and c.roll("1d6") >= 4:
            known.restore("m3996a3")

    c.watch(TurnStart, better_odds, until=When.ENCOUNTER, on=me, label="m3996a4")


# ==========================================================================
# m4211
# ==========================================================================


@power(
    "m4211a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m4211a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4211a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d6", 6, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m4211a1(c: Cast) -> None:
    """Recharges on its own, too, when a named ally elsewhere uses `m43` --
    a cross-creature condition the generic recharge helper reads just as
    well as a self-inflicted one."""
    _recharge_on(c, PowerUsed, lambda ev: getattr(ev, "power", None) == "m43")
    if c.strike():
        c.hit()


@power(
    "m4211a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
)
def m4211a2(c: Cast) -> None:
    me = c.me

    def near_dragon(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        return any(
            c.is_kind("dragon", on=a) and distance_between(c.world, a, who) <= 1
            for a in c.allies()
        )

    c.bonus(
        "damage", 0, dice="1d6", dtype=DamageType.LIGHTNING, on=me,
        until=When.ENCOUNTER, when=near_dragon,
    )


@power(
    "m4211a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4211a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m4211a4",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4211a4(c: Cast) -> None:
    me = c.me
    for d in DEFENCES:
        c.bonus(d, 2, on=me, until=When.ENCOUNTER, when=lambda ctx: c.is_trap(ctx.get("attacker")))


# ==========================================================================
# m4645
# ==========================================================================


@power(
    "m4645a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5),
)
def m4645a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4645a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4645a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        c.use_power("m4645a0", on=victim)
        if c.landed:
            landed += 1
    if landed == 2:
        c.grab(on=victim)


@power(
    "m4645a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("4d8", 3, dtype=DamageType.NECROTIC),
)
def m4645a2(c: Cast) -> None:
    victim = c.target
    if victim is None or victim not in c.grabbing():
        return
    if c.strike():
        c.hit()


# ==========================================================================
# m5093
# ==========================================================================


@power(
    "m5093a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m5093a0(c: Cast) -> None:
    me = c.me

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or not c.bloodied(me):
            return
        if distance_between(c.world, me, ev.actor) <= 1:
            c.flat(4, dtype=DamageType.POISON, on=ev.actor)

    def rise(ev: Bloodied) -> None:
        if ev.actor != me:
            return
        c.mode("fly", 6, until=When.ENCOUNTER, on=me)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label="m5093a0 toll")
    c.watch(Bloodied, rise, until=When.ENCOUNTER, on=me, label="m5093a0 fly")


@power(
    "m5093a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d12", 6),
)
def m5093a1(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 30)


@power(
    "m5093a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("4d6", 5, dtype=DamageType.POISON),
)
def m5093a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5093a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5093a3(c: Cast) -> None:
    """`target=NO_TARGET` leaves `c.basic()`'s own default -- `c.target` --
    empty, so the victim is picked by hand instead."""
    foe = next(iter(c.enemies()), None)
    if foe is None:
        return
    c.basic(on=foe)
    c.basic(on=foe)


@power(
    "m5093a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("3d8", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m5093a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    if c.first:
        c.bonus(
            "damage", 0, dice="1d6", dtype=DamageType.POISON, on=c.me, until=When.EONT,
        )


_M5093_DOWN = "the m5093 drops to 0 hit points"


@power(
    "m5093a5",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5093_DOWN,
    on=Trigger(Dropped, about_me, _M5093_DOWN),
)
def m5093a5(c: Cast) -> None:
    c.extra_action(STANDARD, on=c.me)


# ==========================================================================
# m5288
# ==========================================================================


@power(
    "m5288a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 7),
)
def m5288a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5288a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("4d8", 7, kind=LIMITED),
)
def m5288a1(c: Cast) -> None:
    me = c.me

    def retort(ev: Hit) -> None:
        if ev.target == me and bool(getattr(ev, "opportunity", False)):
            c.flat(c.roll("1d8") + 7, dtype=DamageType.THUNDER, on=ev.attacker)

    watch = c.watch(Hit, retort, until=When.EOT, on=me, label=f"{c.ref} retort")
    c.move(c.speed_of())
    c.world.effects.end(watch, "the move is over")
    if c.strike():
        c.hit()


@power(
    "m5288a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5288a2(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m5288a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5288a3(c: Cast) -> None:
    """Two separate entities already keep two separate health pools by
    default -- nothing shares hit points between them to begin with, so
    there is no mechanism here to turn off."""


# ==========================================================================
# m5295
# ==========================================================================


@power(
    "m5295a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5295a0(c: Cast) -> None:
    ring = c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def strike_(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.basic(on=ev.actor)

    c.watch(TurnStart, strike_, until=When.ENCOUNTER, on=me, label="m5295a0")


@power(
    "m5295a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m5295a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# ==========================================================================
# m5373
# ==========================================================================


@power(
    "m5373a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5373a0(c: Cast) -> None:
    """Nothing in `actions.py` keys a charge's eligibility off burrowing in
    the first place, so there is no restriction here for the trait to lift."""


@power(
    "m5373a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5373a1(c: Cast) -> None:
    me = c.me
    c.penalty("attack", 2, on=me, until=When.ENCOUNTER, when=lambda ctx: c.terrain("sunlight"))

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT:
            c.penalty("attack", 2, on=me, until=When.EONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m5373a1")


@power(
    "m5373a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 6),
)
def m5373a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m5373a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5373a3(c: Cast) -> None:
    """Twice against a bloodied or prone creature.

    **Aimed rather than abandoned.** `Target` filters on side, count and size
    and not on what a creature is suffering, so the chooser hands this row
    whoever is nearest -- and returning when that one does not qualify threw the
    row away while somebody else in reach did. `_restricted_to` is the settled
    answer to that across the tree, and `Target.kind` is the gap in every case.

    **Aimed twice, not once.** m5373a2 pushes what it hits 2 squares, so the
    second claw was being swung at something no longer in reach -- and
    `toward=` is no help, because it is the target that moved and not the
    claw. So the second swing asks again: whoever still qualifies *and* is
    still in reach, which is often the same creature when the first claw
    missed. With nobody in reach the second claw is not swung.
    """
    def qualifies(f: int) -> bool:
        return (c.bloodied(on=f) or c.is_(Condition.PRONE, on=f)) and c.distance(f) <= 1

    victim = _restricted_to(c, 1, qualifies)
    if victim is None:
        return
    c.use_power("m5373a2", on=victim)
    again = _restricted_to(c, 1, qualifies)
    if again is not None:
        c.use_power("m5373a2", on=again)


@power(
    "m5373a4",
    level=7,
    usage=AT_WILL,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5373a4(c: Cast) -> None:
    """"Closer to a bloodied creature" is read live off the nearest one by
    squares, and the destination is the reachable square that shortens
    that distance the most -- the same shape `_slide_toward` uses for a
    forced move, here for a voluntary one with its own anchor to find."""
    me = c.me
    quarry = min(
        (e for e in c.enemies() if c.bloodied(on=e)),
        key=lambda e: distance_between(c.world, me, e),
        default=None,
    )
    if quarry is None:
        return
    now = distance_between(c.world, me, quarry)
    nearby = c.world.reachable_squares(me, 3)
    if not nearby:
        return
    best = next(iter(squares(c.world, quarry)), None)
    if best is None:
        return
    from combat_engine.engine.grid import distance as _grid_distance

    dest = min(nearby, key=lambda sq: _grid_distance(sq, best))
    if _grid_distance(dest, best) < now:
        c.shift(3, to=dest)


@power(
    "m5373a5",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 5),
)
def m5373a5(c: Cast) -> None:
    """Aimed rather than abandoned -- see `m5373a3`. `Target.kind` is the gap."""
    victim = _restricted_to(
        c, 1, lambda f: c.bloodied(on=f) or c.is_(Condition.PRONE, on=f)
    )
    if victim is None:
        return
    if not c.strike(on=victim):
        return
    c.hit()
    if c.is_(Condition.SLOWED, on=victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)
    else:
        c.slowed(until=When.EOTNT, on=victim)


# ==========================================================================
# m5572
# ==========================================================================


@power(
    "m5572a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 6),
)
def m5572a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5572a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 10, kind=LIMITED),
)
def m5572a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


_M5572_KIN_BLED = "an enemy adjacent to it becomes bloodied"


@power(
    "m5572a2",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5572_KIN_BLED,
    on=Trigger(Bloodied, _adjacent_bloodied_became, _M5572_KIN_BLED),
)
def m5572a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    c.restore_use("m5572a1", on=c.me)
    c.use_power("m5572a1", on=foe)


# ==========================================================================
# m5647
# ==========================================================================


@power(
    "m5647a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m5647a0(c: Cast) -> None:
    ring = c.aura(2, until=When.ENCOUNTER)
    me = c.me

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(10, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label="m5647a0")


@power(
    "m5647a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5647a1(c: Cast) -> None:
    c.ignore_resistance(10, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)


@power(
    "m5647a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5647a2(c: Cast) -> None:
    _squeezes_freely(c)


@power(
    "m5647a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 7, dtype=DamageType.FIRE),
)
def m5647a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5647a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 2, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5647a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5647a5",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 4, dtype=DamageType.POISON),
)
def m5647a5(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5647_BLED = "the m5647 is bloodied"


@power(
    "m5647a6",
    level=7,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M5647_BLED,
    on=Trigger(Bloodied, about_me, _M5647_BLED),
)
def m5647a6(c: Cast) -> None:
    c.restore_use("m5647a4", on=c.me)
    c.use_power("m5647a4")


# ==========================================================================
# m5828
# ==========================================================================


@power(
    "m5828a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5828a0(c: Cast) -> None:
    me = c.me

    def ward(ev: DamageRolled) -> None:
        if ev.target == me and ev.dtype is not DamageType.FORCE:
            c.halve(ev)

    c.watch(
        DamageRolled, ward, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label="m5828a0",
    )


_M5828_KIN_DOWN = "an ally with this trait drops to 0 hit points within 5 squares"


@power(
    "m5828a1",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5828_KIN_DOWN,
    on=Trigger(Dropped, _kin_dropped_nearby("m5828", 5), _M5828_KIN_DOWN),
)
def m5828a1(c: Cast) -> None:
    c.bonus("attack", 2, kind="power", on=c.me, until=When.EONT)


@power(
    "m5828a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC),
)
def m5828a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5828a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC),
    charges=True,
)
def m5828a3(c: Cast) -> None:
    """The printed Effect is the charge, so the flag goes up by hand and
    `_run_at` walks -- `c.charge_at` cannot re-enter a row already in
    flight."""
    victim = c.target
    if victim is None:
        return
    c.charge = True
    try:
        _run_at(c, victim)
        if c.strike(on=victim):
            c.hit(on=victim)
            c.push(1, on=victim)
            c.prone(on=victim)
    finally:
        c.charge = False


@power(
    "m5828a4",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m5828a4(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5888
# ==========================================================================


@power(
    "m5888a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5888a0(c: Cast) -> None:
    c.aura(2, until=When.ENCOUNTER)
    me = c.me
    for ally in c.allies():

        def near_and_hurt(_ctx: dict[str, Any], a: int = ally) -> bool:
            return c.bloodied(on=a) and distance_between(c.world, me, a) <= 2

        c.bonus("attack", 2, kind="power", on=ally, until=When.ENCOUNTER, when=near_and_hurt)
        c.bonus("damage", 2, kind="power", on=ally, until=When.ENCOUNTER, when=near_and_hurt)


@power(
    "m5888a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5888a1(c: Cast) -> None:
    me = c.me

    def rattled(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "critical", False):
            c.stunned(until=When.EOTNT, on=ev.target)

    c.watch(Hit, rattled, until=When.ENCOUNTER, on=me, label="m5888a1")


@power(
    "m5888a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 8),
)
def m5888a2(c: Cast) -> None:
    """Pushed first, then it closes the gap back to a square beside where
    the push left the target -- the printed order, and the only order a
    destination chosen *after* the push can be found in."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    c.push(2)
    if victim is None:
        return
    from combat_engine.engine.grid import distance as _grid_distance

    theirs = squares(c.world, victim)
    if not theirs:
        return
    ring = {sq for s in theirs for sq in spread({s}, 1)} - theirs
    reachable = ring & set(c.world.reachable_squares(c.me, 2))
    if not reachable:
        return
    here = next(iter(squares(c.world, c.me)), None)
    if here is None:
        return
    dest = min(reachable, key=lambda sq: _grid_distance(sq, here))
    c.shift(2, to=dest)


@power(
    "m5888a3",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("3d6", 8),
)
def m5888a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5888a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    todo=("c.grant_action(charge)",),
)
def m5888a4(c: Cast) -> None:
    """Nothing plays: `c.grant_action` understands `shift`, `stand`,
    `escape` and `second_wind`, and silently drops anything else --
    `actions.py` reads none of the words that would be needed for
    "charge", so the entire printed Effect has nowhere to land."""


# ==========================================================================
# m5956
# ==========================================================================


@power(
    "m5956a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("compendium.silvered",),
)
def m5956a0(c: Cast) -> None:
    """The regeneration plays. Switching it off for a turn after a silvered
    weapon lands does not: nothing marks a weapon as made of silver, which
    is a different gap from the damage-*type* suspension `suspended_by=`
    already names."""
    c.regeneration(5, on=c.me, until=When.ENCOUNTER)


@power(
    "m5956a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 4),
    requires=_shapes("humanoid", "hybrid"),
    requires_text="it must be in humanoid or hybrid form",
)
def m5956a1(c: Cast) -> None:
    if not c.strike():
        return
    if c.bloodied(on=c.target):
        c.damage("2d10", 9)
    else:
        c.hit()


@power(
    "m5956a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 5),
    requires=_shapes("beast", "hybrid"),
    requires_text="it must be in beast or hybrid form",
)
def m5956a2(c: Cast) -> None:
    if not c.strike():
        return
    if c.bloodied(on=c.target):
        c.damage("3d6", 10)
    else:
        c.hit()
    c.prone()


@power(
    "m5956a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.basic(half_on_miss=)",),
    requires=_shapes("beast", "hybrid"),
    requires_text="it must be in beast or hybrid form",
)
def m5956a3(c: Cast) -> None:
    """"Makes a melee basic attack" is `c.basic()`, which rolls whichever
    row that creature's basic actually is and returns only hit-or-miss --
    there is no door to read back the roll it made, so the printed
    half-damage-on-a-miss has nowhere to read a number from.

    The row declares no target, so the creature it is about to swing at is
    picked *before* the move rather than after it -- the move is what brings
    it into reach, and it cannot be aimed at a choice not yet made."""
    foe = c.choose(c.enemies(), f"{c.ref}: who to run down")
    c.move(c.speed_of() * 2, toward=foe)
    if foe is None:
        return
    c.bonus("damage", 8, kind="power", on=c.me, until=When.EOT, once=True)
    c.basic(on=foe)


@power(
    "m5956a4",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m5956a4(c: Cast) -> None:
    """It alters its physical form: humanoid, hybrid, beast.

    **Written now that a shape can be read.** This was appearance only,
    and correctly so while nothing could ask which form the creature was
    in -- its own note said the gated attacks carried the gap. Those
    Requirements are gates now, so the shape is what decides which of
    this creature's attacks it may use, and the row is no longer out of
    combat.

    `humanoid` leads the list because that is what the creature is before it
    changes anything, and one form replaces another -- which is what
    "until it uses this power again" means.
    """
    _shapechange(c, "humanoid", "hybrid", "beast")
# ==========================================================================
# m5959
# ==========================================================================


@power(
    "m5959a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 6),
)
def m5959a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


_M5959_BLED = "the m5959 is first bloodied"


@power(
    "m5959a1",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
    trigger=_M5959_BLED,
    on=Trigger(Bloodied, about_me, _M5959_BLED),
)
def m5959a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, None, until=When.EONT)
    else:
        c.hit(half=True)


# ==========================================================================
# m6112
# ==========================================================================


@power(
    "m6112a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6112a0(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype in (DamageType.COLD, DamageType.RADIANT):
            c.forbid("m6112a3", on=me, until=When.EONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m6112a0")


@power(
    "m6112a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 7),
    dropped=("c.contract(ref)",),
)
def m6112a1(c: Cast) -> None:
    """The damage and the escalating penalty against a bloodied target both
    play. Contracting the named rot at the end of the encounter does not --
    no mechanism stands up a disease track for a row to progress."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.penalty("save", 5 if c.bloodied(on=victim) else 2, on=victim, until=When.ENCOUNTER)


@power(
    "m6112a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.DISEASE, Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("3d8", 4, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
    dropped=("c.contract(ref)",),
)
def m6112a2(c: Cast) -> None:
    me = c.me
    _recharge_on(c, DamageApplied, lambda ev: ev.target == me and ev.dtype is DamageType.LIGHTNING)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M6112_HIT = "a weapon attack hits it"


def _hit_by_weapon(world: World, me: int, ev: Hit) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and Keyword.WEAPON in row.keywords


@power(
    "m6112a3",
    level=7,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6112_HIT,
    on=Trigger(Hit, _hit_by_weapon, _M6112_HIT),
)
def m6112a3(c: Cast) -> None:
    me = c.me

    def shield(ev: DamageRolled) -> None:
        if ev.target == me:
            c.reduce(5, ev)

    c.watch(
        DamageRolled, shield, until=When.EOT, window=Window.BEFORE, on=me, once=True,
        label=f"{c.ref} resist",
    )


# ==========================================================================
# m6393
# ==========================================================================


@power(
    "m6393a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 7),
)
def m6393a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 6, dtype=DamageType.FORCE)


@power(
    "m6393a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.THUNDER],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 7, kind=LIMITED),
)
def m6393a1(c: Cast) -> None:
    hit = c.strike()
    if hit:
        c.hit()
        c.damage("1d6", 6, dtype=DamageType.FORCE)
    victim = c.target
    if victim is None:
        return
    for who in [victim, *c.within(1, of=victim, side="any")]:
        if who != c.me:
            c.flat(5, dtype=DamageType.THUNDER, on=who)
            c.prone(on=who)


_M6393_HIT = "it hits with an attack"


@power(
    "m6393a2",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FORCE],
    trigger=_M6393_HIT,
    on=Trigger(Hit, lambda w, me, ev: getattr(ev, "attacker", None) == me, _M6393_HIT),
)
def m6393a2(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    c.flat(c.roll("1d10"), dtype=DamageType.FORCE, on=victim)
    c.prone(on=victim)


# ==========================================================================
# m6428
# ==========================================================================


@power(
    "m6428a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6428a0(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("opportunity")))


@power(
    "m6428a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6428a1(c: Cast) -> None:
    me = c.me
    c.penalty("attack", 2, on=me, until=When.ENCOUNTER, when=lambda ctx: c.bloodied(me))
    c.bonus("damage", 0, dice="2d6", on=me, until=When.ENCOUNTER, when=lambda ctx: c.bloodied(me))


@power(
    "m6428a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 8),
)
def m6428a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6428a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d6", 14, kind=LIMITED),
)
def m6428a3(c: Cast) -> None:
    if c.strike():
        c.hit()


_M6428_HIT = "an enemy hits it with an attack"


@power(
    "m6428a4",
    level=7,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6428_HIT,
    on=Trigger(AttackRolled, would_hit_me, _M6428_HIT),
)
def m6428a4(c: Cast) -> None:
    c.reroll_attack()


# ==========================================================================
# m6432
# ==========================================================================


@power(
    "m6432a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d12", 6),
)
def m6432a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6432a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d12", 9, kind=LIMITED),
)
def m6432a1(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()


@power(
    "m6432a2",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m6432a2(c: Cast) -> None:
    me = c.me
    c.temp_hp(6, on=me)
    for eff in sorted(c.world.effects.of(me), key=lambda e: -e.id):
        if eff.ongoing is not None and eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)
            break
    if c.bloodied(me):
        c.heal(6, on=me)


# ==========================================================================
# m6482 / m6483
# ==========================================================================


def _grabs_and_burns(c: Cast, victim: int) -> None:
    c.grab(on=victim)
    hold = c.ongoing(8, on=victim, until=When.ENCOUNTER)
    if hold is None:
        return

    def freed(ev: Escaped, h: Effect = hold, v: int = victim) -> None:
        if ev.actor == v:
            c.world.effects.end(h, "escaped the grab")

    c.watch(Escaped, freed, until=When.ENCOUNTER, on=c.me, once=True, label=f"{c.ref} release")


@power(
    "m6482a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 8, kind=MINION),
    requires=lambda world, eid: _grabbing_count(world, eid) == 0,
    requires_text="the m6482 must have no creature grabbed",
)
def m6482a0(c: Cast) -> None:
    """The grab and the burn both play; the escape DC the card prints (16)
    does not -- `c.grab` has no DC of its own and reads the grabber's live
    defence instead, which this minion's own low numbers would understate."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        _grabs_and_burns(c, victim)


_M6482_DOWN = "the m6482 drops to 0 hit points"


@power(
    "m6482a1",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6482_DOWN,
    on=Trigger(Dropped, about_me, _M6482_DOWN),
)
def m6482a1(c: Cast) -> None:
    me = c.me
    spot = next(iter(squares(c.world, me)), None)

    def rise(ts: TurnStart, s: Any = spot) -> None:
        if ts.ghost or ts.actor != me:
            return
        c.summon("m6483", at=s)
        c.world.effects.end(hold[0], "it rose")

    hold = [c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, once=True, label="m6482a1")]


@power(
    "m6483a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 8, kind=MINION),
    requires=lambda world, eid: _grabbing_count(world, eid) == 0,
    requires_text="it must have no creature grabbed",
)
def m6483a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        _grabs_and_burns(c, victim)


# ==========================================================================
# m6618
# ==========================================================================


@power(
    "m6618a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 7),
)
def m6618a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m6639
# ==========================================================================


def _adjacent_to_active_kin(c: Cast, who: int | None) -> bool:
    if who is None:
        return False
    me = c.me
    for other in creatures(c.world):
        if other == me or not alive(c.world, other):
            continue
        ident = c.world.get(other, Ident)
        if ident is None or ident.ref != "m6639":
            continue
        near = distance_between(c.world, other, who) <= 1
        if near and not c.is_(Condition.UNCONSCIOUS, on=other):
            return True
    return False


@power(
    "m6639a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6639a0(c: Cast) -> None:
    c.gains_advantage(
        lambda ctx: _adjacent_to_active_kin(c, ctx.get("target")), on=c.me, until=When.ENCOUNTER,
    )


@power(
    "m6639a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 9, kind=MINION),
)
def m6639a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    if c.result is not None and c.result.advantage:
        c.flat(2)


# ==========================================================================
# m6644
# ==========================================================================


@power(
    "m6644a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m6644a0(c: Cast) -> None:
    def hold(who: int) -> Effect | None:
        return c.world.effects.apply(
            who, c.me, When.ENCOUNTER, label=f"{c.ref} {who}",
            mods=[(who, Mod(what=d, value=-2, kind="untyped", label=c.ref)) for d in DEFENCES],
        )

    _aura(c, 10, lambda w: w in c.enemies(), hold)


@power(
    "m6644a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m6644a1(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        ident = c.world.get(ev.actor, Ident)
        if ident is not None and ident.ref == "m6644":
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(c.roll("5d8"), on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label="m6644a1")


@power(
    "m6644a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.cannot_hide()",),
)
def m6644a2(c: Cast) -> None:
    """Narrowing who it can surprise plays nowhere here either: nothing
    walks a per-creature hearing check. The one clause the engine can be
    asked -- forbidding this creature from ever hiding -- has no verb,
    since every hide-related method stops at *doing* or *reading* a hide,
    never at refusing one."""


@power(
    "m6644a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.immovable(from_=)",),
)
def m6644a3(c: Cast) -> None:
    """Sharing a space and the difficult terrain that comes with it both
    play. Refusing forced movement from melee and ranged attacks alone does
    not -- `c.immovable` is all-or-nothing and has no way to name the two
    sources this card exempts and nothing else. Squeezing through an
    opening sized for one of its components has no model either and is not
    a second gap worth a second marker: nothing tracks a sub-creature's
    size to measure the opening against."""
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=True)


@power(
    "m6644a4",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("5d8", 0),
)
def m6644a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6644a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6644a5(c: Cast) -> None:
    before = set(c.within(1, side="enemy"))
    c.shift(c.speed_of())
    newly = sorted(set(c.within(1, side="enemy")) - before)
    if not newly:
        return
    victim = newly[0]
    c.use_power("m6644a4", on=victim)
    if c.landed and not c.save(on=victim):
        c.prone(on=victim)


def _m6644_struck(world: World, me: int, ev: Hit) -> bool:
    return getattr(ev, "target", None) == me


@power(
    "m6644a6",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6644a6(c: Cast) -> None:
    _recharge_on(c, Hit, lambda ev: _m6644_struck(c.world, c.me, ev))
    c.shift(c.speed_of())


# ==========================================================================
# m6660
# ==========================================================================


@power(
    "m6660a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6660a0(c: Cast) -> None:
    me = c.me
    granted: set[int] = set()

    def check(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        current = set(c.grabbing())
        rider = c.rider()
        targets = [me] if rider is None else [me, rider]
        for who in current - granted:
            c.world.effects.apply(
                who, me, When.ENCOUNTER, label=f"{c.ref} {who}",
                relations=[(Relation.GRANTS_CA_TO, who, t) for t in targets],
            )
        granted.clear()
        granted.update(current)

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label="m6660a0")


@power(
    "m6660a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6660a1(c: Cast) -> None:
    def helpless_foe(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        return any(
            c.is_(cond, on=who)
            for cond in (
                Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.STUNNED,
                Condition.UNCONSCIOUS,
            )
        )

    c.bonus("damage", 5, kind="power", on=c.me, until=When.ENCOUNTER, when=helpless_foe)


@power(
    "m6660a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 7),
    requires=lambda world, eid: _grabbing_count(world, eid) == 0,
    requires_text="the m6660 must have no creature grabbed",
)
def m6660a2(c: Cast) -> None:
    """"Can use `m6660a1` only on that creature" needs nothing further: a
    single attack already has one target, so the gated bonus on `a1`
    already cannot land anywhere else."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.grab(on=victim, dc=16)
