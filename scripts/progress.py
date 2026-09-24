#!/usr/bin/env python
"""How fast content is actually going in.

    uv run scripts/progress.py          record a reading and show the rate
    uv run scripts/progress.py --show   show the ledger without adding to it

`check.py --history` tracks what the *instruments* cost, because that was
the thing most likely to bloat. It turned out the instruments were fine and
nobody was measuring the part that takes the hours.

A reading is rows declared, by kind, with a timestamp. Rows only ever go up,
so the difference between two readings is work done and the time between
them is what it took -- including the engine fixes each wave provokes, which
is the honest denominator: a wave that reports six bugs is not free just
because the agent finished.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "logs" / "progress.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--show", action="store_true", help="do not add a reading")
    ap.add_argument("--note", default="", help="what just landed, e.g. 'level 8'")
    args = ap.parse_args()

    if not args.show:
        _record(args.note)
    _report()
    return 0


def _count() -> dict[str, int]:
    import sys

    sys.argv = sys.argv[:1]
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    powers = sum(1 for r in REGISTRY if not r.startswith("m"))
    monsters = len(REGISTRY) - powers
    return {"powers": powers, "monsters": monsters, "total": len(REGISTRY)}


def _record(note: str) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {"when": int(time.time()), "note": note, **_count()}
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def _report() -> None:
    if not LEDGER.exists():
        print("# no readings yet")
        return
    rows = [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]
    if len(rows) < 2:
        print(f"  {rows[-1]['total']} rows declared. One reading; no rate yet.")
        return

    print("  when     rows    added    over   rows/min  note")
    for before, after in zip(rows, rows[1:], strict=False):
        gained = after["total"] - before["total"]
        minutes = (after["when"] - before["when"]) / 60
        rate = gained / minutes if minutes else 0
        stamp = time.strftime("%H:%M", time.localtime(after["when"]))
        print(
            f"  {stamp}  {after['total']:5d}  +{gained:5d}  {minutes:5.0f}m"
            f"  {rate:8.1f}  {after['note']}"
        )

    first, last = rows[0], rows[-1]
    minutes = (last["when"] - first["when"]) / 60
    gained = last["total"] - first["total"]
    if minutes:
        print(
            f"\n  {gained} rows over {minutes:.0f}m — {gained / minutes:.1f}/min overall"
        )
        # The number worth knowing, because the remaining work is known.
        left = 4900 - gained
        if left > 0 and gained:
            print(
                f"  at that rate the {left} rows still named in the goal "
                f"are about {left / (gained / minutes) / 60:.0f}h of wall clock"
            )


if __name__ == "__main__":
    raise SystemExit(main())
