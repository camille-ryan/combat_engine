#!/usr/bin/env python
"""Does each doctrine weight actually fire, and what does it decide?

    uv run scripts/doctrine.py                    8 fights at level 5
    uv run scripts/doctrine.py --level 1 --seeds 20
    uv run scripts/doctrine.py --threat           just the threat table

**A weight nothing consults is this component's commonest bug** -- the root
`CLAUDE.md` calls it "silently false" and lists three worked examples. Adding nine
weights to the scorer without an instrument that watches each of them fire would
be the fourth. So this plays real fights with `DoctrinePolicy` and, for every
decision it takes, records which doctrine terms were non-zero and what they
contributed.

Two numbers per term, because they answer different questions:

* **offered** -- how many scored actions the term was non-zero on. A zero here
  means the term is inert and the weight is decoration.
* **decided** -- how often it was non-zero on the action actually *chosen*, and
  the mean contribution there. A term can fire constantly and change nothing.

Not a pass/fail check. It reports what the scorer read, so a weight can be set
against evidence rather than guessed at.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fight
from combat_engine.engine import DoctrinePolicy, Ident, install, take_turn
from combat_engine.engine import threat as T
from combat_engine.engine.doctrine import DOCTRINE, doctrine_features, forget
from combat_engine.engine.query import alive, creatures


class Watched(DoctrinePolicy):
    """A `DoctrinePolicy` that records what its doctrine terms said."""

    # A plain `__init__`, not `__post_init__`: `DoctrinePolicy` is a dataclass
    # and this subclass is not decorated as one, so `__post_init__` would never
    # be called and every counter below would be missing.
    def __init__(self) -> None:
        super().__init__()
        self.offered: dict[str, int] = defaultdict(int)
        self.decided: dict[str, list[float]] = defaultdict(list)
        self.scored = 0
        self.chosen = 0

    def score(self, world, encounter, actor, action):  # noqa: ANN001, ANN201
        d = doctrine_features(world, encounter, actor, action)
        self.scored += 1
        for k, v in d.items():
            if v:
                self.offered[k] += 1
        return super().score(world, encounter, actor, action)

    def act(self, world, encounter, actor, options):  # noqa: ANN001, ANN201
        picked = super().act(world, encounter, actor, options)
        self.chosen += 1
        for k, v in self.explain(world, encounter, actor, picked).items():
            if v:
                self.decided[k].append(v)
        return picked


def threat_table(level: int, seed: int) -> None:
    world, enc = fight.build(seed, level, "full")
    enc.start()
    T.clear()
    forget()
    print(f"\nthreat at level {level}, seed {seed} "
          f"-- best case over {T.ROUNDS} rounds")
    print(f"  {'creature':<24} {'role':<11} {'raw hp':>7} {'share':>7}")
    rows = []
    for eid in creatures(world):
        if not alive(world, eid):
            continue
        ident = world.get(eid, Ident)
        rows.append((
            T.threat(world, eid),
            (ident.ref if ident else "?"),
            (ident.role if ident else "") or "-",
            T.raw(world, eid),
        ))
    for share, ref, role, raw in sorted(rows, reverse=True):
        print(f"  {ref:<24} {role:<11} {raw:>7.1f} {share:>7.1%}")
    if T.unarmed.__doc__:
        bare = [r for _, r, _, raw in rows if raw == 0.0]
        if bare:
            print(f"  zero: {', '.join(bare)}"
                  f"  -- no rows to attack with, or none evaluable")


def rounds_table(level: int, seed: int) -> None:
    """What each condition is worth, in rounds, against every monster on a board.

    **The acceptance test for the rounds model**, and the reason it is here rather
    than in a one-off probe: these are Camille's own figures and they should be
    re-checkable after any change to `engine/threat.py`.

        kill                                3 rounds
        EoNT immobilise, cannot then reach   1
        save-ends immobilise, same           1.8   (a save is 55%, so 1/0.55)
        immobilise a creature in contact     well under 1
        immobilise one with a ranged backup  the melee/ranged differential, often 0
        stun                                 1     (cannot act at all)
        weakened                             0.5   (its damage is halved)
        prone                                ~0.1  (-2 to attack, hit-chance weighted)

    Each monster is measured twice, standing next to a character and four squares
    off, because the whole point of the model is that the same condition is worth
    different amounts in those two places.
    """
    from combat_engine.engine.components import Position, Powers
    from combat_engine.engine.dsl import get
    from combat_engine.engine.movement import place
    from combat_engine.engine.types import Condition

    world, enc = fight.build(seed, level, "full")
    enc.start()
    pcs = [e for e in creatures(world)
           if (world.get(e, Ident).ref if world.get(e, Ident) else "").startswith("c:")]
    mons = [f for f in creatures(world)
            if (world.get(f, Ident).ref if world.get(f, Ident) else "").startswith("m")]
    if not pcs or not mons:
        print("  no board to measure")
        return
    sq = world.get(pcs[0], Position).square
    print(f"\nrounds of damage denied, level {level}, seed {seed}")
    print(f"  {'monster':<22} {'where':<9} {'pot':>5} {'immob':>6} {'save':>6} "
          f"{'stun':>5} {'weak':>5} {'prone':>6}  attacks with")
    for mon in mons:
        known = world.get(mon, Powers)
        kinds = sorted({p.reach.kind for r in (known.known if known else ())
                        if (p := get(r)) is not None and p.attack is not None
                        and p.reach is not None})
        ident = world.get(mon, Ident)
        name = f"{ident.ref if ident else '?'} ({(ident.role if ident else '') or '-'})"
        for gap, where in ((1, "adjacent"), (4, "4 away")):
            place(world, mon, (sq[0] + gap, sq[1]))
            T.clear()
            forget()

            def denied(when: T.When, cond: Condition, m: int = mon) -> float:
                return T.denial(world, m, [T.Laid(when=when, conditions=(cond,))])

            print(f"  {name:<22} {where:<9} {T.potential(world, mon):>5.1f} "
                  f"{denied(T.When.EONT, Condition.IMMOBILIZED):>6.2f} "
                  f"{denied(T.When.SAVE_ENDS, Condition.IMMOBILIZED):>6.2f} "
                  f"{denied(T.When.EONT, Condition.STUNNED):>5.2f} "
                  f"{denied(T.When.EONT, Condition.WEAKENED):>5.2f} "
                  f"{denied(T.When.EOTNT, Condition.PRONE):>6.2f}  "
                  f"{'+'.join(kinds)}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--level", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=30)
    ap.add_argument("--threat", action="store_true",
                    help="print the threat table and stop")
    ap.add_argument("--rounds-table", action="store_true",
                    help="what each condition is worth in rounds, and stop")
    args = ap.parse_args()

    if args.rounds_table:
        rounds_table(args.level, 1)
        return 0
    if args.threat:
        threat_table(args.level, 1)
        return 0

    threat_table(args.level, 1)
    rounds_table(args.level, 1)

    policy = Watched()
    fought = 0
    for seed in range(1, args.seeds + 1):
        world, encounter = fight.build(seed, args.level, "full")
        T.clear()
        forget()
        install(world, encounter, {}, default=policy)
        encounter.start()
        while not encounter.finished and world.round <= args.rounds:
            actor = world.turn
            if actor is None:
                break
            take_turn(world, encounter, actor, policy)
            encounter.advance()
        fought += 1

    print(f"\n{fought} fights at level {args.level}, "
          f"{policy.scored} actions scored, {policy.chosen} chosen\n")
    print(f"{'term':<18} {'weight':>7} {'offered':>8} {'decided':>8} "
          f"{'mean':>8} {'total':>9}")
    for term, weight in sorted(DOCTRINE.items(),
                               key=lambda kv: -abs(kv[1])):
        took = policy.decided.get(term, [])
        mean = statistics.fmean(took) if took else 0.0
        flag = "" if policy.offered.get(term) else "   <-- never fired"
        print(f"{term:<18} {weight:>7.1f} {policy.offered.get(term, 0):>8} "
              f"{len(took):>8} {mean:>8.2f} {sum(took):>9.1f}{flag}")
    dead = [t for t in DOCTRINE if not policy.offered.get(t)]
    if dead:
        print(f"\n{len(dead)} of {len(DOCTRINE)} terms never fired: "
              f"{', '.join(dead)}")
        print("A weight nothing consults is the bug this instrument exists for.")
    else:
        print(f"\nAll {len(DOCTRINE)} terms fired at least once.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
