#!/usr/bin/env python
"""Run every instrument, and say which ones are unhappy.

    uv run scripts/check.py            all of it
    uv run scripts/check.py --all      and audit every row, not just changed ones
    uv run scripts/check.py --fast     skip the two that start a server
    uv run scripts/check.py --history  what each has cost, and what it has caught
    uv run scripts/check.py --list     what it would run, and what each catches

There is no CI and no test runner here -- the repo owner does not want tests
written -- so these are *instruments* rather than a suite: each one plays the
real thing and reports what it saw. The gap this closes is that they were
only ever run by hand, one at a time, which is a fine way to forget the one
that would have caught it.

Exit code is the number of instruments that failed, so it is usable as a
gate without reading the output.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Instrument:
    name: str
    argv: tuple[str, ...]
    catches: str
    #: Starts a server and drives a browser. Slow, and skipped by `--fast`.
    heavy: bool = False


CHECKS = (
    Instrument("ruff", ("uv", "run", "scripts/lint.py"),
               "style, dead imports, undefined names, shadowed methods"),
    Instrument("audit", ("uv", "run", "scripts/audit.py", "--changed"),
               "every declared row fires, and does something"),
    Instrument("leaks", ("uv", "run", "scripts/leaks.py"),
               "no printed name reached the tree"),
    Instrument("replay", ("uv", "run", "scripts/replay.py", "verify"),
               "the engine still plays the recorded fights"),
    Instrument("fight", ("uv", "run", "scripts/fight.py", "--quiet"),
               "a whole fight runs to a finish"),
    Instrument("api", ("uv", "run", "scripts/api_smoke.py"),
               "the wire: options, streams, names off", heavy=True),
    Instrument("browser", ("uv", "run", "scripts/browser.py"),
               "the page itself, in Chromium", heavy=True),
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--fast", action="store_true", help="skip the two that start a server")
    ap.add_argument("--list", action="store_true", help="what would run")
    ap.add_argument("--verbose", action="store_true", help="show each instrument's output")
    ap.add_argument("--history", action="store_true",
                    help="what each has cost, and what it has caught")
    ap.add_argument("--only", help="run just these, comma separated")
    ap.add_argument("--all", action="store_true",
                    help="audit every row, not only the ones in changed files")
    args = ap.parse_args()

    if args.history:
        return history()

    wanted = [c for c in CHECKS if not (args.fast and c.heavy)]
    if args.all:
        # `--changed` is the default because auditing everything is twenty
        # seconds today and minutes once the content is written, and most
        # runs have touched a handful of rows. Before a commit, run the lot.
        wanted = [
            Instrument(c.name, tuple(a for a in c.argv if a != "--changed"),
                       c.catches, c.heavy)
            for c in wanted
        ]
    if args.only:
        keep = {n.strip() for n in args.only.split(",")}
        wanted = [c for c in wanted if c.name in keep]
    if args.list:
        for c in wanted:
            print(f"  {c.name:9} {'(slow) ' if c.heavy else '       '}{c.catches}")
        return 0

    failed: list[str] = []
    width = max(len(c.name) for c in wanted)
    at = _commit()
    for c in wanted:
        started = time.monotonic()
        done = subprocess.run(c.argv, cwd=ROOT, capture_output=True, text=True)
        took = time.monotonic() - started
        tail = _summary(done.stdout) or _summary(done.stderr)
        mark = "ok  " if done.returncode == 0 else "FAIL"
        print(f"  {mark}  {c.name:{width}}  {took:5.1f}s  {tail}")
        _record(c.name, took, done.returncode == 0, at)
        if done.returncode != 0:
            failed.append(c.name)
            if not args.verbose:
                # The failing lines only, which is what is worth reading.
                for line in (done.stdout + done.stderr).splitlines():
                    if "FAIL" in line or "diverged" in line.lower() or "error" in line.lower():
                        print(f"          {line.strip()[:110]}")
        if args.verbose:
            print("\n".join(f"          {x}" for x in done.stdout.splitlines()[-25:]))

    print()
    if failed:
        print(f"{len(failed)} unhappy: {', '.join(failed)}")
    else:
        print(f"all {len(wanted)} instruments clean")
    return len(failed)


# --------------------------------------------------------------------------
# What each one costs, and what it has ever caught
# --------------------------------------------------------------------------
#
# The first attempt at this project grew a check suite that nobody could
# afford to run, and the reason it got that way is that nothing measured it:
# every instrument looked worth its time in the abstract, and none of them
# had to show what it had found. So each run is written down, and
# `--history` prints the two numbers that decide whether an instrument earns
# its place -- what it costs, and what it has caught.
#
# Local, and git-ignored: a timing is about this machine, and a hit rate is
# about how this clone has been used.

LEDGER = ROOT / "logs" / "instruments.jsonl"


def _record(name: str, seconds: float, ok: bool, at: str) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as fh:
            fh.write(json.dumps({
                "when": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "name": name, "seconds": round(seconds, 2), "ok": ok, "commit": at,
            }) + "\n")
    except OSError:
        pass  # never let bookkeeping be the thing that fails a check run


def _commit() -> str:
    done = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def history() -> int:
    if not LEDGER.exists():
        print("# nothing recorded yet -- run it a few times")
        return 0
    rows = [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]
    if not rows:
        print("# nothing recorded yet")
        return 0

    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["name"], []).append(r)

    print(f"  {'instrument':10} {'runs':>5} {'median':>7} {'spent':>8} "
          f"{'caught':>7} {'per catch':>10}  last catch")
    order = sorted(by, key=lambda n: -sum(r["seconds"] for r in by[n]))
    for name in order:
        runs = by[name]
        secs = sorted(r["seconds"] for r in runs)
        spent = sum(secs)
        caught = [r for r in runs if not r["ok"]]
        per = f"{spent / len(caught):.0f}s" if caught else "never"
        last = caught[-1]["when"][:10] if caught else "--"
        print(f"  {name:10} {len(runs):5} {secs[len(secs) // 2]:6.1f}s "
              f"{spent:7.0f}s {len(caught):7} {per:>10}  {last}")

    total = sum(r["seconds"] for r in rows)
    caught = sum(1 for r in rows if not r["ok"])
    print(f"\n  {total:.0f}s spent over {len(rows)} instrument-runs, "
          f"{caught} of them caught something")
    idle = [n for n in order if all(r["ok"] for r in by[n]) and len(by[n]) >= 20]
    if idle:
        print(f"  never caught anything in 20+ runs: {', '.join(idle)}"
              f"\n  -- worth asking whether they still earn their seconds")
    return 0


def _summary(text: str) -> str:
    """The one line of an instrument's output worth putting in a table."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line[:80]
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
