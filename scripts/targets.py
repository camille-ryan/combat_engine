#!/usr/bin/env python
"""Does a row's target pool match the noun its printed Target line names?

    uv run scripts/targets.py            report every disagreement
    uv run scripts/targets.py --quiet    the counts only
    uv run scripts/targets.py p14458 ... just these refs
    uv run scripts/targets.py --record   rewrite the baseline (only ever down)

`cards.py` asks whether a monster ability's header carries the printed attack,
damage, range and usage. `keywords.py` asks whether it declares the printed
keywords. **Nothing asked whether a power's target `side` can hold the thing
its Target line names**, and the answer was no for eleven rows: the page offers
a player an *ally* to pick for a card whose whole subject is a weapon.

`audit.py` cannot see it, and that is the point of a separate instrument. It
fires the row and watches for events; the effect lands, on the wrong kind of
thing, and the row reports working. #855.

## What makes this cheap, and it is the same ground `cards.py` stands on

Neither side is a judgement. The printed line is the most regular text in the
database --

    Target: One weapon
    Target: One creature or unattended object
    Target: One creature adjacent to your familiar

-- and the declared pool is a string in a frozen `Target`, already evaluated by
`@power`. So there is nothing to parse on the engine side and nothing to infer.

## The two things that make it narrow rather than noisy

**A `label` waives the row.** `Target(side, label=)` is the convention for a
card naming a thing the engine has no entity for: the pool is whoever *holds*
it and the label is what the page prints. Four artificer rows already do this
and render "One weapon or implement" correctly, so flagging them would be
flagging the fix. A label is the author saying "I know, and here is what the
player sees" -- which is exactly the distinction a gate wants and a bare regex
cannot make.

**A locator is not a target.** "One creature adjacent to your familiar" names
a creature; the familiar says *where*. A plain substring search cannot tell
that from "One ally's weapon", and on the first run it could not: 19 hits of
which **8 were locators** -- `p1164` ("Each creature in square"), `p12473`,
`p1300`, `p2207`, `p9521`, `p16566`, `p3878`, `p14428`. So `_head` cuts each
`or`-clause at the first locator preposition before looking, and the count
falls to 11 with no false positive left.

That correction is why this is 11 rows and #855's body says 12. Its census
counted four labelled artificer rows as faults and missed three real ones --
`p465`, `p1406`, `p13128`, none of which it names. An issue's census is a
floor.

## Not a count, a per-ref baseline

`fixtures/targets.json` holds the refs known to disagree. A row that starts
disagreeing is red; a listed row that stops is red too, because it means the
baseline is stale and should shrink. Same shape as `keywords.py`,
`cards.KNOWN` and `audited.json`, and for the reason `scripts/CLAUDE.md`
records: a bare count cannot tell a narrow run whether its hits are the known
ones, and cannot see one row healing while another breaks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "fixtures" / "targets.json"

#: The printed field, including the primary/secondary forms a two-attack card
#: prints. `(.*)$` under `MULTILINE`, so it stops at the end of the line.
LINE = re.compile(
    r"(?im)^\s*(?:Primary\s+|Secondary\s+)?Target[s]?\s*:\s*(.*)$")

#: A field that may follow on the same line in a flattened spec. `p14428`'s
#: Target line runs straight into "Effect: As a free action ...", and without
#: this the whole of the following sentence is searched for nouns.
NEXT_FIELD = re.compile(
    r"\b(?:Effect|Hit|Miss|Attack|Special|Trigger|Requirement|Secondary"
    r"|Sustain|Aftereffect)\s*:")

#: Where a target phrase stops naming **what** and starts naming **where**.
#: Everything from here on is a locator and is not the target, which is the
#: whole of the false-positive problem: "One creature adjacent to your
#: familiar" is a creature.
LOCATOR = re.compile(
    r"\b(?:adjacent to|within|next to|nearest|near |in the burst|in the blast"
    r"|in square|in the area|in range|that you can see|you can see)\b")

#: A printed noun the creature pools cannot hold. Measured off the corpus
#: rather than guessed -- these are the eight that actually occur in a Target
#: line across 17,713 specs, by frequency: object 16, weapon 15, square 14,
#: zone 6, conjuration 4, implement 3, spirit companion 3, familiar 3.
THINGS = (
    "spirit companion", "conjuration", "implement", "familiar",
    "weapon", "object", "square", "zone", "item", "mount",
)

#: Pools built from creatures. `dsl.candidates` fills each from a creature
#: query, so none of them can offer a thing. `"object"` is the one side that
#: can -- `scenery(world, "object", ...)` -- and `"self"` names no choice at
#: all, so neither is a disagreement.
CREATURE_SIDES = ("enemy", "ally", "any", "other", "team")


def _head(line: str) -> list[str]:
    """Each `or`-clause of a target phrase, with its locator tail cut off.

    Clause-wise rather than once over the whole line, because a mixed card
    names a creature **and** a thing -- `p11358` is "One ally in the burst
    adjacent to your spirit companion or one object", and cutting the line
    at its first locator would throw away the object that makes it a finding.
    """
    line = NEXT_FIELD.split(line, maxsplit=1)[0]
    out = []
    for clause in re.split(r"\bor\b", line):
        head = LOCATOR.split(clause, maxsplit=1)[0].strip().lower()
        # **A clause opening with a preposition continues the locator it was
        # split out of**, rather than naming a second target. `p16566` is
        # "One ally adjacent to you or to your spiderling familiar": the
        # `or` is inside the *locator*, so clause 2 is "to your spiderling
        # familiar" and the cut above cannot see it -- the "adjacent to" was
        # in clause 1. The only false positive left after the locator cut,
        # and it read exactly like a real finding.
        if re.match(r"(?:to|in|of|from|at|on|with|than)\b", head):
            continue
        out.append(head)
    return [c for c in out if c]


def _printed() -> dict[str, str]:
    """Every ref's printed spec, powers and monster abilities alike."""
    sys.path.insert(0, str(ROOT))
    from combat_engine.db import game

    con = game()
    out: dict[str, str] = {}
    for table in ("power", "monster_power"):
        for ref, spec in con.execute(f"select ref, spec from {table}"):
            if spec:
                out[ref] = spec
    return out


