"""Monk, level 0: the flurry the class gets for free after a hit.

All five are the same shape -- No Action, once a round, off my own `Hit` --
and all five turn on the same question: was this creature already a target
of the attack that triggered the row? The `Hit` names one creature, so the
comparison is `c.target` against `c.trigger.target`, and the row is free to
pick somebody else because the header takes its own target.

The tier lines (11th, 21st) widen the target count, which the header holds
as data and cannot scale, so the number of targets stays at one; the damage
ladder those levels also print is read off `c.level`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    ONE_CREATURE,
    ActionType,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Trigger,
    When,
    by_me,
    power,
)

HIT_ON_MY_TURN = "you hit with an attack during your turn"
TRIGGERED = Trigger(Hit, by_me, HIT_ON_MY_TURN)

#: The five rows that *are* the class feature, one per printed option. A
#: monk knows one of them; `p11215` names the feature in both halves of its
#: card and reads this to tell which row that is on the creature in front
#: of it. Declared here because this is where they are written down, and a
#: second list elsewhere would be a second thing to keep in step.
FLURRIES = ("p7448", "p11207", "p13123", "p16131", "p16132")


def _tier(level: int) -> int:
    return 0 if level < 11 else (1 if level < 21 else 2)


def _elsewhere(c: Cast) -> bool:
    """Is this creature somebody the triggering attack left alone?"""
    return c.target != getattr(c.trigger, "target", None)


@power(
    "p11207",
    level=0,
    cls="monk",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC],
    once_per_round=True,
    trigger=HIT_ON_MY_TURN,
    on=TRIGGERED,
)
def p11207(c: Cast) -> None:
    c.flat(3 + c.str_mod + ((2 + 2 * _tier(c.level)) if _elsewhere(c) else 0))


@power(
    "p13123",
    level=0,
    cls="monk",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC],
    once_per_round=True,
    trigger=HIT_ON_MY_TURN,
    on=TRIGGERED,
)
def p13123(c: Cast) -> None:
    """"Cannot shift" is `c.rooted`, not `c.immobilized` -- the creature can
    still walk. "Cannot make opportunity attacks" has no `Cast` method at
    all, so the second half of the off-target clause is dropped."""
    c.flat(2 + c.con_mod)
    c.rooted(until=When.SONT)


@power(
    "p16131",
    level=0,
    cls="monk",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.ELEMENTAL, Keyword.FIRE],
    once_per_round=True,
    trigger=HIT_ON_MY_TURN,
    on=TRIGGERED,
)
def p16131(c: Cast) -> None:
    """"Any attack that includes you as a target" is a gate on the attack
    context, which carries `target` -- it is the damage context that does
    not."""
    c.flat(2 + c.cha_mod, dtype=DamageType.FIRE)
    if _elsewhere(c):
        c.penalty(
            "attack", -2, until=When.EONT, when=lambda ctx: ctx.get("target") == c.me
        )
    c.shift(1)


@power(
    "p16132",
    level=0,
    cls="monk",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.ELEMENTAL],
    once_per_round=True,
    trigger=HIT_ON_MY_TURN,
    on=TRIGGERED,
)
def p16132(c: Cast) -> None:
    c.flat(c.str_mod)
    c.pull(1)
    if _elsewhere(c):
        c.slowed(until=When.EONT)


@power(
    "p7448",
    level=0,
    cls="monk",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC],
    once_per_round=True,
    trigger=HIT_ON_MY_TURN,
    on=TRIGGERED,
)
def p7448(c: Cast) -> None:
    """A creature the attack hit is already adjacent, so "slide it to a
    square adjacent to you" and "slide it 1 square" come to the same move
    at this reach; the decider picks either way."""
    c.flat(2 + c.wis_mod)
    c.slide(1)
