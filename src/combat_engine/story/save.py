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


#: Who the party is when the model has to play them. Defaults by class, so a
#: party built before personas existed still plays -- a nameless companion is
#: a worse companion and not a broken one.
DEFAULT_WANTS = {
    "fighter": "to be where the fighting is and be paid for it",
    "cleric": "to know the people she travels with are worth saving",
    "rogue": "a bigger share than anyone has offered",
    "wizard": "to understand the thing nobody else has noticed",
    "ranger": "to be outdoors and moving",
    "paladin": "to do this the right way, whatever it costs",
    "warlord": "to get everyone home",
    "warlock": "to find out what the bargain is really for",
}


@dataclass
class Persona:
    """Who a character is, as opposed to what they can do.

    **`chargen` models none of this.** `Character` carries class, level,
    build, feats, race and powers, and no name, background or voice at all --
    so solo play had four party members for the model to speak for and
    nothing to speak from. #803.

    It lives in the save rather than the tree because it is generated prose,
    and the charter is plain about that: a generated name in a column is
    indistinguishable from a leaked one.
    """

    name: str = ""
    voice: str = ""
    wants: str = ""

    @classmethod
    def by_class(cls, who: str, nth: int = 0) -> Persona:
        """A serviceable default, so a party without personas still plays.

        `nth` is which one of that class this is, and it only shows when
        there is more than one -- a lone cleric is "Cleric", not "Cleric 2".
        The first draft numbered by party slot and produced a party of
        Cleric 2, Rogue 3 and Wizard 4, which reads as a bug.
        """
        word = (who or "adventurer").strip().lower()
        return cls(
            name=word.title() if nth == 0 else f"{word.title()} {nth + 1}",
            voice="",
            wants=DEFAULT_WANTS.get(word, "to come out of this better off"),
        )


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
    #: Lore rows already rolled, as `<scene>:<fact>`. **On the campaign and
    #: not on `Playing`**, which is rebuilt every time a scene is entered --
    #: so a `once` row tracked there was re-rolled on a revisit while its
    #: docstring claimed otherwise. Whether a character knows a thing is not
    #: re-decided by walking back into the room.
    recalled: list[str] = field(default_factory=list)
    #: One line per scene played, for a recap. Not a transcript: a fight's
    #: blow-by-blow goes to `logs/` and is re-runnable from its seed.
    log: list[str] = field(default_factory=list)
    #: Who each character is, by the same position `harvest` matches on.
    personas: list[Persona] = field(default_factory=list)
    #: `"human"` or `"ai"` per party slot. **The whole difference between the
    #: two playstyles**: solo is one human and the rest played, party is all
    #: human. One field rather than two flows, so the loop cannot drift the
    #: way encounter setup did when it existed twice (#229).
    control: list[str] = field(default_factory=list)
    #: Encounters completed since the last extended rest, **weighted by the
    #: printed rule** rather than counted flat -- see `Scene.counts_toward`.
    #: Two of these is a milestone and an action point.
    #:
    #: On the campaign rather than on `Party`, because it is a fact about
    #: the day and not about any character, and because an extended rest
    #: has to reset it from `run.step`, which is where the rest happens.
    encounters: int = 0
    #: Extended rests taken. The second of the two units a timeline entry
    #: can be due in; scenes played is `len(visited)` and needs no field.
    rests: int = 0
    #: Timeline entries already fired or cancelled, by `<when><unit>:<scene>`.
    #: **Without this an entry fires every transition once its tick passes**,
    #: because "due" is a comparison against a counter that only goes up.
    fired: list[str] = field(default_factory=list)
    #: What each scene's fight killed, by scene id -> ref -> how many.
    #:
    #: **The DMG states this as a rule twice** -- *"when the characters kill a
    #: monster, it stays dead"*, and again that a revisited site *"shouldn't
    #: just reset to the state it was in the first time around"*. A scene the
    #: module routes back to was fielding its whole cast again, so the party
    #: walked into a room it had cleared and the dead were standing up.
    #:
    #: A **count per ref**, not a set: a scene fielding four of the same
    #: creature that lost three of them must field one on a revisit, and a
    #: set cannot say that. Accumulated across revisits.
    #:
    #: On the campaign for the same reason `recalled` is -- `Playing` is
    #: rebuilt every time a scene is entered, so anything tracked there is
    #: re-decided by walking back into the room. #970.
    cleared: dict[str, dict[str, int]] = field(default_factory=dict)
    #: The party's standing marching order: a band per slot, and how far
    #: apart. Empty means the single column placement has always used, so
    #: a campaign saved before this plays exactly as it did. #994.
    #:
    #: On the campaign rather than the scene because the rules call it a
    #: *standing* arrangement a player sets once and may change at any
    #: time, not something a module re-authors per fight.
    #: The outcome of each decided scene, oldest first. Read by
    #: `tension.footing` to pitch the next scene, and **bounded** -- only
    #: the last few matter, which is what keeps the loop from converging on
    #: a game nobody can lose. #977.
    #: The next short rest is denied, because a scene was lost and said
    #: that was the cost. Cleared by the rest it denies. #975.
    denied: bool = False
    #: Quest id -> one of `module.QUEST_STATES`. **A state per quest, not
    #: a boolean**, because quests can conflict: completing one must be
    #: able to fail another, which a set of flags cannot express. #940.
    quests: dict[str, str] = field(default_factory=dict)
    record: list[str] = field(default_factory=list)
    formation: list[str] = field(default_factory=list)
    spread: int = 2

    @property
    def clock(self) -> dict[str, int]:
        """What a timeline entry is compared against.

        Scenes played and extended rests taken. Deliberately not a real
        clock -- the book's own units are days and sessions, and a tick per
        scene transition is the coarsest thing that expresses any of its
        examples.
        """
        return {"scene": len(self.visited), "rest": self.rests}

    @property
    def milestones(self) -> int:
        """Milestones reached since the last extended rest.

        Camille's ruling on #666: *"an adventuring day consists of 4-5
        encounters, and a milestone is every two encounters."* So this is
        `encounters // 2`, over the weighted count -- `day.milestones` is
        the same arithmetic over the legs of an arcade day.
        """
        return self.encounters // 2

    def persona(self, slot: int) -> Persona:
        """Who slot N is, falling back to a default by class."""
        if slot < len(self.personas) and self.personas[slot].name:
            return self.personas[slot]
        sheets = self.party.sheets
        cls_ = sheets[slot].cls if slot < len(sheets) else ""
        nth = sum(1 for s in sheets[:slot] if s.cls == cls_)
        return Persona.by_class(cls_, nth)

    def controls(self, slot: int) -> str:
        """`"human"` or `"ai"`. Unset is human, which is the safe default --
        a character nobody has decided about should wait for a person rather
        than be spoken for."""
        if slot < len(self.control):
            return self.control[slot]
        return "human"

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
        "recalled": list(campaign.recalled),
        "party": [asdict(s) for s in campaign.party.sheets],
        "personas": [asdict(p) for p in campaign.personas],
        "control": list(campaign.control),
        # **`Campaign` is hand-serialised, unlike `Sheet`.** A new field here
        # has to be written in both directions or it silently resets on
        # every load -- which is what happened to `encounters` until a
        # driver asked, reading 0 where the campaign held 2. `Sheet` gets
        # this for free through `asdict` and `_sheet`'s tolerant filter.
        "encounters": campaign.encounters,
        "rests": campaign.rests,
        "fired": list(campaign.fired),
        "cleared": {k: dict(v) for k, v in campaign.cleared.items()},
        "denied": campaign.denied,
        "quests": dict(campaign.quests),
        "record": list(campaign.record),
        "formation": list(campaign.formation),
        "spread": campaign.spread,
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
        recalled=[str(k) for k in raw.get("recalled", ())],
        party=Party(sheets=[_sheet(s) for s in raw.get("party", ())]),
        personas=[
            Persona(**{k: str(v) for k, v in p.items()
                       if k in Persona.__dataclass_fields__})
            for p in raw.get("personas", ())
        ],
        control=[str(c) for c in raw.get("control", ())],
        # Defaults to 0, so a save written before milestones existed reads
        # as "no encounters since the last extended rest" -- which is the
        # safe direction and needs no `VERSION` bump to refuse the file.
        encounters=int(raw.get("encounters", 0) or 0),
        rests=int(raw.get("rests", 0) or 0),
        fired=[str(k) for k in raw.get("fired", ())],
        cleared={
            str(k): {str(r): int(n) for r, n in (v or {}).items()}
            for k, v in (raw.get("cleared") or {}).items()
        },
        denied=bool(raw.get("denied", False)),
        quests={str(k): str(v)
                for k, v in (raw.get("quests") or {}).items()},
        record=[str(o) for o in raw.get("record", ())],
        formation=[str(b) for b in raw.get("formation", ())],
        spread=int(raw.get("spread", 2) or 2),
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


