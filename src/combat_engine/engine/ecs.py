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
    from .zones import Zone


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
        #: Monotonic, one per attack -- a `Cast` takes the next value the
        #: first time it swings and every target of that use shares it.
        #: `Swung.use` carries it, and the whole reason it is a counter
        #: rather than `id(cast)` is the one `c.once_per_board` records:
        #: CPython reuses a collected object's address.
        self.attacks = 0
        #: How much a level is worth. Swap for BOUNDED to flatten the
        #: treadmill; see `engine/scaling.py`.
        self.scaling = FULL
        #: Which edition's monster maths a fight runs on. Swap for TO_MM3 to
        #: rescale Monster Manual 1 and 2 damage; see `monster_math.py`.
        self.monster_math = AS_PRINTED
        #: **How many fights are left in the day, including this one.**
        #: `policy/doctrine.py` reads it to decide how freely to spend a
        #: daily power -- a character with three fights to come has
        #: reason to hold back and one in the last has none.
        #:
        #: `0` rather than a count, and that keeps the behaviour it had
        #: while stamped: `doctrine` reads it as
        #: `int(getattr(world, "fights_left", DAY) or DAY)`, so a zero
        #: falls through to `DAY` exactly as an absent attribute did.
        #: The only writer is `fight.py --fights`.
        #:
        #: Declared here because it was set with `setattr` on the world
        #: and declared nowhere, so `ty` could not see it and a reader of
        #: `World` could not either. It sits beside `scaling` and
        #: `monster_math` above, which `fight.py`'s own comment already
        #: said it belongs with. `#1278`.
        self.fights_left = 0
        #: Which encounter paradigm built this board -- a word, for the
        #: log to be able to say. Set by `fight.py` off
        #: `story.field_encounter`'s own `paradigm`, and read by nothing
        #: in the engine.
        self.paradigm = ""
        #: Where this fight is happening -- "aquatic", "underground". Words
        #: rather than a type, because the engine never needs to know what
        #: any of them mean: a row asks `c.terrain("aquatic")`.
        #:
        #: **Empty on an arcade board, deliberately, and that is a decision
        #: rather than a gap.** `#1083`/`#539`. The only writer is
        #: `story.run.ground`, from a module scene's `terrain` field, so a
        #: board built straight through `story.field_encounter` -- which is
        #: every arcade fight (`api/session.py`) and every `replay` fixture
        #: -- never gets one. Terrain lives in **modules and only in
        #: modules**.
        #:
        #: Said here because this is the field a reader lands on, and the
        #: alternative was drawing terrain on arcade boards: aquatic and icy
        #: floors change movement, so it re-baselines `winrate`, `scorecard`
        #: and all eight `replay` fixtures, and `#958` makes it owe an
        #: encounter-budget decision too, because a dressed board is harder.
        #: Not worth that to animate clauses the story engine already
        #: reaches. Reversible; nothing here forecloses it.
        #:
        #: **The census, measured, because it has been stated at five
        #: different values across `#1083` and `#539`** -- including once by
        #: me in that issue's own plain-English summary:
        #:
        #:     82  `c.terrain(` call sites under `content/`
        #:     76  of them inside a declared row's own source
        #:     59  declared rows hold one          <- the figure people want
        #:      6  sites in shared helpers, in no row's source
        #:     10  distinct words: aquatic 37, sunlight 31, ice 3,
        #:         darkness 3, snow 2, dim light 2, forest/moonlight/
        #:         starlight/bright 1 each
        #:
        #: Count it off `dsl.REGISTRY` -- rows whose `inspect.getsource`
        #: holds the call -- not with a tree-wide grep. The two answers
        #: differ by the six helper sites, and mixing call sites with rows
        #: is what produced every one of the five wrong numbers.
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
        #: Whether the party is between fights, having just rested --
        #: `"short"`, `"extended"` or `""`.
        #:
        #: **An interval, not the moment `ShortRested` announces.** 26
        #: printed rows carry *"Requirement: you must be taking a short
        #: rest"*, and a requirement is a question asked when the row is
        #: offered, which is never during the one function call that does
        #: the resting. `turns.short_rest` opens it and
        #: `turns.Encounter.start` closes it, which is the sequence
        #: `turns.py`'s own note describes: "`short_rest(world)` and only
        #: then `encounter.start()`".
        #:
        #: Read through `query.resting`. `p9307` and `p11540` both carried
        #: `dropped=("query.resting()",)` for want of it, and both were
        #: being offered in the middle of a fight, which their cards
        #: forbid.
        self.resting: str = ""
        #: Creatures their own **allies** provoke opportunity attacks from,
        #: each mapped to the effects holding that open.
        #:
        #: A dict rather than a set so suspension is readable: the held
        #: effect is the authority, and `durations.suspend` leaves an effect
        #: in place with `suspended` set rather than removing it. A set
        #: would say "yes" for a trait that had been lifted.
        #:
        #: **Here rather than scanned out of `effects`** because the reader
        #: is the per-watcher-per-step branch in `movement.step`, and that
        #: loop's own note records asking each watcher a question turning an
        #: audit from 84 seconds into 331.
        #:
        #: Measured, because that note is the reason this is a dict:
        #: `query.provoked_by_allies` costs **33 ns** when nobody holds the
        #: trait -- one `dict.get` returning nothing -- and **3.8 us** for a
        #: creature that does, which is the `query.allies` scan behind it.
        #: So the cost falls only on the creatures in this dict, and it is
        #: empty in every fight where no row laid the trait.
        self.ally_provokers: dict[int, list[Any]] = {}
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
        self, eid: int, budget: int, kind: str = "walk", share: bool = False,
        by: str = "", granted_by: int = -1,
    ) -> dict[Any, list[Any]]:
        from .movement import reachable

        # `by` is the row that asked for the move, carried so that
        # `movement.may_enter`'s gate can narrow on it -- three cards say
        # "when a <class> power allows you to shift". Empty for a move
        # nobody attributed.
        # `granted_by` is WHO asked, beside `by`'s which row -- see
        # `Movement.ignores_shift_granted_by` for why a ref cannot answer
        # the card that wants it.
        return reachable(self, eid, budget, kind=kind, share=share, by=by,
                         granted_by=granted_by)

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

    def difficult(self, for_: int | None = None, kind: str = "walk",
                  *, granted_by: int = -1) -> set[Any]:
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
        # **A waiver keyed on who granted the move.** `f2424` gives allies
        # the exemption only for a shift one of *its holder's* powers
        # allowed, so the test is the grantor's id rather than a label or
        # a move kind. An empty set -- every creature on every board until
        # a row says otherwise -- costs one membership test. #1461.
        if (granted_by >= 0 and kind == "shift"
                and granted_by in moves.ignores_shift_granted_by):
            return set()
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
        # **A square predicate, which none of the three waivers above can
        # be.** `f3573` ignores rough going "in squares of dim light or
        # darkness" -- a fact about the square, where `ignores` is a
        # label, `ignores_when` a move kind and `ignores_made_by` a
        # provenance. `query.light_level` is the reader `c.unlit` already
        # uses, and its docstring lists ignoring difficult terrain among
        # the rows wanting the question, so this is the nineteenth caller
        # rather than a twentieth way of reading `Grid.light`.
        #
        # Asked only when something laid the waiver: the light of every
        # rough square is not worth computing for the creatures that do
        # not have it.
        unlit: set[Any] = set()
        if moves.ignores_unlit:
            from .query import light_level
            from .types import Light

            unlit = {sq for sq in rough
                     if light_level(self, sq) is not Light.BRIGHT}
        # **The second square predicate, and the only one that moves.**
        # `f1887` prints "while adjacent to your spirit companion", so the
        # waived squares are the ones near a creature rather than the ones
        # with a property -- and the anchor is an id, so a spirit that
        # steps away takes the sure footing with it.
        #
        # Asked here rather than in `crossing`'s per-step closure for the
        # reason the whole set is built here: the answer is a fact about
        # the destination square, so it is computable once per move like
        # every other waiver. A per-step counter would NOT be -- see
        # `Movement.ignores_near`'s sibling gap.
        near: set[Any] = set()
        if moves.ignores_near:
            from .grid import distance as _near_distance

            for anchor, span in moves.ignores_near:
                spots = self._anchor_squares(anchor)
                if not spots:
                    continue
                near |= {sq for sq in rough
                         if min(_near_distance(sq, at) for at in spots)
                         <= span}
        if not ignored and not made and not unlit and not near:
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
            # The square's own light, when something waived it.
            and sq not in unlit
            # And its distance from an anchor, for the waiver that walks.
            and sq not in near
        } | imposed

    def _wet_squares(self, for_: int) -> frozenset[Any]:
        """Liquid squares this creature pays an extra square to enter.

        Empty for a board with no liquid, which is every board until
        something dresses one -- so `crossing`'s fast path is unchanged
        and the term costs a `dict` emptiness test per move search.

        **Three creatures pay nothing.** One that `crosses_liquid`, which
        is the printed permission; one with a **swim** mode, because the
        page gives it a speed to swim at rather than a surcharge; and one
        **flying**, which is over the water rather than in it.

        **An extra square, not impassable, and that is weaker than the
        page on purpose.** Printed, deep water is swum -- an Athletics
        check, half speed, and `movement.swims` already rolls it off
        `world.terrain` for a whole-fight aquatic board. Pricing a single
        liquid square as rough going is the smallest reader that makes
        the permission mean something, and it never stops a creature
        doing what the rules allow. Turning the per-square map into a
        per-square swim check would move pathing on every board that has
        one, and is a second change rather than this one. #1449.
        """
        if not self.grid.liquid:
            return frozenset()
        from .components import Movement

        mv = self.get(for_, Movement)
        if mv is not None and (
            mv.crosses_liquid
            or mv.modes.get("swim")
            or mv.modes.get("fly")
        ):
            return frozenset()
        return frozenset(self.grid.liquid)

    def _wall_tolls(self, for_: int) -> dict[Any, int]:
        """What each stated wall costs this creature to climb, by square.

        Empty for everybody the ruling does not name -- `#1365`:

        > *"flyers can pass over walls regardless of height, but climbers
        > can be assumed to start at the bottom and the height does matter
        > for climbing."*

        So a **flier pays nothing extra** and gets an empty table, which is
        the half that would be easy to get wrong by charging anything that
        can cross. A creature with a climb speed pays the height. One with
        both flies, because flying is the better answer and the card
        charges for starting at the bottom.

        Hoisted out of the per-step closure like `difficult` and the taxing
        zones, for the reason `crossing`'s own docstring gives.
        """
        from .components import Movement

        # **A zone that prices its own crossing is not tolled on top of
        # it**, which is this file's half of "the printed row wins over a
        # printed table". `p16292` is the worked case: *"The wall can be up
        # to 4 squares high"* AND *"Moving through a square of the wall
        # costs 2 extra squares of movement"* -- both printed, on the same
        # card. The height toll is 3 and beat the printed 2 under
        # `crossing`'s "larger of" rule, so a climber paid 4 to cross a wall
        # its own card prices at 3.
        #
        # The height is still **recorded**, and deliberately read from
        # `wall_heights()` elsewhere: `movement.over_a_wall` needs it to
        # know a flier crosses and a walker does not, which is the question
        # `#1365` was actually about. What is dropped here is only the
        # *movement surcharge*, and only where a row states one itself.
        #
        # A wall of wind is the reason the two can disagree at all: it is
        # pushed through rather than climbed, so its printed cost is not a
        # climb and the general rule has nothing to say about it.
        heights: dict[Any, int] = {}
        for _, zone in self.zones.all():
            if zone.height <= 0 or zone.extra_cost:
                continue
            for sq in zone.squares:
                if zone.height > heights.get(sq, 0):
                    heights[sq] = zone.height
        if not heights:
            return {}
        mv = self.get(for_, Movement)
        if mv is None or mv.modes.get("fly") or not mv.modes.get("climb"):
            return {}
        return dict(heights)

    def crossing(self, for_: int, kind: str = "walk",
                 *, granted_by: int = -1) -> Callable[[Any, Any], int]:
        """What one step of a move costs this creature, step by step.

        Returns a function of `(from_square, to_square)` giving the squares
        of movement charged for that step -- 1 ordinarily, 2 across difficult
        ground, more where a zone taxes the crossing.

        **Here for the reason `difficult` is here**, which that docstring
        states: three places charge for movement, and a surcharge honoured by
        some of them and ignored by the rest is a rule that reads correct and
        plays wrong. `step`, `reachable` and `costs` all take their price from
        this, so they cannot disagree.

        **A function rather than a set, because a tax is on the crossing and
        not on the square.** `difficult` can answer with a set because rough
        ground costs the same however you arrive; *"leaving the zone costs 2
        extra"* is a property of the pair, and the same square is free to
        enter and expensive to leave. Returning a closure keeps the one-owner
        property without costing the search anything: the zone list and the
        rough set are computed once, here, and the per-step call is a
        membership test.

        **The fast path is the common one.** Nothing in most fights taxes a
        crossing, so with no taxing zone this hands back exactly the
        expression the three sites used to inline, and a move search pays one
        extra function call for the whole search rather than per square.

        **A difficult-terrain waiver does not waive a tax, and that is a
        reading rather than an oversight.** The printed lines price a wall or
        a warded zone, not rough going -- *"entering a wall square costs 3
        extra squares"* says nothing about difficult terrain -- so a creature
        that crosses mud for free still pays the wall. The exception is
        `extra_cost_if_difficult`, whose clause is explicitly *about*
        difficult terrain (*"difficult terrain in the area costs 2 extra
        instead of the normal 1"*): a creature with nothing to pay there has
        nothing to pay extra, so the waiver carries through.
        """
        from .grid import distance as _distance

        rough = self.difficult(for_, kind, granted_by=granted_by)
        taxes = self._taxes_on(for_)
        toward = self._taxes_toward(for_)
        # **In the fast path's condition as well as the closure**, because a
        # wall toll with no taxing zone on the board would otherwise be
        # skipped entirely -- the shape of bug `Zone.extra_cost`'s own note
        # is about, one square cheaper than the card and nothing saying so.
        climb = self._wall_tolls(for_)
        wet = self._wet_squares(for_)
        if not taxes and not toward and not climb:
            return lambda _frm, to: 2 if (to in rough or to in wet) else 1

        def cost(frm: Any, to: Any) -> int:
            # **The larger of the two, never the sum.** `p3217` prints "2
            # extra **instead of** the normal 1 extra", so a tax replaces
            # difficult's surcharge; adding them would charge 3 for a square
            # the card prices at 2. See `Zone.extra_cost`.
            # **`wet` is beside `rough` and not folded into it**, so a
            # difficult-terrain waiver does not buy a walk on water --
            # `i3110x1` prints both permissions in one sentence and one
            # must not pay for the other. `Grid.liquid` has the argument.
            # The larger and not the sum, like everything else here: a
            # square that is both rough and liquid costs one extra.
            extra = 1 if (to in rough or to in wet) else 0
            for zone in taxes:
                if zone.extra_cost_if_difficult and to not in rough:
                    continue
                if zone.extra_cost_on == "leave":
                    # Leaving is a step from inside to outside. A step from
                    # one of the zone's squares to another is movement
                    # *within* it and is not what the card charges for.
                    if frm not in zone.squares or to in zone.squares:
                        continue
                elif to not in zone.squares:
                    continue
                extra = max(extra, zone.extra_cost)
            # **A step closer, which is what no set of squares could say.**
            # Measured against the nearer square of the anchor, and `<` not
            # `<=`: a step that keeps the distance is not an approach, which
            # is what lets a creature circle at its current range for free.
            for anchor, n in toward:
                near = self._anchor_squares(anchor)
                if not near:
                    continue
                before = min(_distance(frm, sq) for sq in near)
                after = min(_distance(to, sq) for sq in near)
                if after < before:
                    extra = max(extra, n)
            # **Climbing a stated wall costs its height**, so a 4-high wall
            # is four squares of movement and a 1-high one is the ordinary
            # single square. The larger of this and anything above, for the
            # same "instead of, not on top of" reason.
            tall = climb.get(to, 0)
            if tall > 1:
                extra = max(extra, tall - 1)
            return 1 + extra

        return cost

    def barred(self, for_: int, kind: str = "walk") -> frozenset[Any]:
        """Squares this creature's path may not include, moving like this.

        **A refusal, where `crossing` next door is a price**, and the two
        cannot stand in for each other. A price of any size is payable by a
        creature with enough movement left, and the one card printing this
        does not make the route expensive -- it makes it illegal, so a charge
        with twelve squares in hand must still go round.

        Empty on every board that does not lay such a zone, which is almost
        all of them, so both callers pay one set construction per search.

        Consulted by `reachable`, so the square is never offered, **and** by
        `step`, so a scripted move or a route built some other way cannot go
        through the square the search refused. Both, for the reason
        `World.difficult` gives for living here: a rule honoured by one of
        them and not the other reads correct and plays wrong.
        """
        from .query import team

        mine = team(self, for_)
        out: set[Any] = set()
        for _eid, zone in self.zones.all():
            if kind not in zone.closed_to:
                continue
            if zone.closed_to_for == "enemies":
                theirs = team(self, zone.owner)
                # Both sides known and equal is the only waiver, for the
                # reason `_taxes_on` spells out: `team` answers None for
                # anything without a `Side`, and a bare `==` would read two
                # unknowns as allies and let the refused creature through.
                if mine is not None and theirs is not None and theirs == mine:
                    continue
            elif zone.closed_to_for.startswith("kind:"):
                # **A type word rather than a side**, which one printed row
                # needs and `"enemies"` cannot say: `i3305p1`'s scroll
                # refuses *"an affected creature"* -- the creature type
                # chosen when the scroll was made -- and that cuts across
                # both sides. Same `<axis>:<word>` shape `obscured_for`
                # uses, and the word is read through `kinds_of` so a
                # stat block's own type line and anything `c.set_origin`
                # wrote both answer.
                from .query import kinds_of

                want = zone.closed_to_for[len("kind:"):]
                if want and want not in kinds_of(self, for_):
                    continue
            out |= zone.squares
        return frozenset(out)

    def _taxes_toward(self, for_: int) -> list[tuple[int, int]]:
        """Anchors this creature pays extra to approach, and by how much.

        Read off the mover rather than off the anchor, because that is where
        the printed clause puts it -- *"each square moved toward you costs
        **it** 1 extra"* is a burden on the one creature the row named, and
        the two rows that print it each name one.
        """
        from .components import Movement

        moves = self.get(for_, Movement)
        if moves is None or not moves.harder_toward:
            return []
        return sorted(moves.harder_toward.items())

    def _anchor_squares(self, anchor: int) -> frozenset[Any]:
        """Where the anchor is standing, or nothing if it has left the board.

        An anchor that is gone taxes nobody rather than taxing from the
        square it died on, which is the reading the cards imply: the clause
        is *"toward you"*, and there is no "you" to approach.
        """
        from .query import squares

        return frozenset(squares(self, anchor))

    def _taxes_on(self, for_: int) -> list[Zone]:
        """Live zones that charge `for_` extra to cross them.

        The side is resolved here, when somebody moves, rather than frozen
        when the zone was laid -- `Zone.extra_cost_for`'s own note has why.
        A zone whose owner has since left the board still taxes: a warded
        floor does not stop being warded because the caster fell over.

        **An unknown side pays**, which is the branch worth spelling out.
        `query.team` answers `None` for anything without a `Side`, so a bare
        `==` would have read two unknowns as allies and waived the tax --
        exactly the all-False gate this engine keeps producing. The waiver
        needs both sides *known* and equal; anything else is charged.
        """
        live = [zone for _eid, zone in self.zones.all() if zone.extra_cost]
        if not live:
            return []
        from .query import team

        mine = team(self, for_)

        def exempt(zone: Zone) -> bool:
            if zone.extra_cost_for != "enemies":
                return False
            theirs = team(self, zone.owner)
            return mine is not None and theirs is not None and theirs == mine

        return [zone for zone in live if not exempt(zone)]

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
