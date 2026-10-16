#!/usr/bin/env python
"""Ruff, plus the structural faults it cannot see.

    uv run scripts/lint.py

**Twenty-two of them now, and this header said "two" until the count was
checked.** Each is a walk over what the tree declares, looking for a
statement that is silently false rather than wrong -- the class of fault
that leaves a row looking finished. The two below are the original pair and
are still the clearest examples of the shape.

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

    for where, ref, verb in _subjectless_calls():
        print(
            f"{where}: {ref} declares target=NO_TARGET and calls c.{verb}()"
            f" with no `on=`. `on` defaults through `Cast._who`, which is"
            f" `self.target` -- and a NO_TARGET row has none, so this acts on"
            f" nobody every time. Pass `on=c.me` if the clause is about the"
            f" caster."
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

    for where, read, event in _event_attrs():
        print(
            f"{where}: `{read}` -- a {event} has no such attribute and nothing"
            f" attaches one, so the handler raises the first time it fires."
            f" `audit` credits these rows: the trigger arms and the board never"
            f" produces the state the clause is about."
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

    for where, ref in _minor_with_a_declared_trigger():
        print(
            f"{where}: {ref} is a MINOR action with a declared Trigger."
            f" `triggers.WINDOW_OF` has no window for a minor action, so the"
            f" trigger is never subscribed and the body never runs. A printed"
            f" Trigger on an action you choose to take is a `requires=`."
        )
        faults += 1

    for where, ref in _personal_reach_at_an_enemy():
        print(
            f"{where}: {ref} has reach=PERSONAL and an enemy-side target."
            f" A personal reach narrows the pool to whoever is adjacent --"
            f" sometimes to nobody -- so the row is offered against one"
            f" creature whatever its card allows. Give it the reach the card"
            f" prints, or target SELF."
        )
        faults += 1

    for where, ref, said in _count_the_area_decides():
        print(
            f"{where}: {ref} declares Target(count={said}, everyone=True) --"
            f" `everyone=` means the area decides, so the count is never read."
            f" Drop it, or drop `everyone=` if the card really prints a cap."
        )
        faults += 1

    for ref, why in _spent_once_a_fight():
        print(f"{ref}: {why}")
        faults += 1

    for where, what in _db_reaches_upward():
        print(
            f"{where}: imports `{what}`. `db.py` is the read path to game.db and"
            f" sits below every component -- five of them read it and none"
            f" writes. An import from `combat_engine` here gives it a direction"
            f" and puts a component back to reaching through another for a"
            f" sqlite file, which is what #334 moved it out of."
        )
        faults += 1

    for where, _enum in _iterates_the_defence_enum():
        print(
            f"{where}: iterates `Defense`, which has five members and only"
            f" four are defences a creature has. `Defense.ANY` is an"
            f" instruction -- whichever is lowest -- so this reaches one more"
            f" than it means and says nothing about it. Use `DEFENCES`."
        )
        faults += 1

    for ref, where, why in _dangling_implementations():
        print(
            f"{ref}: implemented_in={where!r} but {why}"
            f" -- the row is reported finished and never fired, so this"
            f" pointer is the only thing holding it up. #553."
        )
        faults += 1

    for where, why in _reinvented_area_tuple():
        print(
            f"{where}: {why}. Import it from `combat_engine.engine`"
            f" -- seventeen files already do, and four of the first five"
            f" disagreed. #616."
        )
        faults += 1

    for label, why in _dead_terrain_labels():
        print(
            f"DIFFICULT_LABELS: {label!r} {why}. A closed vocabulary whose"
            f" entries nobody uses stops being a check -- drop it, or write"
            f" the row that needs it. #598."
        )
        faults += 1

    for ref, host, why in _lends_nobody_asks_for():
        print(
            f"{ref}: lends an augment to {host!r} but {why}"
            f" -- the feat has a body and audits as firing, the power still"
            f" works, and nothing counts the gap. That was f3170's state."
        )
        faults += 1

    for where, names, at in _gates_on_nothing():
        print(
            f"{where}:{at}: compares against {names!r}, which no row"
            f" declares. The comparison is False for every event it ever"
            f" sees, so whatever rides on it is silently dead. Either the"
            f" ref is a second id for a row this tree declares under"
            f" another one, or the row owes a marker naming it."
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

#: Verbs whose context is named by the **call** rather than by a `what`
#: string in the first argument.
#:
#: `c.resist(10, DamageType.FIRE, when=...)` leads with an amount, so the
#: `what`-keyed lookup above reads `""` and falls back to the wide union --
#: where `ranged` is present, so a resist gate reading it passed. It was
#: *not* present in the context the gate actually got (#380), which is the
#: exact miss this check exists to prevent, happening to the check itself.
_GATE_CONTEXT = {"resist": "damage"}


@cache
def _ctx_forwarders() -> frozenset[str]:
    """Engine functions that take a `ctx` and hand it to `Mods.total`.

    **The derivation below could not see a context built at a call site
    and threaded through a helper**, and that is a whole class of key,
    not a stray one. `dsl._stretched(world, actor, kind, {"power": ...,
    "kind": ...})` is the case: the literal is written at the two call
    sites in `dsl.py`, and `_stretched` forwards it as `mods.total("reach",
    ctx)` -- a `Name`, carrying no keys a walk can read. So `kind` was
    absent from the union, and the check called two **correct** sites
    faults: `c.as_ranged`, which gates a `"reach"` bonus on exactly the
    key `_stretched` supplies, and a content row doing the same.

    Found by an authoring agent, which dropped the gate from its own row
    to get past the check -- the gate was dead there for an unrelated
    reason, so nothing was lost, but that is the shape of damage a false
    alarm does. A checker that cries wolf gets routed around.

    Still derived, which is the point: name a forwarder's parameter `ctx`
    and pass it to `total`, and its call sites are harvested from the next
    run. Only the forwarders are discovered here; the literals come from
    the call-site walk, so `which`'s file narrowing still applies and
    these keys reach the wide union only.
    """
    out: set[str] = set()
    for path in (ROOT / "src/combat_engine/engine").glob("*.py"):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            if not any(a.arg == "ctx" for a in fn.args.args):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(
                    node.func, "attr", None
                )
                if name not in ("_mods", "total"):
                    continue
                if any(
                    isinstance(a, ast.Name) and a.id == "ctx" for a in node.args
                ):
                    out.add(fn.name)
    return frozenset(out)


def _context_keys(which: str = "") -> frozenset[str]:
    """Every key a modifier context carries, read off the engine.

    **Derived, not listed.** The first version of this was a hand-kept
    set and it was stale within the hour: it missed `how` from
    `movement`'s forced-movement resist and `source` from
    `resolve`'s, and reported sixteen correct rows as faults. A
    checker that cries wolf is worse than no checker, and a list
    somebody has to remember to update is a checker that will.

    So: every dict literal handed to `_mods(...)`, `.total(...)` or a
    `_ctx_forwarders()` helper anywhere in `engine/`, unioned. Add a key
    at any of those sites and this sees it on the next run.
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
            # A forwarder's literal counts toward the **wide** union only.
            # Not a shortcut -- `resolve.py:645` builds
            # `{**ctx, "power": ..., "kind": "ranged"}` and hands it to
            # `_stretched`, which spends it on `total("range", ctx)`. That is
            # a *distance* key, and `_CONTEXT_OF` sends every distance gate
            # to the wide union already. Counting it as attack context would
            # mean an `attack`-key gate reading `ctx["kind"]` passes while
            # still being silently false, which is the hole this check's own
            # docstring was narrowed to close.
            forwarded = not which and name in _ctx_forwarders()
            if name not in ("_mods", "total") and not forwarded:
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


