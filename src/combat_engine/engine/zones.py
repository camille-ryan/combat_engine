"""Zones, auras and conjurations.

All three are the same thing at different settings: an entity with a set of
squares, an owner, and a duration. A zone's squares are fixed where the
caster put them; an aura's are recomputed from its owner's position every
time the owner moves, which is the only real difference between them.

The README's rule that a standing "enemies adjacent to you" effect is an
aura 1 is honoured by `aura(...)` -- there is no separate mechanism for it.

Membership is diffed centrally. Nothing that creates a zone has to work out
who walked into it; it subscribes to `ZoneEntered` and `ZoneExited` for its
own id and is told.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .components import Health, Ident, Position
from .durations import When
from .events import (
    EnterSquare,
    LeaveSquare,
    MoveEnd,
    ZoneCreated,
    ZoneEnded,
    ZoneEntered,
    ZoneExited,
)
from .grid import Square, spread
from .query import creatures, squares, team
from .types import ActionType, Light

if TYPE_CHECKING:
    from .durations import Effect
    from .ecs import World


#: The directions `Zone.obscured_for` may take -- see the field's own note
#: for why this is two words rather than a predicate or a set of ids.
OBSCURED_FOR = frozenset({"enemies", "outside"})


@dataclass
class Zone:
    owner: int
    label: str
    squares: frozenset[Square] = frozenset()
    #: Set for an aura: its radius around the owner, recomputed as it moves.
    aura: int | None = None
    #: False, True, or what sort of going it is -- see `Grid.difficult`.
    difficult: bool | str = False
    blocks_sight: bool = False
    #: Damage a creature takes for being in these squares -- a dice
    #: expression, or `""` for a zone that does not hurt anybody.
    #:
    #: **The book's sixth terrain category, which had no spelling.** Four
    #: categories were modelled (difficult, cover, blocking, obscured) and
    #: this one was not, so a region that damages whoever enters it could
    #: only be written as a watcher inside one row's body, one row at a
    #: time. The converted adventure's opening fight is built on exactly
    #: this -- spreading fire that burns whoever steps into it -- and the
    #: skill challenge's whole outcome is adding or removing it. #952.
    #:
    #: Line of sight is deliberately untouched: this category hurts and
    #: hinders, it does not blind, which is what separates it from
    #: `blocks_sight` and from `obscured`.
    hindering: str = ""
    #: What type the hindering damage is, by `DamageType` value. A string
    #: rather than the enum for the reason `difficult` is one: this module
    #: holds geometry and should not import the rules vocabulary.
    hindering_type: str = ""
    #: How well lit the zone's squares are, when it darkens them -- a
    #: `Light` value, or `""` for a zone that does not touch the light.
    #:
    #: **Not the same as `blocks_sight` and that is the whole point.** That
    #: flag is binary and symmetric: it blinds both sides, which is terrain.
    #: A zone that is "lightly obscured" conceals whoever stands in it from
    #: whoever cannot see in that light, which is a grade and is directional
    #: through the looker's senses. 12 rows wanted `c.zone(obscured=)` and 14
    #: more wanted `c.conceal_in()`; those are one gap, and this is it. #424.
    #:
    #: Read by `query.light_level`, which the attack path consults through
    #: `query.light_concealment`.
    obscured: str = ""
    #: **Who the obscurity applies to**, when the card gives it a side.
    #: `""` is everybody, which is the ordinary case. Two words otherwise:
    #:
    #: * `"enemies"` -- obscured to creatures not on the owner's team. Three
    #:   rows: *"lightly obscured for your enemies only"*, *"heavily
    #:   obscured to enemies"* twice.
    #: * `"outside"` -- obscured to creatures not standing in it. One row:
    #:   *"lightly obscured to creatures outside it"*.
    #:
    #: **A named direction and not a set of ids, which is the opposite call
    #: from `exempt` below, deliberately.** `exempt` can be a set because
    #: its membership is decided when the zone is laid and does not move. A
    #: direction's membership moves constantly: `"outside"` changes every
    #: time anybody steps in or out, and a set frozen at lay time would be
    #: wrong by the next turn. So it is resolved at the moment somebody
    #: looks.
    #:
    #: **And not a predicate either**, for the reason `exempt` is not one:
    #: two words cover all four rows that print this, a predicate is
    #: unserialisable and unreadable by the page, and a third direction is
    #: cheaper to add than a callable is to live with. #424's closing
    #: comment named these rows as the directional case the plain grade
    #: cannot say.
    #:
    #: Read by `query.obscures_for`, which `light_concealment` consults with
    #: the attacker in hand. `light_level` does **not** filter on it -- see
    #: the note there.
    obscured_for: str = ""
    #: **A darkness a light cannot lift.** One card prints a zone that is
    #: heavily obscured and "cannot be illuminated", and the second half had
    #: nothing to refuse: `query.light_level` gives a carried `c.light`
    #: radius an absolute override -- "anything within that radius is bright
    #: however dark the square itself is" -- so a torch cancelled the very
    #: darkness the card says it cannot.
    #:
    #: **A flag on the zone and not a waiver on the carrier**, because the
    #: printed sentence is about the darkness rather than about who walks
    #: into it. Taking the radius away from whoever steps inside would also
    #: put their light out *outside* the zone, which is a bigger rule than
    #: the card -- the same objection `m5426a0` records against reading one
    #: number for cover and concealment together.
    #:
    #: Only meaningful beside `obscured=`: a zone that darkens nothing has
    #: nothing for a light to lift. Read in `light_level`, which skips the
    #: carrier walk entirely for a sealed square. #535.
    no_light: bool = False
    #: Creatures this zone's sight-blocking does not apply to.
    #:
    #: Eight monster cards print a cloud or a darkness that blinds everybody
    #: **except the creature that made it**, and `blocks_sight` is terrain:
    #: binary and symmetric, with nothing to carve out of it. So those rows
    #: laid the zone and dropped the exemption, which inverts the card -- the
    #: whole point of the ability is that its owner can see and nobody else
    #: can.
    #:
    #: A set of ids and **not a predicate**, which is the narrower choice on
    #: purpose. Three more rows want an exemption by *sense* ("whatever can
    #: see in darkness") or by *movement mode*, and one wants `difficult`
    #: waived for a side; a set cannot say any of those, and pretending it
    #: can by snapshotting who qualifies when the zone is laid would be
    #: wrong the moment anything changed. Those rows keep their markers and
    #: name the narrower gaps. #528-adjacent reasoning: one marker, one gap.
    #:
    #: Read by `query._blinding_squares`, which already knows the looker.
    exempt: frozenset[int] = frozenset()
    #: Creatures these squares are difficult terrain **for, and for nobody
    #: else** -- the narrowing `difficult` above cannot express, since that
    #: flag is terrain and roughs the ground for everyone standing on it.
    #:
    #: Two heroic cards need exactly this and neither can be said any other
    #: way: "whenever an enemy in the aura is hit, squares in the aura are
    #: difficult terrain **for that enemy**" must leave the other enemies in
    #: its own aura on ordinary ground, and "that enemy treats all squares
    #: adjacent to you as difficult terrain" names one creature where the
    #: existing waiver is per *side* -- so laying the area flat and exempting
    #: the caster's team is wider than the card by the whole opposing side.
    #:
    #: **On the zone rather than on the creature, because the area follows.**
    #: Both cards describe their squares relative to a creature -- an aura,
    #: and "adjacent to you" -- and `Zones.refresh` already re-centres an
    #: aura's squares every round. A set of squares copied onto the burdened
    #: creature would have been a snapshot, exact for the turn after the hit
    #: and stale afterwards. `Movement.harder_everywhere` is the sibling for
    #: the one card with no geometry to follow.
    #:
    #: **Mutable, unlike `exempt`, and that is what carries the durations.**
    #: One aura serves every enemy in it, but each enemy's burden runs on its
    #: own clock -- "until the end of **its** next turn" -- so an id goes in
    #: with an `Effect` whose `on_suspend` takes that id back out. The zone
    #: outlives all of them.
    #:
    #: Written by `c.difficult_for`, read in `World.difficult`. #831.
    difficult_for: set[int] = field(default_factory=set)
    #: A row **any** creature in or adjacent to this region may use, as its
    #: own action. The board's power rather than anybody's -- "a terrain
    #: power", the book's name for it -- and the one thing on this dataclass
    #: that is not a property of the squares.
    #:
    #: **Why it is a ref on the zone and not a component on a creature.**
    #: The printed requirement is *"you must be adjacent to the <feature>"*,
    #: so eligibility is recomputed every time anybody looks and cannot be
    #: frozen onto a creature when the region is laid -- the same argument
    #: `obscured_for` makes two fields up, and for the same reason: a set of
    #: ids decided at lay time is wrong by the next turn. 16 of the 24
    #: printed rows say *adjacent* and 4 say *in*, which `squares` answers
    #: directly.
    #:
    #: Offered by `actions._terrain`, run by `perform` through
    #: `dsl.use(board=True)`. The row's own header carries the action cost
    #: and the attack line, because the interface and the AI read a header
    #: without running anything -- so none of that belongs here. #980.
    power: str = ""
    #: How many times `power` may still be used, or 0 for no limit.
    #:
    #: **The printed distinction, which the ETL dropped.** The spec heading
    #: is either `Single-Use Terrain` (15 rows) or `At-Will Terrain` (9), and
    #: neither reaches a column -- `terrain.usage` is empty on all 24 and
    #: holds a paragraph of placement advice on the rest. So the count is
    #: hand-written per row off the heading, which is #1104.
    #:
    #: **On the region, not on the user's `Powers`.** A single-use feature is
    #: spent for *everybody* once anybody uses it, and `Powers.used` counts
    #: per creature -- so the per-creature grain would let a second character
    #: shove the same boulder down the same slope. Decremented in `perform`
    #: after the row runs, not before: a row refused mid-body must not
    #: consume the feature.
    power_uses: int = 0
    #: Whether the last use of a limited feature has been spent. `#1126`.
    #:
    #: **A flag and not a sentinel in `power_uses`, which is the whole
    #: point.** That field means two things already -- a count, and 0 for
    #: *no limit* -- so a single-use feature decremented to 0 and read as
    #: unlimited: the spend turned a once-only feature into an at-will one.
    #: Encoding "spent" as a negative `power_uses` would fix the symptom
    #: and leave one int carrying three meanings, which is the failure
    #: `CLAUDE.md` records as having made twelve rows report ready when a
    #: third of the work had landed.
    #:
    #: So `power_uses` keeps counting, this says whether the count ran out,
    #: and the ETL column, `story.module.Feature.uses` and every content
    #: docstring citing the 0-is-no-limit convention stay true unchanged.
    #:
    #: Set by `perform`, like the decrement, and for the same reason: a row
    #: that refuses inside its own body must not spend the feature.
    power_spent: bool = False
    #: How far from these squares a creature may stand and still use
    #: `power`. 1 is adjacent, which is what 20 of the 24 printed rows say.
    #:
    #: **A number because the printed requirements are a number.** 16 say
    #: *"adjacent to"*, 4 say *"in"* or *"on"* -- both reach 1, since a
    #: creature in the region is within 1 of its own square -- and one says
    #: *"within 5 squares of"*. A boolean could not have held that row and
    #: it would have been offered at the wrong distance, which is a rule
    #: that reads correct and plays wrong: this component's named failure.
    power_reach: int = 1
    #: The effect whose duration this zone lives on.
    effect: Effect | None = field(default=None, repr=False)


class Zones:
    """Every live zone, and who is standing in each."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.inside: dict[int, set[int]] = {}
        #: Zones currently unwinding. `end` runs the effect's `on_end`, and
        #: one of those callbacks is `end` itself -- so the recursion has to
        #: be stopped somewhere. It used to be stopped by clearing the whole
        #: `on_end` list, which also threw away every callback a *row* had
        #: hung there ("when the zone ends, ..."), silently.
        self._ending: set[int] = set()
        #: Zone ids that darken their squares, kept as an index rather than
        #: rediscovered. **`all()` is a full component scan materialised into
        #: a list**, and the attack path asks "is anything dark" on every
        #: single attack -- doing it by scan cost +45% on a 400-row audit
        #: sample, measured. Maintained here and in `end`, which is the only
        #: pair of places a zone appears and disappears.
        self.darkening: set[int] = set()
        world.bus.on(MoveEnd, lambda _: self.refresh())
        world.bus.on(EnterSquare, lambda _: self.refresh())
        world.bus.on(LeaveSquare, lambda _: self.refresh())

    # -- making them ---------------------------------------------------------

    def create(
        self,
        owner: int,
        label: str,
        squares_: frozenset[Square] | set[Square],
        when: When,
        *,
        difficult: bool | str = False,
        blocks_sight: bool = False,
        obscured: str = "",
        obscured_for: str = "",
        no_light: bool = False,
        exempt: frozenset[int] | set[int] | None = None,
        sustain: ActionType | None = None,
        hindering: str = "",
        hindering_type: str = "",
        burn: Callable[[int, str, str], None] | None = None,
        power: str = "",
        power_uses: int = 0,
        power_reach: int = 1,
    ) -> int:
        if obscured:
            # **Checked, because the alternative is silent.** `difficult=`
            # next door takes a free label on purpose -- a row may invent
            # "mud" -- but the light levels are a closed set of three, so a
            # misspelling is a zone that darkens nothing and reads as if it
            # does. That is this component's named failure mode, and the
            # check is two lines.
            #
            # Validated here rather than typed as `Light` on the dataclass so
            # content files can pass the printed word without importing an
            # enum into forty monster modules.
            obscured = Light(obscured)
        # **The same check, for the same reason, one argument over.** The
        # directions are a closed set of two and a misspelling is a zone
        # that obscures *everybody* -- which reads exactly like a correct
        # non-directional zone and is wrong in the owner's favour on three
        # of the four rows. A uniformly-dead gate is this component's named
        # failure mode: when every instance answers the same way, a wrong
        # key looks like a right one.
        if obscured_for and obscured_for not in OBSCURED_FOR:
            raise ValueError(
                f"obscured_for={obscured_for!r} is not one of "
                f"{sorted(OBSCURED_FOR)}"
            )
        # A direction with no grade obscures nothing, and says it does. The
        # row that writes one without the other has almost certainly left
        # the grade off by accident -- there is no card that gives a side to
        # an obscurity it never lays.
        if obscured_for and not obscured:
            raise ValueError(
                "obscured_for= needs obscured= as well: a direction with no "
                "grade darkens nothing"
            )
        zone = Zone(
            owner=owner,
            label=label,
            squares=frozenset(squares_),
            difficult=difficult,
            blocks_sight=blocks_sight,
            obscured=obscured,
            obscured_for=obscured_for,
            no_light=no_light,
            exempt=frozenset(exempt or ()),
            hindering=hindering,
            hindering_type=hindering_type,
            power=power,
            power_uses=power_uses,
            power_reach=power_reach,
        )
        made = self._spawn(zone, when, sustain)
        if hindering:
            self._burns(made, hindering, hindering_type, burn)
        return made

    def _burns(self, zone: int, dice: str, dtype: str,
               burn: Callable[[int, str, str], None] | None) -> None:
        """Burn whoever is in `zone`, on arriving and again at a turn's end.

        **Lifted out of `Cast._hinders`, which was its only home and could
        only be reached by a row.** A printed board region has no caster --
        nothing lays it, no `Cast` exists -- so a hindering region on the
        floor recorded the field and burned nobody. `#952` built the
        facility and **zero content rows call `c.zone(hindering=)`**, so
        moving it costs nothing and gives it its first real caller.

        **Both moments, because the printed line names both** -- a creature
        that walks in takes it, and one that stays takes it again when its
        turn ends. Watching only the entry lets a creature end its turn
        standing in fire for nothing; watching only the turn end lets one
        walk through the whole region untouched.

        Entry is `ZoneEntered`, which this class already emits and which
        `c.zone_condition` reads for the same reason. The turn's end is read
        off the zone's own occupant list rather than by tracking arrivals,
        so a creature pushed in by somebody else is burned too -- the
        printed line is about being there, not about choosing to be.

        **`burn` is the damage policy and the caller owns it**, which is the
        one thing this move must not flatten. `Cast.zone` passes its own, so
        a row's hindering damage still goes through `c.flat` and keeps the
        standing-retype (`#795`) that only a caster can apply. A board
        region has no retype to apply and gets the default below, which is
        `resolve.deal_damage` -- the same function `c.flat` ends in.

        Had this taken no callback and always used `deal_damage`, the row
        path would have silently lost its retype. Zero rows use it today, so
        nothing would have gone red: that is the shape of a regression this
        component's rules file calls *silently false*.
        """
        from .events import TurnEnd, ZoneEntered
        from .query import alive

        def hurt(who: int) -> None:
            if burn is not None:
                burn(who, dice, dtype)
                return
            from .resolve import deal_damage
            from .types import DamageType
            try:
                kind = DamageType(dtype) if dtype else DamageType.UNTYPED
            except ValueError:
                # **Untyped rather than raising.** `hindering_type` arrives
                # as a bare string -- `Cast.zone` hands over
                # `DamageType.value` and a board region hands over a
                # database column -- so an unrecognised word is a data
                # problem, and a region that burns for untyped damage is
                # closer to the printed row than one that refuses to exist.
                kind = DamageType.UNTYPED
            mine = self.world.get(zone, Zone)
            # **A flat number is not a dice expression, and the common case
            # is flat** -- 32 of the 47 printed regions this path exists for
            # carry one, so the raise was two thirds of the population
            # rather than an edge. `rng.dice_or_flat` is the normaliser and
            # its docstring has the whole account; it lives there because
            # the hazard term hit the identical wall on `Trap.damage` and
            # two copies of one read is the real bug. #1039, #981.
            from .rng import dice_or_flat

            amount = self.world.rng.roll(dice_or_flat(dice)).total
            deal_damage(
                self.world,
                mine.owner if mine else 0,
                who,
                amount,
                kind,
                mine.label if mine else "",
                from_attack=False,
            )

        def on_enter(ev: ZoneEntered) -> None:
            if getattr(ev, "zone", None) == zone and alive(self.world, ev.actor):
                hurt(ev.actor)

        def at_turn_end(ev: TurnEnd) -> None:
            standing = self.inside.get(zone) or set()
            if ev.actor in standing and alive(self.world, ev.actor):
                hurt(ev.actor)

        self.world.bus.on(ZoneEntered, on_enter)
        self.world.bus.on(TurnEnd, at_turn_end)

    def aura(
        self,
        owner: int,
        label: str,
        radius: int,
        when: When = When.ENCOUNTER,
        sustain: ActionType | None = None,
        *,
        difficult: bool | str = False,
    ) -> int:
        """An aura follows its owner. A power that says "enemies adjacent to
        you" is an aura 1 and gets no special mechanism of its own.

        **`difficult` was reachable through `create` and not through here**,
        which nine rows were marked blocked for. `Zone.difficult` has always
        been the field and a monster helper was flipping it by hand after
        the fact -- `_difficult_aura`'s docstring describes that workaround
        in as many words. Passed through instead. #507-era triage.
        """
        zone = Zone(owner=owner, label=label, aura=radius, difficult=difficult)
        zone.squares = spread(squares(self.world, owner), radius)
        return self._spawn(zone, when, sustain)

    def _spawn(self, zone: Zone, when: When, sustain: ActionType | None = None) -> int:
        eid = self.world.spawn(zone, Ident(ref=f"z:{zone.label}"))
        zone.effect = self.world.effects.apply(
            eid,
            zone.owner,
            when,
            label=f"zone {zone.label}",
            on_end=[lambda: self.end(eid, "duration")],
            sustain_cost=sustain,
        )
        self.inside[eid] = set()
        if zone.obscured:
            self.darkening.add(eid)
        self.world.bus.emit(
            ZoneCreated(
                zone=eid, owner=zone.owner, squares=sorted(zone.squares), label=zone.label
            )
        )
        self.refresh()
        return eid

    def end(self, eid: int, why: str = "ended") -> None:
        zone = self.world.get(eid, Zone)
        if zone is None or eid in self._ending:
            return
        self._ending.add(eid)
        self.darkening.discard(eid)
        try:
            for actor in sorted(self.inside.pop(eid, set())):
                self.world.bus.emit(ZoneExited(zone=eid, actor=actor))
            self.world.bus.emit(ZoneEnded(zone=eid, why=why))
            if zone.effect is not None and not zone.effect.ended:
                self.world.effects.end(zone.effect, why)
            self.world.despawn(eid)
        finally:
            self._ending.discard(eid)

    # -- keeping them current ------------------------------------------------

    def all(self) -> list[tuple[int, Zone]]:
        return list(self.world.each(Zone))

    def dark(self) -> list[Zone]:
        """The live zones that darken their squares, by index not by scan.

        Empty on every board that never lays one, which is the case the
        attack path needs to answer cheaply. See `darkening`.
        """
        out = []
        for eid in self.darkening:
            zone = self.world.get(eid, Zone)
            if zone is not None and zone.obscured:
                out.append(zone)
        return out

    def obscuring_for(self, looker: int) -> list[Zone]:
        """The darkening zones whose obscurity applies to this creature.

        `dark()` answers "which zones darken squares"; this answers "which
        of them darken squares **for you**". Four rows print an obscurity
        with a side and `Zone.obscured_for` carries which:

        * `"enemies"` -- it obscures the owner's enemies and not its own
          side. *"Lightly obscured for your enemies only"*: the caster
          standing in her own fog is not concealed from her allies by it.
        * `"outside"` -- it obscures whoever is not standing in it.
          *"Lightly obscured to creatures outside it"*: the cloud hides what
          is inside from anybody looking in, and a creature inside sees out
          normally.

        **The looker is the attacker in both cases**, which is why one
        filter serves two directions that read as though they were about
        different things. Neither is a fact about the *target* -- which is
        exactly what made them unsayable as a plain grade, since setting the
        grade unconditionally conceals the zone's owner from itself, wrong
        in the monster's favour on three of the four rows.

        Lives here rather than in `query.py` because this module already
        imports that one and the reverse edge would be a cycle. Reached as
        `world.zones.obscuring_for(...)`, so the attack path needs no new
        import in either direction. #424.
        """
        out = []
        for zone in self.dark():
            which = zone.obscured_for
            if not which:
                out.append(zone)
            elif which == "outside":
                if not (zone.squares & frozenset(squares(self.world, looker))):
                    out.append(zone)
            elif which == "enemies":
                # **A zone whose owner has left the board still obscures.**
                # The squares are still full of fog, and answering otherwise
                # would clear the obscurity the moment the caster dropped --
                # which is the turn it matters most.
                mine = team(self.world, zone.owner)
                if mine is None or team(self.world, looker) is not mine:
                    out.append(zone)
        return out

    def refresh(self) -> None:
        """Recompute aura footprints and diff who is standing in what."""
        for eid, zone in self.all():
            # **"Death Ends: If you die, the zone ends immediately."** Two
            # things were wrong and they compounded, so neither a zone nor
            # an aura ended when its owner was killed:
            #
            # * the test ran **only for an aura** (`if zone.aura is not
            #   None`), so a plain zone had no owner-death path at all;
            # * and it asked whether the owner's `Position` was gone, where
            #   **a corpse keeps its position** -- the body stays on the
            #   board -- so even the aura it did cover went on being
            #   recomputed around a dead creature.
            #
            # Asked of every zone, before the aura footprint is redrawn,
            # which is the order the printed rule implies: a dead owner's
            # aura has no footprint to recompute.
            #
            # **`Health` read directly rather than `query.alive`**, and
            # deliberately: `alive` is False for anything carrying no
            # `Health` at all, so routing through it would end a zone owned
            # by something that was never a living creature. An owner with
            # no `Health` keeps exactly its old behaviour here. #998.
            # **A zone nobody laid has no owner to die.** `owner=0` is the
            # board laying a printed region -- `content.terrain.lay`, the
            # region half of `#1039` -- and 0 is not an entity, so it has no
            # `Position` and the test below ended the zone the instant it
            # was created.
            #
            # That was silent in the worst way: `create` returned a real id,
            # `hindering_at` answered `False`, and nothing raised. The only
            # thing that said so was `ZoneEnded.why`, which a probe had to
            # subscribe to in order to read `"its owner died"` about an
            # owner that never existed.
            #
            # **Two wrong fixes first, recorded because each looked
            # right.** Making the zone own itself (`zone.owner or eid`) does
            # not help -- the zone entity has no `Position` either, so it
            # fails the same test one line down. And routing through
            # `query.alive` is what `#998`'s note below already forbids.
            # The discriminator is the owner, not the health. #1039.
            if zone.owner:
                health = self.world.get(zone.owner, Health)
                if self.world.get(zone.owner, Position) is None or (
                    health is not None and health.hp <= health.dying_at
                ):
                    self.end(eid, "its owner died")
                    continue
            if zone.aura is not None:
                zone.squares = spread(squares(self.world, zone.owner), zone.aura)
            was = self.inside.setdefault(eid, set())
            now = {c for c in creatures(self.world) if squares(self.world, c) & zone.squares}
            for actor in sorted(now - was):
                self.world.bus.emit(ZoneEntered(zone=eid, actor=actor))
            for actor in sorted(was - now):
                self.world.bus.emit(ZoneExited(zone=eid, actor=actor))
            self.inside[eid] = now

    def occupants(self, eid: int) -> list[int]:
        return sorted(self.inside.get(eid, set()))

    def difficult_squares(self) -> dict[Square, str]:
        """Rough squares from live zones, each with its label."""
        out: dict[Square, str] = {}
        for _, zone in self.all():
            if not zone.difficult:
                continue
            kind = zone.difficult if isinstance(zone.difficult, str) else ""
            for sq in zone.squares:
                out.setdefault(sq, kind)
        return out
