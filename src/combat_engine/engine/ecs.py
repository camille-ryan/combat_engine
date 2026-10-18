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
        from .monster_math import AS_PRINTED
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
        #: Which edition's monster maths a fight runs on. Swap for TO_MM3 to
        #: rescale Monster Manual 1 and 2 damage; see `monster_math.py`.
        self.monster_math = AS_PRINTED
        #: Where this fight is happening -- "aquatic", "underground". Words
        #: rather than a type, because the engine never needs to know what
        #: any of them mean: a row asks `c.terrain("aquatic")`.
        self.terrain: set[str] = set()
        #: Whose turn it is. None between rounds and before combat starts.
        self.turn: int | None = None
        #: The fight in progress, once one has been made. A back-reference
        #: rather than a lookup, because a power body that summons something
        #: has to put it in the initiative order and had no way to reach it.
        self.encounter: Any = None
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

    def reachable_paths(
        self, eid: int, budget: int, kind: str = "walk", share: bool = False
    ) -> dict[Any, list[Any]]:
        from .movement import reachable

        return reachable(self, eid, budget, kind=kind, share=share)

    def reachable_squares(
        self, eid: int, budget: int, kind: str = "walk", share: bool = False
    ) -> list[Any]:
        """Where `eid` could get to. `kind` prices it as that sort of move.

        The default stays "walk" because the sixteen content sites calling
        this for a shift destination were written against it and changing
        what they ask is not this change's business -- `Cast.shift`, which is
        the one path every one of them actually goes through to *move*, asks
        as a shift.

        `share` offers the squares other creatures are standing in, for a
        mover whose card says it may meld with them. Nothing else changes:
        terrain still blocks and `blocks_entry` still refuses. #527.
        """
        return sorted(self.reachable_paths(eid, budget, kind=kind, share=share))

    def rough(self) -> dict[Any, str]:
        """Every square that costs extra, and what sort of going it is."""
        laid = self.grid.bridged
        out = {sq: kind for sq, kind in self.grid.difficult.items() if sq not in laid}
        for sq, kind in self.zones.difficult_squares().items():
            if sq not in laid:
                out.setdefault(sq, kind)
        # A creature that shares its square makes that square rough for
        # whoever steps in. Read live rather than written into `grid.difficult`
        # once, because the square is wherever the creature is now.
        for sq in self._shared_squares():
            out.setdefault(sq, "shared")
        return out

    def _shared_squares(self) -> set[Any]:
        """Every square a share-space creature is standing in."""
        return set(self._shared_by())

    def _shared_by(self) -> dict[Any, int]:
        """Every shared square, **and which creature makes it rough.**

        `rough()` labels these the literal `"shared"` and throws the
        occupant away, which is what five rows printing "ignores difficult
        terrain related to <a kind of creature>" were blocked on -- all five
        docstrings said "nothing records who put it there", and the answer
        was in hand one line earlier. #659.

        Last writer wins where two share-space creatures overlap, which is
        unprintable on any card in the corpus and so is not worth a tuple:
        the waiver is per-creature and a square made rough by two swarms is
        rough either way for whoever is exempt from only one.
        """
        from .components import Mods
        from .movement import shares_space
        from .query import squares

        out: dict[Any, int] = {}
        for eid, mods in self.each(Mods):
            if not mods.items or mods.total("shares_space_rough", {}) <= 0:
                continue
            if shares_space(self, eid):
                for sq in squares(self, eid):
                    out[sq] = eid
        return out

    def _made_rough_by_something_waived(
        self, eid: int | None, wanted: frozenset[str]
    ) -> bool:
        """Is this the sort of creature the mover is exempt from?

        Two spellings, because the cards print both: a **stat block ref**
        ("difficult terrain that is `m2824`" -- its own kind) and a **type
        word** ("related to spider swarms" -- anybody's). `Ident.ref` is the
        block and `query.kinds_of` is the words.
        """
        if eid is None or not wanted:
            return False
        from .components import Ident
        from .query import kinds_of

        who = self.get(eid, Ident)
        if who is not None and who.ref in wanted:
            return True
        return bool(kinds_of(self, eid) & wanted)

    def difficult(self, for_: int | None = None, kind: str = "walk") -> set[Any]:
        """Terrain that costs extra, from the map and from any live zone.

        With `for_`, the squares that cost extra **for that creature** --
        which is not the same set, because a creature can be at home in one
        kind of going and not another. Applied here rather than at each of
        the three places that charge for movement, so an exemption cannot be
        honoured by some of them and ignored by the rest.

        `kind` is the sort of move being priced -- "walk", "shift" -- and
        picks up the exemptions a creature only has for that sort.
        "Ignores difficult terrain **when it shifts**" is 23 rows, and
        `Movement.ignores` alone could only say it by granting the exemption
        for walking as well.
        """
        rough = self.rough()
        if for_ is None:
            return set(rough)
        from .components import Movement

        moves = self.get(for_, Movement)
        if moves is None:
            return set(rough)
        ignored = moves.ignores | moves.ignores_when.get(kind, set())
        if "*" in ignored:
            return set()
        # **Provenance, which is a different question from the label.** Five
        # rows print "ignores difficult terrain related to <a sort of
        # creature>" -- its own kind, or anybody's spider. A shared square
        # is the only kind of rough ground that has a maker, so the waiver
        # is scoped to the squares `rough()` labelled `"shared"`: a forest
        # square that happens to have a swarm standing in it was labelled
        # `forest` and is still difficult for the forest's reason. #659.
        made = self._shared_by() if moves.ignores_made_by else {}
        if not ignored and not made:
            return set(rough)
        return {
            sq
            for sq, kind_ in rough.items()
            if kind_ not in ignored
            and not (
                kind_ == "shared"
                and self._made_rough_by_something_waived(
                    made.get(sq), moves.ignores_made_by
                )
            )
        }

    # -- shorthands the rest of the engine and every power body call ---------

    def damage(
        self,
        source: int,
        target: int,
        amount: int,
        dtype: Any = None,
        *,
        detail: str = "",
        dtypes: Any = (),
    ) -> int:
        from .resolve import deal_damage
        from .types import DamageType

        return deal_damage(
            self, source, target, amount, dtype or DamageType.UNTYPED, detail,
            dtypes=dtypes,
        )

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

    def components_of(self, eid: int) -> list[Any]:
        """Every component this entity carries.

        For copying a creature onto another board without knowing what it is
        made of -- `engine/threat.py` measures a creature on a board of its own
        and a list of component types kept by hand would silently omit whatever
        was added after it was written. A component is plain data, so copying one
        is safe; copying a *world* is not, because bus subscriptions close over
        the world they were made against.
        """
        return [store[eid] for store in self._stores.values() if eid in store]

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
