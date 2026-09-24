"""Paladin, level 2.

`p1288` steps in front of a blow aimed at somebody else. It is declared on
`DamageRolled` in the interrupt window, which is the one moment the number
exists and has not yet come off anybody -- `c.absorb` is what moves it.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    STANDARD,
    Cast,
    CloseBurst,
    Effect,
    Event,
    Keyword,
    Trigger,
    When,
    World,
    ZoneEntered,
    by_melee,
    by_ranged,
    power,
)
from combat_engine.engine.events import DamageRolled, ZoneExited
from combat_engine.engine.query import adjacent, team


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


_ALLY_STRUCK = "an adjacent ally is hit by a melee or a ranged attack"


def _adjacent_ally_struck(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me or getattr(ev, "amount", 0) <= 0:
        return False
    if team(world, who) is not team(world, me) or not adjacent(world, me, who):
        return False
    return by_melee(world, me, ev) or by_ranged(world, me, ev)


@power(
    "p1288",
    level=2,
    cls="paladin",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    trigger=_ALLY_STRUCK,
    on=Trigger(DamageRolled, when=_adjacent_ally_struck, text=_ALLY_STRUCK),
)
def p1288(c: Cast) -> None:
    """Declared on `DamageRolled` rather than on the printed `Hit`.

    "You are hit by the attack instead" has to happen while the number is
    still in flight: by the time a `Hit` is announced the roll has been
    judged and the only thing left to move is the damage, which is what
    `c.absorb` moves. The consequence is that an attack which hits for
    nothing at all is not stepped in front of -- there is nothing to take.
    """
    taken = c.absorb()
    if taken:
        c.note(f"p1288: {taken} taken in the ally's place")
