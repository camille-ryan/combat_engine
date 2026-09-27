"""Warlock, level 5: the dailies from the books after the first, part one.

The conventions `level_1_b.py` settles hold here: two legs of pact to ask
for and the rest named in a comment, one `dtype` for a line printing two,
and no refund for "the power is not expended".

Two more, both of which this level leans on hard.

**"The target is subject to <something> (save ends), and while it lasts you
can ..."** is a save-ends effect carrying a `sustain_cost`, which
`actions._sustaining` offers once a round and never on the turn it was laid
-- the arrangement `level_5.py`'s own docstring sets out -- with
`c.on_sustain` as the payout half.

**A secondary power printed beneath a primary** has a ref of its own after
all -- the importer mints one with a letter on the end -- and those live in
`second_card.py`. So a primary leaves only what it puts on the board, and
the secondary is offered with the action and trigger it prints rather than
armed here as a watch that fires without asking.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    CON,
    DAILY,
    EACH_CREATURE,
    FORT,
    INT,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Mod,
    Ranged,
    TurnStart,
    When,
    get,
    power,
)
from combat_engine.engine.events import MoveEnd

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _melee_hit_by(c: Cast, who: int, ev: Hit) -> bool:
    """Was that a melee row, swung by that creature?"""
    if ev.attacker != who:
        return False
    p = get(ev.power)
    return p is not None and p.reach.kind == "melee"


@power(
    "p10381",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CON, vs=FORT),
)
def p10381(c: Cast) -> None:
    if c.target is None or not c.strike():
        return
    c.damage("2d10", c.con_mod, dtype=DamageType.NECROTIC)
    c.condition(Condition.DEAFENED, until=When.ENCOUNTER)
    if c.build("infernal"):
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p10382",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
)
def p10382(c: Cast) -> None:
    """`c.form` shapes the caster and nothing else, so the ally's new shape is
    written as what it is *for*: a bonus to its attacks, fire on its melee
    blows, and the printed minor action to put it away, all on one effect so
    that dismissing it takes the whole thing. Darkvision has no home.
    """
    friend = c.target
    if friend is None or not c.may("take the shape"):
        return
    shape = c.world.effects.apply(
        friend,
        c.me,
        When.ENCOUNTER,
        label=c.ref,
        mods=[(friend, Mod(what="attack", value=2, kind="power", label=c.ref))],
        drop_cost=MINOR,
    )

    def scorch(ev: Hit) -> None:
        if _melee_hit_by(c, friend, ev):
            c.flat(c.roll("2d8"), dtype=DamageType.FIRE, on=ev.target)

    shape.subs.append(c.world.bus.on(Hit, scorch))
    if c.build("infernal"):
        ward = c.resist(5 + c.level // 2, DamageType.FIRE, on=friend)
        if ward is not None:
            shape.on_end.append(lambda: c.world.effects.end(ward, "the shape ended"))


@power(
    "p11304",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=FORT),
)
def p11304(c: Cast) -> None:
    """"First Failed Saving Throw" is `escalate`, which runs on exactly that.
    The vestige pact and the augment it grants have no leg to ask for."""
    victim = c.target
    if not c.strike():
        c.half_damage("2d6", c.con_mod)
        c.slowed(until=When.SAVE_ENDS)
        return
    c.damage("2d6", c.con_mod)

    def collapse(_eff: Effect) -> None:
        c.unconscious(on=victim)

    c.condition(until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED), escalate=collapse)


@power(
    "p12892",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.FEAR],
    attack=Attack(CHA, vs=REF),
)
def p12892(c: Cast) -> None:
    """The Effect line is the damage and lands either way; the hit is what
    sets the target alight and drags it about at the start of its turns."""
    victim = c.target
    landed = c.strike()
    c.damage("1d10", c.cha_mod, dtype=DamageType.FIRE)
    if not landed or victim is None:
        return
    flames = c.ongoing(5, DamageType.FIRE)
    if flames is None:
        return

    def dragged(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim:
            return
        c.slide(max(1, c.int_mod), on=victim)
        for foe in c.within(1, of=victim, side="enemy"):
            if foe != victim:
                c.ongoing(5, DamageType.FIRE, on=foe)

    flames.subs.append(c.world.bus.on(TurnStart, dragged))


@power(
    "p13642",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.RADIANT],
)
def p13642(c: Cast) -> None:
    """The ward is the primary; the reaction printed under it is `p13642b`,
    offered rather than armed now that it has a ref, which is what lets the
    holder decline it. The shield bonus is its own `kind`, which is how it
    fails to stack with a real shield. The hold this leaves carries the
    row's own name, which is what the secondary's Requirement reads.
    """
    c.world.effects.apply(
        c.me,
        c.me,
        When.ENCOUNTER,
        label=c.ref,
        mods=[
            (c.me, Mod(what="ac", value=2, kind="shield", label=c.ref)),
            (c.me, Mod(what="ref", value=2, kind="shield", label=c.ref)),
        ],
    )


@power(
    "p13644",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p13644(c: Cast) -> None:
    """"Save ends both" is one hold carrying the condition and the burn, so
    the single throw answers the pair."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.POISON)
        c.condition(
            Condition.DAZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.POISON)
        )
    else:
        c.half_damage("1d8", c.cha_mod, dtype=DamageType.POISON)
        c.grants_advantage(to="team", until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.POISON)


