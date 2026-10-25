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



#: How a verdict's prose is cut into candidate refs. **Not a ref pattern.**
#:
#: The first version of this was one -- anchored on the known prefixes and a
#: digit -- and it was wrong in a way a plant caught: `mba`, `rba`, `bmba` and
#: four digit-less `cf:` features are **declared refs with no digit in them**,
#: 7 of the tree's 23,060, and no pattern can tell them from English words.
#: Widening it to catch them would have matched every three-letter word in
#: every verdict.
#:
#: So the prose is cut into words and **intersected with what the tree
#: declares**, which needs no pattern and cannot false-positive by
#: construction: `1d8`, `2d10`, `#471` and `turns.py:686` are not refs because
#: they are not in the registry, not because a regex was clever about them.
_TOKENS = re.compile(r"[^\w:-]+")


def _moved_since(at: str, ref: str, declared: dict) -> bool:
    """Have this row's own source lines changed since `at`?

    **The row's lines, not its file.** A content file is edited most days, so
    "the file moved" would flag nearly every verdict and say nothing; `git
    log -L<start>,<end>:<file>` asks about the rows themselves, which is what
    a verdict is about.

    Fails **closed** -- returns False, i.e. "not moved", on any doubt: no
    source to locate, git unavailable, a path outside the repo. A verdict
    wrongly called suspect sends a reader to re-judge something that was
    fine, which is the cost this report exists to avoid; a verdict wrongly
    left alone is the status quo.
    """
    import subprocess

    row = declared.get(ref)
    fn = getattr(row, "fn", None) or getattr(row, "body", None)
    if fn is None:
        return False
    try:
        path = inspect.getsourcefile(fn)
        lines, start = inspect.getsourcelines(fn)
    except (OSError, TypeError):
        return False
    if not path:
        return False
    rel = str(Path(path).resolve())
    done = subprocess.run(
        ["git", "log", "--format=%H", f"--since={at}",
         f"-L{start},{start + len(lines) - 1}:{rel}"],
        cwd=ROOT, capture_output=True, text=True)
    return done.returncode == 0 and bool(done.stdout.strip())


