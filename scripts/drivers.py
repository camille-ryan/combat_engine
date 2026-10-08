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


def hiding(out: Result) -> None:
    """Attacking gives you away, and the AFTER window is where you get it back.

    Two printed rules in one ordering, and the ordering is the whole subject:

    * "attacking gives you away" -- `resolve.attack` clears `HIDDEN_FROM` for
      whoever swung;
    * "it remains hidden if the attack misses" -- which has to be laid *after*
      that clear or it is wiped a moment later.

    **The clear cannot move earlier**, and that is the thing most likely to be
    re-tried: being hidden grants combat advantage, and a striker's extra
    damage asks for combat advantage **live at the moment of the hit**
    (`features/strikers.py`). #390 proposed moving it, #446 measured the cost
    -- a rogue silently lost its 2d6 and `level-5-full` went 2043 events to
    1925 -- and it was reverted.

    So this driver asserts the ordering rather than a verb, because there is no
    verb: `c.stay_hidden()` was a marker on three rows and nothing will ever
    arrive under that name. `replay` cannot cover it either -- the fixtures
    roll it incidentally at best -- which is the same argument that put
    `phasing` and `blindness` here.
    """
    from combat_engine.engine.events import AttackDeclared, Miss
    from combat_engine.engine.query import enemies, hidden_from
    from combat_engine.engine.resolve import attack
    from combat_engine.engine.types import Defense, Relation, Window

    world, caster, _ = _board()
    foe = enemies(world, caster)[0]

    def hide_from_everyone() -> set[int]:
        for who in enemies(world, caster):
            world.relations.set(Relation.HIDDEN_FROM, caster, who)
        return set(hidden_from(world, caster))

    before = hide_from_everyone()
    out.that(bool(before), f"a creature can be hidden from {len(before)} enemies")

    # **The positive control for the clear**: swinging gives it away. +30 so
    # the attack lands whatever the board rolls.
    attack(world, caster, foe, 30, Defense.AC, power="driver")
    out.that(
        not hidden_from(world, caster),
        "attacking gives you away -- the first printed rule",
        "the hidden-from list survived a swing, so nothing is clearing it",
    )

    # **And the negative control, which is the half #390 is about**: a re-hide
    # laid in the AFTER window is past the clear and sticks. A `Miss` watch is
    # not, and that is exactly the trap -- so this asserts the window the
    # docstring now sends authors to.
    hide_from_everyone()
    restored: list[int] = []

    def after(ev: AttackDeclared) -> None:
        if ev.attacker != caster:
            return
        world.relations.set(Relation.HIDDEN_FROM, caster, foe)
        restored.append(foe)

    world.bus.on(AttackDeclared, after, window=Window.AFTER)
    attack(world, caster, foe, 30, Defense.AC, power="driver")
    out.that(
        bool(restored) and foe in hidden_from(world, caster),
        "a re-hide in AttackDeclared's AFTER window survives the clear",
        "the AFTER window runs before the clear, so the documented idiom "
        "for 'remains hidden on a miss' does not work",
    )

    # The trap itself, asserted as a trap: the same re-hide from a `Miss`
    # watch is wiped. **On a fresh board**, because the AFTER listener above
    # is still subscribed and would re-hide on this attack too -- which it
    # did, and this assertion caught it. A driver that reuses a world carries
    # the previous arm's subscriptions into the next one.
    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    for who in enemies(world, caster):
        world.relations.set(Relation.HIDDEN_FROM, caster, who)
    laid = []

    def on_miss(ev: Miss) -> None:
        if ev.attacker == caster:
            world.relations.set(Relation.HIDDEN_FROM, caster, foe)
            laid.append(foe)

    world.bus.on(Miss, on_miss)
    # -30 so it misses whatever the board rolls.
    attack(world, caster, foe, -30, Defense.AC, power="driver")
    out.that(
        bool(laid),
        "the control attack really did miss, so the Miss watch ran",
        "it hit instead, and the assertion below would pass without asking",
    )
    out.that(
        foe not in hidden_from(world, caster),
        "and a re-hide from a Miss watch is still wiped -- #390's trap",
        "a Miss watch now works, so the ordering moved and the docs are stale",
    )


