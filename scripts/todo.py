#!/usr/bin/env python
"""Whether the unfinished rows are still telling the truth.

    uv run scripts/todo.py            the markers, and whether any has gone stale
    uv run scripts/todo.py --list     every marked row, not just the summary

A row that cannot be fully written is written anyway now, carrying
`todo=("c.deals()",)`. That is only safe while somebody is pushed to come
back, and "somebody will remember" is exactly the thing that failed before:
three level-5 rows sat blocked on `c.moving_as` for four levels after it was
built. So the pressure is mechanical, and there are two kinds of it, because
either alone has a hole you can park in forever.

**A named symbol now exists.** The day `c.deals` is built, the very next
`check.py` -- on somebody else's commit, about something else -- goes red,
and stays red until the waiting rows are finished. This is the one that
turns an engine method landing into content work landing.

**Markers stay under a tenth of the declared rows.** This is the part that
actually bites. Verb-existence alone lets a marker naming something nobody
will ever build sit invisible for good, and a wave that markers everything
it found hard would sail through. A budget cannot be satisfied by anything
except finishing rows, so a wave that marks more than it writes cannot land.

**Age is not checked.** The honest way would be the git blame of each
`todo=` line, and a `Power` does not record where it was written, so it
would mean re-parsing the tree to map lines back to refs and blaming
thousands of them -- slow, and wrong the moment a file is reformatted. Half
a check here would be worse than none, since it would read as covered. The
budget is the backstop instead.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from blocked import _one, _surface

#: Markers may not exceed this share of the declared rows. A tenth is
#: roughly one row in a class-sized batch of ten, which is the rate a wave
#: hits a genuine engine gap at; above that the wave is marking what it
#: found hard rather than what the engine cannot express.
BUDGET = 0.10


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--list", action="store_true", help="every marked row, with what it wants")
    args = ap.parse_args()

    sys.argv = sys.argv[:1]
    from combat_engine.content import declared

    rows = declared()
    marked = {ref: p.todo for ref, p in sorted(rows.items()) if p.todo}
    have = _surface()

    arrived: dict[str, list[str]] = defaultdict(list)
    for ref, todo in marked.items():
        for want in todo:
            if _one(want, have):
                arrived[want].append(ref)

    if args.list:
        for ref, todo in marked.items():
            print(f"  {ref:<10} wants {', '.join(todo)}")
        if marked:
            print()

    for want in sorted(arrived, key=lambda w: (-len(arrived[w]), w)):
        refs = arrived[want]
        shown = ", ".join(refs[:12]) + (f", … and {len(refs) - 12} more"
                                        if len(refs) > 12 else "")
        print(f"  ARRIVED {want} exists now; {len(refs)} row(s) still unfinished: {shown}")

    share = len(marked) / len(rows) if rows else 0.0
    print(f"\n  {len(marked)} unfinished of {len(rows)} declared "
          f"({share:.1%}, budget {BUDGET:.0%})")
    if not marked:
        print("  nothing is waiting on anything")
        return 0

    bad = 0
    if arrived:
        waiting = len({r for refs in arrived.values() for r in refs})
        print(f"  FAIL {len(arrived)} wanted symbol(s) exist now and "
              f"{waiting} row(s) have not been finished -- "
              f"uv run scripts/blocked.py --refs '<symbol>'")
        bad += 1
    if share > BUDGET:
        print(f"  FAIL markers are {share:.1%} of the tree, over the {BUDGET:.0%} budget "
              f"-- finish rows, do not mark more")
        bad += 1
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
