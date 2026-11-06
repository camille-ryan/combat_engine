"""Bard, level 0: the class features."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    YOU_OR_ONE_ALLY,
    Cast,
    CloseBurst,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import ZoneEntered
from combat_engine.engine.query import distance_between, team


def aura_of_healing(c: Cast, *, label: str, uses: int = 2,
                    per_day: int = 0) -> None:
    """The aura, and the minor action anybody standing in it may take.

    **Three printings share this card and none of them can be the others.**
    `p15849` is the bard's own -- *"twice per encounter but only once per
    turn, you or any ally in the aura can use a minor action"*. `f3664b`
    adds *"the aura's healing benefit can be used only once per day"*.
    `f3668b` swaps the bard's `p2339` and takes **its** allowance instead.
    So the differences are the **allowance**, which is why they are
    parameters here and three refs rather than one.

    It lives beside the class power because that is Camille's ruling on
    `#1045`:

    > *"I think A. The class feature should grant the power and point at
    > it."*

    `uses` is a **shared** count, not one per creature: handing the option
    to five allies must not hand out five times the healing.

    **Membership is asked twice, and both are load-bearing.** `c.aura`
    makes a zone, so `ZoneEntered` is what an ally walking in emits and the
    option is handed over then; and standing inside is asked **again** at
    the moment of spending through `c.in_my_aura`, so an ally who walks
    back out still holding the option cannot spend it.

    *"Only once per turn"* is deliberately not marked: the shared pair of
    uses is already the tighter half of the printed limit.
    """
    me = c.me
    aura = c.aura(5, label=label, until=When.ENCOUNTER, on=me)
    left = [uses]
    handed: set[int] = set()

    def spend(who: int) -> None:
        if not left[0] or not c.in_my_aura(who, label=label):
            return
        # The day's allowance, where a printing has one: charged to the
        # aura's owner rather than to whoever is being healed.
        if per_day and not c.spend_per_day(label, per_day):
            return
        left[0] -= 1
        c.surge(on=who, bonus=c.roll("1d6"))

    def offer(who: int) -> None:
        if who in handed:
            return
        handed.add(who)
        c.give(label, spend, on=who, uses=uses, cost=MINOR)

    offer(me)
    for ally in c.allies():
        if distance_between(c.world, me, ally) <= 5:
            offer(ally)

    def walked_in(ev: Any) -> None:
        if ev.zone == aura and team(c.world, ev.actor) == team(c.world, me):
            offer(ev.actor)

    c.watch(ZoneEntered, walked_in, until=When.ENCOUNTER)


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
    """The aura **and** the minor action anybody in it may take. `#1045`.

    **This used to put up the aura alone, arguing a premise that was false
    in this same tree.** It said *"nothing in `Cast` grants an action to
    the occupants of an aura"* -- and `feats/general_r._aura_printing` had
    been doing exactly that, with `c.give(..., on=who, uses=2,
    cost=MINOR)` and a `ZoneEntered` watch for walk-ins, for as long as
    this note claimed otherwise. So two thirds of the printed card was
    missing while the docstring explained why it had to be.

    `content/CLAUDE.md` names that shape: *a docstring arguing the fault is
    fine*. The fix was to read the helper, not to write a facility.

    `aura_of_healing` is that body, moved here beside the class power
    because this is the class power -- Camille's ruling A on `#1045`. The
    two feat printings call it with their own allowances.

    `uses=2` is this printing's *"twice per encounter"*; it carries no
    per-day limit, which is the clause `f3664b` adds."""
    aura_of_healing(c, label=c.ref, uses=2)


@power(
    "p2339",
    level=0,
    cls="bard",
    usage=ENCOUNTER,
    uses=2,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(5),
    target=YOU_OR_ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p2339(c: Cast) -> None:
    """"Twice per encounter, once per round" is `uses` and `once_per_round`.
    `YOU_OR_ONE_ALLY` is one target out of the caster and the allies
    together, which is the printed "you or one ally". The slide happens
    whether or not the surge is spent."""
    if c.may("spend a healing surge"):
        c.surge(bonus=c.cha_mod)
    c.instead_of("slide", lambda: c.slide(1))


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
