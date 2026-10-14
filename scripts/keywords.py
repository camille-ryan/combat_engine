#!/usr/bin/env python
"""Does a row's header declare the keywords its card printed?

    uv run scripts/keywords.py            check against the baseline
    uv run scripts/keywords.py --record   rewrite the baseline
    uv run scripts/keywords.py --quiet    one line, for `check.py`

A content row's `keywords=[...]` is **hand-declared**; the database holds what
the card printed; before this, nothing compared them. #486 filed that gap and
sized it at 2,916 rows, and its own plan named three steps: decide which
keywords are derived, write the instrument for the declared ones, fix the
tail. This is the second step, and the first one is answered -- *none of them
is derived*, measured on #486:

* the **power source** is not implied by `cls=`. 22 classes carry more than
  one source set, including every one of the 12 real ones -- the ranger
  prints martial on 183 powers and primal on 24, the warlock has four
  different sets -- and 221 powers correctly carry no source at all, 154 of
  them racial. A derived reader would invent a power source for every racial
  power in the game.
* **weapon/implement** is not implied by having an attack. Of 2,449 attack
  powers 213 carry neither and 12 carry both, and 25 *utility* powers carry
  one, so neither `kind` nor the presence of an attack settles it.

So every one of these is declared data, and a declared field that nothing
compares against its source is the shape this repo keeps paying for: #319 is
the worked case, where a dropped keyword left `chargen.loadout` nothing to
gate on and **six powers were dealt to every wizard** whose build can never
satisfy their trigger.

## Why a baseline and not a gate

680 red on the first run is a check that cannot pass, which
`scripts/CLAUDE.md` names as the same failure as a check that is too
generous -- `audit.py` spent two hundred runs in exactly that state. So this
is a **per-ref baseline that may shrink and never grow**, the shape
`audited.json`, `cards.KNOWN` and `leaks.DEFERRED` already use:

* a ref omitting something and **not** on the list is red -- a new omission;
* a listed ref omitting **more** than recorded is red;
* a listed ref omitting **less** is red, so the file tracks the repairs
  rather than quietly covering for them;
* a listed ref omitting exactly what is recorded is named and passes.

That is stricter than a count, which cannot see ten rows healing while ten
others break.

## What it deliberately does not check

**Keywords the header declares and the database does not** -- 4,494 refs,
and almost all of it is representation rather than fault. `melee`, `ranged`,
`close` and `area` are 1,176 of them and the ETL keeps those in `reach`;
damage types are most of the rest and live in `damage=`. A gate on that
direction would be 4,494 red on day one and wrong about nearly all of it.

**A keyword with no `Keyword` member**, since a header has no way to say it.
`invigorating` is the live example: the ETL records it and the enum has no
member, which is why six rows sit blocked on `Keyword.INVIGORATING`. Counting
it here would report a content fault for an engine gap.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

BASELINE = Path(__file__).resolve().parent / "fixtures" / "keywords.json"

#: The tables whose `keywords` column is a card's printed list and whose refs
#: are content rows. `class_feature` and `racial_trait` have no such column --
#: a feature prints no keyword line -- so they are not compared.
TABLES = ("power", "item_block")


def _measure() -> dict[str, list[str]]:
    """Every content row that omits a keyword its card printed."""
    import combat_engine.content  # noqa: F401  -- populates REGISTRY
    from combat_engine.db import game
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.types import Keyword

    sayable = {k.value for k in Keyword}
    printed: dict[str, set[str]] = {}
    db = game()
    for table in TABLES:
        for ref, raw in db.execute(f"SELECT ref, keywords FROM {table}"):
            held = set(json.loads(raw or "[]"))
            if held:
                printed[ref] = held

    out: dict[str, list[str]] = {}
    for ref, power in REGISTRY.items():
        card = printed.get(ref)
        if card is None:
            continue
        declared = {str(k) for k in (power.keywords or ())}
        missing = (card & sayable) - declared
        if missing:
            out[ref] = sorted(missing)
    return out


def _load() -> dict[str, list[str]]:
    if not BASELINE.exists():
        return {}
    return dict(json.loads(BASELINE.read_text()).get("omits", {}))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true",
                    help="rewrite the baseline from what is measured now")
    ap.add_argument("--quiet", action="store_true", help="one line of summary")
    args = ap.parse_args()

    now = _measure()
    if args.record:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(
            {"omits": dict(sorted(now.items()))}, indent=1, sort_keys=True) + "\n")
        per = Counter(w for words in now.values() for w in words)
        print(f"recorded {len(now)} refs omitting a printed keyword")
        for word, count in per.most_common():
            print(f"  {count:5}  {word}")
        return 0

    was = _load()
    new = sorted(set(now) - set(was))
    gone = sorted(set(was) - set(now))
    grew = sorted(r for r in set(was) & set(now) if set(now[r]) > set(was[r]))
    healed = sorted(r for r in set(was) & set(now) if set(now[r]) < set(was[r]))
    changed = sorted(
        r for r in set(was) & set(now)
        if set(now[r]) != set(was[r]) and r not in grew and r not in healed
    )

    if args.quiet and not (new or gone or grew or healed or changed):
        print(f"{len(now)} refs omit a printed keyword, all of them recorded")
        return 0

    for ref in new:
        print(f"NEW      {ref}: header omits {', '.join(now[ref])}")
    for ref in grew:
        print(f"WORSE    {ref}: now omits {', '.join(now[ref])}, "
              f"was {', '.join(was[ref])}")
    for ref in changed:
        print(f"CHANGED  {ref}: now omits {', '.join(now[ref])}, "
              f"was {', '.join(was[ref])}")
    for ref in healed:
        print(f"BETTER   {ref}: now omits {', '.join(now[ref])}, "
              f"was {', '.join(was[ref])} -- tighten the baseline")
    for ref in gone:
        print(f"FIXED    {ref}: declared {', '.join(was[ref])} -- "
              f"tighten the baseline")

    if new or grew or changed:
        print(f"\n{len(new)} new, {len(grew)} worse, {len(changed)} changed. "
              f"A printed keyword a header drops is a row the AI prices wrong "
              f"and a feat naming that keyword cannot find. #486.")
        return 1
    if healed or gone:
        print(f"\n{len(gone) + len(healed)} refs improved. Re-record with "
              f"`--record` so the baseline tracks the repair.")
        return 1
    print(f"{len(now)} refs omit a printed keyword, all of them recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
