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


#: The party size the printed parcel lists are written for.
PRINTED_FOR = 5


def shares(level: int, heads: int = PRINTED_FOR) -> tuple[int, ...]:
    """The monetary parcels, in the printed descending order.

    Sums to `monetary(level)` exactly for the five characters the printed
    lists are written for. The remainder from the rounding goes on the
    **largest** parcel, where it is proportionally smallest and where a
    reader is least likely to notice a lumpy number.

    **The group-size adjustment reaches the monetary half too, and only
    `parcels_for` used to honour it.** DMG page 125 removes printed parcel
    numbers for a party smaller than five, and parcel 5 is the *first
    monetary* one -- so a party of one has it removed and gets five
    monetary parcels rather than six. `parcels_for` returns item parcels
    only and its own comment said a 5 in the remove list was "honoured
    there rather than here"; nothing honoured it, so the whole level's
    coin still went to a solo character. The page's added parcels are all
    items, so nothing is added here.

    A party larger than five is unchanged, which is why the default moves
    no existing caller.
    """
    total = monetary(level)
    if total <= 0:
        return ()
    cut = [int(total * share) for share in PARCELS]
    cut[0] += total - sum(cut)
    # The page names printed parcel *numbers*; 1 to 4 are the items and 5
    # up are these six, so number `n` is `cut[n - 5]`.
    _add, drop = group_size(heads)
    return tuple(
        money for i, money in enumerate(cut)
        if (i + len(ITEM_STEPS) + 1) not in drop
    )


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
            "WHERE s.level = ? AND s.cost > 0 "
            "AND i.category <> ? ORDER BY i.ref",
            (max(level, 1), REWARD),
        )
    ]
    return draw.choice(rows) if rows else ""


#: The printed category an alternative reward carries in `item.category`.
#: 119 rows hold it, of which 64 are priced at levels 6 to 9 -- 5.0% of
#: that pool. **The issue said 184; that is the compendium's count and the
#: imported number is 119**, the level ceiling accounting for the rest.
REWARD = "Alternative Reward"


def reward_for(level: int, draw: Random) -> str:
    """One alternative reward of that level, or `""` if none is priced. #1020.

    `item_for`'s sibling, and the two partition the pool: this one takes
    the category and that one now excludes it. Before this existed,
    `item_for` drew from everything and about **one parcel in twenty came
    out a reward filed as a carried object** -- which is the wrong noun,
    because the page's rewards are not physical.

    **The filter went in with this draw and not before**, which is the
    ordering `#1020` is explicit about: excluding the category first would
    have removed the 5% and awarded nothing in its place.

    Rewards are priced thinly and unevenly -- 6 refs at level 2, 11 at 5,
    31 at 8, 1 at 11 -- so `""` is a normal answer at some levels and the
    caller falls back to an item rather than pretending.
    """
    from combat_engine.db import game

    rows = [
        row[0] for row in game().execute(
            "SELECT DISTINCT i.ref FROM item i "
            "JOIN item_step s ON s.ref = i.ref "
            "WHERE s.level = ? AND s.cost > 0 "
            "AND i.category = ? ORDER BY i.ref",
            (max(level, 1), REWARD),
        )
    ]
    return draw.choice(rows) if rows else ""


#: How many levels a reward lasts before it fades. The page's own number.
FADES_AFTER = 5


def faded(gained_at: int, level: int) -> bool:
    """Has a reward gained at `gained_at` faded by `level`? #1020.

    Five levels of play and then it goes, which is the page's rule and the
    one thing about a reward that an item has no equivalent of.

    **Unobservable today, and that is stated rather than hidden.** Nothing
    levels a character up yet (`#1013`), so no campaign ever reaches
    `gained_at + 5` and this reader answers `False` for every reward this
    engine has ever awarded. The state is built and the arithmetic is
    right; what is missing is somebody to advance the level. Building it
    now means the fade lands with `#1013` rather than being discovered
    missing after it.
    """
    return level - gained_at >= FADES_AFTER


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


#: What the printed table does to the ten parcels for a party that is not
#: five, by head count. DMG page 125, read in `resources/` -- **and this
#: table's absence was my own wrong claim**, corrected by Camille on
#: `#1021`. I searched for an `N characters` phrase and for the heading in
#: normal case; it is set in small caps and extracts as
#: `charact Er Group sizE and trEasurE parcELs`, so neither search could
#: ever have matched. A failed search is not an absent table.
#:
#: Expressed as the page expresses it: which parcels to **add** (as levels
#: above the party, like `ITEM_STEPS`) and which printed parcel **numbers**
#: to remove. The page names the numbers, so this names them too rather
#: than re-deriving an index -- and the numbers line up with `ITEM_STEPS`
#: exactly, which is a cross-check worth having: parcel 1 is level + 4,
#: 2 is + 3, 3 is + 2, 4 is + 1, and parcel 5 is the first monetary one.
GROUP_SIZE: dict[int, tuple[tuple[int, ...], tuple[int, ...]]] = {
    8: ((3, 2, 1), ()),
    7: ((2, 1), ()),
    6: ((2,), ()),
    5: ((), ()),
    4: ((), (3,)),
    3: ((), (2, 4)),
    2: ((), (1, 2, 4)),
    1: ((), (1, 2, 4, 5)),
}