def disagreements(only: set[str] | None = None) -> list[tuple[str, str, str, str]]:
    """`(ref, declared side, the printed noun, the printed line)`, sorted.

    A row is a disagreement when its Target line names a thing, its declared
    pool is built from creatures, and it carries **no** label saying what the
    page should print instead.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.engine.dsl import REGISTRY

    spec = _printed()
    out = []
    for ref, p in REGISTRY.items():
        if only and ref not in only:
            continue
        text = spec.get(ref)
        if not text:
            continue
        found = LINE.search(text)
        if not found:
            continue
        aim = p.target
        if aim.label or aim.side not in CREATURE_SIDES:
            continue
        line = found.group(1).strip()
        named = next((t for clause in _head(line) for t in THINGS
                      if t in clause), "")
        if named:
            out.append((ref, aim.side, named, line[:72]))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("refs", nargs="*", help="only these refs")
    ap.add_argument("--quiet", action="store_true", help="the counts only")
    ap.add_argument("--record", action="store_true",
                    help="rewrite the baseline; refuses to let it grow")
    args = ap.parse_args()

    found = disagreements(set(args.refs) or None)
    known = set(json.loads(BASELINE.read_text())) if BASELINE.exists() else set()
    refs = {ref for ref, *_ in found}

    if args.record:
        # **Only ever down.** A new disagreement is a row to fix, not a line
        # to add -- which is the rule `audited.json` and `keywords.py` are
        # both built on, and the reason neither can be quietly widened.
        if args.refs:
            print("--record takes no refs: a partial run cannot shrink a"
                  " whole-corpus baseline without deleting what it did not"
                  " look at")
            return 1
        fresh = refs - known
        # **The one exception, and it is narrow: there is no baseline yet.**
        # The refuse-to-grow rule protects a prior measurement, and on the
        # first run there is none to protect. Without this the file could
        # only ever be seeded by hand, which is the thing a `--record` flag
        # exists to stop anybody doing.
        if fresh and BASELINE.exists():
            print(f"refusing: {len(fresh)} ref(s) are NOT in the baseline and"
                  f" --record cannot add them: {' '.join(sorted(fresh))}")
            return 1
        BASELINE.write_text(json.dumps(sorted(refs), indent=2) + "\n")
        print(f"baseline: {len(known)} -> {len(refs)}")
        return 0

    if not args.quiet:
        for ref, side, named, line in found:
            mark = " " if ref in known else "NEW"
            print(f"  {mark:3} {ref:10} pool={side:6} prints {named!r:18} "
                  f"{line}")

    fresh = refs - known
    healed = known - refs if not args.refs else set()
    print(f"{len(found)} row(s) declare a creature pool for a Target line"
          f" naming a thing; {len(known)} in the baseline")
    if fresh:
        print(f"  {len(fresh)} NEW: {' '.join(sorted(fresh))}")
    if healed:
        print(f"  {len(healed)} no longer disagree -- shrink the baseline"
              f" with --record: {' '.join(sorted(healed))}")
    return 1 if (fresh or healed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
