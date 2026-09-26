"""Invoker, level 10: an initiative shove for two, and handing surges back.

Both were listed as blocked. The first is `c.initiative`, which exists; the
second wanted the counterpart of `c.spend_surge`, which is `c.regain_surge`.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ONE_ALLY,
    STANDARD,
    ActionType,
    Cast,
    Condition,
    Health,
    InitiativeRolled,
    Keyword,
    Ranged,
    Target,
    Trigger,
    When,
    about_me,
    power,
)

ROLLED = "you roll initiative"


@power(
    "p7191",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
    trigger=ROLLED,
    on=Trigger(InitiativeRolled, about_me, ROLLED),
)
def p7191(c: Cast) -> None:
    """"You and one ally" -- `ONE_ALLY`'s pool includes the caster, so the
    invoker's own half is written explicitly on the first (and only) target.

    "Neither target is surprised" is both halves of the sentence: the
    condition is taken off whoever already has it and refused for the rest
    of the round it would otherwise cost.
    """
    c.initiative(c.int_mod)
    c.cure(Condition.SURPRISED)
    c.immune(Condition.SURPRISED, until=When.EONT)
    if c.first and c.target != c.me:
        c.initiative(c.int_mod, on=c.me)
        c.cure(Condition.SURPRISED, on=c.me)
        c.immune(Condition.SURPRISED, on=c.me, until=When.EONT)


@power(
    "p2861",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=Target(side="ally", count=2),
    keywords=[Keyword.DIVINE],
)
def p2861(c: Cast) -> None:
    """"Two healing surges or fewer" is a targeting restriction with no
    header field for it, so it is asked in the body and a target who is not
    that short is simply passed over -- which is why this row can report
    doing nothing on a board of untouched characters.
    """
    health = c.world.get(c.target, Health) if c.target is not None else None
    if health is None or health.surges > 2:
        return
    c.regain_surge()
