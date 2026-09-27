"""Runepriest, level 2: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    REF,
    WILL,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    Ranged,
    When,
    ZoneEntered,
    power,
)

DEFENCES = (AC, FORT, REF, WILL)


@power(
    "p11378",
    level=2,
    cls="runepriest",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ZONE],
)
def p11378(c: Cast) -> None:
    """The zone's bonus is handed out on entry and to whoever is already
    inside; it runs its duration rather than ending when somebody steps out."""
    area = c.area()
    zid = c.zone(area, until=When.EONT, sustain=MINOR)
    for who in [c.me, *c.in_squares(area, side="ally")]:
        c.bonus("attack", 2, on=who, until=When.EONT, kind="power")

    def sharpen(ev: Any, z: int = zid) -> None:
        if ev.zone == z and ev.actor in [c.me, *c.allies()]:
            c.bonus("attack", 2, on=ev.actor, until=When.EONT, kind="power")

    c.watch(ZoneEntered, sharpen, until=When.EONT)


@power(
    "p11379",
    level=2,
    cls="runepriest",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p11379(c: Cast) -> None:
    """The whole Effect is a bonus to one skill check, trained or not."""
    c.note("p11379: +5 to the next untrained skill check, +2 if trained")


@power(
    "p11380",
    level=2,
    cls="runepriest",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p11380(c: Cast) -> None:
    """Printed for a bloodied ally only, so it checks rather than assuming."""
    if not c.bloodied():
        return
    for defence in DEFENCES:
        c.bonus(defence, 5, until=When.EONT, kind="power")


@power(
    "p11381",
    level=2,
    cls="runepriest",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p11381(c: Cast) -> None:
    """The surge is the target's and buys nothing for the target: two other
    allies heal on it. Hurt allies are preferred when picking the two."""
    who = c.target
    if who is None:
        return
    c.spend_surge(on=who)
    near = [a for a in c.within(5, of=who, side="team") if a != who]
    hurt = [a for a in near if c.wounded(a)] or near
    for ally in hurt[:2]:
        c.heal(c.surge_value(of=ally), on=ally)
        c.bonus(AC, 5, on=ally, until=When.EONT, kind="power")
    c.bonus(AC, 5, on=who, until=When.EONT, kind="power")
