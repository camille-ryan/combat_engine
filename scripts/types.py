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
        # **Merged, and only ever downward.** This wrote `_per_file(text)`
        # straight over the file, so blessing after a narrow run kept the
        # files it had just checked and **deleted every other entry** -- one
        # invocation took the baseline from 317 files to 7 and 1,993 errors
        # to 58. Nothing was loosened by that, which is why it would not
        # have shown up as a red run: a missing entry reads as 0 and makes
        # the file stricter. It just silently threw away the record.
        #
        # So: start from what is there, lower an entry that improved, and
        # refuse to raise one. A count that got worse is a thing to fix or
        # to argue for, never to bless -- `scripts/CLAUDE.md`'s first rule.
        #
        # **And `ty`'s per-file counts move with the file set it is given**,
        # so only the files actually checked in this run are touched:
        # `cast.py` reports 44 alone and 45 across the whole scope, and
        # recording the narrower figure makes `--all` red for no reason.
        base = _baseline()
        now = _per_file(text)
        lowered = {f: (base[f], n) for f, n in now.items()
                   if f in base and n < base[f]}
        risen = {f: (base[f], n) for f, n in now.items()
                 if f in base and n > base[f]}
        # **A file arriving with errors is refused too.** The first draft let
        # one in as a "fresh" entry, and a plant proved it: a file with no
        # baseline has an implied 0, so recording its count is a loosening
        # wearing a different word. Only a clean newcomer is recorded, which
        # is what keeps a file from entering the record already in debt.
        fresh = {f: n for f, n in now.items() if f not in base and not n}
        arriving = {f: n for f, n in now.items() if f not in base and n}
        base.update({f: n for f, (_was, n) in lowered.items()})
        base.update(fresh)
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(base, indent=2, sort_keys=True) + "\n")
        for f, (was, n) in sorted(lowered.items()):
            print(f"  tightened {f}: {was} -> {n}")
        for f, n in sorted(fresh.items()):
            print(f"  recorded  {f}: {n} (was not in the baseline)")
        for f, (was, n) in sorted(risen.items()):
            print(f"  LEFT ALONE {f}: {was} -> {n} is worse; fix it or argue"
                  f" for it, do not bless it")
        for f, n in sorted(arriving.items()):
            print(f"  LEFT ALONE {f}: arriving with {n} error(s) and no"
                  f" baseline; an implied 0 is the stricter record")
        print(f"blessed {len(lowered) + len(fresh)} file(s);"
              f" {len(risen) + len(arriving)} refused; {len(base)} entries total")
        return 1 if (risen or arriving) else 0

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
