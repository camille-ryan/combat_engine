#!/usr/bin/env python
"""Blocked rows whose card nearly matches a row somebody already wrote.

    uv run scripts/twins.py                 ranked, similarity >= 0.55
    uv run scripts/twins.py --min 0.95      the identical-card clusters
    uv run scripts/twins.py --json out.json

**Not a gate and never in `check.py`.** It answers "which row already prints
this sentence", which is a question about where to look next, not a question
with a right answer. `triage.py` is in the same category and for the same
reason.

## Why it exists

`vocab.py` calls filing a gap for something that exists "the commonest and
most expensive mistake in this project", and `docs/symbols/` fixed the half
of that about **verbs**. This is the other half: a *card* somebody has
already written. Two rounds of re-pointing went through the triage queue --
ranked by how many rows wanted a symbol -- and the symbol was the wrong unit
both times. What actually unblocked rows was noticing the sibling card:

* `f1032` is `f233`'s card with attack where the other says damage, written
  and unmarked the whole time, and its docstring settles the objection
  `f233`'s marker was waiting on;
* `p9501`'s own body held the literal `f1817` was marked for;
* one `settle()` helper was six rows of one card, short the same clause.

None of those were visible from the symbol. All three are obvious from the
card text.

## What it does and does not tell you

A twin at 1.0 means the two cards reduce to the same token set, which is as
close to "the same card" as this gets. It does **not** mean the blocked row
is writable: twice in one session the cluster's *written* row turned out to
be the wrong one --

* `settle`'s six callers: two carried no marker and were missing the clause
  the other four admitted to;
* the six "cannot enter its space" rows: the unmarked one had decided the
  card needed no code, and a phasing enemy walks through it.

So read it as "these rows disagree with each other and one of them is
wrong", and go and find out which. That is a much better question than the
symbol queue asks, and it is still a question.

The 0.55 floor and the 400-document token cut-off are judgement, tuned until
the top of the list stopped being noise. Nothing downstream depends on
either number.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

#: Tables whose `spec` is a card's printed text.
TABLES = ("feat", "power", "item_block", "class_feature", "racial_trait",
          "monster_power")

_WORD = re.compile(r"[a-z]+")

#: Words carried by so many cards that sharing them says nothing. Not a
#: linguistic stop-list -- it is the vocabulary of *this* corpus, which is
#: why "target", "square" and "bonus" are in it and ordinary English words
#: like "cannot" are not.
_STOP = frozenset((
    "the", "a", "an", "you", "your", "and", "or", "of", "to", "with", "that",
    "this", "it", "its", "is", "are", "be", "can", "on", "in", "at", "as",
    "if", "for", "from", "by", "not", "no", "any", "one", "two", "each",
    "when", "while", "until", "end", "next", "turn", "target", "creature",
    "square", "squares", "make", "makes", "made", "gain", "gains", "use",
    "uses", "using", "power", "attack", "bonus",
))

#: A token on more than this many cards is dropped from the candidate search.
#: Only an efficiency cut -- it narrows who gets compared, never the score.
_COMMON = 400


def _cards() -> dict[str, str]:
    from combat_engine.db import game

    db = game()
    out: dict[str, str] = {}
    for table in TABLES:
        try:
            rows = db.execute(f"SELECT ref, spec FROM {table}")
        except Exception:  # a table without a spec column
            continue
        for ref, spec in rows:
            if spec and ref not in out:
                out[ref] = spec
    return out


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        w for w in _WORD.findall(text.lower())
        if w not in _STOP and len(w) > 2
    )


def _sides(tier: tuple[int, int]) -> tuple[dict, dict]:
    """Blocked rows and written rows, as token sets."""
    import combat_engine.content  # noqa: F401  -- populates REGISTRY
    from combat_engine.engine.dsl import REGISTRY

    spec = _cards()
    low, high = tier
    blocked: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {}
    written: dict[str, frozenset[str]] = {}
    for ref, p in REGISTRY.items():
        if not low <= (p.level or 0) <= high:
            continue
        text = spec.get(ref)
        if not text:
            continue
        toks = _tokens(text)
        # A card with almost no distinctive words cannot be matched on
        # content, and pretending otherwise fills the top of the list.
        if len(toks) < 5:
            continue
        wants = (getattr(p, "todo", None) or ()) + (getattr(p, "dropped", None) or ())
        excused = any(
            getattr(p, k, None)
            for k in ("narrative", "obsolete", "declined", "defect")
        )
        if wants:
            blocked[ref] = (toks, wants)
        elif not excused:
            written[ref] = toks
    return blocked, written


def _pairs(blocked: dict, written: dict, floor: float) -> list[tuple]:
    index: dict[str, list[str]] = defaultdict(list)
    for ref, toks in written.items():
        for word in toks:
            index[word].append(ref)
    spread = {word: len(refs) for word, refs in index.items()}

    found = []
    for ref, (toks, wants) in blocked.items():
        shared: dict[str, int] = defaultdict(int)
        # Rarest tokens first: they are the ones that identify a card.
        for word in sorted(toks, key=lambda w: spread.get(w, 0))[:14]:
            if spread.get(word, 0) > _COMMON:
                continue
            for other in index[word]:
                shared[other] += 1
        best, score = None, 0.0
        for other, _n in sorted(shared.items(), key=lambda kv: -kv[1])[:40]:
            union = toks | written[other]
            sim = len(toks & written[other]) / len(union) if union else 0.0
            if sim > score:
                best, score = other, sim
        if best is not None and score >= floor:
            found.append((round(score, 3), ref, best, wants))
    found.sort(key=lambda row: (-row[0], row[1]))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min", type=float, default=0.55,
                    help="similarity floor (default 0.55)")
    ap.add_argument("--tier", default="0-10",
                    help="level range, as LOW-HIGH (default 0-10, heroic)")
    ap.add_argument("--json", metavar="PATH", help="also write the full list")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    low, _, high = args.tier.partition("-")
    blocked, written = _sides((int(low), int(high or low)))
    found = _pairs(blocked, written, args.min)

    print(f"{len(blocked)} blocked and {len(written)} written rows in levels "
          f"{args.tier}")
    print(f"{len(found)} blocked rows have a written twin at >= {args.min}")
    exact = sum(1 for row in found if row[0] >= 0.999)
    if exact:
        print(f"{exact} of them at 1.0 -- the same card, written once and "
              f"marked elsewhere")
    print()
    print(f"{'sim':>5}  {'blocked':14} {'written twin':14} waiting on")
    for sim, ref, twin, wants in found[:args.limit]:
        print(f"{sim:5}  {ref:14} {twin:14} {','.join(wants)[:44]}")
    if len(found) > args.limit:
        print(f"... {len(found) - args.limit} more; --limit to see them")

    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"sim": s, "ref": r, "twin": t, "wants": list(w)}
             for s, r, t, w in found], indent=1) + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
