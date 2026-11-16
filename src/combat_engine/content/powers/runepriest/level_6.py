"""Runepriest, level 6: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_ALLY,
    REF,
    STANDARD,
    WILL,
    YOU_AND_EACH_ALLY,
    YOU_OR_ONE_ALLY,
    AdjacencyLost,
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
    target=YOU_AND_EACH_ALLY,
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
    """**"...or until you aren't adjacent" is written now.** The old
    note said "nothing ends an effect on a distance", and `AdjacencyLost`
    is the event for exactly that -- emitted twice, mirrored, "so either
    creature can answer it". `p8238` ends its own effect on a `Moved` in
    the same way; this is the narrower version, which does not have to ask
    where anybody went.

    All four bonuses end together, because the printed line is one
    duration over one effect rather than four that happen to agree.
    """
    mate = c.target
    held = [
        c.bonus(defence, 2, until=When.EONT, kind="power")
        for defence in DEFENCES
    ]
    if mate is None:
        return

    def parted(ev: AdjacencyLost) -> None:
        if {ev.actor, ev.other} != {c.me, mate}:
            return
        for one in held:
            if one is not None:
                c.world.effects.end(one, "the ally stepped away")

    for one in held:
        if one is not None:
            one.subs.append(c.world.bus.on(AdjacencyLost, parted))
            break


@power(
    "p15991",
    level=6,
    cls="runepriest",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=YOU_OR_ONE_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p15991(c: Cast) -> None:
    """Hit points equal to a surge, but no surge is spent."""
    who = c.target
    if who is None:
        return
    c.heal(c.surge_value(of=who), on=who)
    c.bonus("save", 2, on=who, until=When.EOTNT, kind="power")
