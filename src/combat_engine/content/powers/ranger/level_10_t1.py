"""Ranger, level 10: shaving a blow off an ally, and lending the quarry dice.

Both rows needed one number each that the engine kept out of reach -- the
damage of a blow that has been rolled and not yet dealt, and the size of the
quarry's own rider.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    SELF,
    Cast,
    DamageRolled,
    Gear,
    Hit,
    Keyword,
    Miss,
    Ranged,
    Trigger,
    When,
    World,
    power,
)
from combat_engine.engine.query import distance_between, team

_SHOOTERS = ("bow", "crossbow")


def _shooting(world: World, eid: int) -> bool:
    """The printed Requirement: a bow or a crossbow in hand."""
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and weapon.group in _SHOOTERS


def _ally_takes_it(world: World, me: int, ev: Any) -> bool:
    """Somebody on my side, and not me, is about to be hurt by the other lot."""
    hurt = getattr(ev, "target", None)
    source = getattr(ev, "source", None)
    if hurt is None or hurt == me or source is None:
        return False
    mine = team(world, me)
    return team(world, hurt) is mine and team(world, source) is not mine


@power(
    "p10705",
    level=10,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(20),
    target=ONE_ALLY,
    keywords=[Keyword.MARTIAL],
    requires=_shooting,
    requires_text="must be wielding a bow or a crossbow",
    trigger="an ally is hit by an attack",
    on=Trigger(DamageRolled, _ally_takes_it, "an ally is hit by an attack"),
)
def p10705(c: Cast) -> None:
    """The damage roll is the only window in which a number can still be
    taken off a blow, so that is the event answered rather than `Hit`, which
    carries none. The cost of that choice is that an enemy's ongoing damage
    is shaved too; the alternative was a row that could not do its one
    thing."""
    c.reduce(c.dex_mod + c.level // 2)


@power(
    "p4412",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p4412(c: Cast) -> None:
    """The payout is the quarry's own dice handed to somebody else, which is
    what `c.quarry_damage` exists to name. The ally's hit is answered rather
    than modified -- a damage modifier is a flat number and this one is
    dice -- so the extra damage is dealt beside the ally's blow and is
    sourced from the ranger."""
    c.stance()
    me = c.me

    def missed(ev: Miss) -> None:
        quarry = getattr(ev, "target", None)
        if ev.attacker != me or quarry is None or not c.is_quarry(on=quarry):
            return
        near = [
            friend
            for friend in c.allies()
            if distance_between(c.world, friend, quarry) <= 5
        ]
        chosen = c.choose(near, "who collects the quarry damage") if near else None
        if chosen is None:
            return

        def landed(hit: Hit) -> None:
            if hit.attacker == chosen and hit.target == quarry:
                c.damage(c.quarry_damage(), on=quarry)

        c.watch(Hit, landed, until=When.SONT, on=me, once=True)

    c.watch(Miss, missed, until=When.STANCE, on=me)
