#!/usr/bin/env python
"""Every build a row asks about, against the builds a character can take.

    uv run scripts/legs.py
    uv run scripts/legs.py --class invoker

`c.build("wrath")` and `requires=on_leg("wrath")` are how a row says "this
half of the card only applies to one leg of the fork". Both answer False
for a leg that does not exist -- so a rider naming a build nobody can
take is not an error, it is simply never true, in every fight, forever.

That is the failure this repository keeps finding: the row is written,
the tests pass, the audit sees it fire, and the clause does nothing. 118
riders were in that state when this was written, across seven classes --
the invoker's three covenants, the warden's four, the shaman's spirits,
the avenger's cf:avenger-f1 set, the warlord's three commands. Every one had been
written against legs that were never added.

The reverse is checked too. A leg no row asks about is usually harmless,
but it is how a *renamed* leg shows up: one was called `ensnaring` here
while six rows asked for `ensnarement`, an hour after being added.

**A row under `features/` is attributed by its own `cls=`, not by its
path.** This read the directory alone and answered "" for every row in
`content/features/`, so none of them was checked against anything --
which is how `cf:warden-f1` and `cf:avenger-f1` went on asking for the
derived `second-<ability>` legs for months after both classes were given
named ones. Two class features, dead on every leg, under a script written
to find exactly that.
"""

from __future__ import annotations

import argparse
import ast
import collections
import pathlib
import sys
from collections.abc import Iterator

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTENT = ROOT / "src" / "combat_engine" / "content"


