"""Ranger, level 10: utility. No attack roll anywhere in the level.

`p217` answers the same printed sentence `level_6.py`'s `p748` does, and
declares it the same way: adjacency is derived in exactly one place, so "an
enemy moves adjacent to you" is `AdjacencyGained` with the enemy as the
mover. Its destination is filtered here rather than handed to the decider,
because "you can't end your move adjacent to the triggering enemy" is a
condition on the square and `c.move` picks whatever it likes.

`p926`'s second clause -- an extra square on every shift -- is not written.
`actions.legal` offers a shift from a ring fixed at one square and nothing
reads a modifier there, so there is no such number to raise. See the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Event,
    Keyword,
    Trigger,
    When,
    World,
    distance,
    power,
)
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.movement import walk
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.query import team

MARTIAL = [Keyword.MARTIAL]

_ENEMY_CLOSES = "an enemy moves adjacent to you"


def _enemy_moved_next_to_me(world: World, me: int, ev: Event) -> bool:
    """The *mover* is the enemy and the one it reached is me."""
    mover = getattr(ev, "actor", None)
    if mover is None or getattr(ev, "other", None) != me:
        return False
    return team(world, mover) is not team(world, me)


@power(
    "p217",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_ENEMY_CLOSES,
    on=Trigger(AdjacencyGained, when=_enemy_moved_next_to_me, text=_ENEMY_CLOSES),
)
def p217(c: Cast) -> None:
    c.shift(1)
    foe = getattr(c.trigger, "actor", None)
    held = squares_of(c.world, foe) if foe is not None else frozenset()
    paths = c.world.reachable_paths(c.me, 1 + c.wis_mod)
    away = sorted(
        sq for sq in paths if not any(distance(sq, at) <= 1 for at in held)
    )
    dest = c.choose(away, "p217: where to break off to")
    if dest is not None:
        walk(c.world, c.me, paths[dest])


@power(
    "p718",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p718(c: Cast) -> None:
    """Held for the encounter and ended by hand when the stance ends, the
    arrangement `fighter/level_6.py` settled: a second stance-clocked effect
    confuses `Effects.stance_of`."""
    stance = c.stance(label=c.ref)
    easy = c.ignores_difficult(on=c.me, until=When.ENCOUNTER)
    if easy is not None:
        stance.on_end.append(lambda: c.world.effects.end(easy, "stance ended"))


@power(
    "p926",
    level=10,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p926(c: Cast) -> None:
    """The speed only. The extra square of shift has no number to raise --
    see the file's docstring -- and is left unwritten rather than paid out
    as four more squares of walking, which is a different card."""
    c.bonus("speed", 4, on=c.me, until=When.EONT)
