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


def main() -> int:
    done = subprocess.run(["uv", "run", "ruff", "check", "."], cwd=ROOT)
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

    for ref, why in _spent_once_a_fight():
        print(f"{ref}: {why}")
        faults += 1

    for ref, event, cond in _relation_only_conditions():
        print(
            f"{ref}: waits for {event} naming {cond}, which arrives by"
            f" relation and is never announced as a condition"
            f" -- watch RelationSet/RelationCleared instead"
        )
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
    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
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
    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
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
    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
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


_CONDITION_EVENTS = ("ConditionApplied", "ConditionEnded")
_RELATION_EVENTS = ("RelationSet", "RelationCleared")


def _relation_imposed() -> dict[str, str]:
    """Conditions that arrive by relation, mapped to the relation.

    **Derived, not listed.** `Relations.set` writes these straight onto
    the `Conditions` component through `_apply_condition` and announces
    only `RelationSet`; `Effects.cure` takes them off through
    `relations.clear`, which announces only `RelationCleared`. So
    nothing ever names one in a `ConditionApplied` or a
    `ConditionEnded`, and a row declared on that pairing is armed,
    reads correctly, passes every other check and can never fire.

    The set is whatever table `_apply_condition` consults, read off
    `relations.py` -- add a relation there and this sees it on the next
    run. Two hand-kept lists in this repo went stale within the hour.
    """
    from combat_engine.engine import relations as rel

    tree = ast.parse(Path(rel.__file__).read_text())
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "_apply_condition"),
        None,
    )
    out: dict[str, str] = {}
    for node in ast.walk(fn) if fn is not None else ():
        table = getattr(rel, node.id, None) if isinstance(node, ast.Name) else None
        if isinstance(table, dict):
            for kind, cond in table.items():
                out[getattr(cond, "name", "")] = getattr(kind, "name", "")
    out.pop("", None)
    return out


def _relation_only_conditions() -> list[tuple[str, str, str]]:
    """Rows waiting on a condition event that names a relational condition.

    Silenced for a row that also watches the relation, because that is
    the fix: a clause naming several conditions keeps the condition
    event for the rest of them and hangs the relational half on
    `RelationSet`.
    """
    conds = _relation_imposed()
    if not conds:
        return []
    out = []
    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        funcs: dict[str, list[ast.AST]] = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                funcs.setdefault(n.name, []).append(n)
        bound = {
            t.id: n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name)
        }
        rows = _rows(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in ("Trigger", "watch", "on"):
                continue
            event = getattr(node.args[0], "id", "")
            if event not in _CONDITION_EVENTS:
                continue
            handler = node.args[1] if len(node.args) > 1 else next(
                (k.value for k in node.keywords if k.arg in ("when", "fn")), None
            )
            named = _conditions_named(
                handler, funcs, bound, set(conds), node.lineno
            )
            if not named:
                continue
            rel_path = path.relative_to(ROOT)
            row = next(
                (r for r in rows if r[0] <= node.lineno <= r[1]), None
            )
            scope = row[3] if row else tree
            if any(
                isinstance(n, ast.Name) and n.id in _RELATION_EVENTS
                for n in ast.walk(scope)
            ):
                continue
            where = f"{row[2]}" if row else f"{rel_path}:{node.lineno}"
            for cond in sorted(named):
                out.append((where, event, f"Condition.{cond}"))
    return out


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


def _conditions_named(
    node: ast.AST | None,
    funcs: dict[str, list[ast.AST]],
    bound: dict[str, ast.AST],
    wanted: set[str],
    line: int,
) -> set[str]:
    """Which of `wanted` a predicate tests the event's condition against.

    Only a comparison against `ev.condition` counts. Anything looser
    reported handlers that *clear* a domination on their way out -- the
    condition is spelled there too, and calling those rows dead is how a
    check gets ignored.
    """
    seen: set[str] = set()
    args: list[ast.AST] = []
    body: ast.AST | None = None
    if isinstance(node, ast.Lambda):
        body = node
    elif isinstance(node, ast.Name):
        body = _nearest(funcs.get(node.id), line) or bound.get(node.id)
    elif isinstance(node, ast.Call):
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        body = _nearest(funcs.get(name or ""), line)
        args = [*node.args, *(k.value for k in node.keywords)]
    if body is None:
        return seen
    tests = [
        n for n in ast.walk(body)
        if isinstance(n, ast.Compare) and _reads_condition(n)
    ]
    if not tests:
        return seen
    # A factory takes the condition as an argument, so the member is at
    # the call and the comparison is in the body.
    for where in tests + args:
        for inner in ast.walk(where):
            if (isinstance(inner, ast.Attribute)
                    and getattr(inner.value, "id", "") == "Condition"
                    and inner.attr in wanted):
                seen.add(inner.attr)
            elif isinstance(inner, ast.Name) and inner.id in bound:
                for deep in ast.walk(bound[inner.id]):
                    if (isinstance(deep, ast.Attribute)
                            and getattr(deep.value, "id", "") == "Condition"
                            and deep.attr in wanted):
                        seen.add(deep.attr)
    return seen


def _reads_condition(node: ast.Compare) -> bool:
    """Does this comparison have `ev.condition` on one side?"""
    for side in [node.left, *node.comparators]:
        if isinstance(side, ast.Attribute) and side.attr == "condition":
            return True
        if (isinstance(side, ast.Call)
                and getattr(side.func, "id", "") == "getattr"
                and len(side.args) > 1
                and getattr(side.args[1], "value", None) == "condition"):
            return True
    return False


def _nearest(nodes: list[ast.AST] | None, line: int) -> ast.AST | None:
    """The definition a call at `line` sees -- names repeat in one file."""
    if not nodes:
        return None
    before = [n for n in nodes if getattr(n, "lineno", 0) <= line]
    return max(before or nodes, key=lambda n: getattr(n, "lineno", 0))


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
