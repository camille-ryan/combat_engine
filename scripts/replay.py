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

from combat_engine.engine.turns import extended_rest, short_rest
from combat_engine.policy import install, take_turn
from combat_engine.policy.doctrine import DoctrinePolicy
from fight import build

FIXTURES = Path(__file__).parent / "fixtures"

#: A feat's ref, for picking them back out of `Powers.known`.
FEAT = re.compile(r"f\d+[a-z]?")

#: Each fixture is a fight this engine should always play the same way.
CASES = [
    {"name": "level-1-full", "seed": 7, "level": 1, "scaling": "full",
     "enemies": ['m145', 'm264', 'm2998', 'm2978']},
    {"name": "level-1-alt", "seed": 11, "level": 1, "scaling": "full",
     "enemies": ['m441', 'm2821', 'm5029', 'm4865']},
    {"name": "level-1-bounded", "seed": 7, "level": 1, "scaling": "bounded",
     "enemies": ['m145', 'm264', 'm2998', 'm2978']},
    {"name": "level-3-full", "seed": 5, "level": 3, "scaling": "full",
     "enemies": ['m4851', 'm371', 'm2824', 'm3020']},
    {"name": "level-5-full", "seed": 3, "level": 5, "scaling": "full",
     "enemies": ['m4801', 'm4709', 'm2817', 'm4852']},
    {"name": "level-5-bounded", "seed": 3, "level": 5, "scaling": "bounded",
     "enemies": ['m4801', 'm4709', 'm2817', 'm4852']},
    # **Level 10, because the net stopped at 5 and the project stops at 10** --
    # and because scoring the power draw cost `SecondWind` its only coverage.
    # A party that picks its cards on purpose wins before anybody is hurt
    # enough to need one, so the rule went from exercised to unreached, which
    # `coverage` is here to catch and did. This seed is the one of three tried
    # that bloodies somebody.
    {"name": "level-10-full", "seed": 3, "level": 10, "scaling": "full",
     "enemies": ['m4964', 'm3069', 'm5002', 'm221']},
    # **The rest window, which had no net at all.** `coverage` reported
    # `ShortRested` and `ExtendedRested` at zero, and `replay.py`'s own
    # docstring says what a zero means: *"a rule that no fixture reaches can
    # be changed freely and nothing will say a word."* Both rests ran only
    # under `drivers`, which asserts one situation; a fixture compares a
    # whole fight event by event, which is what catches what nobody thought
    # to assert.
    #
    # Level 1 deliberately, and the same board as `level-1-full`: the fight
    # half is already proven by that fixture, so what this one adds is the
    # cheapest possible amount of new ground -- the two rests on a party
    # that has actually spent something. #525.
    {"name": "level-1-rested", "seed": 7, "level": 1, "scaling": "full",
     "enemies": ['m145', 'm264', 'm2998', 'm2978'], "rest": "both"},
]


#: `frozenset({...})` inside an event's repr, with its members captured.
#: No nesting to worry about: the members are scalars and enum reprs like
#: `<Keyword.MARTIAL: 'martial'>`, neither of which carries a brace.
_FROZEN = re.compile(r"frozenset\(\{([^{}]*)\}\)")


def _settled(line: str) -> str:
    """One event's repr, with every `frozenset` put in a fixed order.

    **The regression net was flaky and nobody had caught it.** A `frozenset`
    reprs in hash order, `str` hashes are **salted per process**, and the
    line this file records is `str(event)` -- so any event carrying a
    multi-member frozenset recorded in one order and verified in another,
    at random, per run. Measured on `level-10-full`: three consecutive
    `verify` runs over an unchanged tree gave ok / DIVERGED / DIVERGED, all
    at event 1912, on

        recorded: keywords=frozenset({MARTIAL, RELIABLE, WEAPON})
        now:      keywords=frozenset({MARTIAL, WEAPON, RELIABLE})

    -- the same set, printed two ways. A spurious divergence on the
    regression net costs what a spurious `audit` raise costs, and for the
    same reason: it is the one number here that is supposed to be
    inviolable.

    Sorting the members rather than pinning `PYTHONHASHSEED`, because the
    seed would have to be set by every caller -- `check.py`, the nightly,
    a session running this by hand -- and a fixture recorded under one
    seed would be unverifiable without it. Normalising the text needs
    nothing from the environment.
    """
    return _FROZEN.sub(
        lambda m: "frozenset({"
        + ", ".join(sorted(p.strip() for p in m.group(1).split(",") if p.strip()))
        + "})",
        line,
    )


