"""Invoker, level 7: the encounter attack that shortens the target's sight."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    WIS,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Ranged,
    When,
    power,
)


@power(
    "p2870",
    level=7,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p2870(c: Cast) -> None:
    """A cap on sight rather than blindness: everything further off than
    three squares is unseen by the target, so those creatures have combat
    advantage against it while it lasts."""
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        c.sight_range(3, until=When.EONT)
