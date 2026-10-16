"""Fighter, level 7: encounter attacks.

Four plain swings and one crowd-puller. `p2177` is the only row with any
judgement in it: the printed pull is conditional on where it can end, so the
destination is named outright rather than left to the decider, and the
damage is read off where the target actually finished.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    When,
    distance,
    power,
    spread,
)
from combat_engine.engine.query import hidden_from

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


@power(
    "p1018",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1018(c: Cast) -> None:
    """The walk is an Effect line, so it is taken whether the swing landed."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    c.move(max(1, c.dex_mod))


@power(
    "p1019",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1019(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    c.bonus(AC, 2 if c.wielding("shield") else 1, on=c.me, kind="power")


@power(
    "p1428",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=-2),
)
def p1428(c: Cast) -> None:
    # **`f2370`'s second benefit, written here rather than laid from the
    # feat.** "When you attack with a power associated with this feat, the
    # power gains the invigorating keyword" -- and a row's keywords are one
    # tuple fixed at import and shared by everybody who holds it, so only
    # this creature's copy can gain one. #550's convention: the row holding
    # the thing is the row that asks.
    #
    # Granted before the attack, because that is when it has to be true:
    # `f758`'s +1 reads the attacking power's keywords during the roll, and
    # the weaponmaster's miss clause asks after. `dsl.keywords_of` folds the
    # grant in; `Power.keywords` would not see it.
    if c.feat("f2370"):
        c.counts_as_keyword(c.ref, Keyword.INVIGORATING, on=c.me,
                            until=When.ENCOUNTER)
    if c.strike():
        c.damage(c.w(3), c.str_mod)


@power(
    "p2177",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=WILL),
)
def p2177(c: Cast) -> None:
    """"Only if it can end the pull adjacent to you" is a named destination.

    A pull of two left to the decider ends wherever it likes, which for
    anything three squares out is still out of reach -- so the square is
    picked first, from the free ones beside the fighter that two steps can
    actually reach, and the pull is skipped entirely when there is none.

    Anything already in reach is left where it is: a pull of nought ends it
    adjacent, which is the whole of what the condition asks, and dragging it
    sideways would be a square it is not owed.

    The damage asks where the target finished rather than assuming the pull
    worked.
    """
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if not c.strike():
        return
    there = c.there
    if not c.adjacent():
        room = sorted(
            sq
            for sq in spread({c.here}, 1)
            if c.world.grid.passable(sq)
            and c.world.grid.occupant(sq) is None
            and distance(sq, there) <= 2
        )
        if room:
            c.pull(2, to=min(room, key=lambda sq: distance(sq, there)))
    if c.adjacent():
        c.damage(c.w(1))


@power(
    "p608",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p608(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.penalty(AC, 2)
