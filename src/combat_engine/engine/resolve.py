"""Attack rolls, damage, healing, and dropping.

Two deliberate seams for triggered effects to reach into:

* `AttackDeclared` is emitted **before** the die is rolled, so an immediate
  interrupt can cancel the attack or change its target. An interrupt that
  merely stuns the attacker does not cancel anything by itself, so the roll
  re-checks that the attacker can still act -- that is a real 4e case and it
  fails silently if you only honour explicit cancels.
* `DamageRolled` is emitted **before** the damage lands and carries a mutable
  `amount`, which is where "reduce the damage by 5" and "the attack deals no
  damage to you" get written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .components import Defences, Health
from .conditions import DROPPED
from .durations import When
from .events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Died,
    Dropped,
    Healed,
    Hit,
    Miss,
    TempHP,
)
from .query import (
    alive,
    attack_penalty,
    can_act,
    cover_between,
    deals_half,
    defence,
    has_combat_advantage,
)
from .types import Condition, DamageType, Defense, Relation

if TYPE_CHECKING:
    from .ecs import World


@dataclass
class AttackResult:
    hit: bool = False
    critical: bool = False
    natural: int = 0
    total: int = 0
    target_defence: int = 0
    advantage: bool = False
    cancelled: bool = False

    def __bool__(self) -> bool:
        return self.hit


def attack(
    world: World,
    attacker: int,
    target: int,
    bonus: int,
    vs: Defense,
    power: str = "",
    *,
    advantage: bool | None = None,
    ignore_cover: bool = False,
) -> AttackResult:
    """Roll one attack. `bonus` is everything the attacker brings to it;
    everything the *situation* brings is added here."""
    result = AttackResult()

    def roll(_: AttackDeclared) -> None:
        if not can_act(world, attacker) or not alive(world, target):
            result.cancelled = True
            return

        ca = has_combat_advantage(world, attacker, target) if advantage is None else advantage
        ctx = {"attacker": attacker, "target": target, "power": power, "advantage": ca}

        situational = attack_penalty(world, attacker)
        situational += _mods(world, attacker, "attack", ctx)
        if ca:
            situational += 2
        if not ignore_cover:
            situational -= int(cover_between(world, attacker, target))
        situational += _mark_penalty(world, attacker, target)

        d20 = world.rng.d20()
        natural = d20.total
        total = natural + bonus + situational
        against = defence(world, target, vs, ctx)

        result.natural = natural
        result.total = total
        result.target_defence = against
        result.advantage = ca
        result.critical = natural == 20
        result.hit = natural == 20 or (natural != 1 and total >= against)

        world.bus.emit(
            AttackRolled(
                attacker=attacker,
                target=target,
                power=power,
                vs=vs,
                natural=natural,
                bonus=bonus + situational,
                total=total,
                defence=against,
                advantage=ca,
            )
        )
        if result.hit:
            world.bus.emit(Hit(attacker=attacker, target=target, power=power,
                               critical=result.critical))
        else:
            world.bus.emit(Miss(attacker=attacker, target=target, power=power))

    declared = world.bus.emit(
        AttackDeclared(attacker=attacker, target=target, power=power, vs=vs), roll
    )
    if declared.cancelled:
        result.cancelled = True
    return result


def _mods(world: World, eid: int, what: str, ctx: dict) -> int:
    from .components import Mods

    mods = world.get(eid, Mods)
    return mods.total(what, ctx) if mods else 0


def _mark_penalty(world: World, attacker: int, target: int) -> int:
    """A mark costs you 2 when you attack anyone but the creature that marked you.

    The penalty is for leaving your marker out of the attack -- not for being
    marked, and not for attacking a marked creature.
    """
    markers = world.relations.sources(Relation.MARKED_BY, attacker)
    if markers and target not in markers:
        return -2
    return 0


# -- damage -----------------------------------------------------------------


def deal_damage(
    world: World,
    source: int,
    target: int,
    amount: int,
    dtype: DamageType = DamageType.UNTYPED,
    detail: str = "",
    *,
    from_attack: bool = True,
) -> int:
    """Apply damage, honouring weakened, resistance, vulnerability and temp hp.

    Returns what actually came off hit points.
    """
    health = world.get(target, Health)
    if health is None or not alive(world, target):
        return 0

    if from_attack and deals_half(world, source):
        amount = amount // 2

    rolled = world.bus.emit(
        DamageRolled(source=source, target=target, amount=amount, dtype=dtype, detail=detail)
    )
    if rolled.cancelled:
        return 0
    amount = max(0, rolled.amount)

    defences = world.get(target, Defences)
    if defences is not None and dtype is not DamageType.UNTYPED:
        if dtype in defences.immune:
            amount = 0
        else:
            amount += defences.vulnerable.get(dtype, 0)
            amount = max(0, amount - defences.resist.get(dtype, 0))

    absorbed = min(health.temp, amount)
    health.temp -= absorbed
    landed = amount - absorbed

    was_bloodied = health.bloodied
    health.hp -= landed
    world.bus.emit(
        DamageApplied(
            source=source,
            target=target,
            amount=landed,
            dtype=dtype,
            absorbed=absorbed,
            hp=health.hp,
        )
    )
    if not was_bloodied and health.bloodied and health.hp > 0:
        world.bus.emit(Bloodied(actor=target))
    _check_down(world, target, health)
    return landed


def heal(world: World, source: int, target: int, amount: int) -> int:
    health = world.get(target, Health)
    if health is None or amount <= 0:
        return 0
    if health.hp <= 0:
        health.hp = 0  # healing from below zero starts at zero, not at the deficit
        _revive(world, target)
    before = health.hp
    health.hp = min(health.max_hp, health.hp + amount)
    world.bus.emit(Healed(source=source, target=target, amount=health.hp - before, hp=health.hp))
    return health.hp - before


def temp_hp(world: World, source: int, target: int, amount: int) -> None:
    """Temporary hit points do not stack -- the larger pool wins."""
    health = world.get(target, Health)
    if health is None or amount <= health.temp:
        return
    health.temp = amount
    world.bus.emit(TempHP(source=source, target=target, amount=amount))


# -- going down -------------------------------------------------------------


def _check_down(world: World, eid: int, health: Health) -> None:
    from .query import is_

    if health.hp > 0:
        return
    if health.hp <= health.dying_at:
        _die(world, eid)
        return
    if not is_(world, eid, Condition.DYING):
        world.bus.emit(Dropped(actor=eid))
        world.effects.apply(
            eid, eid, When.ENCOUNTER, label="dropped", conditions=DROPPED
        )


def _revive(world: World, eid: int) -> None:
    """Healing a dying creature clears what dropping it imposed."""
    for eff in world.effects.of(eid):
        if eff.label == "dropped":
            world.effects.end(eff, "healed")
    health = world.get(eid, Health)
    if health is not None:
        health.failures = 0


def _die(world: World, eid: int) -> None:
    """Kill a creature. The body stays an entity; the initiative slot stays too.

    Anything this creature was imposing on somebody else that is measured in
    turns keeps running until its slot comes around -- see `Effects.bereave`
    and `Encounter.advance`. Only what nothing could ever end is cleared now.
    """
    world.bus.emit(Died(actor=eid))
    world.effects.bereave(eid, "died")
    for kind, source, target in list(world.relations._live):
        # Relations carried by a live effect expire with it. A bare one --
        # a grab, most often -- ends now, because a corpse holds nobody.
        if eid in (source, target) and not world.effects.carries(kind, source, target):
            world.relations.clear(kind, source, target, "died")
    world.grid.lift(eid)
