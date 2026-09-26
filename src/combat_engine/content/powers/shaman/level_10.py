"""Shaman, level 10 utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    AreaBurst,
    AttackDeclared,
    Cast,
    CloseBurst,
    Keyword,
    Ranged,
    TurnStart,
    When,
    power,
)

PRIMAL = [Keyword.PRIMAL]


@power(
    "p5402",
    level=10,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PRIMAL,
)
def p5402(c: Cast) -> None:
    c.slide(3)


@power(
    "p5403",
    level=10,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 5),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p5403(c: Cast) -> None:
    """Moving the zone as a move action has no verb, so the zone stays
    where it was put."""
    rocks = c.zone(c.area(), until=When.ENCOUNTER)
    for mate in c.allies():
        for what in (AC, FORT):
            c.bonus(
                what, 2, on=mate, until=When.ENCOUNTER,
                when=lambda ctx, w=mate: w in c.world.zones.occupants(rocks),
            )


@power(
    "p9768",
    level=10,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p9768(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return

    def gift(ev: Any) -> None:
        if getattr(ev, "actor", None) == mate:
            c.temp_hp(c.wis_mod, on=mate)

    c.watch(TurnStart, gift, until=When.ENCOUNTER, on=mate)


@power(
    "p9769",
    level=10,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p9769(c: Cast) -> None:
    """"Until he or she attacks" is not a duration the engine has, so the
    hold is ended by hand off the attack that gives the creature away."""
    who = c.target
    hidden = c.invisible(on=who, until=When.EONT)
    if who is None or hidden is None:
        return

    def reveal(ev: Any) -> None:
        if ev.attacker == who and not hidden.ended:
            c.world.effects.end(hidden, "attacked")

    c.watch(AttackDeclared, reveal, until=When.EONT, on=who)
