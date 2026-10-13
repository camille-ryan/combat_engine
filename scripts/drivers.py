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
    out.that(not two.ended, "the second effect never ended")

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
    out.that(not thin.ended, "and still without ending the trait")

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
    mine = Cast(world=world, me=caster, ref=ref)
    declared = REGISTRY[ref]
    out.that(len(declared.damage.dtypes) == 5,
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


DRIVERS = {
    "phasing": (phasing, "a ghost moves through a body and cannot stop in one"),
    "lighting": (lighting, "dim conceals, dark conceals totally, a sense cancels it"),
    "blindness": (blindness, "a blinded creature cannot see, and can again after"),
    "hiding": (hiding, "attacking gives you away, and AFTER is where you get it back"),
    "suspension": (suspension, "a trait switched off by a hit, and back on after"),
    "sure_footed": (sure_footed, "difficult terrain ignored when shifting, and only then"),
    "reentry": (reentry, "a watcher is not re-entered by an event it caused"),
    "two_types": (two_types, "one roll that is two types, and resistance reads both"),
    "aftereffect": (aftereffect, "a clause that lands when the first one ends"),
    "crit_kill": (crit_kill, "a crit drops it to 0, and that is not damage"),
    "forms": (forms, "which shape a creature is in, and two at once"),
    "summoned": (summoned,
                 "a summon derives its numbers from its summoner"),
    "manoeuvres": (manoeuvres,
                   "bull rush, grab and aid another, electable by anybody"),
    "difficult_aura": (difficult_aura,
                       "an aura can be difficult ground, waived for a side"),
    "compelled_walk": (compelled_walk,
                       "a compulsion moves; the creature does not choose"),
    "fell_might": (fell_might,
                   "the pact boon's one charge, its die, and the trade"),
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
    print(f"\n{total} printed rules hold, {sum(len(r.failed) for r in bad)} do not"
          + (f" ({', '.join(r.name for r in bad)})" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
