#!/usr/bin/env python
"""Do the hand-copied rules tables still match the printed ones?

Two modules in `story/` are transcriptions of printed glossary tables:

    story/dc.py:TABLE          level -> (easy, moderate, hard), 30 levels
    story/module.py:COMPLEXITY complexity -> (successes, moderate, hard), 5

Both are **correct today** -- this check's first run confirmed every one of
the 95 numbers -- and both say in their own notes that an earlier draft was
*remembered* and wrong: "hard at level 4 is 21 and not 22", and a complexity
table that "assumed every primary check rolls at moderate" when the printed
shape escalates. So the risk this gate exists for is not a present error. It
is that **nothing could tell when one stopped being right.**

`#1001` named that as the real prize and it is the reason this is a check
rather than a migration: switching `dc.py` to *read* the column is
`story/` work and a different component's call. Reconciling the two is not,
and it turns a staleness risk into a red line the moment they diverge --
which is the half that stops a silent fabrication, whichever direction the
divergence comes from.

**It fails if the table is absent, rather than passing.** A missing
`rules_dc` means the glossary's printing moved and `_rules_tables` refused
to write a fragment, and a reconciliation that skips itself when its
reference is gone is the "a check that runs on half its runs is not a
check" fault `scripts/CLAUDE.md` opens with.

**One printed column is deliberately not compared**: `advantages`. The
printed complexity table has four columns and `COMPLEXITY` keeps three, so
there is nothing in the tree to compare the fourth against -- it is stored
so the omission is visible and reported here as a count, not as a failure.
Whether a skill challenge should grant advantages is `story`'s question.
"""

from __future__ import annotations

import sys

from combat_engine.db import game


def _dc(out: list[str]) -> int:
    """`rules_dc` against `story.dc.TABLE`, all 30 levels."""
    from combat_engine.story.dc import BANDS, TABLE

    rows = {
        r["level"]: (r["easy"], r["moderate"], r["hard"])
        for r in game().execute("SELECT * FROM rules_dc")
    }
    if not rows:
        out.append(
            "rules_dc is empty: the glossary's printing moved and the ETL "
            "refused to write a fragment. Fix `_rules_tables` -- this "
            "reconciliation cannot run without its reference."
        )
        return 1
    if len(rows) != 30:
        out.append(f"rules_dc holds {len(rows)} levels, not 30")
        return 1
    bad = [
        (lvl, rows[lvl], TABLE.get(lvl))
        for lvl in sorted(rows)
        if rows[lvl] != TABLE.get(lvl)
    ]
    for lvl, printed, hand in bad:
        out.append(
            f"level {lvl}: printed {printed}, story/dc.py has {hand}"
        )
    missing = sorted(set(TABLE) - set(rows))
    if missing:
        out.append(f"story/dc.py holds levels the printed table does not: {missing}")
    if bad or missing:
        out.append(
            "The printed table is the authority. Correct `story/dc.py` -- "
            "never this check -- and say which number moved."
        )
        return 1
    print(
        f"the DC table reconciles: {len(rows)} levels x {len(BANDS)} bands, "
        f"90 numbers, printed and hand copy identical"
    )
    return 0


def _complexity(out: list[str]) -> int:
    """`rules_complexity` against `story.module.COMPLEXITY`, 3 of 4 columns."""
    from combat_engine.story.module import COMPLEXITY

    rows = {
        r["complexity"]: (r["successes"], r["moderate"], r["hard"], r["advantages"])
        for r in game().execute("SELECT * FROM rules_complexity")
    }
    if not rows:
        out.append(
            "rules_complexity is empty: the glossary's printing moved and "
            "the ETL refused to write a fragment. Fix `_rules_tables`."
        )
        return 1
    if len(rows) != 5:
        out.append(f"rules_complexity holds {len(rows)} rows, not 5")
        return 1
    bad = [
        (cx, rows[cx][:3], COMPLEXITY.get(cx))
        for cx in sorted(rows)
        if rows[cx][:3] != COMPLEXITY.get(cx)
    ]
    for cx, printed, hand in bad:
        out.append(
            f"complexity {cx}: printed {printed}, story/module.py has {hand}"
        )
    if bad:
        out.append(
            "The printed table is the authority. Correct "
            "`story/module.py:COMPLEXITY` -- never this check."
        )
        return 1
    held = sum(1 for cx in rows if rows[cx][3])
    print(
        f"the complexity table reconciles: {len(rows)} rows x 3 compared "
        f"columns, printed and hand copy identical"
    )
    print(
        f"  the printed `advantages` column is stored and compared against "
        f"nothing -- {held} of {len(rows)} rows print one and `COMPLEXITY` "
        f"keeps 3 of the 4 columns. Deliberate; see this file's note"
    )
    return 0


def main() -> int:
    problems: list[str] = []
    bad = _dc(problems) | _complexity(problems)
    for line in problems:
        print(line)
    return bad


if __name__ == "__main__":
    sys.exit(main())
