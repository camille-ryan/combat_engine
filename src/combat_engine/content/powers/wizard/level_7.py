"""Wizard, level 7: the encounter attacks.

Three evocations with nothing to explain and one that leaves a zone behind.
The zone's teeth bite at the start of a turn and nowhere else, so they are a
`TurnStart` watch rather than `c.hazard` or `c.burns` -- both of those also
catch whoever walks in, which is a clause this row does not print. "Only
once per turn" comes free with that: there is one turn start per turn.

The rows printed in the later books follow. Two of them fold in a **second
printed stanza** -- `p13987`'s zone lives exactly as long as its own
immobilisation, and `p13988`'s reaction is hung on the conjuration it makes,
so the attack the stanza prints actually happens and stops when the twin does.
Neither is declared as a second ref: the stanza has no id of its own.

"Ends its turn in the zone" is **not** what `c.burns` says -- that is entering
and starting -- so the rows printing it write a `TurnEnd` watch and hang it on
the zone's or the conjuration's own effect.

Three riders have nothing to read and are dropped with a line each: an
implement's enhancement bonus (`Gear` records none), the Tome of Binding on
`p5806` (no such class feature exists), and treating an enemy as an ally for
flanking on `p3221` (flanking asks which side a creature is on and there is no
way to answer differently for one attack).
"""

from __future__ import annotations

from combat_engine.engine import (
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    MeleeOrRanged,
    MoveEnd,
    Position,
    Powers,
    Ranged,
    Relation,
    SavingThrow,
    TurnEnd,
    TurnStart,
    UpTo,
    When,
    Window,
    distance,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.movement import place
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1430",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p1430(c: Cast) -> None:
    """"Lightly obscured" is concealment, which this engine keeps no state
    for -- it is a -2 an attacker takes, and there is no way to hang one on a
    square rather than on a creature -- so the zone carries its cold and
    nothing else. `blocks_sight` would be the wrong word for it: that is a
    wall, not a haze.
    """
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, until=When.EONT)

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.world.zones.occupants(zone):
            return
        c.flat(c.int_mod, dtype=DamageType.COLD, on=ev.actor)

    c.watch(TurnStart, dawn, until=When.EONT, label=c.ref)
    c.note(f"{c.ref}: the zone is lightly obscured, and there is no concealment here")


