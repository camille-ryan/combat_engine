"""The printed damage-by-level table, read once.

A table, not behaviour -- the same shape and the same reasoning as
`armour.py`: numbers the book prints, below every component, importing
nothing from the package. It lives here rather than in `engine/` or
`content/` because both want it (`content/terrain.py` for a trap with no
printed damage, the engine for a terrain power) and neither may import the
other.

**Written out rather than generated.** The columns are not arithmetic: the
Normal High column goes `2d6, 2d8, 2d8, 3d6` across the first four bands,
which is neither a dice-count progression nor a die-size one, and the
modifier repeats at `+5` for two consecutive bands while the dice keep
moving. A loop reproducing two rows would be wrong in the third.

**`story/dc.py` is NOT the other half of this table**, and that is worth
stating here because the issue that asked for this assumed it was. `dc.py`
carries revised **per-level** DCs -- level 1 is `(8, 12, 19)` -- where this
table is printed as ten three-level **bands** whose first is `10 / 15 / 20`.
Different numbers and a different shape, from two printings. Pairing them
would key a banded lookup off a per-level one and misalign silently, since
nothing would raise. The two printings do agree on the damage columns for
heroic, which is what makes this half safe to read from either. #982.

Heroic only, deliberately: `MAX_MONSTER_LEVEL` is 13, so `13th-15th` is one
band past anything that can be fielded. The paragon and epic rows are not
here because only one printing of them was to hand and the DC halves of the
two printings demonstrably differ, so the damage halves might too above
heroic. A caller asking above 15 gets a refusal rather than the top row,
because quietly clamping is how a tier cap becomes a wrong number.
"""

from __future__ import annotations

#: `(lowest, highest)` level of each printed band, and the six expressions it
#: prints: Normal low/medium/high, then Limited low/medium/high.
#:
#: Dice carry no spaces, which is the form the rest of the tree uses --
#: `etl.build` strips them out of a printed expression and `c.damage` is
#: handed `"4d8"`.
_BANDS: tuple[tuple[int, int, tuple[str, str, str], tuple[str, str, str]], ...] = (
    (1, 3, ("1d6+3", "1d10+3", "2d6+3"), ("3d6+3", "2d10+3", "3d8+3")),
    (4, 6, ("1d6+4", "1d10+4", "2d8+4"), ("3d6+4", "3d8+4", "3d10+4")),
    (7, 9, ("1d8+5", "2d6+5", "2d8+5"), ("3d8+5", "3d10+5", "4d8+5")),
    (10, 12, ("1d8+5", "2d6+5", "3d6+5"), ("3d8+5", "4d8+5", "4d10+5")),
    (13, 15, ("1d10+6", "2d8+6", "3d6+6"), ("3d10+6", "4d8+6", "4d10+6")),
)

#: The highest level this table answers for. Above it `damage` refuses.
TOP = _BANDS[-1][1]

#: The two kinds of column the table prints, in the book's own words:
#: **normal** is "comparable to a monster's at-will attack", for something
#: that might attack round after round or is relatively minor; **limited**
#: is "comparable to a monster's special powers", for one-time damaging
#: effects or massive damage.
KINDS = ("normal", "limited")
GRADES = ("low", "medium", "high")


def damage(level: int, kind: str = "normal", grade: str = "medium") -> str:
    """The printed expression for a level, a kind and a grade.

    Refuses rather than clamping, for both an unknown word and a level past
    the tier: a caller that asked for epic and silently got the 13th-15th
    row would be quietly under-dealing by a lot, and the mistake would look
    like a balance opinion rather than a missing row.
    """
    if kind not in KINDS:
        raise ValueError(f"kind is one of {KINDS}, not {kind!r}")
    if grade not in GRADES:
        raise ValueError(f"grade is one of {GRADES}, not {grade!r}")
    for low, high, normal, limited in _BANDS:
        if low <= level <= high:
            column = normal if kind == "normal" else limited
            return column[GRADES.index(grade)]
    raise ValueError(
        f"level {level} is outside the printed heroic bands (1-{TOP});"
        " the paragon and epic rows are deliberately absent -- see the"
        " module docstring"
    )


def for_hazard(
    level: int, *, area: bool = False, ongoing: bool = False, elite: bool = False
) -> str:
    """Which column a trap or hazard reads, by the book's own rule.

    The table is useless without this: it prints six expressions and the
    guidance for choosing between them sits in the surrounding prose rather
    than in the table, so a caller left to pick a column would be inventing
    a number again one level up.

        single-shot, single target  ->  limited medium
        single-shot, an area        ->  limited low
        ongoing, single target      ->  normal medium
        ongoing, an area            ->  normal low
        elite                       ->  one grade higher

    `elite` steps the grade rather than the kind, which is what "one column
    up" means when the columns are ordered low, medium, high within a kind.
    A medium already at `high` stays there -- the table prints no fourth
    grade, and refusing would make an elite area hazard unanswerable.
    """
    kind = "normal" if ongoing else "limited"
    grade = "low" if area else "medium"
    if elite:
        grade = GRADES[min(GRADES.index(grade) + 1, len(GRADES) - 1)]
    return damage(level, kind, grade)
