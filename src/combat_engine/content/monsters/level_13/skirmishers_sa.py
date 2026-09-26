"""Monster abilities, level 13: the interrupt that hands a condition on.

Kept out of `skirmishers.py` only because it needed a verb that did not
exist. The reading it turns on: an immediate **interrupt** resolves before
the blow, so at the moment the row runs the conditions it is about have not
been applied and there is nothing to move. `c.pass_on` arms rather than
moves, and the report that came with it says where the edges are.
"""

from __future__ import annotations

from combat_engine.engine import (
    INTERRUPT,
    ONE_CREATURE,
    Cast,
    Hit,
    Ranged,
    Trigger,
    Usage,
    power,
    targets_me,
)

_M709_CONDITIONED = "the m709 is hit by an attack that applies a condition"


@power(
    "m709a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=Ranged(5),
    target=ONE_CREATURE,
    trigger=_M709_CONDITIONED,
    on=Trigger(Hit, targets_me, _M709_CONDITIONED),
)
def m709a1(c: Cast) -> None:
    """"An attack that applies any conditions" cannot be asked before the
    attack resolves -- nothing on a `Hit` says what the power is about to
    do -- so the declared trigger is being hit, and a blow that turns out
    to apply nothing passes nothing on. That is the whole of the
    approximation: the row is offered a little more often than the card
    offers it, and never does anything it should not.
    """
    victim = c.target
    if victim is None:
        return
    c.pass_on(c.trigger, to=victim)
