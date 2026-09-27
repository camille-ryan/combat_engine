"""Warlord: the second stat block a card prints beside its own.

Both of this class's second cards are the same shape -- a swing the warlord
hands to an ally, printed as a free action with the parent named in its
Requirement -- and the ally is the one that uses it, so every number in the
body is the ally's own: its weapon, its ability, its shift.

That is also why the parents hand the row over with `c.grant_row` rather
than relying on `chargen.loadout`: the loadout deals a second card to the
creature holding its parent, and here the user is somebody else entirely.
"""

from __future__ import annotations

from combat_engine.content.powers.cards import active
from combat_engine.engine import (
    AC,
    DAILY,
    FREE,
    ONE_CREATURE,
    REF,
    STR,
    Attack,
    Cast,
    Keyword,
    MeleeOrRanged,
    power,
    spread,
)
from combat_engine.engine.query import squares


def _close_on(c: Cast, far: int, victim: int) -> bool:
    """Shift up to `far`, ending beside `victim` where that is reachable.

    A distance printed on a move is an "up to", so an ally already in reach
    stays where it is rather than stepping out of it for the sake of the
    number.
    """
    beside = spread(squares(c.world, victim), 1)
    if squares(c.world, c.me) & beside:
        return False
    options = [sq for sq in c.world.reachable_squares(c.me, far) if sq in beside]
    return c.shift(far, to=sorted(options)[0]) if options else c.shift(far)


@power(
    "p11603b",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=FREE,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(STR, vs=REF),
    requires=active("p11603"),
    requires_text="the p11603 power must be active",
)
def p11603b(c: Cast) -> None:
    """The ally is the caster here, so `c.w` reads its weapon and
    `c.attack_mod` the ability its build attacks with -- which is how
    "Strength or Dexterity" comes out right with one line in the header.

    The shift is an Effect and happens whether the swing lands or not. It is
    aimed at the creature about to be hit rather than handed to the decider,
    which knows nothing about the swing that follows and will as readily
    retreat -- the trap `warlord/level_9_b.py` records for its own step.
    """
    victim = c.target
    if victim is None:
        return
    _close_on(c, 2, victim)
    if c.strike():
        c.damage(c.w(3), c.attack_mod)
    else:
        c.half_damage(c.w(3), c.attack_mod)


@power(
    "p11614b",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=FREE,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    requires=active("p11614"),
    requires_text="the p11614 power must be active",
)
def p11614b(c: Cast) -> None:
    """The ally is the caster, so `c.w` reads its weapon and `c.attack_mod`
    the ability the branch it took attacks with -- which is how "Strength or
    Dexterity" comes out right without the header naming both.

    The Requirement is read off the ally, not off the warlord, so the parent
    puts a hold of its own name on each target before handing the swing over.
    """
    c.shift(3)
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
        c.prone()
