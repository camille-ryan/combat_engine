"""Vampire, level 9.

One row. Its Hit line is a domination and a trade, and the trade is the one
clause in this class with nowhere to go -- see the row.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    DAILY,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    Keyword,
    Ranged,
    When,
    power,
)


@power(
    "p13861",
    level=9,
    cls="vampire",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.SHADOW],
    attack=Attack(CHA, vs=WILL, plus=2),
    dropped=("Effect.drop_cost(by=)",),
)
def p13861(c: Cast) -> None:
    """The domination and the Miss line both play; the trade does not.

    "You can use a minor action while adjacent to the target to gain a
    healing surge and to deal necrotic damage ... Doing so ends the
    domination" is `Effect.drop_cost` with a `drop_then` payout, and the
    offer goes to the wrong creature. `actions._dropping` offers a droppable
    effect to whoever it sits **on**, which for a domination is the dominated
    creature -- so declaring it would hand the prisoner its own release, and
    the healing surge with it. `m6109a3` names the same gap for the same
    reason and in the same words, so the symbol is already in the tree.

    The adjacency and the payout both ride on that one offer: a `drop` is
    performed before `drop_then` runs, so a payout refusing itself for
    distance would have ended the domination for nothing. They are one gap,
    not three.

    `c.restore_use` is the Miss line -- "the power is not expended" is the
    use handed back, not a second attack.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.dominate(on=victim, until=When.SAVE_ENDS)
    else:
        c.restore_use(c.ref, on=c.me)
