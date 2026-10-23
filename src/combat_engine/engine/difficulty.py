"""The printed Skill Check Difficulty Class table, by level and band.

4e prints a great many checks as a **named difficulty** rather than a
number -- "an Endurance check (moderate DC)", "Athletics check (hard DC)" --
against one table of Easy/Moderate/Hard DCs by level. Two extractions store
the band and leave the number null for want of it: `terrain.check_band` on
15 rows, and `disease.dc_shape = 'band'` on 8. #491.

**Read off the compendium, not recalled.** `Glossary` entry 384, *Skill
Check Difficulty Class*, `Type = 'Rules Table'`, published in the Dungeon
Master's Guide p.42 and the Rules Compendium p.126. That matters because
this table has been got wrong here before from memory, and the DMG's first
printing used a different one -- the numbers below are the revised table the
Rules Compendium reprints, which is what the compendium carries.

Held as a literal rather than extracted into `game.db`, for the reason
`monster_math` holds `OLD` and `FITTED`: it is a printed rules table that
the engine applies, not data about any one row. Extracting it would be the
more principled route and costs a rebuild; if that happens, this becomes the
reader over it and the numbers move out.

**Not a curve.** The bands do not step uniformly -- easy gains 16 over 29
levels, hard gains 23, and neither increments every level -- so a formula
fitted to the endpoints is wrong in the middle. The table is the rule.
"""

from __future__ import annotations

#: Level -> (easy, moderate, hard). Levels 1-30, as printed.
DCS: dict[int, tuple[int, int, int]] = {
    1: (8, 12, 19),    2: (9, 13, 20),    3: (9, 13, 21),
    4: (10, 14, 21),   5: (10, 15, 22),   6: (11, 15, 23),
    7: (11, 16, 23),   8: (12, 16, 24),   9: (12, 17, 25),
    10: (13, 18, 26),  11: (13, 19, 27),  12: (14, 20, 28),
    13: (14, 20, 29),  14: (15, 21, 29),  15: (15, 22, 30),
    16: (16, 22, 31),  17: (16, 23, 31),  18: (17, 23, 32),
    19: (17, 24, 33),  20: (18, 25, 34),  21: (19, 26, 35),
    22: (20, 27, 36),  23: (20, 27, 37),  24: (21, 28, 37),
    25: (21, 29, 38),  26: (22, 29, 39),  27: (22, 30, 39),
    28: (23, 30, 40),  29: (23, 31, 41),  30: (24, 32, 42),
}

#: The three printed words, in the order the table's columns run. The
#: compendium spells them lower case in `terrain.check_band`.
BANDS: tuple[str, ...] = ("easy", "moderate", "hard")


def difficulty(level: int, band: str) -> int | None:
    """The printed DC for that level and band. `None` if either is unknown.

    **Returns `None` rather than guessing**, and the two ways that happens
    are different and both real:

    * an unrecognised band -- the compendium prints "easy", "moderate" and
      "hard" and nothing else, so anything else is a parse fault upstream
      and inventing a number would bury it;
    * a missing level. The 8 band-shaped diseases have `level IS NULL` as
      well as a null DC, so this table cannot resolve them on its own and
      saying so is the honest answer. The terrain rows carry
      `attack_level` and can be resolved.

    Levels outside 1-30 clamp, because a row may carry a level this table
    does not print and the nearest printed row is the only defensible
    answer -- there is no level 0 or 31 column to read.
    """
    if not isinstance(level, int):
        return None
    word = (band or "").strip().lower()
    if word not in BANDS:
        return None
    return DCS[min(30, max(1, level))][BANDS.index(word)]