def _drift(judged: dict, wanted: dict[str, list[str]], declared: dict) -> int:
    """Reconcile the recorded verdicts against the tree, and report, not gate.

    **452 hand-written verdicts with evidence, and nothing checked them
    against the thing they describe.** Three spot-checked against the code
    were all correct where `triage.py`'s own automated top candidate was
    wrong seven times in ten -- the difference being that each was written
    after reading both the row and the code, and quotes what it found. So the
    fixture is an asset; it had simply recorded a *moment* rather than
    detecting divergence from it. #551.

    `localise.py --drift` is the pattern: a manifest of digests whose whole
    value is that it **names the ref and the field that moved**. Four
    questions, which are the four ways an entry goes wrong:

    * **spent** -- the symbol is no longer in the queue. Each one is a small
      piece of evidence that its verdict was right, and a candidate for
      deletion.
    * **moved** -- the live row count differs from the recorded one. The
      verdict may well still hold; its arithmetic does not.
    * **stale rows** -- a ref the verdict's own prose names that carries no
      marker any more. This is the one that bites while *applying* a verdict:
      "f30 is writable today, nothing new is needed" is advice about a row
      finished since, filed under a symbol that now holds different rows.
    * **live and unapplied** -- a `mis-marked` verdict whose symbol is still
      blocked. The actionable queue, which nothing surfaced before.

    **Not a gate, and not registered in `check.py`.** Every legitimate day's
    work moves all four numbers, so a check that reddens on normal progress
    gets routed around -- which `audit.py`'s docstring records the cost of.
    `triage.py` is not a gate either, for the same reason. A number a session
    can read is the right shape.
    """
    spent, moved, stale, unapplied, suspect = [], [], [], [], []
    undated = 0
    for symbol, entry in sorted(judged.items()):
        # `_note` is the fixture's own header, a list of prose lines rather
        # than a verdict. Skipped by shape rather than by name, so a second
        # such key costs nothing -- and skipping by name is what a first
        # draft did, which crashed on the one that is there.
        if not isinstance(entry, dict):
            continue
        refs = wanted.get(symbol)
        if refs is None:
            spent.append((symbol, entry.get("verdict", "")))
            continue
        was = entry.get("rows")
        if isinstance(was, int) and was != len(refs):
            moved.append((symbol, was, len(refs)))
        if entry.get("verdict") == "mis-marked":
            unapplied.append((symbol, len(refs)))
        # The prose's own row references, which drift independently of the
        # count: a symbol can hold the same number of rows and not the same
        # rows. Only refs the tree actually declares are judged -- an
        # invented or mistyped one is a different fault and `lint.py`'s
        # dead-comparison walk is what finds those.
        said = f"{entry.get('why', '')} {entry.get('found', '')}"
        named = {w for w in _TOKENS.split(said) if w in declared}
        dead = sorted(r for r in named if not declared[r].unfinished)
        if dead:
            stale.append((symbol, dead))

        # **The fifth question: is the verdict older than the note that
        # disagrees with it?** The other four cannot see a verdict the row
        # it describes now *contradicts*, and that is the one that wasted a
        # session -- it is indistinguishable from an actionable entry until
        # somebody reads both. Measured: 11 of 11 symbols taken off the
        # `live and unapplied` queue were unwritable, and **five** of those
        # were refuted by the waiting row's own later docstring. #777.
        #
        # A verdict is suspect when every live ref it names has had its own
        # source lines move since the verdict was recorded. "Every" rather
        # than "any", because one row of six being rewritten says nothing
        # about the symbol -- and `stale rows` above already reports the
        # refs that lost their marker outright.
        at = entry.get("at")
        if not at:
            undated += 1
        elif entry.get("corrected_by"):
            pass  # already re-judged; that is what `corrected_by` records
        else:
            live = [r for r in named if declared[r].unfinished]
            if live and all(_moved_since(at, r, declared) for r in live):
                suspect.append((symbol, at, sorted(live)[:4]))

    print(f"  {len(judged)} verdict(s) recorded, {len(wanted)} symbol(s)"
          f" in the queue today")
    print(f"\n  spent -- no longer blocked, and the verdict earned it:"
          f" {len(spent)}")
    for symbol, verdict in spent[:20]:
        print(f"      {symbol:<44} was {verdict or '(no verdict)'}")
    if len(spent) > 20:
        print(f"      ... and {len(spent) - 20} more")

    print(f"\n  moved -- the row count is not what was recorded:"
          f" {len(moved)}")
    for symbol, was, now in sorted(moved, key=lambda m: -abs(m[1] - m[2]))[:20]:
        print(f"      {symbol:<44} {was:>4} -> {now}")
    if len(moved) > 20:
        print(f"      ... and {len(moved) - 20} more")

    print(f"\n  stale rows -- a ref the verdict names carries no marker now:"
          f" {len(stale)}")
    for symbol, dead in stale[:20]:
        print(f"      {symbol:<44} {', '.join(dead[:6])}")
    if len(stale) > 20:
        print(f"      ... and {len(stale) - 20} more")

    print(f"\n  suspect -- the rows this verdict names have all been"
          f" rewritten since it was recorded: {len(suspect)}")
    for symbol, at, refs in suspect[:20]:
        print(f"      {symbol:<44} judged {at}, moved since:"
              f" {', '.join(refs)}")
    if len(suspect) > 20:
        print(f"      ... and {len(suspect) - 20} more")
    if undated:
        print(f"      ({undated} verdict(s) carry no date and were not asked"
              f" -- a missing stamp is not evidence either way)")

    print(f"\n  live and unapplied -- `mis-marked`, still blocked:"
          f" {len(unapplied)}")
    for symbol, n in sorted(unapplied, key=lambda u: (-u[1], u[0]))[:20]:
        print(f"      {symbol:<44} {n} row(s) waiting")
    if len(unapplied) > 20:
        print(f"      ... and {len(unapplied) - 20} more")

    print("\n  Read, not gated: every day's work moves all five. The"
          " unapplied list is the one with rows behind it -- and cross it"
          " against `suspect` first, because 5 of 11 checked by hand were"
          " refuted by the row's own later note.")
    return 0


