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
    SurgeSpent,
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
    takes_half,
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
    #: Who the blow finally landed on. Usually the creature it was aimed at
    #: -- but an interrupt may move it, and then the body that rolled this
    #: has to be told, or it deals its damage to the one that was missed.
    target: int = 0

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
    opportunity: bool = False,
    among: tuple[int, ...] = (),
    branch: int = 0,
    dying: bool = False,
    charge: bool = False,
) -> AttackResult:
    """Roll one attack. `bonus` is everything the attacker brings to it;
    everything the *situation* brings is added here."""
    result = AttackResult()

    def roll(declared: AttackDeclared) -> None:
        # Read back off the event, because an interrupt may have moved the
        # attack. The module docstring has promised since it was written
        # that "an immediate interrupt can cancel the attack or change its
        # target" -- and the closure captured the parameters instead, so
        # assigning `ev.target` did nothing at all and failed silently.
        # The defence too, not just who is swinging at whom. `vs` is on the
        # event and mutable and was read from the enclosing parameter both
        # times -- so a row printing "its attacks target Reflex instead of
        # AC" set the field, changed nothing, and logged nothing. Sixth of
        # this shape today; the module docstring warns about it directly.
        attacker, target = declared.attacker, declared.target
        vs = declared.vs
        result.target = target
        # `dying` is a death throe swinging on its way down. The killing
        # blow usually overshoots `dying_at` -- and always does for a minion
        # -- so the attacker is not alive by the time its own `Dropped` is
        # answered, and the whole burst declared and then cancelled.
        if (not dying and not can_act(world, attacker)) or not alive(world, target):
            result.cancelled = True
            return

        ca = has_combat_advantage(world, attacker, target) if advantage is None else advantage
        # `opportunity` is in the context because "+2 to AC against
        # opportunity attacks" cannot be written without it, and gating on
        # the power's ref instead catches a standard-action basic and misses
        # a creature whose opportunity attack is something else.
        ctx = {
            "attacker": attacker,
            "target": target,
            "power": power,
            "advantage": ca,
            "opportunity": opportunity,
            "charge": charge,
            # What shape the attack is, so "ranged attacks against this
            # target take +4" is a one-line gate rather than a registry
            # lookup duplicating `_is_ranged`.
            "ranged": _is_ranged(power, branch),
            "branch": branch,
        }

        situational = attack_penalty(world, attacker)
        situational += _mods(world, attacker, "attack", ctx)
        if ca:
            situational += 2
        if charge:
            situational += 1   # the printed charge bonus
        if not ignore_cover:
            situational -= int(
                cover_between(world, attacker, target, ranged=_is_ranged(power, branch))
            )
        situational += _mark_penalty(world, attacker, among or (target,))

        d20 = world.rng.d20()
        natural = d20.total
        total = natural + bonus + situational
        against = defence(world, target, vs, ctx)

        result.natural = natural
        result.total = total
        result.target_defence = against
        result.advantage = ca
        # Provisional, so an interrupt watching the roll can ask whether it
        # is about to be hit -- which is exactly when a shield gets raised.
        # A critical is not always a 20: "crits on a 17-20" is standard on
        # high-crit weapons and on solos, and the number was hard-coded in
        # both of the places it is decided.
        floor = 20 - _mods(world, attacker, "crit_range", ctx)
        result.critical = natural >= floor
        result.hit = result.critical or (natural != 1 and total >= against)

        rolled = AttackRolled(
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
        # The live `AttackResult` rides along as a plain attribute rather
        # than a field, so it never reaches the wire or a replay fixture.
        # It is what an interrupt that rerolls the attack has to reach --
        # without it `c.reroll_attack` had nothing to change and silently
        # did nothing at all.
        rolled.result = result
        # Everyone this one power use is aimed at, not just this
        # announcement. Rides as a plain attribute so it stays off the wire
        # and out of a replay fixture, like `result` beside it. Without it a
        # row triggering on being *left out* of an attack cannot tell a
        # burst that caught it from one that did not.
        rolled.among = among or (target,)
        # Which half of a two-branch row swung. `by_melee` reads the range
        # off the power, and a `MeleeOrRanged` row's range says "melee"
        # whichever branch was used -- so without this a ranged shot let a
        # creature react as though it had been swung at.
        rolled.branch = branch
        # Was this an opportunity attack? Several rows key off that and no
        # event said so -- the flag lived only in the roll's own context, so
        # a creature could not react to being hit by one.
        rolled.opportunity = opportunity
        rolled.charge = charge
        world.bus.emit(rolled)

        # The defence is read **again**, after the roll has been announced.
        # An immediate interrupt fires in that window, and the whole point
        # of the commonest one is to raise your defence and turn a hit into
        # a miss -- which it could not do while the comparison had already
        # been made. The number on the event is what it was when the die
        # landed; this is what it is when the blow arrives.
        against = defence(world, target, vs, ctx)
        result.target_defence = against
        # From the **result**, not from the local `natural`/`total`. A
        # listener in the window above may have changed the die -- that is
        # the whole of what `c.reroll_attack` does -- and recomputing from
        # the locals threw the new number away and judged the old one. Every
        # reroll row in the tree was inert.
        floor = 20 - _mods(world, attacker, "crit_range", ctx)
        result.critical = result.natural >= floor
        result.hit = result.critical or (
            result.natural != 1 and result.total >= against
        )

        # The `Hit`/`Miss` carries it too, so a row can answer "when it is
        # hit by an opportunity attack".
        landed = (
            Hit(attacker=attacker, target=target, power=power, critical=result.critical)
            if result.hit
            else Miss(attacker=attacker, target=target, power=power)
        )
        landed.result = result
        landed.among = among or (target,)
        landed.branch = branch
        landed.opportunity = opportunity
        landed.charge = charge

        # An immediate interrupt answering a hit may undo it -- a reroll on
        # "when you are hit" is the printed shape, and by the rules the hit
        # then never happened. `result.hit` was flipped and nothing looked
        # again: the `Hit` stayed in the log, no `Miss` was ever emitted,
        # and every rider hung on `Hit` had already paid out for a blow that
        # ended as a miss. Dozens of rows in the tree watch `Hit`.
        #
        # Checked in the resolve callback, which runs after the interrupts
        # and before the ordinary listeners -- so cancelling here stops the
        # riders as well as the announcement.
        def confirm(ev: Hit | Miss) -> None:
            if result.hit != isinstance(ev, Hit):
                ev.cancel("undone by an interrupt")

        world.bus.emit(landed, confirm)
        if landed.cancelled:
            landed = (
                Hit(attacker=attacker, target=target, power=power,
                    critical=result.critical)
                if result.hit
                else Miss(attacker=attacker, target=target, power=power)
            )
            landed.result = result
            landed.among = among or (target,)
            landed.branch = branch
            landed.opportunity = opportunity
            landed.charge = charge
            world.bus.emit(landed)

        # Attacking gives you away. Nothing broke hidden before, so a
        # creature that went unseen once stayed unseen for the rest of the
        # fight and drew combat advantage on every attack it ever made. A
        # row that keeps its concealment says so by hiding again -- which is
        # what the printed ones do, and it reads the same way.
        world.relations.clear_source(Relation.HIDDEN_FROM, attacker, "attacked")

    announced = AttackDeclared(attacker=attacker, target=target, power=power, vs=vs)
    announced.among = among or (target,)
    announced.branch = branch
    announced.opportunity = opportunity
    announced.charge = charge
    declared = world.bus.emit(announced, roll)
    if declared.cancelled:
        result.cancelled = True
    return result


def _is_ranged(ref: str, branch: int = 0) -> bool:
    """Is this row a ranged attack? Only those take cover from creatures.

    Read off the power's own range line rather than guessed, and False for a
    row nothing is declared for -- no cover is the safer wrong answer than
    a penalty nobody can explain. `branch` matters for a row printing two
    ranges: its melee half takes no cover from bodies and its ranged half
    does.
    """
    from .dsl import get

    p = get(ref)
    return p is not None and p.reach_of(branch).kind == "ranged"


def _mods(world: World, eid: int, what: str, ctx: dict) -> int:
    from .components import Mods

    mods = world.get(eid, Mods)
    return mods.total(what, ctx) if mods else 0


def _mark_penalty(world: World, attacker: int, among: tuple[int, ...]) -> int:
    """A mark costs you 2 when you attack anyone but the creature that marked you.

    The penalty is for leaving your marker out of **the attack** -- not for
    being marked, and not for attacking a marked creature. `among` is every
    target of this one power use, which is the whole point: a burst is
    announced once per target, so judging this per announcement charged the
    penalty on every other target's roll even when the marker was caught in
    the same blast. The docstring said the right rule for a long time and
    the code underneath it did not implement it.
    """
    markers = world.relations.sources(Relation.MARKED_BY, attacker)
    if markers and not set(markers) & set(among):
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
    opportunity: bool = False,
    charge: bool = False,
) -> int:
    """Apply damage, honouring weakened, resistance, vulnerability and temp hp.

    Returns what actually came off hit points.
    """
    health = world.get(target, Health)
    if health is None or not alive(world, target):
        return 0

    if from_attack:
        # A bonus to damage is a thing powers grant constantly -- "+4 damage
        # against the target until the end of the encounter" -- and for a
        # while this line was missing, so every one of them was stored and
        # never read. Nothing failed; the damage was simply never larger.
        amount += _mods(
            world, source, "damage",
            # `opportunity` and `charge` too: a flat rider on either could
            # not be gated without them, since the ctx named only the first
            # two. A gate on a key the ctx does not carry is silently false,
            # which is the worst way for a rider to be wrong.
            {
                "target": target,
                "power": detail,
                "opportunity": opportunity,
                "charge": charge,
            },
        )
    if from_attack and deals_half(world, source):
        amount = amount // 2

    rolled = world.bus.emit(
        DamageRolled(source=source, target=target, amount=amount, dtype=dtype, detail=detail)
    )
    if rolled.cancelled:
        return 0
    amount = max(0, rolled.amount)
    # The type too. It is on the event and mutable, and every reader below
    # -- immunity, resistance, vulnerability, and the DamageApplied that is
    # announced -- used the local, so "its weapon attacks deal fire damage"
    # set the field and changed nothing.
    dtype = rolled.dtype
    # Read back off the event, the way the attack reads its target back. A
    # listener may move the blow onto somebody else -- one creature stepping
    # in front of another -- and everything below this line used the local.
    #
    # `health` moves with it. It was bound before the emit, so the redirect
    # re-read `takes_half`, the defences and the announcement off the new
    # target while the hit points still came off the old one -- the wrong
    # creature was hurt, and `_check_down` was handed a mismatched pair.
    if rolled.target != target:
        target = rolled.target
        health = world.get(target, Health)
        if health is None or not alive(world, target):
            return 0

    if takes_half(world, target):
        # Insubstantial halves everything, and does it before resistance so a
        # creature with both does not get the better of the two twice.
        amount = amount // 2

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
            detail=detail,
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
    # Announced *before* the hit points go on, so "the target regains half
    # the normal hit points from healing effects" has a seam. It used to add
    # first and announce after, which left a row like that clawing the
    # surplus back off `Health` -- the total came out right and the number
    # in the log did not.
    offered = Healed(source=source, target=target, amount=amount, hp=health.hp)
    if world.bus.emit(offered).cancelled:
        return 0
    before = health.hp
    health.hp = min(health.max_hp, health.hp + max(0, offered.amount))
    offered.amount = health.hp - before
    offered.hp = health.hp
    return health.hp - before


