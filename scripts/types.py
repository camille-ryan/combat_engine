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

#: **Drift above the baseline on a whole-tree run: reported, not failed.**
#: Distinct from 1, which means "the change in hand put a file over its
#: baseline" and is a fault in that change. A `--all` run finds drift that
#: has already landed, often commits ago -- `scripts/drivers.py` was 29 over
#: before anybody noticed, and the gate then blamed whoever next edited the
#: file. So the wide run names it and `check.py` withholds "all clean"
#: without calling the run unhappy. #870.
DRIFT = 4


def _baseline() -> dict[str, dict[str, int]]:
    """The recorded diagnostics, `{file: {fingerprint: count}}`.

    **An old per-file count is refused rather than adapted.** A `{file: int}`
    entry carries no fingerprints, so the only honest reading of it is "we
    do not know which errors these were" -- and quietly treating the number
    as a tolerance would reintroduce exactly the blindness #891 is about,
    while looking migrated. `--migrate` is the one command that may read the
    old shape.
    """
    if not BASELINE.exists():
        return {}
    raw = json.loads(BASELINE.read_text())
    return {f: dict(v) for f, v in raw.items() if isinstance(v, dict)}


def _unmigrated() -> dict[str, int]:
    """Entries still in the old per-file-count shape, if any."""
    if not BASELINE.exists():
        return {}
    raw = json.loads(BASELINE.read_text())
    return {f: v for f, v in raw.items() if isinstance(v, int)}


def _total(held: dict[str, dict[str, int]]) -> int:
    return sum(sum(d.values()) for d in held.values())


def _per_file(text: str) -> dict[str, int]:
    """How many errors each file owns. `_owned` collapsed to a count.

    Kept because three callers want the number and nothing else -- the
    scope-artifact re-measure, the `carried` line, and the `--all` clearing
    pass. The *record* is per diagnostic now (see `_owned`); this is a view
    over it.
    """
    return {f: sum(d.values()) for f, d in _owned(text).items()}


def _owned(text: str) -> dict[str, dict[str, int]]:
    """Which diagnostics each file owns: `{file: {fingerprint: count}}`.

    **The record is per diagnostic, not per file, and that is #891.** A
    baseline of `{"scripts/drivers.py": 33}` says a number and nothing about
    *which* 33, so it cannot answer the three questions that matter:

    * is this error one we recorded? -- attribute nothing
    * is it new? -- red, and name it
    * did a recorded one go away? -- lower the baseline for free

    A count collapses all three. Ten errors fixed and ten introduced reads
    as no change, and a commit is blamed for debt it inherited the moment an
    unrelated edit pulls a file into a narrow run's scope.

    **The fingerprint is `rule|message` and deliberately carries no line
    number.** A line drifts whenever anything above it moves, which is the
    same reasoning `impact.py` gives for fingerprinting at function
    granularity rather than by line -- and a baseline that churns on every
    insertion is one nobody can read a diff of.

    **A count per fingerprint, not a set.** `ty` reports the identical
    message more than once in a file -- `scripts/drivers.py` has
    the message "Object of type AttackRolled has no attribute result" twice
    -- and
    a set would collapse them, so fixing one of the two would look like
    fixing neither. The count is what keeps the ratchet honest at that
    grain.

    Ownership is unchanged and is the half that was already hard-won: the
    first `-->` after each `error[`, and only that one.

    **The first `-->` after each `error[`, and only that one.** A diagnostic
    carries its primary location *and* any number of `info:` back-pointers
    -- "Type variable defined here", "function defined here" -- each on its
    own `-->` line. Counting every one of them charged a file for errors it
    does not own, and two things followed:

    * **a file could go over its baseline because somebody edited another
      file.** `engine/events.py` read 3 against a baseline of 1 on a commit
      that did not touch it: one real error, plus two `info:` pointers at
      `events.py:1592` where `Bus.emit`'s type variable is declared, both
      belonging to errors in `engine/durations.py`. Proved by bisect --
      reverting the `events.py` edit left the count at 3.
    * **`scripts/drivers.py:70` was charged twice for `Result.that`'s own
      `def` line**, which is the definition a bad call points back at.

    So the count was never "errors this file owns"; it was "times this file
    was mentioned". `ty` prints one `error[` line per diagnostic, so arming
    on that and taking the next location is exactly ownership.
    """
    out: dict[str, dict[str, int]] = {}
    want = ""
    for line in text.splitlines():
        if line.startswith("error["):
            rule, _, message = line[len("error["):].partition("]:")
            want = f"{rule}|{message.strip()}"
            continue
        if not want:
            continue
        m = re.match(r"\s*-->\s*([^:]+\.py):", line)
        if m:
            held = out.setdefault(m.group(1), {})
            held[want] = held.get(want, 0) + 1
            want = ""
    return out


