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
    verb, not a gap in the bus. `c.as_ranged(weapon=)` is that narrowing:
    `dsl._reach_of` reads `Gear` for the reach anyway, so it carries the
    held weapon's ref in the modifier context and the gate takes one more
    clause. #1341.

    **The weapon is the one in hand when the power is used**, which is
    what *"choose a weapon you are holding"* means for a row that has no
    way to ask a player: `gear.main` is "the first weapon that can be
    swung", and a character with one weapon is the common case where the
    choice is forced anyway.

    It matters only to a character holding two, which is why this played
    rather than refused before the narrowing existed: with one in hand the
    next melee attack is the chosen weapon's by construction.

    The weapon returning to your hand stays flavour on a thing that never
    left it.
    """
    held = c.held()
    chosen = getattr(held[0], "ref", "") if held else ""
    c.as_ranged(10, until=When.EONT, weapon=chosen)
