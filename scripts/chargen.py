#!/usr/bin/env python
"""What a character would take, ranked, and why.

    uv run scripts/chargen.py --class fighter
    uv run scripts/chargen.py --class wizard --what feats --limit 15
    uv run scripts/chargen.py --class rogue --level 6 --verbose
    uv run scripts/chargen.py --class fighter --draws 200

Every build choice in `chargen` used to be uniform random or fixed, so there
was no way to ask what a character *should* take, and no way to see why it
took what it did. `chargen/choices.py` scores the options; this prints the
scores with the terms that made them.

It is the same job the chargen page will do and it exists first on purpose:
the weights want reading and arguing with before anything draws them in HTML,
and a table in a terminal is the cheapest way to do that.

**Refs only.** This prints `r24` and `f963`, never a name -- the same rule the
rest of the project runs on. `--draws` is how the *distribution* is read rather
than one ranking: a scored draw can fail by being degenerate as easily as by
being wrong, and the two look nothing alike in a list of scores.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from random import Random

import combat_engine.content  # noqa: F401  (registers the rows)
from combat_engine import chargen
from combat_engine.chargen import choices
from combat_engine.engine.dsl import REGISTRY


def _table(ranked: list[choices.Choice], limit: int, verbose: bool) -> None:
    for choice in ranked[:limit]:
        terms = ", ".join(f"{name} {value:+.1f}" for name, value in choice.why)
        print(f"  {choice.ref:<10} {choice.score:7.2f}   {terms}")
    rest = len(ranked) - limit
    if rest > 0 and not verbose:
        print(f"  ... {rest} more, lowest {ranked[-1].score:.2f} ({ranked[-1].ref})")


def _draws(cls: str, level: int, build: chargen.Build, rounds: int) -> None:
    """The distribution, which is the half a ranking cannot show.

    Two ways this can be wrong and both are invisible in a table of scores: a
    draw that always takes the top option (every fighter the same race), and
    one so flat that scoring bought nothing. Both are read here.
    """
    raises = [
        ref
        for ref, line in chargen.RACES.items()
        if build.primary in line.taken(build)
    ]
    drawn = [
        chargen.deal_race(Random(f"{cls}:{i}"), cls, build) for i in range(rounds)
    ]
    counted = Counter(drawn)
    hit = 100 * sum(1 for r in drawn if r in raises) / rounds
    base = 100 * len(raises) / max(1, len(chargen.RACES))
    print(f"\n  races over {rounds} draws")
    print(f"    distinct            {len(counted)} of {len(chargen.RACES)}")
    print(f"    commonest           {counted.most_common(3)}")
    print(f"    raises the primary  {hit:.1f}%   (uniform would be {base:.1f}%)")

    legal = choices.legal_feats(cls, level, build, "")
    opens = {r for r in legal if getattr(REGISTRY[r], "proficiency", ()) or ()}
    picks = Counter(
        chargen._one_feat(legal, cls, build, Random(f"{cls}:f{i}"))
        for i in range(rounds)
    )
    armed = sum(n for ref, n in picks.items() if ref in opens)
    print(f"  feats over {rounds} draws")
    print(f"    legal               {len(legal)}")
    print(f"    distinct drawn      {len(picks)}   (of the top {choices.FEAT_TOP})")
    print(
        f"    opens a weapon      {100 * armed / rounds:.1f}%"
        f"   (uniform would be {100 * len(opens) / max(1, len(legal)):.1f}%)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--class", dest="cls", default="fighter")
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--build", default="", help="which leg of the fork")
    ap.add_argument("--race", default="", help="fixes the race, for a feat ranking")
    ap.add_argument(
        "--what",
        choices=("races", "feats", "both"),
        default="both",
    )
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--verbose", action="store_true", help="every option, not the top")
    ap.add_argument(
        "--draws",
        type=int,
        default=0,
        help="also sample this many characters and report the distribution",
    )
    args = ap.parse_args()

    if args.cls not in chargen.CLASSES:
        print(f"no such class: {args.cls}", file=sys.stderr)
        return 2
    build = chargen.build_of(args.cls, args.build)
    limit = 10_000 if args.verbose else args.limit
    print(
        f"class {args.cls}   level {args.level}   leg {build.name or '(first)'}   "
        f"primary {build.primary.value}   secondary {build.secondary.value}   "
        f"swings a weapon {choices.swings_a_weapon(args.cls, build)}"
    )

    if args.what in ("races", "both"):
        ranked = choices.race_options(args.cls, args.level, build)
        print(f"\nraces, best first ({len(ranked)}):")
        _table(ranked, limit, args.verbose)

    if args.what in ("feats", "both"):
        legal = choices.legal_feats(args.cls, args.level, build, args.race)
        ranked = choices.feat_options(legal, args.cls, build)
        print(f"\nfeats, best first ({len(ranked)} legal):")
        _table(ranked, limit, args.verbose)

    if args.draws:
        _draws(args.cls, args.level, build, args.draws)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
