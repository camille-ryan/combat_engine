#!/usr/bin/env python
"""What to hand somebody who is about to write a power.

    uv run scripts/spec.py p289              one power
    uv run scripts/spec.py m145              a monster: its numbers, then each ability
    uv run scripts/spec.py --class fighter --level 1
    uv run scripts/spec.py --monsters 1 --role brute
    uv run scripts/spec.py --class rogue --level 1 --all

By default only rows that have **not** been declared yet come out, so the
output is a work list rather than a catalogue.

What comes out is the mechanical lines and nothing else. No name, no flavour
text, and no self-reference: a stat block that names itself in its own rules
says "contracts m145 filth fever" here instead. The author writes the function
without ever learning what the row is called, which is the arrangement that
keeps the engine free of a publisher's prose.
"""

from __future__ import annotations

import argparse
import json
import sys

from combat_engine.etl.build import game


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("refs", nargs="*", help="power or monster ids, e.g. p289 m145")
    ap.add_argument("--class", dest="cls", help="any of the eight PHB1 classes")
    ap.add_argument(
        "--level",
        type=int,
        action="append",
        help="power level; repeatable, because a class's level 0 and level 1 "
        "belong in one brief and two runs concatenated end with a spurious "
        "'nothing to write' that two agents in a row reported as a lie",
    )
    ap.add_argument("--monsters", type=int, help="every monster at this level")
    ap.add_argument("--role", help="narrow --monsters to one role")
    ap.add_argument(
        "--book",
        default="Player's Handbook",
        help="only powers printed in this book; empty string for any",
    )
    ap.add_argument(
        "--features",
        action="store_true",
        help="the class features of --class, which live on the class page",
    )
    ap.add_argument("--all", action="store_true", help="include rows already declared")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many rows")
    args = ap.parse_args()

    db = game()
    declared = _declared()

    if args.features:
        return _features(db, args.cls)

    refs: list[str] = list(args.refs)
    if args.cls or args.level:
        refs += _powers(db, args.cls, args.level, args.book)
    if args.monsters is not None:
        refs += _monsters(db, args.monsters, args.role)
    if not refs:
        # Only help when nothing was *asked*. Filters that match nothing
        # used to print usage too, which reads as "you typed it wrong"
        # -- and the commonest cause is the book filter, which defaults
        # to the Player's Handbook and so silently empties any query
        # about a class printed in a later book.
        if args.cls or args.level or args.monsters is not None:
            print(
                "# nothing matched those filters."
                + (f"  --book {args.book!r} excludes later books; try --book ''"
                   if args.book else ""),
                file=sys.stderr,
            )
            return 1
        ap.print_help()
        return 1

    shown = 0
    for ref in refs:
        if not args.all and ref in declared:
            continue
        block = _render(db, ref, declared, args.all)
        if block is None:
            print(f"# {ref}: no such row", file=sys.stderr)
            continue
        print(block)
        print()
        shown += 1
        if args.limit and shown >= args.limit:
            break

    if shown == 0:
        print("# nothing to write -- every row asked for is already declared")
    return 0


def _features(db, cls: str | None) -> int:  # noqa: ANN001
    """Every class feature's printed text, which nothing could ask for.

    The features were never imported -- `class` carried the chassis
    numbers and nothing else -- so `spec.py` answered "no such row" for
    every `cf:` ref, and each one read as a feature with no printed text
    rather than one nobody had loaded. What got written instead was the
    paraphrase in `docs/blocked.json`, or a guess.

    Listed per class rather than per ref because the tree's `cf:` refs are
    hand-chosen descriptions and these are numbered by page order; the two
    are matched by reading, which is the point.
    """
    rows = db.execute(
        "SELECT ref, class, build, spec FROM class_feature"
        + (" WHERE lower(class)=?" if cls else "")
        + " ORDER BY class, build, ord",
        (cls.lower(),) if cls else (),
    ).fetchall()
    if not rows:
        print(f"# no class features for {cls or 'any class'}", file=sys.stderr)
        return 1
    for row in rows:
        build = f" ({row['build']})" if row["build"] else ""
        print(f"### {row['ref']}   {row['class']}{build}")
        print(row["spec"])
        print()
    return 0


def _declared() -> set[str]:
    from combat_engine.content import declared

    return set(declared())


