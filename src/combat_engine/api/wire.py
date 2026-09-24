"""The boundary where ids become names.

The engine holds `m145` and entity 7. A player wants to read a name and "the
second one". Both translations happen here and nowhere else, which is what
keeps a publisher's prose out of the engine rather than merely out of sight.

Two separate jobs:

* **Wire ids.** Entity numbers are an implementation detail and change if the
  spawn order does, so the page is given `pc_1` and `npc_3` instead. They are
  assigned by placement, which exists before initiative is rolled and does
  not move when it is.
* **Labels.** `localization/names.json` is built from your own copy of the
  compendium and is not committed. With it, `m145` reads as its printed name.
  Without it -- a fresh clone, or a hosted deployment with `CE_NAMES=off` --
  the label is the neutral id, and the game is entirely playable that way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from combat_engine.engine import Ident, Side, Team, World
from combat_engine.engine.zones import Zone
from combat_engine.etl.build import localisation


def names_enabled() -> bool:
    """Off in a hosted deployment, which then never serves a printed name."""
    return os.environ.get("CE_NAMES", "on").lower() not in ("off", "0", "false", "no")


@dataclass
class Wire:
    """One encounter's translation table, both ways."""

    to_wire: dict[int, str] = field(default_factory=dict)
    to_eid: dict[str, int] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    zones: dict[int, str] = field(default_factory=dict)
    show_names: bool = True

    @classmethod
    def of(cls, world: World) -> Wire:
        w = cls(show_names=names_enabled())
        table = localisation() if w.show_names else {}
        counts: dict[str, int] = {}
        for eid, ident in _creatures(world):
            side = world.get(eid, Side)
            prefix = "pc" if side and side.team is Team.PC else "npc"
            counts[prefix] = counts.get(prefix, 0) + 1
            wid = f"{prefix}_{counts[prefix]}"
            w.to_wire[eid] = wid
            w.to_eid[wid] = eid
            w.labels[wid] = w._label(ident, table, counts)
        for eid, _zone in world.each(Zone):
            w.zones[eid] = f"zone_{eid}"
        return w

    def _label(self, ident: Ident, table: dict, counts: dict) -> str:
        """What to call this creature on screen.

        Falls back to the id, which is not a placeholder -- it is the neutral
        name, and playing with it is the supported hosted mode.
        """
        if not self.show_names:
            # A hosted deployment serves ids, and that includes the ones the
            # engine names itself -- "Fighter" is not a leak, but the mode is
            # meant to be checkable, and "everything is an id" is checkable.
            return f"{ident.ref} {ident.tag}" if ident.tag else ident.ref
        entry = table.get(ident.ref) or {}
        name = entry.get("name") or _plain(ident.ref)
        return f"{name} {ident.tag}" if ident.tag else name

    # -- lookups ------------------------------------------------------------

    def id(self, eid: int | None) -> str | None:
        return self.to_wire.get(eid) if eid is not None else None

    def eid(self, wid: str | None) -> int | None:
        return self.to_eid.get(wid) if wid else None

    def label(self, eid: int | None) -> str:
        wid = self.id(eid)
        return self.labels.get(wid, wid or "?")

    def zone(self, eid: int) -> str:
        return self.zones.setdefault(eid, f"zone_{eid}")

    def power(self, ref: str) -> str:
        """A power's name, or its id when there is no localisation."""
        if not self.show_names:
            return ref
        entry = localisation().get(ref) or {}
        return entry.get("name") or _plain(ref)

    def flavour(self, ref: str) -> str:
        if not self.show_names:
            return ""
        return (localisation().get(ref) or {}).get("flavour") or ""

    def refresh(self, world: World) -> None:
        """Pick up anything that arrived mid-fight, such as a conjuration."""
        counts = {"pc": 0, "npc": 0}
        for wid in self.to_wire.values():
            counts[wid.split("_")[0]] = max(
                counts[wid.split("_")[0]], int(wid.split("_")[1])
            )
        table = localisation() if self.show_names else {}
        for eid, ident in _creatures(world):
            if eid in self.to_wire:
                continue
            side = world.get(eid, Side)
            prefix = "pc" if side and side.team is Team.PC else "npc"
            counts[prefix] += 1
            wid = f"{prefix}_{counts[prefix]}"
            self.to_wire[eid] = wid
            self.to_eid[wid] = eid
            self.labels[wid] = self._label(ident, table, counts)


def _creatures(world: World) -> list[tuple[int, Ident]]:
    """Entities that get a `pc_`/`npc_` id.

    Only things that fight. A zone is an entity with an `Ident` too, and
    numbering it as a creature handed one a `npc_5` -- which then turned up
    as the actor of the event announcing the zone had expired.
    """
    from combat_engine.engine import Health, Position

    return [
        (eid, ident)
        for eid, ident in world.each(Ident)
        if world.has(eid, Health) and world.has(eid, Position)
    ]


#: Things the engine names itself, which no localisation file covers. They
#: are rules terms rather than a publisher's prose, so they are safe to spell
#: out even with names turned off -- but they go through the same door as
#: everything else, so there is only one place that turns an id into words.
OWN_NAMES = {
    "mba": "Melee Basic Attack",
    "rba": "Ranged Basic Attack",
    "second-wind": "Second Wind",
    "c:fighter": "Fighter",
    "c:cleric": "Cleric",
    "c:rogue": "Rogue",
    "c:wizard": "Wizard",
}


def _plain(ref: str) -> str:
    """A readable fallback for a ref no name table covers."""
    if ref in OWN_NAMES:
        return OWN_NAMES[ref]
    if ref.startswith(("c:", "w:", "z:")):
        return ref.split(":", 1)[1].replace("-", " ").title()
    return ref
