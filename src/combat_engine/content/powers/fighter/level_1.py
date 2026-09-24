"""Fighter, level 1."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Keyword,
    Melee,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


@power(
    "p997",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p997(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    else:
        # A miss still does something, and a two-handed weapon does more.
        c.flat(c.str_mod if c.wielding("two-handed") else c.str_mod // 2)


@power(
    "p992",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p992(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        # And a second enemy beside you takes the modifier on its own.
        others = [e for e in c.within(1, side="enemy") if e != c.target]
        if others:
            c.flat(c.str_mod, on=c.choose(others, "who else does it catch"))


@power(
    "p1000",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=lambda world, eid: _has_shield(world, eid),
    requires_text="needs a shield",
)
def p1000(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        vacated = c.there
        if c.push(1):
            c.shift(to=vacated)  # step into the space it was driven out of


def _has_shield(world: object, eid: int) -> bool:
    from combat_engine.engine import Gear

    gear = world.get(eid, Gear)  # type: ignore[attr-defined]
    return bool(gear and gear.shield)
