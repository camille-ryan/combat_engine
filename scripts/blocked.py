#!/usr/bin/env python
"""Rows left out of the tree, and what each is waiting for.

    uv run scripts/blocked.py           what is blocked, and what is ready now
    uv run scripts/blocked.py --ready   only the ones that have become writable

A row that cannot be written is left absent rather than half-written, and
`coverage.py` counts the hole. What nothing recorded was *why* — that lived
in the wave's report, which is ephemeral, and in an issue comment, which is
not queryable. So when a method was finally built, the rows that had been
waiting for it stayed missing until somebody happened to remember.

Three level-5 rows sat blocked on `c.moving_as` for four levels after it was
built, which is what this exists to stop.

The list is hand-maintained, because the reason a row was skipped is a
judgement a person made and no tool can recover it. Adding an entry is the
last step of leaving a row out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKED = ROOT / "docs" / "blocked.json"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ready", action="store_true", help="only what is now writable")
    args = ap.parse_args()

    if not BLOCKED.exists():
        print(f"# {BLOCKED.relative_to(ROOT)} does not exist yet")
        return 0

    entries = json.loads(BLOCKED.read_text())
    have = _surface()
    declared = _declared()

    ready, waiting, stale = [], [], []
    for ref, entry in sorted(entries.items()):
        wants = entry.get("wants", "")
        if ref in declared:
            stale.append((ref, wants))
        elif wants and _exists(wants, have):
            ready.append((ref, wants, entry.get("why", "")))
        else:
            waiting.append((ref, wants, entry.get("why", "")))

    for ref, wants, why in ready:
        print(f"  READY   {ref:<10} {wants} exists now — {why}")
    if not args.ready:
        for ref, wants, why in waiting:
            print(f"  blocked {ref:<10} {wants or '(no method named)'} — {why}")
        for ref, wants in stale:
            print(f"  written {ref:<10} was waiting on {wants}; drop it from the list")

    print(f"\n  {len(ready)} ready, {len(waiting)} still blocked, {len(stale)} to remove")
    return 0


def _surface() -> set[str]:
    """Everything a row can call, by name."""
    sys.argv = sys.argv[:1]
    from combat_engine.engine import cast as cast_mod
    from combat_engine.engine import events, query, triggers

    names = {f"c.{n}" for n in dir(cast_mod.Cast) if not n.startswith("_")}
    for mod, prefix in ((query, "query."), (triggers, ""), (events, "")):
        names |= {f"{prefix}{n}" for n in dir(mod) if not n.startswith("_")}
    return names


def _declared() -> set[str]:
    sys.argv = sys.argv[:1]
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    return set(REGISTRY)


def _exists(wants: str, have: set[str]) -> bool:
    """Is the named thing on the surface, *with* the parameter asked for?

    `c.no_provoke(mode=)` is not satisfied by `c.no_provoke` existing -- the
    row wanted the argument, and reporting it ready would send somebody to
    write a line that does not work. Checking the head alone called two
    rows ready that were not.
    """
    import inspect

    head, _, rest = wants.partition("(")
    head = head.strip()
    if head not in have:
        return False
    wanted = [p.strip().rstrip("=") for p in rest.rstrip(")").split(",") if p.strip()]
    if not wanted:
        return True
    if not head.startswith("c."):
        return True          # a field on an event; the name is all we can check
    from combat_engine.engine.cast import Cast

    fn = getattr(Cast, head[2:], None)
    if fn is None:
        return False
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return all(p in params for p in wanted)


if __name__ == "__main__":
    raise SystemExit(main())
