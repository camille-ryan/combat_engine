"""Expected damage of a power, in closed form, by enumerating its own body.

Scoring a character's options means asking "what would this row deal?" a few
thousand times -- every candidate weapon against every row the character knows,
and again for every feat that might change one. Fighting each question out in
simulation costs about a second and still carries half a point of noise, which
is both too slow to answer a page and too vague to rank two weapons that differ
by one point.

So the figure is arithmetic. A power body is ordinary Python and its randomness
comes through exactly three doors -- the attack roll, the damage roll, and the
enhancement. `Ledger` is a `Cast` that holds all three shut: it hands the body a
**dictated** attack result and writes damage expressions into a list instead of
rolling them. One run of the body therefore yields the exact damage of one
outcome, and weighting each outcome by its probability gives an exact mean.

How many outcomes a row has is not known in advance, because a body decides
whether to roll again by looking at what the last roll did. So the paths are
discovered rather than assumed: `expected` runs the body against a prefix of
dictated results, and when the body asks for a roll the prefix does not cover,
that run is discarded and one child run starts per outcome-class of the new
roll. Each child's prefix is one longer, so it terminates. The d20 collapses to
at most three classes -- miss, hit, critical -- so a body rolling three times
costs 27 runs and not 8,000.

Measured: 3.8 ms for the median attacking weapon row, and 599 of a 600-row
sample evaluate. Against simulation the two agree to within sampling error --
6,400 runs of three level-1 rows came in at +0.14, +0.09 and -0.02.

**The rules are read out of the kernel, not out of the book**, because on three
counts the kernel differs and the scorer must score what actually happens:

* `resolve.attack` -- `floor = 20 - crit_range`; a natural at or above the floor
  opens a critical *and* the total must also reach the defence. A natural at the
  floor hits either way; a natural 1 never hits.
* `Cast.damage` -- a critical maxes the dice, then adds the flat bonus and the
  enhancement. Neither of those is maxed, both being flat already.
* `Cast.half_damage` -- `(rolled + bonus) // 2`, floored per roll, and no
  enhancement (#241). The flooring is why this needs a distribution rather than
  a mean: halving the average is not the average of the halves.

`high crit` contributes nothing because the kernel reads it nowhere (#240).

**Two limits, both in the harness rather than the maths.** A row that reads
`c.trigger` cannot be evaluated standing still -- there is no triggering event
to read -- and comes back as zero; that is 5 of the 14 zeroes in a 600-row
sample and the rest are rows whose own docstrings say they deal no damage.
And `c.absorb` is not recorded, because it moves damage onto the caster off a
trigger, which is neither damage dealt nor evaluable without the trigger.

Ongoing damage is also absent: it is applied by a duration on a later turn and
not through a `Cast` at all, so a row whose damage is mostly ongoing scores low
here. That is a real gap in the number, not a bug in the enumeration.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from .cast import Cast
from .query import defence
from .resolve import AttackResult, _mods

#: Damage expressions repeat hard across the tree -- `1d8`, `2d6`, `2d10` -- and
#: convolving one costs more than looking it up.
_CACHE: dict[str | int, dict[int, Fraction]] = {}
_DICE = re.compile(r"\s*(\d*)d(\d+)\s*(?:([+-])\s*(\d+))?\s*$")


def dist(dice: str | int) -> dict[int, Fraction]:
    """Exact distribution of a damage expression, as value -> probability.

    A flat number and the empty expression are both certain, and both are real:
    a minion's damage is a number with no dice in it.
    """
    got = _CACHE.get(dice)
    if got is not None:
        return got
    if isinstance(dice, int):
        out = {dice: Fraction(1)}
    elif not dice:
        out = {0: Fraction(1)}
    else:
        m = _DICE.match(dice)
        if m is None:
            out = {0: Fraction(1)}
        else:
            n, faces = int(m.group(1) or 1), int(m.group(2))
            flat = int(m.group(4)) * (1 if m.group(3) == "+" else -1) if m.group(3) else 0
            out = {flat: Fraction(1)}
            for _ in range(n):
                nxt: dict[int, Fraction] = {}
                for total, p in out.items():
                    for face in range(1, faces + 1):
                        nxt[total + face] = nxt.get(total + face, Fraction(0)) + p / faces
                out = nxt
    _CACHE[dice] = out
    return out


def mean(dice: str | int) -> Fraction:
    return sum(v * p for v, p in dist(dice).items())


def most(dice: str | int) -> int:
    """Every die on its highest face. What a critical hit deals."""
    return max(dist(dice))


def halved(dice: str | int, bonus: int) -> Fraction:
    """`(rolled + bonus) // 2` in expectation.

    Floored on each roll and not on the average, which is what the kernel does
    and is up to half a point away from halving the mean.
    """
    return sum(p * ((v + bonus) // 2) for v, p in dist(dice).items())


def faces(need: int, crit_range: int = 0,
          crits: bool = True) -> list[tuple[Fraction, bool, bool]]:
    """(probability, hit, crit) for one d20, collapsed to distinct outcomes.

    `need` is the face the die must show for the total to reach the defence.
    Collapsing matters: three classes instead of twenty faces is what keeps a
    three-roll body at 27 runs.

    `crits=False` prices the same row with criticals switched off, which is how
    a caller separates what the crit window is worth from what the row is worth.
    """
    floor = 20 - crit_range
    tally: dict[tuple[bool, bool], int] = {}
    for nat in range(1, 21):
        crit = crits and nat >= floor and nat >= need
        hit = nat >= floor or (nat != 1 and nat >= need)
        tally[(hit, crit)] = tally.get((hit, crit), 0) + 1
    return [(Fraction(n, 20), hit, crit) for (hit, crit), n in tally.items()]


class _Rolled(Exception):
    """The body asked for an attack roll the dictated prefix does not cover."""

    def __init__(self, need: int, crit_range: int) -> None:
        super().__init__(need)
        self.need, self.crit_range = need, crit_range


class Ledger(Cast):
    """A `Cast` that dictates attack results and records damage unrolled.

    Everything not overridden below still runs for real -- conditions, marks,
    pushes -- against the world it was handed. That is deliberate: a body often
    branches on what it just did, and stubbing those out would take the branch
    away. It does mean the caller's world accumulates the marks of every path
    explored, so hand this a board kept for measuring and not one being played.
    """

    def _setup(self, prefix: list[tuple[bool, bool]]) -> None:
        self._prefix = prefix
        self._at = 0
        #: (kind, dice, bonus, enhancement, was_a_crit)
        self.lines: list[tuple[str, str | int, int, int, bool]] = []

    # -- the attack roll, dictated -------------------------------------------

    def attack(self, bonus: int, vs: Any, *, on: int | None = None, **kw: Any) -> AttackResult:
        who = self._who(on)
        if who is None:
            return AttackResult()
        if self._at >= len(self._prefix):
            ctx = {"power": self.ref, "defence": vs.value}
            against = defence(self.world, who, vs, ctx)
            # The situational modifiers belong in the bonus the same way they do
            # at roll time. Reading the declared bonus alone priced a feat
            # granting +1 to hit at exactly nothing.
            total = bonus + _mods(self.world, self.me, "attack", ctx)
            raise _Rolled(against - total, self._crit_range())
        hit, crit = self._prefix[self._at]
        self._at += 1
        self.result = AttackResult(hit=hit, critical=crit, target=who)
        return self.result

    def strike(self, *, plus: int = 0, **kw: Any) -> AttackResult:
        from .dsl import get

        p = get(self.ref)
        line = p.attack_of(self.branch) if p else None
        if line is None:
            raise ValueError(f"{self.ref} declared no attack line")
        bonus = line.bonus_for(self.world, self.me, self.ref, self.branch)
        return self.attack(bonus + plus, line.vs)

    def _crit_range(self) -> int:
        """How wide the crit window is, asked of the kernel and not the card."""
        return _mods(self.world, self.me, "crit_range", {"power": self.ref})

    # -- damage, recorded rather than rolled ---------------------------------

    def damage(self, dice: str | int = 0, bonus: int = 0, *,
               on: int | None = None, **kw: Any) -> int:
        if self._who(on) is None:
            return 0
        self.lines.append(("full", dice, bonus, self._enhancement(), self.crit))
        # A body writing `if c.damage(...):` is asking whether damage landed,
        # so this has to come back truthy.
        return int(mean(dice)) + bonus + 1

    def half_damage(self, dice: str | int = 0, bonus: int = 0, *,
                    on: int | None = None, **kw: Any) -> int:
        if self._who(on) is None:
            return 0
        self.lines.append(("half", dice, bonus, 0, False))
        return int(mean(dice)) + bonus

    def flat(self, amount: int, *, on: int | None = None, **kw: Any) -> int:
        if self._who(on) is None:
            return 0
        self.lines.append(("flat", 0, amount, 0, False))
        return amount

    def hit(self, *, on: int | None = None, half: bool = False) -> int:
        """The header's declared damage, routed through the recorders above."""
        from .dsl import get

        p = get(self.ref)
        d = p.damage_of(self.branch) if p is not None else None
        if d is None:
            raise ValueError(f"{self.ref} declared no damage")
        dice, bonus = self._converted(d), self._bonus_of(d.bonus)
        if half:
            return self.half_damage(dice, bonus, on=on)
        return self.damage(dice, bonus, on=on)


