"""Assassin: the second stat blocks printed beside `p9426` and `p12564`.

`p9426b` is the duplicate's own swing. The duplicate is a conjuration, so
the gate is that it is standing rather than a hold on the caster, and the
target is picked from what stands next to *it* -- a melee reach in the
header is measured from the caster and no header field says otherwise.

`p12564b` is the free action the zone unlocks. It lived in `level_10.py`
as a watch on `DamageApplied`, because both blocks were printed under one
id; as a row of its own it declares that event as its Trigger, and the
free action's window is after the blow, which is the printed "after the
triggering attack is resolved".
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.components import Conjuration
from combat_engine.engine.zones import Zone


def _duplicate(world: World, me: int, ref: str) -> int | None:
    for eid in list(world.having(Conjuration)):
        made = world.get(eid, Conjuration)
        if made is not None and made.by == me and made.ref == ref:
            return eid
    return None


def _standing(ref: str):  # noqa: ANN202
    def check(world: World, eid: int) -> bool:
        return _duplicate(world, eid, ref) is not None

    return check


def _zone(world: World, me: int, ref: str) -> Zone | None:
    for _eid, zone in world.each(Zone):
        if zone.owner == me and zone.label == ref and zone.squares:
            return zone
    return None


def _zone_up(ref: str):  # noqa: ANN202
    def check(world: World, eid: int) -> bool:
        return _zone(world, eid, ref) is not None

    return check


@power(
    "p9426b",
    level=5,
    cls="assassin",
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=REF),
    requires=_standing("p9426"),
    requires_text="the p9426 duplicate must be standing",
)
def p9426b(c: Cast) -> None:
    """"Your p9400 target" is whoever is carrying this assassin's shrouds."""
    ghost = _duplicate(c.world, c.me, "p9426")
    if ghost is None:
        return
    pool = [foe for foe in c.enemies() if c.adjacent_to(ghost, foe)]
    foe = c.choose(pool, "who the duplicate reaches for") if pool else None
    if foe is None:
        return
    if c.strike(on=foe, from_=ghost):
        c.flat(6 if c.shrouds(on=foe) else 3, on=foe)


@power(
    "p12564b",
    level=10,
    cls="assassin",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW, Keyword.TELEPORTATION, Keyword.ZONE],
    requires=_zone_up("p12564"),
    requires_text="the p12564 zone must be standing",
    trigger="you take damage from an attack",
    on=Trigger(DamageApplied, targets_me, "you take damage"),
)
def p12564b(c: Cast) -> None:
    """Five squares is the whole allowance, so a zone further off than that
    cannot be reached and the hop simply does not happen -- which is what
    the printed number means."""
    zone = _zone(c.world, c.me, "p12564")
    if zone is None:
        return
    reachable = [
        sq
        for sq in sorted(spread(zone.squares, 1))
        if c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and distance(c.here, sq) <= 5
    ]
    if not reachable:
        return
    where = c.choose(reachable, "where the shadows put you down")
    if where is not None:
        c.teleport(5, to=where)
