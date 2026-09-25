"""Barbarian, level 2: the utilities.

Seven of the twelve print a Trigger, so seven are declared with `on=` rather
than only quoted. Four name a sentence no ready-made predicate says, and
those get a local `(world, me, ev) -> bool` written out here.

Two rows are narrative only. One is an Athletics check to jump -- the shape
`rogue/level_2.py` settled, where a jump is a `c.note` and
`out_of_combat=True` -- and one is a bonus to breaking objects, which this
engine has none of.

The move-action rows that buy something *for the duration of the move* apply
the hold, walk, and take it down by hand. The shortest printed duration,
`When.EOT`, is a whole turn too long: a second move in the same turn would
still be covered by it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    CloseBurst,
    Condition,
    Keyword,
    Target,
    Trigger,
    When,
    Window,
    World,
    about_me,
    power,
    targets_me,
)
from combat_engine.engine.events import (
    DamageApplied,
    DamageRolled,
    EffectApplied,
    SavingThrow,
    SurgeSpent,
)
from combat_engine.engine.query import is_, team

from .rage import in_rage

PRIMAL = [Keyword.PRIMAL]
MARTIAL = [Keyword.MARTIAL]


# -- the printed Trigger lines ----------------------------------------------

_A_SAVE_ENDS_EFFECT = "you are subjected to an effect that a save can end"
_I_SPEND_A_SURGE = "you spend a healing surge"
_I_TAKE_DAMAGE = "you take damage"
_I_DAMAGE_AN_ENEMY = "your attack damages an enemy"
_I_HIT_AND_IT_STANDS = "you hit an enemy and do not reduce it to 0 hit points"
_I_FAIL_A_SAVE = "you are conscious and fail a saving throw"


def _save_ends_on_me(world: World, me: int, ev: Any) -> bool:
    """`EffectApplied` rather than `ConditionApplied`: a hold carrying only
    ongoing damage announces no condition, and the printed line covers it.
    Its subject is named `target`, so `about_me` is false here forever."""
    return getattr(ev, "target", None) == me and bool(getattr(ev, "save_ends", False))


def _my_damage_landed_on_a_foe(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    return (
        getattr(ev, "source", None) == me
        and who is not None
        and who != me
        and team(world, who) is not team(world, me)
    )


def _hurt_a_foe_and_it_stands(world: World, me: int, ev: Any) -> bool:
    """"You hit an enemy and don't reduce it to 0 hit points."

    Declared on `DamageApplied` and not on `Hit`: the hit is announced from
    inside `resolve.attack`, *before* the body deals any damage, so at that
    moment nothing has been reduced to anything and the second half of the
    sentence could only ever read true.
    """
    return _my_damage_landed_on_a_foe(world, me, ev) and getattr(ev, "hp", 0) > 0


def _failed_a_save_awake(world: World, me: int, ev: Any) -> bool:
    """A death save is rolled by a creature that is neither, which is what
    keeps this off the one saving throw it must not answer."""
    if getattr(ev, "actor", None) != me or getattr(ev, "saved", True):
        return False
    return not is_(world, me, Condition.UNCONSCIOUS) and not is_(
        world, me, Condition.DYING
    )


# -- encounter --------------------------------------------------------------


@power(
    "p1145",
    level=2,
    cls="barbarian",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_A_SAVE_ENDS_EFFECT,
    on=Trigger(EffectApplied, _save_ends_on_me, _A_SAVE_ENDS_EFFECT),
)
def p1145(c: Cast) -> None:
    """"Against the triggering effect" is what `against=` picks: without it
    `c.save` takes whichever save-ends hold it finds first, which on a
    barbarian already burning is the wrong one."""
    if c.save(on=c.me, against=getattr(c.trigger, "label", "")):
        c.shift(1)


@power(
    "p12277",
    level=2,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=Target("other_ally", 99, everyone=True, label="Each ally in the burst"),
    keywords=PRIMAL,
    trigger=_I_SPEND_A_SURGE,
    on=Trigger(SurgeSpent, about_me, _I_SPEND_A_SURGE),
)
def p12277(c: Cast) -> None:
    """"That can see you" is line of effect the other way round, which is
    the same question `c.can_see` asks."""
    if c.can_see():
        c.temp_hp(c.cha_mod)


@power(
    "p14417",
    level=2,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14417(c: Cast) -> None:
    easy = c.ignores_difficult(on=c.me, until=When.EOT)
    c.move(c.speed_of() + 4)
    if easy is not None:
        c.world.effects.end(easy, "the move is over")


@power(
    "p376",
    level=2,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p376(c: Cast) -> None:
    c.note(f"{c.ref}: a jump at +5, with a running start and no cap from speed")


@power(
    "p4885",
    level=2,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p4885(c: Cast) -> None:
    c.move(c.speed_of() + (6 if c.bloodied(on=c.me) else 2))


@power(
    "p4937",
    level=2,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p4937(c: Cast) -> None:
    """The attack context carries `opportunity`, and `resolve.attack` reads
    the defence through that same context -- so "against any opportunity
    attack" is a gate on the modifier rather than four bonuses and a hope."""
    raised = [
        c.bonus(
            guard, 4, on=c.me, until=When.EOT,
            when=lambda ctx: bool(ctx.get("opportunity")),
        )
        for guard in (AC, FORT, REF, WILL)
    ]
    c.move(c.speed_of() + 4)
    for held in raised:
        if held is not None:
            c.world.effects.end(held, "the move is over")


