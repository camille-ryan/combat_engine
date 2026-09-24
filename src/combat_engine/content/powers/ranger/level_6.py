"""Ranger, level 6: utility.

`p748` is the one that lands on the board. Adjacency is derived in exactly
one place -- `movement.step` diffs who the mover is next to and announces it
-- so "an enemy moves adjacent to you" is `AdjacencyGained` with the enemy
as the mover, declared with `on=` rather than quoted.

`p925` hands an ally a bonus to a skill it is not trained in. The model has
no skills and rolls no checks, so it is inert by declaration.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    SELF,
    Cast,
    Event,
    Keyword,
    Ranged,
    Trigger,
    World,
    power,
)
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.query import team

MARTIAL = [Keyword.MARTIAL]

_ENEMY_CLOSES = "an enemy moves adjacent to you"


def _enemy_moved_next_to_me(world: World, me: int, ev: Event) -> bool:
    """The *mover* is the enemy and the one it reached is me.

    Every step emits the pair both ways round, so reading `actor` alone
    would also answer the ranger walking up to somebody -- which is not what
    the line says.
    """
    mover = getattr(ev, "actor", None)
    if mover is None or getattr(ev, "other", None) != me:
        return False
    return team(world, mover) is not team(world, me)


@power(
    "p748",
    level=6,
    cls="ranger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_ENEMY_CLOSES,
    on=Trigger(AdjacencyGained, when=_enemy_moved_next_to_me, text=_ENEMY_CLOSES),
)
def p748(c: Cast) -> None:
    c.shift(c.wis_mod)


@power(
    "p925",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p925(c: Cast) -> None:
    c.note(f"p925: +{c.wis_mod} to one skill the ranger has and the ally does not")
