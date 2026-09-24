"""The components a creature, a zone or a conjuration is made of.

No display names anywhere. `Ident.ref` is a compendium id like `m145` or
`p289`, and `Ident.tag` distinguishes the second goblin from the first. A
player sees a name because the API looks one up at the boundary; the engine
never holds one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .grid import Square, footprint
from .types import Ability, Condition, DamageType, Defense, Size, Team, modifier

# --------------------------------------------------------------------------
# Identity and placement
# --------------------------------------------------------------------------


@dataclass
class Ident:
    ref: str
    tag: str = ""
    #: Which book this row's numbers were printed under: MM1, MM2, MM3, or
    #: empty for a character. `monster_math` needs it to know what it is
    #: converting *from*.
    book: str = ""

    def __str__(self) -> str:
        return f"{self.ref}{('#' + self.tag) if self.tag else ''}"


@dataclass
class Position:
    square: Square
    size: Size = Size.MEDIUM

    @property
    def squares(self) -> frozenset[Square]:
        return footprint(self.square, self.size)


@dataclass
class Side:
    team: Team


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------


@dataclass
class Stats:
    level: int = 1
    scores: dict[Ability, int] = field(default_factory=dict)

    def score(self, a: Ability) -> int:
        return self.scores.get(a, 10)

    def mod(self, a: Ability) -> int:
        return modifier(self.score(a))

    @property
    def half_level(self) -> int:
        return self.level // 2


@dataclass
class Defenses:
    """Defences **without** their level term. See `engine/scaling.py`.

    `scale` says which way the level term goes: a character's sheet is built
    up from parts and has it added, a stat block is printed as a total and
    had it taken out when the monster was loaded.
    """

    values: dict[Defense, int] = field(default_factory=dict)
    scale: str = "pc"  # pc | monster | none

    def base(self, d: Defense) -> int:
        return self.values.get(d, 10)


@dataclass
class Health:
    max_hp: int
    hp: int = 0
    temp: int = 0
    surges: int = 0
    #: Failed death saves. Three and the creature is dead.
    failures: int = 0

    def __post_init__(self) -> None:
        if self.hp == 0:
            self.hp = self.max_hp

    @property
    def bloodied(self) -> bool:
        return self.hp <= self.max_hp // 2

    @property
    def surge_value(self) -> int:
        return self.max_hp // 4

    @property
    def dying_at(self) -> int:
        """Below this and the creature is dead outright."""
        return -(self.max_hp // 2)


@dataclass
class Movement:
    speed: int = 6
    #: Extra modes and their speeds, e.g. {"fly": 8, "climb": 3}.
    modes: dict[str, int] = field(default_factory=dict)


@dataclass
class Defences:
    """Damage the creature shrugs off or takes worse, by type."""

    resist: dict[DamageType, int] = field(default_factory=dict)
    vulnerable: dict[DamageType, int] = field(default_factory=dict)
    immune: set[DamageType] = field(default_factory=set)


@dataclass
class Initiative:
    """`bonus` excludes the level term, which `scaling` supplies."""

    bonus: int = 0
    rolled: int = 0
    scale: str = "pc"


# --------------------------------------------------------------------------
# What is currently true of a creature
# --------------------------------------------------------------------------


@dataclass
class Conditions:
    """Which conditions hold, and how many effects are imposing each.

    A count rather than a set: two powers can daze the same creature, and the
    first one to expire must not clear the daze the second is still imposing.
    """

    counts: dict[Condition, int] = field(default_factory=dict)

    def has(self, c: Condition) -> bool:
        return self.counts.get(c, 0) > 0

    def add(self, c: Condition) -> bool:
        """True when this is the condition's first source."""
        was = self.has(c)
        self.counts[c] = self.counts.get(c, 0) + 1
        return not was

    def remove(self, c: Condition) -> bool:
        """True when this was the condition's last source."""
        n = self.counts.get(c, 0) - 1
        if n <= 0:
            self.counts.pop(c, None)
            return True
        self.counts[c] = n
        return False

    @property
    def active(self) -> list[Condition]:
        return sorted(c for c, n in self.counts.items() if n > 0)


