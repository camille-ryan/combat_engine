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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .components import Ident, Position
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
from .query import creatures, squares
from .types import ActionType, Light

if TYPE_CHECKING:
    from .durations import Effect
    from .ecs import World


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
        sustain: ActionType | None = None,
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
        zone = Zone(
            owner=owner,
            label=label,
            squares=frozenset(squares_),
            difficult=difficult,
            blocks_sight=blocks_sight,
            obscured=obscured,
        )
        return self._spawn(zone, when, sustain)

    def aura(
        self,
        owner: int,
        label: str,
        radius: int,
        when: When = When.ENCOUNTER,
        sustain: ActionType | None = None,
    ) -> int:
        """An aura follows its owner. A power that says "enemies adjacent to
        you" is an aura 1 and gets no special mechanism of its own."""
        zone = Zone(owner=owner, label=label, aura=radius)
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

    def refresh(self) -> None:
        """Recompute aura footprints and diff who is standing in what."""
        for eid, zone in self.all():
            if zone.aura is not None:
                if self.world.get(zone.owner, Position) is None:
                    self.end(eid, "owner gone")
                    continue
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
