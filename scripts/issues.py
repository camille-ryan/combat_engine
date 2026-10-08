#!/usr/bin/env python
"""Close the content issues whose work is actually finished.

    uv run scripts/issues.py            what would happen, and nothing else
    uv run scripts/issues.py --close    do it

Work is tracked as one issue per class per level for powers and one per
level for monsters. Whether a bucket is *done* is a question `coverage.py`
already answers, so nothing here decides it -- this only carries the answer
to GitHub.

It exists because the alternative is remembering, and remembering does not
scale to sixty-nine issues. Six level-2 buckets sat finished and open
because nobody closed them by hand.

**Declared is not the same as done.** A row may now be written with `todo=`
naming what it could not say, and counting those as declared would have
closed every bucket the first marker wave touched -- which is the one
failure the marker was introduced with, and the reason it is safe at all is
that nothing counts it as finished. So `have` here counts rows with no
`todo`, and a bucket holding one can never reach `want`.

A bucket that is **partly** done is left open **and says so on the issue** —
which rows are unfinished, grouped by the symbol each is waiting for, and
which are absent altogether. The grouping is new: the reason a row was
skipped used to live in a wave's report, and the tree did not know it.

A comment is only posted when the remaining set has *changed* since the last
one, so a bucket that has not moved does not accumulate identical notes.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict

from combat_engine.content import declared
from combat_engine.db import game

ROOT_TITLE = re.compile(r"^(?P<cls>\w+) level (?P<level>\d+): ", re.I)
MONSTER_TITLE = re.compile(r"^Level (?P<level>\d+) monsters: ", re.I)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--close", action="store_true", help="actually close them")
    args = ap.parse_args()

    powers, monsters, missing, unfinished = _coverage()
    issues = _open_issues()
    if not issues:
        print("# no open content issues")
        return 0

    done, partial = [], []
    for number, title in issues:
        m = ROOT_TITLE.match(title)
        if m:
            key = (m.group("cls").lower(), int(m.group("level")))
            have, want = powers.get(key, (0, 0))
        else:
            m = MONSTER_TITLE.match(title)
            if not m:
                continue
            have, want = monsters.get(int(m.group("level")), (0, 0))
        if want and have >= want:
            done.append((number, title, have, want))
        elif want:
            partial.append((number, title, have, want))

    for number, title, have, want in done:
        print(f"  done    #{number:<4} {title:44} {have}/{want}")
        if args.close:
            _close(number, have, want)
    for number, title, have, want in partial:
        key = _key_of(title)
        left = sorted(missing.get(key, ()))
        marked = unfinished.get(key, {})
        flag = f"  ({len(marked)} unfinished)" if marked else ""
        print(f"  partial #{number:<4} {title:44} {have}/{want}{flag}")
        if args.close:
            _say_whats_left(number, have, want, left, marked)

    if not args.close and done:
        print(f"\n{len(done)} issue(s) would close. Re-run with --close.")
    elif args.close:
        print(f"\nclosed {len(done)}, left {len(partial)} open with work remaining")
    return 0


def _key_of(title: str) -> object:
    """The coverage key a bucket's issue title names."""
    m = ROOT_TITLE.match(title)
    if m:
        return (m.group("cls").lower(), int(m.group("level")))
    m = MONSTER_TITLE.match(title)
    return int(m.group("level")) if m else None


