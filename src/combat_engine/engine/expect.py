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

**Riders are counted now, and were not -- #249.** `Ledger.attack` built an
`AttackResult` without going through `resolve.attack`, so no `Hit` was emitted and
**nothing watching for one fired** -- sneak attack, the fighter's class-feature
mark, item and feat riders -- and it never set `AttackResult.advantage` either, so
the figure did not move between advantage on and off at all. Measured over 500 runs
at level 1, before and after:

    rogue   p7396  advantage off   model  5.70 -> 5.70    sim  5.83
    rogue   p7396  advantage on    model  5.70 -> 14.45   sim 15.24
    fighter p997   advantage off   model  9.53 -> 9.53    sim  9.75

2.67x out on the conditional striker, and 1.05 now. **The two lines that were
already honest did not move**, which is the half of the check that says this is a
fix and not a fudge.

Two things closed it and only the first is obvious. `Ledger.attack` emits the
outcome, so a rider armed by **this power's own body** -- closing over this very
`Cast` -- records into `lines` and stays exact. A rider armed **elsewhere**, a
class feature armed at the top of the fight, has a `Cast` of its own and rolls for
real; those are caught by standing a mean-returning roller in front of `world.rng`
and summing `DamageApplied`.

The rest of the gap was not riders at all. The `Ledger` applied `_mods` alone where
`resolve.attack` applies `attack_penalty`, **combat advantage's +2**, cover,
concealment, long range and a mark -- so it priced away the very bonus a
conditional striker keys off. Both now read one `resolve.situational_attack`,
because two implementations of one rule drift.

**The caller owes this a board kept for measuring.** Emitting a real `Hit` means
riders deal real damage and apply real conditions to the target. Hit points are put
back after every path; marks and conditions are not. `engine/threat.py` is the
caller that gets this right, on a scratch board of copied components.

**Two smaller limits, both in the harness rather than the maths.** A row that
reads `c.trigger` cannot be evaluated standing still -- there is no triggering
event to read -- and comes back as zero; that is 5 of the 14 zeroes in a 600-row
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
from .resolve import AttackResult, _mods, situational_attack

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
          crits: bool = True) -> list[tuple[Fraction, bool, bool, int]]:
    """(probability, hit, crit, a face) for one d20, by distinct outcome.

    `need` is the face the die must show for the total to reach the defence.
    Collapsing matters: three classes instead of twenty faces is what keeps a
    three-roll body at 27 runs.

    `crits=False` prices the same row with criticals switched off, which is how
    a caller separates what the crit window is worth from what the row is worth.

    The fourth item is the **lowest face in the class**, kept because a rider
    fired by `Ledger.attack` reads `result.natural` and a collapsed class no
    longer has one face. Lowest rather than an average because it is a real face
    that produces this outcome, where 10.5 is not. It does mean a rider keyed on
    the *parity* of the roll sees one fixed face per class rather than a spread,
    which is a known bias in the figure and not a large population of rows.
    """
    floor = 20 - crit_range
    tally: dict[tuple[bool, bool], int] = {}
    lowest: dict[tuple[bool, bool], int] = {}
    for nat in range(1, 21):
        crit = crits and nat >= floor and nat >= need
        hit = nat >= floor or (nat != 1 and nat >= need)
        tally[(hit, crit)] = tally.get((hit, crit), 0) + 1
        lowest.setdefault((hit, crit), nat)
    return [(Fraction(n, 20), hit, crit, lowest[(hit, crit)])
            for (hit, crit), n in tally.items()]


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

    def _setup(self, prefix: list[tuple[bool, bool, int]]) -> None:
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
            ctx = self._ctx(who, vs)
            against = defence(self.world, who, vs, ctx)
            # The situational modifiers belong in the bonus the same way they do
            # at roll time. Reading the declared bonus alone priced a feat
            # granting +1 to hit at exactly nothing -- and then reading `_mods`
            # alone priced **combat advantage's +2** at nothing too, along with
            # cover, the prone penalty and a mark. `situational_attack` is the
            # kernel's own copy of that sum; see its docstring.
            total = bonus + situational_attack(
                self.world, self.me, who, self.ref, ctx,
                ca=bool(ctx["advantage"]), charge=self.charge,
                branch=self.branch, among=tuple(self.targets) or (who,),
            )
            raise _Rolled(against - total, self._crit_range())
        hit, crit, natural = self._prefix[self._at]
        self._at += 1
        # **Combat advantage has to be on the result, not only in the bonus.**
        # `Ledger.attack` never set it, so a rider reading
        # `ev.result.advantage` -- which is how a conditional striker's extra
        # damage is written -- never fired, and the model did not move at all
        # between advantage on and off. Measured: 5.70 either way against a
        # simulated 5.83 and 15.24. See #249.
        from .query import has_combat_advantage

        self.result = AttackResult(
            hit=hit, critical=crit, target=who, natural=natural,
            rolls=[natural],
            advantage=has_combat_advantage(self.world, self.me, who, self.ref),
        )
        self._announce(who)
        return self.result

    def _announce(self, who: int) -> None:
        """Emit the `Hit` or `Miss` so everything watching for one fires.

        The other half of #249. Nothing here went through `resolve.attack`, so
        no outcome event was ever emitted and **every rider hung on a `Hit` was
        silently absent** -- a rogue's extra damage, a fighter's mark, item and
        feat riders. The attributes are the ones `resolve.attack` sets, because
        a row reading `ev.branch` or `ev.among` must not tell the two apart.

        A rider armed by this power's own body closes over *this* `Cast`, so its
        damage arrives in `self.lines` and stays exact. One armed elsewhere --
        a class feature armed at the top of the fight, with a `Cast` of its own
        -- rolls for real, and `expected` catches that separately.
        """
        from .events import Hit, Miss

        ev: Any = (
            Hit(attacker=self.me, target=who, power=self.ref,
                critical=self.result.critical)
            if self.result.hit
            else Miss(attacker=self.me, target=who, power=self.ref)
        )
        ev.result = self.result
        ev.among = tuple(self.targets) or (who,)
        ev.branch = self.branch
        ev.opportunity = self.opportunity
        ev.charge = self.charge
        ev.granted_by = self.granted_by
        ev.granted_via = self.granted_via
        self.world.bus.emit(ev)

    def strike(self, *, plus: int = 0, **kw: Any) -> AttackResult:
        from .dsl import get

        p = get(self.ref)
        line = p.attack_of(self.branch) if p else None
        if line is None:
            raise ValueError(f"{self.ref} declared no attack line")
        bonus = line.bonus_for(self.world, self.me, self.ref, self.branch)
        return self.attack(bonus + plus, line.vs)

    def _ctx(self, who: int, vs: Any) -> dict[str, Any]:
        """The attack context, with the keys `resolve.attack` puts in it.

        Not optional detail: a modifier gated on `advantage` or on `ranged`
        reads these, and a key that is absent reads as **false** rather than
        raising -- so a thin context prices a real bonus at nothing and looks
        like a working row. The component file calls this shape out by name.
        """
        from .dsl import get
        from .query import has_combat_advantage

        p = get(self.ref)
        return {
            "attacker": self.me,
            "target": who,
            "power": self.ref,
            "defence": vs.value,
            "advantage": has_combat_advantage(self.world, self.me, who, self.ref),
            "opportunity": self.opportunity,
            "charge": self.charge,
            "granted_by": self.granted_by,
            "granted_via": self.granted_via,
            "action_point": False,
            "ranged": (p.reach_of(self.branch).kind == "ranged"
                       if p is not None else False),
            "hand": "main",
        }

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


