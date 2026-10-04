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
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _printed_feature_names() -> set[str]:
    """Every class feature's printed name, normalised for comparison.

    Read straight off `localization/names.json` rather than through the
    package. **This harness imports no `combat_engine` on purpose** -- it is an
    HTTP client and the server is the thing under test, so sharing the server's
    code would let one bug agree with itself. `scripts/leaks.py` reads the same
    file the same way.

    Empty when the file is absent, which makes the check that uses it vacuous
    rather than wrong. It says so where it is used.
    """
    path = ROOT / "localization" / "names.json"
    if not path.is_file():
        return set()
    try:
        table = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    out = {
        (entry.get("name") or "").strip().lower().replace("-", " ")
        for ref, entry in table.items()
        if ref.startswith("cf:")
    }
    out.discard("")
    return out


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
            # **Its own process group, so teardown can reach the server.**
            # `self.proc` is the `uv` wrapper, not uvicorn -- terminating it
            # left the real server running, reparented to PID 1. 69 of them
            # had accumulated over three and a half days, holding 328 MB and
            # contending for the cores the audit is trying to use.
            start_new_session=True,

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
        """Signal the whole process group, not just the wrapper.

        `self.proc` is the `uv run ...` handle; the uvicorn is its child.
        `terminate()` killed `uv` and left the server running, reparented to
        PID 1 -- **69 of them had accumulated over three and a half days**,
        holding 328 MB and contending for the cores the audit needs. That is
        what `start_new_session=True` above is for: `killpg` reaches both.

        Killed rather than asked politely if it dawdles. A uvicorn holding
        an event stream open can outlast a polite terminate, and the wait
        raising turned a clean run into a failure *after* every check had
        passed -- the instrument reporting on its own teardown.
        """
        if not self.proc:
            return
        import signal

        try:
            group = os.getpgid(self.proc.pid)
        except (ProcessLookupError, PermissionError):
            group = None
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                if group is not None:
                    os.killpg(group, sig)
                elif sig == signal.SIGTERM:
                    self.proc.terminate()
                else:
                    self.proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=10)
                return

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


def play(
    server: Server, check: Checks, *, show: bool,
    seen_labels: set[tuple[str, str]] | None = None,
) -> tuple[str, dict]:
    seen_labels = seen_labels if seen_labels is not None else set()
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
        # Every label the fight ever offers, kept for `check_option_labels`.
        # **Checking only the state in hand is why a wield label went unseen**:
        # the opening state has no stowed weapon to take up, so a check written
        # against one snapshot passed while the label said `take up w3611`.
        seen_labels.update(
            (o["kind"], o["label"] or "") for o in options
        )
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


#: A ref where a word belongs. `w3611`, `p12609`, `m145a2`, `w:rod`, `cf:...`.
_REFFY = re.compile(r"\b(?:[wpmifr]\d{2,}(?:a\d+)?|w:[a-z-]+|cf:[a-z0-9-]+)\b")