@power(
    "p189",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p189(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", c.int_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("3d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p251",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p251(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)


@power(
    "p454",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=FORT),
)
def p454(c: Cast) -> None:
    """The miss line shoves it just as far; only the fall is a hit rider."""
    if c.strike():
        c.damage("2d10", c.int_mod, dtype=DamageType.FORCE)
        c.push(3)
        c.prone()
    else:
        c.push(3)


@power(
    "p10146",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p10146(c: Cast) -> None:
    """The slide happens either way; only the hold and the turned blade are
    hit riders. The printed bonus to the granted swing is the implement's
    enhancement, and `Gear` records none, so it is nought rather than guessed.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.slide(3)
        return
    c.slide(3)
    c.immobilized(until=When.EONT)

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == victim or ev.actor not in c.enemies():
            return
        if c.adjacent_to(victim, ev.actor):
            c.grant_attack(victim, on=ev.actor)

    c.watch(TurnStart, dawn, until=When.EONT, on=victim, label=c.ref)


@power(
    "p10421",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CLOSE, Keyword.FORCE],
    attack=Attack(INT, vs=FORT),
)
def p10421(c: Cast) -> None:
    """"Pushed to a space outside the burst" is however far that takes, which
    is measured rather than fixed: a creature in the caster's face is shoved
    four squares and one at the rim is shoved one."""
    if not c.strike():
        return
    c.damage("2d4", c.int_mod, dtype=DamageType.FORCE)
    c.push(max(1, 4 - c.distance()))


@power(
    "p11036",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.ACID, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p11036(c: Cast) -> None:
    """The heavier die is for a burst that caught exactly one creature, which
    is read off the target list rather than off what happened to be hit."""
    dice = "3d8" if len(c.targets) == 1 else "2d8"
    if c.strike():
        c.damage(dice, c.int_mod, dtype=DamageType.ACID)
    if not c.first:
        return
    area = c.area()
    if area:
        c.hazard(area, c.int_mod, DamageType.ACID, label=c.ref, until=When.EONT)


@power(
    "p12548",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.CLOSE,
        Keyword.FIRE,
        Keyword.TELEPORTATION,
    ],
    attack=Attack(INT, vs=REF),
)
def p12548(c: Cast) -> None:
    """"Cannot see anything farther than 3 squares" is everything beyond three
    squares being unseen *by that creature*, which is `HIDDEN_FROM` pointed the
    other way round. The set is worked out once, where the printed line would
    keep up with everybody walking; saying so is cheaper than recomputing it on
    every step for a rider that lasts one round.

    The teleport is an Effect line and belongs after the burst has been rolled,
    or the remaining targets would be measured from wherever the caster landed.
    """
    victim = c.target
    if victim is not None and c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FIRE)
        where = c.world.get(victim, Position)
        pairs = []
        for other in (*c.enemies(), *c.allies(), c.me):
            pos = c.world.get(other, Position)
            if other == victim or pos is None or where is None:
                continue
            if distance(where.square, pos.square) > 3:
                pairs.append((Relation.HIDDEN_FROM, other, victim))
        if pairs:
            c.world.effects.apply(
                victim, c.me, When.EONT, label=f"{c.ref} short sight", relations=pairs
            )
    if c.last:
        c.teleport(5)


@power(
    "p12745",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.AREA, Keyword.FEAR, Keyword.ILLUSION],
)
def p12745(c: Cast) -> None:
    """No attack roll: the whole row is its Effect line.

    The saving throw is a bare one -- nothing is being shaken off, so `c.save`
    has no effect to answer -- and is therefore rolled and announced here so a
    row that meddles with saves still sees it. Turning the blow aside is
    `ev.target` on the declaration, which `resolve.attack` reads back; the
    extra five is a one-shot damage bonus gated on the new victim, which is
    exactly "if it hits one of its allies".
    """
    victim = c.target
    if victim is None:
        return
    c.slowed(until=When.EONT)

    def wavers(ev: AttackDeclared) -> None:
        if ev.attacker != victim:
            return
        roll = c.world.rng.d20().total
        rolled = c.world.bus.emit(
            SavingThrow(
                actor=victim, against=c.ref, natural=roll, bonus=0, saved=roll >= 10
            )
        )
        if rolled.cancelled or rolled.saved:
            return
        others = [x for x in c.within(5, of=victim) if x not in (victim, ev.target)]
        picked = c.choose(sorted(others), f"{c.ref}: who the blow finds instead")
        if picked is None:
            return
        if picked in c.enemies():
            c.bonus(
                "damage", 5, on=victim, until=When.EOT, once=True,
                when=lambda ctx: ctx.get("target") == picked,
            )
        ev.target = picked

    c.watch(
        AttackDeclared, wavers, until=When.EONT, window=Window.BEFORE,
        on=victim, once=True, label=c.ref,
    )


@power(
    "p13987",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p13987(c: Cast) -> None:
    """The zone lasts exactly as long as the hold that made it, so it is torn
    down from the hold's `on_end` rather than given a duration of its own.

    "The power is not expended" is `Powers.unuse`, the same door the Reliable
    keyword goes through, and the +2 for trying again is a gated bonus that
    only pays against the same creature with the same row.

    "Grants combat advantage while in the zone" is granted to the caster's
    side: the relation names beneficiaries and there is no way to say
    "everybody".
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        known = c.world.get(c.me, Powers)
        if known is not None:
            known.unuse(c.ref)
        ref = c.ref
        c.bonus(
            "attack", 2, on=c.me, until=When.EONT,
            when=lambda ctx: ctx.get("target") == victim and ctx.get("power") == ref,
        )
        return

    c.damage("2d6", c.int_mod, dtype=DamageType.NECROTIC)
    held = c.immobilized(until=When.EONT)
    area = spread({c.there}, 2)
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER)
    me = c.me

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(zone):
            c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)

    def exposed(ev: object) -> None:
        for standing in c.world.zones.occupants(zone):
            if standing != me:
                c.grants_advantage(on=standing, until=When.EOTNT, to="allies")

    zone_held = c.world.get(zone, Zone)
    if zone_held is not None and zone_held.effect is not None:
        zone_held.effect.subs.append(c.world.bus.on(TurnEnd, dusk))
    if held is not None:
        held.on_end.append(lambda: c.world.zones.end(zone, "the hold ended"))
    exposed(None)