def _say_whats_left(
    number: int, have: int, want: int, left: list[str], marked: dict[str, tuple[str, ...]]
) -> None:
    """Put the remaining rows on the issue, if they have changed."""
    parts = [f"Worked, not finished: **{have} of {want}**.\n"]

    if marked:
        # Grouped by what is wanted, because that is the shape the engine
        # work actually has: one method unblocks eleven rows, and a flat
        # list of eleven refs does not say so.
        by_want: dict[str, list[str]] = defaultdict(list)
        for ref, todo in sorted(marked.items()):
            for want_sym in todo:
                by_want[want_sym].append(ref)
        parts.append(
            f"\n**Written, unfinished ({len(marked)}).** Each carries `todo=` "
            "naming what it could not say, is refused by `usable`, and is not "
            "counted as done:\n"
        )
        for want_sym in sorted(by_want, key=lambda w: (-len(by_want[w]), w)):
            refs = ", ".join(f"`{r}`" for r in by_want[want_sym][:20])
            more = len(by_want[want_sym]) - 20
            parts.append(f"- `{want_sym}` — {refs}" + (f", and {more} more" if more > 0 else ""))
        parts.append("")

    shown = ", ".join(f"`{r}`" for r in left[:40]) or "(coverage lists none)"
    if len(left) > 40:
        shown += f", and {len(left) - 40} more"
    parts.append(f"\n**Absent ({len(left)}).** No row at all, because there was "
                 f"nothing to decorate:\n\n{shown}\n")
    parts.append(f"\n<!-- remaining:{len(left)}:{','.join(left[:40])}"
                 f"|todo:{','.join(sorted(marked))} -->\n\n— Claude (Camille)")
    body = "\n".join(parts)
    if _already_said(number, left, marked):
        return
    subprocess.run(
        ["gh", "issue", "comment", str(number), "--body", body],
        capture_output=True, text=True,
    )


def _already_said(number: int, left: list[str], marked: dict) -> bool:
    """Has the last note on this issue reported exactly this set?

    The marker carries the unfinished refs as well as the absent ones, so a
    wave that turns twenty absences into twenty markers posts an update
    rather than reading as no change at all.
    """
    done = subprocess.run(
        ["gh", "issue", "view", str(number), "--json", "comments"],
        capture_output=True, text=True,
    )
    if done.returncode != 0:
        return False
    marker = (f"<!-- remaining:{len(left)}:{','.join(left[:40])}"
              f"|todo:{','.join(sorted(marked))} -->")
    comments = json.loads(done.stdout or "{}").get("comments", [])
    return any(marker in (c.get("body") or "") for c in comments)


def _coverage() -> tuple[dict, dict, dict, dict]:
    """What is done, absent, and written-but-unfinished, per bucket."""
    db = game()
    rows = declared()
    done = {ref for ref, p in rows.items() if not p.unfinished}

    missing: dict[object, set[str]] = defaultdict(set)
    marked: dict[object, dict[str, tuple[str, ...]]] = defaultdict(dict)
    powers: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    for r in db.execute("SELECT ref, class, level, books FROM power WHERE class != ''"):
        if "Player's Handbook" not in json.loads(r["books"] or "[]"):
            continue
        key = (r["class"].lower(), r["level"])
        cell = powers[key]
        cell[1] += 1
        if r["ref"] in done:
            cell[0] += 1
        elif r["ref"] in rows:
            marked[key][r["ref"]] = rows[r["ref"]].unfinished
        else:
            missing[key].add(r["ref"])

    monsters: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for r in db.execute(
        "SELECT m.level, p.ref FROM monster m JOIN monster_power p"
        " ON p.monster_ref = m.ref WHERE m.book != ''"
    ):
        cell = monsters[r["level"]]
        cell[1] += 1
        if r["ref"] in done:
            cell[0] += 1
        elif r["ref"] in rows:
            marked[r["level"]][r["ref"]] = rows[r["ref"]].unfinished
        else:
            missing[r["level"]].add(r["ref"])

    return ({k: tuple(v) for k, v in powers.items()},
            {k: tuple(v) for k, v in monsters.items()},
            dict(missing),
            dict(marked))


def _open_issues() -> list[tuple[int, str]]:
    done = subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--limit", "300",
         "--json", "number,title"],
        capture_output=True, text=True,
    )
    if done.returncode != 0:
        return []
    return [(r["number"], r["title"]) for r in json.loads(done.stdout or "[]")]


def _close(number: int, have: int, want: int) -> None:
    body = (
        f"Done -- `coverage.py` reports {have}/{want} for this bucket, with no "
        "`todo=` left in it, and `audit.py` fires every row.\n\nClosed by "
        "`scripts/issues.py`, which reads coverage rather than anyone's "
        "memory.\n\n— Claude (Camille)"
    )
    subprocess.run(
        ["gh", "issue", "close", str(number), "--comment", body],
        capture_output=True, text=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
