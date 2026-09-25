"""Druid, level 9: the daily attacks that leave ground behind.

`p4902` waits for its target to fall before it lays anything down, so its
zone hangs on a `Dropped` rather than on the attack -- and "until it
escapes" is the closest thing this engine has to an escape check, which is
a saving throw.

`p2697` grants a wider critical range, which is `c.bonus("crit_range", n)`,
gated three ways: the swing must be melee, the druid must be in beast form
at the moment of the roll, and the creature being swung at must be standing
in the zone. All three change, so all three are asked then.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    When,
    get,
    power,
    spread,
)
from combat_engine.engine.query import squares

from .forms import aura_hold, burns_if, in_beast_form

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
BEAST_FORM = "you must be in beast form"


@power(
    "p16485",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p16485(c: Cast) -> None:
    """Rough going for enemies only: the zone's squares are given a name and
    the druid's own side is excused from that name, which is the one lever
    `c.ignores_difficult` offers."""
    if c.strike():
        c.damage("2d6", c.wis_mod)
        c.prone()
    else:
        c.half_damage("2d6", c.wis_mod)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult=c.ref)
    for friend in (c.me, *c.allies()):
        c.ignores_difficult(c.ref, on=friend, until=When.ENCOUNTER)


@power(
    "p2670",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p2670(c: Cast) -> None:
    """The Aftereffect hangs on the hold's `on_end`, so it follows the
    blindness going whichever way it goes."""
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        return
    hold = c.blinded(until=When.SAVE_ENDS)
    if hold is not None:
        hold.on_end.append(
            lambda: c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT, on=victim)
        )


@power(
    "p2697",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p2697(c: Cast) -> None:
    """"Slowed until the end of your next turn" on a creature starting its
    turn inside: the clock is the druid's, not the victim's, which is what
    `When.EONT` measures."""
    if c.strike():
        c.damage("1d6", c.wis_mod)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER)
    me = c.me
    foes = set(c.enemies())

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in foes:
            return
        if ev.actor in c.world.zones.occupants(zone):
            c.slowed(on=ev.actor, until=When.EONT)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} roots")

    def keen(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        p = get(ctx.get("power", "") or "")
        if who is None or p is None or p.reach.kind != "melee":
            return False
        return in_beast_form(c.world, me) and who in c.world.zones.occupants(zone)

    c.bonus("crit_range", 2, on=me, until=When.ENCOUNTER, kind="untyped", when=keen)


@power(
    "p2703",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p2703(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.wis_mod)
        c.penalty("attack", 2, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d10", c.wis_mod)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p4900",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.POISON],
    attack=Attack(WIS, vs=FORT),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p4900(c: Cast) -> None:
    """"Enters a square adjacent to you or starts its turn there, once per
    turn" is `c.burns` exactly, over an aura rather than a zone -- but it
    bites enemies only, which that method cannot say."""
    if c.strike():
        c.damage("2d10", c.wis_mod, dtype=DamageType.POISON)
    else:
        c.half_damage("2d10", c.wis_mod, dtype=DamageType.POISON)
    if not c.first:
        return
    foes = set(c.enemies())
    ring = aura_hold(c, 1, lambda who: False, lambda who: None)
    burns_if(
        c, ring, max(1, c.con_mod), DamageType.POISON,
        ok=lambda who: who in foes,
    )


@power(
    "p4902",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        *PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.COLD, Keyword.NECROTIC,
        Keyword.ZONE,
    ],
    attack=Attack(WIS, vs=FORT),
)
def p4902(c: Cast) -> None:
    """"Cold **and** necrotic damage" is one roll of two types, and damage
    here carries one; it is dealt as cold, with both keywords on the row so
    an immunity to either still reads the card.

    "Immobilized until it escapes, and the zone uses your defences" is an
    escape check against a zone, which nothing here rolls; a saving throw is
    the closest clock the engine has.
    """
    landed = bool(c.strike())
    if landed:
        c.damage("2d10", c.wis_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("2d10", c.wis_mod, dtype=DamageType.COLD)
    victim = c.target
    if victim is None:
        return

    def felled(ev: Dropped) -> None:
        if ev.actor != victim:
            return
        area = spread(squares(c.world, victim), 2)
        zone = c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult=True)

        def dusk(turn: Any) -> None:
            who = getattr(turn, "actor", None)
            if who is None or getattr(turn, "ghost", False):
                return
            if who in c.world.zones.occupants(zone):
                c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=who)

        from combat_engine.engine import TurnEnd

        c.watch(TurnEnd, dusk, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} grip")

    c.watch(Dropped, felled, until=When.ENCOUNTER, on=c.me, once=True, label=c.ref)


@power(
    "p5055",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5055(c: Cast) -> None:
    """"Prone and can't stand up (save ends)" is two clocks on one creature,
    which `c.prone(held=)` is exactly: prone for as long as prone lasts, and
    for the shorter clock it may not do the thing that ends it."""
    if c.strike():
        c.damage("2d8", c.wis_mod)
        c.prone(held=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.wis_mod)
        c.prone()
    if not c.first:
        return
    me = c.me
    foes = set(c.enemies())
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER, kind="untyped",
        when=lambda ctx: ctx.get("target") is not None
        and c.is_(Condition.PRONE, on=ctx["target"]),
    )

    def bit(ev: Hit) -> None:
        if ev.attacker != me or ev.target not in foes:
            return
        p = get(ev.power)
        if p is None or p.reach.kind != "melee":
            return
        if in_beast_form(c.world, me) and c.may("knock it down", who=me):
            c.prone(on=ev.target)

    c.watch(Hit, bit, until=When.ENCOUNTER, on=me, label=f"{c.ref} floors them")
