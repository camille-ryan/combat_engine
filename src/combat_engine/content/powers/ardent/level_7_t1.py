"""Ardent, level 7: the at-will that spoils the target's damage rolls."""

from __future__ import annotations

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
    "p12958",
    level=7,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p12958(c: Cast) -> None:
    """The unaugmented line is 1[W] with no ability modifier; the rider is
    the whole point of it. Augment 2 buys the modifier, a second die and a
    flat damage penalty in place of the rider.

    Augment 1 is not offered: "the target's basic attacks deal half damage"
    is `Condition.WEAKENED`, which `query.deals_half` reads off the creature
    rather than off the attack, so it cannot be narrowed to basics.
    """
    spent = augment(c, 2)
    if not c.strike():
        return
    if spent:
        c.damage(c.w(2), c.cha_mod)
        c.penalty("damage", c.con_mod, until=When.EONT)
        return
    c.damage(c.w())
    c.damage_disadvantage(until=When.SONT)
