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
import json
import re
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


#: Per-file error counts as of the last time this was blessed. **A baseline
#: that may shrink and must not grow**, which is `fixtures/audited.json`'s
#: contract and is here for the same reason: the content tree carries years
#: of standing type debt, so a file with 6 pre-existing errors must not fail
#: the moment somebody edits an unrelated line in it.
#:
#: The first version of this had no baseline and went red on exactly that --
#: three monster files with 4, 6 and 7 standing errors, none of them near the
#: change. A check that cannot pass stops being read, which `audit.py`'s own
#: docstring records the cost of.
BASELINE = ROOT / "scripts" / "fixtures" / "types.json"


def _baseline() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text())


def _per_file(text: str) -> dict[str, int]:
    """How many errors each file owns, from `ty`'s own output."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"\s*-->\s*([^:]+\.py):", line)
        if m:
            rel = m.group(1)
            out[rel] = out.get(rel, 0) + 1
    return out


def _run(paths: list[str]) -> tuple[int, str]:
    done = subprocess.run(["uvx", "ty", "check", *paths], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    text = done.stdout + done.stderr
    count = sum(1 for ln in text.splitlines() if ln.startswith("error["))
    return count, text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bless", action="store_true",
                    help="record the current counts as the baseline")
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

    _, text = _run(targets)
    if args.bless:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(_per_file(text), indent=2, sort_keys=True) + "\n")
        print(f"blessed {len(_per_file(text))} file(s) at their current counts")
        return 0

    base = _baseline()
    now = _per_file(text)
    worse = {f: (n, base.get(f, 0)) for f, n in now.items() if n > base.get(f, 0)}
    if worse:
        print(text.rstrip())
        print()
        for f, (n, was) in sorted(worse.items()):
            print(f"  {f}: {n} error(s), baseline {was}")
        print(f"\n{sum(n - w for n, w in worse.values())} error(s) above the baseline")
        return 0 if args.all else 1
    carried = sum(now.values())
    note = f" ({carried} carried, at or below baseline)" if carried else ""
    print(f"ok: {len(targets)} file(s) checked{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