class _Mean:
    """An `Rng` that returns each expression's mean instead of rolling it.

    The single funnel every damage roll in the kernel goes through is
    `world.rng.roll` (`Cast._roll_damage`), so standing in for it is what makes a
    *foreign* cast's damage deterministic and therefore readable as a mean. Only
    `roll` is replaced; `die` and everything else pass through, because a rider
    that rolls its own d20 should still behave like a die.
    """

    def __init__(self, real: Any) -> None:
        self._real = real

    def roll(self, expr: str | int) -> Any:
        from .rng import Roll

        return Roll(expr=str(expr), dice=[round(mean(expr))], bonus=0)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def expected(world: Any, me: int, ref: str, target: int, *,
             cap: int = 6, crits: bool = True) -> Fraction:
    """Expected damage `ref` deals to `target`, over every path of its body.

    `cap` bounds how many attack rolls are explored. A body rolling more than
    six times is an area attack over a crowd, where "expected damage on one
    target" is the wrong question rather than an expensive one.

    **Hand this a board kept for measuring.** `Ledger` emits a real `Hit`, so
    riders land real damage and real conditions on `target`. Hit points are put
    back after every path -- otherwise the target bleeds down as the paths are
    explored and the later ones are priced against a weaker creature -- but marks
    and conditions are not, and a creature measured on a played board would be
    damaged by the act of measuring it. `engine/threat.py` is the caller that
    gets this right, on a scratch board.
    """
    from .components import Health
    from .dsl import get
    from .events import DamageApplied

    row = get(ref)
    if row is None or row.body is None:
        raise ValueError(f"{ref} has no body to run")
    body = row.body
    hurt = world.get(target, Health)

    def once(prefix: list[tuple[bool, bool, int]]) -> tuple[Fraction | None, Any]:
        """One run of the body. Either a value, or the roll it asked for.

        The two are kept apart from `walk` so that the recording below wraps a
        **leaf only**. Recursing inside it would leave the parent's subscription
        live while its children ran, and each child's rider damage would be
        counted once for itself and again for every ancestor.
        """
        # Damage dealt by anything *other* than this Ledger -- a rider armed by
        # a class feature has a `Cast` of its own and rolls for real, so it never
        # reaches `self.lines`. `DamageApplied` is what actually came off hit
        # points, and the Ledger's own `damage` records rather than calling
        # `deal_damage`, so nothing here is counted twice.
        foreign: list[int] = []
        sub = world.bus.on(
            DamageApplied,
            lambda ev: foreign.append(ev.amount) if ev.source == me else None,
        )
        was, world.rng = world.rng, _Mean(world.rng)
        before = hurt.hp if hurt is not None else None
        try:
            c = Ledger(world=world, me=me, ref=ref, target=target,
                       targets=[target])
            c._setup(prefix)
            try:
                body(c)
            except _Rolled as r:
                return None, r
            return worth(c.lines) + sum(foreign), None
        finally:
            world.bus.off(sub)
            world.rng = was
            if hurt is not None and before is not None:
                hurt.hp = before

    def walk(prefix: list[tuple[bool, bool, int]]) -> Fraction:
        value, rolled = once(prefix)
        if rolled is None:
            return value if value is not None else Fraction(0)
        if len(prefix) >= cap:
            return Fraction(0)
        return sum(
            p * walk([*prefix, (hit, crit, nat)])
            for p, hit, crit, nat in faces(rolled.need, rolled.crit_range, crits)
        )

    return walk([])
