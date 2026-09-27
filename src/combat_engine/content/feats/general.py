"""General feats: the ones whose prerequisite names no class and no race.

Almost every row here is a trait -- `action=ActionType.NONE`, no trigger --
that installs one modifier for the fight. The prerequisite is a column and
is not written here; only the Benefit is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    WIS,
    ActionPointSpent,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Melee,
    Ranged,
    SavingThrow,
    Size,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    by_melee,
    get,
    power,
)
from combat_engine.engine.query import distance_between, team

DIVINE = [Keyword.DIVINE]

#: The sizes "Large or larger" means.
_BIG = frozenset({Size.LARGE, Size.HUGE, Size.GARGANTUAN})

#: Weapon groups a projectile feat means, as opposed to a thrown one.
_PROJECTILE = frozenset({"bow", "crossbow", "sling"})


def _tier(level: int, heroic: int, paragon: int, epic: int) -> int:
    """The "this increases at 11th and 21st level" ladder most feats print."""
    return heroic if level < 11 else (paragon if level < 21 else epic)


# -- modifier gates (they are handed a context and nothing else) -------------


def _opportunity(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("opportunity"))


def _charging(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("charge"))


def _with_advantage(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("advantage"))


def _melee_weapon(ctx: dict[str, Any]) -> bool:
    """A weapon attack made at melee reach, read off the row being resolved.

    The damage context carries no weapon and no attacker, so this is the
    only way to ask -- see the note in AUTHORING.md.
    """
    p = get(ctx.get("power", ""))
    if p is None or Keyword.WEAPON not in p.keywords:
        return False
    reach = getattr(p, "reach", None)
    return reach is not None and reach.kind == "melee"


def _keyworded(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """"A power that has the fire or the radiant keyword"."""
    want = frozenset(words)
    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", ""))
        return p is not None and bool(want & frozenset(p.keywords))

    return gate


def _shoots(c: Cast) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(
        w.ranged and w.group in _PROJECTILE for w in gear.held
    )


def _throws(c: Cast) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(
        w.ranged and w.group not in _PROJECTILE for w in gear.held
    )


# -- trigger predicates ------------------------------------------------------


def _anyone_within(squares: int) -> Callable[[World, int, Any], bool]:
    def check(world: World, me: int, ev: Any) -> bool:
        return distance_between(world, me, ev.actor) <= squares

    return check


def _crit_on_me_or_ally(world: World, me: int, ev: Any) -> bool:
    """An enemy crits me, or an ally of mine within 5 squares."""
    if not ev.critical or team(world, ev.attacker) is team(world, me):
        return False
    if ev.target == me:
        return True
    return (
        team(world, ev.target) is team(world, me)
        and distance_between(world, me, ev.target) <= 5
    )


def _friendly_melee_crit(world: World, me: int, ev: Any) -> bool:
    """I or an ally within 5 squares scores a critical hit in melee."""
    if not ev.critical or team(world, ev.attacker) is not team(world, me):
        return False
    if distance_between(world, me, ev.attacker) > 5:
        return False
    return by_melee(world, me, ev)


def _my_kill_within(squares: int) -> Callable[[World, int, Any], bool]:
    def check(world: World, me: int, ev: Any) -> bool:
        return ev.source == me and distance_between(world, me, ev.actor) <= squares

    return check


def _my_natural_20_save(world: World, me: int, ev: Any) -> bool:
    return ev.actor == me and ev.natural == 20


# -- the rows ----------------------------------------------------------------


@power("f3", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3(c: Cast) -> None:
    """The attack context carries `opportunity`, so this is one gated mod."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=_opportunity)


@power("f6", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f6(c: Cast) -> None:
    """Two mods, not one: `query.speed` is handed `{"charge": True}` only on
    a charge, and a run's extra squares are their own `"run"` modifier."""
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, when=_charging)
    c.bonus("run", 2, on=c.me, until=When.ENCOUNTER)


