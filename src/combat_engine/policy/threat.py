"""How dangerous a creature is, as one number the policy can weigh.

`docs/AI_DOCTRINE.md` defines it: "best case average damage over 3 rounds ...
divided by the party total hp pool". So the figure here is a **share of the other
side's health**, not a count of hit points. A share because a weight set against
it has to mean the same thing at level 1 and at level 10, and because two
creatures on one board are being compared.

Three rounds because that is roughly how long a creature survives being focused,
and "best case" because it is a measure of what the creature *could* do -- so it
is the three highest-scoring rows it knows, which lets one daily, an encounter
row and an at-will fall out on their own rather than being special-cased.

**Why this runs on a board of its own.** `expect.expected` lands real damage and
real conditions on whatever world it is handed -- every verb its `Ledger` does not
override runs for real. Measuring a creature on the board it is fighting on would
therefore wound it, and after #249 it wounds it harder, because the riders now
fire. There is no world clone in the engine and there cannot easily be one: bus
subscriptions hold closures over the world they were made against.

A *component*, though, is a plain dataclass of data. So `board` deep-copies every
component the live creature carries onto a fresh world and starts an encounter
there, so that the class features arm. Checked against the same measurement taken
live, on a level-5 party: 13.35 against 14.35 for the fighter, 9.85 against 9.85
for the cleric, 13.75 against 14.50 for the rogue. The remaining difference is
the point rather than an error -- the live figure is against whichever enemy
happened to be adjacent, and this one is against the baseline opponent, which is
what makes two creatures comparable at all.

**What the number is missing, so it is not read as more than it is.** It is a
floor, and knowably so:

* ongoing damage never appears -- it is applied by a duration on a later turn and
  not through a `Cast` at all;
* a row reading `c.trigger` cannot be evaluated standing still and scores zero;
* most of what a creature knows is not an attack, so only 2 of a level-5
  fighter's 33 known refs score above zero at all.

**And it is a damage figure, which is not the same as a threat.**
`notes/DOCTRINE.md` §5 measured a damage-derived ranking putting the fighter 2nd
of 8 and the rogue 7th -- damage does not track role, and a controller's worth is
not damage at all. This module is the damage axis and was asked for as such. It
is not the whole of what makes a creature dangerous.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from combat_engine.engine.components import Defenses, Health, Ident, Position, Powers, Side
from combat_engine.engine.durations import When
from combat_engine.engine.query import alive, creatures
from combat_engine.engine.types import (
    ActionType,
    Condition,
    DamageType,
    Defense,
    Team,
)

#: Chance to shrug a save-ends effect at the end of a turn. The save is
#: `roll.total + bonus >= 10` (`durations.py`), so eleven faces in twenty succeed.
#: Derived rather than typed so it tracks the rule if the rule ever moves.
SAVE_CHANCE = 11 / 20

#: How many of the affected creature's turns each duration covers.
#:
#: **This replaces `CONDITION_THREAT`, a table of zeros that nothing read.** A
#: single number per condition could not express the thing it was wanted for --
#: immobilising a creature already in your face is worth nothing and immobilising
#: one across the room is worth a round, and that is a fact about the board, not
#: about the condition. What a condition *does* now comes from `conditions.RULES`
#: via `from_rules`, and what it is worth is computed. Only the duration is a
#: lookup, because only the duration is genuinely a property of the effect.
#:
#: `SAVE_ENDS` is `1 / SAVE_CHANCE` = 1.82, which is Camille's 1.8x arrived at from
#: the rule rather than from the number.
#:
#: **`EOT` is asymmetric and is the entry to understand.** "End of this turn" ends
#: before the enemy ever acts, so it denies **nothing** -- but a defence debuff
#: lasting that long still helps every ally who acts later this round. So denial
#: and enablement read it differently, which is why `ENABLE_ROUNDS` exists below
#: rather than one table serving both and being wrong for half its callers.
ROUNDS_OF: dict[When, float] = {
    When.INSTANT: 0.0,
    When.EOT: 0.0,
    When.EONT: 1.0,
    When.SONT: 1.0,
    When.EOTNT: 1.0,
    When.SOTNT: 1.0,
    When.SAVE_ENDS: 1 / SAVE_CHANCE,
    When.ENCOUNTER: 3.0,
    When.STANCE: 3.0,
    When.SUSTAIN: 3.0,
}

#: The same durations, counted in *party* turns, for an effect that helps us
#: rather than hindering them. `EOT` is half a round: the allies who have not yet
#: acted this round get the benefit and the ones who already have do not.
ENABLE_ROUNDS: dict[When, float] = {**ROUNDS_OF, When.EOT: 0.5}


#: How many rows make up "best case over three rounds".
ROUNDS = 3

#: Keyed on the board and the creature, because a build does not change during a
#: fight. Spending a power does not change this figure either -- "best case" is
#: about what the creature can do, not what it has left.
_CACHE: dict[tuple[int, int, int], float] = {}


def clear() -> None:
    """Forget every cached figure. For an instrument measuring across fights.

    Worth calling between fights rather than trusting the keys: a `World` that
    has been collected frees its `id()` for the next one, so a stale entry could
    be read as the new board's.
    """
    _CACHE.clear()
    _ROWS.clear()
    _BOARDS.clear()
    _EFFECTS.clear()
    _PUSH.clear()
    _ROUND.clear()
    _DENIED.clear()


def _level_of(world: Any, eid: int) -> int:
    ident = world.get(eid, Ident)
    return getattr(ident, "level", 1) or 1


def board(world: Any, eid: int) -> tuple[Any, int, int] | None:
    """A fresh board holding a copy of `eid` and the baseline opponent.

    The baseline is the one `docs/AI_DOCTRINE.md` names and the monster corpus
    sits on -- AC 14 + level, other defences 11 + level, hp 24 + 8 x level.

    **The opponent is a second copy of the same creature**, with its powers
    stripped and every defence overwritten. That reads oddly and is deliberate:
    it gives a complete, valid creature to attack without this module reaching
    into `content/` for a template, which the component file forbids -- there are
    five `engine` -> `content` sites and a sixth is not to be added. What remains
    of the original on it is never consulted, because it does not act and its
    defences no longer depend on it.

    Its powers are stripped for a measured reason: left in place, one common
    creature's immediate interrupt makes an attacker reroll on being hit, which
    turned a third of landed hits back into misses and made the closed form look
    wrong by a third when it was the board that was wrong.
    """
    from combat_engine.engine.ecs import World
    from combat_engine.engine.events import Bus
    from combat_engine.engine.grid import Grid
    from combat_engine.engine.movement import place
    from combat_engine.engine.rng import Rng
    from combat_engine.engine.turns import Encounter

    level = _level_of(world, eid)
    try:
        parts = world.components_of(eid)
        w = World(Grid(16, 12), Rng(0), Bus())
        me = w.spawn(*[copy.deepcopy(c) for c in parts])
        foe = w.spawn(*[copy.deepcopy(c) for c in parts])
        mine, theirs = w.get(me, Side), w.get(foe, Side)
        if mine is not None:
            mine.team = Team.PC
        if theirs is not None:
            theirs.team = Team.ENEMY
        got = w.get(foe, Powers)
        if got is not None:
            got.known.clear()
        hp = w.get(foe, Health)
        if hp is not None:
            hp.max_hp = hp.hp = 24 + 8 * level
        d = w.get(foe, Defenses)
        if d is not None:
            d.values[Defense.AC] = level + 14
            for nad in (Defense.FORT, Defense.REF, Defense.WILL):
                d.values[nad] = level + 11
        # An encounter has to be running or nothing a class feature arms is
        # armed -- which is exactly where a rogue's extra damage lives, and the
        # whole of what #249 was about.
        Encounter(w).start()
        place(w, me, (4, 6))
        place(w, foe, (5, 6))
    except Exception:
        # A creature that cannot be rebuilt gets no threat rather than crashing
        # a turn. `raw` then reports zero, which reads as "harmless" when it
        # means "unknown" -- the caller cannot tell those apart, so the
        # instrument counts these separately rather than letting them hide.
        return None
    return w, me, foe


def unarmed(world: Any, eid: int) -> bool:
    """Has this creature nothing to attack with at all?

    A familiar carries `Companion`, `Stats` and no `Powers` whatever, so its
    threat is zero because it has no rows -- not because measuring it failed.
    Worth keeping apart: both come back as 0.0 and only one of them is a bug.
    """
    known = world.get(eid, Powers)
    return known is None or not known.known


def raw(world: Any, eid: int) -> float:
    """Best-case damage over `ROUNDS` rounds, in hit points.

    The sum of the `ROUNDS` highest-scoring rows the creature knows, each priced
    by `expect.expected` against the baseline opponent.
    """
    from combat_engine.engine.expect import expected

    if unarmed(world, eid):
        return 0.0
    made = board(world, eid)
    if made is None:
        return 0.0
    w, me, foe = made
    known = w.get(me, Powers)
    if known is None:
        return 0.0
    scored: list[float] = []
    for ref in known.known:
        scrub(w, me, foe)      # see `scrub`: without it each row inherits the last
        try:
            got = float(expected(w, me, ref, foe))
        except Exception:
            # A row that cannot be evaluated standing still -- one reading
            # `c.trigger` has no triggering event -- contributes nothing. The
            # module docstring says so; it is a floor, not a measurement.
            continue
        if got > 0:
            scored.append(got)
    scored.sort(reverse=True)
    return sum(scored[:ROUNDS])


#: Per (board, caster, row) expected damage against the baseline. Separate from
#: `_CACHE` because it is keyed on three things and filled one row at a time.
_ROWS: dict[tuple[int, int, str], float] = {}

#: One scratch board per caster, kept because building it is the expensive part
#: and every row of that caster is measured on the same one.
_BOARDS: dict[tuple[int, int], Any] = {}


#: Where `board` stands the two creatures. `scrub` puts them back.
HOME = ((4, 6), (5, 6))


def scrub(w: Any, me: int, foe: int) -> None:
    """Put a measuring board back the way `board` left it.

    **Without this every row is measured on the wreckage of the last one.**
    `expect.expected` restores hit points after each path and nothing else, so a
    row that marks the target, knocks it prone or lays a penalty on it leaves that
    standing -- and every row measured afterwards is priced against a weakened
    creature. The board is cached per caster, so this applied to all of them.

    Measured on a level-5 fighter's 37 rows, shared board against a fresh one:
    7 rows differed and **every difference was an overstatement**, the worst
    8.80 against 6.35, and its best row read 19.73 instead of 18.57. Order
    dependent too, since it depended on which row happened to be measured first.

    `Effects.forget` is the right tool rather than clearing `live` by hand: it
    runs each effect's `on_end` and drops its bus subscriptions, so nothing is
    left watching. Running `on_end` on a board kept for measuring is harmless.
    """
    from combat_engine.engine.movement import place

    w.effects.forget(me, "measured")
    w.effects.forget(foe, "measured")
    for who in (me, foe):
        health = w.get(who, Health)
        if health is not None:
            health.hp = health.max_hp
    # A push or a slide moves them, and the next row would then be measured at a
    # different range -- which silently changes whether it can reach at all.
    place(w, me, HOME[0])
    place(w, foe, HOME[1])


def row_damage(world: Any, eid: int, ref: str) -> float:
    """What one row of `eid`'s would deal to the baseline opponent, in hp.

    How hard the row hits, not whether it lands against any particular creature:
    `expected_vs` is what scales it to a real target. Against the baseline so that
    two rows, and two creatures, are comparable.
    """
    from combat_engine.engine.expect import expected

    key = (id(world), eid, ref)
    got = _ROWS.get(key)
    if got is not None:
        return got
    made = _BOARDS.get((id(world), eid))
    if made is None:
        made = board(world, eid)
        if made is None:
            _ROWS[key] = 0.0
            return 0.0
        _BOARDS[(id(world), eid)] = made
    w, me, foe = made
    scrub(w, me, foe)
    try:
        out = float(expected(w, me, ref, foe))
    except Exception:
        out = 0.0
    _ROWS[key] = out
    return out


#: Conditions a creature clears itself, whatever the printed duration says.
#:
#: Prone is modelled here as lasting to the end of the encounter, which is right --
#: you lie there until you stand -- and **wrong for scoring**, because standing is
#: a move action the creature takes on its very next turn. Read literally it would
#: price a knockdown at three rounds of denial. One round is what it actually buys.
SELF_CLEARING = {Condition.PRONE}


def _shortened(when: When, conds: Sequence[Condition]) -> When:
    """Cut a duration the target can end on its own turn down to one turn."""
    if ROUNDS_OF.get(when, 0.0) > 1.0 and any(c in SELF_CLEARING for c in conds):
        return When.EOTNT
    return when


@dataclass(frozen=True)
class Laid:
    """One effect a row puts on its target, as the scorer needs to read it."""

    when: When
    conditions: tuple[Condition, ...] = ()
    #: Modifiers the effect laid **on the target**, not on the caster.
    mods: tuple[Any, ...] = ()
    #: True when the effect makes the target grant combat advantage, from any of
    #: its conditions. Pulled out because it is the commonest enablement there is.
    grants_ca: bool = False
    #: Defence penalties the effect imposes, by `Defense`. The other half of
    #: enablement: this is the printed "-2 to AC" that scored nothing at all.
    defences: tuple[tuple[Any, int], ...] = ()


#: Per (board, caster, row), what that row lays. Cached because it costs a Ledger
#: run, and a row does the same thing every time it is used.
_EFFECTS: dict[tuple[int, int, str], tuple[Laid, ...]] = {}

#: How far the row shoves its target, from the same run. Filled by `row_effects`
#: rather than by a second Ledger pass, since the run that reads the conditions
#: has already moved the creature.
_PUSH: dict[tuple[int, int, str], int] = {}


def row_effects(world: Any, eid: int, ref: str) -> tuple[Laid, ...]:
    """What this row would put on its target: conditions, durations, modifiers.

    **No `Power` header declares any of this.** The header carries `attack`,
    `damage`, `reach`, `target`, `keywords` and `requires`, and nothing about
    conditions -- so `immobilized` is not readable off the card at any price. The
    row has to be run and the result observed, which is what the scratch board
    exists for: `Ledger` lets conditions land for real, so after one run the
    answer is sitting in `world.effects.of(target)`.

    Two things it cannot see, and both are in the figure rather than beside it:

    * **`Mod.when` is a closure** and its own docstring calls it
      "un-introspectable", so a modifier that applies only in some circumstance
      reads here as though it always does. Over-counts.
    * A condition applied on a **miss**, or down a branch the dictated hit did not
      take, is never observed. Under-counts.

    `Rules` is read for `grants_ca` and `defences` so that the enablement half --
    a creature made easier for the whole party to hit -- is available without the
    caller knowing which conditions imply it.
    """
    from combat_engine.engine.conditions import RULES
    from combat_engine.engine.expect import expected

    key = (id(world), eid, ref)
    got = _EFFECTS.get(key)
    if got is not None:
        return got
    made = _BOARDS.get((id(world), eid))
    if made is None:
        made = board(world, eid)
        if made is None:
            _EFFECTS[key] = ()
            return ()
        _BOARDS[(id(world), eid)] = made
    w, me, foe = made
    scrub(w, me, foe)
    try:
        expected(w, me, ref, foe)
    except Exception:
        _EFFECTS[key] = ()
        return ()
    # Where the row left it. `scrub` stood it on `HOME[1]`, so anything else is
    # forced movement -- which is worth knowing because shoving a creature that
    # cannot walk back is the cheapest way to take its round away. Camille's
    # suggestion, and `row_push` is the read.
    landed = w.get(foe, Position)
    _PUSH[key] = (max(abs(landed.square[0] - HOME[1][0]),
                      abs(landed.square[1] - HOME[1][1]))
                  if landed is not None else 0)
    out: dict[tuple, Laid] = {}
    for eff in w.effects.of(foe):
        conds = tuple(eff.conditions)
        mods = tuple(m for who, m in eff.mods if who == foe)
        ca = False
        defs: dict[Any, int] = {}
        for cond in conds:
            r = RULES.get(cond)
            if r is None:
                continue
            ca = ca or r.grants_ca
            for d, v in r.defences.items():
                defs[d] = defs.get(d, 0) + v
        for m in mods:
            what = getattr(m, "what", "")
            if isinstance(what, Defense):
                defs[what] = defs.get(what, 0) + m.value
        laid = Laid(when=_shortened(eff.when, conds), conditions=conds, mods=mods,
                    grants_ca=ca, defences=tuple(sorted(defs.items())))
        # **Deduplicated, because `expected` runs the body once per outcome path**
        # and each run lays the effect again. A row that rolls twice left four
        # identical immobilisations standing, and counting them would have priced
        # one condition as four.
        out.setdefault(
            (laid.when, laid.conditions, laid.defences, laid.grants_ca), laid)
    scrub(w, me, foe)
    _EFFECTS[key] = tuple(out.values())
    return _EFFECTS[key]


def row_push(world: Any, eid: int, ref: str) -> int:
    """How many squares this row shoves its target. Zero for most rows."""
    key = (id(world), eid, ref)
    if key not in _PUSH:
        row_effects(world, eid, ref)
    return _PUSH.get(key, 0)


def _baseline_hit(world: Any, eid: int, ref: str) -> float | None:
    """What this row's chance to hit the baseline opponent is.

    The denominator in `expected_vs`. Taken from the same scratch board the damage
    figure came from, so the two are consistent with each other.
    """
    from combat_engine.engine.dsl import get

    made = _BOARDS.get((id(world), eid))
    if made is None:
        made = board(world, eid)
        if made is None:
            return None
        _BOARDS[(id(world), eid)] = made
    w, me, foe = made
    p = get(ref)
    return p.hit_chance(w, me, foe) if p is not None else None



def row_types(ref: str) -> tuple[DamageType, ...]:
    """What damage types a row deals, for pricing a target's defences. #317.

    Two sources, because neither alone covers the corpus: `Damage.dtype` is set
    on all 1,351 rows that declare a damage header, and **1,947 rows carry the
    type as a keyword** -- a fire power is a fire power whether its header says so
    or its body passes `dtype=FIRE` to `c.damage`. The union is the honest answer
    and the keyword half is the bigger one.

    `(UNTYPED,)` when neither says anything, which is most weapon damage and is
    what `Defences` stores an untyped entry for.
    """
    from combat_engine.engine.dsl import get

    p = get(ref)
    if p is None:
        return (DamageType.UNTYPED,)
    found: set[DamageType] = set()
    if p.damage is not None and p.damage.dtype is not DamageType.UNTYPED:
        found.add(p.damage.dtype)
    named = {d.value: d for d in DamageType}
    for kw in p.keywords or ():
        hit = named.get(getattr(kw, "value", ""))
        if hit is not None and hit is not DamageType.UNTYPED:
            found.add(hit)
    return tuple(sorted(found, key=lambda d: d.value)) or (DamageType.UNTYPED,)


def after_defences(world: Any, target: int, types: tuple[DamageType, ...],
                   dmg: float) -> float:
    """`dmg` as the target would actually take it. #317.

    **The scorer consulted none of this.** `expected_vs` scaled by hit chance and
    stopped, so a 20-damage fire row was priced at 20 against a creature that
    resists 10 fire, at 20 against one that is *immune* to fire, and at 20 against
    one with vulnerable 5 where the truth is 25. 142 of 615 usable monsters carry a
    resistance, 120 an immunity and 45 a vulnerability.

    **A deliberate approximation of `resolve`'s arithmetic, not a copy of it.**
    That one splits a blow into parts, spends resistance once across them, reads
    `ignore resist` modifiers and can treat an immunity as a resistance. Copying it
    here would be a second implementation to keep in step, and `_in_area` already
    sets the precedent for a cheap geometric stand-in. What this does is the
    single-part case, which is the overwhelming majority:

    * immune to **all** of the row's types and the damage is gone -- the printed
      rule, and why `all` rather than `any`;
    * otherwise the resistance that applies is the **smallest** across the types,
      because a blow that is fire *and* radiant is only shrugged off by a creature
      that resists both;
    * vulnerability is the largest, and goes on before resistance comes off, which
      is `resolve`'s order.

    What it will get wrong: a multi-part blow with a typed rider, and an attacker
    carrying `ignore resist`. Both make this read low rather than high, which is
    the safer direction for a term that decides what to attack.
    """
    # **`Defences`, not `Defenses`.** Two components one letter apart:
    # `Defenses` holds AC, Fort, Ref and Will; `Defences` holds resist,
    # vulnerable and immune. Imported locally so the two spellings never sit
    # side by side in this file's import block, where picking the wrong one is
    # an `AttributeError` at best and a silently empty answer at worst.
    from combat_engine.engine.components import Defences

    if dmg <= 0:
        return 0.0
    d = world.get(target, Defences)
    if d is None:
        return dmg
    if types and all(t in d.immune for t in types):
        return 0.0
    resist = min((d.resist.get(t, 0) for t in types), default=0)
    vuln = max((d.vulnerable.get(t, 0) for t in types), default=0)
    return max(0.0, dmg + vuln - resist)


def effective_hp(world: Any, eid: int) -> int:
    """Hit points in front of the creature: current plus temporary. #316.

    **Not surges or a second wind**, which is Camille's call and the right one:
    those are day-long resources and this prices a single action. Folding them in
    would make a bloodied fighter standing beside a cleric a *worse* target than
    the same fighter alone, which inverts focus fire, and it would double-count
    against the attrition metrics that already track surges separately.

    **And not divided by the chance of being hit here, though that is part of the
    idea.** Camille's definition is `hit points / probability of being hit` -- a
    soldier is effectively tougher and should rarely be the first target -- and
    that factor is real but is applied **once, in `expected_vs`**, which scales a
    row's damage by its live hit chance against the target. Dividing here as well
    would square it:

        expected damage / effHP  ==  (dmg * p) / (hp / p)  ==  dmg * p^2 / hp

    Both orderings are the same arithmetic with `p` applied once, and
    `expected_vs` is where the hit chance is already known. Said out loud because
    the formula reads like it belongs here and adding it would look like a fix.

    The other half of Camille's point -- that a defender is attacked because it
    *makes* itself attacked, by marking or by making its allies harder to hit --
    is not priced at all: `CONDITION_THREAT` is zeros and a mark is worth nothing.
    That is #263 and is not this function's to solve.
    """
    health = world.get(eid, Health)
    if health is None:
        return 0
    return max(0, health.hp) + max(0, getattr(health, "temp", 0))


def capacity(world: Any, of: Team) -> float:
    """A side's threat-weighted durability: `sum(threat * effective hp)`. #316.

    Camille's formulation, and the denominator that makes a differential
    well-formed. `pool` is the same shape with the threat left out -- total hit
    points -- and stays, because several terms are about hit points rather than
    about capability.

    Why this rather than `pool`: removing ten hit points from the artillery and
    from the brute are the same fraction of a pool and not the same thing done to a
    side. Weighting each creature's durability by what it contributes says so.
    """
    total = 0.0
    for eid in creatures(world):
        side = world.get(eid, Side)
        if side is None or side.team is not of or not alive(world, eid):
            continue
        total += threat(world, eid) * effective_hp(world, eid)
    return total


def expected_vs(world: Any, eid: int, ref: str, target: int,
                *, attack: int = 0) -> float:
    """What one row would deal to a **real** target, in hit points.

    `row_damage` prices a row against the baseline, which is what makes two rows
    comparable and is not what the target in front of you is. Rescaling by the
    ratio of live to baseline hit chance gives the live figure without a second
    Ledger run, because expected damage is proportional to the chance of landing.

    `attack` shifts the attacker's roll, which is how a penalty is priced -- a
    point is a twentieth of the die. Clamped, because a hit chance does not go on
    falling past the automatic miss: a natural 1 always misses and a 20 always
    hits, so the reachable range is 1/20 to 19/20 and a linear shift outside it
    would invent damage or forgive it.

    A row with no attack line at all is damage that does not need to land, so it
    is returned unscaled rather than being scaled by a hit chance of `None`.
    """
    from combat_engine.engine.dsl import get

    dmg = row_damage(world, eid, ref)
    if dmg <= 0:
        return 0.0
    # **What the target would actually take**, which this did not ask. #317.
    dmg = after_defences(world, target, row_types(ref), dmg)
    if dmg <= 0:
        return 0.0
    p = get(ref)
    live = p.hit_chance(world, eid, target) if p is not None else None
    base = _baseline_hit(world, eid, ref)
    if live is None or base is None or base <= 0:
        return dmg
    if attack:
        live = min(0.95, max(0.05, live + attack / 20))
    return dmg * live / base


@dataclass(frozen=True)
class Pinned:
    """What something stops a creature doing, in the terms the scorer needs.

    Assembled by `from_rules` out of `conditions.Rules` and any `Mod` an effect
    laid, so that the worth of a condition is **derived from what it mechanically
    does** rather than from a number somebody typed next to its name. That is the
    whole reason `CONDITION_THREAT` is gone: a single figure per condition cannot
    say that immobilising a creature already in your face is worth nothing while
    immobilising one across the room is worth a round.
    """

    cannot_act: bool = False
    cannot_move: bool = False
    no_standard: bool = False
    speed_cap: int | None = None
    halve_speed: bool = False
    weakened: bool = False
    #: Penalty to the creature's own attack rolls, as a number of faces.
    attack: int = 0
    #: One action for the whole turn instead of a standard, a move and a minor.
    #:
    #: **Without this, dazing anything was worth exactly nothing.** `DAZED` is
    #: `grants_ca + one_action + no_reactions` and `DOMINATED` is the same three, so
    #: `from_rules` returned a bare `Pinned()` for both and `_denial`'s
    #: `if pin == Pinned()` guard dropped the row before measuring it. The
    #: `rounds-table` column read `0.00` on all sixteen monsters on the board.
    #:
    #: Priced as **it may move or attack, not both**, which is what one action
    #: buys: see `_speed_under`. That makes it worth a lot against a creature that
    #: has to close and nothing against one already in your face -- the same shape
    #: Camille signed off on for an immobilise, and for the same reason.
    #:
    #: **So a daze comes out equal to an immobilise, and that is a floor of the
    #: model rather than a bug.** A daze should be worth strictly more: the
    #: immobilised creature keeps its minor action and its opportunity attacks and
    #: the dazed one loses both. `per_round` is a `max` over single rows, not a
    #: simulation of a turn, so it cannot see a second action being taken away --
    #: from anybody, which is why no other condition is understated by it either.
    #: Putting a multiplier here to make up the difference would be exactly the
    #: hand-set constant #314 exists to remove. Pricing `no_reactions` is the real
    #: fix and it wants a term for conceded opportunity attacks.
    one_action: bool = False


def from_rules(conds: Sequence[Condition], mods: Sequence[Any] = ()) -> Pinned:
    """Fold conditions and modifiers into one `Pinned`.

    `conditions.RULES` is the authority on what each condition does -- it is what
    the kernel itself enforces, so a scorer reading it cannot disagree with play.
    A `Mod` whose `what` is `"attack"` is the printed attack debuff and is added on
    top, since a power may impose one without any named condition.
    """
    from combat_engine.engine.conditions import RULES

    out = Pinned()
    for cond in conds:
        r = RULES.get(cond)
        if r is None:
            continue
        cap = out.speed_cap
        if r.speed_cap is not None:
            cap = r.speed_cap if cap is None else min(cap, r.speed_cap)
        out = Pinned(
            cannot_act=out.cannot_act or r.cannot_act,
            cannot_move=out.cannot_move or r.cannot_move,
            no_standard=out.no_standard or r.no_standard,
            speed_cap=cap,
            halve_speed=out.halve_speed or r.halve_speed,
            weakened=out.weakened or r.weakened,
            attack=out.attack + r.attack,
            one_action=out.one_action or r.one_action,
        )
    extra = sum(m.value for m in mods if getattr(m, "what", "") == "attack")
    if extra:
        out = Pinned(**{**out.__dict__, "attack": out.attack + extra})
    return out


def _speed_under(world: Any, eid: int, pin: Pinned | None) -> int:
    """How far the creature may move, given what is on it."""
    from combat_engine.engine.components import Movement

    move = world.get(eid, Movement)
    speed = move.speed if move is not None else 6
    if pin is None:
        return speed
    if pin.cannot_move:
        return 0
    if pin.one_action:
        # **One action is spent either closing or attacking.** `per_round` asks what
        # the best *damage* this round is, and a turn spent walking deals none -- so
        # the honest reading of one action is "attack from where you stand", which
        # is zero squares of approach. Deliberately not a separate field in
        # `per_round`: the quantity being changed really is the reach, and
        # expressing it here keeps one answer to "how far can it get".
        return 0
    if pin.halve_speed:
        speed //= 2
    if pin.speed_cap is not None:
        speed = min(speed, pin.speed_cap)
    return speed


#: Per (board, round, creature, what is on it, whether reach is ignored). Keyed on
#: the round because this is a question about the board and the board moves; keyed
#: on the `Pinned` because the whole model asks it twice, once free and once held.
#:
#: **This is the difference between a usable scorer and an unusable one.** `denial`
#: asks for two of these per candidate target, and a turn scores a few hundred
#: candidate actions, so uncached it recomputed the same figure thousands of times:
#: one fight went from 13s under `LinearPolicy` to 25s, and an 80-seed comparison
#: from 25 minutes to about two hours.
_ROUND: dict[tuple[int, int, int, Pinned | None, bool, Any], float] = {}

#: Per (board, round, target, the effects asked about). Same reasoning.
_DENIED: dict[tuple[int, int, int, tuple], float] = {}


def per_round(world: Any, eid: int, pin: Pinned | None = None,
              *, anywhere: bool = False, where: Any = None) -> float:
    """The best damage this creature could do in one round, in hit points.

    **Against the best target it can reach after moving**, which is Camille's rule
    and the thing that makes a denial computable: a creature that cannot reach
    anybody has no round to lose, and one already in contact loses nothing by
    being held still.

    Reach is approximated as `distance <= speed + the row's own reach` rather than
    by walking `movement.reachable` for every candidate square. The exact answer is
    available and costs a Dijkstra per creature per turn, and a square of error
    does not change which target is the best one. Obstacles are the case it gets
    wrong: a creature penned behind a wall reads as able to reach.

    An area row is worth what it catches, so its figure is multiplied by how many
    enemies fall inside it -- that is a real part of how dangerous a creature is
    and the reason a controller is not scored like a brute.

    `anywhere` drops the reach test, answering "what does a round look like once it
    is standing where it wants to be". That is `potential`, the denominator, and it
    **must come from this same function**: measuring the denominator on the scratch
    board instead made it 8.8 against a live 30.8, so the ratio was nonsense and
    every partial denial -- weakened, prone, an attack penalty -- came out as zero.
    """
    if pin is not None and pin.cannot_act:
        return 0.0
    key = (id(world), getattr(world, "round", 0), eid, pin, anywhere, where)
    hit = _ROUND.get(key)
    if hit is not None:
        return hit
    got = _per_round(world, eid, pin, anywhere=anywhere, where=where)
    _ROUND[key] = got
    return got


def _per_round(world: Any, eid: int, pin: Pinned | None,
               *, anywhere: bool, where: Any = None) -> float:
    """`per_round` without the memo. Split so the cache has one entry point."""
    from combat_engine.engine.dsl import get
    from combat_engine.engine.grid import distance

    known = world.get(eid, Powers)
    me = world.get(eid, Position)
    if known is None or me is None:
        return 0.0
    # `where` asks the question from a square the creature is not standing in --
    # which is what pricing a push needs, and why nothing has to be moved to find
    # out. Same trick the flanking terms use with `Grid.flanks`.
    stand = where if where is not None else me.square
    mine = world.get(eid, Side)
    if mine is None:
        return 0.0
    foes = [f for f in creatures(world)
            if alive(world, f) and (s := world.get(f, Side)) is not None
            and s.team is not mine.team]
    if not foes:
        return 0.0
    speed = _speed_under(world, eid, pin)
    best = 0.0
    for ref in known.known:
        p = get(ref)
        if p is None or p.reach is None or p.reach.kind == "personal":
            continue
        if not known.available(ref):
            continue
        if pin is not None and pin.no_standard and p.action is ActionType.STANDARD:
            continue
        span = max(1, p.reach.size) + speed
        area = p.reach.kind in ("close_burst", "close_blast", "area_burst", "wall")
        for target in foes:
            them = world.get(target, Position)
            if them is None:
                continue
            if not anywhere and distance(stand, them.square) > span:
                continue
            got = expected_vs(world, eid, ref, target,
                              attack=pin.attack if pin else 0)
            if area:
                # Everything else it would catch, standing where it stands. Close
                # enough: the origin it would choose is not known here.
                got *= sum(
                    1 for other in foes
                    if (o := world.get(other, Position)) is not None
                    and (anywhere or distance(stand, o.square)
                         <= max(1, p.reach.size) + speed)
                )
            if pin is not None and pin.weakened:
                got /= 2        # `Rules.weakened`: the damage it deals is halved
            best = max(best, got)
    return best


def potential(world: Any, eid: int) -> float:
    """Its best round once it has closed, in hit points. The denominator.

    **Not what it can reach this instant**, which is the distinction that took two
    attempts to get right. Using this round's reach as the denominator made an
    immobilise on a creature standing next to a character read as denying 58% of a
    round -- because the thing it lost was the chance to *reposition* to something
    better -- and made an immobilise on a creature out of everybody's reach deny
    nothing, because it had nothing to lose this round. Both are wrong against the
    doctrine: §1 says holding a creature already in contact is worth nothing, and
    holding one at a distance plainly delays its arrival.

    So the denominator is reachability-free -- what the creature does in a round
    when it is where it wants to be -- and reachability lives entirely in the
    numerator, `per_round(target, pin)`, which is what it can manage from where it
    actually stands under what it is actually suffering.
    """
    key = (id(world), getattr(world, "round", 0), eid)
    got = _CACHE.get(key)
    if got is None:
        got = _CACHE[key] = per_round(world, eid, None, anywhere=True)
    return got


def landing(world: Any, target: int, pushed: int) -> Any:
    """Where a shove of `pushed` squares would leave `target`, away from us.

    The pusher picks the direction, so the assumption is the useful one: directly
    away from whichever of our creatures is closest to it. Clamped to a square that
    can be stood in, because a shove into a wall stops at the wall.
    """
    from combat_engine.engine.grid import distance

    me = world.get(target, Position)
    mine = world.get(target, Side)
    if me is None or mine is None or pushed <= 0:
        return None
    ours = [a for a in creatures(world)
            if alive(world, a) and (s := world.get(a, Side)) is not None
            and s.team is not mine.team and world.get(a, Position) is not None]
    if not ours:
        return None
    near = min(ours, key=lambda a: distance(me.square, world.get(a, Position).square))
    from_sq = world.get(near, Position).square
    dx = (me.square[0] > from_sq[0]) - (me.square[0] < from_sq[0])
    dy = (me.square[1] > from_sq[1]) - (me.square[1] < from_sq[1])
    if not dx and not dy:
        return None
    out = me.square
    for step in range(1, pushed + 1):
        sq = (me.square[0] + dx * step, me.square[1] + dy * step)
        if not world.grid.passable(sq) or world.grid.occupant(sq) not in (None, target):
            break
        out = sq
    return out


def denial(world: Any, target: int, laid: Sequence[Laid],
               pushed: int = 0) -> float:
    """How many rounds of `target`'s own damage these effects take away.

    The spec, and every case in it falls out of one subtraction rather than a table:

        free   = potential(target)                     a round, once it has closed
        pinned = per_round(target, from_rules(...))    what it manages where it is
        rounds = ROUNDS_OF[when] * (1 - pinned / free)

    | immobilised, melee only, nobody in reach | `pinned` 0, so a whole round |
    | immobilised, already adjacent            | `pinned` = `free`, so **nothing** |
    | immobilised, holding a ranged attack     | the melee/ranged differential |
    | stunned, petrified, dying                | `cannot_act`, so the whole round |
    | attack debuff of N                       | hit chance falls N/20, pro rata |
    | weakened                                 | damage halved, so half a round |
    | slowed                                   | bites only when the target is far |

    The second and third rows are the point: `notes/DOCTRINE.md` §1 calls the
    adjacency case the most load-bearing distinction in the notes, and a single
    number per condition could not express either of them.

    Effects are taken as the **best** of what is laid rather than the sum, because
    two conditions that both stop a creature acting do not stop it twice.
    """
    # **`pushed` belongs in the key**, and leaving it out made the shove look inert:
    # the first call for a given target and condition cached the unshoved answer and
    # every shoved call read it back. The term fired, the numbers were identical to
    # three decimals, and nothing raised -- which is this component's "silently
    # false" failure arriving through a memo rather than through a predicate.
    key = (id(world), getattr(world, "round", 0), target,
           tuple((o.when, o.conditions) for o in laid), pushed)
    hit = _DENIED.get(key)
    if hit is not None:
        return hit
    got = _denial(world, target, laid, pushed)
    _DENIED[key] = got
    return got


def _denial(world: Any, target: int, laid: Sequence[Laid], pushed: int) -> float:
    """`denial` without the memo."""
    free = potential(world, target)
    if free <= 0:
        return 0.0        # nothing to deny; it has no output to take away
    where = landing(world, target, pushed) if pushed else None
    best = 0.0
    # **A shove with no condition on it still gets one round evaluated.** Camille's
    # case: a prone, slowed or immobilised creature pushed away from the party cannot
    # attack on its turn. The arithmetic needs no special case -- `per_round` from the
    # square it lands in already knows whether it can walk back, so a shove on a free
    # creature prices at nearly nothing and the same shove on a held one prices at a
    # whole round.
    entries = list(laid) or ([Laid(when=When.EOTNT)] if where else [])
    for one in entries:
        turns = ROUNDS_OF.get(one.when, 0.0)
        if not turns:
            continue
        pin = from_rules(one.conditions, one.mods)
        if pin == Pinned() and where is None:
            continue      # the effect does nothing to what it can do
        pinned = per_round(world, target, pin, where=where)
        lost = max(0.0, 1.0 - pinned / free)
        best = max(best, min(float(ROUNDS), turns) * lost)
    return best


def enabled(world: Any, target: int, laid: Sequence[Laid]) -> float:
    """How many rounds of extra *party* damage these effects buy, in hp.

    The other sign, and it was worth exactly nothing before. Making a creature
    easier to hit does not reduce its damage, so `denial` cannot see it -- but a
    -2 to a target's AC is about ten points of hit chance on every attack the party
    makes at it, and combat advantage is the same thing by another route.

    Returned in **hit points of party damage**, not as a share, because its
    denominator is the enemy's pool where denial's is ours. The caller divides.

    Assumes the party will actually attack the creature that was made vulnerable.
    `notes/DOCTRINE.md` §7 records focus fire as the assumed party doctrine, so
    that is consistent with the rest of the scorer -- but it is an assumption about
    behaviour and not a fact about the board.
    """
    mine = world.get(target, Side)
    if mine is None:
        return 0.0
    ours = [a for a in creatures(world)
            if alive(world, a) and (s := world.get(a, Side)) is not None
            and s.team is not mine.team]
    if not ours:
        return 0.0
    best = 0.0
    for one in laid:
        turns = ENABLE_ROUNDS.get(one.when, 0.0)
        if not turns:
            continue
        # Combat advantage is +2, and a defence penalty is its own size. Both are
        # a number of faces on the die, so both convert the same way.
        faces = 2.0 if one.grants_ca else 0.0
        faces += float(-min((v for _, v in one.defences), default=0))
        if faces <= 0:
            continue
        for ally in ours:
            out = per_round(world, ally)
            if out <= 0:
                continue
            hit = _best_hit(world, ally, target)
            if hit is None or hit <= 0:
                continue
            after = min(0.95, hit + faces / 20)
            best = max(best, min(float(ROUNDS), turns) * out * (after - hit) / hit)
    return best


def _best_hit(world: Any, eid: int, target: int) -> float | None:
    """This creature's best chance to hit that one, over the rows it has."""
    from combat_engine.engine.dsl import get

    known = world.get(eid, Powers)
    if known is None:
        return None
    best: float | None = None
    for ref in known.known:
        p = get(ref)
        if p is None or not known.available(ref):
            continue
        got = p.hit_chance(world, eid, target)
        if got is not None and (best is None or got > best):
            best = got
    return best


def pool(world: Any, of: Team) -> int:
    """Total current hit points on one side. The denominator."""
    total = 0
    for eid in creatures(world):
        side = world.get(eid, Side)
        if side is None or side.team is not of or not alive(world, eid):
            continue
        health = world.get(eid, Health)
        if health is not None:
            total += max(0, health.hp)
    return total


def threat(world: Any, eid: int) -> float:
    """`eid`'s best-case 3-round damage, as a share of what it is aimed at.

    Zero for a creature that is already dead, because a corpse threatens nobody
    and the caller would otherwise go on paying to remove it.
    """
    if not alive(world, eid):
        return 0.0
    got = potential(world, eid) * ROUNDS
    side = world.get(eid, Side)
    if side is None:
        return 0.0
    other = Team.ENEMY if side.team is Team.PC else Team.PC
    health = pool(world, other)
    return got / health if health else 0.0
