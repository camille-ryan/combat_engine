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
    #: The effect whose duration this zone lives on.
    effect: Effect | None = field(default=None, repr=False)


class Zones:
    """Every live zone, and who is standing in each."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.inside: dict[int, set[int]] = {}
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
    ) -> int:
        zone = Zone(
            owner=owner,
            label=label,
            squares=frozenset(squares_),
            difficult=difficult,
            blocks_sight=blocks_sight,
        )
        return self._spawn(zone, when)

    def aura(
        self,
        owner: int,
        label: str,
        radius: int,
        when: When = When.ENCOUNTER,
    ) -> int:
        """An aura follows its owner. A power that says "enemies adjacent to
        you" is an aura 1 and gets no special mechanism of its own."""
        zone = Zone(owner=owner, label=label, aura=radius)
        zone.squares = spread(squares(self.world, owner), radius)
        return self._spawn(zone, when)

    def _spawn(self, zone: Zone, when: When) -> int:
        eid = self.world.spawn(zone, Ident(ref=f"z:{zone.label}"))
        zone.effect = self.world.effects.apply(
            eid,
            zone.owner,
            when,
            label=f"zone {zone.label}",
            on_end=[lambda: self.end(eid, "duration")],
        )
        self.inside[eid] = set()
        self.world.bus.emit(
            ZoneCreated(
                zone=eid, owner=zone.owner, squares=sorted(zone.squares), label=zone.label
            )
        )
        self.refresh()
        return eid

    def end(self, eid: int, why: str = "ended") -> None:
        zone = self.world.get(eid, Zone)
        if zone is None:
            return
        for actor in sorted(self.inside.pop(eid, set())):
            self.world.bus.emit(ZoneExited(zone=eid, actor=actor))
        self.world.bus.emit(ZoneEnded(zone=eid, why=why))
        if zone.effect is not None and not zone.effect.ended:
            zone.effect.on_end.clear()  # already unwinding; do not recurse
            self.world.effects.end(zone.effect, why)
        self.world.despawn(eid)

    # -- keeping them current ------------------------------------------------

    def all(self) -> list[tuple[int, Zone]]:
        return list(self.world.each(Zone))

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
