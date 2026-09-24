#!/usr/bin/env python
"""The edition-conversion table, beside what the books actually do.

    uv run scripts/mm3.py
    uv run scripts/mm3.py --role brute

Monster Manual 3 revised the monster maths, and `engine/monster_math.py`
carries the published formulas for the revision. Published formulas are a
design target; a book is what got printed. This prints one against the other
so the table gets tuned with evidence rather than argument.

Read the `diff` column. Where it is small the formula describes the corpus
and can be trusted. Where it is large, believe the corpus -- these are the
numbers your fights will actually be made of.
"""

from __future__ import annotations

import argparse
import re
import statistics
from collections import defaultdict

from combat_engine.engine.monster_math import LIMITED, MM3, NORMAL, OLD
from combat_engine.engine.rng import average
from combat_engine.etl.build import game

DICE = re.compile(r"(\d+d\d+(?:\s*\+\s*\d+)?)")
ATTACK = re.compile(r"([+-]\d+)\s*vs\.?\s*AC", re.I)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--role", help="only this role")
    args = ap.parse_args()

    db = game()
    damage = defaultdict(list)
    limited = defaultdict(list)
    attack = defaultdict(list)
    hp = defaultdict(list)

    rows = db.execute(
        "SELECT ref, level, role, rank, book, hp FROM monster "
        "WHERE level BETWEEN 1 AND 13 AND book != ''"
    ).fetchall()
    for row in rows:
        if args.role and row["role"] != args.role:
            continue
        hp[(row["book"], row["rank"])].append(row["hp"] / max(1, row["level"]))
        if row["rank"] != "standard":
            continue
        for a in db.execute(
            "SELECT usage, section, spec FROM monster_power "
            "WHERE monster_ref = ? ORDER BY idx",
            (row["ref"],),
        ):
            if a["section"] != "standard" or "damage" not in (a["spec"] or "").lower():
                continue
            dice = DICE.search(a["spec"])
            if not dice:
                continue
            into = limited if a["usage"] in ("recharge", "encounter") else damage
            into[(row["book"], row["level"])].append(average(dice.group(1).replace(" ", "")))
            if a["usage"] == "at-will":
                hit = ATTACK.search(a["spec"])
                if hit and row["role"]:
                    attack[(row["book"], row["role"])].append(
                        int(hit.group(1)) - row["level"]
                    )

    print("=== standard at-will damage ===")
    _damage(damage, NORMAL)
    print("\n=== recharge and encounter damage ===")
    _damage(limited, LIMITED)
    print("\n=== attack bonus over level, by role ===")
    _attack(attack)
    print("\n=== hit points per level, by rank ===")
    _hp(hp)
    print(
        "\nThe table lives in engine/monster_math.py. A large `diff` means the\n"
        "formula is not what got printed -- believe the corpus."
    )
    return 0


def _damage(seen: dict, kind: str) -> None:
    print(f"   {'lvl':>4}{'MM1 says':>11}{'formula':>9}{'diff':>7}"
          f"{'  |':>4}{'MM3 says':>10}{'formula':>9}{'diff':>7}")
    for level in range(1, 14):
        cells = []
        for book, table in (("MM1", OLD), ("MM3", MM3)):
            xs = seen.get((book, level), [])
            want = table.target(level, kind)
            if xs:
                got = statistics.mean(xs)
                cells.append(f"{got:>10.1f}{want:>9.1f}{got - want:>+7.1f}")
            else:
                cells.append(f"{'-':>10}{want:>9.1f}{'-':>7}")
        print(f"   {level:>4}{cells[0]}   |{cells[1]}")


def _attack(seen: dict) -> None:
    print(f"   {'role':<13}{'MM1 says':>10}{'formula':>9}{'  |':>4}"
          f"{'MM3 says':>10}{'formula':>9}")
    for role in sorted({r for _, r in seen}):
        cells = []
        for book, table in (("MM1", OLD), ("MM3", MM3)):
            xs = seen.get((book, role), [])
            want = table.attack.get(role, 5)
            cells.append(
                f"{statistics.mean(xs):>+10.1f}{want:>+9.0f}" if xs
                else f"{'-':>10}{want:>+9.0f}"
            )
        print(f"   {role:<13}{cells[0]}   |{cells[1]}")


def _hp(seen: dict) -> None:
    base = {b: statistics.mean(seen[(b, "standard")]) for b in ("MM1", "MM2", "MM3")
            if seen.get((b, "standard"))}
    print(f"   {'rank':<10}{'MM1 x':>9}{'formula':>9}{'  |':>4}{'MM3 x':>9}{'formula':>9}")
    for rank in ("standard", "elite", "solo", "minion"):
        cells = []
        for book, table in (("MM1", OLD), ("MM3", MM3)):
            xs = seen.get((book, rank), [])
            want = table.rank_hp.get(rank, 1.0)
            cells.append(
                f"{statistics.mean(xs) / base[book]:>9.1f}{want:>9.1f}"
                if xs and base.get(book) else f"{'-':>9}{want:>9.1f}"
            )
        print(f"   {rank:<10}{cells[0]}   |{cells[1]}")


if __name__ == "__main__":
    raise SystemExit(main())
