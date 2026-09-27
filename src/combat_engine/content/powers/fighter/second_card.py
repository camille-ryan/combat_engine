"""Fighter: the second stat block printed beside `p10493`.

The stance is the parent; this is the unarmed answer it unlocks. Once a
round is not a latch of its own -- an immediate action is once a round by
the budget, which is what `Encounter.can_spend` has always said.
"""

from __future__ import annotations

from combat_engine.content.powers.cards import active
from combat_engine.engine import *
from combat_engine.engine.query import adjacent

from .grips import hand_free

_STANCE_UP = active("p10493")


def _stance_and_a_free_hand(world: World, eid: int) -> bool:
    """Both printed Requirements: the parent's stance up, and a hand free."""
    return _STANCE_UP(world, eid) and hand_free(world, eid)


def _adjacent_attacker(world: World, me: int, ev: Miss) -> bool:
    return ev.attacker is not None and adjacent(world, me, ev.attacker)


@power(
    "p10493b",
    level=5,
    cls="fighter",
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    requires=_stance_and_a_free_hand,
    requires_text="the p10493 stance must be up and a hand free",
    trigger="an enemy adjacent to you misses you with a melee attack",
    on=Trigger(
        Miss,
        both(targets_me, by_melee, _adjacent_attacker),
        "an adjacent enemy misses you with a melee attack",
    ),
)
def p10493b(c: Cast) -> None:
    """Printed At-Will, and the frequency is honest: what limits it to once
    a round is the immediate action it costs."""
    foe = c.target
    if foe is None:
        return
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.grants_advantage(on=foe, to=c.me, until=When.EONT)
