#!/usr/bin/env python
"""The regression net.

    uv run scripts/replay.py record          re-record every fixture
    uv run scripts/replay.py verify          re-run them and diff
    uv run scripts/replay.py coverage        which event kinds are exercised

Combat contains no randomness beyond one seeded generator, so a fixture that
stops matching is always a code change and never a bad roll. `verify` prints
the first diverging event and stops -- the first difference is the one worth
reading, and everything after it is a consequence.

The fixtures are committed on purpose. A fresh clone with nothing to verify
against has no regression net at all.

**It only guards what it runs.** `coverage` exists because that is easy to
forget: a rule that no fixture reaches can be changed freely and nothing will
say a word. When it reports an event kind at zero, that is a fixture waiting
to be written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from combat_engine.policy import install, take_turn
from combat_engine.policy.doctrine import DoctrinePolicy
from fight import build

FIXTURES = Path(__file__).parent / "fixtures"

#: A feat's ref, for picking them back out of `Powers.known`.
FEAT = re.compile(r"f\d+[a-z]?")

#: Each fixture is a fight this engine should always play the same way.
CASES = [
    {"name": "level-1-full", "seed": 7, "level": 1, "scaling": "full"},
    {"name": "level-1-alt", "seed": 11, "level": 1, "scaling": "full"},
    {"name": "level-1-bounded", "seed": 7, "level": 1, "scaling": "bounded"},
    {"name": "level-3-full", "seed": 5, "level": 3, "scaling": "full"},
    {"name": "level-5-full", "seed": 3, "level": 5, "scaling": "full"},
    {"name": "level-5-bounded", "seed": 3, "level": 5, "scaling": "bounded"},
]


def play(case: dict) -> list[str]:
    world, encounter = build(
        case["seed"], case["level"], case["scaling"],
        feats=case.get("feats"),
    )
    policy = DoctrinePolicy()
    install(world, encounter, {}, default=policy)
    encounter.start()
    while not encounter.finished and world.round <= 40:
        actor = world.turn
        if actor is None:
            break
        take_turn(world, encounter, actor, policy)
        encounter.advance()
    return [str(e) for e in world.bus.log]


def _drawn(case: dict) -> dict[str, list[str]]:
    """Which feats this seed deals each class, right now.

    Recorded into the fixture so that replaying it later deals the same
    ones. A character's feats come from the pool of *declared* ones, so
    without this every content wave changed the party, every fixture
    diverged, and the only way through was to re-record -- under which a
    real regression could ride in unseen. Pinning them makes the fixture
    a test of the engine again rather than of how much content exists.
    """
    from combat_engine.engine import Gear, Ident, Powers  # noqa: F401

    world, _ = build(case["seed"], case["level"], case["scaling"])
    out: dict[str, list[str]] = {}
    for eid, ident in sorted(world.each(Ident)):
        if not ident.ref.startswith("c:"):
            continue
        known = world.get(eid, Powers)
        if known is None:
            continue
        out[ident.ref.removeprefix("c:")] = sorted(
            r for r in known.known if FEAT.fullmatch(r)
        )
    return out


def _pinned(case: dict, redraw: bool) -> dict[str, list[str]]:
    """The feats this fixture should run with.

    **The saved ones, unless you say otherwise.** `_drawn` exists so that
    a content wave does not change the party, and re-dealing on every
    `record` gave that away again at the only moment it mattered: the
    fixtures are re-recorded precisely *after* a wave, which is when the
    pool has just moved. One run here re-drew the level-5 party and the
    log went from 1,431 events to 2,622 -- a diff nobody can read, and a
    real regression could ride in under it.

    Re-dealing is still the right thing when the party itself is meant
    to change, so it is `--redraw` rather than gone.
    """
    if not redraw:
        path = FIXTURES / f"{case['name']}.json"
        if path.exists():
            saved = json.loads(path.read_text()).get("feats")
            if saved:
                return saved
    return _drawn(case)


def record(redraw: bool = False) -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        pinned = {**case, "feats": _pinned(case, redraw)}
        log = play(pinned)
        path = FIXTURES / f"{case['name']}.json"
        path.write_text(json.dumps({**pinned, "log": log}, indent=1))
        print(f"  {case['name']:<18} {len(log):5d} events")
    return 0


def verify() -> int:
    if not FIXTURES.exists():
        print("no fixtures. Run: uv run scripts/replay.py record", file=sys.stderr)
        return 1
    bad = 0
    for case in CASES:
        path = FIXTURES / f"{case['name']}.json"
        if not path.exists():
            print(f"  {case['name']:<18} MISSING")
            bad += 1
            continue
        saved = json.loads(path.read_text())
        want = saved["log"]
        got = play({**case, "feats": saved.get("feats")})
        where = _diverges(want, got)
        if where is None:
            print(f"  {case['name']:<18} ok      {len(got):5d} events")
            continue
        bad += 1
        print(f"  {case['name']:<18} DIVERGED at event {where}")
        print(f"      recorded: {want[where] if where < len(want) else '(log ended)'}")
        print(f"      now:      {got[where] if where < len(got) else '(log ended)'}")
        for i in range(max(0, where - 3), where):
            print(f"      before:   {want[i]}")
    if bad:
        print(f"\n{bad} of {len(CASES)} fixtures diverged.")
    return 1 if bad else 0


def _diverges(want: list[str], got: list[str]) -> int | None:
    for i in range(max(len(want), len(got))):
        if i >= len(want) or i >= len(got) or want[i] != got[i]:
            return i
    return None


def coverage() -> int:
    """Which event kinds the fixtures actually reach, and which they do not."""
    from combat_engine.engine import events as ev

    seen: Counter[str] = Counter()
    for case in CASES:
        path = FIXTURES / f"{case['name']}.json"
        log = json.loads(path.read_text())["log"] if path.exists() else play(case)
        seen.update(line.split("(")[0] for line in log)

    known = sorted(
        name
        for name in dir(ev)
        if isinstance(getattr(ev, name), type)
        and issubclass(getattr(ev, name), ev.Event)
        and getattr(ev, name) is not ev.Event
    )
    width = max(len(k) for k in known)
    for kind in known:
        n = seen.get(kind, 0)
        flag = "  <- never exercised" if n == 0 else ""
        print(f"  {kind:<{width}}  {n:6d}{flag}")
    missing = [k for k in known if not seen.get(k)]
    print(f"\n  {len(known) - len(missing)} of {len(known)} event kinds exercised")
    if missing:
        print("  unreached: " + ", ".join(missing))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("action", choices=["record", "verify", "coverage"])
    ap.add_argument(
        "--redraw",
        action="store_true",
        help="re-deal each fixture's feats instead of keeping the pinned ones",
    )
    args = ap.parse_args()
    if args.action == "record":
        return record(args.redraw)
    return {"verify": verify, "coverage": coverage}[args.action]()


if __name__ == "__main__":
    raise SystemExit(main())
