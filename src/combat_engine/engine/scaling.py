"""What a level is worth.

4e adds level to almost every number: half your level to attack rolls, to
every defence and to initiative, and a point per level to a monster's
printed attack and defences. Those terms cancel out -- a level 10 fight plays
almost exactly like a level 1 fight with bigger numbers on both sides -- so
they can be turned down without the arithmetic stopping working.

Nothing in the engine adds a level to anything directly. Components store the
number **without** its level term, `Scaling` supplies the term, and so
`Scaling(amount=0.0)` gives bounded accuracy across the whole system at once:
a level 10 fighter and a level 10 brute keep the numbers they had at level 1,
and hit each other about as often as they always did.

    world.scaling = BOUNDED      # a level is worth nothing
    world.scaling = HALF         # a level is worth half of 4e's step

A monster's numbers are different in kind from a character's. A stat block is
printed as a total that already has the level in it, so what `monster()`
returns is subtracted back out; a character's sheet is built up from parts, so
`pc()` is added on. Both are driven by the same `amount`, which is what keeps
the two sides of a fight in step however it is set.

Hit points are deliberately untouched. Bounded accuracy is about how often
attacks land, not about how long a fight lasts, and flattening hit points as
well would make every fight at every level identical rather than merely
comparable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scaling:
    """How much of 4e's level scaling to apply.

    `amount` is the dial: 1.0 is the printed game, 0.0 is bounded accuracy,
    and anything between is a proportion of it. The two `per_level` values
    are 4e's own rates and are here to be read, not usually to be changed.
    """

    amount: float = 1.0
    #: A character gains half a point of everything per level.
    per_level_pc: float = 0.5
    #: A stat block gains about a point per level over level 1.
    per_level_monster: float = 1.0

    @property
    def on(self) -> bool:
        return self.amount != 0.0

    def pc(self, level: int) -> int:
        """What a character of this level adds to attacks and defences."""
        return int(self.amount * self.per_level_pc * level)

    def monster(self, level: int) -> int:
        """What a stat block of this level keeps of its printed level term."""
        return int(self.amount * self.per_level_monster * max(0, level - 1))

    def printed_monster(self, level: int) -> int:
        """The level term a printed stat block already contains."""
        return int(self.per_level_monster * max(0, level - 1))

    def trim(self, printed: int, level: int) -> int:
        """Take a printed monster number down to what this setting wants.

        Handed the `+6 vs. AC` off a stat block, it gives back the bonus the
        fight should actually use.
        """
        return printed - self.printed_monster(level) + self.monster(level)

    def describe(self) -> str:
        if self.amount == 1.0:
            return "full (as printed)"
        if self.amount == 0.0:
            return "bounded (level adds nothing)"
        return f"{self.amount:.0%} of printed"


#: As published.
FULL = Scaling()

#: Bounded accuracy: a level is worth nothing to attack rolls or defences.
BOUNDED = Scaling(amount=0.0)

#: Halfway, for a game that wants some progression without 4e's treadmill.
HALF = Scaling(amount=0.5)

PRESETS = {"full": FULL, "bounded": BOUNDED, "half": HALF}