@power(
    "p13988",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CONJURATION, Keyword.PSYCHIC],
    attack=Attack(INT, vs=WILL),
)
def p13988(c: Cast) -> None:
    """The twin is an Effect line, so it appears whether or not the first blow
    landed. The second printed stanza -- the twin vanishing and striking when
    the target leaves its side or attacks -- is folded in as a pair of watches
    on the conjuration's own effect, spent once between them, because a stanza
    with no id of its own cannot be a second row.

    The -2 is gated on adjacency rather than reapplied as the two move, which
    is the one way a modifier can follow a position.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.PSYCHIC)
    room = [
        sq
        for sq in sorted(spread({c.there}, 1) - {c.there})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if not room:
        return
    twin = c.conjure(room[0], label=c.ref, until=When.EONT)
    if not twin:
        return
    c.penalty(
        "attack", 2, on=victim, until=When.EONT,
        when=lambda _ctx: c.adjacent_to(twin, victim),
    )
    spent: list[bool] = []

    def pounce(_ev: object) -> None:
        stands = c.world.get(victim, Position)
        if spent or stands is None or c.world.get(twin, Position) is None:
            return
        spent.append(True)
        beside = [
            sq
            for sq in sorted(spread(stands.squares, 1))
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
        ]
        if beside:
            place(c.world, twin, beside[0])
        if c.strike(on=victim, from_=twin):
            c.flat(5 + c.int_mod, dtype=DamageType.PSYCHIC, on=victim)
            c.dazed(on=victim, until=When.EOTNT)
        conj = c.world.get(twin, Conjuration)
        vanish = c.world.effects.live.get(conj.effect) if conj else None
        if vanish is not None:
            c.world.effects.end(vanish, "the twin vanished")

    def walked(ev: MoveEnd) -> None:
        if ev.actor == victim:
            pounce(ev)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == victim:
            pounce(ev)

    conj = c.world.get(twin, Conjuration)
    watching = c.world.effects.live.get(conj.effect) if conj else None
    if watching is not None:
        watching.subs.extend(
            [
                c.world.bus.on(MoveEnd, walked),
                c.world.bus.on(AttackDeclared, swung),
            ]
        )


@power(
    "p14557",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CONJURATION, Keyword.RADIANT],
    attack=Attack(INT, vs=WILL),
)
def p14557(c: Cast) -> None:
    """The sprite's -4 is laid on every enemy and gated on standing beside it,
    which is the only way a modifier keeps up with two things moving."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.RADIANT)
        c.slide(2)
        foes = sorted(x for x in c.enemies() if x != victim)
        mark = c.choose(foes, f"{c.ref}: who the target swings at") if foes else None
        if mark is not None:
            c.grant_attack(victim, on=mark)
    room = [
        sq
        for sq in sorted(spread({c.there}, 1) - {c.there})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if not room:
        return
    sprite = c.conjure(room[0], label=c.ref, until=When.EONT)
    if not sprite:
        return
    for foe in c.enemies():
        c.penalty(
            "attack", 4, on=foe, until=When.EONT,
            when=lambda _ctx, who=foe: c.adjacent_to(sprite, who),
        )


@power(
    "p14558",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(INT, vs=REF),
)
def p14558(c: Cast) -> None:
    """The rider is an Effect line and stands whether or not the dart found
    anything."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d10", c.int_mod, dtype=DamageType.POISON)

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == victim or ev.actor not in c.enemies():
            return
        if c.adjacent_to(victim, ev.actor):
            c.flat(5, dtype=DamageType.POISON, on=ev.actor)

    c.watch(TurnEnd, dusk, until=When.EONT, on=victim, label=c.ref)


@power(
    "p2816",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=WILL),
)
def p2816(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.damage("1d6", c.int_mod)
        c.teleport(3, who=victim)
        c.slowed(until=When.EONT)


@power(
    "p3221",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=20),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p3221(c: Cast) -> None:
    """Flanking asks which side a creature is on, and there is no way to
    answer differently for one attack, so treating the target as an ally for
    flanking is the clause this row loses."""
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.PSYCHIC)
    if c.first:
        c.note(f"{c.ref}: your side may also flank with the target, and flanking is by team")


@power(
    "p4028",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CONJURATION, Keyword.ACID],
    attack=Attack(INT, vs=FORT),
)
def p4028(c: Cast) -> None:
    """The worms are an Effect line and arrive before the roll. They go in a
    free square beside the target rather than in its own, which is occupied by
    definition -- a conjuration takes up its space.
    """
    victim = c.target
    if victim is None:
        return
    room = [
        sq
        for sq in sorted(spread({c.there}, 1) - {c.there})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    worms = c.conjure(room[0], label=c.ref, until=When.EONT) if room else 0
    if not c.strike():
        return
    c.damage("2d8", c.int_mod, dtype=DamageType.ACID)
    if not worms:
        return

    def dusk(ev: TurnEnd) -> None:
        pos = c.world.get(worms, Position)
        if ev.ghost or ev.actor != victim or pos is None:
            return
        if victim in c.in_squares(spread(pos.squares, 2)):
            c.flat(10, dtype=DamageType.ACID, on=victim)

    conj = c.world.get(worms, Conjuration)
    held = c.world.effects.live.get(conj.effect) if conj else None
    if held is not None:
        held.subs.append(c.world.bus.on(TurnEnd, dusk))


@power(
    "p5806",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CONJURATION, Keyword.ACID],
    attack=Attack(INT, vs=REF),
)
def p5806(c: Cast) -> None:
    """The ooze fills the target's own space and travels with it, which is an
    aura of radius nought hung on the target rather than a conjuration: a
    conjuration occupies a square and cannot share one.

    The Tome of Binding rider names a class feature that does not exist here.
    """
    victim = c.target
    if victim is None:
        return
    c.aura(0, label=c.ref, until=When.EONT, on=victim)
    if not c.strike():
        return
    c.damage("4d8", c.int_mod, dtype=DamageType.ACID)

    def bite(_ev: object) -> None:
        c.flat(c.con_mod, dtype=DamageType.ACID, on=victim)

    c.on_attack(bite, by=victim, until=When.EONT, label=f"{c.ref} bite")


@power(
    "p6903",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM, Keyword.THUNDER],
    attack=Attack(INT, vs=WILL),
)
def p6903(c: Cast) -> None:
    """"Each enemy within 3 squares of it" is measured from the target, and
    the target's enemies are the caster's own side."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d6", c.int_mod, dtype=DamageType.THUNDER)

    def burst(_ev: object) -> None:
        c.flat(5, dtype=DamageType.THUNDER, on=victim)
        for near in c.within(3, of=victim, side="ally"):
            c.flat(5, dtype=DamageType.THUNDER, on=near)

    c.on_attack(burst, by=victim, until=When.EONT, once=True, label=f"{c.ref} recoil")


@power(
    "p7510",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=FORT),
)
def p7510(c: Cast) -> None:
    """"Leaves the space it currently occupies" is the square it was standing
    in when the blow landed, so the square is remembered and compared rather
    than any move counting."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d10", c.int_mod, dtype=DamageType.THUNDER)
    stood = c.there

    def left(ev: MoveEnd) -> None:
        if ev.actor == victim and ev.at != stood:
            c.damage("1d10", c.int_mod, dtype=DamageType.THUNDER, on=victim)

    c.watch(MoveEnd, left, until=When.SONT, on=victim, once=True, label=c.ref)
