"""Artificer, level 10: the utilities."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FREE,
    MINOR,
    ONE_ALLY,
    REF,
    Cast,
    CloseBurst,
    Keyword,
    Ranged,
    SurgeSpent,
    Target,
    Trigger,
    When,
    ally_within,
    power,
)


@power(
    "p10207",
    level=10,
    cls="artificer",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=Target("ally", 1),
    keywords=[Keyword.ARCANE],
    trigger="an ally in range spends a healing surge",
    on=Trigger(SurgeSpent, ally_within(10), "an ally spends a healing surge"),
)
def p10207(c: Cast) -> None:
    """`c.surge_value` is the caster's unless told otherwise, and the
    printed line is the ally's own."""
    ally = getattr(c.trigger, "actor", None)
    if ally is not None:
        c.heal(c.surge_value(of=ally), on=ally)


@power(
    "p4203",
    level=10,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE],
)
def p4203(c: Cast) -> None:
    c.slide(5)
    c.bonus(REF, 4, until=When.EONT)


@power(
    "p7658",
    level=10,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
)
def p7658(c: Cast) -> None:
    """Moving the shield to somebody else is a later minor action of the
    caster's and nothing declares one, so the ward simply lasts the fight."""
    c.bonus(AC, 4, on=c.target, until=When.ENCOUNTER)
    c.bonus(REF, 4, on=c.target, until=When.ENCOUNTER)