@power("f9", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f9(c: Cast) -> None:
    """The damage context carries `charge`. The bull rush half is dropped --
    the engine has no bull rush action to put a bonus on."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=_charging)


@power("f19", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f19(c: Cast) -> None:
    """Only the skill half lands: there is no escape action to make cheaper,
    and `c.grant_action` carries any word but `shift` and `stand` silently."""
    c.bonus("skill:acrobatics", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f27", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f27(c: Cast) -> None:
    """`c.jump` is squares crossed; a running start is not a distinction the
    engine draws, so only the skill bonus is written."""
    c.bonus("skill:athletics", 1, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f30", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.no_mount_penalty()", "c.lend_skills()"))
def f30(c: Cast) -> None:
    """A mount takes no printed attack penalty here to waive, and a creature
    cannot borrow another's skill modifier."""


@power("f36", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f36(c: Cast) -> None:
    """Climbing at full speed is a movement mode at the creature's own speed;
    the Athletics check that allows it is the ordinary one."""
    c.mode("climb", c.speed_of(c.me), on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:athletics", 1, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f109", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f109(c: Cast) -> None:
    """`Encounter.start` arms traits before it applies surprise, so refusing
    the condition here is in time to matter."""
    c.immune(Condition.SURPRISED, on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:perception", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f111", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f111(c: Cast) -> None:
    """Armour proficiency is a build-time permission, not a combat effect."""


@power("f112", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f112(c: Cast) -> None:
    """Armour proficiency is a build-time permission."""


@power("f113", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f113(c: Cast) -> None:
    """Armour proficiency is a build-time permission."""


@power("f114", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f114(c: Cast) -> None:
    """Armour proficiency is a build-time permission."""


@power("f115", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f115(c: Cast) -> None:
    """Armour proficiency is a build-time permission."""


@power("f127", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f127(c: Cast) -> None:
    """`query.defence` is handed the attack context, so a defence may be
    gated on `opportunity` where a damage rider could not be."""
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=_opportunity)


@power("f131", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.max_surges()",))
def f131(c: Cast) -> None:
    """Two more healing surges. `c.regain_surge` hands back spent ones and
    cannot raise the ceiling."""


@power("f139", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f139(c: Cast) -> None:
    """`"range"` stretches what a ranged line may be aimed at. The long-range
    penalty threshold is read off the weapon's own printed range and is not
    stretched with it, so only the reach half of the line lands."""
    if _shoots(c):
        c.bonus("range", 5, on=c.me, until=When.ENCOUNTER)


@power("f140", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f140(c: Cast) -> None:
    """As f139: a thrown weapon is a held one that can be fired and is not
    of a projectile group."""
    if _throws(c):
        c.bonus("range", 2, on=c.me, until=When.ENCOUNTER)


@power("f145", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f145(c: Cast) -> None:
    c.bonus(FORT, _tier(c.level, 2, 3, 4), kind="feat", on=c.me,
            until=When.ENCOUNTER)


@power("f148", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f148(c: Cast) -> None:
    c.bonus(WILL, _tier(c.level, 2, 3, 4), kind="feat", on=c.me,
            until=When.ENCOUNTER)


@power("f149", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f149(c: Cast) -> None:
    c.bonus(REF, _tier(c.level, 2, 3, 4), kind="feat", on=c.me,
            until=When.ENCOUNTER)


@power("f150", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f150(c: Cast) -> None:
    """Languages. Nothing a fight reads."""


@power("f157", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f157(c: Cast) -> None:
    """Drawing costs no action here already, so the first clause is the
    engine's behaviour. `c.initiative` moves the creature in the order --
    traits are armed after the opening rolls, which is in time."""
    c.initiative(2, on=c.me)


@power("f159", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f159(c: Cast) -> None:
    """Rituals. Not a combat effect."""


@power("f161", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f161(c: Cast) -> None:
    """Shield proficiency is a build-time permission."""


@power("f162", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f162(c: Cast) -> None:
    """Shield proficiency is a build-time permission."""


@power("f165", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f165(c: Cast) -> None:
    """A bonus to one chosen skill and nothing else."""


@power("f166", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f166(c: Cast) -> None:
    """Training in one skill and nothing else."""


@power("f171", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.max_hp()",))
def f171(c: Cast) -> None:
    """5 more hit points, 10 at 11th and 15 at 21st. `c.temp_hp` is a
    different thing and `c.heal` cannot raise a maximum."""


@power("f172", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f172(c: Cast) -> None:
    """A shield bonus, so it does not stack with an actual shield -- which is
    the point of the printed type."""
    if c.wielding("two-weapon"):
        c.bonus(AC, 1, kind="shield", on=c.me, until=When.ENCOUNTER)
        c.bonus(REF, 1, kind="shield", on=c.me, until=When.ENCOUNTER)


@power("f173", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f173(c: Cast) -> None:
    if c.wielding("two-weapon"):
        c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, when=_melee_weapon)


@power("f178", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f178(c: Cast) -> None:
    """Weapon proficiency is a build-time permission."""


@power("f233", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.chosen_weapon_group()",))
def f233(c: Cast) -> None:
    """+1 damage with one chosen weapon group. Nothing stores which group the
    character chose, and the damage context carries no weapon to gate on."""


@power("f238", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f238(c: Cast) -> None:
    """The weapon is read once, when the trait is armed: the attack context
    carries the hand but not the group in it."""
    if c.wielding("light blade"):
        c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=_with_advantage)


@power("f240", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f240(c: Cast) -> None:
    if c.wielding("heavy blade") or c.wielding("light blade"):
        c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=_opportunity)


@power("f245", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f245(c: Cast) -> None:
    """A bonus to untrained skill checks and nothing else."""


@power("f261", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f261(c: Cast) -> None:
    """The trade is offered before each melee swing rather than baked in: it
    is optional, so a standing penalty would be the wrong row. `Window.BEFORE`
    on `AttackDeclared` is the only moment a modifier can still reach the
    roll, and both halves are one-shots so they are spent on that one attack.
    """
    light = _tier(c.level, 2, 4, 6)
    heavy = _tier(c.level, 3, 6, 9)

    def swing(ev: Any) -> None:
        if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
            return
        if not c.may("take the attack penalty for extra damage"):
            return
        c.penalty("attack", 2, on=c.me, until=When.EOT, once=True)
        c.bonus("damage", heavy if c.wielding("two-handed") else light,
                on=c.me, until=When.EOT, once=True)

    c.watch(AttackDeclared, swing, on=c.me, until=When.ENCOUNTER,
            window=Window.BEFORE)


@power("f272", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f272(c: Cast) -> None:
    c.initiative(4, on=c.me)


@power("f274", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f274(c: Cast) -> None:
    """One extra helping of the rogue's rider, once for the fight. The light
    blade requirement of the real feature is not enforced here -- the feat
    prints none -- and the training half is a chargen line."""
    dice = c.sneak_damage()
    if not dice:
        return

    def landed(ev: Any) -> None:
        if ev.attacker == c.me and c.had_advantage(ev):
            c.flat(c.roll(dice), on=ev.target)

    c.watch(Hit, landed, on=c.me, until=When.ENCOUNTER, once=True)


@power("f277", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f277(c: Cast) -> None:
    """An at-will from another class, once per encounter. The spec names no
    ref for the chosen row, so `c.grant_row` has nothing to be given."""


@power("f278", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f278(c: Cast) -> None:
    c.grant_row("f278b", on=c.me, until=When.ENCOUNTER)


@power("f278b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=SELF,
       keywords=DIVINE,
       trigger="a creature within 10 squares of you spends an action point",
       on=Trigger(ActionPointSpent, _anyone_within(10),
                  "a creature within 10 squares spends an action point"))
def f278b(c: Cast) -> None:
    c.extra_action(MOVE, on=c.me)


@power("f281", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f281(c: Cast) -> None:
    c.grant_row("f281b", on=c.me, until=When.ENCOUNTER)


@power("f281b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=Ranged(5),
       target=ONE_CREATURE, keywords=DIVINE,
       trigger="an enemy scores a critical hit against you or an ally within 5 squares",
       on=Trigger(Hit, _crit_on_me_or_ally,
                  "an enemy crits you or an ally within 5 squares"),
       todo=("c.uncrit()",))
def f281b(c: Cast) -> None:
    """Turn the critical into an ordinary hit. `c.cancel` refuses the whole
    attack and `c.halve` changes the number, so neither says this."""


@power("f282", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f282(c: Cast) -> None:
    """Gated on the row's keywords rather than the damage type: the printed
    line is about the power, and a fire power may deal none."""
    c.bonus("damage", _tier(c.level, 1, 2, 3), kind="feat", on=c.me,
            until=When.ENCOUNTER,
            when=_keyworded(Keyword.FIRE, Keyword.RADIANT))


@power("f283", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f283(c: Cast) -> None:
    c.grant_row("f283b", on=c.me, until=When.ENCOUNTER)


@power("f283b", level=1, cls="", usage=ENCOUNTER, action=MOVE,
       reach=Melee(1), target=ONE_ALLY, keywords=DIVINE)
def f283b(c: Cast) -> None:
    """Swapping is one operation: either both move or neither does, which is
    what the printed "each shift 1 square, swapping positions" means."""
    if c.target is not None:
        c.swap(c.target, who=c.me)


@power("f284", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f284(c: Cast) -> None:
    c.bonus("damage", _tier(c.level, 1, 2, 3), kind="feat", on=c.me,
            until=When.ENCOUNTER,
            when=_keyworded(Keyword.ACID, Keyword.COLD))


@power("f285", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f285(c: Cast) -> None:
    c.bonus("damage", _tier(c.level, 1, 2, 3), kind="feat", on=c.me,
            until=When.ENCOUNTER,
            when=_keyworded(Keyword.NECROTIC, Keyword.PSYCHIC))


@power("f289", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f289(c: Cast) -> None:
    c.grant_row("f289b", on=c.me, until=When.ENCOUNTER)


@power("f289b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_ALLY, keywords=DIVINE)
def f289b(c: Cast) -> None:
    """"The first attack roll" is a one-shot, so it is spent on the roll."""
    c.bonus("attack", 2, kind="power", until=When.SONT, once=True)


@power("f295", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f295(c: Cast) -> None:
    c.grant_row("f295b", on=c.me, until=When.ENCOUNTER)


@power("f295b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=ONE_ALLY, keywords=DIVINE)
def f295b(c: Cast) -> None:
    c.bonus(WILL, 5, kind="power", until=When.SONT)


@power("f296", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f296(c: Cast) -> None:
    c.grant_row("f296b", on=c.me, until=When.ENCOUNTER)


@power("f296b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(5), target=SELF, keywords=[Keyword.DIVINE, Keyword.HEALING],
       trigger="you or an ally within 5 squares scores a critical hit with a melee attack",
       on=Trigger(Hit, _friendly_melee_crit,
                  "you or an ally within 5 squares crits in melee"))
def f296b(c: Cast) -> None:
    """The target is the creature that crit, not the caster."""
    if c.trigger is not None:
        c.surge(on=c.trigger.attacker)


@power("f297", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f297(c: Cast) -> None:
    c.grant_row("f297b", on=c.me, until=When.ENCOUNTER)


@power("f297b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.HEALING])
def f297b(c: Cast) -> None:
    """Regeneration 2 while bloodied. The 11th and 21st level steps are
    out of scope; the project stops at 10."""
    c.regeneration(2, on=c.target, while_bloodied=True)


@power("f298", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f298(c: Cast) -> None:
    c.grant_row("f298b", on=c.me, until=When.ENCOUNTER)


@power("f298b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE)
def f298b(c: Cast) -> None:
    """`Size` is a word, not a number, so "Large or larger" is a set."""

    def big(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.size_of(who) in _BIG

    c.bonus("attack", 2, on=c.me, until=When.EONT, when=big)


@power("f299", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f299(c: Cast) -> None:
    c.grant_row("f299b", on=c.me, until=When.ENCOUNTER)


@power("f299b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(1), target=EACH_ENEMY,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
       attack=Attack(WIS, vs=WILL))
def f299b(c: Cast) -> None:
    """The burst widens at 11th and 21st level, which the header cannot say;
    the printed 1 is used and the dice carry the rest of the ladder."""
    if not c.is_kind("undead"):
        return
    if c.strike():
        c.damage(f"{_tier(c.level, 1, 2, 3)}d10", c.wis_mod,
                 dtype=DamageType.RADIANT)
        c.dazed(until=When.EONT)


@power("f303", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f303(c: Cast) -> None:
    c.bonus("damage", _tier(c.level, 1, 2, 3), kind="feat", on=c.me,
            until=When.ENCOUNTER,
            when=_keyworded(Keyword.LIGHTNING, Keyword.THUNDER))


@power("f304", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f304(c: Cast) -> None:
    c.grant_row("f304b", on=c.me, until=When.ENCOUNTER)


@power("f304b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(10), target=SELF,
       keywords=[Keyword.DIVINE, Keyword.HEALING],
       trigger="your attack reduces an enemy within 10 squares of you to 0 hit points",
       on=Trigger(Dropped, _my_kill_within(10),
                  "your attack drops an enemy within 10 squares"))
def f304b(c: Cast) -> None:
    """The surge is spent by whoever is picked, which may be an ally standing
    near the corpse rather than the caster."""
    if c.trigger is None:
        return
    who = c.choose([c.me, *c.within(5, of=c.trigger.actor, side="ally")],
                   "who spends a healing surge")
    if who is not None:
        c.surge(on=who)


@power("f305", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f305(c: Cast) -> None:
    c.grant_row("f305b", on=c.me, until=When.ENCOUNTER)


@power("f305b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(5), target=ONE_CREATURE, keywords=DIVINE,
       trigger="you roll a natural 20 on a saving throw",
       on=Trigger(SavingThrow, _my_natural_20_save,
                  "you roll a natural 20 on a saving throw"),
       todo=("SavingThrow.effect",))
def f305b(c: Cast) -> None:
    """Hand the effect just saved against to an enemy. `c.transfer` wants the
    live `Effect` and the event names only the string it was saved against."""


@power("f309", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.is_vulnerable()",))
def f309(c: Cast) -> None:
    """Combat advantage with cold powers against whatever is vulnerable to
    cold. `c.vulnerable` writes the state and nothing reads it back."""


@power("f333", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f333(c: Cast) -> None:
    """Another class's heal, once a day. The spec names no ref for it."""


@power("f334", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f334(c: Cast) -> None:
    """A one-shot put in the character's hands rather than a standing bonus:
    the printed line is a free action taken when its owner wants it. The
    weapon-category choice is not stored anywhere, so the bonus is not gated
    on it; the mark lands on hit or miss, which is why it watches the roll."""

    def spend(who: int) -> None:
        c.bonus("attack", 1, on=c.me, until=When.EOT, once=True)

        def swung(ev: Any) -> None:
            if ev.attacker == c.me:
                c.mark(on=ev.target, until=When.EONT)

        c.watch(AttackRolled, swung, on=c.me, until=When.EOT, once=True)

    c.give(fn=spend, on=c.me, uses=1, cost=FREE)


@power("f335", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f335(c: Cast) -> None:
    """Another class's marking feature, once per encounter. No ref for it."""


@power("f336", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f336(c: Cast) -> None:
    """`c.quarry` is the feature, so this one is writable without a ref. The
    feat shortens the naming to the end of your next turn."""

    def designate(who: int) -> None:
        foes = c.within(10, of=who, side="enemy")
        if foes:
            c.quarry(on=foes[0], until=When.EOTNT)

    c.give(fn=designate, on=c.me, uses=1, cost=MINOR)


@power("f337", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f337(c: Cast) -> None:
    """A pact's at-will as an encounter power. The spec names no ref."""


@power("f338", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f338(c: Cast) -> None:
    """Another class's heal, once a day. The spec names no ref for it."""


@power("f339", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f339(c: Cast) -> None:
    """Swapping one known power for another is a build-time exchange."""


@power("f340", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f340(c: Cast) -> None:
    """A build-time exchange."""


@power("f341", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f341(c: Cast) -> None:
    """A build-time exchange."""


@power("f363", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f363(c: Cast) -> None:
    if c.wielding("two-weapon"):
        c.bonus("damage", 3, on=c.me, until=When.ENCOUNTER, when=_opportunity)


@power("f396", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reload()",))
def f396(c: Cast) -> None:
    """Reloading as a free action. Loading a weapon costs nothing here
    because it is not modelled at all, so there is no action to cheapen."""


@power("f419", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.bull_rush()",))
def f419(c: Cast) -> None:
    """+4 to the bull rush attack roll, 6 at 11th and 8 at 21st. There is no
    bull rush action for the bonus to sit on."""


@power("f433", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f433(c: Cast) -> None:
    """Another class's initiative feature. The spec names no ref for it."""


@power("f449", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f449(c: Cast) -> None:
    """Asked at the start of each of the caster's turns, because the printed
    line is a standing condition rather than a one-off count."""

    def look(ev: Any) -> None:
        if ev.actor != c.me:
            return
        if len([e for e in c.enemies() if c.adjacent(e)]) >= 3:
            c.bonus("attack", 1, on=c.me, until=When.EOT)
            c.bonus("damage", 1, on=c.me, until=When.EOT)

    c.watch(TurnStart, look, on=c.me, until=When.ENCOUNTER)
