#!/usr/bin/env python
"""Blocked rows whose card nearly matches a row somebody already wrote.

    uv run scripts/twins.py                 ranked, similarity >= 0.55
    uv run scripts/twins.py --min 0.95      the identical-card clusters
    uv run scripts/twins.py --json out.json
    uv run scripts/twins.py --declared-twice   the gate -- see below

**The ranking is not a gate and never in `check.py`.** It answers "which row
already prints this sentence", which is a question about where to look next,
not a question with a right answer. `triage.py` is in the same category and
for the same reason.

**`--declared-twice` is a gate, and the difference is the question, not the
threshold.** It asks whether one printed card is declared **both as
something a character is granted and as something the draw can deal** --
`class_feature`/`feat` on one side, `power` on the other. That is two routes
to one card, so two hand-written bodies, and which route a holder took
decides what the card does. There is one right answer (none) and no number
to tune.

`--min 0.95` found one of the six live clusters and could not have found the
rest, and the floor was never what stood in the way: the ranking compares
**blocked** rows against written ones, so a cluster where *no* side carries
a marker is invisible to it -- and that is the dangerous case, because then
nothing anywhere reports a gap.

Two things had to be got right, and each was got wrong first.

**The normalisation.** The compendium substitutes a card's self-reference,
so one printed text reads `"... see the cf:warlock-f1c11 Augment entry"`
under one ref and `"... see the p6855 Augment entry"` under the other. A
plain compare finds only the cards that never mention themselves -- which
excluded one of the two pairs this was built for.

**The scope.** Asking the question of *all* declared rows reported **436**
findings against 2 real ones: a monster ability's card is a formula, so two
creatures printing `"+7 vs. AC Hit: 1d8 + 6 damage."` is two creatures with
the same numbers, and five class features printing one boilerplate
bonus-feat sentence is boilerplate. `scripts/CLAUDE.md` already had the
lesson -- coincidence collapsing under scoping is *"true for invented names
and false for mechanical ones"* -- and this failed the same way `--cited`'s
first draft did. Scoping by **route** rather than by a similarity floor took
it to 6, and 4 of the 6 were clusters nobody had found.

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


#: Clusters this gate already knows about, and the issue that decides each.
#:
#: **Keyed by the whole cluster**, so the waiver is a statement about *these
#: refs printing one card* rather than a licence for either ref. If a card
#: changes on either side the two stop matching, the cluster stops forming,
#: and the waiver silently covers nothing -- which is the right direction:
#: a waiver that cannot outlive its subject cannot rot into an allowance.
#:
#: No entry is a judgement that the duplication is acceptable. Each names
#: the issue holding the decision, and the gate reddens on a **seventh**
#: cluster -- which is what makes this a gate and not a record.
#:
#: **Two kinds, and they are two issues because they are two gaps.** The
#: first pair of each kind is the worked example:
#:
#: * `#1043` -- a class feature and a power row for one card, where the
#:   `power` side carries no gate, so the draw deals it to characters who
#:   cannot use it. The `p` body is also the poorer of the two.
#: * `#1045` -- a feat's `b` card re-declaring a class power it *grants*,
#:   which is the `b` convention working as designed on a card that already
#:   has its own ref. Both bodies are hand-written, so one printed card
#:   does two things depending on which route the holder took.
#: **`#1043`'s two clusters are gone rather than waived**, which is this
#: gate's own design working: the `p` side of each pair is no longer
#: declared, so neither cluster forms and a waiver for it would go red as
#: stale. Camille's call, 2026-11-01, asked directly: *"Declare one side
#: only"*. The `#1045` clusters stay waived because that duplication is
#: deliberate -- a feat's `b` card re-declaring a class power it grants.
DECLARED_TWICE_KNOWN: dict[tuple[str, ...], str] = {
    ("f3646b", "p5032"): "#1045",
    ("f3648b", "p15858"): "#1045",
    ("f3664b", "f3668b", "p15849"): "#1045",
    ("f3675b", "p15850"): "#1045",
}


def _self_blind(spec: str, ref: str) -> str:
    """A card's text with its own ref removed and its whitespace collapsed.

    Both halves are needed and each was found by the compare failing. The
    **self-reference** because the compendium substitutes it, so one printed
    card reads differently under each of its refs -- that is what hid
    `cf:warlock-f1c11`/`p6855` from an exact compare while leaving
    `cf:warlock-f1c10`/`p2263` visible. The **whitespace** because the two
    tables do not agree on it: `class_feature` keeps the page's line breaks
    where `power` has reflowed some of them.

    Not lower-cased, deliberately. Case is the one signal that tells a
    card's printed name from the generic rules phrase that spells the same
    (4,100 of 4,100 confirm it), so folding it here would make two different
    sentences compare equal for a reason this function cannot see.
    """
    return " ".join(spec.replace(ref, "@SELF@").split())


def _homes() -> dict[str, str]:
    """Which table each ref's card came out of. First table wins, as `_cards`."""
    from combat_engine.db import game

    db = game()
    out: dict[str, str] = {}
    for table in TABLES:
        try:
            rows = db.execute(f"SELECT ref FROM {table}")
        except Exception:  # a table without a spec column
            continue
        for (ref,) in rows:
            out.setdefault(ref, table)
    return out


