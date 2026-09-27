"""Battlemind feats.

Almost every row is a rider on one of the six class features in
`powers/battlemind/level_0.py`, and all six are named by ref -- `p10438`,
`p10439`, `p10440`, `p10441`, `p11155`, `p12418` -- so the triggers are
declared rather than guessed.

Three things about those six shape this whole file.

**`PowerUsed` is announced before the body runs.** A rider that only adds
distance -- "move 2 additional squares", "shift 2 instead of 1" -- is
written there anyway, because the two moves come to the printed total and
the destination is the decider's either way. A rider that has to see where
the caster *ended up* -- "mark each enemy adjacent to you at the end of the
move" -- watches `PowerResolved`, which is emitted after the body.

**`p10440`'s target is not its victim.** It is a reaction to a
`DamageApplied`, and that event carries neither `attacker` nor `actor`, so
`Triggers._at` cannot aim it and `_auto_targets` picks whichever adjacent
enemy it likes. `PowerUsed.targets` is therefore the wrong creature roughly
as often as the right one. The two riders that need the victim watch the
damage `p10440` itself deals instead, which carries the ref in `detail`.

**Nothing says what set a triggered power off.** `PowerUsed` names the
actor, the ref and the targets and not the event being answered, so "the
triggering enemy" of `p10439` -- which targets only the caster -- cannot be
recovered. That is `PowerUsed.trigger`, and it blocks two rows.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    DamageApplied,
    DamageType,
    InitiativeRolled,
    PowerUsed,
    Trigger,
    When,
    about_me,
    get,
    power,
)
from combat_engine.engine.events import PowerResolved

DEFENCES = (AC, FORT, REF, WILL)

DEMAND = "p10438"
BLURRED_STEP = "p10439"
MIND_SPIKE = "p10440"
SPEED_OF_THOUGHT = "p10441"
BATTLE_RESILIENCE = "p11155"
WILD_FOCUS = "p12418"

#: `PowerUsed` does not carry the event the power was answering, so "the
#: triggering enemy" of a self-targeted reaction is unrecoverable.
TRIGGERING = ("PowerUsed.trigger",)
#: Nothing lets a rider replace the triggering power's own printed effect:
#: `PowerUsed` is a plain `Event`, so `c.cancel()` cannot stop it.
INSTEAD = ("c.instead_of()",)
#: A class feature named in prose with no ref.
FEATURE = ("c.class_feature()",)
#: Spending power points emits a `Note` and nothing a trigger can watch.
POINTS = ("c.on_points_spent()",)


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _mind_spike_damage(world, me: int, ev: DamageApplied) -> bool:  # noqa: ANN001
    return ev.source == me and ev.detail == MIND_SPIKE and ev.amount > 0


def _battlemind_power(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and p.cls == "battlemind"


# -- speed of thought -------------------------------------------------------


@power("f2270", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p10441",
       on=Trigger(PowerUsed, _used(SPEED_OF_THOUGHT), "you use p10441"))
def f2270(c: Cast) -> None:
    """Two extra squares. `PowerUsed` fires before the body, so these are
    walked first and the power's own 3 + Charisma follows -- the same
    ground covered, in two steps rather than one, and the decider chooses
    where in both cases."""
    c.move(2, who=c.me)


@power("f3285", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p10441",
       on=Trigger(PowerUsed, _used(SPEED_OF_THOUGHT), "you use p10441"))
def f3285(c: Cast) -> None:
    """Dexterity in place of Charisma, written as the difference: the power
    walks 3 + Charisma out of its own body and nothing reaches in to change
    the number. A Dexterity *lower* than the Charisma cannot shorten the
    move, so the row pays only when the swap is the improvement it is taken
    for."""
    extra = c.dex_mod - c.cha_mod
    if extra > 0:
        c.move(extra, who=c.me)


@power("f3289", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p10441",
       on=Trigger(PowerUsed, _used(SPEED_OF_THOUGHT), "you use p10441"))
def f3289(c: Cast) -> None:
    """"Each ally adjacent to you" is read before the move, which is where
    `PowerUsed` puts us and also where the allies are standing when the
    power is declared."""
    me = c.me
    for friend in c.within(1, of=me, side="ally"):
        if friend != me:
            c.shift(1, who=friend)


@power("f2787", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you finish the move from p10441",
       on=Trigger(PowerResolved, _used(SPEED_OF_THOUGHT), "you use p10441"))
def f2787(c: Cast) -> None:
    """"Adjacent to you at the end of the move" is the one clause in this
    file that `PowerUsed` gets wrong, so it watches `PowerResolved` -- the
    event emitted after the body, where the battlemind is standing
    somewhere new."""
    for foe in c.within(1, of=c.me, side="enemy"):
        c.mark(on=foe, until=When.EOTNT)


@power("f3314", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you roll initiative, or you use p10441",
       on=[
           Trigger(InitiativeRolled, about_me, "you roll initiative"),
           Trigger(PowerUsed, _used(SPEED_OF_THOUGHT), "you use p10441"),
       ])
def f3314(c: Cast) -> None:
    """Two printed clauses on two different triggers, so both are declared
    and the body asks which one it is answering. At-will rather than
    once-an-encounter for that reason: spent on the initiative roll, the
    row would never be offered for the second clause at all.

    `c.bonus` cannot say the initiative half: the component is read before
    the d20 and this row is by definition answering a roll that has already
    happened. `c.initiative` moves the creature in the order instead, by
    the difference between the two modifiers."""
    if isinstance(c.trigger, InitiativeRolled):
        step = c.cha_mod - c.dex_mod
        if step:
            c.initiative(step, on=c.me)
        return
    c.bonus("speed", 2, on=c.me, until=When.EONT)


# -- blurred step -----------------------------------------------------------


@power("f3279", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p10439",
       on=Trigger(PowerUsed, _used(BLURRED_STEP), "you use p10439"))
def f3279(c: Cast) -> None:
    """"2 squares instead of 1" comes to two squares of shifting either
    way, so the extra one is taken here and the power's own follows."""
    c.shift(1)


