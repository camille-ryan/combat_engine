"""Wizard, level 1: the later books, second half.

`level_1_d.py` carries the rest of them and borrows this file's two helpers.

`c.burns` is the commonest zone sentence -- entering **and** starting a turn
there, once per turn, for everybody. Half the zones in these two files print
something narrower: one beat of the turn, or enemies only, or no latch at
all. `_on_zone` is those three dials.

"Cannot make opportunity attacks" is a veto on `OpportunityWindow` hung on
whatever hold the printed line gives it, which is `_no_opportunity`.
`c.no_provoke` is the other direction: it stops a creature *provoking* rather
than answering.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    INT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    OpportunityWindow,
    Ranged,
    Relation,
    Square,
    TurnEnd,
    TurnStart,
    When,
    Window,
    ZoneEntered,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration, Position
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _on_zone(
    c: Cast,
    zone: int,
    fn: Callable[[int], None],
    *,
    entering: bool = False,
    starting: bool = False,
    ending: bool = False,
    side: str = "any",
    once_per_turn: bool = False,
) -> None:
    """Hang a bite on a zone, saying who it catches and on which beat.

    The subscriptions ride the zone's own effect so they are torn down with
    it. `c.watch` cannot hold them: `until=When.SUSTAIN` on a watch makes an
    effect nothing is able to keep alive, and the shorter durations would
    outlive or predecease the ground they belong to.
    """
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if side == "enemy" and who not in c.enemies():
            return
        if once_per_turn and struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        fn(who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bite(ev.actor)

    def dawn(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    def dusk(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    subs = []
    if entering:
        subs.append(c.world.bus.on(ZoneEntered, entered))
    if starting:
        subs.append(c.world.bus.on(TurnStart, dawn))
    if ending:
        subs.append(c.world.bus.on(TurnEnd, dusk))
    held = c.world.get(zone, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)


def _no_opportunity(c: Cast, held: Effect, who: int) -> None:
    """"Cannot make opportunity attacks" -- a veto hung on the hold saying so.

    `c.no_provoke` is the other direction: it stops a creature *giving* an
    opening, where this stops it taking one.
    """

    def refuse(ev: OpportunityWindow) -> None:
        if ev.actor == who:
            ev.cancel("cannot make opportunity attacks")

    held.subs.append(
        c.world.bus.on(OpportunityWindow, refuse, window=Window.BEFORE, owner=c.me)
    )


@power(
    "p14538",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(INT, vs=FORT),
)
def p14538(c: Cast) -> None:
    """The slide is a printed "can", so it is offered rather than taken, and
    it is the caster's choice rather than the victim's."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
    c.prone()
    if c.may("slide it 1 square", who=c.me):
        c.slide(1)
    held = c.effect(f"{c.ref} no opportunity attacks", until=When.EONT)
    if held is not None:
        _no_opportunity(c, held, victim)


@power(
    "p14539",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    # "Each creature in the burst", and a close burst's origin is the
    # caster's own square rather than part of the burst -- `EACH_CREATURE`
    # would freeze the wizard standing at the middle of it.
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.CLOSE],
    attack=Attack(INT, vs=FORT),
)
def p14539(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.COLD)
        c.push(max(0, c.wis_mod))


