"""Ardent feats.

Two thirds of the list reads "within the radius of your Ardent Mantle",
which is `cf:ardent-f0` -- a close burst 5 the class page prints in full,
and the only mantle the compendium gives text for. So the radius is five
squares here, measured when the row fires rather than when the mantle was
armed: an ally who walked into range since the fight started is inside the
sentence these feats print even though the mantle's own snapshot missed
them.

The rest ride the class's four level-0 rows -- `p10272`, `p10273`,
`p11060`, `p12931` -- all of which are refs, so the triggers are declared.
`p10273` is used twice an encounter, so its riders are at-will: spent once,
they would sit out the second use.

Two rows change a number the mantle grants to a skill and nothing else.
Those are `out_of_combat=True` -- decided, not forgotten.
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
    Bloodied,
    Cast,
    Condition,
    PowerUsed,
    SavingThrow,
    SurgeSpent,
    Trigger,
    TurnStart,
    When,
    about_me,
    get,
    power,
)
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import distance_between, team

DEFENCES = (AC, FORT, REF, WILL)

#: The radius of the one mantle the class page prints, from `cf:ardent-f0`.
MANTLE = 5

ARDENT_SURGE = "p10273"
ARDENT_ERUPTION = "p12931"
BLOODIED_ADVANTAGE = "p11060"

#: Second wind is an action rather than a row and announces nothing of
#: its own -- `SurgeSpent` cannot tell it from any other surge.
SECOND_WIND = ("c.on_second_wind()",)
#: A feature named in prose with no ref.
FEATURE = ("c.class_feature()",)
#: Spending power points emits a `Note` and no event.
POINTS = ("c.on_points_spent()",)

#: The conditions the printed line of f3306 names.
LOCKED = (Condition.DAZED, Condition.DOMINATED, Condition.STUNNED)


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _early_turn_in_mantle(world, me: int, ev: TurnStart) -> bool:  # noqa: ANN001
    """My turn or a friend's, in the surprise round or the first round."""
    return (
        ev.round <= 1
        and team(world, ev.actor) is team(world, me)
        and distance_between(world, me, ev.actor) <= MANTLE
    )


def _my_melee(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind == "melee"


# -- the mantle's own radius ------------------------------------------------


@power("f2144", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you or an ally in the mantle starts a turn in round 1",
       on=Trigger(TurnStart, _early_turn_in_mantle, "an early turn nearby"))
def f2144(c: Cast) -> None:
    """"Who starts his or her turn within the radius" is asked per turn,
    so this is a trigger rather than a standing modifier. A surprise round
    and the first round are both round 1 as the encounter counts."""
    c.bonus("speed", 2, on=c.trigger.actor, until=When.EOT)


@power("f3288", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, dropped=POINTS)
def f3288(c: Cast) -> None:
    """The initiative half only. `c.bonus` cannot say it -- the component
    is read before the d20 -- so `c.initiative` moves each of them in the
    order instead, which is that method's whole reason for existing.

    The second clause pays out the first time the ardent's pool empties,
    and spending power points emits a `Note` and nothing a trigger can
    watch."""
    for who in c.within(MANTLE, of=c.me, side="ally"):
        c.initiative(2, on=who)


@power("f3301", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you make a saving throw",
       on=Trigger(SavingThrow, about_me, "you make a saving throw"))
def f3301(c: Cast) -> None:
    """`"save"` is the key `durations.save` totals off the roller, so the
    bonus is an ordinary modifier rather than a one-off on this roll."""
    me = c.me
    for friend in c.within(MANTLE, of=me, side="ally"):
        if friend != me:
            c.bonus("save", 2, on=friend, until=When.SONT)


@power("f2141", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, about_me, "you spend a healing surge"))
def f2141(c: Cast) -> None:
    """"One ally" is a choice, and so is which of the two things it gets --
    the second asked of the ally, because it is the ally's benefit."""
    me = c.me
    near = [a for a in c.within(MANTLE, of=me, side="ally") if a != me]
    if not near:
        return
    who = c.choose(near, "an ally in the mantle")
    if who is None:
        return
    if c.may("gain temporary hit points", who=who):
        c.temp_hp(5, on=who)
    else:
        c.save(on=who)


@power("f3399", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use f3395b",
       on=Trigger(PowerUsed, _used("f3395b"), "you use f3395b"))
def f3399(c: Cast) -> None:
    """Rides the card another feat grants. No type word is printed before
    "bonus", so it is untyped."""
    for friend in c.within(MANTLE, of=c.me, side="ally"):
        for d in DEFENCES:
            c.bonus(d, 2, on=friend, until=When.SONT)


