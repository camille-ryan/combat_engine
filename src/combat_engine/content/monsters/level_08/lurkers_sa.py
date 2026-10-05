"""Monster abilities, level 8, lurkers, second wave.

Twenty-four stat blocks, 111 rows. `lurkers.py` holds the earlier sweep of
this level and is not touched here; one of the twenty-four prints no
abilities at all and has nothing to decorate: m149.

Conventions, inherited from the level 1-7 lurker sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's column claims;
* a card with no printed range at all is melee 1;
* a close burst or blast whose card names no target set takes **enemies**,
  except where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`;
* **"Target: a creature that cannot see it" or "...that is immobilized,
  stunned, or unconscious" is the target's own state, not the chooser's
  business** -- `Target` filters side, count and size and not what a
  creature is suffering, so `_restricted_to` (level_03) is reused across
  this file the same way it was settled two levels down. Each use is marked for
  the gap it has: `dropped=("Target.relation",)` where the line is about the
  caster -- "cannot see it" -- and `dropped=("Target.condition",)` where it is
  about a condition the creature carries.

Lurkers lean on concealment, invisibility and combat-advantage riders, and
this file leans on `_triggering_enemy`, `_secondary`, `_vanish_until_it_
swings`, `_recharge_when_using`, `_twice`, `_aura_holds` and `_restricted_
to`, all imported rather than written again.

Three helpers are new here, each because a run of rows genuinely shares the
shape: `_bonus_vs_advantage` is "extra damage against a target it has (or
grants) combat advantage against", `_cant_see_me_bonus` is the same shape
for "cannot see it", and `_invisible_to_until_it_fights` is a single
per-target invisibility that two different fey block the same way: ended by
either its own next attack or being struck, whichever comes first.

Two name-shaped things, written around rather than copied: m322a2 and
m5581a3 each name a ritual by its own ref ("x0_27") rather than a creature's
printed name, which is safe to read as what it is -- neither clause has a
combat reading on a board that casts no rituals.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.lurkers_sa import (
    _recharge_when_using,
    _triggering_enemy,
    _twice,
)
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers import _vanish_until_it_swings
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    Keyword,
    Melee,
    Position,
    Ranged,
    Relation,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Escaped,
    Hit,
    Miss,
    PowerUsed,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, has_combat_advantage, team, unseen_by
from combat_engine.engine.triggers import Trigger, about_me, by_melee, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _bonus_vs_advantage(c: Cast, dice: str) -> None:
    """"Deals N extra damage against a target it has (or grants) combat
    advantage against." Both printed directions read the same live fact."""
    c.bonus(
        "damage", 0, dice=dice, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


def _cant_see_me_bonus(c: Cast, dice: str) -> None:
    """"Deals N extra damage to a target that cannot see it" -- asked of the
    target's side, not the attacker's: `c.can_see` would answer the wrong
    question here."""

    def hidden_from_target(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and unseen_by(c.world, who, c.me)

    c.bonus("damage", 0, dice=dice, on=c.me, until=When.ENCOUNTER, when=hidden_from_target)


def _invisible_to_until_it_fights(c: Cast, victim: int) -> None:
    """"Invisible to the target until she attacks or is hit by an attack" --
    one hold, ended by either of two different events, neither of them a
    clock."""
    me = c.me
    held = c.invisible(to=victim, on=me, until=When.ENCOUNTER)
    if held is None:
        return

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(held, "it attacked")

    def struck(ev: Hit) -> None:
        if ev.target == me:
            c.world.effects.end(held, "it was hit")

    c.watch(AttackRolled, swung, until=When.ENCOUNTER, on=me, label=f"{c.ref} reveal atk")
    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=f"{c.ref} reveal hit")


def _has_opening(world: World, eid: int) -> bool:
    """"Requires combat advantage" -- against *some* enemy, the way the
    level-07 `_has_an_opening` asked it, written again here because that one
    is not exported."""
    from combat_engine.engine.query import enemies

    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


# ==========================================================================
# m2483
# ==========================================================================


@power(
    "m2483a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m2483a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m2483a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 3),
)
def m2483a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2483a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2483a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m2483a0", on=victim)
    c.use_power("m2483a1", on=victim)


_M2483_MISSED = "an enemy misses it with a melee attack"


def _missed_me_in_melee(world: World, me: int, ev: Miss) -> bool:
    return ev.target == me and by_melee(world, me, ev)


@power(
    "m2483a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M2483_MISSED,
    on=Trigger(Miss, _missed_me_in_melee, _M2483_MISSED),
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 4),
)
def m2483a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m2483a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m2483a4(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.spend_surge(on=victim)
            c.weakened(on=victim, until=When.SAVE_ENDS)
            c.ignore_resistance(dtype=DamageType.NECROTIC, on=victim, until=When.ENCOUNTER)
    else:
        c.hit(half=True)


@power(
    "m2483a5",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m2483a5(c: Cast) -> None:
    c.restore_use("m2483a4", on=c.me)
    c.use_power("m2483a4")


@power(
    "m2483a6",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
)
def m2483a6(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.dazed(on=victim, until=When.EONT)
        c.penalty("attack", 2, on=victim, until=When.SAVE_ENDS)


@power(
    "m2483a7",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m2483a7(c: Cast) -> None:
    """"Entirely within the area" is approximated as "in the zone at all" --
    the same broad reading every other zone row here takes, since nothing
    measures how much of a creature's own square a footprint covers."""
    me = c.me
    zone = c.zone(c.area(), blocks_sight=True, until=When.SUSTAIN, sustain=MINOR, label=c.ref)
    held: dict[int, Effect] = {}

    def arrive(who: int) -> None:
        if who == me or who in held:
            return
        eff = c.blinded(on=who, until=When.ENCOUNTER)
        if eff is not None:
            held[who] = eff

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            arrive(ev.actor)

    def left(ev: ZoneExited) -> None:
        if ev.zone != zone:
            return
        eff = held.pop(ev.actor, None)
        if eff is not None:
            c.world.effects.end(eff, "left the dark")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")
    for who in c.world.zones.occupants(zone):
        arrive(who)


@power(
    "m2483a8",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2483a8(c: Cast) -> None:
    _bonus_vs_advantage(c, "1d6")


@power(
    "m2483a9",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2483a9(c: Cast) -> None:
    moved = c.move(c.speed_of())
    if moved >= 3:
        _vanish_until_it_swings(c, When.EONT)


# ==========================================================================
# m2542
# ==========================================================================


@power(
    "m2542a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 3, dtype=DamageType.NECROTIC),
)
def m2542a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2542a1",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    no_provoke=True,
    keywords=[Keyword.FEAR, Keyword.GAZE, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m2542a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m2542a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_has_opening,
    requires_text="it must have combat advantage",
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m2542a2(c: Cast) -> None:
    """Sustain pays out 5, or 10 against an immobilized target -- "a target
    he hit during his last turn" narrows *which* target the sustain can
    pick, which this plays the simpler way: whoever is still standing where
    the hold landed."""
    _recharge_when_using(c, "m2542a3")
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.ongoing(5, on=victim)
    held = c.dazed(on=victim, until=When.EONT)

    def sustain_more() -> None:
        amount = 10 if c.is_(Condition.IMMOBILIZED, on=victim) else 5
        c.flat(amount, on=victim)

    if held is not None:
        c.on_sustain(held, sustain_more)


@power(
    "m2542a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2542a3(c: Cast) -> None:
    c.shift(2)
    c.hide()


# ==========================================================================
# m2616
# ==========================================================================


@power(
    "m2616a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 4, dtype=DamageType.ACID),
)
def m2616a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2616a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 5, dtype=DamageType.ACID),
)
def m2616a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m2616a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m2616a2(c: Cast) -> None:
    c.invisible(until=When.EONT)
    c.move(6)


@power(
    "m2616a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2616a3(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        if unseen_by(c.world, ev.target, me):
            c.flat(c.roll("1d10"), on=ev.target)
            c.dazed(on=ev.target, until=When.SAVE_ENDS)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3191
# ==========================================================================


@power(
    "m3191a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m3191a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.COLD, until=When.SAVE_ENDS)


@power(
    "m3191a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3191a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d8"), dtype=DamageType.COLD)
        c.vulnerable(5, DamageType.NECROTIC, until=When.SAVE_ENDS)


@power(
    "m3191a2",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m3191a2(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


# ==========================================================================
# m322
# ==========================================================================


@power(
    "m322a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m322a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m322a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=11),
)
def m322a1(c: Cast) -> None:
    """"Save ends both" is approximated as two independent save-ends holds:
    nothing bundles a condition and an invisible-to relation under one roll
    the way `c.condition(..., ongoing=)` bundles a burn."""
    victim = c.target
    if c.strike():
        c.teleport(5, who=victim)
        c.dazed(on=victim, until=When.SAVE_ENDS)
        c.invisible(to=victim, on=c.me, until=When.SAVE_ENDS)


@power(
    "m322a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m322a2(c: Cast) -> None:
    """"Raising the slain creature (using the x0_27 ritual) does not
    destroy the spawned m322" names a ritual by its own ref and is not
    written: nothing here casts rituals on a board, so the exception has
    nowhere to apply."""
    me = c.me
    pending: list[Any] = []

    def slain(ev: Dropped) -> None:
        if ev.source != me or ev.actor is None or not c.is_kind("humanoid", on=ev.actor):
            return
        pos = c.world.get(ev.actor, Position)
        if pos is not None:
            pending.append(pos.square)

    def rise(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not pending:
            return
        for square in pending:
            c.summon("m322", at=square)
        pending.clear()

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label=f"{c.ref} mark")
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")


# ==========================================================================
# m3239
# ==========================================================================


@power(
    "m3239a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 11),
)
def m3239a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3239a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 11),
)
def m3239a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3239a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 11),
)
def m3239a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.shift(2)
        c.conceal(
            on=c.me, until=When.EONT, total=True,
            when=lambda ctx, v=victim: ctx.get("attacker") == v,
        )


@power(
    "m3239a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3239a3(c: Cast) -> None:
    which = c.choose(["m3239a0", "m3239a1", "m3239a2"], f"{c.ref}: weapon") or "m3239a0"
    foe = next(iter(c.enemies()), None)
    if foe is not None:
        c.use_power(which, on=foe)
        c.use_power(which, on=foe)


@power(
    "m3239a4",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m3239a4(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m3239a5",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3239a5(c: Cast) -> None:
    foe = min(c.enemies(), key=lambda f: c.distance(f), default=None)
    if foe is None:
        return
    c.quarry(on=foe, until=When.ENCOUNTER)
    me = c.me
    last_round: dict[str, int] = {"r": -1}

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None or not c.is_quarry(on=ev.target):
            return
        if last_round["r"] == c.world.round:
            return
        last_round["r"] = c.world.round
        c.flat(c.roll("1d6"), on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3460
# ==========================================================================


@power(
    "m3460a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 6),
)
def m3460a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3460a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_has_opening,
    requires_text="it must have combat advantage",
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 5),
)
def m3460a1(c: Cast) -> None:
    """"Requires a garrote" is equipment, not tracked. "Escape DC 16" has
    nowhere to go, the usual simplification across this project."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    held = c.grab(on=victim)
    if held is not None:
        c.on_sustain(held, lambda v=victim: c.flat(c.roll("1d10") + 5, on=v))


_M3460_SWING = "it is targeted by a melee or ranged attack"


def _targets_me_physically(world: World, me: int, ev: Any) -> bool:
    return ev.target == me and (by_melee(world, me, ev) or ev.__class__.__name__)


@power(
    "m3460a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3460_SWING,
    on=Trigger(AttackRolled, lambda w, m, ev: ev.target == m, _M3460_SWING),
)
def m3460a2(c: Cast) -> None:
    held = c.grabbing()
    attacker = _triggering_enemy(c)
    if not held or attacker in held:
        return
    c.redirect(to=held[0])


def _i_grabbed_the_dead(world: World, me: int, ev: Dropped) -> bool:
    from combat_engine.engine.escape import holders

    return me in holders(world, ev.actor)


@power(
    "m3460a3",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a creature it has grabbed drops to 0 or fewer hit points",
    on=Trigger(
        Dropped, _i_grabbed_the_dead, "a creature it has grabbed drops to 0 or fewer hit points"
    ),
)
def m3460a3(c: Cast) -> None:
    foe = next((f for f in c.enemies() if not c.adjacent(f)), None)
    if foe is not None:
        c.charge_at(foe)


@power(
    "m3460a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3460a4(c: Cast) -> None:
    _bonus_vs_advantage(c, "1d6")


@power(
    "m3460a5",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.treat_as_enemy_for_cover()",),
)
def m3460a5(c: Cast) -> None:
    """Refused in play: nothing recomputes cover with a grabbed creature's
    own allies treated as hostile to it. `c.cover_in` lays resistance in a
    zone by side, not a per-pair reclassification of who blocks whose line.
    Confirmed absent: `grep -n "def treat_as_enemy" cast.py` and
    `uv run scripts/vocab.py --brief | grep treat_as_enemy` are both
    empty."""


# ==========================================================================
# m4707
# ==========================================================================


@power(
    "m4707a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 2, dtype=DamageType.FIRE),
)
def m4707a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.is_hidden():
            c.flat(c.roll("2d6"), dtype=DamageType.FIRE, on=victim)
            c.ongoing(10, DamageType.FIRE, on=victim)


@power(
    "m4707a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4707a1(c: Cast) -> None:
    c.move(c.speed_of())
    for foe in c.enemies():
        if c.adjacent(foe):
            c.use_power("m4707a0", on=foe)


@power(
    "m4707a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m4707a2(c: Cast) -> None:
    c.invisible(until=When.EONT)
    c.shift(2)


@power(
    "m4707a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4707a3(c: Cast) -> None:
    me = c.me

    def paid(ev: Any) -> None:
        if getattr(ev, "source", None) == me:
            c.temp_hp(5, on=me)

    c.watch(Bloodied, paid, until=When.ENCOUNTER, on=me, label=f"{c.ref} bloody")
    c.watch(Dropped, paid, until=When.ENCOUNTER, on=me, label=f"{c.ref} drop")


@power(
    "m4707a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4707a4(c: Cast) -> None:
    me = c.me
    c.bonus("crit_range", 1, on=me, until=When.ENCOUNTER, when=lambda _ctx: c.is_hidden())


# ==========================================================================
# m5173
# ==========================================================================


@power(
    "m5173a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m5173a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(10, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for foe in c.enemies():
        c.penalty(
            WILL, 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: f in c.world.zones.occupants(ring),
        )


@power(
    "m5173a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5173a1(c: Cast) -> None:
    me = c.me

    def ends_far(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for foe in c.enemies():
            if distance_between(c.world, me, foe) >= 5:
                c.invisible(to=foe, on=me, until=When.EONT)

    c.watch(TurnEnd, ends_far, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5173a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 4),
)
def m5173a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m5173a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one creature that cannot see it",
        relation=Relation.HIDDEN_FROM,
    ),
    keywords=[Keyword.HEALING],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 6),
)
def m5173a3(c: Cast) -> None:
    """`relation=Relation.HIDDEN_FROM` is routed through `query.unseen_by`, not
    read off the stored triple, so the capped sight range and anything seeing
    through the hiding are both folded in -- which is what this body was calling
    `unseen_by` by hand to get. #401."""
    if c.strike():
        dealt = c.hit()
        c.heal(dealt // 2, on=c.me)


_M5173A4_TYPES = (
    DamageType.ACID, DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER,
)


def _hit_by_the_elements(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.dtype in _M5173A4_TYPES


_M5173A4_HIT = "it takes acid, cold, fire, lightning, or thunder damage"


@power(
    "m5173a4",
    level=8,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5173A4_HIT,
    on=Trigger(DamageApplied, _hit_by_the_elements, _M5173A4_HIT),
)
def m5173a4(c: Cast) -> None:
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is not None:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5363
# ==========================================================================


@power(
    "m5363a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m5363a0(c: Cast) -> None:
    me = c.me
    attacked_this_turn: dict[str, bool] = {"v": False}

    def go_veiled() -> None:
        held = c.invisible(until=When.EONT, on=me)
        phase = c.phasing(on=me, until=When.EONT)

        def reveal(ev: AttackRolled) -> None:
            if ev.attacker != me:
                return
            if held is not None:
                c.world.effects.end(held, "it attacked")
            if phase is not None:
                c.world.effects.end(phase, "it attacked")

        c.watch(AttackRolled, reveal, until=When.EONT, on=me, label=f"{c.ref} reveal")

    def mark_attack(ev: AttackRolled) -> None:
        if ev.attacker == me:
            attacked_this_turn["v"] = True

    def used_a4(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "m5363a4":
            go_veiled()

    def ends_quiet(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        if not attacked_this_turn["v"]:
            go_veiled()
        attacked_this_turn["v"] = False

    c.watch(PowerUsed, used_a4, until=When.ENCOUNTER, on=me, label=f"{c.ref} teleport")
    c.watch(AttackRolled, mark_attack, until=When.ENCOUNTER, on=me, label=f"{c.ref} mark")
    c.watch(TurnEnd, ends_quiet, until=When.ENCOUNTER, on=me, label=f"{c.ref} quiet")


@power(
    "m5363a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5363a1(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        if unseen_by(c.world, ev.target, me):
            c.flat(c.roll("2d6"), on=ev.target)
            c.slowed(on=ev.target, until=When.EONT)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5363a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 8),
)
def m5363a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5363a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 8),
)
def m5363a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5363a4",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5363a4(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m5364
# ==========================================================================


def _attacker_within(c: Cast, ctx: dict[str, Any], lo: int, hi: int) -> bool:
    attacker = ctx.get("attacker")
    if attacker is None:
        return False
    d = distance_between(c.world, c.me, attacker)
    return lo <= d <= hi


@power(
    "m5364a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5364a0(c: Cast) -> None:
    me = c.me
    c.conceal(on=me, until=When.ENCOUNTER, when=lambda ctx: _attacker_within(c, ctx, 2, 3))
    c.conceal(
        on=me, until=When.ENCOUNTER, total=True, when=lambda ctx: _attacker_within(c, ctx, 4, 999)
    )


@power(
    "m5364a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("", 8, kind=MINION),
)
def m5364a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5364a2",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    attack=Attack(vs=REF, printed=11),
    damage=Damage("", 8, kind=MINION),
)
def m5364a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5574
# ==========================================================================


@power(
    "m5574a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5574a0(c: Cast) -> None:
    def isolated(ctx: dict[str, Any]) -> bool:
        adj_enemies = [f for f in c.enemies() if c.adjacent(f)]
        if len(adj_enemies) != 1:
            return False
        foe = adj_enemies[0]
        return not any(c.adjacent_to(a, foe) for a in c.allies())

    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=isolated)


@power(
    "m5574a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 5),
)
def m5574a1(c: Cast) -> None:
    """"Escape DC 16" has nowhere to go, the usual simplification."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.grab(on=victim)


@power(
    "m5574a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 5),
    dropped=("Target.condition",),
)
def m5574a2(c: Cast) -> None:
    victim = _restricted_to(
        c, 1,
        lambda f: (
            c.is_(Condition.IMMOBILIZED, on=f)
            or c.is_(Condition.STUNNED, on=f)
            or c.is_(Condition.UNCONSCIOUS, on=f)
        ),
    )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.dazed(on=victim, until=When.SAVE_ENDS)
    c.temp_hp(10, on=c.me)


def _my_captive_tries(world: World, me: int, ev: Escaped) -> bool:
    return ev.holder == me


@power(
    "m5574a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="a creature it has grabbed attempts to escape",
    on=Trigger(Escaped, _my_captive_tries, "a creature it has grabbed attempts to escape"),
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m5574a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


# ==========================================================================
# m5581
# ==========================================================================


_M5581_TWISTED = "m5581a6 twisted"


@power(
    "m5581a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5581a0(c: Cast) -> None:
    c.regeneration(5, on=c.me, until=When.ENCOUNTER)


@power(
    "m5581a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m5581a1(c: Cast) -> None:
    victim = c.target
    twisted = any(eff.label == _M5581_TWISTED for eff in c.world.effects.of(c.me))
    if c.strike():
        c.hit()
        c.ongoing(5, on=victim)
        if twisted and victim is not None:
            c.grab(on=victim)


def _one_save_two_mods(c: Cast, victim: int, amount: int, dtype: DamageType) -> None:
    """"-2 to all defenses, and ongoing N damage (save ends both)" -- four
    mods and a burn, bundled under one roll the way a single mod-plus-burn
    already is elsewhere in this tree."""
    from combat_engine.engine import Mod

    which = [AC, REF, WILL, FORT]
    mods = [(victim, Mod(what=w, value=-2, kind="untyped", label=c.ref)) for w in which]
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=f"{c.ref} defences+burn",
        mods=mods, ongoing=(amount, dtype),
    )


@power(
    "m5581a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("4d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5581a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            _one_save_two_mods(c, victim, 10, DamageType.PSYCHIC)


@power(
    "m5581a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("spec.monster_ref()",),
)
def m5581a3(c: Cast) -> None:
    """Refused in play: the whole printed Effect is summoning "echoes of
    despair" and "echoes of madness," and nothing here has a ref for
    either -- only the printed names, which this row must not use. Same
    shape as `m3546a1`'s weapon Requirement, where the only handle on the
    thing is its printed word. "Recharge when all echoes are destroyed"
    waits on the same missing refs and is dropped with it; the die in the
    header still fires on its own."""


def _has_twisted(world: World, eid: int) -> bool:
    from combat_engine.engine.durations import Effects

    effects: Effects = world.effects
    return any(eff.label == _M5581_TWISTED for eff in effects.of(eid))


@power(
    "m5581a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_has_twisted,
    requires_text="it must have used m5581a6",
    keywords=[Keyword.HEALING],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 5),
)
def m5581a4(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    dealt = c.hit()
    c.dazed(on=victim, until=When.SAVE_ENDS)
    c.heal(dealt, on=c.me)


@power(
    "m5581a5",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5581a5(c: Cast) -> None:
    """`c.revives_unless` declares the fact for the AI policy and implements
    nothing itself; the body's own watch is what actually stands her back
    up, the shape `level_02/soldiers_sa.py`'s `m3533a3` settles."""
    c.revives_unless(on=c.me)
    me = c.me

    def rise(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        c.reanimate(on=me, hp=35, until=When.ENCOUNTER)

    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} rise")


@power(
    "m5581a6",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="the Emotional Backlash skill challenge ends",
    todo=("Trigger(SkillChallengeEnded)",),
)
def m5581a6(c: Cast) -> None:
    """Refused in play: there is no event for a skill challenge ending --
    that is a narrative structure outside the board this engine tracks, so
    nothing can declare the trigger. Confirmed absent:
    `grep -n "class SkillChallenge" engine/events.py` is empty, and
    `uv run scripts/vocab.py --brief` names no such trigger."""


# ==========================================================================
# m5618
# ==========================================================================


@power(
    "m5618a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5618a0(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("opportunity")))


@power(
    "m5618a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 9),
)
def m5618a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.flat(c.roll("1d6"))
        c.invisible(until=When.SONT)


_M5618_SWING = "an adjacent enemy hits or misses it with a melee attack"


def _adjacent_melee_swing_at_me(world: World, me: int, ev: Any) -> bool:
    attacker = getattr(ev, "attacker", None)
    if ev.target != me or attacker is None or not by_melee(world, me, ev):
        return False
    return distance_between(world, me, attacker) <= 1


@power(
    "m5618a2",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5618_SWING,
    on=(
        Trigger(Hit, _adjacent_melee_swing_at_me, _M5618_SWING),
        Trigger(Miss, _adjacent_melee_swing_at_me, _M5618_SWING),
    ),
)
def m5618a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    me = c.me
    c.gains_advantage(lambda ctx, f=foe: ctx.get("target") == f, until=When.EOT, on=me)
    c.use_power("m5618a1", on=foe)


# ==========================================================================
# m5632
# ==========================================================================


@power(
    "m5632a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5632a0(c: Cast) -> None:
    _cant_see_me_bonus(c, "4d6")


@power(
    "m5632a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5632a1(c: Cast) -> None:
    icy = lambda _ctx: c.terrain("ice") or c.terrain("snow")  # noqa: E731
    c.conceal(on=c.me, until=When.ENCOUNTER, when=icy)


@power(
    "m5632a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 3),
)
def m5632a2(c: Cast) -> None:
    if c.strike():
        c.hit()


def _icy_terrain(world: World, eid: int) -> bool:
    terrain = getattr(world, "terrain", None)
    return bool(terrain) and ("ice" in terrain or "snow" in terrain)


@power(
    "m5632a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_icy_terrain,
    requires_text="it must be in icy or snowy terrain, or near a white dragon",
)
def m5632a3(c: Cast) -> None:
    """"Or within 10 squares of a white dragon" is dropped silently: the
    kind word that tag would need to match is not one this project's
    `is_kind` vocabulary has been shown to use, and guessing its spelling
    risks a false negative forever rather than a true one."""
    _vanish_until_it_swings(c, When.EONT)


# ==========================================================================
# m5736
# ==========================================================================


@power(
    "m5736a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5),
)
def m5736a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5736a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m5736a1(c: Cast) -> None:
    _twice(c, "m5736a0")


def _invisible_now(world: World, eid: int) -> bool:
    from combat_engine.engine.query import hidden_from

    return bool(hidden_from(world, eid))


@power(
    "m5736a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    requires=_invisible_now,
    requires_text="it must be invisible as a result of m5736a3",
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("3d10", 16, dtype=DamageType.PSYCHIC),
)
def m5736a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5736a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m5736a3(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EOT)
    c.phasing(on=c.me, until=When.EOT)
    c.move(c.speed_of())
    _vanish_until_it_swings(c, When.ENCOUNTER)


def _recharge_on_other_melee_hit(c: Cast) -> None:
    me, ref = c.me, c.ref

    def hit_with_other(ev: Hit) -> None:
        if ev.attacker != me or ev.power == ref:
            return
        row = get(ev.power or "")
        if row is not None and row.reach.kind == "melee":
            c.restore_use(ref, on=me)

    c.watch(Hit, hit_with_other, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")


@power(
    "m5736a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one creature that can see it",
        relation=Relation.HIDDEN_FROM,
        without=True,
    ),
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
)
def m5736a4(c: Cast) -> None:
    """"One creature that **can** see it" -- the relation inverted by `without=`.
    Safe to invert now only because the field routes through `query.unseen_by`:
    inverting the bare triple would have refused an enemy that sees through the
    hiding and accepted one whose sight range cannot reach it. #401."""
    _recharge_on_other_melee_hit(c)
    if c.strike():
        c.push(1)
        c.immobilized(until=When.EONT)


# ==========================================================================
# m5920
# ==========================================================================


@power(
    "m5920a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 7),
    dropped=("c.deny_action()",),
)
def m5920a0(c: Cast) -> None:
    """"Loses its minor action on its next turn" has nowhere to go -- every
    verb in `cast.py` that touches an action grants one, and none takes a
    category away for a future turn. The extra move for m5920 himself,
    right now, is exact."""
    if c.strike():
        c.hit()
    c.extra_action(MOVE, on=c.me)


@power(
    "m5920a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d6", 4),
)
def m5920a1(c: Cast) -> None:
    _recharge_when_using(c, "m5920a0")
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)
    me = c.me
    held = c.condition(Condition.REMOVED, until=When.SONT, on=me)
    if held is not None:
        held.on_end.append(lambda: c.bonus("damage", 0, dice="2d6", on=me, until=When.EONT))


def _enemy_damaged_me(world: World, me: int, ev: DamageApplied) -> bool:
    if ev.target != me or ev.source is None:
        return False
    return team(world, ev.source) is not team(world, me)


_M5920_DAMAGED = "an enemy damages it"


@power(
    "m5920a2",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M5920_DAMAGED,
    on=Trigger(DamageApplied, _enemy_damaged_me, _M5920_DAMAGED),
)
def m5920a2(c: Cast) -> None:
    foe = getattr(c.trigger, "source", None)
    if foe is not None:
        c.condition(Condition.REMOVED, until=When.EONT, on=foe)
    _vanish_until_it_swings(c, When.EONT)


# ==========================================================================
# m5976
# ==========================================================================


@power(
    "m5976a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 7),
)
def m5976a0(c: Cast) -> None:
    was_hidden = c.is_hidden()
    if c.strike():
        c.hit()
        if was_hidden:
            c.flat(c.roll("2d8"))


@power(
    "m5976a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5976a1(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m5976a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit by an attack"),
)
def m5976a2(c: Cast) -> None:
    c.teleport(5)
    c.invisible(until=When.EONT)


# ==========================================================================
# m5996
# ==========================================================================


@power(
    "m5996a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m5996a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.flat(c.roll("2d8"))


@power(
    "m5996a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 9),
)
def m5996a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5996a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5996a2(c: Cast) -> None:
    me = c.me
    options = [f for f in c.enemies() if c.can_see(f)]
    foe = c.choose(options, f"{c.ref}: mark a foe") if options else None
    if foe is not None:
        c.gains_advantage(lambda ctx, f=foe: ctx.get("target") == f, until=When.EONT, on=me)
    c.conceal(
        on=me, until=When.SONT, total=True, when=lambda ctx, f=foe: ctx.get("attacker") != f
    )


# ==========================================================================
# m6022
# ==========================================================================


@power(
    "m6022a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6022a0(c: Cast) -> None:
    _bonus_vs_advantage(c, "2d6")


@power(
    "m6022a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 6),
)
def m6022a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6022a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=11),
)
def m6022a2(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        _invisible_to_until_it_fights(c, victim)


@power(
    "m6022a3",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION, Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6022a3(c: Cast) -> None:
    """Deliberately inert: a disguise with no combat reading, and the
    Insight check it names is never rolled on a board that already knows
    what stands on it."""


@power(
    "m6022a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
)
def m6022a4(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.gains_advantage(lambda ctx, v=victim: ctx.get("target") == v, until=When.EONT, on=c.me)


# ==========================================================================
# m6076
# ==========================================================================


@power(
    "m6076a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6076a0(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("opportunity")))


@power(
    "m6076a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 9),
)
def m6076a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.flat(c.roll("1d6"))
        c.invisible(until=When.SONT)


_M6076_SWING = "an adjacent enemy hits or misses it with a melee attack"


@power(
    "m6076a2",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6076_SWING,
    on=(
        Trigger(Hit, _adjacent_melee_swing_at_me, _M6076_SWING),
        Trigger(Miss, _adjacent_melee_swing_at_me, _M6076_SWING),
    ),
)
def m6076a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    me = c.me
    c.gains_advantage(lambda ctx, f=foe: ctx.get("target") == f, until=When.EOT, on=me)
    c.use_power("m6076a1", on=foe)


_M6076A3_HIT = "it hits with a basic attack"


def _hits_with_basic_m6076a1(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power == "m6076a1"


@power(
    "m6076a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6076A3_HIT,
    on=Trigger(Hit, _hits_with_basic_m6076a1, _M6076A3_HIT),
)
def m6076a3(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None or ev.power != "m6076a1":
            return
        c.ongoing(5, DamageType.PSYCHIC, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m6426
# ==========================================================================


@power(
    "m6426a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6426a0(c: Cast) -> None:
    _bonus_vs_advantage(c, "2d6")


@power(
    "m6426a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 6),
)
def m6426a1(c: Cast) -> None:
    was_hidden = c.is_hidden()
    if c.strike():
        c.hit()
        if was_hidden:
            c.flat(c.roll("1d6") + 6)


@power(
    "m6426a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 5),
)
def m6426a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "it fell unconscious")
        held = c.condition(Condition.UNCONSCIOUS, until=When.ENCOUNTER, on=victim)
        if held is None:
            return

        def wakes(ev: DamageApplied) -> None:
            if ev.target == victim:
                c.world.effects.end(held, "it took damage")

        c.watch(
            DamageApplied, wakes, until=When.ENCOUNTER, on=c.me, once=True, label=f"{c.ref} wake"
        )

    c.condition(Condition.WEAKENED, until=When.SAVE_ENDS, on=victim, escalate=worsen)


@power(
    "m6426a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m6426a3(c: Cast) -> None:
    _vanish_until_it_swings(c, When.SONT)


# ==========================================================================
# m6438
# ==========================================================================


@power(
    "m6438a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6438a0(c: Cast) -> None:
    _bonus_vs_advantage(c, "2d6")


@power(
    "m6438a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d4", 9),
)
def m6438a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6438a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=11),
)
def m6438a2(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        _invisible_to_until_it_fights(c, victim)


@power(
    "m6438a3",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6438a3(c: Cast) -> None:
    """Deliberately inert: she "retains her statistics in her new form," so
    the printed Effect is appearance only."""


@power(
    "m6438a4",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
)
def m6438a4(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.gains_advantage(lambda ctx, v=victim: ctx.get("target") == v, until=When.EONT, on=c.me)


# ==========================================================================
# m6650
# ==========================================================================


@power(
    "m6650a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6650a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    in_ring = lambda ctx: ctx.get("attacker") in c.world.zones.occupants(ring)  # noqa: E731
    c.conceal(on=me, until=When.ENCOUNTER, when=in_ring)


@power(
    "m6650a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m6650a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("2d6"), dtype=DamageType.COLD)


@power(
    "m6650a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 5),
)
def m6650a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.LIGHTNING)


@power(
    "m6650a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6650a3(c: Cast) -> None:
    which = c.choose(["bite_claw", "claw_claw"], f"{c.ref}: attack routine") or "bite_claw"
    foe = next(iter(c.enemies()), None)
    if foe is None:
        return
    if which == "bite_claw":
        c.use_power("m6650a1", on=foe)
        c.use_power("m6650a2", on=foe)
    else:
        c.use_power("m6650a2", on=foe)
        c.use_power("m6650a2", on=foe)


@power(
    "m6650a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("Usage.RECHARGE(when=)",),
)
def m6650a4(c: Cast) -> None:
    """The aura grows by 2, to a ceiling of 5.

    **An earlier version of this row said the radius could not be reached and
    marked it `todo`.** It can: `Zones.refresh` re-cuts `zone.squares` from
    `zone.aura` on every tick, so the field is live and not a record of what the
    aura was made at. Driven to be sure -- an aura 1 covers 16 squares, the same
    zone set to 3 covers 64, and back to 1 covers 16 again.
    `level_06/skirmishers_sa.py`'s `m6655a5` had already settled this shape and
    this row had not found it.

    What is still dropped is the *special recharge* -- "when it starts its turn
    and its aura is smaller than aura 5" is a condition where `recharge=` holds a
    die, which is #335's family. The plain die in the header fires meanwhile."""
    _resize_aura(c, "m6650a0", plus=2)


@power(
    "m6650a5",
    level=8,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("Usage.RECHARGE(when=)",),
)
def m6650a5(c: Cast) -> None:
    """The aura resets to 1 -- see `m6650a4` for why the radius is reachable.

    Approximated only in *which* enemy squares count as "entered": every enemy
    adjacent at the end of the move, since there is no step-by-step callback
    mid-move to catch each square as it is crossed. The printed conditional
    recharge is the dropped half, as it is on `m6650a4`."""
    me = c.me
    _resize_aura(c, "m6650a0", to=1)
    c.cure(Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED, on=me)
    c.insubstantial(on=me, until=When.EOT)
    c.move(c.speed_of())
    for foe in c.enemies():
        if c.adjacent(foe) and c.use_power("m6650a1", on=foe):
            c.slide(2, on=foe)
            c.prone(on=foe)


def _resize_aura(c: Cast, label: str, to: int | None = None, plus: int = 0,
                 cap: int = 5) -> bool:
    """Set a standing aura's radius, which is the only lever that reaches one
    already spawned.

    `Zones.refresh` re-cuts `zone.squares` from `zone.aura` every tick, so the
    field is live rather than a record of what it was created at --
    `level_06/skirmishers_sa.py`'s `m6655a5` settled this. There is no `c.` verb
    for it; `c.my_aura` finds the zone and the radius is a plain field.
    """
    zid = c.my_aura(label=label)
    if not zid:
        return False
    zone = dict(c.world.zones.all()).get(zid)
    if zone is None or zone.aura is None:
        return False
    zone.aura = to if to is not None else min(cap, zone.aura + plus)
    return True


_M6650_TYPES = (DamageType.LIGHTNING, DamageType.THUNDER)


def _struck_by_storm(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.dtype in _M6650_TYPES


_M6650A6_HIT = "it takes lightning or thunder damage"


@power(
    "m6650a6",
    level=8,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6650A6_HIT,
    on=Trigger(DamageApplied, _struck_by_storm, _M6650A6_HIT),
)
def m6650a6(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EONT)
    c.shift(c.speed_of())
