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
        choices=("powers", "monsters", "items", "feats", "features", "traits",
                 "traps", "companions", "all"),
        default="powers",
        help="what to count; `all` is the roll-up every plan should be built from",
    )
    ap.add_argument("--monsters", action="store_true", help="alias for --kind monsters")
    ap.add_argument("--max-level", type=int, help="stop at this level")
    ap.add_argument("--mm13", action="store_true",
                    help="monsters: only the three Monster Manuals, the old default")
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
    done = {ref for ref, p in rows.items() if not p.unfinished}
    partial = {ref: p.unfinished for ref, p in rows.items() if p.unfinished}
    db = game()

    kind = "monsters" if args.monsters else args.kind
    readers = {
        "monsters": lambda: (_monsters(db, args), "level", "role"),
        "items": lambda: (_items(db, args), "category", "base_level"),
        "feats": lambda: (_feats(db, args), "gate", "min_level"),
        "powers": lambda: (_powers(db, args), "class", "level"),
        "features": lambda: (_features(db, args), "class", "build"),
        "traits": lambda: (_traits(db, args), "race", "ord"),
        "traps": lambda: (_traps(db, args), "level", "role"),
        "companions": lambda: (_companions(db, args), "kind", "level"),
    }
    if kind == "all":
        return _roll_up(db, readers, done, partial, args)
    found, a, b = readers[kind]()
    _report(found, done, partial, a, b, args)
    print(f"  {_scope(kind, args, db)}")
    return 0


def _scope(kind: str, args: argparse.Namespace, db) -> str:  # noqa: ANN001
    """What the figure above was counted against.

    **Never a bare percentage**, and #308 established that for monsters only --
    the fix went into one branch of this function while `--book` quietly scoped
    the powers figure to a single book. It read `330 of 333 (99%)` where every
    book reads `4,024 of 4,254`, and I quoted the 99% in #345 as "character
    options are essentially done" on the strength of it. #357.
    """
    if kind == "monsters":
        every = db.execute("SELECT COUNT(*) FROM monster").fetchone()[0]
        mm13 = db.execute(
            "SELECT COUNT(*) FROM monster WHERE book != ''").fetchone()[0]
        if args.mm13:
            return (f"counting the three Monster Manuals -- "
                    f"{mm13} of {every} imported monsters")
        return (f"counting all {every} imported monsters; "
                f"--mm13 narrows to the {mm13} in the Monster Manuals")
    if kind == "powers":
        every = db.execute("SELECT COUNT(*) FROM power").fetchone()[0]
        if args.book:
            return (f"counting only powers printed in {args.book!r}; "
                    f'--book "" counts all {every}')
        return f"counting all {every} imported powers, every book"
    if kind == "feats":
        if args.all_tiers:
            return "counting every tier"
        return "counting heroic feats -- tier, or min_level <= 10 where none is printed"
    if kind == "items":
        return ("counting every Property and Power block; --book is not applied, "
                "see _items")
    if kind == "traits":
        return "counting every printed racial trait; new in #341"
    if kind == "traps":
        return "counting every imported trap and hazard"
    if kind == "companions":
        return "counting every familiar and beast companion"
    return "counting every class feature and sub-option"


def _roll_up(db, readers: dict, done: set[str],  # noqa: ANN001
             partial: dict, args: argparse.Namespace) -> int:
    """One line per kind, which is what an implementation plan is built from.

    Reading six commands to get these figures is how one of them gets
    forgotten -- and two of them (traps, companions) had no command at all,
    so 736 rows at 0% were in nobody's work list. #357.
    """
    print(f"  {'kind':12} {'written':>8} {'of':>7}   {'':4}  unfinished")
    tot = fin = unf = 0
    for kind in ("powers", "feats", "items", "features", "traits", "traps",
                 "companions", "monsters"):
        # The readers return `(rows, bucket_a, bucket_b)` for `_report`; the
        # roll-up wants only the rows.
        rows, _a, _b = readers[kind]()
        refs = [r["ref"] for r in rows]
        n = sum(1 for r in refs if r in done)
        part = sum(1 for r in refs if r in partial)
        tot += len(refs)
        fin += n
        unf += part
        pct = 100 * n / len(refs) if refs else 100.0
        print(f"  {kind:12} {n:8} {len(refs):7}   {pct:3.0f}%  {part:>6}")
    pct = 100 * fin / tot if tot else 100.0
    print(f"\n  {fin} of {tot} rows written ({pct:.0f}%), {unf} declared but "
          f"unfinished, {tot - fin - unf} not declared at all")
    # The powers line obeys `--book`, so say so here too rather than leaving the
    # roll-up to be read as the whole corpus when it is not.
    if args.book:
        print(f"  powers counted only for {args.book!r}; "
              f're-run with --book "" for every book')
    return 0


