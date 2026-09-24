#!/usr/bin/env python
"""Everything a power body can say, generated from the code.

    uv run scripts/vocab.py
    uv run scripts/vocab.py --brief        signatures only
    uv run scripts/vocab.py --header       the decorator's arguments

This is the briefing handed to whoever is about to write a power, and it is
generated rather than written, so it cannot drift from what `Cast` actually
offers. A hand-kept capability document is a document that is wrong by the
second week -- that is how the first attempt ended up with 546 op shapes and
a reference nobody trusted.

If a power needs something that is not in here, the answer is to add a
method to `Cast`, not to work around its absence. Adding one is a few lines,
breaks nothing, and every later power gets it.
"""

from __future__ import annotations

import argparse
import inspect

from combat_engine.engine import types as T
from combat_engine.engine.cast import Cast
from combat_engine.engine.dsl import Attack, Damage, Range, Target, power
from combat_engine.engine.durations import When

#: The order a body tends to need them in, so the page reads like the work.
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--brief", action="store_true", help="signatures only")
    ap.add_argument("--header", action="store_true", help="the @power arguments")
    args = ap.parse_args()

    if args.header:
        _header()
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

    rest = [
        n
        for n in dir(Cast)
        if not n.startswith("_") and n not in shown and n not in ("world", "me", "ref",
                                                                  "targets", "target",
                                                                  "index", "origin", "result",
                                                                  "stats", "mod", "used")
    ]
    if rest:
        print("\n## everything else\n")
        for name in sorted(rest):
            print(_render(name, getattr(Cast, name), brief=args.brief))

    _vocab()
    _header()
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
