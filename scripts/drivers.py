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
