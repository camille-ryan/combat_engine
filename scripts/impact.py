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

## Fail open, always -- all sixteen ways, which is the whole list

A selector that guesses is the one thing `scripts/CLAUDE.md` forbids
outright, so every uncertainty selects everything. **This is the canonical
enumeration and the only one**: it used to be five bullets here, nine in the
root `CLAUDE.md` and sixteen leaf conditions in the code, and three
different lists is how the next reader's wrong model gets built. Both other
places now point here.

Six in `check._rows_from_map`, before the map is even opened:

1. `import impact` raised;
2. `git status` failed;
3. untracked Python under `src/combat_engine/`, which `git diff` cannot see;
4. a changed path under `audit.WIDE` that is not narrowable -- **`etl/`,
   `chargen/`, `scripts/audit.py`**. The audit's two genuine catches in 400
   commits both followed content changes and the backtick scrub was visible
   to *nothing else*, so the build paths keep their full width and this
   narrows the engine case only;
5. `audit._database_moved()` -- a different question with a different key
   from the one in `_load` below, and deliberately kept;
6. the map is a **sample**, so most rows were never observed.

Five in `_load`, about the map as a whole:

7. no map on disk;
8. the map is unreadable;
9. the map is invalid against the current `data/game.db` (see *Validity*);
10. `recorded_at` is not in this tree's history;
11. the corpus moved **and** the map does not say which rows it saw. A map
    that does say is not a refusal -- the rows declared since are nameable,
    so they are unioned in instead. #925.

Five in `selection`, about the change:

12. a changed narrowable file the map never saw;
13. a changed line inside no function (module level, a decorator, an import);
14. a changed function absent from the map whose own lines have moved since
    `recorded_at` -- **unless git says it did not exist then**, which is
    additive and narrows to the rows that name it. #866, #1194;
15. a changed function the map has but marked `wide`;
16. a union across the changed functions exceeding the map's own ceiling.

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
  database between machines.

## Validity: a content digest, not an mtime

Monster defences, a drawn party's items and every number a row reads come
out of `data/game.db`, and `audit._attempts` stops as soon as a row fires --
so the *number of boards played* is outcome-dependent on that file and a
rebuild really can change which rows reach which function. The map therefore
carries a key for it.

**`game_db_mtime` was the wrong key in both directions.** It over-fired:
`etl.build` has no time or random input, so a rebuild with unchanged ETL
produces byte-identical rows and still threw away a recording that cost 1.3
to 2.8 hours. And it under-fired: a database copied in with an older mtime
passed.

`game_db_digest` is a canonical digest of every table's contents -- tables
sorted, columns sorted, rows ordered by the full column tuple -- so nothing
about physical layout reaches it and an identical rebuild is identical. 388ms,
behind the mtime as a fast path, so it is paid once per rebuild rather than
once per run. `_valid` is the one function that answers this and
`check._map_state` calls it rather than re-implementing it, which is #1185.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
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
#: The backstop for all three is **a wide sweep before a push, by whoever
#: pushes**. It used to be an overnight schedule and that is retired -- 7
#: clean runs in 80 attempts, 58 skipped on a dirty tree or a concurrent
#: run -- so nothing pays this debt automatically. What does happen
#: automatically is the top-up: every clean `check.py` records the rows its
#: commit touched, so a new row or verb is in the map one commit after it is
#: written. #866, #865.
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
    # map without re-sweeping for 1.3-2.8 hours. **Reading it back needs
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
                # `isinstance` rather than `fresh or ()`, because a map
                # entry is a ref list *or* the string `"wide"` and the
                # second is handled above -- so anything else here is a
                # malformed map, and treating a stray string as an iterable
                # of refs would quietly splice its characters into the list.
                kept[name] = sorted(set(older) | set(
                    fresh if isinstance(fresh, list) else ()))
        # Re-apply the ceiling: a merged list can cross it even though
        # neither half did.
        for table in out.values():
            for name, entry in list(table.items()):
                if isinstance(entry, list) and len(entry) > ceiling:
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
        # **A merge inherits this rather than recomputing it, and
        # recomputing it is #925.** On a fresh recording `corpus` is the refs
        # asked for and `whole` the corpus they were drawn from, so the
        # comparison is exactly "did I deliberately take a slice". On a
        # *merge* the two count different populations -- `corpus` is the
        # merged `seen`, `whole` is the live tree -- so a top-up branded a
        # map that had recorded everything a SAMPLE the moment one row was
        # declared after it, and a sampled map narrows nothing at all. Two
        # racial traits disabled the selector for the other 23,061 rows for
        # 36 hours; the run that found it paid 1,321s where 658 rows were
        # owed. The word was the expensive part: "SAMPLE" names a decision
        # somebody took, so the reader goes looking for who chose to sample
        # instead of at a three-second top-up.
        "sampled": (merge_into.get("sampled", False)
                    if merge_into is not None else corpus != whole),
        "ceiling": ceiling,
        # **A merge must not advance this either, for `recorded_at`'s exact
        # reason.** This is the stamp `_load` reads to refuse a map recorded
        # against a different database, and writing it unconditionally meant
        # a *top-up* claimed the whole map matched the database the top-up
        # happened to see. Measured: after an ETL rebuild, recording 40 rows
        # stamped a 23,063-row map as current for the new database while
        # 23,023 of its entries had been observed against the old one -- so
        # `_load` would have accepted it and narrowed on stale observations.
        #
        # **That is the dangerous direction, and worse than #925.** A map
        # that narrows nothing is expensive and safe; a map that narrows on
        # observations taken against different data excludes rows whose
        # numbers have moved, and `selection` fails *closed* on an absence.
        # `recorded_at` carries the same note and was got right; this field
        # was missed by it, which is why both now say so in the same place.
        "game_db_mtime": ((merge_into or {}).get("game_db_mtime", 0)
                          if merge_into is not None
                          else (GAME.stat().st_mtime if GAME.exists() else 0)),
        # **The real key, with the mtime above kept as its fast path.** A
        # merge inherits it for the reason the mtime note gives at length:
        # a forty-row top-up has not re-observed the other 23,023 entries
        # against whatever database it happened to see, so claiming the
        # whole map matches is the dangerous direction. See `_valid`.
        "game_db_digest": ((merge_into or {}).get("game_db_digest", "")
                           if merge_into is not None
                           else (_game_db_digest() if GAME.exists() else "")),
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


