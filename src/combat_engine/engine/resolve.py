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

from dataclasses import dataclass, field
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
    concealment_of,
    cover_between,
    cover_waived,
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
    #: Set by a row that says an attack simply hits -- "a close or area
    #: attack targeting you automatically hits". The outcome is recomputed
    #: from the die after the interrupt window, so a listener setting `hit`
    #: had it thrown away, and rigging `total` would be faking.
    forced: bool = False
    #: Who the blow finally landed on. Usually the creature it was aimed at
    #: -- but an interrupt may move it, and then the body that rolled this
    #: has to be told, or it deals its damage to the one that was missed.
    target: int = 0
    #: "Treat the attack roll as odd", regardless of what the die shows.
    #: Set rather than rewriting `natural`, because the card says the
    #: *roll* counts as odd and not that the die landed differently --
    #: faking the die would change whether it hit and whether it crit,
    #: both of which are recomputed from `natural` after the interrupt
    #: window. Read through `parity`, never directly.
    treated: str = ""
    #: Every d20 face this attack has shown, in the order they were rolled.
    #: `natural` holds one, and anything that rolls again overwrites it --
    #: the avenger's two-roll benefit, `c.reroll_attack`, `keep=` below --
    #: so "you roll the same number on each die of the attack roll" and "if
    #: both of your attack rolls would hit" had nothing left to read.
    rolls: list[int] = field(default_factory=list)

    @property
    def parity(self) -> str:
        """`"odd"` or `"even"`, honouring anything that dictated it.

        Two rows read `natural % 2` by hand, which is right until
        something says otherwise -- and a whole build turns on a row
        that does.
        """
        if self.treated:
            return self.treated
        return "even" if self.natural % 2 == 0 else "odd"

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
    keep: str = "",
    hand: str = "main",
) -> AttackResult:
    """Roll one attack. `bonus` is everything the attacker brings to it;
    everything the *situation* brings is added here."""
    result = AttackResult()
    # Was this swing bought with an action point? Rides the same road
    # `opportunity` and `charge` do -- in the attack context and on all four
    # attack events -- because two printed rows are about exactly that
    # attack and neither could be written while nothing said so.
    bought = spent_action_point(world, attacker)

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
            "action_point": bought,
            # What shape the attack is, so "ranged attacks against this
            # target take +4" is a one-line gate rather than a registry
            # lookup duplicating `_is_ranged`.
            "ranged": _is_ranged(power, branch),
            "branch": branch,
            # Which hand swung. `Cast.w(hand="off")` already picked the
            # off-hand weapon's dice, and then threw the fact away -- so
            # a rider gated on an off-hand attack read a key the context
            # did not carry, which is silently false rather than wrong.
            "hand": hand,
        }

        situational = attack_penalty(world, attacker)
        situational += _mods(world, attacker, "attack", ctx)
        if ca:
            situational += 2
        if charge:
            situational += 1   # the printed charge bonus
        if not ignore_cover:
            # Cover and concealment do not add -- only the larger applies,
            # which is the printed rule and also stops a creature in a fog
            # bank behind a pillar being unhittable.
            blocked = max(
                int(cover_between(world, attacker, target,
                                  ranged=_is_ranged(power, branch))),
                int(concealment_of(world, target, ctx)),
            )
            # A standing waiver -- `c.ignore_cover` on the attacker or
            # `c.no_cover` on the target -- reads the same context the
            # penalty does, so "against enemies in the zone" is a gate
            # rather than an argument to one `c.strike`.
            if blocked <= cover_waived(world, attacker, target, ctx):
                blocked = 0
            situational -= blocked
        situational -= _long_range(world, attacker, target, power, branch, ctx)
        situational += _mark_penalty(world, attacker, among or (target,))

        d20 = world.rng.d20()
        natural = d20.total
        result.rolls.append(natural)
        # "Make the attack roll twice and use either result" is printed on
        # the attack line, so it is part of rolling and not something a body
        # can arrange afterwards: by the time `c.strike` has returned the
        # first roll has already decided hit or miss and paid out its riders.
        if keep:
            again = world.rng.d20().total
            result.rolls.append(again)
            natural = min(natural, again) if keep == "worst" else max(natural, again)
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
        rolled.action_point = bought
        # The context the modifiers were actually read with. `c.bonus(
        # once=True)` has to decide whether the bonus it is watching for
        # *applied*, and it was rebuilding a four-key context of its own --
        # so any `when=` gate reading `ranged`, `opportunity`, `charge` or
        # `branch` answered False there and the one-shot was never spent.
        # Forty-six gated one-shots in the tree were permanent bonuses.
        rolled.ctx = ctx
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
        result.hit = result.forced or result.critical or (
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
        landed.action_point = bought
        # Which defence was attacked. `AttackDeclared` and `AttackRolled`
        # carry it as a field; the outcome did not, so "an attack against
        # your AC or Reflex misses you" had nothing to read on the one event
        # that says it missed. A plain attribute, like `result` above, so it
        # stays off the wire and out of a replay fixture.
        landed.vs = vs

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

        def announce() -> Hit | Miss:
            ev = (
                Hit(attacker=attacker, target=target, power=power,
                    critical=result.critical)
                if result.hit
                else Miss(attacker=attacker, target=target, power=power)
            )
            ev.result = result
            ev.among = among or (target,)
            ev.branch = branch
            ev.opportunity = opportunity
            ev.charge = charge
            ev.action_point = bought
            ev.vs = vs
            return ev

        # Until the outcome stops changing. An *interrupt* answers before
        # the callback and is caught by `confirm`; a **free action or a
        # reaction** answers in the AFTER window, after the callback has
        # already passed -- so a reroll of that shape turned a miss into a
        # hit that was never announced, and every rider watching `Hit` was
        # skipped for a blow that landed.
        #
        # Twice is the practical bound: a second answer to the corrected
        # announcement is refused by the in-flight guard.
        for _ in range(3):
            was = result.hit
            world.bus.emit(landed, confirm)
            if not landed.cancelled and result.hit == was:
                break
            landed = announce()
        else:
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
    announced.action_point = bought
    declared = world.bus.emit(announced, roll)
    if declared.cancelled:
        result.cancelled = True
    return result


def spent_action_point(world: World, eid: int) -> bool:
    """Is this creature acting on an action point right now?

    True for the whole of the turn the point was spent on, because the
    extra action it buys is not distinguishable from the rest of the turn
    once it is in the budget -- the engine hands out an action, not a
    labelled one. Wider than the printed sentence by the other actions of
    that turn, and narrower than nothing at all, which is what the four
    rows keyed off it had before.
    """
    from .components import ActionPoints

    points = world.get(eid, ActionPoints)
    return (
        points is not None
        and points.spent_round == world.round
        and world.turn == eid
    )


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


def _long_range(
    world: World, attacker: int, target: int, power: str, branch: int, ctx: dict
) -> int:
    """-2 for shooting past a ranged weapon's normal range.

    Only a **weapon** prints two numbers. A power whose range line reads
    "Ranged 10" has one, and no penalty anywhere in it, so this asks the
    weapon in hand rather than the row. Beyond the long range the shot is
    simply impossible, and nothing here enforces that -- the board is
    smaller than any long range in the table, so the cap has never had a
    situation to be wrong in, and charging a penalty for a distance that
    cannot happen would be worse than leaving it.

    A row that waives the penalty offsets it: `"long_range"` is a modifier
    like any other, so "you take no penalty at long range" is a +2 gated
    however its card gates it.
    """
    from .components import Gear
    from .dsl import get
    from .query import distance_between
    from .types import Keyword

    p = get(power)
    if p is None or Keyword.WEAPON not in p.keywords:
        return 0
    if p.reach_of(branch).kind != "ranged":
        return 0
    gear = world.get(attacker, Gear)
    weapon = gear.ranged if gear is not None else None
    if weapon is None or weapon.ranged is None:
        return 0
    if distance_between(world, attacker, target) <= weapon.ranged[0]:
        return 0
    return max(0, 2 - _mods(world, attacker, "long_range", ctx))


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
    miss: bool = False,
    crit: bool = False,
) -> int:
    """Apply damage, honouring weakened, resistance, vulnerability and temp hp.

    Returns what actually came off hit points.
    """
    health = world.get(target, Health)
    if health is None or not alive(world, target):
        return 0

    # `opportunity` and `charge` too: a flat rider on either could not be
    # gated without them, since the ctx named only the first two. A gate on
    # a key the ctx does not carry is silently false, which is the worst
    # way for a rider to be wrong.
    #
    # **`dtype` for the same reason, and it was the commonest one left.**
    # "You gain a +1 bonus to the damage rolls of your fire powers" is a
    # whole family of feats and a long tail of item riders, and every one
    # of them had to gate on a key that was not here.
    #
    # It is read from the local rather than from the event below, and that
    # ordering is the point: a *weapon* that deals fire has to have said so
    # before this line, in `Cast.damage`'s dtype resolution. Set on a
    # `DamageRolled` listener instead, the type would change after the
    # bonus had been decided, and "my weapon deals fire" and "+1 with fire"
    # would disagree about the same blow.
    dmg_ctx = {
        "target": target,
        "power": detail,
        "opportunity": opportunity,
        "charge": charge,
        "dtype": dtype,
        "crit": crit,
    }
    if from_attack:
        # A bonus to damage is a thing powers grant constantly -- "+4 damage
        # against the target until the end of the encounter" -- and for a
        # while this line was missing, so every one of them was stored and
        # never read. Nothing failed; the damage was simply never larger.
        amount += _mods(world, source, "damage", dmg_ctx)
    # **What a critical hit adds beyond maximising the dice.** 734 of the
    # heroic magic items print "Critical: +1d6 damage per plus" and the
    # engine had no hook for any of them: `Cast.damage` maxed the dice and
    # that was the whole of it, and `Mods` was read for `crit_range` --
    # how often you crit -- and never for what one is worth.
    #
    # Its own `what` rather than a `damage` mod gated on `crit`, because a
    # crit rider is rolled (`Mod.roll` already carries "+1d6") and because
    # the two stack differently: every item you hold adds its own.
    if crit:
        amount += _mods(world, source, "crit_damage", dmg_ctx)
    if from_attack and deals_half(world, source):
        amount = amount // 2

    announce = DamageRolled(
        source=source, target=target, amount=amount, dtype=dtype, detail=detail
    )
    # The context these mods were read with, for the same reason the attack
    # roll carries its own: `c.bonus(once=True)` decides whether the bonus
    # it is watching applied, and it was rebuilding a two-key context here.
    announce.ctx = dmg_ctx
    rolled = world.bus.emit(announce)
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
    if defences is not None:
        # Untyped damage is included. `c.resist(5)` with no type writes an
        # entry for every member *including* untyped, and this used to skip
        # the whole block for untyped -- so "resist 5 to all damage" was
        # read for fire and ignored for a sword, which is most of the
        # damage in a fight. The entry existed and was never consulted,
        # which reads exactly like a working defence.
        if dtype in defences.immune:
            amount = 0
        else:
            amount += defences.vulnerable.get(dtype, 0)
            amount = max(0, amount - defences.resist.get(dtype, 0))

    # Resistance that only applies to some of the damage that comes in --
    # "but only when the damage is from ranged or area attacks". `Defences`
    # holds a flat number per type and has nowhere to put a condition, so a
    # gated resistance written there would have shrugged off everything and
    # been strictly stronger than the printed line. `c.resist(when=...)`
    # lays a modifier instead and this is the only thing that reads it.
    if amount and dtype not in (getattr(world.get(target, Defences), "immune", ())):
        gated = _mods(
            world, target, "resist",
            {
                "source": source,
                "power": detail,
                "dtype": dtype.value,
                "opportunity": opportunity,
                "charge": charge,
            },
        ) + _mods(
            world, target, f"resist {dtype.value}",
            {
                "source": source,
                "power": detail,
                "opportunity": opportunity,
                "charge": charge,
            },
        )
        amount = max(0, amount - gated)

    # "The creature takes no damage from an attack that misses" -- the
    # minion clause, printed on anything standing at one hit point. Nothing
    # in the damage context could say whether the blow landed, so `miss` is
    # handed in; only a miss pays for the lookup.
    if miss and amount and _mods(world, target, "no_miss_damage", {"power": detail}):
        amount = 0

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
    _check_down(world, target, health, source)
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


def _check_down(world: World, eid: int, health: Health, source: int | None = None) -> None:
    from .query import is_

    if health.hp > 0:
        return
    # Announced whichever way it went. `Dropped` used to mean only "dying,
    # not dead", so it never fired for a minion -- whose `dying_at` is 0 --
    # nor for any blow that overshot, which in play is most kills. The
    # printed sentence every row using it carries is "drops to 0 hit points
    # **or fewer**", and those rows were missing almost every death.
    world.bus.emit(Dropped(actor=eid, dead=health.hp <= health.dying_at, source=source))
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