def _declared_twice() -> list[tuple[tuple[str, ...], str]]:
    """Declared refs that share one printed card, as (cluster, sample text).

    **Scoped to clusters that straddle two tables, with monster abilities
    excluded, and that scope is the whole soundness of this gate.** The
    first draft asked only "do two declared rows share a card" and reported
    **436** findings against 2 real ones, because a monster ability's card
    *is* a formula -- `"At-Will Attack: Melee 1 (one creature); +7 vs. AC
    Hit: 1d8 + 6 damage."` is printed by two unrelated creatures and means
    two creatures with the same numbers, not one card declared twice. Five
    class features sharing a boilerplate bonus-feat sentence are the same
    story.

    So identical text does **not** imply one card, and `scripts/CLAUDE.md`
    already says why in as many words -- the premise that coincidence
    collapses under scoping is *"true for invented names and false for
    mechanical ones"*, which is what sank `--cited`'s first draft at 1,379
    hits. This one failed the same way for the same reason.

    What makes the two real pairs real is **structural**: the card is
    declared once as something a character is *granted* (`class_feature`,
    `feat`) and once as something the draw can *deal* (`power`). Those are
    two routes to one card, so two bodies, and which route a character took
    decides what the card does. A monster is neither granted nor dealt, and
    two rows in the same table cannot differ by route -- so both drop out
    by the question rather than by a threshold, which is what lets this be
    a gate at all. 436 -> 6, and 4 of the 6 were pairs I had not found.

    No tier filter and no token floor, unlike `_sides`, which has both.
    Those exist to stop the *ranking* filling with noise; a floor here
    would quietly exempt the short cards.
    """
    import combat_engine.content  # noqa: F401  -- populates REGISTRY
    from combat_engine.engine.dsl import REGISTRY

    spec = _cards()
    home = _homes()
    seen: dict[str, list[str]] = defaultdict(list)
    for ref in REGISTRY:
        text = spec.get(ref)
        if text:
            seen[_self_blind(text, ref)].append(ref)

    found = []
    for text, refs in seen.items():
        if len(refs) < 2:
            continue
        tables = {home.get(r) for r in refs}
        if "monster_power" in tables or len(tables) < 2:
            continue
        found.append((tuple(sorted(refs)), text))
    return found


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


def _gate(limit: int) -> int:
    """The `--declared-twice` run. Non-zero on a cluster nobody has waived."""
    clusters = _declared_twice()
    known = {c: why for c, why in DECLARED_TWICE_KNOWN.items()}
    fresh = [(c, t) for c, t in clusters if c not in known]
    waived = [c for c, _t in clusters if c in known]

    print(f"{len(clusters)} printed card(s) declared under more than one ref")
    for cluster in sorted(waived):
        print(f"  waived  {' '.join(cluster)}  -- {known[cluster]}")
    # **A waiver whose cluster no longer forms is RED, and the first draft
    # had it as a note.** It means one of two opposite things -- the
    # duplication was resolved, so drop the entry; or the gate stopped
    # seeing a cluster it used to see, so it is quietly watching nothing.
    # Only a human can say which, and the second is silent, so it cannot be
    # the default. Found by a plant: removing `_self_blind`'s substitution
    # took the clusters from 6 to 4 and the run still **exited 0**, which is
    # the gate losing two real findings and reporting clean.
    stale = sorted(set(known) - {c for c, _t in clusters})
    for cluster in stale:
        print(f"  STALE WAIVER  {' '.join(cluster)} ({known[cluster]}) -- "
              f"these refs no longer share a card. Either the duplication "
              f"was fixed (drop the entry) or this check stopped seeing it.")
    if not fresh and not stale:
        print("no printed card is declared twice except the waived cluster(s)")
        return 0
    if not fresh:
        print(f"\n{len(stale)} waiver(s) cover nothing -- say which of the "
              f"two it is before dropping them")
        return 1

    print()
    for cluster, text in fresh[:limit]:
        print(f"  {' '.join(cluster)}")
        print(f"      {text[:150]}")
    if len(fresh) > limit:
        print(f"... {len(fresh) - limit} more; --limit to see them")
    print(f"\n{len(fresh)} unwaived -- two bodies for one card can disagree, "
          f"and which one a character holds decides what the card does")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min", type=float, default=0.55,
                    help="similarity floor (default 0.55)")
    ap.add_argument("--tier", default="0-10",
                    help="level range, as LOW-HIGH (default 0-10, heroic)")
    ap.add_argument("--json", metavar="PATH", help="also write the full list")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--declared-twice", action="store_true",
                    help="gate: no printed card declared under two refs")
    args = ap.parse_args()

    if args.declared_twice:
        return _gate(args.limit)

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
