"""Sorcerer feats, the second batch.

Six of these read a class feature, and the difference between the ones
that are written and the ones that carry a marker is whether the feature
has a ref. The **soul** does -- `cf:sorcerer-f0`, in
`content/powers/sorcerer/souls.py` -- and it keeps which type it is sworn
to in a marker effect, so `soul_of` and `soul_resist` answer "your Spell
Source resistance" directly and four rows here turn on that. The cosmic
cycle and the temporary-hit-point feature do not, and those carry
`c.class_feature()` like the fifteen rows elsewhere that want the same
thing.

The other recurring shape is **parity**: three cards ask the player to
call even or odd before a roll and pay out when the call lands. One of the
three is an attack roll, which `AttackRolled.natural` announces before the
damage is rolled, so it is writable. The other two are still held, for
different reasons: the class feature's d10 is rolled inside the feature
and announced to nobody, while the initiative check is **written** now: it
was announced all along -- `InitiativeRolled` -- and what was missing was
the die rather than the moment, since the event carries the finished
count. `Initiative.natural` records the face, so `f2807` reads it off
the component. One half of that card is still owed and it is the
engine's ordering, not the parity: `Encounter.start` rolls before
`_arm_traits`, so no trait is listening for the fight's own opening
roll. `#1500`.

`usage=AT_WILL` throughout -- none of these prints a once-per-encounter
limit, and a triggered row is asked `usable` every time it is offered.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.sorcerer.souls import (
    soul_damage,
    soul_of,
    soul_resist,
    wear_soul,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    DamageType,
    Forced,
    Gear,
    Hit,
    Initiative,
    Keyword,
    Miss,
    Skills,
    Trigger,
    When,
    after_forced_reroll,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    CheckDeclared,
    ForcedMove,
    InitiativeRolled,
)
from combat_engine.engine.triggers import about_me
from combat_engine.engine.types import Usage


def _storm(ctx: dict[str, Any]) -> bool:
    """An arcane power carrying either of the two printed keywords."""
    p = get(str(ctx.get("power") or ""))
    return (
        p is not None
        and Keyword.ARCANE in p.keywords
        and (Keyword.LIGHTNING in p.keywords or Keyword.THUNDER in p.keywords)
    )


def _my_sorcerer_slide(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.source == me
        and ev.how is Forced.SLIDE
        and p is not None
        and p.cls == "sorcerer"
    )


def _my_daily_roll(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "sorcerer"
        and p.usage is Usage.DAILY
    )


#: One call per daily power per round, keyed by caster. "For one attack
#: roll" is the printed scope and a burst rolls once per target, so
#: without this the choice would be offered -- and paid -- on every one.
_CALLED: dict[int, tuple[str, int]] = {}


# -- the soul, which has a ref and can therefore be read --------------------


@power("f1167", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1167(c: Cast) -> None:
    """An aura rather than a loop over whoever is adjacent right now:
    "each ally adjacent to you" follows the sorcerer around the board, and
    `c.resist_in` is the one verb that carries resistance into a zone --
    `c.grants_in` cannot, because resistance lives on `Defences` and a
    modifier named "resist" is read by nothing.

    Which type, and how much, are both the feature's own answers.
    """
    kind = soul_of(c)
    if kind is None:
        return
    c.resist_in(c.aura(1), soul_resist(c.level), kind, side="ally")


@power("f3430", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3430(c: Cast) -> None:
    """Added rather than relaid: `c.resist` sums into `Defences.resist`
    for the type, so 2 on top of whatever the soul already laid is the
    printed increase and does not have to know what that was."""
    gear = c.world.get(c.me, Gear)
    kind = soul_of(c)
    if kind is None or gear is None or gear.armour != "leather":
        return
    c.resist(2, kind, on=c.me, until=When.ENCOUNTER)


@power("f1233", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1233(c: Cast) -> None:
    """"Instead of rolling" is sayable because the roll has already
    happened: traits arm in the order the creature knows its rows and the
    class feature comes before the feats, so `wear_soul` finds a sworn
    type to end. It ends the marker and the resistance together, which is
    why the swap is one call rather than a search.

    Gated on the build, because the other leg does not roll at all.
    """
    if not c.build("wild"):
        return
    kind = c.choose(
        [DamageType.COLD, DamageType.NECROTIC], f"{c.ref}: which resistance"
    )
    if kind is not None:
        wear_soul(c, kind)


@power("f2045", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2045(c: Cast) -> None:
    """The amount and the type are both writable now.

    The damage the card hands `f2023b` is the wild leg's own clause --
    `soul_damage` over the ability that leg keys off -- and a feat's
    granted card is an ordinary ref, so gating a damage modifier on it is
    the whole of the first half.

    "The same type as your current Wild Soul damage type" is the build's
    own element and `c.element` is the reader for it. A build that
    recorded none leaves the rider untyped, which is where it was.
    """
    if not c.build("wild"):
        return
    c.bonus(
        "damage", c.dex_mod + soul_damage(c.level), on=c.me,
        until=When.ENCOUNTER, dtype=c.element(),
        when=lambda ctx: ctx.get("power") == "f2023b",
    )


# -- standing modifiers -----------------------------------------------------


@power("f1159", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1159(c: Cast) -> None:
    """A trait with a watch rather than a declared trigger: the skill
    bonus is a standing modifier, and a row declaring `on=` runs only when
    the trigger fires, so a modifier laid in it is never laid at all.

    Combat advantage is why the damage half cannot be a gated modifier.
    The damage context carries `target`, `power`, `dtype`, `opportunity`,
    `charge` and `crit` and **no `advantage`**, and asking
    `has_combat_advantage` again at damage time is too late -- a one-shot
    grant has already been spent. `Hit` carries the live `AttackResult`,
    so the bonus is laid from there, for that blow and that enemy only,
    and is read by the `c.damage` the power's own body goes on to call.
    """
    me = c.me
    step = 2 + 2 * (c.level >= 11) + 2 * (c.level >= 21)
    c.bonus("skill:stealth", 1, kind="feat", on=me, until=When.ENCOUNTER)

    def on_hit(ev: Hit) -> None:
        p = get(ev.power)
        if (
            ev.attacker != me
            or p is None
            or p.cls != "sorcerer"
            or not (Keyword.POISON in p.keywords or Keyword.PSYCHIC in p.keywords)
            or not getattr(getattr(ev, "result", None), "advantage", False)
        ):
            return
        foe, ref = ev.target, ev.power
        c.bonus(
            "damage", step, kind="feat", on=me, until=When.EOT, once=True,
            when=lambda ctx: (
                ctx.get("target") == foe and ctx.get("power") == ref
            ),
        )

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me)


@power("f1161", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1161(c: Cast) -> None:
    """+1, and +2 while bloodied, written as a +1 and a gated **+2** of
    the same kind. Two feat bonuses do not add and the larger wins, so
    the natural-looking pair -- a +1 and a gated +1 -- would come to +1
    forever and look exactly like a working rider.

    The tier ladder doubles on the bloodied leg at every step, which is
    what the printed 2/4 and 3/6 come to.
    """
    me = c.me
    step = 1 + (c.level >= 11) + (c.level >= 21)
    c.bonus("damage", step, kind="feat", on=me, until=When.ENCOUNTER, when=_storm)
    c.bonus(
        "damage", 2 * step, kind="feat", on=me, until=When.ENCOUNTER,
        when=lambda ctx: _storm(ctx) and c.bloodied(me),
    )


@power("f3431", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3431(c: Cast) -> None:
    """Both feat bonuses are ordinary `skill:` modifiers.

    **The training is no longer dropped, and nothing here changed to
    finish it.** The old note was right on both counts and both have been
    answered: there was no training model -- `engine/skills.py` said so in
    its own docstring -- and where training is granted is `chargen` and
    not a body, because the sheet is made before the board is. So the card
    names a skill, `feat.trains` carries it, and `chargen` adds it to
    `Skills.trained` when this feat is taken. #565.

    The +5 and the +2 below **add**: training is a property of the
    creature and the bonus is a modifier, which is exactly why the first
    is not stored in `Mods` -- one key for both and the second would have
    silently replaced the first.

    This row was the only one of the thirteen whose card names its skill
    outright. The other twelve print "training in one skill from the
    <class> skill list", which needs the pool *and* a decision, and they
    keep the marker."""
    c.bonus("skill:intimidate", 2, kind="feat", on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:streetwise", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


# -- declared triggers ------------------------------------------------------


@power("f1163", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1163(c: Cast) -> None:
    """"The first time you become bloodied" is latched here rather than
    with `c.watch(once=True)`: that spends itself on the first `Bloodied`
    of anybody's, and an ally going down is not this sentence.

    A plain "+1 bonus" prints no type word, so no `kind=`.

    The breath weapon half is one `c.ignore_resistance`, and two things
    in it are read rather than written. The type is the build's own
    element, which is what Dragon Soul records and `c.element` reads --
    a build that recorded none leaves this half inert, which is right,
    because the printed condition is the two types matching. The value
    is the heroic 5 that the soul grants, the same number
    `cf:sorcerer-f0s1` lays. p1448 is the breath weapon the card means.
    """
    me = c.me
    element = c.element(on=me)
    if element is not None:
        c.ignore_resistance(
            5, element, on=me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "p1448",
        )
    done: list[bool] = []

    def on_blood(ev: Bloodied) -> None:
        if ev.actor != me or done:
            return
        done.append(True)
        for defence in (FORT, REF, WILL):
            c.bonus(defence, 1, on=me, until=When.ENCOUNTER)

    c.watch(Bloodied, on_blood, until=When.ENCOUNTER, on=me)


@power("f2805", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you slide a target with a sorcerer attack",
       on=Trigger(ForcedMove, _my_sorcerer_slide, "you slide a target"))
def f2805(c: Cast) -> None:
    """`ForcedMove` rather than `Moved`: it is the only one of the two
    that says who did the shoving and with which row. `Moved` carries the
    creature, both ends of the step and `kind_`, and no source at all, so
    "targets **you** slide" could not be asked of it.

    **Both printed sources land, and the second one needed no widening.**
    The card is *"targets you slide with sorcerer attacks or your
    Unfettered Power"*, and Unfettered Power is the wild soul's natural-20
    rider -- written now, in `souls._unfettered`, laid through the
    feature's own `Cast`. So the `ForcedMove` it announces carries
    `power="cf:sorcerer-f0"`, whose `cls` is `sorcerer`, and
    `_my_sorcerer_slide` already answers it. Measured: this row fires
    twice on a natural 20 and once on an ordinary face.

    **`cls`-wide and not narrowed to `p.attack is not None`**, which was
    the tempting tightening and is wrong: a slide printed on a sorcerer
    attack's *hit* is often laid by a **feature** row's `Cast` --
    `p16224`, `p11834` and `cf:sorcerer-elementalist-f2s3` are the three
    -- so testing for a declared attack would drop exactly those.

    **And the dealability holds too, so there is no marker left.** The
    printed prerequisite is `{"ref": "cf:sorcerer-f0s3"}` in an `all`.
    No declared *row* carries that ref -- the wild soul is a **leg** of
    `cf:sorcerer-f0` -- and `chargen.meets` does not want a row: it asks
    whether the hand holds the ref. `#1427` put it there.
    `cf:sorcerer-f0s3` is a `BUILD_OPTIONS["cf:sorcerer-f0"]` value,
    `OPTION_PACT` keys it to the `wild` leg, and `spawn` draws options in
    a **pre-feat** pass whose result is handed to `feats_for`.
    Re-measured through `spawn` over all eight sorcerer legs: the option
    is held on `wild` and on no other, and this row is in the legal pool
    for exactly those sorcerers. #1533, #1535.
    """
    c.penalty(AC, 2, on=c.trigger.target, until=When.EONT)


@power("f2808", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make an attack roll with a daily sorcerer power",
       on=Trigger(AttackRolled, _my_daily_roll, "you roll for a daily"))
def f2808(c: Cast) -> None:
    """`AttackRolled` carries `natural` and is announced before the hit
    and before any damage, so a damage bonus laid here is read by the
    `c.damage` the power's body goes on to call.

    The call is a real `c.choose`, handed two options and nothing else --
    a decider answering it cannot see the die it is guessing at. The
    latch keeps "for one attack roll" honest across a burst, which rolls
    once per target and would otherwise pay on each.
    """
    ev = c.trigger
    now = (ev.power, c.world.round)
    if _CALLED.get(c.me) == now:
        return
    _CALLED[c.me] = now
    pick = c.choose(["even", "odd"], f"{c.ref}: even or odd")
    if pick is None or (ev.natural % 2 == 0) != (pick == "even"):
        return
    foe, ref = ev.target, ev.power
    c.bonus(
        "damage", c.cha_mod, kind="feat", on=c.me, until=When.EOT, once=True,
        when=lambda ctx: ctx.get("target") == foe and ctx.get("power") == ref,
    )


def _untrained_check(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """This creature is about to roll a skill it is not trained in.

    Two narrowings, and the second is the one a reader would miss.
    `Skills.trained` is the training set (#565), so "untrained" is one
    membership test. And `ability_check` announces its declaration under
    `ability:<name>`, which is **not a skill check** -- the cards print
    "ability check or skill check" as two things -- so the prefix is
    checked rather than the key being taken for a skill.
    """
    if ev.actor != me or ev.skill.startswith("ability:"):
        return False
    trained = world.get(me, Skills)
    return trained is None or ev.skill not in trained.trained


@power("f2804", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="before making an untrained skill check",
       on=Trigger(CheckDeclared, _untrained_check,
                  "you are about to make an untrained skill check"))
def f2804(c: Cast) -> None:
    """Call odd or even before an untrained check; a d20 that matches pays a
    feat bonus equal to your Charisma modifier.

    **All three halves of the old reason are gone.** "No training model"
    was answered by `Skills.trained` and the +5 in #565. "No fight turns on
    one" was answered by the tree rolling 13 skills in 63 places (#691).
    And the moment -- the one thing the card is precise about -- is
    `CheckDeclared`, which is announced before the d20 rather than before
    the modifiers. #693.

    **The call is made in ignorance and the payment is made on the result**,
    which is the whole reason this needed an event. `c.choose` is handed two
    options at a moment when no die has been thrown, so a decider cannot
    guess with the face in hand -- the failure that would have made this an
    always-on bonus. The bonus is then laid here and gated on `natural`,
    which `skills.modifier` only puts in its context when a real check is
    resolving.

    `once=True` so the gamble is spent on the check it was called for: the
    gate would otherwise match every later check of the same parity for as
    long as the effect lasts.

    Compare `f2808` above, which calls odd or even on an **attack** roll and
    reads `AttackRolled.natural`. That one is answered after its die is
    down, and it is defensible for the reason its own docstring gives: the
    options handed to the decider are two strings. This card is not written
    that way on purpose -- the issue that filed the gap is explicit that
    choosing with the face available is the thing to avoid."""
    want = c.choose(["even", "odd"], f"{c.ref}: even or odd")
    if want is None:
        return
    even = want == "even"
    skill = c.trigger.skill
    c.bonus(
        f"skill:{skill}", c.cha_mod, kind="feat", on=c.me, until=When.EOT,
        once=True,
        when=lambda ctx: (
            ctx.get("natural") is not None
            and (ctx["natural"] % 2 == 0) is even
        ),
    )


# -- narrative only ---------------------------------------------------------


# -- features named in prose ------------------------------------------------


@power("f1160", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1160(c: Cast) -> None:
    """A pair of skill bonuses per cosmic phase, and initiative in the sun.

    **Written.** `cf:sorcerer-f0s0` holds a phase now that
    `events.ShortRested` gives it a moment to be chosen at, so there is
    finally something to branch on.

    Laid once per phase with a `when=` that reads the phase at the moment
    the check is rolled, rather than re-laid whenever the phase moves. The
    cycle advances when the sorcerer is bloodied, and a bonus re-laid on
    that crossing would have to take the old one off first; a predicate just
    answers whichever phase is current.

    Initiative is the one of the six that is not a skill, and it sits in the
    sun's pair. `c.bonus("initiative", ...)` is read before the d20 --
    `lint.py` guards that key against being laid and never consulted -- so it
    goes in the same loop under its own name.
    """
    from combat_engine.content.features.sorcerer import phase_of

    pairs = {
        "sun": ("initiative", "heal"),
        "moon": ("bluff", "stealth"),
        "stars": ("insight", "perception"),
    }
    for phase, pair in pairs.items():
        for what in pair:
            key = what if what == "initiative" else f"skill:{what}"
            c.bonus(key, 2, kind="feat", on=c.me, until=When.ENCOUNTER,
                    when=lambda ctx, want=phase: phase_of(c) == want)



def _hit_with_card(ref: str):  # noqa: ANN202
    """"When you hit with <that card>" -- this creature's hit, with that row.

    The same question `invoker_b._hit_with` asks; written here rather than
    imported across two feat files, which is the convention in this tree for
    a two-line predicate.
    """
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


@power("f2026", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a target with f2023b",
       on=Trigger(Hit, _hit_with_card("f2023b"), "you hit with that card"))
def f2026(c: Cast) -> None:
    """"f2023b deals fire and radiant damage equal to your Cosmic Power
    damage bonus."

    **Written.** The docstring this replaces said the number was missing
    because `cf:sorcerer-f0s0` was refused in play -- its phase is chosen at
    a rest nothing announced. `events.ShortRested` landed and that feature
    is written, so the amount is there to read.

    Handing a damage line to a named row is an ordinary `Hit` trigger
    against that ref; `invoker_b.f2032` rides this very card the same way.

    **The number is the source's own ladder, not a second one.** Cosmic
    Power is "your Strength modifier, + 2 at 11th level and + 4 at 21st",
    which is exactly `souls.soul_damage` over the ability -- both printed
    sources use that ladder and differ only in which modifier it sits on,
    which is why it is written once there. Reading it rather than repeating
    the three cases is the difference between this staying right when the
    ladder is re-read and quietly drifting from the two rows that already
    use it.

    `dtypes=` is the two types at once, which is what the card means by
    "fire and radiant damage" -- one amount that is both, shrugged off only
    as far as the target resists both, rather than two lines.
    """
    from combat_engine.content.powers.sorcerer.souls import soul_damage

    amount = c.str_mod + soul_damage(c.level)
    if amount <= 0:
        return
    c.flat(amount, dtype=DamageType.FIRE,
           dtypes=(DamageType.FIRE, DamageType.RADIANT),
           on=c.trigger.target)


@power("f3433", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w3643", "w3619"),
       )
def f3433(c: Cast) -> None:
    """Proficiency with two superior light blades, and both count as daggers.

    Proficiency is header data rather than a body: `Power.proficiency` is
    what `chargen` reads when the character is built, and both weapons are
    in the table.

    The casting clause is written now. "Treat them as daggers" is a waiver
    by **slug** -- a dagger is one weapon rather than a group, and both of
    these are already light blades, so a group waiver would say nothing.
    """
    for blade in ("kukri", "katar"):
        c.counts_as("dagger", holding=blade)
# -- the parity the engine cannot hear --------------------------------------


@power("f2806", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, implemented_in=("cf:sorcerer-f0",))
def f2806(c: Cast) -> None:
    """Calls a half of the class feature's d10 before it is rolled and
    replaces the result when the call lands.

    **Written, and not here.** The feature itself is modelled --
    `souls.sorcerer_soul` rolls the die -- and the note below was right
    that the gap was *the moment*: the roll happens while the trait arms
    and is announced to nobody, so a call made from this row could only
    come after the answer was known and would be free every time.

    The convention answers it. This file's own rules say *"a feat that
    names one power writes its clause into that power, gated on
    `c.feat(...)`"*, and inside `souls._rolled_soul` the call is taken
    **before** `c.roll` -- which is the only place that moment exists.
    So `c.on_feature_roll()` named a facility for reaching into the roll
    from outside, and no such facility is wanted.

    `implemented_in=` rather than a body, which is what that convention
    makes this row: a pointer -- and it is also what keeps this row from
    reporting SILENT, since the clause lays no effect of its own for a
    `c.credit` block to stamp. #1532.
    """


@power("f2807", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you roll initiative",
       on=Trigger(InitiativeRolled, about_me, "you roll initiative"))
def f2807(c: Cast) -> None:
    """Call the parity of your initiative d20 and add Charisma if it lands.

    **Written.** The face is recorded now -- `Initiative.natural`, set at
    the three sites that roll a d20 and traded by `swap_initiative`
    alongside the count -- where the event's `rolled` is the finished
    number with the modifier and the level term already in it and cannot
    be read for parity.

    On the event and not in the body, which is what this file's own rule
    about a before-the-fight clause says: `c.initiative` re-splices the
    order, so laying it in the body would move a count that had not been
    rolled against the call yet.

    **The call is fixed rather than offered, and that is faithful.** The
    card has the character choose before the roll, and a d20 is uniform:
    ten faces are even and ten are odd, so neither call is better than
    the other and nothing is lost by making one. An offer would be
    inventing a decision for the AI to get wrong -- see
    `scripts/CLAUDE.md` on what the measurement instruments are for.

    **The opening roll is reached now, and the symbol that said otherwise
    was about the wrong half of the dispatcher.** This was a *trait* --
    `action=NONE` with no `on=`, so its body ran from `_arm_traits()`,
    which `Encounter.start` calls **after** `_roll_initiative()`. That
    ordering is real and `#1500` is still about it. But a row declaring
    `on=Trigger(InitiativeRolled, ...)` is armed by `self.triggers.arm()`,
    which `start` calls **before** the rolls, and `_roll_initiative` sets
    `self.order` provisionally before its emit loop precisely so those
    offers land. Measured: `p10887` -- a warlord row of exactly this
    shape -- fires on the opening roll of a fresh board. So the clause
    does not need the trait ordering moved; it needs to stop being a
    trait. `#1534`.

    **The call being made after the die is still faithful**, by the
    paragraph above: the choice is fixed at even, and a d20 is uniform, so
    there is nothing a late call can exploit. That is what makes the
    trigger shape available at all -- a row whose call mattered could not
    use it.

    `Initiative.natural` is 0 for a creature whose count was *copied*
    rather than rolled, so the gate reads no match there rather than
    even, which is why the parity test asks for a face at all.

    **The second gap -- "and the feat still cannot be DEALT" -- is gone
    too, and it was a stale measurement rather than a wrong one.** That
    note said `chargen.meets` answers the printed
    `{"ref": "cf:sorcerer-f0s3"}` against a dealt hand that never holds
    a leg ref, and listed five other rows waiting on `#235` for the same
    reason. `#1427` had already fixed it by a route the note did not
    know about: the leg refs are `BUILD_OPTIONS` values, `OPTION_PACT`
    keys each to its own leg, and `spawn` draws options in a **pre-feat**
    pass whose result it hands to `feats_for`. So the hand does hold the
    ref -- for the character on that leg and for nobody else, which is
    exactly what `#235` was being asked to guarantee.

    Re-measured through `spawn` over all eight sorcerer legs: the option
    lands on `wild` alone, and this row is in the legal pool for those
    sorcerers. `f2805`, `f469`, `f470` and `f1009` un-marked with it.
    No symbols left. `#1535`."""
    me = c.me
    # Even, by the argument in the docstring: the call is free.
    want_even = True

    def rolled(ev: InitiativeRolled) -> None:
        if ev.actor != me:
            return
        init = c.world.get(me, Initiative)
        face = init.natural if init else 0
        if not face or (face % 2 == 0) != want_even:
            return
        c.initiative(c.cha_mod, on=me)

    rolled(c.trigger)


@power("f1162", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="p1452 makes an enemy reroll its attack",
       on=(
           Trigger(Hit, after_forced_reroll("p1452"),
                   "the forced reroll hit you"),
           Trigger(Miss, after_forced_reroll("p1452"),
                   "the forced reroll missed you"),
       ))
def f1162(c: Cast) -> None:
    """Even reroll: slide the enemy 1. Odd: shift 1. Both after the attack.

    **Hung on the settled outcome rather than on `Rerolled`, because the
    card says "after the attack".** The reroll event fires while the attack
    is still being worked out, so sliding there would move the enemy before
    its own blow landed. `Hit` and `Miss` are the moment the card means, and
    the face is still readable off the result.

    `result.parity` rather than `natural % 2`: a row elsewhere can dictate
    that a roll counts as odd, and reading the die by hand ignores it. #496.
    """
    result = getattr(c.trigger, "result", None)
    foe = getattr(c.trigger, "attacker", None)
    if result is None or foe is None:
        return
    if result.parity == "even":
        c.slide(1, on=foe)
    else:
        c.shift(1)
