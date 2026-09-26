"""Fighter, level 8: the one utility the later books print at this level.

There is no other row at fighter 8, which is why this file did not exist.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    INTERRUPT,
    ONE_ALLY,
    Cast,
    DamageRolled,
    Keyword,
    Melee,
    Trigger,
    World,
    power,
)
from combat_engine.engine.query import distance_between, team

from .grips import has_shield

_TOOK_A_BLOW = "you or an adjacent ally are dealt damage by an attack"


def _me_or_beside_me(world: World, me: int, ev: DamageRolled) -> bool:
    """`DamageRolled` is the only window where the number is known and not
    yet dealt, which is what "the damage dealt is reduced by" needs.

    "Hits or misses" is not asked: a miss that deals damage still comes
    through here, and one that deals none never reaches this event at all.
    """
    if ev.amount <= 0:
        return False
    if ev.target == me:
        return True
    if team(world, ev.target) is not team(world, me):
        return False
    return distance_between(world, me, ev.target) <= 1


@power(
    "p12677",
    level=8,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.MARTIAL],
    requires=has_shield,
    requires_text="must be used with a shield",
    trigger=_TOOK_A_BLOW,
    on=Trigger(DamageRolled, _me_or_beside_me, _TOOK_A_BLOW),
)
def p12677(c: Cast) -> None:
    dice = f"{3 if c.level >= 21 else 2 if c.level >= 11 else 1}d10"
    c.reduce(c.roll(dice) + c.con_mod, c.trigger)
