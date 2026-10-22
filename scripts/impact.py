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

#: Only these prefixes are narrowed. `etl/` and `chargen/` are deliberately
#: absent -- see the fail-open list in the module docstring.
NARROWABLE = ("src/combat_engine/engine/",)


def real_coverage():  # noqa: ANN201
    """Import the `coverage` package, not `scripts/coverage.py`.

    **`scripts/` shadows it and `scripts/` goes first on `sys.path`.** There
    is an unrelated instrument called `coverage.py` in this directory --
    written/not-written/half-written counts -- and `triage.py`, `refs.py` and
    `blocked.py` all put `scripts/` on the path. So a plain `import coverage`
    from inside an instrument gets the wrong module, silently, and it has a
    `main()` so it even looks plausible.

    Reaching past it with `PathFinder` alone does **not** work: the package's
    own `__init__` does `from coverage.control import ...`, which re-resolves
    `coverage` through the shadowed `sys.modules` entry and dies with
    "'coverage' is not a package". So the shadow has to come off the path and
    out of `sys.modules` for the duration of the import, and the caller's
    existing shadow object is preserved under another key rather than
    destroyed.
    """
    scripts = [p for p in sys.path if p.rstrip("/").endswith("scripts")]
    stashed = {k: v for k, v in sys.modules.items()
               if k == "coverage" or k.startswith("coverage.")}
    if stashed and getattr(stashed.get("coverage"), "__file__", "").endswith(
            "scripts/coverage.py"):
        for key in list(stashed):
            del sys.modules[key]
    else:
        stashed = {}
    for path in scripts:
        sys.path.remove(path)
    try:
        import coverage
        return coverage
    finally:
        sys.path[:0] = scripts
        for key, mod in stashed.items():
            sys.modules.setdefault(f"_shadowed_{key}", mod)


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


def record(sample: int = 0) -> int:
    """One sweep under coverage, labelling each row's work with its ref.

    `sample` records a deterministic slice instead of everything. A sampled
    map is **not** a smaller version of the real one -- a row it never saw is
    a row `--select` must select, so sampling makes selection wider, never
    wrong. It exists to prove the machinery in a minute rather than an hour,
    and `--stats` says which it is holding.
    """
    coverage = real_coverage()
    sys.path.insert(0, str(ROOT / "scripts"))
    import audit

    refs = audit._declared_refs() if hasattr(audit, "_declared_refs") else None
    if refs is None:
        from combat_engine.content import declared
        refs = sorted(declared())
    whole = len(refs)
    if sample:
        refs = refs[::max(1, whole // sample)][:sample]
    print(f"# recording {len(refs)} of {whole} rows under "
          f"coverage {coverage.__version__}")

    # One process, because a per-ref context has to be switched *inside* the
    # process doing the work and the pool's children are not ours to
    # instrument from here. Slower than the parallel sweep by roughly the
    # worker count -- this is a one-off whose output is reused.
    os.environ[RECORDING] = "1"
    data_file = ROOT / "logs" / ".impact-coverage"
    cov = coverage.Coverage(
        data_file=str(data_file),
        source=[str(ROOT / "src" / "combat_engine")],
        branch=False,
        concurrency="thread",
    )
    cov.start()
    started = time.time()
    done = 0
    try:
        for ref in refs:
            cov.switch_context(ref)
            try:
                audit.audit(ref)
            except Exception as exc:
                # A row that raises still recorded the work it did before
                # raising, which is the dependency we are after. The audit
                # itself is what reports raises; this must not.
                print(f"  {ref} raised {type(exc).__name__}", file=sys.stderr)
            done += 1
            if done % 200 == 0:
                rate = done / (time.time() - started)
                print(f"  {done}/{len(refs)}  {rate:.1f} rows/s", file=sys.stderr)
    finally:
        cov.stop()
        cov.save()
        os.environ.pop(RECORDING, None)

    return _build_map(cov, len(refs), whole)


def _build_map(cov, corpus: int, whole: int) -> int:  # noqa: ANN001
    """Turn per-ref line coverage into `{file: {function: refs | "wide"}}`."""
    data = cov.get_data()
    files = list(data.measured_files())
    print(f"# {len(files)} files measured, {len(data.measured_contexts())} contexts")

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

    ceiling = int(corpus * WIDE_SHARE)
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

    MAP.parent.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps({
        "corpus": corpus,
        "whole_corpus": whole,
        "sampled": corpus != whole,
        "ceiling": ceiling,
        "game_db_mtime": GAME.stat().st_mtime if GAME.exists() else 0,
        "recorded_at": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True).stdout.strip(),
        "files": out,
    }))
    print(f"# {narrow} functions carry a ref list, {wide} are wide "
          f"(> {ceiling} of {corpus} rows)")
    print(f"# written to {MAP.relative_to(ROOT)}")
    return 0


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
    return got


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


def select() -> int:
    """Print the refs a change needs audited, or `WIDE`."""
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

    narrowable = [f for f in changed if f.startswith(NARROWABLE)]
    other = [f for f in changed if f not in narrowable]
    if other:
        # Content, instruments, the ETL, chargen: all keep their present
        # behaviour. `audit.py --changed` already narrows content properly.
        print(f"# not narrowable here, deferring to audit.py --changed: "
              f"{', '.join(sorted(other))}")
    if not narrowable:
        print("# nothing under engine/ changed; this instrument has no opinion")
        return 0

    refs: set[str] = set()
    for rel in narrowable:
        table = got["files"].get(rel)
        if table is None:
            print(f"# {rel} is not in the map. WIDE.")
            print("WIDE")
            return 0
        funcs = _functions_of(ROOT / rel)
        touched = {_enclosing(funcs, line) for line in changed[rel]}
        if "" in touched:
            print(f"# {rel} changed outside any function (module level,"
                  f" a decorator or an import). WIDE.")
            print("WIDE")
            return 0
        for name in sorted(touched):
            entry = table.get(name)
            if entry is None:
                print(f"# {rel}:{name} was never executed by any row --"
                      f" no row can depend on it")
                continue
            if entry == "wide":
                print(f"# {rel}:{name} is reached by more than"
                      f" {got['ceiling']} rows. WIDE.")
                print("WIDE")
                return 0
            print(f"# {rel}:{name} -> {len(entry)} rows")
            refs.update(entry)

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
    ap.add_argument("--select", action="store_true", help="refs this change needs")
    ap.add_argument("--why", metavar="REF", help="what one row executes")
    ap.add_argument("--stats", action="store_true", help="what the map holds")
    args = ap.parse_args()
    if args.record:
        return record(args.sample)
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
