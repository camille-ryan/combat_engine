"""Ranger, level 6: the utilities that need a beast companion.

Held back until the engine had one. The species riders are dropped for the
reason given in `level_2_b.py`: a companion whose numbers come off its
owner has no species, and the spec names no database ref for a beast.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    When,
    World,
    power,
)
from combat_engine.engine.events import AdjacencyGained, AttackRolled
from combat_engine.engine.query import distance_between as _gap
from combat_engine.engine.triggers import Trigger, hits_my_companion

MARTIAL = [Keyword.MARTIAL]
MARTIAL_HEALING = [Keyword.MARTIAL, Keyword.HEALING]

_BEAST_HIT = "your beast companion is hit by an attack within 20 squares of you"


def _beast_hit_near_me(world: World, me: int, ev: AttackRolled) -> bool:
    """The printed Trigger, with the roll still open.

    `Hit` is too late -- the defence has been read for the second time by
    then, so a bonus laid on there cannot turn the blow aside, which is the
    whole of what this row is for.
    """
    if not hits_my_companion(world, me, ev):
        return False
    if ev.natural == 1 or ev.total < ev.defence:
        return False
    return _gap(world, me, ev.target) <= 20


@power(
    "p11573",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p11573(c: Cast) -> None:
    """"Any foe to whom you are both adjacent" is a standing question, not a
    set fixed when the power goes off, so the enemies that already qualify
    are granted now and `AdjacencyGained` catches the rest for the fight.

    The Hunter's Quarry half is dropped: the extra damage lives in a
    closure inside the class feature and no modifier key reaches it.
    """
    beast = c.companion()
    if beast is None:
        return

    def grant(foe: int) -> None:
        if c.adjacent(foe) and c.adjacent_to(beast, foe):
            c.grants_advantage(on=foe, to=c.me, until=When.ENCOUNTER)
            c.grants_advantage(on=foe, to=beast, until=When.ENCOUNTER)

    foes = set(c.enemies())
    for foe in foes:
        grant(foe)

    def closed(ev: AdjacencyGained) -> None:
        for who in (ev.actor, ev.other):
            if who in set(c.enemies()):
                grant(who)

    c.watch(AdjacencyGained, closed, until=When.ENCOUNTER, label=c.ref)


@power(
    "p4398",
    level=6,
    cls="ranger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(20),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger=_BEAST_HIT,
    on=Trigger(AttackRolled, when=_beast_hit_near_me, text=_BEAST_HIT),
)
def p4398(c: Cast) -> None:
    """"The defense targeted by the attack" is on the event, so the bonus
    goes on whichever one was rolled against rather than on all four.

    The printed Target is the beast, which is not a creature the targeting
    machinery offers -- a companion holds no initiative slot -- so it is
    reached through `c.companion()`. The species rider extends the duration
    and is dropped.
    """
    ev = c.trigger
    beast = c.companion()
    if ev is None or beast is None:
        return
    c.bonus(ev.vs, 4, on=beast, until=When.EONT, kind="power")


@power(
    "p4399",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=MARTIAL_HEALING,
)
def p4399(c: Cast) -> None:
    """"As if it had spent a healing surge" -- so a surge's worth of hit
    points and no surge actually spent, which is what `c.surge_value`
    without `c.spend_surge` says. The boar-or-lizard rider is dropped."""
    beast = c.companion()
    if beast is not None:
        c.heal(c.surge_value(of=beast), on=beast)
