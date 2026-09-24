#!/usr/bin/env python
"""Run every instrument, and say which ones are unhappy.

    uv run scripts/check.py            all of it
    uv run scripts/check.py --fast     skip the two that start a server
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
import subprocess
import time
from dataclasses import dataclass
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
    Instrument("ruff", ("uv", "run", "ruff", "check", "."),
               "style, dead imports, undefined names"),
    Instrument("audit", ("uv", "run", "scripts/audit.py"),
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
    args = ap.parse_args()

    wanted = [c for c in CHECKS if not (args.fast and c.heavy)]
    if args.list:
        for c in wanted:
            print(f"  {c.name:9} {'(slow) ' if c.heavy else '       '}{c.catches}")
        return 0

    failed: list[str] = []
    width = max(len(c.name) for c in wanted)
    for c in wanted:
        started = time.monotonic()
        done = subprocess.run(c.argv, cwd=ROOT, capture_output=True, text=True)
        took = time.monotonic() - started
        tail = _summary(done.stdout) or _summary(done.stderr)
        mark = "ok  " if done.returncode == 0 else "FAIL"
        print(f"  {mark}  {c.name:{width}}  {took:5.1f}s  {tail}")
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
