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
        self.skipped: list[str] = []
        self.passed = 0

    def that(self, ok: bool, what: str, detail: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"    ok    {what}")
        else:
            self.failed.append(what)
            print(f"    FAIL  {what}" + (f"\n            {detail}" if detail else ""))

    def skip(self, why: str) -> None:
        """A question this board cannot pose. **Not a pass.**

        `scripts/CLAUDE.md`: an instrument must not skip itself quietly,
        and the total has to reconcile -- `browser.py` had eight sites
        writing `that(True, "... (skipped)")`, which increments `passed`
        while the parenthetical admits it, and the only thing that found
        them was the arithmetic not adding up.

        So this is counted apart and printed in the summary. The first
        caller is `at_most_one_applies`: `p992`'s chain has three branches
        and only one can fire on the audit board, so "at most one pays" is
        true there and proves nothing -- planting the regression left it
        green.
        """
        self.skipped.append(why)
        print(f"    skip  {why}")


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



############################################################

def suspension(out: Result) -> None:
    """A trait switched off by a hit and back on at the stated time.

    The printed clause is the same on five different traits -- "when it takes
    fire or radiant damage it **loses this trait until the start of its next
    turn**" -- and it is said about insubstantial, regeneration, a
    vulnerability, an invisibility and a terrain-ignoring stance. So what is
    asserted here is the one mechanism under all of them.

    **The three negative controls are the whole point**, because every one of
    them is a bug a positive-only driver would pass over:

    * the effect must still be *standing* while it is off. `end` would read
      correctly from outside -- the trait is gone -- and spend an
      encounter-long duration on one hit, so the creature never gets it back
      and no saving throw is ever owed.
    * a watcher-shaped trait must go quiet. Suspension lifts installed state,
      and `c.regeneration` installs none: its whole effect is a handler. It
      healed right through the first draft of this.
    * expiring a suspended effect must not lift twice. `c.vulnerable` adds a
      number to a dict, and subtracting it on both the suspend and the expiry
      leaves the creature *resistant* to the type it was vulnerable to --
      which is the printed rule inverted, and silently.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defences, Health, Movement
    from combat_engine.engine.durations import When
    from combat_engine.engine.events import DamageApplied, TurnStart
    from combat_engine.engine.query import takes_half
    from combat_engine.engine.types import DamageType

    # -- installed state: a condition ---------------------------------------
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:suspension")

    out.that(not takes_half(world, caster), "nobody starts insubstantial")
    thin = c.insubstantial(on=caster, until=When.ENCOUNTER)
    # Narrowed because the verb is `Effect | None` and everything below
    # reads fields off it. Pre-existing, and surfaced only when this file
    # entered `types.py`'s changed set -- the same way writing a clause
    # makes a silent row visible.
    assert thin is not None, "insubstantial laid nothing"
    out.that(takes_half(world, caster), "and the trait goes on")

    world.effects.suspend(thin)
    out.that(not takes_half(world, caster), "suspending takes the trait off")
    out.that(not thin.ended and thin.id in world.effects.live,
             "and the effect is STILL STANDING -- it was not ended")
    out.that(thin.when is When.ENCOUNTER,
             "so the encounter-long duration was not spent by one hit")

    world.effects.resume(thin)
    out.that(takes_half(world, caster), "resuming puts the trait back")

    # Suspending what is already suspended must not double-lift: the
    # refcount in `Conditions` is shared with every other effect imposing
    # the same condition.
    world.effects.suspend(thin)
    out.that(not world.effects.suspend(thin), "a second suspend does nothing")
    world.effects.resume(thin)
    out.that(not world.effects.resume(thin), "and a second resume does nothing")
    out.that(takes_half(world, caster), "the trait survived both no-ops")

    # -- side state: a number in a dict -------------------------------------
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:suspension")

    def vuln() -> int:
        held = world.get(caster, Defences)
        return held.vulnerable.get(DamageType.FIRE, 0) if held else 0

    weak = c.vulnerable(5, DamageType.FIRE, until=When.ENCOUNTER, on=caster)
    out.that(vuln() == 5, "vulnerable 5 fire", f"{vuln()}")
    world.effects.suspend(weak)
    out.that(vuln() == 0, "suspended, the vulnerability is gone", f"{vuln()}")
    world.effects.resume(weak)
    out.that(vuln() == 5, "and comes back at 5, not 10", f"{vuln()}")
    world.effects.end(weak, "driver")
    out.that(vuln() == 0, "and a plain expiry still clears it", f"{vuln()}")

    # -- the double-lift control, aimed at where it can actually show -----
    #
    # **Written twice.** The first version expired a suspended
    # `c.vulnerable` and asserted the number had not gone to -5. It passed
    # with the guard deliberately removed, because `undo` pops the key
    # instead of writing a negative -- so the check was asserting something
    # true either way, which is the one thing a driver must not do.
    #
    # Where a double lift *does* show is `Conditions`, which is a refcount
    # shared by every effect imposing the same condition: lift one effect
    # twice and the second effect's hold is gone, while the second effect is
    # still standing and still owed its saving throw. Two sources of the
    # same condition is the board this needs.
    world, caster, _ = _board()
    first = Cast(world=world, me=caster, ref="drivers:suspension:a")
    second = Cast(world=world, me=caster, ref="drivers:suspension:b")
    one = first.insubstantial(on=caster, until=When.ENCOUNTER)
    two = second.insubstantial(on=caster, until=When.ENCOUNTER)
    out.that(takes_half(world, caster), "two effects impose the one condition")

    world.effects.suspend(one)
    out.that(takes_half(world, caster),
             "suspending one leaves the OTHER effect's hold standing")
    world.effects.end(one, "driver")
    out.that(takes_half(world, caster),
             "and expiring it does not lift the refcount a second time")
    # `two` is the second effect laid a dozen lines up and cannot be None
    # here; asserted rather than asserted-around so a future change that
    # makes the lay fail says so instead of raising on the attribute.
    out.that(two is not None and not two.ended,
             "the second effect never ended")

    world.effects.end(two, "driver")
    out.that(not takes_half(world, caster), "the last source ending does clear it")

    # -- side state: a label in a set ---------------------------------------
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:suspension")

    def ignores() -> set:
        held = world.get(caster, Movement)
        return set(held.ignores) if held else set()

    sure = c.ignores_difficult(on=caster, until=When.ENCOUNTER)
    out.that("*" in ignores(), "the terrain label goes on")
    world.effects.suspend(sure)
    out.that("*" not in ignores(), "suspension lifts it")
    world.effects.resume(sure)
    out.that("*" in ignores(), "and resuming restores it")

    # -- a watcher-shaped trait ---------------------------------------------
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:suspension")
    vital = world.get(caster, Health)
    vital.hp = max(1, vital.max_hp - 20)   # room to heal into

    def hp() -> int:
        return world.get(caster, Health).hp

    heals = c.regeneration(5, until=When.ENCOUNTER, on=caster)
    was = hp()
    world.bus.emit(TurnStart(actor=caster, round=world.round))
    out.that(hp() > was, "regeneration heals on a turn start",
             f"{was} -> {hp()}")

    world.effects.suspend(heals)
    was = hp()
    world.bus.emit(TurnStart(actor=caster, round=world.round))
    out.that(hp() == was,
             "a SUSPENDED watcher does nothing -- it installs no state",
             f"{was} -> {hp()}")

    world.effects.resume(heals)
    was = hp()
    world.bus.emit(TurnStart(actor=caster, round=world.round))
    out.that(hp() > was, "and heals again once resumed",
             f"{was} -> {hp()}")

    # -- the verb, end to end, clock and all --------------------------------
    #
    # **The suspending event must not be `TurnStart`**, which an earlier
    # version of this used for both halves -- so the one event that resumed
    # the trait also re-suspended it, and a `suspend_when` wired to resume
    # *nothing at all* passed every assertion in this driver. Found by
    # plant-testing, not by reading. A damage event for the trigger and a
    # turn start for the clock keeps the two separable.
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:suspension")
    thin = c.insubstantial(on=caster, until=When.ENCOUNTER)

    def burn(kind: DamageType) -> None:
        world.bus.emit(DamageApplied(
            source=caster, target=caster, amount=1, dtype=kind,
            absorbed=0, hp=1, detail="drivers:suspension",
        ))

    c.suspend_when(
        thin, DamageApplied,
        lambda ev: ev.target == caster and ev.dtype is DamageType.FIRE,
        for_=When.SONT,
    )
    out.that(takes_half(world, caster), "the trait is on before anything fires")

    burn(DamageType.COLD)
    out.that(takes_half(world, caster),
             "a damage type the predicate REFUSES does not suspend it")

    burn(DamageType.FIRE)
    out.that(not takes_half(world, caster), "the named type does")
    out.that(thin is not None and not thin.ended,
             "and still without ending the trait")

    world.bus.emit(TurnStart(actor=caster, round=world.round))
    out.that(takes_half(world, caster),
             "and it is back at the START OF ITS NEXT TURN -- the clock")

    # A second trigger while it is already off re-ups the one deadline. The
    # dropped timer must resume nothing, or the trait would come back the
    # instant the old clock ran out.
    burn(DamageType.FIRE)
    out.that(not takes_half(world, caster), "a later hit suspends it again")
    standing = len(world.effects.live)
    burn(DamageType.FIRE)
    burn(DamageType.FIRE)
    burn(DamageType.FIRE)
    out.that(not takes_half(world, caster),
             "more hits while it is off do not resume it")
    # Asserted on the count because the behaviour cannot tell the two apart:
    # five timers all come due at the same turn start and four of the five
    # resumes are no-ops, so a plant that removed the guard stayed green.
    # What a missing guard really costs is effects nobody can see.
    out.that(len(world.effects.live) == standing,
             "and lay no second timer -- one deadline, one effect",
             f"{len(world.effects.live)} live against {standing}")
    world.bus.emit(TurnStart(actor=caster, round=world.round))
    out.that(takes_half(world, caster), "and one turn start is still enough")

    # -- the exception, which is a different clause on the same cards --------
    #
    # "Takes half damage from any damage source, **except those that deal
    # force damage**" -- six stat blocks print it, and three of those six
    # print the suspension clause as well, which is why both live on the one
    # verb. Asserted through the damage path rather than by reading
    # `half_except` back: a set nothing subtracted from is the commonest bug
    # in this component.
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:suspension")
    vital = world.get(caster, Health)

    def struck(kind: DamageType, amount: int = 20) -> int:
        vital.hp = vital.max_hp
        world.damage(caster, caster, amount, kind, detail="drivers:suspension")
        return vital.max_hp - vital.hp

    out.that(struck(DamageType.COLD) == 20, "a plain creature takes it all",
             f"{struck(DamageType.COLD)}")
    thin = c.insubstantial(
        on=caster, until=When.ENCOUNTER, except_=(DamageType.FORCE,)
    )
    out.that(struck(DamageType.COLD) == 10, "insubstantial halves cold",
             f"{struck(DamageType.COLD)}")
    out.that(struck(DamageType.FORCE) == 20,
             "and does NOT halve the excepted type",
             f"{struck(DamageType.FORCE)}")

    # The exception must go with the trait when the trait is switched off, or
    # a suspended creature would be left with a standing exception to nothing.
    world.effects.suspend(thin)
    out.that(struck(DamageType.COLD) == 20, "suspended, cold is not halved")
    world.effects.resume(thin)
    out.that(struck(DamageType.COLD) == 10, "resumed, it is halved again")
    out.that(struck(DamageType.FORCE) == 20, "and force is still excepted")

    # **A suspended exception must come off the creature, and that is only
    # observable with a second trait standing.** Suspension takes the
    # condition away, so `takes_half` answers False before it ever reads the
    # exception set -- which is why a plant that stopped the exception
    # lifting stayed green here. Lay a plain insubstantial beside it and the
    # stale exception becomes visible: the creature would stop halving force
    # on the authority of a trait that is switched off.
    world, caster, _ = _board()
    first = Cast(world=world, me=caster, ref="drivers:suspension:a")
    second = Cast(world=world, me=caster, ref="drivers:suspension:b")
    vital = world.get(caster, Health)
    excepting = first.insubstantial(
        on=caster, until=When.ENCOUNTER, except_=(DamageType.FORCE,)
    )
    second.insubstantial(on=caster, until=When.ENCOUNTER)
    out.that(struck(DamageType.FORCE) == 20,
             "with both standing, the exception holds",
             f"{struck(DamageType.FORCE)}")
    world.effects.suspend(excepting)
    out.that(struck(DamageType.FORCE) == 10,
             "suspend the excepting trait and the other one halves force again",
             f"{struck(DamageType.FORCE)}")
    world.effects.resume(excepting)
    out.that(struck(DamageType.FORCE) == 20, "and the exception comes back")

    # An insubstantial with no exception halves everything, which is the
    # negative control: the exception must come from the row, not the verb.
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:suspension")
    vital = world.get(caster, Health)
    c.insubstantial(on=caster, until=When.ENCOUNTER)
    out.that(struck(DamageType.FORCE) == 10,
             "a trait with no exception halves force too",
             f"{struck(DamageType.FORCE)}")



############################################################

def sure_footed(out: Result) -> None:
    """"Ignores difficult terrain when it shifts" -- and only when it shifts.

    The printed rule this hangs off is arithmetic rather than a special case:
    a square of difficult terrain costs one extra to enter, and a shift is
    one square of movement, so **a shift cannot enter difficult terrain at
    all** unless something exempts the creature. 23 rows print that
    exemption, and until now `c.ignores_difficult` could only grant it
    unconditionally -- which made every one of those rows better than its
    card on walks, charges and runs too.

    So the assertion that matters is the **negative** one: the exemption must
    not leak into the other kinds of going. A driver that only checked "it
    can shift into the mud now" would pass an implementation that exempted
    everything, which is the implementation we already had.

    Asserted on what the creature is *offered*, which is where the cost is
    actually spent: nothing in `shift` or `step` charges for terrain, so a
    test that moved the creature and looked at where it ended up would pass
    no matter what this code did.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Movement
    from combat_engine.engine.durations import When

    world, caster, _ = _board()
    mud = world.reachable_squares(caster, 1, kind="shift")[0]
    world.grid.difficult[mud] = "mud"

    def offered(kind: str, budget: int = 1) -> bool:
        return mud in world.reachable_squares(caster, budget, kind=kind)

    out.that(not offered("walk"), "a square of mud is not one square of walking")
    out.that(not offered("shift"), "and a one-square shift cannot enter it")
    out.that(offered("walk", 2), "two squares of walking does reach it")

    c = Cast(world=world, me=caster, ref="drivers:sure_footed")
    held = c.ignores_difficult(on=caster, until=When.ENCOUNTER, when="shift")
    out.that(offered("shift"), "exempt while shifting, the shift reaches it")
    out.that(not offered("walk"),
             "and the exemption does NOT leak into walking")
    out.that(not offered("charge"), "nor into a charge")
    out.that(not offered("run"), "nor into a run")

    # The unscoped form is the one that was being used for these rows, and it
    # is the thing the scope exists to be different from.
    world, caster, _ = _board()
    mud = world.reachable_squares(caster, 1, kind="shift")[0]
    world.grid.difficult[mud] = "mud"
    Cast(world=world, me=caster, ref="drivers:sure_footed").ignores_difficult(
        on=caster, until=When.ENCOUNTER
    )
    out.that(offered("shift"), "the unscoped form exempts the shift")
    out.that(offered("walk"), "and the walk as well -- which is the difference")

    # A scope on a kind nothing prices is refused, not stored. An exemption
    # nothing ever consults is this component's commonest bug.
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:sure_footed")
    refused = False
    try:
        c.ignores_difficult(on=caster, when="teleport")
    except ValueError:
        refused = True
    out.that(refused, "a scope on a kind nothing prices raises rather than storing")
    moves = world.get(caster, Movement)
    out.that(not (moves and moves.ignores_when),
             "and left nothing behind on the creature")

    # It comes off, and it suspends -- it is side state like the unscoped
    # form, so #470's lift has to reach it.
    world, caster, _ = _board()
    mud = world.reachable_squares(caster, 1, kind="shift")[0]
    world.grid.difficult[mud] = "mud"
    c = Cast(world=world, me=caster, ref="drivers:sure_footed")
    held = c.ignores_difficult(on=caster, until=When.ENCOUNTER, when="shift")
    out.that(offered("shift"), "laid")
    world.effects.suspend(held)
    out.that(not offered("shift"), "suspended, the scoped exemption lifts too")
    world.effects.resume(held)
    out.that(offered("shift"), "and comes back")
    world.effects.end(held, "driver")
    out.that(not offered("shift"), "and ends")




############################################################

def reentry(out: Result) -> None:
    """A watcher is not re-entered by an event its own handler caused.

    The printed rules say nothing about this; it is a property of the engine
    that nine rows depend on. "Whenever you heal a creature, it regains extra
    hit points" is a `Healed` watcher that heals, and the heal it performs is
    another `Healed` from the same source -- so the handler answers itself
    until the stack runs out. **Four of the nine rows had hand-rolled a latch
    and four had not**, and `i661p1`'s comment states the rule its neighbours
    were missing: "without the latch it answers its own `Healed` and recurses
    until the stack runs out."

    It took the whole audit down with a `RecursionError` the moment #448 let
    item rows reach a dealt character, because that put one of the unlatched
    four on a board where somebody else healed an ally.

    **Scoped to the one subscription, which is the half worth asserting.** A
    row whose handler causes an event must still let every *other* row see
    it; only its own re-entry is the bug. A guard keyed on the event class
    would have silently stopped the second half, and nothing printed would
    have complained.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health
    from combat_engine.engine.durations import When
    from combat_engine.engine.events import Healed

    world, caster, _ = _board()
    vital = world.get(caster, Health)
    vital.hp = max(1, vital.max_hp - 30)

    c = Cast(world=world, me=caster, ref="drivers:reentry")
    mine: list[int] = []

    def greedy(ev: Healed) -> None:
        # The shape of all nine rows: heal again, from the same source.
        mine.append(1)
        c.heal(1, on=caster)

    c.watch(Healed, greedy, until=When.ENCOUNTER, on=caster)
    c.heal(1, on=caster)
    out.that(len(mine) == 1,
             "a handler that heals is entered ONCE, not once per cascade",
             f"entered {len(mine)} times")

    # And the other half: a second watcher still sees what the first caused.
    world, caster, _ = _board()
    vital = world.get(caster, Health)
    vital.hp = max(1, vital.max_hp - 30)
    first = Cast(world=world, me=caster, ref="drivers:reentry:a")
    second = Cast(world=world, me=caster, ref="drivers:reentry:b")
    seen_a: list[int] = []
    seen_b: list[int] = []

    def causes(ev: Healed) -> None:
        seen_a.append(1)
        first.heal(1, on=caster)

    def observes(ev: Healed) -> None:
        seen_b.append(1)

    first.watch(Healed, causes, until=When.ENCOUNTER, on=caster)
    second.watch(Healed, observes, until=When.ENCOUNTER, on=caster)
    first.heal(1, on=caster)
    out.that(len(seen_a) == 1, "the causing watcher fires once",
             f"{len(seen_a)}")
    out.that(len(seen_b) >= 2,
             "the OTHER watcher still sees the event it caused",
             f"saw {len(seen_b)}")

    # A plain watcher that causes nothing is unaffected -- the negative
    # control, so the latch cannot be passing by refusing everything.
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:reentry")
    vital = world.get(caster, Health)
    vital.hp = max(1, vital.max_hp - 30)
    count: list[int] = []
    c.watch(Healed, lambda ev: count.append(1), until=When.ENCOUNTER, on=caster)
    c.heal(1, on=caster)
    c.heal(1, on=caster)
    c.heal(1, on=caster)
    out.that(len(count) == 3,
             "three separate heals still fire the watcher three times",
             f"{len(count)}")




############################################################

def two_types(out: Result) -> None:
    """One roll that is two damage types, and resistance reads it as a unit.

    88 stat blocks print "2d6 + 5 cold and necrotic damage" -- one roll that
    is both -- and `Damage` carried a single `dtype`, so each of those rows
    was declared as half of what it is. The half that was missing is not the
    log line: it is that **a creature resisting only the second type shrugged
    off nothing**, in every fight, invisibly.

    The printed rule is that resistance to a blow of several types applies
    only as far as the creature resists **all** of them -- so a creature
    resisting one of two takes it in full, and that is the assertion here
    rather than the easier one. A driver that only checked "the log says both
    words" would pass an implementation that typed the blow correctly and
    priced it wrong.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defences, Health
    from combat_engine.engine.dsl import Damage
    from combat_engine.engine.query import enemies
    from combat_engine.engine.types import DamageType as D

    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    vital = world.get(foe, Health)

    def struck(dtypes: tuple, amount: int = 20) -> int:
        vital.hp = vital.max_hp
        world.damage(caster, foe, amount, dtypes[0], detail="drivers:two_types",
                     dtypes=dtypes)
        return vital.max_hp - vital.hp

    out.that(struck((D.COLD, D.NECROTIC)) == 20,
             "a two-type blow lands in full on a creature resisting neither")

    held = world.get(foe, Defences) or world.add(foe, Defences())
    held.resist[D.COLD] = 10
    out.that(struck((D.COLD, D.NECROTIC)) == 20,
             "resisting ONE of the two still takes it in full",
             f"{struck((D.COLD, D.NECROTIC))} of 20")
    out.that(struck((D.COLD,)) == 10,
             "and the same resistance does bite a single-type blow",
             f"{struck((D.COLD,))} of 20")

    held.resist[D.NECROTIC] = 10
    out.that(struck((D.COLD, D.NECROTIC)) == 10,
             "resisting BOTH finally reduces it",
             f"{struck((D.COLD, D.NECROTIC))} of 20")

    # And the header carries it through `c.hit`, which is how all 88 rows
    # deal their damage -- the field being set is worth nothing if the verb
    # that reads it drops the second type.
    line = Damage("2d6", 5, dtype=[D.COLD, D.NECROTIC])
    out.that(line.dtypes == (D.COLD, D.NECROTIC),
             "a header line keeps the whole type")
    out.that(line.dtype is D.COLD,
             "and its primary is the first the card prints")
    out.that(str(line) == "2d6 + 5 cold and necrotic damage",
             "and prints the way the card does", str(line))

    # **Five types, because two could not tell a comma join from "and and
    # and".** The prototype on #420 rendered "acid and cold and fire and
    # lightning and poison"; `cards.py` compares this string against the
    # printed line, and two of the 88 rows name five types. A plant that
    # broke the join passed a two-type assertion unchanged.
    five = Damage("3d6", 2, dtype=[D.ACID, D.COLD, D.FIRE, D.LIGHTNING, D.POISON])
    out.that(str(five) == "3d6 + 2 acid, cold, fire, lightning, and poison damage",
             "five types read as the card prints them", str(five))

    # **Through `c.hit`, which is how all 88 rows actually deal it.** The
    # field being set is worth nothing if the verb that reads the header
    # drops the second type -- #420 named that forwarding line as the known
    # trap, and a plant removing it passed everything above.
    from audit import board as _posed
    from combat_engine.engine.dsl import REGISTRY

    ref = "m2615a3"                      # acid, cold, fire, lightning, poison
    world, caster, _ = _posed(ref, 1)
    foe = enemies(world, caster)[0]
    hurt = world.get(foe, Health)
    if hurt is None:
        # Seven reads below go through this, and a board creature always has
        # it -- so this is a skip and not a guard. Reported as one because
        # this file's rule is that a check which runs on half its runs is
        # not a check.
        out.skip("the board's enemy has no hit points to take damage off")
        return
    mine = Cast(world=world, me=caster, ref=ref)
    declared = REGISTRY[ref]
    out.that(declared.damage is not None
             and len(declared.damage.dtypes) == 5,
             f"{ref} declares five types in its header")

    held = world.get(foe, Defences) or world.add(foe, Defences())
    held.resist[D.ACID] = 100            # one of the five, hugely
    hurt.hp = hurt.max_hp
    mine.hit(on=foe)
    took = hurt.max_hp - hurt.hp
    out.that(took > 0,
             "resisting one of five does not stop a c.hit blow at all",
             f"took {took}")

    for kind in (D.COLD, D.FIRE, D.LIGHTNING, D.POISON):
        held.resist[kind] = 100
    hurt.hp = hurt.max_hp
    mine.hit(on=foe)
    out.that(hurt.max_hp - hurt.hp == 0,
             "and resisting all five stops it dead",
             f"took {hurt.max_hp - hurt.hp}")

    # **The second consumer of a header `Damage` is the summon block**, and
    # it forwards the whole type too -- but nothing can exercise it: of 31
    # summon blocks carrying a damage line, **none prints more than one
    # type**, so a plant that removed that forwarding stays green and will
    # go on staying green. Asserted as the count rather than the behaviour,
    # so the day a summon does print two this line goes red and names the
    # thing that needs covering. #420.
    summons = [
        pw for pw in REGISTRY.values()
        if getattr(pw, "summon", None) is not None
        and getattr(pw.summon, "damage", None) is not None
    ]
    multi = [pw for pw in summons if pw.summon.damage.dtypes]
    out.that(
        not multi,
        f"no summon block prints two types yet, so its forwarding is untested "
        f"({len(summons)} carry a damage line)",
        str([pw.ref for pw in multi][:4]),
    )




############################################################

def aftereffect(out: Result) -> None:
    """A second clause that lands when the first one ends.

    "The target is stunned until the end of its next turn. **Aftereffect:**
    the target takes a -2 penalty to attack rolls (save ends)" -- 22 rows
    print one. It is the mirror of `escalate=`, which runs on a *failed* save
    and worsens the hold in place: this runs when the hold is **over**, by a
    save or by its clock.

    Three things are asserted and the last two are the ones that could go
    quietly wrong:

    * it lands when the hold ends, and not before;
    * it lands **once**, not once per end -- `on_end` can be reached twice
      for one effect if anything ends it again;
    * it does **not** land when the encounter closes. `on_end` is handed no
      reason and runs for every end alike, so without a guard every
      aftereffect in play would pay out as the board is torn down, laying
      conditions on a decided fight.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health
    from combat_engine.engine.durations import When
    from combat_engine.engine.query import enemies, is_
    from combat_engine.engine.types import Condition

    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    c = Cast(world=world, me=caster, ref="drivers:aftereffect")

    held = c.condition(Condition.STUNNED, until=When.ENCOUNTER, on=foe)
    c.aftereffect(held, lambda: c.condition(
        Condition.SLOWED, until=When.SAVE_ENDS, on=foe))
    out.that(is_(world, foe, Condition.STUNNED), "the hold is on")
    out.that(not is_(world, foe, Condition.SLOWED),
             "and the aftereffect has NOT landed yet")

    world.effects.end(held, "driver")
    out.that(not is_(world, foe, Condition.STUNNED), "the hold goes")
    out.that(is_(world, foe, Condition.SLOWED),
             "and the aftereffect lands as it goes")

    # Once, not once per end.
    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    c = Cast(world=world, me=caster, ref="drivers:aftereffect")
    count: list[int] = []
    held = c.condition(Condition.STUNNED, until=When.ENCOUNTER, on=foe)
    c.aftereffect(held, lambda: count.append(1))
    world.effects.end(held, "driver")
    world.effects.end(held, "driver again")
    out.that(len(count) == 1, "it lands once, not once per end",
             f"landed {len(count)} times")

    # **And not when the fight is over**, which is the guard worth having.
    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    c = Cast(world=world, me=caster, ref="drivers:aftereffect")
    late: list[int] = []
    held = c.condition(Condition.STUNNED, until=When.ENCOUNTER, on=foe)
    c.aftereffect(held, lambda: late.append(1))
    world.effects.end_encounter()
    out.that(not late,
             "the encounter ending does NOT pay out the aftereffect",
             f"landed {len(late)} times")

    # **And not when the creature holding it dies**, which the audit found
    # and this driver was not looking for: `i1621p1` raised inside `_die`,
    # two frames under `bereave`, reaching for a creature no longer on the
    # board. A hold cleared by death has no aftereffect to pay -- the card's
    # clause is about the hold ending, not about the victim being removed.
    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    c = Cast(world=world, me=caster, ref="drivers:aftereffect")
    posthumous: list[int] = []
    held = c.condition(Condition.STUNNED, until=When.ENCOUNTER, on=foe)
    c.aftereffect(held, lambda: posthumous.append(1))
    hurt = world.get(foe, Health)
    world.damage(caster, foe, hurt.max_hp + 50, detail="drivers:aftereffect")
    out.that(not posthumous,
             "a holder dying does NOT pay out the aftereffect",
             f"landed {len(posthumous)} times")

    # The negative control: `escalate=` is a different clause and still is.
    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    c = Cast(world=world, me=caster, ref="drivers:aftereffect")
    worse: list[int] = []
    c.condition(Condition.STUNNED, until=When.SAVE_ENDS, on=foe,
                escalate=lambda eff: worse.append(1))
    out.that(not worse, "escalate has not run either, on a fresh hold")




############################################################

def crit_kill(out: Result) -> None:
    """"A critical hit automatically reduces it to 0 hit points."

    Nine stat blocks print it -- brittle constructs and the like -- and it is
    **not damage**: no amount is rolled, so resistance does not apply, being
    insubstantial does not halve it, and immunity to the blow's type does not
    stop it. Dealing a very large hit instead would be wrong at all four of
    those joints, which is why `c.kill` exists rather than
    `c.damage(9999)`.

    What it must still do is go out through the engine's one path from zero,
    so `Dropped` is announced and the dying conditions or the death land
    according to `Health.dying_at`. A creature sitting at 0 that nothing
    noticed is the failure mode here.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defences, Health
    from combat_engine.engine.events import Dropped
    from combat_engine.engine.query import alive, enemies
    from combat_engine.engine.types import DamageType as D

    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    hurt = world.get(foe, Health)
    hurt.hp = hurt.max_hp
    seen: list[Dropped] = []
    world.bus.on(Dropped, seen.append)

    c = Cast(world=world, me=caster, ref="drivers:crit_kill")
    out.that(alive(world, foe), "the creature starts alive", f"{hurt.hp} hp")
    out.that(c.kill(on=foe, critical=True), "killing it reports that it moved")
    out.that(hurt.hp == 0, "it is at 0 hit points", f"{hurt.hp}")
    out.that(not alive(world, foe), "and it is down")
    out.that(len(seen) == 1, "`Dropped` was announced once", f"{len(seen)}")
    out.that(seen and seen[0].critical,
             "and it carries the critical flag, which the mirror rows read")

    # Killing what is already down does nothing and says so.
    out.that(not c.kill(on=foe), "killing it again reports no change")

    # **Resistance and immunity do not stop it, because it is not damage.**
    # This is the half a `c.damage(9999)` implementation would fail.
    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    hurt = world.get(foe, Health)
    hurt.hp = hurt.max_hp
    held = world.get(foe, Defences) or world.add(foe, Defences())
    for kind in D:
        held.immune.add(kind)
    c = Cast(world=world, me=caster, ref="drivers:crit_kill")
    out.that(c.kill(on=foe), "immune to every damage type and still killed")
    out.that(hurt.hp == 0, "at 0 hit points", f"{hurt.hp}")

    # The negative control: ordinary damage *is* stopped by that immunity,
    # so the board is genuinely immune and the kill is genuinely not damage.
    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    hurt = world.get(foe, Health)
    hurt.hp = hurt.max_hp
    held = world.get(foe, Defences) or world.add(foe, Defences())
    held.immune.add(D.FIRE)
    world.damage(caster, foe, 50, D.FIRE, detail="drivers:crit_kill")
    out.that(hurt.hp == hurt.max_hp,
             "50 fire into a fire-immune creature does nothing",
             f"{hurt.hp}/{hurt.max_hp}")




############################################################

def forms(out: Result) -> None:
    """"Requirement: it must be in beast or hybrid form" -- which shape is it?

    58 rows across the tree print a Requirement naming a shape. `c.form`
    identified a form only by the effect label it laid, which is the ref of
    the row that laid it, so `level_04/brutes_sa.py` grew `_in_shapes` to
    sniff those labels. This is the same question asked of a component
    instead, which the policy and the wire can read as well.

    **Permissive when nothing has been recorded**, and that is the half most
    worth asserting because the decision is borrowed rather than mine:
    `_in_shapes`' own note says a creature that has not changed shape is in
    whatever shape it was found in, the block does not say which, so no
    attack is ruled out. Choosing a starting form instead would silently
    refuse half of every shapechanger's card on the strength of something
    nobody printed.

    **A set, not a current-form string**: a card printing "humanoid or
    hybrid" on one row and "beast or hybrid" on another means hybrid has to
    satisfy both at once.

    The words are the 4e categories rather than the species the cards print,
    because a species *is* a printed name -- five of them reached 32 rows of
    mine before `leaks.py` caught the sixth.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.durations import When
    from combat_engine.engine.query import in_form, shifted

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:forms")

    # Nothing recorded: a Requirement must not refuse.
    out.that(in_form(world, caster, "humanoid", "hybrid"),
             "with no shape recorded, a Requirement passes")
    out.that(in_form(world, caster, "beast"),
             "whichever shape it names -- nothing is ruled out")
    out.that(not shifted(world, caster),
             "but it has not SHIFTED, which is the other question")

    beast = c.form(until=When.ENCOUNTER, name="beast")
    out.that(in_form(world, caster, "beast"), "once in beast form, beast passes")
    out.that(not in_form(world, caster, "humanoid", "hybrid"),
             "and the shapes it is NOT now refuse -- the gate bites")
    out.that(shifted(world, caster), "and it counts as shifted")

    hybrid = c.form(until=When.ENCOUNTER, name="hybrid")
    out.that(in_form(world, caster, "beast") and in_form(world, caster, "hybrid"),
             "two at once, which one creature's two rows need")
    out.that(in_form(world, caster, "humanoid", "hybrid"),
             "and any one of several named shapes is enough")
    out.that(in_form(world, caster, " Beast "),
             "the word is matched loosely, since it comes off a card")

    world.effects.end(beast, "driver")
    out.that(not in_form(world, caster, "beast"), "ending a form takes it off")
    out.that(in_form(world, caster, "hybrid"), "and leaves the other standing")

    world.effects.end(hybrid, "driver")
    out.that(not shifted(world, caster), "with both gone it is itself again")
    out.that(in_form(world, caster, "beast"),
             "and a Requirement is permissive once more")

    # **Where the permissive half is the WRONG reader**, which cost a row.
    #
    # The reasoning above is about a creature whose block does not say what
    # shape it was found in. A character is not that case: it starts
    # humanoid, always, and only its own row puts it in another form. So a
    # Requirement of the form "that row must be active" asked through
    # `in_form` answers **yes before the row has ever been used** --
    # `p14193b`'s first draft did exactly that and `audit` exercised it on
    # a board where nobody had transformed.
    #
    # The answerable question is whether a hold that row laid still stands,
    # since every effect carries the laying ref. Asserted here and not only
    # in the content file because the mistake is available to all 58 rows
    # printing a shape Requirement, not to that one.
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:forms")

    def laid_by(ref: str) -> bool:
        return any(e.label.startswith(ref) for e in world.effects.of(caster))

    out.that(in_form(world, caster, "hybrid"),
             "the permissive reader says yes before any form is taken --"
             " correct for a monster, and the trap for a character's row")
    out.that(not laid_by("drivers:forms"),
             "the effect-label read says no, which is the negative control"
             " and the whole point of the distinction")
    c.form(until=When.ENCOUNTER, name="hybrid", label=c.ref)
    out.that(laid_by("drivers:forms"),
             "and yes once the row has actually laid the form")

    # Suspension, because a form is side state like a terrain exemption.
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:forms")
    held = c.form(until=When.ENCOUNTER, name="beast")
    out.that(shifted(world, caster), "laid")
    world.effects.suspend(held)
    out.that(not shifted(world, caster), "suspended, the form lifts")
    world.effects.resume(held)
    out.that(shifted(world, caster), "and comes back")

    # The negative control: a form laid with no name records nothing, so the
    # name is what does the work.
    world, caster, _ = _board()
    Cast(world=world, me=caster, ref="drivers:forms").form(until=When.ENCOUNTER)
    out.that(not shifted(world, caster),
             "a form laid with no name records no shape at all")

    # ---- end to end, through a real grantor row (#477) ------------------
    #
    # **Everything above this point would pass with every grantor in the tree
    # broken**, because it lays its own forms. That is exactly the regression
    # the fold could cause: `monsters/forms.py`'s readers ask `Shapes`, and a
    # grantor that forgets `name=` records nothing -- so `in_form` falls back
    # to its permissive answer and **44 gates start passing unconditionally**.
    # Silently false, and no row would look wrong.
    #
    # So this asserts the whole path a card takes: use the printed polymorph
    # row, then ask the question its own stat block's Requirements ask.
    from combat_engine.engine.dsl import use

    world, caster, _ = _board("m2812a4", 1)
    out.that(not shifted(world, caster), "before using it, no shape is recorded")
    use(world, caster, "m2812a4")
    out.that(shifted(world, caster),
             "using a real printed polymorph row records a shape -- this is"
             " the rule that catches a grantor which forgot `name=`")
    out.that(in_form(world, caster, "wolf") or in_form(world, caster, "bugbear"),
             "and it is one of the two shapes that card prints")
    out.that(not (in_form(world, caster, "wolf")
                  and in_form(world, caster, "bugbear")),
             "exactly one of them, because a polymorph ends the shape before")




############################################################

def substitution(out: Result) -> None:
    """"You can X instead of Y" -- one clause of a row, replaced.

    Twelve feats print a sentence of this shape against a named row, and
    nine more hand a named row an extra clause. Neither had anywhere to go.

    **The substitution is not a prompt.** It is settled before the body
    runs, from the `Action` the menu offered, which is the arrangement
    `branch` and `augment` already use and for the reason `Action.augment`
    states: that is what makes both reachable by clicking *and* weighable by
    a policy. A `c.choose` inside a body is invisible to `policy/`, which
    cannot compare "pull" against "slide" if the option was scored before
    the question was put.

    **It replaces a clause, never a body.** `p5330` pulls and damages; the
    card says "slide instead of pulling", and swapping the whole body would
    quietly cost it the damage. So the row reads `c.instead_of` at the pull,
    which is the deal `change_dice`/`dice_for` already makes -- a row must
    read it to be changed.
    """
    from combat_engine.engine.actions import _variants
    from combat_engine.engine.cast import Cast

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:sub")
    done: list[str] = []

    def printed() -> str:
        done.append("pull")
        return "pull"

    # Nothing registered: the clause is the printed one, and the menu holds
    # exactly one way of using the row.
    out.that(c.instead_of("pull", printed) == "pull",
             "with nothing registered, the printed clause runs")
    out.that(done == ["pull"], "and it really ran, rather than being skipped")
    out.that(_variants(world, caster, "p999") == [0],
             "and the row offers one option, as printed")

    held = c.pre_empt("p999", "pull", lambda using: "slide")
    out.that(held is not None, "a substitution is laid as an effect")
    out.that(_variants(world, caster, "p999") == [0, 1],
             "and now the row offers two -- the printed one still first")
    out.that(c.substitutions("p999") == ["drivers:sub"],
             "labelled with the row that registered it")

    # variant 0 is still the card. This is the half a chargen-time swap
    # would lose: 25 of the 30 cards say "you can", so the printed clause
    # is never taken away.
    done.clear()
    base = Cast(world=world, me=caster, ref="p999")
    out.that(base.instead_of("pull", printed) == "pull",
             "on variant 0 the printed clause still runs")

    done.clear()
    swapped = Cast(world=world, me=caster, ref="p999", variant=1)
    out.that(swapped.instead_of("pull", printed) == "slide",
             "on variant 1 the substitution runs instead")
    out.that(done == [], "and the printed clause did NOT also run")

    # The rest of the row is untouched, which is the whole argument for
    # putting this at the clause rather than at the body.
    out.that(swapped.instead_of("damage", lambda: "damage") == "damage",
             "every OTHER clause of the row is still the printed one")

    # A second feat on the same clause is another option, not a stack.
    c.pre_empt("p999", "pull", lambda using: "teleport")
    out.that(_variants(world, caster, "p999") == [0, 1, 2],
             "two feats on one clause are three options, not four")
    out.that(len(c.substitutions("p999")) == 2,
             "and both are listed")
    picked = Cast(world=world, me=caster, ref="p999", variant=1)
    out.that(picked.instead_of("pull", printed) == "teleport",
             "the latest registered leads, as `rolls` and `dice` do")

    # Out of range is the printed card rather than a crash: a stale Action
    # can outlive the effect that put it in the menu.
    far = Cast(world=world, me=caster, ref="p999", variant=99)
    done.clear()
    out.that(far.instead_of("pull", printed) == "pull",
             "a variant that no longer exists falls back to the card")
    out.that(done == ["pull"], "and the printed clause is what ran")
    # Variant 0 is held by the same range check, not by the fast path above
    # it -- reverting the fast path leaves every assertion here green.
    zero = Cast(world=world, me=caster, ref="p999", variant=0)
    done.clear()
    out.that(zero.instead_of("pull", printed) == "pull"
             and done == ["pull"],
             "and so is variant 0, by the range check rather than the fast path")

    # Ending it puts the clause back and takes the menu entry away.
    world.effects.end(held, "driver")
    out.that(len(c.substitutions("p999")) == 1,
             "ending one substitution leaves the other standing")
    for eff in list(world.effects.of(caster)):
        if "pre-empts" in eff.label:
            world.effects.end(eff, "driver")
    out.that(c.substitutions("p999") == [],
             "and with both gone the row is only itself")
    out.that(_variants(world, caster, "p999") == [0],
             "which the menu agrees with")

    # Suspension, because a registration is side state like the rest (#470).
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:sub")
    sus = c.pre_empt("p999", "pull", lambda using: "slide")
    out.that(len(c.substitutions("p999")) == 1, "laid")
    world.effects.suspend(sus)
    out.that(c.substitutions("p999") == [], "suspended, the option goes away")
    world.effects.resume(sus)
    out.that(len(c.substitutions("p999")) == 1, "and comes back")



############################################################

def drawing(out: Result) -> None:
    """Taking a weapon up: from a body for nothing, or cheaper than a minor.

    **The draw already existed.** `actions._wielding` has offered it since a
    ranger who put the bow away could otherwise never pick it up again, and
    it charges the printed minor action. So `c.draw()` is not "drawing" --
    it is the taking-up on its own, for a row that has already bought the
    action ("you can draw and attack with a dagger as part of the same
    standard action").

    The other three rows change what the *menu's* draw costs, which is a
    fact about the creature rather than about any row and so cannot live in
    a header. `Gear.draw_cost` records it and `_wielding` reads it.

    `c.draw()` was one symbol over 20 rows and three unrelated mechanisms:
    weapons in hand, an entire Fortune Card deck, and one monster dropping
    everything it carries. Only the first is here.
    """
    from combat_engine.engine.actions import _wielding
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Gear
    from combat_engine.engine.types import ActionType

    world, caster, _ = _board("p5330")
    c = Cast(world=world, me=caster, ref="drivers:draw")
    gear = world.get(caster, Gear) or world.add(caster, Gear())
    if len(gear.weapons) < 2:
        out.that(False, "the board deals this character two weapons")
        return

    # Stow everything but the first, so there is something to draw.
    second = gear.weapons[1]
    gear.wield(gear.weapons[0])
    out.that(second.ref in gear.stowed, "the second weapon starts on the belt")

    out.that(c.draw(), "c.draw takes up what is stowed")
    out.that(second.ref not in gear.stowed, "and it is in hand afterwards")

    # Nothing left to take: the row can tell, rather than silently passing.
    for w in gear.weapons:
        gear.stowed.discard(w.ref)
    out.that(not c.draw(), "with nothing stowed it answers False")

    # Named, for a card that says which weapon.
    gear.stowed.add(second.ref)
    out.that(not c.draw("nosuchref"), "a ref that is not stowed is not drawn")
    out.that(second.ref in gear.stowed, "and nothing else was taken instead")
    out.that(c.draw(second.ref), "the named one is")

    # ---- what the MENU charges ----------------------------------------
    world, caster, _ = _board("p5330")
    c = Cast(world=world, me=caster, ref="drivers:draw")
    gear = world.get(caster, Gear)
    gear.wield(gear.weapons[0])
    enc = world.encounter

    offers = _wielding(world, enc, caster)
    out.that(bool(offers), "the menu offers a draw")
    out.that(all(a.cost is ActionType.MINOR for a in offers),
             "and charges the printed minor action by default")

    held = c.draws_free(per_turn=1)
    out.that(held is not None, "a cheaper draw is laid as an effect")
    offers = _wielding(world, enc, caster)
    out.that(offers and all(a.cost is ActionType.FREE for a in offers),
             "now the same draw is free")

    # Spent, it is a minor again -- the row says "once per turn", not
    # "once per encounter", so the draw must not disappear.
    gear.draws_left = 0
    offers = _wielding(world, enc, caster)
    out.that(bool(offers), "with the allowance spent the draw is still offered")
    out.that(all(a.cost is ActionType.MINOR for a in offers),
             "at the printed minor again, rather than vanishing")

    # And the start of the creature's turn refills it.
    world.encounter._begin(caster)
    out.that(gear.draws_left == 1, "its own turn starting refills the allowance")

    # An unlimited one is never spent down.
    world, caster, _ = _board("p5330")
    c = Cast(world=world, me=caster, ref="drivers:draw")
    gear = world.get(caster, Gear)
    c.draws_free()
    out.that(gear.draws_left == -1, "a card printing no limit is unlimited")
    world.encounter._begin(caster)
    out.that(gear.draws_left == -1, "and stays so across a turn")

    # Ending it puts the printed cost back.
    world, caster, _ = _board("p5330")
    c = Cast(world=world, me=caster, ref="drivers:draw")
    gear = world.get(caster, Gear)
    eff = c.draws_free(per_turn=1)
    out.that(gear.draw_cost is ActionType.FREE, "laid")
    world.effects.suspend(eff)
    out.that(gear.draw_cost is None, "suspended, the printed minor is back")
    world.effects.resume(eff)
    out.that(gear.draw_cost is ActionType.FREE, "and it comes back")
    world.effects.end(eff, "driver")
    out.that(gear.draw_cost is None and gear.draws_left == -1,
             "ended, the creature draws for a minor like everybody else")


############################################################

def reroll_low(out: Result) -> None:
    """"Reroll each damage die that shows a 1 until it shows a different
    number."

    14 rows print it and `c.reroll_damage` is **not** it: that rolls the
    whole expression twice and keeps the higher, which is a stronger rule.
    `f1378b`'s own note says six rows wanted the weaker one. Here each low
    die is replaced on its own and the rest of the roll stands.

    Read inside `_roll_damage`, where the dice are in hand -- `DamageRolled`
    carries a total with no dice behind it, and a character's damage is
    rolled in the body rather than declared in a header. That is the same
    argument `reroll_damage` and `c.maximise` already make.
    """
    from combat_engine.engine.cast import Cast, _faces_of
    from combat_engine.engine.types import Keyword

    out.that(_faces_of("2d6+5") == 6 and _faces_of(5) == 0,
             "a flat damage line has no faces and does not raise")

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:reroll")
    out.that(c._reroll_floor() == 0, "with nothing recorded there is no floor")

    held = c.reroll_ones()
    out.that(held is not None, "a reroll hold is laid as an effect")
    out.that(c._reroll_floor() == 2, "and ones are what it rerolls")

    # The real assertion: over many rolls, no die may come up under the
    # floor. A single roll would pass on luck alone.
    lows = 0
    for _ in range(400):
        if c._roll_damage("1d6") == 1:
            lows += 1
    out.that(lows == 0, "across 400 rolls of 1d6, not one result is a 1")

    # And the negative control -- without the hold, ones DO come up, so the
    # assertion above is about the hold and not about the dice.
    world2, other, _ = _board()
    plain = Cast(world=world2, me=other, ref="drivers:reroll")
    seen = sum(1 for _ in range(400) if plain._roll_damage("1d6") == 1)
    out.that(seen > 0, "and without the hold a 1 comes up, so that was the hold")

    # The rest of the expression is untouched: a flat bonus still lands and
    # the dice that were fine keep their faces.
    out.that(all(c._roll_damage("1d6+5") >= 7 for _ in range(50)),
             "the flat half of the expression is left alone")
    out.that(all(2 <= c._roll_damage("1d6") <= 6 for _ in range(50)),
             "and a rerolled die stays inside its own faces")

    # "A 1 or a 2" is the other threshold one card prints.
    world3, third, _ = _board()
    c3 = Cast(world=world3, me=third, ref="drivers:reroll")
    c3.reroll_ones(below=3)
    out.that(all(c3._roll_damage("1d8") >= 3 for _ in range(200)),
             "below=3 rerolls a 1 and a 2 both")

    # A threshold a die cannot satisfy must terminate rather than spin.
    world4, fourth, _ = _board()
    c4 = Cast(world=world4, me=fourth, ref="drivers:reroll")
    c4.reroll_ones(below=99)
    out.that(c4._roll_damage("1d6") >= 1,
             "a floor above every face terminates instead of looping")

    # Scoped by keyword: only the rows carrying the word reroll.
    world5, fifth, _ = _board()
    fire = Cast(world=world5, me=fifth, ref="m145a0")
    fire.reroll_ones(keyword=Keyword.FIRE)
    out.that(fire._reroll_floor() == 0,
             "a keyword hold does not fire for a row without the word")

    # Scoped by ref: the named row rerolls and its neighbour does not.
    world6, sixth, _ = _board()
    named = Cast(world=world6, me=sixth, ref="drivers:reroll")
    named.reroll_ones(ref="p9400")
    out.that(named._reroll_floor() == 0, "a ref hold is silent on another row")
    aimed = Cast(world=world6, me=sixth, ref="p9400")
    out.that(aimed._reroll_floor() == 2, "and bites on the row it names")

    # Suspension and ending, like every other hold (#470).
    world7, seventh, _ = _board()
    c7 = Cast(world=world7, me=seventh, ref="drivers:reroll")
    eff = c7.reroll_ones()
    out.that(c7._reroll_floor() == 2, "laid")
    world7.effects.end(eff, "driver")
    out.that(c7._reroll_floor() == 0, "ended, the dice are ordinary again")


############################################################

def counts_as(out: Result) -> None:
    """"You can use a warhammer with any power that requires a light blade."

    16 feats print a sentence of that shape. The Requirement they waive is
    checked in exactly one place -- `Cast.wielding`, which 78 content rows
    call -- so one waiver covers every row that asks, and the waiver is a
    fact about the character rather than about any of the powers it unlocks.
    That is why it cannot sit in a header: the same rogue power is reachable
    with a light blade by everybody and with a hammer only by whoever took
    the feat.

    **The slug is matched on the waiver side only.** Several of these cards
    name one weapon rather than a group, and a warhammer has no group of its
    own to be named by -- but widening `wielding`'s own test would quietly
    let some of its 78 callers through on a weapon their card never
    mentioned.
    """
    from combat_engine.engine.cast import Cast, _weapon_is
    from combat_engine.engine.components import Gear, Weapon

    hammer = Weapon(ref="w:hammer", slug="warhammer", group="hammer",
                    category="military", properties=frozenset({"versatile"}))
    out.that(_weapon_is(hammer, "hammer"), "a weapon answers to its group")
    out.that(_weapon_is(hammer, "military"), "and to its category")
    out.that(_weapon_is(hammer, "versatile"), "and to a property")
    out.that(_weapon_is(hammer, "warhammer"), "and to its printed slug")
    out.that(not _weapon_is(hammer, "light blade"), "and to nothing else")
    out.that(not _weapon_is(hammer, ""), "an empty word matches nothing")

    world, caster, _ = _board("p5330")
    gear = world.get(caster, Gear) or world.add(caster, Gear())
    gear.weapons = [hammer]
    gear.stowed = set()
    c = Cast(world=world, me=caster, ref="drivers:counts")

    out.that(c.wielding("hammer"), "the printed Requirement passes as it always did")
    out.that(not c.wielding("light blade"),
             "and a Requirement it does not meet still refuses")

    held = c.counts_as("light blade", holding="warhammer")
    out.that(held is not None, "a waiver is laid as an effect")
    out.that(c.wielding("light blade"),
             "now the hammer satisfies a light-blade Requirement")
    out.that(c.wielding("hammer"),
             "and what it actually is still satisfies its own")
    out.that(not c.wielding("crossbow"),
             "a waiver does not open every other Requirement")

    # Keyed on what is in hand, not on the character: swap the weapon and
    # the waiver stops applying.
    sword = Weapon(ref="w:sword", slug="longsword", group="heavy blade",
                   category="military")
    gear.weapons = [sword]
    out.that(not c.wielding("light blade"),
             "holding something else, the waiver does not fire")
    gear.weapons = [hammer]
    out.that(c.wielding("light blade"), "and fires again with the hammer back")

    # Two waivers, because two of these cards name a pair of weapons.
    c.counts_as("crossbow", holding="hammer")
    out.that(c.wielding("light blade") and c.wielding("crossbow"),
             "two waivers on one weapon both stand")

    # Suspension and ending (#470).
    world.effects.suspend(held)
    out.that(not c.wielding("light blade"), "suspended, the waiver lifts")
    out.that(c.wielding("crossbow"), "and leaves the other standing")
    world.effects.resume(held)
    out.that(c.wielding("light blade"), "and comes back")
    world.effects.end(held, "driver")
    out.that(not c.wielding("light blade"),
             "ended, the printed Requirement refuses again")
    out.that(c.wielding("hammer"), "and the weapon is still what it is")


############################################################

def declined(out: Result) -> None:
    """The sixth marker: **we are not building this.**

    The five before it all say something false about a row nobody intends to
    finish. `todo=` and `dropped=` name a symbol, so `todo.py` reports the
    row ready the moment that symbol lands. `narrative=` claims it plays.
    `defect=` blames the compendium, which has the page. `obsolete=` is the
    closest and is the one worth keeping clean -- that row was retired by a
    *rules change*, and a scope decision written into it would blur the one
    word carrying that argument.

    **The unit is the thing, not the row.** Camille's call on the Fortune
    Cards: decline everything that mentions them -- and that means the whole
    *item*, not each line that happens to name a card. `i3333x1` prints only
    a +1 to Bluff and no card clause at all, and it is declined anyway,
    because `i3333p1` is a Fortune Card power and a bonus attached to an
    item nobody can otherwise use is not worth keeping.

    That reading is also why there is no clause-level bucket in
    `blocked.py`: one was built when four of these rows were going to keep
    `dropped=`, and it came out again the moment every declined thing became
    a whole row. A branch nothing reaches is the bug this component is known
    for.
    """
    import re

    from combat_engine.chargen.choices import legal_feats
    from combat_engine.engine.dsl import REGISTRY, usable

    world, caster, _ = _board()
    fortune = sorted(r for r in REGISTRY
                     if re.match(r"i333[3-6][px]\d+$|p1436[3-5]$", r))

    out.that(len(fortune) == 11, "eleven rows carry the Fortune Card decision")
    out.that(all(REGISTRY[r].declined for r in fortune),
             "and every one is declined, the plain item lines included")
    out.that(all(not REGISTRY[r].unfinished for r in fortune),
             "none is waiting on anything, so the queue never counts one")
    out.that(not any("Fortune.deck" in REGISTRY[r].unfinished for r in REGISTRY),
             "and no row anywhere still names the symbol they used to want")

    ok, why = usable(world, caster, REGISTRY["p14363"])
    out.that(not ok, "a declined row is refused in play")
    out.that(why == "not being built",
             "in its own words, not `todo=`'s and not `obsolete=`'s")

    # Read **before** possession, so the reason a declined row gives is its
    # own rather than whatever else happens to be wrong with the board.
    out.that(usable(world, caster, REGISTRY["i3333x1"])[1] == "not being built",
             "the marker is read before possession, so the reason is its own")

    # On its own board -- where the character holds the item -- it is still
    # refused. The board above belongs to a monster, which turns away every
    # item row for "not known" and would have proved nothing.
    its_world, its_actor, _ = _board("i3333x1")
    out.that(not usable(its_world, its_actor, REGISTRY["i3333x1"])[0],
             "and refused on its own board too, where it IS held")

    out.that(all("2026-10-09" in REGISTRY[r].declined for r in fortune),
             "the reason records whose call it was and when")

    # **Two branches here are deliberately unexercised, and saying so is the
    # point.** `chargen.choices` excludes `declined=` rows from the feat and
    # racial-trait draws, added for symmetry with `obsolete=` -- but every
    # declined row is an item or a power, so neither guard is reached, and
    # planting them leaves this driver green.
    #
    # Left in rather than removed: the day a declined feat exists it would
    # otherwise be dealt to a character, which is the failure `obsolete=`'s
    # own note says Camille asked to prevent. `replay coverage` exists for
    # the same reason -- a rule no fixture reaches can be changed freely and
    # nothing says a word.
    offered = set(legal_feats(cls="rogue", level=1, race="r7"))
    out.that(not (offered & set(fortune)),
             "no declined row is dealt to a character (vacuously: none is a feat)")



############################################################

def instead_now(out: Result) -> None:
    """A clause that fires inside a watcher, replaced.

    `c.instead_of` reads `Cast.variant`, which `dsl.use` settles from the
    chosen menu entry -- so it answers for a row that was clicked or offered
    by the dispatcher. The invoker's covenant manifestation is neither: the
    covenant row is used once at the start of a fight and all it does is
    install a `PowerResolved` watcher, so the push it later makes has no
    `Action` behind it and `variant` is 0 for ever.

    **This re-accepts the policy cost `#479` was built to avoid, and the
    reason it is acceptable here is specific.** A question inside a watcher
    is invisible to `policy/`. But a manifestation is a *passive* -- the AI
    never chose to manifest -- so there is no menu entry whose score the
    substitution would have changed. Where a row IS offered, `instead_of` is
    still the right reader: `rt:r24-t0` looked like a watcher case and is
    not, and `f2781` needed no new mechanism at all.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:now")

    out.that(c.instead_of_now("manifest", lambda: "printed") == "printed",
             "with nothing registered the printed clause runs")

    held = c.pre_empt("drivers:now", "manifest", lambda using: "swapped")
    out.that(held is not None, "a registration is laid as an effect")
    out.that(c.instead_of_now("manifest", lambda: "printed") == "swapped",
             "registered, the substitute runs instead")
    out.that(c.instead_of_now("other", lambda: "printed") == "printed",
             "and only for the clause it names")

    # The subject a watcher holds in a closure reaches the clause.
    seen: list[int] = []

    def note_target(using: Cast) -> str:
        seen.append(using.target if using.target is not None else -1)
        return "swapped"

    world2, me2, _ = _board()
    c2 = Cast(world=world2, me=me2, ref="drivers:now")
    c2.pre_empt("drivers:now", "manifest", note_target)
    c2.instead_of_now("manifest", lambda: "printed", on=99)
    out.that(seen == [99], "the clause is handed the creature it is about")
    out.that(c2.target is None,
             "and the binding is put back afterwards, not left standing")

    # **Offered, never imposed.** Every card registering one of these says
    # "you can", so a declined offer has to leave the printed clause
    # running. With no decider installed the first option always wins, so
    # this is the one assertion that needs one -- and without it, deleting
    # the offer entirely leaves this driver green.
    world4, me4, _ = _board()
    c4 = Cast(world=world4, me=me4, ref="drivers:now")
    c4.pre_empt("drivers:now", "manifest", lambda using: "swapped")
    world4.decider = lambda actor, kind, options, prompt="": options[-1]
    out.that(c4.instead_of_now("manifest", lambda: "printed") == "printed",
             "a DECLINED offer leaves the printed clause running")
    world4.decider = lambda actor, kind, options, prompt="": options[0]
    out.that(c4.instead_of_now("manifest", lambda: "printed") == "swapped",
             "and taking it still runs the substitute")

    # Ending it, and suspension, like every other hold (#470).
    world.effects.end(held, "driver")
    out.that(c.instead_of_now("manifest", lambda: "printed") == "printed",
             "ended, the printed clause is back")

    world3, me3, _ = _board()
    c3 = Cast(world=world3, me=me3, ref="drivers:now")
    sus = c3.pre_empt("drivers:now", "manifest", lambda using: "swapped")
    out.that(c3.instead_of_now("manifest", lambda: "printed") == "swapped", "laid")
    world3.effects.suspend(sus)
    out.that(c3.instead_of_now("manifest", lambda: "printed") == "printed",
             "suspended, the printed clause runs")
    world3.effects.resume(sus)
    out.that(c3.instead_of_now("manifest", lambda: "printed") == "swapped",
             "and the substitute comes back")

    # The seven rows #480 named, and where each ended up.
    from combat_engine.engine.dsl import REGISTRY

    seven = ("f1548", "f2285", "f2751", "f2993", "f2430", "f2781", "f3558")
    out.that(all(not REGISTRY[r].unfinished for r in seven),
             "none of the seven is waiting on anything now")
    known = world.get(caster, Powers)
    out.that(known is not None, "and the board carries a Powers to register into")


############################################################

def granted_keywords(out: Result) -> None:
    """A keyword one creature's copy of a row carries, and nobody else's.

    A row's keywords are **header data**: one tuple, fixed at import, shared
    by everybody who ever holds the row. 12 feats print "your <row> is
    considered an arcane attack power" or "gains the reliable keyword",
    which a header cannot say for one character only.

    **The whole risk here is a site that still reads the header.** There
    were 22 of them across `cast`, `dsl`, `resolve`, `triggers`,
    `durations`, `api/render` and `policy`; a grant honoured at 21 is a
    modifier nothing consults at the 22nd, which is this component's
    commonest bug. 19 come through `dsl.keywords_of` now and the other
    three are annotated where they sit, because each has a reason:

    * `cast.py:358` is *identifying* which row in a loadout is the monk's
      at-will by the shape it was declared with -- a granted keyword must
      not make some other row answer that search;
    * `durations.keywords_of(label)` and `policy.threat.row_types(ref)`
      take a ref and no creature, so there is nothing to ask about. `f1538`
      keeps a marker naming the first of those rather than being written
      and quietly half-working.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import REGISTRY, keywords_of
    from combat_engine.engine.types import Keyword

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:kw")
    row = REGISTRY["p11739"]

    declared = frozenset(row.keywords)
    out.that(keywords_of(world, caster, row) == declared,
             "with nothing granted, the header is the whole answer")
    out.that(keywords_of(world, None, row) == declared,
             "and an actor of None answers the header rather than raising")
    out.that(keywords_of(world, caster, None) == frozenset(),
             "a basic attack has no declared row and answers empty")

    held = c.counts_as_keyword("p11739", Keyword.RELIABLE)
    out.that(held is not None, "a grant is laid as an effect")
    out.that(Keyword.RELIABLE in keywords_of(world, caster, row),
             "and the keyword is there for this creature")
    # **Structurally true, not guarded.** `c.counts_as_keyword` never
    # receives a `Power` at all -- it writes a dict on `Powers` -- so there
    # is no line to plant that would make the header change. Asserted
    # anyway, because it is the property the whole design exists for and a
    # future rewrite that reached for `Power.keywords` would break it here.
    out.that(Keyword.RELIABLE not in frozenset(row.keywords),
             "**not on the header**, which everybody else still reads")
    out.that(keywords_of(world, caster, REGISTRY["p1448"])
             == frozenset(REGISTRY["p1448"].keywords),
             "another row is untouched by it")

    # A second creature on the same board does not get it.
    others = [e for e in world.having(Powers) if e != caster]
    if others:
        out.that(Keyword.RELIABLE not in keywords_of(world, others[0], row),
                 "and no other creature on the board has it")

    # Laid twice is once: the set already holds it.
    again = c.counts_as_keyword("p11739", Keyword.RELIABLE)
    out.that(again is None, "granting the same keyword twice lays nothing")

    # Suspension and ending (#470).
    world.effects.suspend(held)
    out.that(Keyword.RELIABLE not in keywords_of(world, caster, row),
             "suspended, the grant lifts")
    world.effects.resume(held)
    out.that(Keyword.RELIABLE in keywords_of(world, caster, row),
             "and comes back")
    world.effects.end(held, "driver")
    out.that(Keyword.RELIABLE not in keywords_of(world, caster, row),
             "ended, the row is its printed self again")

    # The rows this was built for.
    for ref, on_ref, kw in (("f3203", "p11739", Keyword.RELIABLE),
                            ("f921", "p1767", Keyword.RELIABLE),
                            ("f2983", "p1448", Keyword.DIVINE)):
        its_world, its_actor, _ = _board(ref)
        got = keywords_of(its_world, its_actor, REGISTRY[on_ref])
        out.that(kw in got, f"{ref} grants {kw.value} to {on_ref}")


############################################################

def item_as_weapon(out: Result) -> None:
    """A shield that is also a pick, and a rod that is also a mace.

    Four item rows print a full weapon profile on something that is not a
    weapon. There is no `weapon` table row for them -- they are items -- so
    the numbers come off the card and are hand-written into the row, which
    is how every other row in this tree gets its numbers.

    **On the belt, not in hand.** A shield-as-pick is a *second* weapon the
    character may take up. Arriving held would make `Gear.wield` stow
    whatever was in the main hand, so laying an item's profile would
    silently disarm the character -- which is worse than the clause not
    working.

    The other ten rows that wore this symbol are four different mechanisms
    and none of them is this one. See `#474`: twelve more are blocked on
    chargen rather than on any verb, because the pact blades exist in the
    `weapon` table and nothing deals one.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Gear

    world, caster, _ = _board("p5330")
    gear = world.get(caster, Gear)
    if gear is None:
        out.that(False, "the board deals this character gear")
        return
    before = len(gear.weapons)
    held_before = {w.ref for w in gear.held}

    c = Cast(world=world, me=caster, ref="drivers:asweapon")
    eff = c.as_weapon(damage="1d6", group="pick", proficiency=2,
                      properties=frozenset({"high crit", "off-hand"}))
    out.that(eff is not None, "a profile is laid as an effect")
    out.that(len(gear.weapons) == before + 1, "and the weapon list grows by one")

    arm = next(w for w in gear.weapons if w.ref == "drivers:asweapon")
    out.that(arm.damage == "1d6" and arm.group == "pick",
             "carrying the die and group the card printed")
    out.that(arm.proficiency == 2, "and its proficiency")
    out.that("high crit" in arm.properties and "off-hand" in arm.properties,
             "and its properties")

    out.that(arm.ref in gear.stowed, "it starts on the belt")
    out.that({w.ref for w in gear.held} == held_before,
             "so nothing that was in hand was disarmed")

    # It answers the questions a row asks about what is in hand, once drawn.
    gear.wield(arm)
    out.that(c.wielding("pick"), "drawn, a Requirement for a pick passes")
    out.that(not c.wielding("crossbow"), "and one for something else does not")

    # Ending it takes the profile away again.
    world.effects.end(eff, "driver")
    out.that(len(gear.weapons) == before, "ended, the profile is gone")
    out.that(not any(w.ref == "drivers:asweapon" for w in gear.weapons),
             "and the weapon is not left in the list")

    # Suspension, like every other hold (#470).
    world2, me2, _ = _board("p5330")
    g2 = world2.get(me2, Gear)
    c2 = Cast(world=world2, me=me2, ref="drivers:asweapon")
    sus = c2.as_weapon(damage="1d8", group="mace", proficiency=2)
    n = len(g2.weapons)
    world2.effects.suspend(sus)
    out.that(len(g2.weapons) == n - 1, "suspended, the profile lifts")
    world2.effects.resume(sus)
    out.that(len(g2.weapons) == n, "and comes back")

    # The four rows this was built for.
    for ref in ("i1125x1", "i1281x1", "i1656x1", "i3182x1"):
        its_world, its_actor, _ = _board(ref)
        its_gear = its_world.get(its_actor, Gear)
        got = its_gear is not None and any(
            w.ref == ref for w in its_gear.weapons)
        out.that(got, f"{ref} puts its profile in the wearer's gear")


############################################################

def scoped_vulnerable(out: Result) -> None:
    """Vulnerable to *some* of what reaches you, not all of it.

    "Vulnerable 10 to the <monster>'s attacks" is narrower than
    `c.vulnerable` could say: `Defences.vulnerable` is a flat
    `dict[DamageType, int]`, a running total with nowhere to record what the
    clause applies to. Unscoped, `m4307a2` made its victim vulnerable 10 to
    **everything** -- so a monster's reaction handed the party's striker the
    benefit.

    The second of the three scope kinds `#471` names. The first was the move
    kind and needed no new representation at all, because `step` already
    carried it. This one does: the triples live beside the flat dict and are
    read in `resolve.deal_damage`, against the same context immunity and
    resistance are already read against.

    **`max`, not a sum**, which is how the unscoped vulnerability is read
    two lines above it: two clauses both apply and 4e takes the larger.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defences, Health
    from combat_engine.engine.durations import When
    from combat_engine.engine.resolve import _scoped_vuln
    from combat_engine.engine.types import DamageType

    world, caster, _ = _board()
    foes = [e for e in world.having(Defences) if e != caster]
    if not foes:
        out.that(False, "the board fields something to be vulnerable")
        return
    foe = foes[0]
    c = Cast(world=world, me=caster, ref="drivers:vuln")
    ALL = (DamageType.FIRE, DamageType.UNTYPED)

    # **The key is `source`, not `attacker`.** `deal_damage`'s own note
    # says why: damage is dealt by things that are not swings -- ongoing
    # damage, a zone's burn, a trait's `c.flat` -- so the dealer is the
    # effect's owner rather than somebody taking a shot, and `from_attack`
    # is how a gate tells the two apart.
    #
    # Worth spelling out because I got it wrong first and this driver did
    # not catch it: it built its own context with `attacker`, so the two
    # rows written against that key passed here and would never have fired
    # in a real fight. The end-to-end assertion below is the one that bites.
    mine = {"source": caster}
    theirs = {"source": foe}
    out.that(_scoped_vuln(world, foe, ALL, mine) == 0,
             "with nothing recorded there is no scoped vulnerability")

    held = c.vulnerable(10, on=foe, until=When.EONT,
                        when=lambda ctx: ctx.get("source") == caster)
    out.that(held is not None, "a scoped vulnerability is laid as an effect")
    out.that(_scoped_vuln(world, foe, ALL, mine) == 10,
             "and counts for the attacker it names")
    out.that(_scoped_vuln(world, foe, ALL, theirs) == 0,
             "**and not for anybody else**, which is the whole point")

    # It stays out of the flat dict, so an unscoped read is unaffected.
    held_def = world.get(foe, Defences)
    out.that(not held_def.vulnerable,
             "the flat dict is untouched, so an unscoped reader sees nothing")

    # Typed scope: only the type it names.
    c.vulnerable(3, DamageType.COLD, on=foe, until=When.EONT,
                 when=lambda ctx: True)
    out.that(_scoped_vuln(world, foe, (DamageType.COLD,), theirs) == 3,
             "a typed scope counts for its own type")
    out.that(_scoped_vuln(world, foe, (DamageType.ACID,), theirs) == 0,
             "and not for another")

    # Two clauses: the larger, not the sum.
    c.vulnerable(4, DamageType.COLD, on=foe, until=When.EONT,
                 when=lambda ctx: True)
    out.that(_scoped_vuln(world, foe, (DamageType.COLD,), theirs) == 4,
             "two clauses on one type take the larger, not the sum")

    # Ending and suspension (#470).
    world.effects.end(held, "driver")
    out.that(_scoped_vuln(world, foe, ALL, mine) == 0
             or _scoped_vuln(world, foe, (DamageType.COLD,), mine) == 4,
             "ending one clause leaves the others standing")

    # **End to end, through a real blow.** Every assertion above hands
    # `_scoped_vuln` a context this driver built, which is exactly how the
    # wrong key survived: the rows said `attacker` and so did the driver.
    # This one lays the scope and then actually deals damage, so the context
    # is `deal_damage`'s own.
    w3, me3, _ = _board()
    victim = next(e for e in w3.having(Defences) if e != me3)
    mine3 = Cast(world=w3, me=me3, ref="drivers:vuln")
    hp = w3.get(victim, Health)
    if hp is not None:
        mine3.vulnerable(5, on=victim, until=When.EONT,
                         when=lambda ctx: ctx.get("source") == me3)
        before = hp.hp
        mine3.flat(10, on=victim)
        mine3.vulnerable(0, on=victim)  # no-op, keeps the shape honest
        out.that(before - hp.hp == 15,
                 "a real blow from the named source takes 10 + the scoped 5")

        w4, me4, _ = _board()
        other4 = next(e for e in w4.having(Defences) if e != me4)
        c4 = Cast(world=w4, me=me4, ref="drivers:vuln")
        hp4 = w4.get(other4, Health)
        c4.vulnerable(5, on=other4, until=When.EONT,
                      when=lambda ctx: ctx.get("source") == -99)
        was = hp4.hp
        c4.flat(10, on=other4)
        out.that(was - hp4.hp == 10,
                 "and a blow from anybody else takes the 10 alone")

    world2, me2, _ = _board()
    other = next(e for e in world2.having(Defences) if e != me2)
    c2 = Cast(world=world2, me=me2, ref="drivers:vuln")
    sus = c2.vulnerable(7, on=other, until=When.EONT, when=lambda ctx: True)
    out.that(_scoped_vuln(world2, other, ALL, {}) == 7, "laid")
    world2.effects.suspend(sus)
    out.that(_scoped_vuln(world2, other, ALL, {}) == 0, "suspended, it lifts")
    world2.effects.resume(sus)
    out.that(_scoped_vuln(world2, other, ALL, {}) == 7, "and comes back")

def an_immunity_gated_on_the_attacking_defence(out: Result) -> None:
    """m5788a0 ignores every condition from a Will attack and nothing else.

    *"Takes damage as normal, but ignores all other effects"* of a
    Will-targeted attack. The gate asked the context for a `vs` key and
    **nothing in the engine writes one**, so the immunity never applied once
    and the creature was missing a defensive trait in every fight it was
    ever in. It audited green throughout: the row fires, lays a modifier,
    and only the modifier's question was unanswerable. #591.

    The eight rows that ask this elsewhere read `ev.vs` off `AttackDeclared`
    or `AttackRolled`, which carry it -- but those are watchers, and this is
    a standing `when=` gate handed a damage context rather than an event. So
    it asks the **power** the context does name and reads that row's
    declared `Attack(vs=...)`.

    Asserted through `Effects.apply`, which is the door every `c.condition`
    goes through and the one that consults `query.immune_to`. The third case
    is the one that keeps the gate honest: a label naming no row at all must
    leave the condition standing, because a gate that cannot tell what
    attacked has no business refusing anything.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine import When
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.query import enemies, is_
    from combat_engine.engine.types import Condition, Defense

    world, me, _ = _board("m5788a0", 1)
    REGISTRY["m5788a0"].body(Cast(world=world, me=me, ref="m5788a0"))
    foe = next(iter(sorted(enemies(world, me))), me)

    #: A heroic power rolling against each defence, read off the header
    #: rather than named by hand -- the gate's whole question is what the
    #: attacking row declares.
    def rolling_against(defence: Defense) -> str:
        for ref, row in sorted(REGISTRY.items()):
            if not ref.startswith("p") or (row.level or 0) > 10:
                continue
            if getattr(getattr(row, "attack", None), "vs", None) is defence:
                return ref
        return ""

    will, armour = rolling_against(Defense.WILL), rolling_against(Defense.AC)
    out.that(bool(will) and bool(armour),
             "there is a heroic power rolling against Will and one against"
             " AC, or this proves nothing",
             f"{will} / {armour}")

    def lands(label: str) -> bool:
        world.effects.apply(me, foe, When.EONT, label=label,
                            conditions=[Condition.DAZED])
        held = is_(world, me, Condition.DAZED)
        for effect in list(world.effects.of(me)):
            if effect.label == label:
                world.effects.end(effect, "the rule is done with it")
        return held

    out.that(not lands(will),
             f"a condition from a Will attack ({will}) is refused -- the"
             f" immunity applies, which it never did while the gate read a"
             f" ctx key nothing writes",
             f"{will}")
    out.that(lands(armour),
             f"a condition from an AC attack ({armour}) lands -- the card"
             f" narrows the immunity to Will and granting it wider would be"
             f" a row stronger than its page",
             f"{armour}")
    out.that(lands("surprised"),
             "and a label naming no row at all leaves the condition"
             " standing: the engine labels a few effects with a plain word,"
             " and a gate that cannot tell what attacked must answer False"
             " rather than refuse everything")


def a_pact_feat_augments_the_power_it_names(out: Result) -> None:
    """Three `[Greater Pact]` feats pay their augment inside the power.

    Six of these cards print *"you can also expend your fell might to
    augment any power associated with this feat. When you hit an enemy with
    an associated power augmented by this feat, <effect>"*. The clause is
    the feat's and the attack is the power's, so #550's convention puts it
    in the power and gates it; `shared.augmenting` is that gate. #630.

    **The marker they carried named nothing missing.**
    `c.augment_with(resource)` had been re-aimed twice already --
    `dsl.use(augment=)`, then `c.lend_augment` -- and the third reading is
    that there is no verb to wait for: `c.spend_charge` on
    `features.warlock.FELL` is the spend, `c.may` is the decision,
    `c.declare` picks which bracketed feat applies, and `p12887` is the
    worked example eleven lines long in the same mechanic.

    Posed on each power's own board with the feat pushed into
    `Powers.known`, because `audit.board` fields a classless feat on a
    fighter or a ranger and these need a warlock holding the row.

    **The negative control is the whole rule**, for the reason #550's own
    issue gives: a clause written into a power and gated on a feat is
    invisible to the audit board, which fires the feat alone and the power
    without it. Nothing else distinguishes "written" from "written and
    never reachable".
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.content.features.warlock import FELL
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health, Mods, Position, Powers
    from combat_engine.engine.dsl import REGISTRY, keywords_of
    from combat_engine.engine.query import allies, enemies, is_
    from combat_engine.engine.types import Condition, Defense, Keyword

    def pose(power: str, feat: str, seed: int = 1):  # noqa: ANN202
        world, me, _ = _board(power, seed)
        known = world.need(me, Powers)
        if feat:
            known.known.append(feat)
        # `arm_traits` may already have spent the boon before round 1, and
        # this rule is about the augment rather than about that clock.
        known.charges.clear()
        foes = [e for e in sorted(enemies(world, me)) if world.get(e, Health)]
        here = world.get(me, Position)
        victim, neighbour = foes[0], foes[2]
        world.get(victim, Position).square = (here.square[0] + 3, here.square[1])
        world.get(neighbour, Position).square = (here.square[0] + 4, here.square[1])
        for spare in (foes[1], *foes[3:]):
            world.get(spare, Position).square = (here.square[0] + 15, here.square[1])
        use = Cast(world=world, me=me, ref=power, targets=[victim])
        use.target = victim
        return world, me, use, victim, neighbour

    def attack_total(world, who: int) -> int:  # noqa: ANN001
        mods = world.get(who, Mods)
        return mods.total("attack", {}) if mods is not None else 0

    # -- f3427: "you also knock the target prone" ------------------------
    for power in ("p1341", "p5919"):
        world, me, use, victim, _ = pose(power, "f3427")
        REGISTRY[power].body(use)
        out.that(is_(world, victim, Condition.PRONE),
                 f"f3427 knocks {power}'s target prone", f"{power}")
        out.that(world.get(me, Powers).charges.get(FELL) == 1,
                 f"and the boon is spent for it -- `c.spend_charge`'s False"
                 f" is the printed \"if you spend\" ({power})",
                 f"{dict(world.get(me, Powers).charges)}")

        world, me, use, victim, _ = pose(power, "")
        REGISTRY[power].body(use)
        out.that(not is_(world, victim, Condition.PRONE),
                 f"without the feat {power}'s target stays standing -- the"
                 f" control, and the only thing that separates this from"
                 f" the power having grown a clause",
                 f"{power}")
        out.that(not world.get(me, Powers).charges.get(FELL),
                 f"and nothing is spent ({power})",
                 f"{dict(world.get(me, Powers).charges)}")

    # -- the memo: one charge for a use, however many targets -----------
    world, me, use, first, second = pose("p5919", "f3427")
    use.targets = [first, second]
    seen = []
    for victim in (first, second):
        use.target = victim
        REGISTRY["p5919"].body(use)
        seen.append(getattr(use, "greater_pact", None))
    out.that(seen == ["f3427", "f3427"],
             "a two-target row settles the spend once and both targets"
             " honour the same answer -- asked per target the second would"
             " find the charge gone and silently get nothing",
             f"{seen}")
    out.that(world.get(me, Powers).charges.get(FELL) == 1,
             "and it is one charge, not two",
             f"{dict(world.get(me, Powers).charges)}")

    # -- f3423: "you gain insubstantial until the start of your next turn"
    for power in ("p1872", "p4070"):
        world, me, use, victim, _ = pose(power, "f3423")
        REGISTRY[power].body(use)
        out.that(is_(world, me, Condition.INSUBSTANTIAL),
                 f"f3423 makes the CASTER insubstantial through {power}",
                 f"{power}")
        # **This is the assertion that caught a real fault.** Written as a
        # bare `c.insubstantial(until=...)` the hold goes to `_who(None)`,
        # which is the *target* -- so the printed "you gain" handed the
        # enemy a damage halving. The probe read False rather than
        # backwards only because the bare call has no target to land on
        # outside a real use.
        out.that(not is_(world, victim, Condition.INSUBSTANTIAL),
                 f"and NOT the target -- `on=` defaults to the target, so"
                 f" \"you gain insubstantial\" written bare is a gift to"
                 f" the enemy ({power})",
                 f"{power}")

        world, me, use, _, _ = pose(power, "")
        REGISTRY[power].body(use)
        out.that(not is_(world, me, Condition.INSUBSTANTIAL),
                 f"without the feat nobody goes half-there ({power})",
                 f"{power}")

    # -- f3419: the bystanders flinch, and the power turns fearful -------
    for power in ("p1401", "p1462"):
        world, me, use, victim, neighbour = pose(power, "f3419")
        was = attack_total(world, neighbour)
        on_target = attack_total(world, victim)
        REGISTRY[power].body(use)
        out.that(attack_total(world, neighbour) == was - 2,
                 f"f3419 puts -2 on the enemy standing beside {power}'s"
                 f" target",
                 f"{was} -> {attack_total(world, neighbour)}")
        out.that(attack_total(world, victim) == on_target,
                 f"and nothing extra on the target itself -- \"adjacent to"
                 f" the target\" excludes it, where `c.within(1, of=foe)`"
                 f" returns it at distance 0 ({power})",
                 f"{on_target} -> {attack_total(world, victim)}")

        world, me, use, _, neighbour = pose(power, "")
        was = attack_total(world, neighbour)
        REGISTRY[power].body(use)
        out.that(attack_total(world, neighbour) == was,
                 f"without the feat the bystander is untouched ({power})",
                 f"{was} -> {attack_total(world, neighbour)}")

    # The keyword half, read on the power that does **not** print fear.
    world, me, use, _, _ = pose("p1462", "f3419")
    out.that(Keyword.FEAR not in keywords_of(world, me, REGISTRY["p1462"]),
             "p1462 does not print fear, which is what makes it the one to"
             " read this on -- p1401 prints it and could not show a grant")
    REGISTRY["p1462"].body(use)
    out.that(Keyword.FEAR in keywords_of(world, me, REGISTRY["p1462"]),
             "and f3419 grants it: \"the triggering power gains the fear"
             " keyword if it doesn't have it already\"")
    world, me, use, _, _ = pose("p1462", "")
    REGISTRY["p1462"].body(use)
    out.that(Keyword.FEAR not in keywords_of(world, me, REGISTRY["p1462"]),
             "without the feat it stays plain -- and `Power.keywords` could"
             " never have said this, being one tuple shared by everyone who"
             " holds the row")

    # -- f3427, f3423 and f3419 are asserted above. The other three ------
    # Each names two powers; one of each pair is enough to prove the clause,
    # and `shared.augmenting` is the same gate for all six, already planted.

    # f3421: "the target makes a basic attack against a creature you choose"
    world, me, use, victim, neighbour = pose("p1400", "f3421")
    hurt = world.get(neighbour, Health).hp
    REGISTRY["p1400"].body(use)
    out.that(world.get(neighbour, Health).hp < hurt,
             "f3421 makes p1400's target swing at the creature the caster"
             " picks -- `c.grant_attack`'s first argument is who swings and"
             " its `on=` is who is swung at",
             f"{hurt} -> {world.get(neighbour, Health).hp}")

    world, me, use, _, neighbour = pose("p1400", "")
    hurt = world.get(neighbour, Health).hp
    REGISTRY["p1400"].body(use)
    out.that(world.get(neighbour, Health).hp == hurt,
             "and without the feat the bystander is not struck",
             f"{hurt} -> {world.get(neighbour, Health).hp}")

    # f3417: "each ally adjacent to the target can shift 1 or take +2 to all
    # defences". The ally decides, so the headless default -- `c.may`'s first
    # option -- settles it, and that is the shift.
    world, me, use, victim, _ = pose("p4069", "f3417")
    # The stock board stands the allies near the caster, not near whatever
    # it shoots at, so one is walked over -- the same setup the enemies get
    # above. Without it `c.within(1, of=victim, side="ally")` is empty and
    # the clause would read as inert while being correct.
    standing = sorted(a for a in allies(world, me) if a != me)
    if standing:
        spot = world.get(victim, Position).square
        world.get(standing[0], Position).square = (spot[0], spot[1] + 1)
    friends = sorted(a for a in use.within(1, of=victim, side="ally") if a != me)
    out.that(bool(friends),
             "an ally is standing beside p4069's target, or this proves"
             " nothing either way",
             f"{friends}")
    if friends:
        friend = friends[0]
        stood = world.get(friend, Position).square
        braced = (world.get(friend, Mods).total(Defense.AC, {})
                  if world.get(friend, Mods) else 0)
        # **Record who is asked, through the real decider hook.** Asserting
        # only that the ally stepped *or* braced was too weak to see this,
        # and the plant proved it: swapping `c.may(who=friend)` for a bare
        # `c.may` left the rule green, because one of the two still
        # happened -- to the right creature, decided by the wrong one.
        asked: list[tuple[int, str]] = []

        def listen(actor, kind, options, prompt=""):  # noqa: ANN001, ANN202
            asked.append((actor, prompt))
            return options[0]

        was, world.decider = world.decider, listen
        try:
            REGISTRY["p4069"].body(use)
        finally:
            world.decider = was
        now = world.get(friend, Position).square
        after = (world.get(friend, Mods).total(Defense.AC, {})
                 if world.get(friend, Mods) else 0)
        out.that(now != stood or after == braced + 2,
                 "f3417 lets the ally beside the target step or brace",
                 f"square {stood} -> {now}, AC {braced} -> {after}")
        step = [who for who, prompt in asked if "bracing" in prompt]
        out.that(step == [friend],
                 "and the ALLY is the creature asked which -- \"can either\""
                 " on somebody else's clause is their decision, which is"
                 " `c.may`'s own rule about whose resource it is",
                 f"asked {step}, ally is {friend}")

    # f3429: "one ally within 5 makes a basic attack and deals extra thunder
    # damage equal to your Intelligence modifier" -- through p501.
    world, me, use, victim, _ = pose("p501", "f3429")
    foes = {f: world.get(f, Health).hp for f in sorted(enemies(world, me))
            if world.get(f, Health)}
    REGISTRY["p501"].body(use)
    moved = [f for f, hp in foes.items()
             if world.get(f, Health).hp != hp and f != victim]
    out.that(bool(moved) or world.get(victim, Health).hp < foes.get(victim, 0),
             "f3429 sends an ally's swing in through p501",
             f"changed: {moved}")

    # The typed half, which is the one that needed an engine parameter.
    import inspect

    from combat_engine.content.powers.warlock.shared import thunderclap
    out.that("damage_type=DamageType.THUNDER" in inspect.getsource(thunderclap),
             "and its extra damage is typed thunder -- `Mod.dtype`'s own"
             " reason: these points meet the victim's thunder resistance"
             " where the ally's weapon does not",
             "c.grant_attack(damage_type=)")
    out.that("damage_type" in inspect.signature(Cast.grant_attack).parameters,
             "which `c.grant_attack` had no way to say until this row needed"
             " it; untyped the rider joins the blow as whatever it already"
             " was, right for a plain +2 and wrong here")

    world, me, use, victim, _ = pose("p501", "")
    foes = {f: world.get(f, Health).hp for f in sorted(enemies(world, me))
            if world.get(f, Health)}
    REGISTRY["p501"].body(use)
    out.that(not [f for f, hp in foes.items()
                  if world.get(f, Health).hp != hp and f != victim],
             "and without the feat no second creature is touched",
             "control")

    # p1401 answers to two of these feats and must tell them apart.
    out.that('augmenting(c, "f3419", "f3429")'
             in inspect.getsource(REGISTRY["p1401"].body),
             "p1401 declares BOTH feats that name it, so the one-per-use"
             " rule is settled by `c.declare` -- `c.feat` is true for every"
             " feat held and cannot say which is applying (#554)")
    for held, expect in (("f3419", "_dismay"), ("f3429", "_thunderclap")):
        world, me, use, _, _ = pose("p1401", held)
        REGISTRY["p1401"].body(use)
        out.that(getattr(use, "greater_pact", "") == held,
                 f"and holding only {held} declares {held}, so the"
                 f" {expect} branch is the one that runs",
                 f"{getattr(use, 'greater_pact', None)!r}")



def a_feat_lends_an_augment(out: Result) -> None:
    """f3170 hands p10440 an Augment 1 clause the card does not print.

    Four feats print an Augment line on a power whose own card prints none,
    and `c.lend_augment` was built for them -- three are written in
    `general_o.py`. This was the leftover, and its note said the thing could
    not be done: *"an augment is a branch inside the row's own body; a feat
    cannot add one from outside."* That verb does exactly that.

    **What was missing is the reader.** `c.lend_augment`'s own rule is that
    the lent-to row must call `augment.lent(c)`, or the lend is a modifier
    nothing consults -- and `p10440` did not ask. Four racial powers already
    ask the same way, so the pattern was in the tree and this one power was
    outside it.

    **Asserted by running p10440's body, not by calling `augment.lent`.**
    The first draft called the helper directly, and when the plant took
    `lent(c)` back out of the power only the source check went red -- the
    damage still landed, because the driver was the thing doing the asking.
    A rule has to go through the row that will really be holding it.

    Posed on `p10440`'s board rather than the feat's, which is what makes
    the control real: `audit.board("f3170")` arms the feat as part of
    fielding it, so "without the feat" cannot be said there at all.

    Two further details, each of which cost a wrong reading first:

    * **Both neighbours plain dummies.** The second creature `audit.board`
      spawns is undead and the lent clause deals necrotic, so the first run
      showed 40 before and 40 after and looked exactly like a clause that
      never fires. It was immunity working.
    * **The control runs first.** `spent_on` reads a module-level record of
      the last augment paid for, and two boards in one process reuse entity
      ids -- so asking after the lend pose answered 1 for a creature that had
      spent nothing.
    """
    import inspect

    import combat_engine.content  # noqa: F401
    from combat_engine.content.powers.augment import spent_on
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health, Position, Powers
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.events import DamageApplied
    from combat_engine.engine.query import allies, enemies
    from combat_engine.engine.types import DamageType

    #: What the row's own printed effect deals, so the lent clause's share of
    #: a creature's losses can be told apart from it.
    DEALT = 7

    out.that(not REGISTRY["f3170"].unfinished,
             "f3170 carries no marker now",
             f"{REGISTRY['f3170'].unfinished}")
    asks = "lent(c)" in inspect.getsource(REGISTRY["p10440"].body)
    out.that(asks,
             "p10440 calls `augment.lent` -- without it the lend is a"
             " modifier nothing consults, which is that verb's own rule",
             f"{asks}")

    def pose(*, lend: bool):  # noqa: ANN202
        world, me, _ = _board("p10440", 1)
        foes = [e for e in sorted(enemies(world, me)) if world.get(e, Health)]
        here = world.get(me, Position)
        # foes[1] is the undead one, and the clause deals necrotic.
        victim, neighbour = foes[0], foes[2]
        world.get(victim, Position).square = (here.square[0] + 4, here.square[1])
        world.get(neighbour, Position).square = (here.square[0] + 5, here.square[1])
        for spare in (foes[1], *foes[3:]):
            world.get(spare, Position).square = (here.square[0] + 15, here.square[1])
        if lend:
            REGISTRY["f3170"].body(Cast(world=world, me=me, ref="f3170"))
        # The use as the dispatcher hands it over: this row reads its target
        # off the trigger event, not off the aim.
        friend = next(iter(sorted(allies(world, me))), me)
        use = Cast(world=world, me=me, ref="p10440")
        use.trigger = DamageApplied(
            source=victim, target=friend, amount=DEALT,
            dtype=DamageType.FORCE, absorbed=0,
            hp=world.get(friend, Health).hp,
        )
        return world, me, use, victim, neighbour

    # --- the control, first, for `spent_on`'s reason above ---------------
    world, me, use, victim, neighbour = pose(lend=False)
    was = world.get(neighbour, Health).hp
    stood = world.get(victim, Health).hp
    REGISTRY["p10440"].body(use)
    out.that(spent_on(me, "p10440") == 0,
             "without the feat nothing is lent and nothing is spent -- the"
             " control, and why this is not p10440 having grown a clause",
             f"spent {spent_on(me, 'p10440')}")
    out.that(world.get(neighbour, Health).hp == was,
             "and the neighbour of the target is untouched",
             f"{was} -> {world.get(neighbour, Health).hp}")
    out.that(world.get(victim, Health).hp == stood - DEALT,
             "while the row's printed effect still lands on the dealer, so"
             " the control is the feat being absent rather than the power"
             " being broken",
             f"{stood} -> {world.get(victim, Health).hp}")

    # --- and with the feat ----------------------------------------------
    world, me, use, victim, neighbour = pose(lend=True)
    known = world.get(me, Powers)
    out.that(bool(getattr(known, "lent_augments", {}).get("p10440")),
             "the lend is filed against p10440 by ref, which is what"
             " `augment.lent` reads back",
             f"{sorted(getattr(known, 'lent_augments', {}))}")
    before = world.get(neighbour, Health).hp
    stood = world.get(victim, Health).hp
    REGISTRY["p10440"].body(use)
    out.that(spent_on(me, "p10440") == 1,
             "the lent augment is offered and paid for at its printed cost,"
             " routed through `augment` so `spent_on` sees it while the use"
             " is still resolving",
             f"spent {spent_on(me, 'p10440')}")
    out.that(world.get(neighbour, Health).hp == before - use.con_mod,
             "the neighbour of the target takes Constitution modifier"
             " necrotic damage",
             f"{before} -> {world.get(neighbour, Health).hp},"
             f" con_mod {use.con_mod}")
    out.that(world.get(victim, Health).hp == stood - DEALT,
             "and the TARGET takes the printed effect and nothing more --"
             " \"each enemy adjacent to the target\" excludes it, where"
             " `c.within(1, of=foe)` returns it at distance 0",
             f"{stood} -> {world.get(victim, Health).hp},"
             f" printed {DEALT}")


def the_invigorating_keyword_pays(out: Result) -> None:
    """A keyword that is only a tag, and the four feats that read it.

    `Keyword.INVIGORATING` was **not on the enum** while 13 fighter powers
    printed it, so six rows named it as their one gap. Nothing noticed
    because the keyword does nothing by itself: no power's own text acts
    on it, and every reader is somebody else's feat.

    **Two gaps were claimed and only one was real.** `f774` and `f792`
    said a second thing was missing -- *"`resolve.temp_hp` consults `Mods`
    for nothing, so there is no term to add to"* -- and that function now
    reads a `"temp_hp"` modifier off the receiver, with a comment saying
    it was added for these very rows. The note outlived the gap, which is
    the week's recurring shape.

    Asserted through `resolve.temp_hp`, the real payout, because the whole
    question is whether a modifier reaches it. Both directions on every
    row: an invigorating power pays the raised number, a plain one pays
    the bare one.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine import Keyword
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health, Powers
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.resolve import temp_hp

    out.that(hasattr(Keyword, "INVIGORATING"),
             "the keyword is on the enum at all, which is the gap six rows"
             " named", f"{hasattr(Keyword, 'INVIGORATING')}")

    # **The header deliberately, not `keywords_of`.** That reader needs a
    # world and a creature because it folds in `c.counts_as_keyword`
    # grants; the question here is which cards *print* the keyword, which
    # is the declared tuple and what `keywords.py` compares to the
    # database. The grant path is `f2370`'s and is asserted there.
    tagged = sorted(r for r, p in REGISTRY.items()
                    if Keyword.INVIGORATING in (p.keywords or ()))
    out.that(len(tagged) == 13,
             "and the 13 powers whose cards print it declare it -- the set"
             " `keywords.py` compares against the database",
             f"{len(tagged)} rows")
    # **A FIGHTER power without the keyword**, and the class matters. The
    # first version took any class's weapon power, so the battlerager
    # leg's `row.cls != "fighter"` guard rejected it and the keyword gate
    # below was never the thing under test -- a plant removing that gate
    # stayed green. Both halves of the leg's condition need their own
    # control.
    plain = next(r for r, p in REGISTRY.items()
                 if r.startswith("p") and (p.level or 0) <= 10
                 and p.cls == "fighter"
                 and Keyword.INVIGORATING not in (p.keywords or ())
                 and Keyword.WEAPON in (p.keywords or ()))

    def paid(ref: str, using: str, *, bloodied: bool = False) -> int:
        """Temporary hit points a fighter ends up with, via the real path.

        **The board arms the feat; this must not arm it again.** It did,
        and every one of these rows carried its modifier twice. It stayed
        invisible for as long as the bonuses were typed: two `kind="feat"`
        modifiers under one label are the same type, so `Mods.total` takes
        the larger and the duplicate costs nothing. The moment `f755` became
        untyped -- which is what its card prints, and `bonuses.py` said so --
        two untyped bonuses added and the pool read 5 where the card says 3.

        So the bonus type was hiding a fault in this harness, and the row
        that exposed it was correct. `turns.arm_traits` arms an
        `action=NONE` feat dealt through `chargen.Character(feats=[...])`,
        which `audit.board` does for every classless `f` ref, so the body
        has already run by the time this is called.
        """
        world, me, _ = _board(ref, 1)
        body = world.get(me, Health)
        # **Set both ways.** The control first read whatever the board
        # dealt, and this board's fighter arrives already under half -- so
        # "unhurt" was never posed and `f755` looked like it paid
        # unconditionally. Safe to set after arming: `f755` asks
        # `c.bloodied` from inside its `when=`, which is read per payout.
        body.hp = (body.max_hp // 2) if bloodied else body.max_hp
        body.temp = 0
        temp_hp(world, me, me, 1, power=using)
        return body.temp

    # f774: +2 at heroic, gated on the paying power.
    out.that(paid("f774", tagged[0]) == 3,
             "f774 raises an invigorating power's temporary hit points by"
             " its printed 2 -- 1 paid plus 2",
             f"{paid('f774', tagged[0])}")
    out.that(paid("f774", plain) == 1,
             "and leaves a power without the keyword alone -- the gate, and"
             " the reason this is not a flat bonus to every pool",
             f"{paid('f774', plain)}")

    # f792: the smaller ladder.
    out.that(paid("f792", tagged[0]) == 2,
             "f792's printed 1, the same way", f"{paid('f792', tagged[0])}")

    # f755: the same term, gated on bloodied as well.
    out.that(paid("f755", tagged[0], bloodied=True) == 3,
             "f755 pays its 2 while bloodied",
             f"{paid('f755', tagged[0], bloodied=True)}")
    out.that(paid("f755", tagged[0]) == 1,
             "and nothing while unhurt -- the control, asked per payout"
             " rather than at arming because a fight crosses half once",
             f"{paid('f755', tagged[0])}")
    out.that(paid("f755", plain, bloodied=True) == 1,
             "and nothing for a plain power even while bloodied, so both"
             " halves of its condition are load-bearing",
             f"{paid('f755', plain, bloodied=True)}")

    # **f2370 grants the keyword to a power that does not print it**, and
    # that is the case a header read would miss. Written into the two
    # powers rather than laid from the feat (#550) because the feat carries
    # a declared trigger, so its body runs only after a hit -- too late for
    # the attack that just happened.
    from combat_engine.engine.dsl import keywords_of

    def granted(ref: str, *, taken: bool) -> bool:
        world, me, _ = _board(ref, 1)
        known = world.need(me, Powers)
        if taken and "f2370" not in known.known:
            known.known.append("f2370")
        while not taken and "f2370" in known.known:
            known.known.remove("f2370")
        REGISTRY[ref].body(Cast(world=world, me=me, ref=ref))
        return Keyword.INVIGORATING in keywords_of(world, me, REGISTRY[ref])

    for ref in ("p622", "p1428"):
        out.that(Keyword.INVIGORATING not in (REGISTRY[ref].keywords or ()),
                 f"{ref}'s own header does NOT print the keyword, so the"
                 f" grant is the only way it can have it",
                 f"{[k.value for k in (REGISTRY[ref].keywords or ())]}")
        out.that(granted(ref, taken=True),
                 f"and with f2370 taken, {ref} counts as invigorating --"
                 f" read through `keywords_of`, which folds the grant in",
                 f"{granted(ref, taken=True)}")
        out.that(not granted(ref, taken=False),
                 f"and without it, {ref} does not -- the gate, and the"
                 f" reason this is not a header change",
                 f"{granted(ref, taken=False)}")

    out.that(not REGISTRY["f2370"].unfinished,
             "f2370 carries no marker now: its own clause works and the"
             " other lives in the two powers it names",
             f"{REGISTRY['f2370'].unfinished}")

    # **The battlerager's miss clause**, the last row on the keyword.
    # "Use an invigorating <class> attack power and miss every target" --
    # asked of `PowerResolved`, the only event carrying every roll a use
    # made, which is `_missed_everything`'s reason in `items/misc.py`.
    from combat_engine.engine.components import Health as _H
    from combat_engine.engine.events import PowerResolved

    LEG = "cf:fighter-weaponmaster-f3s1"
    out.that(not REGISTRY[LEG].unfinished,
             "the battlerager leg carries no marker now",
             f"{REGISTRY[LEG].unfinished}")

    class _Roll:
        def __init__(self, hit: bool) -> None:
            self.hit = hit

    def fed(power: str, hits: list[bool]) -> int:
        """Temporary hit points after a use that rolled like that."""
        world, me, _ = _board(LEG, 1)
        REGISTRY[LEG].body(Cast(world=world, me=me, ref=LEG))
        body = world.get(me, _H)
        body.temp = 0
        world.bus.emit(PowerResolved(
            actor=me, power=power, targets=[],
            rolls=[_Roll(h) for h in hits]))
        return body.temp

    invig = tagged[0]
    out.that(fed(invig, [False, False]) > 0,
             "missing every target of an invigorating power feeds the pool",
             f"{fed(invig, [False, False])}")
    out.that(fed(invig, [False, True]) == 0,
             "hitting one of them does NOT -- 'miss every target' is the"
             " printed word, and `Miss` alone could never have said it",
             f"{fed(invig, [False, True])}")
    out.that(fed(invig, []) == 0,
             "and a use that rolled nothing did not miss, it did not"
             " attack -- the empty-rolls case `all()` gets wrong",
             f"{fed(invig, [])}")
    out.that(fed(plain, [False, False]) == 0,
             "nor does missing with a power that is not invigorating --"
             " the half that was dropped for want of the keyword",
             f"{fed(plain, [False, False])}")


def a_bare_skill_key_is_read_by_nothing(out: Result) -> None:
    """`c.bonus("perception", 2)` lays a key no reader consults.

    Two readers, two prefixes, and neither takes a bare name.
    `skills.modifier` totals `f"skill:{name}"` plus the blanket
    `"skill"`; `skills.ability_check` totals `f"ability:{x}"` plus
    `"ability_check"`. So a bare skill name sits in `Mods` and no roll
    ever sees it -- while reading exactly like the 37 rows that spell the
    prefix correctly.

    **Four rows did it**, and the clearest sign it was a slip rather than
    a convention is `m1828a5`: its marker reads
    `narrative=("skill:perception",)` while its body laid the bare key, so
    the row named the right form and used the wrong one. Its docstring
    also claims "the Perception bonus plays", which was not true.

    Found by diffing modifier keys **laid** by content against keys
    **read** by the engine -- the same reads-against-writes diff that
    found the one dead ctx key an hour earlier. `lint.py` already had an
    unread-modifier check and missed these, because its list was
    hand-kept and held exactly one key; it is derived from
    `skills.SKILLS` now, so a skill added to the engine cannot arrive
    with a hole beside it.

    Asserted through `skills.modifier`, which is the fixed part of a
    real roll -- ability, half level and the modifiers.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine import When
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.skills import SKILLS
    from combat_engine.engine.skills import modifier as bonus_for

    world, me, _ = _board("m145a0", 1)
    c = Cast(world=world, me=me, ref="drivers:skillkey")
    base = bonus_for(world, me, "perception")

    c.bonus("skill:perception", 7, on=me, until=When.ENCOUNTER)
    out.that(bonus_for(world, me, "perception") == base + 7,
             "the prefixed key reaches a Perception check",
             f"{base} -> {bonus_for(world, me, 'perception')}")

    world2, me2, _ = _board("m145a0", 1)
    c2 = Cast(world=world2, me=me2, ref="drivers:skillkey")
    base2 = bonus_for(world2, me2, "perception")
    c2.bonus("perception", 7, on=me2, until=When.ENCOUNTER)
    out.that(bonus_for(world2, me2, "perception") == base2,
             "and the BARE key reaches nothing -- laid, and no roll sees"
             " it, which is what the four rows were doing",
             f"{base2} -> {bonus_for(world2, me2, 'perception')}")

    out.that("perception" in SKILLS and "thievery" in SKILLS,
             "the skill set the lint rule derives from is the engine's own,"
             " so a new skill cannot arrive without the bare form being"
             " refused too", f"{len(SKILLS)} skills")

    # And the four rows spell it correctly now.
    import inspect

    wrong = []
    for ref in ("m2092a3", "m1828a5", "m6063a0"):
        row = REGISTRY.get(ref)
        if row is None:
            continue
        body = inspect.getsource(row.body)
        body = body.split('"""')[-1] if body.count('"""') >= 2 else body
        for name in SKILLS:
            if f'"{name}"' in body and f'"skill:{name}"' not in body:
                wrong.append((ref, name))
    out.that(not wrong,
             "and none of the repaired rows still lays a bare skill name",
             f"{wrong}")


def immunity_gated_on_the_attacking_power(out: Result) -> None:
    """m5788a0 ignores a Will attack's effects, and the gate was dead. #591.

    "Takes damage as normal, but ignores all other effects" of a
    Will-targeted attack. The row laid immunity to every condition gated on
    `ctx.get("vs")` -- **a key nothing in the engine writes** -- so the
    immunity never applied once and a level 10 soldier went without a
    defensive trait in every fight it was ever in.

    Found by applying to the ctx vocabulary the measurement that caught the
    terrain synonyms: of 34 keys read across 1,886 sites in `content/`,
    **33 are written somewhere in `engine/` and one is not.** That one is
    read exactly once, and this is the row.

    The eight rows asking this elsewhere read `ev.vs` off `AttackDeclared`
    or `AttackRolled`, which carry it -- but those are watchers, and this is
    a standing `when=` gate. So it asks the **power** instead, and
    `query.immune_to` genuinely supplies that key: its context is
    `{"cond", "target", "source", "power"}`, and `power` is documented there
    as "the row doing the laying".

    **Asserted through `query.immune_to`, not through `Mods`.** That is the
    function the engine asks before laying a condition, it builds the
    context itself, and a rule poking the storage would pass while the real
    reader disagreed -- which is how `ctx.get("vs")` survived in the first
    place.

    Both directions, because a live gate is not yet a right one: immunity
    against a power declaring Will, and **no** immunity against one
    declaring AC. The dead gate passed the second for the wrong reason.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine import AC, WILL
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.dsl import REGISTRY, Condition
    from combat_engine.engine.query import immune_to

    row = REGISTRY["m5788a0"]
    will_row = next((r for r, p in REGISTRY.items()
                     if getattr(getattr(p, "attack", None), "vs", None) is WILL), "")
    ac_row = next((r for r, p in REGISTRY.items()
                   if getattr(getattr(p, "attack", None), "vs", None) is AC), "")
    out.that(bool(will_row) and bool(ac_row),
             "the tree fields a Will attack and an AC attack to ask about",
             f"{will_row} / {ac_row}")

    world, me, _ = _board("m5788a0", 1)
    row.body(Cast(world=world, me=me, ref="m5788a0"))

    out.that(immune_to(world, me, Condition.DAZED, power=will_row),
             "immunity applies when the attacking power targets WILL -- the"
             " printed condition, and the one the dead key never met",
             f"{immune_to(world, me, Condition.DAZED, power=will_row)}")
    out.that(not immune_to(world, me, Condition.DAZED, power=ac_row),
             "and NOT when it targets AC -- the other direction, which the"
             " old gate passed only because it refused everything",
             f"{immune_to(world, me, Condition.DAZED, power=ac_row)}")
    out.that(not immune_to(world, me, Condition.DAZED),
             "nor when no power is named -- a condition from a failed save,"
             " a trap or a zone claims no power's narrowing",
             f"{immune_to(world, me, Condition.DAZED)}")

    # Every condition the card exempts, not one of them.
    missed = [c.value for c in Condition
              if not immune_to(world, me, c, power=will_row)]
    out.that(not missed,
             "and it covers EVERY condition, which is what \"ignores all"
             " other effects\" says -- one `c.immune` call per condition, so"
             " a partial list would be a quietly narrower card",
             f"missed {missed[:6]}")


def terrain_words_are_a_closed_set(out: Result) -> None:
    """`c.terrain` refuses a word nobody dresses a board with. #539, #544.

    **Two bugs were stacked here and the outer one hid the inner.**
    `World.terrain` is an empty set that nothing ever adds to, so all 61
    gates across 50 rows are False in every fight -- and *because* they are
    all False, a gate asking for a word the vocabulary does not have read
    exactly like a gate asking for the right one. Nothing could tell them
    apart.

    Re-deriving the histogram found the drift: `water` (6 calls) beside
    `aquatic` (24), and `icy` (1) beside `ice` (2). The same question asked
    two ways, and the second spelling would have stayed broken after
    somebody fixed the first bug.

    So the vocabulary is closed and an unknown word **raises**, which is
    `c.bonus(once=)`'s discipline and the reason #544 gives for it. The
    light words are deliberately not merged: `bright`, `dim light` and
    `darkness` are the three printed levels, `sunlight`, `moonlight` and
    `starlight` are sources, and a creature burned by daylight is not one
    hindered by gloom.

    **The last two assertions are the ones that matter for #539.** They
    show the reader is correct and the *board* is the gap: dress a world
    with a word and the gate answers True, so nothing is wrong with
    `c.terrain` and the whole of the fix is `content.terrain.dress` adding
    the words it already has a seed to choose with.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.cast import TERRAIN_WORDS, Cast

    world, me, _ = _board("m145a0", 1)
    c = Cast(world=world, me=me, ref="drivers:terrain")

    out.that("aquatic" in TERRAIN_WORDS and c.terrain("aquatic") is False,
             "a known word is accepted and answers False -- no board carries"
             " one yet, which is #539",
             f"{sorted(TERRAIN_WORDS)}")

    for gone in ("water", "icy"):
        try:
            c.terrain(gone)
        except ValueError as why:
            out.that(gone in str(why) and "aquatic" in str(why),
                     f"the retired synonym {gone!r} raises, and the message"
                     f" names the word and the vocabulary",
                     f"{str(why)[:70]}")
        else:
            out.that(False, f"{gone!r} should raise -- it is the spelling"
                     f" that was silently never going to match")

    try:
        c.terrain("not a place")
    except ValueError:
        out.that(True, "and so does a typo, which is the whole point of"
                 " closing the set")
    else:
        out.that(False, "a typo should raise")

    out.that(not getattr(world.terrain, "__len__", lambda: 1)(),
             "`World.terrain` is still empty after a real encounter has"
             " started -- the gap #539 names, asserted so it stays proven"
             " rather than rediscovered",
             f"{sorted(world.terrain)}")

    # And the reader itself works, which is what says the board is the gap.
    world.terrain.add("aquatic")
    c2 = Cast(world=world, me=me, ref="drivers:terrain")
    out.that(c2.terrain("aquatic"),
             "dress the world with a word and the gate answers True -- so"
             " `c.terrain` is correct and the whole of the fix is"
             " `terrain.dress` adding the words",
             f"{sorted(world.terrain)}")
    out.that(not c2.terrain("snow"),
             "and only that word -- a dressed board does not answer for"
             " every sort of place at once")


def thrown_is_not_fired(out: Result) -> None:
    """"A thrown weapon such as a dagger or a javelin" -- `Weapon.thrown`.

    `chargen` splits two columns on purpose and says why: *"a thrown melee
    weapon is not a ranged one: a dagger has a printed range and is still
    swung, and `Gear.ranged` picking it up would hand a rogue a ranged basic
    attack it does not have."* So `ranged` is set only for a weapon that is
    **fired**, `thrown` only for a melee weapon with a printed range, and
    they never overlap.

    `feats.general._throws` read `ranged`. That asked for a fireable weapon
    outside the projectile groups, which is wrong in **both** directions --
    the assertions below are one per direction, because a gate that is
    merely too narrow and one that is also too wide want separating:

    * a **dagger** and a **javelin**, the card's own two examples, answered
      False;
    * a **blowgun** answered True.

    Measured from the data rather than reasoned: 27 weapons print a range,
    15 fired and 12 thrown, and the six fired ones outside bow/crossbow/
    sling were the whole of what the old gate could ever see.

    `_shoots` is the sibling and is **correct** -- it wants a fired weapon
    in a projectile group, which is what `ranged` means -- so it is asserted
    here too. A pair where one is right and one is wrong is the case a rule
    covering only the broken one would leave open to a "fix" that breaks
    both.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.content.feats.general import _shoots, _throws
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Gear, Mods, Weapon
    from combat_engine.engine.dsl import REGISTRY

    DAGGER = Weapon(ref="w3594", group="light blade", thrown=(5, 10))
    JAVELIN = Weapon(ref="w3595", group="spear", thrown=(10, 20))
    BLOWGUN = Weapon(ref="w3662", group="blowgun", ranged=(6, 12))
    LONGBOW = Weapon(ref="w3631", group="bow", ranged=(20, 40))
    AXE = Weapon(ref="w3612", group="axe")

    def holding(*arms: Weapon):  # noqa: ANN202
        """Pose a caster holding exactly these.

        `Gear.held` is a **property** -- `weapons` minus `stowed` -- so the
        two backing fields are what a probe sets. Assigning `held` raises,
        which is the kind of thing worth saying once rather than
        rediscovering.
        """
        world, me, _ = _board("f140", 1)
        gear = world.get(me, Gear) or world.add(me, Gear())
        gear.weapons = list(arms)
        gear.stowed.clear()
        return Cast(world=world, me=me, ref="f140"), world, me

    c, _w, _m = holding(DAGGER)
    out.that(_throws(c), "a DAGGER is a thrown weapon -- the card's own first"
             " example, and the old gate answered False", f"{_throws(c)}")
    c, _w, _m = holding(JAVELIN)
    out.that(_throws(c), "and a JAVELIN -- its second", f"{_throws(c)}")
    c, _w, _m = holding(BLOWGUN)
    out.that(not _throws(c),
             "a BLOWGUN is NOT a thrown weapon -- the other direction, and"
             " the old gate answered True because it is fired and is not"
             " filed under bow, crossbow or sling",
             f"{_throws(c)}")
    c, _w, _m = holding(AXE)
    out.that(not _throws(c), "and a plain axe with no printed range is not"
             " one either -- the control", f"{_throws(c)}")

    # The sibling, which is right and must stay right.
    c, _w, _m = holding(LONGBOW)
    out.that(_shoots(c), "a LONGBOW shoots -- `_shoots` wants `ranged` and a"
             " projectile group, which is exactly what that field means",
             f"{_shoots(c)}")
    out.that(not _throws(c),
             "and a longbow is not thrown, so the two gates do not overlap"
             " -- which is the whole reason `chargen` keeps two columns",
             f"{_throws(c)}")
    c, _w, _m = holding(DAGGER)
    out.that(not _shoots(c),
             "nor does a dagger shoot, the same split from the other side",
             f"{_shoots(c)}")

    # And through the row, not only the helper.
    def laid(*arms: Weapon) -> int:
        c, world, me = holding(*arms)
        REGISTRY["f140"].body(c)
        mods = world.get(me, Mods)
        return mods.total("range", {}) if mods else -1

    out.that(laid(DAGGER) == 2,
             "and f140 lays its printed +2 when a dagger is held -- asserted"
             " through the row, so this survives the helper being reverted",
             f"{laid(DAGGER)}")
    out.that(laid(BLOWGUN) == 0,
             "and lays nothing for a blowgun", f"{laid(BLOWGUN)}")


def every_manifestation_pays_its_printed_half(out: Result) -> None:
    """All thirteen of one race's manifestations, each static half asserted.

    **#548 says every character of this race "is permanently missing
    whichever of these its manifestation prints" -- a defence bonus, a
    resistance, saves. That is false, and this rule is the measurement that
    says so.** `rt:r33-t0` forks on which of the thirteen *powers*
    `Powers.known` holds and lays the printed bonuses for that leg; the
    thirteen `rt:…-s<N>` refs have no row because the content chose one row
    with thirteen branches over thirteen rows, not because the halves are
    missing.

    Nobody had asserted it, which is how the issue stood. A thirteen-way
    `elif` chain on a key read from a component is exactly the shape that
    rots silently: one wrong ref and that leg pays nothing, and the row
    still fires and still audits green off whichever leg the board happens
    to deal.

    **Driven through `Powers.known`, not by stubbing `_holds`.** The fork
    reads the component, so the component is what the probe sets -- and
    `known` is the list; `Powers.all` is a derived view and mutating it
    does nothing, which cost me a confusing first probe where the board's
    own leg kept answering.

    Resistances are flat 5 through heroic by the row's own argument -- each
    block prints a step at 11th and 21st and both are out of scope -- so 5
    is what is asserted. Breathing underwater and shrugging off ambient
    temperature are printed on three legs and deliberately unwritten: no
    fight reaches either, and the row says so.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine import FORT, REF, WILL
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defences, Mods, Powers
    from combat_engine.engine.dsl import REGISTRY, DamageType

    D = DamageType
    #: `(the power that marks this leg, resisted type or None, defence or
    #: None, does it raise a save)`, read off the thirteen printed blocks.
    LEGS = (
        ("p1766", D.FIRE, REF, False),
        ("p1767", None, FORT, True),
        ("p1769", D.LIGHTNING, FORT, False),
        ("p1770", None, None, True),
        ("p1828", D.COLD, None, False),
        ("p10043", D.ACID, None, False),
        ("p10044", D.FIRE, FORT, False),
        ("p10045", D.POISON, None, True),
        ("p10046", D.PSYCHIC, WILL, False),
        ("p14073", None, REF, True),
        ("p14074", None, FORT, False),
        ("p14075", None, None, True),
        ("p14076", None, None, True),
    )
    row = REGISTRY["rt:r33-t0"]
    every = [leg[0] for leg in LEGS]

    def pose(power: str):  # noqa: ANN202
        """A character of this race holding exactly one manifestation."""
        world, me, _ = _board("rt:r33-t0", 1)
        held = world.get(me, Powers)
        for other in every:
            while other in held.known:
                held.known.remove(other)
        # The board arms traits, so the leg it dealt has already paid.
        # Cleared, then re-run with the leg this call is about.
        guard = world.get(me, Defences)
        if guard is not None:
            guard.resist.clear()
        mods = world.get(me, Mods)
        if mods is not None:
            mods.items.clear()
        held.known.append(power)
        row.body(Cast(world=world, me=me, ref="rt:r33-t0"))
        return world, me

    out.that(len(LEGS) == 13, "all thirteen legs are asked about, not a"
             " sample -- the point is that none is a dead branch",
             f"{len(LEGS)}")

    paid_nothing = []
    for power, resisted, defence, raises_save in LEGS:
        world, me = pose(power)
        guard = world.get(me, Defences)
        mods = world.get(me, Mods)
        got_resist = dict(guard.resist) if guard else {}
        anything = bool(got_resist) or bool(mods and mods.items)
        if not anything:
            paid_nothing.append(power)
            continue
        if resisted is not None:
            out.that(got_resist.get(resisted) == 5,
                     f"the leg marked by {power} resists 5 of its printed"
                     f" type",
                     f"{ {k.value: v for k, v in got_resist.items()} }")
        if defence is not None:
            # Read straight off `Mods`, which is where `c.bonus(REF, 1)`
            # puts it. The first version hedged on a `c.defence_of` that
            # does not exist, and the hedge was wrong either way: that
            # would answer a defence *value*, not whether this row raised
            # it by the printed 1.
            out.that(mods is not None
                     and mods.total(str(defence), {}) == 1,
                     f"and raises the one defence {power}'s block prints,"
                     f" by the printed 1",
                     f"{mods.total(str(defence), {}) if mods else None}")
        if raises_save:
            out.that(mods is not None and any(
                "save" in str(k) for k in _mod_keys(mods)),
                     f"and {power}'s leg raises a saving throw",
                     f"{sorted(_mod_keys(mods))[:4]}")

    out.that(not paid_nothing,
             "every leg pays something -- a thirteen-way chain on a ref is"
             " where one typo makes a branch dead, and the row would still"
             " fire and still audit green off another leg",
             f"paid nothing: {paid_nothing}")

    # The negative control: no manifestation, no static half.
    world, me, _ = _board("rt:r33-t0", 1)
    held = world.get(me, Powers)
    for other in every:
        while other in held.known:
            held.known.remove(other)
    guard = world.get(me, Defences)
    if guard is not None:
        guard.resist.clear()
    mods = world.get(me, Mods)
    if mods is not None:
        mods.items.clear()
    row.body(Cast(world=world, me=me, ref="rt:r33-t0"))
    guard = world.get(me, Defences)
    out.that(not (guard and guard.resist),
             "and a character holding NONE of the thirteen gets nothing --"
             " the control, without which a row laying one leg"
             " unconditionally would pass every assertion above",
             f"{ {k.value: v for k, v in (guard.resist if guard else {}).items()} }")


def _mod_keys(mods) -> list[str]:  # noqa: ANN001
    """Every modifier key a creature is carrying, however `Mods` holds them."""
    out: list[str] = []
    for item in getattr(mods, "items", ()) or ():
        key = getattr(item, "what", None) or getattr(item, "key", None)
        if key is None and isinstance(item, (tuple, list)) and item:
            key = item[0]
        if key is not None:
            out.append(str(key))
    return out


def one_manifestation_not_thirteen(out: Result) -> None:
    """A race's "choose one" traits are alternatives, not a stack. #548.

    Three races print their traits as a **choice between sub-options**, and
    the race's own spec gives each one a ref -- `rt:r33-s0` and so on, 18 of
    them. **None is declared**, so every character of those races is
    permanently short whichever defence bonus and resistance its
    manifestation prints.

    The obvious fix is the dangerous one, and this rule is the guard against
    it. `RaceLine.traits` collects by **prefix**:

        sorted(r for r in REGISTRY if r.startswith(f"rt:{self.ref}-"))

    so declaring the rows without changing anything else would hand an `r33`
    character all **thirteen** manifestations at once -- +1 Reflex *and* +1
    Fortitude, resist 5 fire *and* resist 5 lightning, +2 to saves, and
    breathing underwater. `m5808a0`'s rule at the scale of a whole race.

    **So the probe declares a sub-option that does not exist**, which is the
    only way to test a guard about rows nobody has written. Registering one
    and asking what a character would carry is the question; waiting until
    the 18 land and then asking is how the fault ships.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.chargen import RACES
    from combat_engine.engine.dsl import REGISTRY

    # `RACES` is a plain `dict[str, RaceLine]` built at import. The first
    # version hedged with `RACES() if callable(RACES) else RACES`, which
    # bought nothing and cost two type errors.
    lines = list(RACES.values())
    r33 = next((ln for ln in lines if ln.ref == "r33"), None)
    out.that(r33 is not None, "the thirteen-manifestation race is on the"
             " board to ask about", f"{[ln.ref for ln in lines][:6]}")
    if r33 is None:
        return

    out.that(not r33.manifestations,
             "none of the 18 sub-options is declared yet, which is #548 and"
             " is why this guard lands before them rather than after",
             f"{r33.manifestations}")
    before = list(r33.granted())

    # Three of them, including a two-digit index so the ordering is tested.
    planted = ("rt:r33-s0", "rt:r33-s9", "rt:r33-s10")
    borrowed = REGISTRY["rt:r1-t0"]
    for ref in planted:
        REGISTRY[ref] = borrowed
    try:
        traits = r33.traits
        out.that(not any(r in traits for r in planted),
                 "a declared sub-option does NOT join `traits` -- the whole"
                 " guard, and what stops thirteen alternatives stacking",
                 f"{[r for r in traits if '-s' in r]}")
        mine = r33.manifestations
        out.that(all(r in mine for r in planted),
                 "it joins `manifestations` instead, so the rows are"
                 " reachable rather than merely excluded",
                 f"{mine}")
        out.that(mine == ["rt:r33-s0", "rt:r33-s9", "rt:r33-s10"],
                 "in PRINTED order -- `-s10` after `-s9`, where a plain"
                 " alphabetical sort puts it between `-s1` and `-s2`",
                 f"{mine}")
        after = list(r33.granted())
        gained = [r for r in after if r not in before]
        out.that(len(gained) <= 1,
                 "and a character carries AT MOST ONE of them -- three"
                 " declared, so a prefix walk would have handed over three",
                 f"gained {gained}")
    finally:
        for ref in planted:
            REGISTRY.pop(ref, None)

    out.that(not r33.manifestations,
             "the probe cleans up after itself, so the registry it shares"
             " with every other rule is as it was",
             f"{r33.manifestations}")


def resistance_taken_off_the_target(out: Result) -> None:
    """"The target loses any resistance or immunity to this damage type."

    Two rows print it -- `i1184p1` and `p16259` -- and `c.resist` has
    always been able to say the resistance half: a **negative** amount is
    arithmetic rather than a highest-wins hold, which that verb's own
    comment calls *"the other printed sentence"*, and `c.resistances`
    reads the standing number so the delta is exact.

    `p16259`'s note said "nothing on `Cast` takes a resistance away" while
    `i1184p1`, written, sat one file over doing it.

    **The assertion about the half that is still missing is the point of
    this rule.** Immunity lives in a separate set, `Defences.immune`, and
    nothing takes anything out of it, so an immune creature must come
    through untouched. Asserting that keeps the `Defences.immune` marker
    *honest*: if somebody later writes the immunity half, this goes red and
    says the marker is stale, which is the one thing a marker cannot report
    about itself.

    Exactness matters in both directions here. Taking off **more** than the
    creature has would turn a resistance into a vulnerability -- `c.resist`
    is arithmetic, so `-99` really does go to -99 -- and that is a row
    stronger than its card, which `m5808a0` names as worse than an absent
    one.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine import When
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defences, Health
    from combat_engine.engine.dsl import REGISTRY, DamageType
    from combat_engine.engine.query import enemies

    PICK, OTHER = DamageType.FIRE, DamageType.COLD

    def run(resist: int, *, immune: bool = False, other: int = 0):  # noqa: ANN202
        world, me, _ = _board("p16259", 1)
        foe = next(e for e in enemies(world, me) if world.get(e, Health))
        held = world.get(foe, Defences) or world.add(foe, Defences())
        held.resist.clear()
        held.immune.clear()
        if resist:
            held.resist[PICK] = resist
        if other:
            held.resist[OTHER] = other
        if immune:
            held.immune.add(PICK)
        c = Cast(world=world, me=me, ref="p16259", targets=[foe])
        c.target = foe
        c.choose = lambda *a, **k: PICK   # ty: ignore[invalid-assignment]
        c.strike = lambda **kw: True      # ty: ignore[invalid-assignment]
        c.damage = lambda *a, **k: None   # ty: ignore[invalid-assignment]
        REGISTRY["p16259"].body(c)
        return world, foe, held

    held = run(10)[2]
    out.that(held.resist.get(PICK, 0) == 0,
             "a target resisting 10 of the chosen type loses all of it",
             f"resist {PICK.value} = {held.resist.get(PICK, 0)}")

    held = run(10, other=7)[2]
    out.that(held.resist.get(OTHER, 0) == 7,
             "and its resistance to a DIFFERENT type is untouched -- the"
             " card names one type, the one the power is dealing",
             f"resist {OTHER.value} = {held.resist.get(OTHER, 0)}")

    held = run(0)[2]
    out.that(held.resist.get(PICK, 0) == 0,
             "a target with no such resistance is not pushed NEGATIVE --"
             " `c.resist` is arithmetic, so a blanket delta would turn no"
             " resistance into a vulnerability and beat the printed card",
             f"resist {PICK.value} = {held.resist.get(PICK, 0)}")

    # The dropped half, asserted so the marker can be trusted.
    held = run(0, immune=True)[2]
    out.that(PICK in held.immune,
             "an IMMUNE target keeps its immunity -- the half `Defences."
             "immune` is marked for, and the assertion that makes that"
             " marker honest rather than merely old",
             f"immune={sorted(t.value for t in held.immune)}")

    row = REGISTRY["p16259"]
    out.that("Defences.immune" in (row.unfinished or ()),
             "and the row says so, rather than reporting finished",
             f"{row.unfinished}")

    # **Restored when the hold ends, which is what `c.resist`'s `undo`
    # exists for.** Ended through the effect the row itself laid rather
    # than by advancing a clock: `Effects` has no `expire(When)`, and
    # reaching for the real teardown path is what proves `undo` runs.
    world, foe, held = run(10)
    out.that(held.resist.get(PICK, 0) == 0, "stripped while it lasts")
    mine = [e for e in world.effects.of(foe) if "p16259" in (e.label or "")]
    out.that(len(mine) == 1,
             "the strip is ONE labelled effect on the target, so it has"
             " something to be taken back by",
             f"{[e.label for e in world.effects.of(foe)]}")
    # **The duration itself, and a plant is why this is here.** Ending the
    # effect by hand below proves `undo` runs and says nothing about *when*
    # it would have run -- so swapping `When.EONT` for `When.ENCOUNTER` in
    # the row left this rule entirely green. The card says "until the end
    # of your next turn", so the duration is a printed number and gets its
    # own assertion rather than being inferred from the teardown working.
    out.that(bool(mine) and mine[0].when is When.EONT,
             "and it lasts until the end of the caster's next turn, which is"
             " what the card prints -- not the encounter",
             f"{mine[0].when if mine else None}")
    for e in mine:
        world.effects.end(e, "driver")
    out.that(held.resist.get(PICK, 0) == 10,
             "and the resistance comes BACK when the hold ends -- the card"
             " says until the end of your next turn, not for good",
             f"resist {PICK.value} = {held.resist.get(PICK, 0)}")


def vulnerability_held_by_a_zone(out: Result) -> None:
    """"Each enemy within the zone gains vulnerable N while it is there."

    `c.vulnerable_in`, the mirror of `c.resist_in` over the same
    `_while_inside` helper. Four heroic rows printed the sentence and sat
    under **two** symbols -- `c.vulnerable_in()` and `c.aura(vulnerable=)`
    -- which was one gap written twice: an aura is a zone as far as that
    helper is concerned, so there was never a second mechanism.

    **The assertions that matter are the ones about scope**, because the
    number landing is the easy half and every one of the four rows differs
    from the others on a scope:

    * the **geometry** -- it lifts when the creature walks out, which is
      what `c.vulnerable(until=...)` cannot say: a duration runs on the
      clock and this runs on where somebody is standing;
    * the **side** -- `p12261` says "each enemy", `p15946` says
      "creatures", and the two sat under one symbol differing on exactly
      that. Hence `side` is a parameter and its default here is `"enemy"`
      where `c.resist_in`'s is `"team"`: a zone that helps prints "you and
      your allies" and a zone that hurts prints "each enemy".
    * the **gate** -- "vulnerable 3 to *weapon* attacks" and "to *your*
      attacks" are not damage types, and are read off a context carrying
      `source` and `power`.

    Dealt end to end with `c.flat` rather than against a hand-built
    context, for the reason `scoped_vulnerable` records: that rule built
    its own ctx with `attacker`, and two rows written against the wrong
    key passed it and would never have fired in a fight.
    """

    import combat_engine.content  # noqa: F401
    from combat_engine.engine import When
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defences, Health, Position
    from combat_engine.engine.dsl import REGISTRY, DamageType
    from combat_engine.engine.query import allies, enemies

    def taken(*, side: str, inside: bool, who: str = "enemy",
              dtype: DamageType | None = None,
              deal: DamageType | None = None,
              gated_to: int | None = None) -> int:
        """Hit somebody for 10 and report what they actually lost."""
        world, me, _ = _board()
        pool = enemies(world, me) if who == "enemy" else [
            a for a in allies(world, me) if a != me]
        victim = next((e for e in pool if world.get(e, Health)), None)
        if victim is None:
            return -1
        here = world.get(me, Position)
        spot = world.get(victim, Position)
        # Lay the zone on the caster's own square. Standing in it is the
        # thing being measured, so the victim is put there or kept out.
        spot.square = here.square if inside else (here.square[0] + 25,
                                                  here.square[1])
        c = Cast(world=world, me=me, ref="drivers:vuln_in")
        zone = c.zone([here.square], label=c.ref, until=When.ENCOUNTER)
        c.vulnerable_in(
            zone, 5, dtype, side=side,
            when=None if gated_to is None
            else (lambda ctx: ctx.get("source") == gated_to),
        )
        hp = world.get(victim, Health)
        was = hp.hp
        # **Not `dtype=deal` when `deal` is None.** `c.flat` with an
        # explicit `None` makes `part_types` `(None,)` and
        # `_ignored_resist` dies on `t.value` -- a crash rather than
        # untyped damage, which is what omitting it gives.
        if deal is None:
            c.flat(10, on=victim)
        else:
            c.flat(10, dtype=deal, on=victim)
        return was - hp.hp

    out.that(taken(side="enemy", inside=True) == 15,
             "an enemy standing in the zone takes 10 + the vulnerable 5",
             f"{taken(side='enemy', inside=True)}")
    out.that(taken(side="enemy", inside=False) == 10,
             "and one standing OUTSIDE takes the 10 alone -- the control, and"
             " the half a plain `c.vulnerable(until=...)` cannot say",
             f"{taken(side='enemy', inside=False)}")

    # The side split, which is the difference the two old symbols hid.
    out.that(taken(side="enemy", inside=True, who="ally") == 10,
             "an ALLY in the same zone is spared under `side=\"enemy\"` --"
             " `p12261` prints \"each enemy\" and `p15946` prints"
             " \"creatures\", and they sat under one symbol",
             f"{taken(side='enemy', inside=True, who='ally')}")
    out.that(taken(side="any", inside=True, who="ally") == 15,
             "and `side=\"any\"` reaches that same ally, so the parameter is"
             " load-bearing rather than decoration",
             f"{taken(side='any', inside=True, who='ally')}")

    # The damage type.
    out.that(taken(side="enemy", inside=True,
                   dtype=DamageType.FIRE, deal=DamageType.FIRE) == 15,
             "a typed vulnerability counts for its own type",
             f"{taken(side='enemy', inside=True, dtype=DamageType.FIRE, deal=DamageType.FIRE)}")
    out.that(taken(side="enemy", inside=True,
                   dtype=DamageType.FIRE, deal=DamageType.COLD) == 10,
             "and not for another -- `p12261` is thunder and `p15946` fire,"
             " so this is what keeps them from each other's blows",
             f"{taken(side='enemy', inside=True, dtype=DamageType.FIRE, deal=DamageType.COLD)}")

    # The gate, which is `p15951`'s and `p16046`'s half.
    out.that(taken(side="enemy", inside=True, gated_to=-99) == 10,
             "a gate naming somebody else takes the 10 alone -- \"vulnerable"
             " to YOUR attacks\" is a question about the dealer, not a type",
             f"{taken(side='enemy', inside=True, gated_to=-99)}")

    # And it comes off when the creature leaves, which is the geometry.
    world, me, _ = _board()
    victim = next(e for e in enemies(world, me) if world.get(e, Health))
    here = world.get(me, Position)
    world.get(victim, Position).square = here.square
    c = Cast(world=world, me=me, ref="drivers:vuln_in")
    zone = c.zone([here.square], label=c.ref, until=When.ENCOUNTER)
    c.vulnerable_in(zone, 5, side="enemy")
    held = world.get(victim, Defences)
    out.that(bool(held and held.vulnerable_when) or bool(held and held.vulnerable),
             "standing inside, the vulnerability is recorded on the creature",
             f"{getattr(held, 'vulnerable_when', None)}")
    c.slide(25, on=victim)
    held = world.get(victim, Defences)
    gone = not (held and (held.vulnerable_when or held.vulnerable))
    out.that(gone,
             "and walking out takes it back -- `_while_inside`'s whole job,"
             " and the reason this is not a duration",
             f"{getattr(held, 'vulnerable_when', None)}"
             f" {getattr(held, 'vulnerable', None)}")

    # **Through a real row, not only the verb.** `p13747` is what the verb
    # was built for and it was live and wrong in three ways -- every
    # attacker's blow, no end on leaving, no end when the aura went -- while
    # auditing green, because its attack and damage are the parts that fire.
    # Asserting the verb alone would survive this row being reverted to its
    # hand-rolled version, which is the whole argument for driving the caller.
    # **No assertion about the row's source text, and the plant is why.**
    # The first version read `inspect.getsource(row.body)` for the verb's
    # name. Planting the old hand-rolled body back and re-running left that
    # assertion **green** -- `getsource` goes through `linecache` against a
    # module already imported, so it is reading neither the behaviour nor
    # reliably the file. Same family as the `startswith("def")` fault that
    # made an AST walk report zero bare calls tree-wide. The behavioural
    # assertions below caught the plant; a source grep is not evidence.
    row = REGISTRY["p13747"]

    world, me, _ = _board("p13747", 1)
    foe = next(e for e in enemies(world, me) if world.get(e, Health))
    world.get(foe, Position).square = world.get(me, Position).square
    c = Cast(world=world, me=me, ref="p13747", targets=[foe])
    c.target = foe
    # Only the Effect half is wanted; the attack is asserted elsewhere.
    c.strike = lambda **kw: False  # ty: ignore[invalid-assignment]
    # **The flat dict is read before as well as after, and that caught a
    # wrong assertion.** The first version asserted the creature carries no
    # flat vulnerability at all, and it failed: this board's monster prints
    # `vulnerable 5 radiant` in its own stat block, which is data and not
    # this row's doing. The question is whether the row *touches* the flat
    # dict -- a widened clause would -- so it is a before-and-after.
    before_flat = dict(getattr(world.get(foe, Defences), "vulnerable", {}) or {})
    row.body(c)
    carried = world.get(foe, Defences)
    scoped = list(getattr(carried, "vulnerable_when", []) or [])
    flat = dict(getattr(carried, "vulnerable", {}) or {})
    out.that(len(scoped) == 1 and flat == before_flat,
             "standing in p13747's aura, an enemy gains ONE scoped"
             " vulnerability and the flat dict is untouched -- the flat dict"
             " is what the widened version used to fill, and what an"
             " unscoped reader would see",
             f"{len(scoped)} scoped; flat {before_flat} -> {flat}")
    if scoped:
        dtype, amount, gate = scoped[0]
        out.that(dtype is DamageType.RADIANT and amount == 3,
                 "and it is the printed 3 radiant", f"{amount} {dtype}")
        out.that(gate({"source": me}) and not gate({"source": foe}),
                 "scoped to the CASTER's attacks -- the qualifier the old"
                 " body dropped, and the one that made the row stronger"
                 " than its card for every other attacker",
                 f"mine={gate({'source': me})} theirs={gate({'source': foe})}")


def class_form(out: Result) -> None:
    """A class form is a state *and* a keyword, and they are not the same test.

    Two sentences printed in nearly the same words on the same cards:

    * "while you are in beast form" -- a state on the creature;
    * "your beast form attack powers deal 1d6 extra damage" -- a keyword on
      the row being used.

    **Ten rows were marked as wanting the first when they wanted the second**,
    which is the mistake this rule exists to keep from coming back. A character
    can be a beast and swing something that is not a beast form power, and a
    bonus gated on the wrong one of those is wrong in every fight rather than
    merely absent.

    The grantors are the other half. They laid `c.form(label=...)` with no
    `name=`, so the hold could be found by its ref and the *word* was nowhere
    -- `c.suffering` answered and `query.in_form` could not, and only the
    second is what "while you are in beast form" asks.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.dsl import get
    from combat_engine.engine.durations import When
    from combat_engine.engine.query import in_form, shifted
    from combat_engine.engine.types import Keyword

    world, caster, _ = _board()

    # ---- the state half -------------------------------------------------
    out.that(not shifted(world, caster), "nobody has changed shape yet")
    out.that(in_form(world, caster, "beast"),
             "and the gate is permissive about that, as a Requirement must be")

    c = Cast(world=world, me=caster, ref="drivers:form")
    held = c.form(until=When.ENCOUNTER, label="drivers:form", name="beast")
    out.that(shifted(world, caster), "taking the form records it")
    out.that(in_form(world, caster, "beast"), "and the word is readable")
    out.that(not in_form(world, caster, "guardian"),
             "a DIFFERENT form's word is not -- this is the negative control,"
             " and without it `in_form`'s permissive answer passes everything")

    world.effects.end(held, "driver")
    out.that(not shifted(world, caster), "ending it takes the shape away")

    # ---- the keyword half, which is a different question ----------------
    bf = [r for r in ("p5036", "p16537", "p16539")
          if (p := get(r)) is not None and Keyword.BEAST_FORM in p.keywords]
    out.that(len(bf) == 3,
             "the rows the cards tag are tagged -- 0 of 68 headers declared"
             " this keyword before the parse fix, so every gate on it was"
             " silently false")
    plain = get("p12400")
    out.that(plain is not None and Keyword.BEAST_FORM not in plain.keywords,
             "and a row the card does not tag is not tagged")

    # The two tests disagree, which is the whole point of having both.
    world2, caster2, _ = _board()
    c2 = Cast(world=world2, me=caster2, ref="drivers:form2")
    c2.form(until=When.ENCOUNTER, label="drivers:form2", name="beast")
    out.that(in_form(world2, caster2, "beast"), "in the form")
    out.that(Keyword.BEAST_FORM not in (get("p12400").keywords),
             "swinging a row that is not a beast form power")
    out.that(
        in_form(world2, caster2, "beast")
        and Keyword.BEAST_FORM not in get("p12400").keywords,
        "so a state gate PAYS and a keyword gate does NOT, on the same swing"
        " -- which is why one marker could not serve both",
    )


def leash(out: Result) -> None:
    """A tether: cannot get further than N squares from something.

    Fourteen rows print one and the three near verbs are all wrong --
    `c.immobilized` and `c.no_walk` stop the creature dead, and nothing else
    measured distance from a remembered point. #512.

    **The controls are about what a tether is not.**

    * It must still be able to **move**, within the radius. A tether that
      pins the creature is `c.immobilized` wearing a different name, and
      that is the mistake the printed lines are distinguished from.
    * A **creature** anchor must move with it, which is what "no more than 2
      squares from a held creature" needs: a trap dragging its victim keeps
      the leash taut rather than snapping it.
    * It filters **destinations, not the search**. Forbidding passage
      *through* a far square to reach a near one is a rule no card prints,
      and would also make a tethered creature unable to walk around a
      pillar.
    * A dead anchor **cuts** the leash rather than measuring against the
      last place a corpse stood.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Position
    from combat_engine.engine.durations import When
    from combat_engine.engine.grid import distance
    from combat_engine.engine.movement import reachable
    from combat_engine.engine.query import enemies, speed

    world, caster, _ = _board()
    foe = sorted(enemies(world, caster))[0]
    c = Cast(world=world, me=caster, ref="drivers:leash")
    here = world.get(caster, Position).square
    free = reachable(world, caster, speed(world, caster))
    out.that(len(free) > 8, "untethered, it has a wide choice of squares")

    held = c.leash(2, on=caster, until=When.ENCOUNTER)
    out.that(held is not None, "a card tethers it")
    near = reachable(world, caster, speed(world, caster))
    out.that(near, "it can still MOVE -- the control, since a tether that"
                   " pins is `c.immobilized` under another name")
    out.that(len(near) < len(free), "but to fewer squares than before")
    out.that(all(distance(sq, here) <= 2 for sq in near),
             "and none of them further than the printed radius")

    # **Destinations are filtered, not the search**, and this is the way to
    # say it that can fail: every square that was reachable before and is
    # inside the radius must still be reachable. Filtering the search would
    # lose the ones whose cheapest route bulges outside it.
    inside_before = {sq for sq in free if distance(sq, here) <= 2}
    out.that(set(near) == inside_before,
             f"every one of the {len(inside_before)} squares that was"
             " reachable and is inside the radius is still reachable --"
             " filtering the search instead would drop the ones whose route"
             " bulges outside it")

    world.effects.end(held, "driver ended it")
    out.that(len(reachable(world, caster, speed(world, caster))) == len(free),
             "ending it restores every square")

    # A creature anchor travels.
    c.leash(1, to=foe, on=caster, until=When.ENCOUNTER)
    at_foe = world.get(foe, Position)
    out.that(all(distance(sq, at_foe.square) <= 1
                 for sq in reachable(world, caster, speed(world, caster))),
             "tethered to a creature, it stays within a square of it")
    at_foe.square = (at_foe.square[0] + 3, at_foe.square[1])
    moved = reachable(world, caster, speed(world, caster))
    out.that(all(distance(sq, at_foe.square) <= 1 for sq in moved) and moved,
             "and the anchor MOVING takes the leash with it -- the control"
             " that distinguishes a creature anchor from a remembered square")


def attacks_defence(out: Result) -> None:
    """Move a creature's attacks onto a different defence.

    Twelve rows print "your weapon attacks target Reflex instead of AC" and
    all twelve say the engine cannot do it: *"`AttackDeclared.vs` is a field
    but `resolve.attack` reads its own local afterwards, so a listener
    rewriting it changes nothing."*

    **That was already false when it was written.** `resolve.roll` reads
    `vs = declared.vs`, and the comment above that line records the fix in
    as many words. What *is* true, and is how the wrong conclusion was
    almost certainly reached: an **ordinary** listener is too late. `roll` is
    the resolve callback -- it runs after the interrupt window and before
    ordinary listeners -- so a plain `c.watch` sees `AttackDeclared` only
    once the defence has been read off it.

    So the two controls that matter are the window ones. Asserting only that
    the defence moved would pass on a verb registered in either window, and
    the whole content of this verb is which one. #509.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import resolve as _resolve
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.durations import When
    from combat_engine.engine.events import AttackDeclared, AttackRolled
    from combat_engine.engine.query import enemies
    from combat_engine.engine.types import Defense

    world, caster, _ = _board()
    foe = sorted(enemies(world, caster))[0]
    rolled: list[Defense] = []
    world.bus.on(AttackRolled, lambda ev: rolled.append(ev.vs))

    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:vs")
    out.that(rolled[-1] is Defense.AC,
             "with nothing moving it, the attack rolls against what it"
             " declared")

    # An ordinary listener is too late -- the control that is the whole
    # point, and the reason twelve rows concluded this was impossible.
    def late(ev: AttackDeclared) -> None:
        if ev.attacker == caster:
            ev.vs = Defense.WILL

    sub = world.bus.on(AttackDeclared, late)
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:vs")
    out.that(rolled[-1] is Defense.AC,
             "an ORDINARY listener rewriting `vs` changes nothing -- it runs"
             " after the resolve callback has read it, which is exactly what"
             " the twelve rows observed and generalised too far")
    world.bus.off(sub)

    # The verb, which registers in the interrupt window.
    c = Cast(world=world, me=caster, ref="drivers:vs")
    held = c.attacks_defence(Defense.REF, until=When.ENCOUNTER)
    out.that(held is not None, "the verb lays a hold")
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:vs")
    out.that(rolled[-1] is Defense.REF,
             "and the attack now rolls against Reflex -- the same rewrite,"
             " in `Window.BEFORE`")

    # Somebody else's attack is untouched.
    _resolve.attack(world, foe, caster, 5, Defense.AC, power="drivers:vs")
    out.that(rolled[-1] is Defense.AC,
             "another creature's attack is untouched -- the control, without"
             " which one feat moves every attack on the board")

    # The gate.
    world.effects.end(held, "driver ended it")
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:vs")
    out.that(rolled[-1] is Defense.AC, "ending the hold puts it back")

    gated = c.attacks_defence(
        Defense.FORT, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "drivers:gated")
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:vs")
    out.that(rolled[-1] is Defense.AC, "a gated hold declines the wrong row")
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:gated")
    out.that(rolled[-1] is Defense.FORT, "and takes the one it names")
    world.effects.end(gated, "driver ended it")

    # `from_` -- three cards narrow on the defence the attack started from.
    c.attacks_defence(Defense.WILL, from_=Defense.REF, until=When.ENCOUNTER)
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:from")
    out.that(rolled[-1] is Defense.AC,
             "`from_=REF` leaves an attack that declared AC alone -- the"
             " control, since a swap that fired whatever the row declared"
             " would move an attack the card never mentions")
    _resolve.attack(world, caster, foe, 5, Defense.REF, power="drivers:from")
    out.that(rolled[-1] is Defense.WILL,
             "and moves one that declared Reflex")


def waive(out: Result) -> None:
    """Switch off part of what a condition costs, without lifting it.

    Twelve rows print a waiver on squeezing -- "you take no penalty to
    attack rolls", "you move at full speed", "you do not grant combat
    advantage" -- and `conditions.RULES` held
    `Rules(grants_ca=True, attack=-5, halve_speed=True)` as a constant with
    nothing to switch off. #508.

    **The controls are the point, and the first one is why this is not
    `suppress`.** Suppressing squeezing means you are not squeezing, so you
    no longer fit where only a squeezing creature fits. These cards keep the
    condition and relax part of its cost, so the condition must still be
    *held* afterwards.

    The rest:

    * **each knob is independent** -- waiving the attack penalty must leave
      the halved speed alone, because three rows waive one and three waive
      all three;
    * **a creature with no waiver is untouched**, which matters because
      `rules_for` is on the path of every speed and every attack in the
      game;
    * **the waiver ends with its effect**, and ends only its own words: two
      rows may waive overlapping sets.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Conditions
    from combat_engine.engine.conditions import rules, rules_for
    from combat_engine.engine.durations import When
    from combat_engine.engine.query import attack_penalty, grants_ca, speed
    from combat_engine.engine.types import Condition

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:waive")

    out.that(rules(Condition.SQUEEZING).attack == -5,
             "the printed table costs a squeezing creature 5 to hit with")

    clean = speed(world, caster)
    c.condition(Condition.SQUEEZING, on=caster, until=When.ENCOUNTER)
    held = world.need(caster, Conditions)
    out.that(held.has(Condition.SQUEEZING), "it is squeezing")
    out.that(attack_penalty(world, caster) == -5, "and takes the penalty")
    out.that(speed(world, caster) == clean // 2, "at half speed")
    out.that(grants_ca(world, caster) is True, "granting advantage")

    # One knob, and only that one.
    eff = c.waive(Condition.SQUEEZING, "attack")
    out.that(eff is not None, "a card waives the attack penalty")
    out.that(attack_penalty(world, caster) == 0, "which is gone")
    out.that(speed(world, caster) == clean // 2,
             "and the halved speed is UNTOUCHED -- the control, since three"
             " rows waive one knob and three waive all three")
    out.that(grants_ca(world, caster) is True,
             "as is granting advantage")
    out.that(held.has(Condition.SQUEEZING),
             "and it is still squeezing -- the whole difference from"
             " suppressing, which would mean it no longer fits where it"
             " squeezed to")

    # The rest.
    c.waive(Condition.SQUEEZING, "halve_speed", "grants_ca")
    out.that(speed(world, caster) == clean, "full speed once that is waived")
    out.that(grants_ca(world, caster) is False, "and no advantage")

    # A creature with no waiver reads the shared table, unchanged.
    out.that(
        rules_for(world, caster + 1, Condition.SQUEEZING)
        is rules(Condition.SQUEEZING),
        "a creature with no waiver gets the shared table object itself --"
        " `rules_for` is on the path of every speed and every attack, so it"
        " must not build one per call",
    )

    # Ending the effect takes back only its own words.
    if eff is not None:
        world.effects.end(eff, "driver ended it")
    out.that(attack_penalty(world, caster) == -5,
             "ending the first waiver restores the attack penalty")
    out.that(speed(world, caster) == clean,
             "and leaves the second waiver's words alone -- removed by its"
             " own set, because two rows may waive overlapping knobs")


def extend_move(out: Result) -> None:
    """Make a named row move you further, from outside it.

    The distance a row moves you is an **argument inside its own body** --
    `c.teleport(8)`, `c.shift(1)`, `c.slide(3)` -- so "one more square on
    every swordmage teleport" and "five squares further on that power" had
    nothing to change. Eleven rows print a sentence of that shape and each
    had worked out the gap independently in its own docstring. #502.

    The exact sibling of `change_dice`/`dice_for`, which won the same
    argument for dice, and the same bargain applies: **a row must read it to
    be changed.** A modifier nothing consults is this component's commonest
    bug.

    Two things here are worth asserting beyond the obvious:

    * **the entries add**, where `dice_for` takes the first that matches. A
      die is *replaced* and a distance is *increased*, so two feats each
      granting a square grant two. That is the one place the two verbs
      differ and it is easy to copy wrongly.
    * **a second move laid beside the first is not the same thing.** Two
      hops of 1 and 8 are not one hop of 9 the moment anything is in the
      way, which is why this is a modifier and not another `c.teleport`.
      Asserted as a distance, not as two calls.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:reach")
    known = world.need(caster, Powers)

    out.that(c.squares_for("p9999", 8) == 8,
             "with nothing changing it, a row moves what its card prints")

    first = c.extend_move("p9999", 2)
    out.that(first is not None, "a feat lengthens it")
    out.that(c.squares_for("p9999", 8) == 10, "by exactly its two squares")

    second = c.extend_move("p9999", 1)
    out.that(c.squares_for("p9999", 8) == 11,
             "and a second feat ADDS to the first -- 8+2+1. `dice_for` takes"
             " the first match instead, because a die is replaced where a"
             " distance is increased")

    out.that(c.squares_for("p8888", 8) == 8,
             "a different row is untouched -- the control, without which one"
             " feat lengthens every move in the game")

    # The gate.
    c.extend_move("p9999", 5, when=lambda ctx: bool(ctx.get("beside_shroud")))
    out.that(c.squares_for("p9999", 8) == 11,
             "a gated square is absent when its condition is not in the"
             " context")
    out.that(c.squares_for("p9999", 8, {"beside_shroud": True}) == 16,
             "and present when it is")

    # Ending one takes back exactly one.
    if first is not None:
        world.effects.end(first, "driver ended it")
    out.that(c.squares_for("p9999", 8) == 9,
             "ending the first feat's effect takes back its two squares and"
             " leaves the other one -- removed by identity, because two feats"
             " may grant the same number to the same row")
    out.that(len(known.extra_squares.get("p9999", ())) == 2,
             "and the store holds the other two entries, not a stale third")
    _ = second


def conceal_in(out: Result) -> None:
    """A zone that conceals whoever stands in it, which `c.conceal` cannot
    say.

    14 rows print a concealing cloud and every one of them plays with the
    concealment clause missing. `c.conceal` is per-creature and runs on a
    clock, so writing the printed line as a plain `c.conceal` concealed the
    caster's allies **wherever they went, for as long as the duration ran**
    -- a different and much stronger rule than standing inside something.

    The third of a set: `c.cover_in` and `c.ignores_difficult_in` are the
    same sentence for cover and difficult terrain, and all three ride on
    `_while_inside`. #500.

    Three controls, and the first is the whole point of the verb:

    * **outside the zone there is no concealment.** That is the entire
      difference from `c.conceal`, and a check that only asserts the inside
      case passes on the bug this replaces.
    * **a creature walking in later is covered too**, which is why
      `_while_inside` asks per arrival rather than once over the occupants
      standing there when the zone was laid.
    * **the zone ending strips it**, rather than it running out on its own
      clock. A concealment that outlives the cloud is the same fault as the
      per-creature version, just slower to notice.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Position
    from combat_engine.engine.durations import When
    from combat_engine.engine.query import allies, concealment_of
    from combat_engine.engine.types import Cover

    world, caster, _ = _board()
    friend = next((a for a in allies(world, caster) if a != caster), None)
    out.that(friend is not None, "the board has an ally to shelter")
    if friend is None:
        return

    here = world.get(caster, Position).square
    patch = [(here[0] + 1, here[1]), (here[0] + 1, here[1] + 1)]

    # **Stand the ally well clear first.** The first version laid the zone on
    # squares beside the caster and asserted the ally was unconcealed before
    # anything happened -- and it was already standing in one of them, so the
    # control failed on its own setup while every later assertion passed. A
    # control that fails because the board was not arranged says nothing
    # about the verb.
    outside = (here[0] - 4, here[1] - 4)
    world.get(friend, Position).square = outside

    c = Cast(world=world, me=caster, ref="drivers:conceal")
    zone = c.zone(patch, until=When.ENCOUNTER)
    c.conceal_in(zone, side="team")

    # The ally is standing outside it.
    out.that(concealment_of(world, friend) is Cover.NONE,
             "an ally outside the cloud is NOT concealed -- the control, and"
             " the entire difference from `c.conceal`")

    # Walk it in. The grant has to arrive on arrival, not at laying.
    world.get(friend, Position).square = patch[0]
    world.zones.refresh()
    out.that(concealment_of(world, friend) is Cover.PARTIAL,
             "walking into the cloud conceals it, even though the zone was"
             " laid before it arrived")

    # And out again.
    world.get(friend, Position).square = outside
    world.zones.refresh()
    out.that(concealment_of(world, friend) is Cover.NONE,
             "leaving gives it back")

    # In again, then end the zone itself.
    world.get(friend, Position).square = patch[0]
    world.zones.refresh()
    out.that(concealment_of(world, friend) is Cover.PARTIAL, "in again")
    world.zones.end(zone, "driver ended it")
    out.that(concealment_of(world, friend) is Cover.NONE,
             "the zone ending strips it, rather than it running out on its"
             " own clock -- a concealment that outlives the cloud is the"
             " same fault as the per-creature version")


def rerolled(out: Result) -> None:
    """Nothing announced that a roll was a reroll, and 18 rows ride on one.

    "A damage bonus when the reroll lands on your sworn enemy", "combat
    advantage when the forced second attack roll misses", "a slide or a
    shift depending on the parity of the reroll". `c.reroll_attack` took the
    reroll and said neither that one happened nor what it came up. #496.

    It is **two** needs and the rows split roughly 14 to 3:

    * most hang on the settled **outcome** -- the rider pays out when the
      rerolled attack hits or misses -- so they read
      `AttackResult.rerolled_by` off the `Hit`/`Miss`, which survives once
      the dust settles;
    * three modify **the reroll itself** ("a penalty on the roll your racial
      power forces to be made again"), which needs the second roll to be
      gateable. `reroll_attack` recomputes its result inline and re-sums
      nothing, so a `when=` gate on a reroll was never consulted at all.

    The controls here are the point. In order of how easily each gets
    written wrong:

    * **a roll that is not a reroll must announce nothing**, or every attack
      in the game triggers eighteen feats;
    * **a reroll-gated modifier must be absent from the first roll** -- that
      is the entire meaning of the gate, and a modifier that applies to both
      is indistinguishable from an ordinary bonus;
    * **`by` must narrow**, or a feat keyed to one racial power pays out on a
      magic weapon's reroll;
    * **`roll` must discriminate**, or a penalty on a rerolled attack lands
      on a rerolled saving throw;
    * **every d20 reroll path must speak.** Four do. A fifth added later and
      left silent is indistinguishable from a rider that never fires, so the
      count is asserted rather than trusted.
    """
    # Every path that rolls a d20 again has to announce. Counted off the one
    # helper they all go through, so adding a fifth that forgets is visible.
    import inspect

    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import resolve as _resolve
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Mod, Mods
    from combat_engine.engine.events import AttackRolled, Hit, Miss, Rerolled
    from combat_engine.engine.query import enemies
    from combat_engine.engine.triggers import after_reroll_by, rerolled_by
    from combat_engine.engine.types import Defense

    src = inspect.getsource(Cast)
    out.that(src.count("_announce_reroll(") == 5,
             "four d20 reroll paths announce, through one helper -- counted so"
             " a fifth added later cannot be silently missed")

    world, caster, _ = _board()
    foe = sorted(enemies(world, caster))[0]
    seen: list[Rerolled] = []
    world.bus.on(Rerolled, lambda ev: seen.append(ev))

    # -- a roll that is not a reroll --------------------------------------
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:plain")
    out.that(not seen,
             "an ordinary attack announces NO reroll -- the control, and"
             " without it every attack in the game triggers eighteen feats")

    # -- the reroll-gated penalty, absent from the first roll -------------
    mods = world.get(caster, Mods) or world.add(caster, Mods())
    mods.items.append(
        Mod(what="attack", value=-5, label="drivers:reroll",
            when=lambda ctx: bool(ctx.get("reroll")))
    )
    firsts: list[int] = []

    def again(ev: AttackRolled) -> None:
        if ev.attacker != caster or ev.result.rerolled_by:
            return
        firsts.append(ev.result.total)
        hand = Cast(world=world, me=caster, ref="p1450")
        hand.trigger = ev
        hand.reroll_attack(keep="new")

    sub = world.bus.on(AttackRolled, again)
    landed: list[object] = []
    world.bus.on(Hit, lambda ev: landed.append(ev))
    world.bus.on(Miss, lambda ev: landed.append(ev))
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:reroll")
    world.bus.off(sub)

    out.that(len(seen) == 1, "the reroll announced itself once")
    out.that(bool(seen) and seen[0].roll == "attack", "as an attack reroll")
    out.that(bool(seen) and seen[0].by == "p1450",
             "naming the row that bought it, which every rider narrows on")
    out.that(bool(seen) and seen[0].actor == caster, "and the creature rolling")

    settled = landed[-1] if landed else None
    result = getattr(settled, "result", None)
    out.that(result is not None and result.rerolled_by == ["p1450"],
             "the settled outcome remembers it was rerolled, and by what --"
             " which is where 14 of the 18 rows hang")
    out.that(result is not None and len(result.rolls) == 2,
             "and both faces are on record")

    # The gate: -5 on the second roll and not on the first.
    out.that(
        result is not None
        and bool(firsts)
        and result.total == firsts[0] + (result.natural - result.rolls[0]) - 5,
        "the reroll-gated penalty applied to the SECOND roll only -- the"
        " total is the first total, plus the change in the die, minus 5",
    )

    # The gate narrows by *which* row forced the reroll, not merely that one
    # happened: all three rows wanting it say "the reroll your racial power
    # forces". A bare flag would have them modify a magic weapon's reroll too.
    mods.items[:] = [m for m in mods.items if m.label != "drivers:reroll"]
    mods.items.append(
        Mod(what="attack", value=-7, label="drivers:other",
            when=lambda ctx: ctx.get("reroll_by") == "p1452")
    )
    firsts.clear()
    seen.clear()
    sub2 = world.bus.on(AttackRolled, again)
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:narrow")
    world.bus.off(sub2)
    settled2 = landed[-1]
    res2 = settled2.result
    out.that(
        res2.total == firsts[0] + (res2.natural - res2.rolls[0]),
        "a gate naming a DIFFERENT row's reroll does not apply -- the"
        " control, without which one feat's penalty lands on every reroll"
        " on the board",
    )
    mods.items[:] = [m for m in mods.items if m.label != "drivers:other"]
    mods.items.append(
        Mod(what="attack", value=-7, label="drivers:mine",
            when=lambda ctx: ctx.get("reroll_by") == "p1450")
    )
    firsts.clear()
    seen.clear()
    sub3 = world.bus.on(AttackRolled, again)
    _resolve.attack(world, caster, foe, 5, Defense.AC, power="drivers:mine")
    world.bus.off(sub3)
    res3 = landed[-1].result
    out.that(
        res3.total == firsts[0] + (res3.natural - res3.rolls[0]) - 7,
        "and the gate naming p1450, which is the row that rerolled, does",
    )
    mods.items[:] = [m for m in mods.items if m.label != "drivers:mine"]
    ev = seen[0]

    # -- `by` narrows -----------------------------------------------------
    out.that(rerolled_by("p1450")(world, caster, ev) is True,
             "rerolled_by matches the row that bought it")
    out.that(rerolled_by("p1452")(world, caster, ev) is False,
             "and not a different row -- the control, without which a feat"
             " keyed to one racial power fires on any reroll at all")
    out.that(rerolled_by("p1450", roll="save")(world, caster, ev) is False,
             "nor a different kind of roll -- a penalty on a rerolled attack"
             " must not land on a rerolled saving throw")
    out.that(after_reroll_by("p1450")(world, caster, settled) is True,
             "after_reroll_by reads the settled outcome")
    out.that(after_reroll_by("p1452")(world, caster, settled) is False,
             "and narrows there too")

    mods.items[:] = [m for m in mods.items if m.label != "drivers:reroll"]


def boost_roll(out: Result) -> None:
    """"Add 4 to the roll" -- a roll already made, and an outcome already
    decided from it.

    18 rows print this and none could say it. Three neighbours exist and each
    is a different sentence: `c.reroll_attack` and `c.reroll_save` **replace**
    the die, which is a different number whenever the original was already
    good enough with the bonus on it; `c.boost_check` does exactly the right
    thing and only for a skill check; `c.bonus("attack", ...)` is read by the
    next attack, not the one in hand. #495.

    **The end-to-end half is what is actually worth asserting**, and it was
    not obvious it would work. `Miss` is announced after the outcome is
    settled, so a row boosting the roll there is editing a decision already
    taken. `resolve` turns out to handle it: the announcement is emitted in a
    loop that re-announces while `result.hit` keeps changing -- built for
    rerolls, and a boost composes with it unchanged. Asserting the **`Hit`
    arrives** rather than that `result.hit` flipped is the difference between
    testing the verb and testing the engine around it.

    The three negative controls are each a real way to get this wrong:

    * a boost must not manufacture a **critical** -- a crit is off a natural
      20 and `natural` does not move, which is the same distinction
      `AttackResult.treated` records for "treat the roll as odd";
    * a boost must not rescue a **natural 1**, which misses at any total;
    * with **no roll in hand** it must report failure, because returning
      success would make 18 rows look written.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.events import Hit, Miss
    from combat_engine.engine.query import enemies
    from combat_engine.engine.resolve import AttackResult
    from combat_engine.engine.types import Defense

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:boost")

    # No trigger at all.
    out.that(c.boost_roll(4) is False,
             "with no roll in hand it refuses -- the control, since returning"
             " success would make every row of this shape look written")

    class _Rolled:
        def __init__(self, result: AttackResult) -> None:
            self.result = result

    # A miss by 3, boosted by 4, becomes a hit. `natural` must not move.
    res = AttackResult(natural=14, total=15, target_defence=18, hit=False)
    c.trigger = _Rolled(res)
    out.that(c.boost_roll(4) is True, "it boosts an attack roll")
    out.that(res.total == 19, "the total rose by exactly the amount")
    out.that(res.natural == 14, "the die did NOT move -- the card adds to the"
                                " roll, not to what the die showed")
    out.that(res.hit is True, "and 19 against 18 now hits")
    out.that(res.critical is False,
             "without becoming a critical -- the control, and the reason"
             " `natural` is left alone")

    # A natural 1 misses at any total.
    res = AttackResult(natural=1, total=2, target_defence=10, hit=False)
    c.trigger = _Rolled(res)
    c.boost_roll(20)
    out.that(res.hit is False,
             "a natural 1 still misses with +20 on it -- the control")

    # A natural 20 that was already a crit stays one.
    res = AttackResult(natural=20, total=21, target_defence=18,
                       hit=True, critical=True)
    c.trigger = _Rolled(res)
    c.boost_roll(4)
    out.that(res.critical is True and res.hit is True,
             "a critical is not undone by boosting it")

    # **The crit floor is read off the context, not assumed to be 20.**
    # `resolve` judges a hit as `natural >= 20 - crit_range`, so a verb
    # hard-coding 20 judges a boosted roll by a different rule than the one
    # that settled it -- and is wrong only for builds that widen the range,
    # which is the kind of wrong nothing notices.
    from combat_engine.engine.components import Mod, Mods

    mods = world.get(caster, Mods) or world.add(caster, Mods())
    mods.items.append(Mod(what="crit_range", value=1, label="drivers:boost"))
    res = AttackResult(natural=19, total=5, target_defence=30, hit=False)
    c.trigger = _Rolled(res)
    c.trigger.ctx = {"attacker": caster}
    c.boost_roll(1)
    out.that(res.hit is True,
             "a 19 hits a defence of 30 when the build's crit range reaches"
             " 19 -- the floor is read, not assumed")
    mods.items[:] = [m for m in mods.items if m.label != "drivers:boost"]
    res = AttackResult(natural=19, total=5, target_defence=30, hit=False)
    c.trigger = _Rolled(res)
    c.trigger.ctx = {"attacker": caster}
    c.boost_roll(1)
    out.that(res.hit is False,
             "and with the range back to normal the same 19 misses -- the"
             " control, without which the assertion above passes on a verb"
             " that always hits")

    # `kind=` refuses the wrong sort of roll.
    res = AttackResult(natural=14, total=15, target_defence=18)
    c.trigger = _Rolled(res)
    out.that(c.boost_roll(4, kind="save") is False,
             "kind='save' declines an attack roll, so a row cannot boost a"
             " roll its card never mentions")

    # -- a save -------------------------------------------------------------
    class _Save:
        def __init__(self) -> None:
            self.natural, self.bonus, self.saved = 7, 0, False

    ev = _Save()
    c.trigger = ev
    out.that(c.boost_roll(4) is True, "it boosts a saving throw")
    out.that(ev.saved is True, "7 + 4 clears the 10 the rule prints")
    out.that(ev.natural == 7, "and again the die did not move")

    # -- end to end: the Hit has to actually be announced -------------------
    foe = sorted(enemies(world, caster))[0]
    seen: list[str] = []
    world.bus.on(Hit, lambda ev: seen.append("hit"))
    world.bus.on(Miss, lambda ev: seen.append("miss"))

    def rescue(ev: Miss) -> None:
        if ev.attacker != caster:
            return
        # The trigger has to be handed over, which is what `dsl` does for a
        # real row. The first version of this built a bare `Cast` and the
        # boost found no roll in hand -- it reported False and the engine was
        # blameless. A driver asserting the engine must first be a driver
        # that calls the verb the way a row does.
        rescuer = Cast(world=world, me=caster, ref="drivers:boost")
        rescuer.trigger = ev
        rescuer.boost_roll(80, kind="attack")

    sub = world.bus.on(Miss, rescue)
    # A bonus low enough that the attack cannot land on its own, and a boost
    # large enough to clear any defence. **Both numbers had to be checked
    # rather than chosen**: the first pair was -50 and +40, which cannot
    # reach a defence of 13 from a total of -31, so the rule went red on its
    # own arithmetic while the engine was doing exactly the right thing.
    from combat_engine.engine import resolve as _resolve

    _resolve.attack(world, caster, foe, -40, Defense.AC, power="drivers:boost")
    out.that("miss" in seen,
             "the attack missed first, which is the setup and not the finding")
    out.that("hit" in seen,
             "and a `Hit` was then ANNOUNCED -- not merely `result.hit`"
             " flipped. `resolve` re-announces while the outcome keeps"
             " changing, so a boost reaches every rider watching `Hit`")

    world.bus.off(sub)


def recharge_while(out: Result) -> None:
    """A recharge condition that is a **state**, not a moment.

    `recharge_when` takes a `Trigger`, which needs an event to watch. Ten
    cards print a standing condition instead -- "recharges when no creature
    is affected by this power", "when it does not have a creature grabbed" --
    and there is no moment to subscribe to: the last hold goes away when its
    owner saves, or dies, or it expires, or it is suspended, or the creature
    holding it drops. Watching all five routes and re-asking at each is both
    the hard way and the fragile way, because missing one leaves the power
    gone for the rest of the fight and says nothing. #489.

    So it is a predicate re-asked where 4e already asks: at the start of the
    creature's turn, in `actions.recharge`, beside the die.

    **Three things here are negative controls and each one caught something
    in the writing.**

    * A row printing *only* a state has `recharge=0`, and `actions.recharge`
      used to `continue` on exactly that before the predicate could be asked.
      Without the first assertion this whole field would be unreachable on
      nine of its ten rows.
    * The state being false must leave the row spent. Five of these rows had
      their predicate wired to `requires=` instead, which is a different
      sentence -- a usability gate refuses the power *while* the condition
      holds, which no card says.
    * The die is rolled before the state is asked, and that ordering is part
      of the contract: this module records every draw in `Rng.rolls` in
      order, so short-circuiting on a state that happens to be true would
      drop a draw a fixture has already recorded.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import actions
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import get
    from combat_engine.engine.query import enemies, holds_somebody, lingers
    from combat_engine.engine.types import Relation

    ref = "m3101a1"
    p = get(ref)
    out.that(p is not None and p.recharge_while is not None,
             "the row declares a state to recharge on")
    out.that(p is not None and p.recharge == 0,
             "and no die, because its card prints none -- the case the old"
             " `recharge <= 0` gate dropped before asking")

    world, caster, _ = _board(ref, 1)
    known = world.need(caster, Powers)
    known.note_use(ref, world.round)
    out.that(ref in known.spent, "spent")

    # Negative control: the state is false, so the row stays spent.
    victim = sorted(enemies(world, caster))[0]
    world.relations.set(Relation.GRABBED_BY, caster, victim)
    out.that(holds_somebody(world, caster), "it is holding somebody")
    actions.recharge(world, caster)
    out.that(ref in known.spent,
             "holding somebody, the row does NOT come back -- the control,"
             " and without it any predicate at all would look like it worked")

    # Positive: let go, and the next turn gives it back.
    world.relations.clear(Relation.GRABBED_BY, caster, victim, "let go")
    out.that(not holds_somebody(world, caster), "no longer holding anybody")
    actions.recharge(world, caster)
    out.that(ref not in known.spent,
             "holding nobody, the row comes back, which is the printed"
             " sentence")

    # A state that is still false must not hand back a row twice either.
    actions.recharge(world, caster)
    out.that(ref not in known.spent, "and asking again changes nothing")

    # `query.lingers` is the shared predicate for five of the ten, and `by=`
    # is what keeps two of a kind from holding each other's power spent.
    held = get("m461a3")
    out.that(held is not None and held.recharge_while is not None,
             "the charm row reads its own lingering hold")
    out.that(not lingers(world, "m461a3", by=caster),
             "nothing lingering from a row nobody has cast")


def recharge_when(out: Result) -> None:
    """"Recharge when first bloodied" -- a condition, where there was a die.

    440 cards print a recharge condition and no threshold at all, and until
    now the only thing that could give such a row back was
    `actions.recharge`'s d6 -- a die the card never printed. 204 rows carried
    a marker saying so and 169 more armed a watcher by hand from the body.

    **The arming is the design decision worth asserting.** The hand-rolled
    version installs a watcher when the row is *used*, which works and means
    the condition cannot be read without running the row. This asks "is this
    ref spent?" at the moment the event fires, so there is no state to arm,
    nothing to disarm, and the header stays readable by the wire and the
    policy -- which is what `engine/CLAUDE.md` means by "header is data".

    The negative control is the half that matters: a row that was **not**
    spent must not be "restored", and a creature that is not the one bloodied
    must not get its row back from somebody else's crossing.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import get
    from combat_engine.engine.events import Bloodied, Miss
    from combat_engine.engine.query import enemies

    ref = "m6669a2"
    p = get(ref)
    out.that(p is not None and bool(p.recharges),
             "the row declares a printed recharge condition")
    out.that(p is not None and p.recharge == 0,
             "and no die, because its card prints none")

    world, caster, _ = _board(ref, 1)
    known = world.need(caster, Powers)

    # Not spent: the event must not pretend to give anything back.
    world.bus.emit(Bloodied(actor=caster, source=None))
    out.that(ref not in known.spent, "unspent to begin with")

    known.note_use(ref, world.round)
    out.that(ref in known.spent, "spent")

    # Somebody else crossing the line is not this creature's condition.
    other = sorted(enemies(world, caster))[0]
    world.bus.emit(Bloodied(actor=other, source=caster))
    out.that(ref in known.spent,
             "another creature being bloodied does NOT give it back -- the"
             " negative control, and without it `about_me` could read any"
             " actor and still pass")

    world.bus.emit(Bloodied(actor=caster, source=other))
    out.that(ref not in known.spent,
             "being bloodied itself does, which is the printed sentence")

    # And again: `Bloodied` is emitted once per crossing by `resolve`, so
    # "first" needs no extra state here -- but a second emit must not resurrect
    # a row that was never re-spent.
    world.bus.emit(Bloodied(actor=caster, source=other))
    out.that(ref not in known.spent, "a second crossing changes nothing")

    known.note_use(ref, world.round)
    world.bus.emit(Bloodied(actor=caster, source=other))
    out.that(ref not in known.spent,
             "and a row spent again is given back again -- the dispatcher"
             " reads the spent set rather than a one-shot arming")

    # ---- "when it uses <another row>", 14 rows --------------------------
    from combat_engine.engine.events import Hit, PowerUsed

    world, user, _ = _board("m5942a1", 1)
    known = world.need(user, Powers)
    known.note_use("m5942a1", world.round)
    world.bus.emit(PowerUsed(actor=user, power="m5942a1", targets=[]))
    out.that("m5942a1" in known.spent,
             "using the row itself does NOT recharge it -- the card names its"
             " sibling, and a predicate reading only the actor would pass here")
    world.bus.emit(PowerUsed(actor=user, power="m5942a2", targets=[]))
    out.that("m5942a1" not in known.spent,
             "using the row the card names does")

    # ---- "when it hits with <row>", 2 rows, and NOT on a miss ----------
    world, hitter, _ = _board("m2243a3", 1)
    known = world.need(hitter, Powers)
    known.note_use("m2243a3", world.round)
    foe = sorted(enemies(world, hitter))[0]
    world.bus.emit(Miss(attacker=hitter, target=foe, power="m2243a2"))
    out.that("m2243a3" in known.spent,
             "a MISS with the named row does not recharge it -- 'hits with'"
             " is a different sentence from 'uses'")
    world.bus.emit(Hit(attacker=hitter, target=foe, power="m2243a2",
                       critical=False))
    out.that("m2243a3" not in known.spent, "a hit does")

    # `Hit` names the swinger `attacker` and `PowerUsed` names it `actor`,
    # which is why those are two predicates. Asserted, because a single
    # function with a `getattr` fallback would pass every rule above and be
    # silently false on exactly one of the two events.
    from combat_engine.engine.triggers import by_power, hit_with

    ev_hit = Hit(attacker=hitter, target=foe, power="m2243a2", critical=False)
    ev_use = PowerUsed(actor=hitter, power="m2243a2", targets=[])
    out.that(hit_with("m2243a2")(world, hitter, ev_hit),
             "hit_with reads `attacker`, which is what Hit carries")
    out.that(not by_power("m2243a2")(world, hitter, ev_hit),
             "and by_power is false on a Hit -- it reads `actor`, which Hit"
             " does not have. The two are not spellings of each other")
    out.that(by_power("m2243a2")(world, hitter, ev_use),
             "while by_power is true on the event that does carry `actor`")

    # ---- "when an ADJACENT creature becomes bloodied", 3 rows -----------
    #
    # The half that goes wrong silently: `Bloodied` carries both the creature
    # bloodied (`actor`) and whoever struck it (`source`), usually on opposite
    # sides, and `by_somebody_adjacent` reads the striker. Reading the wrong
    # one recharges the row off the wrong body and passes any test that only
    # checks "it came back".
    from combat_engine.engine.query import adjacent
    from combat_engine.engine.triggers import about_somebody_adjacent, by_somebody_adjacent

    world, owner, _ = _board("m1059a1", 1)
    near = next(e for e in sorted(enemies(world, owner)) if adjacent(world, owner, e))
    far = next(e for e in sorted(enemies(world, owner)) if not adjacent(world, owner, e))
    known = world.need(owner, Powers)

    known.note_use("m1059a1", world.round)
    world.bus.emit(Bloodied(actor=far, source=owner))
    out.that("m1059a1" in known.spent,
             "a creature bloodied FAR away does not recharge it")
    world.bus.emit(Bloodied(actor=near, source=owner))
    out.that("m1059a1" not in known.spent,
             "a creature bloodied ADJACENT does")

    ev = Bloodied(actor=far, source=near)
    out.that(not about_somebody_adjacent(world, owner, ev),
             "about_somebody_adjacent reads `actor` -- who was bloodied")
    out.that(by_somebody_adjacent(world, owner, ev),
             "where by_somebody_adjacent reads `source` -- who struck. Same"
             " event, two different creatures, and only one is the card\'s")


def keyword_ban(out: Result) -> None:
    """Two keyword prohibitions that point opposite ways, on one creature.

    Seven rows carried `c.forbid(keyword=)` as one marker and the cards read
    three different sentences:

        keyword=   "cannot use powers that HAVE the polymorph keyword"
                   -- two items, imposed on a target, save ends. `p12344`'s
                   "cannot teleport" is the same shape, different keyword.
        lacking=   "can't use weapon or implement attack powers that LACK
                   the beast form keyword" -- four form rows, self-imposed.

    **Both can be true of one creature at once**, which is why they are two
    sets rather than one inverted into the other, and this asserts that
    directly: a creature barred from polymorph *and* required to carry beast
    form refuses a polymorph power for the first reason and a plain power for
    the second.

    The rule most likely to be dropped is the printed exception --
    *"although you can sustain such powers"* -- and dropping it cancels every
    zone and stance the character was holding when it changed shape.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import get, usable
    from combat_engine.engine.durations import When
    from combat_engine.engine.types import Keyword

    world, me, _ = _board()
    c = Cast(world=world, me=me, ref="drivers:ban")
    known = world.need(me, Powers)

    # The board is built around this ref, so the creature already knows it.
    # `Powers.all` is derived, not a set -- `known` is the list to add to.
    plain = "m145a0"          # no beast form keyword
    if plain not in known.known:
        known.known.append(plain)

    ok, why = usable(world, me, get(plain))
    out.that(ok, f"before any ban the row is usable ({why})")

    # ---- `lacking=`: only keyworded powers allowed --------------------
    held = c.forbid(lacking=Keyword.BEAST_FORM, on=me, until=When.ENCOUNTER)
    out.that(held is not None, "the restriction is laid as an effect")
    ok, why = usable(world, me, get(plain))
    out.that(not ok, f"a row LACKING the keyword is refused ({why})")
    out.that("beast form" in (why or ""),
             "and the reason names the keyword, not a generic refusal")

    bf = get("p16537")
    out.that(bf is not None and Keyword.BEAST_FORM in bf.keywords,
             "p16537 carries the keyword")
    if "p16537" not in known.known:
        known.known.append("p16537")
    ok, _ = usable(world, me, bf)
    out.that(ok, "a row that HAS the keyword is still usable -- the negative"
                 " control, and without it a blanket refusal passes above")

    world.effects.end(held, "driver")
    ok, _ = usable(world, me, get(plain))
    out.that(ok, "ending the restriction gives the plain row back")

    # ---- the sustain exception --------------------------------------
    world, me, _ = _board()
    c = Cast(world=world, me=me, ref="drivers:ban")
    known = world.need(me, Powers)
    if plain not in known.known:
        known.known.append(plain)
    # something of that row is already standing when the shape is taken
    world.effects.apply(me, me, When.ENCOUNTER, label=f"{plain} zone")
    c.forbid(lacking=Keyword.BEAST_FORM, on=me, until=When.ENCOUNTER)
    ok, why = usable(world, me, get(plain))
    out.that(ok,
             "a row already standing when the shape was taken may still be"
             " sustained -- the printed exception, and the half whose absence"
             f" would cancel every zone the character was holding ({why})")

    # ---- `keyword=`: that keyword barred, everything else fine -------
    world, me, _ = _board()
    c = Cast(world=world, me=me, ref="drivers:ban")
    known = world.need(me, Powers)
    if plain not in known.known:
        known.known.append(plain)
    # **A row the keyword actually reaches.** `m145a0` carries no keywords
    # at all, so banning one of them proves nothing -- the first version of
    # this rule banned WEAPON and went red, which is the plant test working
    # on the test rather than on the code. `p16537` carries BEAST_FORM.
    banned = get("p16537")
    if "p16537" not in known.known:
        known.known.append("p16537")
    out.that(banned is not None and Keyword.BEAST_FORM in banned.keywords,
             "p16537 carries the keyword about to be banned")
    ok, _ = usable(world, me, banned)
    out.that(ok, "and is usable before the ban")
    c.forbid(keyword=Keyword.BEAST_FORM, on=me, until=When.SAVE_ENDS)
    ok, why = usable(world, me, banned)
    out.that(not ok, f"barred once the keyword is forbidden ({why})")
    ok, _ = usable(world, me, get(plain))
    out.that(ok, "while a row carrying NO keywords is untouched -- the"
                 " negative control for this direction")

    # ---- both at once, which is why they are two sets ----------------
    c.forbid(lacking=Keyword.POLYMORPH, on=me, until=When.ENCOUNTER)
    out.that(Keyword.BEAST_FORM in known.forbidden_keywords
             and Keyword.POLYMORPH in known.required_keywords,
             "one creature holds a forbidden keyword AND a required one --"
             " a single set could not say which direction each meant")


def exposure(out: Result) -> None:
    """Exposed is not contracted, and the throw comes when the fight ends.

    19 stat blocks print "at the end of the encounter, the target makes a
    saving throw. On a failure, the target contracts `x5_N` (stage 1)", and
    the engine had neither half: `c.contract` catches it outright, and
    nothing happened at the end of an encounter.

    The controls that matter here are the ones separating this from
    `c.contract`:

    * exposure must **not** read as contracted while the throw is owed --
      the tempting shortcut is to record it in one dict and call the
      distinction cosmetic, and `m5100a0`'s trait asks after exactly the
      difference.
    * the throw must fire **only** when the fight ends. `on_end` is handed
      no reason, so an implementation that skips the `effects.closing` check
      settles the disease every time the hold is broken -- including on
      death, which would infect corpses.
    * and it must fire **at all**: an effect laid with no `on_end`, or hung
      on a duration no encounter-end reaches, is a row that silently never
      pays out. #515.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Afflictions
    from combat_engine.engine.query import enemies

    world, me, _ = _board()
    c = Cast(world=world, me=me, ref="drivers:exposure")
    foe = sorted(enemies(world, me))[0]

    laid = c.expose("x5_23", on=foe)
    out.that(laid is not None, "exposure is laid as an effect")
    out.that(c.exposed("x5_23", on=foe, pending=True),
             "the creature is exposed to it, with a throw owed")
    out.that(not c.exposed("x5_23", on=foe),
             "and is NOT yet infected -- the control that separates this from"
             " c.contract, and the whole of what m5100a0 asks after")
    out.that(not c.exposed("x5_34", on=foe, pending=True),
             "and not exposed to a different disease -- the negative control")

    held = world.get(foe, Afflictions)
    out.that(held is not None and held.pending.get("x5_23") == 1,
             "pending at the stage it would be caught at")
    out.that(held is not None and not held.contracted,
             "with nothing in `contracted` while the throw is owed")

    # Exposing twice is one exposure.
    out.that(c.expose("x5_23", on=foe) is None,
             "exposing the same creature to the same disease twice does nothing")

    # **A hold broken early settles nothing.** Without the `closing` check
    # this is where an implementation infects somebody on the wrong signal.
    other = c.expose("x5_34", on=foe)
    assert other is not None
    world.effects.end(other, "broken early, not the fight ending")
    out.that(not c.exposed("x5_34", on=foe),
             "a hold broken early does NOT settle the disease -- `on_end` fires"
             " for every ending alike and only `effects.closing` tells them"
             " apart")
    out.that(not c.exposed("x5_34", on=foe, pending=True),
             "and the exposure is gone rather than left owed forever")

    # Now the fight ends, which is the printed moment. Through
    # `Encounter.finish` and not `effects.end_encounter` directly: the whole
    # claim is that the verb needs no new moment because that chain already
    # exists, and calling the inner half would assume the outer one.
    enc = world.encounter
    out.that(enc is not None, "the board hands back a live encounter to end")
    assert enc is not None

    # **Both branches, forced.** "Either it caught it or it saved" is true of
    # any implementation including one that never rolls, so the outcome is
    # pinned instead: a -30 save cannot succeed and a +30 cannot fail, which
    # makes each half a real assertion rather than a tautology.
    c.expose("x5_44", on=foe, bonus=-30)
    c.expose("x5_51", on=foe, bonus=30)

    from combat_engine.engine.events import SavingThrow

    throws: list[str] = []
    world.bus.on(SavingThrow, lambda ev: throws.append(ev.against))

    enc.finish()

    out.that(not c.exposed("x5_23", on=foe, pending=True),
             "the encounter ending settles the throw, so nothing stays pending")
    out.that("x5_44" in throws and "x5_51" in throws,
             f"a saving throw was actually rolled for each exposure -- {throws}"
             " -- which an implementation that laid the effect and never armed"
             " `on_end` would fail")
    settled = world.get(foe, Afflictions)
    out.that(settled is not None and "x5_44" in settled.contracted,
             "the throw it could not pass contracts the disease")
    out.that(settled is not None and "x5_51" not in settled.contracted,
             "and the throw it could not fail does NOT -- the two halves of"
             " the printed sentence, each pinned so neither can pass by luck")


def short_rest(out: Result) -> None:
    """Five minutes announces itself, once per creature, after the restore.

    `turns.short_rest` was written, correct and silent: it restored
    encounter powers and said nothing, so 17 rows clocked on a rest had no
    moment to hang from.

    The controls are the three ways an implementation of this goes wrong:

    * **once per creature**, not once for the party -- every printed clause
      is about what *you* get back, so a single party-wide event makes every
      listener re-derive who it is about.
    * **after the restore**, because a row answering the rest asks what it
      has available. Emitting first shows it the spent list.
    * **a daily stays spent.** That is the whole distinction between the two
      rests and the thing a restore loop gets wrong by being too eager.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.components import Powers
    from combat_engine.engine.events import ShortRested
    from combat_engine.engine.query import enemies
    from combat_engine.engine.turns import short_rest as rest

    world, me, _ = _board()
    foe = sorted(enemies(world, me))[0]

    heard: list[int] = []
    available_when_heard: list[bool] = []
    mine = world.get(me, Powers)
    assert mine is not None

    # Spend something that comes back, and something that does not.
    mine.note_use("drivers:encounter-power", world.round)
    mine.note_use("drivers:daily-power", world.round)

    def listen(ev: ShortRested) -> None:
        heard.append(ev.actor)
        if ev.actor == me:
            available_when_heard.append(
                "drivers:encounter-power" not in (world.get(me, Powers) or mine).used
            )

    world.bus.on(ShortRested, listen)
    rest(world)

    out.that(bool(heard), "a short rest announces itself at all -- it restored"
                          " powers and said nothing before this")
    out.that(me in heard, "the creature that rested hears its own rest")
    out.that(len(heard) == len(set(heard)),
             f"once each and not twice -- {len(heard)} events for"
             f" {len(set(heard))} creatures")
    out.that(foe in heard,
             "every creature with powers hears it, not only the caster --"
             " a rest is party-wide and the event is per-creature")
    out.that(available_when_heard and available_when_heard[0],
             "the power is already back when the event lands: a row answering"
             " a rest asks what it has, so emitting before the restore would"
             " show it the spent list")


def manoeuvres(out: Result) -> None:
    """The three basic manoeuvres anybody may elect, and what each prints.

    26 rows modify a bull rush, a grab or an aid action and **none of them
    makes one**, so the gap was the manoeuvre rather than a verb. The menu
    offered coup de grace and total defence as first-class actions, had grab
    as a verb nobody could choose, and did not have the other two at all.

    The controls are the printed clauses that an implementation gets wrong
    by being too generous:

    * **bull rush shifts only if the push happened.** "If there's no square
      you can push the target into, your bull rush has no effect" -- so a
      hit against a target with its back to a wall must not walk the
      attacker forward.
    * **aid is scoped to the chosen enemy.** A bare +2 to an ally's next
      attack pays out against anything it swings at, which is wider than
      the card by every other creature on the board.
    * **the aid duration is the aider's next turn**, not the ally's. Two
      different clocks, and the card names the harder one to implement.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.actions import legal
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.query import allies, enemies

    world, me, _ = _board()
    enc = world.encounter
    assert enc is not None
    foe = sorted(enemies(world, me))[0]

    kinds = {a.kind for a in legal(world, enc, me)}
    for kind in ("bull_rush", "grab", "aid_attack", "aid_defence"):
        out.that(kind in kinds,
                 f"{kind} is on the action menu -- it was absent, which is"
                 " what left 26 rows with nothing to modify")

    c = Cast(world=world, me=me, ref="drivers:manoeuvres")

    # **Aid is scoped.** The ally's bonus must answer for the chosen enemy
    # and not for anybody else.
    # **`world.having_team` does not exist.** This read it behind a
    # `hasattr` and fell through to `ally = me`, so "the aided ally gets its
    # +2 against the chosen enemy" was measuring the *aider* -- and the
    # control beneath it compared one creature's bonus against its own. The
    # guard is what hid it: a missing attribute behind `hasattr` is a
    # silently weaker test, never a failing one.
    friends = [a for a in allies(world, me) if a != me]
    assert friends, "the board has no ally to aid"
    ally = friends[0]
    c.aid_attack(foe, ally)
    other = next((f for f in sorted(enemies(world, me)) if f != foe), None)
    hit_chosen = c.total("attack", ally, {"actor": ally, "target": foe})
    out.that(hit_chosen >= 2,
             f"the aided ally gets its +2 against the chosen enemy ({hit_chosen})")
    if other is not None:
        hit_other = c.total("attack", ally, {"actor": ally, "target": other})
        out.that(hit_other < hit_chosen,
                 "and NOT against a different enemy -- the control that keeps"
                 f" aid from being a bonus to everything ({hit_other})")

    # A bull rush against a target it cannot move does nothing to either.
    from combat_engine.engine.components import Position

    was_there = world.get(foe, Position)
    target_before = was_there.square if was_there is not None else None
    mine = world.get(me, Position)
    me_before = mine.square if mine is not None else None
    pushed = c.bull_rush(on=foe)
    mine_after = world.get(me, Position)
    me_after = mine_after.square if mine_after is not None else None

    # **The invariant, which is failable both ways.** Either nothing moved
    # the attacker -- a miss, or a target with nowhere to go -- or it is
    # standing exactly where the target was. Anything else means the shift
    # went somewhere the card does not send it.
    out.that(me_after in (me_before, target_before),
             "after a bull rush the attacker is either where it started or"
             f" in the square the target vacated, never a third place"
             f" (start {me_before}, target was {target_before}, now"
             f" {me_after})")
    if pushed:
        out.that(me_after == target_before,
                 "and on a push that landed, it followed into the vacated"
                 " square -- the second half of the printed Hit line")

    # **The impossible push.** "If there's no square you can push the target
    # into, your bull rush has no effect" -- so the attacker must not walk
    # forward.
    #
    # **This assertion is a guard, not a verified check, and the difference
    # is worth stating.** Three plants failed to make it fail: dropping the
    # push-succeeded return, dropping the did-the-target-actually-move
    # check, and dropping both. The clause survives all three because
    # `c.shift` refuses to enter an occupied square and the target is still
    # standing in it -- so the behaviour is right for a reason one layer
    # below this verb. It would start earning its place the day somebody
    # moves the attacker with `place` instead, which is exactly the change
    # that would break it quietly.
    from combat_engine.engine.movement import place

    width, height = world.grid.width, world.grid.height
    corner = (width - 1, height - 1)
    beside = (width - 2, height - 1)
    place(world, foe, corner)
    place(world, me, beside)
    for _ in range(12):            # push away from `me` is off the map
        stuck_before = world.get(me, Position)
        at = stuck_before.square if stuck_before is not None else None
        c.bull_rush(on=foe)
        now = world.get(me, Position)
        out.that(now is not None and now.square == at,
                 "a bull rush against a target with nowhere to go moves"
                 " nobody -- the printed Impossible Push clause, and the"
                 " one an unconditional shift gets wrong")
        break


def difficult_aura(out: Result) -> None:
    """An aura can be difficult terrain, and "for enemies" is the pair.

    **Nine rows were marked blocked for a field that existed.**
    `Zone.difficult` has always been there and `Zones.create` has always
    taken it; `Zones.aura` did not pass it on, so the only route was making
    the aura and flipping the field by hand -- which one monster helper did,
    documenting the workaround in its own docstring. Found by `triage.py`'s
    first calibration run, which is the whole reason that instrument exists.

    Two rules, and the second is the one that keeps the three theme powers
    honest: the printed line is "difficult terrain **for enemies**", and the
    flag applies to whoever stands there. So the aura is laid difficult for
    everybody and the caster's own side is waived *inside the zone* --
    `c.ignores_difficult_in`, which `c.ignores_difficult` would get wrong by
    exempting the party everywhere.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.zones import Zone

    world, me, _ = _board()
    c = Cast(world=world, me=me, ref="drivers:rough")

    plain = world.get(c.aura(2, label="plain"), Zone)
    rough = world.get(c.aura(2, label="rough", difficult=True), Zone)
    out.that(plain is not None and plain.difficult is False,
             "an ordinary aura is not difficult ground"
             f" ({plain.difficult if plain else None})")
    out.that(rough is not None and rough.difficult is True,
             "and one asked for it is -- the parameter nine rows waited on"
             f" ({rough.difficult if rough else None})")

    # **The waiver is bounded by the zone**, which is the half that keeps
    # the party from ignoring rough ground everywhere on the board.
    # Read off `Movement.ignores`, which is where the exemption lives --
    # there is no `query` reader for it, and `_while_inside` lays the effect
    # on whoever is standing in the zone when it is created.
    from combat_engine.engine.components import Movement

    ring = c.aura(2, label="ringed", difficult=True, on=me)
    c.ignores_difficult_in(ring)
    mine = world.get(me, Movement)
    out.that(mine is not None and mine.ignores,
             "standing inside its own difficult aura, the caster is exempt"
             f" -- the 'for enemies' half ({mine.ignores if mine else None})")


def compelled_walk(out: Result) -> None:
    """A compulsion moves a creature; the creature does not choose.

    **The distinction is the whole verb.** `c.move(toward=)` *ranks* the
    destinations and hands them to `World.decide` -- `_nearest_first` says
    so in as many words, and a real decider still sees every option.
    `c.walk_toward` picks the nearest square itself and never asks, which
    is what "must use a move action to move as close to the attacker as
    possible" and "walks by the most direct route" print. #513.

    So the rule that matters is the **decider never being consulted**: a
    decider rigged to pick the *worst* square must change nothing. A check
    that only asserted the creature ended up closer would pass on
    `c.move(toward=)`, which is the verb this exists to differ from.

    It is still the creature's own move rather than forced movement -- it
    provokes, and it spends the mover's economy, which `c.push` does not.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Position
    from combat_engine.engine.grid import distance
    from combat_engine.engine.movement import place
    from combat_engine.engine.query import enemies

    world, me, _ = _board()
    foe = sorted(enemies(world, me))[0]
    place(world, me, (2, 2))
    place(world, foe, (12, 2))
    c = Cast(world=world, me=me, ref="drivers:compelled")

    before = distance(world.get(me, Position).square,
                      world.get(foe, Position).square)
    c.walk_toward(foe, on=me)
    after = distance(world.get(me, Position).square,
                     world.get(foe, Position).square)
    out.that(after < before,
             f"a compelled walk closes on its target ({before} -> {after})")

    # **The decider gets no vote**, which is the rule `c.move(toward=)`
    # would fail. Rigged to choose the farthest option offered.
    world2, me2, _ = _board()
    foe2 = sorted(enemies(world2, me2))[0]
    place(world2, me2, (2, 2))
    place(world2, foe2, (12, 2))
    asked: list[str] = []

    def contrary(eid: int, what: str, options, why: str):  # noqa: ANN001,ANN202
        asked.append(what)
        return max(options, key=lambda sq: distance(sq, (12, 2)))

    world2.decide = contrary          # type: ignore[assignment]
    c2 = Cast(world=world2, me=me2, ref="drivers:compelled-rigged")
    c2.walk_toward(foe2, on=me2)
    rigged = distance(world2.get(me2, Position).square, (12, 2))
    out.that(rigged == after and "move" not in asked,
             "and a decider rigged to pick the farthest square changes"
             " nothing, because it is never asked -- the half that tells"
             f" this apart from c.move(toward=) ({rigged}, asked {asked})")


def fell_might(out: Result) -> None:
    """The warlock's pact boon: one charge, an extra die, and a trade.

    **This rule passed over a broken mechanism, and that is the finding.**
    Its first version recorded `c.fell_might()` as "never a gap": the boon
    is a row with `usage=ENCOUNTER`, so its charge *is* a use of that
    feature, spent with `c.expend_row`. Wrong, and the rule could not see it
    because it **never armed the trait** -- it called `c.expend_row` straight
    off a fresh board, which is the one state in which the charge is still
    there. In play `turns.arm_traits` spends a trait's single use before
    round 1, so the rider never fired. #529.

    So this now **arms first, then spends**, which is the shape of every
    driver here that has caught something real: set the board up the way
    play does, not the way the verb does. The charge is `c.spend_charge` on
    its own key, and arming is free.

    Four things measured:

    * **arming does not spend the charge**, which is the regression this
      rule exists for and the one it used to be blind to;
    * **the charge is one.** A second spend in the same encounter must
      refuse, which is what `c.spend_charge` returning False is for -- and
      that False is the printed "if you spend" clause.
    * **spending it buys the extra die.** p12887's own rider, which its
      comment had called unwritable for a build that exists.
    * **a feat can forgo that die for something else.** Seven feats print
      it, and the clause has to be *replaced* rather than added beside --
      so the control is that the damage does **not** also land.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.content.features.warlock import FELL
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Build, Health, Powers, Stats
    from combat_engine.engine.query import enemies
    from combat_engine.engine.turns import arm_traits
    from combat_engine.engine.types import Ability

    BOON = "cf:warlock-f1s4"

    def warlock(seed: int = 1):  # noqa: ANN202
        world, me, _ = _board(seed=seed)
        known = world.get(me, Powers) or world.add(me, Powers())
        known.known = (*tuple(known.known), BOON, "p12887")
        # **The leg, or the row gates itself out.** `cf:warlock-f1s4` opens
        # with `c.build("sorcerer-king")` and now carries
        # `requires=on_leg(...)` as well, so a character without the leg is
        # not even armed -- which is the point of the gate and would make
        # this rule measure nothing.
        held = world.get(me, Build) or world.add(me, Build())
        held.choices = (*tuple(held.choices), "sorcerer-king")
        # **Charisma, or the row never hits.** p12887 rolls Cha against
        # Fortitude and the board's creature is a monster with a default
        # ability line, so at +0 every attempt missed and both halves of
        # the damage rule read 0 -- which looked like the trade working.
        stats = world.get(me, Stats) or world.add(me, Stats())
        stats.scores[Ability.CHA] = 24
        return world, me, known

    # **Arming must not spend the charge.** This is the control the old
    # version of this rule lacked, and the reason it passed over a boon
    # nobody could spend.
    world, me, known = warlock()
    c = Cast(world=world, me=me, ref="drivers:fell")
    arm_traits(world, me)
    out.that(c.charge_left(FELL) == 1,
             "arming the trait leaves the charge alone -- the boon's own"
             f" encounter use is spent at arming ({known.used.get(BOON)}),"
             " which is why the charge cannot live there")

    # **One charge an encounter**, after arming, which is the state play is in.
    spends = [c.spend_charge(FELL) for _ in range(2)]
    out.that(spends == [True, False],
             "the pact boon is one charge an encounter -- the second spend"
             f" refuses, and that refusal is the printed clause {spends}")

    # And a cursed kill hands it back.
    out.that(c.restore_charge(FELL),
             "and it comes back when the card says it does -- the regain"
             " `cf:warlock-f1s4` watches for")
    out.that(c.spend_charge(FELL),
             "which leaves it spendable again")

    # **The trade replaces the die rather than joining it.** Measured as
    # damage dealt, with and without a feat that forgoes it.
    # **`variant=1` is how the trade is taken**, which is #479's design: a
    # pre-empted clause fires only when the *use* names the substitution,
    # because the dispatcher offers it as its own menu entry beside taking
    # the printed clause. Written without it first and both runs dealt the
    # same damage -- which read as the trade failing when it was the
    # harness never asking for it.
    #
    # The seed varies too. `_board()` defaults to one, so twenty runs of it
    # are twenty copies of the same fight and `max` over them is a single
    # sample dressed as a spread.
    def hurt(seed: int, traded: bool) -> int:
        from combat_engine.engine.dsl import use

        world, me, _ = warlock(seed)
        # **Arm here too, and this is the half the plant test caught.**
        # Arming was added to the control above and *not* to this helper, so
        # the damage assertions still ran on an unarmed board -- the one
        # state where the old broken mechanism works. Planting `p12887` back
        # onto `c.expend_row` left every number identical and the rule
        # green, which is the original #529 blindness surviving the fix to
        # the rule that was written for it.
        arm_traits(world, me)
        foe = sorted(enemies(world, me))[0]
        if traded:
            Cast(world=world, me=me, ref="drivers:fell-trade").pre_empt(
                "p12887", "fell_might_damage", lambda using: None)
        hp = world.get(foe, Health)
        before = hp.hp if hp is not None else 0
        use(world, me, "p12887", targets=[foe], spend=False,
            variant=1 if traded else 0)
        now = world.get(foe, Health)
        return before - (now.hp if now is not None else 0)

    seeds = range(1, 9)
    plain = [hurt(n, False) for n in seeds]
    traded = [hurt(n, True) for n in seeds]
    out.that(all(t <= q for q, t in zip(plain, traded, strict=True)) and traded != plain,
             "forgoing the extra damage really gives it up, on every seed --"
             " a trade written as an addition would leave the die in"
             f" (kept {plain}, traded {traded})")


def event_provenance(out: Result) -> None:
    """Three more events that did not say which row caused them.

    `Healed.power` was the first of four of the same shape, and these are
    the other three. 21 rows between them, each printing a narrowing the
    event could not answer:

    * **`TempHP.power`** -- "the temporary hit points you gained from your
      rt:r36-t1 racial trait";
    * **`Dropped.power`** -- "whenever you reduce an enemy to 0 hit points
      **with a melee basic attack**", "with a ranged attack";
    * **`SkillCheck.target`** -- "if you successfully intimidate **an
      enemy**", which is a creature rather than a number.

    Each is driven with the same pair that `healed_power` uses: the field
    arrives, and **it is empty when nothing named the cause**. The second
    half is the one that matters -- ongoing damage and a failed death save
    drop a creature with no power behind them, and a History check is
    about a fact and not a creature, so a gate treating empty as a
    wildcard fires on all of those.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import When
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health
    from combat_engine.engine.events import Dropped, SkillCheck, TempHP
    from combat_engine.engine.query import enemies
    from combat_engine.engine.resolve import temp_hp as _temp_hp

    # ---- TempHP.power
    world, me, _ = _board(seed=1)
    seen: list[str] = []
    c = Cast(world=world, me=me, ref="drivers:ward")
    c.watch(TempHP, lambda ev: seen.append(ev.power),
            until=When.ENCOUNTER, on=me, label="drivers:tw")
    c.temp_hp(5, on=me)
    _temp_hp(world, me, me, 9)          # nothing named this one
    out.that(seen == ["drivers:ward", ""],
             "temporary hit points name the row that granted them, and are"
             f" blank when nothing did {seen}")

    # **And there is a term to raise them by**, which several of the same
    # rows needed after the power: `resolve.temp_hp` consulted `Mods` for
    # nothing, so "+2 to the number of temporary hit points you gain" had
    # no number to add to. Read off the *receiver*, since the printed line
    # is about the creature gaining them.
    world, me, _ = _board(seed=1)
    c = Cast(world=world, me=me, ref="drivers:ward2")
    c.bonus("temp_hp", 3, on=me, until=When.ENCOUNTER, kind="feat")
    c.temp_hp(5, on=me)
    got = world.get(me, Health).temp
    out.that(got == 8,
             f"a +3 to temporary hit points makes a printed 5 arrive as {got}")

    # ---- Dropped.power
    world, me, _ = _board(seed=1)
    fell: list[str] = []
    c = Cast(world=world, me=me, ref="drivers:slay")
    c.watch(Dropped, lambda ev: fell.append(ev.power),
            until=When.ENCOUNTER, on=me, label="drivers:dw")
    foe = sorted(enemies(world, me))[0]
    c.kill(on=foe)
    out.that(fell == ["drivers:slay"],
             "a kill names the row that struck the blow, which seven rows"
             f" need to say 'with a melee basic attack' {fell}")

    world, me, _ = _board(seed=1)
    fell = []
    c = Cast(world=world, me=me, ref="drivers:slay2")
    c.watch(Dropped, lambda ev: fell.append(ev.power),
            until=When.ENCOUNTER, on=me, label="drivers:dw2")
    other = sorted(enemies(world, me))[0]
    hp = world.get(other, Health)
    hp.hp = 1
    from combat_engine.engine.resolve import _check_down
    hp.hp = 0
    _check_down(world, other, hp)       # ongoing damage, no power
    out.that(fell == [""],
             "and a creature that drops with nothing behind it -- ongoing"
             f" damage, a failed save -- names no row {fell}")

    # ---- SkillCheck.target
    world, me, _ = _board(seed=1)
    asked: list[object] = []
    c = Cast(world=world, me=me, ref="drivers:lean")
    c.watch(SkillCheck, lambda ev: asked.append(ev.target),
            until=When.ENCOUNTER, on=me, label="drivers:sw")
    foe = sorted(enemies(world, me))[0]
    c.check("intimidate", 10, against=foe)
    c.check("history", 10)
    out.that(asked == [foe, None],
             "a check names the creature it was made against, and leaves it"
             f" None for a check about a fact {asked}")


def healed_power(out: Result) -> None:
    """Which row did the healing, which `Healed` did not say.

    Ten rows print a rider on *some* heals and not others -- "the hit
    points regained by your cleric healing powers", "each character healed
    by one of your encounter or daily powers", "the amount healed by
    p1455" -- and the event carried who healed whom and the number, with
    no way to tell one heal from another.

    Three controls, and the second is the one a careless gate gets wrong:

    * **a heal from a row announces that row's ref**;
    * **a heal nothing named announces `""`**, and a gate on a particular
      ref must not fire on it. Empty is not a wildcard: treating it as one
      would make a short rest read as every power at once;
    * **the rider can still change the amount**, because `resolve.heal`
      announces before the hit points go on and that seam is what every
      one of the ten rows needs. A field nobody can act on at the right
      moment would be no use.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import When
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health
    from combat_engine.engine.events import Healed
    from combat_engine.engine.resolve import heal as _heal

    world, me, _ = _board(seed=1)
    hurt = world.get(me, Health)
    hurt.hp = max(1, hurt.max_hp - 20)

    seen: list[tuple[str, int]] = []
    c = Cast(world=world, me=me, ref="drivers:cure")
    c.watch(Healed, lambda ev: seen.append((ev.power, ev.amount)),
            until=When.ENCOUNTER, on=me, label="drivers:watch")

    c.heal(5, on=me)
    out.that(seen and seen[-1][0] == "drivers:cure",
             "a heal announces the row that did it, which ten rows needed"
             f" and the event never said {seen[-1:]}")

    # **Nothing named it.** `resolve.heal` straight, as a rest or a bare
    # surge reaches it.
    _heal(world, me, me, 3)
    out.that(seen[-1][0] == "",
             "a heal nothing named announces an empty ref, so a gate on one"
             f" particular row does not fire on it {seen[-1:]}")

    gated = [p for p, _ in seen if p == "drivers:cure"]
    out.that(len(gated) == 1,
             "which is the gate working: one of the two heals matches the"
             f" ref and the other does not ({len(gated)} of {len(seen)})")

    # **The seam still works.** A rider adds before the hit points go on.
    world, me, _ = _board(seed=1)
    hurt = world.get(me, Health)
    hurt.hp = max(1, hurt.max_hp - 20)
    before = hurt.hp
    c = Cast(world=world, me=me, ref="drivers:cure")

    def more(ev: Healed) -> None:
        if ev.power == "drivers:cure":
            ev.amount += 4

    from combat_engine.engine.types import Window
    c.watch(Healed, more, until=When.ENCOUNTER, window=Window.BEFORE,
            on=me, label="drivers:more")
    c.heal(5, on=me)
    got = world.get(me, Health).hp - before
    out.that(got == 9,
             "and a rider keyed on that ref still adds before the hit"
             f" points go on -- 5 printed became {got}")


def reach_stretch(out: Result) -> None:
    """"The target's reach increases by 1", on the rows that print a weapon.

    The modifier was written, stored and **read**, and then discarded by
    the one function that decides what a melee or ranged power can touch.
    `area_of` computed the stretch, added it to `r.size` and called
    `_reach_of`, which answers a by-weapon range off the weapon in hand and
    never looked at `r.size`. #533.

    That is the common path, not an edge: 1,023 melee rows print "melee
    weapon" against 325 with a fixed number, and `mba` is on it -- so the
    melee basic attack ignored a reach bonus entirely.

    Four controls:

    * **a by-weapon melee row stretches**, which is the fix;
    * **it does not stretch without a modifier**, the negative control --
      otherwise this passes on a build that simply reaches one further;
    * **a fixed-range melee row stretches too but does not inherit the
      weapon's reach.** `_reach_of` guards that case deliberately, because
      "Melee touch" must not grow in a glaive's hand, and a careless fix
      here would have flattened the guard;
    * **`_within_reach` agrees with the area.** This is the half the issue
      called the second bug: that function calls `_reach_of` without a
      stretch and applied one nowhere else, so the modifier reached the
      squares a power *offered* and not the question "may I reach that
      creature".
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import When
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.dsl import BY_WEAPON, REGISTRY, _reach_of

    by_weapon = "mba"
    fixed = next(
        (r for r, p in REGISTRY.items()
         if p.reach.kind == "melee"
         and not getattr(p.reach, "by_weapon", False)
         and r not in BY_WEAPON),
        "",
    )

    def reach_of(ref: str, *, plus: int) -> int:
        world, me, _ = _board(seed=1)
        c = Cast(world=world, me=me, ref="drivers:reach")
        if plus:
            c.bonus("reach", plus, on=me, until=When.ENCOUNTER, kind="power")
        declared = REGISTRY.get(ref)
        assert declared is not None, ref
        return _reach_of(world, me, declared.reach_of(0), ref)

    plain = reach_of(by_weapon, plus=0)
    stretched = reach_of(by_weapon, plus=1)
    out.that(stretched == plain + 1,
             "a +1 to reach reaches one further on a by-weapon melee row --"
             f" `{by_weapon}` goes {plain} -> {stretched}, and this is the"
             " row the melee basic attack is")

    out.that(plain == reach_of(by_weapon, plus=0),
             "and reaches no further with no modifier laid, which is the"
             f" negative control ({plain})")

    if fixed:
        a, b = reach_of(fixed, plus=0), reach_of(fixed, plus=1)
        out.that(b == a + 1 and a == REGISTRY[fixed].reach_of(0).size,
                 "a fixed-range melee row stretches as well and still does"
                 f" not inherit the weapon's reach -- {fixed} is {a} printed"
                 f" and {b} stretched, which is the guard `_reach_of` keeps")

    # **The reach question, not the area question.** `_within_reach` is a
    # different call site and had no stretch of its own.
    from combat_engine.engine.dsl import _within_reach
    world, me, _ = _board(seed=1)
    from combat_engine.engine.components import Position
    from combat_engine.engine.query import enemies, squares
    foe = sorted(enemies(world, me))[0]
    here = sorted(squares(world, me))[0]
    world.get(foe, Position).square = (here[0] + 2, here[1])
    declared = REGISTRY[by_weapon]
    c = Cast(world=world, me=me, ref="drivers:reach")
    before = _within_reach(world, me, declared, foe)
    c.bonus("reach", 2, on=me, until=When.ENCOUNTER, kind="power")
    after = _within_reach(world, me, declared, foe)
    out.that(not before and after,
             "and a creature two squares off is out of reach until a +2 to"
             f" reach says otherwise ({before} then {after}) -- the half"
             " that asks 'may I reach it' rather than 'what do I cover'")


def shield_bonuses(out: Result) -> None:
    """A shield's contribution to AC, as a number a row can read.

    Nine rows wanted it and none could ask. The shield's bonus is folded
    into the AC the sheet is built with, and `Gear.shield` was a bare
    `bool` -- so "your shield bonus also applies to Fortitude", "raises the
    light shield's bonus by one" and "trade the shield's bonus to AC and
    Reflex for damage" had nothing to read.

    **The kind was known the whole time and thrown away at one boundary.**
    The class line records 0, 1 or 2 and says so in its own comment;
    `chargen` wrote `shield=bool(carried_shield)` into `Gear`. So the fix
    was a widened field and a dropped `bool()`, not a new mechanism -- and
    the control that matters is the second one below, because a reader that
    works on a hand-set component and never sees a real character is the
    shape this file has been caught by before.

    Three things:

    * **the number comes from the database**, light 1 and heavy 2, not from
      a literal in the engine;
    * **a built character carries its kind through**, which is the half
      that was lost;
    * **no shield is 0**, so a row trading the bonus away trades nothing.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.components import Gear
    from combat_engine.engine.query import shield_bonus

    world, me, _ = _board(seed=1)
    gear = world.get(me, Gear) or world.add(me, Gear())
    seen = {}
    for kind in (0, 1, 2):
        gear.shield = kind
        seen[kind] = shield_bonus(world, me)
    out.that(seen == {0: 0, 1: 1, 2: 2},
             "a light shield reads 1 and a heavy one 2, off the armour"
             f" table rather than a literal {seen}")

    # **A real character off the chargen path, not a hand-set component.**
    # `chargen.spawn` is where the kind was being flattened, so a reader
    # proven only against a component this rule set itself would have
    # passed straight over the actual fault.
    from combat_engine.chargen import Character, spawn
    kinds: dict[str, int] = {}
    for cls in ("fighter", "paladin", "warden"):
        who = Character(cls=cls, level=1)
        eid = spawn(world, who, (1, 1))
        held = world.get(eid, Gear)
        kinds[cls] = int(getattr(held, "shield", 0) or 0)
    # **Assert a *heavy* shield, not merely a shield.** Written as
    # `any(v > 0)` first and the plant test went green: `bool(2)` is True
    # and `int(True)` is 1, so the old flattening turns every heavy shield
    # into a light one and still passes a "carries something" check. The
    # distinguishable value is the whole point of widening the field.
    out.that(2 in kinds.values(),
             "and a character built through `chargen.spawn` carries a"
             " *heavy* shield as 2 -- flattening it to a bool reads 1 here"
             f" and would silently downgrade every one {kinds}")

    gear.shield = 0
    out.that(shield_bonus(world, me) == 0,
             "while a creature with no shield reads 0, so a row trading the"
             " bonus away trades nothing")


def ability_checks(out: Result) -> None:
    """A raw ability check, which is not a skill check.

    Fourteen rows carried a marker saying so -- `i1385x1`'s note was "a raw
    ability check is not a skill check and nothing rolls one" -- and the
    cards keep the two apart: one prints "ability check or skill check" as
    two separate things.

    Four things, and the last two are the ones that would be easy to get
    wrong:

    * **it rolls and totals** ability modifier plus half level;
    * **a DC decides success**, and a `dc` of 0 always succeeds, as
      `c.check` does;
    * **a skill rider does not fire on it.** `my_check("athletics")` must
      not match a Strength check -- which is exactly what folding this into
      `check()` under an invented skill name would have done;
    * **an ability-check bonus does apply**, so the modifier keys have a
      reader. A modifier nothing consults is this component's commonest
      bug and `lint.py` keeps a list of the spellings it has caught.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import When
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Stats
    from combat_engine.engine.types import Ability

    def roller():  # noqa: ANN202
        world, me, _ = _board(seed=1)
        stats = world.get(me, Stats) or world.add(me, Stats())
        stats.scores[Ability.STR] = 20          # +5
        return world, me, Cast(world=world, me=me, ref="drivers:check")

    world, me, c = roller()
    got = c.ability_check(Ability.STR)
    half = (world.get(me, Stats)).half_level
    out.that(got.total == got.natural + 5 + half,
             "a Strength check is the die plus the ability modifier plus"
             f" half level ({got.natural} + 5 + {half} = {got.total})")

    world, me, c = roller()
    easy = c.ability_check(Ability.STR, 0)
    out.that(bool(easy),
             "a check with no DC always succeeds, as `c.check` does"
             f" ({easy.total} against 0)")

    # **A skill rider must not hear it.** The negative control.
    world, me, c = roller()
    heard: list[str] = []
    from combat_engine.engine.events import SkillCheck
    from combat_engine.engine.triggers import my_check
    c.watch(SkillCheck,
            lambda ev: heard.append(ev.skill)
            if my_check("athletics")(world, me, ev) else None,
            until=When.ENCOUNTER, on=me, label="drivers:athletics")
    c.ability_check(Ability.STR)
    out.that(not heard,
             "and a rider watching for an Athletics check does not fire on"
             f" a Strength check -- the two are different rolls {heard}")

    # **An unnamed check rider must hear it**, which is the positive half of
    # the control above and is what five rows' markers came off on. Those
    # rows print "an attack roll, a skill check, or an ability check" and
    # already declared `Trigger(SkillCheck, my_check(), ...)`; naming no
    # skill means any check, so the ability arm needed no second entry and
    # no code. If this goes red those five rows are silently short a clause.
    world, me, c = roller()
    any_check: list[str] = []
    c.watch(SkillCheck,
            lambda ev: any_check.append(ev.skill)
            if my_check()(world, me, ev) else None,
            until=When.ENCOUNTER, on=me, label="drivers:anycheck")
    c.ability_check(Ability.STR)
    out.that(any_check == ["ability:str"],
             "while a rider watching for *any* check does hear it, which is"
             " how five rows printing 'a skill check or an ability check'"
             f" need no second trigger {any_check}")

    # And the modifier keys have a reader.
    world, me, c = roller()
    c.bonus("ability_check", 3, on=me, until=When.ENCOUNTER, kind="power")
    boosted = c.ability_check(Ability.STR)
    base = (world.get(me, Stats)).half_level + 5
    out.that(boosted.total == boosted.natural + base + 3,
             "while a bonus to ability checks is read, so the key is not a"
             f" modifier nothing consults ({boosted.total})")


def unpreventable(out: Result) -> None:
    """"This damage cannot be reduced or prevented in any way."

    Ten cards print it. Most are a **price the character elects to pay** --
    hit points for an ally's healing, for pulling an attack onto itself,
    for raising a weapon's damage -- and the clause exists so the payer
    cannot dodge the bill and keep what it bought. `i696p1` is the
    clearest, since the target takes double what the wielder took, so
    resisting your own cost would double the profit.

    **Two are not a self-cost, and writing the rows found it:** `i2056p1`
    deals five necrotic to an *enemy* ending its turn adjacent, precisely
    to go through that enemy's necrotic resistance, and `i3376p1` charges
    an *ally* who volunteers. The flag is about the damage, not about who
    takes it -- which is why the controls below test an ordinary foe and
    not a self-inflicted cost.

    Three things measured:

    * **resistance does not touch it**, which is the clause;
    * **resistance still works on an ordinary blow of the same type and
      size**, which is the negative control. Without it this passes on an
      implementation that broke resistance altogether -- and resistance
      being read for one type and silently skipped for another is a fault
      this file has already recorded once;
    * **immunity does not stop it either.** "Prevented" is the stronger
      half of the printed pair and immunity is what prevents; a check on
      resistance alone would miss it.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defences, Health
    from combat_engine.engine.query import enemies
    from combat_engine.engine.types import DamageType

    def hurt(*, resist: int = 0, immune: bool = False, free: bool) -> int:
        world, me, _ = _board(seed=1)
        foe = sorted(enemies(world, me))[0]
        shield = world.get(foe, Defences) or world.add(foe, Defences())
        shield.resist = dict(getattr(shield, "resist", {}) or {})
        shield.immune = set(getattr(shield, "immune", set()) or set())
        if resist:
            shield.resist[DamageType.FIRE] = resist
        if immune:
            shield.immune.add(DamageType.FIRE)
        hp = world.get(foe, Health)
        before = hp.hp
        Cast(world=world, me=me, ref="drivers:cost").flat(
            10, dtype=DamageType.FIRE, unpreventable=free, on=foe)
        return before - world.get(foe, Health).hp

    plain = hurt(resist=4, free=False)
    out.that(plain == 6,
             "resistance takes its 4 off an ordinary blow of 10 -- the"
             f" negative control, without which this rule would pass on a"
             f" build that had simply stopped reading resistance ({plain})")

    free = hurt(resist=4, free=True)
    out.that(free == 10,
             "and an unpreventable 10 lands whole through resist 4, which is"
             f" the printed clause ({free})")

    walled = hurt(immune=True, free=False)
    blown = hurt(immune=True, free=True)
    out.that(walled == 0 and blown == 10,
             "while immunity stops an ordinary blow dead and does not stop"
             f" an unpreventable one -- 'prevented' is the stronger half of"
             f" the pair ({walled} then {blown})")


def zone_exempt(out: Result) -> None:
    """A cloud that blinds everybody except the creature that made it.

    Eight monster cards print exactly that, and all eight laid the zone and
    dropped the exemption -- which **inverts the ability**: the point of the
    card is that its owner sees through its own darkness and nobody else
    does. `blocks_sight` is terrain, binary and symmetric, with nothing to
    carve out of it.

    **Two things about the board had to be fixed before this measured
    anything**, and both made it look like the code was wrong:

    * every creature `_board` deals stands *adjacent* to the caster, so
      there is no square between anybody and a fog laid between them covers
      nothing. The first version read `Cover.NONE` everywhere.
    * with the foe moved away, the other creatures are still standing on the
      line, and a creature gives `Cover.PARTIAL` -- a different mechanism
      with the same units. Every case then read 2 whether the exemption
      worked or not. So the line is cleared, and the zone is the only thing
      between.

    A third trap was in the assertion rather than the board: `cover_between`
    returns an `IntEnum`, and `is Cover.SUPERIOR` is False for the equal
    integer. That is a **false pass** -- the exempt case "passed" while the
    exemption was doing nothing. Compared with `==`.

    Three controls:

    * **the exempt creature sees through it** -- the clause eight rows had
      dropped;
    * **everybody else is still blinded**, the negative control. `query.py`'s
      own comment records that `blocks_sight` was once stored and read by
      nothing, so a zone that blocks nothing is a real failure mode here;
    * **the exemption is about the looker, not the target.** Exempting only
      the target must leave the attacker blinded: the card says the exempt
      creature can see out, not that others can see it.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Position
    from combat_engine.engine.query import cover_between, enemies, squares
    from combat_engine.engine.types import Cover

    def board_with(exempt_who: str):  # noqa: ANN202
        """Two creatures six squares apart with only a fog between them.

        `exempt_who` is "owner", "target" or "nobody".
        """
        world, me, _ = _board(seed=1)
        foe = sorted(enemies(world, me))[0]
        here = sorted(squares(world, me))[0]
        far = (here[0] + 6, here[1])
        world.get(foe, Position).square = far
        # Clear the line. A creature standing between gives PARTIAL cover of
        # its own, which reads in the same units as the zone's and hid the
        # result entirely in the first version of this rule.
        for other in sorted(enemies(world, me)):
            if other != foe:
                spot = world.get(other, Position)
                if spot is not None:
                    spot.square = (here[0], here[1] + 9)
        # **And clear the target's carried cover.** `cover_between` ends with
        # `max(traced, _carried_cover(target))`, and the dealt creature holds
        # a `cover` modifier -- so every case read PARTIAL whatever the zone
        # did. Three board artifacts in one rule, each of which looked like
        # the implementation failing.
        from combat_engine.engine.components import Mods
        held = world.get(foe, Mods)
        if held is not None:
            held.items = type(held.items)()
        # **Three rows thick, because `Grid.cover` traces corner to corner.**
        # A single row of fog across the line still leaves the corner traces
        # above and below it clear, which is PARTIAL and not SUPERIOR -- so a
        # one-row zone could not be told apart from the board's own terrain.
        area = frozenset(
            (x, here[1] + dy)
            for x in range(here[0] + 1, here[0] + 6)
            for dy in (-1, 0, 1)
        )
        who = {me} if exempt_who == "owner" else (
            {foe} if exempt_who == "target" else set())
        Cast(world=world, me=me, ref="drivers:fog").zone(
            area, label="drivers:fog", blocks_sight=True, exempt=who)
        return world, me, foe

    # **The baseline is PARTIAL, not NONE, and that is the board rather than
    # the zone.** `Grid.cover` consults its own terrain, and this line
    # already has some of it -- measured by tracing with no blockers at all.
    # So the thing to assert is that the fog takes a non-exempt looker to
    # SUPERIOR and leaves an exempt one where the terrain put them.
    world, me, foe = board_with("nobody")
    blind = cover_between(world, me, foe)
    out.that(blind == Cover.SUPERIOR,
             "a sight-blocking zone between two creatures blinds the looker"
             f" -- the negative control, and it reads {blind!r}")

    world, me, foe = board_with("owner")
    seen = cover_between(world, me, foe)
    out.that(seen < Cover.SUPERIOR,
             "and the creature the card exempts sees through its own cloud"
             f" ({seen!r} -- the terrain's own cover, not the fog's), which"
             " is the clause eight rows had dropped")

    world, me, foe = board_with("target")
    still = cover_between(world, me, foe)
    out.that(still == Cover.SUPERIOR,
             "while exempting only the target leaves the looker blinded --"
             " the exemption is about who is looking, not who is looked at"
             f" ({still!r})")


def points_regained(out: Result) -> None:
    """A power point put *back*, which nothing on the surface could say.

    `c.regain_points` closed eight markers, and the interesting half is
    what it **refuses**: it caps at the pool's maximum. That cap is not a
    detail, it is the reason three of those eight rows were re-pointed
    instead of written -- `f3389`, `f3625` and `i1793p1` all create a point
    *over* the ceiling, so the new verb would hand a full-pool character
    nothing. If the cap were dropped to make those rows pass, they would be
    silently wrong rather than honestly marked, so it is measured here.

    Three things:

    * **a spent point comes back**, which is the eight rows' printed line;
    * **a full pool regains nothing**, which is the cap, and is why three
      rows still carry a marker;
    * **`c.transfer_points` still refuses self-targeting**, which is the
      verb the marker originally named. It returning 0 is what made a
      self-regain unsayable, and it must keep returning 0 -- a transfer to
      yourself would be free points.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import PowerPoints

    world, me, _ = _board(seed=1)
    pool = world.get(me, PowerPoints) or world.add(me, PowerPoints())
    pool.maximum, pool.points = 3, 1
    c = Cast(world=world, me=me, ref="drivers:points")

    got = c.regain_points(2)
    out.that(got == 2 and pool.points == 3,
             "a spent power point comes back, which is what eight rows"
             f" printed and nothing could say (regained {got}, pool"
             f" {pool.points})")

    again = c.regain_points(2)
    out.that(again == 0 and pool.points == 3,
             "and a full pool regains nothing -- the cap three re-pointed"
             f" rows depend on (regained {again}, pool {pool.points})")

    # Measured as a *delta*, not against the literal 3. Written as
    # `pool.points == 3` first, which made this assertion fail whenever the
    # cap above was broken -- two red lines for one fault, and the second
    # one's message blamed transfers. An assertion that only holds while
    # its neighbours do is not an independent measurement.
    before = pool.points
    moved = c.transfer_points(1)
    out.that(moved == 0 and pool.points == before,
             "while a transfer to yourself is still refused, which is the"
             " verb the markers first named and the reason a self-regain"
             f" had to exist (moved {moved}, pool {before} -> {pool.points})")


def boon_traded(out: Result) -> None:
    """A feat replaces the pact boon's regain with a power point.

    `f3232` is the row, and the whole of it is one `c.pre_empt`. Three
    things had to be true at once and each had been written down as
    impossible at some point:

    * the charge is **not** the boon row's encounter use, which
      `turns.arm_traits` spends before round 1 (#529);
    * `c.regain_points()` exists -- `c.transfer_points` refuses
      self-targeting and returns 0, so there was genuinely nothing to call;
    * `cf:warlock-f1s4` offers its regain as a named clause through
      `c.instead_of_now`, because the regain fires inside a watcher that row
      installed and `c.variant` is therefore 0 for ever.

    **The negative control is the whole rule.** Asserting only that a point
    arrives would pass on an implementation that pays the point *and* hands
    the charge back -- which is the "written without it, the row pays twice"
    the old docstring predicted. So the measurement is both sides: with the
    feat the charge stays spent and a point arrives; without it the charge
    comes back and no point does.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.content.features.warlock import FELL
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Build, PowerPoints, Powers
    from combat_engine.engine.events import Dropped
    from combat_engine.engine.query import enemies
    from combat_engine.engine.turns import arm_traits
    from combat_engine.engine.types import Relation

    BOON = "cf:warlock-f1s4"

    def play(with_feat: bool) -> tuple[int, int]:
        """Returns (charge left after a cursed kill, points gained)."""
        world, me, _ = _board(seed=1)
        known = world.get(me, Powers) or world.add(me, Powers())
        refs = [BOON, "p12887", *(["f3232"] if with_feat else [])]
        known.known = (*tuple(known.known), *refs)
        held = world.get(me, Build) or world.add(me, Build())
        held.choices = (*tuple(held.choices), "sorcerer-king")
        # A pool with room in it, or `c.regain_points` correctly returns 0
        # for a full one and the trade would read as not happening.
        pool = world.get(me, PowerPoints) or world.add(me, PowerPoints())
        pool.maximum, pool.points = 2, 0
        arm_traits(world, me)

        c = Cast(world=world, me=me, ref="drivers:boon")
        c.spend_charge(FELL)
        foe = sorted(enemies(world, me))[0]
        world.relations.set(Relation.CURSED_BY, me, foe)
        world.bus.emit(Dropped(actor=foe))
        return c.charge_left(FELL), pool.points

    left_with, points_with = play(True)
    out.that(left_with == 0 and points_with == 1,
             "with the feat the charge stays spent and a power point"
             f" arrives instead (charge {left_with}, points {points_with})")

    left_without, points_without = play(False)
    out.that(left_without == 1 and points_without == 0,
             "and without it the printed clause is untouched -- the charge"
             f" comes back and no point does (charge {left_without},"
             f" points {points_without})")


def lent_augments(out: Result) -> None:
    """A feat lends a power an Augment line the card does not print.

    Four feats print "your <power> gains the augmentable keyword. When you
    would use it, you can spend 1 power point to <effect>". The effect is
    the *feat's*, so it belongs neither in the power's header nor in its
    body -- `c.lend_augment` records it against the character and
    `content.powers.augment.lent` is what the lent-to row asks.

    **Not `Power.augments`**, which the action menu reads before any body
    runs. Threading the holder through that surface would make header data
    holder-dependent, which is the rule #507 turned on; all four clauses
    are body-sayable, so the spend happens at body time instead.

    Three things measured, and the third is the control that matters:

    * **the point is actually spent**, so a lent augment is not free;
    * **the clause runs**, which is the "both halves" rule -- a lend on a
      row that never calls `lent` is a modifier nothing consults;
    * **a character without the feat is offered nothing**, which is the
      half an implementation that put the augment on the header would get
      wrong for every holder of the power.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import PowerPoints, Powers
    from combat_engine.engine.dsl import use
    from combat_engine.engine.durations import When

    def board(lend: bool):  # noqa: ANN202
        world, me, _ = _board()
        world.add(me, PowerPoints(points=4))
        known = world.get(me, Powers) or world.add(me, Powers())
        known.known = (*tuple(known.known), "p1450")
        c = Cast(world=world, me=me, ref="drivers:lent")
        ran = []
        if lend:
            c.lend_augment("p1450", 1, lambda _use: ran.append(1),
                           on=me, until=When.ENCOUNTER)
        return world, me, ran

    # **With the feat**: the point goes and the clause runs.
    world, me, ran = board(True)
    use(world, me, "p1450", targets=[me], spend=False)
    left = (world.get(me, PowerPoints) or PowerPoints()).points
    out.that(left == 3,
             f"using the lent-to row spends the point, so the augment is not"
             f" free (4 -> {left})")
    out.that(ran == [1],
             "and the feat's own clause runs -- the half a lend on a row"
             f" that never asks gets wrong {ran}")

    # **Without it**: nothing offered, nothing spent.
    world2, me2, ran2 = board(False)
    use(world2, me2, "p1450", targets=[me2], spend=False)
    left2 = (world2.get(me2, PowerPoints) or PowerPoints()).points
    out.that(left2 == 4 and not ran2,
             "a character without the feat is offered nothing and pays"
             " nothing -- the control an augment written into the power's"
             f" header would fail for every other holder ({left2}, {ran2})")


def counts_as_basic(out: Result) -> None:
    """"Counts as a basic attack" and "in place of" are different sentences.

    Camille's wording, which is the whole of #522: *"'In place of a melee
    basic attack' means it could be used when a melee basic attack could be
    used, but it is NOT a melee basic attack. 'Counts as' or 'can be used
    as' a basic attack means that it would benefit from modifiers to basic
    attacks."*

    **The negative control is the rule that matters**, and it is the second
    one below. A check asserting only that the designation works passes on
    an implementation that conflated the two -- which is the bug this
    driver exists for. So a row registered with `c.as_basic` is asserted to
    be offered where a swing is granted **and** to be absent from
    `basics_of`, which is what a basic-attack modifier reads.

    Nine content rows declare `basic=` in their headers. `p1333` is the one
    used here because its card is the clearest case of the phrase.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import (
        REGISTRY,
        basic_options,
        basics_of,
        use,
    )
    from combat_engine.engine.events import AttackRolled
    from combat_engine.engine.query import enemies

    world, me, _ = _board()
    known = world.get(me, Powers) or world.add(me, Powers())

    out.that(REGISTRY["p1333"].basic == "ranged",
             "a row whose card reads 'counts as a ranged basic attack'"
             " declares it in its header, which the UI and policy/ read"
             f" without running anything ({REGISTRY['p1333'].basic!r})")

    # **The designation.** Held, so it is a basic attack for this creature.
    known.known = (*tuple(known.known), "p1333")
    designated = basics_of(world, me, "ranged")
    out.that("p1333" in designated,
             "holding it makes it one of this creature's ranged basic"
             f" attacks ({designated})")
    out.that("p1333" in basic_options(world, me, "ranged"),
             "and it is offered where a ranged basic attack is granted --"
             " 259 printed sites hand one out and none could reach it")

    # **The negative control**, which is the point of the whole issue.
    #
    # The stand-in has to be a row this creature possesses: `c.as_basic`
    # files rows a character may not have, and `basic_options` drops those
    # at the moment the swing is offered. Written without the `known.known`
    # line first, and the control then failed for the wrong reason -- which
    # would have read as the engine refusing a stand-in rather than as the
    # harness never offering one.
    known.known = (*tuple(known.known), "p1341")
    c = Cast(world=world, me=me, ref="drivers:counts-as")
    c.as_basic("p1341", window="ranged")
    stands_in = basic_options(world, me, "ranged")
    out.that("p1341" in stands_in,
             f"a row filed with c.as_basic is offered too ({stands_in})")
    out.that("p1341" not in basics_of(world, me),
             "but is NOT one of this creature's basic attacks -- 'in place"
             " of' is explicitly not 'counts as', and a reader that folded"
             " the two would hand every stand-in a basic-attack modifier")

    # **The context key**, which is the other reader #522 names and the one
    # a feat actually gates on. The attack context carried eight shape keys
    # and none of them said whether the attack was a basic one, so "+2
    # damage with basic attacks" had nothing to ask -- every such row
    # reached for `Powers` itself and compared against a pair of refs.
    seen: list[tuple[str, bool]] = []
    world.bus.on(AttackRolled, lambda ev: seen.append(
        (ev.power, bool((getattr(ev, "ctx", None) or {}).get("basic")))))
    foe = sorted(enemies(world, me))[0]
    use(world, me, "p1333", targets=[foe], spend=False)
    use(world, me, "p1341", targets=[foe], spend=False)
    answers = dict(seen)
    out.that(answers.get("p1333") is True,
             "the attack context says a designated row IS a basic attack --"
             f" ctx['basic'], which nothing carried before ({answers})")
    out.that(answers.get("p1341") is False,
             "and says a c.as_basic stand-in is not, on the same key --"
             " the negative control again, this time where a modifier"
             f" reads it ({answers})")

    # A creature holding neither has only its designated pair.
    world2, me2, _ = _board()
    plain = basics_of(world2, me2)
    out.that("p1333" not in plain,
             "and a creature that does not hold the card does not get the"
             f" designation off the header alone ({plain})")


def empowerment_pool(out: Result) -> None:
    """The artificer's per-day allowance: one pool, two separate limits.

    `cf:artificer-f0` begins the day with one empowerment and the two
    `-f0s*` options spend from it. `cf:artificer-f0s1` also prints its own
    limit -- "an item can be recharged only once per day in this way" --
    and the two are **different sentences about different things**: N
    empowerments for the artificer, one recharge per item. Folding them
    would let a single item soak every empowerment once a milestone raised
    the pool.

    The order matters and is the thing an implementation gets backwards.
    The item's own limit is asked first, because asking the pool first
    burns one of the day's allowance on an item that cannot take a second
    recharge -- a silent loss, since both refusals look the same from
    outside.

    `f3791` raises the pool by one, which it could not do while the limit
    was a module constant three rows passed by name. `empowerments()` is
    the read it writes through.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.content.features.martial_leaders import (
        EMPOWERMENTS,
        EMPOWERMENTS_REF,
        empowerments,
    )
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers
    from combat_engine.engine.durations import When
    from combat_engine.engine.turns import short_rest

    world, me, _ = _board()
    c = Cast(world=world, me=me, ref="drivers:empowerments")

    out.that(empowerments(c) == EMPOWERMENTS,
             "with no feat the day's allowance is the printed"
             f" {EMPOWERMENTS} ({empowerments(c)})")

    # **The pool is spent down, and runs out.** `EMPOWERMENTS` is 1, so the
    # first spend takes and the second must not.
    took = [c.spend_per_day(EMPOWERMENTS_REF, empowerments(c))
            for _ in range(2)]
    out.that(took == [True, False],
             "the allowance is spent down and refuses when the day is out"
             f" -- a pool that always says yes is free {took}")

    # **A rest between encounters runs the rest clause**, which is the whole
    # of #498's second half and the thing that was silently broken. The
    # three features and five feats written against `events.ShortRested`
    # were all dead in both of `fight.py`'s paths: the rest is called
    # before `encounter.start()`, so no trait had laid a watcher. They
    # audited green because the audit board arms first and then provokes.
    world4, me4, _ = _board()
    known4 = world4.get(me4, Powers) or world4.add(me4, Powers())
    known4.known = (*tuple(known4.known), "cf:artificer-f0s0")
    enc = world4.encounter
    assert enc is not None
    enc.arm_traits_of(me4)
    for eff in list(world4.effects.of(me4)):
        world4.effects.end(eff, "the encounter ended")
    world4.encounter = None          # what fight.py's order amounts to
    short_rest(world4)
    out.that(known4.per_day.get(EMPOWERMENTS_REF) == 1,
             "a short rest taken between encounters banks the empowerment --"
             " with no encounter nothing is armed, so the row had laid no"
             f" watcher and the rest reached nothing ({dict(known4.per_day)})")

    # **And a rest *during* an encounter must not arm anything twice.**
    # `Encounter.start` has already armed, and a second pass lays a second
    # copy of every standing modifier -- the seventy-one-watchers bug
    # `turns._arm_traits` records, in one step rather than over seven
    # rounds. Added because a plant removing the guard in `_rest_window`
    # left all 507 rules green: the guard was reasoned and unmeasured.
    # Measured as **how many times the rest clause ran**, not as a count of
    # live effects: a mid-encounter rest legitimately adds one, the banked
    # charge itself, and the first version of this rule asserted the count
    # was unchanged and went red on correct code. The pool is raised to 3
    # first, because at the printed 1 the second bank is refused by the
    # allowance and the two cases look identical.
    world5, me5, _ = _board()
    known5 = world5.get(me5, Powers) or world5.add(me5, Powers())
    known5.known = (*tuple(known5.known), "cf:artificer-f0s0")
    enc5 = world5.encounter
    assert enc5 is not None
    enc5.arm_traits_of(me5)
    Cast(world=world5, me=me5, ref="drivers:headroom").change_amount(
        EMPOWERMENTS_REF, 3, on=me5, until=When.ENCOUNTER)
    short_rest(world5)
    banked = known5.per_day.get(EMPOWERMENTS_REF, 0)
    out.that(banked == 1,
             "a rest taken while an encounter is running arms nothing a"
             " second time -- a second copy of the trait would lay a second"
             f" rest watcher and bank twice off one rest ({banked})")

    # f3791's raise, on a fresh day.
    world2, me2, _ = _board()
    c2 = Cast(world=world2, me=me2, ref="drivers:empowerments-feat")
    c2.change_amount(EMPOWERMENTS_REF, EMPOWERMENTS + 1, on=me2,
                     until=When.ENCOUNTER)
    out.that(empowerments(c2) == EMPOWERMENTS + 1,
             "f3791's additional use is read off the same door"
             f" ({empowerments(c2)})")
    raised = [c2.spend_per_day(EMPOWERMENTS_REF, empowerments(c2))
              for _ in range(3)]
    out.that(raised == [True, True, False],
             "and buys exactly one more spend, not an unlimited pool"
             f" {raised}")

    # **The item's own once-a-day is a different key**, so spending the
    # pool must not have spent it, and vice versa.
    world3, me3, _ = _board()
    c3 = Cast(world=world3, me=me3, ref="drivers:empowerments-item")
    item = [c3.spend_per_day("i601p1", 1) for _ in range(2)]
    out.that(item == [True, False],
             f"an item takes one recharge a day on its own key {item}")
    out.that(c3.spend_per_day(EMPOWERMENTS_REF, empowerments(c3)),
             "and spending the item's limit leaves the empowerment pool"
             " untouched -- two sentences, two keys, and folding them is"
             " how one item eats the whole day")


def aid_grants(out: Result) -> None:
    """How much an aid action grants is a knob, and the biggest raise wins.

    Twelve rows modify aiding and **seven of them change the size of the
    bonus**. The number lived inside `c.aid_attack`, where none of them
    could reach it -- so the gap was a knob rather than another verb, which
    is the same shape the bull rush turned out to have.

    Three things are measured, each the way a wrong implementation differs:

    * **the default is still 2** when nothing has changed it, which an
      over-eager reader breaks by returning its own floor;
    * **a raise is read**, which a modifier nothing consults breaks -- the
      commonest bug in this component;
    * **two raises do not add.** The printed rule is one aid per attack, so
      +4 and +3 together are +4, not +7. `amount_for` takes a maximum for
      exactly this, and summing is the natural way to write it wrong.

    The fourth rule is the mirror: **setting it to 0 means zero**, which
    f2444 needs because its reroll *replaces* the +2. A reader written as
    `max(default, ...)` would quietly keep the 2 and leave that feat paying
    out twice.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import MANOEUVRE_AID, Cast
    from combat_engine.engine.durations import When
    from combat_engine.engine.events import Aided
    from combat_engine.engine.query import allies, enemies

    world, me, _ = _board()
    foe = sorted(enemies(world, me))[0]
    friends = [a for a in allies(world, me) if a != me]
    assert friends, "the board has no ally to aid"
    ally = friends[0]
    c = Cast(world=world, me=me, ref="drivers:aid")

    out.that(c.amount_for(MANOEUVRE_AID, 2) == 2,
             "with nothing changing it an aid action grants the printed 2"
             f" ({c.amount_for(MANOEUVRE_AID, 2)})")

    c.change_amount(MANOEUVRE_AID, 4, on=me, until=When.ENCOUNTER)
    got = c.amount_for(MANOEUVRE_AID, 2)
    out.that(got == 4,
             f"a row raising it to 4 is read -- the half that is a modifier"
             f" nothing consults when it is missing ({got})")

    c.change_amount(MANOEUVRE_AID, 3, on=me, until=When.ENCOUNTER)
    both = c.amount_for(MANOEUVRE_AID, 2)
    out.that(both == 4,
             "and a second raise of 3 beside it is still 4, not 7 -- an ally"
             f" benefits from one aid per attack ({both})")

    # **Zero means zero.** f2444 replaces the +2 with a reroll.
    world2, me2, _ = _board()
    c2 = Cast(world=world2, me=me2, ref="drivers:aid-zero")
    c2.change_amount(MANOEUVRE_AID, 0, on=me2, until=When.ENCOUNTER)
    out.that(c2.amount_for(MANOEUVRE_AID, 2) == 0,
             "a row setting the grant to 0 gets 0, not the printed 2 kept by"
             f" a max against the default ({c2.amount_for(MANOEUVRE_AID, 2)})")

    # **What the action actually grants**, which is a different question
    # from what the reader returns. Added because a plant putting the
    # literal 2 back inside `c.aid_attack` left every rule above green --
    # the driver was measuring the knob and not the thing holding it, which
    # is precisely the unread-modifier bug its own docstring claims to
    # catch. Four assertions on a reader prove nothing about its callers.
    heard: list[tuple[int, int, str, int | None]] = []
    world.bus.on(Aided, lambda ev: heard.append(
        (ev.actor, ev.ally, ev.kind_, ev.enemy)))
    c.aid_attack(foe, ally)
    paid = c.total("attack", ally, {"actor": ally, "target": foe})
    out.that(paid == 4,
             "and the aid action pays out the raised 4, not the 2 written in"
             f" its own body -- the half a reader test cannot see ({paid})")
    out.that(heard == [(me, ally, "aid_attack", foe)],
             "aiding announces itself with who aided, who was helped and the"
             f" enemy it was aimed at -- the door f2444 and f3761 read ({heard})")


def bull_rush_riders(out: Result) -> None:
    """A row that lengthens a bull rush does, and the two allowances differ.

    `p14383` prints "increase the push by a number of squares up to your
    Constitution modifier, **shifting into each square the target leaves**",
    which is the only clause in the tree that lengthens the *follow* as well
    as the push. A belt lengthens the push alone.

    So this measures both separately, and the measurement is the count of
    moves rather than the distance covered -- displacement is clipped by the
    board edge and by whoever is standing in the vacated square, which is
    what made the first three readings of this look wrong when the code was
    right. Counting `MoveEnd` is board-independent.

    **Why it needs a driver at all.** `audit.py` reports `p14383` UNUSED and
    always will: the audit board never elects a manoeuvre, so no row
    triggering off one can fire there. That is a harness limit rather than a
    row fault, and this is the thing that actually exercises it.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import events
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers, Stats
    from combat_engine.engine.movement import place
    from combat_engine.engine.query import enemies
    from combat_engine.engine.types import Ability

    def follows(rider: bool) -> int | None:
        world, me, _ = _board()
        foe = sorted(enemies(world, me))[0]
        stats = world.get(me, Stats) or world.add(me, Stats())
        stats.scores[Ability.CON] = 18       # +4, so a rider is unmistakable
        stats.scores[Ability.STR] = 24       # land the Fortitude attack
        known = world.get(me, Powers) or world.add(me, Powers())
        if rider:
            known.known = (*tuple(known.known), "p14383")
        place(world, me, (2, 7))
        place(world, foe, (3, 7))
        seen = [0]
        world.bus.on(events.MoveEnd, lambda ev: seen.__setitem__(
            0, seen[0] + (getattr(ev, "kind_", "") == "shift"
                          and ev.actor == me)))
        if not Cast(world=world, me=me, ref="drivers:riders").bull_rush(on=foe):
            return None
        return seen[0]

    plain = next((f for f in (follows(False) for _ in range(40))
                  if f is not None), None)
    laden = next((f for f in (follows(True) for _ in range(40))
                  if f is not None), None)
    # **This one is bounded by the push, and that is worth saying.** The base
    # bull rush pushes one square, so the loop takes one step and the follow
    # cannot exceed it whatever the allowance says -- a plant setting the base
    # follow to 2 stays green here. What it does catch is a follow of 0, which
    # is the whole second half of the printed sentence. Reworded from "exactly
    # one square, and no more", which claimed the plant it cannot fail.
    out.that(plain == 1,
             "an ordinary bull rush follows the square it pushed -- the"
             f" printed shift, which a dropped follow makes 0 ({plain})")
    out.that(laden == 5,
             "and with p14383 held it follows 1 + the Constitution modifier,"
             f" which is the clause's second half ({laden} with CON 18)")


def long_rest(out: Result) -> None:
    """A long rest announces itself, and a daily does come back.

    "Per day" has no calendar to hang on in this engine, so Camille's answer
    -- it means until a long rest -- makes `turns.extended_rest` the moment a
    daily allowance resets at. That function existed and said nothing.

    The control that matters is the **difference from a short rest**: a short
    rest restores encounter powers and leaves dailies spent, a long rest
    restores both. An implementation that emitted the new event from the
    wrong function would pass a test that only checked the event arrived.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.components import Powers
    from combat_engine.engine.events import ExtendedRested, ShortRested
    from combat_engine.engine.turns import extended_rest, short_rest

    world, me, _ = _board()
    mine = world.get(me, Powers)
    assert mine is not None

    heard: list[tuple[str, int]] = []
    world.bus.on(ShortRested, lambda ev: heard.append(("short", ev.actor)))
    world.bus.on(ExtendedRested, lambda ev: heard.append(("long", ev.actor)))

    # A daily and an encounter power, both spent.
    mine.note_use("drivers:daily", world.round)
    mine.note_use("drivers:enc", world.round)

    short_rest(world)
    out.that(("short", me) in heard, "a short rest announces itself")
    out.that(not any(k == "long" for k, _ in heard),
             "and does NOT announce a long one -- the two are different"
             " moments and emitting from the wrong function would pass a"
             " check that only asked whether the event arrived")

    extended_rest(world)
    out.that(("long", me) in heard, "a long rest announces itself too")
    out.that(len([1 for k, a in heard if k == "long" and a == me]) == 1,
             "once for this creature, not twice")
    out.that(not mine.used,
             "and the long rest cleared what was spent, which is the half"
             " that makes 'per day' mean something")

    # **The daily allowance, which is what "per day" was decided for.** The
    # counter lives on `story.Sheet` so it outlives a fight; these are the
    # two rules that make it a *day* rather than an encounter.
    from combat_engine.story import Party, Sheet

    sheet = Sheet(cls="artificer", level=1)
    party = Party(sheets=[sheet])
    sheet.per_day["cf:artificer-f0"] = 1
    party.rest(extended=False)
    out.that(sheet.per_day.get("cf:artificer-f0") == 1,
             "a short rest does NOT give a daily allowance back -- the"
             " control that separates per-day from per-encounter, and the"
             " reason `Powers.used` was the wrong counter")
    party.rest(extended=True)
    out.that(not sheet.per_day,
             "and a long rest does, which is what 'per day' was decided to"
             " mean")
    out.that(Sheet(cls="x", per_day={"r": 1}).per_day_left("r", 1) == 0,
             "an allowance spent to its limit reads as nothing left")


def disease(out: Result) -> None:
    """"...and the target contracts `x5_23`." 47 rows printed this. #389.

    The ref had nothing behind it: diseases were indexed by name and id and
    there was no table, so `c.contract(ref)` named a ref that could not
    resolve to a row. The table is 69 rows now and the verb records it.

    **The stage does not advance, and that is the card.** Every one of the 69
    pages checks at the end of an *extended rest*, which this engine does not
    have -- so a disease caught in a fight stays where it was caught. The
    assertion below is deliberately that it does *not* move, because the
    tempting bug is to advance it on a turn boundary and call that progress.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Afflictions
    from combat_engine.engine.query import enemies

    world, me, _ = _board()
    c = Cast(world=world, me=me, ref="drivers:disease")
    foe = sorted(enemies(world, me))[0]

    out.that(not c.exposed(on=foe), "nobody has caught anything yet")
    held = c.contract("x5_23", on=foe)
    out.that(held is not None, "contracting it is laid as an effect")
    out.that(c.exposed(on=foe), "and the creature is exposed")
    out.that(c.exposed("x5_23", on=foe), "to that disease by name")
    out.that(not c.exposed("x5_34", on=foe),
             "and NOT to a different one -- the negative control, and without"
             " it `exposed` could answer yes to anything")

    caught = world.get(foe, Afflictions)
    out.that(caught is not None and caught.contracted.get("x5_23") == 1,
             "recorded at stage 1, which is where every page starts")

    # Catching it twice is not catching it again.
    again = c.contract("x5_23", on=foe)
    out.that(again is None, "contracting the same disease twice does nothing")
    out.that(caught is not None and len(caught.contracted) == 1,
             "and leaves one entry, not two")

    # A turn passing does not move the stage. This is the assertion that keeps
    # somebody from "fixing" the track into something the cards do not say.
    from combat_engine.engine.events import TurnEnd

    before = dict(caught.contracted) if caught else {}
    world.bus.emit(TurnEnd(actor=foe, round=world.round))
    out.that(caught is not None and caught.contracted == before,
             "a turn ending does NOT advance the stage -- every page checks at"
             " the end of an extended rest, which this engine has none of")

    # Suspension, because it is side state like the rest (#470).
    world.effects.suspend(held)
    out.that(not c.exposed(on=foe), "suspended, the infection lifts")
    world.effects.resume(held)
    out.that(c.exposed(on=foe), "and comes back")

    # The table the ref resolves to, which is the half that did not exist.
    import sqlite3

    from combat_engine.db import GAME
    db = sqlite3.connect(GAME)
    row = db.execute(
        "select level, check_skills, worsen_dc, improve_dc, dc_shape, stages"
        " from disease where ref='x5_23'").fetchone()
    out.that(row is not None, "the ref resolves to a row in `disease`")
    out.that(row is not None and row[5] >= 2,
             "which carries a stage track")
    out.that(row is not None and row[4] in
             ("fixed", "source_level", "encounter_level", "band"),
             "and a DC shape, because the pages print four of them")


def summoned(out: Result) -> None:
    r"""A character's summon takes its numbers from the summoner. #459.

    88 blocks, and **79 of them print no numbers at all** -- "HP your
    bloodied value", "Defenses your defenses + 2". So the block is a rule for
    deriving a stat line and the creature it derives from is not known until
    something summons it, which is why `spawn_associate` requires `of=` and
    `loader.spawn` cannot serve these refs.

    The rule most worth asserting is the **sign**. The first version of the
    offset pattern read `\+\s*(\d+)` and silently missed the two blocks that
    print a *penalty*, which gave those summons two points more defence than
    their page allows, on every defence they have -- a wrong number rather
    than a missing one.
    """
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defenses, Health, Movement
    from combat_engine.engine.types import Defense

    def made(ref: str):  # noqa: ANN202
        world, me, _ = _board()
        c = Cast(world=world, me=me, ref="drivers:summon")
        base = world.get(me, Defenses)
        mine = world.get(me, Health)
        eid = c.summon(ref)
        return world, eid, base, mine

    # +0: defences equal the summoner's, hp is their bloodied value
    world, eid, base, mine = made("x10_12")
    d, h, mv = (world.get(eid, Defenses), world.get(eid, Health),
                world.get(eid, Movement))
    out.that(eid != 0, "a summon with a relative block reaches the board")
    out.that(d is not None and d.values[Defense.AC] == base.values[Defense.AC],
             "its defences equal the summoner's, which is what the page says")
    out.that(h is not None and h.max_hp == max(1, mine.max_hp // 2),
             "and its hit points are the summoner's bloodied value")
    out.that(mv is not None and mv.speed == 8,
             "speed is the printed 8, not the engine's default -- this row used"
             " to spawn off `Summon`'s bare defaults and lose it")

    # +1: the same block one point better, which is what f3541 chooses
    world, eid, base, _ = made("x10_13")
    d = world.get(eid, Defenses)
    out.that(d is not None and d.values[Defense.AC] == base.values[Defense.AC] + 1,
             "a block printing `+ 1` is one better")

    # -2: the sign, and the reason this rule exists
    world, eid, base, _ = made("x10_93")
    d = world.get(eid, Defenses)
    out.that(d is not None and d.values[Defense.AC] == base.values[Defense.AC] - 2,
             "and a block printing `-2` is two WORSE -- the negative control,"
             " and the one a plus-only pattern reads as +0")

    # the 9 that print absolute numbers use them
    world, eid, base, _ = made("x10_1")
    d = world.get(eid, Defenses)
    out.that(d is not None and d.values[Defense.AC] == 15,
             "a block printing `AC 15` uses 15, not an offset")

    # a summon joins the order, which is the half `loader.spawn` alone misses
    out.that(world.encounter is None or eid in list(world.encounter.order),
             "and it is in the initiative order rather than standing there")


def conjurer_count(out: Result) -> None:
    """"Initiative as conjurer": the servant acts on its summoner's count.

    10 of the 12 stat blocks printed inside an item's own entry say this
    outright (#601), and it is a printed rule rather than a tidying: a
    servant on its conjurer's count acts in the same part of every round,
    and one that rolls its own does not. Before `summon(after=)` there was
    no way to say it -- `Encounter.join` always rolled -- so every one of
    those creatures would have arrived somewhere random in the order.

    **The negative control is the whole of the evidence here**, because the
    positive one passes by luck. `join` rolls a d20 plus a level term, so an
    unforced roll lands on the conjurer's count about one time in twenty and
    an assertion that only checked `after=` could not tell "copied" from
    "rolled and got lucky". So `rng.loaded` fixes the die at a value whose
    resulting count is **not** the conjurer's, and the two summons differ in
    nothing but the keyword.

    The third case is the fallback: a `beside` that is not in the order
    rolls, rather than raising or landing at a count of zero. A conjurer can
    leave the fight between a row being written and it firing, and a
    creature with no slot at all never acts -- which is the failure this
    whole family exists to avoid.
    """
    from combat_engine.content import loader
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Initiative

    world, me, _ = _board()
    if world.encounter is None:
        out.skip("the board has no initiative order to join")
        return

    # Positive: handed the conjurer, it copies the count. The die is fixed
    # so the only difference between this run and the negative one below is
    # the keyword.
    world.rng.loaded = 3
    c = Cast(world=world, me=me, ref="drivers:conjurer")
    made = c.summon("m1932c0", after=me)
    mine = world.get(me, Initiative)
    theirs = world.get(made, Initiative)
    out.that(made != 0, "a conjured block reaches the board at all")
    out.that(mine is not None and theirs is not None
             and theirs.rolled == mine.rolled,
             "`after=` puts the servant on its conjurer's own count",
             f"conjurer {mine.rolled if mine else '?'},"
             f" servant {theirs.rolled if theirs else '?'}")
    order = list(world.encounter.order)
    out.that(made in order, "and it is in the order rather than standing there")
    if me in order and made in order:
        out.that(order.index(made) > order.index(me),
                 "on the same count it acts AFTER the conjurer, which is what"
                 " `_splice` inserting before a strictly lower count gives")

    # negative: the same board, the same fixed die, no `after=`
    world2, me2, _ = _board()
    world2.rng.loaded = 3
    made2 = Cast(world=world2, me=me2, ref="drivers:conjurer").summon("m1932c0")
    mine2 = world2.get(me2, Initiative)
    theirs2 = world2.get(made2, Initiative)
    out.that(mine2 is not None and theirs2 is not None
             and theirs2.rolled != mine2.rolled,
             "without it the servant rolls its own and does NOT match -- the"
             " negative control, and the one a copy-always change passes",
             f"conjurer {mine2.rolled if mine2 else '?'},"
             f" servant {theirs2.rolled if theirs2 else '?'}")

    # the fallback: a `beside` nobody is standing as
    world3, me3, _ = _board()
    world3.rng.loaded = 3
    made3 = Cast(world=world3, me=me3, ref="drivers:conjurer").summon(
        "m1932c0", after=99999)
    theirs3 = world3.get(made3, Initiative)
    out.that(made3 != 0 and theirs3 is not None and theirs3.rolled != 0,
             "a `beside` that is in no order falls back to rolling rather than"
             " leaving the servant at a count of zero",
             f"servant {theirs3.rolled if theirs3 else '?'}")

    # ---- and the row that wanted it from the other end -----------------
    #
    # `m5624a4` is "four <minions> appear in its space … these act on the
    # <creature>'s initiative". It sat on `spec.monster_ref()` with a
    # docstring saying the four "name a kind with no ref in this tree" --
    # written when the spec could not resolve it, and the spec names
    # `m5623` outright. Asserted through the row rather than the verb,
    # which is this file's rule: a driver that calls the facility survives
    # the row being reverted and says nothing about it.
    from combat_engine.content.monsters.level_08 import soldiers_sa
    from combat_engine.engine.components import Ident
    from combat_engine.engine.query import creatures

    world, _me, _ = _board()
    if world.encounter is None:
        out.skip("no encounter, so nothing can join an order")
        return
    bursting = loader.spawn(world, "m5624", (10, 10))
    world.encounter.join(bursting)
    soldiers_sa.m5624a4(Cast(world=world, me=bursting, ref="m5624a4"))
    stood = [
        e for e in creatures(world)
        if (who := world.get(e, Ident)) is not None and who.ref == "m5623"
    ]
    out.that(len(stood) == 4,
             "m5624a4 stands four of its own kind up where it fell, which is"
             " what the card prints",
             f"{len(stood)} appeared")
    theirs = world.get(bursting, Initiative)
    out.that(bool(stood) and theirs is not None and all(
        (i := world.get(e, Initiative)) is not None and i.rolled == theirs.rolled
        for e in stood
    ), "and every one of them on the bursting creature's own count -- without"
       " `after=` they would each roll and arrive scattered through the round",
       f"{[getattr(world.get(e, Initiative), 'rolled', None) for e in stood]}"
       f" against {theirs.rolled if theirs else '?'}")
    order = list(world.encounter.order)
    out.that(all(e in order for e in stood),
             "all four in the initiative order rather than standing there --"
             " the half `loader.spawn` alone misses")


def raises_the_fallen(out: Result) -> None:
    """A corpse can be named now, and three rows dropped on saying it cannot.

    `m3219a5` and `m3499a3` carried `dropped=("query.dead_allies()",)` with
    docstrings saying "the board has no way to name a corpse" -- and the
    board always had. `_die` keeps the body an entity *and its `Position`*
    and only lifts it off the grid, so the corpses were sitting there. What
    could not hand one over was the vocabulary: `c.within`, `c.in_squares`
    and every other finder ends in `alive(...)`, which is right for the
    thousands of rows that mean a living target. `m135a3` is the proof the
    gap was never in the board -- it hand-rolled the same comprehension at
    level 4 and worked, while three others were marked unwritable.

    **The asymmetry is the whole assertion**, and it is checked in both
    directions on one board: while the minion lives `c.within` sees it and
    `c.fallen` must not; once it is killed `c.fallen` sees it and `c.within`
    must not. Asserting only the second would pass for a `c.fallen` that
    ignored `alive` altogether and returned everybody.

    `side="enemy"` is asserted *blind* -- it cannot see an enemy corpse,
    because `query.enemies` filters the dead where `query.allies` does not.
    That is a documented limitation rather than a bug: no printed card asks
    for an enemy corpse, and changing `enemies` to match would move hundreds
    of live rows for the sake of none. It is asserted so the docstring
    saying so is checked rather than believed.

    The rows are then driven through `REGISTRY`, not re-implemented, so this
    survives either row being reverted and says nothing about it.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content import loader
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health, Ident, Initiative, Position
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.query import alive, creatures, distance_between

    world, me, _ = _board()
    c = Cast(world=world, me=me, ref="drivers:fallen")

    # An undead minion on the caster's own side, which is what all four
    # cards ask for. Summoned rather than posed, so it is a real stat block.
    minion = c.summon("m499")
    if minion == 0:
        out.skip("the board would not take a summon")
        return
    out.that(c.is_kind("undead", on=minion),
             "the summoned ally is undead, which every one of these cards"
             " restricts itself to")

    # ---- alive: within sees it, fallen does not ------------------------
    out.that(minion in c.within(20),
             "while it lives the ordinary finder sees it")
    out.that(minion not in c.fallen(20),
             "and `c.fallen` does NOT -- the control a `c.fallen` that"
             " ignored `alive` and returned everybody would fail")

    c.kill(on=minion)
    out.that(not alive(world, minion), "the minion is destroyed")

    # ---- dead: fallen sees it, within does not -------------------------
    out.that(minion in c.fallen(20),
             "once destroyed `c.fallen` names the corpse, which is the read"
             " three rows were marked unwritable for wanting")
    out.that(minion not in c.within(20),
             "and the ordinary finder has stopped seeing it, so the two"
             " never both answer for one creature")
    out.that(minion in c.fallen(20, side="ally", kind="undead"),
             "`side=` and `kind=` both pass it, which is the exact call the"
             " three rows make")
    # The radius, on the boundary rather than at a guessed number. The first
    # draft asserted `c.fallen(1)` excluded it and went red, which was the
    # assertion being wrong and not the verb: `c.summon` places the ally
    # adjacent, so a radius of 1 includes it correctly. Measure the distance
    # and test either side of it.
    far = distance_between(world, me, minion)
    out.that(minion in c.fallen(far, side="ally", kind="undead"),
             "a radius exactly reaching the corpse offers it",
             f"{far} squares off")
    out.that(minion not in c.fallen(far - 1, side="ally", kind="undead"),
             "and one square short does not -- the radius is read, not"
             " decoration",
             f"{far - 1} did not reach it")
    out.that(minion not in c.fallen(20, side="ally", kind="dragon"),
             "a kind it is not excludes it")
    out.that(c.fallen(20, side="enemy") == [],
             "`side=\"enemy\"` can never see a corpse, because `query.enemies`"
             " filters the dead -- documented, and asserted so the note"
             " saying so is checked")

    # ---- m3219a5: the minion half it was dropped on --------------------
    raiser = loader.spawn(world, "m3219", (12, 12))
    REGISTRY["m3219a5"].body(Cast(world=world, me=raiser, ref="m3219a5"))
    body = world.get(minion, Health)
    out.that(alive(world, minion) and body is not None and body.hp == 1,
             "m3219a5 stands the destroyed minion back up at the printed one"
             " hit point",
             f"hp {body.hp if body else '?'}")

    # ---- m3499a3: the same gap at level 6, and a declared target that
    # ---- could never be a corpse ---------------------------------------
    #
    # Its own board: the row above raised the only corpse this one has. The
    # header used to declare `Target(side="ally", ...)` and the dispatcher
    # only offers live creatures, so it was a row that could run and never
    # have a subject -- which is why the level ceiling is asserted too. 15
    # is the printed number.
    world3, me3, _ = _board()
    c3 = Cast(world=world3, me=me3, ref="drivers:fallen3")
    corpse = c3.summon("m499")
    c3.kill(on=corpse)
    healer = loader.spawn(world3, "m3499", (12, 12))
    REGISTRY["m3499a3"].body(Cast(world=world3, me=healer, ref="m3499a3"))
    raised = world3.get(corpse, Health)
    out.that(alive(world3, corpse) and raised is not None and raised.hp == 15,
             "m3499a3 raises the destroyed ally at the printed 15 hit points,"
             " having found it rather than been handed it",
             f"hp {raised.hp if raised else '?'}")

    # ---- m1042a2: four corpses become a different creature -------------
    #
    # A fresh board, because the row above raised the only corpse. Two
    # corpses rather than four, so "up to" is tested on the short side: a
    # row that stood four up regardless would fail here.
    world2, me2, _ = _board()
    c2 = Cast(world=world2, me=me2, ref="drivers:fallen2")
    dead = [c2.summon("m499"), c2.summon("m499")]
    for e in dead:
        c2.kill(on=e)
    caster = loader.spawn(world2, "m1042", (14, 14))
    if world2.encounter is not None:
        world2.encounter.join(caster)
    before = {
        e for e in creatures(world2)
        if (i := world2.get(e, Ident)) is not None and i.ref == "m499"
    }
    REGISTRY["m1042a2"].body(Cast(world=world2, me=caster, ref="m1042a2"))
    risen = {
        e for e in creatures(world2)
        if (i := world2.get(e, Ident)) is not None and i.ref == "m499"
    } - before
    out.that(len(risen) == 2,
             "m1042a2 raises one new creature per corpse and no more -- 'up"
             " to 4' with two on the board is two",
             f"{len(risen)} rose from {len(dead)} corpses")
    theirs = world2.get(caster, Initiative)
    out.that(bool(risen) and theirs is not None and all(
        (i := world2.get(e, Initiative)) is not None and i.rolled == theirs.rolled
        for e in risen
    ), "and each on the raiser's own count, which is the printed 'act after"
       " the <creature> in the initiative order'")
    out.that(all(
        world2.grid.occupant(sq) == e
        for e in risen
        if (p := world2.get(e, Position)) is not None
        for sq in (p.square,)
    ), "each one standing in a square of its own, so the corpse's square was"
       " free to be taken -- `_die` lifts the body off the grid")


def named_in_prose(out: Result) -> None:
    """Three rows marked unwritable because a card names a creature in prose.

    All three carried `spec.monster_ref()` or `todo=` saying the creature the
    card names "has no ref in this tree" and that only its printed name was
    available. **All three refs existed and were declared.** Nothing was
    missing but a lookup against the `monster` table, which an authoring
    agent cannot do and the main session can -- so the marker recorded the
    author's reach, not the tree's state, and sat there.

    What each needed, and why each is asserted differently:

    * `m4418a3` summons four of one block. The row was already one
      `c.summon` away; the comment half-admitted it ("`c.summon` ... was the
      wrong thing to mark").
    * `m5581a3` summons 1d4 in any mix of two blocks, and recharges when all
      of them are destroyed. The mix and the recharge condition are separate
      assertions, and the recharge's **negative control is the point**: one
      echo falling must not give the row back.
    * `m5790a1` guards one named ally. Asserted on the predicate rather than
      the body, because the predicate is the clause that changed -- and the
      negative control is a different ally being struck, which the old
      fallback answered True for. That fallback was a strictly *stronger*
      power than the card: the shield followed the attack instead of the
      creature.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content import loader
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Ident, Position, Powers
    from combat_engine.engine.dsl import REGISTRY, get
    from combat_engine.engine.events import Hit
    from combat_engine.engine.query import creatures, enemies

    def standing(world, ref: str) -> list[int]:  # noqa: ANN001
        return [
            e for e in creatures(world)
            if (i := world.get(e, Ident)) is not None and i.ref == ref
        ]

    # ---- m4418a3: four of one block ------------------------------------
    world, _me, _ = _board()
    caller = loader.spawn(world, "m4418", (12, 12))
    REGISTRY["m4418a3"].body(Cast(world=world, me=caller, ref="m4418a3"))
    four = standing(world, "m1923")
    out.that(len(four) == 4,
             "m4418a3 stands four of the block its card names, whose ref the"
             " marker said did not exist",
             f"{len(four)} appeared")
    spots = {
        p.square for e in four
        if (p := world.get(e, Position)) is not None
    }
    out.that(len(spots) == 4,
             "each in a space of its own, which is the printed 'four"
             " unoccupied spaces'",
             f"{len(spots)} distinct squares")

    # ---- m5581a3: 1d4 in any mix, and the recharge condition -----------
    ref = "m5581a3"
    row = get(ref)
    out.that(row is not None and bool(row.recharges),
             "m5581a3 declares a printed recharge condition")
    out.that(row is not None and row.recharge == 0,
             "and no die, because its card prints a condition instead")

    world2, summoner, _ = _board(ref, 1)
    REGISTRY[ref].body(Cast(world=world2, me=summoner, ref=ref))
    echoes = standing(world2, "m5579") + standing(world2, "m5580")
    out.that(1 <= len(echoes) <= 4,
             "between one and four echoes answer, which is what 1d4 rolls --"
             " and both of the card's two blocks are reachable refs",
             f"{len(echoes)} appeared")

    known = world2.need(summoner, Powers)
    known.note_use(ref, world2.round)
    out.that(ref in known.spent, "the row is spent after being used")

    c2 = Cast(world=world2, me=summoner, ref="drivers:echoes")
    if len(echoes) > 1:
        c2.kill(on=echoes[0])
        out.that(ref in known.spent,
                 "one echo falling does NOT give the row back -- the negative"
                 " control, and the one a predicate reading 'any echo died'"
                 " would fail")
    for e in echoes[1:]:
        c2.kill(on=e)
    out.that(ref not in known.spent,
             "the last of them falling does, which is the printed 'recharge"
             " when all the echoes are destroyed'")

    # ---- m5790a1: the one named ally it guards --------------------------
    from combat_engine.content.monsters.level_05.brutes_sa import (
        _ally_struck_within_six,
    )

    world3, _me3, _ = _board()
    guard = loader.spawn(world3, "m5790", (12, 12))
    c3 = Cast(world=world3, me=guard, ref="drivers:guard")
    guarded = c3.summon("m5787")
    other = c3.summon("m499")
    foe = sorted(enemies(world3, guard))[0]
    out.that(guarded != 0 and other != 0,
             "the named ally and a second ally both reach the board")

    # A real melee row, because the predicate's last clause reads the reach
    # kind off the row that struck rather than guessing it. `power=""` makes
    # that clause False and the whole assertion vacuous.
    swing = "m145a0"
    hit_named = Hit(attacker=foe, target=guarded, power=swing, critical=False)
    hit_other = Hit(attacker=foe, target=other, power=swing, critical=False)
    out.that(_ally_struck_within_six(world3, guard, hit_named),
             "the guard answers when the ally its card names is struck")
    out.that(not _ally_struck_within_six(world3, guard, hit_other),
             "and does NOT when a different ally is -- the negative control,"
             " and exactly what the old fallback got wrong: it shielded"
             " whoever was hit, a strictly stronger power than the card")
    out.that(not _ally_struck_within_six(world3, guard, Hit(
        attacker=guard, target=guarded, power=swing, critical=False)),
        "nor when the blow came from its own side, since the card says an"
        " enemy")

    # ---- i3475x1 / i3475p1: the creature behind an opaque spec token ----
    #
    # Same cause as the four above and a different mechanism: `build.py`
    # gives a monster name in a non-`monster_power` spec an opaque `x_`
    # token, so the author saw `x_m6273` and could not know `m6273` is a
    # declared level-4 soldier. #610. Both rows print an exception for that
    # one creature, so **both negative controls are a different creature**,
    # which is the clause that was missing rather than the one that worked.
    from combat_engine.engine import When
    from combat_engine.engine.components import Conditions
    from combat_engine.engine.dsl import use
    from combat_engine.engine.durations import Effects
    from combat_engine.engine.types import Condition, Team

    def dominated_when(world, who: int) -> set[When]:  # noqa: ANN001
        """Which durations a domination on this creature is hung on.

        **`Effect.when`, not `Effect.until`.** The first draft read `until`
        -- the keyword `c.condition` takes -- and there is no such field, so
        the comprehension raised inside the matching branch and both cases
        reported an empty set. A reader that names a field the object does
        not have is this project's own commonest bug and it does not stop
        being one in an instrument.
        """
        effects: Effects = world.effects
        return {
            eff.when
            for eff in effects.of(who)
            if Condition.DOMINATED in eff.conditions
        }

    # Through `use`, not by constructing a `Cast` and poking `.targets`:
    # the first draft did the second and both cases came back empty,
    # because nothing had rolled an attack. A rule that goes through the
    # caller survives the row being rewritten -- **and it is what found the
    # control below.** `m499` was the first choice, and going through `use`
    # produced neither a `Hit` nor a `Miss`: the row's target line is
    # `kinds={"construct"}` and an undead minion is refused before the
    # exception can matter. So the control has to be a *construct* the
    # exception does not name, which is `m6272`. Poking `.targets` would
    # have bypassed the target line and the control would have been
    # meaningless while looking right.
    for ref, foe_ref, longer in (("i3475p1", "m6273", True),
                                 ("i3475p1", "m6272", False)):
        w, wearer, _ = _board(ref, 1)
        cw = Cast(world=w, me=wearer, ref="drivers:i3475")
        mark = cw.summon(foe_ref, team=Team.ENEMY)
        if mark == 0:
            out.skip(f"the board would not take a {foe_ref}")
            continue
        w.rng.loaded = 20                      # the hold needs the hit
        use(w, wearer, ref, targets=[mark], spend=False)
        holds = dominated_when(w, mark)
        want = When.SAVE_ENDS if longer else When.EONT
        why = ("the printed exception" if longer else
               "the control -- another construct, which the exception does"
               " not name, must get the ordinary hold")
        out.that(holds == {want},
                 f"i3475p1 dominates {foe_ref} until"
                 f" {want.name.lower().replace('_', ' ')}: {why}",
                 f"{sorted(h.name for h in holds)}")

    # i3475x1's daze, and the control: a creature the card does not name
    for foe_ref, dazes in (("m6273", True), ("m499", False)):
        w, wearer, _ = _board("i3475x1", 1)
        cw = Cast(world=w, me=wearer, ref="drivers:i3475x")
        striker = cw.summon(foe_ref, team=Team.ENEMY)
        if striker == 0:
            out.skip(f"the board would not take a {foe_ref}")
            continue
        REGISTRY["i3475x1"].body(Cast(world=w, me=wearer, ref="i3475x1"))
        w.bus.emit(Hit(attacker=striker, target=wearer,
                       power=swing, critical=False))
        held = w.get(striker, Conditions)
        got = held is not None and held.has(Condition.DAZED)
        out.that(got is dazes,
                 f"i3475x1 {'dazes' if dazes else 'does NOT daze'} a"
                 f" {foe_ref} that hits its wearer"
                 + ("" if dazes else " -- the control, and the whole of what"
                                     " the opaque token cost"),
                 f"dazed={got}")


def blank_defence_is_defective(out: Result) -> None:
    """"+X vs <blank>" is malformed, and the whole entry drops. Camille, #612.

    **The ruling, 2026-10-15:** *"If an attack says '+X vs. BLANK' it's
    malformed... To be clear, this is different than something like '+X vs
    reflex or will, whichever is lower.'"* With #600 -- a defective part
    drops the entire compendium entry -- that makes every one of these a
    `defect=` and takes its creature off the board.

    **I had this wrong and the correction is worth keeping.** I read the
    blank line as importer boilerplate pasted in front of the real text,
    retired the marker on 26 rows and called them finished. The measurement
    behind that reading was sound and is still asserted below -- blank-defence
    lines draw their damage from a pool of nineteen expressions where named
    ones use over a thousand -- but the conclusion was mine to get wrong:
    knowing *why* a line is junk does not make the row writable. The rows'
    original docstrings said "a compendium defect rather than a number to
    guess", which was right, and are restored.

    The distinction the ruling draws matters and the corpus hides it: these
    cards read `+N vs  or  (whichever is lower)` with **both** defence names
    absent, which is the blank form with a conjunction left over -- not the
    legitimate `vs Reflex or Will` that prints two real defences.
    """
    import re
    import sqlite3
    from collections import Counter
    from html import unescape

    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content import loader
    from combat_engine.db import SOURCE, localisation
    from combat_engine.engine.dsl import REGISTRY

    if not SOURCE.exists():
        out.skip("compendium.sqlite is not on this machine, and it is never"
                 " committed; nothing to measure")
        return

    comp = sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True)
    loc = localisation()
    # "+N vs" with no defence word. The `or` left behind by a blanked pair
    # counts as blank -- that is the whole of the ruling's second sentence.
    blank = re.compile(r"\+\s*\d+\s+vs\.?\s*(?:or\b|;|<|$)", re.I)

    def line_of(ref: str) -> str:
        name = (loc.get(ref) or {}).get("name") or ""
        mid = re.match(r"m(\d+)a\d+", ref)
        if not name or not mid:
            return ""
        got = comp.execute("SELECT Txt FROM Monster WHERE id=?",
                           (mid.group(1),)).fetchone()
        if not got:
            return ""
        found = re.search(
            r"<b>\s*" + re.escape(name) + r"\s*</b>(.*?)</p>\s*<p[^>]*>(.*?)</p>",
            unescape(got[0]), re.S | re.I)
        return (re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", found.group(2))).strip()
                if found else "")

    malformed = [
        ref for ref in REGISTRY
        if re.match(r"^m\d+a\d+$", ref) and blank.search(line_of(ref))
    ]
    out.that(len(malformed) >= 50,
             "the corpus still holds the rows this ruling is about -- the"
             " floor, so the two assertions below cannot pass on an empty set",
             f"{len(malformed)} rows")

    # **Both blank shapes have to stay in scope, counted separately.** A
    # floor on the total does not do it: narrowing the pattern to drop the
    # blanked *pair* -- "vs  or  (whichever is lower)" -- left 50+ of the
    # single-blank form behind and the rule stayed green while quietly
    # stopping checking half its subject. A plant found that. The pair form
    # is the one the ruling's second sentence is about, so it is the one most
    # worth pinning.
    pair = [r for r in malformed if re.search(r"vs\.?\s*or\b", line_of(r), re.I)]
    lone = [r for r in malformed if r not in pair]
    out.that(len(pair) >= 15 and len(lone) >= 15,
             "and both blank shapes are in scope -- the bare `vs ;` and the"
             " blanked pair `vs  or  (whichever is lower)`, which is the one"
             " the ruling distinguishes from a real two-defence line",
             f"{len(lone)} bare, {len(pair)} blanked pairs")

    undeclared = [r for r in malformed if not getattr(REGISTRY[r], "defect", "")]
    out.that(not undeclared,
             "every row whose printed attack line names no defence carries"
             " `defect=`, which is the ruling applied",
             f"{len(undeclared)} do not: {undeclared[:8]}")

    kept = [s for s in {r.split("a")[0] for r in malformed}
            if not loader.defective(s)]
    out.that(not kept,
             "and every entry holding one is defective, so #600 takes the"
             " whole creature off the board rather than the one row",
             f"{len(kept)} entries survive: {kept[:8]}")

    # ---- the entries with no row written, which is Camille's "all of them"
    #
    # *"Drop all of them for defect. I can review them later to see if we can
    # bring them back in, but the answer is probably no."* 150 compendium
    # entries have a blank attack line and only 85 have a row today, so a
    # row-level marker cannot reach the rest -- `etl.build._malformed_attack`
    # writes `monster.defect` at import instead, before anybody writes a row.
    #
    # **The 65 that are left are not a gap**: they are never imported into
    # `game.db` at all, so there is nothing to field and nothing to drop. The
    # assertion is that every *imported* one is marked, which is the whole of
    # what "all of them" can mean.
    from combat_engine.db import game

    db = game()
    page = set()
    for (mid, txt) in comp.execute("SELECT ID, Txt FROM Monster WHERE Txt IS NOT NULL"):
        if blank.search(unescape(txt)):
            page.add(f"m{mid}")
    imported = {r["ref"] for r in db.execute("SELECT ref FROM monster")}
    marked = {r["ref"] for r in db.execute(
        "SELECT ref FROM monster WHERE defect IS NOT NULL")}
    unmarked = sorted((page & imported) - marked)
    out.that(len(page & imported) >= 50,
             "the floor again -- there are imported blank-defence entries to"
             " ask about",
             f"{len(page & imported)} imported of {len(page)} on the page")
    out.that(not unmarked,
             "every imported entry with a blank attack line carries"
             " `monster.defect`, including the ones with no row written --"
             " which a row marker could never have reached",
             f"{len(unmarked)} unmarked: {unmarked[:8]}")
    fieldable = [r for r in marked if loader.usable(r)]
    out.that(not fieldable,
             "and none of them is fieldable, which is the point of the"
             " column rather than the record",
             f"{len(fieldable)} still usable: {fieldable[:8]}")

    # ---- why the compendium looks like this, which the ruling does not
    # ---- need but the next reader will want -----------------------------
    line = re.compile(r"\+(\d+)\s+vs\.?\s*([A-Za-z]*)\s*(or)?[^;<]*;\s*([^.<]*?)damage\.")
    pool: Counter[str] = Counter()
    named: Counter[str] = Counter()
    for (txt,) in comp.execute("SELECT Txt FROM Monster WHERE Txt IS NOT NULL"):
        for m in line.finditer(unescape(txt)):
            dice = re.sub(r"\s+", "", m.group(4))
            (pool if m.group(2) in ("", "or") else named)[dice] += 1
    if sum(pool.values()) < 20 or sum(named.values()) < 200:
        out.skip("too few attack lines to measure a distribution")
        return
    out.that(len(pool) < len(named) / 10,
             "a blank-defence line's damage comes from a tiny pool where a"
             " named one's does not -- which is how the malformation got into"
             " the source, and is why it is not a row fault to fix",
             f"{len(pool)} distinct over {sum(pool.values())} lines against"
             f" {len(named)} over {sum(named.values())}")



def area_or_close_is_one_set(out: Result) -> None:
    """"An area or a close attack power" was five tuples and one disagreement.

    `_AREA_SHAPES`, `_SPREAD_OUT`, `BURSTS`, `_SPREAD` and `_SPREADS` --
    warlord, psion, sorcerer, a sorcerer feat and a level-3 monster file --
    each wrote out the same answer to the same question, and **four of the
    five left `"wall"` out**. A wall is an area power, so those four were
    under-firing: `f1155`'s card prints "area and close attack powers", which
    covers one.

    `feats/sorcerer._SPREAD` was the one that had it right, which is why
    `dsl.AREA_OR_CLOSE` takes its reading rather than the majority's. Being
    outvoted four to one is not evidence here; the card is.

    **The blast radius is one row and that is the point.** `m5784a4` is the
    only `wall` row in the tree that declares an attack line at all -- 1 of
    9 -- so the correction is safe as well as right, and asserting the count
    is what keeps it honest if more wall attacks arrive later.

    Three neighbouring tuples are deliberately *not* folded in, and the rule
    asserts that too: the provoke set excludes close shapes on purpose, and
    `_stretched`'s excludes `"wall"` because a wall's size is its length.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content.feats import sorcerer as fs
    from combat_engine.content.monsters.level_03 import artillery as ar
    from combat_engine.content.powers.psion import level_10 as ps
    from combat_engine.content.powers.sorcerer import level_10_sc as so
    from combat_engine.content.powers.warlord import level_10_b as wl
    from combat_engine.engine.dsl import AREA_OR_CLOSE, REGISTRY, Power, Range

    named = {
        "warlord._AREA_SHAPES": wl._AREA_SHAPES,
        "psion._SPREAD_OUT": ps._SPREAD_OUT,
        "sorcerer.BURSTS": so.BURSTS,
        "feats.sorcerer._SPREAD": fs._SPREAD,
        "monsters.artillery._SPREADS": ar._SPREADS,
    }
    for label, got in sorted(named.items()):
        out.that(got is AREA_OR_CLOSE,
                 f"{label} is the shared set itself, not a copy of it",
                 f"{got}")
    out.that("wall" in AREA_OR_CLOSE,
             "and the shared set includes `wall`, which four of the five"
             " omitted -- a wall is an area power and `f1155` prints"
             " \"area and close attack powers\"")

    # The row the correction actually reaches, and the count that makes it
    # safe. A second wall attack arriving is not a fault -- it is a prompt to
    # re-read this -- so the assertion names the number rather than pinning
    # the ref alone.
    walls = [
        ref for ref, p in REGISTRY.items()
        if getattr(getattr(p, "reach", None), "kind", "") == "wall"
    ]
    arms = [r for r in walls if getattr(REGISTRY[r], "attack", None)]
    out.that(arms == ["m5784a4"],
             "exactly one wall row declares an attack line, so exactly one"
             " row changes behaviour -- if this grows, re-read the four"
             " predicates before trusting them",
             f"{len(walls)} wall rows, {len(arms)} with an attack: {arms}")

    # ---- the three that must stay separate -----------------------------
    def provokes(kind: str) -> bool:
        return Power("drivers:x", lambda c: None, reach=Range(kind=kind)).provokes

    out.that(provokes("wall") and not provokes("close_burst")
             and not provokes("close_blast"),
             "the provoke set is NOT this set -- a wall provokes, a close"
             " burst and a close blast do not, which is exactly why folding"
             " the two readings together would be wrong",
             f"wall={provokes('wall')} burst={provokes('close_burst')}"
             f" blast={provokes('close_blast')}")


def band_stays_in_tier(out: Result) -> None:
    """The three-level band does not cross a tier boundary. Camille, 2026-10-15.

    *"There's a kind of step change going into paragon tier which makes lvl+3
    monsters appropriate WITHIN heroic tier, but not going across to
    paragon."* The band was unclamped, so it ignored the step in both
    directions: measured before the fix, a level-8 party drew up to level 11,
    a level-10 party up to 13, and a paragon party at 11 reached back **down**
    to 8.

    **The recorded fixtures do not cover this**, which is why the rule exists.
    All seven still verify unchanged, because `story._compose` sorts the pool
    nearest-the-party-first and the XP budget fills before it reaches the top
    of the band -- so the only level-10 fixture never fielded the level 11-13
    creatures it was entitled to. A fixture that passes either way is no
    evidence about a boundary.

    Asserted at the boundary rather than in the middle: level 10 and level 11
    are the pair that moved, and a level in the middle of a tier would pass
    without the clamp.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content import loader
    from combat_engine.db import game

    db = game()

    def levels_for(level: int, band: int = 3) -> list[int]:
        refs = loader.pick(level, limit=0, band=band)
        return sorted({
            db.execute("SELECT level FROM monster WHERE ref=?", (r,)).fetchone()[0]
            for r in refs
        })

    top = levels_for(10)
    out.that(bool(top) and max(top) <= 10,
             "a level-10 party's band stops at 10 -- it reached 13 before"
             " this, which is three paragon levels of creature",
             f"levels {top}")
    out.that(bool(top) and min(top) == 7,
             "and still reaches three levels down, so the clamp took the"
             " boundary and not the band",
             f"levels {top}")

    low = levels_for(8)
    out.that(bool(low) and max(low) <= 10,
             "a level-8 party stops at 10 as well, rather than drawing the"
             " level 11 it was entitled to",
             f"levels {low}")

    para = levels_for(11)
    out.that(bool(para) and min(para) >= 11,
             "and the clamp works downward too: a paragon party at 11 no"
             " longer reaches back into heroic, which it did to level 8",
             f"levels {para}")

    mid = levels_for(5)
    out.that(mid == [2, 3, 4, 5, 6, 7, 8],
             "a level in the middle of a tier is untouched -- the control,"
             " and the reason asserting one would have proved nothing",
             f"levels {mid}")

    # A solo gets `band=1` from `story._compose` and must still be clamped,
    # since level 10 + 1 is 11.
    solo = levels_for(10, band=1)
    out.that(bool(solo) and max(solo) <= 10,
             "a solo's narrower band is clamped on the same boundary -- 10+1"
             " is still across it",
             f"levels {solo}")


def shield_penalty_waived(out: Result) -> None:
    """"You ignore the check penalty for wearing a shield." `f3779`.

    Half of this feat was marked unwritable on the grounds that the
    penalty "is settled when the character is built". It is not:
    `skills._armour_penalty` computes it per check, and #452 is the commit
    that gave it a reader -- before which "hide, chainmail, plate and a
    heavy shield were all free". So the shield's share is a live number
    and can be handed back on the way past.

    **Three controls, and each one is a different way to get this wrong.**
    A *light* shield costs nothing (`SHIELD_CHECK` is 0 for light, -2 for
    heavy), so waiving it must change nothing -- a feat that added a flat
    2 would pass the heavy case and fail here. An *unencumbered* skill is
    never penalised, so the waiver must not reach it; `ENCUMBERED` is four
    skills and Diplomacy is not one. And the armour's own share must
    survive: the card waives the shield and says nothing about plate.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.chargen import ARMOUR_CHECK, SHIELD_CHECK
    from combat_engine.engine import skills
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Gear
    from combat_engine.engine.dsl import REGISTRY

    def armed(armour: str, shield: int, *, feat: bool):  # noqa: ANN202
        world, me, _ = _board()
        gear = world.get(me, Gear) or world.add(me, Gear())
        gear.armour, gear.shield = armour, shield
        if feat:
            REGISTRY["f3779"].body(Cast(world=world, me=me, ref="f3779"))
        return world, me

    def rolled(world, me, skill: str) -> int:  # noqa: ANN001
        world.rng.loaded = 10
        return skills.check(world, me, skill).bonus

    # The number the waiver is about, read off the table rather than typed.
    heavy = SHIELD_CHECK.get("heavy", 0)
    out.that(heavy < 0,
             "a heavy shield carries a check penalty at all -- the premise,"
             " and 0 here would make every assertion below vacuous",
             f"SHIELD_CHECK heavy = {heavy}")

    bare = rolled(*armed("cloth", 2, feat=False), "stealth")
    with_feat = rolled(*armed("cloth", 2, feat=True), "stealth")
    out.that(with_feat - bare == -heavy,
             "the feat gives back exactly the heavy shield's penalty on an"
             " encumbered skill",
             f"{bare} -> {with_feat}, expected +{-heavy}")

    # control: a light shield costs nothing, so there is nothing to waive
    light_bare = rolled(*armed("cloth", 1, feat=False), "stealth")
    light_feat = rolled(*armed("cloth", 1, feat=True), "stealth")
    out.that(light_feat == light_bare,
             "a LIGHT shield waives to no change -- the control a flat +2"
             " would fail, since the table prices light at 0",
             f"{light_bare} -> {light_feat}")

    # control: an unencumbered skill was never penalised
    dip_bare = rolled(*armed("cloth", 2, feat=False), "diplomacy")
    dip_feat = rolled(*armed("cloth", 2, feat=True), "diplomacy")
    out.that(dip_feat == dip_bare,
             "and an unencumbered skill is untouched -- Diplomacy is not"
             " harder in a shield and the waiver must not reach it",
             f"{dip_bare} -> {dip_feat}")

    # control: the armour's own share survives the shield's waiver
    plate = ARMOUR_CHECK.get("plate", 0)
    pl_bare = rolled(*armed("plate", 2, feat=False), "stealth")
    pl_feat = rolled(*armed("plate", 2, feat=True), "stealth")
    out.that(plate < 0 and pl_feat - pl_bare == -heavy,
             "in plate AND a heavy shield only the shield is given back --"
             " the card waives one of the two and says nothing about armour",
             f"{pl_bare} -> {pl_feat}, plate still costs {plate}")


def both_printed_shapes_offered(out: Result) -> None:
    """"Close blast 3 **or** area burst 3 within 10" -- both, reachable. #614.

    `m5193a2` carried `dropped=("Power.reach_alt",)` with a note saying the
    alternative "has nowhere to sit: `reach_alt` is a numeric alternative,
    not a second reach kind". **There is no `Power.reach_alt` field at
    all**, and the thing that does the job -- `Range.alt` -- holds a whole
    `Range`, so a blast with a burst in its `alt` is the card exactly.

    **The assertion is that both are reachable, not that the header parses.**
    A `reach_of(1)` that answered correctly while `actions._aimings` offered
    only one action would be a form nobody can pick, which is the shape of
    failure this engine produces: right by inspection, absent in play.

    The control is the other two rows in the family, and it has now caught
    me twice. `m6683a0` prints "Melee 2, or 4 while bloodied" and
    `m1826a4` "close burst 2 (5 while bloodied)" -- *conditional* on a
    state, where `m5193a2`'s branch is a **choice**. Both are written now,
    and both the **other way**: one reach declared, no `alt`, the body
    narrowing. So the control asserts the distinction rather than their
    markers -- if either ever grows an `alt`, the branch mechanism is being
    stretched to carry a condition, which no branch can be gated on.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.engine import actions as A
    from combat_engine.engine.dsl import REGISTRY, area_of

    p = REGISTRY["m5193a2"]
    out.that(p.reach.branches == (0, 1),
             "the row declares two branches, which is what a printed `or`"
             " between two shapes means",
             f"{p.reach.branches}")
    kinds = (p.reach_of(0).kind, p.reach_of(1).kind)
    out.that(kinds == ("close_blast", "area_burst"),
             "and they are the two printed kinds, not one twice",
             f"{kinds}")
    out.that(not p.unfinished,
             "the row carries no marker now", f"{p.unfinished}")

    # **The board's own caster, not a second one spawned beside it.** The
    # first draft called `loader.spawn` for an `m5193` and asked about that
    # -- it offered zero actions, because a creature dropped onto the board
    # mid-probe has no action budget, and `_board(ref)` already poses the
    # row's own creature as the caster. The probe was posing its subject
    # twice and blaming the row for the one that could not act.
    world, who, _ = _board("m5193a2", 1)
    offered = A._aimings(world, who, "m5193a2")
    branches = sorted({a.branch for a in offered})
    out.that(branches == [0, 1],
             "and BOTH are offered in the action menu -- the half that makes"
             " the choice the player's rather than a form nobody can pick",
             f"{len(offered)} action(s), branches {branches}")

    a0 = area_of(world, who, p, None, 0)
    a1 = area_of(world, who, p, None, 1)
    out.that(a0 and a1 and a0 != a1,
             "the two cover different squares, so picking one is a real"
             " decision rather than a relabelling",
             f"{len(a0)} squares against {len(a1)}")

    # **The control, and it has caught me twice.** First draft: both
    # conditional rows stay marked -- then I wrote `m6683a0`. Second:
    # `m1826a4` stays marked -- then I wrote that too. Twice the assertion
    # was about a marker when the thing worth protecting is the *shape*,
    # and a marker assertion goes stale the moment the row is written.
    #
    # So: neither conditional row carries an `alt`. They declare the
    # permissive reach and narrow it in the body, which is a different
    # mechanism from this one and the reason the two are not one gap. If
    # either grows an `alt`, a branch is being gated on hit points.
    for ref, shape in (("m6683a0", "Melee 2 or 4 while bloodied"),
                       ("m1826a4", "close burst 2 (5 while bloodied)")):
        row = REGISTRY.get(ref)
        out.that(row is not None and row.reach.alt is None
                 and row.reach.branches == (0,),
                 f"{ref} -- \"{shape}\", conditional on a state -- is"
                 " written with ONE reach and no `alt`, which is what keeps"
                 " the two mechanisms distinguishable rather than blurred",
                 f"alt={getattr(row.reach, 'alt', None)}"
                 f" branches={getattr(row.reach, 'branches', None)}")


def reach_that_depends_on_a_state(out: Result) -> None:
    """"Melee 2, or 4 while bloodied" -- both, and the slide to match. #614.

    The header carries the **permissive** reach and the body narrows it,
    which is `m5466a0`'s answer to the same sentence. Its reasoning is the
    assertion here: the chooser offers from the header, so declaring the
    short reach would mean the row could never reach 4 squares even while
    bloodied -- the half the card is about.

    **Both halves move together and that is worth asserting separately.**
    The reach and the slide are the same number on this card, and a row that
    narrowed one and not the other would look right in a log: the attack
    lands, something slides, and only the distance is wrong.

    Asserted on the *offered action*, not just the header, for the reason
    `m5193a2`'s rule gives -- a reach that reads correctly while the menu
    offers something else is a form nobody can use.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.engine import actions as A
    from combat_engine.engine.components import Health
    from combat_engine.engine.dsl import REGISTRY, area_of

    p = REGISTRY["m6683a0"]
    out.that(p.reach.size == 4,
             "the header declares the permissive reach, 4 -- the one the"
             " chooser has to be able to offer",
             f"Melee {p.reach.size}")
    out.that(not p.unfinished, "and carries no marker", f"{p.unfinished}")

    def squares_at(bloodied: bool) -> int:
        world, me, _ = _board("m6683a0", 1)
        body = world.get(me, Health)
        body.hp = (body.max_hp // 2) if bloodied else body.max_hp
        return len(area_of(world, me, p, None, 0))

    whole, hurt = squares_at(False), squares_at(True)
    out.that(whole == hurt,
             "the *offered* area is the same either way, because the header"
             " is one number -- the narrowing is the body's job and this"
             " says so rather than pretending the menu changes",
             f"{whole} squares unhurt, {hurt} bloodied")

    world, me, _ = _board("m6683a0", 1)
    offered = A._aimings(world, me, "m6683a0")
    out.that(offered, "the row is reachable in the action menu at all",
             f"{len(offered)} action(s)")

    # The narrowing itself, which is the clause that was dropped.
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.query import enemies

    # **Who was hit, not whether anything was.** The first version of this
    # asked "did the attack land" and the control passed when it should not
    # have: `_restricted_to` **re-aims** to another enemy within reach rather
    # than throwing the attack away -- that is its documented job and about
    # 160 rows rely on it -- so something was always hit, just not the far
    # creature. The printed rule is about distance, so the distance is what
    # the assertion has to name.
    def hit_whom(bloodied: bool, at: int) -> tuple[int | None, int]:
        from combat_engine.engine.components import Position

        world, me, _ = _board("m6683a0", 1)
        body = world.get(me, Health)
        body.hp = (body.max_hp // 2) if bloodied else body.max_hp
        here = world.get(me, Position)
        foes = sorted(enemies(world, me))
        far = foes[0]
        # Everybody else out of the way, so a re-aim has nowhere to go but
        # the one creature this is about.
        for i, other in enumerate(foes[1:], start=1):
            spot = world.get(other, Position)
            if spot is not None:
                spot.square = (here.square[0] + 20 + i, here.square[1])
        spot = world.get(far, Position)
        spot.square = (here.square[0] + at, here.square[1])
        c = Cast(world=world, me=me, ref="m6683a0", targets=[far])
        struck: list[int] = []
        c.strike = lambda **kw: True  # ty: ignore[invalid-assignment]  -- a stub standing in for a die roll
        c.hit = lambda **kw: struck.append(kw.get("on") or -1)  # ty: ignore[invalid-assignment]  -- a stub standing in for a die roll
        REGISTRY["m6683a0"].body(c)
        return (struck[0] if struck else None), far

    got, far = hit_whom(True, 4)
    out.that(got == far,
             "bloodied, the creature 4 squares off is the one hit -- the"
             " clause the old marker dropped",
             f"hit {got}, wanted {far}")
    got, far = hit_whom(False, 4)
    out.that(got != far,
             "unhurt, that creature is NOT hit -- the control, and the whole"
             " reason the header cannot simply declare 4 and stop",
             f"hit {got}, the far creature is {far}")
    got, far = hit_whom(False, 2)
    out.that(got == far,
             "and unhurt it still reaches 2, which is its ordinary state",
             f"hit {got}, wanted {far}")


def one_rows_burst_grows_by_a_modifier(out: Result) -> None:
    """f1010: one named power's burst grows by Charisma, while raging. #614.

    **The row's own last blocker was "`c.widen_areas` has no way to name
    one row", and this is the assertion that it is false.** `widen_areas`
    exposes no `when=`, but it is one line over
    `c.bonus("blast_size", ...)` and `c.bonus` has always taken a gate --
    `dsl._stretched` says the ctx carries the row being measured. So the
    narrowing is a gate on the modifier, and the interesting question is
    not whether the number lands but whether it lands on **one** row.

    Hence the two controls that matter here are both about *scope*:

    * **another close burst 5 must not grow** -- without that, this rule
      would pass on a blanket `c.widen_areas(c.cha_mod)`, which is what
      the row was told to write and would have been wrong;
    * **not raging, nothing grows** -- the condition both halves hang on,
      read per measurement rather than at arming, because a rage can end
      mid-fight and the menu is redrawn constantly.

    And the premise, asserted rather than assumed: Charisma is worth
    something on this board. A `+0` would make every other assertion here
    vacuously true.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content.powers.barbarian.rage import RAGE, raging
    from combat_engine.engine import Keyword
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.dsl import REGISTRY, area_of

    ROAR = "p4932"
    row = REGISTRY["f1010"]
    out.that(not row.unfinished, "f1010 carries no marker now",
             f"{row.unfinished}")

    roar = REGISTRY[ROAR]
    # Another close burst of the same printed size, so a blanket widening
    # and a row-scoped one are distinguishable at all.
    twin = next((r for r, q in REGISTRY.items()
                 if q.reach and q.reach.kind == "close_burst"
                 and q.reach.size == roar.reach.size and r != ROAR), None)
    out.that(twin is not None,
             "there is a second close burst of the same size to compare"
             " against -- without one, 'only this row grew' is unprovable",
             f"{twin}")
    if twin is None:
        # The assertion above has already gone red, so returning hides
        # nothing -- and every assertion below measures the twin.
        return

    def squares(rage: bool) -> tuple[int, int, int]:
        world, me, _ = _board("f1010", 1)
        c = Cast(world=world, me=me, ref="f1010")
        cha = c.cha_mod
        if rage:
            c.stance(on=me, label=f"{ROAR} {RAGE}")
            assert raging(world, me)
        REGISTRY["f1010"].body(Cast(world=world, me=me, ref="f1010"))
        return (len(area_of(world, me, roar, None, 0)),
                len(area_of(world, me, REGISTRY[twin], None, 0)), cha)

    calm_roar, calm_twin, cha = squares(False)
    out.that(cha > 0,
             "Charisma is worth something on this board, so a growth is"
             " visible at all -- the premise the rest of this rests on",
             f"cha_mod {cha}")
    angry_roar, angry_twin, _ = squares(True)

    out.that(angry_roar > calm_roar,
             "raging, the named row's burst covers more ground -- the half"
             " three re-point notes had written off as unsayable",
             f"{calm_roar} squares calm, {angry_roar} raging")
    out.that(angry_twin == calm_twin,
             "and ANOTHER close burst of the same size does not grow -- the"
             " control that separates a gate on one row from the blanket"
             " `c.widen_areas(c.cha_mod)` the row was told to write",
             f"{calm_twin} calm, {angry_twin} raging")
    out.that(calm_roar == calm_twin,
             "unraging, the named row measures exactly like its twin -- so"
             " the growth is the rage's doing and not a header difference",
             f"{calm_roar} against {calm_twin}")

    # The damage half, through the event that arms it.
    from combat_engine.engine.components import Mods
    from combat_engine.engine.events import PowerUsed

    # **A row with the weapon keyword and one without**, because the bonus
    # is printed as "+2 to *weapon* damage rolls". The first version of this
    # probe only ever asked about a weapon row, so deleting the keyword gate
    # from the row changed nothing it measured -- a plant stayed green and
    # the finding was a missing assertion, not a bad plant.
    armed_row = next((r for r, q in REGISTRY.items()
                      if Keyword.WEAPON in (q.keywords or ())), "")
    bare_row = next((r for r, q in REGISTRY.items()
                     if q.keywords and Keyword.WEAPON not in q.keywords), "")

    def paid(rage: bool, used: str, rolling: str = "") -> int:
        world, me, _ = _board("f1010", 1)
        c = Cast(world=world, me=me, ref="f1010")
        if rage:
            c.stance(on=me, label=f"{ROAR} {RAGE}")
        REGISTRY["f1010"].body(Cast(world=world, me=me, ref="f1010"))
        world.bus.emit(PowerUsed(actor=me, power=used, targets=[]))
        mods = world.get(me, Mods)
        if mods is None:
            return 0
        return mods.total("damage", {"power": rolling or armed_row})

    out.that(paid(True, ROAR) == 2,
             "using the named row while raging pays +2 to a weapon damage"
             " roll", f"{paid(True, ROAR)}")
    out.that(paid(False, ROAR) == 0,
             "not raging, it pays nothing -- the condition, on the half the"
             " area assertions cannot see", f"{paid(False, ROAR)}")
    out.that(paid(True, twin) == 0,
             "and raging while using a DIFFERENT power pays nothing either"
             " -- the card names one row for both halves",
             f"{paid(True, twin)}")
    out.that(bool(bare_row) and paid(True, ROAR, rolling=bare_row) == 0,
             "and the +2 reaches a WEAPON row only -- the card says weapon"
             " damage, and `f454`'s note is that a barbarian's rage rows are"
             " not all of them",
             f"{paid(True, ROAR, rolling=bare_row)} on {bare_row}")


def area_that_depends_on_a_state(out: Result) -> None:
    """"Close burst 2 (5 while bloodied)" -- the same sentence about an area.

    `reach_that_depends_on_a_state` is this card's melee twin and the
    reasoning carries over unchanged: the header declares the **permissive**
    radius, because the chooser can only offer what the header says, and a
    burst 2 could never reach 5 squares even while bloodied -- the half the
    card is about. The body drops anybody past the real radius.

    **Two layers, because the area version can fail in a way the melee one
    cannot.** A burst both *offers* a target set and *resolves* one, so:

    * the chooser must hand the body the creature 4 squares off at all --
      that is what declaring 5 buys, and it is the assertion that would have
      gone red under the old `CloseBurst(2)` header;
    * and the body must refuse it when the creature is unhurt -- the
      control, without which the row would simply be a burst 5 that always
      reaches.

    **No `_restricted_to` here, and that is the difference worth recording.**
    `EACH_ENEMY` dispatches the body once per target (`dsl.use` sets
    `cast.target` and calls the body in a loop), so the narrowing is a
    distance guard; there is nobody to re-aim at when every enemy in the
    burst is already being offered in turn. The melee row needs the re-aim
    precisely because its chooser picked **one** creature.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.engine import actions as A
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health, Position
    from combat_engine.engine.dsl import REGISTRY, area_of
    from combat_engine.engine.query import enemies

    p = REGISTRY["m1826a4"]
    out.that(p.reach.kind == "close_burst" and p.reach.size == 5,
             "the header declares the permissive radius, 5 -- the one the"
             " chooser has to be able to offer",
             f"{p.reach.kind} {p.reach.size}")
    out.that(not p.unfinished, "and carries no marker", f"{p.unfinished}")

    def posed(bloodied: bool, at: int):  # noqa: ANN202
        """The creature, one enemy `at` squares off, everybody else parked."""
        world, me, _ = _board("m1826a4", 1)
        body = world.get(me, Health)
        body.hp = (body.max_hp // 2) if bloodied else body.max_hp
        here = world.get(me, Position)
        foes = sorted(enemies(world, me))
        far = foes[0]
        for i, other in enumerate(foes[1:], start=1):
            spot = world.get(other, Position)
            if spot is not None:
                spot.square = (here.square[0] + 30 + i, here.square[1])
        world.get(far, Position).square = (here.square[0] + at, here.square[1])
        return world, me, far

    # The offered area is the header's, both ways -- the menu is one number
    # and the narrowing is the body's job. Said plainly rather than left to
    # be inferred, because a reader's first guess is that the burst shrinks.
    sizes = []
    for hurt in (False, True):
        world, me, _ = posed(hurt, 4)
        sizes.append(len(area_of(world, me, p, None, 0)))
    out.that(sizes[0] == sizes[1],
             "the *offered* burst is the same either way -- the header is one"
             " number, so the narrowing cannot be the menu's doing",
             f"{sizes[0]} squares unhurt, {sizes[1]} bloodied")

    # Layer one: the chooser hands the body the far creature at all. This is
    # the assertion the old `CloseBurst(2)` header failed.
    world, me, far = posed(True, 4)
    offered = A._aimings(world, me, "m1826a4")
    reached = {t for a in offered for t in a.targets}
    out.that(far in reached,
             "the creature 4 squares off is OFFERED -- past the printed 2 and"
             " inside the bloodied 5, which is the whole reason the header"
             " carries the permissive radius",
             f"{len(offered)} action(s), {len(reached)} target(s) offered")

    # Layer two: the body, per target, exactly as `dsl.use` runs it.
    #
    # **Recorded off `c.push`, not `c.hit`.** The first version stubbed
    # `c.hit` -- the verb the melee twin's body calls -- and reported
    # nothing hit in every case, including the one the control needs to
    # fail. This card's effect is a push and a knockdown, so `c.hit` is
    # never reached and the probe was measuring a verb the row does not
    # use. A probe that reads the same in all three cases is measuring the
    # wrong thing, not finding a dead row.
    def hit_at(bloodied: bool, at: int) -> tuple[int | None, int]:
        world, me, far = posed(bloodied, at)
        c = Cast(world=world, me=me, ref="m1826a4", targets=[far])
        c.target = far
        struck: list[int] = []
        c.strike = lambda **kw: True  # ty: ignore[invalid-assignment]  -- a stub standing in for a die roll
        c.push = lambda *a, **kw: struck.append(kw.get("on") or far)  # ty: ignore[invalid-assignment]  -- a stub standing in for a die roll
        c.prone = lambda **kw: None  # ty: ignore[invalid-assignment]  -- a stub standing in for a die roll
        p.body(c)
        return (struck[0] if struck else None), far

    got, far = hit_at(True, 4)
    out.that(got == far,
             "bloodied, that creature is hit -- the clause the old marker"
             " dropped", f"hit {got}, wanted {far}")
    got, far = hit_at(False, 4)
    out.that(got is None,
             "unhurt, it is NOT hit -- the control, and the whole reason the"
             " header cannot simply declare 5 and stop",
             f"hit {got}, the far creature is {far}")
    got, far = hit_at(False, 2)
    out.that(got == far,
             "and unhurt it still reaches 2, which is its printed radius",
             f"hit {got}, wanted {far}")


def defective_entry(out: Result) -> None:
    """A defective part drops the **whole compendium entry**. #600.

    **Camille's rule, 2026-10-15:** *"defective entries should be dropped
    from the game... I mean that the ENTIRE compendium entry should be
    dropped if any part of it is defective."*

    It already worked that way for a stat block and for one reason worth
    repeating: a monster fielded without the thing its card is *about* is
    wrong in every fight, not merely incomplete. Nothing did it for an item
    or a power, so a tome whose Power was defective was still dealt, still
    worn, and still paid out its Property -- a player holding a working
    fraction of an object the compendium cannot describe.

    **The negative controls are what make this a rule rather than a
    blanket.** Three things must NOT be dropped:

    * a row in a *different* entry whose ref merely starts the same way --
      `m1034a1` is defective and `m10340a0` must not be, which the old
      `startswith(f"{ref}a")` walk in `loader.defective` got right only
      because no such pair existed;
    * a sibling of a `todo=` row. Unfinished is not wrong: `todo.py`
      reports that row ready the day its symbol lands, and the rest of the
      creature plays meanwhile;
    * anything at all, when no row in the entry is defective.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.engine import dsl
    from combat_engine.engine.dsl import REGISTRY, entry_defect, entry_of

    # ---- the shapes an entry is read off a ref -------------------------
    shapes = [
        ("m1234a5", "m1234", "a stat block's ability belongs to the creature"),
        ("m1932c0a0", "m1932c0",
         "a conjuration is its own entry, so the `c<n>` is KEPT -- dropping"
         " it would defect the item's namesake creature instead (#601)"),
        ("i601p1", "i601", "an item's Power belongs to the item"),
        ("i601x1", "i601", "and so does its Property, which is the whole point"),
        ("p123b", "p123", "a second card printed inside another power's entry"),
        ("p123", "p123", "and the first card is the same entry"),
        ("f959", "f959",
         "a feat is its own entry -- the f959/f960b pair is two different"
         " printed ids and the convention cannot be read off the ref"),
        ("cf:fighter-x", "cf:fighter-x", "a class feature is its own entry"),
    ]
    for ref, want, why in shapes:
        got = entry_of(ref)
        out.that(got == want, f"{ref} -> {want}: {why}", f"got {got!r}")

    # ---- the live tree, which is the half that matters -----------------
    real = sorted(r for r, p in REGISTRY.items() if p.defect)
    if not real:
        out.skip("no row in the tree carries defect=, so there is nothing to drop")
        return
    # **The one with siblings, not simply the first.** Carrying the drop
    # across an entry is the whole of this rule, and the first defective ref
    # alphabetically is a single-block item -- so taking `real[0]` skipped
    # the only assertion that distinguishes this from the row-level refusal
    # that already existed.
    def kin(r: str) -> int:
        return sum(1 for other in REGISTRY if entry_of(other) == entry_of(r))

    ref = max(real, key=kin)
    entry = entry_of(ref)
    siblings = sorted(r for r in REGISTRY if entry_of(r) == entry and r != ref)
    out.that(bool(entry_defect(ref)),
             f"the defective row itself is dropped ({ref})")
    if siblings:
        out.that(all(entry_defect(s) for s in siblings),
                 f"and every other row of its entry with it"
                 f" ({len(siblings)} sibling(s) of {entry})",
                 f"{siblings}")
        out.that(not any(REGISTRY[s].defect for s in siblings),
                 "none of which carries a defect= of its own -- so the drop"
                 " really is derived from one row and not listed twice")
    else:
        out.skip(f"{entry} has no sibling row to carry the drop to")

    # negative: a longer id that merely starts the same way
    stem = entry.rstrip("0123456789")
    digits = entry[len(stem):]
    longer = f"{stem}{digits}0a0" if digits else ""
    out.that(not longer or not entry_defect(longer),
             f"a ref whose id merely STARTS with a defective one is untouched"
             f" ({longer or 'no such shape'}) -- the negative control for a"
             f" prefix walk",
             f"entry_of({longer!r}) = {entry_of(longer) if longer else '-'}")

    # negative: a todo= row's entry is NOT dropped
    unfinished = sorted(
        r for r, p in REGISTRY.items()
        if p.todo and not p.defect and not entry_defect(r)
    )
    out.that(bool(unfinished) and not entry_defect(unfinished[0]),
             "a `todo=` row does not drop its entry -- unfinished is not"
             " wrong, and the rest of the creature plays meanwhile",
             f"{len(unfinished)} todo rows, none dropping an entry;"
             f" e.g. {unfinished[0] if unfinished else '-'}")

    # and the index is derived, not cached stale
    before = len({r for r in REGISTRY if entry_defect(r)})
    dsl._forget_defects()
    after = len({r for r in REGISTRY if entry_defect(r)})
    out.that(before == after,
             "the index rebuilds to the same answer after being forgotten,"
             " which is what makes caching it safe",
             f"{before} rows dropped before, {after} after")


def printed_regeneration(out: Result) -> None:
    """A stat block's `Regeneration N` heals it, and the printed clause stops it.

    **Camille's call, #602:** regeneration is a property of the creature like
    `resist`, `vulnerable` and `immune`, so it is stored beside them and
    applied by `loader.spawn`. I had argued for a query each trait row would
    read, worried that a loader-applied version would double-pay beside rows
    writing their own. Measured afterwards: **69 monsters print one, 0 rows
    on those 69 write an amount**, and the single call site on a regenerating
    creature is `m2068a3`, which *suppresses* it. So nothing double-paid and
    the state being guarded against did not exist -- while the state actually
    there was worse: all 69 regenerated **not at all**, silently, and the row
    whose clause suppresses its own regeneration had nothing to suppress.

    **The negative control is the suppression**, because the positive half
    alone cannot tell "the amount is applied" from "the amount is applied
    unconditionally". Of the 40 blocks printing a parenthesised clause, 23
    name a damage type and 11 a weapon property; storing the amount and
    dropping the clause would heal 34 creatures through the exact damage
    their card says stops them -- a wrong number rather than a missing one,
    which is harder to see.

    And the clause is read as a **list**: nine blocks print "takes acid or
    fire damage" and reading the one word beside "damage" stores only `fire`. That version
    looked right in a tally and was wrong for nine creatures.
    """
    import json

    from combat_engine.content import loader
    from combat_engine.db import game
    from combat_engine.engine.components import Health
    from combat_engine.engine.types import DamageType

    db = game()

    def turns(ref: str, hurt_by: DamageType | None = None,
              count: int = 2) -> list[int]:
        """How much it healed on each of its own first `count` turns.

        **Read per own-turn, which the first draft of this did not.** That
        version advanced the clock "until hit points move" -- and they
        always do, one round later, because the printed clause suppresses
        exactly one tick. So every suppression assertion passed by finding
        the *next* round's heal and the driver reported the engine broken
        when the engine was right. The lesson is the repo's own: a probe
        that waits for the outcome it is testing for will find it.
        """
        world, me, _ = _board()
        eid = loader.spawn(world, ref, (10, 10))
        health = world.get(eid, Health)
        floor = max(1, health.max_hp - 20)
        health.hp = floor
        if world.encounter is None:
            return []
        world.encounter.join(eid)
        if hurt_by is not None:
            from combat_engine.engine.cast import Cast
            Cast(world=world, me=me, ref="drivers:regen").damage(
                1, dtype=hurt_by, on=eid)
            # Undo the blow and keep the memory of it: the flag is set by
            # the event, so the hit points can go back without disturbing it.
            health.hp = floor
        from combat_engine.engine.events import TurnStart

        its_turn: list[int] = []
        world.bus.on(
            TurnStart,
            lambda ev: its_turn.append(1)
            if ev.actor == eid and not ev.ghost else None,
        )
        moved: list[int] = []
        was = health.hp
        for _ in range(240):
            seen = len(its_turn)
            world.encounter.advance()
            if len(its_turn) > seen:
                moved.append(health.hp - was)
                was = health.hp
                if len(moved) >= count:
                    break
        return moved

    # ---- a bare printed amount ----------------------------------------
    bare = [
        r for r, t, w in db.execute(
            "SELECT ref, regen_unless_damaged_by, regen_unless_struck_by "
            "FROM monster WHERE regeneration > 0 ORDER BY ref")
        if not json.loads(t or "[]") and not w and loader.usable(r)
    ]
    if not bare:
        out.skip("no monster prints an unconditional Regeneration")
        return
    ref = bare[0]
    amount = db.execute(
        "SELECT regeneration FROM monster WHERE ref = ?", (ref,)).fetchone()[0]
    got = turns(ref)
    out.that(got[:1] == [amount],
             f"a printed `Regeneration {amount}` heals that much at the start"
             f" of its own turn ({ref})",
             f"healed {got} over its first turns")

    # ---- a creature printing none ------------------------------------
    none = next(
        (r for r, in db.execute(
            "SELECT ref FROM monster WHERE regeneration = 0 AND level BETWEEN 3 AND 8"
            " ORDER BY ref")
         if loader.usable(r)), "")
    quiet = turns(none) if none else []
    out.that(bool(none) and not any(quiet),
             "a creature whose block prints no Regeneration heals nothing --"
             " the control that says this is read off the card and not"
             f" handed to everybody ({none})",
             f"healed {quiet}")

    # ---- the suppression, which is the whole of the evidence ----------
    conditional = [
        (r, json.loads(t or "[]"))
        for r, t in db.execute(
            "SELECT ref, regen_unless_damaged_by FROM monster "
            "WHERE regeneration > 0 ORDER BY ref")
        if json.loads(t or "[]") and loader.usable(r)
    ]
    if not conditional:
        out.skip("no monster prints a damage type that stops its regeneration")
        return
    # Prefer one printing TWO types, since that is the read that was wrong.
    ref, types = max(conditional, key=lambda pair: len(pair[1]))
    kinds = [DamageType(t) for t in types]
    amount = db.execute(
        "SELECT regeneration FROM monster WHERE ref = ?", (ref,)).fetchone()[0]
    clear = turns(ref)
    out.that(clear == [amount, amount],
             f"{ref} regenerates on every turn when nothing has stopped it",
             f"healed {clear}, printed {amount}")
    for kind in kinds:
        hurt = turns(ref, hurt_by=kind)
        out.that(hurt[:1] == [0],
                 f"and NOT on the turn after taking {kind.value} damage,"
                 f" which its card names -- the negative control",
                 f"healed {hurt}")
        out.that(hurt[1:2] == [amount],
                 "then resumes the turn after that, because the clause is"
                 " 'until the end of its next turn' and not a removal",
                 f"healed {hurt}")
    if len(kinds) > 1:
        out.that(True,
                 f"both of the two types its card lists are read"
                 f" ({', '.join(k.value for k in kinds)}) -- a one-word read"
                 f" stored only the second and let nine creatures regenerate"
                 f" through the first")
    other = next((k for k in DamageType
                  if k not in kinds and k is not DamageType.UNTYPED), None)
    if other is not None:
        spared = turns(ref, hurt_by=other)
        out.that(spared[:1] == [amount],
                 f"while {other.value} damage, which its card does NOT name,"
                 f" leaves the regeneration alone",
                 f"healed {spared}")


def sealed_space(out: Result) -> None:
    """"An enemy cannot enter this creature's space by any means."

    Eight stat blocks print that sentence word for word. The clause is
    **entirely about the waivers**, and that is what makes it worth driving:
    an occupied square is already closed to ordinary movement, so a row
    written as `pass` would have audited identically on every board where
    nobody was phasing. The two things that normally open a square are
    phasing through the occupant and the occupant having been made
    shareable, and both have to stop working.

    So the positive control is a **phasing** enemy, not a walking one. A
    walking enemy is refused by the plain occupancy rule and proves nothing
    about this verb at all -- it is the assertion that would have passed
    against an empty body.

    Three negative controls:

    * a phasing **ally** still passes, because the card says enemy;
    * a phasing enemy still passes a creature **without** the trait, which
      is what says the refusal comes from the trait and not from the change;
    * `c.shares_space` laid on a sealed creature does not re-open it, which
      is the half a `shares_space`-shaped implementation would have got
      backwards.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.durations import When
    from combat_engine.engine.movement import _clear
    from combat_engine.engine.query import allies, enemies, squares

    world, caster, _ = _board()
    foe = enemies(world, caster)[0]
    seat = next(iter(squares(world, foe)))
    here = Cast(world=world, me=caster, ref="drivers:sealed")

    # Ordinary movement: already refused, and that is the point about it.
    out.that(not _clear(world, caster, {seat}),
             "an ordinary creature cannot enter an occupied square anyway --"
             " which is why this rule is driven through a phasing one")

    # Phasing, with no seal: the waiver works.
    here.phasing(until=When.ENCOUNTER)
    out.that(_clear(world, caster, {seat}),
             "a phasing enemy passes through a creature that does NOT carry"
             " the trait -- the control that says the refusal below comes"
             " from the trait and not from the change")

    # Seal it. Same board, same phasing mover.
    Cast(world=world, me=foe, ref="drivers:sealed").blocks_entry(
        until=When.ENCOUNTER)
    out.that(not _clear(world, caster, {seat}),
             "and is refused once the occupant blocks entry -- \"by any"
             " means\" beating the phasing waiver, which is the whole of"
             " what the clause adds")

    # Shareable AND sealed: the seal wins.
    Cast(world=world, me=foe, ref="drivers:sealed").shares_space(
        until=When.ENCOUNTER)
    out.that(not _clear(world, caster, {seat}),
             "being made shareable does not re-open a sealed square -- the"
             " other waiver, and the one an implementation copied from"
             " `c.shares_space` would have got backwards")

    # An ally of the sealer, phasing: the card says enemy.
    #
    # **`allies(world, mate)`, not `enemies(world, mate)` minus the
    # caster.** The first draft asked for the sealer's enemies and took out
    # the caster, which is the caster's *own* side -- so it tested a
    # phasing enemy, got the correct refusal, and reported it as a failure.
    # The probe was backwards, not the verb.
    world, caster, _ = _board()
    mate = next((a for a in enemies(world, caster)), None)
    ally = next((a for a in allies(world, mate)), None) if mate is not None else None
    if mate is None or ally is None:
        out.skip("the board has no two creatures on the same side to test"
                 " the ally half")
        return
    Cast(world=world, me=mate, ref="drivers:sealed").blocks_entry(
        until=When.ENCOUNTER)
    Cast(world=world, me=ally, ref="drivers:sealed").phasing(
        until=When.ENCOUNTER)
    seat = next(iter(squares(world, mate)))
    out.that(_clear(world, ally, {seat}),
             "a phasing ALLY of the sealer still passes, because the card"
             " says enemy and the side is asked rather than assumed",
             f"ally {ally} into {mate}'s square {seat}")


def lost_mode(out: Result) -> None:
    """"It loses its fly speed until the end of its next turn", and gets it back.

    Five rows print a clause of this shape and `c.mode` only ever *raises* a
    speed, so there was no way to say any of them. The mirror is small; what
    is worth driving is the two things that are easy to get wrong in it.

    **Popped, not zeroed, and `query.phasing` is why.** Every other reader
    asks `modes.get(name)` for a truthy value, so 0 would have been the
    tidier spelling -- `dsl.Summon.modes` records "speed 0, fly 6" as a
    real printed shape. But `query.phasing` tests `"phasing" in mv.modes`,
    membership rather than value, so a phasing creature set to 0 would
    still be phasing and `m1032a1`'s clause would read as written and do
    nothing. Changing that reader instead is **not** safe: `c.phasing` lays
    `mode("phasing", speed_of(...))`, which is 0 for an immobilised
    creature, so a creature phasing *and* immobilised would stop phasing.

    **And it restores what was there, not what is there now.** A loss that
    popped the key and then put back whatever it found would hand the mode
    to a creature that never had it, or drop a longer grant laid underneath.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Movement
    from combat_engine.engine.durations import When
    from combat_engine.engine.movement import mode_of, phasing

    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:lose")
    moves = world.get(caster, Movement) or world.add(caster, Movement())

    # ---- a flier loses its flight and gets it back --------------------
    c.mode("fly", 8, until=When.ENCOUNTER)
    out.that(mode_of(world, caster, None) == "fly",
             "a creature with a fly speed flies, which is what `mode_of` is")
    held = c.lose_mode("fly", until=When.EONT)
    out.that(held is not None, "`c.lose_mode` lays a hold when there is a mode")
    out.that("fly" not in moves.modes,
             "the mode is POPPED rather than set to 0 -- see the docstring"
             " for why `query.phasing` decides that",
             f"modes {dict(moves.modes)}")
    out.that(mode_of(world, caster, None) == "walk",
             "so it walks while the loss stands")
    world.effects.end(held, "driver")
    out.that(moves.modes.get("fly") == 8,
             "and the printed 8 comes back when the loss ends -- the value it"
             " had, not a 0 and not an absence",
             f"modes {dict(moves.modes)}")

    # ---- phasing is a mode, and the membership reader is the point ----
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:lose")
    c.phasing(until=When.ENCOUNTER)
    out.that(phasing(world, caster), "a phasing creature is phasing")
    held = c.lose_mode("phasing", until=When.EONT)
    out.that(not phasing(world, caster),
             "and stops being phasing when it loses the mode -- the assertion"
             " a 0 would have failed, because `query.phasing` asks whether"
             " the key is THERE and not what it is")
    world.effects.end(held, "driver")
    out.that(phasing(world, caster), "and is phasing again afterwards")

    # ---- the negative control: a mode it never had --------------------
    world, caster, _ = _board()
    c = Cast(world=world, me=caster, ref="drivers:lose")
    moves = world.get(caster, Movement) or world.add(caster, Movement())
    before = dict(moves.modes)
    out.that(c.lose_mode("burrow", until=When.EONT) is None,
             "losing a mode the creature never had lays nothing -- \"loses"
             " its fly speed\" said by a grounded creature is a sentence"
             " about nothing, not a fault")
    out.that(dict(moves.modes) == before,
             "and changes no other mode while failing to find that one",
             f"{before} -> {dict(moves.modes)}")


def recharge_announced(out: Result) -> None:
    """A spent row coming back says so, on both of the two paths. #605.

    `triggers.py` carried the argument for this in a comment: there was no
    `PowerRecharged` event, `m6180a3` wanted one, and *"it wants adding on
    both paths at once"* -- a recharge happens either by the printed die at
    the start of a turn (`actions.recharge`) or by a printed condition that
    is an event (`Triggers`). Minting it on one path is how a row written
    against it is right in half the game and silently wrong in the other.

    **`rolled` carries which path, and the first draft got it wrong.** The
    die is rolled *before* the condition is asked, and deliberately: this
    module's contract is that every draw lands in `Rng.rolls` in order, so
    short-circuiting on a state would drop a draw a fixture has recorded.
    So a row printing **both** rolls the die even when the condition is
    what brings it back -- and reporting that die as the reason announces a
    roll that **missed** as the roll that succeeded.

    The invariant is therefore the assertion worth making: every announced
    `rolled` is either **0** -- the condition did it -- or **at least the
    printed recharge**. Never a number below it.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content import loader
    from combat_engine.engine import actions
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.events import PowerRecharged
    from combat_engine.engine.types import Usage

    rows = [
        (ref, p) for ref, p in sorted(REGISTRY.items())
        if p.usage is Usage.RECHARGE and p.recharge > 0 and ref.startswith("m")
        and loader.usable(ref.split("a")[0])
    ]
    if not rows:
        out.skip("no usable monster row prints a recharge die")
        return

    def rolls(ref: str, stock: str, boards: int = 40) -> tuple[int, list[int]]:
        """How many times it came back, and what each event announced."""
        restored, announced = 0, []
        for seed in range(1, boards + 1):
            world, _me, _ = _board("m145a0", seed)
            eid = loader.spawn(world, stock, (12, 12))
            known = world.need(eid, Powers)
            if ref not in known.known:
                known.known.append(ref)
            known.note_use(ref, 1)
            world.bus.on(PowerRecharged, lambda ev: announced.append(ev.rolled))
            actions.recharge(world, eid)
            restored += ref not in known.spent
        return restored, announced

    ref, power = rows[0]
    restored, announced = rolls(ref, ref.split("a")[0])
    out.that(restored > 0, f"{ref} comes back at least once over 40 boards",
             f"{restored} restores")
    out.that(len(announced) == restored,
             "and every single restore announces a PowerRecharged -- one"
             " each, no more and no fewer",
             f"{restored} restores, {len(announced)} events")
    out.that(all(r == 0 or r >= power.recharge for r in announced),
             f"every announced `rolled` is 0 or at least the printed"
             f" {power.recharge} -- never a die that missed",
             f"saw {sorted(set(announced))}, printed recharge"
             f" {power.recharge}")

    # **The negative control: a row that stays spent says nothing.** Without
    # it "every restore announces one" passes against a verb that announces
    # on every attempt.
    quiet = 0
    for seed in range(1, 41):
        world, _me, _ = _board("m145a0", seed)
        eid = loader.spawn(world, ref.split("a")[0], (12, 12))
        known = world.need(eid, Powers)
        if ref not in known.known:
            known.known.append(ref)
        known.note_use(ref, 1)
        heard: list[int] = []
        world.bus.on(
            PowerRecharged,
            lambda ev, into=heard: into.append(ev.rolled),
        )
        actions.recharge(world, eid)
        if ref in known.spent and heard:
            quiet += 1
    out.that(quiet == 0,
             "and a row that is still spent afterwards announced nothing --"
             " the control that says this fires on the restore and not on"
             " the attempt",
             f"{quiet} boards announced a recharge that did not happen")

    # The condition path, forced: the one row printing both a die and a
    # condition, with the condition made true, must announce `rolled=0`.
    both = [
        (r, p) for r, p in sorted(REGISTRY.items())
        if p.usage is Usage.RECHARGE and p.recharge > 0
        and p.recharge_while is not None and loader.usable(r.split("a")[0])
    ]
    if not both:
        out.skip("no usable row prints both a recharge die and a condition")
        return
    ref, power = both[0]
    was = power.recharge_while
    try:
        # Forced rather than waited for: the printed state does not arise on
        # a bare probe board, and the point being asserted is which number
        # the event carries, not whether that state can happen.
        object.__setattr__(power, "recharge_while", lambda _w, _e: True)
        seen: list[int] = []
        for seed in range(1, 13):
            world, _me, _ = _board("m145a0", seed)
            eid = loader.spawn(world, ref.split("a")[0], (12, 12))
            known = world.need(eid, Powers)
            if ref not in known.known:
                known.known.append(ref)
            known.note_use(ref, 1)
            world.bus.on(PowerRecharged, lambda ev: seen.append(ev.rolled))
            actions.recharge(world, eid)
    finally:
        object.__setattr__(power, "recharge_while", was)
    out.that(bool(seen) and all(r == 0 or r >= power.recharge for r in seen),
             f"{ref} prints a die AND a condition: with the condition true,"
             f" every announced `rolled` is 0 or a die that actually made"
             f" the printed {power.recharge} -- the assertion a `back`"
             f" instead of a `by_die` fails",
             f"saw {sorted(set(seen))} over {len(seen)} restores")

    # ---- the SECOND path, which the first draft of this driver missed ----
    #
    # Dropping the emit from `triggers._recharge` and leaving
    # `actions.recharge` alone left every assertion above green. The whole
    # argument for this commit is "both paths at once", so a driver that
    # covers one of them is the shape of mistake it exists to prevent.
    #
    # 184 usable monster rows declare a recharge *trigger* -- "Recharge when
    # first bloodied" -- and those never go through the die at all.
    triggered = [
        (r, p) for r, p in sorted(REGISTRY.items())
        if getattr(p, "recharges", ()) and r.startswith("m")
        and loader.usable(r.split("a")[0])
    ]
    if not triggered:
        out.skip("no usable monster row declares a recharge trigger")
        return
    # **Tried until one fires, not the first one.** Most of these printed
    # conditions want a board -- "when an adjacent creature becomes
    # bloodied" needs somebody adjacent -- and taking `triggered[0]` left
    # this half a `skip`, which is the same hole as not writing it.
    fired = ()
    for ref, power in triggered[:40]:
        for trig in power.recharges:
            world, _me, _ = _board("m145a0", 1)
            if world.encounter is None:
                continue
            holder = loader.spawn(world, ref.split("a")[0], (12, 12))
            world.encounter.join(holder)
            known = world.need(holder, Powers)
            if ref not in known.known:
                known.known.append(ref)
            known.note_use(ref, 1)
            heard: list[int] = []
            world.bus.on(
                PowerRecharged, lambda ev, into=heard: into.append(ev.rolled)
            )
            # Handed straight to the handler rather than fabricated onto the
            # bus: what is asserted is that a restore announces, not how the
            # bus routes to it.
            fields = getattr(trig.event, "__dataclass_fields__", {})
            try:
                made = trig.event(actor=holder) if "actor" in fields else trig.event()
                world.encounter.triggers._recharge(made)
            except Exception:
                # This event class wants more state than a bare build gives.
                continue
            if ref not in known.spent:
                fired = (ref, trig.event.__name__, list(heard))
                break
        if fired:
            break
    if not fired:
        out.skip("no recharge condition in the first 40 rows is met by a"
                 " bare event, so this path cannot be posed on this board")
    else:
        got_ref, event_name, heard = fired
        out.that(len(heard) == 1 and heard[0] == 0,
                 f"the condition path announces too, with `rolled` 0 --"
                 f" {got_ref} came back on a {event_name} and no die was"
                 f" rolled. **This is the assertion that was missing**: a"
                 f" plant dropping the emit from `triggers._recharge` alone"
                 f" left every other rule here green",
                 f"heard {heard}")


def regeneration_resumed(out: Result) -> None:
    """"Its regeneration immediately reactivates" -- the other side of the clause.

    `c.regeneration`'s suppression lived in a local `{"skip": False}`, so
    nothing outside could ask whether a creature's regeneration was off,
    let alone switch it back on. That is the state `c.latched`'s docstring
    describes for the striker latch, fixed there in #569 for the same
    reason: **two rows are the same question from two sides.** Here the
    second side is `m2068a3`, which has been re-marked three times -- twice
    at a `Cast` verb and once, by me, at the ETL -- while the gap was that
    the flag was unreachable. #602.

    Driven because `audit` cannot pose it: the row wants a *second*
    creature of its own kind, within 10 squares, whose regeneration is
    currently off, and the harness fires each row once on a fresh board.
    So this is the only evidence it works, and the `KNOWN_SILENT` entry
    points here rather than arguing.

    The negative control is the row's own guard: with nobody suppressed it
    must produce **nothing**, because the card says "one creature whose
    regeneration is currently inactive" and a minor action spent on an
    empty set is a minor action the creature did not have to spend.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content import loader
    from combat_engine.content.monsters.level_10 import soldiers_sa
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.types import DamageType

    world, me, _ = _board()
    first = loader.spawn(world, "m2068", (10, 10))
    second = loader.spawn(world, "m2068", (11, 10))
    asking = Cast(world=world, me=second, ref="drivers:regen")
    out.that(not asking.regen_suppressed(),
             "a creature the loader just put down regenerates -- nothing is"
             " suppressed before anything suppresses it")

    Cast(world=world, me=me, ref="drivers:regen").damage(
        1, dtype=DamageType.FIRE, on=second)
    out.that(asking.regen_suppressed(),
             "fire -- which this block's card names -- switches it off, and"
             " the switch is now ASKABLE from outside the closure that used"
             " to hold it")

    mark = len(world.bus.log)
    soldiers_sa.m2068a3(Cast(world=world, me=first, ref="m2068a3"))
    out.that(not asking.regen_suppressed(),
             "and its own kind spends a minor to switch it back on, which is"
             " what the card says and what three markers were looking for"
             " somewhere else")
    out.that(len(world.bus.log) > mark,
             "the resume leaves a trace, so it is not a silent state poke",
             f"{len(world.bus.log) - mark} event(s)")

    # The negative control: nobody to help.
    #
    # **It asks about the prompt as well as the log, and the first draft
    # asked only about the log -- which a plant proved too weak.** Dropping
    # the `c.regen_suppressed` filter from the row's own body left this
    # green: the body then offered a choice among every ally in range,
    # `c.resume_regeneration` found nothing to end, and no event was
    # emitted. A decision is not an event, so the log cannot see one. The
    # card says "one creature **whose regeneration is currently
    # inactive**", so offering a choice at all when there is none is the
    # fault, and that is what is asserted now.
    world, _me, _ = _board()
    alone = loader.spawn(world, "m2068", (10, 10))
    loader.spawn(world, "m2068", (11, 10))
    asked: list[str] = []
    first_decide = world.decide

    def watching(who: int, kind: str, pool: list, what: str = ""):  # noqa: ANN202
        asked.append(kind)
        return first_decide(who, kind, pool, what)

    world.decide = watching
    mark = len(world.bus.log)
    soldiers_sa.m2068a3(Cast(world=world, me=alone, ref="m2068a3"))
    out.that(len(world.bus.log) == mark,
             "with nobody's regeneration off the row emits nothing",
             f"{len(world.bus.log) - mark} event(s)")
    out.that(not asked,
             "and offers no choice either -- the control that bites when a"
             " body picks among every ally in range and only then discovers"
             " there was nothing to do",
             f"decisions asked: {asked}")


def racial_power_riders(out: Result) -> None:
    """Two feats that answer one racial power, and the ref resolves now.

    `f1541` and `f3160` both sat on `spec.monster_ref()` with docstrings
    saying the spec printed `x_m5139a3` -- the ETL's mark for a ref it
    could not resolve -- so there was "no power to ask whether it is
    active, and nothing to mirror". The spec reads `p6188` today: a
    declared `r37` racial power. **The marker outlived its reason**, which
    is why both are driven here rather than trusted.

    The history is worth one line: that marker was once spelled
    `m5139a3`, a bare monster ref, so `todo.py` watched for it -- and a
    level-13 wave declared an `m5139a3` that is a demon brute's temporary
    hit points, nothing to do with either feat. One spelling, two
    unrelated needs.

    **Both controls are the point.** `f1541` mirrors "the same resistance
    that the power grants you", read rather than restated, so with nothing
    standing there is nothing to mirror and it must lay no aura at all.
    `f3160`'s Will bonus is gated on still holding a power point when the
    racial power goes off, so at zero points it must pay nothing.
    """
    import combat_engine.content  # noqa: F401  -- fills the registry
    from combat_engine.content.feats import general_j, general_o
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Mods, PowerPoints, Powers
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.events import PowerUsed
    from combat_engine.engine.types import Defense

    out.that("p6188" in REGISTRY,
             "p6188 is declared, which is what both markers said it was not")

    def armed(ref: str):  # noqa: ANN202
        world, me, _ = _board()
        known = world.need(me, Powers)
        for r in (ref, "p6188"):
            if r not in known.known:
                known.known.append(r)
        return world, me, Cast(world=world, me=me, ref=ref)

    def auras(world) -> int:  # noqa: ANN001
        return len([z for _i, z in world.zones.all() if z.aura])

    # ---- f1541: mirror the racial resistance onto adjacent allies ----
    world, me, c = armed("f1541")
    general_j.f1541(c)
    Cast(world=world, me=me, ref="p6188").resist(5)
    before = auras(world)
    world.bus.emit(PowerUsed(actor=me, power="p6188", targets=[]))
    out.that(auras(world) == before + 1,
             "f1541 lays an aura when the racial power goes off, and an aura"
             " rather than a modifier because adjacency changes as people"
             " walk -- `f1542` beside it is the same shape",
             f"{before} -> {auras(world)}")

    world, me, c = armed("f1541")
    general_j.f1541(c)
    before = auras(world)
    world.bus.emit(PowerUsed(actor=me, power="p6188", targets=[]))
    out.that(auras(world) == before,
             "and lays NOTHING when there is no resistance standing to"
             " mirror -- the control, and the one a row that restated the"
             " printed 5 instead of reading it would fail",
             f"{before} -> {auras(world)}")

    # ---- f3160: the Will bonus, gated on a power point ---------------
    for points, want in ((1, 2), (0, 0)):
        world, me, c = armed("f3160")
        pool = world.get(me, PowerPoints) or world.add(me, PowerPoints())
        pool.points = points
        c.trigger = PowerUsed(actor=me, power="p6188", targets=[])
        general_o.f3160(c)
        mods = world.get(me, Mods)
        got = mods.total(Defense.WILL, {}) if mods else 0
        out.that(got == want,
                 f"f3160 pays {want} to Will on {points} power point(s)"
                 + ("" if points else " -- the control: the card gates the"
                                      " bonus on still holding one"),
                 f"Will modifier {got}")


def once_spent(out: Result) -> None:
    """A `once=` hold is spent by a handler that only rewrites its event.

    Nothing printed says this either -- it is the same kind of engine
    property `reentry` measures, and it had been wrong twice in the same
    place for the same reason. `c.watch`'s spend test asks *"did the handler
    do anything"* by *enumerating ways of doing something*: it grew the bus
    log, or it changed the effect list. Both enumerations missed a case.

    * `c.summon` emits nothing at all, so a once-only summon never spent and
      fired every round. The effect-count term was added for it.
    * A handler whose whole effect is rewriting a field on the event it was
      handed -- `ev.amount -= cut` -- moves neither count, so `once=` never
      spent and the hold fired on **every** matching event for its whole
      duration. Three rows, #540.

    The sharpest of the three is the reason this is driven rather than
    trusted: its docstring says it was written as a `DamageRolled` watch
    *expressly* to avoid `c.resist`, "which would shave every other blow the
    ally took as well" -- and the bug made it shave every blow. A row can
    state its own intent correctly and be defeated by the engine under it.

    **`audit.py` cannot see any of this.** All three rows fire and do
    something; they do it too many times. Firing twice and measuring the
    second firing is the only thing that distinguishes them, which is why
    the second assertion here is the load-bearing one.

    The third assertion is the guard that must survive the fix: a handler
    that *reads and rejects* still must not spend, or "the first time you hit
    a bloodied enemy" goes back to being burned by a miss on a healthy one --
    the original fault the enumeration was introduced to cure.
    """
    from collections.abc import Callable

    from combat_engine.engine.cast import Cast
    from combat_engine.engine.durations import When
    from combat_engine.engine.ecs import World
    from combat_engine.engine.events import DamageRolled, Window
    from combat_engine.engine.types import DamageType

    def blow(world: World, who: int, amount: int = 10) -> DamageRolled:
        return world.bus.emit(DamageRolled(
            source=who, target=who, amount=amount,
            dtype=DamageType.FIRE, detail="drivers:once",
        ))

    # Built per board rather than closed over `me`: the second half rebinds
    # it, and a late-bound closure would still have worked here while
    # breaking silently the moment the two halves were reordered.
    def shaver(whose: int) -> Callable[[DamageRolled], None]:
        def shave(ev: DamageRolled) -> None:
            if ev.target == whose:
                ev.amount -= 3
        return shave

    # -- the bug: a mutate-only handler, fired twice ----------------------
    world, me, _ = _board(seed=1)
    c = Cast(world=world, me=me, ref="drivers:once")
    c.watch(DamageRolled, shaver(me), until=When.ENCOUNTER, on=me,
            once=True, window=Window.BEFORE, label="drivers:once")

    first = blow(world, me)
    out.that(first.amount == 7,
             "a once= handler that only rewrites its event does fire"
             f" (10 -> {first.amount})")

    second = blow(world, me)
    out.that(second.amount == 10,
             "and is SPENT by having done so -- the second blow is untouched,"
             " which is the whole of #540: three rows shaved every blow for"
             f" their duration instead of one (10 -> {second.amount})")

    # -- the guard: rejecting must not spend ------------------------------
    # Fired at somebody else first, so the handler's `if` says no. If the
    # fix spent the hold on a rejected event it would be the original fault
    # restored, and the assertion above would still pass -- which is why
    # this one is here and not folded into it.
    world, me, foe = _board(seed=1)
    c = Cast(world=world, me=me, ref="drivers:once")
    c.watch(DamageRolled, shaver(me), until=When.ENCOUNTER, on=me,
            once=True, window=Window.BEFORE, label="drivers:once")

    rejected = blow(world, foe)
    wanted = blow(world, me)
    out.that(rejected.amount == 10 and wanted.amount == 7,
             "while a handler that reads and REJECTS does not spend the hold"
             " -- the fault the spend test was introduced to cure, which the"
             f" fix must not restore (other {rejected.amount}, mine"
             f" {wanted.amount})")

def creature_kinds(out: Result) -> None:
    """Every player character is a natural humanoid, and an origin replaces it.

    Camille's ruling, #542. Nothing on any race's page says the universal
    half, which is exactly why nothing had it: the compendium omits it
    because it is the default, and the 19 races that print a type sentence
    carry an **additional** type rather than their only one.

    Measured before the fix: every character answered `[]` while every
    monster answered three or four words. So `humanoid` -- the second
    most-asked type word in the tree, 22 sites -- was False for the whole
    party, and five *written* rows read false against any party:
    `m2015a3` raised no slain character, and a level-4 skirmisher's target
    line `kinds=frozenset({"humanoid"})` was offered against an empty pool.
    None of it showed up anywhere, because every creature on the audit
    board is a monster and a monster has the word.

    Four things, and the fourth is the one guarding the design:

    * **a built character is a natural humanoid**, which is the default;
    * **an origin displaces `natural`** -- a fey character is not also
      natural, and `c.set_origin(instead_of=)` lays the `unorigin:` that
      takes it off;
    * **a keyword does not displace** -- `reptile`, `undead` and
      `shapechanger` sit beside `natural` quite correctly, which is why
      only 15 of the 19 rows name a displacement;
    * **an entity with no `Build` gets nothing.** The default is keyed on
      the component `chargen.spawn` adds, not on the absence of a stat
      block, because the audit dummy also has no stat block and its
      `types=` knob depends on having *no* words unless given some. Keyed
      the lazy way, every row gating on `humanoid` would start passing on
      the audit board -- the change would hide faults instead of finding
      them, and nothing would have said so.
    """
    from combat_engine import story
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health, Position
    from combat_engine.engine.durations import When

    fielded = story.field_encounter(seed=7, level=3)
    world = fielded.world
    pc = next(e for e in sorted(world.entities) if not query.stat_block(world, e))

    base = query.kinds_of(world, pc)
    out.that("humanoid" in base and "natural" in base,
             "a built character is a natural humanoid, which no race's page"
             f" prints and nothing had before #542 ({sorted(base)})")

    # An origin is exclusive.
    Cast(world=world, me=pc, ref="drivers:kinds").set_origin(
        "fey", until=When.ENCOUNTER, instead_of="natural")
    fey = query.kinds_of(world, pc)
    out.that("fey" in fey and "natural" not in fey and "humanoid" in fey,
             "and an origin REPLACES natural rather than stacking -- a fey"
             f" character is fey and humanoid, not also natural ({sorted(fey)})")

    # A keyword is additive. Fresh board, or the fey hold above is still up.
    other = story.field_encounter(seed=8, level=3)
    w2 = other.world
    pc2 = next(e for e in sorted(w2.entities) if not query.stat_block(w2, e))
    Cast(world=w2, me=pc2, ref="drivers:kinds").set_origin(
        "reptile", until=When.ENCOUNTER)
    kw = query.kinds_of(w2, pc2)
    out.that("reptile" in kw and "natural" in kw,
             "while a keyword is additive and keeps natural, which is why 4"
             f" of the 19 rows name no displacement ({sorted(kw)})")

    # The guard: no `Build`, no words. This is what keeps the audit dummy
    # wordless and the board honest.
    bare = w2.spawn(Position(square=(1, 1)), Health(max_hp=10))
    none = query.kinds_of(w2, bare)
    out.that(not none,
             "and an entity with no Build gets NO words -- the audit dummy"
             " must stay wordless or every humanoid gate would start"
             f" passing on the board ({sorted(none)})")


def living_targets(out: Result) -> None:
    """"One living creature" is not a set operation, and #411 said so first.

    Seven rows print the restriction. Every one of them spelled it
    `kinds_without={"undead"}` and carried the remainder as a marker,
    because the exact test cannot be written as an any-of negative:

        not undead, and not construct unless it carries living

    Twenty-five stat blocks carry **both** `living` and `construct` and
    their cards call them living, while a construct carrying neither word
    is not living at all. So the loose negative admits a non-living
    construct and the tight one refuses the twenty-five. `query.living` is
    the one `if` that says it, and `Target(living=True)` is the header
    saying it -- which matters because a target restriction has to narrow
    the **pool**, or the row is offered against creatures it then declines.

    The marker history is the reusable part: `Target.living` was right,
    went to `chargen.kind_words()` when a character turned out to carry no
    type words at all, and comes back now that #542 supplies them. Both
    re-points were correct when made. The symbol that finally closed it is
    the one it started on.

    Four cases, and the third is the one no previous spelling could pass.
    """
    from combat_engine import story
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.dsl import Target, _stands_right
    from combat_engine.engine.durations import When

    fielded = story.field_encounter(seed=7, level=3)
    world = fielded.world
    party = [e for e in sorted(world.entities) if not query.stat_block(world, e)]
    caster = next(e for e in sorted(world.entities) if query.stat_block(world, e))
    aim = Target("enemy", 1, label="one living creature", living=True)

    def admits(eid: int) -> bool:
        return _stands_right(world, caster, aim, eid, "drivers:living")

    out.that(all(admits(p) for p in party),
             "an ordinary character is a living creature, which it could not"
             " be before #542 gave it any type words at all")

    def word(eid: int, *words: str) -> None:
        for w in words:
            Cast(world=world, me=eid, ref="drivers:living").set_origin(
                w, until=When.ENCOUNTER)

    word(party[0], "undead")
    out.that(not admits(party[0]),
             "an undead creature is refused, which is the half a plain"
             " kinds_without={'undead'} already got right")

    word(party[1], "construct")
    out.that(not admits(party[1]),
             "a construct carrying no living word is ALSO refused -- the half"
             " no any-of negative could say, and the reason seven rows"
             " carried a marker (#411)")

    word(party[2], "construct", "living")
    out.that(admits(party[2]),
             "while a construct that DOES carry living is admitted, which is"
             " the 25 stat blocks a tight kinds_without={'undead',"
             " 'construct'} would have wrongly refused")


def regeneration_suspended(out: Result) -> None:
    """What switches a regeneration off for a turn, in both of its kinds.

    Twenty-four rows carried `compendium.silvered` -- a marker blaming the
    source -- and **all twenty-four specs print the clause in full**. The
    compendium was missing nothing; the engine held no notion of what a
    weapon is made of. `i469p1`'s own docstring recorded that it had been
    re-pointed *from* `Weapon.silvered`, which was right, *to* the
    compendium symbol, which was not: the exact ledger fault #360 names,
    pointed the other way.

    Silver is a weapon property. `c.gains_property` writes it onto the
    per-character `Gear.weapons` copy -- the mechanism `weapon_dice`
    already used, which needs no reader because `_high_crit`, `_weapon_is`
    and `query.holding` all see it.

    Three things, and the second is the one no amount of reading would
    have settled:

    * **the property lands**, which is the setter half nine item and feat
      rows print;
    * **the suspension costs exactly one turn** -- heal, then nothing,
      then heal again. A flag cleared on a clock rather than consumed by
      the tick it suppresses would race the tick, which is why
      `m5798a1` settled the consumed shape for the acid version;
    * **a plain weapon suspends nothing**, the negative control. Without
      it this passes on an implementation that suspends regeneration
      after any hit at all;
    * **a damage type does it too, and the wrong type does not.** Camille
      asked whether the mechanism should be less specific than silver, and
      it should: these cards come in two kinds and the mechanism under
      them is one. A material is read off the `Hit`, because only that
      carries `attacker`; a damage type is a field on `DamageApplied`. Two
      feeds, one consumed flag. **Four spellings had grown for the single
      idea** -- `suspended_by=`, `suppressed_by=`, `when=`, and three rows
      that hand-rolled the watch -- and asking the question found three
      *silvered* rows hiding under `suspended_by=`, outside the family's
      own count.

    The trap worth recording: `weapon_of` finds the swing through
    `ev.attacker`, and `DamageApplied` carries `source` instead. A watch on
    damage -- the obvious reading of "when it takes damage from a silvered
    weapon" -- would have answered False for ever, and all fifteen rows
    would have audited clean while doing nothing.
    """
    from combat_engine import story
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Gear, Health
    from combat_engine.engine.durations import When
    from combat_engine.engine.events import DamageApplied, Hit, TurnStart
    from combat_engine.engine.types import DamageType

    def fight(silver: bool) -> tuple[int, int, int]:
        fielded = story.field_encounter(seed=7, level=3)
        world = fielded.world
        pc = next(e for e in sorted(world.entities)
                  if not query.stat_block(world, e))
        mon = next(e for e in sorted(world.entities)
                   if query.stat_block(world, e))
        hurt = world.get(mon, Health)
        assert hurt is not None
        hurt.hp = max(1, hurt.max_hp - 40)
        if silver:
            Cast(world=world, me=pc, ref="drivers:silver").gains_property(
                "silvered", every=True, on=pc)
        Cast(world=world, me=mon, ref="drivers:silver").regeneration(
            5, on=mon, until=When.ENCOUNTER, unless_struck_by="silvered")
        rnd = [1]

        def turn() -> int:
            rnd[0] += 1
            was = hurt.hp
            world.bus.emit(TurnStart(actor=mon, round=rnd[0], ghost=False))
            return hurt.hp - was

        clean = turn()
        world.bus.emit(Hit(attacker=pc, target=mon, power="rba", critical=False))
        after = turn()
        again = turn()
        return clean, after, again

    board = story.field_encounter(seed=7, level=3)
    who = next(e for e in sorted(board.world.entities)
               if not query.stat_block(board.world, e))
    laid = Cast(world=board.world, me=who, ref="drivers:silver").gains_property(
        "silvered", every=True, on=who)
    held = board.world.get(who, Gear)
    assert held is not None
    out.that(laid > 0 and all("silvered" in w.properties for w in held.weapons),
             f"a weapon can be silvered at all, which is what 24 rows wanted"
             f" and no page was missing ({laid} weapon(s))")

    clean, after, again = fight(silver=True)
    out.that((clean, after, again) == (5, 0, 5),
             "and a silvered hit suspends the regeneration for EXACTLY one"
             " turn -- consumed by the tick it suppresses, not cleared on a"
             f" clock that would race it (healed {clean}, {after}, {again})")

    plain = fight(silver=False)
    out.that(plain == (5, 5, 5),
             "while a plain weapon suspends nothing, without which this"
             " passes on an implementation that stops regeneration after any"
             f" hit at all (healed {plain[0]}, {plain[1]}, {plain[2]})")

    # -- the other kind: a damage type, read off DamageApplied -----------
    def burn(dtype: DamageType,
             dtypes: tuple[DamageType, ...] = ()) -> tuple[int, int, int]:
        fielded = story.field_encounter(seed=7, level=3)
        world = fielded.world
        mon = next(e for e in sorted(world.entities)
                   if query.stat_block(world, e))
        hurt = world.get(mon, Health)
        assert hurt is not None
        hurt.hp = max(1, hurt.max_hp - 40)
        Cast(world=world, me=mon, ref="drivers:regen").regeneration(
            5, on=mon, until=When.ENCOUNTER,
            unless_damaged_by=(DamageType.ACID, DamageType.FIRE))
        rnd = [1]

        def turn() -> int:
            rnd[0] += 1
            was = hurt.hp
            world.bus.emit(TurnStart(actor=mon, round=rnd[0], ghost=False))
            return hurt.hp - was

        clean = turn()
        world.bus.emit(DamageApplied(
            source=mon, target=mon, amount=1, dtype=dtype, dtypes=dtypes,
            detail="drivers", absorbed=0, hp=hurt.hp))
        after = turn()
        return clean, after, turn()

    acid = burn(DamageType.ACID)
    out.that(acid == (5, 0, 5),
             "a named damage type suspends it the same way and for the same"
             " one turn, through the same consumed flag -- the generalisation"
             f" Camille asked for (healed {acid[0]}, {acid[1]}, {acid[2]})")

    cold = burn(DamageType.COLD)
    out.that(cold == (5, 5, 5),
             "and an unnamed type does nothing, which is the control that"
             " separates 'suspended by acid or fire' from 'suspended by"
             f" being hurt' (healed {cold[0]}, {cold[1]}, {cold[2]})")

    # **A blow that is two types at once, with the named one second.**
    # #420's lesson, and the assertion this rule was missing: with a
    # single-type blow, `ev.dtype in wanted` and `wanted &
    # set(ev.types())` agree, so a plant swapping one for the other
    # stayed green. It only separates them here.
    pair = burn(DamageType.COLD, (DamageType.COLD, DamageType.FIRE))
    out.that(pair == (5, 0, 5),
             "and a blow that is TWO types suspends it when the named one is"
             " not the first -- reading `ev.dtype` instead of `ev.types()`"
             f" passes every other case here (healed {pair[0]}, {pair[1]},"
             f" {pair[2]})")


def once_spend_moments(out: Result) -> None:
    """A one-shot bonus is spent where it is READ, not by the next swing.

    `c.bonus(..., once=True)` dispatches on the key to decide which event
    ends the hold, and the fix for every gap in it has been "add a branch
    for the key I just found". The `else` kept silently mis-spending the
    next one, and the code's own comments count the instances: the damage
    branch was the second, `crit_range` the third, `save` the fourth
    ("fourth time a branch of this method has spent a modifier somewhere
    other than where it is read"), and `f3530`'s docstring found the fifth
    while unable to write its row.

    **None of the four previous fixes shipped the assertion that would
    have caught the next one**, which is why there was a next one each
    time: each proved its own key worked and none proved that the *wrong*
    roll leaves the hold alone. That is what this rule is.

    So, per moment, both halves:

    * a check bonus is spent by the **check** and **not** by an attack
      roll -- the bug, seven sites in the tree, and two more that
      hand-rolled the latch rather than trust `once=`;
    * a shove reduction is spent by the **shove**. Two rows say "spends
      the reduction on this shove rather than on every one until the end
      of the turn" and neither got it;
    * an attack bonus is still spent by the attack roll, which is what the
      `else` was right about all along and must not regress.

    And the refusal, which is the part that stops a sixth instance: a key
    with no spend moment **raises** instead of being quietly handed to the
    attack roll. `range` and `reach` are *not* in that set and must not
    be -- both are read by `dsl._reach_of` when it decides what may be
    reached, which happens before the roll, so the roll is genuinely the
    moment after which they have been used.
    """
    from combat_engine import story
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Mods
    from combat_engine.engine.durations import When
    from combat_engine.engine.ecs import World
    from combat_engine.engine.events import AttackRolled
    from combat_engine.engine.types import Defense

    def board() -> tuple[World, int, int]:
        fielded = story.field_encounter(seed=7, level=3)
        world = fielded.world
        pc = next(e for e in sorted(world.entities)
                  if not query.stat_block(world, e))
        mon = next(e for e in sorted(world.entities)
                   if query.stat_block(world, e))
        return world, pc, mon

    def total(world: World, who: int, key: str) -> int:
        mods = world.get(who, Mods)
        return mods.total(key, {"target": who, "attacker": who}) if mods else 0

    def swing(world: World, who: int, at: int) -> None:
        """An attack roll, announced directly.

        `c.strike` needs a declared attack line and this rule is about the
        spend rather than about any row, so the event is emitted the way
        the other rules here emit a `Hit` or a `TurnStart`.
        """
        roll = AttackRolled(
            attacker=who, target=at, power="drivers:once", vs=Defense.AC,
            natural=11, bonus=5, total=16, defence=10, advantage=False,
        )
        # `ctx` is a plain attribute `resolve.attack` stamps on, not a
        # field -- and the spend branch reads it to ask whether a gated
        # one-shot applies, so an event without one takes the fallback.
        # `setattr` rather than an attribute write: `ctx` is stamped on by
        # `resolve.attack` and is not a declared field, so a direct write
        # is an unresolved attribute to the checker.
        setattr(roll, "ctx", {  # noqa: B010
            "attacker": who, "target": at,
            "power": "drivers:once", "advantage": False,
        })
        world.bus.emit(roll)

    # -- a check bonus, and the attack roll that must NOT spend it -------
    world, pc, mon = board()
    c = Cast(world=world, me=pc, ref="drivers:once")
    c.bonus("skill:bluff", 2, on=pc, until=When.ENCOUNTER, once=True)
    before = total(world, pc, "skill:bluff")
    swing(world, pc, mon)
    survived = total(world, pc, "skill:bluff")
    out.that(before == 2 and survived == 2,
             "a one-shot CHECK bonus survives an attack roll, which is the"
             " bug: every key the four named branches missed was handed to"
             f" the swing instead ({before} -> {survived})")

    c.check("bluff", 10)
    spent = total(world, pc, "skill:bluff")
    out.that(spent == 0,
             f"and is spent by the check itself, where it is read ({spent})")

    # -- a shove reduction, spent by the shove ---------------------------
    world, pc, mon = board()
    Cast(world=world, me=pc, ref="drivers:once").bonus(
        "forced", 2, on=mon, until=When.ENCOUNTER, once=True)
    armed = total(world, mon, "forced")
    Cast(world=world, me=pc, ref="drivers:once").push(3, on=mon)
    gone = total(world, mon, "forced")
    out.that(armed == 2 and gone == 0,
             "a shove reduction is spent by the SHOVE -- `movement` reads it"
             " inside ForcedMove's resolve callback, which runs before the"
             f" after window the spend listens on ({armed} -> {gone})")

    # -- the attack branch must not regress ------------------------------
    world, pc, mon = board()
    Cast(world=world, me=pc, ref="drivers:once").bonus(
        "attack", 2, on=pc, until=When.ENCOUNTER, once=True)
    up = total(world, pc, "attack")
    swing(world, pc, mon)
    down = total(world, pc, "attack")
    out.that(up == 2 and down == 0,
             "while an ATTACK bonus is still spent by the attack roll, which"
             f" the else branch was right about all along ({up} -> {down})")

    # -- the refusal, which is what stops a sixth instance ---------------
    world, pc, mon = board()
    c = Cast(world=world, me=pc, ref="drivers:once")
    refused = []
    for key in ("surge_value", "temp_hp", "made_up"):
        try:
            c.bonus(key, 1, on=pc, until=When.ENCOUNTER, once=True)
        except ValueError:
            refused.append(key)
    out.that(len(refused) == 3,
             "a key with no spend moment RAISES rather than being handed to"
             f" the attack roll ({len(refused)} of 3 refused)")

    kept = []
    for key in ("attack", "range", "reach", "damage", "save",
                "skill", "skill:bluff", "ability_check", "forced"):
        try:
            Cast(world=world, me=pc, ref=f"drivers:{key}").bonus(
                key, 1, on=pc, until=When.ENCOUNTER, once=True)
            kept.append(key)
        except ValueError:
            pass
    out.that(len(kept) == 9,
             "and every key that DOES have one is still accepted -- `range`"
             " and `reach` included, read by _reach_of before the roll, so"
             f" the roll really is their moment ({len(kept)} of 9)")


def lengthened_shift(out: Result) -> None:
    """A feat that lengthens another row's shift, and where the read lives.

    Three feats print "when you use <row>, you can shift N extra squares"
    and all three were marked blocked on `c.extend_move(any_of=)`. All
    three docstrings blamed the same thing: *"`PowerUsed` is announced
    before the body runs, so by the time a watcher sees it the shift has
    not happened and there is nothing yet to lengthen."*

    **True, and irrelevant** -- nothing watches an event here.
    `c.extend_move` lays a standing modifier against a ref and the
    **moved row** reads it. So the gap was never in the feats: `p1489` and
    `p2479` hard-coded `c.shift(1)` where they should have asked
    `c.squares_for(c.ref, 1)`. Two one-line content fixes, and the three
    feats become one line each.

    Found by an agent that could not write the three and went looking for
    why, which is the shape worth repeating: when several rows blame the
    same mechanism, read the mechanism.

    Four things, and the last two are the gate:

    * the moved row's own printed distance, with nothing laid;
    * **the entries add**, which `squares_for` documents and which matters
      because two feats can lengthen the same row;
    * a gated entry stays shut while its condition is false;
    * and opens when it becomes true -- read at the moment the distance is
      asked for, not at the moment the modifier was laid, so a character
      who becomes bloodied mid-fight gains it.
    """
    from combat_engine import story
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health
    from combat_engine.engine.dsl import REGISTRY

    fielded = story.field_encounter(seed=7, level=3)
    world = fielded.world
    pc = next(e for e in sorted(world.entities)
              if not query.stat_block(world, e))
    vital = world.get(pc, Health)
    assert vital is not None

    def asked(bloodied: bool = False) -> int:
        vital.hp = (vital.max_hp // 3) if bloodied else vital.max_hp
        return Cast(world=world, me=pc, ref="p1489").squares_for("p1489", 1)

    out.that(asked() == 1,
             f"the moved row's own printed distance, unlengthened ({asked()})")

    Cast(world=world, me=pc, ref="drivers:f3748").extend_move(
        "p1489", 1, on=pc)
    out.that(asked() == 2,
             f"one feat lengthens it by the square it prints ({asked()})")

    gated = Cast(world=world, me=pc, ref="drivers:f3746")
    gated.extend_move("p1489", 2, on=pc,
                      when=lambda _ctx: gated.bloodied(on=pc))
    out.that(asked() == 2,
             "a second feat gated on being bloodied adds NOTHING while it is"
             f" not -- the control that separates the gate from the sum"
             f" ({asked()})")

    out.that(asked(bloodied=True) == 4,
             "and adds its two the moment it is, because the gate is asked"
             " when the distance is read rather than when the modifier was"
             f" laid ({asked(bloodied=True)})")

    # **And the half the three assertions above do not cover.** They ask
    # `squares_for` directly, so removing the read from the moved row --
    # which is the actual fix, two one-line content changes -- leaves them
    # all green. Caught by planting exactly that and watching nothing
    # redden.
    #
    # Asserted on what the row **asks for**, not on where it ends up:
    # `c.shift(n)` is "shift *up to* n" and a chooser picks the square, so
    # a row asking for 3 can legitimately move 1. Measuring the landing
    # square would have made this rule depend on board geometry and on the
    # mover's preferences, neither of which is what the three feats
    # changed.
    asks: list[int] = []
    Cast(world=world, me=pc, ref="drivers:plain").extend_move(
        "p1489", 5, on=pc)
    spy = Cast(world=world, me=pc, ref="p1489")
    # Patched on the instance rather than by subclassing: a subclass
    # narrowing `shift` is an invalid override and `types.py` says so.
    def record(squares_: int = 1, **kw: object) -> bool:
        asks.append(squares_)
        return True

    # `setattr` for the same reason as `ctx` above: replacing a bound
    # method on one instance is a narrower type than the method it
    # replaces, which is a real objection in general and not here.
    setattr(spy, "shift", record)  # noqa: B010
    REGISTRY["p1489"].body(spy)
    out.that(asks == [9],
             "and the moved row ASKS for its lengthened distance -- 1 printed,"
             " plus the 1 and 5 laid flat and the 2 whose gate the assertion"
             " above left open. This is the only assertion here that fails"
             " when `p1489` goes back to a hard-coded `c.shift(1)`, which the"
             f" three above all survive ({asks})")


def aid_another_grants(out: Result) -> None:
    """The aid another action's +2, which had never applied to anything.

    `c.aid_another` laid its grant as `c.bonus(skill, 2, ...)` -- the bare
    skill name. `skills.modifier` totals `f"skill:{skill.lower()}"` and
    `"skill"` and nothing else, so the key had no reader: a modifier
    nothing consults, which `engine/CLAUDE.md` calls the commonest bug in
    this component and `lint.py`'s `UNREAD_MODIFIER_KEYS` exists to guard.

    **So aiding an ally granted nothing, in every fight, since the action
    was written.** It is in `actions.legal`, so any character could take it
    and did.

    Found by `c.bonus(once=)`'s new refusal (#544) raising on the key
    during a **pre-push wide sweep** -- which is two arguments at once: for
    paying for that sweep, and for the refusal, because the dead key had
    been silent for as long as it existed and no narrow run had ever
    reached it. `audit.py --calls 'c.bonus('` could not: the call is inside
    a helper, not in any row.

    Three things, and the third is what makes the first meaningful:

    * the grant lands on the key the reader actually totals;
    * the bare key totals nothing, which is the state this fixes and the
      control that would have caught it;
    * and a check with a **different** skill gets no part of it, because
      the card grants "a +2 bonus to its next check with that skill".
    """
    from combat_engine import story
    from combat_engine.content import loader  # noqa: F401
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Mods

    fielded = story.field_encounter(seed=7, level=3)
    world = fielded.world
    party = [e for e in sorted(world.entities)
             if not query.stat_block(world, e)]
    helper, mate = party[0], party[1]

    mods = world.get(mate, Mods)
    assert mods is not None

    def total(key: str) -> int:
        return mods.total(key, {"target": mate})

    # **Deltas, not absolutes.** `chargen` deals this party its feats, and
    # one of them may already carry a bonus to the skill being measured --
    # which is how the third assertion below first failed inside the full
    # suite while passing alone. `points_regained` records the same lesson:
    # "an assertion that only holds while its neighbours do is not an
    # independent measurement".
    was_aided = total("skill:athletics")
    was_bare = total("athletics")
    was_other = total("skill:stealth")

    landed = Cast(world=world, me=helper, ref="drivers:aid").aid_another(
        mate, "athletics", auto=True)

    out.that(landed and total("skill:athletics") - was_aided == 2,
             "aiding an ally grants +2 on the key `skills.modifier` totals"
             f" -- `skill:<name>` (+{total('skill:athletics') - was_aided})")

    out.that(total("athletics") - was_bare == 0,
             "while the bare skill name totals nothing, which is where the"
             " grant used to be laid: a modifier with no reader, silent for"
             f" as long as the action has existed (+{total('athletics') - was_bare})")

    out.that(total("skill:stealth") - was_other == 0,
             "and a check with a different skill gets none of it, which is"
             " the card -- '+2 to its next check with that skill' -- and the"
             f" control that separates it from a blanket"
             f" (+{total('skill:stealth') - was_other})")


def penalties_by_source(out: Result) -> None:
    """Two penalties from two printed sources add; the same one twice does not.

    `Mods.total` buckets penalties by `Mod.label`, which `c.bonus` set to
    the laying row's ref and nothing could override. That is right for the
    rule it was built for -- "two penalties from the same source do not
    add, the worse applies", so one power landing on a creature twice is
    -2 and not -4 (#471's fix).

    **It is wrong for one body paying two different sentences**, and
    `m238a3` was the live instance: a zone laying -2 to attack for
    standing in it and a second -2 for attacking somebody concealed by it.
    Both hold at once whenever an enemy inside the fog swings at an ally
    inside it, the card gives -4 there, and the row returned -2 for as
    long as it existed. Found while correcting `docs/AUTHORING.md`, which
    told authors to pass a `label=` that `c.bonus` did not take.

    It will recur: #550's migration writes a feat's clause into the power
    it names, so a body laying a penalty of its own beside a feat's is the
    normal shape on several of the 20 rows in that set.

    Four assertions, and the second is the rule this must not break:

    * two penalties with different labels **add**;
    * two with the same label **do not** -- the worse applies, which is
      the whole of #471 and the thing a `label=` could regress;
    * the ref stays the label's prefix, so `audit._claimed` still credits
      the row that laid it;
    * and a **bonus** is unaffected, because bonuses bucket by `kind` --
      the control that stops `label=` being reached for as a stacking
      knob in general.

    **It recurred, as predicted above, and the fifth assertion is that
    case.** `monsters/level_06/skirmishers._worsen` stacks a rust penalty
    the card caps at five and laid every step under the laying row's ref,
    so all five collapsed to **-1**. It looked right because it *did* set a
    label -- on the `Effect`, which is what its own cap counts, and never on
    the `Mod`s the effect carries. Four rows were capped at -1 for their
    whole lives: `m3062a0`, `m3062a1`, `m3063a1`, `m3063a3`.

    Found by a Bin C authoring agent writing the same card one block over,
    and reproduced here before the fix: five holds, delta -1, one distinct
    `Mod` label.
    """
    from combat_engine import story
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Mods
    from combat_engine.engine.types import Defense

    fielded = story.field_encounter(seed=7, level=3)
    world = fielded.world
    pc = next(e for e in sorted(world.entities)
              if not query.stat_block(world, e))
    mon = next(e for e in sorted(world.entities)
               if query.stat_block(world, e))
    ctx = {"target": mon, "attacker": pc}

    def ac() -> int:
        mods = world.get(mon, Mods)
        return mods.total(Defense.AC, ctx) if mods else 0

    def labels() -> list[str]:
        mods = world.get(mon, Mods)
        return [m.label for m in mods.items
                if m.what == Defense.AC] if mods else []

    base = ac()
    c = Cast(world=world, me=pc, ref="drivers:m238a3")
    c.penalty(Defense.AC, 2, on=mon, label="inside")
    one = ac() - base
    c.penalty(Defense.AC, 3, on=mon, label="concealed")
    out.that(ac() - base == -5,
             "two penalties from two printed sources ADD -- the state"
             " `m238a3` was in, where this came to -3 because both carried"
             f" the row's bare ref ({ac() - base}, after {one})")

    out.that(all(lab.startswith("drivers:m238a3") for lab in labels()),
             "and the row's ref is still the label's prefix, so"
             " `audit._claimed` credits the row that laid them"
             f" ({labels()})")

    was = ac()
    same = Cast(world=world, me=pc, ref="drivers:twice")
    same.penalty(Defense.AC, 2, on=mon)
    first = ac() - was
    same.penalty(Defense.AC, 2, on=mon)
    out.that(ac() - was == -2,
             "the SAME source landing twice still does not add -- the worse"
             " applies, which is #471's rule and the one a label could"
             f" regress ({ac() - was}, after {first})")

    before = ac()
    b = Cast(world=world, me=pc, ref="drivers:bonuses")
    b.bonus(Defense.AC, 2, on=mon, label="one")
    b.bonus(Defense.AC, 3, on=mon, label="two")
    out.that(ac() - before == 5,
             "and two untyped BONUSES add whatever their labels, because"
             " bonuses bucket by kind -- the control that stops `label=`"
             f" being read as a general stacking knob ({ac() - before})")

    # ---- the recurrence: a capped stack of one-point penalties ----------
    #
    # `_worsen` lays up to five, and laid them all under the row's own ref
    # until this was found -- so the card's -5 was -1. The `Effect` label it
    # does set is the one its cap counts, which is exactly why the fault
    # looked like working code.
    from combat_engine.content.monsters.level_06.skirmishers import _worsen

    world2, caster2, _ = _board("m3062a0")
    victim = sorted(query.enemies(world2, caster2))[0]
    mods2 = world2.need(victim, Mods)
    start = mods2.total("attack", {})
    rust = Cast(world=world2, me=caster2, ref="m3062a0")
    for _ in range(7):                       # past the printed cap of five
        _worsen(rust, victim, "attack", "m3062 rust")
    got = mods2.total("attack", {}) - start
    out.that(got == -5,
             "five one-point rust penalties come to -5, not -1: each step"
             " carries its own Mod label",
             f"seven calls moved the attack roll by {got}")
    held = sum(1 for e in world2.effects.of(victim) if e.label == "m3062 rust")
    out.that(held == 5,
             "and the stack stops at the five the card prints, counted off"
             " the shared Effect label",
             f"{held} holds standing after seven calls")


def feat_clause_exclusivity(out: Result) -> None:
    """The feat clauses written into `p704`: which exclude each other, which do not.

    #550's convention: a feat naming one power has its clause written into
    that power's body, gated on `c.feat()`, instead of registering a rider
    from its own body. `p704` is the first row migrated and is the worked
    example because four feats name it and they are **two kinds**.

    **The grouping is the compendium's bracket, and the first version of
    this rule had it wrong.** A feat's category is printed in brackets
    after its name -- `[Arena Fighting]`, `[Lesser Style]`,
    `[Greater Style]`, or nothing at all -- and Camille's rule is one
    Arena Fighting feat, one Lesser Style feat, and **any number** of
    unbracketed ones per use of a power.

    So on `p704`:

    * `f972`, `f3188` and `f3234` are **all** Arena Fighting: one chain,
      at most one pays;
    * `f1300` carries no bracket: a plain `if`, and it **stacks** with
      whichever arena feat paid.

    The first version asserted `f972` and `f1300` were exclusive and that
    `f3188`/`f3234` stacked -- wrong in both directions at once, because I
    inferred the families from the books they came from rather than
    reading the bracket. The bracket is in the compendium's `PlainTxt`
    and the ETL strips it, which is why `game.db` looks like it has no
    category at all.

    **The exclusivity is the assertion that matters**, because it is the
    one a later reader can undo by "tidying" an `elif` into a second
    `if`. Nothing else would notice: every clause is correct in isolation.
    So the rule poses the state where all three arena clauses apply at
    once and asserts that **exactly one** pays -- and, as the control
    against writing the exclusivity too wide, that the unbracketed clause
    pays *as well*.

    Driven through the row rather than through the clauses: the clauses
    are ordinary verbs that were never broken, and the whole of the
    migration is that `p704`'s body now calls them. A rule asking
    `c.penalty` directly would survive the body being reverted to a
    rider, which is the mistake two rules in this file were written with.
    """
    from combat_engine import story
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.resolve import AttackResult

    fielded = story.field_encounter(seed=7, level=3)
    world = fielded.world
    pc = next(e for e in sorted(world.entities)
              if not query.stat_block(world, e))
    mon = next(e for e in sorted(world.entities)
               if query.stat_block(world, e))

    known = world.get(pc, Powers)
    assert known is not None
    held_originally = list(known.known)

    def run(*feats: str, crit: bool = False, held: bool = False,
            declares: str = "") -> set[str]:
        """Fire `p704`'s body and report which clauses asked for anything.

        `declares` stands in for the player's answer to `c.declare` when
        more than one feat of a category is held. Left empty, the engine's
        own pick -- the first option -- is taken, which `c.choose`
        documents as a real choice rather than a fallback.
        """
        known.known[:] = [*held_originally, *feats]
        asked: set[str] = set()
        spy = Cast(world=world, me=pc, ref="p704", target=mon,
                   result=AttackResult(hit=True, critical=crit, target=mon))

        # `setattr` on the instance, not a subclass: a subclass narrowing
        # these signatures is an invalid override and `types.py` says so.
        # Same reason `lengthened_shift` does it.
        def record(what: str, ret: object = None):  # noqa: ANN202
            def spied(*_a: object, **_kw: object) -> object:
                asked.add(what)
                return ret

            return spied

        setattr(spy, "strike", record("strike", True))        # noqa: B010
        setattr(spy, "damage", record("damage", 0))           # noqa: B010
        setattr(spy, "penalty", record("f972", None))         # noqa: B010
        setattr(spy, "flat", record("f1300", 0))              # noqa: B010
        setattr(spy, "ignores_difficult", record("f3188"))    # noqa: B010
        setattr(spy, "shift", record("f3188", True))          # noqa: B010
        setattr(spy, "push", record("f3234", 0))              # noqa: B010
        # The held test is a read, not a write, so it is answered rather
        # than recorded -- planting four conditions on the board would
        # make this rule depend on what else clears them.
        setattr(spy, "is_", lambda *_a, **_kw: held)          # noqa: B010
        if declares:
            setattr(spy, "choose",                            # noqa: B010
                    lambda options, *_a, **_kw: declares
                    if declares in options else (options[0] if options else None))
        REGISTRY["p704"].body(spy)
        return asked - {"strike", "damage"}

    out.that(run() == set(),
             "with no feat held the body lays no feat clause at all -- the"
             f" control, since every assertion below is a set it adds to"
             f" ({sorted(run())})")

    # Each arena clause on its own, so the chain below cannot pass by
    # having branches that never fire. `p992` taught that lesson.
    out.that(run("f972", crit=True) == {"f972"},
             "f972 (Arena Fighting) pays on a critical hit")
    out.that(run("f972") == set(),
             "and NOT on an ordinary one, which is the printed condition"
             f" ({sorted(run('f972'))})")
    out.that(run("f3188") == {"f3188"},
             "f3188 (Arena Fighting) pays on any hit")
    out.that(run("f3234") == {"f3234"},
             "f3234 (Arena Fighting) pays on any hit")

    arena = run("f972", "f3188", "f3234", crit=True)
    out.that(len(arena) == 1,
             "**holding all three Arena Fighting feats on a critical hit,"
             " exactly ONE pays.** The assertion that fails the moment an"
             " `elif` in p704's body becomes a second `if`, and the only"
             f" one that does ({sorted(arena)})")

    # **The declaration is made before the roll and is not revisited**,
    # which is the printed rule: "you must declare which of each type you
    # are using before making the attack". This assertion used to say the
    # opposite -- that on an ordinary hit `f3188` would pay "rather than
    # nothing", because the chain carried its applicability per branch and
    # fell through. That was more generous than the card, and `c.declare`
    # is what fixed it. The rule reddened on this exact line when the verb
    # landed, which is the instrument doing its job.
    out.that(run("f972", "f3188", declares="f972") == set(),
             "declaring f972 and then NOT critting pays nothing -- the"
             " declaration happens before the attack and does not fall"
             " through to the other feat"
             f" ({sorted(run('f972', 'f3188', declares='f972'))})")

    out.that(run("f972", "f3188", declares="f3188") == {"f3188"},
             "and declaring f3188 instead pays, on the same ordinary hit --"
             " the control that makes the line above a *choice* and not"
             " simply a clause that never fires"
             f" ({sorted(run('f972', 'f3188', declares='f3188'))})")

    out.that(run("f972", "f3188", crit=True, declares="f3188") == {"f3188"},
             "and a declaration of f3188 holds even on a critical hit,"
             " where f972 would have paid more -- the player's answer is"
             " not second-guessed by the outcome"
             f" ({sorted(run('f972', 'f3188', crit=True, declares='f3188'))})")

    # The control against writing the exclusivity too wide, which is the
    # mistake the first version of this rule made.
    out.that(run("f1300", held=True) == {"f1300"},
             "f1300 carries NO bracket and pays against a held target")
    out.that(run("f1300") == set(),
             "and not against a free one"
             f" ({sorted(run('f1300'))})")

    mixed = run("f972", "f1300", crit=True, held=True)
    out.that(mixed == {"f972", "f1300"},
             "**and an unbracketed feat stacks with an arena feat: BOTH"
             " pay.** This is the assertion the first version of this rule"
             " had backwards -- it asserted exactly one, on a family split"
             f" inferred from the books instead of read from the compendium"
             f" ({sorted(mixed)})")

    known.known[:] = held_originally


#: Every row migrated under #550, keyed by row and then by the feat
#: **category the compendium prints in brackets** after a feat's name.
#: `at_most_one_applies` is what makes migrating a row cost a line here
#: rather than a function.
#:
#: Camille's rule: **one `[Arena Fighting]` feat, one `[Lesser Style]`
#: feat, and any number of unbracketed ones** per use of a power. So each
#: category is its own chain and the two chains are independent; an
#: unbracketed feat is never in either and never appears here.
#:
#: **This used to be one flat tuple per row and that encoded a mistake.**
#: I had grouped the feats by the last word of their printed name -- so a
#: `[Arena Fighting]` feat and an unbracketed one, both printed "... Style",
#: looked like one family -- and the grouping came out wrong on four of the
#: five rows migrated. The bracket lives in the compendium's `PlainTxt`;
#: the ETL strips it, which is why `game.db` looks like it carries no
#: category at all. Read it from `compendium.sqlite`, not from the books a
#: feat appeared in and not from its name.
#:
#: A chain of fewer than two is nothing to assert and is left out.
MIGRATED = {
    "p704": {"Arena Fighting": ("f972", "f3188", "f3234")},
    "p1758": {"Arena Fighting": ("f978", "f985")},
}

#: Rows migrated under #550 that have **no** chain yet to assert on, with
#: why. Carried so the set of migrated rows is one list rather than two,
#: and so a row cannot quietly drop out of the instrument's view.
NO_CHAIN_YET = {
    "p997": "one Arena Fighting clause written (f994); the other four and"
            " the three Lesser Style ones are not",
    "p2099": "one Arena Fighting clause written (f992); f973 and f3245 are"
             " not, nor either Lesser Style one",
    "p992": "its three written clauses are all unbracketed, so they stack"
            " and there is nothing to chain; its four Arena Fighting and"
            " two Lesser Style feats are unwritten",
}

#: Feats of the exclusive category that name a migrated row and are **still
#: riders**, so that row's chain does not cover them and they stack when the
#: printed rule says they must not.
#:
#: **This exists so the gap is in the instrument and not only in a
#: docstring.** `p1758` is the first row where the convention could not
#: deliver its own main argument: `f981`'s clause asks whether the target
#: has hurt the character since the end of their last turn, which is a
#: *memory* that has to be armed before the blow it remembers. `_riders`
#: arms it through `setup=` at the start of the fight; a body runs far too
#: late and would build an empty set, which is exactly how the first
#: attempt at that memory failed silently.
#:
#: A chain that looks complete and is not is the worst of the three states,
#: so every entry here is reported as a skip. #556.
STILL_RIDERS = {
    "p1758": ("f981",),
}


def at_most_one_applies(out: Result) -> None:
    """For every row migrated under #550, at most one exclusive clause pays.

    `feat_clause_exclusivity` proves the property in detail for `p704`,
    including that each clause works on its own and that the stacking
    feats still stack. This is the same property asked of **every**
    migrated row, cheaply, so that migrating the next one costs a line in
    `MIGRATED` rather than a function here.

    The board is made as generous as it can be -- every condition read
    answers True, the attack crits, the weapon is whatever was asked for
    -- precisely so that **both** branches of each chain would fire if
    the chain were two independent `if`s. That is the only state in which
    the property is testable: a chain whose branches never both apply is
    trivially exclusive and proves nothing.

    What it cannot see: whether the right feats are in the chain. That is
    a reading of printed names and lives in each row's docstring. This
    asks only that the chain is a chain.
    """
    from collections import Counter

    from combat_engine import story
    from combat_engine.engine import query
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.resolve import AttackResult

    fielded = story.field_encounter(seed=7, level=3)
    world = fielded.world
    pc = next(e for e in sorted(world.entities)
              if not query.stat_block(world, e))
    mon = next(e for e in sorted(world.entities)
               if query.stat_block(world, e))
    known = world.get(pc, Powers)
    assert known is not None
    was = list(known.known)

    def fire(ref: str, feats: tuple[str, ...], *, hit: bool) -> list[str]:
        """One use of `ref` holding `feats`, reporting which clauses paid."""
        known.known[:] = [*was, *feats]
        paid: list[str] = []

        def spend(which: str):  # noqa: ANN202
            def spied(*_a: object, **_kw: object) -> object:
                paid.append(which)
                return 0

            return spied

        spy = Cast(world=world, me=pc, ref=ref, target=mon,
                   result=AttackResult(hit=hit, critical=hit, target=mon))
        # Every laying verb a migrated chain reaches for. A chain using one
        # that is absent here records nothing, which is what the second
        # assertion below is the control against.
        for verb in ("penalty", "flat", "temp_hp", "bonus", "push",
                     "shift", "slide", "pull", "grants_advantage",
                     "vulnerable", "mark", "immobilized", "prone"):
            setattr(spy, verb, spend(verb))
        setattr(spy, "strike", lambda *_a, **_kw: hit)        # noqa: B010
        setattr(spy, "damage", lambda *_a, **_kw: 0)          # noqa: B010
        # Generous: every question a clause's gate can ask says yes.
        setattr(spy, "is_", lambda *_a, **_kw: True)          # noqa: B010
        setattr(spy, "is_kind", lambda *_a, **_kw: True)      # noqa: B010
        setattr(spy, "wielding", lambda *_a, **_kw: True)     # noqa: B010
        # **And the board reads, as far as they can be faked.** A clause
        # gate is not only about the feats: `p992`'s first branch asks
        # whether the creature hit is the only enemy near it, and on a
        # drawn encounter it usually is not -- so that branch could not
        # fire and the chain's exclusivity was unprovable. An empty
        # neighbourhood is the generous answer, and it is safe because
        # every figure here is a difference against the same board.
        #
        # What cannot be faked this way is a clause reading the *world* --
        # `p992`'s third branch wants a zone a particular row laid. Those
        # are counted and reported as skipped rather than patched around.
        setattr(spy, "within", lambda *_a, **_kw: [])         # noqa: B010
        REGISTRY[ref].body(spy)
        return paid

    def added(ref: str, feats: tuple[str, ...], *, hit: bool) -> list[str]:
        """What holding `feats` adds over the row's own output.

        **Measured as a difference, because the spy cannot tell a feat's
        clause from the row's own.** `p997` pays flat damage on its own
        miss and `f994` adds flat damage on top, so a bare count read two
        payments and called the chain broken -- it was not; one of the two
        was the printed row. `feat_clause_exclusivity` already uses this
        control for `p704` and it has to be generic here.
        """
        bare = Counter(fire(ref, (), hit=hit))
        held = Counter(fire(ref, feats, hit=hit))
        return sorted((held - bare).elements())

    for ref, chains in MIGRATED.items():
        for family, feats in chains.items():
            # **Both outcomes, because a chain may live in either branch.**
            # `p704`'s pays on the hit and `p997`'s on the miss, and the
            # first version of this rule forced a hit and so never reached
            # `p997`'s `else` at all -- which the reachability assertion
            # caught, reporting zero clauses paid on a row whose chain is
            # two lines long. One use of a power is one run, so "at most
            # one" is asked per run; reachability across the pair.
            landed = added(ref, feats, hit=True)
            missed = added(ref, feats, hit=False)
            for outcome, paid in (("hit", landed), ("miss", missed)):
                out.that(len(paid) <= 1,
                         f"{ref} on a {outcome}: holding all {len(feats)}"
                         f" [{family}] feats with every condition met, at"
                         f" most one clause pays ({len(paid)}: {paid})")

            # **How many of this chain's branches can pay on THIS board.**
            # Without this the rule passes vacuously, and it did: a
            # three-way chain was planted into three independent `if`s and
            # **nothing reddened**, because only one branch could fire here
            # -- one needed the target to be the last enemy near it and one
            # a zone another row lays, and the spy fakes neither. The
            # docstring claimed the board was "as generous as it can be"
            # and that was false: the gates read the board, not just which
            # feats are held.
            #
            # So the limit is measured and reported rather than papered
            # over with more patching, which would be endless.
            alone = [f for f in feats
                     if added(ref, (f,), hit=True)
                     or added(ref, (f,), hit=False)]
            out.that(len(alone) >= 1,
                     f"{ref} [{family}]: the chain is REACHED -- at least"
                     f" one branch pays when its feat is held alone"
                     f" ({alone} of {list(feats)})")
            if len(alone) < 2:
                out.skip(f"{ref} [{family}]: exclusivity NOT PROVEN -- only"
                         f" {len(alone)} of {len(feats)} branches can fire"
                         f" here ({alone}), so 'at most one' above is"
                         f" vacuous. The rest read the world rather than the"
                         f" Cast; a dedicated rule has to build the state.")
            elif len(alone) < len(feats):
                out.skip(f"{ref} [{family}]: {len(alone)} of {len(feats)}"
                         f" branches posed ({alone}) -- the exclusivity"
                         f" between those IS proven, the rest read the world"
                         f" and are not.")

        # **A chain that looks complete and is not.** Reported every run,
        # because the only other place this is written down is the row's
        # docstring, and a docstring is not an instrument.
        riders = STILL_RIDERS.get(ref, ())
        if riders:
            out.skip(f"{ref}: INCOMPLETE chain -- {' '.join(riders)} of the"
                     f" same bracketed category still ride this row from"
                     f" their own file and stack with whatever the chain"
                     f" pays, which the printed rule forbids. See the row's"
                     f" docstring for why they could not move. #556")

    # **Migrated rows with nothing to assert on are still listed.** A row
    # that quietly drops out of this instrument's view is how a chain goes
    # unwatched, and three of the five migrated so far are in this state:
    # their written clauses are unbracketed, or only one of a category is
    # written, so there is no chain yet.
    for ref, why in NO_CHAIN_YET.items():
        out.skip(f"{ref}: migrated, no chain to assert -- {why}")

    known.known[:] = was


def penalty_scoped_to_an_aura(out: Result) -> None:
    """A penalty against "this creature and its allies within its aura 5".

    `m1032a2` prints "-2 to attacks against this creature **and its allies
    within its aura** (save ends)", and for its whole life it paid only the
    first half: the gate was `ctx.get("target") == c.me` and the rest was
    dropped as `Power.aura`. That marker was wrong twice -- there is no
    `Power.aura` field, and the radius it called unwritable is printed on
    the creature's own trait line, which an authoring agent cannot read and
    the main session can. The referral is what found it.

    **The negative control is the whole rule**, for the reason the aura
    half went missing in the first place: a gate that answers "yes" too
    often is indistinguishable from a correct one if nothing ever asks it
    about a creature that should be outside. So three questions, and the
    third is the one that fails if the geometry is dropped or the radius is
    read as a constant `True`:

    * an attack **against the creature itself** takes the -2;
    * an attack against an **ally standing within 5** takes it;
    * an attack against that same ally moved **out to 9** does not.

    The ally is moved rather than a second one placed, so the two
    geometric answers are about one creature and cannot differ by
    anything but distance. That also matches why the row re-reads
    `c.allies()` inside the gate instead of snapshotting: the printed
    clause is re-checked at every swing and allies walk in and out.

    **Each answer is the row's own contribution, not `Mods.total`.** The
    first draft asserted the totals and read -4, -4, -2 where it wanted
    -2, -2, 0 -- because `audit.board` lays an **ungated** -2 to attack of
    its own, labelled `audit:setup`, to provoke the row under test. It
    applies to every target, so it inflates all three answers and, worse,
    makes the negative control read -2 instead of 0: the one assertion
    that proves the geometry is live would have been *failing for the
    wrong reason*, and tuning the expectation to -4/-4/-2 would have made
    the rule pass while measuring the harness. That is the fault
    `scripts/CLAUDE.md` records against `audit.py` itself -- crediting a
    row with the harness's own provocation, 173 rows reporting `ok` on
    borrowed evidence.

    So the baseline is subtracted. Still read through `Mods.total`, which
    is the reader the engine uses, rather than by picking the row's `Mod`
    out of the list by label.

    **And the baseline is taken before the row fires, which the second
    draft got wrong in a way only the plant test found.** That draft read
    it off the leaving enemy, on the argument that the clause excludes it
    "by construction" -- but whether the clause excludes anybody is the
    thing under test, so the baseline was circular. Planting `return True`
    for the gate proved it: the plant lands the row's -2 on the leaving
    enemy too, the baseline absorbs it, and the **negative control
    passed** -- the one assertion whose whole job is catching a gate that
    says yes too often. The rule did go red, on the two assertions that
    should have been unaffected, which is a red for the wrong reason and
    would have read as "the aura half broke".

    A pre-fire reading cannot be contaminated by any gate, because the row
    has not run. That is the only baseline that is independent of what is
    being measured.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Defenses, Mods, Position
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.query import allies, enemies
    from combat_engine.engine.types import Defense

    world, caster, _ = _board("m1032a2")
    foes = enemies(world, caster)
    mates = [a for a in allies(world, caster) if a != caster]
    if not foes or not mates:
        out.skip(
            "m1032a2's board has no enemy or no ally, so neither half of"
            " the printed clause can be posed"
        )
        return
    foe, mate = foes[0], mates[0]

    # The row rolls +13 vs Reflex before it lays anything, so the clause is
    # only observable on a hit. Flattening the defence is what makes the
    # roll irrelevant -- the subject here is the gate, not the attack.
    defs_ = world.get(foe, Defenses)
    if defs_ is not None:
        defs_.values[Defense.REF] = 1

    here = world.get(caster, Position).square
    world.get(mate, Position).square = (here[0] + 2, here[1])

    # Before the row runs, so no gate of its own can colour it.
    was = world.get(foe, Mods)
    base = {
        who: (was.total("attack", {"target": who}) if was else 0)
        for who in (caster, mate)
    }

    c = Cast(world=world, me=caster, ref="m1032a2")
    c.trigger = type("Leaving", (), {"actor": foe})()
    REGISTRY["m1032a2"].body(c)

    mods = world.get(foe, Mods)
    if mods is None or not mods.items:
        out.skip("m1032a2 laid no modifier on the leaving enemy -- it missed")
        return

    def owed(who: int) -> int:
        return mods.total("attack", {"target": who}) - base[who]

    out.that(
        owed(caster) == -2,
        "the -2 applies to an attack against the creature itself",
        f"the row contributed {owed(caster)} (total"
        f" {mods.total('attack', {'target': caster})},"
        f" pre-fire baseline {base[caster]})",
    )
    out.that(
        owed(mate) == -2,
        "and to an attack against an ally standing within the aura 5",
        f"the row contributed {owed(mate)} at distance 2",
    )

    world.get(mate, Position).square = (here[0] + 9, here[1])
    out.that(
        owed(mate) == 0,
        "and not to that same ally once it is outside the aura",
        f"the row contributed {owed(mate)} at distance 9",
    )


def an_effects_keywords_come_from_the_row_that_laid_it(out: Result) -> None:
    """"A +2 bonus to saving throws against charm and psychic effects."

    `Effect` stores no keywords, so the only way to answer "is this a
    psychic effect" is to find the row that laid it. `durations.keywords_of`
    did that by taking the **first word of the label** -- which works
    because almost every site labels with its own ref, and silently failed
    for the six in `cast.py` that label by content. `c.ongoing` writes
    `"ongoing 5"`; `c.deals` writes `"deals:fire:weapon"`.

    So a psychic monster's burn answered *no keywords*, and `p16438`'s
    augment -- "make a saving throw against any charm effect and psychic
    effect at the **start** of your turn" -- was told the psychic effect was
    not psychic. 62 rows carry a watched keyword and lay a label of that
    shape; 4 rows ask the question. #580.

    The fix is `Effect.by`, a **plain attribute** (Camille's call) carrying
    the laying ref, defaulted from the label so the other 327 call sites
    keep today's behaviour.

    Six questions, and the last two are the ones a weaker rule would miss:

    * a psychic power's burn reports **psychic**;
    * a fire burn does **not**  <- the control, which fails if `by` is
      wired to something constant;
    * a row labelling by its own ref still answers, so nothing regressed;
    * a prose label still answers, because `by` is set from the row rather
      than parsed out of the words;
    * the **saving throw's context** carries the keywords, which is the
      half that reaches a rule rather than a lookup;
    * **`c.transfer` keeps the original layer's keywords.** Moving a hold to
      another creature does not make it somebody else's effect, and the
      transfer site is the one place `by` must not be `self.ref`.
    """
    from combat_engine.engine import Cast, DamageType, When
    from combat_engine.engine.durations import keywords_of
    from combat_engine.engine.query import allies
    from combat_engine.engine.types import Keyword

    world, caster, _ = _board()

    def burn(ref: str, dtype: DamageType, who: int) -> object:
        before = set(world.effects.live)
        Cast(world=world, me=who, ref=ref).ongoing(5, dtype, on=who)
        laid = [e for i, e in world.effects.live.items() if i not in before]
        return laid[0] if laid else None

    # `m4389a1` is a psychic monster ability; its burn is labelled "ongoing 5".
    psychic = burn("m4389a1", DamageType.PSYCHIC, caster)
    if psychic is None:
        out.skip("the psychic burn did not land, so nothing can be asked")
        return
    out.that(
        Keyword.PSYCHIC in keywords_of(psychic),
        "a psychic row's burn reports psychic, though its label is the amount",
        f"label={psychic.label!r} by={getattr(psychic, 'by', None)!r} "
        f"-> {sorted(k.value for k in keywords_of(psychic))}",
    )

    world.effects.end(psychic, "driver")
    # A row with no psychic keyword, laying the same shape of effect.
    plain = burn("mba", DamageType.FIRE, caster)
    out.that(
        plain is not None and Keyword.PSYCHIC not in keywords_of(plain),
        "and a burn from a row without the keyword does not",
        f"by={getattr(plain, 'by', None)!r} -> "
        f"{sorted(k.value for k in keywords_of(plain)) if plain else None}",
    )
    if plain is not None:
        world.effects.end(plain, "driver")

    # The ordinary case, which must not have regressed: a label that *is*
    # the ref, and a label that is prose.
    c = Cast(world=world, me=caster, ref="m4389a1")
    own = c.effect("m4389a1 hold", until=When.ENCOUNTER, on=caster)
    prose = c.effect("shrugging it off", until=When.ENCOUNTER, on=caster)
    out.that(
        own is not None and Keyword.PSYCHIC in keywords_of(own),
        "a row labelling with its own ref still answers",
        f"by={getattr(own, 'by', None)!r}",
    )
    out.that(
        prose is not None and Keyword.PSYCHIC in keywords_of(prose),
        "and so does one labelling with prose, which the label never could",
        f"label={prose.label!r} by={getattr(prose, 'by', None)!r}",
    )

    # The half that reaches a rule: the save's own context.
    held = burn("m4389a1", DamageType.PSYCHIC, caster)
    if held is None:
        out.skip("no burn to save against")
    else:
        seen: list = []
        c.bonus(
            "save", 2, on=caster, until=When.ENCOUNTER,
            when=lambda ctx: (seen.append(set(ctx.get("keywords", ()))), True)[1],
        )
        world.effects.save(held)
        out.that(
            any(Keyword.PSYCHIC in got for got in seen),
            "the saving throw's context carries the laying row's keywords",
            f"the save was offered {seen}",
        )

    # Transfer keeps the original layer.
    mates = [a for a in allies(world, caster) if a != caster]
    if not mates:
        out.skip("no ally to transfer a hold to")
        return
    moving = burn("m4389a1", DamageType.PSYCHIC, caster)
    if moving is None:
        out.skip("no hold to transfer")
        return
    other = Cast(world=world, me=mates[0], ref="driver:thief")
    landed = other.transfer(moving, to=mates[0])
    out.that(
        landed is not None and Keyword.PSYCHIC in keywords_of(landed),
        "a transferred hold keeps the keywords of the row that laid it",
        f"after transfer by={getattr(landed, 'by', None)!r} -- if this is "
        f"'driver:thief' the transfer site is claiming the effect",
    )


def a_granted_action_that_walks_a_zone(out: Result) -> None:
    """"As a minor action it can move the zone up to 3 squares."

    Nine monster rows print a line of this shape and **none of them offered
    it**. `c.move_zone` has existed and worked the whole time; what was
    missing was a reader for the word. `c.grant_action` knew four --
    `shift`, `stand`, `escape`, `second_wind` -- and its own docstring warns
    that "anything else is carried, costs nothing and does nothing". So the
    nine laid a `"move_zone as minor"` modifier that nothing read. #583.

    **The negative control is the one the family invites and the four
    existing words cannot get wrong**, because none of them takes an
    object: a granted move must not relocate **somebody else's** zone.
    `_recovery` filters on `Zone.owner`, and if that filter goes the menu
    offers a creature the enemy's zone to walk.

    Six questions:

    * no grant, no entry -- the zone sits there unoffered;
    * granted, and the entry appears, at the cost the card printed;
    * it is offered **per zone**, so a creature holding two gets two
      (`m1003a2` prints "up to three such portals at a time");
    * **another creature's zone is never offered**  <- the control;
    * performing it actually moves the zone;
    * an **aura** is refused, which is the printed rule and `c.move_zone`'s
      own guard -- filtered on the offer side too, so the menu never shows
      an entry that would fail.
    """
    from combat_engine.engine import ActionType, Cast, When
    from combat_engine.engine.actions import legal, perform
    from combat_engine.engine.components import Position
    from combat_engine.engine.query import enemies
    from combat_engine.engine.zones import Zone

    world, caster, _ = _board()
    enc = world.encounter
    if enc is None:
        out.skip("the board has no encounter, so nothing can be offered")
        return
    foes = enemies(world, caster)
    if not foes:
        out.skip("the board fields no enemy to own a rival zone")
        return
    rival = foes[0]

    here = world.get(caster, Position)
    if here is None:
        out.skip("the caster is off the grid")
        return
    x, y = here.square

    c = Cast(world=world, me=caster, ref="driver:move_zone")
    mine = c.zone([(x + 2, y)], label="driver:mine", until=When.ENCOUNTER)
    second = c.zone([(x + 3, y)], label="driver:second", until=When.ENCOUNTER)

    # The rival's, laid by the rival so `Zone.owner` is theirs.
    theirs = Cast(world=world, me=rival, ref="driver:theirs").zone(
        [(x + 6, y)], label="driver:theirs", until=When.ENCOUNTER
    )

    def entries() -> list:
        return [a for a in legal(world, enc, caster)
                if a.kind == "move_zone"]

    out.that(
        entries() == [],
        "a zone nobody granted a move for is not offered",
        f"it offered {entries()}",
    )

    c.grant_action("move_zone", ActionType.MINOR, squares_=3, on=caster,
                   until=When.ENCOUNTER)
    got = entries()
    out.that(
        bool(got) and all(a.cost is ActionType.MINOR for a in got),
        "the grant puts the move in the menu, at the printed cost",
        f"it offered {got}",
    )
    offered = {a.targets[0] for a in got if a.targets}
    # **Not an exact set, and the first draft asserted one.** It read
    # `offered == {mine, second}` and failed naming a third zone -- which
    # turned out to be `audit:setup zone`, laid by the board itself and
    # owned by the caster. The menu was right and the assertion was wrong,
    # so this asks the question the card asks: is each of my zones offered.
    out.that(
        {mine, second} <= offered,
        "one entry per zone the creature owns, and two for two",
        f"it offered zones {sorted(offered)}, wanted both of "
        f"{sorted({mine, second})}",
    )
    # The board lays `audit:setup foe zone` as well, so this is posed twice
    # over: by the rival zone laid above and by the harness's own.
    not_mine = {
        zid for zid, z in world.each(Zone)
        if z.owner != caster and z.aura is None
    }
    out.that(
        theirs not in offered and not (offered & not_mine),
        "and never another creature's zone",
        f"it offered {sorted(offered & not_mine) or [theirs]}, which "
        f"belong(s) to somebody else",
    )

    before = min(world.get(mine, Zone).squares)
    pick = next(a for a in got if a.targets and a.targets[0] == mine)
    perform(world, enc, caster, pick)
    after = min(world.get(mine, Zone).squares)
    out.that(
        after != before,
        "performing it moves that zone",
        f"it sat still at {before}",
    )

    # An aura belongs to its owner and travels with them, which `c.move_zone`
    # refuses. The menu must not offer it either.
    aura = c.aura(2, label="driver:aura", until=When.ENCOUNTER)
    if aura is None:
        out.skip("c.aura laid nothing, so the aura half cannot be posed")
        return
    out.that(
        aura not in {a.targets[0] for a in entries() if a.targets},
        "an aura is not offered, because it moves with its owner",
        "the menu offered the aura, which `c.move_zone` would refuse",
    )


def a_target_line_naming_an_earlier_swing(out: Result) -> None:
    """"One creature it hit this turn", and the row that says **missed**.

    Four rows narrow their *target* by what the caster already swung at,
    which is a different thing from the Requirement
    `a_hit_earlier_this_turn` covers: a Requirement allows the row and
    then lets it be aimed at anybody, where these narrow the pool itself.
    `Target.hit_by_me_this_turn` and `Target.missed_by_me_this_turn`
    read `query.my_hits_this_turn` and `my_misses_this_turn`. #576.

    **Asserted through `candidates()`, which is the half that silently
    goes missing.** A new `Target` field has to be named in that
    function's hand-kept "is any relational field set" guard *as well as*
    tested in `_stands_right`, or the explicit-target arm honours it and
    the offer path does not -- #381's disagreement arriving one field at a
    time, and the fault `ident`'s driver caught on its first run.

    Five questions, and the last two are the ones with teeth:

    * nobody swung at: the pool is **empty**;
    * after hitting one of two enemies, the pool is exactly that one;
    * the **other** enemy is excluded -- which is what fails if the guard
      entry is missing, because `candidates()` then returns both;
    * a **miss** does not satisfy a hit-shaped field, nor a hit a
      miss-shaped one. `i1132p1` prints "missed" and was mis-marked to the
      hit field one commit ago, so this is the control for my own error;
    * the memory dies with the turn.
    """
    import combat_engine.content  # noqa: F401
    from combat_engine.engine.dsl import REGISTRY, Target, candidates
    from combat_engine.engine.events import Hit, Miss, TurnStart
    from combat_engine.engine.query import enemies

    world, caster, _ = _board()
    foes = enemies(world, caster)
    if len(foes) < 2:
        out.skip("the board fields fewer than two enemies, so 'the one you "
                 "hit' cannot be told from 'any enemy'")
        return
    struck, spared = foes[0], foes[1]

    # A real row, re-aimed, rather than a hand-built Power: `candidates`
    # reads the whole header and a synthetic one drifts from the corpus.
    row = REGISTRY.get("i2133p1")
    if row is None:
        out.skip("i2133p1 is not declared")
        return

    def pool(**fields) -> list[int]:  # noqa: ANN003
        row.target = Target("enemy", 1, **fields)
        return candidates(world, caster, row)

    out.that(
        pool(hit_by_me_this_turn=True) == [],
        "nothing hit this turn offers no target at all",
        f"it offered {pool(hit_by_me_this_turn=True)}",
    )

    world.bus.log.append(
        Hit(attacker=caster, target=struck, power="x", critical=False)
    )
    got = pool(hit_by_me_this_turn=True)
    out.that(
        got == [struck],
        "after one blow lands, exactly that creature is offered",
        f"it offered {got}, wanted [{struck}]",
    )
    out.that(
        spared not in got,
        "and the enemy it did not hit is excluded",
        f"{spared} was offered anyway, which is `candidates()` ignoring "
        f"the field -- check the hand-kept guard, not `_stands_right`",
    )

    # The two fields are not each other's negation, which is why they are
    # two fields: a miss must not satisfy the hit-shaped one.
    out.that(
        pool(missed_by_me_this_turn=True) == [],
        "a hit does not satisfy the missed-shaped field",
        f"it offered {pool(missed_by_me_this_turn=True)} off a hit alone",
    )
    world.bus.log.append(
        Miss(attacker=caster, target=spared, power="x")
    )
    missed = pool(missed_by_me_this_turn=True)
    out.that(
        missed == [spared],
        "and a miss offers the creature that was missed, not the one hit",
        f"it offered {missed}, wanted [{spared}]",
    )

    world.bus.log.append(TurnStart(actor=caster, round=2))
    out.that(
        pool(hit_by_me_this_turn=True) == []
        and pool(missed_by_me_this_turn=True) == [],
        "both pools empty again once the creature's own turn begins",
        f"hit={pool(hit_by_me_this_turn=True)} "
        f"missed={pool(missed_by_me_this_turn=True)}",
    )


def a_hit_earlier_this_turn(out: Result) -> None:
    """"You must have hit an enemy with a weapon attack during this turn."

    Three rows print a Requirement of this shape and **six rows'
    docstrings each asserted the fact was not recorded** -- one of them
    that `requires=` "is handed a world and an eid with no turn history in
    it". `requires=` is handed exactly `(world, eid)`, `world.bus.log`
    *is* the turn history, and `lurkers_sa._landed_with` had been reading
    it as a `requires=` gate the whole time. `query.my_hits_this_turn` is
    that walk, shared. #576.

    **This rule is not optional cover, it is the only cover.** Enforcing
    the Requirement moved `m1097a3` and `i3151p1` from "fires and does
    something" to "never usable here": the audit board does not make a
    creature attack before spending its minor action, so a green audit
    says nothing about either row. That is the blind spot the plan names
    and `drivers.py` exists for.

    Four questions per row, and the third is the one that matters:

    * with nothing hit this turn, the row is **refused**, and refused *for
      this reason* -- not merely refused, because `usable` reports
      "requirement not met" for unrelated causes too and asserting the
      bare boolean let a planted deletion through on `a_weapon_requirement`;
    * after a qualifying blow, it is allowed;
    * after a blow of the **wrong kind**, it is still refused. `p15928`
      wants a weapon attack and `m1097a3` a melee one, so a hit that is
      neither must not open either -- this is what fails if the keyword
      and reach tests are dropped and the gate degrades to "hit anything";
    * once the creature's own turn starts again, the memory is **gone**.

    And for `i3151p1`, a fifth that is about the *other* half of its card:
    the ally arrives beside **the enemy actually hit**, not beside an
    enemy of the harness's choosing. Its body used `c.choose(foes, ...)`
    before, which is strictly better than the printed "the enemy you hit
    this turn" -- so the assertion names the victim and not just that
    somebody moved.
    """
    # **Content first, and this rule needed saying so.** `REGISTRY` is
    # populated by importing the content package, which every other rule
    # gets for free because it calls `_board` before touching the registry.
    # This one scans the corpus *first*, to pick its controls, and the scan
    # silently found nothing -- so the rule skipped itself with a message
    # blaming the corpus for a gap that was really an unimported package.
    import combat_engine.content  # noqa: F401
    from combat_engine.engine import Cast
    from combat_engine.engine.components import Position, Powers
    from combat_engine.engine.dsl import REGISTRY, usable
    from combat_engine.engine.events import Hit, TurnStart
    from combat_engine.engine.grid import distance
    from combat_engine.engine.query import allies, enemies
    from combat_engine.engine.types import Keyword

    # A real ref of each kind, taken from the corpus rather than written
    # down, so a renamed row cannot make this rule quietly vacuous.
    def pick(want_weapon: bool, want_melee: bool) -> str:
        for ref, row in REGISTRY.items():
            if row.attack is None or getattr(row, "reach", None) is None:
                continue
            if (Keyword.WEAPON in row.keywords) != want_weapon:
                continue
            if (row.reach.kind == "melee") != want_melee:
                continue
            return ref
        return ""

    melee_weapon = pick(True, True)
    neither = pick(False, False)
    if not melee_weapon or not neither:
        out.skip("the corpus offers no melee weapon row and no row that is "
                 "neither, so the wrong-kind control cannot be posed")
        return

    CASES = (
        ("p15928", "it must have hit an enemy with a weapon attack this turn"),
        ("m1097a3", "it must have hit with a melee attack this turn"),
        ("i3151p1", "you must have hit an enemy with a weapon this turn"),
    )
    for ref, want in CASES:
        if ref not in REGISTRY:
            out.skip(f"{ref} is not declared")
            continue
        world, caster, _ = _board(ref)
        foes = enemies(world, caster)
        if not foes:
            out.skip(f"{ref}'s board fields no enemy to have hit")
            continue
        foe = foes[0]
        known = world.get(caster, Powers)
        if known is not None and ref not in known.known:
            known.known = [*known.known, ref]

        # **Bound as defaults, not captured.** `world` and `caster` are
        # rebound every pass of the loop, so a closure over them reads
        # whichever board the loop reached last -- which would make every
        # assertion after the first case measure the wrong fight.
        def why(w=world, who=caster, r: str = ref) -> str:  # noqa: ANN001
            ok, reason = usable(w, who, REGISTRY[r])
            return "" if ok else str(reason)

        out.that(
            want in why(),
            f"{ref} is refused before anything has been hit",
            f"it said {why()!r}, wanted {want!r}",
        )

        world.bus.log.append(
            Hit(attacker=caster, target=foe, power=neither, critical=False)
        )
        out.that(
            want in why(),
            f"{ref} is still refused after a hit of the wrong kind",
            f"a hit with {neither} (no weapon keyword, not melee) said {why()!r}",
        )

        world.bus.log.append(
            Hit(attacker=caster, target=foe, power=melee_weapon, critical=False)
        )
        out.that(
            not why(),
            f"{ref} is allowed once a melee weapon blow has landed",
            f"it still said {why()!r} after a hit with {melee_weapon}",
        )

        world.bus.log.append(TurnStart(actor=caster, round=2))
        out.that(
            want in why(),
            f"{ref} is refused again once its own next turn begins",
            f"the memory outlived the turn: {why()!r}",
        )

    # The remembered victim, which is `i3151p1`'s second clause.
    if "i3151p1" in REGISTRY:
        world, caster, _ = _board("i3151p1")
        foes = enemies(world, caster)
        friends = [a for a in allies(world, caster) if a != caster]
        if len(foes) < 2 or not friends:
            out.skip("i3151p1 needs two enemies and an ally to tell the "
                     "remembered victim from a chosen one")
        else:
            # **The blow lands on the *second* enemy, and that is the whole
            # design of this control.** `c.choose` with no decider installed
            # takes the first option, which is `foes[0]` -- so hitting
            # `foes[0]` makes "the enemy you hit" and "any enemy" the same
            # creature and the assertion cannot tell them apart. The first
            # version of this plant did exactly that and **stayed green**
            # with the row reverted to `c.choose`, which `scripts/CLAUDE.md`
            # says is a finding either way: it was the plant that was wrong.
            hit_one = foes[1]
            here = world.get(hit_one, Position)
            if here is not None:
                # The remembered enemy is parked far away, so arriving
                # beside it and arriving beside the nearest one are
                # different squares by a distance no rounding can hide.
                mine = world.get(caster, Position)
                if mine is not None:
                    here.square = (mine.square[0] + 11, mine.square[1])
            known = world.get(caster, Powers)
            if known is not None and "i3151p1" not in known.known:
                known.known = [*known.known, "i3151p1"]
            world.bus.log.append(
                Hit(attacker=caster, target=hit_one, power=melee_weapon,
                    critical=False)
            )
            c = Cast(world=world, me=caster, ref="i3151p1")
            c.target = friends[0]
            REGISTRY["i3151p1"].body(c)
            ally_at = world.get(friends[0], Position)
            victim_at = world.get(hit_one, Position)
            if ally_at is None or victim_at is None:
                out.skip("i3151p1's ally or victim left the grid")
            else:
                gap = distance(ally_at.square, victim_at.square)
                out.that(
                    gap <= 1,
                    "i3151p1 lands the ally beside the enemy it actually hit",
                    f"the ally ended {gap} squares from the remembered victim",
                )


def every_move_of_a_kind(out: Result) -> None:
    """"One extra square on every shift", and not on anything else.

    `c.extend_move` keys on a row's ref, which cannot say *any* row. Eight
    rows print the other sentence and `f1393`'s note names the gap exactly:
    *"both are distances a row names when it moves you; nothing lengthens
    one from the outside."* `c.extend_every` is the kind-keyed half.

    **The negative control is the whole rule, and it is a crossing one**:
    a shift extension must not lengthen a teleport, nor a teleport
    extension a shift. That is the assertion that fails if the reserved
    key is dropped and the squares go in under one shared bucket -- which
    is exactly what writing this on top of `extra_squares` invites, since
    `extend_move("", n)` already keys the empty ref. Two rows here want
    shifts and two want teleports, so one bucket would silently pay both.

    Measured **through the verb**, not off the component. The whole design
    claim is that `c.shift` and `c.teleport` consult this without the row
    asking -- twelve content sites call `c.squares_for(c.ref, n)` and so
    cannot name a kind -- and reading `Powers.extra_squares` back would
    assert the write and leave that claim untested. A rule that calls the
    facility survives the fix being reverted; one that calls the store
    does not.

    `toward=` is what makes the distance observable: the options are
    offered nearest-first to a named creature, so with a foe out along one
    axis the chosen square is the farthest the budget reaches and the
    distance moved *is* the budget. Asserting the chosen square outright
    would be asserting the decider.

    Six questions:

    * a shift of 1 moves 1 square;
    * with a +1 on every shift it moves 2;
    * a teleport of 2 moves 2;
    * the shift extension leaves that teleport at 2  <- crossing control;
    * a +1 on every teleport moves it to 3;
    * and the two stack with nothing, so a creature holding neither moves
      what the card prints.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Position
    from combat_engine.engine.grid import distance
    from combat_engine.engine.query import enemies

    world, caster, _ = _board()
    foes = enemies(world, caster)
    if not foes:
        out.skip("the board has no enemy to move toward, so no distance is posed")
        return
    foe = foes[0]

    here = world.get(caster, Position)
    mate = world.get(foe, Position)
    if here is None or mate is None:
        out.skip("either the caster or the enemy is off the grid")
        return

    # The foe is parked far along one axis and the lane cleared, so the
    # budget is the only thing deciding how far the mover gets. Without
    # this the measurement is of whatever was in the way.
    origin = here.square
    mate.square = (origin[0] + 12, origin[1])

    def moved(call) -> int:  # noqa: ANN001
        here.square = origin
        call()
        return distance(origin, here.square)

    c = Cast(world=world, me=caster, ref="driver:extend_every")

    out.that(
        moved(lambda: c.shift(1, toward=foe)) == 1,
        "a shift of 1 moves one square",
        f"it moved {moved(lambda: c.shift(1, toward=foe))}",
    )
    out.that(
        moved(lambda: c.teleport(2, toward=foe)) == 2,
        "and a teleport of 2 moves two",
        f"it moved {moved(lambda: c.teleport(2, toward=foe))}",
    )

    c.extend_every("shift", 1)
    shifted = moved(lambda: c.shift(1, toward=foe))
    out.that(
        shifted == 2,
        "one extra square on every shift lengthens a shift of 1 to 2",
        f"it moved {shifted}",
    )
    out.that(
        moved(lambda: c.teleport(2, toward=foe)) == 2,
        "and does not lengthen a teleport, which is a different kind of move",
        f"the teleport moved {moved(lambda: c.teleport(2, toward=foe))}",
    )

    c.extend_every("teleport", 1)
    out.that(
        moved(lambda: c.teleport(2, toward=foe)) == 3,
        "one extra square on every teleport lengthens a teleport of 2 to 3",
        f"it moved {moved(lambda: c.teleport(2, toward=foe))}",
    )
    out.that(
        moved(lambda: c.shift(1, toward=foe)) == 2,
        "and the shift is still 2, not 3 -- the two kinds do not pool",
        f"the shift moved {moved(lambda: c.shift(1, toward=foe))}",
    )


def a_reachable_latch(out: Result) -> None:
    """A once-a-round payout can be asked about and handed back.

    `features/strikers.extra_damage` kept its latch in a closure, so two
    feats could not be written at all -- "a second helping of the extra
    damage after an action point" and "pays the extra damage on a miss".
    Both docstrings blamed a missing *announcement*; the announcement was
    never missing, since the payout passes `detail=label` and both damage
    events carry it. What was missing was a latch anybody could reach.
    #569.

    Five assertions, and the fourth is the one the closure existed for:

    * a fresh creature has not paid;
    * latching makes it paid;
    * `unlatch` hands it back **and says it did**, so a row paying an
      action point for the refund can tell that from a no-op;
    * a **per-turn** latch is a different window from a per-round one --
      the rogue may pay again on somebody else's turn, which a per-round
      latch silently refused, and that is the whole reason
      `c.payment_window` takes the initiative slot and not just the round;
    * and unlatching something never latched answers False rather than
      raising.
    """
    from combat_engine.engine.cast import Cast

    world, caster, _ = _board("p704")
    c = Cast(world=world, me=caster, ref="drivers:latch")
    label = "drivers:striker"

    out.that(
        not c.latched(label),
        "a creature that has not paid reads unlatched",
        f"latched={c.latched(label)}",
    )
    c.latch(label)
    out.that(
        c.latched(label),
        "and reads latched once it has",
        f"latched={c.latched(label)}",
    )
    gave = c.unlatch(label)
    out.that(
        gave and not c.latched(label),
        "unlatch hands it back and reports that it did",
        f"returned {gave}, now latched={c.latched(label)}",
    )

    # **The per-turn window.** Latched per round, a per-turn question must
    # still read unpaid -- they are different windows, which is what the
    # rogue's card needs and a single round counter cannot say.
    c.latch(label)
    out.that(
        c.latched(label) and not c.latched(label, per_turn=True),
        "a per-round latch does not answer a per-turn question",
        f"round={c.latched(label)} turn={c.latched(label, per_turn=True)}",
    )
    c.unlatch(label)

    out.that(
        not c.unlatch("drivers:never-latched"),
        "and unlatching something never spent answers False",
        "a refund of nothing must be distinguishable from a real one",
    )

    # **`f1722`'s trigger, which the board cannot pose.** It needs a ranger
    # holding a daily, a quarry, and a miss against it -- so the predicate
    # is tested directly, with the three near-misses its card excludes.
    # Without this the row sits "never usable here" and unverified, which
    # is how a wrong predicate survives.
    from combat_engine.content.feats.ranger_b import (
        _my_ranger_daily_missed_quarry as missed,
    )
    from combat_engine.engine import Relation
    from combat_engine.engine.dsl import REGISTRY

    foe = next(iter(_enemies_of(world, caster)), None)
    if foe is None:
        out.skip("p704's board fields no enemy to be made a quarry")
        return
    world.relations.set(Relation.QUARRY_OF, caster, foe)

    daily = next(
        (r for r, p in REGISTRY.items()
         if p.cls == "ranger" and p.usage.name == "DAILY"), "",
    )
    other = next(
        (r for r, p in REGISTRY.items()
         if p.cls == "ranger" and p.usage.name == "ENCOUNTER"), "",
    )
    not_ranger = next(
        (r for r, p in REGISTRY.items()
         if p.cls == "fighter" and p.usage.name == "DAILY"), "",
    )

    def ev(power: str, target: int):  # noqa: ANN202
        return type("M", (), {"attacker": caster, "power": power, "target": target})()

    out.that(
        bool(daily) and missed(world, caster, ev(daily, foe)),
        "f1722 accepts a daily ranger attack missing the quarry",
        f"power={daily!r}",
    )
    out.that(
        not other or not missed(world, caster, ev(other, foe)),
        "and refuses a ranger ENCOUNTER power -- the card says daily",
        f"power={other!r}",
    )
    out.that(
        not not_ranger or not missed(world, caster, ev(not_ranger, foe)),
        "and refuses another class's daily -- the card names the class",
        f"power={not_ranger!r}",
    )
    stranger = next((f for f in _enemies_of(world, caster) if f != foe), None)
    if stranger is not None:
        out.that(
            not missed(world, caster, ev(daily, stranger)),
            "and refuses a miss against somebody who is not the quarry",
            f"target={stranger}",
        )


def _enemies_of(world, who):  # noqa: ANN001, ANN202
    from combat_engine.engine.query import enemies

    return enemies(world, who)


def target_of_one_kind(out: Result) -> None:
    """"Up to four of its own kind" offers only that kind.

    Nine rows filtered this in their **bodies** -- comparing `Ident.ref`
    and returning for a target of the wrong block -- and that is not the
    same thing. The targeter chooses first, so a row printing "up to four
    of its own kind" was offered any four allies, rejected the wrong ones
    one at a time, and paid nothing for them: the printed count is spent
    on candidates the card never allowed.

    `Target.ident` declares it instead, tested inside `_stands_right`,
    which is the one predicate `candidates()` and `use` share -- #381 is
    what happens when those two disagree, so a second copy of this test
    would be the bug rather than the fix.

    The negative control is an ally of a **different** block standing in
    exactly the same place: it must drop out of the offer entirely, not be
    offered and then refused.
    """
    from combat_engine.engine.components import Ident, Position
    from combat_engine.engine.dsl import REGISTRY, Target, candidates

    world, caster, _ = _board("m858a2")
    mine = REGISTRY["m858a2"]
    kind = world.get(caster, Ident)
    if kind is None:
        out.skip("m858a2's caster carries no Ident, so no kind can be asked for")
        return

    allies_ = [a for a in _allies_of(world, caster) if a != caster]
    if not allies_:
        out.skip("m858a2's board fields no ally to offer")
        return

    # Stand one ally close, and make it the caster's own kind.
    mate = allies_[0]
    here = world.get(caster, Position).square
    world.get(mate, Position).square = (here[0] + 1, here[1])
    world.get(mate, Ident).ref = kind.ref

    same = Target(side="ally", count=4, ident=kind.ref)
    other = Target(side="ally", count=4, ident="m-nothing-of-this-kind")

    offered = candidates(world, caster, _aimed(mine, same))
    out.that(
        mate in offered,
        "an ally of the caster's own kind is offered",
        f"offered {offered}, wanted {mate} among them",
    )

    refused = candidates(world, caster, _aimed(mine, other))
    out.that(
        mate not in refused,
        "and the same ally is not offered for a different kind",
        f"offered {refused} for a kind nothing on the board is",
    )

    # And the field must not narrow a row that does not ask for a kind.
    wide = candidates(world, caster, _aimed(mine, Target(side="ally", count=4)))
    out.that(
        mate in wide,
        "while a target line naming no kind is unnarrowed",
        f"offered {wide}",
    )

    # **`ident="own"`**, which four of the eight rows need and a literal
    # cannot say: the block being asked for is whichever creature casts.
    own = Target(side="ally", count=4, ident="own")
    out.that(
        mate in candidates(world, caster, _aimed(mine, own)),
        'ident="own" offers an ally of the caster\'s own block',
        f"offered {candidates(world, caster, _aimed(mine, own))}",
    )
    world.get(mate, Ident).ref = "m-some-other-block"
    out.that(
        mate not in candidates(world, caster, _aimed(mine, own)),
        'and drops it the moment its block differs',
        f"offered {candidates(world, caster, _aimed(mine, own))} after the change",
    )

    # **`kind_or_ident`: kind OR own block.** Eight rows print one sentence that
    # needs it -- "allies of its own sort" counts an ally carrying the
    # printed type word *or* one of the caster's own block -- and neither
    # test alone is right, because the words are uneven: only 11 stat
    # blocks carry `kobold` and `m906`, whose card rallies them, is not one
    # of them. #570.
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.query import kinds_of

    # Give the ally a type word if it has none. `c.set_origin` is the
    # sanctioned writer -- `kinds_of` reads an `origin:<word>` effect
    # label -- so this is the same route a polymorph takes, not a poke at
    # the internals.
    word = next(iter(kinds_of(world, mate)), "")
    if not word:
        word = "drivers-sort"
        Cast(world=world, me=caster, ref="drivers:kind").set_origin(
            word, on=mate
        )
    if word not in kinds_of(world, mate):
        out.skip("the ally could not be given a type word to match on")
        return

    # The ally is now a *different* block carrying a known type word.
    either = Target(side="ally", count=4, kinds=frozenset({word}),
                    ident="own", kind_or_ident=True)
    out.that(
        mate in candidates(world, caster, _aimed(mine, either)),
        'kind_or_ident offers an ally that matches the KIND but not the block',
        f"word={word!r} offered {candidates(world, caster, _aimed(mine, either))}",
    )

    # **The control that proves the field does anything**: the same two
    # tests without `kind_or_ident` compound, so the ally must drop out.
    both = Target(side="ally", count=4, kinds=frozenset({word}), ident="own")
    out.that(
        mate not in candidates(world, caster, _aimed(mine, both)),
        "and without it the two compound, so that ally is refused",
        f"offered {candidates(world, caster, _aimed(mine, both))}",
    )

    # The other way in: the block matches and the kind does not.
    world.get(mate, Ident).ref = kind.ref
    other_way = Target(side="ally", count=4, ident="own", kind_or_ident=True,
                       kinds=frozenset({"no-such-type-word"}))
    out.that(
        mate in candidates(world, caster, _aimed(mine, other_way)),
        "and offers one that matches the BLOCK but not the kind",
        f"offered {candidates(world, caster, _aimed(mine, other_way))}",
    )

    # Neither: still refused, or the union has become "anybody".
    world.get(mate, Ident).ref = "m-some-other-block"
    out.that(
        mate not in candidates(world, caster, _aimed(mine, other_way)),
        "and refuses one that matches neither",
        f"offered {candidates(world, caster, _aimed(mine, other_way))}",
    )


def _aimed(p, aim):  # noqa: ANN001, ANN202
    """The same row with a different target line, for comparing offers."""
    from dataclasses import replace

    return replace(p, target=aim)


def _allies_of(world, who):  # noqa: ANN001, ANN202
    from combat_engine.engine.query import allies

    return allies(world, who)


def a_weapon_requirement(out: Result) -> None:
    """A printed "Requirement: you must be wielding <a weapon>" is enforced.

    `f3485b`, `f3486b` and `f3487b` dropped that line under a symbol
    saying the engine had "no group and no ref" for the weapon. It has
    both: `w3739` is a superior polearm with a group, a category, a price
    and a place in `chargen.PRINTED`. So the rows now declare
    `requires=_wields_w3739`.

    **The trade this rule exists to police.** Enforcing the Requirement
    moves all three from "fires and does something" to "never usable here"
    on the audit board, because the board's character is not dealt that
    weapon -- the audit's 1,069 board-unreachable family. That is correct
    and it is also exactly how a row gets turned off by accident, so the
    positive control is the point: with the weapon in hand the Requirement
    passes, and without it the row is refused rather than silently
    swinging anyway.

    Matched on the ref rather than the slug, which is what keeps the
    printed name out of `general_v.py`; the negative control is a
    *different* superior polearm, because `c.wielding` tests group and
    category and would have passed any of them.

    **`usable` returns `(ok, reason)`**, and the first draft of this rule
    wrote `not usable(...)` -- a non-empty tuple is always truthy, so the
    refusal list was always empty and two assertions failed against
    perfectly good rows. The rule was wrong, not the content; `[0]` is the
    whole fix, and it is worth a line because the same mistake reads as a
    content bug.
    """
    from combat_engine.chargen import PRINTED
    from combat_engine.engine.components import Gear, Powers
    from combat_engine.engine.dsl import REGISTRY, usable

    world, caster, _ = _board("p704")
    gear = world.get(caster, Gear)
    if gear is None:
        out.skip("p704's board deals no Gear, so nothing can be put in hand")
        return

    arm = PRINTED.get("w3739")
    if arm is None:
        out.skip("w3739 is not in chargen.PRINTED, so it cannot be dealt")
        return

    rows = [r for r in ("f3485b", "f3486b", "f3487b") if r in REGISTRY]
    out.that(
        len(rows) == 3,
        "all three rows that require the weapon are declared",
        f"found {rows}",
    )

    # **Known first, or every assertion below passes for the wrong reason.**
    # These are `b`-suffix cards a parent feat hands over, so a character
    # without the feat is refused `not known` -- which is what the first
    # draft of this rule measured. Both negative controls passed while the
    # Requirement was never consulted at all, the same vacuous pass
    # `at_most_one_applies` records. With the rows known, the weapon is the
    # only term that varies.
    known = world.get(caster, Powers)
    if known is None:
        out.skip("p704's board gives the caster no Powers component")
        return
    known.known = [*known.known, *rows]

    # Empty-handed of it: the Requirement must refuse them, **and the
    # reason must be the Requirement**. Asserting only the boolean is not
    # enough and the plant test proved it: with `requires=` stripped from
    # `f3485b` the row is still refused, for an unrelated reason that
    # `usable` reports as "requirement not met", so the assertion passed
    # over a row whose printed Requirement had just been deleted.
    WANT = "it must be wielding the printed weapon"
    gear.weapons = [w for w in gear.weapons if w.ref != "w3739"]
    said = {r: usable(world, caster, REGISTRY[r]) for r in rows}
    refused = [r for r, (ok, why) in said.items() if not ok and why == WANT]
    out.that(
        len(refused) == len(rows),
        "without the weapon every one is refused, naming the Requirement",
        f"refused for that reason: {refused}; all verdicts {said}",
    )

    # A different superior polearm is not the one the card names.
    other = next(
        (w for w in PRINTED.values()
         if w.ref != "w3739" and w.group == arm.group and w.category == arm.category),
        None,
    )
    if other is not None:
        gear.weapons = [*gear.weapons, other]
        other_said = {r: usable(world, caster, REGISTRY[r]) for r in rows}
        still = [r for r, (ok, why) in other_said.items() if not ok and why == WANT]
        out.that(
            len(still) == len(rows),
            "and another weapon of the same group and category does not satisfy it",
            f"{other.ref} left these still refused on the Requirement: {still}",
        )
        gear.weapons = [w for w in gear.weapons if w.ref != other.ref]

    # The weapon itself: the Requirement must pass.
    gear.weapons = [*gear.weapons, arm]
    allowed = [r for r in rows if usable(world, caster, REGISTRY[r])[0]]
    out.that(
        len(allowed) == len(rows),
        "and with the weapon in hand every one is allowed",
        f"allowed {allowed} of {rows}",
    )


def a_lent_basic_attack(out: Result) -> None:
    """"An ally can make a basic attack" -- and who it swings at.

    `c.basic(who=other)` names the **attacker**. The victim is `on=`, which
    defaults through `Cast._who` to the *caster's* target -- so a row that
    lends a swing and declares `target=NO_TARGET` passed `None`, and
    `c.basic` returns False on its third line before rolling anything.

    Ten rows were written that way and every one of them audited green,
    because each had a second clause -- a heal, a shift, a summon -- that
    did fire. The printed attack never happened in any fight.

    The negative control is the whole point and it is not hypothetical: it
    is the state the tree was in. Asserting only that the lent swing lands
    would pass just as well against a `c.basic` that quietly picked a
    target of its own, which is the other way this could have been
    "fixed" and would have been wrong -- the card names who swings, not
    who gets hit, and choosing the victim is the row's job.
    """
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Position
    from combat_engine.engine.events import AttackDeclared
    from combat_engine.engine.query import allies, enemies

    world, caster, _ = _board("m4612a0")
    foes = enemies(world, caster)
    mates = [a for a in allies(world, caster) if a != caster]
    if not foes or not mates:
        out.skip(
            "m4612a0's board has no ally to lend the swing to, or no enemy"
            " to lend it against"
        )
        return
    mate, foe = mates[0], foes[0]

    # Stand the enemy next to the *ally*, which is the geometry the printed
    # clause is about -- not next to the caster.
    spot = world.get(mate, Position).square
    world.get(foe, Position).square = (spot[0] + 1, spot[1])

    swings: list[tuple[int, int]] = []
    world.bus.on(AttackDeclared, lambda ev: swings.append((ev.attacker, ev.target)))

    c = Cast(world=world, me=caster, ref="drivers:lent-basic")
    landed = c.basic(who=mate, on=foe)
    out.that(
        landed and (mate, foe) in swings,
        "a lent basic attack is declared by the ally, against the named enemy",
        f"returned {landed}; declared {swings}",
    )

    # The same call with no victim -- what every one of the ten rows did.
    before = len(swings)
    again = c.basic(who=mate)
    out.that(
        not again and len(swings) == before,
        "and with no `on=` it declares nothing at all, rather than"
        " choosing a victim of its own",
        f"returned {again}; declared {swings[before:]}",
    )


def trained_skills(out: Result) -> None:
    """Being trained in a skill is worth +5, and only on that skill.

    `engine/skills.py` carried the absence of this in its own docstring --
    *"there is no training model ... nothing here decides who is trained
    and the +5 is not applied by default"* -- so every skill check in the
    game was rolled by an untrained character, including the opposed check
    that decides whether a creature escapes a grab. #565.

    Four assertions, and the last two are the ones that could have been
    quietly wrong:

    * a dealt character **is** trained in something, which is the half
      that depends on `class_skill` having been extracted at all;
    * a trained skill is exactly `TRAINING` higher than the same skill
      untrained -- measured by clearing the set and re-asking, so the
      ability modifier and half level cancel and 5 is the only term left;
    * **an untrained skill is unchanged**, which is what fails if the
      bonus is laid as a blanket `skill` modifier instead of per skill;
    * and training **adds to** a card's own bonus rather than replacing
      it. That is why it is not a `Mods` entry: `Mods.total` buckets by
      key and the second +5 would have lost to the first.
    """
    from combat_engine.engine.components import Mod, Mods, Skills
    from combat_engine.engine.skills import TRAINING, modifier

    # A **character's** board. The default is a monster, and a monster has
    # no training by design -- a stat block prints its skill totals outright
    # rather than its training -- so `_board()` skipped this rule loudly
    # instead of asserting anything.
    world, caster, _ = _board("p704")
    sk = world.get(caster, Skills)
    if sk is None or not sk.trained:
        out.skip(
            "the board's caster has no Skills component or no training,"
            " so neither half of the sum can be posed"
        )
        return

    trained = sorted(sk.trained)[0]
    other = next(
        (s for s in ("arcana", "religion", "history", "nature", "heal",
                     "diplomacy", "bluff")
         if s not in sk.trained),
        "",
    )
    out.that(
        bool(sk.trained),
        "a dealt character is trained in at least one skill",
        f"trained in {sorted(sk.trained)}",
    )

    with_it = modifier(world, caster, trained)
    before_other = modifier(world, caster, other) if other else 0
    sk.trained = frozenset()
    without = modifier(world, caster, trained)
    after_other = modifier(world, caster, other) if other else 0

    out.that(
        with_it - without == TRAINING,
        f"a trained skill is +{TRAINING} over the same skill untrained",
        f"{trained}: {with_it} trained, {without} untrained",
    )
    out.that(
        not other or before_other == after_other,
        "and an untrained skill is not touched by somebody else's training",
        f"{other}: {before_other} then {after_other}",
    )

    # Training plus a card's own bonus. Restored first, then a modifier on
    # the same key -- the two must add.
    sk.trained = frozenset({trained})
    mods = world.get(caster, Mods) or world.add(caster, Mods())
    mods.items.append(
        Mod(what=f"skill:{trained}", value=2, kind="item", label="drivers:training")
    )
    both = modifier(world, caster, trained)
    out.that(
        both == with_it + 2,
        "and a card's own bonus adds to training rather than replacing it",
        f"{trained}: {with_it} trained, {both} with a +2 item bonus as well",
    )

    # A feat that names its skill outright trains in it, and buys no free
    # pick from the class pool in exchange. `f3431` is the only one of the
    # thirteen whose card names the skill; the other twelve print a choice
    # from another class's list and keep their marker.
    from random import Random

    from combat_engine.chargen import _trained_skills

    # **A class whose pool does not contain the feat's skill**, which the
    # first draft of this got wrong: against a fighter -- whose own pool
    # includes streetwise -- the assertion passed or failed by seed, since
    # a class pick can land on the same skill the feat grants. The set is
    # right to collapse those into one training; the test was wrong to
    # assume they stay distinct. A cleric's pool has no streetwise, so the
    # feat's grant is additive whatever the sample does.
    seed = Random(11)
    plain = _trained_skills("cleric", [], Random(11))
    with_feat = _trained_skills("cleric", ["f3431"], Random(11))
    out.that(
        set(with_feat) - set(plain) == {"streetwise"},
        "a feat naming a skill trains in exactly that skill",
        f"without {sorted(plain)}, with {sorted(with_feat)}",
    )
    out.that(
        len(with_feat) == len(plain) + 1,
        "and it does not cost the character one of its class picks",
        f"{len(plain)} without the feat, {len(with_feat)} with it",
    )
    out.that(
        _trained_skills("nosuchclass", ["f3431"], seed) == frozenset({"streetwise"}),
        "and the feat's training applies even where the class has no entry",
        "a class with no class_skill rows must still honour the feat",
    )



def mage_school_riders(out: Result) -> None:
    """The four mage school tiers an `audit` board cannot pose.

    **`audit` cannot see three of these four.** Each reported "never usable
    here" the moment it was written: the board poses no wizard landing an
    illusion, a necromancy or a nethermancy power, so the trigger never
    fires and the row is credited with nothing either way. That is the blind
    spot `drivers` exists for, and the reason these assertions are here
    rather than in a sweep. The fourth is a standing trait that does fire,
    and whether its two clauses are *scoped* right is still invisible to a
    sweep.

    The negative control is the keyword, not the event: a hit with a wizard
    power carrying **neither** school keyword must leave both rows cold. A
    rule that only fired the matching power would pass whether the gate
    read the keyword or just said yes.
    """
    import combat_engine.content  # noqa: F401  -- populates REGISTRY
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health, Mods, Position
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.events import Hit
    from combat_engine.engine.query import enemies

    ILLUSION, NECROMANCY, NEITHER = "p1217", "p416", "p1225"
    NETHERMANCY, FIRE_ARCANE = "p13971", "p10191"
    ENCHANTMENT = "p451"
    # An arcane evocation row, for the reroll tier. Its keywords are what
    # `_reroll_pick` asks about, so the ref has to carry both words -- 74
    # rows do and this is one.
    EVOCATION_POWER = "p1166"

    # ---- the illusion tier: a -2 on the next swing AT THE CASTER --------
    #
    # **Both refs, because the card is printed twice.** `f0s2` is the school
    # chosen at 1st level and `f3s2` the one chosen at 4th, and the
    # compendium prints the same benefit under both. They are one body
    # registered twice in `content/features/arcanist.py`, so this asserts
    # the twin pays the same thing rather than trusting that it must --
    # `audit` reports `f3s2` UNUSED exactly as it does `f0s2`, for the same
    # reason this rule exists at all.
    for ref in ("cf:wizard-mage-f0s2", "cf:wizard-mage-f3s2"):
        if ref not in REGISTRY:
            out.skip(f"{ref} is not declared")
            continue
        world, caster, _ = _board(ref)
        foe = sorted(enemies(world, caster))[0]

        def held(w=world, who=foe, r: str = ref) -> int:  # noqa: ANN001
            mods = w.get(who, Mods)
            return 0 if mods is None else sum(1 for m in mods.items
                                              if m.label.startswith(r))

        out.that(held() == 0, f"{ref} lays nothing before anything is hit")
        world.bus.emit(Hit(attacker=caster, target=foe, power=NEITHER,
                           critical=False))
        out.that(held() == 0,
                 f"{ref}: nothing after a wizard power with neither school"
                 f" keyword -- the negative control",
                 f"a hit with {NEITHER} laid {held()} modifier(s)")
        world.bus.emit(Hit(attacker=caster, target=foe, power=ILLUSION,
                           critical=False))
        out.that(held() == 1,
                 f"{ref}: a hit with an illusion power lays the penalty on"
                 f" the target",
                 f"it laid {held()}")

        # **The difference, not the total.** `audit:setup` lays its own
        # ungated -2 to attack on this board, so an absolute reading is -4
        # against the caster and -2 against anybody else -- and an assertion
        # on the total passes or fails on the harness's modifier rather than
        # on this row's. The claim is that the gate is worth exactly 2 and
        # only against the caster.
        mods = world.need(foe, Mods)
        at_caster = mods.total("attack", {"target": caster})
        at_other = mods.total("attack", {"target": foe})
        out.that(at_caster - at_other == -2,
                 f"{ref}: the penalty is worth exactly 2 against the caster"
                 f" and nothing against anybody else",
                 f"against the caster {at_caster}, against another"
                 f" {at_other}, difference {at_caster - at_other}")

    # ---- the enchantment tier: 2 more squares of forced movement -------
    ref = "cf:wizard-mage-f0s0"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
    else:
        world, caster, _ = _board(ref)
        victim = sorted(enemies(world, caster))[0]
        # **No second arming.** `_board(ref)` already armed the row, and
        # calling its body again laid the rider twice -- a push of 1 came
        # out at 5 and the first draft of this rule read that as the engine
        # being wrong. The modifier is additive by design, so a double
        # arming is indistinguishable from a bigger bonus.

        # Driven through the verb, not the modifier: the point of the three
        # new readers is that `c.push` *consults* the rider, and a test that
        # read `Mods` back would pass whether it did or not.
        def shoved(power: str, who: int = victim) -> int:
            start = world.get(who, Position).square
            Cast(world=world, me=caster, ref=power).push(1, on=who)
            end = world.get(who, Position).square
            from combat_engine.engine.grid import distance
            return distance(start, end)

        far = shoved(ENCHANTMENT)
        out.that(far == 3,
                 "a push of 1 from an arcane enchantment power travels 3",
                 f"it travelled {far}")
        near = shoved(NEITHER)
        out.that(near == 1,
                 "and a push of 1 from a power of neither school travels 1"
                 " -- the negative control",
                 f"it travelled {near}")

    # ---- the nethermancy tier: distant enemies look half-hidden --------
    ref = "cf:wizard-mage-f0s4"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
    else:
        world, caster, _ = _board(ref)
        foes = sorted(enemies(world, caster))
        victim = foes[0]
        world.bus.emit(Hit(attacker=caster, target=victim, power=NETHERMANCY,
                           critical=False))
        mods = world.need(victim, Mods)

        # Two squares is the card's line, so the assertion is about the
        # boundary rather than about "far" in the abstract. Distances are
        # read off the board rather than assumed, because the harness places
        # the creatures and this rule must not depend on where.
        from combat_engine.engine.query import distance_between
        near = [e for e in world.entities
                if e != victim and distance_between(world, victim, e) <= 2]
        far = [e for e in world.entities
               if e != victim and distance_between(world, victim, e) > 2]
        if not near or not far:
            out.skip(f"{ref}: the board puts nothing both inside and outside"
                     f" 2 squares of the victim")
        else:
            at_far = mods.total("attack", {"target": far[0]})
            at_near = mods.total("attack", {"target": near[0]})
            out.that(at_far - at_near == -2,
                     "the struck creature is -2 against a target more than 2"
                     " squares off and unchanged against a closer one",
                     f"far {at_far}, near {at_near}")

    # ---- the pyromancy tier: a damage rider and no fire resistance ------
    ref = "cf:wizard-mage-f0s5"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
    else:
        world, caster, _ = _board(ref)
        mods = world.need(caster, Mods)
        out.that(mods.total("damage", {"power": FIRE_ARCANE}) == 1,
                 "a +1 damage bonus on an arcane fire power",
                 f"it gave {mods.total('damage', {'power': FIRE_ARCANE})}")
        out.that(mods.total("damage", {"power": NEITHER}) == 0,
                 "and none on a power that is neither -- the negative control",
                 f"it gave {mods.total('damage', {'power': NEITHER})}")

    # ---- the evocation tier: ONE die, rerolled ONCE ---------------------
    #
    # The point of the row is that it is **weaker** than the verb's default,
    # so the assertions are about what it does *not* do. A sweep cannot see
    # any of this: the holds are laid by a standing trait that fires, and
    # whether the number they produce is the card's number only shows up
    # inside a damage roll.
    ref = "cf:wizard-mage-f0s1"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
    else:
        world, caster, _ = _board(ref)
        mods = world.need(caster, Mods)
        floor = mods.total("reroll_damage_pick:evocation")
        count = mods.total("reroll_damage_pick:evocation#n")
        out.that(floor == 2 and count == 1,
                 f"{ref} lays a pick-one hold: floor 2, one die",
                 f"floor {floor}, count {count}")
        # **The design claim, asserted.** A pick-card must not lay the loop
        # card's hold, or `_damage_roll` would take the loop branch and the
        # row would reroll every 1 until it was not a 1 -- strictly better
        # than the page.
        out.that(mods.total("reroll_damage_below") == 0
                 and mods.total("reroll_damage_below:evocation") == 0,
                 "and lays none of the loop card's hold -- the shapes are"
                 " separate so they cannot blend",
                 f"loop hold read {mods.total('reroll_damage_below')}"
                 f"/{mods.total('reroll_damage_below:evocation')}")

        # Now drive a real damage roll with the dice forced, which is the
        # only way to tell the two shapes apart.
        #
        # **The scripted sequence is [1, 1, 1, 6] and that matters.** The
        # first draft used [1, 1, 6]: 2d6 comes up snake eyes and the single
        # reroll immediately gives a 6 -- which is *also* what the loop
        # does, since the loop stops as soon as the die is not low. Both
        # assertions passed under a planted loop, so neither was telling the
        # shapes apart and the evidence was worth nothing.
        #
        # With a third 1 the two diverge: this row rerolls once and keeps
        # the 1 it got, for 1 + 1 = 2 and three dice rolled; the loop would
        # roll again for 1 + 6 = 7 and four. Found by planting the loop and
        # watching the driver stay green.
        faces_seen: list[int] = []
        script = [1, 1, 1, 6]

        def scripted(faces: int, _seen=faces_seen) -> int:  # noqa: ANN001
            _seen.append(faces)
            n = len(_seen) - 1
            return script[n] if n < len(script) else 6

        c = Cast(world=world, me=caster, ref=EVOCATION_POWER)
        world.rng.die = scripted  # type: ignore[method-assign]
        got = c._roll_damage("2d6")
        out.that(got == 2,
                 "2d6 of [1, 1], one die rerolled once into another 1, comes"
                 " to 2 -- the new result stands even when it is a 1",
                 f"it came to {got} after rolling {faces_seen}")
        out.that(len(faces_seen) == 3,
                 "and exactly three dice were rolled: two for the expression"
                 " and one reroll, not a loop",
                 f"{len(faces_seen)} dice rolled")

    # ---- the enchantment master tier: +2 on a swing it forced -----------
    ref = "cf:wizard-mage-f6s0"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
    else:
        # **Driven through `c.grant_attack`, not through `c.amount_for`.**
        # The first draft asked `amount_for` directly and so asserted only
        # that the row lays its rider -- planting `grant_attack` to read the
        # *swinger's* store instead of the granter's left it green, because
        # the assertion never went through the verb being changed. That is
        # the "assert through the caller, not the helper" rule, and this is
        # what finding it the hard way looks like.
        # **Read off the roll, not off the modifier afterwards.** The second
        # draft looked for the Mod on the swinger once `grant_attack`
        # returned and found 0 every time -- correctly, because the verb's
        # `finally` ends every effect it granted with "the granted attack is
        # over". The bonus exists only for the duration of that one swing,
        # which is exactly right and means the only honest place to observe
        # it is the attack roll it changes.
        #
        # `rng.loaded` fixes the d20, so two runs on the same seed differ in
        # the granting row and nothing else, and the difference between the
        # announced totals is the whole of the claim.
        from combat_engine.engine.events import AttackRolled

        def swing(granting: str) -> int | None:
            w, me, _ = _board(ref)
            foes = sorted(enemies(w, me))
            if len(foes) < 2:
                return None
            w.rng.loaded = 10
            seen: list[int] = []
            w.bus.on(AttackRolled, lambda ev: seen.append(ev.total))
            Cast(world=w, me=me, ref=granting).grant_attack(
                foes[0], on=foes[1])
            return seen[0] if seen else None

        with_it = swing(ENCHANTMENT)
        without = swing(NEITHER)
        if with_it is None or without is None:
            out.skip(f"{ref}: the board posed no granted attack roll")
        else:
            out.that(with_it - without == 2,
                     f"{ref}: a swing forced by an arcane enchantment power"
                     f" rolls 2 higher than one forced by a power of neither"
                     f" school -- the negative control is the same swing",
                     f"enchantment {with_it}, neither {without},"
                     f" difference {with_it - without}")

    # ---- the master tier: a miss counts, and resistance is walked -------
    ref = "cf:wizard-mage-f6s2"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
    else:
        from combat_engine.engine.events import Miss
        world, caster, _ = _board(ref)
        victim = sorted(enemies(world, caster))[0]

        def granted(w=world, who=victim, r: str = ref) -> int:  # noqa: ANN001
            return sum(1 for e in w.effects.of(who) if e.label.startswith(r))

        # A **miss** is the half a Hit trigger would have dropped, so it is
        # the one asserted first.
        world.bus.emit(Miss(attacker=caster, target=victim, power=NEITHER))
        out.that(granted() == 0,
                 f"{ref} ignores a miss with a power of neither school"
                 f" -- the negative control",
                 f"it laid {granted()}")
        world.bus.emit(Miss(attacker=caster, target=victim, power=ILLUSION))
        out.that(granted() == 1,
                 "and a MISS with an illusion power opens the target up",
                 f"it laid {granted()}")

    ref = "cf:wizard-mage-f6s3"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
    else:
        from combat_engine.engine.resolve import _ignored_resist
        from combat_engine.engine.types import DamageType
        world, caster, _ = _board(ref)
        necrotic = (DamageType.NECROTIC,)
        walked = _ignored_resist(world, caster, necrotic,
                                 {"power": NECROMANCY})
        other = _ignored_resist(world, caster, necrotic, {"power": NEITHER})
        out.that(walked > 0,
                 f"{ref} walks through necrotic resistance on its own school",
                 f"it walked {walked}")
        out.that(other == 0,
                 "and through none on a power of neither school"
                 " -- the negative control",
                 f"it walked {other}")

    # ---- the necromancy tier: 2 temporary hit points --------------------
    ref = "cf:wizard-mage-f0s3"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
        return
    world, caster, _ = _board(ref)
    foe = sorted(enemies(world, caster))[0]
    health = world.need(caster, Health)
    health.temp = 0

    world.bus.emit(Hit(attacker=caster, target=foe, power=NEITHER,
                       critical=False))
    out.that(health.temp == 0,
             "the necromancy tier grants nothing for a power of neither"
             " school -- the negative control",
             f"temp hp went to {health.temp}")
    world.bus.emit(Hit(attacker=caster, target=foe, power=NECROMANCY,
                       critical=False))
    out.that(health.temp == 2,
             "and 2 temporary hit points for a necromancy hit",
             f"temp hp is {health.temp}")

    # "At least one target" with no counter: three hits leave 2, because
    # temporary hit points do not stack. The row relies on that rather than
    # keeping its own once-per-power guard.
    world.bus.emit(Hit(attacker=caster, target=foe, power=NECROMANCY,
                       critical=False))
    world.bus.emit(Hit(attacker=caster, target=foe, power=NECROMANCY,
                       critical=False))
    out.that(health.temp == 2,
             "and three hits in one burst still leave 2 -- the larger pool"
             " wins, so 'at least one target' needs no guard",
             f"temp hp is {health.temp}")



def shaman_spirits(out: Result) -> None:
    """Each Companion Spirit option keeps its own two powers and loses the
    others'.

    **Two of the four were crossed.** `cf:shaman-f0s2` is the Watcher
    option -- its boon is the no-cover one its card prints and its powers
    are `p9732`/`p9734` -- and it gated on `c.build("world speaker")`.
    `cf:shaman-f0s3` is World Speaker and gated on `c.build("watcher")`.
    Since `_spirit_choice` **forbids** the pair when the gate fails, a
    Watcher shaman lost its own two powers *and* its boon, and was handed
    the other spirit's instead. Measured before the fix: `watcher` kept
    `p9733, p9736`.

    Nothing caught it. `legs.py` compares a leg's name against the page and
    both names exist; `audit` fires a row on a board with no build choice,
    where either gate is equally false. The only question that separates
    them is "does *this* build keep *these* powers", which is this rule.

    **The elemental option is the fifth and was absent entirely** until
    #588 gave it a ref -- so an elemental shaman kept *none* of the eight
    powers its siblings forbid, which this rule now also asserts.

    The negative half is the half that matters: the other spirit's pair
    must be **forbidden**, not merely absent, because `loadout` deals them
    and the row's job is to take them away again.
    """
    import combat_engine.content  # noqa: F401  -- populates REGISTRY
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Build, Powers
    from combat_engine.engine.dsl import REGISTRY

    # ref -> (its leg, its own pair, the sibling ref)
    PAIRS = {
        "cf:shaman-f0s0": ("elemental", {"p12865", "p12866"}),
        "cf:shaman-f0s1": ("protector", {"p5389", "p6521"}),
        "cf:shaman-f0s2": ("stalker", {"p5388", "p5510"}),
        "cf:shaman-f0s3": ("watcher", {"p9732", "p9734"}),
        "cf:shaman-f0s4": ("world speaker", {"p9733", "p9736"}),
    }
    missing = [r for r in PAIRS if r not in REGISTRY]
    if missing:
        out.skip(f"not declared: {', '.join(missing)}")
        return
    every = {p for _, pair in PAIRS.values() for p in pair}

    for ref, (leg, own) in sorted(PAIRS.items()):
        world, me, _ = _board(ref)
        held = world.get(me, Build)
        if held is None:
            world.add(me, Build(choices=frozenset({leg})))
        else:
            held.choices = frozenset({leg})
        known = world.need(me, Powers)
        known.known = sorted(set(known.known) | every)
        known.forbidden = set()
        for other in sorted(PAIRS):
            REGISTRY[other].body(Cast(world=world, me=me, ref=other))
        kept = every - known.forbidden
        out.that(own <= kept,
                 f"{ref} keeps its own two powers when its leg is taken",
                 f"build {leg!r} kept {sorted(kept)}, wanted {sorted(own)}")
        out.that(not ((every - own) & kept),
                 f"{ref} forbids the other spirits' powers",
                 f"build {leg!r} also kept {sorted((every - own) & kept)}")


def a_feats_clause_in_its_power(out: Result) -> None:
    """A feat that names one power, written into that power. #550.

    `f1817` widens the ring `p9501` picks its second target out of, from 5
    squares to 10. The clause lives in `p9501` and reads `c.feat("f1817")`,
    which is the documented shape for a feat naming a single power -- and
    `audit` can see none of it: `p9501` is "never usable here" and `f1817`
    is bucketed as `implemented_in=` and never fired at all. Without this
    rule the row is marker-free and has no evidence whatsoever.

    **What this proves and what it does not.** It observes *which creature
    the row asks to swing at*, by recording the `on=` of its
    `c.grant_attack` call with one candidate placed 7 squares from the
    creature missed -- outside the printed 5, inside the widened 10. That
    is exactly the decision the feat changes.

    It does **not** prove the swing resolves. `c.grant_attack` returns
    False on this board: the harness's caster cannot make a ranged basic
    attack, which is the same wall that makes `audit` call `p9501` never
    usable. Asserting the resolution would need a board built around a
    seeker with a ranged weapon, and that is a bigger fixture than the
    claim needs.

    Two earlier drafts of this rule were worth less than nothing and are
    recorded so they are not rewritten:

    * the first computed `10 if c.feat(...) else 5` and asserted that --
      this driver asserting its own arithmetic, which would pass with the
      row hard-coding either number;
    * the second watched for `AttackRolled` and got 0 in **both** arms, so
      the negative control passed for the wrong reason. A control that
      holds because nothing happens at all is not a control.
    """
    import combat_engine.content  # noqa: F401  -- populates REGISTRY
    from combat_engine.engine.basic import RANGED
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Position, Powers
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.events import Miss
    from combat_engine.engine.query import enemies

    for ref in ("p9501", "f1817"):
        if ref not in REGISTRY:
            out.skip(f"{ref} is not declared")
            return

    def asked(with_feat: bool) -> int | None:
        world, caster, _ = _board("p9501")
        known = world.get(caster, Powers)
        foes = sorted(enemies(world, caster))
        if known is None or len(foes) < 3:
            return None
        if with_feat:
            known.known.append("f1817")
        missed, candidate = foes[0], foes[1]
        at = world.get(missed, Position)
        if at is None:
            return None
        x, y = at.square
        # The one candidate sits in the gap between the two rings; every
        # other foe goes far enough away that neither ring finds it, so the
        # answer cannot come from a creature this rule did not place.
        world.add(candidate, Position(square=(x + 7, y)))
        for other in foes[2:]:
            world.add(other, Position(square=(x + 40, y)))

        seen: list[int] = []
        real = Cast.grant_attack

        def record(self, who, *, on=None, **kw):  # noqa: ANN001, ANN003, ANN202
            seen.append(on)
            return real(self, who, on=on, **kw)

        Cast.grant_attack = record  # type: ignore[method-assign]
        try:
            c = Cast(world=world, me=caster, ref="p9501",
                     trigger=Miss(attacker=caster, target=missed, power=RANGED))
            REGISTRY["p9501"].body(c)
        finally:
            Cast.grant_attack = real  # type: ignore[method-assign]
        return sum(1 for t in seen if t == candidate)

    without, with_it = asked(False), asked(True)
    if without is None or with_it is None:
        out.skip("the board posed fewer than three foes")
    else:
        out.that(without == 0,
                 "without f1817, p9501 does not even ask to swing at a foe 7"
                 " squares from the one it missed -- the printed ring is 5",
                 f"it asked {without} time(s)")
        out.that(with_it == 1,
                 "and with f1817 it does -- the clause is in the power, read"
                 " off c.feat, not laid from the feat row",
                 f"it asked {with_it} time(s)")


def a_coup_de_grace_finisher(out: Result) -> None:
    """One card printed six times: ground yourself, finish the helpless, feed.

    `audit` cannot reach any of it. Three of the six rows carry a Requirement
    the board cannot meet -- there is nothing helpless on it -- so they report
    "never usable here", and the shared `settle` helper is where the clause
    lives, which no sweep exercises.

    **Two of the six carried no marker while missing the finisher.**
    `m2939a2` and `m2940a3` paid the two printed costs and never swung or
    healed, reporting finished; the other four said so with
    `dropped=("c.coup_de_grace(ref=)",)`. That verb is the wrong symbol --
    it refuses a row declaring no attack line (#250) and none of these cards
    print one -- so the swing is the creature's own basic attack and the
    automatic critical is `c.maximise(critical=True)`.

    The negative control is a victim that **survives**: the heal is printed
    "if it kills the target", so a row that healed on any swing would be
    strictly better than the card and this is what catches it.
    """
    import combat_engine.content  # noqa: F401  -- populates REGISTRY
    from combat_engine.content.monsters.level_01 import settle
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Health
    from combat_engine.engine.dsl import REGISTRY
    from combat_engine.engine.events import AttackRolled
    from combat_engine.engine.query import enemies
    from combat_engine.engine.types import Condition

    ref = "m2939a2"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
        return

    def finish(lethal: bool) -> tuple[int, bool, int, int]:
        world, caster, _ = _board(ref)
        victim = sorted(enemies(world, caster))[0]
        hurt = world.need(victim, Health)
        hurt.hp = 1 if lethal else hurt.max_hp
        mine = world.need(caster, Health)
        mine.hp = max(1, mine.max_hp // 4)
        before = mine.hp
        c = Cast(world=world, me=caster, ref=ref, target=victim,
                 targets=[victim])
        c.condition(Condition.HELPLESS, on=victim)
        crits: list[bool] = []
        world.bus.on(AttackRolled, lambda ev: crits.append(
            ev.natural == 20 or ev.total >= ev.defence))
        settle(c)
        return len(crits), bool(crits), before, world.need(caster, Health).hp

    swings, _any, before, after = finish(lethal=True)
    out.that(swings == 1,
             f"{ref} makes exactly one swing at the helpless target",
             f"it swung {swings} time(s)")
    out.that(after > before,
             "and regains hit points when that kills the target",
             f"it went from {before} to {after}")

    _s2, _a2, before2, after2 = finish(lethal=False)
    out.that(after2 == before2,
             "and regains none when the target survives -- the negative"
             " control, since the heal is printed 'if it kills the target'",
             f"it went from {before2} to {after2}")


def a_tome_charges_before_it_lends(out: Result) -> None:
    """The tome card, printed four times: pay an unused attack power, borrow
    a card from the tome.

    **No row of this card fires on the audit board and all four are
    `quiet`** -- the bearer holds no unused wizard attack power, so the
    printed cost refuses and the row correctly declines. That is the card
    working and it is also zero evidence, so the claim is made here instead.

    `i744p1` has charged the price since it was written; `i2717p1`,
    `i2899p1` and `i2900p1` carried `dropped=("c.expend_row(among=)",)` on
    the reading that nothing enumerates the bearer's unspent powers.
    `implement_c._spend_unused` does, off `Powers.all`.

    Both directions, because the ordering is the whole of the clause: the
    price is charged **first**, so a bearer with nothing to spend gets no
    card -- and a bearer who pays loses the power it paid with.
    """
    import combat_engine.content  # noqa: F401  -- populates REGISTRY
    from combat_engine.content.items.implement_c import _spend_unused
    from combat_engine.engine.cast import Cast
    from combat_engine.engine.components import Powers
    from combat_engine.engine.dsl import REGISTRY

    ref = "i744p1"
    if ref not in REGISTRY:
        out.skip(f"{ref} is not declared")
        return

    # A real wizard daily attack power at or above the tome's rung, taken
    # from the registry rather than named, so this does not rot when the
    # tree's wizard dailies move around.
    payable = [
        r for r, p in REGISTRY.items()
        if p.cls == "wizard" and p.level >= 5 and p.attack is not None
        and str(getattr(p.usage, "value", p.usage)) == "daily"
    ]
    if not payable:
        out.skip("no wizard daily attack power at level 5 or above is declared")
        return
    card = sorted(payable)[0]

    world, caster, _ = _board(ref)
    c = Cast(world=world, me=caster, ref=ref)
    out.that(_spend_unused(c, cls="wizard", level=5, attacks=True) is False,
             f"{ref} refuses when the bearer holds no unused wizard attack"
             f" power -- the printed cost is a Requirement",
             "it charged something it should not have")

    known = world.need(caster, Powers)
    known.known.append(card)
    before = dict(known.used)
    paid = _spend_unused(c, cls="wizard", level=5, attacks=True)
    out.that(paid is True,
             "and charges one when the bearer has it",
             f"it returned {paid} with {card} unused in hand")
    out.that(known.used != before,
             "and the power it charged is spent, not merely counted",
             f"used went from {before} to {dict(known.used)}")


DRIVERS = {
    "shaman_spirits": (
        shaman_spirits,
        "each Companion Spirit keeps its own powers and loses the others'",
    ),
    "feats_clause": (
        a_feats_clause_in_its_power,
        "a feat naming one power is written into that power (#550)",
    ),
    "tome_price": (
        a_tome_charges_before_it_lends,
        "the tome card charges its printed cost before it lends a card",
    ),
    "coup_de_grace": (
        a_coup_de_grace_finisher,
        "the helpless-finisher card, printed six times and short a clause",
    ),
    "mage_schools": (
        mage_school_riders,
        "the four mage school tiers an audit board cannot pose",
    ),
    "reachable_latch": (
        a_reachable_latch,
        "a once-a-round payout can be asked about and handed back",
    ),
    "target_kind": (
        target_of_one_kind,
        "a target line naming one kind offers only that kind",
    ),
    "weapon_requirement": (
        a_weapon_requirement,
        "a printed Requirement naming one weapon is enforced, by ref",
    ),
    "trained_skills": (
        trained_skills,
        "being trained in a skill is worth +5, on that skill only",
    ),
    "lent_basic": (
        a_lent_basic_attack,
        "a swing one row lends another creature, and who it is aimed at",
    ),
    "aura_penalty": (
        penalty_scoped_to_an_aura,
        "a penalty scoped to a creature and its allies inside its aura",
    ),
    "effect_keywords": (
        an_effects_keywords_come_from_the_row_that_laid_it,
        "an effect's keywords come from the row that laid it, not its label",
    ),
    "move_zone": (
        a_granted_action_that_walks_a_zone,
        "a granted action that walks one of the creature's own zones",
    ),
    "hit_target_line": (
        a_target_line_naming_an_earlier_swing,
        "a target line narrowed by what the caster already hit or missed",
    ),
    "hit_this_turn": (
        a_hit_earlier_this_turn,
        "a Requirement naming a blow landed earlier this turn, and its kind",
    ),
    "extend_every": (
        every_move_of_a_kind,
        "one extra square on every shift, and not on a teleport",
    ),
    "phasing": (phasing, "a ghost moves through a body and cannot stop in one"),
    "lighting": (lighting, "dim conceals, dark conceals totally, a sense cancels it"),
    "blindness": (blindness, "a blinded creature cannot see, and can again after"),
    "hiding": (hiding, "attacking gives you away, and AFTER is where you get it back"),
    "suspension": (suspension, "a trait switched off by a hit, and back on after"),
    "sure_footed": (sure_footed, "difficult terrain ignored when shifting, and only then"),
    "reentry": (reentry, "a watcher is not re-entered by an event it caused"),
    "regeneration_suspended": (regeneration_suspended,
                               "what switches a regeneration off: a material, or a damage type"),
    "living_targets": (living_targets,
                       "one living creature: not undead, and not construct unless living"),
    "creature_kinds": (creature_kinds,
                       "every character is a natural humanoid; an origin replaces it"),
    "lengthened_shift": (lengthened_shift,
                         "a feat lengthens another row's shift, read in the moved row"),
    "aid_another_grants": (aid_another_grants,
                           "the aid another action's +2 reaches a reader"),
    "penalties_by_source": (penalties_by_source,
                            "two penalties from two sources add; one source"
                            " landing twice does not"),
    "feat_clause_exclusivity": (feat_clause_exclusivity,
                                "two feats of one category cannot both ride"
                                " one use of a power; two of another can"),
    "at_most_one_applies": (at_most_one_applies,
                            "every row migrated under #550 pays exactly one"
                            " of its exclusive feats' clauses"),
    "once_spend_moments": (once_spend_moments,
                           "a one-shot bonus is spent where it is read"),
    "once_spent": (once_spent,
                   "a once= hold is spent by rewriting its own event"),
    "two_types": (two_types, "one roll that is two types, and resistance reads both"),
    "aftereffect": (aftereffect, "a clause that lands when the first one ends"),
    "crit_kill": (crit_kill, "a crit drops it to 0, and that is not damage"),
    "forms": (forms, "which shape a creature is in, and two at once"),
    "summoned": (summoned,
                 "a summon derives its numbers from its summoner"),
    "defective_entry": (defective_entry,
                        "a defective part drops the whole compendium entry"),
    "recharge_announced": (recharge_announced,
                           "a spent row coming back says so, on both paths"),
    "lost_mode": (lost_mode,
                  "a creature loses a way of moving, and gets it back"),
    "sealed_space": (sealed_space,
                     "an enemy cannot enter this creature's space by any means"),
    "racial_power_riders": (racial_power_riders,
                            "two feats answering one racial power, whose ref"
                            " resolves now"),
    "regeneration_resumed": (regeneration_resumed,
                             "a suppressed regeneration switched back on"),
    "printed_regeneration": (printed_regeneration,
                             "a stat block's Regeneration heals it, and its"
                             " printed clause stops it"),
    "conjurer_count": (conjurer_count,
                       "\"Initiative as conjurer\": the servant acts on the"
                       " summoner's count"),
    "raises_the_fallen": (raises_the_fallen,
                          "a corpse can be named now, and the rows dropped"
                          " on saying it cannot"),
    "area_or_close_is_one_set": (area_or_close_is_one_set,
                                 "\"an area or a close attack\" was five"
                                 " tuples and one disagreement"),
    "named_in_prose": (named_in_prose,
                       "three creatures a card names in prose, whose refs"
                       " were declared all along"),
    "reach_that_depends_on_a_state": (reach_that_depends_on_a_state,
                                      "\"Melee 2, or 4 while bloodied\": the"
                                      " header carries the permissive one"),
    "one_rows_burst_grows_by_a_modifier": (one_rows_burst_grows_by_a_modifier,
                                          "f1010: one named row's burst"
                                          " grows by Charisma while raging"),
    "area_that_depends_on_a_state": (area_that_depends_on_a_state,
                                     "\"close burst 2 (5 while bloodied)\":"
                                     " offered at 5, narrowed in the body"),
    "an_immunity_gated_on_the_attacking_defence": (
        an_immunity_gated_on_the_attacking_defence,
        "m5788a0 ignores conditions from a Will attack and nothing else"),
    "a_pact_feat_augments_the_power_it_names": (
        a_pact_feat_augments_the_power_it_names,
        "three [Greater Pact] feats pay their augment inside the power"),
    "a_feat_lends_an_augment": (a_feat_lends_an_augment,
                                "f3170 lends p10440 an Augment clause"
                                " its card does not print"),
    "the_invigorating_keyword_pays": (the_invigorating_keyword_pays,
                                      "a tag-only keyword, and the feats\n"
                                      " that read it"),
    "a_bare_skill_key_is_read_by_nothing":
        (a_bare_skill_key_is_read_by_nothing,
         "a bare skill name lays a modifier no roll reads"),
    "immunity_gated_on_the_attacking_power":
        (immunity_gated_on_the_attacking_power,
         "m5788a0's Will immunity, gated on a key that is written"),
    "terrain_words_are_a_closed_set":
        (terrain_words_are_a_closed_set,
         "c.terrain refuses a word no board is dressed with"),
    "thrown_is_not_fired": (thrown_is_not_fired,
                            "a thrown weapon is not a fired one; f140's gate\n"
                            " read the wrong column"),
    "every_manifestation_pays_its_printed_half":
        (every_manifestation_pays_its_printed_half,
         "all thirteen manifestations pay their printed static half"),
    "one_manifestation_not_thirteen": (one_manifestation_not_thirteen,
                                       "a race's choose-one traits are\n"
                                       " alternatives, not a stack"),
    "resistance_taken_off_the_target": (resistance_taken_off_the_target,
                                         "a target loses a resistance to one\n"
                                         " type; immunity is not"),
    "vulnerability_held_by_a_zone": (vulnerability_held_by_a_zone,
                                     "a zone or aura confers a"
                                     " vulnerability on whoever stands in"
                                     " it"),
    "both_printed_shapes_offered": (both_printed_shapes_offered,
                                    "a printed \"or\" between two shapes"
                                    " offers both, and the conditional pair"
                                    " is not the same gap"),
    "shield_penalty_waived": (shield_penalty_waived,
                              "f3779 gives back a heavy shield's check"
                              " penalty, and only that"),
    "band_stays_in_tier": (band_stays_in_tier,
                           "the three-level band does not cross a tier"
                           " boundary -- Camille, 2026-10-15"),
    "blank_defence_is_defective": (blank_defence_is_defective,
                                   "\"+X vs <blank>\" is malformed and the"
                                   " whole entry drops -- Camille, #612"),
    "manoeuvres": (manoeuvres,
                   "bull rush, grab and aid another, electable by anybody"),
    "difficult_aura": (difficult_aura,
                       "an aura can be difficult ground, waived for a side"),
    "compelled_walk": (compelled_walk,
                       "a compulsion moves; the creature does not choose"),
    "fell_might": (fell_might,
                   "the pact boon's one charge, its die, and the trade"),
    "event_provenance": (event_provenance,
                         "three more events that did not say what caused them"),
    "healed_power": (healed_power,
                     "which row did the healing, which Healed did not say"),
    "reach_stretch": (reach_stretch,
                      "a reach modifier the by-weapon rows were dropping"),
    "shield_bonuses": (shield_bonuses,
                       "a shield's AC contribution, as a readable number"),
    "ability_checks": (ability_checks,
                       "a raw ability check, which is not a skill check"),
    "unpreventable": (unpreventable,
                      "damage that resistance and immunity do not touch"),
    "zone_exempt": (zone_exempt,
                    "a cloud that blinds all but the creature that made it"),
    "points_regained": (points_regained,
                        "a power point put back, and the cap that refuses one"),
    "boon_traded": (boon_traded,
                    "a feat takes a power point instead of the boon's regain"),
    "lent_augments": (lent_augments,
                      "a feat lends a power an augment its card omits"),
    "counts_as_basic": (counts_as_basic,
                        "'counts as' is a designation, 'in place of' is not"),
    "empowerment_pool": (empowerment_pool,
                         "one per-day pool, two limits, and the order"),
    "aid_grants": (aid_grants,
                   "how much an aid action grants, and the raise that wins"),
    "bull_rush_riders": (bull_rush_riders,
                         "a row lengthens the push and the follow apart"),
    "long_rest": (long_rest,
                  "a long rest announces itself, and a daily comes back"),
    "short_rest": (short_rest,
                   "five minutes announces itself, once per creature, after"
                   " the restore"),
    "disease": (disease,
                "catching a disease, and a stage that does not move"),
    "exposure": (exposure,
                 "exposed is not contracted, and the throw comes when the"
                 " fight ends"),
    "keyword_ban": (keyword_ban,
                    "powers barred by keyword, in both directions"),
    "recharge_when": (recharge_when,
                      "a printed condition gives a spent row back"),
    "leash": (leash,
              "a tether: no further than N squares from something"),
    "attacks_defence": (attacks_defence,
                        "an attack moved onto a different defence"),
    "waive": (waive,
              "part of a condition's cost switched off, condition intact"),
    "extend_move": (extend_move,
                    "a named row moves you further, from outside it"),
    "conceal_in": (conceal_in,
                   "a zone that conceals whoever stands in it"),
    "rerolled": (rerolled,
                 "a roll announced as a second one, and gateable as one"),
    "boost_roll": (boost_roll,
                   "adding to a roll already made, without rolling again"),
    "recharge_while": (recharge_while,
                       "a recharge condition that is a state, not a moment"),
    "class_form": (class_form,
                   "a class form is a state and a keyword, and those differ"),
    "substitution": (substitution,
                     "one clause of a row replaced, and one added"),
    "drawing": (drawing,
                "taking a weapon up, and what it costs"),
    "reroll_low": (reroll_low,
                   "each damage die that shows a 1, rolled again"),
    "counts_as": (counts_as,
                  "what is in hand standing in for what a card asks"),
    "declined": (declined,
                 "the marker for work nobody intends to do"),
    "instead_now": (instead_now,
                    "a clause inside a watcher, replaced"),
    "granted_keywords": (granted_keywords,
                         "a keyword one creature's copy of a row carries"),
    "item_as_weapon": (item_as_weapon,
                       "an item that is also a weapon"),
    "scoped_vulnerable": (scoped_vulnerable,
                          "vulnerable to some of what reaches you"),
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
    skipped = sum(len(r.skipped) for r in results)
    # **The skipped count is printed even when it is zero.** A line that
    # only appears when something was skipped is a line nobody learns to
    # look for, and `browser.py`'s eight silent skips were found by
    # arithmetic rather than by a failure. See `Result.skip`.
    print(f"\n{total} printed rules hold, {sum(len(r.failed) for r in bad)} do not"
          + (f" ({', '.join(r.name for r in bad)})" if bad else "")
          + f", {skipped} could not be posed on the board used")
    if skipped:
        print("  what was skipped, and by which driver:")
        for r in results:
            for why in r.skipped:
                print(f"    {r.name}: {why}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
