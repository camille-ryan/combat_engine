#!/usr/bin/env python
"""Which rows actually execute the code you just changed.

    uv run scripts/impact.py --record      one sweep under coverage, build the map
    uv run scripts/impact.py --select      which refs the working tree's change touches
    uv run scripts/impact.py --why <ref>   which mapped functions that row executes
    uv run scripts/impact.py --stats       what the map holds, and what it cannot narrow

## The cost this exists to remove

`check.py --history`, 2026-10-22:

```
audit wide     17 runs   36,901s spent   3 caught   12,300s per catch
audit narrow   49 runs    3,897s spent   6 caught      650s per catch
```

The wide sweep is **half of everything this suite has ever spent** -- 36,901
of 73,294 seconds -- and the narrow one catches twice as much for a
nineteenth of the price per catch. The reason it runs wide so often is
`audit.WIDE`: any change under `engine/`, `etl/` or `chargen/` widens
`--changed` back to all 21,476 rows, **including a comment**. That is the
right default, because an engine change really can move any row and a
narrowed run would be wrong rather than narrow. It is also why five engine
commits in one evening owed five whole-tree sweeps and found nothing.

Static analysis cannot fix this. 744 of 783 content files import from
`engine/`, and `cast.py` arrives as the `Cast` parameter rather than by
import, so an import graph answers "everything" -- which is why the plan
behind this file rejected one. **Coverage observes what static analysis has
to infer.**

## Function granularity, not lines

Lines drift whenever anything above them moves, so a line-keyed map goes
stale on an unrelated edit. `pytest-testmon` solved this by hashing the
enclosing block and this does the same thing more cheaply: covered lines are
mapped to the **function that encloses them** at record time, and selection
asks about function names. A docstring edit above a function no longer
invalidates it.

## Fail open, always

A selector that guesses is the one thing `scripts/CLAUDE.md` forbids
outright, so every uncertainty selects everything:

* no map on disk, or a map older than the last `data/game.db` rebuild;
* a changed file the map never saw;
* a changed line inside no function (module level, a decorator, an import);
* **anything under `etl/` or `chargen/`**, which stay as wide as they are
  today. The audit's two genuine catches in 400 commits both followed
  content changes, and the backtick scrub was visible to *nothing else*, so
  the content and build paths keep their full width and this narrows the
  engine case only;
* a changed function the map has but marked `wide`.

## The `wide` mark, which is what keeps the map small

A function like `dsl.use` is executed by nearly every row, so storing its ref
list costs 21,476 entries and buys nothing -- selecting all of them is the
same answer. So any function reached by more than `WIDE_SHARE` of the corpus
is stored as the bare string `"wide"` instead of a list. The map holds real
ref lists only where they can actually exclude something.

## Two blind spots, stated so nobody reads a narrow run as proof

* **`drivers.py` monkeypatches** (`world.decider`, `setattr(c, "shift", ...)`).
  A rule that patches over real code records no dependency on it. That does
  not arise for selecting *rows*, which is all this does, but it would if
  this were ever extended to select drivers rules.
* **The map is only as current as its recording.** It is git-ignored, like
  `data/` and `logs/`, both because `audited.json`'s own note refuses a
  per-ref map in the tree ("a megabyte of diff nobody reads and Camille is
  short of disk") and because testmon's known pain is sharing this kind of
  database between machines. `--select` refuses a map recorded before the
  current `game.db`.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: Git-ignored, beside the other things regenerated rather than kept.
MAP = ROOT / "logs" / "impact.json"
GAME = ROOT / "data" / "game.db"

#: A function reached by more than this share of the corpus is stored as
#: `"wide"`. Selecting 60% of the rows is not a saving worth a megabyte.
WIDE_SHARE = 0.30

#: The environment variable `audit.py` reads to decide whether to label each
#: row's work. Absent on every ordinary run, so the default path pays one
#: `os.environ` lookup per row and nothing else.
RECORDING = "COMBAT_ENGINE_IMPACT"

#: Which directories the worker's recorder measures. `NARROWABLE` is the one
#: authority for that, and it lives here, so it is handed over rather than
#: repeated in `audit.py`.
#:
#: **Scoping it is not an optimisation, it is what `select` already does.**
#: That function consults the map only for files under `NARROWABLE`; a
#: recording of all 783 content modules is tracing nobody reads, and the ref
#: lists it stores are the bulk of the file -- a function reached by 6,900
#: rows costs 60KB on its own, and `audited.json`'s note is explicit that
#: Camille is short of disk.
SOURCE = "COMBAT_ENGINE_IMPACT_SOURCE"

#: **What this cannot see, stated because it is a limit and not a hole.**
#: The map narrows a *per-commit* run. It is blind to a row added or rewritten
#: since `recorded_at` -- the first is caught by `_declared_now`, the second is
#: not -- and blind to a row that does not reach a function today and would
#: after the change, which is coverage-based selection's documented blind spot.
#:
#: The backstop for all three is the 03:07 wide sweep, which is the same
#: day-long window the root `CLAUDE.md` already accepts for a regression: "a
#: regression that lands at 10am being found at 3am is the right trade against
#: a gate people route around". So a row this omits is swept that night, and
#: `nightly.sh` re-records the map in the same run. #866, #865.
#:
#: Only these prefixes are narrowed. `etl/` and `chargen/` are deliberately
#: absent -- see the fail-open list in the module docstring.
NARROWABLE = ("src/combat_engine/engine/",)


def real_coverage():  # noqa: ANN201
    """Import the `coverage` package, defensively, and say if it is shadowed.

    **`scripts/` goes first on `sys.path`** -- `triage.py`, `refs.py` and
    `blocked.py` all put it there -- so any instrument named after a library
    shadows that library for every other instrument. One was: the
    written/not-written counter was called `coverage.py`, and since it has a
    `main()` the wrong module even looked plausible.

    It is `written.py` now (#853), because the shadow could not be worked
    around from here. Reaching past it with `PathFinder` fails -- the
    package's own `__init__` does `from coverage.control import ...`, which
    re-resolves `coverage` through `sys.modules` and dies with "'coverage' is
    not a package" -- and taking it off the path for the duration of *this*
    import does nothing for the **worker**, because coverage's own
    multiprocessing support imports itself inside the library, where no
    `sys.path` tricks of ours are running.

    So the guard that remains is a check, not a workaround: if the name is
    shadowed again by some future instrument, say so loudly here rather than
    letting the recording silently measure nothing.
    """
    import coverage

    where = getattr(coverage, "__file__", "") or ""
    if "/scripts/" in where:
        raise SystemExit(
            f"`import coverage` resolves to {where}, not the library. An "
            "instrument in scripts/ is shadowing it -- rename the instrument "
            "(see #853); this cannot be worked around from the worker side.")
    return coverage


def _functions_of(path: Path) -> list[tuple[int, int, str]]:
    """Every function in this file as `(first line, last line, name)`.

    Nested functions come after their parent, so the **last** match wins when
    a line is inside both -- which is what makes the innermost enclosing
    function the one credited.
    """
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError):
        return []
    out: list[tuple[int, int, str]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                out.append((child.lineno, _end_of(child), name))
                walk(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            else:
                walk(child, prefix)

    walk(tree, "")
    return out


def _end_of(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None)
    if end:
        return end
    return max((getattr(n, "lineno", 0) for n in ast.walk(node)), default=0)


def _enclosing(funcs: list[tuple[int, int, str]], line: int) -> str:
    """The innermost function containing `line`, or "" for module level."""
    best, span = "", None
    for start, end, name in funcs:
        if start <= line <= end and (span is None or (end - start) < span):
            best, span = name, end - start
    return best


def record(sample: int = 0, jobs: int = 0, core: str = "",
           only: list[str] | None = None) -> int:
    """One pooled sweep under coverage, labelling each row's work with its ref.

    `sample` records a deterministic slice instead of everything. A sampled
    map is **not** a smaller version of the real one -- a row it never saw is
    a row `--select` must select, so sampling makes selection wider, never
    wrong. It exists to prove the machinery in a minute rather than an hour,
    and `--stats` says which it is holding.

    **This ran serially and that was the whole of #853's cost.** One process
    managed 1.0 rows/s against the pool's ~20, which is where the 6.4-hour
    estimate came from; the instrumentation itself is about 2x. The fix is
    not here but in `audit.py`: a per-ref context has to be switched *inside*
    the process doing the work, so the recording is started by the worker
    (`audit._label_this_row`) and this function only sets the environment
    variable, runs the ordinary parallel sweep, and combines what the workers
    wrote.

    `data_suffix=True` in the worker is what makes that safe -- every process
    writes its own file and `combine` merges them -- and it is also the thing
    that can fail silently, because a worker that never starts its recorder
    contributes no rows and the map simply narrows too far. Hence the control
    in `_build_map`, which refuses to write a map whose contexts are not
    exactly the refs asked for.
    """
    coverage = real_coverage()
    sys.path.insert(0, str(ROOT / "scripts"))
    import audit

    refs = list(declared_refs())
    whole = len(refs)
    merge_into = None
    if only:
        # **The incremental form, which is what makes the map maintainable.**
        # A full recording is 83-158 minutes, so the only way a verb written
        # today entered the map was to wait for the nightly -- and until it
        # did, every *edit* to that verb went wide. #865.
        #
        # Refuses on a map without `seen`, because the merge cannot be sound
        # without it: a row that executes no engine function appears in no
        # ref list, so an older map cannot say whether it was recorded and
        # found nothing or never recorded at all. One full run fixes that
        # once.
        merge_into = _load_raw()
        if merge_into is None:
            print("# no map to merge into. Record the whole corpus once"
                  " first: `impact.py --record`.")
            return 1
        if "seen" not in merge_into:
            # **A complete map's `seen` is derivable, so it does not owe a
            # 2.5-hour re-record to gain one.** `_build_map`'s control
            # refuses to write unless the combined data holds *exactly* the
            # refs it asked for, and a full recording asks for the whole
            # declared corpus -- so for a map whose `corpus` is its
            # `whole_corpus`, "which rows it saw" is "all of them", and the
            # only question is whether the corpus has moved since. If it
            # has, the migration is declined and a full recording is the
            # honest answer; the map is not edited either way.
            if (merge_into.get("corpus") == merge_into.get("whole_corpus")
                    == whole):
                merge_into["seen"] = sorted(refs)
                print(f"# this map predates `seen`. It recorded the whole"
                      f" corpus and the corpus has not moved ({whole} rows),"
                      f" so `seen` is all of them -- migrated in place.")
            else:
                print("# this map predates incremental recording and does"
                      " not say which rows it saw, so a merge cannot be"
                      f" sound: it holds {merge_into.get('corpus')} of"
                      f" {merge_into.get('whole_corpus')} rows against"
                      f" {whole} declared now. Record the whole corpus"
                      " once: `impact.py --record`.")
                return 1
        known = set(refs)
        unknown = [r for r in only if r not in known]
        if unknown:
            print(f"# not declared rows: {', '.join(unknown[:8])}")
            return 1
        refs = sorted(set(only))
    if sample:
        refs = refs[::max(1, whole // sample)][:sample]
    print(f"# recording {len(refs)} of {whole} rows under "
          f"coverage {coverage.__version__}")

    base = ROOT / "logs" / ".impact-coverage"
    base.parent.mkdir(parents=True, exist_ok=True)
    # The suffixed files from any previous run, which `combine` would happily
    # merge into this one -- a stale ref list is worse than no map.
    for stale in base.parent.glob(base.name + "*"):
        stale.unlink()

    if core == "sysmon":
        # **Measured, and the plan was wrong to recommend it.** `sysmon` is
        # 3x faster -- 12.5 rows/s against 4.1 on the same 400-row sample --
        # and it recorded **278 of 400 contexts**, because coverage does not
        # support dynamic contexts on that core at all. It says so in a
        # warning that scrolls past in a run printing thousands of lines:
        # "Dynamic contexts aren't supported with core=sysmon; context data
        # may be incomplete (no-sysmon-context)".
        #
        # So the speedup is real and useless here: a map missing 30% of its
        # refs narrows those rows to nothing. `_build_map`'s control is what
        # caught it, which is the clearest evidence in this file that the
        # control earns its place -- the run looked like a 3x win and
        # finished clean. Refused up front so nobody pays 90 minutes to
        # rediscover it.
        print("# core=sysmon cannot record dynamic contexts "
              "(coverage: no-sysmon-context). It recorded 278 of 400 refs "
              "when measured. Refusing.")
        return 1

    os.environ[RECORDING] = str(base)
    os.environ[SOURCE] = os.pathsep.join(str(ROOT / rel) for rel in NARROWABLE)
    if core:
        # `sys.monitoring` on 3.13 is much cheaper than the trace function,
        # but it is a different core with its own limits, so it is opt-in and
        # the context control below is what says whether it worked.
        os.environ["COVERAGE_CORE"] = core
    started = time.time()
    try:
        audit._run_all(refs, jobs=jobs)
    finally:
        # **The parent is a worker too, for a small batch, and nothing saved
        # it.** `_run_all` runs serially *in this process* for `--jobs 1` or
        # fewer than 8 refs, so the recorder `_label_this_row` starts belongs
        # to the parent -- whose `atexit` fires long after `_build_map` has
        # already combined and judged. A one-ref batch therefore wrote no
        # data file at all and the control reported the row as recording
        # nothing, which is exactly the incremental form's normal case. The
        # same call is a no-op in the pooled case, where `_RECORDER` here is
        # `None` and each worker saved its own slice.
        audit._save_this_worker()
        os.environ.pop(RECORDING, None)
        os.environ.pop(SOURCE, None)
        if core:
            os.environ.pop("COVERAGE_CORE", None)
    took = time.time() - started
    wrote = sorted(base.parent.glob(base.name + ".*"))
    print(f"# swept in {took:.0f}s ({len(refs) / took:.1f} rows/s), "
          f"{len(wrote)} worker data files")
    if not wrote:
        print("# no worker wrote any coverage data. Nothing recorded.")
        return 1

    # The combined data is left on disk: it is the only way to re-derive the
    # map without re-sweeping for 83 minutes. **Reading it back needs
    # `Coverage.load()`** -- a fresh `Coverage` over an existing data file
    # that is asked for `get_data()` without loading first initialises an
    # empty one and can overwrite the file, which is how 87MB of this run's
    # data was destroyed by a probe that only meant to read it.
    cov = coverage.Coverage(data_file=str(base))
    cov.combine(strict=True, keep=False)
    cov.save()
    return _build_map(cov, refs, whole, merge_into=merge_into)


def _build_map(cov, asked: list[str], whole: int,  # noqa: ANN001
               merge_into: dict | None = None) -> int:
    """Turn per-ref line coverage into `{file: {function: refs | "wide"}}`.

    Refuses to write unless the combined data holds **exactly** the refs
    that were asked for, which is #853's control and the only thing that
    can see the failure this design makes possible: a worker whose
    recorder never started, or whose data file was lost, records nothing
    for its whole chunk. Every row in that chunk then looks like a row
    that depends on no engine function at all, so `--select` *omits* it --
    silently, and in the direction that misses a regression. A map built
    short is worse than no map, because `_load` fails open and no map
    selects everything.
    """
    data = cov.get_data()
    files = list(data.measured_files())
    seen = {c for c in data.measured_contexts() if c}
    corpus = len(asked)
    print(f"# {len(files)} files measured, {len(seen)} contexts")
    missing = sorted(set(asked) - seen)
    extra = sorted(seen - set(asked))
    if missing or extra:
        print(f"# REFUSED: {len(missing)} of {corpus} refs recorded "
              f"nothing, {len(extra)} contexts were not asked for.")
        if missing:
            print(f"#   missing: {', '.join(missing[:10])}"
                  f"{' ...' if len(missing) > 10 else ''}")
        if extra:
            print(f"#   unasked: {', '.join(extra[:10])}"
                  f"{' ...' if len(extra) > 10 else ''}")
        print("# no map written. A short map narrows too far, silently.")
        return 1

    funcs_by_file = {f: _functions_of(Path(f)) for f in files}
    hit: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for context in data.measured_contexts():
        if not context:
            continue
        data.set_query_context(context)
        for filename in files:
            lines = data.lines(filename) or ()
            if not lines:
                continue
            rel = str(Path(filename).relative_to(ROOT))
            table = funcs_by_file[filename]
            for line in lines:
                name = _enclosing(table, line)
                if name:
                    hit[rel][name].add(context)

    # **The ceiling is a share of the corpus the map covers, not of this
    # batch**, and getting that backwards destroyed the map on the first
    # incremental run: a two-row batch gives `int(2 * 0.30) == 0`, so every
    # function those two rows touched crossed the ceiling and was recorded
    # `"wide"` -- 0 narrow, 567 wide, and the merge below cannot recover it
    # because a fresh `"wide"` is kept wide by design. The merged corpus is
    # known before any row is classified, so it is computed here.
    seen = set(asked) | set((merge_into or {}).get("seen", ()))
    ceiling = int(len(seen) * WIDE_SHARE)
    out: dict[str, dict[str, object]] = {}
    wide = narrow = 0
    for rel, funcs in hit.items():
        out[rel] = {}
        for name, refs in funcs.items():
            if len(refs) > ceiling:
                out[rel][name] = "wide"
                wide += 1
            else:
                out[rel][name] = sorted(refs)
                narrow += 1

    # **A partial recording merges rather than replaces**, and the merge has
    # one rule that is easy to get backwards: every ref in this batch is
    # **dropped from every existing list first**, then added where it was
    # just observed. Adding without dropping would leave a row attributed to
    # a function it no longer calls -- which is the direction that selects
    # too few rows, silently, and is exactly what `_build_map`'s control
    # exists to prevent on a full run.
    if merge_into is not None:
        batch = set(asked)
        for rel, table in merge_into.get("files", {}).items():
            kept = out.setdefault(rel, {})
            for name, entry in table.items():
                if entry == "wide":
                    # A wide function stays wide: its list was discarded at
                    # recording time, so there is nothing to subtract from
                    # and no way to tell whether this batch belongs to it.
                    # Re-widening is the fail-open direction.
                    #
                    # **Assignment, not `setdefault`.** This was
                    # `kept.setdefault(name, "wide")`, which cannot do what
                    # the paragraph above says: the fresh batch has already
                    # written its own list into that slot, and a two-row
                    # batch is never above the ceiling, so the slot is
                    # always taken. A merge therefore turned every wide
                    # function the batch touched into a narrow list holding
                    # *only the batch's rows* -- `equipment._onto_weapon`,
                    # reached by most of the corpus, came out naming two.
                    # That is the silent under-selection this whole file is
                    # built to avoid, arriving through the one path that
                    # looked like bookkeeping.
                    kept[name] = "wide"
                    continue
                fresh = kept.get(name)
                older = [r for r in entry if r not in batch]
                if fresh == "wide":
                    continue
                kept[name] = sorted(set(older) | set(fresh or ()))
        # Re-apply the ceiling: a merged list can cross it even though
        # neither half did.
        for table in out.values():
            for name, entry in list(table.items()):
                if entry != "wide" and len(entry) > ceiling:
                    table[name] = "wide"
        narrow = sum(1 for tb in out.values() for e in tb.values()
                     if e != "wide")
        wide = sum(1 for tb in out.values() for e in tb.values()
                   if e == "wide")
        corpus = len(seen)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    stamp = ((merge_into or {}).get("recorded_when") if merge_into is not None
             else time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    MAP.parent.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps({
        "corpus": corpus,
        # **Which rows the map has actually looked at**, which `corpus` alone
        # could not say and an incremental recording cannot do without. A
        # row that executes no engine function appears in no ref list, so
        # without this there is no way to tell it from a row that was never
        # recorded -- and `select()` fails *closed* on an unmapped function,
        # so guessing wrong omits rows.
        "seen": sorted(seen),
        "whole_corpus": whole,
        "sampled": corpus != whole,
        "ceiling": ceiling,
        "game_db_mtime": GAME.stat().st_mtime if GAME.exists() else 0,
        # **A merge must not advance this, and advancing it broke the guard
        # it exists to feed.** `recorded_at` is the sha whose code the map's
        # *silence* can speak for -- `selection` reads it to tell a function
        # written since the recording from a genuinely dead one. An
        # incremental batch re-measures three rows, not the corpus, so
        # stamping HEAD on it claims the whole map is current and sends
        # every new verb straight back into the fail-closed branch. Caught
        # by `Cast.replace_roll` still selecting 0 rows after the guard
        # landed. The batch's own sha is kept beside it instead.
        "recorded_at": (merge_into or {}).get("recorded_at") or head,
        # **When, in wall clock, because neither of the other two answers
        # it.** `check.py` reported the map's age from the file's mtime,
        # which a top-up rewrites -- so three re-measured rows made a
        # 9-hour-old recording read "under an hour ago". Reading the age off
        # `recorded_at`'s *commit date* instead was no better: the nightly
        # records at 01:55 against whatever HEAD then is, so a map recorded
        # 8 hours ago at a 22-hour-old commit reported 22 hours. Only the
        # recording knows. Preserved across a merge for `recorded_at`'s
        # reason -- a batch re-measures three rows, not the corpus.
        #
        # **A merge that finds no stamp must not invent one**, and the first
        # version did: topping up a map written before this field existed
        # wrote `now`, so a 22-hour-old recording reported "under an hour
        # ago" through the very field added to stop that. Absent stays
        # absent, and `check.py` says it has no recording time rather than
        # guessing from the file.
        **({"recorded_when": stamp} if stamp else {}),
        "topped_up": ([*(merge_into or {}).get("topped_up", []),
                       {"at": head, "rows": sorted(asked)}]
                      if merge_into is not None else []),
        "files": out,
    }))
    print(f"# {narrow} functions carry a ref list, {wide} are wide "
          f"(> {ceiling} of {corpus} rows)")
    print(f"# written to {MAP.relative_to(ROOT)}")
    return 0


def _load_raw() -> dict | None:
    """The map as written, with none of `_load`'s freshness refusals.

    `_load` is for *selecting* and so fails open on anything suspicious --
    a moved corpus, a rebuilt database, a sha outside this history. A merge
    is the opposite situation: those are the very conditions a re-recording
    is meant to repair, so refusing to read the file would make the map
    unrepairable exactly when it needs repairing.
    """
    if not MAP.exists():
        return None
    try:
        return json.loads(MAP.read_text())
    except (OSError, ValueError):
        return None


def _load() -> dict | None:
    """The map, or None with a reason printed. Any doubt means fail open."""
    if not MAP.exists():
        print("# no map recorded -- `impact.py --record`. Selecting everything.")
        return None
    try:
        got = json.loads(MAP.read_text())
    except (OSError, ValueError) as exc:
        print(f"# map unreadable ({exc}). Selecting everything.")
        return None
    if GAME.exists() and got.get("game_db_mtime", 0) < GAME.stat().st_mtime:
        print("# map predates the current data/game.db. Selecting everything.")
        return None
    at = got.get("recorded_at") or ""
    if at and not _in_history(at):
        print(f"# map was recorded at {at[:9]}, which is not in this tree's"
              f" history. Selecting everything.")
        return None
    live = _declared_now()
    if live and live != got.get("corpus"):
        print(f"# the corpus moved: {got.get('corpus')} rows when the map was "
              f"recorded, {live} now. Selecting everything.")
        return None
    return got


@cache
def _in_history(sha: str) -> bool:
    """Is this commit an ancestor of HEAD, or HEAD itself?

    **The guard that makes the map safe to carry between trees**, which is
    what the map is for: `logs/` is git-ignored and per-worktree, so a map
    recorded on a branch has to be copied to the main checkout to be worth
    anything -- and copied *before* the branch merges it describes an
    `engine/` the receiving tree does not have yet. `select` resolves a
    changed line to its enclosing function by parsing the file **as it is
    now**, so a name can match a recorded ref list belonging to a different
    version of that function. The corpus count only notices if the row total
    also happens to have moved.

    Ancestry answers it exactly. A map is valid for any tree that contains
    the commit it was recorded at, and for no other: after the merge, used;
    before it, refused. The same test covers bisecting back past the
    recording and two branches that each recorded their own.

    True on failure to ask, deliberately -- the other guards still run, and
    treating an unavailable `git` as "refuse everything" would turn a
    missing binary into a silent twenty-minute tax.
    """
    # **Does the commit exist here at all**, asked first and separately. A
    # map copied from a tree whose history this one does not share names a
    # sha that is simply absent, and `merge-base --is-ancestor` reports that
    # with exit **128** -- the same code it uses for "not a repository". The
    # first draft folded 128 into "could not ask" and returned True, so a map
    # from an unrelated repository was accepted: the plant for this guard
    # passed a sha of forty zeroes and was told it was in history.
    #
    # An absent commit is a definite no, not a failure to answer.
    try:
        known = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                               cwd=ROOT, capture_output=True, text=True)
        if known.returncode != 0:
            return False
        done = subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
            cwd=ROOT, capture_output=True, text=True)
    except OSError:
        return True          # no git to ask; the other guards still run
    if done.returncode in (0, 1):
        return done.returncode == 0
    return True              # it exists but the question could not be put


@cache
def declared_refs() -> tuple[str, ...]:
    """Every ref the tree declares, counted the way the recording counts them.

    **One definition, because two were off by two and the guard below could
    only ever misfire.** `declared()` answers differently depending on who has
    imported what: bringing in `audit` registers its test board's own two rows
    (`dummy:mba`, `dummy:rba`), so the corpus is 23,062 asked from inside the
    audit and 23,060 asked from outside it. `record` imported `audit` and got
    the larger number into the map; `_load`'s first draft asked without it and
    got the smaller one, so **every** run reported "the corpus moved: 23062
    when the map was recorded, 23060 now" and narrowed nothing. A selector
    that silently never fires is the same failure as one that fires wrongly,
    and it would have looked exactly like the fail-open design working.

    So both sides come through here. The import is the load-bearing line, not
    an accident of ordering.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import audit  # noqa: F401  -- registers the test board's two rows
    from combat_engine.content import declared
    return tuple(sorted(declared()))


@cache
def _declared_now() -> int:
    """How many rows the tree declares right now, or 0 if it cannot be asked.

    **The guard #866 is about, and the half of it that is cheap.** A map's ref
    lists are only a complete answer for the corpus that was recorded; a row
    added afterwards is in no list, so `select` would omit it -- and a newly
    written row is the row most likely to be broken. Counting is one import of
    `combat_engine.content`, seconds against the twenty minutes the selection
    exists to save.

    **It does not catch a row rewritten in place**, which may now reach engine
    functions the recording never saw it reach. That case is a stated limit
    rather than a hole -- the 03:07 wide sweep is its backstop -- and #865 is
    what makes the window small enough for the limit to be a small one. Do not
    read a passing count as "the map is current".

    0 on any failure, which means "cannot tell" and leaves the other guards to
    speak. Failing *open* here would be wrong in the other direction: an import
    error would silently widen every run back to 23,062 rows and nobody would
    notice the selector had stopped working.
    """
    try:
        return len(declared_refs())
    except Exception:
        return 0


def _changed_lines() -> dict[str, set[int]]:
    """Changed files and the lines that moved, from the working tree."""
    done = subprocess.run(["git", "diff", "-U0", "HEAD", "--", "."],
                          cwd=ROOT, capture_output=True, text=True)
    out: dict[str, set[int]] = defaultdict(set)
    current = ""
    for line in done.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("@@") and current:
            # @@ -a,b +c,d @@
            try:
                plus = line.split("+", 1)[1].split(" ", 1)[0]
                start, _, count = plus.partition(",")
                first = int(start)
                span = int(count) if count else 1
            except (IndexError, ValueError):
                continue
            out[current].update(range(first, first + max(span, 1)))
    return dict(out)


def _moved_since(sha: str, rel: str) -> set[int] | None:
    """Lines of `rel` that differ from `sha`, in working-tree coordinates.

    `None` if the question cannot be answered -- no sha recorded, a sha this
    checkout does not hold, or git failing for any reason -- which the
    caller must read as "the map's silence is not evidence".
    """
    if not sha or not _in_history(sha):
        return None
    done = subprocess.run(["git", "diff", "-U0", sha, "--", rel],
                          cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        return None
    out: set[int] = set()
    for line in done.stdout.splitlines():
        if not line.startswith("@@"):
            continue
        try:
            plus = line.split("+", 1)[1].split(" ", 1)[0]
            start, _, count = plus.partition(",")
            first, span = int(start), int(count) if count else 1
        except (IndexError, ValueError):
            continue
        out.update(range(first, first + max(span, 1)))
    return out


def _carrying(path: Path, lines: set[int]) -> set[int]:
    """The changed lines that carry behaviour: not blank, not a comment.

    **This is for the message, not the verdict**, and that is worth saying
    because it looks like a saving and is not. A single blank line at
    `cast.py:4804` was what made one batch report *"changed outside any
    function (module level, a decorator or an import)"* and go WIDE -- so
    the obvious conclusion is that filtering these buys narrow runs.

    Measured across the six engine batches of 2026-10-24/25: **every verdict
    is identical with and without this filter.** Each of those commits has a
    real cause underneath -- a genuinely hot function, a module-level import,
    a class-level field -- and the inert lines were only the first reason
    reported, not the operative one.

    So it is kept for one reason: a diagnosis that blames a blank line sends
    the next reader looking in the wrong place, which cost a session here
    exactly once. A line past the end of the file is a deletion and carries
    nothing either.
    """
    try:
        src = path.read_text().splitlines()
    except OSError:
        return set(lines)
    out = set()
    for line in lines:
        if not 0 < line <= len(src):
            continue
        text = src[line - 1].strip()
        if text and not text.startswith("#"):
            out.add(line)
    return out


def selection(got: dict, changed: dict[str, set[int]]
              ) -> tuple[list[str] | None, list[str]]:
    """The refs this change needs, or `None` for WIDE, plus lines to print.

    Split out of `select` so `check.py` can ask the question without parsing
    a subprocess's stdout -- a selector read through a text format is a
    selector that mis-reads it once and narrows to nothing.

    `None` means **select everything**, and every doubt returns it: a changed
    file absent from the map, an edit outside any function, a function the
    recording found too hot to list, or a union that exceeds the map's own
    ceiling. `[]` means this instrument has no opinion, which is not the same
    thing -- it is what a content-only change gets, and the caller keeps its
    present behaviour.
    """
    notes: list[str] = []
    narrowable = [f for f in changed if f.startswith(NARROWABLE)]
    other = [f for f in changed if f not in narrowable]
    if other:
        # Content, instruments, the ETL, chargen: all keep their present
        # behaviour. `audit.py --changed` already narrows content properly.
        notes.append(f"# not narrowable here, deferring to audit.py --changed: "
                     f"{', '.join(sorted(other))}")
    if not narrowable:
        notes.append("# nothing under engine/ changed; this instrument has no"
                     " opinion")
        return [], notes

    refs: set[str] = set()
    for rel in sorted(narrowable):
        table = got["files"].get(rel)
        if table is None:
            notes.append(f"# {rel} is not in the map. WIDE.")
            return None, notes
        funcs = _functions_of(ROOT / rel)
        # Which lines of this file the recording never saw, so the branch
        # below can tell a genuinely dead function from one written since.
        since = _moved_since(got.get("recorded_at", ""), rel)
        touched = {_enclosing(funcs, line)
                   for line in _carrying(ROOT / rel, changed[rel])}
        if not touched:
            notes.append(f"# {rel} changed only in blank lines and comments")
            continue
        if "" in touched:
            notes.append(f"# {rel} changed outside any function (module level,"
                         f" a decorator or an import). WIDE.")
            return None, notes
        for name in sorted(touched):
            entry = table.get(name)
            if entry is None:
                # **The one place this fails closed**, and it is only sound
                # because the recording's context control proves the map saw
                # every row. A function no row executes is a function no row
                # can depend on.
                #
                # **But only if the recording could have seen it.** That was
                # #866 and it is not theoretical: `Cast.replace_roll` was
                # written hours after the map was recorded, two rows call it,
                # and an edit inside it selected **0 rows** under the note
                # "no row can depend on it" -- a brand-new verb, which is the
                # code most likely to be wrong, audited by nothing and
                # reported clean. A new *function* is exactly the case this
                # branch cannot distinguish from a dead one, because both are
                # simply absent from the table.
                #
                # So ask git. If the function's own lines differ from the
                # recorded sha, the map's silence is about a different
                # function and says nothing; if the question cannot be
                # answered at all, the same applies. Only an unchanged
                # function keeps the fail-closed reading.
                span = next(((s, e) for s, e, n in funcs if n == name), None)
                fresh = since is None or (
                    span is not None
                    and any(s in since for s in range(span[0], span[1] + 1)))
                if fresh:
                    notes.append(
                        f"# {rel}:{name} is not in the map and has changed"
                        f" since it was recorded, so the map cannot speak"
                        f" for it. WIDE. Record it in seconds instead:"
                        f" `impact.py --record --refs <rows>`.")
                    return None, notes
                notes.append(f"# {rel}:{name} was never executed by any row --"
                             f" no row can depend on it")
                continue
            if entry == "wide":
                notes.append(f"# {rel}:{name} is reached by more than"
                             f" {got['ceiling']} rows. WIDE.")
                return None, notes
            notes.append(f"# {rel}:{name} -> {len(entry)} rows")
            refs.update(entry)

    # **A union can exceed what the per-function ceiling allows**, and at that
    # point narrowing has stopped being a saving: the same 30% rule that sends
    # one hot function to `wide` sends a wide-enough union there too. Also
    # keeps the ref list off a command line it could overflow.
    if len(refs) > got["ceiling"]:
        notes.append(f"# the union across those functions is {len(refs)} rows,"
                     f" over the {got['ceiling']} ceiling. WIDE.")
        return None, notes
    return sorted(refs), notes


def select() -> int:
    """Print the refs a change needs audited, or `WIDE`.

    **Proven by a plant, on `Cast.crit_becomes`.** A comment edited inside
    that method selects **71 rows of 23,062** (0.3%). Making the method
    `raise` instead, and auditing three sets of refs:

        the 71 selected                     70 of 70 raise
        the 15 rows that *name* the verb
          and were not selected              0 raise, 13/15 still fire
        71 random unselected rows            0 raise

    So every row the selection names does execute the changed function, and
    neither control is disturbed. The negative control is drawn at the
    positive's size on purpose -- a smaller one proves nothing.

    **The disagreement with `--calls` is real and favours the map**, which
    was not what I expected when the two sets came out sharing only three
    refs. `audit.py --calls 'c.crit_becomes'` finds 18 rows naming the verb
    in their source or a marker; 15 of those never reach it on the audit
    board, so a change to it cannot move their verdict and auditing them
    proves nothing. The map names 71 and **all 70 posable ones** are
    exercised. Narrower *and* more complete.

    `--calls` keeps its job, which is a different one: a brand-new verb has
    no recorded history, and a marker naming a symbol is a static fact.

    What neither instrument can see is a row that does **not** reach the
    function today and **would** after the change -- coverage-based
    selection's documented blind spot, and the reason the 03:07 wide sweep
    stays the backstop. #866 states that limit; #865 is what keeps the map
    close enough to the tree for it to be a small one.
    """
    got = _load()
    changed = _changed_lines()
    if not changed:
        print("# nothing changed in the working tree")
        return 0
    print(f"# {len(changed)} changed file(s): {', '.join(sorted(changed))}")
    if got is None:
        print("WIDE")
        return 0

    if got.get("sampled"):
        print(f"# the map is a {got['corpus']}-row sample of "
              f"{got['whole_corpus']}, so most rows were never observed"
              f" and cannot be excluded. WIDE.")
        print("WIDE")
        return 0

    refs, notes = selection(got, changed)
    for note in notes:
        print(note)
    if refs is None:
        print("WIDE")
        return 0
    if not refs:
        return 0

    print(f"\n# {len(refs)} rows of {got['corpus']} "
          f"({len(refs) * 100 // max(got['corpus'], 1)}%)")
    for ref in sorted(refs):
        print(ref)
    return 0


def why(ref: str) -> int:
    """Which mapped functions this row executes."""
    got = _load()
    if got is None:
        return 1
    found = 0
    for rel, table in sorted(got["files"].items()):
        for name, entry in sorted(table.items()):
            if entry != "wide" and ref in entry:
                print(f"  {rel}:{name}  ({len(entry)} rows)")
                found += 1
    print(f"# {ref} is named by {found} narrow function(s); "
          f"everything else it runs is wide")
    return 0


def stats() -> int:
    got = _load()
    if got is None:
        return 1
    print(f"recorded at {got['recorded_at'][:9]} over {got['corpus']} rows, "
          f"ceiling {got['ceiling']}")
    for rel, table in sorted(got["files"].items()):
        wide = sum(1 for v in table.values() if v == "wide")
        narrow = len(table) - wide
        if narrow:
            print(f"  {rel:48} {narrow:4} narrow, {wide:4} wide")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true", help="build the map")
    ap.add_argument("--sample", type=int, default=0, metavar="N",
                    help="record a deterministic N-row slice, to prove it works")
    ap.add_argument("--jobs", type=int, default=0, metavar="N",
                    help="workers for the recording sweep; 1 is serial")
    ap.add_argument("--core", default="", metavar="NAME",
                    help="coverage core: sysmon is cheaper on 3.13, ctrace is the default")
    ap.add_argument("--refs", default="", metavar="R1,R2|@FILE",
                    help="record only these rows and merge into the map")
    ap.add_argument("--select", action="store_true", help="refs this change needs")
    ap.add_argument("--why", metavar="REF", help="what one row executes")
    ap.add_argument("--stats", action="store_true", help="what the map holds")
    args = ap.parse_args()
    if args.record:
        only: list[str] = []
        if args.refs:
            if args.refs.startswith("@"):
                only = [line.strip() for line
                        in Path(args.refs[1:]).read_text().split()
                        if line.strip()]
            else:
                only = [r.strip() for r in args.refs.split(",") if r.strip()]
        return record(args.sample, args.jobs, args.core, only=only)
    if args.select:
        return select()
    if args.why:
        return why(args.why)
    if args.stats:
        return stats()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