@cache
def _subjectless_verbs() -> frozenset[str]:
    """`Cast` verbs whose `on=` defaults to the target and never to the caster.

    **Derived off `Cast`, for the reason `_context_keys` is**: a hand-kept
    list of 92 method names would be stale within a week.

    Three tests, and the second two are what make the set mean something:

    * `on: int | None = None` -- there is a subject to default;
    * the body resolves it with `self._who(on)`, which is
      `self.target if on is None else on`. Verbs that write
      `on or self.me` are **excluded** -- `c.aura` and `c.watch` are the
      common ones, and counting them put the first measurement of this at
      888 sites instead of 162;
    * and no `or self.me` / `if on is not None else self.me` fallback after
      it. `c.end_effect`, `c.save` and `c.regeneration` all have one, so a
      bare call there is correct and must not be flagged.
    """
    import inspect

    from combat_engine.engine.cast import Cast

    out: set[str] = set()
    for name in dir(Cast):
        if name.startswith("__"):
            continue
        fn = getattr(Cast, name, None)
        if not callable(fn):
            continue
        try:
            sig = inspect.signature(fn)
            src = inspect.getsource(fn)
        except (TypeError, ValueError, OSError):
            continue
        p = sig.parameters.get("on")
        if p is None or p.default is not None:
            continue
        if not re.search(r"self\._who\(\s*on\s*\)", src):
            continue
        if re.search(r"_who\(\s*on\s*\)\s*or\s+self\.me", src):
            continue
        if re.search(
            r"_who\(\s*on\s*\)\s*if\s+on\s+is\s+not\s+None\s+else\s+self\.me", src
        ):
            continue
        out.add(name)

    # **One hop, because a quarter of this family does not resolve `on` at
    # all -- it hands it to a verb that does.** `c.insubstantial` is
    # `self.condition(..., on=on)`; so are `c.dazed`, `c.prone`,
    # `c.stunned`, `c.slowed`, `c.weakened`, `c.immobilized`, `c.blinded`,
    # `c.unconscious` and `c.cannot_shift`, and another twenty go through
    # `c.bonus` the same way. The three tests above all read the verb's own
    # source, so every one of them was invisible: 92 verbs where there are
    # 122, and the missing 30 are the whole condition family.
    #
    # Found by writing `c.insubstantial(until=When.SONT)` for a card that
    # says "you gain insubstantial" and watching nothing happen. That is a
    # fault this check exists to catch and it was not even a candidate.
    #
    # Derived, not listed, for the same reason the set above is: `on=on`
    # forwarded to a method already proved target-defaulting inherits the
    # proof exactly. A second hop would need the same argument again and no
    # verb in the tree takes one, so the walk stops here rather than
    # recursing into a shape that does not exist.
    for name in dir(Cast):
        if name.startswith("__") or name in out:
            continue
        fn = getattr(Cast, name, None)
        if not callable(fn):
            continue
        try:
            sig = inspect.signature(fn)
            src = inspect.getsource(fn)
        except (TypeError, ValueError, OSError):
            continue
        p = sig.parameters.get("on")
        if p is None or p.default is not None:
            continue
        if any(hop in out for hop in re.findall(FORWARDS, src)):
            out.add(name)
    return frozenset(out)


