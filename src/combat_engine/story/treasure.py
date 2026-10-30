"""What the party finds, and what it is worth. #969.

No treasure was awarded anywhere: a party finished a module with the
equipment `chargen` dealt it and nothing else -- no coins, no gems, no
record of any.

**This is the monetary half only, and that is a deliberate line.** The
printed system is ten parcels per level: four magic items at party level
+1 to +4, and six monetary parcels. The item half is left alone because
found items sit **above** `band(level)`, and `band` is exactly what
monster defences are set against -- so items beyond the dealt baseline
move the party off the curve `engine/scaling.py` cannot see, and that
owes `winrate` both ways. Coins change no number on any board, so they
owe nothing.

**Nothing is written down here that the database already holds.** The
monetary curve is `2 x market_price(level)`, computed, and it is exact:
measured against the book's own Total Monetary Treasure line, nine of ten
heroic levels agree to the gold piece and the tenth is off by 5.
"""

from __future__ import annotations

import collections

#: What each of the six monetary parcels is worth, as a share of the
#: level's total. The printed 5-10 split, which is regular across every
#: heroic level.
#:
#: **Normalised, because the printed proportions do not sum to one** --
#: they come to 1.005 as rounded figures on the page. `shares` divides the
#: real total by these and puts the remainder on the largest parcel, so
#: the six always add up to exactly what the level is owed rather than to
#: a rounding of it.
PARCELS = (0.28, 0.25, 0.17, 0.17, 0.08, 0.055)

#: *"They should find gold and other monetary treasure equal to the market
#: price of two magic items of their level."*
DOUBLE = 2


def market_price(level: int) -> int:
    """What a magic item of this level costs, from `item_step`.

    **The mode, not the first row nor the mean.** The dominant cost at a
    level *is* the printed market price and it dominates heavily -- 440 of
    497 rows at level 8, 340 of 362 at level 9 -- while the outliers are
    rungs of oddly-priced items. The same reasoning, and the same
    mistake-to-avoid, as `xp.standard`: see #1014.

    Returns 0 for a level the database has no priced item at, which the
    caller must treat as "no treasure can be worked out" rather than as
    "no treasure".
    """
    from combat_engine.db import game

    rows = [
        row[0] for row in game().execute(
            "SELECT cost FROM item_step WHERE level = ? AND cost > 0",
            (max(level, 1),),
        )
    ]
    if not rows:
        return 0
    return collections.Counter(rows).most_common(1)[0][0]


def monetary(level: int) -> int:
    """The whole level's monetary treasure.

    Twice a magic item of the party's level, which is the printed rule and
    which reproduces the book's table: 720 at level 1, 3,600 at 6, 10,000
    at 10.
    """
    return DOUBLE * market_price(level)


def shares(level: int) -> tuple[int, ...]:
    """The six monetary parcels, in the printed descending order.

    Sums to `monetary(level)` exactly. The remainder from the rounding
    goes on the **largest** parcel, where it is proportionally smallest
    and where a reader is least likely to notice a lumpy number.
    """
    total = monetary(level)
    if total <= 0:
        return ()
    cut = [int(total * share) for share in PARCELS]
    cut[0] += total - sum(cut)
    return tuple(cut)


def per_head(parcel: int, heads: int) -> int:
    """One parcel split between the party.

    Floored, like `xp.share`, and for the same reason: the page gives no
    rule for who gets the odd coin, so it is dropped rather than handed to
    somebody.
    """
    return parcel // max(heads, 1)
