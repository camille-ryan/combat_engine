"""Seeker level 1."""

from __future__ import annotations

from combat_engine.content.powers.seeker import (
    PRIMAL_WEAPON,
    banish,
    bites,
    extra_dice,
    foes_around,
    free_near,
    has_bow,
    has_thrown,
    on_enemies_within,
    once_when,
    scaled_w,
    square_of,
    when_turn_ends_in,
    when_turn_starts_in,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    DamageType,
    Keyword,
    MeleeOrRanged,
    Ranged,
    When,
    power,
)
from combat_engine.engine.events import EnterSquare, Miss, MoveEnd, TurnEnd, TurnStart
from combat_engine.engine.grid import Square, distance, spread


@power(
    "p11463",
    level=1,
    cls="seeker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p11463(c: Cast) -> None:
    """"Can't shift" is `c.rooted`, which still walks -- `c.immobilized` would
    say a different and stronger sentence."""
    if c.strike():
        c.damage(scaled_w(c), c.wis_mod)
        c.slowed(until=When.EOTNT)
        c.rooted(until=When.EOTNT)


@power(
    "p11464",
    level=1,
    cls="seeker",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
    requires=has_thrown,
    requires_text="a light or heavy thrown weapon, to make the melee attack",
)
def p11464(c: Cast) -> None:
    """"Its starting position" is where it stands when its next turn begins,
    which is not known when the arrow lands. So the square is taken at that
    turn's start and measured again at its end."""
    if not c.strike():
        return
    c.damage(scaled_w(c), c.wis_mod)
    victim = c.target
    if victim is None:
        return
    began: list[Square] = []

    def start(ev: object) -> None:
        here = square_of(c, victim)
        if here is not None:
            began.append(here)

    def end(ev: object) -> None:
        now = square_of(c, victim)
        if began and now is not None and distance(began[0], now) < 2:
            c.flat(c.str_mod, on=victim)

    once_when(c, TurnStart, victim, start)
    once_when(c, TurnEnd, victim, end)


@power(
    "p11465",
    level=1,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p11465(c: Cast) -> None:
    """The fall is at the end of the turn, so the move is only latched during
    it -- being pushed on somebody else's turn is not the target moving."""
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod + extra_dice(c, "1d6"))
    victim = c.target
    if victim is None:
        return
    stirred: list[bool] = []

    def moved(ev: MoveEnd) -> None:
        if ev.actor == victim and c.turn_of() == victim:
            stirred.append(True)

    def end(ev: object) -> None:
        if stirred:
            c.prone(on=victim)

    c.watch(MoveEnd, moved, until=When.EOTNT)
    once_when(c, TurnEnd, victim, end)


@power(
    "p11466",
    level=1,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p11466(c: Cast) -> None:
    """"An enemy adjacent to it" is read the printed way round: an enemy of
    the caster's, so the target is turned on its own side."""
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod)
    victim = c.target
    near = foes_around(c, victim)
    foe = c.choose(near) if near else None
    if foe is not None and victim is not None and c.basic(who=victim, on=foe):
        c.dazed(on=victim, until=When.EONT)
        c.dazed(on=foe, until=When.EONT)


@power(
    "p11467",
    level=1,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
    requires=has_thrown,
    requires_text="a light or heavy thrown weapon, to make the melee attack",
)
def p11467(c: Cast) -> None:
    """The build rider is the Strength secondary the class table derives."""
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod + extra_dice(c, "1d6"))
    victim = c.target
    if victim is None:
        return
    far = c.str_mod if c.build("second-str") else 1

    def end(ev: object) -> None:
        c.slide(1, on=victim)
        for foe in foes_around(c, victim):
            c.slide(far, on=foe)

    once_when(c, TurnEnd, victim, end)


@power(
    "p11468",
    level=1,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.COLD, Keyword.ZONE],
    attack=Attack(WIS, vs=AC),
)
def p11468(c: Cast) -> None:
    """The zone is an Effect line, so it is laid whether or not the shot
    landed. "As a minor action you can end the zone" is dropped: nothing can
    declare an action whose whole content is ending an effect."""
    if c.strike():
        c.damage(c.w(), c.wis_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.wis_mod, dtype=DamageType.COLD)
    c.hazard(
        spread({c.there}, 1),
        5,
        DamageType.COLD,
        until=When.ENCOUNTER,
        difficult=True,
        sustain=None,
    )


