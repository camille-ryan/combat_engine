#!/usr/bin/env python
"""What has been written, and what has not.

    uv run scripts/coverage.py
    uv run scripts/coverage.py --class fighter
    uv run scripts/coverage.py --monsters --max-level 3

The work list. Every row in `game.db` is either declared in `content/` or it
is not, and this prints the difference. There is no third state: a row that
cannot be written yet is simply not written, and shows up here until it is.

That is deliberate. The previous attempt let a row be declared empty with a
note explaining the absence, and ended up with 1,717 essays about missing
capabilities, 928 of them naming a blocker that had already been fixed. A
plain count of what is left needs no maintenance and cannot go stale.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from combat_engine.etl.build import game


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--class", dest="cls", help="only this class")
    ap.add_argument("--monsters", action="store_true", help="monsters instead of powers")
    ap.add_argument("--max-level", type=int, help="stop at this level")
    ap.add_argument("--list", action="store_true", help="print the undeclared refs")
    args = ap.parse_args()

    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    declared = set(REGISTRY)
    db = game()

    if args.monsters:
        rows = db.execute(
            "SELECT a.ref, m.level, m.role FROM monster_power a "
            "JOIN monster m ON m.ref = a.monster_ref "
            + ("WHERE m.level <= ? " if args.max_level else "")
            + "ORDER BY m.level, m.role, a.ref",
            (args.max_level,) if args.max_level else (),
        ).fetchall()
        _report(rows, declared, "level", "role", args.list)
    else:
        sql = "SELECT ref, class, level FROM power"
        where, params = [], []
        if args.cls:
            where.append("lower(class) = ?")
            params.append(args.cls.lower())
        if args.max_level:
            where.append("level <= ?")
            params.append(args.max_level)
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = db.execute(sql + " ORDER BY class, level, ref", params).fetchall()
        _report(rows, declared, "class", "level", args.list)
    return 0


def _report(rows, declared: set[str], a: str, b: str, show: bool) -> None:  # noqa: ANN001
    buckets: dict[tuple, list[tuple[str, bool]]] = defaultdict(list)
    for row in rows:
        buckets[(row[a], row[b])].append((row["ref"], row["ref"] in declared))

    total = done = 0
    width = max((len(f"{k[0]} {k[1]}") for k in buckets), default=10)
    for key in sorted(buckets, key=lambda k: (str(k[0]), k[1])):
        items = buckets[key]
        n = sum(1 for _, ok in items if ok)
        total += len(items)
        done += n
        bar = "#" * round(20 * n / len(items)) + "." * (20 - round(20 * n / len(items)))
        print(f"  {f'{key[0]} {key[1]}':<{width}}  {bar}  {n:4d}/{len(items):<4d}")
        if show:
            for ref, ok in items:
                if not ok:
                    print(f"      {ref}")
    share = done / total if total else 1.0
    print(f"\n  {done} of {total} declared ({share:.0%})")


if __name__ == "__main__":
    raise SystemExit(main())
