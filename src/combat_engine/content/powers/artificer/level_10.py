"""Artificer, level 10: the utilities."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    REF,
    STANDARD,
    Cast,
    CloseBurst,
    Keyword,
    Ranged,
    Summon,
    SurgeSpent,
    Target,
    Trigger,
    When,
    ally_within,
    get,
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
    c.bonus(AC, 4, on=c.target, until=When.ENCOUNTER, kind="power")
    c.bonus(REF, 4, on=c.target, until=When.ENCOUNTER, kind="power")


@power(
    "p4148",
    level=10,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    summon=Summon(speed=5),
)
def p4148(c: Cast) -> None:
    """The printed bonus is to AC and Fortitude only and `Summon.defences` is one
    offset across all four, so the two are handed out in the body instead.

    Dropped: the three minor-action saves an adjacent ally may take, which
    nothing grants a limited number of, and the first-aid command, which is a
    skill check."""
    figurine = c.summon_inline(get(c.ref).summon, at=c.origin)
    if not figurine:
        return
    c.bonus(AC, 2, on=figurine, until=When.ENCOUNTER)
    c.bonus(FORT, 2, on=figurine, until=When.ENCOUNTER)

    def top_up(ev: SurgeSpent) -> None:
        if ev.actor in c.within(1, of=figurine, side="ally"):
            c.heal(c.wis_mod, on=ev.actor)

    c.watch(SurgeSpent, top_up, until=When.ENCOUNTER)