#: A `Cast` verb handing its own `on=` straight to another one, for
#: `_subjectless_verbs`' second pass. `on=on` and not `on=something_else`:
#: a verb that computes a subject and passes *that* has made the decision
#: the check is looking for.
FORWARDS = re.compile(r"self\.(\w+)\([^)]*\bon=on\b")


def _subjectless_calls() -> list[tuple[str, str, str]]:
    """A row declaring `target=NO_TARGET` acting on its own absent target.

    **`on=` defaults to `c.target`, not `c.me`**, which `content/CLAUDE.md`
    already calls "the commonest single mistake here". What it could not say
    is when the mistake is *provable*: usually `c.target` is set and reading
    the card is the only way to know which creature the sentence means. A
    row whose header declares `target=NO_TARGET` has no target at all, so a
    bare call there is dead by construction and needs no card to judge.

    Nine sites in eight rows when this was written, and every one was a real
    fault:

    * seven monster traits printing "while **this creature** is bloodied"
      -- `c.bloodied()` with no subject returns False for ever, so the
      bonus, the shift, the Requirement and the doubled aura damage were
      all permanently off. None carried a marker.
    * `p10191b` read "your implement's enhancement bonus" as `c.held()`,
      which asks what the *target* is holding. It always came to the
      printed 5 -- and the docstring had rationalised that as "everything
      chargen deals is plain", which is true and is not why.

    That last one is the case for this being static rather than left to the
    audit: the row fires, does something, and audits green. Only the
    *subject* is wrong, and nothing at runtime can tell that from a card
    that really does mean nobody.
    """
    verbs = _subjectless_verbs()
    out: list[tuple[str, str, str]] = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            ref = ""
            no_target = False
            for dec in fn.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                for kw in dec.keywords:
                    if kw.arg == "target" and isinstance(kw.value, ast.Name):
                        no_target = kw.value.id == "NO_TARGET"
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    ref = str(dec.args[0].value)
            if not no_target or not ref:
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                if not isinstance(f, ast.Attribute) or f.attr not in verbs:
                    continue
                if not (isinstance(f.value, ast.Name) and f.value.id == "c"):
                    continue
                # `on=` is the author saying who, which is all this check
                # wants.
                if any(k.arg == "on" for k in node.keywords):
                    continue
                # **A positional argument is only a subject where `on` can
                # actually be passed as one, and for 107 of these 122 verbs
                # it cannot** -- `on` is keyword-only, so the first
                # positional is an amount, a key, a damage type or a
                # condition. Skipping every call with any positional hid 35
                # further sites, including `c.resist_forced(N)` in 19
                # separate monster traits and `c.vulnerable(5, RADIANT)`
                # standing two lines from a bare `c.insubstantial` this
                # check already reported.
                #
                # The 15 verbs that *do* take it positionally are the
                # readers -- `c.bloodied(foe)`, `c.size_of(ally)` -- where
                # the first argument genuinely is the creature, and there
                # the old skip was right. Decided off the signature rather
                # than a list, so a verb that changes shape is reclassified
                # by the check instead of by somebody remembering.
                if node.args and f.attr not in _KEYWORD_ONLY_SUBJECT:
                    continue
                out.append((f"{path}:{node.lineno}", ref, f.attr))
    return out


def _keyword_only_subject() -> frozenset[str]:
    """Of `_subjectless_verbs`, those whose `on` is **keyword-only**.

    For these a positional argument can never be the subject, so a call
    carrying one is still subjectless. See `_subjectless_calls`.
    """
    import inspect

    from combat_engine.engine.cast import Cast

    out = set()
    for name in _subjectless_verbs():
        try:
            p = inspect.signature(getattr(Cast, name)).parameters.get("on")
        except (TypeError, ValueError):
            continue
        if p is not None and p.kind is inspect.Parameter.KEYWORD_ONLY:
            out.add(name)
    return frozenset(out)


#: Computed once; `_subjectless_calls` asks it per call site.
_KEYWORD_ONLY_SUBJECT = _keyword_only_subject()


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
            called = getattr(node.func, "attr", None)
            if called not in ("bonus", "penalty", *_GATE_CONTEXT):
                continue
            what = (
                node.args[0].value
                if node.args and isinstance(node.args[0], ast.Constant)
                else ""
            )
            if called in _GATE_CONTEXT:
                known = _context_keys(_GATE_CONTEXT[called])
            else:
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
#: **And every bare skill name.** `skills.check` reads
#: `f"skill:{name}"` plus the blanket `"skill"`; the *ability* reader two
#: functions down reads `f"ability:{x}"` plus `"ability_check"`. So a bare
#: `c.bonus("perception", 2)` lays a key **neither** consults, while
#: reading exactly like the 37 rows that spell `skill:perception`
#: correctly.
#:
#: Four rows did it -- two on perception, one on stealth, one more on
#: perception -- and the clearest evidence it was a slip rather than a
#: convention is `m1828a5`, whose own marker reads
#: `narrative=("skill:perception",)` while its body laid the bare key. The
#: row named the right form and used the wrong one.
#:
#: Derived from `skills.SKILLS` rather than listed, so a skill added to the
#: engine cannot arrive with a hole beside it. The *rule* stays
#: hand-stated, which is what the note above asks for: the engine has a
#: verb for this (the prefixed key) and no reader for the bare form.
def _bare_skill_keys() -> dict[str, str]:
    from combat_engine.engine.skills import SKILLS

    return {
        name: f'c.bonus("skill:{name}", …) -- the bare key is read by nothing'
        for name in SKILLS
    }


