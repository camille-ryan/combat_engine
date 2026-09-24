#!/usr/bin/env python
"""Play a whole fight and print the log.

    uv run scripts/fight.py
    uv run scripts/fight.py --seed 12 --scaling bounded
    uv run scripts/fight.py --level 3 --quiet

The thing to read. Combat contains no randomness beyond one seeded generator,
so the same seed gives the same log every time and a difference between two
runs is always a code change.

`--scaling bounded` turns off 4e's level treadmill everywhere at once -- see
`engine/scaling.py` -- which is worth watching at higher levels, where the
numbers should stay where they were at level 1 while the hit points do not.
"""

from __future__ import annotations

import argparse

from combat_engine.content import chargen, loader
from combat_engine.engine import (
    Bus,
    Encounter,
    Grid,
    Ident,
    LinearPolicy,
    Rng,
    Team,
    World,
    install,
    take_turn,
)
from combat_engine.engine.monster_math import PRESETS as MATHS
from combat_engine.engine.query import alive, creatures
from combat_engine.engine.scaling import PRESETS

PARTY = [
    ("fighter", ["p997", "p992", "p1000", "p289", "p1429"]),
    ("cleric", ["p841", "p889", "p1455", "p891", "p913"]),
    ("rogue", ["p704", "p970", "p1382", "p163"]),
    ("wizard", ["p1167", "p1166", "p463", "p159", "p185"]),
]


def build(
    seed: int, level: int, scaling: str, math: str = "printed"
) -> tuple[World, Encounter]:
    world = World(Grid(16, 12), Rng(seed), Bus())
    world.scaling = PRESETS[scaling]
    world.monster_math = MATHS[math]

    for i, (cls, powers) in enumerate(PARTY):
        chargen.spawn(world, chargen.Character(cls, level, powers), (2, 3 + i * 2))

    pool, found_at = _opposition(level)
    if not pool:
        raise SystemExit(
            "no monster anywhere has all of its abilities written.\n"
            "Run: uv run scripts/coverage.py --monsters --max-level 3"
        )
    if found_at != level:
        print(
            f"# no monster at level {level} is fully written yet, so this "
            f"fight uses level {found_at} ones\n"
        )
    for i in range(4):
        loader.spawn(world, pool[i % len(pool)], (12, 3 + i * 2), team=Team.ENEMY)

    _tag(world)
    return world, Encounter(world)


def _opposition(level: int) -> tuple[list[str], int]:
    """Monsters to field. Falls back down the levels while content is thin.

    A fight against nothing is not a useful thing to print, so rather than
    refuse, this drops to whatever level has been written and says which.
    """
    for candidate in range(min(level, 13), 0, -1):
        pool = loader.pick(candidate)
        if pool:
            return pool, candidate
    return [], level


def _tag(world: World) -> None:
    """Number the repeats, so two of the same monster are tellable apart."""
    seen: dict[str, int] = {}
    for _eid, ident in world.each(Ident):
        seen[ident.ref] = seen.get(ident.ref, 0) + 1
        if seen[ident.ref] > 1 or ident.ref.startswith("m"):
            ident.tag = str(seen[ident.ref])


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--scaling", choices=sorted(PRESETS), default="full")
    ap.add_argument(
        "--monster-math",
        choices=sorted(MATHS),
        default="printed",
        help="rescale Monster Manual 1 and 2 damage to the MM3 curve",
    )
    ap.add_argument("--quiet", action="store_true", help="the summary only")
    ap.add_argument("--rounds", type=int, default=30, help="give up after this many")
    args = ap.parse_args()

    world, encounter = build(args.seed, args.level, args.scaling, args.monster_math)
    policy = LinearPolicy()
    install(world, encounter, {}, default=policy)

    encounter.start()
    while not encounter.finished and world.round <= args.rounds:
        actor = world.turn
        if actor is None:
            break
        take_turn(world, encounter, actor, policy)
        encounter.advance()

    if not args.quiet:
        print(world.bus.render())
        print()

    print(
        f"seed {args.seed}   level {args.level}   "
        f"scaling {world.scaling.describe()}   "
        f"monsters {world.monster_math.describe()}"
    )
    print(f"rounds {world.round}   events {len(world.bus.log)}   winner {encounter.winner}")
    print()
    from combat_engine.engine import Health

    for eid in creatures(world):
        ident = world.get(eid, Ident)
        health = world.get(eid, Health)
        state = "dead" if not alive(world, eid) else f"{health.hp}/{health.max_hp}"
        print(f"  {ident!s:<10} {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
