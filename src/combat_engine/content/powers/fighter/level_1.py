"""Fighter, level 1."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Keyword,
    Melee,
    power,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.query import squares as squares_of

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


@power(
    "p1758",
    level=1,
    cls="fighter",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=2),
)
def p1758(c: Cast) -> None:
    """No ability modifier on the damage: the +2 to hit is what it buys."""
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1))


def _has_shield(world: object, eid: int) -> bool:
    from combat_engine.engine import Gear

    gear = world.get(eid, Gear)  # type: ignore[attr-defined]
    return bool(gear and gear.shield)


# -- encounter --------------------------------------------------------------


@power(
    "p1004",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1004(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.prone()


@power(
    "p1008",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1008(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.slowed()
        # Slowed leaves shifting alone, so the second half of the line is a
        # real extra. Immobilised would stop walking too and is the wrong card.
        c.note(f"p1008: {c.target} also could not shift until the end of your next turn")


@power(
    "p1015",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1015(c: Cast) -> None:
    """Two swings at two creatures, and the step is what joins them.

    The header carries the primary line, which is what a policy reads; the
    secondary rolls longhand because it has its own bonus.

    The shift is aimed rather than handed to the world's shift decider, which
    knows nothing about the swing that follows and will happily walk out of
    reach of it. The second creature is picked first, from anything a single
    step can reach, and the step goes to a square beside it. The shift is
    printed as optional, so standing still is allowed when the follow-up is
    already in reach.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    primary = c.target
    pool = [e for e in c.within(2, side="enemy") if e != primary]
    second = c.choose(pool, "who the follow-up catches") if pool else None
    if second is None:
        c.shift(1)  # the step is granted whether or not there is a second swing
        return
    if not c.adjacent(second):
        beside = squares_of(c.world, second)
        steps = [
            s
            for s in c.world.reachable_squares(c.me, 1)
            if any(distance(s, f) <= 1 for f in beside)
        ]
        if steps:
            c.shift(1, to=steps[0])
    if c.attack(c.str_ + 2, AC, on=second):
        c.damage(c.w(1), c.str_mod, on=second)


@power(
    "p1427",
    level=1,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1427(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        # "An ally of yours": the caster is not one of them.
        friends = [a for a in c.within(1, of=c.target, side="ally") if a != c.me]
        if friends:
            c.shift(2, who=c.choose(friends, "who gets clear"))


# -- daily ------------------------------------------------------------------


@power(
    "p1431",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.HEALING, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p1431(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.surge(on=c.me)


@power(
    "p1524",
    level=1,
    cls="fighter",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p1524(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