def group_size(heads: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """`(levels to add, printed parcel numbers to remove)` for a party. #1021.

    Clamped to the printed range rather than extrapolated: the page gives
    one through eight and says nothing about nine, so a larger party is
    treated as eight and a smaller one as one. Extending the pattern would
    be deriving a number the page does not print, which is the rule this
    module's own `market_price` docstring already follows.
    """
    return GROUP_SIZE[max(1, min(8, heads))]


def monetary_only(level: int, heads: int) -> int:
    """The whole level's treasure as coin, per character. Camille's ask.

    > *"let's have somewhere an option to just do monetary treasure. For
    > example: at level 1, it is 144gp per character."*

    144 is exactly what this computes: `monetary(1)` is 720 -- twice a
    level-1 item's market price, which is the printed Total Monetary
    Treasure figure -- and 720 over the five characters the lists are
    written for is 144. So the figure confirms the existing curve rather
    than needing one of its own, which is why there is no new constant
    here.

    **Divided by the real head count, not by five.** A party of four at
    level 1 gets 180 each and the level still pays out 720, which is the
    same reading `per_head` already takes: the level's total is the level's
    total, and who shares it is a different question.

    **Summed from `shares` rather than from `monetary`**, so the two cannot
    disagree: the group-size adjustment removes printed parcel 5 for a solo
    character, and reading the level's total directly would hand a parcel
    over that the page took away.

    Floored, like `per_head` and `xp.share`, and for the same reason: the
    page gives no rule for the odd coin.
    """
    return sum(shares(level, heads)) // max(1, heads)


def parcels_for(level: int, draw: Random,
                heads: int = PRINTED_FOR,
                ) -> tuple[tuple[str, bool, int], ...]:
    """The item parcels, each with whether it is a reward and its step. #1020.

    `(ref, is_reward, step)`, best first, where `step` is how many levels
    above the party the parcel is priced -- `ITEM_STEPS` for the printed
    four and `GROUP_SIZE`'s added ones after them.

    **The step is returned rather than re-derived, because the caller
    cannot re-derive it.** `run.hoard` used to index `ITEM_STEPS` by how
    many parcels it had handed out, which is only right when the returned
    list is the printed four in order. It is not: a level the database
    prices nothing at drops its parcel, and `#1021`'s group-size
    adjustment drops named parcels for a small party and appends extra
    ones for a large one. For a party of four, parcel 3 is removed, so the
    third parcel handed out is printed parcel 4 at `+1` and the old index
    called it `+2`; for a party of eight there are seven parcels against
    four steps and it would have raised `IndexError`. The page replaces **one magic item per
    level** with an alternative reward, and it says which one: the highest
    it would otherwise have given. So parcel 1 -- the `+4` step -- is the
    reward and parcels 2 to 4 stay items. `run`'s own comment at the award
    site already recorded that reading, which is why it is not a guess:
    rewards replace *the highest-level magic items you would otherwise
    give out*, and that only means anything if parcel 1 is the dearest.

    **One per level, replacing rather than adding.** The party gets four
    parcels either way, so this composes with `ITEM_STEPS` and changes no
    total -- which is what makes it safe against the budget the whole
    parcel system is set against.

    **A reward never grants an enhancement bonus**, by the page's own rule,
    which is why this is the one parcel that could later be put *in play*
    without moving the curve `engine/scaling.py` sets monster defences
    against. The item half of `#969` landed carried-and-not-worn precisely
    to avoid that, and owed nothing as a result.

    Falls back to an item when no reward is priced at `level + 4` -- 11 of
    the levels in band price none -- rather than dropping the parcel or
    retrying at another level, both of which would hide a thin spot in the
    corpus. The caller is told which it got.
    """
    # **The printed group-size adjustment, by parcel number.** DMG page
    # 125, and `heads` defaults to the five the lists are written for so
    # every existing caller is unchanged. #1021.
    #
    # The page names parcel *numbers* and `ITEM_STEPS` is in the same
    # order, so `i + 1` is the printed number -- parcel 1 at level + 4
    # through parcel 4 at level + 1. Parcel 5 is the first monetary one,
    # so a `5` in the remove list is `shares`' business and is honoured
    # there; this returns item parcels only.
    add, drop = group_size(heads)
    out: list[tuple[str, bool, int]] = []
    for i, step in enumerate(ITEM_STEPS):
        if (i + 1) in drop:
            continue
        if i == 0:
            got = reward_for(level + step, draw)
            if got:
                out.append((got, True, step))
                continue
        got = item_for(level + step, draw)
        if got:
            out.append((got, False, step))
    # Added after the printed four, in the page's own order, and never a
    # reward: the page says *"add a magic item of level + N"*, and a
    # reward replaces the dearest item rather than an extra one.
    for step in add:
        got = item_for(level + step, draw)
        if got:
            out.append((got, False, step))
    return tuple(out)


def per_head(parcel: int, heads: int) -> int:
    """One parcel split between the party.

    Floored, like `xp.share`, and for the same reason: the page gives no
    rule for who gets the odd coin, so it is dropped rather than handed to
    somebody.
    """
    return parcel // max(heads, 1)
