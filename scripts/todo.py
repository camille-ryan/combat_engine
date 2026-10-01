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

**There was a second pressure and it has been removed.** Markers had to stay
under a tenth of the declared rows. The share is still printed below, because
it is worth knowing; it is no longer a gate. Three measurements retired it and
they are kept here so it is not reinstated by someone who only remembers that
it existed:

* **It was red in 43 of 66 recorded runs** -- 65%, against 23% for the next
  worst instrument -- and green for the last time four days before it went.
  `logs/instruments.jsonl` holds that. A check that is nearly always red is a
  check nobody reads, which is the exact failure `check.py --history` exists
  to surface.
* **Closing the gap meant 294 rows**, at a measured exchange rate of 30 rows
  per 0.3 points (#230). A gate that cannot be cleared by any one session's
  work is not applying pressure, it is just on.
* **It paid for silence.** This is the one that settles it. The denominator is
  the *declared* rows, so a row written honestly with a marker moves the share
  from 12.4048% to 12.4119% -- worse -- while **not writing that row at all
  leaves it untouched**. The cheapest way to satisfy the budget was always to
  leave the row out of the tree, where no instrument here can see it. It was
  rewarding the opposite of what it was installed to encourage.

So this is the check's *definition* being wrong rather than the tree being
wrong, which is the branch `scripts/CLAUDE.md` demands be named out loud. The
volume of markers was never the thing worth gating: a half-written compendium
honestly marked is what this project looks like mid-flight. **Staleness** is
the thing worth gating, and that is the check above, which stays.

No ratchet replaced it, and deliberately: "markers must not increase" has the
same flaw as "markers must stay under a tenth", because any gate that counts
markers charges a row for being declared and charges nothing for being absent.
`coverage.py` is what sees an absent row; `blocked.py --group` is the work
queue.

**A narrative clause is not a marker and is still listed here.** `narrative=
("skill:thievery",)` says a clause has no combat meaning rather than that the
engine is missing something, so it is counted done and never goes red -- and a
field that is invisible is worse than the `dropped=` it replaced, because the
way to make an awkward clause disappear must not be quieter than the way to
declare it. So the rows are named below the budget line, under the skill each
one narrows, where a reader of this page walks past them.

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


def _narrative(rows: dict) -> None:
    """Every row declaring a clause narrative, named, under its skill.

    Named and not counted: a count is a number that only ever goes up and
    nobody reads a number. The refs are what lets somebody ask whether
    `skill:perception` is being used for genuinely narrative circumstances
    or as a place to put whichever clause was awkward that day.
    """
    by_skill: dict[str, list[str]] = defaultdict(list)
    for ref, p in sorted(rows.items()):
        for clause in p.narrative:
            by_skill[clause].append(ref)
    if not by_skill:
        return
    total = len({r for refs in by_skill.values() for r in refs})
    print(f"  {total} row(s) declare a clause narrative -- counted done, "
          f"never red, and audited like any other row:")
    for clause in sorted(by_skill, key=lambda s: (-len(by_skill[s]), s)):
        print(f"    {clause:<20} {' '.join(by_skill[clause])}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--list", action="store_true", help="every marked row, with what it wants")
    args = ap.parse_args()

    sys.argv = sys.argv[:1]
    from combat_engine.content import declared

    rows = declared()
    marked = {
        ref: p.unfinished for ref, p in sorted(rows.items()) if p.unfinished
    }
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
    print(f"\n  {len(marked)} unfinished of {len(rows)} declared ({share:.1%})")
    _narrative(rows)
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
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