def asked() -> dict[str, collections.Counter]:
    """Every build name a row names, by the class whose row names it.

    Read with `ast` rather than by regex: `c.build(...)` is frequently
    inside a lambda or a comprehension, and the one thing a regex here
    reliably does is skip those.
    """
    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for path in sorted(CONTENT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:          # a tree mid-write; say so rather than lie
            print(f"# {path}: does not parse", file=sys.stderr)
            continue
        by_path = _class_of(path)
        for owner, cls in _owners(tree):
            for node in ast.walk(owner):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name not in ("build", "on_leg"):
                    continue
                value = getattr(node.args[0], "value", None)
                if isinstance(value, str):
                    out[cls or by_path][value] += 1
    return out


def _owners(tree: ast.Module) -> Iterator[tuple[ast.FunctionDef, str]]:
    """Every top-level function, with the class its decorator declares.

    A helper with no decorator of its own is attributed to nothing and
    falls back to the path -- which is right: a module-level `_beside(c)`
    under `powers/warlord/` is a warlord's.

    **And a `cf:` ref names its class, which this did not read.**
    `_class_of`'s docstring already said rows under `features/` are
    *"attributed by the ref they are declared with instead -- that is the
    only honest answer"*, and nothing here did it: only `cls=` was read, so
    every row in `features/` came back attributed to no class at all.

    That made the ambiguity check below report **2 findings that were not
    faults** -- `c.build('shielding')` on `cf:warlord-marshal-f1` and
    `c.build('elemental')` on a shaman's and a warlock's own feature rows.
    All three are scoped by their ref; the instrument could not see it.
    With the ref read, the check is **0** and the two are correctly quiet.
    #235.
    """
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        cls, marked = "", False
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            first = dec.args[0] if dec.args else None
            ref = getattr(first, "value", None)
            for kw in dec.keywords:
                value = getattr(kw, "value", None)
                if kw.arg == "cls" and isinstance(value, ast.Constant):
                    cls = value.value or ""
                # A row that names a missing leg **and says so** is not the
                # failure this hunts: `todo=("chargen.BUILDS",)` is the
                # author declaring the leg absent, and it goes red in
                # `todo.py` the day one arrives.
                if kw.arg in ("todo", "dropped"):
                    marked = marked or "chargen.BUILDS" in ast.dump(value)
            # **After the keywords, not before, and that ordering is the
            # whole of it.** The ref is only a fallback for a row that
            # declares no class -- but `cls=""` is an explicit keyword, so
            # inferring first and then reading the keywords put the empty
            # string straight back and the fallback did nothing. It cost
            # one debugging pass and read exactly like the lookup failing.
            if isinstance(ref, str) and not cls:
                cls = (_class_in_ref(ref) if ref.startswith("cf:")
                       else _one_class_in_prereq(ref))
        if not marked:
            yield node, cls


def _class_in_ref(ref: str) -> str:
    """The class a `cf:` ref names, or `""`.

    Matched against `chargen.BUILDS`' own keys **longest first**, not by
    splitting on the first hyphen: a chassis segment is hyphenated too
    (`cf:wizard-sha-ir-f0`), so a split would answer `wizard` by luck here
    and something wrong the first time a class slug carries a hyphen.
    """
    from combat_engine import chargen

    body = ref[len("cf:"):]
    for cls in sorted(chargen.BUILDS, key=len, reverse=True):
        if body == cls or body.startswith(f"{cls}-"):
            return cls
    return ""


def ambiguous() -> list[tuple[str, str, int, list[str]]]:
    """Readers of a leg name that more than one class owns, unscoped. #235.

    `Build.name` is an **identity** -- it is what `c.build("two-blade")`
    gates on -- and it does not identify a leg. Measured over all of
    `chargen.BUILDS`:

        99 legs, 76 distinct names
        13 names owned by MORE THAN ONE class

    `f1s0` belongs to four classes at once (assassin, bard, druid, warden)
    and `f0s2` to four more. `query.on_build` resolves by **string**
    against `Build.choices` with no class scoping at all, so the name alone
    cannot say which leg is being asked about.

    **It is latent rather than live, and that was checked rather than
    assumed.** Every reader today is reached through a class-scoped ref or
    a printed prerequisite naming the class: the sharpest candidate was
    `f2413`, a feat with `cls=""` reading `c.build('shielding')`, which the
    swordmage also owns -- and its printed prereq is
    `{"all": [{"class": "warlord"}, ...]}`, so `legal_feats` offers it to
    none of the swordmage's three legs. Verified.

    So this is the gate that keeps it latent: a reader of an ambiguous name
    must be attributable to a class that owns the name. Nothing enforced
    that, which is why it is worth a check rather than a comment -- the
    first unscoped one would read exactly like the twenty-two scoped ones.
    """
    from combat_engine import chargen

    owners: dict[str, set[str]] = collections.defaultdict(set)
    for cls, builds in chargen.BUILDS.items():
        for leg in builds:
            owners[leg.name].add(cls)
    shared = {name for name, who in owners.items() if len(who) > 1}

    out: list[tuple[str, str, int, list[str]]] = []
    for cls, names in sorted(asked().items()):
        for name, count in sorted(names.items()):
            if name in shared and (not cls or cls not in owners[name]):
                out.append((cls or "(no class)", name, count,
                            sorted(owners[name])))
    return out


def _one_class_in_prereq(ref: str) -> str:
    """Classes a row's **printed prerequisite** names. #235.

    The third way a row is scoped, after `cls=` and a `cf:<class>-` ref,
    and the one `f2413` uses: a feat declared `cls=""` whose printed
    prereq is `{"all": [{"class": "warlord"}, ...]}`. `legal_feats` reads
    that, so a swordmage is never offered it -- verified against all three
    of the swordmage's legs.

    Counted as scoping because it is the same guarantee by a different
    route. Not counted as *equivalent*: a prereq is checked at build time
    and `c.build(...)` is asked mid-fight, so a row that somehow reached
    the wrong class would still answer wrongly. That is the latency this
    whole check is about, and it is stated rather than papered over.
    """
    import json

    from combat_engine.db import game

    row = game().execute(
        "SELECT prereq FROM feat WHERE ref = ?", (ref,)).fetchone()
    if row is None or not (row["prereq"] or "").strip():
        return ""
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            named = node.get("class")
            if isinstance(named, str):
                found.add(named.lower())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    try:
        walk(json.loads(row["prereq"]))
    except (ValueError, TypeError):
        return ""
    # **Exactly one, or nothing.** Two classes in a prereq is not scoping.
    return next(iter(found)) if len(found) == 1 else ""


def _class_of(path: pathlib.Path) -> str:
    """Which class a file's rows belong to.

    `powers/<class>/...` says so outright. A file under `features/` serves
    several classes at once, so its rows are attributed by the ref they
    are declared with instead -- that is the only honest answer, and
    guessing from the filename put a dozen riders under a class called
    "features".
    """
    parts = path.parts
    if "powers" in parts:
        return parts[parts.index("powers") + 1]
    return ""


#: How many legs `chargen.PRINTED_LEG` maps to an entry on their class's own
#: page. **A floor that may rise and may not fall**, the shape
#: `audit.silent_refs` and `leaks.DEFERRED` use: the other 27 legs are four
#: known shapes (see `PRINTED_LEG`'s own note) and a mapping that *shrinks* is
#: a leg that stopped being joinable, which is how a renamed leg looks. #235.
MAPPED = 70


def against_the_book(only: str = "") -> tuple[list[str], int]:
    """Does a mapped leg's fork agree with the entry its page prints?

    `chargen.BUILDS` holds the fork and `build_option` holds what the class's
    own page states; `PRINTED_LEG` is the join. Five legs disagreed when that
    join was first built, and **not one of them was findable before it
    existed**: the leg counts differ on 11 of 25 classes and only 5 of the 14
    classes that do agree hold their legs in the printed order, so comparing
    the two lists by position reported 14 disagreements of which 9 were the
    ordering and not the data.

    A blank on the page is not a disagreement. 11 of the 90 entries state no
    ability at all, because the class line above them already did, and 24 more
    state only one -- `etl/build.py` records a blank rather than guessing, so
    this has to read one the same way.
    """
    from combat_engine import chargen
    from combat_engine.db import game

    db = game()
    page = {
        ref: ((ability or "")[:3].lower(), (second or "")[:3].lower())
        for ref, ability, second in db.execute(
            "SELECT ref, ability, second FROM build_option"
        )
    }
    wrong: list[str] = []
    mapped = 0
    for cls, legs in sorted(chargen.PRINTED_LEG.items()):
        if only and cls != only:
            continue
        held = {b.name: b for b in chargen.BUILDS.get(cls, ())}
        for leg, ref in sorted(legs.items()):
            if ref not in page:
                wrong.append(f"  {cls:12} {leg:16} -> {ref}, which is not a printed leg")
                continue
            mapped += 1
            build = held.get(leg)
            if build is None:
                wrong.append(f"  {cls:12} {leg:16} is mapped and is not a leg")
                continue
            says = page[ref]
            ours = (build.primary.value, build.secondary.value)
            for i, which in enumerate(("primary", "secondary")):
                if says[i] and says[i] != ours[i]:
                    wrong.append(
                        f"  {cls:12} {leg:16} {which} is {ours[i]}, "
                        f"the page says {says[i]}   ({ref})"
                    )
    return wrong, mapped


#: **This was a gate for about an hour and is now a census, deliberately.**
#:
#: It was added in `8761879` to catch the moment a class gained a second
#: declared feature chassis, because `loadout` then dealt *both* to every
#: character of the class -- one character being two sub-classes, with
#: nothing failing to say so. The wizard was live proof.
#:
#: `chargen.chassis_of` fixed that in the commit after, so declaring a
#: second chassis is now safe and #642 is about to do it seventeen more
#: times. A gate that reddens on the intended future state is one people
#: route around, which `scripts/CLAUDE.md` is explicit about -- so what is
#: left is the number, printed, with the invariant asserted where it can
#: actually be asserted: `drivers.chassis` spawns characters and checks that
#: each gets one ladder and not two.
#:
#: Kept rather than deleted because the count is worth watching as #642
#: lands: it should climb from 2 towards 25.


def _slug(name: str) -> str:
    """The ref spelling of a printed build name.

    Mirrors `etl/build._slug`, which is the function that minted these refs
    in the first place -- `cf:{class}-{slug}` at `etl/build.py:1781`. Copied
    rather than imported because importing it drags the whole ETL in for one
    regex, and because `scripts/` reaching into `etl/` for a helper is a seam
    the `.importlinter` contracts would rather not have to waive.
    """
    import re

    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def chassis_census() -> tuple[list[str], dict[str, int]]:
    """How many feature chassis each class declares. A number, not a verdict.

    `class_feature.build` separates a chassis from the class-wide rows:
    blank means every character of the class has it, a name means it belongs
    to one sub-class. The Essentials line gave most classes a second ladder,
    which is what #642's 529 rows are.

    This counted as a **gate** for one commit, because `loadout` dealt every
    level-0 row of a class to every character of it -- so a class with two
    declared chassis dealt both, and one character was two sub-classes with
    nothing failing to say so. `chargen.chassis_of` fixed that, and the
    invariant now lives in `drivers.chassis`, which spawns characters and
    checks each gets one ladder. See this module's note above `_slug`.

    What is left is worth printing as #642 lands: the count should climb from
    2 towards 25, and a class dropping *back* to one would mean a declared
    chassis had been lost.

    A ref the `class_feature` table does not list is a **hand-coined** one
    (`cf:barbarian-aura`, `cf:rogue-tactic-club`, and two more), described
    only in the class's own page as `content/features/__init__.py` says. It
    belongs to no chassis and is counted against none.
    """
    import combat_engine.content  # noqa: F401  registers the rows
    from combat_engine.db import game
    from combat_engine.engine.dsl import REGISTRY

    chassis = {r["ref"]: r["build"]
               for r in game().execute("SELECT ref, build FROM class_feature")}
    named: dict[str, set[str]] = collections.defaultdict(set)
    for ref, power in REGISTRY.items():
        if not ref.startswith("cf:") or power.level != 0:
            continue
        # Absent from the table, or blank: class-wide, not a chassis.
        if chassis.get(ref):
            named[power.cls].add(chassis[ref])

    counts = {cls: len(names) for cls, names in named.items() if len(names) > 1}
    out: list[str] = []
    for cls, how_many in sorted(counts.items()):
        # **The ref's spelling, not the column's.** `class_feature.build`
        # holds the printed sub-class name with printed punctuation -- the
        # typographic apostrophe in one of the wizard's two is the giveaway
        # -- and this line goes to a terminal on every `check.py`. The ref
        # stem is the sanitised form of the same thing and is already in
        # tracked files, so it is what gets printed.
        names = ", ".join(_slug(n) for n in sorted(named[cls]))
        out.append(f"  {cls:12} declares {how_many} chassis: {names}")
    return out, counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--class", dest="cls", help="only this class")
    args = ap.parse_args()

    from combat_engine import chargen

    wanted = asked()
    dead: list[tuple[str, str, int]] = []
    unasked: list[tuple[str, str]] = []

    for cls in sorted(chargen.BUILDS):
        if args.cls and cls != args.cls:
            continue
        legs = {b.name for b in chargen.BUILDS[cls]}
        names = wanted.get(cls, collections.Counter())
        for name, count in sorted(names.items()):
            if name not in legs:
                dead.append((cls, name, count))
        for leg in sorted(legs):
            if leg not in names:
                unasked.append((cls, leg))

    for cls, name, count in dead:
        print(f"  {cls:12} {name:20} asked {count:3}x, no such leg")
    if unasked:
        print()
        for cls, leg in unasked:
            print(f"  {cls:12} {leg:20} is a leg no row asks about")

    total = sum(n for _, _, n in dead)
    print(f"\n{total} riders name a build that does not exist, "
          f"across {len({c for c, _, _ in dead})} classes")

    wrong, mapped = against_the_book(args.cls or "")
    if wrong:
        print()
        for line in wrong:
            print(line)
    shrunk = not args.cls and mapped < MAPPED
    print(f"{len(wrong)} mapped legs disagree with the page they came off; "
          f"{mapped} legs carry a printed entry"
          + (f"   <-- WAS {MAPPED}. A leg stopped being joinable." if shrunk else ""))

    census, counts = chassis_census()
    if census:
        print()
        for line in census:
            print(line)
    print(f"{len(counts)} class(es) declare more than one feature chassis; "
          f"`drivers.chassis` is what asserts a character gets only one")

    loose = ambiguous()
    if loose:
        print()
        for cls, name, count, who in loose:
            print(f"  {cls:14} c.build({name!r}) asked {count:3}x, and that"
                  f" name belongs to {', '.join(who)}")
        print("  `query.on_build` matches a leg by STRING with no class"
              " scoping, so an unscoped reader cannot say which leg it"
              " means. Scope the row -- a `cls=` or a `cf:<class>-` ref.")
    print(f"{len(loose)} row(s) ask about a leg name more than one class owns"
          " without being scoped to one of them")
    return 1 if dead or wrong or shrunk or loose else 0


if __name__ == "__main__":
    raise SystemExit(main())
