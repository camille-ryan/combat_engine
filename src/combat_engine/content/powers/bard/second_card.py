"""Bard: the second stat block printed beside `p2977`.

The minor action buys a hold; this is the opportunity attack that hold
unlocks. It used to live in `level_9.py` as a watch hung on the hold,
because both blocks were printed under one id -- they are two rows now,
and the hold is the Requirement the second one reads.
"""

from __future__ import annotations

from combat_engine.content.powers.cards import active
from combat_engine.engine import *


def _enemy_opens_within(squares_: int):  # noqa: ANN202
    """"An enemy starts its turn within N squares of you."

    A ghost turn is the order being walked rather than a creature acting,
    so it is not the start of anybody's turn.
    """
    near = enemy_within(squares_)

    def check(world: World, me: int, ev: TurnStart) -> bool:
        return not ev.ghost and near(world, me, ev)

    return check


@power(
    "p2977b",
    level=9,
    cls="bard",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(CHA, vs=WILL),
    requires=active("p2977"),
    requires_text="the p2977 power must be active",
    trigger="an enemy starts its turn within 3 squares of you",
    on=Trigger(
        TurnStart,
        _enemy_opens_within(3),
        "an enemy starts its turn within 3 squares of you",
    ),
)
def p2977b(c: Cast) -> None:
    """The errata deletes the dice from the Hit line, so the modifier alone
    is the damage."""
    if c.strike():
        c.damage(0, c.cha_mod)
        c.cannot_shift(until=When.EONT)
