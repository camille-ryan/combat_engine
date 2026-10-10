"""General feats, continued: mostly the channelled divine ones.

Two shapes dominate this batch and neither appears in `general.py`.

**The granted pair.** A feat whose entire printed benefit is "you can
invoke the power of your deity to use X" is a trait that hands over the
card beside it. The parent does nothing else and should not; the card is
the row. Both refs are in the brief and both are written.

**The channel divinity budget.** Every one of those cards prints "you can
use only one channel divinity power per encounter", which is not a usage
limit on the row -- it is a limit shared across every such row a
character has, from any source. `group=CHANNEL_DIVINITY` is what says so,
and `dsl._group_spent` enforces it. Writing `uses=1` instead would let a
character with three of these use all three.

The prerequisites are all a deity the engine cannot name, so every one of
these rows is unreachable by `chargen.meets` today. That is not a reason
to leave them unwritten: the gate is a column and the day a deity exists
they all work.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    Ability,
    ActionType,
    Attack,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageType,
    Defences,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Ranged,
    SavingThrow,
    SecondWind,
    SkillCheck,
    TotalDefence,
    Trigger,
    When,
    about_me,
    get,
    power,
)
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import distance_between, team

DIVINE = [Keyword.DIVINE]
DIVINE_HEAL = [Keyword.DIVINE, Keyword.HEALING]


def _granted(ref: str, card: str):  # noqa: ANN202
    """The parent half of a feat that grants a card.

    Sixteen of them in this batch, identical but for two ids, and a
    hand-written copy each is sixteen chances to point at the wrong card.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
        reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


# -- the channelled cards ---------------------------------------------------


