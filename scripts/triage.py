#!/usr/bin/env -S uv run python
"""Ask, for every blocked symbol, whether the thing already exists.

**The most expensive mistake this project makes, measured.** Of fourteen
marked families examined by hand in one session, **seven needed no engine
work at all** -- the facility was already there under another name:

    c.contract           "nothing contracts a disease"
    rage.raging()        "nothing says a barbarian is raging"
    c.extend_move        "nothing lengthens a printed distance"
    Build.choices        "a racial choice is recorded nowhere"
    _holding_ref         "nothing asks which weapon is in hand"
    Sheet.per_day        "nothing counts uses across a day"
    c.fell_might()       "nothing holds a resource across uses"

`vocab.py --find` was built for exactly this question and asks it one symbol
at a time, for a symbol you already suspect. Nobody has ever asked it of the
**whole queue**, which is 1,105 symbols -- so a marker that was wrong on the
day it was written stays wrong until somebody happens to read that row.

This runs the question over every one of them and ranks what it finds.

## What it does not do

**It does not decide.** Matching prose against a terse symbol name produces
candidates, not verdicts: `c.zone(exempt=)` will surface `c.zone` whatever
happens, and that tells you nothing. The output is a ranked list for a person
or an agent to judge, and the judgement is recorded in `fixtures/triage.json`
so it is made once.

So the honest reading of a run is "these N symbols are worth a second look",
never "these N symbols are wrong".

## Two different questions, because the symbols are two shapes

    c.zone(exempt=)      the verb EXISTS -- 306 symbols are like this
    c.cover_from()       the verb is ABSENT -- 424 are like this

For the first, searching the verb's own name is noise: of course `c.zone`
exists. The question is whether anything already expresses the **kwarg** --
so those are searched on the parameter words alone, and the report says so.
Searching the whole symbol would have returned the verb itself at rank 1 for
all 306 and looked like a 100% hit rate.

## Calibrate before trusting it

`--top N` runs only the N symbols with the most rows waiting. That is the
measurement that decides whether the instrument earns its place: if it flags
roughly a third of the biggest symbols the way hand-reading did, the rate is
real. If it flags none, the seven above were a property of which families
somebody happened to pick, and this should be deleted rather than believed.
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

VERDICTS = ROOT / "scripts/fixtures/triage.json"

#: Words that carry no search signal. Deliberately short: a stop list that
#: grows starts throwing away the words that matter, and `when`/`of`/`by`
#: are exactly the parameter names several real gaps are named for.
NOISE = {
    "the", "a", "an", "and", "or", "is", "it", "to", "for", "with", "on",
    "in", "that", "this", "ref", "self", "true", "false", "none",
}

#: Prefixes that say which layer a symbol names. `compendium.` is the source
#: and no code can ever close it, so it is dropped before searching rather
#: than reported as "nothing found" 50 times.
SOURCE = "compendium."


def _words(symbol: str) -> tuple[list[str], str]:
    """A symbol's searchable words, and which question to ask of it.

    Returns `(words, shape)` where shape is `"kwarg"` when the verb already
    exists and only a parameter is missing -- in which case the verb's own
    name is dropped, because finding it proves nothing.
    """
    from combat_engine.engine.cast import Cast

    head = re.match(r"([A-Za-z_][\w.]*)", symbol)
    name = head.group(1) if head else symbol
    bare = name.split(".")[-1]
    inner = symbol[len(name):]

    # **Split on underscores as well as punctuation.** `race_option` kept
    # whole matched nothing in the entire vocabulary, and the real facility
    # it was already served by -- `Build.choices`' `race:<ref>` note -- says
    # "race" and never "race_option". A symbol name is a compound and the
    # prose it should match is not.
    def split(text: str) -> list[str]:
        parts = re.split(r"[^A-Za-z]+", text)
        return [p.lower() for p in parts
                if len(p) > 1 and p.lower() not in NOISE and p != "self"]

    # `c.foo(bar=)` where `c.foo` is a real method: ask about `bar` only.
    if (symbol.startswith("c.") and hasattr(Cast, bare)
            and re.search(r"[(\[]", inner)):
        got = split(inner)
        if got:
            return got, "kwarg"
    return split(symbol), "whole"


def _corpus() -> list[tuple[str, str, str]]:
    """Everything the engine says it does: `(name, text, kind)`.

    The same four places `vocab.py --find` reads, and for the reason its
    docstring gives -- the three facilities that were missed most recently
    lived in three different layers, so a search of `Cast` alone would have
    found none of them.
    """
    import combat_engine.engine.dsl as _dsl
    import combat_engine.engine.query as _query
    import combat_engine.engine.triggers as _triggers
    from combat_engine.engine.cast import Cast

    out: list[tuple[str, str, str]] = []
    for label, obj in (("c.", Cast), ("query.", _query),
                       ("triggers.", _triggers), ("dsl.", _dsl)):
        for name, member in sorted(vars(obj).items()):
            if name.startswith("__") or not callable(member):
                continue
            doc = inspect.getdoc(member) or ""
            out.append((f"{label}{name}", f"{name} {doc}", "verb"))

    comp = (ROOT / "src/combat_engine/engine/components.py").read_text()
    for blk in re.split(r"\n(?=@dataclass)", comp):
        cls = re.search(r"\nclass (\w+)", blk)
        if not cls:
            continue
        for m in re.finditer(r"((?:\s*#:[^\n]*\n)+)\s*(\w+)\s*:", blk):
            note, field = m.group(1), m.group(2)
            out.append((f"{cls.group(1)}.{field}", f"{field} {note}", "state"))

    # **Shared helpers only, never rows.** The first version swept in every
    # decorated row body, because a row *is* a function with a docstring --
    # and then "spec + weapon" ranked four monster abilities at the top,
    # purely because their prose happens to use both words. A row can never
    # be the facility a symbol is waiting for; it is the thing waiting.
    #
    # **Read off the registry, not off the decorators.** Matching
    # `@power(...)` through to the next `def` is unreliable: a
    # module-level helper sitting between a decorator and its row makes
    # the lazy match stop at the helper and capture *its* name, so the
    # row stays in -- which is how two feat rows were still being ranked
    # for `chargen.skill_training()`. Every declared row carries its own
    # function object, so the registry answers it exactly.
    # **The layers a symbol can name, beyond the engine.** 677 row-wants
    # name `spec.`, `chargen.`, `etl.` or `turns.`/`loader.` -- and searching
    # engine docstrings cannot answer "does spec.py already resolve a weapon
    # ref". Without these the instrument was blind to a third of the queue
    # while reporting candidates for it.
    for rel in ("src/combat_engine/chargen", "src/combat_engine/etl",
                "src/combat_engine/engine", "src/combat_engine/story",
                "scripts/spec.py"):
        here = ROOT / rel
        files = [here] if here.is_file() else sorted(here.rglob("*.py"))
        for path in files:
            if "__pycache__" in str(path):
                continue
            # The four modules the verb sweep above already covers, so a
            # candidate is not reported twice under two kinds.
            if path.name in ("cast.py", "dsl.py", "query.py", "triggers.py"):
                continue
            src = path.read_text(errors="replace")
            stem = path.relative_to(ROOT).as_posix()
            stem = stem.removesuffix(".py").split("/")[-1]
            for m in re.finditer(
                r'\ndef (\w+)\([^)]*\)[^:]*:\n\s+"""(.*?)"""', src, re.S
            ):
                name, doc = m.group(1), m.group(2)
                out.append((f"{stem}.{name}", f"{name} {doc}", "layer"))

    from combat_engine.engine.dsl import REGISTRY

    # `getattr`, not `.__name__`: `Body` is a Callable protocol and a
    # callable need not be a function -- a few rows are wrapped. `ty` is
    # right to refuse the direct attribute.
    rows = {name for name in
            (getattr(getattr(p, "body", None), "__name__", "")
             for p in REGISTRY.values())
            if name}

    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        src = path.read_text(errors="replace")
        for m in re.finditer(r'\ndef (\w+)\([^)]*\)[^:]*:\n\s+"""(.*?)"""',
                             src, re.S):
            name, doc = m.group(1), m.group(2)
            if name in rows:
                continue
            rel = path.relative_to(ROOT / "src/combat_engine/content")
            dotted = rel.as_posix().removesuffix(".py").replace("/", ".")
            out.append((f"{dotted}.{name}", f"{name} {doc}", "helper"))
    return out


def _score(words: list[str], name: str, text: str) -> int:
    """How well this candidate answers those words.

    **Name matches are worth more than prose matches**, which is the whole
    of the ranking. A docstring mentioning "shift" somewhere in four
    paragraphs is weaker evidence than a method called `shift_as`, and
    without the weighting the long docstrings in `cast.py` outrank the short
    ones for every query -- the longest file wins, which is not a signal.

    **Scored on the bare name, never the dotted path.** The path says where
    a thing lives and not what it does, and counting it put every helper
    under `monsters/` four points up on the word "monster" -- which ranked
    four unrelated private predicates at the top for `spec.monster_ref()`
    and looked like four candidates worth reading.
    """
    low_name = name.rsplit(".", 1)[-1].lower()
    low_text = text.lower()
    score = 0
    for w in words:
        if w in low_name:
            score += 4
        elif re.search(rf"\b{re.escape(w)}", low_text):
            score += 1
    # Every word accounted for is the strong case. Partial matches are
    # reported but must not outrank it on length alone.
    if all(w in low_name or w in low_text for w in words):
        score += 3
    return score


def _queue() -> dict[str, list[str]]:
    """Every wanted symbol and the rows waiting, straight off the tree.

    Reuses `blocked.py`'s own reader rather than re-deriving: that file is
    the authoritative queue and a second parser of the same markers would
    drift from it silently. Hand-rolling this was tried first and
    undercounted by 40%.
    """
    import blocked

    wanted: dict[str, list[str]] = defaultdict(list)
    for ref, p in sorted(blocked._declared().items()):
        for want in p.unfinished:
            wanted[want.strip()].append(ref)
    return dict(wanted)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--top", type=int, metavar="N",
                    help="only the N symbols with the most rows waiting"
                         " -- the calibration run")
    ap.add_argument("--symbol", metavar="SYM", help="one symbol, in full")
    ap.add_argument("--show", type=int, default=4, metavar="N",
                    help="candidates per symbol (default 4)")
    ap.add_argument("--quiet", action="store_true", help="counts only")
    args = ap.parse_args()

    wanted = _queue()
    judged = json.loads(VERDICTS.read_text()) if VERDICTS.exists() else {}

    pool = [(s, refs) for s, refs in wanted.items()
            if not s.startswith(SOURCE)]
    pool.sort(key=lambda p: (-len(p[1]), p[0]))
    if args.symbol:
        pool = [(s, r) for s, r in pool if s == args.symbol]
        if not pool:
            print(f"{args.symbol!r} is not in the queue.")
            return 1
    elif args.top:
        pool = pool[: args.top]

    corpus = _corpus()
    flagged = 0
    for symbol, refs in pool:
        words, shape = _words(symbol)
        if not words:
            continue
        ranked = sorted(
            ((_score(words, n, t), n, t, k) for n, t, k in corpus),
            key=lambda r: (-r[0], r[1]),
        )
        best = [r for r in ranked if r[0] >= 5][: args.show]
        verdict = judged.get(symbol, {}).get("verdict", "")
        if best and not verdict:
            flagged += 1
        if args.quiet:
            continue
        mark = f"  [{verdict}]" if verdict else ""
        asked = " + ".join(words)
        print(f"\n{symbol}  ({len(refs)} rows){mark}")
        print(f"    asked: {asked}"
              + ("   (the kwarg only -- the verb exists)"
                 if shape == "kwarg" else ""))
        if not best:
            print("    nothing in the vocabulary comes close")
            continue
        for score, name, text, kind in best:
            first = " ".join(text.split())
            first = first[len(name) + 1:] if first.startswith(name) else first
            print(f"    {score:3}  {kind:6} {name:42} {first[:70]}")

    print(f"\n  {len(pool)} symbol(s) asked, {flagged} with a candidate"
          f" worth reading and no verdict recorded yet")
    if not args.symbol and not args.top:
        print("  judge them with --symbol, and record the verdict in"
              f" {VERDICTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
