"""Runepriest, level 10: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_ALLY,
    MINOR,
    MOVE,
    ONE_ALLY,
    Cast,
    CloseBurst,
    Hit,
    Keyword,
    Melee,
    When,
    power,
)


@power(
    "p11404",
    level=10,
    cls="runepriest",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p11404(c: Cast) -> None:
    ward = c.target
    if ward is None:
        return

    def feed(ev: Any, w: int = ward) -> None:
        if ev.attacker == w:
            c.temp_hp(5, on=w)

    c.watch(Hit, feed, until=When.ENCOUNTER, on=ward)


@power(
    "p11406",
    level=10,
    cls="runepriest",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p11406(c: Cast) -> None:
    """One named skill, shared at the best bonus in the party: a skill check
    and nothing else."""
    if c.first:
        c.note("p11406: one chosen skill is rolled at the party's best bonus")


@power(
    "p11407",
    level=10,
    cls="runepriest",
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
    once_per_round=True,
)
def p11407(c: Cast) -> None:
    c.slide(4)
