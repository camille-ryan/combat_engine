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
from typing import Any

from .components import Defenses, Health, Ident, Powers, Side
from .query import alive, creatures
from .types import Condition, Defense, Team

#: How much of a creature's threat each condition takes away, as a fraction.
#:
#: **Every entry is deliberately zero.** Camille's instruction for this pass was
#: to "set the conditions applied threat modifiers to 0 (so that we can edit them
#: later)", and a table of zeros that is genuinely consulted is worth more than
#: an absent one: the tuning is a one-line edit here rather than a new mechanism,
#: and a reader can see at a glance that conditions currently count for nothing.
#:
#: Written out rather than generated so each line is somewhere to put a number.
#: When they are filled in, note that the ordering is contested --
#: `notes/DOCTRINE.md` §1 found guide doctrine ranks these by *action denial*
#: (helpless, then immobilised, then dazed) while this project's own tiers rank
#: them by geography, and that both are right because they answer different
#: questions. A single column here cannot express both.
CONDITION_THREAT: dict[Condition, float] = {
    Condition.BLINDED: 0.0,
    Condition.DAZED: 0.0,
    Condition.DEAFENED: 0.0,
    Condition.DOMINATED: 0.0,
    Condition.DYING: 0.0,
    Condition.GRABBED: 0.0,
    Condition.HELPLESS: 0.0,
    Condition.IMMOBILIZED: 0.0,
    Condition.INSUBSTANTIAL: 0.0,
    Condition.MARKED: 0.0,
    Condition.PETRIFIED: 0.0,
    Condition.PINNED: 0.0,
    Condition.PRONE: 0.0,
    Condition.REMOVED: 0.0,
    Condition.RESTRAINED: 0.0,
    Condition.SHAPED: 0.0,
    Condition.ROOTED: 0.0,
    Condition.SLOWED: 0.0,
    Condition.SQUEEZING: 0.0,
    Condition.STUNNED: 0.0,
    Condition.SURPRISED: 0.0,
    Condition.UNCONSCIOUS: 0.0,
    Condition.WEAKENED: 0.0,
}

#: How many rows make up "best case over three rounds".
ROUNDS = 3

#: Keyed on the board and the creature, because a build does not change during a
#: fight. Spending a power does not change this figure either -- "best case" is
#: about what the creature can do, not what it has left.
_CACHE: dict[tuple[int, int], float] = {}


def clear() -> None:
    """Forget every cached figure. For an instrument measuring across fights.

    Worth calling between fights rather than trusting the keys: a `World` that
    has been collected frees its `id()` for the next one, so a stale entry could
    be read as the new board's.
    """
    _CACHE.clear()
    _ROWS.clear()
    _BOARDS.clear()


def condition_threat(cond: Condition) -> float:
    """The share of a creature's threat that `cond` removes. Currently zero."""
    return CONDITION_THREAT.get(cond, 0.0)


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
    from .ecs import World
    from .events import Bus
    from .grid import Grid
    from .movement import place
    from .rng import Rng
    from .turns import Encounter

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
    from .expect import expected

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


def row_damage(world: Any, eid: int, ref: str) -> float:
    """What one row of `eid`'s would deal to the baseline opponent, in hp.

    The damage half of `threat_removed`. Against the **baseline** rather than the
    creature actually being aimed at, which is the approximation to know about:
    accuracy against the real target is carried separately by the `hit_chance`
    feature, so this is a measure of how hard the row hits and not of whether it
    lands. Pricing it against the live target would be the better number and is
    not available -- `expect.expected` would wound that target to find out.
    """
    from .expect import expected

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
    try:
        out = float(expected(w, me, ref, foe))
    except Exception:
        out = 0.0
    _ROWS[key] = out
    return out


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
    key = (id(world), eid)
    got = _CACHE.get(key)
    if got is None:
        got = _CACHE[key] = raw(world, eid)
    side = world.get(eid, Side)
    if side is None:
        return 0.0
    other = Team.ENEMY if side.team is Team.PC else Team.PC
    health = pool(world, other)
    return got / health if health else 0.0
