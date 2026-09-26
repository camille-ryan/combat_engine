"""Warlord level 10: handing an ally another action point."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ONE_ALLY,
    REACTION,
    Cast,
    CloseBurst,
    Keyword,
    Miss,
    Trigger,
    ally_within,
    both,
    by_action_point,
    power,
)


@power(
    "p11727",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.MARTIAL],
    trigger=(
        "an ally in the burst misses all targets with an attack made using an "
        "action gained by spending an action point"
    ),
    on=Trigger(
        Miss,
        both(ally_within(5), by_action_point),
        "an ally in the burst misses with an action-point attack",
    ),
)
def p11727(c: Cast) -> None:
    """A second action point that is outside the encounter's limit.

    "Misses **all** targets" is narrowed to one miss: `Miss` is announced
    per target and nothing announces the end of a multi-target attack, so
    the first miss of a burst that also hit something would fire this. The
    in-flight guard keeps it to one payout per attack either way.

    `c.grant_action_point` puts the point in `ActionPoints.free`, which is
    spent before the pool and is cleared by `refresh` -- the printed "if
    the target does not spend it before the end of the encounter, it is
    lost".
    """
    who = getattr(c.trigger, "attacker", None) or c.target
    if who is not None:
        c.grant_action_point(on=who)
