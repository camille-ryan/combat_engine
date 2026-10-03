"""Record a fight so it can be watched afterwards, and argued with.

The point is the **decision**, not the board. A fight log already exists in several
shapes -- `Bus.log`, `transcript.py`'s JSONL, the replay fixtures -- and none of them says
*why*. `score` is computed live in `render.option_dto` and written nowhere;
`DoctrinePolicy.weighed` is on no endpoint at all. So a reviewer reading a recording built
from any existing artefact can see that a creature did something odd and cannot see what
it thought the alternatives were worth.

This writes all three tracks at once:

* **events** -- `render.event_dto` shapes, so the page's existing log appenders work
  unchanged;
* **frames** -- one board snapshot per turn, which is what `renderBoard` draws;
* **decisions** -- what each creature chose, the next few it passed over, and the weighted
  terms behind each, which is the track that makes a comment actionable.

**Both sides are the policy**, which is what makes this reproducible from a seed alone. A
*web* fight is not: `Session._install` routes every character's choice to the browser and
nothing records which option index came back. An all-AI fight has no such gap, and
`scripts/replay.py` has relied on that for the regression net for a long time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from combat_engine import story
from combat_engine.engine.turns import Encounter
from combat_engine.policy import install, take_turn
from combat_engine.policy import threat as _threat
from combat_engine.policy.doctrine import DoctrinePolicy, forget

from . import render
from .session import Session
from .wire import Wire

#: Where recordings live. Git-ignored, like every other fight on disk.
REPLAYS = Path(__file__).resolve().parents[3] / "logs" / "replay"

#: Where a reviewer's notes live, beside the recording they are about.
REVIEWS = Path(__file__).resolve().parents[3] / "logs" / "review"

#: How many rejected options to keep beside each choice.
#:
#: Four, because the question a reviewer asks is "what else was there" and the answer is
#: only interesting near the top -- `scripts/watch.py` defaults to three for the same
#: reason. Keeping all of them would store 253 options per decision on a level-10 board.
KEEP = 4

#: Stop a runaway fight. `take_turn` has its own spin guard; this one bounds the whole
#: recording, because a fight that will not end would otherwise write until the disk did.
ROUNDS = 40


@dataclass
class Decision:
    """One creature's turn-choice, with what it passed over."""

    seq: int
    round: int
    actor: int
    chosen: dict[str, Any]
    passed: list[dict[str, Any]] = field(default_factory=list)


class Recorder(DoctrinePolicy):
    """A `DoctrinePolicy` that writes down every choice and its runners-up.

    **Not a dataclass**, deliberately, and `scripts/doctrine.py:48-50` is the precedent:
    `DoctrinePolicy` is one, so a subclass decorated as a dataclass never runs the plain
    `__init__` and every counter here would be silently empty.
    """

    def __init__(self, keep: int = KEEP) -> None:
        super().__init__()
        self.keep = keep
        self.decisions: list[Decision] = []

    def _entry(self, world: Any, encounter: Any, actor: int, action: Any) -> dict:
        """One action, its score, and the terms that add up to it.

        **`weighed()` times the weights, never `explain()`.** `explain` filters to
        `DOCTRINE`, which is 18 keys against `WEIGHTS`' 31, so it returns barely a third
        of the terms and **its values do not sum to the score printed beside them**. The
        component file records what that cost once already: a counter built on
        `explain()["allies_caught"]` read 0 in every state, including with the deterrent
        disarmed, and the zero was read as "this does not happen". It happens 93 times a
        run.
        """
        raw = self.weighed(world, encounter, actor, action)
        terms = {}
        for name, value in raw.items():
            weighted = self.weights.get(name, 0.0) * value
            if weighted:
                terms[name] = round(weighted, 3)
        return {
            "label": str(action),
            "kind": action.kind,
            "ref": action.ref or "",
            "score": round(self.score(world, encounter, actor, action), 3),
            "terms": dict(sorted(terms.items(), key=lambda kv: -abs(kv[1]))),
        }

    def act(self, world: Any, encounter: Any, actor: int, options: list[Any]) -> Any:
        picked = super().act(world, encounter, actor, options)
        usable = [o for o in options if getattr(o, "available", True)]
        # **Score the chosen action itself.** `scripts/watch.py` reports `scored[0][0]`,
        # the *top* score, as the chosen action's -- and 12-14% of decisions are tied at
        # the top, so the number it prints can belong to a different action than the one
        # it names.
        chosen = self._entry(world, encounter, actor, picked)
        rest = sorted(
            (o for o in usable if o is not picked),
            key=lambda o: -self.score(world, encounter, actor, o),
        )
        self.decisions.append(
            Decision(
                seq=len(world.bus.log),
                round=getattr(world, "round", 0),
                actor=actor,
                chosen=chosen,
                passed=[
                    self._entry(world, encounter, actor, o) for o in rest[: self.keep]
                ],
            )
        )
        return picked


