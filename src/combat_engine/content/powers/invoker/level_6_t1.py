"""Invoker, level 6: the daily that moves where your attacks come from."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    ONE_ALLY,
    Cast,
    Keyword,
    Ranged,
    When,
    power,
)


@power(
    "p10265",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p10265(c: Cast) -> None:
    """The proviso -- only while you have line of sight to the ally -- is
    checked where the square is borrowed, so it needs nothing here.

    **The printed restriction is written, and the note below is why it was
    a marker rather than a rounding.** `dsl._lenders` is reached per
    *range kind*, not per row, so a bare borrow let every ranged or area
    attack the invoker makes use the origin -- wider than the card, not
    narrower: a daily and a non-divine attack both got an origin the
    printed line withholds.

    `only=("divine", "at-will", "encounter")` is the card's three words.
    `_lenders` matches them against the row's **keywords and its usage**
    together, and a row satisfying none of them does not borrow -- so a
    divine daily is refused on the usage and an arcane encounter attack on
    the keyword, which is both halves of what the sentence excludes.

    The sibling is `p10203`, which wants a **square** rather than a
    creature -- `Relation.CASTS_FROM` relates two entities and a bare
    square is nobody. That one is still a marker."""
    ally = c.target
    if ally is not None:
        c.cast_from(ally, until=When.ENCOUNTER,
                    only=("divine", "at-will", "encounter"))
