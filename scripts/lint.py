#!/usr/bin/env python
"""Ruff, plus two structural faults it cannot see.

    uv run scripts/lint.py

A second `def` of the same name in the same class silently replaces the
first. Python allows it, and ruff's F811 catches it in a small file but did
not catch it in `cast.py` -- which is exactly the file several agents at a
time are adding methods to.

It cost a live regression: a new `_free_square_near(eid)` shadowed the
existing `_free_square_near(square)`, and every conjuration in the game
stopped appearing. Nothing failed loudly; the replay fixtures diverged a
hundred events later and the cause was three edits back.

The second is a declared trigger whose predicate reads a field its event
does not have. `about_me` reads `ev.actor`; `ConditionApplied` names its
subject `target`. Put them together and the predicate is silently false
forever -- indistinguishable from a trigger that simply never happens, and
the row looks finished. That cost twenty minutes to diagnose once already.

Folded in here rather than added as an eighth instrument, because both are
static walks and cost a fraction of a second between them.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    done = subprocess.run(["uv", "run", "ruff", "check", "."], cwd=ROOT)
    faults = 0

    dupes = _duplicate_methods()
    for where, name, n in dupes:
        print(f"{where}: {name} is defined {n} times -- the last one wins")
    faults += len(dupes)

    for ref, pred, event, has in _dead_triggers():
        print(
            f"{ref}: `{pred}` reads a field {event} does not have"
            f" -- it will never be true. {event} has {has}."
        )
        faults += 1

    if faults:
        print(f"\n{faults} structural fault(s).")
        return 1
    return done.returncode


#: What each ready-made predicate reads off the event it is handed. Only the
#: ones that look at a single field; the combinators are not checkable this
#: way and are not listed.
#: Every field a predicate reads, not one of them. `hits_me` and `by_me`
#: each look at two, and recording only the second let a trigger that can
#: never fire pass this check -- `hits_me` on `DamageRolled` reads
#: `ev.attacker`, which that event spells `source`, and the walk approved it
#: because `target` was present. The check existed and was itself too
#: forgiving, which is worse than not having it.
PREDICATE_FIELDS = {
    "about_me": ("actor",),
    "not_me": ("actor",),
    "by_me": ("attacker", "source"),
    "targets_me": ("target",),
    "hits_me": ("attacker", "target"),
}


def _dead_triggers() -> list[tuple[str, str, str, str]]:
    """Declared triggers that can never be true."""
    import dataclasses
    import sys

    sys.argv = sys.argv[:1]
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    out = []
    for p in REGISTRY.values():
        for trig in p.triggers:
            name = getattr(trig.when, "__name__", "")
            want = PREDICATE_FIELDS.get(name)
            if want is None:
                continue
            fields = {f.name for f in dataclasses.fields(trig.event)}
            # A predicate that reads several fields is satisfied by any one
            # of a pair it treats as alternatives, and refused when it needs
            # both. `hits_me` wants an attacker *and* a target; `by_me`
            # takes an attacker or a source.
            if name == "hits_me":
                ok = "target" in fields and bool({"attacker"} & fields)
            else:
                ok = bool(set(want) & fields)
            if not ok:
                want = "/".join(want)
                out.append(
                    (p.ref, name, trig.event.__name__, ", ".join(sorted(fields)))
                )
    return out


def _duplicate_methods() -> list[tuple[str, str, int]]:
    out = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Overloads and property setters are deliberate repeats.
            names = Counter(
                b.name
                for b in node.body
                if isinstance(b, ast.FunctionDef | ast.AsyncFunctionDef)
                and not any(_decorator(d) in _REPEATABLE for d in b.decorator_list)
            )
            for name, n in names.items():
                if n > 1:
                    rel = path.relative_to(ROOT)
                    out.append((f"{rel}:{node.name}", name, n))
    return out


_REPEATABLE = {"overload", "setter", "getter", "deleter", "register"}


def _decorator(node: ast.expr) -> str:
    while isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else ""


if __name__ == "__main__":
    sys.exit(main())