UNREAD_MODIFIER_KEYS = {
    "initiative": "c.initiative(amount, on=)",
    **_bare_skill_keys(),
}


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
    call -- and so are `obsolete=`, `declined=` and `defect=`.
    """
    out = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for start, _end, ref, node in _rows(tree):
            dec = " ".join(ast.unparse(d) for d in node.decorator_list)
            if any(m in dec for m in
                   ("todo=", "obsolete=", "declined=", "defect=")):
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


def _db_reaches_upward() -> list[tuple[str, str]]:
    """`db.py` must import nothing from `combat_engine`. It sits below everything.

    That is the whole property the module exists for. ETL, content, chargen,
    story and the API all read `game.db` through it, so the moment it imports
    any of them it has a direction and one of those five is reaching through
    another to get to a sqlite file -- which is the state #334 was filed about,
    when the read path lived in `etl/build.py` and four components pulled 3,828
    lines of compendium parsing to open a read-only database.

    Measured at the time of the move:

        import combat_engine.db           13.7 ms   2 modules, 0 parsers
        import combat_engine.etl.build    67.8 ms  11 modules, 7 parsers

    A static check rather than that timing, because the timing varies and the
    import graph does not. #334.
    """
    path = ROOT / "src/combat_engine/db.py"
    if not path.exists():
        return []
    out: list[tuple[str, str]] = []
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level or name.startswith("combat_engine"):
                out.append((f"db.py:{node.lineno}", name or "a relative import"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("combat_engine"):
                    out.append((f"db.py:{node.lineno}", alias.name))
    return out


def _iterates_the_defence_enum() -> list[tuple[str, str]]:
    """`for d in Defense` / `*Defense`, which no longer means the four.

    `Defense.ANY` is a fifth member and is an *instruction* -- "whichever
    defence is lowest" -- not a defence a creature has. So iterating the enum
    to mean "all defences" now reaches one more thing than the author meant,
    and both halves of that are silent: a `c.bonus` laid under `ANY` is read
    by nothing, and `Defenses(values=dict.fromkeys(Defense, 0))` gives a
    creature a defence that is not one.

    Thirteen sites existed when `ANY` was added -- two of them `Cast`'s own
    second wind and total defence, i.e. +2 to all defences on every character
    who has ever taken either. All thirteen were rewritten to `DEFENCES`, and
    this walk is what stops the fourteenth being written.

    **Why a walk rather than trusting the docstring.** Fifteen content files
    had already hand-written `ALL_DEFENCES = (AC, FORT, REF, WILL)` before the
    engine owned the tuple, which is fifteen authors independently reaching for
    the four and not finding them. The next one reaches for the enum. #360.
    """
    out: list[tuple[str, str]] = []
    for path in _every_py():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        where = path.relative_to(ROOT)
        for node in ast.walk(tree):
            # `for x in Defense:` and any comprehension over it.
            iters = []
            if isinstance(node, ast.For | ast.comprehension):
                iters.append(node.iter)
            elif isinstance(node, ast.Starred):
                iters.append(node.value)
            elif isinstance(node, ast.Call):
                # `dict.fromkeys(Defense, 0)`, `list(Defense)`, `set(Defense)`.
                iters.extend(node.args[:1])
            for each in iters:
                if isinstance(each, ast.Name) and each.id == "Defense":
                    out.append((f"{where}:{node.lineno}", "Defense"))
    return out


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


def _minor_with_a_declared_trigger() -> list[tuple[str, str]]:
    """`action=MINOR` with a declared `Trigger`, which is never subscribed.

    `triggers.WINDOW_OF` maps the three immediate actions, `FREE` and `NONE`
    to a bus window and has **no entry for `MINOR`**. So the trigger is never
    registered, the body never runs, and the row reads as finished: the
    decorator accepts it, this file passed it, and `audit.py` reports UNUSED
    -- which is indistinguishable from a Requirement the board cannot meet.
    #426.

    **Refused rather than given a window**, because a minor action with a
    trigger window would behave as both and no printed rule asks for that.
    The cards that look like they do are printing a *condition on acting*:
    `f723` prints "Minor Action" and "Trigger: When you become bloodied"
    together, and the honest reading is a `requires=`, which is what both
    rows this caught now use.

    So a prose `trigger="..."` beside a `requires=` is **correct** and is not
    flagged -- only a declared `on=Trigger(...)`, which is the half that
    silently does nothing.
    """
    out: list[tuple[str, str]] = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                kw = {k.arg: k.value for k in dec.keywords}
                if "action" not in kw or "on" not in kw:
                    continue
                if "MINOR" not in ast.unparse(kw["action"]):
                    continue
                if "Trigger(" not in ast.unparse(kw["on"]):
                    continue
                rel = path.relative_to(ROOT)
                out.append((f"{rel}:{dec.lineno}", node.name))
    return out


def _personal_reach_at_an_enemy() -> list[tuple[str, str]]:
    """`reach=PERSONAL` with an enemy-side target, which collapses the pool.

    **Measured rather than assumed, and it is not what #427 says.** That issue
    expects an empty pool and an UNUSED verdict. On a board holding three
    enemies, `candidates` returns:

        reach=PERSONAL   1 candidate -- the adjacent enemy -- for four rows
                         0 for the fifth
        once fixed       3, which is what each card allows

    So the usual failure is **silent narrowing**, not refusal: the row is
    offered against whichever creature happens to be adjacent and against
    nothing else, whatever its card says. `m115806a5` repeats a bite with
    reach 2 and could only ever reach 1; `m5337a3` may choose "one creature
    it can see" and could only choose an adjacent one. Only `m5843a5` was
    refused outright, and that is the one shape the issue describes.

    That is worse than an empty pool, because an empty pool reports UNUSED
    and a narrowed one reports `ok`.

    A clean rule rather than a judgement: there is no card for which the
    combination is the right reading.

    **`ONE_CREATURE` is `Target("enemy", 1)`**, which is why this resolves the
    constants instead of matching a literal `"enemy"` -- all five rows it
    found use the constant, and a check written the obvious way finds none of
    them.
    """
    enemy_side = {"ONE_CREATURE", "EACH_ENEMY"}
    out: list[tuple[str, str]] = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                kw = {k.arg: k.value for k in dec.keywords}
                if "reach" not in kw or "target" not in kw:
                    continue
                if "PERSONAL" not in ast.unparse(kw["reach"]):
                    continue
                aim = ast.unparse(kw["target"])
                if aim in enemy_side or '"enemy"' in aim or "'enemy'" in aim:
                    rel = path.relative_to(ROOT)
                    out.append((f"{rel}:{dec.lineno}", node.name))
    return out


def _count_the_area_decides() -> list[tuple[str, str, int]]:
    """`Target(count=N, everyone=True)` -- two contradictory claims, one discarded.

    `everyone=True` means the area decides who is in it, so `count` is never
    read. A header carrying both says "everybody" and "N of them" at once and
    nothing reports which won: a reader cannot tell a cap that is broken from a
    number that was never a cap.

    Ten rows carry it and **all ten cards print no cap** -- every one is a burst
    hitting "each target" or "<kind> in the burst", so the `1` on them is a
    default nobody read rather than a restriction being overridden. Which is
    why this is a lint rule and not an engine change: honouring `count` would
    have silently narrowed ten correct rows.

    Read those ten cards before loosening this. The printed shape that *would*
    need a cap -- "up to three creatures in the burst" -- is real in the books
    and simply does not appear among the rows written against `everyone=`.
    """
    out: list[tuple[str, str, int]] = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                for kw in dec.keywords:
                    if kw.arg != "target" or not isinstance(kw.value, ast.Call):
                        continue
                    aim = kw.value
                    if not any(k.arg == "everyone" for k in aim.keywords):
                        continue
                    # `count` is the second positional as well as a keyword.
                    said = None
                    if len(aim.args) >= 2 and isinstance(aim.args[1], ast.Constant):
                        said = aim.args[1].value
                    for k in aim.keywords:
                        if k.arg == "count" and isinstance(k.value, ast.Constant):
                            said = k.value.value
                    # 99 and up is the tree's spelling of "no cap", which is
                    # what `everyone=` already means -- agreement, not conflict.
                    if isinstance(said, int) and said < 99:
                        rel = path.relative_to(ROOT)
                        out.append((f"{rel}:{aim.lineno}", node.name, said))
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


def _dangling_implementations() -> list[tuple[str, str, str]]:
    """A row saying `implemented_in="X"` where X does not carry its clause.

    #550's convention is that a feat naming one power has its clause written
    into that power, gated on `c.feat("<the feat>")`. `implemented_in=` is
    how the feat says so, and `audit.py` trusts it: the row is reported
    finished and **never fired**.

    So the pointer is load-bearing, and the obvious way for it to rot is
    silent -- somebody rewrites the power and drops the `c.feat` branch, and
    the feat goes on claiming to be implemented by a row that no longer
    mentions it. Nothing would fail: the feat is not fired, the power still
    works, and `blocked.py` counts neither as owed.

    That is the exact shape of #492 (two hand-kept lists, nothing
    reconciles them) and #551 (a fixture with no freshness check), so this
    marker shipped with the check rather than acquiring one later.

    **Its own path set, deliberately.** `_asked_for()` returns content only
    and is scoped that way for a good reason (#388), but a sibling check
    inheriting it is #546 -- the unknown-context-key walk never runs over
    `engine/` and there is a live fault there it cannot see. The pair here
    is always content-to-content, so content is the right scope; it is
    written explicitly so that nobody has to wonder which it got.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    sources: dict[Path, str] = {}
    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
        sources[path] = path.read_text()

    out = []
    for ref, row in sorted(REGISTRY.items()):
        hosts = getattr(row, "implemented_in", ()) or ()
        # **Two spellings, and the second is the one the convention
        # prefers.** `c.feat("f993")` is how an *unbracketed* clause is
        # gated. A feat printing a bracketed category is reached through
        # `c.declare(category, …)` instead, and `content/CLAUDE.md` is
        # explicit that the branch then reads `if arena == "f974":` and
        # **never** `c.feat("f974")`, because `c.feat` is true for every
        # feat held and cannot say which one is being applied (#554).
        #
        # So the check asked for the one spelling the convention forbids
        # for bracketed feats. It was green only because no bracketed feat
        # had yet been migrated this way; `f993` into `p992` is the first,
        # and it went red for doing exactly what the rules say.
        asked = (f'c.feat("{ref}")', f'"{ref}"')
        for where in hosts:
            if where not in REGISTRY:
                out.append((ref, where, "names a row that is not declared"))
                continue
            # Every named row's own source must ask for this feat. Checked
            # per host rather than "any of them", or a feat naming four
            # powers would pass on one and leave three clauses missing.
            #
            # The `c.declare` spelling is recognised by the ref appearing
            # in a `c.declare(` call in the same source, which is narrower
            # than a bare ref mention: a docstring naming the feat is not a
            # branch on it.
            if any(f'"{where}"' in t and asked[0] in t for t in sources.values()):
                continue
            if any(
                f'"{where}"' in t
                and any(ref in call for call in _DECLARES.findall(t))
                for t in sources.values()
            ):
                continue
            out.append((ref, where,
                        f"that row's source neither asks {asked[0]} nor names"
                        f" it in a c.declare(…) call"))
    return out


#: The arguments of a `c.declare(` call, for `_dangling_implementations`.
#: Non-greedy to the closing bracket, which is enough: every call in the
#: tree is one line of literals and a category string.
_DECLARES = re.compile(r"c\.declare\(([^)]*)\)")


#: A ref, for the gate walk below. Matches the shapes the tree mints and
#: nothing looser -- a bare word would catch every string in `content/`.
_REF_SHAPE = re.compile(
    r"p\d+|m\d+(?:c\d+)?a\d+|i\d+[px]\d+|f\d+[a-z]?|cf:[\w-]+|rt:[\w-]+"
)


def _strings_in(tree: object, call: object) -> set[str]:
    """Every string constant in the function containing that call.

    For `_dead_terrain_labels`, where a label reaches
    `c.ignores_difficult` through a loop variable and no literal is in the
    call itself.
    """
    import ast as _ast

    for fn in _ast.walk(tree):  # ty: ignore[invalid-argument-type]
        if not isinstance(fn, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue
        if any(node is call for node in _ast.walk(fn)):
            return {
                node.value.lower()
                for node in _ast.walk(fn)
                if isinstance(node, _ast.Constant)
                and isinstance(node.value, str)
            }
    return set()


def _reinvented_area_tuple() -> list[tuple[str, str]]:
    """A file spelling `AREA_OR_CLOSE` out instead of importing it.

    #616 found five files each defining the same tuple of area shapes, and
    **four of the five left `"wall"` out** -- so "an area or a close attack"
    under-fired on the one wall row in the tree that declares an attack.
    Consolidating found twelve more sites, every one of them the same
    printed sentence and every one missing `"wall"`.

    Seventeen files is too many to keep agreeing by hand, so this is the
    check that stops the eighteenth. It is a **textual** test, deliberately:
    the fault is somebody writing the words out again, and that is visible
    in the source where it is invisible at runtime -- all the spellings
    behave identically until a wall row fires.

    **Order-insensitive**, because one of the twelve was
    `("area_burst", "close_burst", "close_blast")` -- the same three in a
    different order, which a substring match would have missed.

    The neighbouring tuples are **not** this and must stay apart, which is
    why the test is for exactly these three members and nothing wider:
    `("melee", "close_burst", "close_blast")` is the melee-reach question a
    dozen rows ask, and `("ranged", "area_burst", "wall")` is "a line aimed
    away from you", which excludes close bursts for a reason. Both are
    listed in `dsl.AREA_OR_CLOSE`'s own note.
    """
    import ast as _ast

    want = {"close_burst", "close_blast", "area_burst"}
    out = []
    for path in _asked_for():
        try:
            tree = _ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.Tuple, _ast.List, _ast.Set)):
                continue
            words = {
                e.value for e in node.elts
                if isinstance(e, _ast.Constant) and isinstance(e.value, str)
            }
            if words == want and len(node.elts) == 3:
                out.append((
                    f"{path}:{node.lineno}",
                    "spells AREA_OR_CLOSE out instead of importing it, and"
                    " so omits `\"wall\"`",
                ))
    return out


