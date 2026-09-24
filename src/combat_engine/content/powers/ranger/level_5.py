"""Ranger, level 5: the daily attacks.

Two of the four are the two-weapon rows, and both spell their hands out --
the main weapon's dice and the off-hand's are different sizes on one of
them, which is the whole point of that row.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    Ranged,
    UpTo,
    When,
    World,
    power,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _step_beside(c: Cast, who: int, squares_: int) -> None:
    """Aim a shift at a square next to `who`, for the swing that follows.

    The world's shift decider knows nothing about the attack coming after
    it and will happily step out of reach of it.
    """
    beside = squares_of(c.world, who)
    steps = [
        s
        for s in c.world.reachable_squares(c.me, squares_)
        if any(distance(s, f) <= 1 for f in beside)
    ]
    if steps:
        c.shift(squares_, to=steps[0])


@power(
    "p2210",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p2210(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.penalty("attack", 2, until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(3), c.dex_mod)
        c.penalty("attack", 1, until=When.ENCOUNTER)


@power(
    "p86",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p86(c: Cast) -> None:
    """Two swings at the primary, a step, and one more at somebody else.

    The header carries the primary line; the secondary rolls longhand
    because it takes no ability modifier on its damage. Both steps are
    printed as optional and both are aimed at the swing that follows them
    rather than handed to the decider, which would as soon walk out of
    reach of it -- the opening one is what closes the distance, so it is
    only taken when there is distance to close.

    The secondary swing is only offered if the step actually reached: a
    melee weapon does not attack two squares away, and `c.attack` does not
    check reach for you.
    """
    if c.target is not None and not c.adjacent() and c.may("shift", who=c.me):
        _step_beside(c, c.target, 2)
    for hand, dice in (("main", 2), ("off", 1)):
        if c.strike():
            c.damage(c.w(dice, hand=hand), c.str_mod)

    primary = c.target
    pool = [e for e in c.within(3, side="enemy") if e != primary]
    second = c.choose(pool, "who the second attack catches") if pool else None
    if second is None:
        return
    if not c.adjacent(second):
        _step_beside(c, second, 2)
    if c.adjacent(second) and c.attack(c.str_, AC, on=second):
        c.damage(c.w(2, hand="off"), on=second)


@power(
    "p871",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p871(c: Cast) -> None:
    """Two attacks over one or two creatures; the daze is per creature hit.

    Both swings landing on the *same* creature is what buys the slow, which
    is why the conditions wait until the shooting stops rather than being
    applied as each one lands.

    The Special line's move is taken after the attacks -- "before" cannot be
    offered, the body starting after the power is already aimed -- and the
    openings are closed one enemy at a time: `c.no_provoke` with no `from_`
    means the target of the power, not everybody.
    """
    shots = 2 if (c.first and c.last) else 1
    landed = 0
    for swing in range(shots):
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand="off" if swing else "main"), c.str_mod)
    if landed:
        c.dazed()
    if landed == 2:
        c.slowed()
    if c.last and c.may("move", who=c.me):
        for foe in c.enemies():
            c.no_provoke(from_=foe, until=When.EOT)
        c.move(c.speed_of(c.me))


@power(
    "p921",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p921(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(3), c.dex_mod)
