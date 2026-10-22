#!/usr/bin/env python
"""Everything a power body can say, generated from the code.

    uv run scripts/vocab.py
    uv run scripts/vocab.py --brief        signatures only
    uv run scripts/vocab.py --header       the decorator's arguments
    uv run scripts/vocab.py --find a b     every symbol whose docstring says
                                           **all** of those words

This is the briefing handed to whoever is about to write a power, and it is
generated rather than written, so it cannot drift from what `Cast` actually
offers. A hand-kept capability document is a document that is wrong by the
second week -- that is how the first attempt ended up with 546 op shapes and
a reference nobody trusted.

**Read `docs/symbols/<category>.md` first.** This file prints all 397
members of `Cast` in one stream, and the whole of it is more than a row
needs: if you know what *kind* of symbol you want -- a movement verb, a
condition, a modifier, a ctx gate -- one category file is a tenth the
reading and names the near-misses in the other files. `scripts/symbols.py`
generates those from `CATEGORIES` and `check.py` fails when they drift, so
they are as current as this is. Come here when you do not know the
category, or want the signature of something you have already found.

If a power needs something that is not in here, the answer is to add a
method to `Cast`, not to work around its absence. Adding one is a few lines,
breaks nothing, and every later power gets it.
"""

from __future__ import annotations

import argparse
import inspect
import re
import sys

from combat_engine.engine import types as T
from combat_engine.engine.cast import Cast
from combat_engine.engine.dsl import Attack, Damage, Range, Target, power
from combat_engine.engine.durations import When

#: The order a body tends to need them in, so the page reads like the work.
#: Fields `Cast` has grown that `CONTEXT` does not describe. Collected
#: rather than raised, and reported after everything has been printed.
_GREW: list[str] = []

GROUPS = [
    ("attacking", ["strike", "attack", "landed", "crit"]),
    ("damage and healing", ["hit", "damage", "half_damage", "flat", "heal",
                            "surge", "temp_hp", "ongoing"]),
    ("moving things", ["push", "pull", "slide", "shift", "move", "teleport", "flee"]),
    ("conditions", ["condition", "prone", "dazed", "stunned", "slowed",
                    "immobilized", "weakened", "blinded", "unconscious",
                    "mark", "grab", "grants_advantage"]),
    ("modifiers", ["bonus", "penalty", "total"]),
    ("areas and triggers", ["zone", "aura", "hazard", "area", "watch"]),
    ("asking the board", ["allies", "enemies", "within", "in_squares", "distance",
                          "adjacent", "can_see", "is_", "bloodied", "wounded",
                          "speed_of", "here", "there", "first", "last"]),
    ("the caster's numbers", ["str_", "dex_", "con_", "int_", "wis_", "cha_",
                              "str_mod", "dex_mod", "con_mod", "int_mod",
                              "wis_mod", "cha_mod", "level", "w", "wielding"]),
    ("choices and notes", ["choose", "note"]),
]  # fmt: skip


