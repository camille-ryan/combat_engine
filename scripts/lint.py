#!/usr/bin/env python
"""Ruff, plus the one thing ruff misses here: a method defined twice.

    uv run scripts/lint.py

A second `def` of the same name in the same class silently replaces the
first. Python allows it, and ruff's F811 catches it in a small file but did
not catch it in `cast.py` -- which is exactly the file several agents at a
time are adding methods to.

It cost a live regression: a new `_free_square_near(eid)` shadowed the
existing `_free_square_near(square)`, and every conjuration in the game
stopped appearing. Nothing failed loudly; the replay fixtures diverged a
hundred events later and the cause was three edits back.

Folded in here rather than added as an eighth instrument, because it is an
AST walk over the tree and costs a fraction of a second.
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
    dupes = _duplicate_methods()
    for where, name, n in dupes:
        print(f"{where}: {name} is defined {n} times -- the last one wins")
    if dupes:
        print(f"\n{len(dupes)} shadowed definition(s).")
        return 1
    return done.returncode


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
