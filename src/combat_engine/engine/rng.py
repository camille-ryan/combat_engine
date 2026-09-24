"""Seeded dice.

An encounter is `(seed, setup, events)` and must replay exactly, so every
random draw in the engine comes from one `Rng` and nothing else calls into
`random`. `rolls` records every draw in order, which is what makes a
divergence between two runs locatable rather than merely visible.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

_DICE = re.compile(r"^\s*(\d*)d(\d+)\s*(?:([+-])\s*(\d+))?\s*$", re.IGNORECASE)


@dataclass
class Roll:
    """One dice expression, resolved. `dice` holds the individual faces."""

    expr: str
    dice: list[int]
    bonus: int

    @property
    def total(self) -> int:
        return sum(self.dice) + self.bonus

    def __str__(self) -> str:
        faces = "+".join(str(d) for d in self.dice)
        tail = f"{self.bonus:+d}" if self.bonus else ""
        return f"{self.expr} [{faces}]{tail} = {self.total}"


@dataclass
class Rng:
    seed: int
    _r: random.Random = field(init=False, repr=False)
    rolls: list[Roll] = field(default_factory=list, repr=False)
    #: Force every d20 to this face. For the audit, which needs to exercise
    #: the critical and the fumble branches deliberately -- a natural 20 is
    #: one roll in twenty, and eight seeds a row is not enough to find a
    #: crash that only happens on one. It found none for a year; the first
    #: forced pass found a minion raising on every crit in the game.
    loaded: int | None = None

    def __post_init__(self) -> None:
        self._r = random.Random(self.seed)

    def die(self, faces: int) -> int:
        if self.loaded is not None and faces == 20:
            return self.loaded
        return self._r.randint(1, faces)

    def d20(self) -> Roll:
        return self.roll("1d20")

    def roll(self, expr: str | int) -> Roll:
        """Resolve `NdM+K`. A bare int is a constant, which keeps callers that
        sometimes have flat damage from having to special-case it."""
        if isinstance(expr, int):
            r = Roll(str(expr), [], expr)
            self.rolls.append(r)
            return r
        m = _DICE.match(expr)
        if not m:
            raise ValueError(f"not a dice expression: {expr!r}")
        count = int(m.group(1) or 1)
        faces = int(m.group(2))
        bonus = int(m.group(4) or 0) * (-1 if m.group(3) == "-" else 1)
        r = Roll(expr, [self.die(faces) for _ in range(count)], bonus)
        self.rolls.append(r)
        return r

    def choice[T](self, seq: list[T]) -> T:
        return seq[self._r.randrange(len(seq))]

    def shuffled[T](self, seq: list[T]) -> list[T]:
        out = list(seq)
        self._r.shuffle(out)
        return out


def average(expr: str | int) -> float:
    """What a dice expression is worth on average. For ordering choices
    without spending a draw -- calling `roll` to preview would desync replay."""
    if isinstance(expr, int):
        return float(expr)
    m = _DICE.match(expr)
    if not m:
        raise ValueError(f"not a dice expression: {expr!r}")
    count = int(m.group(1) or 1)
    faces = int(m.group(2))
    bonus = int(m.group(4) or 0) * (-1 if m.group(3) == "-" else 1)
    return count * (faces + 1) / 2 + bonus
