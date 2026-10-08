#!/usr/bin/env python
"""Fire one row and watch what it does.

    uv run scripts/show.py p289
    uv run scripts/show.py m206a1 --seed 4

The read-it-yourself check. It prints the printed text beside the events the
function actually emitted, on a fixed little board, so the two can be
compared by eye.

This is generated, never hand-written per row. The previous attempt owed a
bespoke check per power and it cost about an hour each; the whole point of a
power being code is that running it tells you more than reading a static
description of it would.
"""

from __future__ import annotations

import argparse
import re

from combat_engine import chargen
from combat_engine.content import loader
from combat_engine.content.loader import SIZES
from combat_engine.db import game
from combat_engine.engine import (
    Bus,
    Conditions,
    Encounter,
    Grid,
    Health,
    Ident,
    Position,
    Rng,
    Team,
    World,
    get,
    use,
)
from combat_engine.engine.scaling import PRESETS

#: This used to be a four-entry map with a fighter fallback, from when only
#: four classes existed -- so every warlord, paladin, ranger and warlock row
#: was rendered on a fighter, with the wrong ability modifiers and no
#: `Build`, which meant no `c.build(...)` rider could ever fire here.

#: What to stand in front of the caster. Medium, so a push has somewhere to
#: go and a burst catches a sensible number of them.
DUMMY = "m145"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("ref", help="a power id (p289) or a monster ability id (m206a1)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--scaling", choices=sorted(PRESETS), default="full")
    ap.add_argument("--targets", type=int, default=3, help="how many to stand in front of it")
    args = ap.parse_args()

    declared = get(args.ref)
    if declared is None:
        print(f"{args.ref} is not declared. Its spec:\n")
        print(_spec(args.ref) or "  (no such row)")
        return 1

    print("=== as printed " + "=" * 55)
    print(_spec(args.ref) or "  (not in game.db)")
    print()
    print("=== the header it was given " + "=" * 42)
    print(f"  {declared}")
    print(f"  target   {declared.target}")
    if declared.attack:
        print(f"  attack   {declared.attack}")
    if declared.damage:
        # The one header field the MM1-to-MM3 conversion exists for, and for
        # a while the one you could not see on the card.
        print(f"  damage   {declared.damage}")
    if declared.keywords:
        print(f"  keywords {', '.join(k.value for k in declared.keywords)}")
    if declared.requires_text:
        print(f"  requires {declared.requires_text}")
    print()

    world, caster = _board(args.ref, declared, args.seed, args.scaling, args.targets)
    cursor = len(world.bus.log)

    print("=== what it did " + "=" * 54)
    try:
        ran = use(world, caster, args.ref)
    except AttributeError as broke:
        # **A row driven outside its trigger, reported rather than raised.**
        # 365 rows read `c.trigger.<field>` with no guard, and `c.trigger` is
        # `None` unless the row was fired *by* that trigger -- so driving one
        # here died inside the content with a traceback that reads as a bug in
        # the row. It is not: the row is fine and this instrument asked it the
        # wrong question.
        #
        # Narrow on purpose. Only the `'NoneType' has no attribute` shape is
        # caught, and only when the row declares `on=`; any other
        # `AttributeError` is a real fault in the row and must keep its
        # traceback. Matching on the message is ugly and is the only thing that
        # distinguishes the two without a guard in all 365 rows -- which is the
        # option #435 argues against, and it is right: the convention is clean
        # in the most-written part of the tree, with class powers at zero.
        #
        # **A verdict and not a synthesised trigger.** #435 prefers
        # synthesising, and so would I: it would make 365 rows readable rather
        # than merely explained. That is the same provocation machinery #214
        # wants for `audit.py`, now tracked on the sweeps milestone, and doing
        # it twice is how it ends up different in two places.
        if declared.on is None or "'NoneType' object has no attribute" not in str(broke):
            raise
        field = str(broke).rsplit("attribute ", 1)[-1].strip("'\"")
        print(f"  this row needs its trigger: the body reads "
              f"`c.trigger.{field}`, and nothing fired it")
        event = declared.on.event
        print(f"  it is declared on {getattr(event, '__name__', event)} "
              f"-- {declared.on.text or 'no printed text'}")
        print("  not a fault in the row: `c.trigger` is None unless the "
              "trigger is what used the row. #435")
        return 1
    if not ran:
        from combat_engine.engine import usable

        print(f"  could not be used: {usable(world, caster, declared)[1]}")
        return 1
    print(world.bus.render(cursor))
    print()

    print("=== the board afterwards " + "=" * 45)
    for eid, ident in world.each(Ident):
        # Not everything on the board is a creature. A zone, an aura and a
        # conjuration all carry an `Ident` and no `Health`, and assuming
        # otherwise crashed on any monster that puts up an aura.
        health = world.get(eid, Health)
        hp = f"{health.hp:>4}/{health.max_hp}" if health else "       -"
        note = " <- the caster" if eid == caster else ""
        conds = world.get(eid, Conditions)
        tail = f"  [{', '.join(c.value for c in conds.active)}]" if conds and conds.active else ""
        pos = world.get(eid, Position)
        where = f" at {pos.square}" if pos else ""
        print(f"  {ident!s:<12} {hp}{where}{tail}{note}")
    return 0


