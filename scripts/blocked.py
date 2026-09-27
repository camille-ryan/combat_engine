#!/usr/bin/env python
"""Rows that are not finished, and what each is waiting for.

    uv run scripts/blocked.py                   what is outstanding, and what is ready now
    uv run scripts/blocked.py --ready           only the ones that have become writable
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
    args = ap.parse_args()

    rows = _declared()
    marked = [(ref, tuple(p.todo)) for ref, p in sorted(rows.items()) if p.todo]
    entries = json.loads(BLOCKED.read_text()) if BLOCKED.exists() else {}

    if args.group or args.refs:
        return _queue(marked, entries, set(rows), args)

    have = _surface()
    return _report(marked, entries, set(rows), have, args.ready)


# --------------------------------------------------------------------------
# The two sources, reported apart
# --------------------------------------------------------------------------


def _report(
    marked: list[tuple[str, tuple[str, ...]]],
    entries: dict,
    declared: set[str],
    have: dict[str, object],
    only_ready: bool,
) -> int:
    ready = partial = waiting = 0
    lines: list[str] = []
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
        else:
            waiting += 1
            if not only_ready:
                lines.append(f"  blocked {ref:<10} {', '.join(todo)}")
    if lines:
        print("  in the tree, marked `todo=`")
        print("\n".join(lines))

    jready, jwaiting, stale, unchecked = [], [], [], []
    for ref, entry in sorted(entries.items()):
        wants = entry.get("wants", "")
        if ref in declared:
            stale.append((ref, wants))
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

    print(f"\n  tree: {ready} ready, {partial} partial, {waiting} still blocked")
    print(f"  {BLOCKED.relative_to(ROOT)}: {len(jready)} ready, "
          f"{len(jwaiting)} still blocked, {len(stale)} to remove")
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
    """
    import re

    out: list[str] = []
    for token in re.findall(r"\b[A-Za-z_][\w.]*\s*\([^)]*\)|\b[a-z_]+\.[A-Za-z_]\w*"
                            r"|\b[A-Z][A-Za-z]*\.[A-Za-z_]\w*", wants):
        token = token.strip()
        head = token.partition("(")[0].strip()
        # Not a symbol: an English phrase that happens to hold a dot, and
        # the `c.` of a sentence that merely mentions one.
        if (head and "." in head) or token.endswith(")"):
            out.append(token)
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
    """Is this single symbol present, with the parameter it asks for?"""
    head, _, rest = token.partition("(")
    head = head.strip()
    if head in have:
        return _params_ok(head, rest, have)
    if "." in head:
        owner, _, attr = head.rpartition(".")
        thing = have.get(owner)
        return thing is not None and hasattr(thing, attr)
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
    return all(_one(n, have) for n in named)


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
        params = inspect.signature(have[head]).parameters  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True          # not callable: a field on an event, name is all we have
    return all(p in params for p in wanted)


if __name__ == "__main__":
    raise SystemExit(main())