def _find(words: list[str]) -> int:
    """Search what the code *says it does*, not what it is called.

    **This is the instrument for the commonest and most expensive mistake in
    this project**: filing a gap for something that already exists under
    another name. `content/CLAUDE.md` has warned about it in as many words
    for a long time -- "most gaps filed here have turned out to exist under
    another name" -- and it kept happening, because the rule asks you to
    search and the only search was `grep` over a name you do not know.

    349 verbs across 10,486 lines of `cast.py`, with near-synonyms
    throughout: `as_basic`/`no_basic`/`counts_as`, `instead_of`/
    `instead_of_now`/`pre_empt`, `extend_move`/`extend_shift`. Knowing a
    facility exists does not tell you what it is called.

    Seven families in one session were marked for a gap that was already
    filled -- `c.contract` for "no contraction mechanism", `rage.raging()`
    for "nothing says a barbarian is raging", `race:<ref>` on
    `Build.choices` for "a racial choice is recorded nowhere". Those three
    live in three different places, which is why this searches wider than
    `Cast`:

    * `Cast` methods -- the verb surface;
    * `query`, `triggers`, `dsl` functions -- the readers;
    * `components` fields and their `#:` notes -- where state lives;
    * module-level helpers in `content/` -- `rage.raging`, `_holding_ref`.

    Matching is on the **docstring and the surrounding note**, not the name.
    A name search is what already failed.

    **Pass separate words, not a quoted phrase.** Every argument is ANDed
    against the docstring independently, so `--find ignore resistance`
    finds 36 places and `--find "ignore resistance"` finds none -- the
    quoted form is one literal argument, and no docstring contains that
    exact string. Four verbs that exist were marked missing in one session
    after the quoted form came back empty, and the first conclusion drawn
    was that this instrument was broken. It was not; it was being asked for
    a phrase.
    """
    import re as _re
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    wanted = [w.lower() for w in words]

    def hit(text: str) -> bool:
        low = text.lower()
        return all(w in low for w in wanted)

    found: list[tuple[str, str, str]] = []

    # Cast, and the three reader modules, through their own docstrings.
    import combat_engine.engine.dsl as _dsl
    import combat_engine.engine.query as _query
    import combat_engine.engine.triggers as _triggers
    from combat_engine.engine.cast import Cast as _Cast

    for label, obj in (("c.", _Cast), ("query.", _query),
                       ("triggers.", _triggers), ("dsl.", _dsl)):
        for name, member in sorted(vars(obj).items()):
            if name.startswith("__") or not callable(member):
                continue
            doc = inspect.getdoc(member) or ""
            if hit(f"{name} {doc}"):
                first = doc.strip().splitlines()[0] if doc.strip() else "(no docstring)"
                found.append((f"{label}{name}", first[:96], "verb"))

    # Component fields, whose `#:` notes say what the state is for.
    comp = (root / "src/combat_engine/engine/components.py").read_text()
    for blk in _re.split(r"\n(?=@dataclass)", comp):
        cls = _re.search(r"\nclass (\w+)", blk)
        if not cls:
            continue
        for m in _re.finditer(r"((?:\s*#:[^\n]*\n)+)\s*(\w+)\s*:", blk):
            note, field = m.group(1), m.group(2)
            if hit(f"{field} {note}"):
                line = " ".join(note.replace("#:", "").split())
                found.append((f"{cls.group(1)}.{field}", line[:96], "state"))

    # Helpers the content tree shares between its own rows.
    for path in sorted((root / "src/combat_engine/content").rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        src = path.read_text(errors="replace")
        for m in _re.finditer(r'\ndef (\w+)\([^)]*\)[^:]*:\n\s+"""(.*?)"""', src, _re.S):
            name, doc = m.group(1), m.group(2)
            if hit(f"{name} {doc}"):
                rel = path.relative_to(root / "src/combat_engine/content")
                first = " ".join(doc.split())[:88]
                found.append((f"{rel.as_posix().removesuffix('.py').replace('/', '.')}.{name}",
                              first, "helper"))

    if not found:
        print(f"nothing in the vocabulary mentions {' + '.join(words)!r}.")
        print("That is weak evidence of absence -- try one word, or a synonym.")
        return 1
    print(f"{len(found)} place(s) mention {' + '.join(words)}:\n")
    for kind in ("verb", "state", "helper"):
        rows = [f for f in found if f[2] == kind]
        if not rows:
            continue
        print(f"  -- {kind} --")
        for name, blurb, _ in rows[:24]:
            print(f"  {name:46} {blurb}")
        if len(rows) > 24:
            print(f"  ... and {len(rows) - 24} more")
        print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--find", nargs="+", metavar="WORD",
                    help="what already does this? searches docstrings, not names")
    ap.add_argument("--brief", action="store_true", help="signatures only")
    ap.add_argument("--header", action="store_true", help="the @power arguments")
    ap.add_argument("--examples", action="store_true", help="only the worked rows")
    args = ap.parse_args()

    if args.find:
        return _find(args.find)
    if args.header:
        _header()
        return 0
    if args.examples:
        _examples()
        return 0

    print("# What a power body can say\n")
    print("The body is called once per target. `c.target` is whichever target")
    print("this call is for; `c.first` is True on the first of them, which is")
    print("where a once-per-power line goes. Everything aims at `c.target`")
    print("unless given `on=`.\n")

    shown: set[str] = set()
    for title, names in GROUPS:
        print(f"\n## {title}\n")
        for name in names:
            member = getattr(Cast, name, None)
            if member is None:
                continue
            shown.add(name)
            print(_render(name, member, brief=args.brief))

    _context()
    shown |= set(CONTEXT) | {"stats", "mod", "used"}

    rest = [n for n in dir(Cast) if not n.startswith("_") and n not in shown]
    if rest:
        print("\n## everything else\n")
        for name in sorted(rest):
            print(_render(name, getattr(Cast, name), brief=args.brief))

    _vocab()
    _header()
    if not args.brief:
        _examples()
    if _GREW:
        print(
            f"\nvocab.py: Cast grew {_GREW}; describe them in CONTEXT.",
            file=sys.stderr,
        )
        return 1
    return 0