def _dead_terrain_labels() -> list[tuple[str, str]]:
    """A `DIFFICULT_LABELS` entry that nothing writes and nothing waives.

    The set is closed so `c.ignores_difficult(kind=)` can refuse a word no
    square carries -- #598, where 29 calls named one and each waived nothing
    while reading as a finished row. A closed set has its own failure mode:
    the cheapest way to silence the raise is to add the word, and then the
    set stops meaning anything.

    So every entry must be **used by somebody**. Two legitimate kinds:

    * written by `c.zone(difficult=...)`, which is the five words any zone
      lays today -- `forest`, `ice`, `rubble`, `water`, `web`;
    * waived by `c.ignores_difficult`, which is the words the *cards* print.
      Those are correct clauses waiting for a map that makes that ground,
      which is a different thing from a typo and is why both halves belong
      in the set.

    An entry in neither is dead weight, and this says so by name. It does
    **not** fault a label that is waived but never written: that is the
    honest state of a card whose ground nothing creates yet, and faulting it
    would push an author to delete a correct clause.
    """
    import ast as _ast

    from combat_engine.engine.cast import DIFFICULT_LABELS

    written: set[str] = set()
    waived: set[str] = set()
    for path in _asked_for():
        try:
            tree = _ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            f = node.func
            if not isinstance(f, _ast.Attribute):
                continue
            if f.attr == "ignores_difficult":
                word = None
                if node.args and isinstance(node.args[0], _ast.Constant):
                    word = node.args[0].value
                for kw in node.keywords:
                    if kw.arg == "kind" and isinstance(kw.value, _ast.Constant):
                        word = kw.value.value
                if isinstance(word, str):
                    waived.add(word.lower())
                else:
                    # **A word fed through a loop variable, which is how six
                    # files say a printed line naming three sorts of ground:
                    # `for kind in ("rubble", "uneven stone", ...)`.** The
                    # first draft read literal arguments only and reported
                    # four real labels as used by nobody. Every string in
                    # the enclosing function is taken rather than tracing
                    # the variable: this decides whether a vocabulary entry
                    # is dead, so a few extra words make it quieter and
                    # never wronger.
                    waived |= _strings_in(tree, node)
            elif f.attr in ("zone", "aura", "create"):
                for kw in node.keywords:
                    if (kw.arg == "difficult"
                            and isinstance(kw.value, _ast.Constant)
                            and isinstance(kw.value.value, str)):
                        written.add(kw.value.value.lower())
    return [
        (label, "in DIFFICULT_LABELS but no zone writes it and no row waives it")
        for label in sorted(DIFFICULT_LABELS - written - waived)
    ]


