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
        #: How many milestones the party has reached **today**, not in this
        #: fight. Camille's ruling on #666: *"An adventuring day consists of
        #: 4-5 encounters, and a milestone is every two encounters."*
        #:
        #: On the `World` rather than on a component because it is a fact
        #: about the day, not about a creature -- every character in the
        #: party has reached the same number of them, and a fight fielded on
        #: its own has reached none, which is what 0 means. Whoever fields
        #: the encounter sets it: `api/day.py` from the legs already
        #: finished, `scripts/fight.py --milestones` by hand.
        #:
        #: Read through `c.milestone()`; no row should touch this directly.
        self.milestones = 0
        #: The fight in progress, once one has been made. A back-reference
        #: rather than a lookup, because a power body that summons something
        #: has to put it in the initiative order and had no way to reach it.
        self.encounter: Any = None
        #: The `OpportunityWindow` currently open, or None. Live state about
        #: the fight in progress, like `turn` and `encounter` above.
        #:
        #: It exists so `resolve.attack` can say **what provoked** an
        #: opportunity attack. The chain is: a window opens knowing the ref,
        #: the move kind and the mode -> a controller answers -> somebody
        #: swings -> `resolve.attack` builds a context that used to carry
        #: `opportunity=True` and nothing else about the provocation.
        #: Threading it through every taker would touch each call site; one
        #: field here keeps the knowledge in one place.
        #:
        #: **It cannot go stale, and that is structural rather than
        #: careful.** All three emitters are a plain synchronous
        #: `bus.emit(...)` and the window is a `Decision` -- the controller
        #: takes the swing *inside* that call -- so the field is set and
        #: cleared around one function call in a `finally`. `#880` deferred
        #: itself over the risk of a stale provocation reading as a working
        #: narrowing, and the synchronous emit is what removes it: nothing
        #: can observe this outside the emit, even if a listener raises.
        #:
        #: Read through the attack context, never directly from a row.
        self.provocation: Any = None
        #: What each row has already done once on this board. Read and
        #: written only through `Cast.latch`.
        #:
        #: **It is here because the obvious home is unsound.** Ten content
        #: rows kept this in a module-level dict keyed on `id(world)` --
        #: "keyed on the world so a second encounter arms its own watch",
        #: as `powers/assassin/level_0.py` put it. CPython hands a
        #: collected object's address to the next one allocated, and
        #: nothing ever removed an entry, so a latch outlived its board and
        #: the next `World` at that address read it as its own. Measured:
        #: 48 audit boards produced **45 distinct ids**, and 3 of them
        #: landed on an id already in the store.
        #:
        #: A set on the world cannot go stale, because it dies with the
        #: board it describes -- the same argument `items/weapon.py` makes
        #: for its `_range_pushed` latch, and the same one `#262` reached
        #: for `policy.threat`, which needs a `clear()` called by hand
        #: precisely because its caches are not here.
        #:
        #: A **balanced** guard -- added and discarded in a `finally`, as
        #: `falling._FALLING` and `monsters/level_13/misc_sa._ECHOING` are
        #: -- is sound on `id(world)` and deliberately left alone: its
        #: entry exists only while that world is live, and a live object's
        #: address is not reused.
        self.latches: set[Any] = set()
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
            # **A blanket waiver takes the imposed squares with it**, and
            # that is a ruling rather than an accident of line order. A
            # creature that crosses difficult terrain for nothing crosses
            # *this* for nothing: what a row imposes through
            # `Movement.harder` is difficult terrain, and the waiver is
            # written against the category and not against a cause. Reading
            # it the other way would make the newest verb in the engine
            # quietly beat every sure-footed feat in it. #831.
            return set()
        imposed = self._imposed_on(for_, moves)
        # **Provenance, which is a different question from the label.** Five
        # rows print "ignores difficult terrain related to <a sort of
        # creature>" -- its own kind, or anybody's spider. A shared square
        # is the only kind of rough ground that has a maker, so the waiver
        # is scoped to the squares `rough()` labelled `"shared"`: a forest
        # square that happens to have a swarm standing in it was labelled
        # `forest` and is still difficult for the forest's reason. #659.
        made = self._shared_by() if moves.ignores_made_by else {}
        if not ignored and not made:
            return set(rough) | imposed
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
        } | imposed

    def _imposed_on(self, for_: int, moves: Any) -> set[Any]:
        """Squares that are rough for this creature and for nobody else.

        Two sources, because the cards come in two shapes:

        * `Movement.harder_everywhere` -- "treats **all squares** as
          difficult terrain". Materialised here rather than at write time so
          a board where nothing imposed it pays nothing; `difficult` is
          called once per square examined during a move search.
        * a live `Zone` naming this creature in `difficult_for` -- "squares
          in the aura are difficult terrain **for that enemy**". On the zone
          because the area follows a creature and `Zones.refresh` already
          re-centres it, where a square set copied onto the burdened
          creature would be a snapshot.

        **Added after the waiver filter and never through it.** The filter
        asks what sort of going each square is, and an imposed square is
        rough for no reason the ground knows -- so a narrow waiver like
        "ignores difficult terrain that is mud" has nothing to match on and
        correctly does not touch it. Only the blanket `"*"` waiver reaches
        it, and that is settled by its caller. #831.
        """
        out: set[Any] = set()
        for _eid, zone in self.zones.all():
            if for_ in zone.difficult_for:
                out |= zone.squares
        if moves.harder_everywhere:
            out |= {
                (x, y)
                for x in range(self.grid.width)
                for y in range(self.grid.height)
            }
        return out

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