@dataclass
class Mod:
    """One numeric modifier.

    `what` names what it changes: `attack`, `damage`, `save`, `speed`, or a
    `Defense` value. `kind` is the bonus type -- same-named types do not
    stack, untyped ones do, and penalties always do.

    `when` is an optional gate the power body closes over. It makes the
    modifier un-introspectable, which is the accepted price of powers being
    code: a bonus that applies "only against the creature you marked" is one
    lambda here instead of a new op, a builder and a schema.
    """

    what: str
    value: int
    kind: str = "untyped"
    when: Callable[[dict[str, Any]], bool] | None = None
    label: str = ""

    def applies(self, ctx: dict[str, Any]) -> bool:
        return self.when is None or self.when(ctx)


@dataclass
class Mods:
    items: list[Mod] = field(default_factory=list)

    def total(self, what: str, ctx: dict[str, Any] | None = None) -> int:
        """Sum the modifiers to `what`, applying 4e's stacking rules."""
        ctx = ctx or {}
        best: dict[str, int] = {}
        out = 0
        for m in self.items:
            if m.what != what or not m.applies(ctx):
                continue
            if m.value < 0 or m.kind == "untyped":
                out += m.value  # penalties and untyped bonuses always stack
            else:
                best[m.kind] = max(best.get(m.kind, 0), m.value)
        return out + sum(best.values())


@dataclass
class Powers:
    """What a creature can do, by id. Never by name."""

    known: list[str] = field(default_factory=list)
    #: How many times each row has been used this encounter. A count rather
    #: than a set, because a few powers are usable twice -- and one of them
    #: is the cleric's heal, which a party without is not a party.
    used: dict[str, int] = field(default_factory=dict)
    #: The round each was last used, for "once per round" on top of that.
    last_round: dict[str, int] = field(default_factory=dict)
    #: Recharge powers that came back up this turn, and those still down.
    recharging: dict[str, int] = field(default_factory=dict)
    #: What this creature's basic attack is. A monster points at one of its
    #: own abilities; everyone else uses the engine's melee basic.
    basic: str = "mba"
    #: A power that replaces the basic attack when opportunity knocks.
    opportunity: str = ""

    @property
    def all(self) -> list[str]:
        """Everything usable, with the basic attack included exactly once."""
        out = list(self.known)
        for extra in (self.basic, self.opportunity):
            if extra and extra not in out:
                out.append(extra)
        return out

    @property
    def spent(self) -> set[str]:
        """Rows used at least once. Kept for readers that only ask that."""
        return {ref for ref, n in self.used.items() if n > 0}

    def times(self, ref: str) -> int:
        return self.used.get(ref, 0)

    def note_use(self, ref: str, round_: int) -> None:
        self.used[ref] = self.used.get(ref, 0) + 1
        self.last_round[ref] = round_

    def restore(self, ref: str) -> None:
        self.used.pop(ref, None)
        self.last_round.pop(ref, None)

    def available(self, ref: str) -> bool:
        return ref in self.all and self.times(ref) == 0


@dataclass
class Budget:
    """The action economy for one turn.

    `immediate_round` and `opportunity_turn` are stamped with the round and
    the turn they were spent on, because their limits are per round and per
    *other creature's* turn rather than per own turn.
    """

    standard: int = 1
    move: int = 1
    minor: int = 1
    immediate_round: int = -1
    opportunity_turn: int = -1

    def refresh(self) -> None:
        self.standard = 1
        self.move = 1
        self.minor = 1


@dataclass
class Gear:
    """What the creature is holding and wearing, as mechanical facts only.

    A weapon is its numbers -- there is no place here for a printed name.
    """

    weapons: list[Weapon] = field(default_factory=list)
    shield: bool = False
    armour: str = "cloth"

    @property
    def main(self) -> Weapon | None:
        """What is in hand. The first weapon listed is the one being swung."""
        return self.weapons[0] if self.weapons else None

    @property
    def ranged(self) -> Weapon | None:
        """The first weapon that can be fired, if the creature carries one.

        A ranger with a short sword and a longbow has both, and a ranged
        power should be rolling the bow's dice rather than the sword's.
        """
        return next((w for w in self.weapons if w.ranged), None)


@dataclass
class Weapon:
    ref: str
    damage: str = "1d8"
    proficiency: int = 2
    reach: int = 1
    ranged: tuple[int, int] | None = None
    group: str = ""
    properties: frozenset[str] = frozenset()

    @property
    def is_light_blade(self) -> bool:
        return self.group == "light blade"