def _asked_about(reported: dict[str, int], targets: list[str]) -> set[str]:
    """Of the files `ty` reported on, which did this run actually ask about?

    **`ty` reports diagnostics for files it merely imported**, and their
    counts are *lower* than the same files' full-scope counts, because a
    narrower file set resolves fewer types. So the two things a bless must
    not confuse: a file that got better, and a file that was never asked
    about and looks better for it.

    This cost a real baseline. Blessing after a three-file run recorded
    `cast.py` 45 -> 1, `dsl.py` 332 -> 9 and `query.py` 81 -> 7 -- none of
    them edited, none of them a target, every one of those numbers an
    artifact of the scope. It passed the "only ever downward" guard above
    because downward is exactly the direction the artifact points, which is
    why that guard is not sufficient on its own. The next `--all` would have
    been red by ~440 for no reason.

    Worse, the comment in `main` already *claimed* this -- "only the files
    actually checked in this run are touched" -- and nothing did it.

    `targets` is either a list of files or, under `--all`, the `SCOPE`
    directory prefixes, so both forms have to match.
    """
    asked: set[str] = set()
    for f in reported:
        for t in targets:
            t = t.rstrip("/")
            if f == t or f.startswith(t + "/"):
                asked.add(f)
                break
    return asked


def _run(paths: list[str]) -> tuple[int, str]:
    done = subprocess.run(["uvx", "ty", "check", *paths], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    text = done.stdout + done.stderr
    count = sum(1 for ln in text.splitlines() if ln.startswith("error["))
    return count, text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bless", action="store_true",
                    help="record the current diagnostics as the baseline")
    ap.add_argument("--all", action="store_true",
                    help="the whole scope, backlog included")
    ap.add_argument("--migrate", action="store_true",
                    help="convert a per-file-count baseline to fingerprints")
    ap.add_argument("paths", nargs="*", help="specific files")
    args = ap.parse_args()

    stale = _unmigrated()
    if stale and not args.migrate:
        print(f"{len(stale)} baseline entry(ies) still hold a per-file count"
              f" ({sum(stale.values())} error(s)) and carry no fingerprints,"
              f" so nothing can be attributed: {' '.join(sorted(stale))}")
        print("run `types.py --migrate` on a clean tree. #891")
        return 1

    if args.migrate:
        return _migrate(stale)

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
        return _bless(text, targets, args.all)
    return _compare(text, targets, args.all)


def _migrate(stale: dict[str, int]) -> int:
    """Turn `{file: count}` into `{file: {fingerprint: count}}`, once.

    **Mechanism only: it must not move a verdict.** So it measures the whole
    `SCOPE` and records exactly what is there, and it **refuses** any file
    whose live total exceeds the count the old baseline allowed -- that is
    pre-existing drift, and recording it would be a loosening dressed up as
    a format change. #891.
    """
    if not stale:
        print("nothing to migrate: every entry already holds fingerprints")
        return 0
    _, text = _run(list(SCOPE))
    live = _owned(text)
    counts = {f: sum(d.values()) for f, d in live.items()}
    in_scope = _asked_about(dict.fromkeys(stale, 0), list(SCOPE))
    over = {f: (counts[f], stale[f]) for f in in_scope
            if counts.get(f, 0) > stale[f]}
    if over:
        for f, (now, was) in sorted(over.items()):
            print(f"  REFUSING {f}: {now} error(s) against an allowance of"
                  f" {was} -- that is drift to fix or argue for, not to"
                  f" migrate")
        return 1
    fresh = {f: dict(live.get(f, {})) for f in in_scope}
    # Entries for files outside `SCOPE` are dropped, which is what `--bless
    # --all` already does to them and for the same reason: this instrument
    # never checks them, so their counts could never go red or be lowered.
    outside = {f: n for f, n in stale.items() if f not in in_scope}
    BASELINE.write_text(json.dumps(fresh, indent=2, sort_keys=True) + "\n")
    print(f"migrated {len(fresh)} entry(ies), {_total(fresh)} error(s) across"
          f" {sum(len(d) for d in fresh.values())} distinct diagnostic(s)")
    for f in sorted(fresh):
        was, now = stale[f], sum(fresh[f].values())
        if was != now:
            print(f"  {f}: {was} -> {now} (lower; the live count is what is"
                  f" recorded)")
    if outside:
        print(f"  dropped {len(outside)} entry(ies) outside SCOPE,"
              f" {sum(outside.values())} error(s)")
    return 0


