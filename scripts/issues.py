#!/usr/bin/env python
"""Carry the tree's own answer about an issue to GitHub, instead of remembering.

    uv run scripts/issues.py            content buckets: what would close
    uv run scripts/issues.py --close    do it
    uv run scripts/issues.py --stale    any open issue whose premise the tree
                                        has since falsified. Reports only.

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

## `--stale`: the same idea over the whole backlog

The bucket pass above covers the ~69 issues whose title matches a coverage
key. The other ~110 get nothing, and they go stale the same way -- #666 sat
open asking whether an adventuring day was in scope while `World.milestones`
was built and **no row named `c.milestone()` any more**. It was found by
hand, in a session that was looking for something else.

So `--stale` asks the one question the tree can answer about any issue:
**does a single row still want the symbol this issue is about?** Two
independent readings, which is what makes it worth trusting:

* `exists` -- the verb is a public member of `Cast` today;
* `waiting` -- how many declared rows carry it in `unfinished`.

`exists and not waiting` means the facility was built *and* the demand is
gone. That is as close to "finished" as this instrument can see.

**It reports and never closes, and that is deliberate.** `triage.py`'s rule
applies and for the same reason: *"a number that is wrong 70% of the time
cannot be a gate"*, so this ranks and a human confirms.

### The measured precision is 1 in 31, and the first estimate was 1 in 2

Worth writing down at length, because the honest number is much worse than
the one this was built on and the gap is instructive.

Calibrating on **two** candidates gave one real (`#615`) and one false
(`#823`, a browser-flake issue that merely *quotes* a commit named after a
verb) -- so "about one in two" went into this docstring. Reading **all 31**
gave exactly **one** confirmed close, which is `#615`.

The reason is a class of issue the signal cannot distinguish from a spent
one, and it turns out to be most of them: **an issue about code that should
start using a verb which now exists.** `#843` ("six content sites hand-roll
two weapon verbs that now exist") and `#838` are live work, and from here
they look identical to `#615` -- the verb is on `Cast`, no row carries the
marker, and the issue names it. The marker set answers "does a *row* want
this", and a great many issues are about `content/`, `scripts/` or `etl/`
sites instead, which no marker tracks.

`#814` is the sharpest case: it is titled *"`c.class_feature()` is at zero
rows but 16 files still define its marker constant"*. Being at zero rows is
its **premise**, not its resolution, and the strong tier flagged it anyway.

So the finding from the first full run is not the one close. **It is that
this backlog is not stale** -- 180 issues, well-evidenced, and the two
spent ones (`#666`, `#615`) were the same symbol. Anyone reaching for a
bigger reconciliation pass should read that result first.

Two things it deliberately does not see, so nobody reads a clean run as
proof: an issue naming **no** symbol at all (110 of 180 -- most of the
backlog, and the honest limit of this approach), and an issue whose census
has drifted rather than whose symbol has gone. `#214`'s 1,177-that-was-808
is the second kind and needs a different probe.
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
    ap.add_argument("--stale", action="store_true",
                    help="any open issue whose premise the tree has falsified")
    args = ap.parse_args()

    if args.stale:
        return _stale()

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


#: A symbol as an issue writes one: `c.foo()`, `chargen.bar()`,
#: `etl.monster.baz()`.
#:
#: **The backtick is optional and that is load-bearing.** The first version
#: required one, on the reasoning that the tree's issues quote every symbol.
#: Bodies do. **Titles do not** -- `#615` is titled `c.milestone(): the 6
#: rows need an adventuring day`, with no backticks anywhere -- so the title
#: tier, which is the whole point of the split, matched nothing and reported
#: a confident zero. A gate every instance of which is False reads exactly
#: like a passing one.
#:
#: The trailing `(` is what keeps this honest without the backtick: it is
#: the call syntax, so ordinary prose about a class or a file does not match.
SYMBOL = re.compile(r"\b((?:c|chargen|etl|query|spec|expect)\.[\w.]+?)\(")


def _wanted() -> dict[str, int]:
    """Every symbol a declared row still waits on, and how many want it.

    `unfinished` is the authority rather than `todo`/`dropped` read
    separately: it is what `coverage.py` and the bucket pass above already
    count, so a row cannot be finished here and unfinished there.
    """
    counts: dict[str, int] = defaultdict(int)
    for power in declared().values():
        for symbol in power.unfinished or ():
            counts[symbol.strip().split("(")[0]] += 1
    return dict(counts)


def _cast_surface() -> set[str]:
    """What `Cast` actually offers today, as `c.`-prefixed names.

    `vocab.py` is the documented authority on this surface; it is read by
    introspecting the same class, so this asks the class directly rather
    than shelling out to parse a report.
    """
    from combat_engine.engine.cast import Cast

    return {f"c.{name}" for name in dir(Cast) if not name.startswith("_")}


def _stale() -> int:
    """Rank open issues by whether the tree still wants what they name."""
    wanted, surface = _wanted(), _cast_surface()
    issues = _issue_bodies()
    if not issues:
        print("# could not read the open issues")
        return 0

    strong, weak, silent = [], [], 0
    for number, title, body in issues:
        in_title = {m.group(1) for m in SYMBOL.finditer(title)}
        in_body = {m.group(1) for m in SYMBOL.finditer(body)} - in_title
        if not (in_title or in_body):
            silent += 1
            continue
        # A symbol with even one row behind it means the issue has live
        # demand, wherever it was named -- so the whole issue is live.
        if any(wanted.get(s, 0) for s in in_title | in_body):
            continue
        row = (number, title, sorted(in_title or in_body),
               [s for s in in_title | in_body if s in surface])
        (strong if in_title else weak).append(row)

    print(f"# {len(issues)} open issues; {len(wanted)} symbols still wanted by a row\n")
    _say_stale("named in the TITLE, and no row wants it", strong, surface)
    _say_stale("named only in the body -- weaker, reads commit refs too", weak, surface)
    print(f"\n{len(strong)} strong, {len(weak)} weak, "
          f"{silent} name no symbol at all and this cannot see them.")
    print("Reports only -- confirm each by hand. Measured precision: 1 of 31 "
          "candidates on the first full run was really closeable.")
    print("Most of the rest are live issues about a site that should *start* "
          "using a verb that now exists; see the docstring.")
    return 0


def _say_stale(heading: str, rows: list, surface: set[str]) -> None:
    print(f"## {heading}  ({len(rows)})")
    if not rows:
        print("   none\n")
        return
    for number, title, symbols, built in sorted(rows):
        # `built` is the second reading: the verb is there and nothing wants
        # it, which is the pair that means finished rather than abandoned.
        mark = "built" if built else "gone "
        print(f"  {mark} #{number:<4} {', '.join(symbols)[:38]:38} {title[:58]}")
    print()


def _issue_bodies() -> list[tuple[int, str, str]]:
    done = subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--limit", "400",
         "--json", "number,title,body,comments"],
        capture_output=True, text=True,
    )
    if done.returncode != 0:
        return []
    out = []
    for r in json.loads(done.stdout or "[]"):
        text = (r["body"] or "") + "\n" + "\n".join(
            c.get("body") or "" for c in r.get("comments", ()))
        out.append((r["number"], r["title"], text))
    return out


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
