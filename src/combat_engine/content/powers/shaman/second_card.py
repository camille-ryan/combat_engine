"""Shaman: the second stat block, where the card prints two.

All three are a row the first block grants and gates: the zone's own
opportunity attack, the ward's retaliation, and the attack the changed
spirit can make. Each parent now leaves a hold or a zone under its own ref
and nothing else of the second block, so the two cards cost the two actions
they print instead of one paying for both.

**Usage is the child's own printed column**, except where the parent states
a rate in words: `p12532` prints "at will" and that is what its child gets.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.powers.cards import active
from combat_engine.engine import *
from combat_engine.engine.components import Companion
from combat_engine.engine.query import enemies

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]


def _my_zone(world: World, me: int, ref: str) -> int:
    for zid, zone in world.zones.all():
        if zone.owner == me and zone.label == ref:
            return zid
    return 0


def _zoned(ref: str) -> Callable[[World, int], bool]:
    """"Requirement: the p#### power must be active", where the parent left a
    zone. `cards.active` reads the effect table and a zone's hold sits on the
    zone rather than on its owner, so the zone register is what answers."""

    def check(world: World, eid: int) -> bool:
        return _my_zone(world, eid, ref) != 0

    return check


def _ends_turn_in_the_zone(world: World, me: int, ev: Any) -> bool:
    if ev.ghost or ev.actor not in enemies(world, me):
        return False
    zone = _my_zone(world, me, "p12871")
    return zone != 0 and ev.actor in world.zones.occupants(zone)


@power(
    "p12871b",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=OPPORTUNITY,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
    requires=_zoned("p12871"),
    requires_text="the p12871 power must be active",
    trigger="an enemy ends its turn within the zone",
    on=Trigger(TurnEnd, _ends_turn_in_the_zone, "an enemy ends its turn within the zone"),
)
def p12871b(c: Cast) -> None:
    """The printed origin is the burst's own square rather than the shaman's,
    and no header field says so -- `Range.from_` knows the companion and
    nothing else.

    So the row takes no target: the dispatcher only aims a row at creatures
    its printed reach already covers, and the enemy standing in a zone two
    squares wide somewhere else on the board is not one of them. The
    triggering enemy is read off the event instead.
    """
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.slide(3, on=foe)


def _hits_the_warded(world: World, me: int, ev: Any) -> bool:
    """"An enemy hits the primary target with a melee attack."

    The ally warded is the one carrying the hold `p3877` left on it, which is
    also how a second use of the parent moves the ward.
    """
    if ev.attacker == me or ev.attacker not in enemies(world, me):
        return False
    if not any(e.label == "p3877" and e.source == me for e in world.effects.of(ev.target)):
        return False
    return by_melee(world, me, ev)


@power(
    "p3877b",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
    requires=active("p3877"),
    requires_text="the p3877 power must be active",
    trigger="an enemy hits the warded ally with a melee attack",
    on=Trigger(Hit, _hits_the_warded, "an enemy hits the warded ally with a melee attack"),
)
def p3877b(c: Cast) -> None:
    """An interrupt that does not interrupt: the printed line answers the
    blow and never stops it, so nothing here calls `c.cancel`."""
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.FIRE)


def _shaped_spirit(ref: str) -> Callable[[World, int], bool]:
    """The parent's own clock: "until the end of the encounter **or until
    your spirit companion is no longer present**"."""
    held = active(ref)

    def check(world: World, eid: int) -> bool:
        return held(world, eid) and any(
            world.get(who, Companion).owner == eid for who in world.having(Companion)
        )

    return check


@power(
    "p12532b",
    level=9,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1, from_="companion"),
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
    requires=_shaped_spirit("p12532"),
    requires_text="the p12532 power must be active",
)
def p12532b(c: Cast) -> None:
    """At will, which is what the parent prints rather than what this card's
    own usage column says.

    The rider pays out once: `DamageApplied` is damage that actually came off
    hit points, which is the printed "deals any damage", and the watch is
    ended by hand when it does rather than left `once=True` -- that would
    spend the one firing on the first blow anybody struck.
    """
    spirit = c.companion()
    if spirit is None:
        return
    if not c.strike(from_=spirit):
        return
    c.damage("1d12", c.wis_mod)
    victim = c.target
    if victim is None:
        return
    held: list[Effect] = []

    def paid(ev: DamageApplied) -> None:
        if ev.source != victim or not held:
            return
        c.damage("1d12", on=victim)
        c.world.effects.end(held[0], "the extra damage was paid")

    held.append(c.watch(DamageApplied, paid, until=When.EONT, on=c.me, label=c.ref))
