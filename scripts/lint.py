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
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Paths named on the command line, or empty for the whole tree. Held here
#: rather than in `argv` because `_dead_triggers` clears `argv` before importing
#: `combat_engine.content`, so an argument left there would not survive.
_ONLY: tuple[Path, ...] = ()


def _asked_for() -> tuple[Path, ...]:
    """Content files to walk: the ones named, or all of them.

    **`content/CLAUDE.md` tells a parallel agent it "lints only its own file"
    and this took no paths**, so the one command the rule named did the one
    thing the rule forbids. Four waves in a round each had to read other
    agents' faults out of their own output and decide which were theirs; they
    all got it right, and the failure mode if one had not is editing another
    agent's in-flight file. It is worse mid-round, where a tree-wide walk also
    picks up whatever half-written state somebody else is in -- one wave
    reported a tree-wide blocker that the owning agent had already fixed by
    the time anyone looked. #388.
    """
    if not _ONLY:
        return tuple(sorted((ROOT / "src/combat_engine/content").rglob("*.py")))
    out: list[Path] = []
    for p in _ONLY:
        out.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    return tuple(out)


def main() -> int:
    global _ONLY
    _ONLY = tuple(Path(a).resolve() for a in sys.argv[1:] if not a.startswith("-"))
    targets = [str(p) for p in _ONLY] or ["."]
    done = subprocess.run(["uv", "run", "ruff", "check", *targets], cwd=ROOT)
    faults = 0

    dupes = _duplicate_methods()
    for where, name, n in dupes:
        print(f"{where}: {name} is defined {n} times -- the last one wins")
    faults += len(dupes)

    for where, key, near in _unknown_context_keys():
        hint = f" -- did you mean {near}?" if near else ""
        print(
            f"{where}: a `when=` gate reads ctx[{key!r}], which no"
            f" modifier context carries{hint}"
        )
        faults += 1

    for where, key in _unread_modifiers():
        print(
            f"{where}: c.bonus({key!r}, ...) -- nothing reads that key,"
            f" so the modifier is laid and never consulted"
        )
        faults += 1

    for where, ref in _unhandled_half_on_miss():
        print(
            f"{where}: {ref} declares half_on_miss=True and never deals it"
            f" -- nothing in the engine reads that flag, so the printed"
            f" Miss line is dropped. Write `else: c.hit(half=True)`."
        )
        faults += 1

    for where, ref in _dropped_but_empty():
        print(
            f"{where}: {ref} is marked `dropped=` and its body does nothing"
            f" -- `dropped=` means it plays with one clause missing. A row that"
            f" cannot play is `todo=`, which is refused rather than counted ok."
        )
        faults += 1

    for where, read, what in _effect_attrs():
        hint = ("an Effect has no such field, so this raises the moment the row"
                " runs. The duration is `when`." if what == "effect" else
                "an AttackResult has no such field, so this raises the moment the"
                " row runs. A critical is `critical`, not `crit`.")
        print(f"{where}: `{read}` -- {hint}")
        faults += 1

    for where, ref, call, field in _strike_without_line():
        print(
            f"{where}: {ref} calls {call} and its header declares no {field}"
            f" -- that raises the moment the row is provoked. Two sat latent"
            f" through a sweep reporting 0 raise because the board never"
            f" provoked them."
        )
        faults += 1

    for where, ref, how in _close_area_hits_itself():
        what = "a close area" if how == "power" else "an augment's close area"
        print(
            f"{where}: {ref} declares {what} with target=EACH_CREATURE,"
            f" which is side 'any' and catches the creature using it."
            f" Use EACH_OTHER unless the card says it includes the user."
        )
        faults += 1

    for where, name, scope, first in _duplicate_defs():
        print(
            f"{where}: `{name}` is defined twice in {scope} (first at line"
            f" {first}). Python binds the later one, so every call between them"
            f" silently runs it. ruff's F811 cannot see this when the name is"
            f" used in between."
        )
        faults += 1

    for where, name in _unreferenced_defs():
        print(
            f"{where}: `{name}` is referenced nowhere in src/ or scripts/."
            f" ruff does not flag an unused module-level def, so this is"
            f" invisible to everything else. Read it before deleting -- a"
            f" predicate with no caller is sometimes the evidence that a row's"
            f" clause was quietly dropped."
        )
        faults += 1

    for where, ref, dice in _flat_damage_as_a_number():
        print(
            f"{where}: {ref} declares Damage({dice!r}, ...) -- a dice string that"
            f" is a bare number. `Cast.hit` tests `if dice`, so {dice!r} is truthy"
            f" and reaches `rng.roll`, which raises `not a dice expression`."
            f" Flat damage is an empty string: Damage(\"\", n)."
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


#: Which context a `c.bonus` call's gate will actually be handed,
#: decided by what it modifies.
#:
#: **The union is too forgiving and that is a real hole**, found by a
#: content agent who wrote `ctx["keywords"]` into an *attack* gate and
#: watched it pass. Keywords reach a saving throw and nothing else; an
#: attack gate reading one is as silently false as the six rows this
#: check was built for. So the key set is narrowed by the `what`.
#:
#: Anything not listed -- `speed`, `crit_range`, a `skill:` key, the
#: internal `Mods` stores -- falls back to the union, because those are
#: asked from places that build no context worth the name and a false
#: alarm there would be worse than the miss.
_CONTEXT_OF = {
    "attack": "attack",
    "damage": "damage",
    "save": "save",
}


def _context_keys(which: str = "") -> frozenset[str]:
    """Every key a modifier context carries, read off the engine.

    **Derived, not listed.** The first version of this was a hand-kept
    set and it was stale within the hour: it missed `how` from
    `movement`'s forced-movement resist and `source` from
    `resolve`'s, and reported sixteen correct rows as faults. A
    checker that cries wolf is worse than no checker, and a list
    somebody has to remember to update is a checker that will.

    So: every dict literal handed to `_mods(...)` or `.total(...)`
    anywhere in `engine/`, unioned. Add a key at any of those sites and
    this sees it on the next run.
    """
    #: Where each named context is built, so `which` can narrow to one.
    homes = {
        "attack": ("resolve.py",),
        "damage": ("resolve.py",),
        "save": ("cast.py", "durations.py"),
    }
    files = homes.get(which) or ()
    keys: set[str] = set()
    for path in (ROOT / "src/combat_engine/engine").glob("*.py"):
        if files and path.name not in files:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in ("_mods", "total"):
                continue
            for arg in node.args:
                # Either the literal itself or a name bound to one; the
                # bound case is picked up by the sweep over every dict
                # assigned to something called `*ctx` below.
                if isinstance(arg, ast.Dict):
                    keys |= {
                        k.value for k in arg.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            named = any(
                getattr(t, "id", "").endswith("ctx") for t in node.targets
            )
            if not named:
                continue
            target = next(
                (getattr(t, "id", "") for t in node.targets), ""
            )
            # `dmg_ctx` is the damage one and `ctx` in `resolve` is the
            # attack one; narrowing by name is what lets a `when=` on a
            # damage bonus be checked against the smaller set.
            if which == "damage" and target != "dmg_ctx":
                continue
            if which == "attack" and target == "dmg_ctx":
                continue
            keys |= {
                k.value for k in node.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    return frozenset(keys)


def _unknown_context_keys() -> list[tuple[str, str, str]]:
    """`ctx[...]` reads inside a gate for a key no context carries.

    **Six bugs in one wave were this shape.** `ctx.get("cover")` on a
    cover waiver, `ctx.get("against")` on a save narrowed to two
    conditions, `ctx.get("keywords")` before the save context carried
    any -- each a row that read as finished, passed the audit, and did
    nothing in every fight it was ever in. A `.get` default is what
    hides it: the gate is not wrong, it is absent.
    """
    import difflib

    wide = _context_keys()
    narrow = {k: _context_keys(v) for k, v in _CONTEXT_OF.items()}
    out = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", None) not in ("bonus", "penalty"):
                continue
            what = (
                node.args[0].value
                if node.args and isinstance(node.args[0], ast.Constant)
                else ""
            )
            known = narrow.get(what) or wide
            for inner in ast.walk(node):
                key = None
                if (isinstance(inner, ast.Call)
                        and getattr(inner.func, "attr", None) == "get"
                        and getattr(inner.func.value, "id", "") == "ctx"
                        and inner.args
                        and isinstance(inner.args[0], ast.Constant)):
                    key = inner.args[0].value
                elif (isinstance(inner, ast.Subscript)
                        and getattr(inner.value, "id", "") == "ctx"
                        and isinstance(inner.slice, ast.Constant)):
                    key = inner.slice.value
                if not isinstance(key, str) or key in known:
                    continue
                if key.startswith("skill:"):
                    continue
                near = difflib.get_close_matches(key, known, 1, 0.6)
                rel = path.relative_to(ROOT)
                out.append(
                    (f"{rel}:{inner.lineno}", key, near[0] if near else "")
                )
            continue
            # `skill:<name>` is a modifier key asked for by name, not a
            # context key.
    return out


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
    for path in _asked_for():
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


def _unhandled_half_on_miss() -> list[tuple[str, str]]:
    """Rows declaring `half_on_miss=True` whose body never deals the half.

    The flag is **declared data and nothing more**: `Damage.half_on_miss`
    is read by `scripts/cards.py` and by no line of the engine, and the
    page's Miss sentence comes from the printed prose, not from here. So
    a row that sets it and writes a bare `if c.strike(): c.hit()` drops
    its printed Miss line in play while looking finished -- six did, all
    in one file, found only because a wave's agent read the engine.

    Wiring the flag into `resolve` instead is not available: 123 of the
    129 declarations already carry the branch and would double-apply.
    """
    out = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for start, _end, ref, node in _rows(tree):
            declared = any(
                isinstance(n, ast.Call)
                and getattr(n.func, "id", getattr(n.func, "attr", "")) == "Damage"
                and any(
                    k.arg == "half_on_miss"
                    and isinstance(k.value, ast.Constant)
                    and k.value.value is True
                    for k in n.keywords
                )
                for d in node.decorator_list
                for n in ast.walk(d)
            )
            if not declared or _deals_half(node, _module_defs(tree)):
                continue
            out.append((f"{path.relative_to(ROOT)}:{start}", ref))
    return out


def _dropped_but_empty() -> list[tuple[str, str]]:
    """Rows marked `dropped=` whose body does nothing at all.

    The three markers draw one distinction and this is it: `dropped=` means the
    row **plays** with one named clause missing, `todo=` means nothing works and
    the row is refused in play. A body that is a docstring and nothing else
    cannot play, so `dropped=` is the wrong word -- and it is not cosmetic.
    `audit.py` fires a `dropped=` row and counts it inside the headline `ok`,
    so seven rows were being reported as working while doing nothing, and each
    showed up as an unexplained SILENT instead of as the refusal it was.

    Seven across the tree when this was written -- five from one week of the
    monster sweep and two older -- which is the rate a hand-applied distinction
    drifts at. One of the seven also carried `out_of_combat=True` beside its
    marker, a pair that claims the row is both finished-and-inert and missing a
    clause; `dsl.use` refuses `out_of_combat` with `todo` outright, so converting
    it surfaced the contradiction.
    """
    out = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for start, _end, ref, node in _rows(tree):
            dec = " ".join(ast.unparse(d) for d in node.decorator_list)
            if "dropped=" not in dec:
                continue
            real = [
                n for n in node.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))
            ]
            if not real or all(isinstance(n, ast.Pass) for n in real):
                out.append((f"{path.relative_to(ROOT)}:{start}", ref))
    return out


def _strike_without_line() -> list[tuple[str, str, str, str]]:
    """Rows whose body swings or lands a blow the header never declared.

    `c.strike()` raises without an `attack=` and `c.hit()` raises without a
    `damage=`, and both say so plainly -- but only *when the row is provoked*.
    That is what makes this worth a static walk instead of leaving it to the
    sweep: two of these sat in the tree through a full `audit.py` run reporting
    **0 raise**, because each needs a trigger the audit board does not arrange.
    `m5407a4` wants a marked adjacent enemy walking away while its own burst is
    unexpended; `m4014a1` likewise. `scorecard.py` plays whole fights, reached
    them, and died -- which is the right instrument finding it far too late and
    one row at a time.

    So the rule is read off the two `raise` sites in `cast.py` rather than
    invented here, including their own escape hatch: the message says *call
    `c.damage(...)`*, so a row that declares the line in its body is fine and
    is not reported. Six rows when this was written.

    A `todo=` row is skipped -- it is refused in play and never reaches either
    call -- and so is `obsolete=`.
    """
    out = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for start, _end, ref, node in _rows(tree):
            dec = " ".join(ast.unparse(d) for d in node.decorator_list)
            if "todo=" in dec or "obsolete=" in dec:
                continue
            calls = {
                n.func.attr for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and getattr(n.func.value, "id", "") == "c"
            }
            where = f"{path.relative_to(ROOT)}:{start}"
            if "strike" in calls and "attack=" not in dec and "attack" not in calls:
                out.append((where, ref, "c.strike()", "attack="))
            if "hit" in calls and "damage=" not in dec and "damage" not in calls:
                out.append((where, ref, "c.hit()", "damage="))
    return out


#: Rows whose card really does catch the creature using it, so `EACH_CREATURE`
#: on a close area is right there. Ten cards in the compendium print "include
#: you"; this is the only one of them written that way, and the check would
#: otherwise report it forever.
CATCHES_ITSELF = {"p9652"}


#: Every Python file the project owns. **Uses are counted across all of them**
#: whatever was asked for on the command line: a helper defined in one content
#: file is routinely imported by another, so a narrowed scan would report a live
#: function dead. Only the *definitions* checked are narrowed.
def _every_py() -> tuple[Path, ...]:
    out = sorted((ROOT / "src/combat_engine").rglob("*.py"))
    out += sorted((ROOT / "scripts").rglob("*.py"))
    return tuple(out)


@cache
def _scan() -> dict[str, object]:
    """One parse of the whole tree, for the two walks below.

    Collected together because both answer a question about a `def` that no
    instrument could previously see, and parsing 800-odd files twice to ask them
    separately is the kind of second pass `--history` exists to discourage.
    """
    used: Counter[str] = Counter()
    # (file, scope) -> name -> [lineno, ...]
    scopes: dict[tuple[Path, str], dict[str, list[int]]] = {}
    for path in _every_py():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used[node.id] += 1
            elif isinstance(node, ast.Attribute):
                used[node.attr] += 1
            elif isinstance(node, ast.alias):
                used[node.name.split(".")[-1]] += 1
        bodies = [("", tree.body)]
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bodies.append((node.name, node.body))
        for scope, body in bodies:
            seen = scopes.setdefault((path, scope), {})
            for node in body:
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    seen.setdefault(node.name, []).append(node.lineno)
    return {"used": used, "scopes": scopes}


def _duplicate_defs() -> list[tuple[str, str, str, int]]:
    """Two `def`s binding one name at one scope.

    **`ruff`'s F811 is blind to this exactly when it matters.** The rule is
    "redefinition of an *unused* name", so a call sitting between the two
    definitions marks the first one used and the rule goes quiet -- while Python
    binds the **last** definition at import, so that call silently runs the
    other function. Reproduced both ways: with no use between, F811 fires; with
    one, `ruff` passes clean.

    It bit `scripts/browser.py`, where a second `_settled` was added above three
    existing callers of a three-argument one. `ruff` passed; the run died with
    `TypeError: _settled() takes 2 positional arguments but 3 were given`. That
    was the lucky outcome -- call-compatible signatures would have rebound three
    callers to different code with nothing saying so.

    `lint.py` already walked `cast.py` for this inside a class, because 7,500
    lines are edited by many agents at once. This is the same question asked of
    every scope in every file. #408.
    """
    out: list[tuple[str, str, str, int]] = []
    narrowed = {p.resolve() for p in _ONLY} if _ONLY else None
    scopes: dict[tuple[Path, str], dict[str, list[int]]] = _scan()["scopes"]  # type: ignore[assignment]
    for (path, scope), names in sorted(scopes.items()):
        if narrowed is not None and not any(
            path.resolve() == q or q in path.resolve().parents for q in narrowed
        ):
            continue
        for name, lines in sorted(names.items()):
            if len(lines) > 1:
                rel = path.relative_to(ROOT)
                out.append((f"{rel}:{lines[-1]}", name, scope or "module", lines[0]))
    return out


def _unreferenced_defs() -> list[tuple[str, str]]:
    """A module-level private `def` that nothing anywhere references.

    `ruff` flags an unused *import* (F401) and nothing about an unused `def`, so
    dead code at module scope is invisible to every instrument here. 26 were
    found the first time this ran, most of them `requires=` gates orphaned when
    the target filters landed and the content rule rightly forbade an agent from
    deleting a definition it could not prove unshared.

    **A content module is imported for its decorators' side effects**, so
    "referenced nowhere" is not in general "never runs" -- but a module-level
    `def` cannot be reached by a decorator it does not appear in, so for this
    shape the two coincide. Stated here so the next reader need not re-derive it.

    Private names only. A public one may be part of a surface something outside
    this scan reads. #410.
    """
    used: Counter[str] = _scan()["used"]  # type: ignore[assignment]
    scopes: dict[tuple[Path, str], dict[str, list[int]]] = _scan()["scopes"]  # type: ignore[assignment]
    out: list[tuple[str, str]] = []
    for path in _asked_for():
        names = scopes.get((path, ""), {})
        for name, lines in sorted(names.items()):
            if not name.startswith("_") or name.startswith("__"):
                continue
            if used[name] == 0:
                out.append((f"{path.relative_to(ROOT)}:{lines[0]}", name))
    return out


def _flat_damage_as_a_number() -> list[tuple[str, str, str]]:
    """`Damage("0", n)` and friends -- a dice string holding a bare number.

    `Cast.hit` does `self._roll_damage(dice) if dice else bonus`, so a dice
    string of `"0"` is **truthy** and goes to `rng.roll`, which raises
    `not a dice expression: '0'`. Flat damage is spelled `Damage("", n)`.

    Three rows carried this and two of them raised in play. The audit could not
    see any of them: every one is restricted to a grabbed creature, and the
    board never grabs, so all three reported `UNUSED` through sweep after sweep
    reporting 0 raise. They were found by driving a row by hand, which is the
    argument for a static walk -- a board cannot be relied on to reach them.
    """
    out: list[tuple[str, str, str]] = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            ref = node.name
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                for kw in dec.keywords:
                    if kw.arg != "damage":
                        continue
                    for call in ast.walk(kw.value):
                        if not isinstance(call, ast.Call):
                            continue
                        if not call.args:
                            continue
                        first = call.args[0]
                        if (
                            isinstance(first, ast.Constant)
                            and isinstance(first.value, str)
                            and first.value.strip().isdigit()
                        ):
                            rel = path.relative_to(ROOT)
                            out.append((f"{rel}:{call.lineno}", ref, first.value))
    return out


def _close_area_hits_itself() -> list[tuple[str, str, str]]:
    """A close burst or blast that targets the creature using it.

    `EACH_CREATURE` is `Target("any", ...)` and `"any"` is `creatures(world)` --
    the actor included. A **close** area emanates from its user and never
    targets them, so the pairing is wrong unless the card says otherwise.
    `EACH_OTHER` is the same Target with `side="other"` and prints identically,
    so this is a pool bug with no visible symptom on the card.

    **Nothing caught this and 356 rows had it.** Four driven on the board each
    emitted `DamageApplied` against their own caster and two lost hit points,
    15 and 7. `audit.py` cannot see it -- the row does do something, to itself
    -- and `cards.py` cannot either, because "each creature in the burst" is
    exactly what the card prints. #385.

    Ten cards genuinely print "include you"; `CATCHES_ITSELF` holds the one of
    them that is written this way.

    Augments are checked too: two of the original 355 were `Augment(...)` calls
    inside `augments=` rather than decorators, and a decorator-only pass missed
    both.

    **Read off each call's own keywords, not its unparsed text.** The first
    version tested `"target=EACH_CREATURE" in ast.unparse(node)`, and a
    `power(...)` whose *augment* carries the pairing contains that substring --
    so the outer row was reported alongside the augment and the count came out
    two high. The duplicate pointed at a real fault, which is why it was easy
    to miss.
    """
    out = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", "")
            if name not in ("power", "Augment"):
                continue
            own = {k.arg: k.value for k in node.keywords if k.arg}
            reach, target = own.get("reach"), own.get("target")
            if not isinstance(target, ast.Name) or target.id != "EACH_CREATURE":
                continue
            if not (
                isinstance(reach, ast.Call)
                and getattr(reach.func, "id", "") in ("CloseBurst", "CloseBlast")
            ):
                continue
            ref = ""
            if name == "power" and node.args and isinstance(node.args[0], ast.Constant):
                ref = str(node.args[0].value)
            if ref and ref in CATCHES_ITSELF:
                continue
            out.append((f"{path.relative_to(ROOT)}:{node.lineno}", ref or "augment", name))
    return out


def _module_defs(tree: ast.Module) -> dict[str, ast.AST]:
    """Module-level functions, by name, so a shared helper can be followed."""
    return {
        n.name: n for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def _deals_half(node: ast.AST, helpers: dict[str, ast.AST] | None = None,
                _depth: int = 0) -> bool:
    """Does this body pay out a half-damage branch anywhere in it?

    An `else:` on any `if` counts, because a row that bothered to write
    one on an attack row is handling the miss -- being generous here is
    deliberate, since the fault this catches is the *absence* of any miss
    handling at all and a false alarm would get the walk ignored.

    **A shared helper counts too.** This walked the decorated function alone, so
    two near-duplicate monsters paying the miss out through one
    `_helper(c)` were both reported as faults -- a false alarm, and the wave that
    hit it inlined the branch twice to satisfy the check rather than the other way
    round. Following a call to a module-level function in the same file fixes it;
    one level is enough for the shape this is about, and bounding the depth keeps
    a helper calling a helper from looping.
    """
    for n in ast.walk(node):
        if isinstance(n, ast.If) and n.orelse:
            return True
        if not isinstance(n, ast.Call):
            continue
        if getattr(n.func, "attr", "") in ("half_damage", "half"):
            return True
        if any(
            k.arg == "half" and isinstance(k.value, ast.Constant) and k.value.value
            for k in n.keywords
        ):
            return True
        called = getattr(n.func, "id", "")
        if (
            helpers and _depth < 2 and called in helpers
            and _deals_half(helpers[called], helpers, _depth + 1)
        ):
            return True
    return False


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
        # A row in a `group` shares one budget with its siblings -- "you
        # can use only one channel divinity power per encounter" -- so the
        # limit is printed and declared, just not in these words. Without
        # this the check called a correct row wrong the moment its marker
        # came off, which is how the check gets ignored.
        if p.group:
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
#: **`not_me` reads two fields, and this said one.** It is
#: `getattr(ev, "actor", getattr(ev, "attacker", None)) != me` -- it falls back
#: to `attacker` -- so listing only `actor` called six correct rows dead the
#: moment the combinator blind spot below was closed and they became visible at
#: all. Proven before changing anything: on a `Hit` with `attacker=7`, `not_me`
#: is False for 7 and True for 9, which is exactly right.
#:
#: That is the shape this table's own note warns about pointing the other way, so
#: it is worth saying which was wrong here: the six rows were fine and the entry
#: was not.
PREDICATE_FIELDS = {
    "about_me": ("actor",),
    "not_me": ("actor", "attacker"),
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
            fields = {f.name for f in dataclasses.fields(trig.event)}
            for name in _predicates(trig.when):
                want = PREDICATE_FIELDS.get(name)
                if want is None:
                    continue
                # A predicate that reads several fields is satisfied by any one
                # of a pair it treats as alternatives, and refused when it needs
                # both. `hits_me` wants an attacker *and* a target; `by_me`
                # takes an attacker or a source.
                if name == "hits_me":
                    ok = "target" in fields and bool({"attacker"} & fields)
                else:
                    ok = bool(set(want) & fields)
                if not ok:
                    out.append(
                        (p.ref, name, trig.event.__name__, ", ".join(sorted(fields)))
                    )
    return out


def _predicates(when: object, _depth: int = 0) -> list[str]:
    """Every named predicate inside one `when=`, unwrapping the combinators.

    **`both(...)` and `either(...)` return a closure called `check`**, so looking
    a predicate up by `__name__` skipped every trigger built with one -- 505 of
    them across the tree, which is most of the triggers there are. A level-7 wave
    wrote `about_me` on `Hit` eight times; the three bare ones went red and the
    five inside `both(...)` sailed through, and the agent found those by reading
    every trigger by hand.

    `triggers.both`/`either` hang their constituents on `check.parts` for this.
    Nested, because a combinator inside a combinator is legal and two rows do it.
    """
    parts = getattr(when, "parts", None)
    if parts and _depth < 4:
        return [n for part in parts for n in _predicates(part, _depth + 1)]
    return [getattr(when, "__name__", "")]


def _effect_fields() -> set[str]:
    """What an `Effect` actually carries, read off the dataclass."""
    import dataclasses

    from combat_engine.engine.durations import Effect

    return {f.name for f in dataclasses.fields(Effect)} | {
        n for n in dir(Effect) if not n.startswith("_")
    }


def _effect_attrs() -> list[tuple[str, str]]:
    """Reads of a field an `Effect` does not have.

    **`Effect.until` does not exist -- the duration field is `when`** -- and four
    rows across four files wrote `eff.until is When.SAVE_ENDS`. Every one raised
    `AttributeError` the moment its trigger fired, and every one looked finished:
    three were committed and `audit.py` reported them UNUSED, because the trigger
    they wait for is not one the board produces, so the raise never happened
    where anybody could see it. Proven both ways before this walk was written --
    the old spelling raises at `artillery_sa.py:464`, the new one rolls a
    `SavingThrow`.

    Exactly the `_dead_triggers` shape one object over: a name spelled correctly
    against the wrong class. The engine's own `CLAUDE.md` calls this component's
    failure mode *silently false* and says to read the event before reading a
    field off it; the same goes for an effect.

    Scoped to names bound by iterating `effects.of(...)`, which is how a row gets
    hold of one. A wider net would have to guess what every local is.
    """
    fields = _effect_fields()
    out = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.For) or not isinstance(node.target, ast.Name):
                continue
            if "effects.of" not in ast.unparse(node.iter):
                continue
            bound = node.target.id
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Attribute)
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id == bound
                    and inner.attr not in fields
                ):
                    rel = path.relative_to(ROOT)
                    out.append(
                        (f"{rel}:{inner.lineno}", f"{bound}.{inner.attr}", "effect")
                    )
        # **`.result.<attr>` is the same trap on `AttackResult`.** A level-7 wave
        # wrote `ev.result.crit`, which raises: the field is `critical`, and
        # `c.crit` on `Cast` is a differently-named convenience that makes the
        # wrong spelling look familiar. It caught its own on a row whose trigger
        # does fire; a row whose trigger the board never produces would have
        # shipped, which is exactly how the four `eff.until` rows did.
        #
        # **Both spellings.** `ev.result.crit` is an attribute on an attribute;
        # `result = ...` then `result.crit` is an attribute on a local name, and
        # that is the commoner shape in this tree. The first version of this walk
        # only matched the former, so breaking a real line to test it produced
        # nothing -- the line was `bool(result and result.critical)`. Checked by
        # breaking it again afterwards.
        # **Reads only.** `result.blurred = True` *writes* an ad-hoc attribute,
        # which a dataclass allows, and a sibling row on the same stat block reads
        # it back with `getattr(..., "blurred", False)` -- a deliberate out-of-band
        # channel between two rows, not a mistake. Flagging the store called it
        # one. A read of a field that is not there is the thing that raises.
        for inner in ast.walk(tree):
            if not isinstance(inner, ast.Attribute):
                continue
            if not isinstance(inner.ctx, ast.Load):
                continue
            holder = inner.value
            looks_like_result = (
                isinstance(holder, ast.Attribute) and holder.attr == "result"
            ) or (isinstance(holder, ast.Name) and holder.id == "result")
            if looks_like_result and inner.attr not in _attack_result_fields():
                rel = path.relative_to(ROOT)
                out.append((f"{rel}:{inner.lineno}", f"result.{inner.attr}", "attack"))
    return out


