"""Paladin, level 2."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    STANDARD,
    Cast,
    CloseBurst,
    Effect,
    Keyword,
    When,
    ZoneEntered,
    power,
)
from combat_engine.engine.events import ZoneExited


@power(
    "p1255",
    level=2,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.ZONE],
)
def p1255(c: Cast) -> None:
    """The bonus belongs to standing in the zone, not to being caught in the
    burst, so it is applied on entry and taken away on exit -- the shape
    `c.burns` uses to deal damage for the same reason.

    Whoever is already inside gets it by hand: `c.zone` refreshes membership
    before it returns, so their `ZoneEntered` has been and gone by the time
    there is anything to subscribe.
    """
    me = c.me
    zone = c.zone(c.area(), until=When.ENCOUNTER)
    held = dict(c.world.zones.all()).get(zone)
    inside: dict[int, Effect] = {}

    def cover(who: int) -> None:
        if who != me and who not in c.allies():
            return
        if who in inside:
            return
        effect = c.bonus(AC, 1, on=who, until=When.ENCOUNTER, kind="power")
        if effect is not None:
            inside[who] = effect

    def uncover(who: int) -> None:
        effect = inside.pop(who, None)
        if effect is not None:
            c.world.effects.end(effect, "left the zone")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            cover(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            uncover(ev.actor)

    def cleanup() -> None:
        for who in list(inside):
            uncover(who)

    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(ZoneExited, exited),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
        # The zone ending unsubscribes the pair above before it announces the
        # exits, so the bonuses have to be picked up here rather than there.
        held.effect.on_end.append(cleanup)
    for who in c.world.zones.occupants(zone):
        cover(who)


@power(
    "p1292",
    level=2,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def p1292(c: Cast) -> None:
    c.note("p1292: +4 power bonus to one social skill until the encounter ends")