#: Where a party lives, as opposed to a campaign. Same directory, different
#: thing: a party is the characters, a campaign is a party plus where it has
#: got to. Keeping them apart is what lets somebody build a group once and
#: play several adventures with it.
def party_path(name: str) -> Path:
    return SAVES / f"{Path(name).name}.party.json"


def save_party(party: Party, name: str,
               personas: list[Persona] | None = None) -> Path:
    SAVES.mkdir(parents=True, exist_ok=True)
    where = party_path(name)
    where.write_text(
        json.dumps(
            {
                "version": VERSION,
                "party": [asdict(s) for s in party.sheets],
                "personas": [asdict(p) for p in personas or ()],
            },
            indent=2,
        )
        + "\n"
    )
    return where


def load_personas(name: str) -> list[Persona]:
    """Who a hand-made party are. `[]` when the file predates personas."""
    where = party_path(name)
    if not where.exists():
        return []
    raw = json.loads(where.read_text())
    return [
        Persona(**{k: str(v) for k, v in p.items()
                   if k in Persona.__dataclass_fields__})
        for p in raw.get("personas", ())
    ]


def load_party(name: str) -> Party:
    where = party_path(name)
    if not where.exists():
        raise SystemExit(
            f"{where} is missing. Make one with: "
            f"uv run scripts/play.py --new-character --party {Path(name).name}"
        )
    raw = json.loads(where.read_text())
    got = raw.get("version", 0)
    if got != VERSION:
        raise SystemExit(f"that party is version {got}; this build reads {VERSION}.")
    return Party(sheets=[_sheet(s) for s in raw.get("party", ())])


def names() -> list[str]:
    """Every saved campaign on this machine."""
    if not SAVES.exists():
        return []
    return sorted(
        p.name.removesuffix(".json") for p in SAVES.glob("*.json")
    )
