"""Seeker, level 0: the class features."""

from __future__ import annotations

from combat_engine.engine import (
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    Cast,
    CloseBurst,
    Melee,
    Miss,
    Trigger,
    When,
    both,
    by_me,
    by_melee,
    by_ranged,
    power,
    targets_me,
)
from combat_engine.engine.basic import RANGED

from . import PRIMAL, PRIMAL_WEAPON, has_thrown


@power(
    "p11462",
    level=0,
    cls="seeker",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    requires=has_thrown,
    requires_text="needs a light thrown or heavy thrown weapon",
    thrown_by_hand=True,
    trigger="an enemy misses you with a melee attack",
    on=Trigger(
        Miss,
        both(targets_me, by_melee),
        "an enemy misses you with a melee attack",
    ),
)
def p11462(c: Cast) -> None:
    """No attack roll is printed: the damage simply happens to the enemy that
    missed."""
    c.damage(c.w(), c.str_mod)
    c.push(1)


@power(
    "p9500",
    level=0,
    cls="seeker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL,
)
def p9500(c: Cast) -> None:
    c.push(1)
    c.slowed(until=When.EONT)


def _repeating(c: Cast) -> bool:
    """Is this use running inside another use of the same row?

    Which is what `p12792` does to this one: it hands the use back and
    spends it again while the swing that missed is still on the stack. The
    swing the repeat makes is then the very swing being answered, so the
    in-flight guard has to stand aside for it -- and only then. Asked of
    the stack rather than of the row that did it, so nothing here has to
    know which rows can cause a repeat.
    """
    from combat_engine.engine.dsl import running_below

    seen: object = c
    while True:
        below = running_below(seen)
        if below is None or below is seen:
            return False
        if below.ref == c.ref:
            return True
        seen = below


@power(
    "p9501",
    level=0,
    cls="seeker",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="you miss a creature with a ranged attack",
    on=Trigger(Miss, both(by_me, by_ranged), "you miss with a ranged attack"),
)
def p9501(c: Cast) -> None:
    """The shot is fired from the caster: nothing here takes a `from_`, so
    "using that creature's space as the origin square" is dropped and only
    the range it measures -- 5 squares from the creature missed -- is kept.
    Regaining the power on an action point is not modelled.

    The swing goes through `c.grant_attack` rather than `c.basic` for the
    one thing `c.basic` cannot pass: whether the guard against a row
    reaching itself applies. It does, every time but the repeat above.
    """
    missed = getattr(c.trigger, "target", None)
    if missed is None:
        return
    foes = [f for f in c.within(5, of=missed, side="enemy") if c.can_see(f)]
    if foes:
        c.grant_attack(c.me, on=foes[0], ref=RANGED, reentrant=_repeating(c))