def _ally_saved(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.saved and (ev.actor == me or team(world, ev.actor) == team(world, me))


def _ally_failed(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return not ev.saved and team(world, ev.actor) == team(world, me)


def _i_failed(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and not ev.saved


def _ally_dropped(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return team(world, ev.actor) == team(world, me) and ev.actor != me


def _ally_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.critical
        and team(world, ev.target) == team(world, me)
        and distance_between(world, me, ev.target) <= 10
    )


def _ally_rolled(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.attacker != me
        and team(world, ev.attacker) == team(world, me)
        and distance_between(world, me, ev.attacker) <= 10
    )


def _ally_checked(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.actor != me
        and team(world, ev.actor) == team(world, me)
        and distance_between(world, me, ev.actor) <= 10
    )


def _radiant_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.attacker == me and p is not None and Keyword.RADIANT in p.keywords


_granted("f595", "f595b")


@power("f595b", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
    reach=Ranged(10), target=ONE_ALLY, keywords=DIVINE, group=CHANNEL_DIVINITY,
    trigger="you or an ally within range succeeds on a saving throw",
    on=Trigger(SavingThrow, _ally_saved, "an ally makes a saving throw"))
def f595b(c: Cast) -> None:
    """A No Action, so it costs nothing and is declared `NONE` rather than
    `FREE` -- the budget it draws on is the channel divinity group."""
    c.bonus("save", 4, on=c.target, until=When.EONT, kind="power")


_granted("f597", "f597b")


@power("f597b", level=1, cls="", usage=ENCOUNTER, action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10), target=ONE_ALLY, keywords=DIVINE_HEAL,
    group=CHANNEL_DIVINITY,
    trigger="an ally drops to 0 hit points or fewer",
    on=Trigger(Dropped, _ally_dropped, "an ally drops"))
def f597b(c: Cast) -> None:
    """"Can immediately spend a healing surge" -- theirs, not yours."""
    c.surge(on=c.target)


_granted("f600", "f600b")


@power("f600b", level=1, cls="", usage=ENCOUNTER, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(10), target=ONE_ALLY, keywords=DIVINE,
    group=CHANNEL_DIVINITY,
    trigger="an ally within 10 squares fails a saving throw",
    on=Trigger(SavingThrow, _ally_failed, "an ally fails a saving throw"))
def f600b(c: Cast) -> None:
    """An interrupt rather than the printed No Action: the reroll has to
    reach the event before it is acted on, and `SavingThrow` is announced
    first for exactly that."""
    c.reroll_save(bonus=4)


_granted("f605", "f605b")


@power("f605b", level=1, cls="", usage=ENCOUNTER, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL, target=NO_TARGET, keywords=DIVINE, group=CHANNEL_DIVINITY,
    trigger="you fail a saving throw",
    on=Trigger(SavingThrow, _i_failed, "you fail a saving throw"))
def f605b(c: Cast) -> None:
    c.reroll_save()


_granted("f606", "f606b")


@power("f606b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY)
def f606b(c: Cast) -> None:
    c.bonus("speed", 2, on=c.me, until=When.EONT, kind="power")
    c.ignores_difficult(on=c.me, until=When.EONT)


_granted("f611", "f611b")


@power("f611b", level=1, cls="", usage=ENCOUNTER, action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(10), target=ONE_ALLY, keywords=DIVINE_HEAL,
    group=CHANNEL_DIVINITY,
    trigger="an ally in the burst is damaged by a critical hit",
    on=Trigger(Hit, _ally_crit, "an ally is critically hit"))
def f611b(c: Cast) -> None:
    """The surge is *given* and then spent, so an ally with none left still
    heals -- which is the printed line and the reason it costs you one."""
    c.regain_surge(1, on=c.target)
    c.surge(on=c.target)
    c.spend_surge(on=c.me)


_granted("f623", "f623b")


@power("f623b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(10), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f623b(c: Cast) -> None:
    c.save(on=c.target)


_granted("f629", "f629b")


@power("f629b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=ONE_ALLY, keywords=DIVINE,
       group=CHANNEL_DIVINITY)
def f629b(c: Cast) -> None:
    """**Re-aimed off `c.bonus('skill:any')`, which does not need to
    exist.** `engine/skills.py` reads a bare `skill` key beside
    `skill:<name>` and says so outright: "a blanket `skill` modifier
    applies to every check". That is exactly a bonus the card declines
    to pin to one skill.

    The printed "or" is a choice made when the bonus is spent and
    nothing carries that, so both one-shots are laid: an ally who both
    attacks and rolls a skill before the end of my next turn takes it
    twice. Narrow enough to prefer to dropping the clause, because the
    engine rolls a skill check perhaps once a fight and an attack roll
    every round.
    """
    c.bonus("attack", 2, on=c.target, until=When.EONT, kind="power", once=True)
    c.bonus("skill", 2, on=c.target, until=When.EONT, kind="power", once=True)


_granted("f630", "f630b")


@power("f630b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY)
def f630b(c: Cast) -> None:
    """Gated on the *target* being bloodied, which the attack context
    carries -- the damage context would not."""
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.EONT, kind="power",
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )


_granted("f618", "f618b")


@power("f618b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       keywords=[Keyword.DIVINE, Keyword.RADIANT], group=CHANNEL_DIVINITY,
       trigger="you hit an enemy with a radiant power",
       on=Trigger(Hit, _radiant_hit, "you hit with a radiant power"))
def f618b(c: Cast) -> None:
    """"All targets hit by the power" -- the trigger names one, so the
    extra lands on that one. A `Hit` is announced per target, so a burst
    that hits three pays three times, which is the printed line."""
    c.flat(c.roll("1d10"), dtype=DamageType.RADIANT, on=c.trigger.target)


_granted("f620", "f620b")


@power("f620b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
       dropped=("c.crit_dice_on_hit()",))
def f620b(c: Cast) -> None:
    """The critical half: a crit's extra damage is maximised. The other
    half -- rolling the critical dice as extra damage on an ordinary hit
    -- has no verb; nothing turns a normal hit into a partial crit."""
    c.maximise(on=c.me, until=When.EONT, critical=True)


_granted("f614", "f614b")


@power("f614b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBlast(5), target=EACH_ENEMY,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
       group=CHANNEL_DIVINITY,
       attack=Attack(Ability.WIS, vs=WILL))
def f614b(c: Cast) -> None:
    """Undead only, so the blast is declared over every enemy and the row
    passes over anything else. `c.is_kind` reads the type line.

    The attack is "highest mental ability", which the header cannot say --
    it holds one ability. Wisdom is declared, and `plus=` makes up the
    difference when Intelligence or Charisma is the better of the three.
    """
    if not c.is_kind("undead"):
        return
    best = max(c.wis_, c.int_, c.cha_)
    if c.strike(plus=best - c.wis_).hit:
        c.damage("1d12", c.wis_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage("1d12", c.wis_mod, dtype=DamageType.RADIANT)


_granted("f635", "f635b")


@power("f635b", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=CloseBurst(10), target=ONE_ALLY, keywords=DIVINE,
    group=CHANNEL_DIVINITY, out_of_combat=True)
def f635b(c: Cast) -> None:
    """Rerolls a social skill check. Nothing in a fight turns on one."""


_granted("f608", "f608b")


@power("f608b", level=1, cls="", usage=ENCOUNTER, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(10), target=ONE_ALLY, keywords=DIVINE,
    group=CHANNEL_DIVINITY,
    trigger="an ally in the burst makes an attack roll or skill check",
    on=(Trigger(AttackRolled, _ally_rolled, "an ally makes an attack roll"),
        Trigger(SkillCheck, _ally_checked, "an ally makes a skill check")))
def f608b(c: Cast) -> None:
    """Rerolls an **ally's** attack roll or skill check.

    **`c.reroll_attack(on=)` was the wrong symbol and the row was
    blocked on nothing.** It reads the roll off `c.trigger` and never
    asks whose it is -- the live `AttackResult` rides on `AttackRolled`
    as a plain attribute for exactly this -- so the ally's roll is
    reachable the moment the row is declared against the ally's event.
    An immediate interrupt lands in `Window.BEFORE`, which for both
    events is before the outcome is settled: `resolve.attack`
    recomputes hit and crit from `result` after the window, and
    `skills.check` totals the modifiers in its resolve callback.

    `keep="new"`, the default, is the printed "must keep the second
    result, even if it is worse".
    """
    if not c.reroll_attack():
        c.reroll_check()


_granted("f610", "f610b")


@power("f610b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY)
def f610b(c: Cast) -> None:
    """"An attack roll made with a magic item power" -- an item's rows
    carry `cls="item"`, which the attack context's `power` reaches."""
    c.bonus(
        "attack", 2, on=c.me, until=When.EONT, kind="power", once=True,
        when=lambda ctx: getattr(get(ctx.get("power", "")), "cls", "") == "item",
    )


_granted("f631", "f631b")


@power("f631b", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
    todo=("c.advantage_on_roll()",))
def f631b(c: Cast) -> None:
    """"Roll d20 twice and use whichever you prefer", banked for a *later*
    roll of the character's choosing. `c.reroll_attack(keep="best")` is the
    same idea applied to the roll that just happened; nothing holds it."""


# -- the standalone ones ----------------------------------------------------


@power("f507", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
    reach=PERSONAL, target=SELF,
    trigger="you use your second wind or take the total defence action",
    on=[Trigger(SecondWind, about_me, "you use your second wind"),
        Trigger(TotalDefence, about_me, "you take the total defence action")])
def f507(c: Cast) -> None:
    """Both actions, as two declared triggers -- `Power.on` takes a sequence
    and the saving throw is the same either way. Total defence announces
    itself now, so the dropped half is written."""
    c.save(on=c.me)


@power("f509", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, todo=("c.allies_in_area()",))
def f509(c: Cast) -> None:
    """+1 to attack with a burst or blast implement power **if an ally is
    inside it**. The attack context carries the target and not the area,
    so there is nothing to ask who else is standing in it."""


@power("f511", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, out_of_combat=True)
def f511(c: Cast) -> None:
    """First aid as a minor, and a Heal check bonus. Stabilising is not
    modelled and a skill bonus is not a fight."""


@power("f517", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
    reach=PERSONAL, target=NO_TARGET,
    trigger="you hit a target that has fire resistance with a fire power",
    on=Trigger(Hit, lambda w, me, ev: (
        ev.attacker == me
        and (p := get(ev.power)) is not None
        and Keyword.FIRE in p.keywords
        and (d := w.get(ev.target, Defences)) is not None
        and d.resist.get(DamageType.FIRE, 0) > 0
    ), "you hit a fire-resistant target with a fire power"))
def f517(c: Cast) -> None:
    """Five extra fire damage from **any** fire power against that one
    target, until the end of your next turn. Gated on the damage type and
    on who is being hit, both of which the damage context carries."""
    victim = c.trigger.target
    c.bonus(
        "damage", 5, on=c.me, until=When.EONT,
        when=lambda ctx: (
            ctx.get("target") == victim and ctx.get("dtype") is DamageType.FIRE
        ),
    )


@power("f519", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
    reach=PERSONAL, target=NO_TARGET,
    trigger="you hit with a lightning attack power",
    on=Trigger(Hit, lambda w, me, ev: (
        ev.attacker == me
        and (p := get(ev.power)) is not None
        and Keyword.LIGHTNING in p.keywords
    ), "you hit with a lightning power"))
def f519(c: Cast) -> None:
    """A plain "+1 bonus", so untyped -- the card names no type."""
    c.bonus(
        "attack", 1, on=c.me, until=When.EONT,
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.THUNDER in p.keywords
        ),
    )


@power("f521", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
    reach=PERSONAL, target=NO_TARGET,
    trigger="you hit with a thunder attack power",
    on=Trigger(Hit, lambda w, me, ev: (
        ev.attacker == me
        and (p := get(ev.power)) is not None
        and Keyword.THUNDER in p.keywords
    ), "you hit with a thunder power"))
def f521(c: Cast) -> None:
    """The 11th and 21st steps are out of scope; the project stops at 10."""
    c.bonus("damage", 1, on=c.me, until=When.EONT)


@power("f534", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, out_of_combat=True)
def f534(c: Cast) -> None:
    """Skill checks made while performing a ritual."""


@power("f603", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF)
def f603(c: Cast) -> None:
    """A cumulative bonus on each melee basic attack `p3322` grants.

    Counted on `PowerResolved` rather than `PowerUsed`, which is the
    printed "future attack rolls": a use is announced before its own
    roll, so counting there would pay the bonus to the swing that earned
    it. Each step is its own untyped +1 -- untyped bonuses stack, which
    is what "cumulative" means -- and the cap is the counter.

    "Resets at the end of the encounter" is the duration; "or if you are
    rendered unconscious" is `c.end_effect` on each step laid so far,
    which is why they are kept rather than laid and forgotten.
    """
    steps: list[Any] = []

    def swung(ev: Any) -> None:
        if ev.actor != c.me or ev.granted_via != "p3322" or len(steps) >= 3:
            return
        steps.append(c.bonus(
            "attack", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("granted_via") == "p3322",
        ))

    def collapsed(ev: Any) -> None:
        if ev.target != c.me or ev.condition is not Condition.UNCONSCIOUS:
            return
        for held in steps:
            c.end_effect(held, why=f"{c.ref} resets")
        steps.clear()

    c.watch(PowerResolved, swung, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} aegis swings")
    c.watch(ConditionApplied, collapsed, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} reset")


@power("f619", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, todo=("c.triggering_attacker()",))
def f619(c: Cast) -> None:
    """**Re-aimed.** This was never about a granted attack -- `f603`'s
    half of the same feature was, and that one is written now.

    `p3323` is declared as a minor action that arms a watcher, because
    what it does is stand ready; the printed immediate interrupt is that
    watcher firing. So `PowerUsed` for `p3323` is announced when the
    aegis is placed, hours before anything triggers it, and the foe
    "that triggered the p3323 immediate interrupt" is a local inside a
    closure that emits nothing. The gap is the same one four other rows
    name: who threw the blow an interrupt answered."""


@power("f650", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF)
def f650(c: Cast) -> None:
    """Multiclass: training, an implement proficiency, and the card."""
    c.grant_row("f650b", on=c.me, until=When.ENCOUNTER)


@power("f650b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def f650b(c: Cast) -> None:
    """+1 AC while wielding a blade, +3 with a hand free. The hand is free
    when one weapon is held and it is not two-handed."""
    gear = c.world.get(c.me, Gear)
    held = list(gear.held) if gear else []
    free = len(held) == 1 and not held[0].two_handed and not gear.shield
    c.bonus(AC, 3 if free else 1, on=c.me, until=When.ENCOUNTER)


@power("f652", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, out_of_combat=True)
def f652(c: Cast) -> None:
    """Making alchemical items. A workshop, not a fight."""


@power("f658", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF, todo=("c.on_grab_attack()",))
def f658(c: Cast) -> None:
    """+4 to the attack roll of the grab action. `c.grab` sets the relation
    and rolls nothing, so there is no roll to raise."""


@power("f664", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF)
def f664(c: Cast) -> None:
    """Multiclass: once a day, +2 damage for the encounter. Written as once
    per encounter, which is what a day is to this engine -- see #72."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER)


@power("f665", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF)
def f665(c: Cast) -> None:
    """Multiclass: one power of another class, once a day, and the spec
    names it by ref. The granted row is an encounter power of its own,
    and one fight is one day to this engine -- see #72 -- so it carries
    the printed limit itself. The training and the implements are
    chargen's."""
    c.grant_row("p2339", on=c.me, until=When.ENCOUNTER)


@power("f666", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF)
def f666(c: Cast) -> None:
    """Multiclass: that class's form power, which the spec names by ref
    and which prints no limit of its own, plus one of its 1st-level
    at-wills once per encounter.

    **The narrowing is written now.** This row's marker said "no keyword in
    the tree says so, so the set is every 1st-level at-will of the class
    rather than the subset" -- and that was true until `Keyword.BEAST_FORM`
    arrived and 67 headers declared it. `c.borrow_row` already took
    `keyword=`, so the subset the card names is one argument. **4 of the
    class's 18 1st-level at-wills are in it**, which is the whole point of
    the narrowing: the unfiltered set was more than four times too big."""
    c.grant_row("p5032", on=c.me, until=When.ENCOUNTER)
    c.borrow_row("druid", level=1, uses=1, keyword=Keyword.BEAST_FORM)


@power("f667", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
    reach=PERSONAL, target=SELF)
def f667(c: Cast) -> None:
    """Multiclass: one 1st-level at-will of that class, once per
    encounter. The card names a set rather than a ref and
    `c.borrow_row` reads the set off the registry; `uses=1` is the
    printed limit, which an at-will handed over bare would not keep."""
    c.borrow_row("invoker", level=1, uses=1)