@cache
def _attack_result_fields() -> frozenset[str]:
    """What an `AttackResult` carries, read off the dataclass."""
    import dataclasses

    from combat_engine.engine.resolve import AttackResult

    return frozenset(
        {f.name for f in dataclasses.fields(AttackResult)}
        | {n for n in dir(AttackResult) if not n.startswith("_")}
    )


# **A check lived here and was deleted; #382.** It flagged a row waiting on
# `ConditionApplied`/`ConditionEnded` for a condition a relation mirrors -- a
# grab, a mark, a domination -- on the grounds that `Relations.set` wrote onto
# `Conditions` in silence and announced only `RelationSet`, so such a row was
# armed, read correctly and could never fire.
#
# That was true. It was then **fixed in the engine** and this was not updated:
# `relations._apply_condition` is now titled "Move the condition a relation
# mirrors, *and say so*", and its docstring is the record of the fix, including
# that clearing had been silent the same way. Driven on a board, a `c.grab`
# emits `ConditionApplied: grabbed` beside `RelationSet`, so a row declared the
# obvious way does fire.
#
# It was not dormant when removed -- it fired on a level-11 lurker row and the
# author re-aimed a working row to satisfy it. So it was spending author
# attention to move rows off a pattern that works, and teaching a false fact
# about the engine while it did it. `_context_keys` below is the argument:
# a checker that cries wolf is worse than no checker. The derivation read the
# right table; the conclusion drawn from it went stale.
#
# Do not re-add it without first checking whether `_apply_condition` still
# announces. If that ever stops being true, the check is right again.


def _rows(tree: ast.Module) -> list[tuple[int, int, str, ast.AST]]:
    """Every `@power("ref", ...)` function, with the lines it spans."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or _decorator(dec) != "power":
                continue
            if dec.args and isinstance(dec.args[0], ast.Constant):
                start = min(
                    [node.lineno] + [d.lineno for d in node.decorator_list]
                )
                out.append(
                    (start, node.end_lineno or node.lineno, dec.args[0].value, node)
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
