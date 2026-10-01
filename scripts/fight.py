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

from combat_engine import story
from combat_engine.engine import (
    DoctrinePolicy,
    Encounter,
    Ident,
    World,
    install,
    take_turn,
)
from combat_engine.engine.monster_math import PRESETS as MATHS
from combat_engine.engine.query import alive, creatures
from combat_engine.engine.scaling import PRESETS
from combat_engine.engine.turns import extended_rest, short_rest

#: Which four classes take the field. What each of them *knows* is worked
#: out from the registry rather than listed, because a hand-written list goes
#: stale the moment a row lands -- and it did. For a long while this party
#: carried no class features at all: no mark, no channel, no extra damage.
#: The rogue was swinging a dagger for 1d4 with none of its extra damage,
#: which is not a rogue, and the fight it produced said more about the
#: roster than about the engine.
#: Re-exported from `story`, which owns it now -- `winrate.py` reads
#: `fight.PARTY` and there is one definition again.
PARTY = story.PARTY

def build(
    seed: int, level: int, scaling: str, math: str = "printed",
    feats: dict[str, list[str]] | None = None,
) -> tuple[World, Encounter]:
    """One fight, built from a seed.

    `feats` pins what each class has taken, by class name. It exists for
    `replay.py`: a character's feats are otherwise dealt from the pool
    of *declared* ones, so every content wave changed the party and
    every fixture diverged -- which meant re-recording after each batch,
    and a real regression could have ridden in under a feat-draw change
    without anybody seeing it. Pinning them makes the fixture a test of
    the engine again rather than of the corpus's size.
    """

    fielded = story.field_encounter(
        seed, level, scaling=scaling, math=math, feats=feats
    )
    world = fielded.world
    if not fielded.enemies:
        raise SystemExit(
            "no monster anywhere has all of its abilities written.\n"
            "Run: uv run scripts/coverage.py --monsters --max-level 3"
        )
    if fielded.found_at != level:
        print(
            f"# no monster at level {level} is fully written yet, so this "
            f"fight uses level {fielded.found_at} ones\n"
        )
    return world, Encounter(world)










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
    ap.add_argument(
        "--surprise",
        choices=("none", "party", "monsters"),
        default="none",
        help="who did not see it coming. A surprised creature grants combat "
        "advantage and can do nothing on the first round, which is the only "
        "way a rogue ever opens a fight with a sneak attack",
    )
    ap.add_argument(
        "--rest",
        choices=("none", "short", "extended"),
        help="take a rest before the fight, which is the only way a daily "
        "power differs from an encounter one: a World never outlived a "
        "single fight, so nothing ever had to tell them apart",
    )
    args = ap.parse_args()

    world, encounter = build(args.seed, args.level, args.scaling, args.monster_math)
    policy = DoctrinePolicy()
    install(world, encounter, {}, default=policy)

    caught: list[int] = []
    if args.surprise != "none":
        from combat_engine.engine.query import combatants, team
        from combat_engine.engine.types import Team

        losing = Team.PC if args.surprise == "party" else Team.ENEMY
        caught = [c for c in combatants(world) if team(world, c) is losing]
    if args.rest == "short":
        short_rest(world)
    elif args.rest == "extended":
        extended_rest(world)
    encounter.start(caught)
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
