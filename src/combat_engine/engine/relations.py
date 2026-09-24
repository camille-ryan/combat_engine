"""Effects that need two creatures to mean anything.

Grabbed, marked, dominated and hidden are not properties of a creature -- `x
is grabbed` is only half a fact, and storing it on `x` alone is how an engine
ends up unable to answer "grabbed by whom" when the grabber is knocked out.

Flanking and combat advantage are deliberately *not* here. Both are computed
from the board on demand, because too many unrelated things grant them and a
stored flag drifts the moment one of them ends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .events import RelationCleared, RelationSet
from .types import Condition, Relation

if TYPE_CHECKING:
    from .ecs import World

#: A relation that also imposes a condition on the creature it is aimed at.
IMPLIES: dict[Relation, Condition] = {
    Relation.GRABBED_BY: Condition.GRABBED,
    Relation.MARKED_BY: Condition.MARKED,
    Relation.DOMINATED_BY: Condition.DOMINATED,
}


class Relations:
    """A set of `(kind, source, target)` triples, kept in insertion order."""

    def __init__(self, world: World) -> None:
        self.world = world
        self._live: dict[tuple[Relation, int, int], None] = {}

    def holds(self, kind: Relation, source: int, target: int) -> bool:
        return (kind, source, target) in self._live

    def sources(self, kind: Relation, target: int) -> list[int]:
        return [s for (k, s, t) in self._live if k is kind and t == target]

    def targets(self, kind: Relation, source: int) -> list[int]:
        return [t for (k, s, t) in self._live if k is kind and s == source]

    def anyone(self, kind: Relation, target: int) -> bool:
        return any(k is kind and t == target for (k, s, t) in self._live)

    def set(self, kind: Relation, source: int, target: int) -> None:
        """Establish the relation.

        A creature can only be marked by one other at a time, so a new mark
        silently displaces the old one rather than stacking with it -- that is
        the printed rule, and it is the only place a relation behaves this
        way.
        """
        if kind is Relation.MARKED_BY:
            for other in self.sources(kind, target):
                if other != source:
                    self.clear(kind, other, target, "superseded")
        if self.holds(kind, source, target):
            return
        self._live[(kind, source, target)] = None
        self._apply_condition(kind, target, +1)
        self.world.bus.emit(RelationSet(kind_=kind, source=source, target=target))

    def clear(self, kind: Relation, source: int, target: int, why: str = "expired") -> None:
        if not self.holds(kind, source, target):
            return
        del self._live[(kind, source, target)]
        self._apply_condition(kind, target, -1)
        self.world.bus.emit(
            RelationCleared(kind_=kind, source=source, target=target, why=why)
        )

    def clear_source(self, kind: Relation, source: int, why: str = "expired") -> None:
        """Drop every relation of one kind that `source` holds over anybody."""
        for k, src, target in list(self._live):
            if k is kind and src == source:
                self.clear(k, src, target, why)

    def forget(self, eid: int, why: str = "left play") -> None:
        """Drop every relation `eid` is either end of."""
        for kind, source, target in list(self._live):
            if source == eid or target == eid:
                self.clear(kind, source, target, why)

    def _apply_condition(self, kind: Relation, target: int, delta: int) -> None:
        from .components import Conditions

        cond = IMPLIES.get(kind)
        if cond is None:
            return
        conds = self.world.get(target, Conditions)
        if conds is None:
            return
        if delta > 0:
            conds.add(cond)
        else:
            conds.remove(cond)
