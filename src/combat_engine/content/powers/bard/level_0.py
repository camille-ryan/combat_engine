"""Bard, level 0: the class features."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    SELF,
    Cast,
    CloseBurst,
    Keyword,
    When,
    power,
)


@power(
    "p15849",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
)
def p15849(c: Cast) -> None:
    """Only the aura is put up. The healing printed inside it is a minor
    action *somebody standing in it* takes, twice a fight, and nothing in
    `Cast` grants an action to the occupants of an aura -- a surge spent
    here instead would be the caster's and would happen once."""
    c.aura(5, until=When.ENCOUNTER)


@power(
    "p2339",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    uses=2,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p2339(c: Cast) -> None:
    """"Twice per encounter, once per round" is `uses` and `once_per_round`.
    `ONE_ALLY` already includes the caster, which is the printed "you or one
    ally". The slide happens whether or not the surge is spent."""
    if c.may("spend a healing surge"):
        c.surge(bonus=c.cha_mod)
    c.slide(1)


@power(
    "p2887",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.CHARM],
    out_of_combat=True,
)
def p2887(c: Cast) -> None:
    c.note("p2887: +5 to the next Diplomacy check, before the end of your next turn")