def _render(name: str, member: object, *, brief: bool) -> str:
    if isinstance(member, property):
        doc = (member.__doc__ or "").strip().split("\n")[0]
        return f"  c.{name}" + (f"\n      {doc}" if doc and not brief else "")
    try:
        sig = str(inspect.signature(member)).replace("self, ", "").replace("(self)", "()")
    except (TypeError, ValueError):
        sig = "(...)"
    line = f"  c.{name}{sig}"
    if brief:
        return line
    doc = (member.__doc__ or "").strip().split("\n")[0]
    return line + (f"\n      {doc}" if doc else "")


#: One worked row per shape, chosen by what the row *is* rather than by ref,
#: so the section cannot rot when a row is rewritten or removed. The shapes
#: are the ones that have cost somebody time -- a signature says what
#: `on=Trigger(...)` takes and still leaves you guessing what a declared
#: trigger looks like next to its printed `trigger=` prose.
#:
#: This exists because agents were being handed a 2,226-line monster file to
#: "copy the shape of", at four times the cost of the whole vocabulary.
SHAPES = [
    ("the plainest row: attack, damage, rider",
     lambda p, s: p.cls and p.attack and "c.strike()" in s and "c.prone()" in s),
    ("a declared trigger -- `trigger=` is prose, `on=` is what fires",
     lambda p, s: p.on and p.trigger),
    ("a save-ends rider",
     lambda p, s: "SAVE_ENDS" in s and p.cls),
    ("a burst, with `c.first` for the once-per-power line",
     lambda p, s: "c.first" in s and p.reach.__class__.__name__ != "Melee"),
    ("a charge -- `charges=True` or the engine refuses it out of reach",
     lambda p, s: p.charges),
    ("healing, and whose surge is spent",
     lambda p, s: "c.surge(" in s or "c.spend_surge(" in s),
    ("a zone or an aura",
     lambda p, s: "c.zone(" in s or "c.aura(" in s),
    ("a monster: numbers load from the database, the attack line is printed",
     lambda p, s: p.ref.startswith("m") and p.attack and p.damage),
    ("a monster recharge -- two header fields, not a callable",
     lambda p, s: p.ref.startswith("m") and p.recharge),
    ("deliberately inert: the printed effect is not a combat effect",
     lambda p, s: p.out_of_combat),
    ("an entry requirement the board has to meet",
     lambda p, s: p.requires is not None),
]


#: The context's own fields. They are plain dataclass attributes, so they
#: have no signature and no docstring and the generated page used to drop
#: them silently -- `c.targets` among them, which is the only way to say "if
#: you hit two creatures, both are affected". A runepriest wave had to open
#: `cast.py` to find it, which is exactly the reading this page exists to
#: prevent. Hand-written, and `_context` fails loudly if a field appears or
#: disappears, so the drift it costs is bounded.
CONTEXT = {
    "me": "the caster's eid. `on=c.me` aims a target-defaulting method back at you.",
    "target": "the target this call is for, or None. Everything defaults here.",
    "targets": "**every** target of this one use, as a list -- what "
               '"if you hit two creatures" needs. `c.target` is one of them.',
    "index": "which target this is, counting from 0. `c.first` is `index == 0`.",
    "ref": "this row's own id.",
    "result": "the last `AttackResult`, or None. `.advantage` is whether the "
              "attack had combat advantage; asking again is too late.",
    "swings": "every `AttackResult` this body has rolled for the current "
              "target, in order, where `result` is only the last. Read it "
              "when a clause says *every* attack roll you made; `result` "
              "answers \"did that one hit\". #810.",
    "trigger": "the event being answered, on an interrupt or reaction.",
    "origin": "the square an area was aimed at.",
    "charge": "is this use a charge?",
    "opportunity": "is this use an opportunity attack?",
    "branch": "which half of a melee-or-ranged row is being used.",
    "augment": "how many power points this use was augmented by, or 0.",
    "granted_by": "who handed this creature the basic attack, or -1.",
    "granted_via": "the ref of the row that handed it over, or empty.",
    "variant": "which variant of a substituted clause this use is -- `0` is "
               "the printed one. `c.instead_of` reads it; `Trigger._ask` "
               "offers them.",
    "declared_feats": "the feat already picked for each bracketed category "
                      "this use, so `c.declare` asks once and every later "
                      "clause honours the same answer.",
    "world": "the world itself. Prefer the methods above; reach for this last.",
}


