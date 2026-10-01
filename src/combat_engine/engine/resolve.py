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

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .ammunition import nock
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


def situational_attack(
    world: World,
    attacker: int,
    target: int,
    power: str,
    ctx: dict[str, Any],
    *,
    ca: bool = False,
    charge: bool = False,
    ignore_cover: bool = False,
    branch: int = 0,
    among: tuple[int, ...] = (),
) -> int:
    """Everything the *situation* adds to an attack roll, and nothing the
    attacker brings to it.

    Extracted so the closed-form model in `expect.py` reads it out of the kernel
    rather than keeping its own copy. It had its own copy by omission -- it
    applied `_mods` alone -- so it priced away **combat advantage's +2**, cover,
    concealment, the prone penalty, long range and a mark. Measured on one rogue
    row with advantage: 12.70 against a simulated 15.24, and the whole of that
    gap was this. Two implementations of one rule is how they drift.
    """
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
    return situational


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
    granted_by: int = -1,
    granted_via: str = "",
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
    # One piece of magic ammunition, drawn and spent as the shot is
    # declared. Rides the same road `opportunity` and `charge` do -- in
    # the attack context and on all four attack events -- because "an
    # attack using this ammunition" is about *this* shot and there was
    # nothing on the wire that said which one.
    drawn = nock(world, attacker, power, branch)

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
            # Who handed this swing over, and through which row. A bonus
            # to "the melee basic attack granted by your Combat
            # Challenge" is a gate on these two and nothing else, and
            # the keys were simply absent -- silently false, which is
            # what an inert feat looks like.
            "granted_by": granted_by,
            "granted_via": granted_via,
            "action_point": bought,
            # What shape the attack is, so "ranged attacks against this
            # target take +4" is a one-line gate rather than a registry
            # lookup duplicating `_is_ranged`.
            "ranged": _is_ranged(power, branch),
            "branch": branch,
            # Which magic ammunition this shot came from, empty for every
            # attack that is not one. In the context as well as on the
            # events so a standing modifier can be gated on it.
            "ammo": drawn,
            # Which hand swung. `Cast.w(hand="off")` already picked the
            # off-hand weapon's dice, and then threw the fact away -- so
            # a rider gated on an off-hand attack read a key the context
            # did not carry, which is silently false rather than wrong.
            "hand": hand,
            # **Everyone this attack is aimed at**, not just the one being
            # rolled against. "Attacks that do not include you as a target" is
            # a printed clause -- the mark penalty a few hundred lines down
            # implements exactly it, and correctly, by testing the whole target
            # set -- but a gated modifier could only see `target` and so could
            # not ask the same question. A rider that sharpens a mark had
            # nothing to gate on and read as unwritable.
            "among": tuple(among),
        }

        situational = situational_attack(
            world, attacker, target, power, ctx,
            ca=ca, charge=charge, ignore_cover=ignore_cover,
            branch=branch, among=among,
        )

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
        # **A high roll is not enough on its own.** "If you land a natural 20,
        # *and* the total of your attack roll is high enough to hit the
        # target's defence, it's a critical hit" -- so the die opens the door
        # and the total still has to walk through it. Without the second half
        # a 20 that fell fourteen short of an AC was dealing maximum damage,
        # and against anything far above its level a creature was critting on
        # every 20 no matter how hopeless the swing.
        #
        # The **hit** is a separate question and is unchanged: a 20 hits.
        result.critical = natural >= floor and total >= against
        result.hit = natural >= floor or (natural != 1 and total >= against)

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
        rolled.granted_by = granted_by
        rolled.granted_via = granted_via
        rolled.action_point = bought
        rolled.ammo = drawn
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
        # See the window above: the natural opens the door, the total has to
        # reach the defence. `forced` hits without rolling well and so is not
        # a critical either.
        result.critical = result.natural >= floor and result.total >= against
        result.hit = result.forced or result.natural >= floor or (
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
        landed.granted_by = granted_by
        landed.granted_via = granted_via
        landed.action_point = bought
        landed.ammo = drawn
        # Which defence was attacked. `AttackDeclared` and `AttackRolled`
        # carry it as a field; the outcome did not, so "an attack against
        # your AC or Reflex misses you" had nothing to read on the one event
        # that says it missed. A plain attribute, like `result` above, so it
        # stays off the wire and out of a replay fixture.
        landed.vs = vs
        # Which hand swung. Already in the attack context and already
        # thrown away by the time anything could answer "when you hit with
        # an off-hand attack", which is the whole of a two-weapon feat's
        # printed trigger. Same plain attribute as `vs`.
        landed.hand = hand

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
            ev.granted_by = granted_by
            ev.granted_via = granted_via
            ev.action_point = bought
            ev.ammo = drawn
            ev.vs = vs
            ev.hand = hand
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
    announced.granted_by = granted_by
    announced.granted_via = granted_via
    announced.action_point = bought
    announced.ammo = drawn
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

    The threshold is the **stretched** normal range, asked of the same
    `"range"` modifier `dsl._stretched` asks when it decides what may be
    aimed at, and with `"kind"` in the context because that is the key
    the targeting passes and a gate on a key its context lacks is
    silently false. Read raw, a line lengthening both a weapon's ranges
    moved the reach and left the -2 where it was, so every extra square
    it bought was targetable and penalised.
    """
    from .components import Gear
    from .dsl import _stretched, get
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
    normal = weapon.ranged[0] + _stretched(
        world, attacker, "ranged", {**ctx, "power": power, "kind": "ranged"}
    )
    if distance_between(world, attacker, target) <= normal:
        return 0
    return max(0, 2 - _mods(world, attacker, "long_range", ctx))


def _mods(world: World, eid: int, what: str, ctx: dict) -> int:
    from .components import Mods

    mods = world.get(eid, Mods)
    return mods.total(what, ctx) if mods else 0


#: "Your attacks ignore all resistances", with no number printed on the
#: card. Stored as a number because `Mods` holds numbers, and larger than
#: any resistance a heroic-tier creature can have.
IGNORE_ALL = 999


def _split_mods(
    world: World, eid: int, what: str, ctx: dict
) -> dict[tuple[DamageType, ...], int]:
    from .components import Mods

    mods = world.get(eid, Mods)
    return mods.split(what, ctx) if mods else {}


def _add_mods(
    parts: list[tuple[tuple[DamageType, ...], int]],
    extra: dict[tuple[DamageType, ...], int],
) -> list[tuple[tuple[DamageType, ...], int]]:
    """Fold a `Mods.split` result into the blow.

    An untyped rider joins the power's own part, because it is whatever
    the power is. A typed one becomes a part of its own, merging with any
    earlier rider of exactly the same types.
    """
    if not extra:
        return parts
    out = list(parts)
    out[0] = (out[0][0], out[0][1] + extra.get((), 0))
    for types, value in extra.items():
        if not types or not value:
            continue
        for i, (had, seen) in enumerate(out[1:], start=1):
            if had == types:
                out[i] = (had, seen + value)
                break
        else:
            out.append((types, value))
    return out


def _rescale(
    parts: list[tuple[tuple[DamageType, ...], int]], total: int
) -> list[tuple[tuple[DamageType, ...], int]]:
    """Hold the typed split steady when something changes the total.

    Halving and "reduce the damage by 5" are written against one number
    and know nothing about parts, so the split is kept in proportion and
    the power's own part absorbs the rounding. Exact for the single-part
    case, which is every blow that has no typed rider.
    """
    was = sum(v for _, v in parts)
    if was == total:
        return parts
    if len(parts) == 1 or was <= 0:
        return [(parts[0][0], total), *((t, 0) for t, _ in parts[1:])]
    rest = [(t, v * total // was) for t, v in parts[1:]]
    return [(parts[0][0], total - sum(v for _, v in rest)), *rest]


def _ignored_resist(
    world: World, source: int, types: tuple[DamageType, ...], ctx: dict
) -> int:
    """How much of the target's resistance the attacker simply walks through.

    Read off the **attacker**, unlike every other term in `deal_damage`'s
    resistance arithmetic: "your attacks ignore the first 5 points of
    necrotic resistance" is a thing the character has, not a thing done to
    the creature in front of them.

    A rider of two types is walked through only as far as both are, which
    is the same `min` the resistance itself is read with.
    """
    specific = min(
        (_mods(world, source, f"ignore resist {t.value}", ctx) for t in types),
        default=0,
    )
    return _mods(world, source, "ignore resist", ctx) + specific


def _immunity_ignored(
    world: World, source: int, types: tuple[DamageType, ...], ctx: dict
) -> int | None:
    """`None` if the immunity stands, else the resistance it counts as instead.

    Two numbers rather than one flag because the cards print it both ways:
    "your attacks ignore poison immunity" is a zero, and "treat a creature
    immune to poison as if it had resist poison 20" is a twenty that the
    ignored points are then taken off.
    """
    on = _mods(world, source, "ignore immunity", ctx) or min(
        (_mods(world, source, f"ignore immunity {t.value}", ctx) for t in types),
        default=0,
    )
    if not on:
        return None
    return max(
        _mods(world, source, "immune as resist", ctx),
        max(
            (_mods(world, source, f"immune as resist {t.value}", ctx) for t in types),
            default=0,
        ),
    )


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
    granted_by: int = -1,
    granted_via: str = "",
    miss: bool = False,
    crit: bool = False,
    dtypes: Sequence[DamageType] = (),
) -> int:
    """Apply damage, honouring weakened, resistance, vulnerability and temp hp.

    `dtypes` is for a blow that is **several types at once** -- "1d8
    lightning and thunder damage" is one roll of two types, not two rolls.
    The printed rule is that such a blow is resisted only as far as the
    target resists *every* type in it, and is ignored only by an immunity
    covering all of them, which is exactly what the per-part arithmetic
    below already does for a typed rider. `dtype` stays the blow's primary
    type, which is what the events carry and what every existing reader
    asks about; leave `dtypes` empty for the ordinary one-type blow and
    nothing below changes by so much as a point.

    Returns what actually came off hit points.
    """
    health = world.get(target, Health)
    if health is None or not alive(world, target):
        return 0

    # Duplicates dropped rather than kept: "cold and cold" is cold, and a
    # repeated type would have `min(resist)` and `all(immune)` read the
    # same entry twice for no change and one more chance to be wrong.
    types: tuple[DamageType, ...] = tuple(dict.fromkeys(dtypes)) or (dtype,)
    dtype = types[0]

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
        # The provenance of a granted swing, the same two keys the attack
        # context carries. "+2 to the damage roll of the basic attack you
        # granted" is a damage-side rider and had nothing to gate on.
        "granted_by": granted_by,
        "granted_via": granted_via,
        "dtype": dtype,
        "crit": crit,
        # **Asked of the board, not carried from the roll.** "+2 damage
        # against a creature granting you combat advantage" is a whole
        # family of feats, and the key was simply absent -- so each of
        # them either dropped the clause or called
        # `has_combat_advantage` by hand from inside its own gate, which
        # is the same question asked in the same place with more code.
        #
        # The caveat is real and is the reason this is not simply the
        # attack context's `advantage`: a *one-shot* grant is spent by
        # the attack roll, so by damage time the board says no and this
        # key says no with it. That is wrong for exactly those grants
        # and right for every standing one. Threading the rolled value
        # down would fix it and means an argument on six call sites
        # plus `Cast.damage` knowing its own result, which it does not.
        "advantage": (
            has_combat_advantage(world, source, target) if from_attack else False
        ),
        # **Melee or ranged, which only the attack context had.** Two
        # rows gated a damage bonus on `ctx["ranged"]` and, because the
        # key was absent, `not ctx.get("ranged", False)` read as True --
        # so a rider printed for melee paid on every shot as well. That
        # is the failure mode that is *too generous* rather than inert,
        # and nothing but reading the card would have caught it.
        #
        # Read off the row's own range line. `branch` is not carried
        # this far, so a power printing two ranges answers for its
        # first -- wrong for the handful that do, and right for
        # everything else.
        "ranged": _is_ranged(detail),
        # **Every type the blow is**, for the handful that are more than
        # one. `dtype` above is the primary and answers for all the blows
        # it always did; a gate that means "is there any thunder in this"
        # asks here, because `ctx["dtype"] is DamageType.THUNDER` is
        # silently false for a lightning-and-thunder blow.
        "dtypes": types,
    }
    # **The blow is a list of typed parts, not one number.** `parts[0]` is
    # what the power itself rolled, of the power's own type; a rider that
    # names a type of its own -- "your attacks deal 2 extra fire damage" --
    # is its own part, because those two points meet the target's fire
    # resistance whether or not the sword does. Every part but the first
    # exists only because some row asked for one, so a blow with no typed
    # rider is a single part and comes out of the arithmetic below
    # bit-for-bit what it did before this existed.
    parts: list[tuple[tuple[DamageType, ...], int]] = [(types, amount)]
    if from_attack:
        # A bonus to damage is a thing powers grant constantly -- "+4 damage
        # against the target until the end of the encounter" -- and for a
        # while this line was missing, so every one of them was stored and
        # never read. Nothing failed; the damage was simply never larger.
        parts = _add_mods(parts, _split_mods(world, source, "damage", dmg_ctx))
        amount = sum(v for _, v in parts)
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
        parts = _add_mods(parts, _split_mods(world, source, "crit_damage", dmg_ctx))
        amount = sum(v for _, v in parts)
    if from_attack and deals_half(world, source):
        amount = amount // 2
        parts = _rescale(parts, amount)

    announce = DamageRolled(
        source=source, target=target, amount=amount, dtype=dtype, detail=detail,
        # Empty for a one-type blow, so a listener that retypes by setting
        # `dtype` alone -- which is every one of them in the tree -- keeps
        # meaning what it has always meant.
        dtypes=types if len(types) > 1 else (),
    )
    # The context these mods were read with, for the same reason the attack
    # roll carries its own: `c.bonus(once=True)` decides whether the bonus
    # it is watching applied, and it was rebuilding a two-key context here.
    announce.ctx = dmg_ctx
    rolled = world.bus.emit(announce)
    if rolled.cancelled:
        return 0
    amount = max(0, rolled.amount)
    parts = _rescale(parts, amount)
    # The type too. It is on the event and mutable, and every reader below
    # -- immunity, resistance, vulnerability, and the DamageApplied that is
    # announced -- used the local, so "its weapon attacks deal fire damage"
    # set the field and changed nothing.
    #
    # Two ways to say it and they mean different things. Setting `dtypes`
    # is "this blow is necrotic **and** poison" -- one part of two types,
    # which resistance reads as a unit. Setting `dtype` alone is the older
    # and commoner sentence, "this weapon deals fire **instead**", and it
    # overrides whatever the blow was, pair included.
    said = tuple(dict.fromkeys(rolled.dtypes))
    if said and said != types:
        new_types = said
    elif rolled.dtype != dtype:
        new_types = (rolled.dtype,)
    else:
        new_types = types
    if new_types != types:
        types = new_types
        dtype = types[0]
        rolled.dtype = dtype
        # Only the power's own part is retyped. A listener saying "this
        # attack deals cold" is speaking about the attack, not about the
        # fire rider a feat hung off it.
        parts = [(types, parts[0][1]), *parts[1:]]
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

    if takes_half(world, target) and not _mods(
        world, source, "ignore insubstantial", dmg_ctx
    ):
        # Insubstantial halves everything, and does it before resistance so a
        # creature with both does not get the better of the two twice.
        #
        # "The power deals full damage to insubstantial creatures" is the
        # attacker's line and so it is read off the attacker, beside the
        # resistance it is printed next to on most of the cards that have
        # either.
        amount = amount // 2
        parts = _rescale(parts, amount)

    # What the target's defences take off, summed across every step below
    # and announced on `DamageApplied`. `absorbed` is temporary hit points
    # and nothing else, and a row wanting "my resistance reduced this" was
    # reading it and getting False in every fight without temp hp.
    resisted = 0
    defences = world.get(target, Defences)
    if defences is not None:
        # Untyped damage is included. `c.resist(5)` with no type writes an
        # entry for every member *including* untyped, and this used to skip
        # the whole block for untyped -- so "resist 5 to all damage" was
        # read for fire and ignored for a sword, which is most of the
        # damage in a fight. The entry existed and was never consulted,
        # which reads exactly like a working defence.
        #
        # **Resistance and vulnerability are each spent once per blow**,
        # which is why the per-part figures are capped at the largest one
        # rather than summed. A creature with resist 5 to everything, hit
        # for 10 with a sword and 5 with a fire rider, shrugs off five
        # points and not ten: it has one resistance, not one per part.
        # Vulnerability is the printed version of the same rule -- only the
        # highest applies.
        live: list[list[int]] = []
        worst_vuln = 0
        # Parts an immunity removed outright. Counted into `resisted` with
        # the rest: the printed rows asking about it say "if the damage is
        # reduced", and an immunity reduces it the hardest.
        ignored = 0
        # Not `types`: that is the blow's own, read again below, and the
        # loop variable used to be spelled the same.
        for part_types, value in parts:
            resist = min(defences.resist.get(t, 0) for t in part_types)
            if all(t in defences.immune for t in part_types):
                # Immunity is not resistance and is not capped with it: a
                # part the target is immune to is simply not there.
                # `c.ignore_resistance(immunity=...)` is the only thing
                # that reopens it, and the printed form of that line is
                # usually "treat immunity as resist 20" rather than a
                # blanket ignore.
                becomes = _immunity_ignored(world, source, part_types, dmg_ctx)
                if becomes is None:
                    ignored += value
                    continue
                resist = max(resist, becomes)
            resist = max(
                0, resist - _ignored_resist(world, source, part_types, dmg_ctx)
            )
            worst_vuln = max(
                worst_vuln, max(defences.vulnerable.get(t, 0) for t in part_types)
            )
            live.append([value, resist])
        resisted += ignored
        if not live:
            amount = 0
        else:
            # Vulnerability goes on before resistance comes off, which is
            # the printed order, and it goes on the power's own part so
            # that a single-part blow -- every blow in the tree that has
            # no typed rider -- lands on exactly the arithmetic this did
            # before parts existed.
            live[0][0] += worst_vuln
            shrugged = min(
                sum(min(v, r) for v, r in live), max(r for _, r in live)
            )
            amount = max(0, sum(v for v, _ in live) - shrugged)
            resisted += shrugged

    # Resistance that only applies to some of the damage that comes in --
    # "but only when the damage is from ranged or area attacks". `Defences`
    # holds a flat number per type and has nowhere to put a condition, so a
    # gated resistance written there would have shrugged off everything and
    # been strictly stronger than the printed line. `c.resist(when=...)`
    # lays a modifier instead and this is the only thing that reads it.
    immune_to_all = all(
        t in getattr(world.get(target, Defences), "immune", ()) for t in types
    )
    if amount and not immune_to_all:
        gated = _mods(
            world, target, "resist",
            {
                "source": source,
                "power": detail,
                "dtype": dtype.value,
                "dtypes": types,
                "opportunity": opportunity,
                "charge": charge,
            },
        ) + min(
            # **The smallest of the per-type resistances, not their sum.**
            # A blow that is lightning *and* thunder is shrugged off only
            # as far as the target resists both, so a gated "resist 10
            # lightning" and nothing against thunder stops none of it.
            # One type in `types` is every blow in the tree that is not a
            # pair, and `min` over one is that number.
            _mods(
                world, target, f"resist {t.value}",
                {
                    "source": source,
                    "power": detail,
                    "opportunity": opportunity,
                    "charge": charge,
                },
            )
            for t in types
        )
        left = max(
            0, amount - max(0, gated - _ignored_resist(world, source, types, dmg_ctx))
        )
        resisted += amount - left
        amount = left

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
            dtypes=types if len(types) > 1 else (),
            resisted=resisted,
        )
    )
    if not was_bloodied and health.bloodied and health.hp > 0:
        world.bus.emit(Bloodied(actor=target, source=source))
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
