"""Battlemind, level 6: throwing the weapon without letting go of it."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p2633",
    dropped=("c.as_ranged(weapon=)",),
    level=6,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
)
def p2633(c: Cast) -> None:
    """The printed clause **is** written -- `c.as_ranged`'s own docstring
    opens on this very sentence -- and only the weapon narrowing is not.

    **The old note gave the wrong reason and it was checkable.** It said
    "nothing records which weapon a melee swing was made with"; `Swung`
    carries a `weapon` field and every `AttackRolled` is one, so the
    record exists. What is missing is a way to tell `c.as_ranged` to
    spend itself only on a swing with *that* weapon -- a narrowing on the
    verb, not a gap in the bus. #1341.

    It matters only to a character holding two weapons, which is why this
    plays rather than refuses: with one in hand the next melee attack is
    the chosen weapon's by construction.

    The weapon returning to your hand stays flavour on a thing that never
    left it.
    """
    c.as_ranged(10, until=When.EONT)
