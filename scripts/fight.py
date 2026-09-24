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
from combat_engine.engine.types import ActionType, Usage

#: Which four classes take the field. What each of them *knows* is worked
#: out from the registry rather than listed, because a hand-written list goes
#: stale the moment a row lands -- and it did. For a long while this party
#: carried no class features at all: no mark, no channel, no extra damage.
#: The rogue was swinging a dagger for 1d4 with none of its extra damage,
#: which is not a rogue, and the fight it produced said more about the
#: roster than about the engine.
PARTY = ["fighter", "cleric", "rogue", "wizard"]

#: A level 1 character: every class feature, two at-wills, one encounter
#: power and one daily. Straight out of the book.
SLOTS = {Usage.AT_WILL: 2, Usage.ENCOUNTER: 1, Usage.DAILY: 1}


def loadout(cls: str, level: int) -> list[str]:
    """A legal set of powers for one class at one level, from what exists.

    Deterministic -- sorted, then the first of each kind -- so the same fight
    is the same fight, and self-updating, so it can never again be a list of
    ids that used to be right.
    """
    import combat_engine.content  # noqa: F401  (registers the rows)
    from combat_engine.engine.dsl import REGISTRY

    mine = [p for p in REGISTRY.values() if p.cls == cls]
    # Level 0 is the class itself: features, marks, channels. All of it.
    out = sorted(p.ref for p in mine if p.level == 0)
    # A leader's heal is a class feature that happens to be printed at level
    # 1, and it does not spend an encounter slot. Taken out of the slots, the
    # cleric was choosing between healing the party and attacking anything,
    # which is not a choice the book asks it to make.
    free = sorted(p.ref for p in mine if _is_class_heal(p))
    out.extend(free)
    for usage, count in SLOTS.items():
        pool = [
            p.ref
            for p in sorted(mine, key=lambda p: p.ref)
            if p.level == level and p.usage is usage and p.ref not in out
        ]
        out.extend(pool[:count])
    return out


def _is_class_heal(p) -> bool:  # noqa: ANN001
    """The leader's signature heal: a minor action, healing, twice a fight."""
    from combat_engine.engine.types import Keyword

    return (
        p.level <= 1
        and Keyword.HEALING in p.keywords
        and p.action is ActionType.MINOR
        and p.uses > 1
    )


def build(
    seed: int, level: int, scaling: str, math: str = "printed"
) -> tuple[World, Encounter]:
    world = World(Grid(16, 12), Rng(seed), Bus())
    world.scaling = PRESETS[scaling]
    world.monster_math = MATHS[math]

    for i, cls in enumerate(PARTY):
        who = chargen.Character(cls, level, loadout(cls, level))
        chargen.spawn(world, who, (2, 3 + i * 2))

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

    Sorted by role rather than by id, and taken one role at a time, so the
    four that turn up are a mixed band. Taking the first four by id gave an
    all-brute line-up with half again the party's hit points and more damage
    per swing, and a demo fight that says more about alphabetical order than
    about the engine.
    """
    for candidate in range(min(level, 13), 0, -1):
        pool = loader.pick(candidate)
        if pool:
            return _one_of_each(pool), candidate
    return [], level


#: The order roles are drawn in. A soldier and a brute in front, something
#: shooting from the back, a skirmisher moving. What a published encounter
#: looks like.
ROLE_ORDER = ["soldier", "brute", "artillery", "skirmisher", "controller", "lurker"]


def _one_of_each(pool: list[str]) -> list[str]:
    """Reorder a pool so consecutive picks come from different roles."""
    from combat_engine.etl.build import game

    db = game()
    by_role: dict[str, list[str]] = {}
    for ref in pool:
        row = db.execute("SELECT role FROM monster WHERE ref = ?", (ref,)).fetchone()
        by_role.setdefault((row["role"] if row else "") or "", []).append(ref)
    out: list[str] = []
    while any(by_role.values()):
        for role in [*ROLE_ORDER, *sorted(set(by_role) - set(ROLE_ORDER))]:
            if by_role.get(role):
                out.append(by_role[role].pop(0))
    return out


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
