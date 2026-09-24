"""Warlord, level 7: encounter attacks.

The swing is the same in all four and what differs is what a friend gets out
of it, as at level 3. Every printed "can" is asked, and every pool a friend
is drawn from is sorted so the answer a headless fight takes -- the first
one -- is worth taking.

`p1074` is a `crit_range` modifier rather than anything held on the target,
because the wider range belongs to the attackers and is read at the moment
each of them rolls; the gate on the damage context is what keeps it to this
one creature.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Keyword,
    Melee,
    Position,
    distance,
    power,
    spread,
)

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _friends_within(c: Cast, squares: int) -> list[int]:
    """Allies in range -- "an ally", so never the warlord itself."""
    return sorted(a for a in c.within(squares, side="ally") if a != c.me)


@power(
    "p1074",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1074(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    if foe is None:
        return
    against = lambda ctx: ctx.get("target") == foe  # noqa: E731
    for friend in [c.me, *c.allies()]:
        c.bonus("crit_range", 2, on=friend, when=against)


@power(
    "p1075",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1075(c: Cast) -> None:
    """The combat advantage is printed as part of the granted attack, so it
    is a one-shot grant put on the creature the ally picks rather than a
    standing one -- `once=True` spends it on that swing and no other.

    "A creature of his or her choice" is whatever that ally's own basic
    attack can reach, which for a melee basic is whoever it is standing next
    to; offering the whole board would be offering attacks it cannot make.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    pool = _friends_within(c, 5)
    friend = c.choose(pool, "who takes a free swing") if pool else None
    if friend is None:
        return
    foes = sorted(c.within(1, of=friend, side="enemy"))
    victim = c.choose(foes, "who that ally swings at") if foes else None
    if victim is None:
        return
    c.grants_advantage(on=victim, to=friend, once=True)
    c.grant_attack(
        friend, on=victim, attack_bonus=c.int_mod if c.build("tactical") else 0
    )


@power(
    "p1076",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p1076(c: Cast) -> None:
    """The surge is an Effect line, so it is spent whether the swing landed.

    "You or one ally" puts the warlord in the pool, worst hurt first, and
    the surge is that creature's own so it is the one asked for it.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    pool = sorted(c.within(5, side="ally"), key=lambda a: -c.missing(a))
    who = c.choose(pool, "who spends a healing surge") if pool else None
    if who is not None and c.may("spend a healing surge", who=who):
        c.surge(on=who)


@power(
    "p450",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p450(c: Cast) -> None:
    """The slide names its destination, because the printed line does.

    A free slide of five would wander; this one has to finish adjacent to
    the target, so the square is chosen first and the slide walks to it.
    "Through the target's space" is the one clause that does not survive:
    `step` will not cross an occupied square, so a friend directly opposite
    goes the long way round and may be a square short.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    foe = c.target
    if foe is None:
        return
    beside = spread({c.there}, 1)
    pool = sorted(a for a in c.within(1, of=foe, side="ally") if a != c.me)
    friend = c.choose(pool, "who is repositioned") if pool else None
    if friend is None:
        return
    pos = c.world.get(friend, Position)
    if pos is None:
        return
    room = sorted(
        sq
        for sq in beside
        if sq != pos.square
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and distance(sq, pos.square) <= 5
    )
    where = c.choose(room, "where that ally ends up") if room else None
    if where is not None:
        c.slide(5, on=friend, to=where)