@power("f2142", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2142(c: Cast) -> None:
    """Raises the mantle's Insight and Perception bonus from a flat +2 to
    the ardent's Wisdom modifier. The whole benefit is a skill number, so
    the row is deliberately inert rather than unwritten -- and laying a
    second bonus here would add to the mantle's instead of replacing it,
    which is the one thing the sentence does not say."""


@power("f2593", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2593(c: Cast) -> None:
    """The same shape as f2142 for Diplomacy and Intimidate, and for a
    mantle whose text is not on the class page at all."""


@power("f3321", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.widen_area()",))
def f3321(c: Cast) -> None:
    """Grows the mantle by 2 squares while the pool is empty. The radius is
    `cf:ardent-f0`'s close burst 5, which is header data read before that
    row's body runs -- the same gap f1010 and f1134 name."""


@power("f3173", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, todo=("When.CONSCIOUS",))
def f3173(c: Cast) -> None:
    """Allies in the mantle stay up at 0 hit points until their first death
    save. Nothing holds a creature conscious below zero: dropping applies
    `unconscious` outright and there is no duration that says otherwise."""


# -- riders on the class's own rows ----------------------------------------


@power("f2143", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p10273",
       on=Trigger(PowerUsed, _used(ARDENT_SURGE), "you use p10273"))
def f2143(c: Cast) -> None:
    """`p10273` picks its target before its body runs, so `ev.targets` is
    the ally being helped. The defence half is the only half this mantle
    prints, and the power's own bonus is untyped -- so a second untyped
    +1 on the same creature comes to the +2 the feat means."""
    for who in c.trigger.targets:
        for d in DEFENCES:
            c.bonus(d, 1, on=who, until=When.EONT)


@power("f3302", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p10273 while bloodied",
       on=Trigger(PowerResolved, _used(ARDENT_SURGE), "you use p10273"))
def f3302(c: Cast) -> None:
    """`PowerResolved` rather than `PowerUsed`: the extra hit points are
    added to a heal that has to have happened, and `p10273` only heals if
    the ally agrees to spend the surge."""
    if not c.bloodied(on=c.me):
        return
    for who in c.trigger.targets:
        if c.wounded(on=who):
            c.heal(c.roll("1d6"), on=who)


@power("f3306", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p10273",
       on=Trigger(PowerResolved, _used(ARDENT_SURGE), "you use p10273"))
def f3306(c: Cast) -> None:
    """`c.save(against=)` picks an effect by label fragment and a
    condition effect's label is the ref that laid it, so the one the
    printed line names is found by its conditions and then saved against
    by that label."""
    for who in c.trigger.targets:
        for effect in c.world.effects.of(who):
            if effect.when is not When.SAVE_ENDS:
                continue
            if any(cond in effect.conditions for cond in LOCKED):
                c.save(on=who, against=effect.label)
                break


@power("f3283", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p12931",
       on=Trigger(PowerUsed, _used(ARDENT_ERUPTION), "you use p12931"))
def f3283(c: Cast) -> None:
    """`p12931`'s own bonus is untyped and lasts to the start of its next
    turn, so the extra +2 is laid the same way on the same allies."""
    me = c.me
    for who in c.trigger.targets:
        if who != me:
            c.bonus("damage", 2, on=who, until=When.SONT)


@power("f3305", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET)
def f3305(c: Cast) -> None:
    """"Granting combat advantage **from your p11060**" is the effect that
    row laid, not combat advantage in general -- `c.suffering` finds
    exactly the creatures carrying it, asked per damage roll because the
    effect ends while the fight goes on."""
    me = c.me
    for friend in c.allies():
        if friend == me:
            continue
        c.bonus(
            "damage", 2, on=friend, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") in c.suffering(BLOODIED_ADVANTAGE),
        )


@power("f3315", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p11052",
       on=Trigger(PowerUsed, _used("p11052"), "you use p11052"))
def f3315(c: Cast) -> None:
    """The racial power is a ref, so the trigger is declared even though no
    row carries that id yet. "Allies within the radius" is narrower than
    the whole side, so the grant is laid once per ally by eid rather than
    once with `to="allies"`."""
    me = c.me
    near = [a for a in c.within(MANTLE, of=me, side="ally") if a != me]
    for foe in c.trigger.targets:
        for friend in near:
            c.grants_advantage(on=foe, until=When.EONT, to=friend)


@power("f3278", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you are bloodied",
       on=Trigger(Bloodied, about_me, "you are bloodied"))
def f3278(c: Cast) -> None:
    """"The first time during an encounter" is the once-an-encounter usage.
    The damage context carries the ref, so "your melee attacks" is that
    row's own reach."""
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EONT, when=_my_melee)


# -- the ones with nothing to hang on --------------------------------------


@power("f2786", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       todo=("c.on_racial_power()", "c.zone(side=)"))
def f2786(c: Cast) -> None:
    """Two gaps. The power it rides is named in prose with no ref, and the
    effect is difficult terrain that only the targets suffer -- a zone's
    rough going is the ground's property and has no side."""


@power("f3115", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, todo=SECOND_WIND + FEATURE)
def f3115(c: Cast) -> None:
    """Temporary hit points when an ally under a racial trait takes a
    second wind. Neither half is sayable: second wind is an action that
    announces only a `SurgeSpent`, and the trait naming who benefits is
    prose with no ref."""


@power("f3328", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, todo=SECOND_WIND)
def f3328(c: Cast) -> None:
    """Your own second wind hands an ally theirs. `c.second_wind` exists
    and would do the ally's half; nothing announces that you took yours,
    so there is no moment to hang it on."""