def _powers(db, cls: str | None, levels: list[int] | None, book: str = "") -> list[str]:  # noqa: ANN001
    """Powers matching the filters, in a stable order.

    `book` is a membership test rather than a LIKE: `Source` is a
    comma-separated list and a row often names five books, so matching by
    substring picks up everything.
    """
    import json

    where, params = [], []
    if cls:
        where.append("lower(class) = ?")
        params.append(cls.lower())
    if levels:
        where.append("level IN (" + ",".join("?" * len(levels)) + ")")
        params.extend(levels)
    sql = "SELECT ref, books FROM power"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY class, level, ref"
    return [
        r["ref"]
        for r in db.execute(sql, params)
        if not book or book in json.loads(r["books"] or "[]")
    ]


def _monsters(db, level: int, role: str | None, book: bool = True) -> list[str]:  # noqa: ANN001
    """Monsters at a level. Monster Manual 1 to 3 only, which is the scope."""
    sql = "SELECT ref FROM monster WHERE level = ?"
    params: list = [level]
    if book:
        sql += " AND book != ''"
    if role:
        sql += " AND role = ?"
        params.append(role)
    return [r["ref"] for r in db.execute(sql + " ORDER BY ref", params)]


def _render(db, ref: str, declared: set[str], include_all: bool) -> str | None:  # noqa: ANN001
    if ref.startswith("comp:"):
        row = db.execute("SELECT * FROM companion WHERE ref = ?", (ref,)).fetchone()
        if row is None:
            return None
        return f"### {row['ref']}   {row['kind']}\n{row['spec']}"
    if ref.startswith("cf:"):
        row = db.execute(
            "SELECT * FROM class_feature WHERE ref = ?", (ref,)
        ).fetchone()
        if row is None:
            return None
        build = f" ({row['build']})" if row["build"] else ""
        return f"### {row['ref']}   {row['class']}{build}\n{row['spec']}"
    if ref.startswith("p"):
        row = db.execute("SELECT * FROM power WHERE ref = ?", (ref,)).fetchone()
        if row is None:
            return None
        head = (
            f"### {row['ref']}   {row['class']} level {row['level']}   "
            f"{row['usage']} / {row['action']}"
        )
        kw = json.loads(row["keywords"] or "[]")
        if kw:
            head += f"   keywords: {', '.join(kw)}"
        return f"{head}\n{row['spec']}"

    if ref.startswith("m"):
        row = db.execute("SELECT * FROM monster WHERE ref = ?", (ref,)).fetchone()
        if row is None:
            return None
        out = [_stat_block(row)]
        for a in db.execute(
            "SELECT * FROM monster_power WHERE monster_ref = ? ORDER BY idx", (ref,)
        ):
            if not include_all and a["ref"] in declared:
                continue
            kw = json.loads(a["keywords"] or "[]")
            head = (
                f"--- {a['ref']}   {a['section']} / {a['action']} / {a['usage']}"
                + (f" / recharge {a['recharge']}+" if a["recharge"] else "")
                + (f"   keywords: {', '.join(kw)}" if kw else "")
            )
            out.append(f"{head}\n{a['spec']}")
        return "\n\n".join(out)

    return None


def _stat_block(row) -> str:  # noqa: ANN001
    """The numbers, which are loaded from the database and never hand-written.

    Printed here only so whoever is writing the abilities can see what they
    are working with -- an attack line that reads `+6 vs. AC` makes more sense
    beside a Strength of 14.
    """
    scores = json.loads(row["scores"] or "{}")
    modes = json.loads(row["modes"] or "{}")
    tags = [t for t in (row["role"], row["size"], row["origin"], row["kind"]) if t]
    for flag in ("minion", "elite", "solo", "leader"):
        if row[flag]:
            tags.append(flag)
    lines = [
        f"### {row['ref']}   level {row['level']}   {', '.join(tags)}",
        f"HP {row['hp']}   AC {row['ac']}  Fort {row['fort']}  "
        f"Ref {row['ref_def']}  Will {row['will']}   Init {row['initiative']:+d}",
        f"Speed {row['speed']}"
        + (f" ({', '.join(f'{k} {v}' for k, v in modes.items())})" if modes else ""),
        "  ".join(f"{k.title()} {v}" for k, v in scores.items()),
    ]
    for label, key in (("Resist", "resist"), ("Vulnerable", "vulnerable")):
        values = json.loads(row[key] or "{}")
        if values:
            lines.append(f"{label} " + ", ".join(f"{v} {k}" for k, v in values.items()))
    immune = json.loads(row["immune"] or "[]")
    if immune:
        lines.append("Immune " + ", ".join(immune))
    lines.append("(these numbers load from game.db -- do not hand-write them)")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
