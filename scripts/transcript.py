#!/usr/bin/env python
"""Read a fight back off disk.

    uv run scripts/transcript.py                 the most recent one
    uv run scripts/transcript.py --list          what is on disk
    uv run scripts/transcript.py <id>            one by name
    uv run scripts/transcript.py --moves         only who went where
    uv run scripts/transcript.py --actor c:rogue only one creature

Every web session writes one to `logs/`, starting with its setup line, so a
fight can be read after the tab is closed -- and re-run, since the seed is
in the header and combat holds no randomness beyond it.

Names are applied here, at the edge, the same way the API applies them. The
file itself holds ids only, so it is readable without a localisation table
and cannot carry a printed name into the repository.
"""

from __future__ import annotations

import argparse
import sys

from combat_engine.transcript import LOGS, read

#: Events that are bookkeeping rather than fight. Hidden unless asked for.
NOISE = {
    "LeaveSquare", "EnterSquare", "AdjacencyGained", "AdjacencyLost",
    "RelationSet", "RelationCleared", "MoveStart", "MoveEnd",
}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("which", nargs="?", help="a transcript id; default is the newest")
    ap.add_argument("--list", action="store_true", help="what is on disk")
    ap.add_argument("--moves", action="store_true", help="only movement")
    ap.add_argument("--actor", help="only this creature, by ref or wire id")
    ap.add_argument("--all", action="store_true", help="include the bookkeeping")
    ap.add_argument("--names", action="store_true", help="apply printed names")
    args = ap.parse_args()

    files = sorted(LOGS.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if args.list:
        for f in files:
            head, events = read(f)
            print(f"  {f.stem}  seed {head.get('seed')}  level {head.get('level')}  "
                  f"{len(events)} events")
        if not files:
            print("# nothing in logs/ yet -- play a session and it will be here")
        return 0

    path = (LOGS / f"{args.which}.jsonl") if args.which else (files[0] if files else None)
    if path is None or not path.exists():
        print("# no such transcript. --list shows what is on disk", file=sys.stderr)
        return 1

    head, events = read(path)
    print(f"# {path.stem}   seed {head.get('seed')}   level {head.get('level')}   "
          f"scaling {head.get('scaling')}")
    print(f"#   {' '.join(head.get('pcs', []))}  vs  {' '.join(head.get('enemies', []))}")
    print(f"#   re-run: uv run scripts/fight.py --seed {head.get('seed')} "
          f"--level {head.get('level')}\n")

    label = _namer() if args.names else (lambda x: x)
    for ev in events:
        kind = ev.get("kind", "?")
        if args.moves and kind != "Moved":
            continue
        if not args.all and not args.moves and kind in NOISE:
            continue
        if args.actor and args.actor not in _who(ev):
            continue
        body = {
            k: v for k, v in ev.items() if k not in ("kind", "seq", "depth", "cancelled")
        }
        indent = "  " * min(int(ev.get("depth", 0)), 6)
        print(f"{ev.get('seq', 0):5} {indent}{label(kind)} "
              + " ".join(f"{k}={label(str(v))}" for k, v in body.items()))
    return 0


def _who(ev: dict) -> str:
    """Every creature this event mentions, as one string to search."""
    return " ".join(
        str(ev.get(k, "")) for k in ("actor", "attacker", "source", "target", "other")
    )


def _namer():  # noqa: ANN202
    """Printed names, if this clone has them. Ids otherwise."""
    from combat_engine.etl.build import localisation

    table = localisation()

    def label(text: str) -> str:
        entry = table.get(text)
        return (entry or {}).get("name") or text

    return label


if __name__ == "__main__":
    raise SystemExit(main())