@power(
    "p13645",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p13645(c: Cast) -> None:
    if c.target is None:
        return
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.COLD)
        c.prone()
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.COLD)
    c.slide(3)  # an Effect line: every target moves, hit or not


@power(
    "p13882",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p13882(c: Cast) -> None:
    # "Miss: the power is not expended" has no method; nothing gives a use
    # back, so the miss is simply a miss.
    if c.strike():
        c.damage("3d10", c.cha_mod, dtype=DamageType.COLD)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p13883",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(CHA, vs=REF),
)
def p13883(c: Cast) -> None:
    """The secondary is `p13883b`, an opportunity attack of its own gated on
    this zone standing -- including the "or ends its turn there" half, which
    was unwritten here for want of an event and is asked of `TurnEnd`.
    """
    if c.target is not None:
        if c.strike():
            c.damage("1d10", c.cha_mod, dtype=DamageType.NECROTIC)
            c.slowed(until=When.SAVE_ENDS)
        else:
            c.half_damage("1d10", c.cha_mod, dtype=DamageType.NECROTIC)
    if not c.last:
        return
    area = c.area()
    if not area:
        return
    c.zone(area, label=c.ref, until=When.ENCOUNTER)


@power(
    "p13955",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=FORT),
)
def p13955(c: Cast) -> None:
    if c.target is not None:
        if c.strike():
            c.damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
            c.blinded(until=When.SAVE_ENDS)
        else:
            c.half_damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
    if not c.last:
        return
    for near in c.within(1):
        c.flat(10, dtype=DamageType.NECROTIC, on=near)
    room = sorted(
        sq
        for sq in c.area()
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if room:
        where = c.choose(room, f"{c.ref}: where the dark puts you")
        if where is not None:
            c.teleport(20, to=where)


@power(
    "p1883",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.RELIABLE],
    attack=Attack(CHA, vs=WILL),
)
def p1883(c: Cast) -> None:
    # The dark pact rider -- a penalty to the saves against the burn -- has
    # no leg to ask for.
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
        c.ongoing(10, DamageType.NECROTIC)


@power(
    "p3406",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=REF),
)
def p3406(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.FORCE)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.FORCE)


@power(
    "p4282",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.FEAR],
    attack=Attack(INT, vs=REF, plus=2),
)
def p4282(c: Cast) -> None:
    """The printed check against falling has no die to roll here, so the
    target simply falls -- and keeps falling at the start of each of its
    turns until it saves, which is what the repeated check amounts to.
    """
    victim = c.target
    if not c.strike():
        c.half_damage("3d10", c.int_mod)
        c.prone()
        return
    c.damage("3d10", c.int_mod)
    c.prone()
    if victim is None:
        return
    footing = c.effect(f"{c.ref}: no footing")
    if footing is None:
        return

    def trip(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == victim:
            c.prone(on=victim)

    footing.subs.append(c.world.bus.on(TurnStart, trip))


@power(
    "p5913",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p5913(c: Cast) -> None:
    if c.target is None:
        return
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
        c.vulnerable(5, DamageType.FIRE)
        c.vulnerable(5, DamageType.LIGHTNING)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.FIRE)


@power(
    "p5914",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p5914(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.pull(4)
    else:
        c.half_damage("2d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.pull(2)
    if victim is None:
        return
    leash = c.world.effects.apply(
        c.me, c.me, When.ENCOUNTER, label=c.ref, sustain_cost=MINOR
    )
    c.on_sustain(leash, lambda: c.pull(2, on=victim))


@power(
    "p5915",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p5915(c: Cast) -> None:
    """"Willingly moves" cannot be told from being shoved: `MoveEnd` says
    who arrived where and not who chose it."""
    victim = c.target
    if c.strike():
        c.damage("3d6", c.cha_mod, dtype=DamageType.ACID)
        c.grants_advantage(to="team", until=When.SAVE_ENDS)
    else:
        c.half_damage("3d6", c.cha_mod, dtype=DamageType.ACID)
    if victim is None or c.int_mod <= 0:
        return
    stirred = [False]

    def stepped(ev: MoveEnd) -> None:
        if stirred[0] or ev.actor != victim:
            return
        stirred[0] = True
        c.ongoing(c.int_mod, DamageType.POISON, on=victim)

    c.watch(MoveEnd, stepped, until=When.EOTNT)
