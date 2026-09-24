"""Paladin, level 5: daily attacks."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    DAILY,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    When,
    ZoneEntered,
    power,
)
from combat_engine.engine.events import ZoneExited
from combat_engine.engine.zones import Zone

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]

_DEFENCES = (AC, FORT, REF, WILL)


@power(
    "p1252",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.ZONE],
    attack=Attack(CHA, vs=REF),
)
def p1252(c: Cast) -> None:
    """The bonus belongs to standing in the light, not to being in the burst.

    So it is applied on entry and taken away on exit, which is `p1255`'s
    arrangement for the same sentence -- four defences instead of one.
    Whoever is already inside gets it by hand: `c.zone` refreshes membership
    before it returns, so their `ZoneEntered` has been and gone.
    """
    if c.strike():
        c.damage("2d6", c.cha_mod)
    if not c.first:
        return

    me = c.me
    zone = c.zone(c.area(), until=When.ENCOUNTER)
    held = c.world.get(zone, Zone)
    inside: dict[int, list[Effect]] = {}

    def light(who: int) -> None:
        if who in inside or (who != me and who not in c.allies()):
            return
        inside[who] = [
            e
            for e in (
                c.bonus(d, 1, on=who, until=When.ENCOUNTER, kind="power")
                for d in _DEFENCES
            )
            if e is not None
        ]

    def unlight(who: int) -> None:
        for effect in inside.pop(who, []):
            c.world.effects.end(effect, "left the zone")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            light(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            unlight(ev.actor)

    def cleanup() -> None:
        for who in list(inside):
            unlight(who)

    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(ZoneExited, exited),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
        # The zone ending unsubscribes the pair above before it announces the
        # exits, so the bonuses come off here rather than there.
        held.effect.on_end.append(cleanup)
    for who in c.world.zones.occupants(zone):
        light(who)


@power(
    "p1267",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p1267(c: Cast) -> None:
    """The surge is part of the attack line and buys nothing back.

    `c.spend_surge` is the one that takes a surge and heals no hit points,
    and it is paid once for the use rather than once per target.
    """
    if c.first:
        c.spend_surge(on=c.me)
    if c.strike():
        c.damage(c.w(4), c.str_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(4), c.str_mod, dtype=DamageType.RADIANT)


@power(
    "p1274",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=FORT),
)
def p1274(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.vulnerable(5, DamageType.RADIANT, until=When.ENCOUNTER)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.RADIANT)
