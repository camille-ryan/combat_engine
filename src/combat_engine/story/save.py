"""A campaign written down, which nothing in this repository has ever been.

A grep for `json.dump` across `src/` and `scripts/` finds the ETL writing the
database and the localisation, the transcript writer, and the replay recorder.
**No character, party or session is ever serialised.** The root `CLAUDE.md`
says it in one clause against `chargen`: *"Persistence does not exist."* #792.

## Why a seed is not enough here, when it is everywhere else

The rest of this project persists by **reproducibility**. A transcript's first
line re-runs the fight; `replay.py` pins seven fixtures and a divergence from
one is always a code change. That is exactly right for a fight, which is a
pure function of a seed.

A campaign is not. It is the accumulated consequences of choices a person
made -- which scene they went to, what they said, whether the challenge was
won -- and no seed reproduces a person. So this is the one thing here that has
to be written down rather than re-derived, and that is also why `saves/` is
git-ignored: a save is one person's game.

## The seam already existed

`story.Sheet` -- the #72 answer -- is a flat dataclass of scalars and lists,
mirroring `chargen.Character` field for field plus the wear. So a party is
`asdict` and back with no new model, and the character is **rebuilt from its
class every load** rather than stored: a content wave or a rules fix reaches a
saved party, and only the wear is carried. That is the same argument `_wear`
makes for why wear is laid after `spawn` rather than instead of it.

`version` is written because the first thing that will happen to this format
is that it changes. A load that does not recognise the version says so rather
than half-reading a file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from combat_engine.db import ROOT

from . import Party, Sheet

#: Bumped whenever a field is removed or changes meaning. Adding one does not
#: need it -- `_sheet` ignores keys it does not know and defaults the rest.
VERSION = 1

#: Git-ignored, beside `logs/`. One file per campaign.
SAVES = ROOT / "saves"


@dataclass
class Campaign:
    """Where a party has got to, and what it cost them."""

    module: str
    #: The campaign's own seed. Every scene derives its stream from this and
    #: its own id, so replaying a campaign replays its fights.
    seed: int = 0
    #: The scene about to be played. Empty means the module is finished.
    scene: str = ""
    visited: list[str] = field(default_factory=list)
    party: Party = field(default_factory=Party)
    #: Campaign resources a module names -- a reputation score, a door left
    #: unlocked. Declared by the module with its starting values.
    flags: dict[str, int] = field(default_factory=dict)
    #: One line per scene played, for a recap. Not a transcript: a fight's
    #: blow-by-blow goes to `logs/` and is re-runnable from its seed.
    log: list[str] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return not self.scene

    def note(self, line: str) -> None:
        self.log.append(line)


def _sheet(raw: dict) -> Sheet:
    """A `Sheet` from a saved dict, tolerant of a field it has not met.

    Unknown keys are dropped rather than raising, so a save written by a newer
    build loads in an older one minus whatever it did not understand. A missing
    key takes the dataclass default, which is what a save written before a
    field existed should get.
    """
    known = {f for f in Sheet.__dataclass_fields__}
    return Sheet(**{k: v for k, v in raw.items() if k in known})


def to_dict(campaign: Campaign) -> dict:
    return {
        "version": VERSION,
        "module": campaign.module,
        "seed": campaign.seed,
        "scene": campaign.scene,
        "visited": list(campaign.visited),
        "flags": dict(campaign.flags),
        "log": list(campaign.log),
        "party": [asdict(s) for s in campaign.party.sheets],
    }


def from_dict(raw: dict) -> Campaign:
    got = raw.get("version", 0)
    if got != VERSION:
        raise SystemExit(
            f"this save is version {got} and this build reads version "
            f"{VERSION}. Start a new campaign, or check out the build that "
            "wrote it."
        )
    return Campaign(
        module=str(raw.get("module", "")),
        seed=int(raw.get("seed", 0)),
        scene=str(raw.get("scene", "")),
        visited=[str(s) for s in raw.get("visited", ())],
        flags={str(k): int(v) for k, v in (raw.get("flags") or {}).items()},
        log=[str(line) for line in raw.get("log", ())],
        party=Party(sheets=[_sheet(s) for s in raw.get("party", ())]),
    )


def path_for(name: str) -> Path:
    """Where a campaign by that name lives. Names are not paths.

    `Path(name).name` rather than the name as given: a save id comes off the
    command line and a module file, and neither should be able to write
    outside `saves/`.
    """
    return SAVES / f"{Path(name).name}.json"


def save(campaign: Campaign, name: str) -> Path:
    """Write a campaign. Returns where it went."""
    SAVES.mkdir(parents=True, exist_ok=True)
    where = path_for(name)
    where.write_text(json.dumps(to_dict(campaign), indent=2) + "\n")
    return where


def load(name: str) -> Campaign:
    """Read a campaign back."""
    where = path_for(name)
    if not where.exists():
        raise SystemExit(f"{where} is missing. Start one with --play.")
    return from_dict(json.loads(where.read_text()))


def names() -> list[str]:
    """Every saved campaign on this machine."""
    if not SAVES.exists():
        return []
    return sorted(p.stem for p in SAVES.glob("*.json"))