def worth(lines: list[tuple[str, str | int, int, int, bool]]) -> Fraction:
    """Expected damage of one recorded path, exactly."""
    total = Fraction(0)
    for kind, dice, bonus, enh, crit in lines:
        if kind == "half":
            total += halved(dice, bonus)
        elif kind == "flat":
            total += bonus
        elif crit:
            total += most(dice) + bonus + enh
        else:
            total += mean(dice) + bonus + enh
    return total


def expected(world: Any, me: int, ref: str, target: int, *,
             cap: int = 6, crits: bool = True) -> Fraction:
    """Expected damage `ref` deals to `target`, over every path of its body.

    `cap` bounds how many attack rolls are explored. A body rolling more than
    six times is an area attack over a crowd, where "expected damage on one
    target" is the wrong question rather than an expensive one.
    """
    from .dsl import get

    row = get(ref)
    if row is None or row.body is None:
        raise ValueError(f"{ref} has no body to run")
    body = row.body

    def walk(prefix: list[tuple[bool, bool]]) -> Fraction:
        c = Ledger(world=world, me=me, ref=ref, target=target, targets=[target])
        c._setup(prefix)
        try:
            body(c)
        except _Rolled as r:
            if len(prefix) >= cap:
                return Fraction(0)
            return sum(
                p * walk([*prefix, (hit, crit)])
                for p, hit, crit in faces(r.need, r.crit_range, crits)
            )
        return worth(c.lines)

    return walk([])
