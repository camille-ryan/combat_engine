#!/usr/bin/env python
"""Do the rules tables in the tree still match the printed ones?

Two printed glossary tables have readers here, and the two are now at
different stages, which is why this file asks them different questions:

    combat_engine/dc.py        READS `rules_dc` -- 90 cells, no copy left
    story/module.py:COMPLEXITY a transcription -- 5 rows x 3 of 4 columns

Both were **correct on this check's first run** -- every one of the 95
numbers -- and both say in their own notes that an earlier draft was
*remembered* and wrong: "hard at level 4 is 21 and not 22", and a complexity
table that "assumed every primary check rolls at moderate" when the printed
shape escalates. So the risk this gate exists for was never a present error.
It is that **nothing could tell when one stopped being right.**

**The DC half has since been migrated rather than merely gated**, which is
the stronger of the two answers `#1001` set out: `combat_engine/dc.py` reads
the column, so the whole class of transcription error is gone instead of
watched. What is left to ask there is whether the *reader* returns what the
column holds -- see `_dc`, which is narrower and catches more than the
reconciliation it replaced.

**The complexity half is still a hand copy**, so it still gets the original
question. Migrating it is `story/`'s call and wants its own issue; until
then the reconciliation is what stops it drifting, in either direction.

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
    """`rules_dc` against what `combat_engine.dc.dc()` answers, all 90 cells.

    **The question moved one step out when the hand copy went away, and this
    is narrower and stronger than what it replaced.** It used to reconcile
    `story/dc.py:TABLE` against the column; `#949`/`#1001` moved the table to
    `combat_engine/dc.py`, which *reads* the column, so there is no
    transcription left to disagree with one -- and a check comparing a
    column against itself would be theatre.

    What is still worth asking is whether **the reader returns what the column
    holds**, which the old check could not see at all:

    * a band mis-mapped to a column -- `easy` and `hard` swapped reads as a
      working table and moves every DC in the campaign by eleven;
    * `BANDS` reordered without the ETL's columns following, which the
      module's own note warns about;
    * the 1-30 clamp, which is behaviour rather than data and had no gate;
    * a short table, which `#1001` records needing its own assertion because
      a lookup against three rows of thirty looks exactly like one against
      all of them.

    So this reads the column directly -- the one place a second opinion is
    still available -- and asks the reader for each cell.
    """
    from combat_engine.dc import BANDS, LEVELS, dc

    # **Keyed by the column's own name, never by position**, and that is the
    # difference between a check and a nuisance. The first draft compared
    # `dc(lvl, BANDS[i])` against the i'th column, which goes red when
    # `BANDS` is merely *reordered* -- and a reorder is harmless, because
    # `dc.py` uses the same tuple to name the columns it selects and to index
    # the row, so the two move together by construction. Asking by name keeps
    # that green and still catches the bug that matters: a `_table` whose
    # tuple order and whose `BANDS` order disagree, which hands back a
    # neighbouring band's number and reads as a working table.
    rows = {
        r["level"]: {band: r[band] for band in BANDS}
        for r in game().execute("SELECT * FROM rules_dc")
    }
    if not rows:
        out.append(
            "rules_dc is empty: the glossary's printing moved and the ETL "
            "refused to write a fragment. Fix `_rules_tables` -- this "
            "reconciliation cannot run without its reference."
        )
        return 1
    if len(rows) != LEVELS:
        out.append(f"rules_dc holds {len(rows)} levels, not {LEVELS}")
        return 1
    bad: list[str] = []
    for lvl in sorted(rows):
        for band in BANDS:
            try:
                got = dc(lvl, band)
            except Exception as exc:
                bad.append(f"dc({lvl}, {band!r}) raised {exc!r}")
                continue
            if got != rows[lvl][band]:
                bad.append(
                    f"dc({lvl}, {band!r}) answers {got}, the printed"
                    f" {band} column holds {rows[lvl][band]}"
                )
    # **The clamp is behaviour and gets asked about too.** A module may name a
    # level this engine does not play, and `dc` promises the nearest level the
    # table holds rather than a raise.
    for level, nearest in ((0, 1), (-3, 1), (31, LEVELS), (99, LEVELS)):
        for band in BANDS:
            if dc(level, band) != rows[nearest][band]:
                bad.append(
                    f"dc({level}, {band!r}) does not clamp to level {nearest}"
                )
    # And the band refusal, for #539's reason: a gate on a word nothing
    # carries reads exactly like a gate that works.
    #
    # **The message has to be the guard's own, and a plant is what established
    # that.** The first version accepted any `ValueError` and stayed green
    # when `dc`'s band check was replaced by `if False:` -- because
    # `BANDS.index('trivial')` raises `ValueError` of its own two lines
    # later. So the check passed while the guard was gone, which is exactly
    # the fault it was written to watch for, one level up. It now requires the
    # refusal to name the three bands, which only the guard does.
    try:
        got = dc(5, "trivial")
        bad.append(f"dc(5, 'trivial') returned {got} instead of raising")
    except ValueError as exc:
        if "not one of" not in str(exc):
            bad.append(
                f"dc(5, 'trivial') raised {exc!r}, which is not the band"
                f" guard's refusal -- `tuple.index` raises ValueError too, so"
                f" the guard may be gone"
            )
    except Exception as exc:
        bad.append(f"dc(5, 'trivial') raised {exc!r}, not a ValueError")
    for line in bad:
        out.append(line)
    if bad:
        out.append(
            "The printed column is the authority. Correct"
            " `combat_engine/dc.py` -- never this check -- and say which"
            " number moved."
        )
        return 1
    print(
        f"the DC reader reconciles: {len(rows)} levels x {len(BANDS)} bands,"
        f" {len(rows) * len(BANDS)} cells read back out of `rules_dc`,"
        f" plus the clamp and the band refusal"
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




#: The two printed condition names the engine spells differently or models
#: another way. Both were reconciled by hand once, 2026-10-30, and the
#: reasons are what make this a two-entry allow-list rather than a fudge:
#:
#: * **`removed from play` is the engine's `REMOVED`** -- the same state
#:   under a shorter name.
#: * **`hidden` is not a `Condition` and should not be**, which is the more
#:   interesting of the two. Hiding is **per observer**: a creature is
#:   hidden from some watchers and plain to others, and `query.hidden_from`
#:   models it as `Relation.HIDDEN_FROM` for exactly that reason. A flat
#:   condition could not express it, so the engine's representation is
#:   better than the printed list's and the mismatch is deliberate.
#:
#: An **allow-list**, so a *third* unmatched printed name is a finding. That
#: is the whole point: a re-import that adds a printed condition the engine
#: has never heard of currently looks identical to one that adds nothing.
CONDITION_SPELLINGS = {
    "removed from play": "REMOVED",
    "hidden": "a relation, not a condition -- query.hidden_from",
}


def _conditions(out: list[str]) -> int:
    """Does the engine know every condition the glossary prints? #1001.

    `#1001` measured 18 printed against 24 engine members and said the two
    readings -- "the engine invented a condition" and "the glossary omits
    six" -- were **indistinguishable** because nothing had reconciled them.
    Reconciled: all 18 are accounted for and the 24 are legitimate.

    **The asymmetry is the design.** Engine members the printed list does
    not name are *fine* -- `DEAD`, `MARKED`, `INSUBSTANTIAL`, `PINNED`,
    `SQUEEZING`, `SHAPED`, `CANNOT_SHIFT`, `REMOVED` are states this kernel
    needs and the printed condition list does not call conditions. A printed
    name with **no** engine member is the direction that matters, because
    that is a rule the engine cannot express at all.

    So this counts the extras and reports them, and fails only on an
    unmatched printed name that is not in `CONDITION_SPELLINGS`.
    """
    from combat_engine.engine.types import Condition

    rows = [
        str(r["name"]).strip().lower()
        for r in game().execute(
            "SELECT name FROM rules_condition")
    ] if _has_table("rules_condition") else []
    if not rows:
        out.append(
            "  the printed condition list reaches no column, so this"
            " reconciliation has nothing to read -- see #1001's remaining"
            " `rules_table` half. Reported, not failed: the column was never"
            " claimed to exist."
        )
        return 0
    forms: dict[str, set[str]] = {}
    for c in Condition:
        # Annotated, because the inferred `set[LiteralString]` is not
        # assignable to `forms`' declared `set[str]` -- the same erasure
        # `adjust_level`'s `world: object` was, pointed the other way.
        each: set[str] = {c.name.lower().replace("_", " ")}
        if isinstance(c.value, str):
            each.add(c.value.lower().replace("_", " "))
        forms[c.name] = each
    known = set().union(*forms.values()) if forms else set()
    missing = sorted(
        p for p in rows if p not in known and p not in CONDITION_SPELLINGS)
    extra = sorted(n for n, f in forms.items() if not (f & set(rows)))
    for name in missing:
        out.append(
            f"  the glossary prints the condition {name!r} and no `Condition`"
            f" member spells it -- a printed rule the engine cannot say. Add"
            f" the member, or an entry to `rules.CONDITION_SPELLINGS` saying"
            f" why not"
        )
    print(
        f"the condition vocabulary reconciles: {len(rows)} printed, "
        f"{len(forms)} in the engine, {len(missing)} printed names unmatched; "
        f"{len(extra)} engine members the printed list does not name, which "
        f"is expected -- see this file's note"
    )
    return 1 if missing else 0


def _has_table(name: str) -> bool:
    """Is that table in the built database?"""
    return bool(game().execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone())


def main() -> int:
    problems: list[str] = []
    bad = _dc(problems) | _complexity(problems) | _conditions(problems)
    for line in problems:
        print(line)
    return bad


if __name__ == "__main__":
    sys.exit(main())
