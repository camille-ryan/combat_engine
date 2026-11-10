"""Diseases, levels 6 to 8. #948.

Five cards, one row each, branching on `c.stage` -- see the package
docstring for the shape and for the one rule these rows have to obey:
**a stage lays a standing effect and never charges a one-time cost**,
because `turns.arm_afflictions` runs the row at the start of every fight.

Two conventions settled while writing them, both worth stating because the
printed pages do not state either:

* **A stage's paragraph is the whole of that stage.** The pages restate
  what carries over -- `x5_53` prints its attack penalty again at stages 2
  and 3, and `x5_81` prints its halved healing again at stage 3 -- so a
  clause that is *not* restated is one that stage does not have. The
  branches are therefore exact (`== 1`) rather than cumulative, except
  where a line says "until cured", which outlives the stage that granted
  it.
* **An end-of-rest clause has no moment in a fight.** Damage taken at an
  extended rest, and a track that kills the character at its worst stage,
  belong to `affliction.tick` and cannot be re-laid per encounter without
  charging them once a fight. Those are marked rather than approximated.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.diseases import lost_surges
from combat_engine.engine import (
    AT_WILL,
    NO_TARGET,
    WILL,
    ActionType,
    Cast,
    Health,
    Melee,
    SavingThrow,
    When,
    Window,
    power,
)
from combat_engine.engine.events import (
    Bloodied,
    DamageApplied,
    DamageType,
    Healed,
    Hit,
    TurnStart,
)


def _ally_beside(c: Cast) -> int | None:
    """An ally the diseased character could reach with a melee swing.

    Lowest id of the ones adjacent, so two runs of the same board pick the
    same victim: the card says "an ally adjacent to it" and leaves the
    choice open, and a random pick would move every replay fixture for
    nothing.
    """
    beside = sorted(friend for friend in c.allies() if c.adjacent(friend))
    return beside[0] if beside else None


def _swing_at_an_ally(c: Cast, busy: list[Any]) -> None:
    """The free melee basic attack two of these cards turn on the party.

    `who=` is the attacker and `on=` is who gets hit, and both have to be
    said: the row is `NO_TARGET`, so a bare `c.basic()` aims at nobody and
    never rolls.

    `busy` is the re-entrancy guard, and it is load-bearing on the
    stage-3 reading of `x5_54`: that one answers *being hit*, and the
    swing it makes can provoke a hit back.
    """
    if busy:
        return
    friend = _ally_beside(c)
    if friend is None:
        return
    busy.append(friend)
    try:
        c.basic(who=c.me, on=friend)
    finally:
        busy.clear()


def _weakened_while_bloodied(c: Cast) -> None:
    """"While bloodied, the target is weakened" -- laid and lifted.

    A condition takes no `when=` gate, so unlike a modifier this cannot be
    asked as it is read. Laid as the line is crossed and taken off again if
    the character climbs back over it, which is `m784a3`'s arrangement for
    a hold the printed "while" gives back -- laid once and left, the
    character would stay weakened after a heal that should have cleared it.

    **Both halves had to be driven, and both were wrong for the same
    reason: an event that announces a change does not mean the change has
    happened.**

    * `Bloodied` alone never laid it. A character crossing the line is
      routinely healed straight back over it by something answering that
      very event -- an ally spending a surge on it -- so a listener running
      after the healer reads a creature that is not bloodied. Measured: hp
      28 of 68 at the blow, 49 by the time `Bloodied` had finished being
      handled. `DamageApplied` is emitted before `Bloodied` and carries the
      hit points the blow left, so the hold goes on there; `hold` makes the
      two idempotent.
    * `Healed` never lifted it, because that event is announced **before**
      the hit points go on (`resolve.heal` says so outright) -- so the live
      component still reads bloodied and `c.bloodied` answers True in the
      one handler whose whole job is to notice that it has stopped being
      true. The number the heal *will* leave is `ev.hp + ev.amount`.

    `TurnStart` is the net under both: it reconciles the hold against the
    hit points at a moment when nothing is mid-resolution.
    """
    me = c.me
    hold: list[Any] = []

    def sicken() -> None:
        if hold:
            return
        got = c.weakened(on=me, until=When.ENCOUNTER)
        if got is not None:
            hold.append(got)

    def relieve() -> None:
        if hold:
            c.world.effects.end(hold.pop(), c.ref)

    def hurt(ev: DamageApplied) -> None:
        if ev.target == me and c.bloodied(on=me):
            sicken()

    def bled(ev: Bloodied) -> None:
        if ev.actor == me and c.bloodied(on=me):
            sicken()

    def mended(ev: Healed) -> None:
        health = c.world.get(me, Health)
        if ev.target != me or not hold or health is None:
            return
        if min(health.max_hp, ev.hp + max(0, ev.amount)) > health.max_hp // 2:
            relieve()

    def opens(ev: TurnStart) -> None:
        if ev.actor != me:
            return
        if c.bloodied(on=me):
            sicken()
        else:
            relieve()

    # Armed mid-fight as well as at the start of one: a character can walk
    # into an encounter already below half.
    if c.bloodied(on=me):
        sicken()
    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} weakens")
    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label=f"{c.ref} crossed")
    c.watch(Healed, mended, until=When.ENCOUNTER, on=me, label=f"{c.ref} mended")
    c.watch(TurnStart, opens, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} reconciled")


@power("x5_54", cls="disease", level=6, usage=AT_WILL, action=ActionType.NONE,
       target=NO_TARGET, reach=Melee(0))
def x5_54(c: Cast) -> None:
    """Three stages, three paragraphs, all written.

    Stages 2 and 3 differ only in the moment they answer, so they are one
    helper and two watches. Neither is the gap `c.must_attack` names: the
    row makes the swing itself rather than constraining what the character
    chooses to do with its own turn.
    """
    me = c.me
    stage = c.stage
    busy: list[Any] = []
    if stage == 1:
        c.penalty(WILL, 2, on=me, until=When.ENCOUNTER)
        return
    if stage == 2:

        def bled(ev: Bloodied) -> None:
            if ev.actor == me:
                _swing_at_an_ally(c, busy)

        c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me,
                label=f"{c.ref} frenzy")
        return

    def struck(ev: Hit) -> None:
        if getattr(ev, "target", None) == me:
            _swing_at_an_ally(c, busy)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=f"{c.ref} frenzy")


@power("x5_36", cls="disease", level=6, usage=AT_WILL, action=ActionType.NONE,
       target=NO_TARGET, reach=Melee(0))
def x5_36(c: Cast) -> None:
    """All three stages written, and the middle one needed no new verb.

    "It can roll only one saving throw at the end of its turn, even if it
    is affected by multiple effects" is a **refusal** of the throws after
    the first. `SavingThrow` is a `Decision` and `Durations.save` reads
    `cancelled` back -- its own comment says a cancelled throw never
    happened, so the effect stays and nothing escalates, which is exactly
    what the card withholds. `ev.cancel` rather than `c.cancel`: the
    latter answers the row's own declared trigger and a trait has none.

    Stage 3 is `c.reroll_save(keep="worst")`, which is "rolls two dice and
    takes the lower" said once instead of by hand -- it re-totals `saved`
    off the kept die, which a hand-written version has to remember.

    The bloodied half of each line is asked at the moment of the throw and
    never snapshotted at arming: all three windows are open for the whole
    fight and the character crosses the line inside them.
    """
    me = c.me
    stage = c.stage
    if stage == 1:
        c.penalty("save", 2, on=me, until=When.ENCOUNTER,
                  when=lambda ctx: c.bloodied(on=me))
        return
    if stage == 2:
        spent = f"{c.ref} throw"

        def one_only(ev: SavingThrow) -> None:
            if ev.actor != me or ev.when_ != "end" or not c.bloodied(on=me):
                return
            if c.latched(spent, on=me, per_turn=True):
                ev.cancel(c.ref)
            else:
                c.latch(spent, on=me, per_turn=True)

        c.watch(SavingThrow, one_only, until=When.ENCOUNTER, on=me,
                window=Window.BEFORE, label=f"{c.ref} one throw")
        return

    def two_dice(ev: SavingThrow) -> None:
        if ev.actor == me and c.bloodied(on=me):
            c.reroll_save(keep="worst", ev=ev)

    c.watch(SavingThrow, two_dice, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=f"{c.ref} two dice")


@power("x5_81", cls="disease", level=7, usage=AT_WILL, action=ActionType.NONE,
       target=NO_TARGET, reach=Melee(0),
       dropped=("affliction.tick(rest_damage=)", "affliction.tick(dies=)"))
def x5_81(c: Cast) -> None:
    """Stages 1 and 2 are whole; stage 3 plays its healing half only.

    **The lost surge goes through `_lost_surges`**, which is one place
    rather than two: `c.surge` would take a fresh surge every encounter,
    and the field pair this writes instead has one trap in it that my own
    first version walked into.

    `_wear` runs **before** `turns.arm_afflictions` and clamps the
    harvested pool against the ceiling this row has not lowered yet, so a
    decrement takes a second surge on the next board, and a third on the
    one after. Measured at level 7 over four boards with no rest between
    them -- which is a real sequence (`#947`) -- as `11,11 11,10 11,9
    11,8`, against `11,11` four times for the clamp. A rest refills the
    pool and hides it completely, and `max_surges` alone is stable under
    both, so the only check that sees it reads **both** fields over
    **three or more** boards. Found by a sibling module on this wave, not
    by my own driving, which rested. See `low_heroic._lost_surges`.

    **The keyword outlives the stage that granted it**, because the card
    says "until cured" rather than "while affected by stage 2" -- so it is
    laid at stage 2 and at stage 3, which is the only line on these five
    cards that crosses a stage boundary. `c.set_origin` is where a type
    word lives for a character, which has no stat block to carry one.

    Stage 3's other two clauses are the marker. Both happen **at an
    extended rest** -- 15 poison damage that cannot be healed, and a
    worsened check killing the character outright -- and `affliction.tick`
    is the one place with that moment. Re-laid per fight they would be
    charged once an encounter, which is the failure the package docstring
    is about; the death half also needs the tick to be able to end a
    character and stand something else up, which it cannot.
    """
    me = c.me
    stage = c.stage
    if stage == 1:
        lost_surges(c, 1)
        return
    c.half_healing(on=me, until=When.ENCOUNTER)
    c.set_origin("plant", on=me, until=When.ENCOUNTER)


@power("x5_53", cls="disease", level=7, usage=AT_WILL, action=ActionType.NONE,
       target=NO_TARGET, reach=Melee(0))
def x5_53(c: Cast) -> None:
    """The penalty and the weakening play at every stage; stage 3's extra
    poison damage is the marker, and it is a measured number rather than a
    missing verb.

    The attack penalty is printed by every stage, so it is laid before the
    branch rather than three times inside it.

    **Written, driven, and withdrawn.** The clause was
    `c.flat(10, dtype=POISON, on=c.me)` off a `DamageApplied` gated on
    `c.by_attack` -- the right event, the right gate, and the right type --
    and it came out as **5**. Every damage verb a row can reach deals the
    blow as the *caster's* output: `c.flat` hands `deal_damage` the default
    `from_attack=True`, and `resolve.deal_damage` halves that when
    `query.deals_half` says the source is weakened. The source here is the
    diseased character, and this same paragraph weakens it -- so the one
    stage that prints this clause is the one stage that can never pay it in
    full, on every board, with nothing saying so.

    **Restored, with the parameter.** `c.flat(from_attack=)` exists now:
    `resolve.deal_damage` has taken the flag since #731 and `c.flat` simply
    never forwarded it. Passing `from_attack=False` says what is true --
    this packet is the disease paying out, not the character attacking --
    so `resolve.py:1286`'s `if from_attack and deals_half(...)` no longer
    halves it. Measured on a board: 10 unweakened, **5** weakened with the
    old default, 10 weakened with the flag.

    The gate stays `c.by_attack(ev=ev)` because the *incoming* blow must be
    an attack -- which is what the card narrows on -- while the *outgoing*
    10 is not one. The two directions were conflated by having a single
    default, and that is the whole of why the clause read wrong.
    """
    me = c.me
    stage = c.stage
    c.penalty("attack", 2, on=me, until=When.ENCOUNTER)
    if stage == 1:
        return
    if stage == 2:
        _weakened_while_bloodied(c)
        return
    c.weakened(on=me, until=When.ENCOUNTER)

    def bleeds(ev: DamageApplied) -> None:
        """Ten more, whenever an attack is what hurt them.

        `ev.amount` is not consulted: the card prints a flat ten rather
        than a share, so a blow for 1 and a blow for 40 both add the same.
        """
        if getattr(ev, "target", None) != me or not c.by_attack(ev=ev):
            return
        c.flat(10, dtype=DamageType.POISON, on=me, from_attack=False)

    c.watch(DamageApplied, bleeds, until=When.ENCOUNTER, on=me, label=c.ref)


@power("x5_34", cls="disease", level=8, usage=AT_WILL, action=ActionType.NONE,
       target=NO_TARGET, reach=Melee(0),
       dropped=("c.must_attack(on=, against=)",))
def x5_34(c: Cast) -> None:
    """Stage 1 plays; stages 2 and 3 are one gap said twice.

    Both of the later paragraphs take the character's turn away from it --
    a melee attack on a random creature within 5 squares, or on the
    nearest one in sight, and a random walk when there is nobody to hit.
    That is an instruction to whoever is choosing the character's actions,
    and nothing constrains that: `m784a3` carries the same symbol for the
    same reason.

    **Stage 2's saving throw is deliberately not written.** It exists only
    to decide whether the forced attack happens, so on its own it would
    roll a die every turn and act on nothing -- a row that looks like it
    is doing the work.
    """
    if c.stage == 1:
        c.penalty(WILL, 2, on=c.me, until=When.ENCOUNTER)