@power("f3286", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p10439",
       on=Trigger(PowerUsed, _used(BLURRED_STEP), "you use p10439"),
       dropped=INSTEAD)
def f3286(c: Cast) -> None:
    """The teleport lands; "instead of shifting" does not. `PowerUsed` is a
    plain `Event` rather than a `Decision`, so nothing suppresses the
    square `p10439` shifts on its own -- the battlemind gets both."""
    if c.points() >= 1:
        c.teleport(max(1, c.int_mod))


@power("f2271", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=TRIGGERING)
def f2271(c: Cast) -> None:
    """Combat advantage against the enemy whose shift set `p10439` off, if
    the shift ends beside it. `p10439` targets only the caster and
    `PowerUsed` does not carry the event it is answering, so there is no
    way to name that enemy from out here."""


@power("f3290", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=TRIGGERING + INSTEAD)
def f3290(c: Cast) -> None:
    """Teleport beside the triggering enemy rather than shifting. Both
    halves are missing: the enemy for the same reason f2271's is, and the
    replacement of the printed shift for the same reason f3286's is."""


# -- mind spike -------------------------------------------------------------


@power("f2605", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="p10440 damages a creature",
       on=Trigger(DamageApplied, _mind_spike_damage, "p10440 lands"))
def f2605(c: Cast) -> None:
    """Watches the damage rather than the use: `p10440` answers a
    `DamageApplied`, which carries no `attacker` and no `actor`, so the
    dispatcher cannot aim it and its declared target is whichever adjacent
    enemy `_auto_targets` picked. The creature it actually hurt is the one
    on the damage this row is answering."""
    c.slide(1, on=c.trigger.target)


@power("f2722", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="p10440 damages a creature",
       on=Trigger(DamageApplied, _mind_spike_damage, "p10440 lands"))
def f2722(c: Cast) -> None:
    """Same reading of the victim as f2605. "The next saving throw it
    makes" is `once=True`; the window is the duration."""
    c.penalty("save", 2, on=c.trigger.target, until=When.SONT, once=True)


@power("f3280", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p10440",
       on=Trigger(PowerUsed, _used(MIND_SPIKE), "you use p10440"))
