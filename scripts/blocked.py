#!/usr/bin/env python
"""Rows left out of the tree, and what each is waiting for.

    uv run scripts/blocked.py           what is blocked, and what is ready now
    uv run scripts/blocked.py --ready   only the ones that have become writable

A row that cannot be written is left absent rather than half-written, and
`coverage.py` counts the hole. What nothing recorded was *why* — that lived
in the wave's report, which is ephemeral, and in an issue comment, which is
not queryable. So when a method was finally built, the rows that had been
waiting for it stayed missing until somebody happened to remember.

Three level-5 rows sat blocked on `c.moving_as` for four levels after it was
built, which is what this exists to stop.

The list is hand-maintained, because the reason a row was skipped is a
judgement a person made and no tool can recover it. Adding an entry is the
last step of leaving a row out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCKED = ROOT / "docs" / "blocked.json"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ready", action="store_true", help="only what is now writable")
    args = ap.parse_args()

    if not BLOCKED.exists():
        print(f"# {BLOCKED.relative_to(ROOT)} does not exist yet")
        return 0

    entries = json.loads(BLOCKED.read_text())
    have = _surface()
    declared = _declared()

    ready, waiting, stale, unchecked = [], [], [], []
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
            ready.append((ref, wants, entry.get("why", "")))
        else:
            waiting.append((ref, wants, entry.get("why", "")))

    for ref, wants, why in ready:
        print(f"  READY   {ref:<10} {wants} exists now — {why}")
    if not args.ready:
        for ref, wants, why in waiting:
            print(f"  blocked {ref:<10} {wants or '(no method named)'} — {why}")
        for ref, wants in stale:
            print(f"  written {ref:<10} was waiting on {wants}; drop it from the list")

    print(f"\n  {len(ready)} ready, {len(waiting)} still blocked, {len(stale)} to remove")
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


def _declared() -> set[str]:
    sys.argv = sys.argv[:1]
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    return set(REGISTRY)



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

    head, _, rest = wants.partition("(")
    head = head.strip()
    # `wants` is `name` or `name(param=, param=)`. Prose after the closing
    # bracket makes the parameter list garbage, every check against it
    # fails, and the row reports blocked forever -- which is the silence
    # this file exists to break, so it is said out loud instead. 106 rows
    # sat ready behind one such string.
    # **Prose is the normal case, not the exception.** 45 of 46 entries
    # are written as a sentence, because a gap is usually more than one
    # symbol. Treating that as unreadable made the whole instrument
    # silent; treating it as a name made every one of them report
    # blocked forever, which is how `p11603` sat there after the ref it
    # asked for had been minted. So the symbols are picked out of the
    # sentence and each is checked -- a partial answer that is true
    # beats a total answer that is not.
    if " " in head or (rest and not rest.rstrip().endswith(")")):
        named = _symbols(wants)
        if not named:
            return None
        missing = [n for n in named if not _one(n, have)]
        return not missing
    if head not in have and "." in head:
        owner, _, attr = head.rpartition(".")
        thing = have.get(owner)
        return thing is not None and hasattr(thing, attr)
    if head not in have:
        return False
    return _params_ok(head, rest, have)


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
