"""Ardent, level 3: the at-will that stops the target walking.

The spec entry wanted the mirror of `c.rooted`: `c.immobilized` bars the
shift as well, which is a stronger card than this row prints. `c.no_walk` is
that mirror, read by `query.can_walk` in `movement.walk` and in the menu
`actions.legal` builds, so a policy is not offered a move it may not take.
"""

from __future__ import annotations

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
    "p12945",
    level=3,
    cls="ardent",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p12945(c: Cast) -> None:
    """"On its next turn" is `When.EOTNT`: the bar has to survive the
    ardent's own turn ending to still be there when the target acts.

    The two Augment lines are dropped -- nothing holds power points.
    """
    if c.strike():
        c.damage(c.w(), c.cha_mod)
        c.no_walk(until=When.EOTNT)