@cache
def _game_db_digest() -> str:
    """A content digest of `data/game.db`, stable across identical rebuilds.

    **The key `game_db_mtime` should have been**, and it was wrong in both
    directions. It over-fired: `etl.build` has no time or random input and
    `compendium.sqlite` has not changed since 2026-09-18, so a rebuild with
    unchanged ETL produces byte-identical *rows* and still threw away a
    23,095-row recording that cost 1.3-2.8 hours -- which is how the map
    came to be void on the day this was written, with no way to clear it
    short of re-recording. And it under-fired: a database copied in with an
    older mtime passed.

    **Not a whole-file sha256**, though that is the cheapest thing here at
    15ms: SQLite's page layout is not stable across identical rebuilds --
    freelist pages, vacuum state and insertion order all move bytes that no
    row reads -- so a file hash has the same over-firing fault with a
    bigger constant.

    **Every table, not the `monster` columns `loader.spawn` reads**, which
    was the first design. The map records which rows execute which engine
    function, and that depends on far more than monster defences: a drawn
    party's items, feats and powers come out of `game.db` too, and
    `audit._attempts` stops as soon as a row fires, so the *number of
    boards played* is outcome-dependent on any of them. A 25-column
    hand-list is also the kind of thing that goes stale the first time a
    reader is added, and the whole point of this change is a key that
    cannot rot. Measured: 35 tables, 388ms against 38ms for `monster`
    alone -- and behind the mtime fast path in `_valid` it is paid once per
    rebuild rather than once per run.

    Canonical by construction: tables sorted, columns sorted, rows ordered
    by the full column tuple, so nothing about physical layout reaches the
    hash.
    """
    import hashlib
    import sqlite3

    digest = hashlib.sha256()
    con = sqlite3.connect(f"file:{GAME}?mode=ro", uri=True)
    try:
        tables = sorted(r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%'"))
        for table in tables:
            cols = sorted(r[1] for r in con.execute(f"PRAGMA table_info({table})"))
            digest.update(f"{table}:{','.join(cols)}\n".encode())
            picked = ", ".join(f'"{c}"' for c in cols)
            for row in con.execute(
                    f'SELECT {picked} FROM "{table}" ORDER BY {picked}'):
                digest.update(repr(row).encode())
    finally:
        con.close()
    return digest.hexdigest()


def _valid(got: dict) -> str:
    """"" if the map matches the current `data/game.db`, else why not.

    **One function, because `check._map_state` used to re-implement this and
    diverged.** That divergence is #1185: the map grew a void state that
    `check.py` did not know about, so a run printed the map's age and
    corpus as though it were narrowing while `_load` was refusing it. The
    rule in `scripts/CLAUDE.md` about a check that passes over its own
    subject matter is the same shape -- two readers of one fact is one
    reader too many.

    Reads mtime first and only then the digest, so the 388ms is paid on the
    run after a rebuild and never again: a digest that matches a moved
    mtime rewrites the stamp, which is sound because the stamp is the fast
    path for a question the digest has just answered properly.
    """
    if not GAME.exists():
        return ""
    when = GAME.stat().st_mtime
    if got.get("game_db_mtime", 0) >= when:
        return ""
    want = got.get("game_db_digest")
    if not want:
        # **A map recorded before this field existed cannot be checked**, so
        # it keeps the old blunt answer rather than being trusted on a key
        # it does not carry.
        return ("the map predates the current data/game.db and carries no"
                " content digest, so nothing can say whether the rebuild"
                " moved anything it saw")
    if want == _game_db_digest():
        got["game_db_mtime"] = when
        _restamp(got)
        return ""
    return ("data/game.db has been rebuilt and its contents moved, so every"
            " number the recording observed may have")


def _restamp(got: dict) -> None:
    """Persist a validated mtime so the next run takes the fast path.

    Atomic, and silent on failure: this is a cache warm-up rather than a
    result, and a map that cannot be rewritten is still a map that was just
    proven valid. The alternative is paying 388ms on every run forever
    after a rebuild, which is the kind of cost that gets a selector turned
    off.
    """
    try:
        tmp = MAP.with_suffix(".tmp")
        tmp.write_text(json.dumps(got))
        tmp.replace(MAP)
    except OSError:
        pass


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
    stale = _valid(got)
    if stale:
        print(f"# {stale}. Selecting everything.")
        return None
    at = got.get("recorded_at") or ""
    if at and not _in_history(at):
        print(f"# map was recorded at {at[:9]}, which is not in this tree's"
              f" history. Selecting everything.")
        return None
    seen = set(got.get("seen") or ())
    try:
        live_refs = set(declared_refs())
    except Exception:
        live_refs = set()        # cannot tell; the other guards speak
    if not seen:
        # **A map predating `seen` cannot say which rows it looked at**, so a
        # corpus that grew is indistinguishable from a recording that came
        # out short, and only the old blunt refusal is sound here.
        if live_refs and len(live_refs) != got.get("corpus"):
            print(f"# the corpus moved: {got.get('corpus')} rows when the map"
                  f" was recorded, {len(live_refs)} now, and this map does not"
                  f" say which rows it saw. Selecting everything.")
            return None
        return got
    # **A corpus that merely grew is not a reason to stop narrowing**, which
    # is what this guard used to do and what #925 is about. The map is a
    # complete answer for every row it did record; the only rows it cannot
    # speak for are the ones declared since, and those are *nameable*. So
    # they are unioned into every selection -- the treatment an engine file
    # absent from the map already gets -- instead of the whole corpus being
    # audited on their account.
    #
    # This matters because the condition is the normal consequence of any
    # content wave, so the old refusal meant every wave silently disabled
    # the map until somebody re-recorded the corpus, 1.3-2.8 hours.
    if live_refs:
        got["unrecorded"] = sorted(live_refs - seen)
        got["retired"] = sorted(seen - live_refs)
        if got["unrecorded"]:
            gap = got["unrecorded"]
            shown = ", ".join(gap[:6])
            more = "" if len(gap) <= 6 else f", and {len(gap) - 6} more"
            print(f"# {len(gap)} row(s) declared since the recording and never"
                  f" measured, so they are audited unconditionally rather than"
                  f" widening the run: {shown}{more}.")
            print(f"#   close the gap in seconds: `impact.py --record --refs"
                  f" '{','.join(gap[:40])}'`")
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
    rather than a hole -- the overnight wide sweep is its backstop -- and #865 is
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


#: How content spells a verb from each narrowable engine file. A copy of
#: `check.NARROWABLE`, not an import: `check` imports *this* module, so the
#: dependency only runs one way. Two files, deliberately -- the list is
#: short because the claim is strong, and a file absent from it keeps the
#: fail-closed answer.
VERB_PREFIX = {
    "src/combat_engine/engine/cast.py": "c.",
    "src/combat_engine/engine/query.py": "",
}


def _engine_names_it(name: str, rel: str) -> bool:
    """Does any **other** narrowable engine file name `name`?

    The one guard `audit._calls` cannot provide, because it searches
    *content* only. A verb that did not exist when the map was recorded
    cannot have an unchanged engine caller -- so an engine reference to it
    means a committed engine edit the map's entry for *that* caller is now
    stale about, and the rows naming the new verb are not the whole blast
    radius. Costs a read of two files and fires ~never for a verb added in
    the same commit as its callers.

    **A call or a quoted name, not the bare word**, and the difference was
    measured rather than guessed: a bare `\\bname\\b` search answered True
    for `Cast.resolve` because the English word "resolve" appears in
    `query.py`'s prose. That is the safe direction -- it falls back to WIDE
    -- but it would have refused the narrowing for every verb named with an
    ordinary word, which is most of them, so the branch would have been
    dead on arrival for exactly the verbs it is most useful on.

    A quoted form is included because this tree really does reach methods
    by name: `getattr(c, "shift")` and `setattr` both appear, and
    `impact.py`'s own blind-spot note is about that habit. What is left
    uncovered is an exotic indirection no file here uses.
    """
    short = re.escape(name.split(".")[-1])
    reaches = re.compile(rf"\b{short}\s*\(|[\"']{short}[\"']")
    for other in VERB_PREFIX:
        if other == rel:
            continue
        path = ROOT / other
        if path.exists() and reaches.search(path.read_text()):
            return True
    return False


def _existed_at(sha: str, rel: str, name: str) -> bool | None:
    """Did `name` exist in `rel` at `sha`? `None` if git cannot say.

    **The question `_moved_since` is a proxy for.** That function asks
    whether a function's text moved, and `selection` reads a move as "the
    map's silence is about a different function, so it says nothing". That
    is sound and coarse: it cannot tell a verb whose *meaning changed* from
    a verb that **did not exist** when the map was recorded, and those want
    opposite answers. A changed verb can move any row that reaches it. A
    verb that did not exist cannot have been reached by anything, so the
    rows that can possibly depend on it are exactly the rows that **name**
    it -- which is what `audit._calls` finds, in seconds, and what
    `CLAUDE.md` already prescribes as the evidence for a new verb.

    Measured on the live map before this was written: of 51 `cast.py`
    functions absent from the table, exactly **one** had moved since
    `recorded_at` -- and it was exactly the one that did not exist then
    (`Cast.stage`, 48 content call sites). So this branch is rare and
    precise rather than a loosening of a hot path.

    Parses the recorded blob rather than the working tree, through the same
    walk `_functions_of` uses, so a nested or class-scoped name is spelled
    the same way in both answers.
    """
    if not sha or not _in_history(sha):
        return None
    done = subprocess.run(["git", "show", f"{sha}:{rel}"],
                          cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        # The file itself did not exist at that sha, which is a definite
        # answer about the function and not a failure: a new engine module
        # is `check._rows_from_map`'s untracked-file case, already WIDE.
        return False
    try:
        tree = ast.parse(done.stdout)
    except SyntaxError:
        return None
    was: set[str] = set()

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                here = f"{prefix}{child.name}"
                was.add(here)
                walk(child, f"{here}.")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            else:
                walk(child, prefix)

    walk(tree, "")
    return name in was


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

    `None` means **select everything**, and every doubt returns it -- the
    five conditions this function owns are numbers 12 to 16 of the module
    docstring's list, which is the canonical one. `[]` means this instrument
    has no opinion, which is not the same thing, and the caller tells the
    two apart by a named verdict rather than by whether `notes` is empty:
    see `check.NARROWED`.
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
                    # **But a function that did not EXIST then is a
                    # different answer.** `_moved_since` cannot tell a verb
                    # whose meaning changed from one that is brand new, and
                    # those want opposite scopes: a changed verb can move
                    # any row that reaches it, where a new one can only
                    # reach a row that **names** it -- "a fact about the
                    # text", as `audit._calls`' own docstring puts it, and
                    # the evidence `CLAUDE.md` already prescribes for a new
                    # verb. Asking git costs one `git show`. #1194.
                    prefix = VERB_PREFIX.get(rel)
                    existed = _existed_at(got.get("recorded_at", ""), rel, name)
                    public = not name.split(".")[-1].startswith("_")
                    if (existed is False and prefix is not None and public
                            and not _engine_names_it(name, rel)):
                        import audit

                        named = audit._calls([f"{prefix}{name.split('.')[-1]}"])
                        notes.append(
                            f"# {rel}:{name} did not exist at"
                            f" {got.get('recorded_at', '')[:9]}, so nothing"
                            f" the map saw could reach it -- scope is the"
                            f" {len(named)} row(s) that NAME it.")
                        refs.update(named)
                        continue
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
    # **The rows the map has never measured, unioned in unconditionally.**
    # They appear in no function's ref list, and `selection` otherwise fails
    # *closed* on an absence -- "no row was observed to execute this, so no
    # row can depend on it" -- which is sound for a recorded corpus and
    # false for a row recorded by nobody. Without this the narrowing would
    # omit precisely the newest rows, which are the ones most likely broken.
    #
    # Added **after** the ceiling test on purpose: a two-row gap must not be
    # what tips a selection into WIDE, and the gap is small by construction
    # because `_load` prints the command that closes it. A gap big enough to
    # matter is a content wave, and `check._top_up_map` records up to 250
    # of them on the next clean run. #925.
    gap = sorted(set(got.get("unrecorded", ())) - refs)
    if gap:
        refs.update(gap)
        notes.append(f"# plus {len(gap)} row(s) the map has never measured,"
                     f" audited unconditionally rather than excluded")
    # A ref the map saw and the tree no longer declares cannot be audited.
    refs.difference_update(got.get("retired", ()))
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
    selection's documented blind spot, and the reason the overnight wide sweep
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