def _lends_nobody_asks_for() -> list[tuple[str, str, str]]:
    """`c.lend_augment("pNNN", …)` pointing at a row that never asks.

    The verb hands a power an Augment option its own card does not print,
    and its docstring states the obligation plainly: the lent-to row must
    call `augment.lent(c)` or **the lend is a modifier nothing consults**.

    That is a silent failure in every direction. The feat has a real body,
    so it is not SILENT; `audit.py` fires it alone and sees a modifier laid,
    so it reports the row firing and doing something; the power still works,
    because the missing call is an absence; and `blocked.py` counts no owed
    work. `f3170` sat in exactly that state -- marked for a verb that had
    existed for weeks, while the thing actually missing was one line in
    `p10440`.

    Same reasoning as `_dangling_implementations` above and the same scope:
    both halves of the pair are always content, so the walk is content.

    Read off the registry rather than by grepping file names, because four
    of the five lent-to powers live in modules whose names do not contain
    their ref -- a grep for the power would have missed them and the check
    would have been quietly green.
    """
    import inspect

    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    out = []
    for ref, row in sorted(REGISTRY.items()):
        try:
            lender = inspect.getsource(row.body)
        except (OSError, TypeError):
            continue
        for host in _LENDS.findall(lender):
            target = REGISTRY.get(host)
            if target is None:
                out.append((ref, host, "names a row that is not declared"))
                continue
            try:
                asked = inspect.getsource(target.body)
            except (OSError, TypeError):
                continue
            # The call, not the import: `general_o.py` imports `lent` once
            # for a module of rows and all but one of them never call it.
            if "lent(c)" not in asked:
                out.append((ref, host,
                            "that row never calls `augment.lent(c)`, so the"
                            " lend is a modifier nothing consults"))
    return out


