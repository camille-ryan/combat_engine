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
    marked = [
        (ref, tuple(p.unfinished))
        for ref, p in sorted(rows.items())
        if p.unfinished
    ]
    entries = json.loads(BLOCKED.read_text()) if BLOCKED.exists() else {}

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

#: Symbols that will never arrive **by decision**, with whose call it was.
#:
#: The third reason a row can be stuck, and the queue has to tell it from the
#: other two: `SOURCE_GAP` above is "the page does not print it", `waiting` is
#: "nobody has built it", and this is "nobody is going to".
#:
#: A row whose *whole* benefit is declined work carries `declined=` and never
#: reaches this list -- it is refused in play and is not in `unfinished` at
#: all. This is for the other case, which `content/CLAUDE.md` is explicit
#: about for `defect=` and which holds here for the same reason: four of the
#: Fortune Card items grant a working skill bonus and only their card clause
#: is declined, so they keep `dropped=` and keep playing. Marking them
#: `declined=` would have refused four rows that work.
DECLINED = {
    "Fortune.deck": "Fortune Cards are out of scope: Camille's call, "
                    "2026-10-09 (#482)",
}


def _report(
    marked: list[tuple[str, tuple[str, ...]]],
    entries: dict,
    declared: set[str],
    have: dict[str, object],
    only_ready: bool,
) -> int:
    ready = partial = waiting = sourced = capped = declined = 0
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
        elif all(w in DECLINED for w in todo):
            # **Declined is not blocked either.** The row plays and the one
            # clause it is missing is a clause nobody intends to write, so
            # counting it with the unstarted rows overstates the backlog by
            # exactly as much as the compendium rows did before #360.
            declined += 1
            if not only_ready:
                why = DECLINED[todo[0]]
                lines.append(f"  declined {ref:<9} {', '.join(todo)} — {why}")
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

    print(f"\n  tree: {ready} ready, {partial} partial, "
          f"{waiting} still blocked, {sourced} waiting on the compendium, "
          f"{declined} declined")
    if capped:
        print(f"  of the {waiting} blocked, {capped} also want something the "
              f"page does not print, so they cannot fully clear")
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
    """
    import re as _re

    if _re.fullmatch(r"[pmifr]\d+[a-z]?\d*|(?:cf|rt):[\w-]+", token):
        from combat_engine.content import declared

        return token in declared()
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
        params = inspect.signature(have[head]).parameters  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True          # not callable: a field on an event, name is all we have
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
        params = inspect.signature(thing).parameters  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True          # not callable: a field, where the name is all there is
    return all(p in params for p in wanted)


if __name__ == "__main__":
    raise SystemExit(main())
