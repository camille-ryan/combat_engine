"""The basic attacks, which every creature has whether or not it knows any powers.

These live in the engine rather than in `content/` because they are not rows
out of the compendium -- they are part of the action economy. An opportunity
attack *is* a melee basic attack unless a creature has a power that replaces
it, so without these the opportunity window opens and nothing can ever go in
it, which is a failure that shows up as silence rather than as an error.

A monster's basic attack is usually one of its own declared abilities. It
says so by setting `Powers.basic` to that ability's id, and then these are
never reached.
"""

from __future__ import annotations

from .cast import Cast
from .dsl import ONE_CREATURE, Attack, Melee, Ranged, power
from .types import Ability, ActionType, Defense, Keyword, Usage

MELEE = "mba"
RANGED = "rba"
#: A beast companion's own melee basic attack. Here for the same reason the
#: other two are: its page prints no id for the line, an opportunity attack
#: *is* a melee basic attack, and `mba` would roll the die in the beast's
#: nonexistent hands rather than the one on its block.
BEAST = "bmba"


@power(
    MELEE,
    usage=Usage.AT_WILL,
    action=ActionType.STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(Ability.STR, vs=Defense.AC),
)
def _melee_basic(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)


@power(
    RANGED,
    usage=Usage.AT_WILL,
    action=ActionType.STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(Ability.DEX, vs=Defense.AC),
)
def _ranged_basic(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    BEAST,
    usage=Usage.AT_WILL,
    action=ActionType.STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(Ability.STR, vs=Defense.AC),
)
def _beast_basic(c: Cast) -> None:
    """`1[B]` and the beast's own modifier, both read off its block.

    No `Keyword.WEAPON`: the beast has no hands and adding proficiency for
    a weapon it is not holding is two points of attack from nowhere. The
    attack ability in the header is Strength because that is what every
    row written against a beast already names; the *printed* total arrives
    as a standing modifier laid on at spawn, so the header's ability only
    decides which modifier is already counted.
    """
    if c.strike():
        c.damage(c.b(1), c.b_mod())
