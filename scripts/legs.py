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
the avenger's censures, the warlord's three commands. Every one had been
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
    """
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        cls, marked = "", False
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
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
        if not marked:
            yield node, cls


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
    from combat_engine.etl.build import game

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
    return 1 if dead or wrong or shrunk else 0


if __name__ == "__main__":
    raise SystemExit(main())