def _signatures(show: int) -> int:
    """Does the verb a `verb(keyword=)` marker names carry arguments the
    marker's own prose never mentions?

    **The markers are not wrong when written.** They enumerate the signature
    as it stood that day -- *"`c.teleport` takes `to=`, `toward=` and
    `away_from=`"* -- and then a verb grows an argument for some other row and
    nothing connects the two. `c.teleport` has taken `into=` since #685, which
    is a predicate over squares and so is exactly the *"set the decider picks
    from"* `f2945`'s note goes on to say is the honest shape of its gap. The
    prose reads current and is not. #832.

    **The strict half of that question is already a gate and is not here.**
    A marker naming a keyword the verb *does* accept is stale or mis-worded
    with no third option, and `todo.py` reds it as ARRIVED through
    `blocked._params_ok`. So this asks only about the markers that half
    passes over -- the keyword is genuinely absent, and the question is
    whether the row is waiting for the wrong one.

    **Ranked, not gated, and the threshold is why.** Asking the bare
    question -- "has the verb any keyword the prose omits" -- flags **208 of
    233**, because `on=` and `until=` are plumbing on nearly every verb and
    no row enumerates them. That is a report nobody reads. The signal is the
    prose *enumerating*: a note that names two or more of the verb's own
    keywords is reciting the signature, and what it leaves out is then
    evidence rather than silence. 4 markers at that band, 34 at one keyword,
    and a rank is printed rather than a cutoff imposed, because the band is
    my judgement and not a measurement.

    Candidates, in `triage.py`'s sense: of the 4 sharp ones, **1 is real**
    (`f2945`), and the other three name a keyword the verb has not grown --
    `i2762p1` wants a lapse *suppressed*, `f2179` wants a type read off
    another row's resolved roll. That is the same rate as the rest of this
    instrument and the reason it is not in `check.py`.
    """
    import blocked

    have = blocked._surface()
    sys.argv = sys.argv[:1]
    from combat_engine.content import declared

    rows = declared()
    found: list[tuple[int, str, str, list[str], list[str]]] = []
    shaped = 0
    for ref, row in sorted(rows.items()):
        if not row.unfinished:
            continue
        fn = getattr(row, "fn", None) or getattr(row, "body", None)
        doc = (inspect.getdoc(fn) or "") if callable(fn) else ""
        for want in row.unfinished:
            for token in blocked._wants_of(want):
                head, _, rest = token.partition("(")
                head = head.strip()
                asked = [a.split("=")[0].strip()
                         for a in rest.rstrip(")").split(",") if a.strip()]
                if not asked:
                    continue
                thing = have.get(head)
                if thing is None and "." in head:
                    owner, _, attr = head.rpartition(".")
                    thing = getattr(have.get(owner), attr, None)
                if not callable(thing):
                    continue
                try:
                    params = inspect.signature(thing).parameters
                except (TypeError, ValueError):
                    continue
                shaped += 1
                if all(a in params for a in asked):
                    continue     # todo.py's ARRIVED reds this one
                kw = [n for n, p in params.items()
                      if p.default is not inspect.Parameter.empty
                      and not n.startswith("_")]
                named = [k for k in kw
                         if re.search(rf"[`'\"]?\b{re.escape(k)}=", doc)]
                missed = [k for k in kw if k not in named]
                if named and missed:
                    found.append((len(named), ref, token, named, missed))

    found.sort(key=lambda f: (-f[0], f[1]))
    print(f"  {shaped} parameter-shaped want(s) resolve to a callable;"
          f" {len(found)} name a verb carrying keywords the note omits\n")
    for enumerated, ref, token, named, missed in found[:show]:
        print(f"  {ref:<16} {token}")
        print(f"      the note recites {enumerated}: "
              f"{', '.join(k + '=' for k in named)}")
        print(f"      the verb also takes: "
              f"{', '.join(k + '=' for k in missed[:10])}")
    if len(found) > show:
        print(f"\n  ... and {len(found) - show} more, fewer keywords recited"
              f" each -- raise --show to see them")
    print("\n  Candidates, not verdicts: the sharp band is the note that"
          " recites 2+ keywords,\n  and 1 of those 4 was real when read by"
          " hand. A verb may have grown a keyword\n  that means something"
          " else entirely. #832.")
    return 0


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
    ap.add_argument("--drift", action="store_true",
                    help="reconcile the recorded verdicts against the tree")
    ap.add_argument("--signatures", action="store_true",
                    help="markers whose `verb(keyword=)` note recites a"
                         " signature the verb has since outgrown")
    args = ap.parse_args()

    if args.signatures:
        return _signatures(args.show if args.show != 4 else 8)

    wanted = _queue()
    judged = json.loads(VERDICTS.read_text()) if VERDICTS.exists() else {}

    if args.drift:
        import blocked

        return _drift(judged, wanted, blocked._declared())

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