#: The ref a `c.lend_augment(` call lends to. First argument, a literal in
#: every call in the tree -- a computed one would belong to a different
#: check, since there would be nothing to resolve at lint time.
_LENDS = re.compile(r'c\.lend_augment\(\s*"([^"]+)"')


def _gates_on_nothing() -> list[tuple[str, str, str]]:
    """Content **comparing** against a ref that no declared row can produce.

    `f3798` is why this exists. Its trigger predicate asked
    `ev.trigger.power == "p4807"`, and `p4807` is the compendium's second
    id for a card this tree declares as `cf:barbarian-f2c0` -- so the
    comparison was False for every event the row ever saw, the use it
    hands back was never handed back, and the row carried **no marker**,
    so it reported finished for as long as it existed.

    **A comparison, not a mention, and that distinction is the whole
    check.** 23 ref-shaped literals in `content/` name nothing declared
    and only one of them is a fault:

    * nine sit in a `todo=`/`dropped=` marker, which is the *correct* way
      to say "this gates on a row nobody has written" -- `f2817` does
      exactly that for `rt:r16-t1` and its docstring is a model of it;
    * eleven are the keys of a choice table in `feats/general_c.py`,
      offered to a player rather than matched against an event;
    * one is an f-string prefix;
    * one was `f3798`.

    A walk over mentions would be twelve waivers for one catch, which is
    the shape `leaks.py`'s over-broad name search was and the reason
    `--cited` replaced it. A walk over comparisons is one catch and no
    waivers, because none of the legitimate twenty-two is a comparison.

    **The first version of this walked only decorated row bodies and the
    plant test caught it**: putting `p4807` back left the check green,
    because the predicate is an undecorated module-level helper and the
    constant is module-level too. A row's trigger reaches code the row
    does not lexically contain, so per-row attribution was the wrong
    frame -- the file is.

    Content-scoped on purpose and written out rather than taken from
    `_asked_for()`, for `_dangling_implementations`'s reason: #546 is a
    differently-scoped check that inherited that default and misses a
    live fault because of it.
    """
    import ast

    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    declared = set(REGISTRY)
    out = []
    for path in sorted((ROOT / "src/combat_engine/content").rglob("*.py")):
        text = path.read_text()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        # Constants compared against, plus the module-level names bound to
        # a ref-shaped literal -- `_BURN_A_RAGE = "p4807"` then
        # `ev.power == _BURN_A_RAGE` is the same fault one indirection away,
        # and is how this file was written after the fault was fixed.
        aliases: dict[str, tuple[str, int]] = {}
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and _REF_SHAPE.fullmatch(node.value.value)):
                aliases[node.targets[0].id] = (node.value.value, node.lineno)

        # `bound=aliases` rather than closing over it: the dict is rebuilt
        # per file inside the loop, and a closure over a loop variable is
        # the B023 ruff refuses -- rightly, since a later file's dict would
        # be the one consulted.
        def named(side: ast.expr,
                  bound: dict[str, tuple[str, int]] = aliases,
                  ) -> tuple[str, int] | None:
            if (isinstance(side, ast.Constant) and isinstance(side.value, str)
                    and _REF_SHAPE.fullmatch(side.value)):
                return side.value, side.lineno
            if isinstance(side, ast.Name) and side.id in bound:
                return bound[side.id][0], side.lineno
            return None

        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for side in (node.left, *node.comparators):
                found = named(side)
                if found and found[0] not in declared:
                    out.append((path.name, found[0], f"line {found[1]}"))
    return out


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


