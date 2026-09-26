"""Warlord level 2: the action-point bounty on one enemy."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    EACH_ALLY,
    ENCOUNTER,
    FREE,
    Cast,
    CloseBurst,
    Hit,
    Keyword,
    Trigger,
    When,
    by_me,
    power,
)


@power(
    "p11605",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.MARTIAL],
    trigger="an enemy is hit by your attack",
    on=Trigger(Hit, by_me, "an enemy is hit by your attack"),
)
def p11605(c: Cast) -> None:
    """+2 to an ally's attack roll, but only on a swing bought with an action
    point and only against the enemy you just hit.

    `ctx["action_point"]` is true for the whole turn the point was spent on
    -- `resolve.spent_action_point` explains why -- so this is wider than
    the card by the rest of that turn's attacks.

    Fired by hand with no trigger the bounty has no enemy named, and the
    gate then asks only for the action point; that is the auditor's board
    rather than a printed reading.
    """
    if c.target is None or not c.can_see(c.target):
        return
    foe = getattr(c.trigger, "target", None)

    def bought(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("action_point")) and (foe is None or ctx.get("target") == foe)

    c.bonus("attack", 2, kind="power", until=When.EONT, when=bought)
