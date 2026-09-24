"""The entity-component store.

Deliberately thin. A board holds a dozen creatures, a handful of zones and
some conjurations, which does not justify a framework -- components are
dataclasses in dicts and systems are plain functions that take a `World`.

What the store buys at this size is not speed, it is that a zone, a
conjuration, an aura and a creature are all just entities with different
components, so "everything within 2 squares of a thing" is one query rather
than three special cases.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .events import Bus
    from .grid import Grid
    from .rng import Rng


class World:
    def __init__(self, grid: Grid, rng: Rng, bus: Bus) -> None:
        from .durations import Effects
        from .relations import Relations
        from .scaling import FULL
        from .zones import Zones

        self.grid = grid
        self.rng = rng
        self.bus = bus
        self.round = 0
        #: How much a level is worth. Swap for BOUNDED to flatten the
        #: treadmill; see `engine/scaling.py`.
        self.scaling = FULL
        #: Whose turn it is. None between rounds and before combat starts.
        self.turn: int | None = None
        self._stores: dict[type, dict[int, Any]] = {}
        self._alive: list[int] = []
        self._next = 0
        self.relations = Relations(self)
        self.effects = Effects(self)
        self.zones = Zones(self)
        #: Whoever is playing. Set by the CLI, the API, or a monster brain.
        self.decider: Callable[[int, str, list[Any], str], Any] | None = None

    # -- choices -------------------------------------------------------------

    def decide[T](self, actor: int, kind: str, options: list[T], prompt: str = "") -> T:
        """Ask whoever is playing `actor` to pick one of `options`.

        The engine never decides. With no decider installed it takes the first
        option, which keeps a headless replay deterministic rather than
        arbitrary -- the options are always in sorted order by the time they
        get here.
        """
        if not options:
            raise ValueError(f"{kind}: nothing to choose from")
        if self.decider is None:
            return options[0]
        return self.decider(actor, kind, options, prompt)

    def reachable_paths(self, eid: int, budget: int) -> dict[Any, list[Any]]:
        from .movement import reachable

        return reachable(self, eid, budget)

    def reachable_squares(self, eid: int, budget: int) -> list[Any]:
        return sorted(self.reachable_paths(eid, budget))

    def difficult(self) -> set[Any]:
        """Terrain that costs extra, from the map and from any live zone."""
        return self.grid.difficult | self.zones.difficult_squares()

    # -- shorthands the rest of the engine and every power body call ---------

    def damage(
        self,
        source: int,
        target: int,
        amount: int,
        dtype: Any = None,
        *,
        detail: str = "",
    ) -> int:
        from .resolve import deal_damage
        from .types import DamageType

        return deal_damage(self, source, target, amount, dtype or DamageType.UNTYPED, detail)

    def heal(self, source: int, target: int, amount: int) -> int:
        from .resolve import heal

        return heal(self, source, target, amount)

    # -- entities ------------------------------------------------------------

    def spawn(self, *components: Any) -> int:
        self._next += 1
        eid = self._next
        self._alive.append(eid)
        for c in components:
            self.add(eid, c)
        return eid

    def despawn(self, eid: int) -> None:
        """Take an entity out of play, unwinding everything it was holding up.

        Effects and relations go first. An effect on somebody else that was
        waiting for *this* creature's turn to expire would otherwise wait
        forever, since a creature that has left play never takes another one.
        """
        self.effects.forget(eid, "left play")
        self.relations.forget(eid, "left play")
        for store in self._stores.values():
            store.pop(eid, None)
        if eid in self._alive:
            self._alive.remove(eid)
        self.grid.lift(eid)
        self.bus.off_owner(eid)

    @property
    def entities(self) -> list[int]:
        return list(self._alive)

    # -- components ----------------------------------------------------------

    def add[C](self, eid: int, component: C) -> C:
        self._stores.setdefault(type(component), {})[eid] = component
        return component

    def get[C](self, eid: int, ctype: type[C]) -> C | None:
        return self._stores.get(ctype, {}).get(eid)

    def need[C](self, eid: int, ctype: type[C]) -> C:
        got = self.get(eid, ctype)
        if got is None:
            raise KeyError(f"entity {eid} has no {ctype.__name__}")
        return got

    def has(self, eid: int, ctype: type) -> bool:
        return eid in self._stores.get(ctype, {})

    def drop(self, eid: int, ctype: type) -> None:
        self._stores.get(ctype, {}).pop(eid, None)

    # -- queries -------------------------------------------------------------

    def each[C](self, ctype: type[C]) -> Iterator[tuple[int, C]]:
        """Every entity carrying `ctype`, in spawn order."""
        store = self._stores.get(ctype, {})
        for eid in self._alive:
            if eid in store:
                yield eid, store[eid]

    def having(self, *ctypes: type) -> Iterator[int]:
        for eid in self._alive:
            if all(self.has(eid, c) for c in ctypes):
                yield eid
