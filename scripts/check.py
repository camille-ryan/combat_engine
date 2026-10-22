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
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
    Instrument("types", ("uv", "run", "scripts/types.py"),
               "signatures mean what the call says, on the files that moved"),
    Instrument("refs", ("uv", "run", "scripts/refs.py"),
               "every ref a row's prose names resolves to something"),
    # **Beside `refs` because it is the same question about the other
    # vocabulary.** `refs` asks whether a ref a row names exists; this asks
    # whether a *symbol* a row looks up exists, in both directions:
    #
    # * a `Cast` member in no category file, so `docs/symbols/` cannot go
    #   stale as `Cast` grows -- Camille's requirement on the plan, and the
    #   half a hand-written hierarchy cannot keep;
    # * a `when=lambda ctx: ctx.get("...")` naming a key nothing writes.
    #   `m5788a0` is the motivating case: a level-10 soldier whose whole card
    #   is an immunity, reading a `vs` key that no ctx has ever carried, while
    #   eight rows wanting the same fact read it off the event. The row lays
    #   its effect, audits green, and does nothing. #591.
    #
    # Under a second: one import of `content/` and a regex walk. The expensive
    # mistake it is aimed at is the one `vocab.py`'s own docstring records --
    # six verbs that exist marked missing by four agents in one afternoon.
    Instrument("symbols", ("uv", "run", "scripts/symbols.py"),
               "docs/symbols/ is current, and no gate reads an unknown key"),
    Instrument("audit", ("uv", "run", "scripts/audit.py", "--changed"),
               "every declared row fires, and does something"),
    # **The instrument that says whether the one above means anything**, and it
    # was missing. `audit` reported silent 193 -> 107 at `65421a0` and all 86
    # of the difference was credited with one event the rows cannot emit --
    # `f139`, whose whole body is `c.bonus("range", 5)`, was credited with
    # setting a relation. A 17-instrument sweep ran clean through it; this
    # caught it in **seconds**, and nothing was running it.
    #
    # Worse than missing it: `audit`'s baseline only went red because the
    # number *improved*, so re-recording would have made the artifact
    # permanent and every later sweep green. That is the shape
    # `scripts/CLAUDE.md` warns about -- "a check that cannot pass is the same
    # failure pointed the other way" -- arriving from the other side.
    #
    # Cheap enough to be unconditional: ten pinned rows, each run twice
    # (as written and `hollowed`), seconds. `VERDICT_KNOWN` carries the one
    # standing failure by name so this is a gate and not an allowance. #578.
    Instrument("verdicts", ("uv", "run", "scripts/audit.py", "--verdicts"),
               "the verdict itself is honest, on rows whose answer is known"),
    Instrument("leaks", ("uv", "run", "scripts/leaks.py"),
               "no printed name reached the tree"),
    Instrument("specs", ("uv", "run", "scripts/leaks.py", "--specs"),
               "no printed name reached what an author is shown"),
    # **The gate that replaced a construction guarantee**, 2026-10-12: an
    # author is now shown each ref's name so a row can tell when a clause
    # means itself, so something has to ask whether one was written down.
    # Beside `leaks` rather than folded into it because it asks a *narrower*
    # question -- only the refs a file cites -- and therefore needs none of
    # the waivers that give `leaks` its #494 blind spot. Proven by planting
    # `cf:ranger-f1`'s name in a content file: this went red naming the file,
    # and `leaks` in the same run still said "no printed names in tracked
    # files". Twenty real leaks on its first run, including five in one SQL
    # comment and one in a `trigger=` string the page renders.
    Instrument("cited", ("uv", "run", "scripts/leaks.py", "--cited"),
               "no file prints the name of a ref it cites"),
    # **The same narrow-question shape as `cited`, on the column nothing
    # read.** `feat.category` is the bracket after a feat's printed name.
    # `--specs` reads `spec` only; `columns` tests whole-value equality
    # against the name index, which a category is not; and the tree-wide
    # walk waives a two-word label of ordinary words in prose, correctly.
    # So 72 labels went unexamined and one was an invented proper noun in
    # `etl/feat.py`. Seconds, and it caught its own author's comment on
    # the first run. #622.
    Instrument("categories",
               ("uv", "run", "scripts/leaks.py", "--categories"),
               "no tracked file prints a feat category that is a name"),
    Instrument("todo", ("uv", "run", "scripts/todo.py"),
               "no `todo=` waits on a symbol that now exists"),
    Instrument("bonuses", ("uv", "run", "scripts/bonuses.py", "--quiet"),
               "every bonus says the type its card prints"),
    # Beside `bonuses` because it is the same question about a different corpus:
    # does the code say the printed number. A monster ability's whole content is
    # its header, so this is most of what can be wrong with one.
    Instrument("cards", ("uv", "run", "scripts/cards.py", "--quiet"),
               "every monster header says the numbers its stat block prints"),
    # **The third of the same question, and the one nothing asked.** `bonuses`
    # compares a printed bonus type, `cards` a stat block's numbers; a power's
    # printed *keyword list* was hand-declared against nothing. `cards` has the
    # right shape for it and only ever reads a damage type, so a row with no
    # `damage=` returned before the keywords were looked at. Half a second: an
    # import of `content/` and two queries. #486.
    Instrument("keywords", ("uv", "run", "scripts/keywords.py", "--quiet"),
               "every header declares the keywords its card printed"),
    # **Added because its new half caught a real fork on its first run**, and
    # because nothing else asks this question: a leg's fork decides which rows a
    # character is offered and which race scores best in a draw, and until
    # `PRINTED_LEG` existed there was nothing to compare it against. Seconds to
    # run -- an AST walk over `content/` plus one query. #235.
    Instrument("legs", ("uv", "run", "scripts/legs.py"),
               "every gated leg exists, and agrees with the page it came off"),
    # **Beside `replay` because it is the half `replay` cannot do.** Seven
    # recorded fights cover what seven drawn parties happen to do, and two
    # engine mechanics had no cover at all -- 0 phasing events and 6 blindness
    # events of 10,665 -- so both bugs shipped with `replay` 7 of 7 green.
    # Camille's call on #422: targeted drivers, not an eighth fixture.
    Instrument("drivers", ("uv", "run", "scripts/drivers.py", "--quiet"),
               "the printed rule for a mechanic no fixture reaches"),
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


