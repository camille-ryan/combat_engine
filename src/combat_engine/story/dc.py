"""What a check has to beat, by level and by how hard the thing is.

**This table does not exist anywhere else in the project**, and three places
have been waiting on it: `terrain` has 15 rows whose `check_band` reads easy,
moderate or hard with `check_dc` NULL; `disease` has 8 rows with
`dc_shape = 'band'` and both DC columns NULL; and #491 was opened for the first
two. Skill challenges are the third. #791.

## It is read, not derived

Every shape in content today either prints an integer at the call site, rolls
against somebody's passive, or -- twice -- computes `10 + level // 2`. That
last shape is the tempting one and it is wrong: the ETL measured the printed
trap DCs and found they are **not a function of level at all**, with level-1
traps printing anything from 9 to 22 and the per-level median wandering from
level+3.5 to level+18. A formula here would be a fabrication wearing a table's
clothes.

So these are the printed numbers, read out of the compendium's own glossary
entry for this table rather than remembered. Worth saying plainly because the
first draft of this file *was* remembered, and it was wrong in both directions:
hard at level 4 is 21 and not 22, and hard at level 30 is 42 and not 48. The
glossary is in the compendium every contributor already supplies, so this is
re-derivable rather than transcribed from a book:

    select Txt from Glossary where Name = 'Skill Check Difficulty Class'

A glossary entry is mechanical vocabulary -- the ETL deliberately leaves
`Glossary` out of its alias tables for exactly that reason -- so the numbers
are a game system and the tree may hold them, the same way every `printed=` in
`content/` holds a printed number.

## Why it lives here and not in `engine/`

Two reasons, both temporary and both real. A change under `engine/` widens
`audit.py` to all 12,197 rows, which is about forty minutes, and a skill
challenge should not have to pay that. And another session is working in
`engine/` right now.

**#491 is where it belongs** -- as `query.difficulty(level, band)`, reading a
table the ETL imports from that same glossary entry, so nothing is transcribed
at all. When that lands, this module should become a one-line forward to it and
then disappear. It is listed here rather than left implicit so the duplicate is
visible instead of quiet.
"""

from __future__ import annotations

#: The three bands the compendium prints, and the two that the `terrain` and
#: `disease` tables already spell in their `check_band` / `dc_shape` columns.
BANDS = ("easy", "moderate", "hard")

#: `level -> (easy, moderate, hard)`, levels 1-30.
#:
#: Written out rather than generated, which is this project's rule for a row
#: and is the right rule here too: the sequence is not arithmetic. Easy goes
#: 8, 9, 9, 10, 10, 11, 11 -- a half-level step with its own rounding -- and
#: hard is not a fixed offset from moderate, drifting from +7 at level 1 to
#: +10 at level 30. A loop that reproduced the first six rows would be wrong
#: by three somewhere in paragon and nobody would notice.
TABLE: dict[int, tuple[int, int, int]] = {
    1: (8, 12, 19),
    2: (9, 13, 20),
    3: (9, 13, 21),
    4: (10, 14, 21),
    5: (10, 15, 22),
    6: (11, 15, 23),
    7: (11, 16, 23),
    8: (12, 16, 24),
    9: (12, 17, 25),
    10: (13, 18, 26),
    11: (13, 19, 27),
    12: (14, 20, 28),
    13: (14, 20, 29),
    14: (15, 21, 29),
    15: (15, 22, 30),
    16: (16, 22, 31),
    17: (16, 23, 31),
    18: (17, 23, 32),
    19: (17, 24, 33),
    20: (18, 25, 34),
    21: (19, 26, 35),
    22: (20, 27, 36),
    23: (20, 27, 37),
    24: (21, 28, 37),
    25: (21, 29, 38),
    26: (22, 29, 39),
    27: (22, 30, 39),
    28: (23, 30, 40),
    29: (23, 31, 41),
    30: (24, 32, 42),
}


def dc(level: int, band: str = "moderate") -> int:
    """What a check at that level and band has to beat.

    Clamped to 1-30 rather than raising, because a module may name a level
    this engine does not play -- the scope cap is 10 for characters and 13 for
    monsters -- and refusing to run the scene would be a worse answer than
    running it at the nearest level the table holds.

    An unknown band raises, because there are exactly three and a fourth word
    is a typo rather than a judgement. That is the same call `Cast.terrain`
    makes, and for the reason #539 recorded: a gate on a word nothing carries
    reads exactly like a gate that works.
    """
    if band not in BANDS:
        raise ValueError(f"dc(band={band!r}): not one of {', '.join(BANDS)}")
    row = TABLE[min(max(int(level), 1), 30)]
    return row[BANDS.index(band)]
