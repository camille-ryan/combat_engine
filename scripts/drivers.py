#!/usr/bin/env python
"""The printed rule for one mechanic, asserted on a board built for it.

    uv run scripts/drivers.py            every driver
    uv run scripts/drivers.py --list     what each one watches
    uv run scripts/drivers.py phasing    just these

**Why this exists rather than an eighth `replay` fixture.** `replay` is seven
recorded fights and it covers what those seven drawn parties happen to do.
Measured for #422: **0 phasing events across all seven, and 6 blindness
events** of 10,665 -- three apply/end pairs with no sight question asked in
between. So two engine mechanics had no automated cover at all, and the suite
reported clean:

* `toward=` (#381) ranked move destinations by distance, which made an occupied
  square the *preferred* destination for a phasing creature -- so a row that
  leaps at a victim reliably landed on top of it, across 79 `c.phasing` rows.
  `replay` passed 7 of 7 before, during and after.
* `Rules.blind` (#406) was set for `Condition.BLINDED` and **read by nothing**,
  so every sight question in the tree answered as though nobody were blind.
  Fixed with `replay` unmoved.

Two for two is a pattern. The obvious answer -- record an eighth fixture -- costs
a 1,000-to-2,500-event baseline that every future diff has to be read against,
and Camille's call was that eight fixtures are not better than seven if the
eighth is noise. What actually caught both bugs was a hand-driven probe with a
positive and a negative control, so that is what this is.

**Every driver carries both controls.** A driver that only asserts the fixed
behaviour cannot tell "the rule works" from "the question was never asked" --
which is exactly how both bugs survived. So each one also builds the state where
the rule must *not* apply and asserts that too. Breaking the rule has to turn a
driver red, and both were checked by breaking what they watch:

* letting `_can_stop` waive occupancy for a ghost -- the #392 state -- fails
  *"never waives it for stopping"*;
* returning False from `query.blinded` -- the #406 state -- fails *"a blinded
  creature cannot [see]"*.

Each reproduces its original bug's signature, which is the only evidence that a
driver would have caught it.

These are not `replay`'s job and do not replace it: `replay` catches a change
nobody intended anywhere in a whole fight, and these catch a rule nobody
exercised. Seconds to run, so `check.py` runs them every time.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


class Result:
    """What one driver saw. Pass/fail with the numbers attached."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.failed: list[str] = []
        self.passed = 0

    def that(self, ok: bool, what: str, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"    ok    {what}")
        else:
            self.failed.append(what)
            print(f"    FAIL  {what}" + (f"\n            {detail}" if detail else ""))


def _board(ref: str = "m145a0", seed: int = 1):  # noqa: ANN202
    """A legal world, borrowed from the auditor rather than built again."""
    from audit import board

    return board(ref, seed)