@power(
    "p11469",
    level=1,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
    requires=has_thrown,
    requires_text="a light or heavy thrown weapon, to make the melee attack",
)
def p11469(c: Cast) -> None:
    """The Effect line stands whether or not the shot landed."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    if victim is None:
        return
    spent: dict[int, int] = {}

    def whiffed(ev: Miss) -> None:
        if ev.attacker != victim or spent.get(0) == c.world.round:
            return
        spent[0] = c.world.round
        for foe in foes_around(c, victim):
            c.flat(c.wis_mod, on=foe)

    c.watch(Miss, whiffed, until=When.ENCOUNTER)


@power(
    "p11470",
    level=1,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p11470(c: Cast) -> None:
    """Two clauses are dropped, both for want of anywhere to put them: the
    zone being rough going for fliers as well, and the move action that walks
    the zone four squares. A zone has no notion of either."""
    if c.strike():
        c.damage(c.w(), c.wis_mod)
    c.slide(1)
    if c.first:
        zone = c.zone(c.area(), until=When.EONT, difficult=True)
        on_enemies_within(
            c,
            zone,
            lambda who: c.grants_advantage(on=who, to="allies", until=When.EONT),
            until=When.EONT,
        )


@power(
    "p12786",
    level=1,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=20),
    target=EACH_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
    requires=has_bow,
    requires_text="a bow",
)
def p12786(c: Cast) -> None:
    """The barbs fill the *unoccupied* squares, so they are picked out of the
    burst rather than taken whole."""
    if c.strike():
        c.damage(c.w())
    if not c.first:
        return
    barbs = [
        sq
        for sq in c.area()
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if not barbs:
        return
    zone = c.zone(barbs, until=When.SONT, difficult=True)
    bites(
        c,
        zone,
        c.wis_mod,
        until=When.SONT,
        side="any",
        on_start=False,
        unless_shifting=True,
    )


@power(
    "p12787",
    level=1,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.CONJURATION],
    attack=Attack(WIS, vs=AC),
    requires=has_bow,
    requires_text="a bow",
)
def p12787(c: Cast) -> None:
    """The second half -- the minor action that expends the arrow -- has no id
    of its own in the spec and so is not a row. What is written is the
    conjuration and its footfall damage; note that a conjuration occupies its
    square, so in this engine nothing can walk onto the arrow to take it."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    spot = free_near(c, c.there)
    if not spot:
        return
    where = spot[0]
    arrow = c.conjure(where, until=When.ENCOUNTER, sustain=None)
    struck: dict[int, int] = {}

    def stepped(ev: EnterSquare) -> None:
        if ev.square != where or ev.actor == c.me:
            return
        if struck.get(ev.actor) == c.world.round:
            return
        struck[ev.actor] = c.world.round
        c.flat(c.wis_mod, on=ev.actor)
        banish(c, arrow)

    c.watch(EnterSquare, stepped, until=When.ENCOUNTER)


@power(
    "p16600",
    level=1,
    cls="seeker",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=20),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p16600(c: Cast) -> None:
    if c.strike():
        c.damage(scaled_w(c))
        c.slide(1)


@power(
    "p9502",
    level=1,
    cls="seeker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p9502(c: Cast) -> None:
    """The lingering half is "adjacent to the target", which follows the
    target about -- so an aura on it rather than a zone where it stood."""
    kind = c.choose(
        [DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER],
        "damage type",
    )
    if kind is None:
        kind = DamageType.COLD
    if not c.strike():
        return
    c.damage(scaled_w(c), c.wis_mod, dtype=kind)
    victim = c.target
    if victim is None:
        return
    ring = c.aura(1, on=victim, until=When.EONT)

    def scorch(who: int) -> None:
        if who != victim:
            c.flat(c.dex_mod, dtype=kind, on=who)

    when_turn_starts_in(c, ring, scorch, until=When.EONT)


@power(
    "p9503",
    level=1,
    cls="seeker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p9503(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(scaled_w(c), c.wis_mod)
    victim = c.target
    for who in (victim, *foes_around(c, victim)):
        c.penalty("attack", 2, on=who, until=When.SONT)


@power(
    "p9504",
    level=1,
    cls="seeker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.POISON, Keyword.ZONE],
    attack=Attack(WIS, vs=AC),
)
def p9504(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(scaled_w(c), c.wis_mod)
    zone = c.zone(spread({c.there}, 1), until=When.SONT)

    def rot(who: int) -> None:
        c.flat(c.wis_mod, dtype=DamageType.POISON, on=who)

    when_turn_ends_in(c, zone, rot, until=When.SONT)


@power(
    "p9505",
    level=1,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p9505(c: Cast) -> None:
    """The cover clause is dropped -- cover is computed from two positions at
    the moment of the attack and no modifier reaches it. The ring of penalty
    is an aura on the target, because it moves when the target does."""
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod + extra_dice(c, "1d6"))
    victim = c.target
    if victim is None:
        return
    reach = 2 + c.dex_mod if c.build("second-dex") else 2
    ring = c.aura(reach, on=victim, until=When.EONT)
    on_enemies_within(
        c,
        ring,
        lambda who: c.penalty("attack", 2, on=who, until=When.EONT),
        until=When.EONT,
    )


@power(
    "p9506",
    level=1,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.POISON],
    attack=Attack(WIS, vs=AC),
)
def p9506(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod + extra_dice(c, "1d8"), dtype=DamageType.POISON)
    c.slowed(until=When.EONT)
    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, 2, until=When.EONT)


@power(
    "p9507",
    level=1,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PRIMAL,
        Keyword.WEAPON,
        Keyword.POISON,
        Keyword.CONJURATION,
    ],
    attack=Attack(WIS, vs=AC),
)
def p9507(c: Cast) -> None:
    """The blooms' own attack has no id in the spec, so it is written inline
    rather than as a row: it rolls the caster's Wisdom from the bloom's
    square and the bloom goes when it has swung."""
    if c.strike():
        c.damage(c.w(), c.wis_mod)
        c.immobilized(until=When.SAVE_ENDS)
    for spot in free_near(c, c.there, 4):
        bloom = c.conjure(spot, until=When.ENCOUNTER, sustain=None)
        _bloom_waits(c, bloom, spot)


def _bloom_waits(c: Cast, bloom: int, spot: tuple[int, int]) -> None:
    def stepped(ev: EnterSquare) -> None:
        if ev.square != spot or ev.actor == c.me:
            return
        for foe in c.in_squares(spread({spot}, 1), side="enemy"):
            if c.attack(c.wis_, FORT, on=foe, from_=bloom):
                c.flat(c.wis_mod, dtype=DamageType.POISON, on=foe)
        banish(c, bloom)

    c.watch(EnterSquare, stepped, until=When.ENCOUNTER)


@power(
    "p9508",
    level=1,
    cls="seeker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=20),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p9508(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.wis_mod + extra_dice(c, "2d6"))
    else:
        c.half_damage(c.w(), c.wis_mod + c.roll("2d6"))
