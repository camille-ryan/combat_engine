"""Swordmage: the second stat block a card prints beside its own.

One row. `p5749`'s stance printed a parry underneath it, and the parry was
written inside the stance as a `Hit` watcher because it had no ref of its
own. It has one now, so the stance keeps only what the stance does and the
parry is the immediate interrupt the card prints.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.cards import active
from combat_engine.engine import (
    DAILY,
    INTERRUPT,
    PERSONAL,
    SELF,
    Cast,
    Hit,
    Keyword,
    Trigger,
    World,
    power,
)
from combat_engine.engine.query import distance_between, team


def _hits_an_ally_beside_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy hits an ally who is adjacent to you"."""
    mate = getattr(ev, "target", None)
    foe = getattr(ev, "attacker", None)
    if mate is None or foe is None or mate == me or foe == me:
        return False
    if team(world, mate) is not team(world, me):
        return False
    if team(world, foe) is team(world, me):
        return False
    return distance_between(world, me, mate) <= 1


@power(
    "p5749b",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.STANCE],
    requires=active("p5749"),
    requires_text="the p5749 power must be active",
    trigger="an enemy hits an ally who is adjacent to you",
    on=Trigger(Hit, _hits_an_ally_beside_me, "an enemy hits an ally adjacent to you"),
)
def p5749b(c: Cast) -> None:
    """A "Special" attack against the enemy's own roll rather than against a
    defence, so it is a bare d20 plus the caster's Intelligence attack bonus
    compared with `result.total`. Beating it turns the blow aside outright,
    which is the interrupt cancelling the `Hit` before damage is rolled.
    """
    ev = c.trigger
    result = getattr(ev, "result", None)
    if result is None:
        return
    if c.roll("1d20") + c.int_ >= result.total:
        c.cancel()
