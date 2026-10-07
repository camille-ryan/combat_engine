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
import re
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
    #: Not run unless asked for by name. Two reasons, and the text should say
    #: which:
    #:
    #: * **its failure is known and not yet understood** -- leaving it in the
    #:   default run trains people to re-run until it passes, which is worse
    #:   than not running it;
    #: * **its value is conditional on what changed** -- a before/after
    #:   measurement is worth its minute on the change it measures and worth
    #:   nothing on the other ninety-nine, and `--history` is where that shows
    #:   up as a cost per catch nobody can defend.
    paused: str = ""


CHECKS = (
    Instrument("ruff", ("uv", "run", "scripts/lint.py"),
               "style, dead imports, undefined names, shadowed methods"),
    Instrument("audit", ("uv", "run", "scripts/audit.py", "--changed"),
               "every declared row fires, and does something"),
    Instrument("leaks", ("uv", "run", "scripts/leaks.py"),
               "no printed name reached the tree"),
    Instrument("specs", ("uv", "run", "scripts/leaks.py", "--specs"),
               "no printed name reached what an author is shown"),
    Instrument("todo", ("uv", "run", "scripts/todo.py"),
               "no `todo=` waits on a symbol that now exists"),
    Instrument("bonuses", ("uv", "run", "scripts/bonuses.py", "--quiet"),
               "every bonus says the type its card prints"),
    # Beside `bonuses` because it is the same question about a different corpus:
    # does the code say the printed number. A monster ability's whole content is
    # its header, so this is most of what can be wrong with one.
    Instrument("cards", ("uv", "run", "scripts/cards.py", "--quiet"),
               "every monster header says the numbers its stat block prints"),
    # **Added because its new half caught a real fork on its first run**, and
    # because nothing else asks this question: a leg's fork decides which rows a
    # character is offered and which race scores best in a draw, and until
    # `PRINTED_LEG` existed there was nothing to compare it against. Seconds to
    # run -- an AST walk over `content/` plus one query. #235.
    Instrument("legs", ("uv", "run", "scripts/legs.py"),
               "every gated leg exists, and agrees with the page it came off"),
    Instrument("replay", ("uv", "run", "scripts/replay.py", "verify"),
               "the engine still plays the recorded fights"),
    Instrument("fight", ("uv", "run", "scripts/fight.py", "--quiet"),
               "a whole fight runs to a finish"),
    # **Both of these were broken by a refactor and nothing noticed**, which is why
    # they are here. Retiring `LinearPolicy` left `winrate.py` with a stale
    # `policy_name="linear"` default, so its ordinary invocation raised `KeyError`
    # on every seed and reported nothing played; `check.py` ran every other
    # instrument and not that one. Two seeds is enough to catch a broken
    # instrument, which is all these two are for -- the numbers they exist to
    # produce need far more and are not a pass/fail question.
    Instrument("winrate", ("uv", "run", "scripts/winrate.py",
                           "--seeds", "2", "--level", "5", "--draw", "scored"),
               "the batch fight runner still runs"),
    # **Paused on its own numbers.** 108 runs, 13,114s -- 12.8% of everything
    # this suite has ever cost -- and 2 of those runs red, which is 6,557s a
    # catch. Its own docstring calls it "the gate on a policy change", and it
    # self-reports a baseline 111 commits stale, so on an ordinary commit it
    # spends a minute comparing against a number that no longer means what it
    # meant. Run it where it is the measurement: `--only scorecard` on a
    # `policy/` change, and `scorecard.py --save` when the change is the
    # improvement.
    Instrument("scorecard", ("uv", "run", "scripts/scorecard.py", "--level", "5"),
               "the policy scorecard still measures",
               paused="value is conditional: a policy/ change, not every commit"),
    Instrument("api", ("uv", "run", "scripts/api_smoke.py"),
               "the wire: options, streams, names off", heavy=True),
    # Un-paused. The intermittent failure was never `check.py` and was never
    # a click that missed: the instrument clicked the fourth highlighted
    # square, the overlay draws the provoking squares first, and a walk that
    # provokes can be stopped by the attack it draws -- 200, nobody moved,
    # nothing wrong. It clicks a free square now. 18 runs straight, in both
    # ways of launching it, against roughly one failure in five before.
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

    asked = {n.strip() for n in args.only.split(",")} if args.only else set()
    wanted = [
        c for c in CHECKS
        if not (args.fast and c.heavy) and (not c.paused or c.name in asked)
    ]
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
        for c in CHECKS:
            if c.paused and c not in wanted:
                print(f"  {c.name:9} PAUSED  {c.paused}")
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
        _record(c.name, took, done.returncode == 0, at,
                _scope(done.stdout))
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
    owed = _sweep_owed()
    if failed:
        print(f"{len(failed)} unhappy: {', '.join(failed)}")
    elif owed:
        # **The one sentence that means "nothing is outstanding" is withheld
        # while something is.** Every instrument still ran and still reported;
        # the verdict is not narrowed, only the claim.
        print(f"{len(wanted)} instruments clean, {owed}")
    else:
        print(f"all {len(wanted)} instruments clean")
    return len(failed)


#: Where `audit.py` records the commit of the last sweep that looked at every
#: row. Read rather than written here -- this only reports the debt.
WATERMARK = ROOT / "scripts" / "fixtures" / "audited.json"


def _sweep_owed() -> str:
    """Is a whole-tree audit outstanding, and since when?

    **The saving this pairs with is only safe if the sweep still happens.** The
    wide sweep is 36% of everything this suite has ever cost and 12x the
    per-catch price of a narrow run, so the protocol is one of them before a
    push rather than one per commit -- and a protocol nobody is reminded of is
    a protocol that lapses. `audit.py` already prints its own baseline age for
    exactly this reason (#291); this is the same discipline one level up, where
    the decision to pay is actually made.

    **Not an exit code.** An owed sweep is not a failure of the change in hand,
    and a run that goes red for a reason unrelated to what you just did is how
    red gets ignored -- which is the failure `scripts/CLAUDE.md` records about a
    check that could not pass.

    Two ways to owe one, and the second is the one a path test cannot see: the
    database is git-ignored, so a rebuild moves every number a row reads with no
    source change to notice. Same argument as `audit._database_moved`.
    """
    try:
        mark = json.loads(WATERMARK.read_text())
    except (OSError, ValueError):
        return "no whole-tree sweep on record -- `check.py --all` writes one"
    sha = mark.get("sha") or ""
    if not sha:
        return "no whole-tree sweep on record -- `check.py --all` writes one"

    database = ROOT / "data" / "game.db"
    try:
        rebuilt = database.stat().st_mtime > WATERMARK.stat().st_mtime
    except OSError:
        rebuilt = False

    done = subprocess.run(["git", "rev-list", "--count", f"{sha}..HEAD"],
                          cwd=ROOT, capture_output=True, text=True)
    behind = int(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else 0
    if rebuilt:
        return (f"wide sweep owed: the database was rebuilt after {sha[:9]}"
                f" -- `check.py --all`")
    if behind:
        return (f"wide sweep owed since {sha[:9]}, {behind} commit(s) back"
                f" -- `check.py --all`")
    return ""


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


#: `audit.py`'s declared contract for how wide a run was. See the note beside
#: the `print` that emits it: keyed on the exact prefix so that moving it makes
#: the field **absent** rather than wrong.
SCOPE = re.compile(r"^# scope: (\d+) of (\d+) declared rows$", re.M)


def _scope(text: str) -> tuple[int, int] | None:
    """How many rows an instrument covered, out of how many there are."""
    found = SCOPE.search(text)
    return (int(found.group(1)), int(found.group(2))) if found else None


def _record(name: str, seconds: float, ok: bool, at: str,
            scope: tuple[int, int] | None = None) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "when": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "name": name, "seconds": round(seconds, 2), "ok": ok, "commit": at,
        }
        # **Only when the instrument said**, so a missing field means "this run
        # did not report its scope" and never "it covered nothing". `history`
        # counts the silent ones out loud rather than averaging over them.
        if scope:
            row["refs"], row["of"] = scope
        with LEDGER.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
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

    # **Split by how wide a run was, not by how long it took.** Answering
    # "is the wide sweep worth it" needed bucketing by duration, which is a
    # proxy for scope that breaks on a faster machine or a bigger corpus. The
    # answer was worth having -- wide sweeps were 36% of everything this suite
    # had cost, at 12x the per-catch price of a narrow run -- so the scope is
    # recorded now and this reads it. `audit.py` is the only instrument that
    # reports one; the rest fall through unsplit.
    by: dict[str, list[dict]] = {}
    quiet = 0
    for r in rows:
        name = r["name"]
        if r.get("of"):
            name = f"{name} {'wide' if r['refs'] >= r['of'] else 'narrow'}"
        elif r["name"] == "audit":
            quiet += 1
        by.setdefault(name, []).append(r)

    print(f"  {'instrument':13} {'runs':>5} {'median':>7} {'spent':>8} "
          f"{'caught':>7} {'per catch':>10}  last catch")
    order = sorted(by, key=lambda n: -sum(r["seconds"] for r in by[n]))
    for name in order:
        runs = by[name]
        secs = sorted(r["seconds"] for r in runs)
        spent = sum(secs)
        caught = [r for r in runs if not r["ok"]]
        per = f"{spent / len(caught):.0f}s" if caught else "never"
        last = caught[-1]["when"][:10] if caught else "--"
        print(f"  {name:13} {len(runs):5} {secs[len(secs) // 2]:6.1f}s "
              f"{spent:7.0f}s {len(caught):7} {per:>10}  {last}")

    total = sum(r["seconds"] for r in rows)
    caught = sum(1 for r in rows if not r["ok"])
    print(f"\n  {total:.0f}s spent over {len(rows)} instrument-runs, "
          f"{caught} of them caught something")
    # Named rather than folded into either half: a run from before the scope
    # was recorded is not a narrow run, and counting it as one would flatter
    # whichever side it landed on. They stay in the undecorated `audit` row.
    if quiet:
        print(f"  {quiet} audit run(s) predate the scope being recorded and are "
              f"counted in the plain `audit` row, not in wide or narrow")
    # Fruitless *and* expensive. An instrument that has never caught
    # anything but has cost fourteen seconds in total is not the one to cut,
    # and flagging it on catches alone invited exactly that mistake.
    idle = [
        n for n in order
        if all(r["ok"] for r in by[n])
        and len(by[n]) >= 20
        and sum(r["seconds"] for r in by[n]) >= 60
    ]
    if idle:
        print(f"  never caught anything in 20+ runs, and not cheap: {', '.join(idle)}"
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
