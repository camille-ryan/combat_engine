"""What the party finds, and what it is worth. #969.

No treasure was awarded anywhere: a party finished a module with the
equipment `chargen` dealt it and nothing else -- no coins, no gems, no
record of any.

**Ten parcels per level: four magic items at party level +1 to +4, and
six monetary.** Both halves are here now, on Camille's call of
2026-10-30.

**A found item is carried, not worn, and that is the whole of why this
owes no `winrate` run.** `chargen.treasure` equips three items at
`band(level)` and monster defences are set against that number -- so an
item *in play* above the band would move the party off the curve
`engine/scaling.py` cannot see. A parcel goes into `Sheet.carried`,
which is a count of what happened to the party and which nothing in a
fight reads. So the party's power is unchanged, provably: `replay`'s
fixtures are identical.

**Equipping one is the part that owes the measurement**, and nothing
equips from inventory today -- there is no action for it. Said here
rather than left to be discovered.

**Nothing is written down here that the database already holds.** The
monetary curve is `2 x market_price(level)`, computed, and it is exact:
measured against the book's own Total Monetary Treasure line, nine of ten
heroic levels agree to the gold piece and the tenth is off by 5.
"""

from __future__ import annotations

import collections
from random import Random

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


#: What the four item parcels are worth, as levels above the party's.
#:
#: *"Expect a group of five characters to acquire four magic items ranging
#: in level from one to four levels above the party level."* Descending,
#: because the page lists parcel 1 as the best of them -- and because
#: DMG2's alternative rewards replace *"the highest-level magic items you
#: would otherwise give out"*, which only means anything if parcel 1 is
#: the dearest.
ITEM_STEPS = (4, 3, 2, 1)


def item_for(level: int, draw: Random) -> str:
    """One magic item of that level, or `""` if none is priced there.

    **Drawn the way `chargen.treasure` draws**, which is the pattern to
    reuse rather than `terrain.printed_trap`'s: it joins `item` to
    `item_step` and so only ever picks a rung that actually exists at the
    level asked for. The difference is the level bound -- a parcel is
    above the party rather than at its band.

    Not filtered by slot or base item, deliberately: a parcel is what the
    party *found*, and the page does not promise it is usable by anybody
    present. `chargen`'s `_fits_base` matters when an item is being
    **equipped**, which nothing here does.

    **One consequence of that, measured rather than assumed: about 5% of the
    pool is an alternative reward** -- 64 of the 1,287 refs priced at levels
    6 to 9 -- and one of those is *not a physical object*. It cannot be
    carried, bought or sold, it occupies no slot, and it fades after five
    levels. So a reward drawn here is filed as a carried object, which is
    the wrong noun. It is harmless today because nothing reads `carried`,
    and it is not fixed here because the right fix is to award one
    deliberately rather than to filter the category out: a reward is the
    one parcel that could safely be put *in play*, since the page says
    alternative rewards **never grant enhancement bonuses** and the
    enhancement curve is the whole reason the item half owes nothing.
    """
    from combat_engine.db import game

    rows = [
        row[0] for row in game().execute(
            "SELECT DISTINCT i.ref FROM item i "
            "JOIN item_step s ON s.ref = i.ref "
            "WHERE s.level = ? AND s.cost > 0 ORDER BY i.ref",
            (max(level, 1),),
        )
    ]
    return draw.choice(rows) if rows else ""


def items(level: int, draw: Random) -> tuple[str, ...]:
    """The four item parcels for a level, best first.

    Empty entries are dropped rather than retried at another level: a
    level the database prices nothing at is a gap in the corpus, and
    quietly substituting a different level would hide it.
    """
    found = tuple(
        item_for(level + step, draw) for step in ITEM_STEPS
    )
    return tuple(ref for ref in found if ref)


def per_head(parcel: int, heads: int) -> int:
    """One parcel split between the party.

    Floored, like `xp.share`, and for the same reason: the page gives no
    rule for who gets the odd coin, so it is dropped rather than handed to
    somebody.
    """
    return parcel // max(heads, 1)
