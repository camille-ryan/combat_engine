"""Which feat rows can the dealer actually produce?

Every other instrument asks whether a row is **written** or **marked**.
None asks whether a character can ever **hold** it:

    audit.py     does it fire -- on a board that HAND-GRANTS it
    blocked.py   does it carry a todo=/dropped=
    todo.py      are its markers still true
    written.py   does a body exist
    legs.py      can every build leg be dealt

So a row can be written, unmarked, audited green, and unreachable in play.
This walks the dealer's own doors -- `chargen.loadout` and
`choices.legal_feats` -- and reports which feats reach a legal pool.

**It calls the dealer rather than re-deriving its test**, and that is the
whole design. `legs.py` records the same rule, and `#1415` is what happens
when it is broken: measuring `choices._legal_feats(...)` directly with
`taken=()` produced a confident "1,221 feats can never be dealt", which was
wrong and had to be retracted. The real caller `chargen.feats_for` passes the
character's powers as `taken`, and `loadout` returns its `cf:` rows among
them, so prerequisites naming a class feature or a power resolve normally.

**"Never offered" is always relative to a spread**, so the spread is printed
with the result and never implied. A feat wanting a particular chassis *and*
a particular race is narrow, not broken, and a census that does not say what
it sampled is the shape of the number that had to be withdrawn.

A **ledger, not a gate**: coverage moves with every chargen and content
change, so a check that reddens on ordinary progress gets routed around.
`triage.py --drift` and `localise.py --drift` are kept out of `check.py` for
exactly this reason.

    uv run scripts/dealable.py              the default spread
    uv run scripts/dealable.py --races      add a pass over every race
    uv run scripts/dealable.py --show 40    list some never-offered refs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HEROIC = (1, 4, 8, 10)


def _spread(races: bool) -> list[tuple[str, int, str, str, str]]:
    """Every `(class, level, chassis, leg, race)` this run will deal.

    Chassis and leg are enumerated because they decide which class features a
    character holds -- measured, **693 of 827 `cf:` rows are chassis-tied** --
    so a spread over classes alone would under-report by construction.
    """
    from combat_engine import chargen

    out: list[tuple[str, int, str, str, str]] = []
    for cls in sorted(chargen.CLASSES):
        chassis_list = chargen.declared_chassis(cls) or ("",)
        for chassis in chassis_list:
            legs = chargen.legs_for(cls, chassis) or ()
            names = [b.name for b in legs] or [""]
            for leg in names:
                for level in HEROIC:
                    out.append((cls, level, chassis, leg, ""))
    if races:
        from combat_engine import db

        every = [r[0] for r in db.game().execute("select distinct ref from race")]
        for cls in sorted(chargen.CLASSES):
            for race in every:
                out.append((cls, 10, "", "", race))
    return out


def _offered(spread: list[tuple[str, int, str, str, str]]) -> set[str]:
    """The union of every legal feat pool across the spread."""
    from combat_engine import chargen
    from combat_engine.chargen import choices

    seen: set[str] = set()
    legs_by: dict[tuple[str, str], dict[str, object]] = {}
    for cls, level, chassis, leg, race in spread:
        key = (cls, chassis)
        if key not in legs_by:
            legs_by[key] = {b.name: b for b in (chargen.legs_for(cls, chassis) or ())}
        build = legs_by[key].get(leg) or chargen.build_of(cls)
        try:
            powers = list(chargen.loadout(cls, level, build, who_chassis=chassis) or [])
        except TypeError:
            powers = list(chargen.loadout(cls, level, build) or [])
        except Exception:
            powers = []
        try:
            seen |= set(choices.legal_feats(cls, level, build, race, taken=powers))
        except Exception:
            continue
    return seen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--races", action="store_true",
                    help="add a pass over every race at level 10")
    ap.add_argument("--show", type=int, default=0,
                    help="list this many never-offered refs")
    args = ap.parse_args(argv)

    import combat_engine.content  # noqa: F401  registers the rows
    from combat_engine.engine.dsl import REGISTRY

    declared = {r for r, p in REGISTRY.items()
                if r.startswith("f") and not p.todo and not p.dropped}
    spread = _spread(args.races)
    seen = _offered(spread)
    offered = seen & declared
    never = declared - seen

    print(f"  spread            {len(spread)} (class, level, chassis, leg, race) "
          f"combinations, levels {HEROIC}"
          + (", every race at 10" if args.races else ", race unset"))
    print(f"  declared feats    {len(declared)}  (written, unmarked)")
    print(f"  offered at least once {len(offered)}")
    print(f"  never offered     {len(never)}")
    if declared:
        print(f"  coverage          {100 * len(offered) / len(declared):.1f}%")
    if args.show and never:
        print()
        print(f"  a sample of never-offered, {min(args.show, len(never))} of {len(never)}:")
        print("   ", " ".join(sorted(never)[:args.show]))
    print()
    print("  A ledger, not a gate. 'Never offered' is relative to the spread")
    print("  above: a feat wanting a particular chassis AND race is narrow,")
    print("  not broken. Widen the spread before calling anything unreachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