#: Engine files whose public functions content calls **by name**, so a change
#: to one is narrowable by `audit.py --calls`. Everything else under
#: `engine/` changes what an existing verb *means* rather than adding one,
#: which is precisely the case `_calls`' docstring says to pay the wide run
#: for. Two files, deliberately: the list is short because the claim is
#: strong. #761.
NARROWABLE = {
    "src/combat_engine/engine/cast.py": "c.",
    "src/combat_engine/engine/query.py": "",
}


def _verbs_from_diff() -> tuple[list[str], list[str]]:
    """The verbs this working tree touches, and the reasons it cannot say.

    Derived rather than typed, for the reason `audit._ctx_forwarders` gives
    about itself: a flag you have to remember is a flag that gets forgotten,
    and the one time it is forgotten is the time the wide run mattered.

    Returns `(needles, refusals)`. **A non-empty `refusals` is a refusal** --
    the caller must not narrow -- because every entry is a change this cannot
    bound: a file whose functions content does not call by name, a private
    helper every verb routes through, or an edit at module level that could
    change anything.

    The needle for a `Cast` method is `c.<name>`, which is how a row spells
    it. For a `query` reader it is the bare name, because content imports
    those and calls them unqualified -- and a bare name over-matches, which
    is the safe direction for something whose job is to *narrow*.
    """
    import ast

    done = subprocess.run(
        ["git", "status", "--porcelain", "-uall"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if done.returncode != 0:
        return [], ["git status failed, so the diff cannot be read"]
    files = [ln[3:].strip() for ln in done.stdout.splitlines() if ln[3:].strip()]
    engine = [f for f in files if f.startswith("src/combat_engine/engine/")]
    if not engine:
        return [], ["nothing under engine/ has changed, so there is nothing "
                    "to narrow -- plain `check.py` is already narrow here"]

    needles: list[str] = []
    refusals: list[str] = []
    for name in engine:
        prefix = NARROWABLE.get(name)
        if prefix is None:
            refusals.append(f"{name} -- content does not call its functions by "
                            f"name, so a change here is not bounded by any "
                            f"verb")
            continue
        path = ROOT / name
        if not path.exists():
            refusals.append(f"{name} -- gone from the tree")
            continue
        base = subprocess.run(
            ["git", "show", f"HEAD:{name}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if base.returncode != 0:
            refusals.append(f"{name} -- no committed version to compare with")
            continue
        now, was = path.read_text(), base.stdout
        moved = _moved_lines(was, now)
        try:
            tree = ast.parse(now)
        except SyntaxError as exc:
            refusals.append(f"{name} -- will not parse: {exc}")
            continue
        spans = [
            (fn.name, fn.lineno, fn.end_lineno or fn.lineno)
            for fn in ast.walk(tree)
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        text = now.splitlines()
        for line in sorted(moved):
            inside = [n for n, lo, hi in spans if lo <= line <= hi]
            if not inside:
                # **Blank and comment-only lines are forgiven, and nothing
                # else is.** Inserting a method moves the blank line that
                # separates it from the next one, which belongs to no
                # function -- and refusing on that made the derivation
                # refuse every additive change, which is the one case it
                # exists for. A module-level *statement* outside a function
                # still refuses: a constant can change any verb at once.
                body = text[line - 1].strip() if line - 1 < len(text) else ""
                if not body or body.startswith("#"):
                    continue
                refusals.append(f"{name}:{line} -- changed outside any "
                                f"function, so it could change anything")
                continue
            # The innermost enclosing def is last by line number; the
            # outermost is the one content can name.
            outer = min(
                (n for n, lo, hi in spans if lo <= line <= hi),
                key=lambda n: next(lo for m, lo, _h in spans if m == n),
            )
            if outer.startswith("_"):
                refusals.append(f"{name}:{line} -- inside `{outer}`, a private "
                                f"helper, so what it changes is not one verb")
                continue
            needle = f"{prefix}{outer}"
            if needle not in needles:
                needles.append(needle)
    return needles, refusals


def _moved_lines(was: str, now: str) -> set[int]:
    """Line numbers in `now` that differ from `was`.

    `difflib` rather than `git diff -U0` parsing, so the hunk arithmetic is
    somebody else's. Only the new side matters: a deleted line changes a
    verb that is still named by the lines around it.
    """
    import difflib

    out: set[int] = set()
    sm = difflib.SequenceMatcher(
        a=was.splitlines(), b=now.splitlines(), autojunk=False
    )
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            out |= set(range(j1 + 1, j2 + 1))
        elif tag == "delete":
            out.add(j1 + 1)
    return out


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
    ap.add_argument("--calls", nargs="*", metavar="SYMBOL", default=None,
                    help="an ADDITIVE engine change: audit the rows that name "
                         "these verbs instead of all 21,000. Bare `--calls` "
                         "derives them from the diff. Refuses when the change "
                         "is not narrowable, and never claims to be the wide "
                         "sweep")
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
    narrowed: list[str] = []
    if args.calls is not None:
        if args.all:
            print("--calls and --all ask for opposite things", file=sys.stderr)
            return 2
        narrowed, refusals = (args.calls, []) if args.calls \
            else _verbs_from_diff()
        if refusals:
            print("this change is not narrowable, so the wide audit stands:",
                  file=sys.stderr)
            for why in refusals:
                print(f"  {why}", file=sys.stderr)
            print("\nRun plain `check.py` and pay for it, or name the verbs "
                  "outright with `--calls c.foo`.", file=sys.stderr)
            return 2
        print(f"narrowing the audit to {len(narrowed)} verb(s): "
              f"{', '.join(narrowed)}")
        wanted = [
            Instrument(
                c.name,
                c.argv + tuple(a for n in narrowed for a in ("--calls", n))
                if c.name == "audit" else c.argv,
                c.catches, c.heavy)
            for c in wanted
        ]

    if args.only:
        keep = {n.strip() for n in args.only.split(",")}
        # **A name that matches nothing is a typo, said so.** `--only lint`
        # -- the instrument is called `ruff` -- left `wanted` empty and the
        # run died on `max() iterable argument is empty` eight lines below,
        # which reads like a crash in the suite rather than a mistyped
        # argument. Every name is checked against `CHECKS`, not against
        # `wanted`, so asking for a paused or slow check by name says
        # "excluded by this invocation" instead of "no such thing".
        unknown = sorted(keep - {c.name for c in CHECKS})
        if unknown:
            known = ", ".join(sorted(c.name for c in CHECKS))
            print(f"no instrument named {', '.join(unknown)}. "
                  f"Known: {known}", file=sys.stderr)
            return 2
        wanted = [c for c in wanted if c.name in keep]
        if not wanted:
            excluded = ", ".join(sorted(keep))
            print(f"{excluded}: known, but excluded by this invocation"
                  f" -- paused, or filtered out by --fast", file=sys.stderr)
            return 2
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
    # **Captured before anything runs, not after.** A whole-tree sweep
    # rewrites `fixtures/audited.json` itself, so asking about dirtiness at
    # the *end* can never be satisfied -- the run dirties the tree by doing
    # its job. `nightly.sh` asks the same question as a precondition and for
    # the same reason; measured by watching a green `--all` refuse to clear
    # the marker it had just earned. See `_clear_red`.
    began_clean = _tree_clean()
    # **Run them concurrently, report them in order.** The futures are
    # resolved in `wanted` order below, so the output still reads top to
    # bottom exactly as it did -- which it has to: these lines are read by
    # eye and diffed between runs, and a list that reshuffles is the thing
    # `audit._run_all` chose `pool.map` over `as_completed` to avoid.
    #
    # Threads rather than processes: each one only waits on a
    # `subprocess.run`, so there is nothing for the GIL to hold up.
    # Not a `with` block: its exit waits for every future, which would hold
    # all the output back to the end of the run instead of printing each
    # verdict as it lands.
    pool = ThreadPoolExecutor(max_workers=_LANES)
    flight = {c.name: pool.submit(_run_one, c) for c in _submit_order(wanted)}
    for c in wanted:
        took, done = flight[c.name].result()
        tail = _summary(done.stdout) or _summary(done.stderr)
        mark = "ok  " if done.returncode == 0 else "FAIL"
        print(f"  {mark}  {c.name:{width}}  {took:5.1f}s  {tail}")
        _record(c.name, took, done.returncode == 0, at,
                _scope(done.stdout))
        if done.returncode != 0:
            failed.append(c.name)
            if not args.verbose:
                # The failing lines only, which is what is worth reading.
                said = 0
                for line in (done.stdout + done.stderr).splitlines():
                    if "FAIL" in line or "diverged" in line.lower() or "error" in line.lower():
                        print(f"          {line.strip()[:110]}")
                        said += 1
                # **And a traceback whole, because this filter drops the
                # half of one that says anything.** A traceback's useful
                # lines are its `File "...", line N, in <name>` frames and
                # the source line under each, and **not one of them holds
                # the words `FAIL`, `diverged` or `error`** -- so a raise
                # came through as its last two lines and nothing else.
                #
                # The 2026-10-16 03:15 nightly is the measured cost. `audit`
                # raised a `tokenize.TokenError` over 42 minutes of wide
                # sweep and the log kept exactly:
                #
                #     raise TokenError(msg, (e.lineno, e.offset)) from None
                #     tokenize.TokenError: ('unterminated string literal ...
                #
                # Neither names the file, the row, or the frame, and `audit`
                # does not reach that row again for a day. A raise is the one
                # verdict this project treats as inviolable and it was the one
                # least possible to act on. #634.
                raised = 0
                for blob in (done.stdout, done.stderr):
                    frames = _traceback(blob)
                    if frames:
                        print("\n".join(f"          {x}" for x in frames))
                        raised += 1
                # **And the tail when neither of those said anything, which
                # is the premise and not the coverage.** A keyword filter
                # cannot know what an instrument prints when it fails: each
                # has its own vocabulary for its own verdict, and these three
                # words were chosen before most of them existed.
                #
                # `audit` is the case that proved it, in the same run that
                # argued for `_traceback` above. Its per-ref baseline report
                # holds no `FAIL`, no `diverged` and no `error`, and there was
                # no traceback either, so a 2,023-second wide sweep failed and
                # printed **nothing** underneath -- the row that had gone
                # silent had to be found by diffing `fixtures/audited.json` by
                # hand.
                #
                # So the rule is now the invariant that was wanted all along:
                # **a failing check is never detail-free.** Matching lines
                # when there are some, a traceback when there is one, and
                # otherwise the tail -- which is what `--verbose` has always
                # done per check, just applied where it is needed. #634.
                if not said and not raised:
                    body = (done.stdout or done.stderr).splitlines()
                    kept = [x for x in body if x.strip()][-_TAIL:]
                    if kept:
                        print(f"          (no line matched; last {len(kept)}"
                              f" of the output)")
                        print("\n".join(f"          {x[:110]}" for x in kept))
        if args.verbose:
            print("\n".join(f"          {x}" for x in done.stdout.splitlines()[-25:]))

    pool.shutdown(wait=True)

    print()
    for line in _nightly_state():
        print(line)
    owed = _sweep_owed()
    if narrowed and not failed:
        # **Said even when every instrument is green, and before the verdict
        # line.** A narrowed audit is evidence the named verbs work and is
        # blind to a row that changes behaviour without naming one -- which
        # is `audit._calls`' own caveat. Printing it here and withholding
        # "all clean" below is the same arrangement the wide-sweep debt
        # already uses: every instrument still ran, only the claim narrows.
        print(f"the audit was narrowed to {', '.join(narrowed)} -- evidence "
              f"those verbs work, not that nothing else broke")
    if failed:
        print(f"{len(failed)} unhappy: {', '.join(failed)}")
    elif owed or narrowed:
        # **The one sentence that means "nothing is outstanding" is withheld
        # while something is.** Every instrument still ran and still reported;
        # the verdict is not narrowed, only the claim.
        print(f"{len(wanted)} instruments clean"
              + (f", {owed}" if owed else "")
              + (", and the audit was narrow" if narrowed else ""))
    else:
        print(f"all {len(wanted)} instruments clean")
    for line in _clear_red(args.all, bool(failed), at, began_clean):
        print(line)
    return len(failed)


def _tree_clean() -> bool:
    """Is the working tree clean *right now*? Used as a precondition only."""
    done = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                          capture_output=True, text=True)
    return done.returncode == 0 and not done.stdout.strip()


def _clear_red(whole_tree: bool, any_failed: bool, started_at: str,
               began_clean: bool) -> list[str]:
    """Take down `NIGHTLY-FAILED` when *this* run is the green verdict.

    **The action that fixes an owed sweep was the one that left the signal
    most wrong.** `logs/NIGHTLY-FAILED` is written by `nightly.sh` on a red
    sweep and removed by `nightly.sh` on a green one -- and the root
    `CLAUDE.md` tells anybody with an owed sweep to run `check.py --all`,
    which reaches the same verdict through the other door and had no way to
    clear the flag. So somebody doing exactly what the documentation says
    ended with a green tree and a file saying the last sweep failed. #566's
    third route to the same confusion.

    **Not "removing the marker by hand"**, which `scripts/CLAUDE.md` rightly
    calls the mistake. This is the instrument acting on a verdict it reached
    itself, under the same four guards `nightly.sh` applies -- and it says so
    on stdout, so the removal is never silent:

    * **every instrument clean.** One red check is not a green sweep.
    * **`--all`.** A narrow run has not looked at the rest of the tree, which
      is the whole argument `audit.py` makes for only watermarking a full
      sweep.
    * **a tree that was clean when the run began.** A sweep over uncommitted
      edits certifies no commit, which is why `nightly.sh` refuses to start
      on one. Asked as a **precondition** and not at the end, because a
      whole-tree sweep rewrites `fixtures/audited.json` itself: the first
      version of this asked afterwards and so could never fire, which a
      green `--all` demonstrated by declining to clear the marker it had
      just earned.
    * **the sha did not move under it.** A sweep across two trees certifies
      neither, which is `nightly.sh`'s `MOVED` state.

    Left alone in every other case, including a red run: a non-verdict must
    never erase a real one, which is the invariant #543 was filed for.
    """
    if not NIGHTLY_RED.exists():
        return []
    if any_failed or not whole_tree:
        return []
    if not began_clean:
        return ["         logs/NIGHTLY-FAILED left alone: the tree was dirty"
                " when this run started, so the sweep certifies no commit"]
    now = _commit()
    if not now or not started_at or now != started_at:
        return ["         logs/NIGHTLY-FAILED left alone: the sha moved under"
                f" this run ({started_at} -> {now}), so it certifies neither"]
    was = NIGHTLY_RED.read_text().strip().splitlines()
    try:
        NIGHTLY_RED.unlink()
    except OSError:
        return []
    return [f"         logs/NIGHTLY-FAILED removed -- this run is the green"
            f" verdict at {now}. It had said: {was[0] if was else '(empty)'}"]


#: Where `audit.py` records the commit of the last sweep that looked at every
#: row. Read rather than written here -- this only reports the debt.
WATERMARK = ROOT / "scripts" / "fixtures" / "audited.json"


#: What the nightly leaves behind. `NIGHTLY-FAILED` is written on a red run
#: and removed on a green one; `nightly-latest.log` is copied on every run
#: **including a skip**, which is the asymmetry this reads.
NIGHTLY_RED = ROOT / "logs" / "NIGHTLY-FAILED"
NIGHTLY_LOG = ROOT / "logs" / "nightly-latest.log"


def _nightly_state() -> list[str]:
    """What the 02:07 net last did, said where the decision to trust it is made.

    **#543: a nightly that never ran is indistinguishable from one that
    passed.** The documented signal was `logs/NIGHTLY-FAILED` existing, and
    the protocol in the root `CLAUDE.md` was "a one-line check at the start
    of a session". Two things make that unsound, and both were live on
    2026-10-13:

    * **Both of `nightly.sh`'s skip paths `exit 0` without touching the
      marker.** So a red run on the 12th left the file, the 13th's run
      skipped on a dirty tree, and the file still read `FAILED at 227e2b0`
      -- describing a sweep two days and 60 commits old while the stated
      invariant says it describes the last run. A session following the
      protocol concludes "the last run was red". The last run did not run.
    * **A green run removes the marker and leaves nothing**, so "no marker"
      covers both "swept clean last night" and "has not swept since
      August".

    So this reports the age and the verdict together, from the log's
    mtime rather than the marker's existence, and says which it is in
    words. Not an exit code, for `_sweep_owed`'s reason: the nightly's
    health is not a verdict on the change in hand, and a red that is not
    about your work is how red gets ignored.

    The marker is still worth keeping -- it is the only place the failing
    sha is written down -- but it is evidence about *a* run, not the last
    one, and this says so when the two disagree.

    **The time comes out of the log's own text, not its mtime**, and that
    correction came from exercising the four branches here: `nightly.sh`
    copies this file into place with `cp`, every one of the branch probes
    did the same to restore it, and each copy reset the mtime to now. A
    function written to stop a stale signal being read as a fresh one
    cannot take its own reading from the most easily-touched field on
    disk. `nightly.sh` writes `%F %T` into the first line of every path it
    has, so the file says when it ran; mtime is the fallback for a log
    from some older shape of the script.
    """
    try:
        head = NIGHTLY_LOG.read_text()[:400]
    except OSError:
        return ["nightly: no run on record -- `uv run bash scripts/nightly.sh`"]

    stamped = re.search(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d):\d\d", head)
    if stamped:
        ran = datetime.strptime(f"{stamped.group(1)} {stamped.group(2)}",
                                "%Y-%m-%d %H:%M")
    else:
        ran = datetime.fromtimestamp(NIGHTLY_LOG.stat().st_mtime)

    hours = (datetime.now() - ran).total_seconds() / 3600
    when = f"{ran:%F %H:%M}"
    old = f", {int(hours / 24)}d old" if hours >= 48 else ""
    if _moved(NIGHTLY_LOG):
        # **A MOVED attempt is no more a verdict than a SKIPPED one**, so it
        # is reported the same way and the marker is read with the same
        # suspicion. The difference is only when the obstacle arrived: a
        # dirty tree is seen before the run, commits landing are seen after.
        out = [f"nightly: last attempt {when} MOVED{old} -- commits landed"
               f" mid-sweep, so it certifies nothing"]
        if NIGHTLY_RED.exists():
            out.append(f"         logs/NIGHTLY-FAILED is from BEFORE that"
                       f" -- {NIGHTLY_RED.read_text().splitlines()[0]}")
        return [*out, *_stale_net()]
    if head.lstrip().startswith("SKIPPED"):
        why = "a check.py was running" if "already running" in head else "a dirty tree"
        out = [f"nightly: last attempt {when} SKIPPED -- {why}{old}"]
        if NIGHTLY_RED.exists():
            # The trap this function exists for: the marker is from an
            # earlier run and the protocol reads it as the current one.
            out.append(f"         logs/NIGHTLY-FAILED is from BEFORE that"
                       f" -- {NIGHTLY_RED.read_text().splitlines()[0]}")
        return [*out, *_stale_net()]
    if NIGHTLY_RED.exists():
        why = NIGHTLY_RED.read_text().splitlines()[0]
        return [f"nightly: last run {when} RED{old} -- {why}", *_stale_net()]
    return [f"nightly: last run {when} clean{old}", *_stale_net()]



#: How long the net may go unpaid before saying so. A day plus an hour: the
#: sweep is nightly, and the agent has landed as much as 60 minutes late, so
#: 24 would cry wolf every morning the machine was slow to wake.
STALE_AFTER_HOURS = 26


def _stale_net() -> list[str]:
    """How long since a sweep actually reached a verdict, when that is news.

    **A skip is not a verdict, and nothing was counting them.** `#566`: the
    agent fired three times since it was installed and *every one* either
    skipped or had to be kicked by hand -- a dirty tree, then a `check.py`
    already running -- so no sweep has ever been paid on the schedule. Each
    of those nights the line above read correctly and said nothing about the
    net going unpaid, because it reports the last **attempt**.

    Read off the dated logs rather than the marker or the latest-copy,
    because they are the only per-attempt record that survives: the most
    recent one whose first line is not `SKIPPED` is the last time every row
    was actually looked at. Silent when that is recent, so an ordinary
    morning gains no line.
    """
    logs = sorted((ROOT / "logs").glob("nightly-20*.log"), reverse=True)
    for log in logs:
        try:
            head = log.read_text()[:200]
        except OSError:
            continue
        if head.lstrip().startswith("SKIPPED") or _moved(log):
            continue
        stamped = re.search(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d)", head)
        if not stamped:
            continue
        ran = datetime.strptime(
            f"{stamped.group(1)} {stamped.group(2)}", "%Y-%m-%d %H:%M"
        )
        hours = (datetime.now() - ran).total_seconds() / 3600
        if hours < STALE_AFTER_HOURS:
            return []
        skipped = sum(
            1 for other in logs
            if other > log and (_skipped(other) or _moved(other))
        )
        tail = f", {skipped} attempt(s) skipped since" if skipped else ""
        return [f"         the net last reached a verdict {ran:%F %H:%M},"
                f" {int(hours / 24)}d ago{tail}"]
    if logs:
        return ["         no attempt on record has reached a verdict --"
                " every one skipped"]
    return []


def _moved(log: Path) -> bool:
    """Did the tree move under this sweep while it ran?

    **Read from the tail, not the head**, which is the difference from
    `_skipped`: a skip is decided before the header is written and so is the
    whole file, while this is decided 43 minutes in and is appended. Reading
    only the first 400 bytes would have missed it in every case.
    """
    try:
        text = log.read_text()
    except OSError:
        return False
    return any(line.startswith("MOVED ") for line in text.splitlines())


def _skipped(log: Path) -> bool:
    """Did this attempt skip rather than sweep?"""
    try:
        return log.read_text()[:200].lstrip().startswith("SKIPPED")
    except OSError:
        return False


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


#: How many instruments may be in flight at once. The loop was a plain `for`
#: with a blocking `subprocess.run`, so 21 instruments ran strictly one after
#: another on a ten-core machine where sixteen of them are single-process.
#: Measured: the twenty non-audit instruments are a stable **480s wide, 464s
#: narrow**, and the longest single one is `drivers` at ~140s -- so the floor
#: is the longest member, not the sum.
#:
#: Four rather than ten, deliberately. `audit` already runs ten worker
#: processes of its own (`audit._run_all`), so a wide run has every core busy
#: for most of its length and more lanes would mostly take cores away from
#: it. Four collapses the 480s to roughly `drivers`' own 140s without
#: oversubscribing.
_LANES = 4

#: Instruments that must not run beside each other, by group.
#:
#: **`audit` and `verdicts` are the same script.** `audit.py --changed`
#: rewrites `fixtures/audited.json` at the end of a full clean run and
#: `audit.py --verdicts` reads that baseline, so letting them overlap means
#: `verdicts` can read a file mid-write. Nothing had to care while the loop
#: was serial.
#:
#: **`api` and `browser` each start a uvicorn.** They pick their own free
#: port, so they would not collide on one -- but both pay a cold `uv run`
#: plus a full `combat_engine` import before a 20-second health poll, and two
#: of those at once on a loaded machine is how that poll starts timing out.
#: `scripts/CLAUDE.md` already records what server bookkeeping costs when it
#: goes wrong: 69 orphaned uvicorns over three and a half days.
_EXCLUSIVE: tuple[frozenset[str], ...] = (
    frozenset({"audit", "verdicts"}),
    frozenset({"api", "browser"}),
)

#: Instruments that need the machine to themselves.
#:
#: `browser.py` drives real Chromium and several of its checks are about
#: **timing** -- "enemy tokens animate", "the button is gone while that fight
#: is being played". An animation has a wall-clock duration, so no amount of
#: waiting on a condition makes those robust to a loaded box: they were
#: calibrated on a quiet one.
#:
#: Measured, and this is why the entry exists: putting the loop on four lanes
#: turned "enemy tokens animate (0 of them slid)" red on its first full run,
#: a *different* assertion from the one #847 is about. Two load-sensitive
#: checks in one instrument is a pattern, not a coincidence.
#:
#: Costs almost nothing. `browser` is last in `CHECKS`, so by the time its
#: turn comes the other lanes have largely drained; the full run measured
#: 195s with it parallel and the same within noise with it solo.
_SOLO: frozenset[str] = frozenset({"browser"})

_LOCKS: dict[frozenset[str], threading.Lock] = {
    group: threading.Lock() for group in _EXCLUSIVE
}

#: One permit a lane. A `_SOLO` instrument takes every permit, so nothing
#: else is running while it does; everything else takes one.
_GATE = threading.Semaphore(_LANES)
#: So two solo instruments could not each hold some permits and wait for the
#: rest. There is one today; the guard is for when there are two.
_SOLO_TURN = threading.Lock()


def _run_one(c: Instrument) -> tuple[float, subprocess.CompletedProcess]:
    """One instrument, timed, held out of its exclusion group's way.

    The locks are taken in `_EXCLUSIVE`'s own order so that an instrument in
    two groups -- none is today -- could not deadlock against one in the
    other order.
    """
    solo = c.name in _SOLO
    if solo:
        _SOLO_TURN.acquire()
        for _ in range(_LANES):
            _GATE.acquire()
    else:
        _GATE.acquire()
    held = [_LOCKS[g] for g in _EXCLUSIVE if c.name in g]
    for lock in held:
        lock.acquire()
    try:
        started = time.monotonic()
        done = subprocess.run(c.argv, cwd=ROOT, capture_output=True, text=True)
        return time.monotonic() - started, done
    finally:
        for lock in reversed(held):
            lock.release()
        if solo:
            for _ in range(_LANES):
                _GATE.release()
            _SOLO_TURN.release()
        else:
            _GATE.release()


def _submit_order(wanted: list[Instrument]) -> list[Instrument]:
    """`wanted`, reordered so no lane blocks early on a group-mate.

    A thread waiting for its exclusion group holds a lane while doing
    nothing, and the queue is FIFO -- so with `audit` and `verdicts`
    adjacent in `CHECKS`, `verdicts` would take a lane and sit on it for the
    whole 1,300-second audit. The second and later members of each group go
    to the back instead.

    Reporting order is unaffected: the caller resolves futures by name in
    `wanted` order.
    """
    claimed: set[frozenset[str]] = set()
    head: list[Instrument] = []
    tail: list[Instrument] = []
    for c in wanted:
        group = next((g for g in _EXCLUSIVE if c.name in g), None)
        if group is not None and group in claimed:
            tail.append(c)
            continue
        if group is not None:
            claimed.add(group)
        head.append(c)
    return head + tail


def _record(name: str, seconds: float, ok: bool, at: str,
            scope: tuple[int, int] | None = None) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "when": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "name": name, "seconds": round(seconds, 2), "ok": ok, "commit": at,
            # **How many instruments were in flight**, because without it the
            # seconds stop being comparable across this change. A serial run
            # and a four-lane run measure different things -- the second
            # includes contention -- and `history`'s medians span both. 1 is
            # the old behaviour.
            "lanes": _LANES,
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


#: How much output to keep from a failing check that printed no matching
#: line and no traceback. The same depth `--verbose` uses, less a little,
#: because this is the fallback and not the thing somebody asked for.
_TAIL = 20


#: How much of a traceback to keep. Deep enough for the innermost frames,
#: which are the ones naming the row, and short enough that a check failing
#: on twenty of them does not bury the table above it.
_FRAMES = 14


def _traceback(text: str) -> list[str]:
    """Every traceback in an instrument's output, last `_FRAMES` lines each.

    Returned rather than printed so the caller decides where it goes, and
    kept **verbatim** -- a frame's indentation is what pairs a source line
    with the call above it, and stripping it makes a traceback unreadable
    in exactly the way that cost #634 a day.

    The tail and not the head: `audit.py` runs rows in a pool, so the
    outermost frames are the same `pool.map` bootstrap every time and the
    innermost are the ones that name the file being tokenized.
    """
    out: list[str] = []
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines)
              if ln.lstrip().startswith("Traceback (most recent call last)")]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(lines)
        block = [ln for ln in lines[start:end] if ln.strip()]
        if len(block) > _FRAMES:
            # Say what was dropped rather than truncating silently, which is
            # the whole complaint #634 is about.
            block = [block[0], f"... {len(block) - _FRAMES} frame(s) above",
                     *block[-(_FRAMES - 2):]]
        out.extend(block)
    return out


def _summary(text: str) -> str:
    """The one line of an instrument's output worth putting in a table."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line[:80]
    return ""


#: Written while a run is in progress and removed on the way out, so
#: `nightly.sh` can tell "a sweep is running" from "a shell mentioned this
#: file". **It could not**, and that cost a night's sweep: its guard was
#: `pgrep -f "scripts/check\.py"`, a substring match over every command
#: line on the machine, so a session that merely *grepped* for check.py
#: inside the nightly's window matched -- and on 2026-10-15 at 03:07 one
#: did, leaving `SKIPPED ... a check.py is already running` with nothing
#: running at all.
#:
#: A pid and `kill -0` instead of a pattern, which is the rule this repo
#: already learned from the other side: a `pgrep` waiter matched its own
#: command line and stranded three of them.
LOCK = ROOT / "logs" / "check.pid"


def _hold_lock() -> None:
    """Record this run's pid, and leave no lock behind on the way out."""
    import atexit
    import os

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(f"{os.getpid()}\n")

    def release() -> None:
        # Only our own: a crash elsewhere must not let this run delete a
        # live sweep's lock.
        if LOCK.exists() and LOCK.read_text().strip() == str(os.getpid()):
            LOCK.unlink()

    atexit.register(release)


if __name__ == "__main__":
    _hold_lock()
    raise SystemExit(main())
