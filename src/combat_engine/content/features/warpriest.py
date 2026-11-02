"""The nine domain options printed under `cf:cleric-warpriest-f1`.

Nine sub-options, one shape: a standing benefit, a rider on `p1455`, and a
list of powers the option hands over. **None of the nine is dealt by the
draw** -- `chargen.chassis_of("cleric")` takes the first declared chassis in
ref order and that is `templar`, and nothing in production asks for another
-- so the consumer is `f3589`, which trades `cf:cleric-templar-f1` for one
of these through `c.borrow_row(among=)`. That filter was empty for as long
as none of them was declared, which is the cleric half of #581.

The parent `cf:cleric-warpriest-f1` is **not** declared and is not declared
here either. `arcanist.py`'s rule -- where a parent implements a branch
outright the sub-option ref is skipped, because declaring both deals the
same card twice -- does not bite: there is no parent row to double, and
`f3589` has to be able to name one option of the nine.

**The `p1455` riders hang off two different events, and which one is the
card's choice rather than a convenience.**

* A rider whose subject is the caster or the burst answers `PowerUsed`.
* A rider whose subject is *the target* answers `Healed`, because `p1455`
  picks the creature it heals **inside its own body** and the choice can be
  declined -- so `PowerUsed.targets` names whoever the framework
  pre-selected and not whoever regained hit points.

`feats/cleric_b.py` settled that reading for the nineteen feats on the same
rail and its module docstring states it; these rows follow it rather than
deciding it again.

`level=0`, which is what `cf:cleric-templar-f1` and every other chassis row
carries and what `chargen._declared_chassis` counts.

Every one of these cards prints an 11th- and a 21st-level number. Those are
paragon and epic, so the heroic figure is the whole row rather than a
clause that is missing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    WILL,
    ActionType,
    Cast,
    DamageRolled,
    DamageType,
    Healed,
    Keyword,
    PowerUsed,
    SavingThrow,
    TurnStart,
    When,
    power,
)
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.query import allies, distance_between

#: The row every one of the nine riders on, by ref.
WORD = "p1455"

_DEFENCES = (AC, FORT, REF, WILL)


def _on_word_used(c: Cast, fn: Callable[[Any], None]) -> None:
    """This caster's own use of `WORD`, answered as it is declared.

    For the riders whose subject is the caster or the burst. `PowerUsed` is
    announced before the body runs, which costs nothing here: none of those
    riders reads anything the body does.
    """
    me = c.me

    def used(ev: Any) -> None:
        if ev.actor == me and ev.power == WORD:
            fn(ev)

    c.watch(PowerUsed, used, until=When.ENCOUNTER, on=me, label=c.ref)


def _on_word_target(c: Cast, fn: Callable[[Any], None]) -> None:
    """The creature `WORD` actually heals, once per use of it.

    `Healed` and not `PowerUsed.targets` -- see the module docstring.

    **Latched, because one use announces two heals.** `c.surge` emits a
    `Healed` carrying the row's ref for the surge's own payout and the body
    then emits a second for the extra hit points, so an unguarded rider
    pays twice for one printed sentence. The latch is cleared on
    `PowerUsed`, which is announced before the body and so before either
    heal. `once=` on `c.watch` cannot do this job: it reads the log to see
    whether the handler did anything, and a handler whose whole work is a
    modifier announces nothing and never spends its hold -- which is the
    reasoning `cleric_b._once_healed` already records.
    """
    me = c.me
    paid: list[int] = []

    def used(ev: Any) -> None:
        if ev.actor == me and ev.power == WORD:
            paid.clear()

    def healed(ev: Any) -> None:
        if ev.source != me or ev.power != WORD or paid:
            return
        paid.append(1)
        fn(ev)

    c.watch(PowerUsed, used, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(Healed, healed, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:cleric-warpriest-f1s0",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    dropped=("spec.ref",),
)
def warpriest_domain_s0(c: Cast) -> None:
    """An extra throw against a charm, and rough ground ignored on a shift.

    **The throw is an additional one, not a moved one, which is why this is
    not `c.save_early`.** That verb *moves* the end-of-turn throw to the
    start, and its own docstring draws the line: `cf:warden-f0` grants an
    extra throw from a `TurnStart` watch and the ordinary one still
    happens. This card says "at the start of each of your turns, **as well
    as at the end**", so it is the warden's shape and not the item's.

    The narrowing to a charm is a label-to-ref read. `c.save(against=)`
    matches a label fragment, an effect's label leads with the ref of the
    row that laid it, and `durations.keywords_of` turns that back into the
    row's keywords. Each charm hold is therefore named to `c.save`
    individually: left to pick for itself, `c.save` takes whichever
    save-ends effect it finds first, which may well be a daze when the card
    means the charm.

    "You can" is not offered, for `cf:warden-f0`'s reason -- an extra throw
    against a save-ends effect is never worse than declining it.

    The rider is about the caster and the burst, so it answers `PowerUsed`.
    `when="shift"` and not a bare exemption: the card says "when
    shifting", and the bare form would buy a free walk over rough ground
    as well. `SONT` because the card says "until the start of your next
    turn", which is the one place in this file that is not `EONT`.

    The last sentence is `dropped`. The spec prints "the following powers"
    and no refs, and `class_feature` holds no `cf:cleric-warpriest-f1s0c<N>`
    card either, so there is nothing to grant and nothing to guess.
    """
    me = c.me

    def extra_throws(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for held in list(c.world.effects.of(me)):
            if held.when is When.SAVE_ENDS and Keyword.CHARM in keywords_of(held):
                c.save(on=me, when_="early", against=held.label)

    c.watch(TurnStart, extra_throws, until=When.ENCOUNTER, on=me, label=c.ref)

    def shifting_is_free(ev: Any) -> None:
        for friend in c.within(5, of=me, side="team"):
            c.ignores_difficult(when="shift", on=friend, until=When.SONT)

    _on_word_used(c, shifting_is_free)


@power(
    "cf:cleric-warpriest-f1s1",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def warpriest_domain_s1(c: Cast) -> None:
    """A resistance, temporary hit points for the caster, four powers.

    The temporary hit points are **yours** and not the target's -- "you
    gain 5" -- so this is a `PowerUsed` rider with `on=c.me`. The row has
    no target of its own, so a bare call would grant them to nobody.

    5 is the heroic number; 10 and 15 are paragon and epic.
    """
    me = c.me
    c.resist(5, DamageType.NECROTIC, on=me, until=When.ENCOUNTER)

    def braced(ev: Any) -> None:
        c.temp_hp(5, on=me)

    _on_word_used(c, braced)

    for ref in ("p13939", "p13940", "p13941", "p13942"):
        c.grant_row(ref)


@power(
    "cf:cleric-warpriest-f1s2",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    dropped=("class_feature.trains",),
)
def warpriest_domain_s2(c: Cast) -> None:
    """A skill training with no column to live in, and a rider that plays.

    **The training is a chargen fact and `class_feature` cannot carry it.**
    `race.trains` and `feat.trains` both exist and `chargen` reads them
    into `Skills.trained`; `class_feature` holds `ref`, `class`, `ord`,
    `build`, `spec` and `duplicate_of` and nothing else, so a class feature
    granting a training has nowhere to say so. `rt:r52-t3` is the row that
    settles the shape -- inert in a body, granted in `chargen` -- and the
    only thing missing here is the column.

    Writing it as `c.bonus("skill:intimidate", 5)` instead would be the
    wrong mechanism, and `engine/skills.py` says why in its own comment:
    training is a property of the creature rather than an effect laid on
    it, so it must not be ended, suspended, stacked with itself or scoped
    by a gate -- and one key for both would let a card's own +5 silently
    replace it.

    The rider is about the target, so it is a `Healed` read. 5 temporary
    hit points; the 10 and the 15 are paragon and epic.
    """

    def shielded(ev: Any) -> None:
        c.temp_hp(5, on=ev.target)

    _on_word_target(c, shielded)

    for ref in ("p16418", "p16419", "p16420", "p16421"):
        c.grant_row(ref)


@power(
    "cf:cleric-warpriest-f1s3",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def warpriest_domain_s3(c: Cast) -> None:
    """A save bonus against burns, and exactly one softened blow.

    The saving-throw context carries `ongoing` **and** `actor`, which is
    what makes both halves of the first sentence answerable: the narrowing
    is the gate, and the distance is asked of the creature rolling rather
    than closed over, so the five squares are measured when the throw is
    made and not when the trait armed. Both creatures move. The caster is
    covered unconditionally; the allies are the ones the distance is about.

    **The rider is a latched halving and not `c.insubstantial`.** That verb
    takes no `once=`, so laid until the end of my next turn it would halve
    every attack inside the window where the card halves one -- strictly
    stronger than print, and it would read as a working row.  `c.halve`
    takes a number off a rolled blow and `DamageRolled` is the `Decision`
    carrying the amount, which `resolve` reads back after the emit.

    `c.by_attack` is what makes it "the next **attack** that hits it", and
    `from_attack` is the trap its docstring names: that flag is true of an
    ongoing tick and of a trait's flat payout too, so a hold spent on one
    would never reach an attack.
    """
    me = c.me

    def against_a_burn(ctx: dict[str, Any]) -> bool:
        who = ctx.get("actor")
        if not ctx.get("ongoing") or not isinstance(who, int):
            return False
        return who == me or distance_between(c.world, me, who) <= 5

    for friend in [me, *c.allies()]:
        c.bonus(
            "save", 2, kind="power", on=friend, until=When.ENCOUNTER,
            when=against_a_burn,
        )

    def soften(ev: Any) -> None:
        victim = ev.target
        spent: list[int] = []

        def halved(blow: Any) -> None:
            if spent or blow.target != victim or not c.by_attack(ev=blow):
                return
            if c.halve(blow):
                spent.append(1)

        c.watch(DamageRolled, halved, until=When.EONT, on=me, label=c.ref)

    _on_word_target(c, soften)

    for ref in ("p13706", "p13707", "p13708", "p13709"):
        c.grant_row(ref)


@power(
    "cf:cleric-warpriest-f1s4",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    dropped=("spec.ref",),
)
def warpriest_domain_s4(c: Cast) -> None:
    """One ability rolled in place of another, and a save bonus for allies.

    **The substitution is the difference between the two modifiers**, which
    is `f3777`'s shape and its reasoning: `skill:<name>` is a live key
    `skills.modifier` reads, so "in place of its own" is the gap between
    the two numbers. `skills.SKILLS` keys exactly three checks off
    Intelligence, so the sentence is three calls rather than a blanket one
    -- a blanket `skill` modifier would pay on the other fourteen too.

    Laid only when the gap is positive, because the card prints "can": a
    negative gap applied anyway would force the character to roll the worse
    of the two abilities. The gap is taken when the trait arms, which is
    when the two readings agree -- nothing temporary has been laid on
    either ability yet. That is `f3777`'s approximation and the same small
    one.

    "+1 bonus" with no type word in front of it, so untyped, and `once=`
    for "the next saving throw" -- a hold spent by one throw rather than a
    duration. `side="ally"` leaves the caster out, which is what "each ally
    in the burst" says.

    The powers are `dropped` for `f1s0`'s reason: the spec prints no refs
    and no card row exists to grant.
    """
    me = c.me
    gap = c.wis_mod - c.int_mod
    if gap > 0:
        for skill in ("arcana", "history", "religion"):
            c.bonus(f"skill:{skill}", gap, on=me, until=When.ENCOUNTER)

    def steady(ev: Any) -> None:
        for friend in c.within(5, of=me, side="ally"):
            c.bonus("save", 1, on=friend, until=When.EONT, once=True)

    _on_word_used(c, steady)


@power(
    "cf:cleric-warpriest-f1s5",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    dropped=("spec.ref",),
)
def warpriest_domain_s5(c: Cast) -> None:
    """Two resistances, and the creatures crowding whoever was healed.

    The rider has to know which creature `p1455` healed in order to measure
    adjacency, so it is a `Healed` read and not a `PowerUsed` one.
    `c.within(1, of=..., side="enemy")` moves the centre of the circle and
    still reads the side from the caster, which is what "each enemy" means
    on a cleric's card.

    "The next damage roll it makes before the end of **its** next turn" is
    `EOTNT` -- the one rider in this file measured from the creature
    carrying it rather than from the caster -- with `once=` for "the next".
    A penalty, so no `kind=`.

    The -4 and the -6 are paragon and epic. The powers are `dropped` for
    `f1s0`'s reason.
    """
    me = c.me
    c.resist(5, DamageType.NECROTIC, on=me, until=When.ENCOUNTER)
    c.resist(5, DamageType.RADIANT, on=me, until=When.ENCOUNTER)

    def cowed(ev: Any) -> None:
        for foe in c.within(1, of=ev.target, side="enemy"):
            c.penalty("damage", 2, on=foe, until=When.EOTNT, once=True)

    _on_word_target(c, cowed)


@power(
    "cf:cleric-warpriest-f1s6",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def warpriest_domain_s6(c: Cast) -> None:
    """Two resistances, four powers, and a bonus on the healed creature.

    `kind="power"` because the card prints the word in front of "bonus",
    and `EOTNT` because the window is "the end of **his or her** next
    turn" -- the creature healed, not the cleric. `once=` for "the next
    damage roll".

    The +4 and the +6 are paragon and epic.
    """
    me = c.me
    c.resist(5, DamageType.LIGHTNING, on=me, until=When.ENCOUNTER)
    c.resist(5, DamageType.THUNDER, on=me, until=When.ENCOUNTER)

    def emboldened(ev: Any) -> None:
        c.bonus(
            "damage", 2, kind="power", on=ev.target,
            until=When.EOTNT, once=True,
        )

    _on_word_target(c, emboldened)

    for ref in ("p12634", "p12635", "p12636", "p12637"):
        c.grant_row(ref)


@power(
    "cf:cleric-warpriest-f1s7",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def warpriest_domain_s7(c: Cast) -> None:
    """A death-save bonus no modifier can carry, and two hit points.

    **`c.bonus("save", 2)` would be laid and never read here.**
    `turns._death_saves` rolls with `bonus=0` and never asks
    `total("save")`, so the only seam is the `SavingThrow` it emits: a
    `Decision` read back for `saved`, which this re-decides with the +2 in
    it. `f1964` is the same sentence at a different number and is the row
    this follows.

    The distance is asked when the throw is made rather than when the trait
    arms, because both creatures move. The caster is covered
    unconditionally -- the first sentence is about the cleric and the
    second extends it to allies within five squares.

    The rider is "you **or** an ally in the burst", so it is a choice and a
    `PowerUsed` read: who regains the hit points is a different question
    from who the power healed, which is why this one is not on `Healed`.
    2 is the heroic number.
    """
    me = c.me

    def steadier(ev: SavingThrow) -> None:
        if ev.against != "death" or ev.saved:
            return
        if ev.actor != me:
            if ev.actor not in allies(c.world, me):
                return
            if distance_between(c.world, me, ev.actor) > 5:
                return
        ev.saved = ev.natural + ev.bonus + 2 >= 10

    c.watch(SavingThrow, steadier, until=When.ENCOUNTER, on=me, label=c.ref)

    def a_little_back(ev: Any) -> None:
        pool = [me, *c.within(5, of=me, side="ally")]
        who = c.choose(pool, f"{c.ref}: who regains 2 hit points")
        if who is not None:
            c.heal(2, on=who)

    _on_word_used(c, a_little_back)

    for ref in ("p12647", "p12648", "p12649", "p12650"):
        c.grant_row(ref)


@power(
    "cf:cleric-warpriest-f1s8",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    dropped=("c.refuses_forced_attack()", "spec.ref"),
)
def warpriest_domain_s8(c: Cast) -> None:
    """The refusal has no seam to sit in; the rider is `f1752`'s shape.

    **Nothing routes a compelled attack through anything the compelled
    creature can fail.** A card that turns a creature on its own side calls
    `c.basic(who=victim, on=foe)` outright --
    `monsters/level_08/controllers_sa._forced_basic_against_own_side` is
    the worked case and there are others -- so there is no moment at which
    "such an attempt automatically fails" could be read.

    And the card's own second sentence rules out the near miss: "damage or
    conditions associated with the effect can still affect you" means this
    must **not** be written as an immunity to the condition that compels.
    Refusing the condition would be strictly stronger than print and in
    the wrong place. What is wanted is narrow -- a creature-level refusal
    the attack-granting verbs consult.

    The rider plays, and it is `f1752` at a different duration: a +2 power
    bonus to all four defences on the creature healed, until the end of the
    caster's next turn.

    The powers are `dropped` for `f1s0`'s reason -- the spec prints no refs
    and no card row exists to grant.
    """

    def warded(ev: Any) -> None:
        for defence in _DEFENCES:
            c.bonus(defence, 2, kind="power", on=ev.target, until=When.EONT)

    _on_word_target(c, warded)
