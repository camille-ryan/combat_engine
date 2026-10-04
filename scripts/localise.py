#!/usr/bin/env python
"""What the localisation holds, against what it should.

    uv run scripts/localise.py                  every namespace
    uv run scripts/localise.py --namespace m     one of them
    uv run scripts/localise.py --missing name    which refs lack a field
    uv run scripts/localise.py --all-tiers       beyond heroic too

`localization/names.json` is where every printed name and every line of
printed prose lives, and nothing else in the repository may hold one. #344 asks
for it to be *complete* for heroic tier and then frozen, which needs a number
rather than an opinion -- so this is that number.

**A field present but empty counts as missing.** The same rule `coverage.py`
applies to a row carrying a `todo=`: the only way to move the figure is to fill
the field. An entry reading `{"name": ""}` is not a named entry.

**Relevance is per namespace and is declared once, in `WANTED` below.** A
monster has a possessive because the rules say "the <monster>'s turn"; a power
does not, because nothing possesses through one. Asking every namespace for
every field would report a 40% that means nothing. Asking each for what it
actually needs is the only figure worth freezing.

This instrument reads `game.db` and the localisation and **exercises nothing**
-- no board, no fight -- so it costs milliseconds. The ten-minute instrument is
`audit.py` and this does not touch it.

**Not in `check.py`, for the reason `coverage.py` is not.** It is a work list,
and a work list in the gate is a gate that is red until the work is finished --
which trains people to ignore it. It exits non-zero so a human can use it as a
gate deliberately, and the freeze in #351 is the thing that will.

## Heroic tier, defined once

Three definitions were in the tree when this was written and twelve tables had
none. Camille's: **character options to level 10, monsters to 13** -- a heroic
encounter fields up to party level +3 -- and traps on the same argument.

It costs almost nothing to adopt, which is the useful part: monsters at 13 is
*exactly* the 3,130 already imported, and powers and items are already
heroic-only at the import. Traps are the one real narrowing, 354 of 631. So
nothing is dropped and nothing ends up half-localised.

For feats, `HEROIC` is reused from `coverage.py` rather than respelled, because
**758 heroic feats print no tier line at all** and the fallback to `min_level`
is the thing that gets forgotten.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict

from combat_engine.etl.build import game, localisation

#: Heroic is `tier` when the page printed one and `min_level` when it did not.
#: Lifted from `scripts/coverage.py` deliberately -- one definition, two
#: readers, so they cannot come to disagree about what heroic means.
HEROIC_FEAT = "(tier = 'Heroic' OR (tier = '' AND min_level <= 10))"

#: Character options stop at 10, monsters and traps at 13. A trap is part of an
#: encounter and an encounter is built at party level +3, which is the same
#: argument the monster ceiling rests on.
CHARACTER_CEILING = 10
MONSTER_CEILING = 13


#: Which fields each namespace is asked for, and why it is asked.
#:
#: **The `why` is not decoration.** A field in this table is work somebody has
#: to do by hand -- 2,621 possessives, 4,485 plurals -- and the only defence
#: against asking for a field nobody reads is writing down who reads it.
#:
#: `description` and `rules_text` are a copy from the compendium.
#: `possessive`, `plural` and `aliases` are **not**: no table in the source has
#: an `Alias`, `Short` or `Abbrev` column and no inflected form anywhere, so
#: those three are authored. #350.
WANTED: dict[str, dict[str, str]] = {
    "p": {
        "name": "the page's title, which the card shows",
        "description": "the italic line under the title",
        "rules_text": "the printed Attack/Hit/Effect lines, names intact",
    },
    "m": {
        "name": "what the board calls the creature",
        "rules_text": "the printed stat block",
    },
    "f": {
        "name": "the feat's title",
        "description": "the prose above the benefit",
        "rules_text": "the printed Prerequisite and Benefit",
    },
    "i": {
        "name": "the item's title",
        "description": "the prose teaser the page prints",
        "plural": "a character carries several of some items",
    },
    "r": {
        "name": "the race's title",
        "description": "the page's own prose section",
        "possessive": "'the <race>'s racial power' is a printed phrase",
        "plural": "a warband is described in the plural",
    },
    "c": {
        "name": "the class's title",
        "description": "the prose the class page opens with",
        "possessive": "'the <class>'s features' is how the books refer to them",
    },
    "w": {
        "name": "what the weapon is called",
        "plural": "a character may carry two of the same weapon",
    },
    "cf:": {
        "name": "the feature's printed heading",
        "rules_text": "the printed benefit",
    },
    "comp:": {
        "name": "what the companion is called",
        "possessive": "'your <companion>'s attack' is a printed phrase",
        "aliases": "a stat block names a companion by a fragment",
    },
    "t:": {
        "name": "what the trap is called",
        "rules_text": "the printed trigger, attack and countermeasures",
    },
    "rt:": {
        "name": "the trait's printed label",
        "rules_text": "the printed trait text",
    },
}

#: Namespaces that carry a name and nothing else, on purpose.
#:
#: `x` is every other compendium page -- rituals, deities, themes, paragon
#: paths, diseases. **None is imported as a row and none ever will be**, and
#: they exist in the localisation only so the scrubber can recognise the name
#: and `leaks.py` can report it. Asking them for rules text would be asking for
#: 4,698 rows of a game the engine does not play.
#:
#: `q` is a prerequisite *term* -- a printed phrase a feat asks for. 227 of the
#: 308 carry no name and that is correct: the phrase is the content.
NAME_ONLY = ("x", "q")


def _heroic_refs(db, all_tiers: bool) -> dict[str, set[str]]:  # noqa: ANN001
    """Every ref in scope, by namespace.

    The ceilings are applied here and nowhere else, so "heroic" has one
    meaning in this instrument. `monster_power` and `item_block` inherit their
    parent's level -- an ability is in scope exactly when its creature is --
    which is why neither is filtered directly.
    """
    char_cap = 99 if all_tiers else CHARACTER_CEILING
    mon_cap = 99 if all_tiers else MONSTER_CEILING
    out: dict[str, set[str]] = defaultdict(set)

    def take(ns: str, sql: str, *params: object) -> None:
        for (ref,) in db.execute(sql, params):
            out[ns].add(ref)

    take("p", "SELECT ref FROM power WHERE level <= ?", char_cap)
    take("m", "SELECT ref FROM monster WHERE level <= ?", mon_cap)
    take("m", "SELECT mp.ref FROM monster_power mp JOIN monster m "
              "ON mp.ref LIKE m.ref || 'a%' WHERE m.level <= ?", mon_cap)
    take("i", "SELECT ref FROM item WHERE base_level <= ?", char_cap)
    take("t:", "SELECT ref FROM trap WHERE level <= ?", mon_cap)
    if all_tiers:
        take("f", "SELECT ref FROM feat")
    else:
        take("f", f"SELECT ref FROM feat WHERE {HEROIC_FEAT}")
    # No level in the source at all: available from level 1, so all are in.
    for ns, table in (("r", "race"), ("c", "class"), ("cf:", "class_feature"),
                      ("comp:", "companion"), ("w", "weapon")):
        take(ns, f"SELECT ref FROM {table} WHERE ref IS NOT NULL")
    return out


#: Fields that are still stored under an older name.
#:
#: `description` is `flavour` until #348 renames it -- and that rename waits on a
#: bug, because `flavour` currently holds **rules text** for monsters and feats.
#: Counting `flavour` as `description` here is the honest reading: the prose is
#: present for 31% of entries and the field it sits in is simply misnamed, so
#: reporting 0% would describe work that is already done.
#:
#: The alias goes away with the rename. `localise.py --missing description` is
#: what says whether it still has anything to do.
ALIASED = {"description": ("flavour",)}


def _filled(entry: dict, field: str) -> bool:
    """Is this field actually there?

    Empty is missing, and a list has to have something in it. `aliases` is the
    only list-valued field and `[]` means nobody recorded one, which is exactly
    the state this instrument exists to count.
    """
    for key in (field, *ALIASED.get(field, ())):
        value = entry.get(key)
        if isinstance(value, (list, tuple, set)):
            if value:
                return True
        elif isinstance(value, str):
            if value.strip():
                return True
        elif value:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--namespace", help="only this one, e.g. m or cf:")
    ap.add_argument("--missing", help="list the refs lacking this field")
    ap.add_argument("--all-tiers", action="store_true",
                    help="beyond heroic too, so the ceiling can be seen")
    args = ap.parse_args()

    names = localisation()
    if not names:
        print("localization/names.json is missing. Run: uv run scripts/build.py")
        return 1

    db = game()
    scope = _heroic_refs(db, args.all_tiers)
    wanted = WANTED if not args.namespace else {
        k: v for k, v in WANTED.items() if k == args.namespace
    }
    if args.namespace and not wanted:
        print(f"no namespace {args.namespace!r}; known: {', '.join(WANTED)}")
        return 1

    missing: dict[str, list[str]] = defaultdict(list)
    width = max(len(k) for k in wanted) if wanted else 4
    print(f"  {'':{width}}  {'rows':>6}  field        filled   of    missing")
    rows_total = filled_total = asked_total = 0

    for ns in sorted(wanted):
        refs = sorted(scope.get(ns, ()))
        if not refs:
            continue
        rows_total += len(refs)
        first = True
        for field, _why in wanted[ns].items():
            have = [r for r in refs if _filled(names.get(r) or {}, field)]
            gap = [r for r in refs if r not in set(have)]
            asked_total += len(refs)
            filled_total += len(have)
            pct = 100 * len(have) / len(refs)
            label = ns if first else ""
            count = f"{len(refs)}" if first else ""
            first = False
            print(f"  {label:{width}}  {count:>6}  {field:<11} "
                  f"{pct:5.0f}%  {len(refs):>5}  {len(gap):>6}")
            if gap:
                missing[field].extend(gap)

    print()
    overall = 100 * filled_total / asked_total if asked_total else 100.0
    print(f"  {filled_total} of {asked_total} fields filled across "
          f"{rows_total} rows -- {overall:.1f}%")
    tier = "every tier" if args.all_tiers else (
        f"heroic: character options to {CHARACTER_CEILING}, "
        f"monsters and traps to {MONSTER_CEILING}")
    # **Never a bare percentage.** `coverage.py` learned this the hard way: its
    # monster figure read 100% against a fifth of the corpus and nothing on the
    # line said which fifth. An instrument that scopes itself prints the scope.
    print(f"  counting {tier}")
    if ALIASED:
        for field, older in ALIASED.items():
            print(f"  {field} is still stored as {' or '.join(older)}; #348 renames it")

    for ns in NAME_ONLY:
        held = [r for r in names if re.match(rf"^{re.escape(ns)}\d", r)]
        named = [r for r in held if _filled(names[r], "name")]
        print(f"  {ns}: {len(named)} of {len(held)} named, and nothing else "
              f"asked of them -- see NAME_ONLY")

    if args.missing:
        refs = sorted(set(missing.get(args.missing, ())))
        print(f"\n  {len(refs)} refs with no {args.missing}:")
        for ref in refs[:60]:
            print(f"    {ref}")
        if len(refs) > 60:
            print(f"    ... and {len(refs) - 60} more")

    return 0 if filled_total == asked_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
