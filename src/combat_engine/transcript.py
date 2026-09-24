"""Writing a fight down as it happens.

Nothing was. The bus held the whole log in memory and `scripts/replay.py`
kept a handful of recorded fixtures, so the moment a session ended -- or the
server restarted -- the fight it had just played was gone. That is the wrong
way round for the one case that matters: something looked wrong on the
board and the only copy of what actually happened is the thing you have
just closed.

A transcript is a JSONL file. The first line is the **setup** -- seed,
level, scaling, who was on each side -- and every line after it is one
event, in the order the bus emitted them. Because combat holds no
randomness beyond the seeded generator, those two facts together are the
whole fight: the header alone re-runs it, and the events say what happened
if you would rather read than re-run.

Deliberately not the wire format. What goes down is the engine's own event,
ids and all, so a transcript is readable without a localisation file and
cannot leak a printed name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .engine.events import Event

if TYPE_CHECKING:
    from .engine.ecs import World

#: Where transcripts go. Git-ignored: every one of them is reproducible from
#: its own header, so there is nothing here worth keeping under version
#: control.
LOGS = Path(__file__).resolve().parents[2] / "logs"


@dataclass
class Transcript:
    """One fight, appended to a file as it is played."""

    path: Path
    #: Buffered rather than flushed per event. A fight is a few thousand
    #: events and a flush each would make the board feel the disk.
    _pending: list[str] = field(default_factory=list, repr=False)
    _seen: int = 0

    @classmethod
    def open(cls, name: str, setup: dict[str, Any], *, where: Path | None = None) -> Transcript:
        root = where or LOGS
        root.mkdir(parents=True, exist_ok=True)
        t = cls(path=root / f"{name}.jsonl")
        t.path.write_text(json.dumps({"kind": "setup", **setup}) + "\n")
        return t

    def attach(self, world: World) -> None:
        """Record everything from here on.

        Subscribed to `Event` itself, so a new event class is written down
        the day it is added and nobody has to remember to list it.
        """
        world.bus.on(Event, self._note)

    def _note(self, ev: Event) -> None:
        try:
            self._pending.append(json.dumps(_plain(ev.wire())))
        except (TypeError, ValueError):
            # A transcript must never be the thing that breaks a fight.
            self._pending.append(json.dumps({"seq": ev.seq, "kind": ev.kind}))
        if len(self._pending) >= 64:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        with self.path.open("a") as fh:
            fh.write("\n".join(self._pending) + "\n")
        self._seen += len(self._pending)
        self._pending.clear()

    def close(self) -> None:
        self.flush()


def _plain(value: Any) -> Any:
    """JSON without the enums. `DamageType.FIRE` becomes "fire"."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(v) for v in value]
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return _plain(value.value)
    return value


def read(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A transcript back off disk: its setup, and its events."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        return {}, []
    head = rows[0] if rows[0].get("kind") == "setup" else {}
    return head, rows[1:] if head else rows
