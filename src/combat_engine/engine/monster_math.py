"""Converting a monster between the two sets of maths 4e was printed under.

Monster Manual 1 and 2 ran on one set of numbers; Monster Manual 3 and the
Monster Vault revised them. The revision is famous for the right reason:
MM1 monsters do too little damage and fights take too long. `MM3` rescales
an older row to the newer curve without touching what the row *does*.

**What actually differs, measured against this corpus rather than recalled.**
Standard monsters, heroic tier, first at-will attack:

    damage        lvl 1 both about 7; by lvl 10, MM1 11.5 and MM3 17.3
    brute attack  MM1 +4.1 over level, MM3 +4.7
    soldier       MM1 +5.4, MM3 +5.2 -- other roles converge on +5.0
    solo hp       MM1 3.9x a standard monster, MM3 3.4x
    AC, other defences, standard hit points    the same in both

So this is, in the main, a **damage** conversion. Defences and hit points
come off the stat block already and need nothing done to them.

Two tables describe the revision, and they disagree. `MM3` is the published
design formula. `FITTED` is a least-squares fit to the 154 MM3 rows in this
corpus -- what actually got printed. `scripts/mm3.py` puts them side by side
and is how the numbers get argued with using evidence.

`TO_MM3` uses the **fitted** one, and the reason is the recharge line: the
published `12 + level x 1.5` wants 27 damage at level 10 where the books
average 14. Converting an old monster on that formula would roughly double
every recharge attack in the game. `TO_MM3_PUBLISHED` is there for anyone
who wants the stated intent instead.

Nothing is converted unless asked for. The default is `AS_PRINTED`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .rng import average

#: What a damage expression is for. MM3 scales these differently: a
#: recharge power hits harder than an at-will, and a minion hits for half.
NORMAL = "normal"
LIMITED = "limited"
MINION = "minion"


@dataclass(frozen=True)
class Table:
    """One book's idea of what a monster's numbers should be.

    Only `damage` is consulted at the moment, because it is the only one the
    corpus says really moved. The rest are here because they are part of the
    same published claim and `scripts/mm3.py` reports on all of them -- when
    one of them earns its keep, it is already written down.
    """

    name: str
    #: Average damage a standard attack should do at this level.
    damage: object
    #: And a recharge or encounter attack.
    limited: object
    #: Attack bonus over level, by role. Reported, not yet applied.
    attack: dict[str, float] = field(default_factory=dict)
    #: Hit points as a multiple of a standard monster's, by rank.
    rank_hp: dict[str, float] = field(default_factory=dict)

    def target(self, level: int, kind: str) -> float:
        if kind == LIMITED:
            return float(self.limited(level))
        out = float(self.damage(level))
        return out / 2 if kind == MINION else out


#: Attack bonus over level, by role, as published. Reported by
#: `scripts/mm3.py` rather than applied -- the corpus says the real gap is
#: about half a point, not two.
ATTACK_OLD = {
    "brute": 3, "soldier": 7, "artillery": 5,
    "lurker": 5, "skirmisher": 5, "controller": 5,
}  # fmt: skip
ATTACK_MM3 = dict.fromkeys(ATTACK_OLD, 5)


#: Monster Manual 1 and 2. Damage scaled poorly, which is the whole reason
#: the revision happened.
OLD = Table(
    name="MM1/MM2",
    damage=lambda level: 4 + level * 0.6,
    limited=lambda level: (4 + level * 0.6) * 1.25,
    attack=ATTACK_OLD,
    rank_hp={"standard": 1.0, "elite": 2.0, "solo": 5.0, "minion": 0.0},
)

#: Monster Manual 3 and the Monster Vault, as the design notes describe it.
MM3 = Table(
    name="MM3 (published)",
    damage=lambda level: 8 + level,
    limited=lambda level: 12 + level * 1.5,
    attack=ATTACK_MM3,
    rank_hp={"standard": 1.0, "elite": 2.0, "solo": 4.0, "minion": 0.0},
)

#: Monster Manual 3 as it was actually printed, fitted to the 154 MM3 rows
#: in this corpus by least squares. `scripts/mm3.py` is where the two are
#: put side by side.
#:
#: The standard-damage formula above runs two to three points hot across
#: heroic tier. The limited-damage one is not close: `12 + level x 1.5` says
#: 27 at level 10 and the books say 14, so converting an older monster with
#: it would roughly double every recharge attack in the game. That is the
#: reason this table exists and is the one `TO_MM3` uses.
FITTED = Table(
    name="MM3 (as printed)",
    damage=lambda level: 6.6 + 0.82 * level,
    limited=lambda level: 9.1 + 0.61 * level,
    attack=ATTACK_MM3,
    rank_hp={"standard": 1.0, "elite": 2.0, "solo": 3.4, "minion": 0.0},
)

BOOKS = {"MM1": OLD, "MM2": OLD, "MM3": FITTED, "": OLD}


@dataclass(frozen=True)
class Math:
    """Which maths a fight is played under."""

    name: str
    #: None leaves every row exactly as its book printed it.
    to: Table | None = None

    @property
    def on(self) -> bool:
        return self.to is not None

    def convert(self, expr: str, *, book: str, level: int, kind: str = NORMAL) -> str:
        """Rescale a printed damage expression to the target maths.

        The shape of the expression is kept and its size is changed: `2d8+2`
        stays two eight-sided dice and gains a flat bonus. Keeping the dice
        keeps the spread -- a brute that swings wildly goes on swinging
        wildly -- and moving the flat part is what the revision did anyway.
        """
        if self.to is None:
            return expr
        source = BOOKS.get(book, OLD)
        if source is self.to:
            return expr
        want = self.to.target(level, kind)
        have = average(expr)
        if have <= 0:
            return expr
        return _retune(expr, want - have)

    def describe(self) -> str:
        return self.name


#: As written. Every monster keeps the numbers its book gave it.
AS_PRINTED = Math("as printed")

#: MM1 and MM2 rows rescaled to the MM3 curve the books actually show.
TO_MM3 = Math("MM3 damage", FITTED)

#: The same, on the published design formula. Hits appreciably harder,
#: especially for recharge attacks. Kept because it is somebody's stated
#: intent and worth being able to play.
TO_MM3_PUBLISHED = Math("MM3 damage (published formula)", MM3)

PRESETS = {
    "printed": AS_PRINTED,
    "mm3": TO_MM3,
    "mm3-published": TO_MM3_PUBLISHED,
}

_DICE = re.compile(r"^\s*(\d*)d(\d+)\s*(?:([+-])\s*(\d+))?\s*$", re.I)


def _retune(expr: str, delta: float) -> str:
    """Shift a dice expression's flat part by `delta`, keeping the dice."""
    m = _DICE.match(expr)
    if not m:
        return expr
    count = int(m.group(1) or 1)
    faces = int(m.group(2))
    flat = int(m.group(4) or 0) * (-1 if m.group(3) == "-" else 1)
    flat = max(0, round(flat + delta))
    return f"{count}d{faces}" + (f"+{flat}" if flat else "")