def f3280(c: Cast) -> None:
    """No victim to find -- the temporary hit points are the caster's."""
    c.temp_hp(max(0, c.con_mod), on=c.me)


@power("f3170", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.lend_augment(ref_or_class, clause)",))
def f3170(c: Cast) -> None:
    """Hands `p10440` an Augment 1 clause it does not print. An augment is
    a branch inside the row's own body reading `augment(c)`; a feat cannot
    add one from outside, which is the gap the five psionic rows printing
    "you gain the following augmentation" already name."""


# -- battle resilience ------------------------------------------------------


@power("f2591", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p11155",
       on=Trigger(PowerUsed, _used(BATTLE_RESILIENCE), "you use p11155"))
def f2591(c: Cast) -> None:
    """"While it is in effect" is the resistance's own duration, which
    `p11155` lays until the end of its user's next turn. No type word is
    printed in front of "bonus", so it is untyped."""
    for d in DEFENCES:
        c.bonus(d, 2, on=c.me, until=When.EONT)


@power("f3296", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p11155",
       on=Trigger(PowerUsed, _used(BATTLE_RESILIENCE), "you use p11155"))
def f3296(c: Cast) -> None:
    """"Ignore forced movement" is `c.immovable`, which is the whole of it:
    push, pull and slide all read the same key."""
    c.immovable(on=c.me, until=When.EONT)


@power("f3316", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("dsl.use(augment=)",))
def f3316(c: Cast) -> None:
    """Pays out when `p10438` is augmented, and `p10438` cannot be: its
    only printed augment widens the target line, targeting happens before
    the body runs, and its own docstring says so. `p10438:augment1` is
    already on that list, so the trigger this row wants can never be
    true."""


# -- wild focus, forced movement, and the marked --------------------------


@power("f3219", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p12418",
       on=Trigger(PowerUsed, _used(WILD_FOCUS), "you use p12418"))
def f3219(c: Cast) -> None:
    """`p12418` picks its target before the body runs, so `ev.targets` is
    trustworthy here in a way `p10440`'s is not -- this one is aimed by
    `Triggers._at` off the `TurnStart` it answers."""
    for foe in c.trigger.targets:
        c.pull(2, on=foe)


@power("f3241", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3241(c: Cast) -> None:
    """`c.forces` is the key the shove reads off whoever is doing it, and
    its gate is handed the power's ref -- so "your battlemind powers" is
    the class off that ref's header."""
    c.forces(1, on=c.me, until=When.ENCOUNTER, when=_battlemind_power)


@power("f3281", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p6189",
       on=Trigger(PowerUsed, _used("p6189"), "you use p6189"))
def f3281(c: Cast) -> None:
    """The racial power is a ref, so the trigger is declared even though no
    row carries that id yet -- it fires the day one does."""
    if c.points() < 1:
        return
    for foe in c.enemies():
        if c.marked(on=foe):
            c.flat(max(0, c.str_mod), dtype=DamageType.PSYCHIC, on=foe)


@power("f3400", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use f3395b",
       on=Trigger(PowerUsed, _used("f3395b"), "you use f3395b"))
def f3400(c: Cast) -> None:
    """Rides the card another feat grants, which is a ref like any other.
    Same shape as f3281."""
    for foe in c.enemies():
        if c.marked(on=foe):
            c.flat(max(0, c.con_mod), dtype=DamageType.PSYCHIC, on=foe)


# -- the ones with nothing to hang on --------------------------------------


@power("f3299", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.effects_on()",))
def f3299(c: Cast) -> None:
    """Fires when an attack misses *because of* a named racial power's
    defence bonus. `Miss` carries no totals and nothing reads back which
    standing effects a defence was built from, so "the bonus made the
    difference" cannot be asked."""


@power("f3304", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3304(c: Cast) -> None:
    """Three riders, one per aspect of a racial feature named in prose with
    no ref and no row. Which aspect is current is the question, and nothing
    answers it."""


@power("f3322", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, todo=POINTS + FEATURE)
def f3322(c: Cast) -> None:
    """Two gaps. Spending power points emits a `Note` and no event, so
    "the first time you drop to 0" has nothing to watch; and the range is
    a racial telepathy named in prose, which is not a number anything
    carries."""