@power(
    "p4938",
    level=2,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p4938(c: Cast) -> None:
    c.note(f"{c.ref}: +5 to break an object, and double damage against one")


@power(
    "p5244",
    level=2,
    cls="barbarian",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_I_HIT_AND_IT_STANDS,
    on=Trigger(DamageApplied, _hurt_a_foe_and_it_stands, _I_HIT_AND_IT_STANDS),
)
def p5244(c: Cast) -> None:
    """"The enemy you hit" is read off the trigger: the printed range is
    Personal, so the header has no target line that could hold it.

    The feud is one watcher looking both ways, because "each other" is one
    sentence and two rows of it would roll separate dice.
    """
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    me = c.me
    c.mark(on=victim, until=When.EONT)

    def feud(ev: DamageRolled) -> None:
        if (ev.source, ev.target) in ((me, victim), (victim, me)) and ev.amount > 0:
            ev.amount += c.roll("1d8")

    c.watch(
        DamageRolled, feud, until=When.EONT, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} feud",
    )


# -- daily ------------------------------------------------------------------


@power(
    "p14416",
    level=2,
    cls="barbarian",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_I_TAKE_DAMAGE,
    on=Trigger(DamageApplied, targets_me, _I_TAKE_DAMAGE),
)
def p14416(c: Cast) -> None:
    """`DamageApplied` rather than `DamageRolled`: "the triggering damage"
    is what actually came off hit points, which is the later number."""
    c.temp_hp(getattr(c.trigger, "amount", 0), on=c.me)


@power(
    "p4827",
    level=2,
    cls="barbarian",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p4827(c: Cast) -> None:
    c.temp_hp(c.level // 2 + (2 * c.con_mod if in_rage(c) else c.con_mod), on=c.me)


@power(
    "p4915",
    level=2,
    cls="barbarian",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
    trigger=_I_DAMAGE_AN_ENEMY,
    on=Trigger(DamageApplied, _my_damage_landed_on_a_foe, _I_DAMAGE_AN_ENEMY),
)
def p4915(c: Cast) -> None:
    """The extra hit points ride on the surge rather than being a second
    heal: one printed line, one `Healed`."""
    killed = getattr(c.trigger, "hp", 1) <= 0
    c.surge(on=c.me, bonus=c.level // 2 + c.cha_mod if killed else 0)


@power(
    "p9565",
    level=2,
    cls="barbarian",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger=_I_FAIL_A_SAVE,
    on=Trigger(SavingThrow, _failed_a_save_awake, _I_FAIL_A_SAVE),
)
def p9565(c: Cast) -> None:
    """`SavingThrow` is announced before it is acted on and `saved` is read
    back off the event afterwards, so turning it round here is the printed
    line and not a second save."""
    ev = c.trigger
    c.damage("2d6", on=c.me)
    if ev is not None:
        ev.saved = True
