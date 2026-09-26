"""Ardent, level 2: the utility that lengthens somebody else's reach."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    Cast,
    Keyword,
    Ranged,
    When,
    power,
)


@power(
    "p11066",
    level=2,
    cls="ardent",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.PSIONIC],
)
def p11066(c: Cast) -> None:
    """Both halves are distances rather than numbers on a roll, so both are
    ordinary modifiers -- `dsl.area_of` is what reads them, which means the
    extra square decides what the ally may aim at and not merely what it can
    touch. Untyped, as the card prints no bonus type."""
    c.bonus("reach", 1, until=When.EONT)
    if c.wis_mod > 0:
        c.bonus("range", c.wis_mod, until=When.EONT)
