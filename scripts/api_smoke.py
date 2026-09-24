#!/usr/bin/env python
"""Play a whole encounter over HTTP and check what crossed the wire.

    uv run scripts/api_smoke.py
    uv run scripts/api_smoke.py --show

Starts its own server on a spare port, plays a fight to the finish, and
checks the things a browser would notice and a unit of the engine would not:

* the same state twice gives the same option indices, because an index *is*
  the wire id for an action and a click must not land on a different one;
* replaying the event stream from the start hands back every event exactly
  once, which is what a reconnect does;
* the power roster arrives whole and says why each greyed entry cannot be
  used;
* a power that asks a question mid-resolution actually suspends, and carries
  on from where it stopped when answered;
* no engine entity id reaches the wire -- everything is `pc_1` or `npc_2`;
* and with `CE_NAMES=off`, the same game is served with no printed name
  anywhere, which is how a hosted deployment runs.
"""

from __future__ import annotations

import argparse
import contextlib
import itertools
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, *, names: bool = True) -> None:
        self.port = free_port()
        self.names = names
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> Server:
        env = {**os.environ, "CE_NAMES": "on" if self.names else "off"}
        self.proc = subprocess.Popen(
            [
                "uv", "run", "uvicorn", "combat_engine.api.app:app",
                "--port", str(self.port), "--log-level", "warning",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(80):
            with contextlib.suppress(Exception):
                self.get("/api/health")
                return self
            time.sleep(0.25)
        raise SystemExit("the server did not come up")

    def __exit__(self, *_: object) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def get(self, path: str) -> dict:
        return json.load(urllib.request.urlopen(self.base + path, timeout=20))

    def post(self, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(body or {}).encode(),
            headers={"Content-Type": "application/json"},
        )
        return json.load(urllib.request.urlopen(req, timeout=20))

    def stream(self, path: str, limit: int = 6000) -> dict[str, list[dict]]:
        """Read the stream, keeping the frame kinds apart.

        Two kinds come down it: `encounter_event` is the raw log and
        `narration` is the sentence a player reads. They share a `seq` -- a
        sentence borrows the seq of the last event it covers -- so lumping
        them together looks exactly like a duplicated event.
        """
        out: dict[str, list[dict]] = {"encounter_event": [], "narration": []}
        kind = None
        idle = 0
        handle = urllib.request.urlopen(self.base + path, timeout=20)
        # The stream never ends -- it is a live feed, and once it has caught
        # up it sends keep-alives forever. Two of those in a row is the
        # signal that the whole log has been delivered.
        for raw in itertools.islice(handle, limit * 6):
            line = raw.decode().rstrip("\n")
            if line.startswith(":"):
                idle += 1
                if idle >= 2 and (out["encounter_event"] or out["narration"]):
                    break
                continue
            if line.startswith("event: "):
                kind = line[7:].strip()
            elif line.startswith("data: ") and kind in out:
                idle = 0
                out[kind].append(json.loads(line[6:]))
        handle.close()
        return out


class Checks:
    def __init__(self) -> None:
        self.failed: list[str] = []
        self.passed = 0

    def that(self, ok: bool, what: str, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"  ok    {what}")
        else:
            self.failed.append(what)
            print(f"  FAIL  {what}" + (f"\n          {detail}" if detail else ""))


def play(server: Server, check: Checks, *, show: bool) -> tuple[str, dict]:
    state = server.post("/api/encounter", {"level": 1, "seed": 3})
    eid = state["id"]
    check_roster(check, state)  # while somebody is still acting; it empties at the end

    again = server.get(f"/api/encounter/{eid}")
    check.that(
        [o["index"] for o in again["options"]] == [o["index"] for o in state["options"]]
        and [o["label"] for o in again["options"]] == [o["label"] for o in state["options"]],
        "the same state twice gives the same options, in the same order",
    )

    asked = 0
    for _ in range(600):
        if state["status"] == "finished":
            break
        if state.get("pending"):
            asked += 1
            q = state["pending"]
            check.that(
                bool(q["answers"]) and bool(q["prompt"]),
                f"the question '{q['prompt'][:40]}' arrived with answers",
            ) if asked == 1 else None
            if show:
                print(f"        asked: {q['prompt']} -> {q['answers'][0]['label']}")
            state = server.post(f"/api/encounter/{eid}/decide", {"answer_index": 0})
            continue
        options = state["options"]
        if not options:
            break
        best = max(range(len(options)), key=lambda i: options[i]["score"])
        if show:
            print(f"        {state['current']}: {options[best]['label']}")
        state = server.post(f"/api/encounter/{eid}/act", {"action_index": best})

    check.that(state["status"] == "finished", "the fight reached a finish", str(state["round"]))
    check.that(state["winner"] is not None, "somebody won")
    check.that(asked > 0, "at least one power suspended to ask a question")
    return eid, state


def check_stream(server: Server, check: Checks, eid: str) -> list[dict]:
    frames = server.stream(f"/api/encounter/{eid}/events?from=0")
    events = frames["encounter_event"]
    narration = frames["narration"]

    seqs = [e["seq"] for e in events]
    check.that(seqs == sorted(seqs), "the stream arrives in order")
    check.that(len(seqs) == len(set(seqs)), "every event arrives exactly once")
    check.that(
        seqs[:1] == [1] if seqs else False,
        "the first event is seq 1",
        f"got {seqs[:1]} -- the page treats `from` as exclusive, so zero is never shown",
    )
    check.that(
        bool(narration),
        f"the readable log arrived ({len(narration)} sentences)",
        "raw events came but no narration frames -- the page shows those and "
        "hides the raw ones behind a checkbox, so this is an empty log panel",
    )
    check.that(
        all(n.get("text") for n in narration), "every sentence has words in it"
    )
    if narration:
        print(f"        e.g. {narration[min(3, len(narration) - 1)]['text'][:66]}")
    return events


def check_no_engine_ids(check: Checks, state: dict, events: list[dict]) -> None:
    """Nothing on the wire may be an engine entity id."""
    known = {a["id"] for a in state["actors"]}
    check.that(
        all(a["id"].startswith(("pc_", "npc_")) for a in state["actors"]),
        "every creature is a wire id",
    )
    bad = [
        o
        for o in state["options"]
        for t in o["targets"]
        if t not in known
    ]
    check.that(not bad, "every option targets a wire id", str(bad[:3]))
    stray = [
        e
        for e in events
        if e["actor"] is not None and e["actor"] not in known
    ]
    check.that(not stray, "every event names a wire id", str(stray[:2]))


def check_roster(check: Checks, state: dict) -> None:
    roster = state["roster"]
    check.that(bool(roster), "the roster is not empty")

    # What a power *does*, which is the printed rule and not the flavour.
    told = [p for p in roster if p["hit_text"] or p["effect_text"]]
    check.that(
        len(told) >= len(roster) - 1,
        f"{len(told)} of {len(roster)} powers say what they do",
        str([p["name"] for p in roster if not (p["hit_text"] or p["effect_text"])]),
    )
    attacks = [p for p in roster if p["attack_text"]]
    check.that(bool(attacks), "an attack power shows its attack line")
    if told:
        line = told[0]["hit_text"] or told[0]["effect_text"]
        print(f"        e.g. {told[0]['name']}: {line[:52]}")

    # Reach must be on the board. A ranged 20 power on a board sixteen wide
    # otherwise lights up squares that do not exist.
    width, height = state["board"]["width"], state["board"]["height"]
    off = [
        (p["name"], sq)
        for p in roster
        for sq in p["squares"]
        if not (0 <= sq[0] < width and 0 <= sq[1] < height)
    ]
    check.that(not off, "no power reaches off the edge of the board", str(off[:3]))
    greyed = [p for p in roster if not p["available"]]
    check.that(
        all(p["reason"] for p in greyed),
        "every unavailable power says why",
        str([p["name"] for p in greyed if not p["reason"]][:3]),
    )
    check.that(
        any("squares away" in (p["reason"] or "") for p in greyed) or not greyed,
        "where distance is the answer, the reason is the number",
    )


def check_hosted(check: Checks) -> None:
    """The same game with names off. Nothing printed may come through."""
    with Server(names=False) as server:
        state = server.post("/api/encounter", {"level": 1, "seed": 3})
        labels = [a["label"] for a in state["actors"]]
        check.that(
            all(lb.startswith(("m", "c:")) or lb[0].islower() for lb in labels),
            "with names off, every creature is its id",
            str(labels),
        )
        names = [p["name"] for p in state["roster"]]
        check.that(
            all(n.startswith(("p", "m")) for n in names),
            "with names off, every power is its id",
            str(names),
        )
        # The printed rule is the publisher's sentences too, so it is absent
        # rather than blanked -- serving an empty "Hit:" is still serving it.
        prose = [
            p["name"]
            for p in state["roster"]
            if p["hit_text"] is not None or p["effect_text"] is not None
        ]
        check.that(not prose, "with names off, no printed rule text is served", str(prose[:3]))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--show", action="store_true", help="narrate each action taken")
    args = ap.parse_args()

    check = Checks()
    print("playing a fight over HTTP")
    with Server() as server:
        eid, state = play(server, check, show=args.show)
        events = check_stream(server, check, eid)
        check_no_engine_ids(check, state, events)
    print("\nthe same game with CE_NAMES=off")
    check_hosted(check)

    print(f"\n{check.passed} checks passed, {len(check.failed)} failed")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
