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

from .events import Note, RelationCleared, RelationSet
from .query import immune_to
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
        # "You cannot be marked until the end of your next turn" has to stop
        # the relation, not just the condition it mirrors: clearing the
        # count alone would leave the marker holding a mark over somebody
        # who is not marked, and `resolve` reads the relation for its -2.
        cond = IMPLIES.get(kind)
        if cond is not None and immune_to(self.world, target, cond, source):
            self.world.bus.emit(Note(text=f"{target} cannot be {cond.value}"))
            return
        if kind is Relation.MARKED_BY:
            for other in self.sources(kind, target):
                if other != source:
                    self.clear(kind, other, target, "superseded")
        if self.holds(kind, source, target):
            return
        self._live[(kind, source, target)] = None
        self._apply_condition(kind, target, +1, source)
        self.world.bus.emit(RelationSet(kind_=kind, source=source, target=target))

    def clear(self, kind: Relation, source: int, target: int, why: str = "expired") -> None:
        if not self.holds(kind, source, target):
            return
        del self._live[(kind, source, target)]
        self._apply_condition(kind, target, -1, source, why)
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

    def _apply_condition(
        self,
        kind: Relation,
        target: int,
        delta: int,
        source: int = 0,
        why: str = "expired",
    ) -> None:
        """Move the condition a relation mirrors, and **say so**.

        This wrote onto `Conditions` in silence, so establishing a grab, a
        mark or a domination emitted `RelationSet` and no
        `ConditionApplied` -- and a row declared the obvious way, watching
        `ConditionApplied` for `Condition.GRABBED`, was armed, read right
        and could never fire. Four content docstrings recorded it as
        unfixable from where they sat. Clearing was silent in the same way,
        which the issue reporting this only noticed half of.

        **Guarded on `add`/`remove`, which is what keeps it single-fire.**
        `durations.apply` calls `relations.set` *before* running its own
        `ConditionApplied` loop, so by the time that loop reaches this
        condition `conds.add` returns False and says nothing. Drop the
        guard and every save-ends grab announces itself twice.

        `duration` is deliberately `""` and not a `When`. A relation has no
        duration -- it lasts until it is cleared -- and twelve listeners in
        the tree carry no condition filter and gate on
        `duration == When.SAVE_ENDS.value` instead. Passing a real `When`
        here would wake all twelve on every mark laid in the game. The
        empty string is not a `When` value, and nothing parses this field
        back into the enum.
        """
        from .components import Conditions
        from .events import ConditionApplied, ConditionEnded

        cond = IMPLIES.get(kind)
        if cond is None:
            return
        conds = self.world.get(target, Conditions)
        if conds is None:
            return
        if delta > 0:
            if conds.add(cond):
                self.world.bus.emit(
                    ConditionApplied(
                        source=source, target=target, condition=cond, duration=""
                    )
                )
        elif conds.remove(cond):
            self.world.bus.emit(
                ConditionEnded(target=target, condition=cond, why=why)
            )
