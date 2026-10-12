"""Does the code mean what its signatures say? `ty`, on the files that moved.

**Changed files only, and that is the whole design.** Pointed at `engine/`
alone this reports **113** diagnostics, nearly all of them standing debt from
before it existed; pointed at `scripts/drivers.py` it reports 40. Fixing that
backlog is a project and suppressing it is noise, so neither is what this is
for. What it is for is the file you just edited, where the count is normally
zero and anything it says is yours.

**It paid for itself in its first minute**, which is the measurement that
justifies it being here. Three bugs in `features/sorcerer.py`, all committed
an hour earlier, all of them past `ruff`, past `lint.py`, and past `audit`
reporting "2 of 2 rows fire and do something":

* `c.flat(amount, DamageType.FIRE, ...)` -- `dtype` is keyword-only.
* `c.teleport(n, on=me)` -- the parameter is `who=`.
* `c.choose` returns `T | None` and the result went into a dict lookup.

Two of the three would have raised in a real fight and `audit` could not see
them: the branches only run on a `TurnStart` or a `Miss` while the creature
is in one particular phase, which its board never reaches. That is the gap
this fills -- not "is the row written", but "would the code run at all".

Not a gate on the backlog. `--all` exists to look at the standing debt
deliberately, and it is expected to be red.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Where a type error is worth hearing about. `content/` is deliberately out:
#: 677 modules of hand-written rows, written by many agents over a long time,
#: and a row is data more than logic -- the per-file run below still covers
#: any content file that actually changed, which is the case that matters.
SCOPE = ("src/combat_engine/engine", "src/combat_engine/chargen",
         "src/combat_engine/api", "src/combat_engine/etl", "scripts")


def _changed() -> list[str]:
    """Python files that differ from HEAD, staged or not, plus untracked."""
    out: set[str] = set()
    for args in (["diff", "--name-only", "HEAD"],
                 ["ls-files", "--others", "--exclude-standard"]):
        done = subprocess.run(["git", *args], cwd=ROOT,
                              capture_output=True, text=True, check=False)
        out |= {ln.strip() for ln in done.stdout.splitlines() if ln.strip()}
    return sorted(f for f in out if f.endswith(".py") and (ROOT / f).exists())


def _run(paths: list[str]) -> tuple[int, str]:
    done = subprocess.run(["uvx", "ty", "check", *paths], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    text = done.stdout + done.stderr
    count = sum(1 for ln in text.splitlines() if ln.startswith("error["))
    return count, text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="the whole scope, backlog included; expected red")
    ap.add_argument("paths", nargs="*", help="specific files")
    args = ap.parse_args()

    if args.paths:
        targets = args.paths
    elif args.all:
        targets = list(SCOPE)
    else:
        targets = _changed()
        if not targets:
            print("no changed Python files")
            return 0

    count, text = _run(targets)
    if count:
        print(text.rstrip())
        print(f"\n{count} type error(s) in {len(targets)} file(s)")
        return 0 if args.all else 1
    print(f"ok: {len(targets)} file(s) clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
