"""What a character's rows would deal, in closed form, against the baseline.

`engine/expect.py` does the arithmetic; this is the instrument that asks it a
question a human wants answered -- which weapon, which feat, which row -- and
prints the answer ranked.

The target is the baseline opponent `docs/AI_DOCTRINE.md` names, which is the
line the monster corpus actually sits on:

    AC   14 + level        lowest non-AC defence  11 + level
    hp   24 + 8 x level

    uv run scripts/expect.py --class fighter --level 10
    uv run scripts/expect.py --class fighter --level 1 \\
        --weapons w:greataxe,w:fullblade --feats f1032
    uv run scripts/expect.py --class rogue --level 5 --rows 12

Nothing here is a pass/fail check. It reports a number so a weight can be set
against it rather than guessed at.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import combat_engine.content  # noqa: F401
from combat_engine import chargen
from combat_engine.content import dummy
from combat_engine.engine import Bus, Encounter, Grid, Rng, World
from combat_engine.engine.components import (
    Gear,
    Powers,
)
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.expect import expected
from combat_engine.engine.movement import place
from combat_engine.engine.types import Keyword, Team

#: An eight-round fight, which is the round count the project targets: one
#: daily, a couple of encounter rows, at-wills for the rest.
ROUND = {"at-will": 5 / 8, "encounter": 2 / 8, "daily": 1 / 8}


def target(world: World, level: int) -> int:
    """The baseline opponent: `content.dummy`, which is built for this.

    **This used to spawn a real creature and overwrite it**, and the reason is
    worth keeping: that creature's immediate interrupt made an attacker reroll on
    being hit, which turned a third of landed hits back into misses and had the
    closed form looking wrong by a third when it was the board that was wrong.

    `content.dummy` is that workaround made into a thing, so the next instrument
    does not have to know to do it. #243.

    **It also fixes a number this function had wrong.** Flattening the three
    non-AC defences to `level + 11` understated Fortitude and Reflex by a point
    each -- measured across 1,997 standard monsters they sit at `level + 12`, and
    only Will is at `level + 11`. So every row targeting Fort or Ref was being
    priced against a target a point softer than the corpus.
    """
    return dummy.spawn(world, level, (5, 6), team=Team.ENEMY)


def board(cls: str, level: int, weapon: str, feats: list[str],
          race: str | None) -> tuple[World, int, int]:
    """One character against one baseline target, ready to be measured."""
    world = World(Grid(16, 12), Rng(0), Bus())
    who = chargen.Character(cls, level, [], feats=list(feats))
    if race:
        who = replace(who, race=race)
    me = chargen.spawn(world, who, (4, 6))
    foe = target(world, level)
    if weapon:
        gear = world.need(me, Gear)
        arm = replace(chargen.PRINTED[weapon],
                      enhancement=gear.main.enhancement if gear.main else 0)
        gear.weapons.clear()
        gear.weapons.append(arm)
        gear.stowed.clear()
        gear.wield(arm)
    # An encounter has to be running or nothing a feat arms is armed, and a
    # feat granting +1 to hit measured as worth exactly zero.
    Encounter(world).start()
    place(world, me, (4, 6))
    place(world, foe, (5, 6))
    return world, me, foe


def attacking(world: World, me: int) -> tuple[list[str], dict[str, int]]:
    """The character's rows that roll an attack, and a tally of what was left.

    The tally is reported rather than dropped. A level-10 character is dealt
    one attacking row or none at all (#244), and printing a short table without
    saying so reads as "these are its options" when it means "this is all there
    was".
    """
    known = world.need(me, Powers).known
    out: list[str] = []
    left = {"known": len(known), "no attack line": 0, "marked todo": 0}
    for ref in known:
        row = REGISTRY.get(ref)
        if row is None or row.attack is None:
            left["no attack line"] += 1
        elif row.todo:
            left["marked todo"] += 1
        else:
            out.append(ref)
    return out, left


def measure(world: World, me: int, foe: int, refs: list[str]) -> list[dict]:
    got = []
    for ref in refs:
        row = REGISTRY[ref]
        try:
            full = float(expected(world, me, ref, foe))
            bare = float(expected(world, me, ref, foe, crits=False))
        except Exception as exc:
            got.append({"ref": ref, "why": f"{type(exc).__name__}", "dmg": None})
            continue
        got.append({
            "ref": ref, "dmg": full, "crit": full - bare,
            "usage": row.usage.value, "level": row.level,
            "weapon": Keyword.WEAPON in row.keywords,
        })
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--class", dest="cls", default="fighter")
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--race", default="", help="pin the race; omit to let the dealer choose")
    ap.add_argument("--weapons", default="", help="comma-separated refs, one column each")
    ap.add_argument("--feats", default="", help="comma-separated refs, given to the character")
    ap.add_argument("--rows", type=int, default=20, help="how many rows to print")
    ap.add_argument("--scored", action="store_true",
                    help="let the scorer choose gear instead of taking the chassis")
    args = ap.parse_args()

    # **Off by default.** The option scorer is what this instrument exists to
    # give numbers to, and it currently puts a 1d4 whip in a level-10 fighter's
    # hand (#234). Measuring a weapon while the scorer picks the weapon would
    # be measuring the bug.
    chargen.SCORED_CHOICES = args.scored

    feats = [f for f in args.feats.split(",") if f]
    weapons = [w for w in args.weapons.split(",") if w]
    hp = 24 + 8 * args.level
    started = time.perf_counter()

    print(f"{args.cls} level {args.level}"
          + (f", feats {' '.join(feats)}" if feats else "")
          + f"   target AC {args.level + 14}, NADs {args.level + 11}, hp {hp}")

    if not weapons:
        world, me, foe = board(args.cls, args.level, "", feats, args.race or None)
        arm = world.need(me, Gear).main
        print(f"weapon in hand: {arm.ref if arm else '(none)'}"
              + (f"  {arm.damage} prof {arm.proficiency} +{arm.enhancement}" if arm else ""))
        refs, left = attacking(world, me)
        measured = measure(world, me, foe, refs)
        got = [g for g in measured if g["dmg"] is not None]
        got.sort(key=lambda g: -g["dmg"])
        print(f"{left['known']} rows known, {len(refs)} roll an attack, "
              f"{len(got)} scored"
              + (f", {sum(1 for g in measured if g['dmg'] is None)} refused"
                 if len(got) < len(refs) else ""))
        print(f"\n{'row':<10} {'usage':<10} {'lvl':>3} {'expected':>9} "
              f"{'of hp':>7} {'crits':>7}")
        for g in got[:args.rows]:
            crit = g["crit"] / g["dmg"] if g["dmg"] else 0.0
            print(f"{g['ref']:<10} {g['usage']:<10} {g['level']:>3} "
                  f"{g['dmg']:>9.2f} {g['dmg'] / hp:>6.1%} {crit:>6.1%}")
        for g in measured:
            if g["dmg"] is None:
                print(f"{g['ref']:<10} refused: {g['why']}")
        best = {}
        for g in got:
            best.setdefault(g["usage"], g["dmg"])
        blend = sum(best.get(u, 0.0) * share for u, share in ROUND.items())
        print(f"\n  best of each usage, blended over an eight-round fight: "
              f"{blend:.2f} per round ({blend / hp:.1%} of the target)")
    else:
        # A column per weapon, rows in common so the comparison is like for like.
        cols, refs = {}, None
        for weapon in weapons:
            world, me, foe = board(args.cls, args.level, weapon, feats, args.race or None)
            mine, left = attacking(world, me)
            refs = mine if refs is None else [r for r in refs if r in mine]
            cols[weapon] = {g["ref"]: g for g in measure(world, me, foe, mine)}
        print(f"{left['known']} rows known, {len(refs or [])} scored in every column")
        refs = [r for r in (refs or [])
                if all(cols[w].get(r, {}).get("dmg") is not None for w in weapons)]
        refs.sort(key=lambda r: -cols[weapons[0]][r]["dmg"])
        wide = max(len(w) for w in weapons) + 1
        print(f"\n{'row':<10} {'usage':<10} "
              + " ".join(f"{w.removeprefix('w:'):>{wide}}" for w in weapons))
        for ref in refs[:args.rows]:
            print(f"{ref:<10} {cols[weapons[0]][ref]['usage']:<10} "
                  + " ".join(f"{cols[w][ref]['dmg']:>{wide}.2f}" for w in weapons))
        def blended(w: str) -> float:
            """The best row of each usage, weighted by how often it is used."""
            return sum(
                max((cols[w][r]["dmg"] for r in refs
                     if cols[w][r]["usage"] == usage), default=0.0) * share
                for usage, share in ROUND.items()
            )

        print(f"\n{'blended per round':<21} "
              + " ".join(f"{blended(w):>{wide}.2f}" for w in weapons))
        first = weapons[0]
        base = blended(first)
        if base:
            print(f"\n  against {first.removeprefix('w:')}:")
            for w in weapons[1:]:
                got = blended(w)
                print(f"    {w.removeprefix('w:'):<14} {got - base:>+6.2f} per round "
                      f"({got / base - 1:>+6.1%})")

    print(f"\n  ({time.perf_counter() - started:.2f}s, closed form -- no sampling)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
