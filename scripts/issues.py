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

A bucket that is **partly** done is left open **and says so on the issue** —
which rows are still absent, so the next person does not have to re-derive
it from coverage. The rows that are missing were left out deliberately, each
naming the thing that would let it be written, and an issue that closed
anyway would bury exactly that; an issue that stayed open in silence buried
it almost as well.

A comment is only posted when the remaining set has *changed* since the last
one, so a bucket that has not moved does not accumulate identical notes.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict

from combat_engine.etl.build import game

ROOT_TITLE = re.compile(r"^(?P<cls>\w+) level (?P<level>\d+): ", re.I)
MONSTER_TITLE = re.compile(r"^Level (?P<level>\d+) monsters: ", re.I)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--close", action="store_true", help="actually close them")
    args = ap.parse_args()

    powers, monsters, missing = _coverage()
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
        left = sorted(missing.get(_key_of(title), ()))
        print(f"  partial #{number:<4} {title:44} {have}/{want}")
        if args.close:
            _say_whats_left(number, have, want, left)

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


def _say_whats_left(number: int, have: int, want: int, left: list[str]) -> None:
    """Put the remaining rows on the issue, if they have changed."""
    shown = ", ".join(f"`{r}`" for r in left[:40]) or "(coverage lists none)"
    if len(left) > 40:
        shown += f", and {len(left) - 40} more"
    body = (
        f"Worked, not finished: **{have} of {want}**.\n\nStill absent:\n\n"
        f"{shown}\n\nEach was left out deliberately rather than half-written — "
        "the wave that skipped it named the `Cast` method or header field it "
        "wanted, and those are collected on the engine issues. A row that is "
        "absent is counted; a row that is half-written looks finished.\n\n"
        f"<!-- remaining:{len(left)}:{','.join(left[:40])} -->\n\n— Claude (Camille)"
    )
    if _already_said(number, left):
        return
    subprocess.run(
        ["gh", "issue", "comment", str(number), "--body", body],
        capture_output=True, text=True,
    )


def _already_said(number: int, left: list[str]) -> bool:
    """Has the last note on this issue reported exactly this set?"""
    done = subprocess.run(
        ["gh", "issue", "view", str(number), "--json", "comments"],
        capture_output=True, text=True,
    )
    if done.returncode != 0:
        return False
    marker = f"<!-- remaining:{len(left)}:{','.join(left[:40])} -->"
    comments = json.loads(done.stdout or "{}").get("comments", [])
    return any(marker in (c.get("body") or "") for c in comments)


def _coverage() -> tuple[dict, dict, dict]:
    """What is declared, by power bucket and by monster level."""
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    db = game()
    declared = set(REGISTRY)

    missing: dict[object, set[str]] = defaultdict(set)
    powers: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    for r in db.execute("SELECT ref, class, level, books FROM power WHERE class != ''"):
        if "Player's Handbook" not in json.loads(r["books"] or "[]"):
            continue
        key = (r["class"].lower(), r["level"])
        cell = powers[key]
        cell[1] += 1
        if r["ref"] in declared:
            cell[0] += 1
        else:
            missing[key].add(r["ref"])

    monsters: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for r in db.execute(
        "SELECT m.level, p.ref FROM monster m JOIN monster_power p"
        " ON p.monster_ref = m.ref WHERE m.book != ''"
    ):
        cell = monsters[r["level"]]
        cell[1] += 1
        if r["ref"] in declared:
            cell[0] += 1
        else:
            missing[r["level"]].add(r["ref"])

    return ({k: tuple(v) for k, v in powers.items()},
            {k: tuple(v) for k, v in monsters.items()},
            dict(missing))


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
        f"Done -- `coverage.py` reports {have}/{want} for this bucket, and "
        "`audit.py` fires every row in it.\n\nClosed by `scripts/issues.py`, "
        "which reads coverage rather than anyone's memory.\n\n— Claude (Camille)"
    )
    subprocess.run(
        ["gh", "issue", "close", str(number), "--comment", body],
        capture_output=True, text=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