def record(seed: int, level: int, *, scaling: str = "full", name: str = "") -> dict:
    """Play a fight with nobody watching, and write down everything about it.

    Returns the recording and writes it to `logs/replay/<name>.json`.
    """
    _threat.clear()
    forget()
    fielded = story.field_encounter(seed, level, scaling=scaling)
    world = fielded.world
    if not fielded.enemies:
        raise ValueError("no monster is fully written yet")

    ident = name or f"s{seed}_L{level}"
    encounter = Encounter(world)
    policy = Recorder()
    session = Session(
        id=ident,
        world=world,
        encounter=encounter,
        wire=Wire.of(world),
        policy=policy,
        seed=seed,
        level=level,
        scaling=scaling,
    )
    # **The plain `install`, not `Session._install`.** The session's own one routes a
    # character's question to the browser's turnstile, which is right for a played fight
    # and would hang forever here. This hands both sides to the policy, which is also what
    # makes the recording reproducible from its seed.
    install(world, encounter, {}, default=policy)

    frames: list[dict] = []
    #: Every creature's trait list, stored **once**.
    #:
    #: `ActorDTO.traits` is a character's whole power list with its printed text -- 6.7
    #: KiB each -- and it is identical in every frame: measured, one distinct value across
    #: all 31 frames of a level-5 fight, for monsters and characters alike. Repeating it
    #: per frame was 830 KiB of the same bytes in a 1.7 MB recording, which is most of the
    #: file. The hover card does read it (`card.js:148`), so it is kept, just not 31 times.
    cast: dict[str, Any] = {}

    def snapshot() -> None:
        """A board, as `renderBoard` wants it.

        Trimmed to what the page draws. A whole `EncounterStateDTO` also carries a
        `roster` of every power's printed text, which is most of its weight and nothing a
        replay draws.
        """
        whole = render.state(session)
        actors = []
        for a in whole.actors:
            got = a.model_dump()
            traits = got.pop("traits", None)
            if traits and got["id"] not in cast:
                cast[got["id"]] = traits
            actors.append(got)
        frames.append({
            "seq": whole.seq,
            "round": whole.round,
            "current": whole.current,
            "board": whole.board.model_dump(),
            "actors": actors,
        })

    encounter.start()
    snapshot()
    while not encounter.finished and world.round <= ROUNDS:
        actor = world.turn
        if actor is None:
            break
        take_turn(world, encounter, actor, policy)
        encounter.advance()
        snapshot()

    events = [render.event_dto(session, e).model_dump() for e in world.bus.log]
    out = {
        "name": ident,
        "seed": seed,
        "level": level,
        "scaling": scaling,
        "paradigm": getattr(fielded, "paradigm", ""),
        "enemies": list(fielded.enemies),
        "rounds": world.round,
        "winner": encounter.winner.value if encounter.winner else None,
        # Hoisted out of every frame; the page puts it back before building a card.
        "cast": cast,
        "events": events,
        "frames": frames,
        "decisions": [
            {
                "seq": d.seq,
                "round": d.round,
                "actor": session.wire.id(d.actor),
                "chosen": d.chosen,
                "passed": d.passed,
            }
            for d in policy.decisions
        ],
    }
    REPLAYS.mkdir(parents=True, exist_ok=True)
    (REPLAYS / f"{ident}.json").write_text(json.dumps(out))
    return out


def listing() -> list[dict]:
    """Every recording on disk, newest first, without reading the whole of any."""
    out = []
    for path in REPLAYS.glob("*.json"):
        try:
            got = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "name": got.get("name", path.stem),
            "seed": got.get("seed"),
            "level": got.get("level"),
            "paradigm": got.get("paradigm", ""),
            "rounds": got.get("rounds"),
            "winner": got.get("winner"),
            "decisions": len(got.get("decisions", [])),
            "events": len(got.get("events", [])),
        })
    return sorted(out, key=lambda r: (r["level"] or 0, str(r["name"])))


def read(name: str) -> dict | None:
    """One recording, or `None`. `name` is checked rather than joined blindly."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    path = REPLAYS / f"{name}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def note(name: str, entry: dict) -> bool:
    """Append one reviewer's note to `logs/review/<name>.json`.

    A write, and worth being plain about: it touches a log, never a world. Nothing in the
    replay surface can change a fight.
    """
    if read(name) is None:
        return False
    REVIEWS.mkdir(parents=True, exist_ok=True)
    path = REVIEWS / f"{name}.json"
    notes = []
    if path.is_file():
        try:
            notes = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            notes = []
    notes.append(entry)
    path.write_text(json.dumps(notes, indent=1))
    return True
