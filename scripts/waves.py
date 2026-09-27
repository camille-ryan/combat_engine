#!/usr/bin/env python
"""What a wave of agents cost, per row written.

    uv run scripts/waves.py --record druid 1 413254 190    name, agents, tokens, calls
    uv run scripts/waves.py                                the ledger and the rate

`progress.py` measures rows per minute and `check.py --history` measures what
the instruments cost. Nothing measured the agents, which turned out to be
almost all of the spend -- 120 of them, 25.7M tokens, and the only way to
learn that was to mine a session transcript after the fact.

Tokens per row is what compares a class written by one agent against a class
split across four. When that comparison was finally made it said the opposite
of what everyone assumed:

    sorcerer   115 rows  1 agent    308k   2,679/row
    druid      140 rows  1 agent    413k   2,952/row
    avenger    141 rows  4 agents   972k   6,894/row
    barbarian  128 rows  4 agents   944k   7,375/row

Splitting a class cost about 2.5x per row, because roughly 110k of each
agent's bill is a fixed floor -- prompt, tools, brief, vocabulary, spec --
paid the moment it starts and again for every agent you add. Fitting the 118
agents with usage data:

    tokens = 110,153 fixed + 1,243 per tool call

Which is why the column to watch is **marginal** -- tokens above that floor,
per row. Raw tokens-per-row punishes a small class for being small: the floor
is the same whether 42 rows spread it or 140. Marginal is the part a brief can
actually move, and it is what runepriest was run to test (854, against druid's
2,165, on the same instrument).

Rows are counted from the registry, so the denominator cannot be fudged; the
tokens and call counts come off the agent's completion notification and have
to be typed in.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "logs" / "waves.jsonl"

#: Where the floor sat when it was last measured, so a new reading can be
#: told apart from the old regime without re-deriving it.
#: `marginal` is what the old whole-class waves spent per row *above* the
#: floor -- druid 2,165, sorcerer 1,721. A wave beating it is a brief doing
#: its job; a wave over it is reading or poking more than it needs to.
BASELINE = {
    "fixed": 110_153,
    "per_call": 1_243,
    "split": 7_100,
    "marginal": 1_800,
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--record",
        nargs=4,
        metavar=("WHAT", "AGENTS", "TOKENS", "CALLS"),
        help="a finished wave: what it wrote, how many agents, tokens, tool calls",
    )
    ap.add_argument("--rows", type=int, help="rows written, if not a whole class")
    args = ap.parse_args()

    if args.record:
        what, agents, tokens, calls = args.record
        rows = args.rows if args.rows is not None else _rows_for(what)
        if not rows:
            print(f"# no rows found for {what!r} -- pass --rows N")
            return 1
        _record(what, int(agents), int(tokens), int(calls), rows)
    _report()
    return 0


def _rows_for(what: str) -> int:
    """Rows in the registry belonging to a class, so it cannot be fudged."""
    import sys

    sys.argv = sys.argv[:1]
    from combat_engine.content import declared

    return sum(1 for p in declared().values() if getattr(p, "cls", None) == what)


def _record(what: str, agents: int, tokens: int, calls: int, rows: int) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "when": int(time.time()),
        "what": what,
        "agents": agents,
        "tokens": tokens,
        "calls": calls,
        "rows": rows,
    }
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def _report() -> None:
    if not LEDGER.exists():
        print("# no waves recorded yet")
        print(f"#   the regime this replaces: {BASELINE['split']:,}/row split,")
        print(f"#   {BASELINE['marginal']:,}/row above the floor")
        return

    rows = [json.loads(ln) for ln in LEDGER.read_text().splitlines() if ln.strip()]
    # Raw tokens-per-row punishes a small class for nothing it did: the floor
    # is the same 110k whether there are 42 rows to spread it over or 140.
    # What a brief can actually move is the marginal cost above the floor.
    print("  what           agents   rows     tokens   tok/row  marginal  calls/row")
    for r in rows:
        floor = BASELINE["fixed"] * r["agents"]
        marginal = max(r["tokens"] - floor, 0) / r["rows"]
        flag = "" if marginal <= BASELINE["marginal"] else "  <-- over"
        print(
            f"  {r['what']:<14} {r['agents']:6d} {r['rows']:6d} {r['tokens']:10,}"
            f" {r['tokens'] / r['rows']:9,.0f} {marginal:9,.0f}"
            f" {r['calls'] / r['rows']:10.1f}{flag}"
        )

    tokens = sum(r["tokens"] for r in rows)
    n = sum(r["rows"] for r in rows)
    print(f"\n  {n} rows for {tokens:,} tokens -- {tokens / n:,.0f} a row")
    # The comparison worth printing: what the old way would have cost.
    print(
        f"  the split-class regime would have been {BASELINE['split'] * n:,}"
        f" ({BASELINE['split'] * n / tokens:.1f}x)"
    )


if __name__ == "__main__":
    raise SystemExit(main())