def _context() -> None:
    """What the `c` handed to a body already knows, before it calls anything.

    **This used to `SystemExit` when `Cast` grew a field, and it is called
    from the middle of `main`.** So the moment three fields landed, the
    whole "everything else" section below it -- about two hundred of
    `Cast`'s three hundred members -- stopped being printed, and the
    document every author is told to grep before marking a row quietly
    became a third of itself. Six verbs that exist were marked missing
    by four different agents in one afternoon because of it.

    A tool that hides what it knows is worse than one that complains, so
    it complains at the end and prints everything either way.
    """
    import dataclasses

    fields = {f.name for f in dataclasses.fields(Cast)}
    if missing := fields - set(CONTEXT):
        _GREW.extend(sorted(missing))

    print("\n## what `c` already knows\n")
    for name, note in CONTEXT.items():
        if name in fields:
            print(f"  c.{name}\n      {note}")


def _dangling(src: str) -> int:
    """Names the row borrows from its own file, and so cannot carry with it.

    A body that is one call to `_steps_either_side(c, 1)` shows nothing at
    all once lifted out. Counted rather than rejected, because the same habit
    in a *header* -- `requires=_is_bloodied` -- is the idiom worth showing,
    and for some shapes every candidate has one.
    """
    return len(set(re.findall(r"(?<![\w.])_\w+", src)) - {"_"})


def _examples() -> None:
    """A real row per shape, shortest match wins, so the page stays small."""
    import inspect
    import sys

    sys.argv = sys.argv[:1]
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY

    sources = {}
    for ref, p in REGISTRY.items():
        try:
            sources[ref] = inspect.getsource(p.body)
        except (OSError, TypeError):
            continue

    print("\n## worked rows\n")
    print("Real rows from the tree, picked by shape rather than by name, so")
    print("they are current. Copy the shape, not the content.\n")

    shown: set[str] = set()
    for label, matches in SHAPES:
        best, best_score = None, None
        for ref, src in sources.items():
            if ref in shown or len(src) > 900:
                continue
            try:
                ok = matches(REGISTRY[ref], src)
            except AttributeError:
                continue
            if not ok:
                continue
            score = (_dangling(src), len(src))
            if best_score is None or score < best_score:
                best, best_score = ref, score
        if best is None:
            continue
        shown.add(best)
        print(f"### {label}\n")
        print("\n".join("  " + ln for ln in sources[best].rstrip().splitlines()))
        print()


def _vocab() -> None:
    print("\n## the words\n")
    for label, enum in (
        ("conditions", T.Condition), ("damage types", T.DamageType),
        ("defences", T.Defense), ("keywords", T.Keyword),
        ("abilities", T.Ability), ("usage", T.Usage),
    ):
        print(f"  {label:<14} {', '.join(m.value for m in enum)}")
    print(f"  {'durations':<14} " + ", ".join(f"When.{w.name}" for w in When))


def _header() -> None:
    print("\n## the header\n")
    sig = inspect.signature(power)
    for name, param in sig.parameters.items():
        if name == "ref":
            print("  ref                 the compendium id: p289, or m145a0")
            continue
        default = "" if param.default is inspect.Parameter.empty else f" = {param.default!r}"
        print(f"  {name:<19} {default}")
    print("\n  ranges     Melee(n)  Ranged(n)  CloseBurst(n)  CloseBlast(n)"
          "  AreaBurst(n, within)  PERSONAL")
    print("  targets    ONE_CREATURE  ONE_ALLY  SELF  EACH_ENEMY  EACH_ALLY"
          "  EACH_CREATURE  NO_TARGET  UpTo(n)")
    print(f"\n  {Attack.__name__}     {inspect.signature(Attack)}")
    print(f"  {Damage.__name__}     {inspect.signature(Damage)}")
    print(f"  {Range.__name__}      {inspect.signature(Range)}")
    print(f"  {Target.__name__}     {inspect.signature(Target)}")


if __name__ == "__main__":
    raise SystemExit(main())