def configured_dummy(out: Result) -> None:
    """The crash test dummy can be handed the state a row needs to see.

    **Why this is a driver and not a count.** `audit.py`'s `KNOWN_SILENT` is
    231 hand-written excuses for rows that fire and do nothing, and a read of
    a random 20 found **19 blaming the harness** rather than the row -- the
    board could not pose the question. Classified by the state needed:

        63  grabbed       37  a condition      13  a creature type

    Those are `dummy.spawn`'s three new knobs, and `grabbed_by` alone is 27%
    of the file. Creature type was the knob asked for first and is a tenth of
    the problem, which is worth knowing before building in that order.

    **Every arm has its negative control on the same board**, because the
    failure these guard against is a knob that silently does nothing: a
    `types=` that lays an effect `kinds_of` does not read, or a `conditions=`
    hold that expires before anybody asks. A plain dummy spawned beside each
    configured one is what makes the assertion mean something.
    """
    from combat_engine.content import dummy
    from combat_engine.engine.query import holds_somebody, is_, kinds_of
    from combat_engine.engine.types import Condition

    world, caster, _ = _board()

    plain = dummy.spawn(world, level=5, square=(2, 2))
    out.that(not kinds_of(world, plain), "a plain dummy has no creature type")
    out.that(not is_(world, plain, Condition.DAZED), "and no conditions")
    out.that(not is_(world, plain, Condition.GRABBED), "and nobody is holding it")
    out.that(not holds_somebody(world, caster), "and the caster holds nobody")

    # `types=` is an effect labelled `origin:<word>`, which is what
    # `query.kinds_of` reads off a creature with no stat block.
    tagged = dummy.spawn(world, level=5, square=(2, 4), types=("undead", "humanoid"))
    out.that(
        kinds_of(world, tagged) >= {"undead", "humanoid"},
        "types= gives a dummy its creature type words",
        f"kinds_of says {sorted(kinds_of(world, tagged))}",
    )

    held = dummy.spawn(world, level=5, square=(2, 6),
                       conditions=(Condition.DAZED, Condition.PRONE))
    out.that(
        is_(world, held, Condition.DAZED) and is_(world, held, Condition.PRONE),
        "conditions= lays every condition asked for",
    )
    out.that(
        not is_(world, held, Condition.STUNNED),
        "and only those -- a condition not asked for is absent",
        "something is laying conditions nobody requested",
    )

    # The direction the excuses want: *"attacks or acts on a creature it has
    # grabbed"*, so the row's own caster must be the holder.
    caught = dummy.spawn(world, level=5, square=(2, 8), grabbed_by=caster)
    out.that(
        is_(world, caught, Condition.GRABBED),
        "grabbed_by= puts the dummy in a grab",
        "the relation was filed and `Condition.GRABBED` does not follow from it",
    )
    out.that(
        holds_somebody(world, caster),
        "and the named creature is the one holding it",
        "`requires=holds_somebody` would still refuse the row this is for",
    )


def lighting(out: Result) -> None:
    """Dim light conceals, darkness conceals totally, and a sense cancels it.

    The printed rules, in the order they have to compose:

    * dim light gives the creature standing in it **partial** concealment, -2;
    * darkness gives **total** concealment, -5;
    * low-light vision answers dim and **not** darkness, which is the
      distinction 14 rows turn on;
    * darkvision answers both;
    * a carried light brightens the square it is standing in, however dark the
      terrain under it.

    Driven rather than left to `replay`, for the reason `phasing` and
    `blindness` are: the fixtures never darken a board, so none of this is
    rolled incidentally and a regression would be invisible. And it is the
    *attack modifier* that is asserted, not `light_level` -- reading the model
    back proves the model, where the thing worth protecting is that
    `resolve.situational_attack` consults it. A light level nothing subtracted
    would be the commonest bug in this component.

    The negative controls are the two that matter and are easy to get wrong:
    a bright board must cost nothing, and low-light vision must **not** rescue
    a creature looking into the dark.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.query import enemies, light_level, squares
    from combat_engine.engine.resolve import situational_attack
    from combat_engine.engine.types import Light

    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    square = next(iter(squares(world, foe)))

    def penalty() -> int:
        return situational_attack(world, caster, foe, "drivers:lighting", {})

    base = penalty()
    out.that(light_level(world, square) is Light.BRIGHT,
             "a board nobody darkened is bright everywhere")

    world.grid.light[square] = Light.DIM
    out.that(penalty() == base - 2,
             "dim light is partial concealment, -2 to the attack",
             f"{penalty():+d} against {base - 2:+d}")

    world.grid.light[square] = Light.DARK
    out.that(penalty() == base - 5,
             "darkness is total concealment, -5",
             f"{penalty():+d} against {base - 5:+d}")

    sees = Cast(world=world, me=caster, ref="drivers:lighting")
    sees.low_light()
    out.that(penalty() == base - 5,
             "low-light vision does NOT answer darkness",
             f"{penalty():+d} against {base - 5:+d}")

    world.grid.light[square] = Light.DIM
    out.that(penalty() == base,
             "low-light vision does answer dim light",
             f"{penalty():+d} against {base:+d}")

    world.grid.light[square] = Light.DARK
    sees.darkvision()
    out.that(penalty() == base,
             "darkvision answers darkness",
             f"{penalty():+d} against {base:+d}")

    # **A printed range stops the sense answering past it**, which is what
    # several cards print -- "darkvision out to 5 squares" -- and what an
    # earlier draft of these verbs could not say at all. Asked of `sees_in`
    # directly rather than through an attack, because the board puts the only
    # foe one square away and a range test needs more room than that.
    from combat_engine.engine.query import sees_in

    world, caster, _ = _board()
    Cast(world=world, me=caster, ref="drivers:lighting").darkvision(5)
    out.that(sees_in(world, caster, Light.DARK, 5),
             "a sense with a printed range answers inside it")
    out.that(not sees_in(world, caster, Light.DARK, 6),
             "and stops answering past it")

    world, caster, _ = _board()
    Cast(world=world, me=caster, ref="drivers:lighting").darkvision()
    out.that(sees_in(world, caster, Light.DARK, 40),
             "no printed range means no limit")

    # A carried light, on a fresh board so the senses above do not mask it.
    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    square = next(iter(squares(world, foe)))
    world.grid.light[square] = Light.DARK
    out.that(light_level(world, square) is Light.DARK, "the square starts dark")
    Cast(world=world, me=foe, ref="drivers:lighting").light(2)
    out.that(light_level(world, square) is Light.BRIGHT,
             "a carried light brightens the square it stands in")


DRIVERS = {
    "phasing": (phasing, "a ghost moves through a body and cannot stop in one"),
    "lighting": (lighting, "dim conceals, dark conceals totally, a sense cancels it"),
    "blindness": (blindness, "a blinded creature cannot see, and can again after"),
    "hiding": (hiding, "attacking gives you away, and AFTER is where you get it back"),
    "dummy": (configured_dummy, "the crash test dummy takes the state a row needs"),
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
