"""Ardent level 2: handing power points to a friend."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    Cast,
    Keyword,
    Melee,
    power,
)


@power(
    "p11067",
    level=2,
    cls="ardent",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.PSIONIC],
)
def p11067(c: Cast) -> None:
    """One or two points, whichever the pool can stand.

    "1 or 2" is a choice the card leaves to the player and giving two is
    the only reason to use the row, so two is taken whenever two are
    there. The ally gets a pool if it had none -- the card does not ask
    whether it is psionic -- and the transfer is over that ally's own
    maximum until the fight ends.
    """
    c.transfer_points(2 if c.points() >= 2 else 1)
