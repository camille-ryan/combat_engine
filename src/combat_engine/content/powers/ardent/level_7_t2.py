"""Ardent, level 7: a strike that strips the target's partial cover.

The printed Special -- usable as a melee basic attack -- is not declared:
`basic.MELEE` is chosen per creature and nothing rewrites which row that is.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import augment
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
    superior cover standing, as printed.

    Augment 2 trades the per-attacker waiver for an aura that strips it from
    every enemy standing inside, and hands you combat advantage when the
    target is already beside an ally. The aura's membership is asked when
    the attack is made, so an enemy that walks out of it gets its cover
    back.

    Augment 1 is not offered: it is a +5 to Perception checks *made to find
    hidden creatures*, and a skill check carries no such purpose to gate on
    -- the bonus would apply to every Perception check the ardent makes."""
    spent = augment(c, 2)
    victim = c.target
    if spent and victim is not None:
        beside = any(a != c.me and c.adjacent_to(victim, a) for a in c.allies())
        if c.strike(advantage=True if beside else None):
            c.damage(c.w(2), c.cha_mod)
    elif c.strike():
        c.damage(c.w(), c.cha_mod)

    def mine_or_a_neighbour(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        if who is None:
            return False
        return who == c.me or (who in c.allies() and c.adjacent(who))

    if not spent:
        c.no_cover(partial=True, until=When.EONT, when=mine_or_a_neighbour)
        return
    if c.first:
        c.aura(5, label=c.ref, until=When.EONT)
        for foe in c.within(5, side="enemy"):
            c.no_cover(
                partial=True, on=foe, until=When.EONT,
                when=lambda ctx, f=foe: c.in_my_aura(f, label=c.ref),
            )