def spend_surge(world: World, eid: int) -> bool:
    """Take one healing surge off a creature. False if it had none.

    The only place a surge is decremented. Four sites were each doing it by
    hand and none announced it, so "when a creature spends a healing surge"
    was a sentence the engine could not observe.
    """
    health = world.get(eid, Health)
    if health is None or health.surges <= 0:
        return False
    health.surges -= 1
    world.bus.emit(SurgeSpent(actor=eid, left=health.surges))
    return True


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
    # Announced whichever way it went. `Dropped` used to mean only "dying,
    # not dead", so it never fired for a minion -- whose `dying_at` is 0 --
    # nor for any blow that overshot, which in play is most kills. The
    # printed sentence every row using it carries is "drops to 0 hit points
    # **or fewer**", and those rows were missing almost every death.
    world.bus.emit(Dropped(actor=eid, dead=health.hp <= health.dying_at))
    # Read hit points again. A row that answers its own `Dropped` by healing
    # itself -- the shape the `dying` flag exists for -- was healed inside
    # the emit and then knocked unconscious, prone and dying regardless,
    # because this decided all of that from the reading it took on the way
    # in. `heal`'s own revival cannot help: the "dropped" effect does not
    # exist yet, so there is nothing for it to clear.
    if health.hp > 0:
        return
    if health.hp <= health.dying_at:
        _die(world, eid)
        return
    if not is_(world, eid, Condition.DYING):
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
