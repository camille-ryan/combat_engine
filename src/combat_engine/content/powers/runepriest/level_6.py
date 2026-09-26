"""Runepriest, level 6: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_ALLY,
    REF,
    STANDARD,
    WILL,
    Cast,
    CloseBurst,
    DamageRolled,
    Keyword,
    Melee,
    When,
    Window,
    power,
)

DEFENCES = (AC, FORT, REF, WILL)


@power(
    "p11390",
    level=6,
    cls="runepriest",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p11390(c: Cast) -> None:
    """The interrupt is an option every time, so it is offered rather than
    taken: `c.may` asks, and `c.absorb` moves the blow before it lands."""
    ward = c.target
    if ward is None:
        return
    c.guard(on=ward)

    def take_it(ev: Any, w: int = ward) -> None:
        if ev.target != w or ev.amount <= 0:
            return
        if c.may("take the damage instead", who=c.me):
            c.absorb(ev, on=c.me)

    c.watch(DamageRolled, take_it, until=When.ENCOUNTER, window=Window.BEFORE)


@power(
    "p11391",
    level=6,
    cls="runepriest",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p11391(c: Cast) -> None:
    """Two skill bonuses and nothing else, and they end the moment anybody
    attacks -- there is no combat effect here to write."""
    if c.first:
        c.note("p11391: +5 to two social skills until somebody attacks")


@power(
    "p11393",
    level=6,
    cls="runepriest",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p11393(c: Cast) -> None:
    """"Or until he or she is no longer adjacent to you" is dropped: nothing
    ends an effect on a distance."""
    for defence in DEFENCES:
        c.bonus(defence, 2, until=When.EONT, kind="power")


@power(
    "p15991",
    level=6,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p15991(c: Cast) -> None:
    """Hit points equal to a surge, but no surge is spent."""
    who = c.target
    if who is None:
        return
    c.heal(c.surge_value(of=who), on=who)
    c.bonus("save", 2, on=who, until=When.EOTNT, kind="power")
