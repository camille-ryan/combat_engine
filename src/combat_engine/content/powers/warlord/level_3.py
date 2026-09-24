"""Warlord, level 3: encounter attacks.

The swing is the same in all four; what differs is what a friend gets out
of it. Every printed "can" here is asked rather than assumed, and every
pool a friend is picked from is sorted so that the name a headless fight
takes -- the first one -- is the one worth taking.

Two of the four carry a build rider, which `c.build(...)` can now read, so
the bigger number is paid out where the character earned it.
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
    Condition,
    Keyword,
    Melee,
    When,
    Window,
    power,
)
from combat_engine.engine.events import ForcedMove

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _friends_within(c: Cast, squares: int) -> list[int]:
    """Allies in range -- "an ally", so never the warlord itself."""
    return [a for a in c.within(squares, side="ally") if a != c.me]


def _has_save(c: Cast, who: int) -> bool:
    """Is that ally carrying anything a saving throw could end?"""
    return any(e.when is When.SAVE_ENDS for e in c.world.effects.of(who))


@power(
    "p1065",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1065(c: Cast) -> None:
    """Every ally hits it harder, wherever they are standing.

    No range on the printed line, so the whole side carries it; the gate on
    the damage context is what makes it a bonus against this creature only.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    value = 1 + c.cha_mod if c.build("inspiring") else 2
    against = lambda ctx: ctx.get("target") == foe  # noqa: E731
    for friend in c.allies():
        c.bonus("damage", value, on=friend, when=against)


@power(
    "p1413",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1413(c: Cast) -> None:
    """One step each for as many friends as the build allows.

    Offered to whoever is in somebody's face first: a free square is worth
    most to the ally that wants out of a melee, and worth nothing to the
    one already standing alone.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    pool = _friends_within(c, 5)
    pool.sort(key=lambda a: not c.within(1, of=a, side="enemy"))
    for _ in range(c.int_mod if c.build("tactical") else 1):
        if not pool:
            return
        who = c.choose(pool, "who steps a square")
        if who is None:
            return
        pool.remove(who)
        if c.may("shift a square", who=who):
            c.shift(1, who=who)


@power(
    "p1556",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1556(c: Cast) -> None:
    """The Effect line lands whether or not the swing did.

    "Who can hear you" is a deafened ally being no use to shout at, and an
    ally carrying nothing that saves is a wasted extra save -- so the ones
    with something to shake off are offered first. The save itself is not
    asked about: nobody declines a free one, and the row that already does
    this for a single target does not ask either.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    pool = [a for a in _friends_within(c, 5) if not c.is_(Condition.DEAFENED, on=a)]
    pool.sort(key=lambda a: not _has_save(c, a))
    if pool:
        c.save(on=c.choose(pool, "who shakes something off"))


@power(
    "p158",
    level=3,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p158(c: Cast) -> None:
    """Stand next to the warlord and nothing moves you.

    Both halves of the Effect line are "while adjacent to you", which is
    asked when the attack or the shove happens rather than now -- people
    move, and a bonus fixed at cast time would follow the ally out of the
    huddle it was standing in.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)

    def hold(ev: ForcedMove) -> None:
        if ev.target in c.allies() and c.adjacent(ev.target):
            ev.cancel("p158")

    c.watch(ForcedMove, hold, until=When.EONT, window=Window.BEFORE, label="p158")
    for friend in c.allies():
        c.bonus(AC, 2, on=friend, when=lambda ctx, who=friend: c.adjacent(who))
