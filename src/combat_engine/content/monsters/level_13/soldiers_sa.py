"""Monster abilities, level 13: the one row a character rolls for.

Numbers load from `game.db`; this is only behaviour. The conventions of
`soldiers.py` are kept.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    MINOR,
    NO_TARGET,
    Cast,
    CloseBurst,
    When,
    power,
)


@power(
    "m2963a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
)
def m2963a4(c: Cast) -> None:
    """A character studies the m2963 and finds the seam in it.

    **Whose minor action.** The card gives the action to the character and
    `use` only ever spends the owner's, so the row sits on the m2963 and
    `c.check(..., who=)` hands the roll to the character -- which is the
    half of the sentence that matters, since the check and its consequence
    are both about that creature. The minor action is the m2963's here.

    **Who rolls.** "Any character" is read as the one most likely to
    manage it, which is what a party would do; `c.passive` ranks them
    without spending a roll.

    **Whose next attack.** The vulnerability is printed as applying to that
    character's next attack and `c.vulnerable` is not per attacker, so it
    stands against everybody until the end of the m2963's next turn. Wider
    than the card by the other characters' swings in that window.
    """
    watching = c.within(10, side="enemy")
    if not watching:
        return
    who = max(watching, key=lambda e: c.passive("history", of=e))
    if c.check("history", 25, who=who):
        c.vulnerable(10, on=c.me, until=When.EONT)