def _spec(ref: str) -> str:
    db = game()
    table = "monster_power" if ref.startswith("m") and "a" in ref[1:] else (
        "monster" if ref.startswith("m") else "power"
    )
    row = db.execute(f"SELECT spec FROM {table} WHERE ref = ?", (ref,)).fetchone()
    return ("  " + row["spec"].replace("\n", "\n  ")) if row else ""


def _board(
    ref: str, declared, seed: int, scaling: str, targets: int  # noqa: ANN001
) -> tuple[World, int]:
    """A caster and a row of targets, close enough for anything to reach."""
    world = World(Grid(24, 16), Rng(seed), Bus())
    world.scaling = PRESETS[scaling]

    if ref.startswith("m"):
        owner = ref.split("a")[0]
        caster = loader.spawn(world, owner, (4, 6), team=Team.ENEMY)
        foe_team = Team.PC
    else:
        # **`declared.cls` is not always a class**, and `or "fighter"` only
        # covered the empty case -- so `chargen.CLASSES[...]` raised on 3,163
        # of the 23,009 declared rows: 2,491 items, 507 themes, 155 races and
        # 10 `wild talent`. One declared row in seven could not be driven by
        # the read-it-yourself check that `scripts/CLAUDE.md` points at over
        # trusting a verdict. #413.
        #
        # Ported from `audit.py:1177-1225`, which has fielded all four kinds
        # for a while, rather than re-derived -- and three of its distinctions
        # are the reason it works:
        #
        # * **a magic item is not a class.** Its rows belong to whoever holds
        #   it, so the character underneath is free.
        # * **a race is a `race=` on the character**, not a class, and the
        #   class beneath it takes the classless fallback.
        # * **a theme has nothing to put on the character at all**, because
        #   nothing selects one yet, so it takes the fallback too.
        #
        # The race is matched **by the shape of the ref**, not by membership
        # in `chargen.RACES`: that set is the 46 a character may be, and `r67`
        # is a race with rows written for it that nobody can play. Fielded as
        # a class it raised; fielded as a race that does not exist it is a
        # raceless character, which is the honest answer.
        carried = declared.cls == "item"
        racial = bool(re.fullmatch(r"r\d+", declared.cls or ""))
        themed = bool(re.fullmatch(r"x\d+_\d+", declared.cls or "")) \
            or declared.cls == "wild talent"
        cls = (not carried and not racial and not themed and declared.cls) or (
            "ranger" if declared.reach.kind in ("ranged", "area_burst") else "fighter"
        )
        # And the build whose gear can hold the row, the way `audit.py`
        # picks one -- a ranged ranger row fielded on the two-blade leg is
        # refused for a reason that says nothing about the row.
        caster = chargen.spawn(
            world,
            chargen.Character(
                cls, max(1, declared.level), [ref],
                build=chargen.build_for(cls, ref),
                race=declared.cls if racial else "",
            ),
            (4, 6),
        )
        foe_team = Team.ENEMY

    # Targets in a line just past the caster, so a melee power reaches the
    # first and a burst or blast catches several. Spaced by footprint and
    # not by one: a Large creature is two squares on a side, and packing
    # them a square apart stacked them on top of each other -- which made a
    # push look broken when there was simply nowhere on the board to go.
    from combat_engine.engine.types import Size

    stock = loader.load(DUMMY)
    step = SIZES.get(stock.row["size"], Size.MEDIUM).squares
    for i in range(targets):
        loader.spawn(world, DUMMY, (5 + i * step, 6 + (i % 2) * step), team=foe_team)

    # An ally too, for the powers that help one.
    if not ref.startswith("m"):
        chargen.spawn(world, chargen.Character("cleric", 1, []), (3, 6))

    _tag(world)
    Encounter(world).start()
    world.turn = caster
    return world, caster


def _tag(world: World) -> None:
    seen: dict[str, int] = {}
    for _eid, ident in world.each(Ident):
        seen[ident.ref] = seen.get(ident.ref, 0) + 1
        ident.tag = str(seen[ident.ref])


if __name__ == "__main__":
    raise SystemExit(main())
