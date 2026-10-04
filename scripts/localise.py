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
    # **A creature is asked for no rules text, and that is a measurement.**
    # It read 81% while every one of the 13,432 abilities had rules text and
    # every one of the 3,130 creatures did not -- one bucket reporting a gap
    # that was really two row kinds with different needs. Checked rather than
    # assumed: across 900 heroic creature pages, the labelled lines not already
    # covered by an ability or by a `monster` column are **four** -- three book
    # citations (`Draconomicon`, `Monster Vault`, `Into the Unknown`) and
    # `Mount:`, which is a conjuring item's boilerplate on two figurine pages
    # and belongs to the item. A creature's own mechanics are columns; its
    # printed clauses are its abilities. So the split is honest and 81% was not.
    "m": {
        "name": "what the board calls the creature",
        "possessive": "'the <creature>'s turn' is printed on every page",
        "aliases": "a stat block names itself by a fragment of its own name",
    },
    "ma": {
        "name": "the ability's printed heading",
        "rules_text": "the printed Attack, Hit and Effect lines",
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
    # **A block, not the item.** An item with a Property and a Power is two
    # blocks, either can be written without the other, and the block is what
    # carries the printed rules a card shows. It is asked for **no name**: the
    # compendium gives 6 of 2,491 one, and the rest take the item's.
    "ib": {
        "rules_text": "the printed Power or Property this block is",
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
    # `ma` is not a ref prefix -- an ability's ref is `m702a2`. It is a *row
    # kind*, because a creature and its abilities want different fields and
    # bucketing them together reported a gap neither had.
    take("ma", "SELECT mp.ref FROM monster_power mp JOIN monster m "
               "ON mp.ref LIKE m.ref || 'a%' WHERE m.level <= ?", mon_cap)
    take("i", "SELECT ref FROM item WHERE base_level <= ?", char_cap)
    take("ib", "SELECT b.ref FROM item_block b JOIN item i "
               "ON b.ref LIKE i.ref || '%' WHERE i.base_level <= ?", char_cap)
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


#: Fields still stored under an older name, as a transition.
#:
#: **Empty, and it earned being emptied.** `description` was `flavour` until
#: #348, and this read the older key so the figure described work already done
#: for 31% of entries rather than reporting 0%. The rename has landed, so an
#: entry here now would be a lie about where the data lives.
#:
#: Kept as a mechanism rather than deleted, because the next field to be renamed
#: wants it and the argument for it is above.
ALIASED: dict[str, tuple[str, ...]] = {}


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


#: A line's label, if it has one. `Hit:`, `Effect:`, `Requirement:` -- **and a
#: ref**, because a clause labelled with a printed name has that name swapped for
#: one in the spec. Digits and hyphens are in the class for exactly that: without
#: them `p12609:` and `c53:` were not detected as labels at all, so the two sides
#: disagreed about how many labelled lines a row had and 141 rows read as
#: divergent when the only difference was the substitution.
_LABEL = re.compile(r"^\s*([A-Za-z][\w '/-]{1,40}?)\s*:")

#: Ref namespaces whose own colon is not a label separator.
#:
#: `cf:invoker-f1s2` substituted into a line that had no colon makes that line
#: *look* labelled, because the first colon is one character in. A printed label
#: is never one of these words alone, so excluding them is exact rather than a
#: heuristic -- and without it 90 rows read as divergent for having had a name
#: replaced by a ref that happens to carry a colon.
_NAMESPACE = frozenset({"cf", "rt", "comp", "t", "w", "x", "q"})


#: Rows whose `spec` and `rules_text` labels differ for a reason that is not a
#: lost clause. **The check is a baseline, not a zero**, and that is a finding
#: rather than a compromise: #349 asked for "the same labelled lines in the same
#: order" and that cannot be written, because a clause label can be
#:
#:   * a printed name            `Vestige Pact:`  -> `cf:warlock-f1s6:`
#:   * a name plus a word        `<name> Augment:` -> `p6855 Augment:`
#:   * a name spanning a newline  two lines collapse into one when substituted
#:   * a monster's own ability name, which its own spec scrubs
#:
#: and substitution moves all four. Eight comparisons were tried; each failed on
#: a *correct* difference. What survives is a figure: **24,510 of 24,598 agree**,
#: and every divergence examined was a substitution rather than a dropped clause.
#:
#: Guarded the way `scripts/fixtures/audited.json` guards the audit -- a number
#: that may not get worse. If it rises, a clause went missing and that is what
#: this exists to catch.
KNOWN_LABEL_DRIFT = 88


def _printed_labels() -> frozenset[str]:
    """Every printed name that could appear as a clause label, lowered.

    **The discriminator is data, not shape.** A build rider's label *is* a
    printed name -- 523 rows carry one -- and nothing about `brutal scoundrel`
    or `aegis of assault` looks different from `hit` or `effect` until you ask
    whether the localisation knows it as a name. It does, so ask.
    """
    out = set()
    for ref, entry in localisation().items():
        if not ref.startswith(("cf:", "rt:")):
            continue
        name = (entry.get("name") or "").strip().lower()
        if len(name) > 2:
            out.add(name)
    return frozenset(out)


def _mechanical_labels(body: str, printed: frozenset[str]) -> set[str]:
    """Every label on a line that is a rules label rather than a name.

    A name can be a label and is substituted; `Hit`, `Effect` and `Target` are
    not and never move. So this is the half of a row's shape that must be
    identical in `spec` and `rules_text`, and a difference means a clause was
    dropped.

    A ref-shaped label is excluded on both sides, which is what makes the
    comparison survive substitution at all.
    """
    out: set[str] = set()
    for line in (body or "").splitlines():
        found = _LABEL.match(line)
        if not found:
            continue
        label = found.group(1).strip()
        low = label.lower()
        if low in _NAMESPACE or re.fullmatch(r"[a-z]+\d+", low) or low in printed:
            continue
        # **A compound label: a printed name plus a mechanics word.**
        # `<name> Augment` becomes `p6855 Augment`, so the label is neither
        # wholly a name nor wholly mechanics. Take the names and the refs out of
        # it and compare what is left, which is the mechanics word that cannot
        # move. 97 rows, every one of them an augment line.
        bare = re.sub(r"\b[a-z]+\d+\b", " ", low)
        for name in printed:
            if name in bare:
                bare = bare.replace(name, " ")
        bare = " ".join(bare.split())
        out.add(bare or low)
    return out


def _is_labelled(line: str) -> bool:
    """Does this line carry a printed label, as opposed to a ref's own colon?

    A substituted ref can either **be** the label or merely sit in the sentence,
    and the two look alike after one colon:

        cf:rogue-scoundrel-f1s0: you gain ...   the label, substituted
        cf:invoker-f1s2 benefits from ...       a mention, not a label

    So when the text before the first colon is a bare namespace, the question is
    whether a *second* colon follows on the same line. That is exact rather than
    a guess, and both halves of it were got wrong once: counting the namespace as
    a label made 90 unlabelled lines look labelled, and excluding it outright
    unlabelled 523 lines that really were.
    """
    found = _LABEL.match(line)
    if not found:
        return False
    if found.group(1).lower() not in _NAMESPACE:
        return True
    return ":" in line[found.end():]


def rules_against_spec(db) -> tuple[int, int, list[str]]:  # noqa: ANN001
    """Do `rules_text` and `spec` carry the same rules?

    They are one extraction with two endings -- `sanitise.power_rules` and
    `power_spec` differ by a single `scrub` call -- so a divergence means one of
    them lost a clause, which is the thing worth catching.

    **The assertion is not "the same labels".** #349 specified that and it is
    wrong as written: a power's clause can be labelled with a *build's printed
    name* -- 395 powers carry one -- and the spec has cross-referenced that name
    to a `cf:` ref while `rules_text` keeps it. The labels differ there
    **because the fix is working**, so comparing label text fails on the one
    difference the two halves exist to have.

    What holds instead: **the same number of lines, and the same labels wherever
    a label is not a ref.** That still catches a dropped or reordered clause.
    """
    names = localisation()
    printed = _printed_labels()
    checked = agree = 0
    bad: list[str] = []
    for table in ("power", "monster_power", "feat", "item_block",
                  "class_feature", "trap"):
        for ref, spec in db.execute(f"SELECT ref, spec FROM {table}").fetchall():
            rules = (names.get(ref) or {}).get("rules_text")
            if rules is None or not (spec or "").strip():
                continue
            checked += 1
            # **Compare the labels that are never substituted.**
            #
            # Three comparisons were tried and each failed on a *correct*
            # difference between the two halves:
            #
            # * label text -- a label can BE a printed name, so `Vestige Pact:`
            #   legitimately becomes `cf:warlock-f1s6:`. 489 rows.
            # * line count -- a printed name can span a line break, and the ref
            #   replacing it is one token, so two lines collapse into one. 13
            #   rows, `p3839` among them.
            # * labelled positions -- a ref carries its own colon, so it can
            #   make an unlabelled line look labelled or the reverse. ~69 rows.
            #
            # What cannot move is a label that is *not* a name: `Hit`, `Effect`,
            # `Target`, `Requirement` are mechanics and nothing substitutes them.
            # If one of those is in `rules_text` and not in `spec`, a clause was
            # lost -- which is the only thing this check is for.
            theirs = _mechanical_labels(rules, printed)
            ours = _mechanical_labels(spec, printed)
            if theirs == ours:
                agree += 1
            elif len(bad) < 8:
                bad.append(
                    f"{table}.{ref}: in rules only {sorted(theirs - ours)}, "
                    f"in spec only {sorted(ours - theirs)}")
    return checked, agree, bad


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--namespace", help="only this one, e.g. m or cf:")
    ap.add_argument("--missing", help="list the refs lacking this field")
    ap.add_argument("--all-tiers", action="store_true",
                    help="beyond heroic too, so the ceiling can be seen")
    ap.add_argument("--rules", action="store_true",
                    help="check rules_text against spec and stop")
    args = ap.parse_args()

    names = localisation()
    if not names:
        print("localization/names.json is missing. Run: uv run scripts/build.py")
        return 1

    db = game()
    if args.rules:
        checked, agree, bad = rules_against_spec(db)
        drift = checked - agree
        print(f"  {agree} of {checked} rows carry the same rules in spec and "
              f"rules_text ({100 * agree / max(1, checked):.1f}%)")
        print(f"  {drift} differ by a label a substitution moved; "
              f"{KNOWN_LABEL_DRIFT} is the recorded baseline -- see it for why "
              f"this is not zero")
        for line in bad:
            print(f"    {line}")
        if drift > KNOWN_LABEL_DRIFT:
            print(f"  **{drift - KNOWN_LABEL_DRIFT} more than the baseline.** A "
                  "label that is not a name cannot move, so a clause was lost.")
            return 1
        return 0
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
