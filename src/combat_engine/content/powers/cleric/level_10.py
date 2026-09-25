"""Cleric, level 10: utility. Nothing here rolls an attack.

`p1411` is raised on `AttackRolled` rather than on the printed `Hit`, the
reading `rogue/level_6.py` settled: the defence is read again once the
interrupt window closes, so a bonus put on there can still turn the blow
aside. The dispatcher only re-aims a row whose printed target is a single
*enemy*, so the ally is read off the event rather than trusted to targeting.

`p955` holds its two turns away with `Condition.REMOVED` -- on the board,
out of the fight -- and counts the target's own turn starts, because the
printed line measures in the target's turns and no duration does.

`p957`'s knights are conjurations: they occupy their squares and nothing
walks through them, which is the printed clause about enemies and costs the
one about allies passing. Their partial cover has nowhere to go either --
`query.cover_between` counts creatures, and a conjuration carries no
`Health`, so it is not one.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    NO_TARGET,
    ONE_ALLY,
    ONE_OTHER_ALLY,
    STANDARD,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    Event,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    TurnStart,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.query import distance_between, team

DIVINE = [Keyword.DIVINE]
DIVINE_HEALING = [Keyword.DIVINE, Keyword.HEALING]

_ALLY_IS_HIT = "an ally within 5 squares of you is hit by an attack"


def _ally_about_to_be_hit(radius: int) -> Callable[[World, int, Event], bool]:
    """`would_hit_me` for somebody else, with a range on it.

    `ally_within` reads the creature the event is *about* -- the attacker on
    an attack event -- so it answers "an ally swings", not "an ally is hit".
    """

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "target", None)
        result = getattr(ev, "result", None)
        if who is None or who == me or not (result and result.hit):
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= radius

    return check


@power(
    "p1411",
    level=10,
    cls="cleric",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=DIVINE,
    trigger=_ALLY_IS_HIT,
    on=Trigger(AttackRolled, when=_ally_about_to_be_hit(5), text=_ALLY_IS_HIT),
)
def p1411(c: Cast) -> None:
    friend = getattr(c.trigger, "target", None) or c.target
    if friend is not None:
        c.bonus(AC, 4, on=friend, until=When.EONT, kind="power")


@power(
    "p152",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=DIVINE_HEALING,
)
def p152(c: Cast) -> None:
    """"His or her healing surge value" -- the target's quarter, not the
    cleric's -- and no surge leaves anybody's pool."""
    c.heal(c.surge_value(of=c.target) + c.cha_mod)


@power(
    "p955",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=DIVINE_HEALING,
)
def p955(c: Cast) -> None:
    """Two turns out of the fight, spent healing.

    "Reappears in the space he or she last occupied" needs no arranging:
    `Condition.REMOVED` leaves the creature standing where it was and takes
    away its actions, so the square is still its own when the hold lifts.
    """
    friend = c.target
    if friend is None or not c.may("step out of the fight", who=friend):
        return
    gone = c.condition(Condition.REMOVED, until=When.ENCOUNTER, on=friend)
    if gone is None:
        return
    turns = [0]

    def elsewhere(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != friend or gone.ended:
            return
        turns[0] += 1
        if turns[0] > 2:
            c.world.effects.end(gone, "the third turn began")
            return
        if c.may("spend a healing surge", who=friend):
            c.surge(on=friend)

    gone.subs.append(c.world.bus.on(TurnStart, elsewhere, owner=c.me))


@power(
    "p957",
    level=10,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.DIVINE],
)
def p957(c: Cast) -> None:
    """Four of them, each in its own square.

    `speed=2` on each is the printed move action: `actions` offers a
    conjuration's creator the walk, and two squares is what the line allows.
    """
    free = [
        sq
        for sq in sorted(spread({c.here}, 10))
        if sq != c.here
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]
    for i in range(4):
        if not free:
            return
        where = c.choose(free, "p957: where a knight stands")
        if where is None:
            return
        free.remove(where)
        c.conjure(
            where,
            label=f"{c.ref} {i}",
            until=When.ENCOUNTER,
            sustain=None,
            speed=2,
        )
