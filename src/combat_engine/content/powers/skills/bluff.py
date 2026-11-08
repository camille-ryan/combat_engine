"""Skill powers for bluff: eight utilities at levels 2, 6 and 10.

What the group has in common is a **contest**: six of the eight roll a
bluff check against somebody's passive insight, or answer a bluff check
that has already been rolled. `c.check(skill, dc)` and `c.passive` are
the two halves of that, and the dc form is used rather than comparing
totals by hand -- `skills.check` settles `success` as `total >= dc`.

`cls` is the skill and not a class, which is the module's own convention;
see `__init__.py`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    Cast,
    CloseBurst,
    Condition,
    Melee,
    Ranged,
    Trigger,
    When,
    about_me,
    my_check,
    power,
)
from combat_engine.engine.events import InitiativeRolled, SkillCheck
from combat_engine.engine.query import is_

#: The three checks a card in this family hands a bonus to. The blanket
#: `skill` modifier key is read on every check beside `skill:<name>`, so one
#: effect gated on this set says "one of these three" where three separate
#: `skill:<name>` effects would each pay once.
_SOCIAL = frozenset({"bluff", "diplomacy", "intimidate"})


def _failed_against_somebody(world: Any, me: int, ev: Any) -> bool:
    """A settled bluff check of mine, against a creature, that missed its dc.

    `success` is filled inside `skills.check`'s resolve callback, which runs
    after the interrupt window -- so this can only be true in the after
    window, which is where `WINDOW_OF` puts a free action anyway.

    `SkillCheck.target` is who the check was about, and it is `None` for a
    check about a fact. The printed trigger names a creature, so a bare
    failure is not this row's.
    """
    return (
        getattr(ev, "actor", None) == me
        and getattr(ev, "skill", "") == "bluff"
        and getattr(ev, "target", None) is not None
        and not getattr(ev, "success", False)
    )


@power(
    "p11536",
    level=2,
    cls="bluff",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=lambda world, eid: is_(world, eid, Condition.MARKED),
    requires_text="you must be marked",
)
def p11536(c: Cast) -> None:
    """The Requirement is a `requires=` rather than a body gate: this is an
    action row and not a trait, so it is asked every time the row is
    offered rather than once at arming.

    `c.is_` and not `c.marked`, because the card does not say whose mark --
    any mark counts. `c.cure` is the verb that reaches a mark, which is
    held relationally and only mirrored into the condition count.
    """
    c.cure(Condition.MARKED, on=c.me)


@power(
    "p12826",
    level=2,
    cls="bluff",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you fail a bluff check against a creature",
    on=Trigger(
        SkillCheck,
        _failed_against_somebody,
        "you fail a bluff check against a creature",
    ),
)
def p12826(c: Cast) -> None:
    """One effect on the blanket `skill` key, not three on `skill:<name>`.

    "The next" is one hold between the three skills, and `once=True` would
    be spent by *any* check the character makes -- `c.bonus`'s own spend
    watch does not re-read the gate -- so the hold is ended by hand from a
    watch that asks the same question the gate does.
    """
    foe = getattr(c.trigger, "target", None)
    held = c.bonus(
        "skill",
        5,
        on=c.me,
        kind="power",
        until=When.EONT,
        when=lambda ctx: ctx.get("skill") in _SOCIAL and ctx.get("target") == foe,
    )
    if held is None:
        return

    def spent(ev: SkillCheck) -> None:
        if (
            ev.actor == c.me
            and ev.skill in _SOCIAL
            and getattr(ev, "target", None) == foe
        ):
            c.world.effects.end(held, "used")

    c.watch(SkillCheck, spent, until=When.EONT)


@power(
    "p9304",
    level=2,
    cls="bluff",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def p9304(c: Cast) -> None:
    """`to=<id>` is the printed "one ally gains combat advantage against the
    target", and `once=True` is "for that ally's next attack against it".
    Which ally is a choice nothing can score, so it is asked.
    """
    foe = c.target
    if foe is None:
        return
    if not c.check("bluff", c.passive("insight", of=foe), against=foe):
        return
    ally = c.choose(c.within(1, side="ally"), "which ally gains combat advantage")
    if ally is None:
        return
    c.grants_advantage(on=foe, to=ally, until=When.EONT, once=True)


@power(
    "p11537",
    level=6,
    cls="bluff",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p11537(c: Cast) -> None:
    """The exemption is laid, spent on the one square, and ended -- the card
    gives it for this step and not for the rest of the turn, and
    `c.no_provoke` has no "for one move" duration to pass.
    """
    foe = c.choose(c.within(1, side="enemy"), "which enemy is fooled")
    if foe is None:
        return
    if not c.check("bluff", c.passive("insight", of=foe), against=foe):
        return
    free = c.no_provoke(from_=foe, on=c.me, until=When.EOT)
    c.move(1)
    if free is not None:
        c.world.effects.end(free, "the square was stepped")


@power(
    "p11538",
    level=6,
    cls="bluff",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a bluff, a diplomacy, or an intimidate check and dislike the result",
    on=Trigger(
        SkillCheck,
        my_check("bluff", "diplomacy", "intimidate"),
        "you make a bluff, a diplomacy, or an intimidate check and dislike the result",
    ),
    dropped=("c.substitute_check()",),
)
def p11538(c: Cast) -> None:
    """Answering a bluff check is an ordinary reroll and plays. Answering the
    other two is not: the card rolls a *bluff* check in place of the one
    that was made, and `c.reroll_check` rerolls the same skill. The
    difference is not a bonus either -- `c.reroll_check(bonus=)` lands on
    `ev.bonus`, so a modifier delta would still apply when `keep="best"`
    kept the original roll.

    `p16435` waits on the same symbol and says the same thing.
    """
    if getattr(c.trigger, "skill", "") == "bluff":
        c.reroll_check(keep="best")


@power(
    "p12829",
    level=6,
    cls="bluff",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    out_of_combat=True,
)
def p12829(c: Cast) -> None:
    """Deliberately inert. The whole printed Effect is a contest whose only
    outcome is what the target believes about events it remembers -- the
    card states no mechanical change either way, and the shared-language
    target line and the unfriendly/hostile bonuses are attitudes no board
    carries.
    """


@power(
    "p9305",
    level=6,
    cls="bluff",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
)
def p9305(c: Cast) -> None:
    """**One** check against each target's passive insight, so it is rolled
    inside `c.first` and the whole target list is walked there rather than
    once per target -- a body per target would roll the burst one check at
    a time.

    `from_=` is which creature loses the opening and `on=c.me` is who stops
    provoking it, which is the printed direction: the target cannot swing
    at *you*.
    """
    if not c.first:
        return
    told = c.check("bluff")
    for foe in c.targets:
        if told.total >= c.passive("insight", of=foe):
            c.no_provoke(from_=foe, on=c.me, until=When.EONT)


@power(
    "p11539",
    level=10,
    cls="bluff",
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=EACH_ENEMY,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p11539(c: Cast) -> None:
    """`Ranged(20)` stands in for a sight range, which the header cannot
    spell; it covers any board the engine draws.

    `c.initiative` and not `c.bonus`: `Initiative.bonus` is added before
    the d20, and this row answers a roll that has already happened.
    """
    c.initiative(-10, on=c.target)
