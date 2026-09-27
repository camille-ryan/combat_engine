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
import re
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

    for where, key in _unread_modifiers():
        print(
            f"{where}: c.bonus({key!r}, ...) -- nothing reads that key,"
            f" so the modifier is laid and never consulted"
        )
        faults += 1

    for ref, why in _spent_once_a_fight():
        print(f"{ref}: {why}")
        faults += 1

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


#: Modifier keys that look like a bonus and are read by nothing.
#:
#: `initiative` is the whole list so far and it cost seven rows across
#: four files. `Initiative.bonus` is summed before the d20 and `Mods` is
#: never consulted, so `c.bonus("initiative", 2)` sits in the table and
#: no roll ever sees it -- while reading exactly like every other bonus
#: in the corpus. `c.initiative` is the verb, and it moves the creature
#: in the order after the roll, which is the only thing a trait armed
#: after the opening rolls can do.
#:
#: A key belongs here when the engine has a *verb* for the thing and no
#: reader for the modifier. A key nothing implements at all is a gap and
#: belongs in a `todo=`, not here.
UNREAD_MODIFIER_KEYS = {"initiative": "c.initiative(amount, on=)"}


def _unread_modifiers() -> list[tuple[str, str]]:
    """`c.bonus` calls whose key no part of the engine reads."""
    out = []
    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", None) not in ("bonus", "penalty"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            key = node.args[0].value
            if key in UNREAD_MODIFIER_KEYS:
                rel = path.relative_to(ROOT)
                out.append((f"{rel}:{node.lineno}", key))
    return out


#: A card that really does limit itself says so in one of these ways.
_PRINTED_LIMIT = re.compile(
    r"once per (encounter|day)"
    r"|once a (day|fight)"
    r"|only once"
    # "**The first time** you make an attack roll **during each
    # encounter**" is the same limit said the long way round, and it is
    # how several cards print it. Without this the check called two
    # correct rows wrong, which is the failure mode that gets a checker
    # ignored.
    r"|the first time .{0,80}?(each|an|this) encounter",
    re.I | re.S,
)


def _spent_once_a_fight() -> list[tuple[str, str]]:
    """Triggered traits declared `ENCOUNTER` whose card prints no limit.

    **A triggered `action=NONE` row spends a use every time it fires.**
    `triggers._answers` asks `dsl.usable` before offering a row, and an
    `ENCOUNTER` row is expended after one use -- so a feat reading
    "whenever you hit" answered once a fight and was inert for the rest
    of it. Two content waves found this independently on the same
    afternoon, having each watched a row do nothing from round two.

    It is invisible to every other instrument: the row fires, the audit
    sees it fire, and the second firing that never comes is not an
    event anybody is looking for.

    **Feats only.** A power card and an item's Power block print their
    own usage line -- "Encounter", "Daily" -- so `ENCOUNTER` there is
    the card speaking and is right. A feat prints no usage line at all,
    which is why the field is an authoring choice on a feat and a
    transcription everywhere else. Scoped wider this check reported 205
    faults and most of them were correct rows.

    The card decides. 167 of the 169 rows declared this way printed no
    limit at all, so the default was simply wrong; the two that print
    one are correct and must stay. A trait with **no** trigger is not
    checked -- `Encounter._arm_traits` casts it once by design, and
    `ENCOUNTER` is what stops it being re-armed.
    """
    import sqlite3

    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.engine import ActionType
    from combat_engine.engine.dsl import REGISTRY

    db = ROOT / "data" / "game.db"
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    spec = dict(con.execute("SELECT ref, spec FROM feat"))
    spec.update(con.execute("SELECT ref, spec FROM item_block"))

    out = []
    for ref, p in REGISTRY.items():
        if not ref.startswith("f") or not ref[1:2].isdigit():
            continue
        if not p.triggers or p.action is not ActionType.NONE:
            continue
        if p.usage.name != "ENCOUNTER" or p.unfinished:
            continue
        text = spec.get(ref) or spec.get(ref.rstrip("b")) or ""
        if _PRINTED_LIMIT.search(text):
            continue
        out.append((
            ref,
            "a triggered trait declared ENCOUNTER is spent on its first "
            "firing, and this card prints no limit -- use AT_WILL",
        ))
    return out


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