def _compare(text: str, targets: list[str], wide: bool) -> int:
    """Is every diagnostic one the baseline already holds?

    **Not gated by `_asked_about`, deliberately.** A swept-in file's narrow
    count is the *lower* one, so comparing it against a full-scope baseline
    can only ever let it pass -- gating here would discard a real finding to
    tidy up a symmetry. If a swept-in file ever does report higher than its
    baseline, that is a question worth being red about, not a scope artifact
    to waive. Narrowing a check to match a bless is how the loosening in
    `scripts/CLAUDE.md`'s first rule happens.
    """
    base = _baseline()
    now = _owned(text)
    # Per fingerprint, which is the whole of #891: ten fixed and ten
    # introduced used to read as no change.
    over: dict[str, dict[str, tuple[int, int]]] = {}
    for f, held in now.items():
        had = base.get(f, {})
        bad = {fp: (n, had.get(fp, 0)) for fp, n in held.items()
               if n > had.get(fp, 0)}
        if bad:
            over[f] = bad

    # **A target can be over its baseline on scope alone**, and that is not a
    # regression. A count is only comparable against a baseline taken at the
    # same scope -- `cast.py` is 46 alone and 45 across the whole `SCOPE` --
    # so a file that looks worse is re-measured at the scope the baseline
    # came from, and only then believed. One extra `ty` run, on the failing
    # path only. The fix is not a tolerance. #618.
    explained: dict[str, dict[str, tuple[int, int]]] = {}
    if over:
        _, text_wide = _run(list(SCOPE))
        at_scope = _owned(text_wide)
        for f, bad in list(over.items()):
            seen = at_scope.get(f, {})
            ok = {fp: v for fp, v in bad.items()
                  if seen.get(fp, 0) <= v[1]}
            left = {fp: (seen.get(fp, n), was) for fp, (n, was) in bad.items()
                    if fp not in ok}
            if ok:
                explained[f] = ok
            if left:
                over[f] = left
            else:
                del over[f]
        for f, ok in sorted(explained.items()):
            print(f"  {f}: {len(ok)} diagnostic(s) at this scope that the"
                  f" whole scope does not report above baseline -- a scope"
                  f" artifact, not a regression")

    if over:
        print(text.rstrip())
        print()
        for f, bad in sorted(over.items()):
            print(f"  {f}:")
            for fp, (n, was) in sorted(bad.items()):
                rule, _, message = fp.partition("|")
                tag = "NEW" if not was else f"{was} -> {n}"
                print(f"      {tag:9} [{rule}] {message[:92]}")
        total = sum(n - was for bad in over.values()
                    for n, was in bad.values())
        print(f"\n{total} error(s) above the baseline in {len(over)} file(s),"
              f" named above -- each one is a diagnostic the baseline does"
              f" not hold")
        # **`--all` reports drift rather than failing on it.** The drift
        # happened in whichever commit caused it, and a red that is not
        # about your work is how red gets ignored -- `_sweep_owed`'s
        # reasoning, and `scripts/CLAUDE.md`'s record of a check that could
        # not pass. So a third code, which `check.py` prints and lets
        # withhold "all clean" without calling the run unhappy. #870.
        return DRIFT if wide else 1

    carried = _total({f: d for f, d in now.items()})
    gone = _gone(base, now, targets) if wide else {}
    if gone:
        print(f"  {sum(len(d) for d in gone.values())} recorded diagnostic(s)"
              f" in {len(gone)} file(s) no longer occur -- `--bless --all`"
              f" lowers the baseline for free")
    note = f" ({carried} carried, at or below baseline)" if carried else ""
    print(f"ok: {len(targets)} file(s) checked{note}")
    return 0


def _gone(base: dict[str, dict[str, int]], now: dict[str, dict[str, int]],
          targets: list[str]) -> dict[str, dict[str, int]]:
    """Recorded diagnostics that no longer occur, per file.

    **`--all` only**, and that restriction is the whole of its safety: under
    a narrow run almost every file in `SCOPE` is absent from the report
    because it was never checked, and "absent" would then mean "never
    looked at" rather than "fixed". `--all` is the one invocation where in
    scope and silent means clean. Same reasoning the old per-file `cleared`
    pass carried, at the finer grain. #886, #891.
    """
    in_scope = _asked_about(dict.fromkeys(base, 0), list(SCOPE))
    out: dict[str, dict[str, int]] = {}
    for f in in_scope:
        held = now.get(f, {})
        missing = {fp: n for fp, n in base[f].items() if n > held.get(fp, 0)}
        if missing:
            out[f] = missing
    return out


