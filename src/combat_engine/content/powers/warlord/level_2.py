"""Warlord, level 2: utility. Nothing here rolls an attack.

Three of the four hand something to a friend, and each of those printed
lines is a **can** or a **may** -- so the surge and the move are offered
rather than taken, with the useful answer first, because a headless fight
takes the first option on every question it is asked.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    MOVE,
    ONE_ALLY,
    REACTION,
    STANDARD,
    Cast,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    World,
    power,
)
from combat_engine.engine.query import distance_between, team

MARTIAL = [Keyword.MARTIAL]


def _ally_crit_within(squares: int) -> Callable[[World, int, Hit], bool]:
    """An ally -- not you -- within range scored a critical hit.

    Neither shared predicate says this. `ally_within` reads `ev.actor` and
    falls back to `ev.target`, and a `Hit` carries neither of those as the
    creature that landed it: `ev.attacker` is the one who swung. Nothing
    reads `critical` at all, so both halves of the printed line are here.
    Worth moving beside the shared predicates if a second row wants it.
    """

    def check(world: World, me: int, ev: Hit) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or who == me or not ev.critical:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


@power(
    "p1136",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p1136(c: Cast) -> None:
    """An extra saving throw with Charisma behind it.

    A target carrying nothing that saves has nothing to shake off, which is
    a wasteful use rather than something for the row to refuse.
    """
    c.save(bonus=c.cha_mod)


@power(
    "p1137",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
)
def p1137(c: Cast) -> None:
    """A printed "can": the surge is the target's to spend or to keep, so
    the question goes to the target rather than to the warlord."""
    if c.may("spend a healing surge", who=c.target):
        c.surge()


@power(
    "p1139",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p1139(c: Cast) -> None:
    """The ally moves, now, off your action.

    A granted move action could also be spent shifting or standing up;
    walking is the part of it `Cast` can say, so that is what is offered --
    and offered, because "can" means the ally may stay where it is.
    """
    who = c.target
    if c.may("take a move action", who=who):
        c.move(c.speed_of(who), who=who)


_ALLY_CRITS = "an ally within 5 squares of you scores a critical hit"


@power(
    "p1310",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger=_ALLY_CRITS,
    on=Trigger(Hit, when=_ally_crit_within(5), text=_ALLY_CRITS),
)
def p1310(c: Cast) -> None:
    """Temporary hit points to whoever landed the blow.

    The dispatcher only re-aims a row whose printed target is a single
    *enemy*, so "the triggering ally" is read off the event here instead of
    being taken from whatever the targeting picked.
    """
    who = getattr(c.trigger, "attacker", None) or c.target
    c.temp_hp(c.cha_mod, on=who)
