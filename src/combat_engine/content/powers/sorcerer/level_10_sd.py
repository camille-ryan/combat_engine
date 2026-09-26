"""Sorcerer, level 10: unmaking somebody else's zone.

The target line is not a creature, so the header takes no target and the
body picks from `c.conjurations`. The attack is rolled against a creature
all the same -- "the Will of the target's creator" -- which is why the
header's defence is Will and the roll is aimed by hand.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    DAILY,
    STANDARD,
    WILL,
    Attack,
    Cast,
    Keyword,
    Ranged,
    power,
)
from combat_engine.engine.dsl import NO_TARGET


@power(
    "p3782",
    level=10,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(CHA, vs=WILL, plus=2),
)
def p3782(c: Cast) -> None:
    """The creator may be anywhere -- the range is to the zone, not to the
    creature -- so the roll is aimed at whoever made it and the header's
    line supplies the numbers.

    Your own conjurations are left out of the pool. "One conjuration or
    zone" does not say whose, but a sorcerer rolling against its own Will
    is not a card anybody printed.
    """
    found = [z for z in c.conjurations(within=5) if c.made_by(z) != c.me]
    pick = c.choose(found, "which conjuration or zone")
    if pick is None:
        return
    maker = c.made_by(pick)
    if maker is None:
        return
    if c.strike(on=maker):
        c.dispel(pick)