def play(case: dict) -> list[str]:
    world, encounter = build(
        case["seed"], case["level"], case["scaling"],
        feats=case.get("feats"), powers=case.get("powers"),
        enemies=case.get("enemies"), pcs=case.get("pcs"),
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
    # **The rest, after the fight and inside what the log records.** #525
    # read the single-fight path as unable to cover this -- *"a replay
    # fixture records one encounter from its start, so the rest happens
    # outside what is recorded"* -- and that is true of a rest taken
    # *before* `start()`, which is where `fight.py --rest` puts it. Taken
    # afterwards it is on the same bus the fixture reads, and it is also the
    # only place a rest means anything: the party has spent surges and
    # encounter powers by then, so the refresh has something to refresh.
    # Measured: 8 `ShortRested` and 8 `ExtendedRested` on a level-5 board.
    #
    # A second encounter with the carry between is a bigger thing and is
    # **not** needed for these events; `api/day.py`'s legs already exercise
    # the carry, and `api_smoke` asserts it equals the sheets exactly.
    if case.get("rest") in ("short", "both"):
        short_rest(world)
    if case.get("rest") in ("extended", "both"):
        extended_rest(world)
    return [_settled(str(e)) for e in world.bus.log]


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


def _drawn_powers(case: dict) -> dict[str, list[str]]:
    """Which hand this seed deals each class, **pre-swap**.

    The other half of `_drawn`, and it exists for the same reason stated
    there: a hand is drawn from the pool of *declared* rows, so writing a
    clause into a power could change which powers a character is dealt --
    and from there the action menu, what the policy is offered, and every
    choice after it. Measured on `level-5-full`: adding one feat clause to
    `p992` put it into a character's hand that had not held it, displacing
    another row, and three fixtures diverged. #783.

    **Pre-swap, which is what `chargen.dealt_hand` returns.** `power_swap` is
    not idempotent -- one row leaves per feat that trades one -- so recording
    the post-swap list and feeding it back through `spawn` would take a second
    card away on every record. Pinning the pre-swap hand lets `spawn`'s single
    swap run exactly as it always has, which is what makes this pin
    behaviour-neutral: recording it changes no log.

    Derived rather than read off the board, because `Powers.known` holds the
    post-swap hand mixed in with class features, racial rows and item powers,
    and picking "the powers" back out of that by ref shape is how a pin comes
    to cover less than it says.
    """
    from combat_engine.chargen import build_of, dealt_hand
    from combat_engine.engine import Ident

    world, _ = build(case["seed"], case["level"], case["scaling"])
    out: dict[str, list[str]] = {}
    for _eid, ident in sorted(world.each(Ident)):
        if not ident.ref.startswith("c:"):
            continue
        key = ident.ref.removeprefix("c:")
        out[key] = dealt_hand(
            case["seed"], key, case["level"], build_of(key, "")
        )
    return out


def _pinned_powers(case: dict, redraw: bool) -> dict[str, list[str]]:
    """The saved hand, unless `--redraw`. `_pinned`'s reasoning, verbatim."""
    if not redraw:
        path = FIXTURES / f"{case['name']}.json"
        if path.exists():
            saved = json.loads(path.read_text()).get("powers")
            if saved:
                return saved
    return _drawn_powers(case)


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


def record(redraw: bool = False, only: str = "") -> int:
    """Write the fixtures. `only` names one case.

    **One case at a time matters more than it looks.** Recording is how a
    real regression rides in unseen, so a run that rewrites seven fixtures
    to add an eighth is seven chances to bless a divergence nobody read.
    With `only`, adding a fixture touches exactly the file it adds and the
    other seven stay available to `verify` as the control. #525.
    """
    FIXTURES.mkdir(parents=True, exist_ok=True)
    chosen = [c for c in CASES if not only or c["name"] == only]
    if only and not chosen:
        # `str(...)` because a case dict holds lists as well as strings, so
        # `c["name"]` is not provably one and `join` refuses the generator.
        print(f"no case named {only!r}. Have: "
              f"{', '.join(str(c['name']) for c in CASES)}", file=sys.stderr)
        return 1
    for case in chosen:
        pinned = {**case, "feats": _pinned(case, redraw),
                  "powers": _pinned_powers(case, redraw)}
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
        got = play({**case, "feats": saved.get("feats"),
                    "powers": saved.get("powers")})
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
    ap.add_argument(
        "--only",
        default="",
        metavar="NAME",
        help="record just this case, leaving the others as they are",
    )
    args = ap.parse_args()
    if args.action == "record":
        return record(args.redraw, args.only)
    return {"verify": verify, "coverage": coverage}[args.action]()


if __name__ == "__main__":
    raise SystemExit(main())
