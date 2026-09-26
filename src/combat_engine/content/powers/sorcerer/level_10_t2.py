"""Sorcerer, level 10: one damage type rolled twice for the fight."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)

#: The ten the card lists, as keywords rather than damage types: a power
#: declares what it is in its header keywords, and that is what the gate can
#: read back off the row that rolled.
_CHOICES = [
    Keyword.ACID,
    Keyword.COLD,
    Keyword.FIRE,
    Keyword.FORCE,
    Keyword.LIGHTNING,
    Keyword.NECROTIC,
    Keyword.POISON,
    Keyword.PSYCHIC,
    Keyword.RADIANT,
    Keyword.THUNDER,
]


@power(
    "p3203",
    level=10,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p3203(c: Cast) -> None:
    """The arcane half of "an arcane power with the chosen keyword" is not a
    second gate here: every row this class can use is arcane, and a narrower
    filter than the card's would be indistinguishable from a broken one.
    `c.maximise` is not a substitute -- a maximum is not a second roll."""
    picked = c.choose(_CHOICES, "damage type")
    if picked is not None:
        c.reroll_damage(keyword=picked, until=When.ENCOUNTER)
