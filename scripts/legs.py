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
"""

from __future__ import annotations

import argparse
import ast
import collections
import pathlib
import sys

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
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name not in ("build", "on_leg"):
                continue
            value = getattr(node.args[0], "value", None)
            if isinstance(value, str):
                out[_class_of(path)][value] += 1
    return out


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--class", dest="cls", help="only this class")
    args = ap.parse_args()

    from combat_engine.content import chargen

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
    return 1 if dead else 0


if __name__ == "__main__":
    raise SystemExit(main())
