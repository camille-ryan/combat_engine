#!/usr/bin/env python
"""What has been written, what has not, and what is half-written on purpose.

    uv run scripts/coverage.py
    uv run scripts/coverage.py --class fighter
    uv run scripts/coverage.py --monsters --max-level 3
    uv run scripts/coverage.py --kind items
    uv run scripts/coverage.py --kind feats --class fighter
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

**The row counted is the row somebody writes.** For items that is the
`item_block` -- one Property or one Power -- and not the item: an item with
a property and a power is two jobs, either can be written without the
other, and counting items would call such a row half-done with nowhere to
say which half. For feats it is the `feat`, cards included, since a feat
that prints a whole power card is two declarations under two refs.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

from combat_engine.content import declared
from combat_engine.etl.build import game

#: Heroic is `tier` when the page printed one and `min_level` when it did
#: not -- 758 of the heroic feats print no tier line at all. `etl/feat.py`
#: argues it; this is the same clause its docstring gives.
HEROIC = "(tier = 'Heroic' OR (tier = '' AND min_level <= 10))"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--class", dest="cls", action="append", help="only this class; repeatable")
    ap.add_argument(
        "--kind",
        choices=("powers", "monsters", "items", "feats"),
        default="powers",
        help="what to count",
    )
    ap.add_argument("--monsters", action="store_true", help="alias for --kind monsters")
    ap.add_argument("--max-level", type=int, help="stop at this level")
    ap.add_argument(
        "--book",
        default="Player's Handbook",
        help="only powers printed in this book; empty string for any",
    )
    ap.add_argument(
        "--all-tiers",
        action="store_true",
        help="feats: paragon and epic as well, which are out of scope by default",
    )
    ap.add_argument("--list", action="store_true", help="print the undeclared refs")
    ap.add_argument("--partial", action="store_true",
                    help="print the declared-but-unfinished refs and what each wants")
    args = ap.parse_args()

    rows = declared()
    done = {ref for ref, p in rows.items() if not p.todo}
    partial = {ref: p.todo for ref, p in rows.items() if p.todo}
    db = game()

    kind = "monsters" if args.monsters else args.kind
    found, a, b = {
        "monsters": lambda: (_monsters(db, args), "level", "role"),
        "items": lambda: (_items(db, args), "category", "base_level"),
        "feats": lambda: (_feats(db, args), "gate", "min_level"),
        "powers": lambda: (_powers(db, args), "class", "level"),
    }[kind]()
    _report(found, done, partial, a, b, args)
    return 0


def _monsters(db, args: argparse.Namespace) -> list:  # noqa: ANN001
    # MM1-3 only. Everything else in the compendium is out of scope and
    # counting it would make the work look endless.
    where = ["m.book != ''"]
    params: list = []
    if args.max_level:
        where.append("m.level <= ?")
        params.append(args.max_level)
    return db.execute(
        "SELECT a.ref, m.level, m.role FROM monster_power a "
        "JOIN monster m ON m.ref = a.monster_ref WHERE "
        + " AND ".join(where)
        + " ORDER BY m.level, m.role, a.ref",
        params,
    ).fetchall()


def _powers(db, args: argparse.Namespace) -> list:  # noqa: ANN001
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
    return [
        r
        for r in db.execute(sql + " ORDER BY class, level, ref", params)
        if not args.book or args.book in json.loads(r["books"] or "[]")
    ]


def _items(db, args: argparse.Namespace) -> list:  # noqa: ANN001
    """Every Property and every Power, filed under the item it hangs off.

    `--book` is not applied here and there is no way to ask for it. Its
    default is the Player's Handbook, which prints no magic item at all, so
    honouring it would answer every question about items with nothing.
    """
    sql = (
        "SELECT b.ref, i.category, i.base_level FROM item_block b "
        "JOIN item i ON i.ref = b.item_ref"
    )
    params: list = []
    if args.max_level:
        sql += " WHERE i.base_level <= ?"
        params.append(args.max_level)
    return db.execute(sql + " ORDER BY i.category, i.base_level, b.ref", params).fetchall()


def _feats(db, args: argparse.Namespace) -> list[dict]:  # noqa: ANN001
    """Feats and their power cards, bucketed by what gates them.

    A card carries no prerequisite of its own -- the gate stays on the
    parent feat, which is why both share an `id` -- so it is filed under
    the parent's gate. Bucketing it on its own null gate would have put
    230 class feats in `general`.
    """
    gates = {
        r["id"]: _gate(r["prereq"])
        for r in db.execute("SELECT id, prereq FROM feat WHERE prereq IS NOT NULL")
    }
    sql = "SELECT ref, id, min_level FROM feat"
    if not args.all_tiers:
        sql += " WHERE " + HEROIC
    rows = [
        {"ref": r["ref"], "gate": gates.get(r["id"], "general"), "min_level": r["min_level"]}
        for r in db.execute(sql + " ORDER BY id, ref")
    ]
    if args.cls:
        wanted = {c.lower() for c in args.cls}
        rows = [r for r in rows if r["gate"] in wanted]
    return rows


def _gate(prereq: str | None) -> str:
    """Which shelf a feat sits on: a class, `race`, or `general`.

    Class outranks race, because a feat gated on both -- one race and any
    of three classes -- is a class feat that one race may also take, and
    filing it under race hides it from the class about to be written.
    `general` is the residue, so it also holds every gate the tree could
    not read; that is the honest place for them, since nothing about an
    opaque clause says whose feat it is.
    """
    leaves = list(_leaves(json.loads(prereq) if prereq else None))
    for leaf in leaves:
        if "class" in leaf:
            return leaf["class"]
    return "race" if any("race" in leaf for leaf in leaves) else "general"


def _leaves(node: dict | None):  # noqa: ANN202
    if not node:
        return
    for joiner in ("all", "any"):
        if joiner in node:
            for child in node[joiner]:
                yield from _leaves(child)
            return
    yield node


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
