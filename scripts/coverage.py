#!/usr/bin/env python
"""What has been written, what has not, and what is half-written on purpose.

    uv run scripts/coverage.py
    uv run scripts/coverage.py --class fighter
    uv run scripts/coverage.py --monsters --max-level 3
    uv run scripts/coverage.py --partial          the rows that said what they lack

The work list. Every row in `game.db` is in one of three states:

* **done** -- declared in `content/`, with no `todo=`.
* **partial** -- declared, but carrying `todo=("c.deals()",)`: the author
  wrote what they could and named the symbols they wanted. `dsl.usable`
  refuses such a row, so it is exactly as inert in play as an absence.
* **absent** -- no row at all, because there was nothing to decorate.

There used to be no third state, and the reason was sound: the attempt
before this one let a row be declared empty with a note explaining the
absence, and ended up with 1,717 essays about missing capabilities, 928 of
them naming a blocker that had already been fixed. What broke that argument
is items and feats -- four thousand rows against an engine that has never
met either, where the absences are the majority and the reason for each
would live nowhere.

So a partial row is allowed, and **it never rolls into done**. The
percentage printed is done over total; partial is counted beside it and
listed by name, so the only way to move the number is to finish the row.
`scripts/todo.py` fails the build if the markers outgrow their budget or if
one of them is waiting on something that now exists.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

from combat_engine.content import declared
from combat_engine.etl.build import game


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--class", dest="cls", action="append", help="only this class; repeatable")
    ap.add_argument("--monsters", action="store_true", help="monsters instead of powers")
    ap.add_argument("--max-level", type=int, help="stop at this level")
    ap.add_argument(
        "--book",
        default="Player's Handbook",
        help="only powers printed in this book; empty string for any",
    )
    ap.add_argument("--list", action="store_true", help="print the undeclared refs")
    ap.add_argument("--partial", action="store_true",
                    help="print the declared-but-unfinished refs and what each wants")
    args = ap.parse_args()

    rows = declared()
    done = {ref for ref, p in rows.items() if not p.todo}
    partial = {ref: p.todo for ref, p in rows.items() if p.todo}
    db = game()

    if args.monsters:
        # MM1-3 only. Everything else in the compendium is out of scope and
        # counting it would make the work look endless.
        where = ["m.book != ''"]
        params: list = []
        if args.max_level:
            where.append("m.level <= ?")
            params.append(args.max_level)
        found = db.execute(
            "SELECT a.ref, m.level, m.role FROM monster_power a "
            "JOIN monster m ON m.ref = a.monster_ref WHERE "
            + " AND ".join(where)
            + " ORDER BY m.level, m.role, a.ref",
            params,
        ).fetchall()
        _report(found, done, partial, "level", "role", args)
    else:
        sql = "SELECT ref, class, level, books FROM power"
        where, params = [], []
        if args.cls:
            where.append("lower(class) IN (" + ",".join("?" * len(args.cls)) + ")")
            params.extend(c.lower() for c in args.cls)
        if args.max_level:
            where.append("level <= ?")
            params.append(args.max_level)
        if where:
            sql += " WHERE " + " AND ".join(where)
        found = [
            r
            for r in db.execute(sql + " ORDER BY class, level, ref", params)
            if not args.book or args.book in json.loads(r["books"] or "[]")
        ]
        _report(found, done, partial, "class", "level", args)
    return 0


def _report(rows, done: set[str], partial: dict[str, tuple[str, ...]],  # noqa: ANN001
            a: str, b: str, args: argparse.Namespace) -> None:
    buckets: dict[tuple, list[str]] = defaultdict(list)
    for row in rows:
        buckets[(row[a], row[b])].append(row["ref"])

    total = finished = unfinished = 0
    width = max((len(f"{k[0]} {k[1]}") for k in buckets), default=10)
    for key in sorted(buckets, key=lambda k: (str(k[0]), k[1])):
        items = buckets[key]
        n = sum(1 for ref in items if ref in done)
        part = [ref for ref in items if ref in partial]
        total += len(items)
        finished += n
        unfinished += len(part)
        bar = "#" * round(20 * n / len(items)) + "." * (20 - round(20 * n / len(items)))
        note = f"  +{len(part)} partial" if part else ""
        print(f"  {f'{key[0]} {key[1]}':<{width}}  {bar}  {n:4d}/{len(items):<4d}{note}")
        if args.list:
            for ref in items:
                if ref not in done and ref not in partial:
                    print(f"      {ref}")
        if args.partial:
            for ref in part:
                print(f"      {ref:<10} wants {', '.join(partial[ref])}")
    share = finished / total if total else 1.0
    print(f"\n  {finished} of {total} declared ({share:.0%})")
    if unfinished:
        # Said apart, and never folded into the percentage: a marker that
        # could move the number would be a way to finish a class by
        # declaring that you had not.
        print(f"  {unfinished} more declared but unfinished -- see --partial")


if __name__ == "__main__":
    raise SystemExit(main())
