"""Fighter, level 1: the powers that are not at-will."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    When,
    World,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _shield(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.shield)


@power(
    "p289",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL],
    attack=Attack(STR, vs=REF, plus=2),
    requires=_shield,
    requires_text="needs a shield",
)
def p289(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.str_mod)
        c.push(1)
        c.prone()


@power(
    "p1429",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1429(c: Cast) -> None:
    """Hit or miss, you have this creature's measure for the rest of the fight.

    The two outcomes differ only in size, so the bonuses are worked out once
    and the gate is the same lambda either way -- "against *this* creature"
    is what both lines say.
    """
    hit = c.strike()
    if hit:
        c.damage(c.w(2), c.str_mod)
    mark = c.target
    against = lambda ctx: ctx.get("target") == mark  # noqa: E731
    c.bonus("attack", 2 if hit else 1, until=When.ENCOUNTER, on=c.me, when=against)
    c.bonus("damage", 4 if hit else 2, until=When.ENCOUNTER, on=c.me, when=against)
