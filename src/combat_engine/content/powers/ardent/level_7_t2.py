"""Ardent, level 7: a strike that strips the target's partial cover.

The Augment line is power points, which are not modelled, so the unaugmented
row is what is written here. The printed Special -- usable as a melee basic
attack -- is not declared either: `basic.MELEE` is chosen per creature and
nothing rewrites which row that is.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    Keyword,
    Melee,
    When,
    power,
)


@power(
    "p13783",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p13783(c: Cast) -> None:
    """`c.no_cover` sits on the creature being looked at, which is the end the
    card writes from, and its `when` is handed the attack context -- so "on
    attacks made by you or allies adjacent to you" is a gate on `attacker`
    rather than a waiver granted to the whole party. `partial=True` leaves
    superior cover standing, as printed."""
    if c.strike():
        c.damage(c.w(), c.cha_mod)

    def mine_or_a_neighbour(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        if who is None:
            return False
        return who == c.me or (who in c.allies() and c.adjacent(who))

    c.no_cover(partial=True, until=When.EONT, when=mine_or_a_neighbour)
