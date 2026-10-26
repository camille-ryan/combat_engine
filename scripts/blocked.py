#!/usr/bin/env python
"""Rows that are not finished, and what each is waiting for.

    uv run scripts/blocked.py                   what is outstanding, and what is ready now
    uv run scripts/blocked.py --ready           only the ones that have become writable,
                                                plus the three shapes the rest are in
    uv run scripts/blocked.py --group           the engine's work queue, ranked by demand
    uv run scripts/blocked.py --refs 'c.deals()'   just the refs waiting on that one

Nothing recorded *why* a row was skipped. That lived in the wave's report,
which is ephemeral, and in an issue comment, which is not queryable, so when
a method was finally built the rows waiting for it stayed missing until
somebody happened to remember. Three level-5 rows sat blocked on
`c.moving_as` for four levels after it was built.

The list used to be hand-maintained, and a hand-maintained list of four
thousand items and feats is a list nobody maintains. So the outstanding set
is now read **out of the tree**: a row that cannot be fully written is
written with `todo=("c.deals()",)`, and this reads those markers. The
hand-written `docs/blocked.json` is kept only for rows that are genuinely
absent -- there is nothing to decorate when the row does not exist -- and the
two are reported separately so its remaining size is visible and shrinking.

`--group` is the point of the whole arrangement. The queue is generated and
ranked by the number of rows actually asking, which is what `blocked.json`
was trying and failing to be, and `--refs` turns a queue entry straight back
into a brief:

    uv run scripts/spec.py $(uv run scripts/blocked.py --refs 'c.deals()') --all
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKED = ROOT / "docs" / "blocked.json"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ready", action="store_true", help="only what is now writable")
    ap.add_argument("--group", action="store_true",
                    help="wanted symbols, ranked by how many rows asked")
    ap.add_argument("--refs", metavar="SYMBOL",
                    help="the refs waiting on this one, space separated, for spec.py")
    ap.add_argument("--prose", action="store_true",
                    help="rows admitting a dropped clause while declaring no marker")
    args = ap.parse_args()

    rows = _declared()
    marked = [
        (ref, tuple(p.unfinished))
        for ref, p in sorted(rows.items())
        if p.unfinished
    ]
    entries = json.loads(BLOCKED.read_text()) if BLOCKED.exists() else {}

    if args.prose:
        return _drops_report()

    if args.group or args.refs:
        return _queue(marked, entries, set(rows), args)

    have = _surface()
    return _report(marked, entries, set(rows), have, args.ready)


# --------------------------------------------------------------------------
# The two sources, reported apart
# --------------------------------------------------------------------------


#: Prefix for a want that names the **source** rather than our code. A row
#: whose every want starts with this is not unstarted work -- the compendium
#: does not print what the row would be written from, so no symbol can arrive.
#: Kept as a prefix rather than a list so a second source gap is counted the
#: day somebody names one, with no edit here.
SOURCE_GAP = "compendium."


def _head_of(token: str) -> tuple[str, str]:
    """A want split into the thing named and the arguments asked for."""
    head, _, rest = token.partition("(")
    return head.strip(), rest


def _named_thing_exists(token: str, have: dict[str, object]) -> bool:
    """Does **something of that name** exist, ignoring the arguments?

    The other half of `_one`, which answers the whole question. Apart,
    because the difference is the whole of #677: a want whose head exists
    and whose argument does not is **one parameter** of work, and a want
    whose head does not exist is a facility nobody has started. Reported as
    one four-figure total, the first was buried in the second.
    """
    import re as _re

    if _re.fullmatch(r"[pmifr]\d+[a-z]?\d*|(?:cf|rt):[\w-]+", token):
        from combat_engine.content import declared

        return token in declared()
    head, _ = _head_of(token)
    if head in have:
        return True
    if "." not in head:
        return False
    owner, _, attr = head.rpartition(".")
    thing = have.get(owner)
    if thing is not None and hasattr(thing, attr):
        return True
    # The same fallback `_one` makes, and for the same reason: a marker
    # written from memory names the wrong module about as often as it names
    # the wrong thing.
    pool = _FALLBACK or have
    engine_owned = owner.split(".")[0] in (_ENGINE_OWNERS or {owner.split(".")[0]})
    if not (owner.islower() and engine_owned):
        return False
    return any(
        k.endswith(f".{attr}") or k == attr
        for k in pool
        if not k.startswith("c.")
    )


def _shape_of(token: str, have: dict[str, object]) -> str:
    """Which bucket this want is in: `parameter`, `facility` or `source`.

    #677. `--ready` read "0 ready, 1153 still blocked" and the flat total
    implied the whole of it was waiting on work nobody had started. 285 of
    them wanted **one argument on a verb that already exists, with its
    readers** -- the cheapest work in the tree, and invisible.

    A want naming arguments on a thing that exists is `parameter`. Nothing
    of that name at all is `facility`.

    **A want naming no arguments on a thing that exists answers `ready`**,
    which in the report is unreachable -- `_one` has already put that row
    in the ready bucket. It is named rather than folded into `facility`
    because this function is also the thing a reader calls to ask about one
    symbol, and answering "facility" for a symbol that exists would be a
    lie told to be tidy. If it ever shows up in a count, the two halves
    disagree and that is the finding.
    """
    if token.startswith(SOURCE_GAP):
        return "source"
    if not _named_thing_exists(token, have):
        return "facility"
    _, rest = _head_of(token)
    return "parameter" if rest.strip(" )") else "ready"


def _report(
    marked: list[tuple[str, tuple[str, ...]]],
    entries: dict,
    declared: set[str],
    have: dict[str, object],
    only_ready: bool,
) -> int:
    ready = partial = waiting = sourced = capped = 0
    lines: list[str] = []
    #: Blocked rows by the shape of what they want. See `_shape_of`.
    shape: dict[str, list[str]] = defaultdict(list)
    for ref, todo in marked:
        arrived = [w for w in todo if _one(w, have)]
        if len(arrived) == len(todo):
            ready += 1
            lines.append(f"  READY   {ref:<10} {', '.join(todo)} exists now")
        elif arrived:
            # Two of three built is news, and reporting it as blocked hides
            # the only thing that changed.
            partial += 1
            left = [w for w in todo if w not in arrived]
            lines.append(f"  partial {ref:<10} {', '.join(arrived)} exists; "
                         f"still waiting on {', '.join(left)}")
        elif all(w.startswith(SOURCE_GAP) for w in todo):
            # **Waiting on the compendium is not waiting on work.** 22 rows
            # name `compendium.attack_defence`: the page prints no defence on
            # that attack line, so no symbol can ever arrive and the row is as
            # finished as it will ever be. Counting them with the genuinely
            # unstarted rows made the headline mix "nobody has done this" with
            # "nobody can". #360 settled the fact; this stops the queue
            # reporting it as a backlog item.
            #
            # They keep `dropped=` and that is deliberate -- `content/CLAUDE.md`
            # is explicit that `defect=` here would be wrong: *"Of 26 rows with
            # a blank attack defence, 23 play and 3 do not -- flagging all 26
            # would have refused 23 working rows."*
            sourced += 1
            if not only_ready:
                lines.append(f"  source  {ref:<10} {', '.join(todo)} "
                             f"— the page does not print it; nothing to build")
        else:
            waiting += 1
            # **Which kind of blocked**, which is #677's whole point. A row
            # wanting one argument on an existing verb is cheap work; a row
            # wanting a facility is not; and a flat total said neither. A row
            # with two wants counts in the *dearer* bucket, because that is
            # what has to land before it can be written.
            kinds = {_shape_of(w, have) for w in todo}
            shape["facility" if "facility" in kinds else
                  "parameter" if "parameter" in kinds else
                  "ready" if "ready" in kinds else "source"].append(ref)
            # A row wanting the source *and* real work can be worked on and
            # still never clear. Four of them. Counted as waiting, because the
            # work is real, and named so the ceiling is not a surprise.
            if any(w.startswith(SOURCE_GAP) for w in todo):
                capped += 1
            if not only_ready:
                cap = " (capped: also waits on the source)" if any(
                    w.startswith(SOURCE_GAP) for w in todo) else ""
                lines.append(f"  blocked {ref:<10} {', '.join(todo)}{cap}")
    if lines:
        print("  in the tree, marked `todo=`")
        print("\n".join(lines))

    jready, jwaiting, stale, unchecked = [], [], [], []
    jsourced: list[tuple[str, str]] = []
    for ref, entry in sorted(entries.items()):
        wants = entry.get("wants", "")
        if ref in declared:
            stale.append((ref, wants))
            continue
        if wants.startswith(SOURCE_GAP):
            # **The same separation the tree half makes, and this half did
            # not.** A `compendium.` want is not work owed: the page does
            # not print what the row would be written from, so no symbol
            # can arrive. `p2621:augment1` is the case -- its Augment 1
            # heading has only a `Special:` line under it -- and it was
            # counted with the blocked ones, which mixes "nobody has done
            # this" with "nobody can" exactly as #360 argued.
            jsourced.append((ref, wants))
            continue
        verdict = _exists(wants, have) if wants else False
        if verdict is None:
            # Prose it cannot parse. **Not the same as blocked** -- it is
            # not known either way, and counting it with the blocked ones
            # is how eleven entries went unchecked while the summary said
            # "0 ready" and two of them were writable.
            unchecked.append((ref, wants))
        elif verdict:
            jready.append((ref, wants, entry.get("why", "")))
        else:
            jwaiting.append((ref, wants, entry.get("why", "")))

    if jready or (not only_ready and (jwaiting or stale)):
        print(f"\n  in {BLOCKED.relative_to(ROOT)}, no row to decorate")
    for ref, wants, why in jready:
        print(f"  READY   {ref:<10} {wants} exists now — {why}")
    if not only_ready:
        for ref, wants, why in jwaiting:
            print(f"  blocked {ref:<10} {wants or '(no method named)'} — {why}")
        for ref, wants in stale:
            print(f"  written {ref:<10} was waiting on {wants}; drop it from the list")
        for ref, wants in jsourced:
            print(f"  source  {ref:<10} {wants} — the page does not print "
                  f"it; nothing to build")

    print(f"\n  tree: {ready} ready, {partial} partial, "
          f"{waiting} still blocked, {sourced} waiting on the compendium")
    if waiting:
        # **The headline that matters.** "1,153 still blocked" reads as a
        # four-figure backlog; a quarter of it is one keyword each. #677.
        want_arg = len(shape["parameter"])
        want_new = len(shape["facility"])
        print(f"  of the {waiting}: {want_arg} want an ARGUMENT on a verb "
              f"that exists, {want_new} want a facility")
        # Unreachable unless `_one` and `_shape_of` disagree about the same
        # symbol, which would be a fault in one of them rather than news
        # about a row. Printed rather than asserted so it cannot be silent.
        if shape["ready"]:
            print(f"  and {len(shape['ready'])} that `_shape_of` calls ready "
                  f"while `_one` calls blocked -- the two disagree: "
                  f"{' '.join(sorted(shape['ready'])[:10])}")
        if want_arg:
            print("  the cheap queue, by ref:")
            for line in _in_columns(sorted(shape["parameter"])):
                print(f"      {line}")

    # **The third bucket, which carries no marker and so was never counted.**
    # See `_premise_rows`: a reading queue, not a ready list. #677.
    claims = _premise_rows()
    if claims:
        print(f"\n  and {len(claims)} row(s) carry NO marker and rest on a "
              f"claim about the engine -- a reading queue, not a ready list:")
        by_phrase: dict[str, list[str]] = defaultdict(list)
        for ref, phrase in claims:
            by_phrase[phrase].append(ref)
        for phrase, refs in sorted(by_phrase.items(),
                                   key=lambda kv: (-len(kv[1]), kv[0])):
            print(f"      {phrase!r:28} {len(refs):>3}  "
                  f"{' '.join(sorted(refs)[:6])}"
                  f"{' …' if len(refs) > 6 else ''}")
    # **The fourth bucket, and the one nothing surfaced at all.** A row may
    # admit its missing clause in prose and declare no marker, which makes it
    # invisible to `todo.py` and to every count above -- #729 measured 369 and
    # found 14 of 14 sampled genuine. One line here rather than the whole list,
    # because `--prose` is where the list belongs and this report is already
    # long; the point of the line is that the number cannot be zero unnoticed.
    drops = _undeclared_drops()
    if drops:
        print(f"\n  and {len(drops)} row(s) admit a dropped clause in prose "
              f"while declaring NO marker -- `--prose` for the list, grouped "
              f"by phrase and by family. #729")

    if capped:
        print(f"  of the {waiting} blocked, {capped} also want something the "
              f"page does not print, so they cannot fully clear")
    print(f"  {BLOCKED.relative_to(ROOT)}: {len(jready)} ready, "
          f"{len(jwaiting)} still blocked, {len(jsourced)} waiting on the "
          f"compendium, {len(stale)} to remove")
    if unchecked:
        # Loud, and a non-zero exit. Printing a line and carrying on was
        # the whole failure: the summary read "0 ready" and nobody
        # noticed that a quarter of the list had not been looked at.
        print(f"  {len(unchecked)} NOT CHECKED -- their `wants` is prose this "
              f"cannot read, so their readiness is unknown:")
        for ref, wants in unchecked:
            print(f"      {ref:<12} {wants[:88]}")
        return 1
    return 0


#: Phrases that make a docstring a **claim about the engine** rather than
#: about the card. Each one has been the whole reason a row was inert, and
#: each has been false at least once:
#:
#: * "light and darkness are not modelled" -- 24 rows, and light had been
#:   modelled for weeks (#686);
#: * "no fight rolls a skill check" -- 24 rows, and a fight rolls thirteen
#:   of them in sixty-three places (#691).
#:
#: The claim that survives says something about the **card** instead -- "the
#: card states no mechanical change either way" -- or about a *circumstance*
#: no board presents. Those cannot go stale, which is the whole distinction.
PREMISE = (
    "not modelled", "no reader", "nothing records", "nothing reads",
    "no fight rolls", "nothing ever", "cannot be asked", "nothing asks",
    "nothing in the engine", "no such", "no training model",
    "no encumbrance", "no inventory",
)

#: **`"there is no"` was on the list above and came off, with its
#: measurement.** It matched 52 rows and read 14 of them: most were correct
#: claims about the *card* or the *circumstance* phrased that way -- "there
#: is no ritual in a fight", "no creature on a board eats anything", "there
#: is no combat clause here to write" -- which is precisely the kind of
#: reason that cannot go stale. Roughly one in ten was an engine claim. A
#: screen at that precision is a list somebody stops reading, which is worse
#: than no screen. The two phrases it was there for are named explicitly
#: instead.
_REJECTED_PHRASE = "there is no"

#: A docstring that **quotes a premise in order to correct it** contains the
#: premise. `f1284` reads *"'There is no training model' was the reason and
#: it stopped being true"* -- a row already fixed, and the first thing this
#: screen reported. So a correction marker anywhere in the docstring takes
#: the row out: the claim has been looked at, which is all this queue is
#: for.
#: **`"the old note"` is the one this tree actually writes**, and it was
#: missing. Measured 2026-10-26 under #625: the phrase occurs **102 times
#: across 68 content files** -- it is the established way an author
#: announces that the reason a row used to carry has been retracted
#: ("the old note said gear handling costs no action", "the old note was
#: right that the sense is granted per watcher and wrong that this cannot
#: be said"). Without it, four rows in `--prose` were honest retractions
#: counted as open admissions.
#:
#: Nine other candidates were tried the same day and waived **nothing**:
#: `re-pointed`, `repointed`, `re-aimed`, `reaimed`, `was stale`,
#: `is now false`, `is fixed`, `no longer it`, `already fixed`. Recorded so
#: they are not re-added on the reasonable-sounding grounds that they
#: ought to match something -- every one of them does, in prose that
#: already contains `"the old note"` too.
CORRECTED = (
    "stopped being true", "was the reason", "is false", "was false",
    "no longer true", "had stopped", "correction", "corrected",
    "and that is false", "turned out", "the old note",
)


#: What a docstring says when it admits a clause is unwritten. Sixteen
#: phrases, taken from #729's hand reading of the shape rather than guessed:
#: the signal is **a prose claim that something is absent**, which is why
#: none of these is a symbol name.
#:
#: `"there is no"` is deliberately absent, for the reason `PREMISE`'s note
#: gives at length -- it matched 52 rows at roughly one-in-ten precision,
#: because most were correct claims about the *card* or the *circumstance*.
ADMITS = (
    "has no method", "is dropped", "are dropped", "is left out",
    "nothing forbids", "no primitive", "cannot be written",
    "has nowhere", "nothing expresses", "is not written",
    "are not written", "no way to say", "nothing to hang",
    "cannot be said", "no facility", "is unwritten",
)

#: Added to `CORRECTED` for this walk only. **This tree's style is to keep
#: the history beside the fix**, so a docstring that says "X was dropped;
#: written now" is a finished row describing its own past -- and counting it
#: is how a report like this becomes a list nobody reads. #729 measured
#: 536 admissions down to 369 by subtracting exactly these.
MENDED = (
    "written now", "is written now", "landed", "re-pointed", "repointed",
    "was wrong", "stale", "closed by", "now writable", "paid",
    "re-aimed", "reaimed", "fixed",
)

#: The six markers a row may carry. A row with any of them is already
#: visible to `todo.py` and to the queue above, so it is not what #729 is
#: about.
MARKERS = ("todo", "dropped", "narrative", "obsolete", "defect", "declined")


def _drops_report() -> int:
    """Print the bucket `_undeclared_drops` finds, grouped three ways.

    **The deliverable of #729**, whose last comment said the report did not
    exist: *"Nothing yet surfaces the 369 except the probe quoted in the
    body."* Three groupings because the bucket is read for three different
    questions -- by phrase to judge the precision of the walk, by family to
    hand a wave to one agent, and the ref list because `spec.py` takes refs.

    **Exit 0 always.** It is a queue and not a gate: this count falls as
    rows are written and rises as rows are written *honestly*, so reddening
    on it would punish the second. `todo.py` is where a marker becoming
    false is a failure.
    """
    rows = _undeclared_drops()
    if not rows:
        print("no row admits a dropped clause while declaring no marker")
        return 0

    print(f"{len(rows)} row(s) admit a dropped clause in prose and declare "
          f"no marker.")
    print("  Neither `todo.py` nor the queue above can see these: a marker "
          "is what both read.")

    by_phrase: dict[str, list[str]] = defaultdict(list)
    for ref, phrase in rows:
        by_phrase[phrase].append(ref)
    print("\n  by what the docstring says:")
    for phrase, refs in sorted(by_phrase.items(),
                               key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"      {phrase!r:22} {len(refs):>4}  "
              f"{' '.join(sorted(refs)[:5])}"
              f"{' …' if len(refs) > 5 else ''}")

    # By family rather than by file: a wave is handed out per directory
    # (`delegating-rows-to-agents` -- partition by file, one agent per), and
    # 355 rows across ~200 files is not a partition anybody can act on.
    where = _families(r for r, _p in rows)
    print("\n  by family:")
    for family, refs in sorted(where.items(),
                               key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"      {family:28} {len(refs):>4}")

    print("\n  every ref, for spec.py:")
    for line in _in_columns(sorted(r for r, _p in rows)):
        print(f"      {line}")
    return 0


def _families(refs: Iterable[str]) -> dict[str, list[str]]:
    """Group refs by the content subdirectory each is declared in.

    One `rglob` rather than a lookup per ref: the registry knows a row's
    module, but this walk has already parsed every file and asking the
    registry would import all 677 of them for a report.
    """
    import ast

    want = set(refs)
    out: dict[str, list[str]] = defaultdict(list)
    root = ROOT / "src" / "combat_engine" / "content"
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        here = path.relative_to(root).parent
        family = str(here) if str(here) != "." else "(top level)"
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                for word in deco.args:
                    # `isinstance(word.value, str)` rather than leaning on
                    # `in want`: a `Constant` can hold a number, and a set of
                    # refs would simply not contain it -- so the test is
                    # already sound and this is what makes it *provably* so.
                    if (isinstance(word, ast.Constant)
                            and isinstance(word.value, str)
                            and word.value in want):
                        out[family].append(word.value)
    return out


def _undeclared_drops() -> list[tuple[str, str]]:
    """Rows admitting a dropped clause in prose while declaring no marker.

    **The bucket both trackers are blind to.** A marker is what `todo.py`
    reports ready and what `blocked.py --group` counts; a row that describes
    its missing clause in the docstring and declares nothing is invisible to
    each. #729 measured 369 of them and read a random 14 by hand: **14 of
    14 were genuine, live, undeclared dropped clauses**, no false positives.

    Returned as `(ref, the phrase that admits it)`, the same shape as
    `_premise_rows`, and for the same reason an `ast` walk rather than a
    grep over the registry: the thing being read is the *source* docstring
    beside the *source* header.

    **A reading queue, not a ready list**, which is the warning
    `_premise_rows` earns the hard way and this inherits. An admission is
    evidence that a clause is missing; whether it is *writable* depends on
    the facility, and of the 14 read by hand only three were writable that
    day.
    """
    import ast

    out: list[tuple[str, str]] = []
    root = ROOT / "src" / "combat_engine" / "content"
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            ref = ""
            marked = False
            decorated = False
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                decorated = True
                for word in deco.args:
                    if isinstance(word, ast.Constant) and isinstance(
                            word.value, str):
                        ref = ref or word.value
                for kw in deco.keywords:
                    if kw.arg in MARKERS:
                        marked = True
            if not (decorated and ref) or marked:
                continue
            said = (ast.get_docstring(node) or "").lower()
            if not said or any(w in said for w in (*CORRECTED, *MENDED)):
                continue
            hit = next((w for w in ADMITS if w in said), "")
            if hit:
                out.append((ref, hit))
    return out


def _premise_rows() -> list[tuple[str, str]]:
    """`out_of_combat=True` rows whose reason is a claim about the engine.

    **The bucket `--ready` cannot see by construction**, and it is the
    biggest one. A row declared inert carries no marker at all, so
    `blocked.py` has never counted one -- and two hand screens found **48**
    of them resting on premises that had stopped being true (#686, #691).

    Returned as `(ref, the phrase that makes it a claim)`. An `ast` walk
    rather than a grep over the built registry, because the thing being
    read is the *source* docstring beside the *source* header, and a row
    whose body is generated by a helper has neither.

    **A reading queue and not a ready list**, which is the one thing to say
    out loud. Of the 24 in #691: 5 were writable, 8 stayed inert on a
    circumstance no board presents, 3 wanted a facility and 1 was already
    right. A false premise does not make a row writable -- the circumstance
    decides -- so this is a list of claims worth checking, not of work.
    """
    import ast

    out: list[tuple[str, str]] = []
    root = ROOT / "src" / "combat_engine" / "content"
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            inert = False
            ref = ""
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                for word in deco.args:
                    if isinstance(word, ast.Constant) and isinstance(
                        word.value, str
                    ):
                        ref = ref or word.value
                for kw in deco.keywords:
                    if kw.arg == "out_of_combat" and isinstance(
                        kw.value, ast.Constant
                    ):
                        inert = bool(kw.value.value)
            if not (inert and ref):
                continue
            said = (ast.get_docstring(node) or "").lower()
            if any(w in said for w in CORRECTED):
                continue
            hit = next((w for w in PREMISE if w in said), "")
            if hit:
                out.append((ref, hit))
    return out


def _in_columns(refs: list[str], per_line: int = 8) -> list[str]:
    """Refs wrapped, so a few hundred of them stay readable."""
    return [
        " ".join(f"{r:<11}" for r in refs[i: i + per_line]).rstrip()
        for i in range(0, len(refs), per_line)
    ]


def _queue(
    marked: list[tuple[str, tuple[str, ...]]],
    entries: dict,
    declared: set[str],
    args: argparse.Namespace,
) -> int:
    """The work queue: every wanted symbol, and who is waiting on it."""
    # A dict per symbol rather than a list: a `wants` sentence that says
    # `dsl.Power.reach and dsl.Power.target` names `dsl.Power` twice, and
    # counting it twice made one entry look like two rows of demand --
    # which is the one number this view exists to get right.
    wanted: dict[str, dict[str, None]] = defaultdict(dict)
    mute = 0
    for ref, todo in marked:
        for want in todo:
            wanted[want.strip()][ref] = None
    for ref, entry in sorted(entries.items()):
        if ref in declared:
            continue
        named = _wants_of(entry.get("wants", ""))
        if not named:
            mute += 1
            continue
        for want in named:
            wanted[want.strip()][ref] = None

    if args.refs:
        # Space separated and nothing else, because the whole use is
        # `spec.py $(blocked.py --refs ...)`. An unknown symbol prints
        # nothing rather than a complaint the shell would paste into argv.
        print(" ".join(wanted.get(args.refs.strip(), ())))
        return 0

    if not wanted:
        print("# nothing outstanding")
        return 0
    width = min(max(len(w) for w in wanted), 44)
    for want in sorted(wanted, key=lambda w: (-len(wanted[w]), w)):
        refs = list(wanted[want])
        shown = ", ".join(refs[:12]) + (f", … and {len(refs) - 12} more"
                                        if len(refs) > 12 else "")
        print(f"  {want:<{width}} ({len(refs):>3} rows): {shown}")
    print(f"\n  {len(wanted)} symbols wanted by {sum(len(v) for v in wanted.values())} rows")
    if mute:
        print(f"  {mute} blocked.json entr(ies) name no symbol at all "
              f"-- run without --group to see them")
    return 0


# --------------------------------------------------------------------------
# What exists, and whether a `wants` names it
# --------------------------------------------------------------------------


#: The names the "wrong module guessed" fallback in `_one` may search by bare name.
#: **Engine-owned only, deliberately.** That fallback exists because a marker names
#: the module it *thinks* a symbol lives in and is often wrong, and it was safe while
#: this index held one package. Widening the index to `chargen` and `spec` made it
#: unsafe: `chargen.spawn` and the `loader.spawn` a marker asks for are different
#: functions that share a name, and matching them reported a row ready on somebody
#: else's symbol. So the index grew and the fallback did not.
_FALLBACK: set[str] = set()

#: The owners that fallback may be used *on*, which is the other half of the same
#: rule and was missing. The pool was engine-only; the *question* was not, so a
#: marker naming `etl.monster.scenery()` searched the engine pool, found
#: `query.scenery` and `dsl.scenery`, and reported the gap closed. That row's own
#: docstring says the opposite -- finding scenery was never the gap, putting a
#: piece of it on the board is, one component away. Same word, different thing,
#: which is what a component boundary means. So the fallback now needs the owner
#: to be engine-owned too.
_ENGINE_OWNERS: set[str] = set()


def _surface() -> dict[str, object]:
    """Everything a row can call, by name, with the thing itself.

    The object and not just the name, because a wanted *parameter* can only
    be checked against a real signature -- see `_exists`.
    """
    sys.argv = sys.argv[:1]
    from combat_engine.engine import cast as cast_mod
    from combat_engine.engine import events, query, triggers

    have: dict[str, object] = {
        f"c.{n}": getattr(cast_mod.Cast, n)
        for n in dir(cast_mod.Cast)
        if not n.startswith("_")
    }
    for mod, prefix in ((query, "query."), (triggers, ""), (events, "")):
        for n in dir(mod):
            if not n.startswith("_"):
                have.setdefault(f"{prefix}{n}", getattr(mod, n))

    # **Every engine module, by its own name.** A marker names a symbol
    # by guessing where it lives, and the guess is often wrong:
    # `query.keywords_of(effect)` sat on nine rows after
    # `durations.keywords_of` had landed, and `todo.py` stayed quiet
    # because the owner it was asked about genuinely does not have that
    # attribute. Silence there is the failure this file exists to break.
    import importlib
    import inspect
    import pkgutil

    import combat_engine.engine as engine_pkg

    for info in pkgutil.iter_modules(engine_pkg.__path__):
        mod = importlib.import_module(f"combat_engine.engine.{info.name}")
        for n in dir(mod):
            if not n.startswith("_"):
                have.setdefault(f"{info.name}.{n}", getattr(mod, n))

    _FALLBACK.clear()
    _FALLBACK.update(have)
    _ENGINE_OWNERS.clear()
    _ENGINE_OWNERS.update(
        {"c"} | {info.name for info in pkgutil.iter_modules(engine_pkg.__path__)}
    )

    # **Not only the engine.** A marker names the owner it thinks a symbol belongs
    # to, and 21 of them -- 148 row-slots -- name `chargen.` or `spec.`, which this
    # index did not cover. So `_one` answered False for every one of them *forever*,
    # whether or not the symbol existed: `chargen` is a real package in this repo,
    # and at least nine `spec.associated_clause()` markers were already satisfied by
    # a brief that carries the clause. That is the same silence this function's own
    # note above was written about, one directory further out.
    import combat_engine.chargen as chargen_pkg

    for n in dir(chargen_pkg):
        if not n.startswith("_"):
            have.setdefault(f"chargen.{n}", getattr(chargen_pkg, n))
    for info in pkgutil.iter_modules(chargen_pkg.__path__):
        mod = importlib.import_module(f"combat_engine.chargen.{info.name}")
        for n in dir(mod):
            if not n.startswith("_"):
                have.setdefault(f"chargen.{n}", getattr(mod, n))
                have.setdefault(f"{info.name}.{n}", getattr(mod, n))

    # **`etl` too, for the same reason and with the same evidence.** A marker
    # naming `etl.monster.scenery()` could not be answered at all while this
    # index stopped at `chargen`, and an unanswerable question went through the
    # fallback and came back "arrived" off a same-named engine function. Covering
    # it makes the answer real: `etl.monster` has no `scenery`, so the row is
    # still blocked, which is what its docstring has said all along. Every etl
    # module imports without the database.
    import combat_engine.etl as etl_pkg

    for info in pkgutil.iter_modules(etl_pkg.__path__):
        mod = importlib.import_module(f"combat_engine.etl.{info.name}")
        have.setdefault(f"etl.{info.name}", mod)
        for n in dir(mod):
            if not n.startswith("_"):
                have.setdefault(f"etl.{info.name}.{n}", getattr(mod, n))

    # `spec.py` is an instrument rather than a component, and it is what a marker
    # means by `spec.`: the brief handed to an author. Sideways rather than downward,
    # and both files already live in `scripts/`.
    try:
        import spec as spec_mod
    except Exception:
        spec_mod = None
    if spec_mod is not None:
        for n in dir(spec_mod):
            if not n.startswith("_"):
                have.setdefault(f"spec.{n}", getattr(spec_mod, n))

    # **A class, by its bare name, because that is how the markers spell it.**
    # A header-field want is written `Target.kind_or_ident`, and nothing in
    # the index above is keyed that way: the walks key a class as
    # `dsl.Target`, so `'Target' in have` is False and `_one` could not
    # answer at all. The resolver already walks two dots --
    # `dsl.Target.kind_or_ident` resolves -- so the blind spot was purely the
    # spelling, which is a smaller thing than #570's comment assumed.
    #
    # The queue is full of header-field wants (`Target.*`, `Gear.*`,
    # `Usage.RECHARGE(when=)`, `Scenery.kind`, `Damage(...)`) and the guard's
    # whole job is this case: `Target.kind_or_ident` landed in `14711d5` and
    # four rows waiting on `Target.any_of` stayed green for two commits,
    # because a field arriving under a name four rows wanted satisfied none
    # of them. It had to be found by reading. #849.
    #
    # The resolver changes rather than the markers, deliberately. Making 10
    # row-slots carry the module would tie a marker to where a class happens
    # to live -- and `_weapon_reach.Damage` shows that is sometimes a private
    # implementation detail, which is not a thing a content row should be
    # naming.
    #
    # **Refused when ambiguous, never resolved to whichever came first.** A
    # bare name meaning two different classes cannot answer, and `setdefault`
    # would have picked by module iteration order and said nothing. 166
    # visible today, 0 ambiguous -- so this costs nothing now and stays sound
    # as the tree grows.
    seen: dict[str, object] = {}
    clash: set[str] = set()
    for key, thing in list(have.items()):
        if "." not in key or not inspect.isclass(thing):
            continue
        bare = key.rpartition(".")[2]
        if bare in seen and seen[bare] is not thing:
            clash.add(bare)
        seen.setdefault(bare, thing)
    for bare, thing in seen.items():
        if bare not in clash:
            have.setdefault(bare, thing)
    return have


def _declared() -> dict:
    sys.argv = sys.argv[:1]
    from combat_engine.content import declared

    return declared()


def _symbols(wants: str) -> list[str]:
    """Every concrete thing a prose `wants` names.

    `c.halt(on=)`, `AttackResult.parity`, `Keyword.RAGE` -- a sentence
    almost always contains the symbol it is waiting for, even when it
    also contains a paragraph about why.

    **The whole dotted path, not its first two segments.** This stopped after
    one dot, so `dsl.Range.by_ability` came out as `dsl.Range` -- a class that
    has existed since before the entry was written, so the entry read *ready*
    from the day it was filed. Every such wait is for a new attribute on an
    existing thing, which is the commonest shape there is, and the instrument
    could not see any of them.

    **And a bare ref counts, which it did not.** `_one` has always been able
    to check one -- a row waiting on another row is the same kind of wait --
    but nothing handed it one out of prose, so an entry whose whole want was
    "the `cf:barbarian-f1s0` row" reported NOT CHECKED for ever. Three of the
    eight unreadable entries named a ref, and one of those three had gone
    stale: `cf:warden-f1-rest` said "four refs nobody has declared" when all
    four were declared, unmarked, and carrying the rider it wanted.
    """
    import re

    out: list[str] = []
    for token in re.findall(r"\b[A-Za-z_][\w.]*\s*\([^)]*\)|\b[a-z_]+(?:\.[A-Za-z_]\w*)+"
                            r"|\b[A-Z][A-Za-z]*(?:\.[A-Za-z_]\w*)+", wants):
        token = token.strip()
        head = token.partition("(")[0].strip()
        # Not a symbol: an English phrase that happens to hold a dot, and
        # the `c.` of a sentence that merely mentions one.
        if (head and "." in head) or token.endswith(")"):
            out.append(token)
    # Refs, in the shapes `_one` recognises. Added after the dotted paths so
    # an entry naming both is checked on both.
    out.extend(re.findall(r"\b(?:cf|rt):[\w-]+|\b[pmifr]\d+[a-z]?\d*\b", wants))
    return out


def _wants_of(wants: str) -> list[str]:
    """The symbols one `wants` string names, whether or not it is prose.

    **Prose is the normal case, not the exception.** 45 of `blocked.json`'s
    46 entries were written as a sentence, because a gap is usually more
    than one symbol. Treating that as unreadable made the whole instrument
    silent; treating it as a name made every one of them report blocked
    forever, which is how `p11603` sat there after the ref it asked for had
    been minted. So the symbols are picked out of the sentence and each is
    checked -- a partial answer that is true beats a total answer that is
    not.

    A `todo=` element never comes through here: `dsl.power` already refuses
    anything but a single symbol, which is the whole reason the marker is
    symbols and not prose.
    """
    head, _, rest = wants.partition("(")
    head = head.strip()
    # `wants` is `name` or `name(param=, param=)`. Prose after the closing
    # bracket makes the parameter list garbage, every check against it
    # fails, and the row reports blocked forever -- which is the silence
    # this file exists to break. 106 rows sat ready behind one such string.
    if " " in head or (rest and not rest.rstrip().endswith(")")):
        return _symbols(wants)
    return [wants.strip()] if head else []


def _one(token: str, have: dict[str, object]) -> bool:
    """Is this single symbol present, with the parameter it asks for?

    A compendium ref -- `p2365`, `cf:cleric-f0`, `rt:r44-t2` -- is looked for in the
    registry rather than on the `Cast` surface. A row waiting on another
    row is the same kind of wait as a row waiting on a method, and the
    instrument should go red on the day either arrives.

    **But a declared row is not a written one, and that distinction is the
    whole of this wait.** `declared()` holds every row that has a header,
    including rows with an empty body carrying markers of their own -- so
    `token in declared()` reported *arrived* for a sibling that has not been
    written. `f2429` is the case: it shortens a distance that is a literal
    inside `cf:rogue-scoundrel-f1s2`'s printed text, and that feature has an
    empty body and waits on two symbols of its own. Its own note says why
    pointing this marker at those symbols instead would be wrong -- it would
    "report this feat ready the day a symbol lands, which is one step early".
    There is nothing to take a chunk out of until the sibling is written.
    So a ref has arrived when it is declared **and not itself unfinished**.

    This narrows a false arrival rather than widening an excuse: a sibling
    that is finished still counts, which is the case the docstring above is
    about.
    """
    import re as _re

    if _re.fullmatch(r"[pmifr]\d+[a-z]?\d*|(?:cf|rt):[\w-]+", token):
        from combat_engine.content import declared

        rows = declared()
        got = rows.get(token)
        return got is not None and not got.unfinished
    head, _, rest = token.partition("(")
    head = head.strip()
    if head in have:
        return _params_ok(head, rest, have)
    if "." in head:
        owner, _, attr = head.rpartition(".")
        thing = have.get(owner)
        if thing is not None and hasattr(thing, attr):
            # **The parameter still has to be there.** Reached this way the
            # answer used to be a bare yes, so a `wants` naming an existing
            # function and a new keyword -- which is most of them -- reported
            # arrived on the function alone.
            return _params_ok_on(getattr(thing, attr), rest)
        # **The marker may have guessed the wrong module.** A symbol is
        # written from memory while the row is being written, so
        # `query.keywords_of` gets named for something that lives in
        # `durations`. The gap is closed either way, and reporting it
        # still blocked is the instrument agreeing with a typo. So the
        # bare name is looked for anywhere on the surface -- but only
        # for a lowercase owner, which is a module: `Dropped.source` is
        # a field on one named class and must not match a `source`
        # somewhere else.
        #
        # **A `c.` method is not a module function and must not satisfy
        # one.** This fallback reported `etl.monster.scenery()` arrived
        # because `c.scenery` exists -- and that row's own docstring says
        # `c.scenery` was never the gap: the gap is that nothing puts a
        # piece of scenery on the board, one component away. The marker
        # had not guessed the wrong module; it had named a different
        # thing with the same word. A row wanting a verb writes
        # `c.verb()`, which the `head in have` test above already
        # answers, so excluding the `c.` keys here costs nothing and
        # stops the one crossing that is never a typo.
        #
        # **And the parameter is checked against whatever it matched.** This
        # answered on the name alone, so `c.deals_half(when=)` reported arrived
        # off `query.deals_half(world, eid)` -- a function that exists and takes
        # no `when`. The whole wait was for that keyword. Asked the other way
        # round, `query.deals_half(when=)`, the same instrument said blocked,
        # correctly: one path checked parameters and the other did not.
        pool = _FALLBACK or have
        engine_owned = owner.split(".")[0] in (_ENGINE_OWNERS or {owner.split(".")[0]})
        if not (owner.islower() and engine_owned):
            return False
        return any(
            (k.endswith(f".{attr}") or k == attr)
            and _params_ok_on(have.get(k), rest)
            for k in pool
            if not k.startswith("c.")
        )
    return False


def _exists(wants: str, have: dict[str, object]) -> bool | None:
    """Is the named thing on the surface, *with* the parameter asked for?

    Returns **None** when the `wants` is prose it cannot read, which is
    neither yes nor no. Returning False there made an unreadable entry
    indistinguishable from a genuinely blocked one, and the summary
    counted both as "still blocked".

    `c.no_provoke(mode=)` is not satisfied by `c.no_provoke` existing -- the
    row wanted the argument, and reporting it ready would send somebody to
    write a line that does not work. Checking the head alone called two
    rows ready that were not.

    That guard was written for `c.` methods and exempted everything else,
    which let the same mistake straight back in by the side door:
    `query.speed(world, eid, ctx)` was reported ready while `query.speed`
    still took two arguments, because the name matched and the parameters
    were never looked at. Anything with a signature is now checked; only a
    bare field on an event, which has none, is taken on its name.

    A dotted name is a *field* on something -- `Dropped.source`,
    `Healed.power`. Those were never resolvable: the surface holds `Dropped`
    and not `Dropped.source`, so the head was simply absent and the row
    stayed blocked after its gap had been closed. `Dropped.source` was
    added and `p11285` went on sitting there, which is the same silence
    this file exists to break, pointing the other way.
    """
    named = _wants_of(wants)
    if not named:
        return None
    # **A container's existence cannot answer a wait for what goes inside it.**
    # Seven entries read READY on `dsl.REGISTRY`, `dsl.Summon`, `chargen.BUILDS`
    # and `etl.sanitise` -- every one a thing that has existed since long before
    # the entry was filed, where the wait is for an *entry in* it: a ref in the
    # registry, a third command on the summon, a leg in the builds, an Augment
    # body in the import. None of those is a symbol, so none of them can be
    # looked up, and answering yes on the container sent a reader to write a row
    # that still cannot be written. That is the `None` case this function
    # already has a name for.
    if all(_is_container(n, have) for n in named):
        return None
    return all(_one(n, have) for n in named)


def _is_container(token: str, have: dict[str, object]) -> bool:
    """Is this token a module, class or plain collection, named bare?

    Bare meaning no parameter clause and no attribute after it -- `dsl.Summon`
    rather than `dsl.Summon.command` or `c.summon(heal=)`. With either of those
    the wait names something that can be absent, and `_one` can answer it.
    """
    head, _, rest = token.partition("(")
    if rest or head not in have:
        return False
    thing = have[head]
    import inspect

    return (
        inspect.ismodule(thing)
        or inspect.isclass(thing)
        or isinstance(thing, dict | tuple | list | set | frozenset)
    )


def _params_ok(head: str, rest: str, have: dict[str, object]) -> bool:
    """Does the named thing take the parameters the `wants` asks for?

    `label=''` and `label=` both mean "it must take a `label`". Taking the
    text before the `=` rather than stripping a trailing one, because a
    written-out default parsed as the parameter name `label=''`, which
    matched nothing -- so twelve rows whose method had existed for hours
    went on reporting themselves blocked.
    """
    import inspect

    wanted = [
        p.split("=")[0].strip() for p in rest.rstrip(")").split(",") if p.strip()
    ]
    if not wanted:
        return True
    try:
        params = inspect.signature(have[head]).parameters  # ty: ignore[invalid-argument-type]
    except (TypeError, ValueError):
        return False         # no signature, so it cannot take one -- see `_params_ok_on`
    return all(p in params for p in wanted)


def _params_ok_on(thing: object, rest: str) -> bool:
    """`_params_ok` against an object already in hand rather than a key.

    The two paths in `_one` that resolve a symbol *without* a surface key --
    `getattr` on a named owner, and the wrong-module fallback -- both used to
    answer on the name alone, so a `wants` for a new keyword on an existing
    function read as arrived. They share this.
    """
    import inspect

    wanted = [
        p.split("=")[0].strip() for p in rest.rstrip(")").split(",") if p.strip()
    ]
    if not wanted:
        return True
    if thing is None:
        return False
    try:
        params = inspect.signature(thing).parameters  # ty: ignore[invalid-argument-type]
    except (TypeError, ValueError):
        # **A thing with no signature cannot take an argument, so the honest
        # answer is no.** This used to read `return True`, waived as "a
        # field, where the name is all there is" -- and the waiver is
        # unreachable for the case it names: a want with no parameter clause
        # returns True at the top of this function, so the only way here is
        # a want that *asks* for a keyword, which a field can never grow.
        #
        # #849 predicted the consequence and `Gear.ranged(thrown=)` is it:
        # `Gear.ranged` is a `property`, `inspect.signature` raises on one,
        # and the want reported **arrived** -- against #838, a real open gap
        # with 86 callers on the melee/ranged pair. The bare-name index
        # above is what would have made that reachable, so the two changes
        # belong in one commit.
        #
        # Measured before tightening: **0** markers resolve True through
        # this branch today, so nothing green goes red and no row's wait is
        # hidden. #838 is the control and stays unresolved.
        return False
    return all(p in params for p in wanted)


if __name__ == "__main__":
    raise SystemExit(main())
