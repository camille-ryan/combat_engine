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

    def stream(self, path: str, limit: int = 4000) -> list[dict]:
        out = []
        handle = urllib.request.urlopen(self.base + path, timeout=20)
        for raw in itertools.islice(handle, limit):
            line = raw.decode().strip()
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
            if len(out) >= limit:
                break
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
    events = server.stream(f"/api/encounter/{eid}/events?from=0")
    seqs = [e["seq"] for e in events]
    check.that(seqs == sorted(seqs), "the stream arrives in order")
    check.that(len(seqs) == len(set(seqs)), "every event arrives exactly once")
    check.that(
        seqs[:1] == [0] if seqs else False,
        "replaying from the start really starts at the start",
    )
    narrated = [e for e in events if e["text"]]
    check.that(len(narrated) > 20, f"the log reads as prose ({len(narrated)} lines)")
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
