"""What a check has to beat, by level and by how hard the thing is.

**Below every component, for the reason `db.py` and `armour.py` are.** Nothing
here imports anything in `combat_engine` except `db`, so the story engine, the
kernel and the instruments can all read these ninety numbers without any of
them reaching through another.

This lived in `story/dc.py`, and that was the right place for exactly as long
as the campaign runner was the only reader. It is not any more:

* **`#949`'s remaining clause needs a DC in the kernel** -- a creature with no
  swim speed uses a skill to swim, and the printed rule gives a *difficulty*
  rather than a number. `engine -> story` is **zero** imports and
  `.importlinter` holds two contracts naming `combat_engine.story`, so
  `engine/movement.py` reaching into `story/` for this table would open an
  edge from the kernel into the campaign runner, backwards.
* So it is the same shape `armour.py` was: *a table, not behaviour*, with
  readers in more than one component. #334's reasoning, third application.

## It is read, not derived, and now not even transcribed

`story/dc.py` held the ninety numbers as a **hand copy**, with
`scripts/rules.py` reconciling them against the column so a divergence would
go red. `#1001` built that column -- `rules_dc`, 30 rows, extracted by the ETL
from the compendium's own glossary entry for this table:

    select Txt from Glossary where Name = 'Skill Check Difficulty Class'

A glossary entry is mechanical vocabulary -- the ETL deliberately leaves
`Glossary` out of its alias tables for exactly that reason -- so the numbers
are a game system and the tree may hold them, the same way every `printed=` in
`content/` holds a printed number.

**Reading the column retires the copy rather than gating it**, which is the
better of the two. The hand copy is on record as having been wrong in both
directions when it was first written from memory -- *"hard at level 4 is 21
and not 22, and hard at level 30 is 42 and not 48"* -- and the whole class of
that error is gone once nobody transcribes anything.

What the move costs is that `scripts/rules.py` can no longer reconcile a copy
against a column, because there is no copy. So it asks the question one step
further out instead: **does this reader return what the column holds**, for
all ninety cells. That is strictly more than the old check could see -- it
also catches a reader that mis-maps a band or clamps wrongly -- and it is why
the gate did not get deleted along with the duplicate.

## The formula temptation, recorded because it is wrong

Every shape in content today either prints an integer at the call site, rolls
against somebody's passive, or -- twice -- computes `10 + level // 2`. That
last one is a fabrication wearing a table's clothes: the ETL measured the
printed trap DCs and found they are **not a function of level at all**, with
level-1 traps printing anything from 9 to 22 and the per-level median
wandering from level+3.5 to level+18.

The printed sequence is not arithmetic either. Easy goes 8, 9, 9, 10, 10, 11,
11 -- a half-level step with its own rounding -- and hard is not a fixed offset
from moderate, drifting from +7 at level 1 to +10 at level 30. A loop that
reproduced the first six rows would be wrong by three somewhere in paragon and
nobody would notice.

## Precedence belongs to the caller, not to this table

Camille's refinement, asked during planning, 2026-10-31:

> *"The story engine though should firist prefer the DCs present in a module
> before referencing the table."*

So this module answers only *"what does the printed table say"*. A module that
prints its own DC wins, and that precedence is the caller's -- it is already
how `story/beat.py` reads: `chosen.dc or dc_for(level, chosen.band)`. Nothing
here knows about a module, which is the test for whether something belongs
this low.
"""

from __future__ import annotations

from functools import cache

#: The three bands the compendium prints, and the two that the `terrain` and
#: `disease` tables already spell in their `check_band` / `dc_shape` columns.
#:
#: Also the column names in `rules_dc`, which is not a coincidence to rely on
#: quietly: `_table` below indexes the row by this tuple, so a band renamed
#: here without the ETL renaming its column would raise on the first lookup
#: rather than return a neighbouring band's number.
BANDS = ("easy", "moderate", "hard")

#: The printed shape. A table read short is the failure this guards: a
#: reconciliation or a lookup against **three** rows of thirty looks exactly
#: like one against all of them, and `#1001` records the ETL half needing the
#: same assertion for the same reason.
LEVELS = 30


@cache
def _table() -> dict[int, tuple[int, ...]]:
    """`level -> (easy, moderate, hard)`, read once out of `rules_dc`.

    **Lazy and cached rather than read at import**, which is where this
    differs from `armour.py` beside it. Those four numbers are wanted on every
    chargen draw, so paying at import costs nothing and a missing table is a
    loud failure in the one place that matters. These ninety are wanted by two
    narrow paths, and an import-time read would mean a `game.db` built before
    `#1001`'s column existed could not even *import* the package -- taking
    every instrument that would have explained why down with it. Deferring it
    makes a stale database a raise in the caller that asked for a DC, which
    `audit.py` reports as a raise and names.

    The `@cache` has the usual consequence and it is the right trade here: a
    rebuild inside one process is not seen. These are printed numbers that a
    re-import cannot change, and the instruments all run the ETL in a separate
    process from their readers.
    """
    from combat_engine.db import game

    rows = {
        int(row["level"]): tuple(int(row[band]) for band in BANDS)
        for row in game().execute(
            f"SELECT level, {', '.join(BANDS)} FROM rules_dc"
        )
    }
    if len(rows) != LEVELS:
        raise ValueError(
            f"rules_dc holds {len(rows)} of {LEVELS} printed levels, so no DC"
            f" can be trusted -- rebuild the database (`scripts/build.py`)."
            f" See #1001 for the import."
        )
    return rows


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
    row = _table()[min(max(int(level), 1), LEVELS)]
    return row[BANDS.index(band)]
