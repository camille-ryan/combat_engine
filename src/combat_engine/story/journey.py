"""How far the party gets in a day's travel. #937.

A `rest` scene printed one canned line and a journey had no
representation at all -- Camille, playing: *"No prompt to head out in the
morning, and no prose for the journey."* This is the arithmetic half of
that: how far a party travels, from numbers the page prints and numbers
the engine already holds.

**The tables were read in `resources/` rather than taken from the
issue's quote**, which is this repo's rule about a quoted table, and it
paid twice. The figures were exact -- all 12 cells of the overland speed
table and all three terrain multipliers -- but two claims around them
were wrong, and both changed the design:

* the issue cites *"the DMG, chapter 8"*. The tables are in the
  **Player's Handbook**, and the page defers the over-ten-hours rule to
  the DMG -- so a **forced march is a second table in a second book and
  is still unread**. Nothing here extends into it.
* the issue says `Scene.terrain` can carry the multiplier. It cannot:
  `TERRAIN_WORDS` is the **combat board's** vocabulary -- light levels,
  weather, footing -- and 2 of its 13 words are landscape at all. Hence
  `GOING`, which is its own three-word set. One symbol serving two needs
  is what the root rules file forbids, and for this reason.

## Nothing is written down that the page prints

`DAY_HOURS` and the three multipliers are the only constants here. The
distance itself is **computed from the printed combat speed**, and the
three printed rows come out exactly:

    speed 5    2.5 miles/hour    25 miles/day
    speed 6    3                 30
    speed 7    3.5              35

A point of speed is half a mile an hour because a square is 5 feet and a
round is six seconds: speed 5 is 25 feet a round, 250 feet a minute --
which is the table's own third column -- and 2.5 miles in an hour. So
`MILES_PER_POINT` is a unit conversion rather than a figure to trust, and
`drivers.journey` asserts all three rows and both columns against it.

**That matters because the printed table stops at speed 5 and the corpus
does not.** Measured: of 55 races, speeds run 4, 5, 6 and 7 -- and armour
takes another point off a character wearing chain, plate or scale, so a
real board speed reaches **3**. A table lookup would have had no row for
a third of what this engine can field. Computing from the per-hour law
covers them and reproduces the page where the page speaks.
"""

from __future__ import annotations

#: How long a character can walk in a day without tiring, in hours. The
#: page's own figure, and the reason the day column is what it is.
#:
#: **This is the party's number, not everybody's.** The same paragraph
#: gives ordinary people 6 to 8 hours and a shorter day, which is a rule
#: about NPCs -- a summary of this table dropped that clause, and read
#: without it the smaller figure looks like the party's.
DAY_HOURS = 10

#: Miles per hour per point of speed. A unit conversion, not a printed
#: figure -- see the module docstring for the derivation from a 5-foot
#: square and a six-second round.
MILES_PER_POINT = 0.5

#: How much of the day's distance a landscape costs, by how much of it is
#: difficult terrain. The three printed rows, named by the words that
#: distinguish them rather than by their terrain lists.
GOING = {
    "mostly": 0.5,
    "extensive": 0.75,
    "little": 1.0,
}

#: What a scene means when it says nothing. The page's own `x 1` row, so
#: a module that does not describe its landscape is not silently slowed.
CLEAR = "little"


def miles_per_hour(speed: int) -> float:
    """How far a creature of that speed walks in an hour.

    Reproduces the printed column for speeds 5, 6 and 7, and answers for
    the speeds below it that the page has no row for.
    """
    return max(speed, 0) * MILES_PER_POINT


def miles(speed: int, hours: int = DAY_HOURS, going: str = CLEAR) -> float:
    """How far a party of that pace travels.

    `hours` beyond `DAY_HOURS` is **not** scaled down for fatigue, and
    that is a stated gap rather than an oversight: the rule for travelling
    longer than ten hours is in the other book and has not been read. A
    module asking for sixteen hours gets sixteen hours' distance.
    """
    return miles_per_hour(speed) * max(hours, 0) * GOING.get(going, 1.0)


def pace(board: object) -> int:
    """The slowest speed on a laid board, which is the party's pace.

    *"A group of travellers moves at the slowest traveller's pace"*, so
    this is a `min` and not a mean.

    **Read off the board rather than re-derived**, which is the whole
    reason this takes a `table.Table`. A character's speed is their race's
    **minus their armour** -- `chargen` applies `ARMOUR_SPEED` at spawn,
    and chain, plate and scale each cost a point -- and the page names
    exactly that as why groups are slow, *"to accommodate the group's
    dwarves and heavily armoured members"*. Re-deriving it here from
    `Sheet.race` would drop the armour term, because a `Sheet` does not
    carry armour, and would be a second copy of a rule `chargen` already
    owns.

    `0` when nobody is standing, which the caller must treat as "no pace
    could be worked out" rather than as a party that cannot move.
    """
    from combat_engine.engine.components import Movement

    world = getattr(board, "world", None)
    eids = list(getattr(board, "eids", ()) or ())
    if world is None or not eids:
        return 0
    found = [
        got.speed for got in
        (world.get(eid, Movement) for eid in eids)
        if got is not None
    ]
    return min(found) if found else 0
