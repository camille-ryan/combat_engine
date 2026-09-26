"""Shaman, level 0: the class features -- calling the spirit, and the four
opportunity attacks it threatens with.

All four share one printed Trigger, "an enemy leaves a square adjacent to
your spirit companion without shifting", which is `MoveStart` and not
`MoveEnd`: the enemy has to still *be* beside the spirit for the sentence to
be true, and by `MoveEnd` it has gone. `kind_` tells a walk from a shift.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    RANGED,
    REF,
    SELF,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    Companion,
    Gear,
    Keyword,
    Melee,
    MoveStart,
    Trigger,
    When,
    World,
    power,
)
from combat_engine.engine.query import adjacent, team

from ._spirit import beside, friends, near_spirit

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
SPIRIT_MELEE = Melee(1, from_="companion")


def _spirit_of(world: World, me: int) -> int | None:
    for eid in world.having(Companion):
        mine = world.get(eid, Companion)
        if mine is not None and mine.owner == me:
            return eid
    return None


def _no_spirit(world: World, eid: int) -> bool:
    """"Requirement: your spirit companion must not be present."""
    return _spirit_of(world, eid) is None


def _leaves_spirit(world: World, me: int, ev: MoveStart) -> bool:
    spirit = _spirit_of(world, me)
    who = ev.actor
    return (
        ev.kind_ == "walk"
        and spirit is not None
        and who not in (me, spirit)
        and team(world, who) is not team(world, me)
        and adjacent(world, spirit, who)
    )


LEAVES = Trigger(
    MoveStart, _leaves_spirit, "an enemy leaves a square adjacent to your spirit"
)


@power(
    "p6515",
    level=0,
    cls="shaman",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(20),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.CONJURATION],
    requires=_no_spirit,
    requires_text="your spirit companion must not be present",
)
def p6515(c: Cast) -> None:
    """The spirit is a companion rather than a conjuration: it belongs to the
    character, it persists, and it can be hit. Everything printed about
    moving it with your move action and about the 10 + half level that
    disperses it is the companion's own behaviour, not this row's."""
    c.call_companion()


@power(
    "p12865",
    level=0,
    cls="shaman",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
    trigger="an enemy leaves a square adjacent to your spirit companion",
    on=LEAVES,
)
def p12865(c: Cast) -> None:
    if c.strike(from_=c.companion()):
        c.damage("1d6", c.wis_mod)
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "p5388",
    level=0,
    cls="shaman",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
    trigger="an enemy leaves a square adjacent to your spirit companion",
    on=LEAVES,
)
def p5388(c: Cast) -> None:
    if c.strike(from_=c.companion()):
        c.damage("1d10", c.wis_mod)


@power(
    "p5389",
    level=0,
    cls="shaman",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.IMPLEMENT, Keyword.HEALING],
    attack=Attack(WIS, vs=REF),
    trigger="an enemy leaves a square adjacent to your spirit companion",
    on=LEAVES,
)
def p5389(c: Cast) -> None:
    """The heal is an Effect line, so it happens whether or not the swing
    lands. `friends` leaves the spirit out of the ally list -- an ally
    within 5 squares of the spirit never meant the spirit."""
    if c.strike(from_=c.companion()):
        c.damage(0, c.wis_mod)
    mates = [a for a in friends(c) if near_spirit(c, a, 5)]
    if mates and c.wis_mod > 0:
        c.heal(c.wis_mod, on=mates[0])


@power(
    "p9732",
    level=0,
    cls="shaman",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL],
    trigger="an enemy leaves a square adjacent to your spirit companion",
    on=LEAVES,
)
def p9732(c: Cast) -> None:
    """No attack of your own: an ally shoots instead. The combat advantage is
    granted to that ally alone and spent on the one shot."""
    foe = c.target
    mates = [a for a in friends(c) if near_spirit(c, a, 10)]
    if foe is None or not mates:
        return
    # "One ally" is a choice, so it is made among the ones holding a bow:
    # an ally with a mace is handed a ranged basic it cannot make.
    armed = [a for a in mates if (g := c.world.get(a, Gear)) is not None and g.ranged]
    friend = (armed or mates)[0]
    c.grants_advantage(on=foe, to=friend, once=True)
    c.grant_attack(friend, on=foe, ref=RANGED)


@power(
    "p9733",
    level=0,
    cls="shaman",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
    trigger="an enemy leaves a square adjacent to your spirit companion",
    on=LEAVES,
)
def p9733(c: Cast) -> None:
    """"Stops moving and must use a different action to resume" is the move
    being cancelled -- an opportunity action resolves in the interrupt
    window, so `MoveStart` has not happened yet and can be stopped."""
    if c.strike(from_=c.companion()):
        c.cancel()


@power(
    "p3773",
    level=0,
    cls="shaman",
    usage=ENCOUNTER,
    uses=2,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p3773(c: Cast) -> None:
    """The second creature only heals if the first actually spent a surge,
    which is what `c.surge` returning 0 says."""
    if not c.may("spend a healing surge") or not c.surge():
        return
    mates = [a for a in beside(c) if a not in (c.me, c.target)]
    if mates:
        c.heal(c.roll("1d6"), on=mates[0])


@power(
    "p3775",
    level=0,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
    out_of_combat=True,
)
def p3775(c: Cast) -> None:
    c.note("p3775: a bonus to your next skill check this turn, equal to your Wisdom")