@power(
    "p14541",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p14541(c: Cast) -> None:
    """Sustaining is a fresh roll of the same dice, so the hold has to carry
    a payout and not just a clock. It is applied through `Effects.apply`
    rather than any `Cast` helper because only that door takes a
    `sustain_cost`, and a `When.SUSTAIN` effect without one lapses after a
    round with nothing able to keep it going.

    "Once the target is out of range you can't sustain this power" is read as
    the hold ending itself: there is no way to refuse a sustain that has
    already been paid for.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d10", c.int_mod, dtype=DamageType.LIGHTNING)
    hold = c.world.effects.apply(
        victim, c.me, When.SUSTAIN, label=c.ref, sustain_cost=STANDARD
    )

    def again() -> None:
        if c.distance(to=victim) > 5:
            c.world.effects.end(hold, "out of range to sustain")
            return
        # A reroll, not a repeat of the first one -- and `c.flat` rather than
        # `c.damage`, which would still be maximising off the original hit
        # if that one happened to be a critical.
        c.flat(c.roll("1d10") + c.int_mod, dtype=DamageType.LIGHTNING, on=victim)

    c.on_sustain(hold, again)


@power(
    "p14542",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.NECROTIC,
        Keyword.FEAR,
        Keyword.ZONE,
        Keyword.CLOSE,
    ],
    attack=Attack(INT, vs=WILL),
)
def p14542(c: Cast) -> None:
    """"Ends its turn in the zone" is one beat of a turn, so the bite is a
    `TurnEnd` and not `c.burns`, which is entering and starting.

    Ignoring five points of necrotic resistance has no expression: resistance
    is subtracted inside `deal_damage` and nothing can step past it.
    """
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.NECROTIC)
        c.slowed()
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT)
    toll = max(1, c.wis_mod)
    _on_zone(
        c,
        zone,
        lambda who: c.flat(toll, dtype=DamageType.NECROTIC, on=who),
        ending=True,
        side="enemy",
    )
    c.note(f"{c.ref}: its damage should ignore 5 points of necrotic resistance")


@power(
    "p14543",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT, Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(INT, vs=WILL),
)
def p14543(c: Cast) -> None:
    """The Effect line catches the caster as well as the allies, which is
    what `side="ally"` already means -- it is the only pool that includes
    the creature asking."""
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.RADIANT)
        c.push(max(0, c.wis_mod))
    if not c.first:
        return
    for friend in c.within(2, side="ally"):
        c.temp_hp(max(1, c.wis_mod), on=friend)


@power(
    "p14544",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM, Keyword.AREA],
    attack=Attack(INT, vs=WILL),
)
def p14544(c: Cast) -> None:
    """No damage anywhere: the hold is the whole row. "First Failed Saving
    Throw" is `escalate`, and what replaces the daze carries none of its own
    so it cannot worsen twice."""
    victim = c.target
    if victim is None:
        return

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.DAZED, Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=eff.owner
        )

    if c.strike():
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, escalate=worsen)
        return
    held = c.effect(f"{c.ref} no opportunity attacks", until=When.EONT)
    if held is not None:
        _no_opportunity(c, held, victim)


@power(
    "p14545",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p14545(c: Cast) -> None:
    """The Effect line is unconditional, so the recoil is laid whether the
    attack landed or not. "Hits or misses" is both events: a `Miss` is an
    attack roll like any other and leaving it out would halve the row.
    """
    victim = c.target
    if c.strike():
        c.damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
    if victim is None:
        return
    hold = c.effect(f"{c.ref} recoil", until=When.SAVE_ENDS)
    if hold is None:
        return
    toll = 2 + c.wis_mod
    mine = {c.me, *c.allies()}

    def recoil(ev: Hit | Miss) -> None:
        if ev.attacker == victim and ev.target in mine:
            c.flat(toll, dtype=DamageType.PSYCHIC, on=victim)

    for kind in (Hit, Miss):
        hold.subs.append(c.world.bus.on(kind, recoil, owner=c.me))


@power(
    "p16274",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.CLOSE],
)
def p16274(c: Cast) -> None:
    """A held damage modifier rather than a watcher, so the engine's own
    `once` spends it on the first attack that could use it -- which is what
    "the next ranged weapon attack" means.

    The gate reads the reach and the keywords off the row that rolled: the
    damage context carries `power` and has no `ranged` flag and no
    `attacker`. Two things are lost and neither can be helped here -- a
    `Mod` is a number, so the extra comes out untyped rather than fire, and
    it is rolled when the power is used rather than when the arrow lands.
    """

    def is_ranged_weapon(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", "") or "")
        # "Ranged weapon attack" is the ranged kind exactly. `by_ranged`
        # counts an area burst as ranged too, which is right for cover and
        # wrong for this: 4e tells a ranged attack and an area attack apart.
        return (
            p is not None
            and Keyword.WEAPON in p.keywords
            and p.reach.kind == "ranged"
        )

    c.bonus(
        "damage",
        c.roll("1d6"),
        on=c.target,
        until=When.EONT,
        when=is_ranged_weapon,
        once=True,
    )
    if c.first:
        c.note(f"{c.ref}: the extra die should be fire damage, and rolled on the hit")


@power(
    "p16275",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    # An area wall 6 within 10. The distance is the printed one; the run of
    # squares is laid in the body, and everybody standing in it is a target.
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA],
    attack=Attack(INT, vs=FORT),
)
def p16275(c: Cast) -> None:
    """A wall is not a shape a `Range` can be, so it is built the way
    `level_6.py:p1548` builds one -- across the line from the wizard to the
    square it was pointed at, which is the only placement the caller is not
    being asked to describe square by square. Its height has nowhere to go:
    the board is flat.

    The anchors are ranked by how many creatures the wall would catch, the
    way `c.overrun` ranks a trample. Offered in plain sorted order the first
    answer is the lowest-numbered square on the board, and a wall there
    catches nobody every time.
    """

    def run_from(anchor: Square) -> list[Square]:
        across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
        step = (1, 0) if abs(along) >= abs(across) else (0, 1)
        laid = [
            (anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(6)
        ]
        return [sq for sq in laid if c.world.grid.inside(sq)]

    anchors = sorted(
        sq for sq in spread({c.here}, 10) if c.world.grid.inside(sq) and sq != c.here
    )
    if not anchors:
        return
    ranked = sorted(anchors, key=lambda sq: (-len(c.in_squares(run_from(sq))), sq))
    anchor = c.choose(ranked, "where the wall stands")
    if anchor is None:
        return
    for who in sorted(c.in_squares(run_from(anchor))):
        if c.strike(on=who):
            c.slide(2, on=who)
            c.slowed(on=who)


@power(
    "p16276",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ZONE, Keyword.AREA],
    attack=Attack(INT, vs=REF),
)
def p16276(c: Cast) -> None:
    """The hit is one hold carrying both halves, so one saving throw ends
    both. "Grants combat advantage" *is* the relation, and
    `c.grants_advantage` would lay a second effect with a second save.

    The printed immediate reaction -- make this attack against whoever enters
    the zone or starts a turn there -- is folded in rather than declared as
    its own ref, hung on the zone's effect so it goes when the zone goes. The
    miss slides, and a slide can put a creature back into the zone, so the
    reaction latches itself out while it is resolving.

    Two clauses have no expression and are left off: partial cover across the
    zone, and walking the zone three squares with a move action, which a
    zone's fixed squares cannot do.
    """
    if c.target is not None:
        _p16276_attack(c, c.target)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(
        area, label=c.ref, until=When.SUSTAIN, sustain=MINOR, difficult=True
    )
    busy: set[int] = set()

    def again(who: int) -> None:
        if who in busy:
            return
        busy.add(who)
        try:
            _p16276_attack(c, who)
        finally:
            busy.discard(who)

    _on_zone(c, zone, again, entering=True, starting=True)
    c.note(f"{c.ref}: the zone should grant partial cover and be walkable 3 squares")


def _p16276_attack(c: Cast, victim: int) -> None:
    """The one attack `p16276` prints, rolled from the burst and again from
    the zone it leaves behind."""
    if c.strike(on=victim):
        c.world.effects.apply(
            victim,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.IMMOBILIZED,),
            relations=[
                (Relation.GRANTS_CA_TO, victim, who) for who in [c.me, *c.allies()]
            ],
        )
        return
    area = c.area()
    pos = c.world.get(victim, Position)
    fringe = [
        sq
        for sq in sorted(spread(area, 1) - area)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if pos is None or not fringe:
        c.slide(3, on=victim)
        return
    c.slide(3, on=victim, to=min(fringe, key=lambda sq: (distance(sq, pos.square), sq)))


@power(
    "p16277",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    # "One creature adjacent to the blade" -- the blade is put down beside
    # whoever was picked, which is the same sentence from the other end.
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
)
def p16277(c: Cast) -> None:
    """The blade swings from its own square with its maker's numbers, which
    is what `from_` is for, and is walked with a move action like any other
    conjuration.

    "Enemies adjacent to the blade grant combat advantage" is a fact about
    where everyone is standing, and which enemies qualify changes every time
    anybody walks -- so it is recomputed on `MoveEnd` and torn down with the
    blade, the arrangement `level_10.py:p513` uses for the same shape.

    Repeating the attack as a standard action has no door; the printed
    Sustain line only keeps the blade on the board.
    """
    if not c.first:
        return
    victim = c.target
    if victim is None:
        return
    room = [
        sq
        for sq in sorted(spread({c.there}, 1) - {c.there})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    blade = c.conjure(
        c.choose(room, "where the blade hangs"),
        label=c.ref,
        until=When.SUSTAIN,
        sustain=MINOR,
        speed=10,
    )
    if not blade:
        return
    if c.strike(from_=blade):
        c.damage("2d6", c.int_mod, dtype=DamageType.FORCE)
        if c.may("slide it 1 square", who=c.me):
            c.slide(1)
    conj = c.world.get(blade, Conjuration)
    hold = c.world.effects.live.get(conj.effect) if conj else None
    if hold is None:
        return
    watching = [c.me, *c.allies()]
    open_to: set[int] = set()

    def redraw(_ev: object = None) -> None:
        if hold.ended:
            return
        for foe in c.enemies():
            near = c.adjacent_to(blade, foe)
            if near and foe not in open_to:
                for who in watching:
                    c.world.relations.set(Relation.GRANTS_CA_TO, foe, who)
                open_to.add(foe)
            elif not near and foe in open_to:
                for who in watching:
                    c.world.relations.clear(
                        Relation.GRANTS_CA_TO, foe, who, "away from the blade"
                    )
                open_to.discard(foe)

    def sheathe() -> None:
        for foe in sorted(open_to):
            for who in watching:
                c.world.relations.clear(
                    Relation.GRANTS_CA_TO, foe, who, "the blade is gone"
                )
        open_to.clear()

    hold.subs.append(c.world.bus.on(MoveEnd, redraw, owner=c.me))
    hold.on_end.append(sheathe)
    redraw()
