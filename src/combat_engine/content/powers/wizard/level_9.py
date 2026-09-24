"""Wizard, level 9: the daily attacks.

`p722` prints an area **wall**, which is not a shape a `Range` can be, so its
distance is the printed ten squares and the run is laid in the body the way
`level_6.py` lays the fog. Two clauses of it do not survive: the four squares
of height, the board being flat, and "each square of movement costs 3 extra",
where a zone's difficult terrain is a fixed one extra and there is nowhere to
say a different number.

`p419`'s sword is a conjuration and is given a speed of ten so the printed
move action can reach anywhere in range; the printed line repositions it
beside a creature rather than walking it, which is a shorter journey than the
grid will charge for.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    FORT,
    INT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    Condition,
    DamageType,
    Keyword,
    Ranged,
    TurnStart,
    When,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p191",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(3, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p191(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.COLD)
        c.slowed(until=When.SAVE_ENDS)
    if not c.first:
        return
    area = c.area()
    if area:
        c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult=True)


@power(
    "p419",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    # "One creature adjacent to the sword" -- the sword is placed next to
    # whoever was picked, which is the same thing said from the other end.
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
)
def p419(c: Cast) -> None:
    """The sword swings with the wizard's numbers from its own square, which
    is what `from_` is for, and sustaining it swings again at whatever it is
    now standing next to.
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
        c.choose(room, "where the sword hangs"),
        label=c.ref,
        until=When.SUSTAIN,
        sustain=MINOR,
        speed=10,
    )
    if not blade:
        return
    if c.strike(from_=blade):
        c.damage("1d10", c.int_mod, dtype=DamageType.FORCE)

    def again() -> None:
        near = sorted(e for e in c.enemies() if c.adjacent_to(blade, e))
        foe = c.choose(near, "who the sword cuts") if near else None
        if foe is not None and c.strike(on=foe, from_=blade):
            c.damage("1d10", c.int_mod, dtype=DamageType.FORCE, on=foe)

    conj = c.world.get(blade, Conjuration)
    c.on_sustain(c.world.effects.live.get(conj.effect) if conj else None, again)


@power(
    "p480",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING, Keyword.POISON],
    attack=Attack(INT, vs=REF),
)
def p480(c: Cast) -> None:
    """"Slowed and takes ongoing 5 poison (save ends both)" is one effect and
    one saving throw, which is what `c.condition`'s `ongoing` is for."""
    if c.strike():
        c.damage("2d12", c.int_mod, dtype=DamageType.LIGHTNING)
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )
    else:
        c.half_damage("2d12", c.int_mod, dtype=DamageType.LIGHTNING)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p722",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.CONJURATION],
)
def p722(c: Cast) -> None:
    """The bite inside the wall is `c.burns`, which is that sentence exactly
    -- entering, starting there, and the once-per-turn latch. The bite for
    standing beside it is a start of turn and nothing else, so it is its own
    watch, and it leaves out whoever is *in* the wall: that creature has
    already been bitten by the heavier line.
    """
    anchors = sorted(
        sq for sq in spread({c.here}, 10) if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, "where the wall stands")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-4, 4)]
    squares_ = [sq for sq in run if c.world.grid.inside(sq)]
    if not squares_:
        return
    wall = c.zone(
        squares_,
        label=c.ref,
        until=When.SUSTAIN,
        sustain=MINOR,
        difficult=True,
        blocks_sight=True,
    )
    c.burns(wall, f"3d6+{c.int_mod}", DamageType.FIRE)
    beside = spread(frozenset(squares_), 1) - frozenset(squares_)

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor in c.world.zones.occupants(wall):
            return
        if ev.actor in c.in_squares(beside):
            c.damage("1d6", c.int_mod, dtype=DamageType.FIRE, on=ev.actor)

    held = c.world.get(wall, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.append(c.world.bus.on(TurnStart, dawn))
    c.note(
        f"{c.ref}: each square of movement through the wall should cost 3 extra, "
        "and difficult terrain is one"
    )