def _monsters(db, args: argparse.Namespace) -> list:  # noqa: ANN001
    # **Every imported source, not MM1-3.** This was `m.book != ''` with the
    # reasoning "everything else in the compendium is out of scope and counting it
    # would make the work look endless" -- which was sound about the work and wrong
    # about the reporting: it meant **630 of 3,130 imported monsters** were in the
    # denominator, so the line read `100%` while 2,500 monsters that `loader.pick`
    # can field were invisible to the only instrument that asks whether they are
    # written. #308.
    #
    # Camille's call, with the condition that the checks must not get slower. They
    # do not: this instrument reads `game.db` and the registry and **exercises
    # nothing** -- no board, no fight, no `take_turn` -- so a wider denominator is a
    # bigger SQL result and costs milliseconds. The ten-minute instrument is
    # `audit.py` and this does not touch it.
    #
    # `--mm13` keeps the old view, because scoping the *work* to MM1-3 is still a
    # reasonable plan; what was wrong was a percentage that did not say so.
    where = ["m.book != ''"] if args.mm13 else []
    params: list = []
    if args.max_level:
        where.append("m.level <= ?")
        params.append(args.max_level)
    # `WHERE` only when there is something to put after it: the scope is a flag now
    # and the unscoped form has no clauses at all.
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    return db.execute(
        "SELECT a.ref, m.level, m.role FROM monster_power a "
        "JOIN monster m ON m.ref = a.monster_ref"
        + clause
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


def _features(db, args: argparse.Namespace) -> list:  # noqa: ANN001
    """Every class feature and sub-option, bucketed by class and build.

    Had no mode at all until #357, so 290 rows sat outside the only
    instrument that asks whether a row is written -- and 148 of them are not.
    """
    sql = "SELECT ref, class, build FROM class_feature"
    params: list = []
    if args.cls:
        sql += " WHERE lower(class) IN (" + ",".join("?" * len(args.cls)) + ")"
        params.extend(c.lower() for c in args.cls)
    return [
        {"ref": r["ref"], "class": r["class"], "build": r["build"] or "-"}
        for r in db.execute(sql + " ORDER BY class, build, ref", params)
    ]


def _traits(db, args: argparse.Namespace) -> list:  # noqa: ANN001
    """Every printed racial trait. New in #341, so a low figure here is work
    that has only just become visible rather than work that regressed."""
    return [
        {"ref": r["ref"], "race": r["race"], "ord": r["ord"]}
        for r in db.execute(
            "SELECT ref, race, ord FROM racial_trait ORDER BY race, ord")
    ]


def _traps(db, args: argparse.Namespace) -> list:  # noqa: ANN001
    """Every trap and hazard. **0 of 631 are written**, and nothing said so.

    They were imported because `content/terrain.py` was inventing numbers off
    the monster curve for want of a row to read. Having imported them, the
    work list never learned they existed.
    """
    sql = "SELECT ref, role, level FROM trap"
    params: list = []
    if args.max_level:
        sql += " WHERE level <= ?"
        params.append(args.max_level)
    return [
        {"ref": r["ref"], "role": r["role"] or "-", "level": r["level"] or 0}
        for r in db.execute(sql + " ORDER BY level, role, ref", params)
    ]


def _companions(db, args: argparse.Namespace) -> list:  # noqa: ANN001
    """Every familiar and beast companion. **0 of 105 are written.**

    Imported because `c.familiar()` had been written against nothing.
    """
    return [
        {"ref": r["ref"], "kind": r["kind"] or "-", "level": 0}
        for r in db.execute("SELECT ref, kind FROM companion ORDER BY kind, ref")
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
