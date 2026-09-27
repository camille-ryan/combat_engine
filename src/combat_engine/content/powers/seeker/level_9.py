"""Seeker level 9."""

from __future__ import annotations

from combat_engine.content.powers.seeker import (
    PRIMAL_WEAPON,
    bind_to_zone,
    extra_dice,
    foes_around,
    free_near,
    has_thrown,
    landed_on,
    square_of,
)
from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    FORT,
    MINOR,
    ONE_CREATURE,
    STANDARD,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    Condition,
    DamageType,
    Keyword,
    MeleeOrRanged,
    Ranged,
    UpTo,
    When,
    power,
)
from combat_engine.engine.events import DamageApplied, MoveEnd
from combat_engine.engine.grid import spread
from combat_engine.engine.query import team


@power(
    "p11484",
    level=9,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(WIS, vs=AC),
    requires=has_thrown,
    requires_text="a light or heavy thrown weapon, to make the melee attack",
)
def p11484(c: Cast) -> None:
    """A sustained zone outlives every duration in `When`, so its trigger is
    given the encounter and ended with the zone instead. Ongoing damage also
    arrives as `DamageApplied`, so the detail line keeps it out of "deals
    damage with an attack"."""
    if c.strike():
        c.damage(c.w(), c.wis_mod + extra_dice(c, "1d6"))
        c.slide(1)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.wis_mod + c.roll("1d6"))
    zone = c.zone(spread({c.there}, 1), until=When.SUSTAIN, sustain=MINOR)

    def punish(ev: DamageApplied) -> None:
        who = ev.source
        if who == c.me or team(c.world, who) is team(c.world, c.me):
            return
        if "ongoing" in ev.detail or who not in c.world.zones.occupants(zone):
            return
        if c.is_(Condition.IMMOBILIZED, on=who):
            c.flat(5, on=who)
            c.condition(Condition.RESTRAINED, on=who, until=When.SAVE_ENDS)
        else:
            c.immobilized(on=who, until=When.SAVE_ENDS)

    bind_to_zone(
        c, zone, c.watch(DamageApplied, punish, until=When.ENCOUNTER)
    )


@power(
    "p11485",
    level=9,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.FIRE, Keyword.COLD],
    attack=Attack(WIS, vs=AC),
)
def p11485(c: Cast) -> None:
    """"Save ends both" is one effect carrying both the condition and the
    burn, which is what `c.condition(ongoing=...)` is for -- two separate
    holds would want two saves."""
    victim = c.target
    if not c.strike():
        c.half_damage(c.w(), c.wis_mod, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.COLD, until=When.SAVE_ENDS)
        return
    c.damage(c.w(), c.wis_mod, dtype=DamageType.FIRE)
    if victim is None:
        return
    who = c.choose([victim, *foes_around(c, victim)]) or victim
    c.condition(
        Condition.IMMOBILIZED,
        until=When.SAVE_ENDS,
        on=who,
        ongoing=(5, DamageType.COLD),
    )

    def chills(ev: DamageApplied) -> None:
        if (
            ev.target != who
            or ev.dtype is not DamageType.COLD
            or "ongoing" not in ev.detail
        ):
            return
        for foe in foes_around(c, who):
            c.flat(5, dtype=DamageType.COLD, on=foe)

    c.watch(DamageApplied, chills, until=When.ENCOUNTER)


@power(
    "p16602",
    level=9,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[
        Keyword.PRIMAL,
        Keyword.WEAPON,
        Keyword.POISON,
        Keyword.TELEPORTATION,
    ],
    attack=Attack(WIS, vs=FORT),
)
def p16602(c: Cast) -> None:
    """The teleport is an Effect line and lands whether or not the shot did."""
    if c.strike():
        c.condition(
            Condition.WEAKENED,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.POISON),
        )
    spots = [
        sq
        for sq in sorted(c.area())
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if spots:
        c.teleport(5, who=c.target, to=c.choose(spots) or spots[0])


@power(
    "p9521",
    level=9,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=UpTo(2),
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p9521(c: Cast) -> None:
    """"Can't move to a square that isn't adjacent to the other" is enforced
    by dragging the strayer back, there being no way to refuse one
    destination and allow another. The optional "take 10 damage for +5 to the
    saving throw" is dropped: nothing can bid on a save in progress."""
    if c.strike():
        c.damage(c.w(), c.wis_mod + extra_dice(c, "1d8"))
    else:
        c.half_damage(c.w(), c.wis_mod + c.roll("1d8"))
    if not c.last:
        return
    landed = landed_on(c)
    if len(landed) < 2:
        return
    one, two = landed[0], landed[1]
    spot = free_near(c, square_of(c, two))
    if spot:
        c.slide(5, on=one, to=spot[0])
    for who, mate in ((one, two), (two, one)):
        _bind(c, who, mate)


def _bind(c: Cast, who: int, mate: int) -> None:
    hold = c.effect(c.ref, on=who, until=When.SAVE_ENDS)

    def strayed(ev: MoveEnd) -> None:
        if ev.actor != who or hold is None or hold.ended:
            return
        if c.adjacent_to(mate, who):
            return
        spot = free_near(c, square_of(c, mate))
        if spot:
            c.slide(20, on=who, to=spot[0])

    watching = c.watch(MoveEnd, strayed, until=When.ENCOUNTER)
    if hold is not None:
        hold.on_end.append(lambda: c.world.effects.end(watching, "saved"))


@power(
    "p9522",
    level=9,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PRIMAL,
        Keyword.WEAPON,
        Keyword.LIGHTNING,
        Keyword.THUNDER,
    ],
    attack=Attack(WIS, vs=FORT),
)
def p9522(c: Cast) -> None:
    if c.strike():
        c.damage(
            c.w(), c.wis_mod + extra_dice(c, "2d8"), dtype=DamageType.LIGHTNING
        )
        for foe in foes_around(c, c.target):
            c.flat(5, dtype=DamageType.THUNDER, on=foe)
    else:
        c.half_damage(
            c.w(), c.wis_mod + c.roll("2d8"), dtype=DamageType.LIGHTNING
        )