def phasing(out: Result) -> None:
    """A phasing creature moves *through* a body and may not stop in one.

    The printed rule is two halves and only the first had cover: "can move
    through occupied squares" is what `_clear` waives, and "must end its move
    in an unoccupied space" is what `_can_stop` enforces. #392 is the second
    half going missing for 79 rows.

    **The negative control is the point.** Asserting only that the occupied
    square is absent would pass on a board where it was never reachable, which
    is how this hid: the destination list went to `World.decide` unranked and
    the occupied square was rarely first, so nothing noticed it was there.
    """
    from combat_engine.engine.components import Movement, Position
    from combat_engine.engine.grid import footprint
    from combat_engine.engine.movement import _can_stop, _clear, reachable
    from combat_engine.engine.query import enemies, speed

    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    here = world.get(caster, Position)
    there = world.get(foe, Position)

    # Stand them a short walk apart, so the occupied square is reachable and
    # is also the nearest one to the target -- which is what `toward=` prefers.
    here.square = (there.square[0] + 3, there.square[1])

    walker = world.get(caster, Movement) or world.add(caster, Movement())
    budget = speed(world, caster, {})
    before = set(reachable(world, caster, budget))
    out.that(
        there.square not in before,
        "an ordinary creature cannot stop in an occupied square",
        f"{there.square} was offered among {len(before)} destinations",
    )

    # `modes` is {name: speed}; `phasing` at the creature's own speed.
    walker.modes = {**walker.modes, "phasing": budget}
    after = set(reachable(world, caster, budget, mode="phasing"))
    out.that(
        bool(after),
        f"a phasing creature still has somewhere to go ({len(after)} squares)",
    )
    out.that(
        there.square not in after,
        "and still cannot stop on top of its victim",
        f"{there.square} is offered -- this is #392, across 79 c.phasing rows",
    )
    # **The two halves, asked of the two predicates that answer them**, because
    # comparing destination *sets* turned out to be vacuous: on an open board
    # going around a body costs the same as going through it, so the sets are
    # identical with and without the mode and the comparison proves nothing.
    # The driver's own control caught that, which is why it is written down
    # rather than quietly dropped.
    taken = footprint(there.square, world.get(foe, Position).size)
    out.that(
        _clear(world, caster, taken),
        "phasing waives occupancy on the way past -- the first printed half",
        "a ghost cannot cross a body at all, so the mode does nothing",
    )
    out.that(
        not _can_stop(world, caster, taken),
        "and never waives it for stopping -- the second half, which is #392",
        "`_can_stop` allows it, so a leap lands on top of the victim",
    )


def blindness(out: Result) -> None:
    """A blinded creature cannot see, and `Rules.blind` is what says so.

    #406: the flag was declared, set for `Condition.BLINDED`, and read by
    nothing -- so every sight question answered as though nobody were blind.
    The two readers that *did* exist (combat advantage, the -2) made it look
    covered.

    **Both controls, and the negative one is what #406 needed.** A driver that
    only asserted "a blinded creature cannot see" would have passed the moment
    somebody wired one reader; this asserts that an unblinded creature *can*,
    on the same board, so the question is demonstrably being asked.
    """
    from combat_engine.engine.durations import When
    from combat_engine.engine.query import blinded, enemies
    from combat_engine.engine.types import Condition

    world, caster, _ = _board()
    foe = enemies(world, caster)[0]

    out.that(not blinded(world, caster), "a creature with no conditions can see")

    world.effects.apply(
        source=foe, owner=caster, when=When.SAVE_ENDS,
        conditions=(Condition.BLINDED,), label="driver blindness",
    )
    out.that(blinded(world, caster), "a blinded creature cannot -- this is #406")

    # And it comes back, because a rule that cannot be turned off is a rule
    # nobody can write a save against.
    for eff in list(world.effects.of(caster)):
        if eff.label == "driver blindness":
            world.effects.end(eff, "driver")
    out.that(not blinded(world, caster), "and can see again once it ends")


DRIVERS = {
    "phasing": (phasing, "a ghost moves through a body and cannot stop in one"),
    "blindness": (blindness, "a blinded creature cannot see, and can again after"),
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("only", nargs="*", help="just these drivers")
    ap.add_argument("--list", action="store_true", help="what each one watches")
    ap.add_argument("--quiet", action="store_true", help="only the summary")
    args = ap.parse_args()

    if args.list:
        for name, (_fn, what) in DRIVERS.items():
            print(f"  {name:12} {what}")
        return 0

    wanted = args.only or list(DRIVERS)
    unknown = [n for n in wanted if n not in DRIVERS]
    if unknown:
        print(f"no such driver: {', '.join(unknown)}", file=sys.stderr)
        return 2

    results = []
    for name in wanted:
        fn, what = DRIVERS[name]
        if not args.quiet:
            print(f"  {name} -- {what}")
        out = Result(name)
        fn(out)
        results.append(out)

    bad = [r for r in results if r.failed]
    total = sum(r.passed for r in results)
    print(f"\n{total} printed rules hold, {sum(len(r.failed) for r in bad)} do not"
          + (f" ({', '.join(r.name for r in bad)})" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
