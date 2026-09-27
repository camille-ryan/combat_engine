"""Seeker: the second stat block, where the card prints two.

Three rows a conjuration or a zone makes possible: the arrow expended by
firing it again, the bloom that bites whoever treads on it, and the thicket
that snares whoever walks into it. Each was folded into its parent, where
it cost nothing; here each costs the action it prints.

What is left unsaid on all three is the **origin square**. The parents put
the thing on the board and the printed line measures from it, and `Range`
can borrow a square only from a companion -- so the range is the seeker's.
For the two that are aimed by their own trigger this changes nothing,
because the dispatcher hands them the creature that set them off.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import *
from combat_engine.engine.components import Conjuration, Position
from combat_engine.engine.query import enemies

from . import banish

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]


def _conjurations(world: World, me: int, ref: str) -> list[int]:
    out = []
    for eid in world.having(Conjuration):
        made = world.get(eid, Conjuration)
        if made is not None and made.by == me and made.ref == ref:
            out.append(eid)
    return out


def _conjured(ref: str) -> Callable[[World, int], bool]:
    """"Requirement: the p#### power must be active", where what the parent
    left is a conjuration. Its hold sits on the thing conjured rather than
    on the seeker, so `cards.active` would never see it."""

    def check(world: World, eid: int) -> bool:
        return bool(_conjurations(world, eid, ref))

    return check


def _my_zone(world: World, me: int, ref: str) -> int:
    for zid, zone in world.zones.all():
        if zone.owner == me and zone.label == ref:
            return zid
    return 0


def _zoned(ref: str) -> Callable[[World, int], bool]:
    def check(world: World, eid: int) -> bool:
        return _my_zone(world, eid, ref) != 0

    return check


@power(
    "p12787b",
    level=1,
    cls="seeker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.CONJURATION],
    attack=Attack(WIS, vs=AC),
    requires=_conjured("p12787"),
    requires_text="the p12787 power must be active",
)
def p12787b(c: Cast) -> None:
    """Using this **is** expending the arrow, so the conjuration goes whether
    or not the shot lands. No ability modifier on the damage line, which is
    printed and not an omission."""
    arrows = _conjurations(c.world, c.me, "p12787")
    if c.strike():
        c.damage(c.w())
        c.prone()
    if arrows:
        banish(c, arrows[0])


def _trod_on_a_bloom(world: World, me: int, ev: Any) -> bool:
    if ev.actor not in enemies(world, me):
        return False
    return any(
        world.need(bloom, Position).square == ev.square
        for bloom in _conjurations(world, me, "p9507")
    )


@power(
    "p9507b",
    level=1,
    cls="seeker",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[
        Keyword.PRIMAL,
        Keyword.WEAPON,
        Keyword.POISON,
        Keyword.CONJURATION,
    ],
    attack=Attack(WIS, vs=FORT),
    requires=_conjured("p9507"),
    requires_text="the p9507 power must be activated",
    trigger="an enemy enters a bloom's square",
    on=Trigger(EnterSquare, _trod_on_a_bloom, "an enemy enters a bloom's square"),
)
def p9507b(c: Cast) -> None:
    """The burst is centred on the bloom that was trodden on, and a header
    cannot say so -- so this row takes no target of its own and works from
    the square its trigger names. The bloom rolls the seeker's attack, which
    is what a conjuration does, and goes once it has swung."""
    where = getattr(c.trigger, "square", None)
    if where is None:
        return
    trodden = [
        bloom
        for bloom in _conjurations(c.world, c.me, "p9507")
        if c.world.need(bloom, Position).square == where
    ]
    if not trodden:
        return
    bloom = trodden[0]
    for foe in c.in_squares(spread({where}, 1), side="enemy"):
        if c.attack(c.wis_, FORT, on=foe, from_=bloom):
            c.flat(c.wis_mod, dtype=DamageType.POISON, on=foe)
    banish(c, bloom)


def _entered_the_thicket(world: World, me: int, ev: Any) -> bool:
    zone = _my_zone(world, me, "p9515")
    return zone != 0 and ev.zone == zone and ev.actor in enemies(world, me)


def _started_in_the_thicket(world: World, me: int, ev: Any) -> bool:
    if ev.ghost or ev.actor not in enemies(world, me):
        return False
    zone = _my_zone(world, me, "p9515")
    return zone != 0 and ev.actor in world.zones.occupants(zone)


@power(
    "p9515b",
    level=5,
    cls="seeker",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
    requires=_zoned("p9515"),
    requires_text="the p9515 power must be active",
    trigger="an enemy enters the zone or starts its turn there",
    on=(
        Trigger(ZoneEntered, _entered_the_thicket, "an enemy enters the zone"),
        Trigger(TurnStart, _started_in_the_thicket, "an enemy starts its turn there"),
    ),
)
def p9515b(c: Cast) -> None:
    """Both halves of the printed trigger are declared: entering the zone and
    waking up in it are two events, and a row naming only the first would sit
    silent for whatever the zone was dropped on top of.

    The row takes no target of its own. The burst is thrown from a square in
    the zone, which may be twenty squares from the seeker, and the dispatcher
    only aims a row at creatures its *printed reach* already covers -- so a
    declared target would be dropped and the row would fire at nobody.
    """
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.immobilized(on=foe, until=When.SAVE_ENDS)
