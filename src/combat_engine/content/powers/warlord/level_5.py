"""Warlord, level 5: the daily attacks.

Two of the three spend the swing on somebody else's turn -- a free save, a
surge all round -- and both of those Effect lines land whether or not the
attack did.

The third is a standing immediate interrupt against walking, and the one
clause here with no vocabulary: `MoveStart` is emitted with no resolution
hanging off it, so cancelling it in the interrupt window stops nothing. It
is written down rather than approximated, as `level_1.py` does.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    Attack,
    Cast,
    Effect,
    Keyword,
    Melee,
    When,
    power,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _squad(c: Cast, squares: int) -> list[int]:
    """"You or one ally within 5 squares" -- the caster is in this pool."""
    return c.within(squares, side="ally")


def _saves(c: Cast, who: int, *, by: int | None = None) -> list[Effect]:
    """What this creature is carrying that a save could end, optionally
    narrowed to the one creature that caused it."""
    return [
        e
        for e in c.world.effects.of(who)
        if e.when is When.SAVE_ENDS and (by is None or e.source == by)
    ]


@power(
    "p1414",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p1414(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    # A walk cannot be stopped from outside it: `movement.walk` announces
    # `MoveStart` and then walks regardless of what the announcement was
    # answered with. Immobilising instead would be automatic rather than a
    # choice, and would stop a shift as well, so it is the wrong card.
    c.note(
        f"p1414: for the rest of the encounter, while adjacent to {c.target}, you could "
        "cancel its walk or run as an immediate interrupt -- not expressible"
    )


@power(
    "p1574",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1574(c: Cast) -> None:
    """Hit and miss both buy a saving throw; they differ in what it may be
    spent on.

    The hit line is any save-ends effect, which is what `c.save` already
    rolls against. The miss line is narrowed to one this creature caused, and
    `c.save` cannot be asked for that, so the effect is picked by hand and
    rolled the same way. Offered to whoever is actually carrying something,
    since a free save against nothing is no gift.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        pool = [a for a in _squad(c, 5) if _saves(c, a)]
        if pool:
            c.save(on=c.choose(pool, "who shakes something off"))
        return

    if victim is None:
        return
    pool = [a for a in _squad(c, 5) if _saves(c, a, by=victim)]
    who = c.choose(pool, "who shakes off something it caused")
    if who is not None and c.may("try to throw it off", who=who):
        c.world.effects.save(_saves(c, who, by=victim)[0])


@power(
    "p1575",
    level=5,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p1575(c: Cast) -> None:
    """"Each ally within 10 squares of you" leaves the warlord out, and the
    surge is a printed *can*, so each of them is asked separately."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    for friend in _squad(c, 10):
        if friend != c.me and c.may("spend a healing surge", who=friend):
            c.surge(on=friend, bonus=c.cha_mod)