def _bless(text: str, targets: list[str], wide: bool) -> int:
    """Record the current diagnostics. **Only ever downward.**

    `fixtures/audited.json`'s contract, and here for the same reason: the
    tree carries years of standing type debt, so a file with 6 pre-existing
    errors must not fail the moment somebody edits an unrelated line in it.

    Three refusals, each of which a plant has proved necessary:

    * **a diagnostic the baseline does not hold** -- new, or a higher count
      of a recorded one. That is the thing to fix or to argue for, never to
      bless; `scripts/CLAUDE.md`'s first rule.
    * **a file arriving with errors and no entry.** A missing entry is an
      implied 0, so recording its diagnostics is a loosening wearing a
      different word. Only a clean newcomer is recorded.
    * **a file swept in but not asked about.** `ty` reports diagnostics for
      files it merely imported, and their counts are *lower* than the same
      files' full-scope counts, so blessing them records a figure nothing
      measured. This cost a real baseline once: a three-file run recorded
      `cast.py` 45 -> 1, `dsl.py` 332 -> 9 and `query.py` 81 -> 7, none of
      them edited, every number an artifact of the scope. It passed the
      only-ever-downward guard because downward is the direction the
      artifact points, which is why that guard is not sufficient alone.
    """
    base = _baseline()
    reported = _owned(text)
    asked = _asked_about({f: 0 for f in reported}, targets)
    now = {f: d for f, d in reported.items() if f in asked}
    swept = {f: d for f, d in reported.items() if f not in asked}

    risen: dict[str, dict[str, tuple[int, int]]] = {}
    lowered: dict[str, dict[str, tuple[int, int]]] = {}
    for f, held in now.items():
        had = base.get(f)
        if had is None:
            continue
        up = {fp: (had.get(fp, 0), n) for fp, n in held.items()
              if n > had.get(fp, 0)}
        down = {fp: (had[fp], held.get(fp, 0)) for fp in had
                if held.get(fp, 0) < had[fp]}
        if up:
            risen[f] = up
        if down:
            lowered[f] = down
    fresh = {f: {} for f, d in now.items() if f not in base and not d}
    arriving = {f: d for f, d in now.items() if f not in base and d}

    # **Clearing a recorded diagnostic that no longer occurs is `--all` only**
    # -- see `_gone`. Lowering a count for a diagnostic still present is not,
    # which is the behaviour this had before #891 and the same risk profile.
    cleared = _gone(base, now, targets) if wide else {}
    dropped: dict[str, dict[str, int]] = {}
    if wide:
        in_scope = _asked_about(dict.fromkeys(base, 0), list(SCOPE))
        dropped = {f: d for f, d in base.items() if f not in in_scope}

    for f, down in lowered.items():
        for fp, (_was, n) in down.items():
            if n:
                base[f][fp] = n
            else:
                base[f].pop(fp, None)
    for f, missing in cleared.items():
        for fp in missing:
            base[f].pop(fp, None)
    base.update(fresh)
    for f in dropped:
        del base[f]
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(base, indent=2, sort_keys=True) + "\n")

    for f, down in sorted(lowered.items()):
        for fp, (was, n) in sorted(down.items()):
            print(f"  tightened {f}: {fp.partition('|')[0]} {was} -> {n}")
    for f in sorted(fresh):
        print(f"  recorded  {f}: clean, and now in the baseline")
    for f, up in sorted(risen.items()):
        for fp, (was, n) in sorted(up.items()):
            rule, _, message = fp.partition("|")
            tag = "NEW" if not was else f"{was} -> {n}"
            print(f"  LEFT ALONE {f}: {tag} [{rule}] {message[:76]}"
                  f" -- fix it or argue for it, do not bless it")
    for f, d in sorted(arriving.items()):
        print(f"  LEFT ALONE {f}: arriving with {sum(d.values())} error(s)"
              f" and no baseline; an implied 0 is the stricter record")
    # Named rather than silently dropped. A reader who watched `ty` print
    # diagnostics for `dsl.py` and then saw nothing about it here would
    # reasonably think the bless had missed something.
    for f, d in sorted(swept.items()):
        print(f"  not a target {f}: {sum(d.values())} error(s) at this scope,"
              f" which is not comparable to a full-scope baseline")
    if cleared:
        print(f"  cleared {sum(len(d) for d in cleared.values())}"
              f" diagnostic(s) in {len(cleared)} file(s) that no longer"
              f" occur")
    if dropped:
        print(f"  dropped {len(dropped)} entry(ies) for files outside SCOPE,"
              f" {_total(dropped)} error(s) that could never go red or be"
              f" lowered")
    print(f"blessed {len(lowered) + len(fresh) + len(cleared)} file(s);"
          f" {len(risen) + len(arriving)} refused;"
          f" {len(swept)} swept in but not asked about;"
          f" {len(base)} entries, {_total(base)} error(s)")
    return 1 if (risen or arriving) else 0


if __name__ == "__main__":
    raise SystemExit(main())