def check_option_labels(check: Checks, seen: set[tuple[str, str]]) -> None:
    """No option's label is a ref, across **every** option the fight offered.

    A different question from "every option targets a wire id", and nobody was
    asking it. `render._option_label` built the `wield` label by string surgery
    on the weapon ref: before #339 that served the printed name straight to the
    page around `wire` (#342), and after it the label read `take up w3611`.
    Either way the tell is an identifier where a word should be.

    **Accumulated over the whole fight rather than read off one state**, which
    is the correction that makes this cover anything. Written against the
    opening state it passed with the broken label still in place -- there is no
    stowed weapon to take up on round one, so the option it exists to check was
    never in the snapshot. The first version of this check was as weak as the
    casing test it was written to replace.

    Reports which kinds were actually seen, because a check that silently
    covered three option kinds out of eight is not a check -- `scripts/CLAUDE.md`
    on an instrument that must not skip itself quietly.
    """
    raw = sorted(f"{kind}: {label}" for kind, label in seen if _REFFY.search(label))
    kinds = sorted({kind for kind, _ in seen})
    check.that(
        not raw,
        f"no option label is a bare ref, over {len(seen)} labels "
        f"of {len(kinds)} kinds ({', '.join(kinds)})",
        str(raw[:3]),
    )


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
    # The *property*, not the situation. This used to require that somebody
    # in this one fight had a power out of range at this one moment, which
    # is a fact about the seed and the initiative order rather than about
    # the interface -- and it duly failed the first time the roster shifted
    # under it, with nothing wrong.
    vague = [
        p["name"] for p in greyed
        if "squares away" in (p["reason"] or "")
        and not any(ch.isdigit() for ch in p["reason"])
    ]
    check.that(
        not vague,
        "where distance is the answer, the reason is the number",
        str(vague[:3]),
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
            all(IS_REF.match(n) for n in names),
            "with names off, every power is its id",
            str([n for n in names if not IS_REF.match(n)]),
        )
        # The printed rule is the publisher's sentences too, so it is absent
        # rather than blanked -- serving an empty "Hit:" is still serving it.
        prose = [
            p["name"]
            for p in state["roster"]
            if p["hit_text"] is not None or p["effect_text"] is not None
        ]
        check.that(not prose, "with names off, no printed rule text is served", str(prose[:3]))

        # **The chargen advisor is the largest new name surface there is.** It
        # is the first thing that shows a *race* and a *feat* to a human, and
        # there are 46 and ~2,000 of them. Everything it shows goes through the
        # same `Wire.power` the fight page uses, so with names off a label is
        # its ref -- and that is asserted here rather than trusted, because the
        # page was built after this check and would not otherwise be covered.
        options = server.get("/api/chargen/options?cls=fighter")
        shown = [
            c["label"]
            for kind in ("races", "feats")
            for c in options[kind]
            if c["label"] != c["ref"]
        ]
        check.that(
            not shown,
            "with names off, every chargen option is its ref",
            str(shown[:3]),
        )
        # A build leg's printed name is a name like any other, and it is the
        # newest thing to go through `Wire`. With names off it must be the
        # slug -- `Wire.build` falls back through `power`, so this is asserting
        # the fallback and not merely the happy path.
        legs = [
            b["label"]
            for entry in server.get("/api/chargen/classes")
            for b in entry["builds"]
        ]
        # **Lower case is not the test, and testing it is how four printed names
        # got served.** This asserted `lb != lb.lower()`, and four warden legs
        # were named for their printed class-feature options -- `earthstrength`
        # and three more, every one already lower case. The check passed on all
        # of them while `Wire.build`'s fallback returned the printed word
        # verbatim under `CE_NAMES=off`. #342, found by #337 rather than here.
        #
        # So the test is the one the question actually asks: **is this label a
        # printed name?** Read off the localisation, which this script may do --
        # it is `scripts/leaks.py`'s whole method and the server is the thing
        # under test, not this.
        # Vacuous without a name table, which is the right failure: a machine
        # with no `localization/` has nothing to leak.
        printed = _printed_feature_names()
        leaked = [
            lb for lb in legs
            if lb != lb.lower() or lb.lower().replace("-", " ") in printed
        ]
        check.that(
            not leaked,
            "with names off, a build leg is its slug and not a printed name",
            str(leaked[:3]),
        )
        # A score is not a name and must survive the hosted mode: a page that
        # ranks nothing is no use to anybody running without a name table.
        check.that(
            options["races"] and options["races"][0]["terms"],
            "with names off, the scores and their reasons still come through",
        )


#: Every shape of id the engine uses for a row. A compendium power or
#: monster ability, a class feature the books describe on the class page and
#: give no row of its own (`cf:`), and the two attacks the engine names
#: itself. The check used to be "starts with p or m", which was fine until
#: the party finally carried its class features and `cf:rogue-scoundrel-f4` --
#: which *is* its own id, and is exactly what serving no printed name looks
#: like -- read as a failure.
IS_REF = re.compile(r"^(p\d+|m\d+a\d+|cf:[a-z0-9-]+|mba|rba|second-wind)$")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--show", action="store_true", help="narrate each action taken")
    args = ap.parse_args()

    check = Checks()
    print("playing a fight over HTTP")
    with Server() as server:
        labels: set[tuple[str, str]] = set()
        eid, state = play(server, check, show=args.show, seen_labels=labels)
        events = check_stream(server, check, eid)
        check_no_engine_ids(check, state, events)
        check_option_labels(check, labels)
    print("\nthe same game with CE_NAMES=off")
    check_hosted(check)

    print(f"\n{check.passed} checks passed, {len(check.failed)} failed")
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
