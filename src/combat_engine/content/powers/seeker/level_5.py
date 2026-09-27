"""Seeker level 5."""

from __future__ import annotations

from combat_engine.content.powers.seeker import (
    PRIMAL_WEAPON,
    bind_to_zone,
    extra_dice,
    foes_around,
    free_near,
    has_bow,
    has_thrown,
    square_of,
    when_turn_starts_in,
)
from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Keyword,
    MeleeOrRanged,
    Ranged,
    When,
    power,
)
from combat_engine.engine.events import DamageApplied, Hit, TurnStart, ZoneEntered
from combat_engine.engine.grid import spread
from combat_engine.engine.query import squares, team


@power(
    "p11476",
    level=5,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.CONJURATION],
    attack=Attack(WIS, vs=AC),
    requires=has_thrown,
    requires_text="a light or heavy thrown weapon, to make the melee attack",
)
def p11476(c: Cast) -> None:
    """`query.flanked_by` only ever looks at creatures, and the wolf is a
    conjuration, so the flank is drawn here from the wolf's square directly --
    which is the same line `Grid.flanks` draws for two allies."""
    if c.strike():
        c.damage(c.w(), c.wis_mod + extra_dice(c, "1d6"))
    spot = free_near(c, c.there)
    if not spot:
        return
    wolf = c.conjure(spot[0], until=When.EONT, sustain=None)
    mine = {c.me, *c.allies()}

    def flanked(ev: Hit) -> None:
        if ev.attacker not in mine:
            return
        den = square_of(c, wolf)
        if den is None:
            return
        theirs = squares(c.world, ev.target)
        for mine_sq in squares(c.world, ev.attacker):
            if c.world.grid.flanks(mine_sq, den, theirs):
                c.flat(c.roll("2d6"), on=ev.target)
                return

    c.watch(Hit, flanked, until=When.EONT)


@power(
    "p11477",
    level=5,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=WILL),
)
def p11477(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.wis_mod + extra_dice(c, "1d6"))
        c.push(2)
        c.prone()
    else:
        c.half_damage(c.w(), c.wis_mod + c.roll("1d6"))
        c.push(1)


@power(
    "p11478",
    level=5,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
)
def p11478(c: Cast) -> None:
    """The spread is hung on the moment the burn is taken, which `durations`
    deals as ordinary damage at the owner's turn start -- so it is the
    detail line, not the clock, that says which damage this is."""
    victim = c.target
    if c.strike():
        c.damage(c.w(), c.wis_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage(c.w(), c.wis_mod, dtype=DamageType.FIRE)
    c.ongoing(5, DamageType.FIRE, until=When.SAVE_ENDS)
    if victim is None:
        return

    def catches(ev: DamageApplied) -> None:
        if (
            ev.target != victim
            or ev.dtype is not DamageType.FIRE
            or "ongoing" not in ev.detail
        ):
            return
        for foe in foes_around(c, victim):
            c.ongoing(5, DamageType.FIRE, on=foe, until=When.SAVE_ENDS)

    c.watch(DamageApplied, catches, until=When.ENCOUNTER)


@power(
    "p12791",
    level=5,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(WIS, vs=AC),
    requires=has_bow,
    requires_text="a bow",
)
def p12791(c: Cast) -> None:
    """"The zone moves with the target" is an aura on the target -- the one
    kind of zone that follows anybody. The save that ends it has to be rolled
    by a creature, so the aura is tied to a save-ends hold on the target
    rather than carrying the duration itself."""
    if c.strike():
        c.damage(c.w(), c.wis_mod)
        c.damage("1d10", 0, dtype=DamageType.PSYCHIC)
    victim = c.target
    if victim is None:
        return
    ring = c.aura(1, on=victim, until=When.ENCOUNTER)
    hold = c.effect(c.ref, on=victim, until=When.SAVE_ENDS)
    if hold is not None:
        hold.on_end.append(lambda: c.world.zones.end(ring, "saved"))

    def wither(who: int) -> None:
        if who == victim or team(c.world, who) is team(c.world, c.me):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=who)
        c.immobilized(on=who, until=When.SOTNT)

    bind_to_zone(c, ring, when_turn_starts_in(c, ring, wither, until=When.ENCOUNTER))


@power(
    "p9514",
    level=5,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.RELIABLE],
    attack=Attack(WIS, vs=AC),
)
def p9514(c: Cast) -> None:
    """The secondary is an Effect line, so it is rolled whether or not the
    first shot landed."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    victim = c.target
    if victim is None:
        return
    for foe in [e for e in c.within(5, of=victim, side="enemy") if e != victim][:2]:
        if c.attack(c.wis_, AC, on=foe):
            c.damage(c.w(), 0, on=foe)
            spot = free_near(c, square_of(c, victim))
            if spot:
                c.slide(5, on=foe, to=spot[0])


@power(
    "p9515",
    level=5,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p9515(c: Cast) -> None:
    """The zone's own opportunity attack has no id in the spec, so it is not a
    row; it is written here as what the zone does, rolling the caster's
    Wisdom against whoever walks in."""
    if c.strike():
        c.damage(c.w(), c.wis_mod)
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    zone = c.zone(spread({c.there}, 1), until=When.EONT, difficult=True)

    def snare(who: int) -> None:
        if who == c.me or team(c.world, who) is team(c.world, c.me):
            return
        if c.attack(c.wis_, REF, on=who):
            c.immobilized(on=who, until=When.SAVE_ENDS)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            snare(ev.actor)

    def began(ev: TurnStart) -> None:
        if ev.actor in c.world.zones.occupants(zone):
            snare(ev.actor)

    c.watch(ZoneEntered, entered, until=When.EONT)
    c.watch(TurnStart, began, until=When.EONT)
