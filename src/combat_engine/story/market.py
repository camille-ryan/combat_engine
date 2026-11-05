"""Spending a party's coin: a price, a purchase and a sale.

`#1081`. `Sheet.coins` has accumulated since `#969` -- six monetary parcels
a level, measured at 1,996 of 2,000 gp over nine fights at level 5 -- and
nothing in the tree could spend one. `#969`'s own note called that honest
rather than finished: *"Nothing spends the coins. An economy wants rituals
(#453) and a market; a visible number that cannot be spent is honest,
awarding nothing was not."* Rituals landed with `#453`. This is the market.

## The printed rule, which contradicts what `#1081` asked for

`#1081` wanted *"a stock list, because **everything at my level** is not a
shop"*, and said *"the printed guidance for what a town stocks is worth
reading before inventing a rule"*. It was, and there is no such guidance to
read. The page, verbatim:

> *"You can sometimes buy magic items just as you can mundane equipment.
> It's rare to find a shop or a bazaar that routinely sells magic items,
> except perhaps the lowest-level items. [...] Your DM might say that you
> can track down a seller for the item you want to buy or that you might
> have to do some searching, but **in general you can buy any item you can
> afford.**"*

So the printed constraint on a purchase is **money and nothing else**. The
shop rarity is the DM's colour -- *"might say"*, *"might have to do some
searching"* -- not a rule with a table behind it, and the one concrete thing
the sentence offers (*"except perhaps the lowest-level items"*) is hedged
with "perhaps" and names no level.

A stock list is therefore an **invention**, and inventing one here would put
a number this project did not read off a page in front of every purchase.
This module does not have one. `rungs()` exposes what the database prices so
a caller that wants to offer a *selection* can narrow it however a scene
likes; the market itself refuses only what cannot be afforded.

Recorded at this length because the issue asked for the opposite and a later
reader will wonder whether the stock list was forgotten. It was read for and
is not there.

## Selling is one-fifth, and that is printed

> *"The sale price of a magic item, or the value of residuum you get from
> disenchanting it, is only one-fifth the normal price of the item. That
> means selling an item gives you enough money or residuum to buy or enchant
> an item that's five levels lower than the original item."*

The second sentence is the useful check on the first: the printed price
curve multiplies by **five** every five levels -- `i1001` runs 680, 3,400,
17,000, 85,000 at levels 3, 8, 13, 18 -- so a fifth of an item's price is
exactly the price of the rung five levels below it. The arithmetic agrees
with the sentence, which is why `SALE` is held as the divisor rather than as
a table of sale prices.

## What is deliberately not here

**Equipping.** A bought item goes into `Sheet.carried`, exactly as a found
one does, and nothing wears it. That is `#1081`'s third part and it is the
one that **owes a `winrate` run both ways**: `#969` carried its items rather
than wearing them precisely because a worn item off the `band(level)` curve
moves what monster defences are set against. Buying does not change that
question and must not be the thing that answers it by accident.

**A reason not to hoard**, which is `#1081`'s fourth part and a design
question rather than a printed one.

**A `setup` scene kind.** `#942` called it *"nearly free"* on the assumption
that shopping existed; `#1081` is the correction. With this module it is
thin, and it is still `#942`'s work rather than this file's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from combat_engine.story import Sheet

#: What a sale returns, as a divisor of the market price. *"Only one-fifth
#: the normal price."* The same number covers disenchanting, which the
#: printed sentence treats as the same transaction.
SALE = 5


def rungs(ref: str) -> tuple[tuple[int, int], ...]:
    """Every priced rung of an item, as `(level, cost)` ascending.

    An item is not one price. `item_step` holds a row per rung -- `i1001`
    has six, levels 3 to 28 -- so *"the price of this item"* is not a
    question with one answer and a caller has to say which rung it means.
    1,853 refs are priced, 470 of them at a single rung.

    Empty for an unpriced ref, which includes every mundane item and every
    ref that is not an item at all. A caller must read that as **not for
    sale** rather than as free.
    """
    from combat_engine.db import game

    return tuple(
        (int(row["level"]), int(row["cost"]))
        for row in game().execute(
            "SELECT level, cost FROM item_step"
            " WHERE ref = ? AND cost > 0 ORDER BY level",
            (ref,),
        )
    )


def price(ref: str, level: int = 0) -> int:
    """What one rung costs, in gold pieces. 0 if it is not for sale.

    `level = 0` means the **cheapest** rung, which is the only honest
    default: it is the one a party can afford soonest and the one the
    printed *"except perhaps the lowest-level items"* is about. Naming a
    level takes that rung exactly, and a level the item has no rung at is
    0 rather than the nearest one -- a +2 sword is not a +3 sword at a
    discount, and rounding to a neighbour would sell a rung the page does
    not price.
    """
    priced = rungs(ref)
    if not priced:
        return 0
    if level <= 0:
        return priced[0][1]
    return next((cost for lvl, cost in priced if lvl == level), 0)


def sale_price(ref: str, level: int = 0) -> int:
    """What selling or disenchanting one rung returns. One-fifth, exactly.

    **Measured: 0 of the 7,533 priced rungs leave a remainder** -- every
    printed price is divisible by five -- so the floor here never actually
    rounds anything and the operator is a guard rather than a policy. It
    stays floored because that is the direction that cannot invent coin if
    a later printing prices a rung at 681, and `drivers.market` asserts the
    census so the day one does is a red run rather than a silent rounding.

    That is also the arithmetic behind the printed gloss *"enough money to
    buy or enchant an item that's five levels lower"*: the curve multiplies
    by five every five levels, so a fifth of a rung **is** the rung five
    levels below it.
    """
    return price(ref, level) // SALE


def buy(sheet: Sheet, ref: str, level: int = 0) -> bool:
    """Spend the coin and carry the item. False if it cannot be bought.

    Two refusals, and they are different kinds of thing:

    * **not for sale** -- no priced rung, so there is no transaction to
      make. Not the same as free, and the case that covers every mundane
      item and every ref that is not an item at all.
    * **not affordable** -- *"in general you can buy any item you can
      afford"* read the other way round, and the only constraint the page
      puts on a purchase.

    There is deliberately no third refusal about **stock**. See the module
    docstring: the page does not have one.

    **Carried, not worn.** This is the same noun `treasure.award` uses and
    for the same reason -- see the module docstring on what equipping would
    owe. A party that buys a sword is holding a sword.
    """
    cost = price(ref, level)
    if cost <= 0 or cost > sheet.coins:
        return False
    sheet.coins -= cost
    sheet.carried[ref] = sheet.carried.get(ref, 0) + 1
    return True


def sell(sheet: Sheet, ref: str, level: int = 0) -> bool:
    """Give up a carried item for a fifth of its price. False if not held.

    Refuses a ref the party is not carrying, which is the one check that
    cannot be skipped: without it a party could sell anything priced and
    the market would mint coin out of the database.

    The count is decremented and the key **dropped at zero**, so `carried`
    stays a record of what is held rather than a history of what was --
    the same convention `afflictions` keeps and for the same reason.
    """
    held = sheet.carried.get(ref, 0)
    if held <= 0:
        return False
    paid = sale_price(ref, level)
    if held == 1:
        del sheet.carried[ref]
    else:
        sheet.carried[ref] = held - 1
    sheet.coins += paid
    return True
