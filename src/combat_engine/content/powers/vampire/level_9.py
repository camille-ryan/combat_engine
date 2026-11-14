"""Vampire, level 9.

One row. Its Hit line is a domination and a trade, and the trade used to be
the one clause in this class with nowhere to go -- `#1304` built the half
it waited on. See the row.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    DAILY,
    MINOR,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Ranged,
    When,
    power,
)
from combat_engine.engine.query import adjacent


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
)
def p13861(c: Cast) -> None:
    """All three clauses play now, and the trade was the whole of the gap.

    *"You can use a minor action while adjacent to the target to gain a
    healing surge and to deal necrotic damage to the target equal to your
    healing surge value. Doing so ends the domination."*

    **`by=c.me`, because the offer went to the wrong creature.**
    `actions._dropping` offers a droppable effect to whoever it sits *on*,
    which for a domination is the prisoner -- so declaring it without this
    would have handed the prisoner its own release and the healing surge
    with it. `Effect.drop_by` is `#1304`.

    **`when=` and not a test inside the payout.** `Effects.drop` ends the
    effect before the payout runs, so an adjacency check there would have
    ended the domination for nothing on the one turn it refused. The
    condition gates the offer.

    The surge and the damage are one price, and the damage is the surge's
    own value -- read *after* spending it, because that is what the card
    names and a character whose surge value changed mid-fight should pay the
    current one.

    `c.restore_use` is the Miss line -- "the power is not expended" is the
    use handed back, not a second attack.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.restore_use(c.ref, on=c.me)
        return
    hold = c.dominate(on=victim, until=When.SAVE_ENDS)

    def bite() -> None:
        # **`on=c.me` on both, and neither is spare.** `c.regain_surge`
        # follows `c.target` -- its docstring says so, because every other
        # printed line of that shape hands surges to allies -- so a bare
        # call gave the surge to the DOMINATED ENEMY. `c.surge_value` takes
        # `of=` for the same reason: the card pays out the vampire's value,
        # not the victim's, and the two differ by level and Constitution.
        c.regain_surge(on=c.me)
        c.damage(
            c.surge_value(of=c.me), dtype=DamageType.NECROTIC, on=victim,
        )

    c.endable(
        hold, MINOR, then=bite, by=c.me,
        when=lambda world, who: adjacent(world, who, victim),
    )