def _event_attrs_known() -> tuple[dict[str, set[str]], set[str]]:
    """What each event carries, and what the engine bolts on afterwards.

    Two sets, and the second is what makes this walk usable. **An event's
    declared fields are not its whole surface**: `resolve.py:384` sets
    `landed.result`, `:385` sets `landed.among`, `movement.py:175` sets
    `moved.kind_` and `expect.py:269-270` sets both on a rehearsed attack. So
    `Hit` has no `result` field and **18 rows read `ev.result` correctly**.

    The attached set is **derived** by scanning `engine/` for an attribute
    assignment rather than listed, and over-collects deliberately: a name this
    picks up spuriously only makes the walk quieter, while a name it misses is
    a false accusation against a working row. That is the opposite direction
    from `_common_words`' guard and for the opposite reason -- there the costly
    error is the hidden leak, here it is the wrong finding.
    """
    import dataclasses
    import re as _re

    from combat_engine.engine import events as _events

    declared: dict[str, set[str]] = {}
    for name in dir(_events):
        cls = getattr(_events, name)
        if isinstance(cls, type) and dataclasses.is_dataclass(cls):
            declared[name] = {f.name for f in dataclasses.fields(cls)} | set(dir(cls))

    attached: set[str] = set()
    for path in (ROOT / "src/combat_engine/engine").rglob("*.py"):
        for hit in _re.finditer(r"^\s*\w+\.(\w+)\s*=\s*[^=]", path.read_text(), _re.M):
            attached.add(hit.group(1))
    return declared, attached


def _event_attrs() -> list[tuple[str, str, str]]:
    """Reads of an attribute the watched event does not have and never gets.

    `_effect_attrs` one object over, and the same failure: a name spelled
    correctly against the wrong class. `scorecard.py` raised
    `'Dropped' object has no attribute 'ghost'` in a level-10 aura whose whole
    job is to react when an ally drops inside it -- so the handler could only
    ever crash -- and **`audit.py` reported that row `1 of 1 rows fire and do
    something`**, because the trait arms, the aura goes down, and nothing drops
    inside it on that board.

    `ghost` is declared on `TurnStart` and `TurnEnd` only and assigned in one
    place, `turns.py:425-426`, where a **dead** creature's turn is ticked so
    durations measured against it can end. A dead creature does not move and
    does not drop again, so `ev.ghost` on `Moved` or `Dropped` is meaningless
    as well as fatal: the clause comes out rather than getting a replacement.

    **Nested handlers are not walked through**, which cost two false
    accusations before it was fixed: these watchers nest, `ast.walk` descends
    into an inner `def`, and reads belonging to an inner `SavingThrow` handler
    were being charged to the outer `Hit` one. The sweep's number went 164 ->
    40 -> 7 -> 5 across three corrections, every earlier figure plausible and
    wrong, so the shape of each cut is recorded in `_event_attrs_known` and
    here rather than re-derived.
    """
    declared, attached = _event_attrs_known()

    def body_of(fn: ast.AST) -> list[ast.AST]:
        """This handler's own nodes, stopping at any nested callable."""
        out: list[ast.AST] = []
        stack = list(fn.body)  # type: ignore[attr-defined]
        while stack:
            node = stack.pop()
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            ):
                continue
            out.append(node)
            stack.extend(ast.iter_child_nodes(node))
        return out

    out = []
    for path in _asked_for():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = fn.args.args
            if len(args) != 1 or args[0].annotation is None:
                continue
            annotation = args[0].annotation
            event = annotation.id if isinstance(annotation, ast.Name) else None
            if event not in declared:
                continue
            known, bound = declared[event], args[0].arg
            for inner in body_of(fn):
                if (
                    isinstance(inner, ast.Attribute)
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id == bound
                    and inner.attr not in known
                    and inner.attr not in attached
                ):
                    rel = path.relative_to(ROOT)
                    out.append(
                        (f"{rel}:{inner.lineno}", f"{bound}.{inner.attr}", event)
                    )
    return out


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
