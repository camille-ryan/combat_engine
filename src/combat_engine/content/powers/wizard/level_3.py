"""Wizard, level 3: the encounter attacks.

Four evocations and nothing clever: each is an area or a pair of targets,
one attack roll per creature, and a rider the engine already has a word for.

The rows printed in the later books follow below, and they are less tidy.
Three of them leave ground behind whose rider is *not* the "enters or starts
its turn there" latch `c.hazard` carries, so each writes its own listener and
hangs it on the zone's own effect -- `until=When.SUSTAIN` on a `c.watch` makes
a hold nobody can sustain, and only a zone, an aura, a hazard or a conjuration
carries a sustain cost.

`p4020` prints a second stanza with its own Requirement and Trigger. It is
folded into the one row rather than declared as a second ref: the pattern is
conjured, and the attack the stanza prints hangs on the conjuration's own
effect, so it actually happens.

**The same `Cast` is reused for every target of one use** -- `index` and
`target` are reassigned round the loop -- so nothing a body closes over
survives into the next target. `p4022` finds its beetles again by their label
for that reason.
"""

from __future__ import annotations

from combat_engine.engine import (
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
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
    Defences,
    Dropped,
    Effect,
    Hit,
    Keyword,
    Position,
    Ranged,
    Square,
    TurnStart,
    UpTo,
    When,
    Window,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.events import OpportunityWindow, ZoneEntered, ZoneExited
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1530",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p1530(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)


@power(
    "p173",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(INT, vs=WILL),
)
def p173(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.RADIANT)
        c.dazed()


@power(
    "p2272",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=FORT),
)
def p2272(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)


@power(
    "p435",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=REF),
)
def p435(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.COLD)
        c.immobilized()
    else:
        # The miss line still holds the target where it stands, slowly.
        c.slowed()


@power(
    "p10070",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.RADIANT, Keyword.ZONE],
)
def p10070(c: Cast) -> None:
    """Blindness here is a property of standing in the light rather than a
    duration, so it is applied on the way in and taken back on the way out --
    and a zone ending announces everyone leaving it, which unwinds the rest.

    Doubling a vulnerability is read off `Defences` at the start of a turn; a
    creature with no radiant vulnerability takes nothing, as printed.
    """
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT)
    dazzled: dict[int, Effect] = {}

    def enter(who: int) -> None:
        if who in dazzled:
            return
        held = c.blinded(until=When.ENCOUNTER, on=who)
        if held is not None:
            dazzled[who] = held

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            enter(ev.actor)

    def walked_out(ev: ZoneExited) -> None:
        held = dazzled.pop(ev.actor, None)
        if ev.zone == zone and held is not None:
            c.world.effects.end(held, "out of the light")

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.world.zones.occupants(zone):
            return
        defences = c.world.get(ev.actor, Defences)
        weak = defences.vulnerable.get(DamageType.RADIANT, 0) if defences else 0
        if weak:
            c.flat(weak * 2, dtype=DamageType.RADIANT, on=ev.actor)

    held_zone = c.world.get(zone, Zone)
    if held_zone is not None and held_zone.effect is not None:
        held_zone.effect.subs.extend(
            [
                c.world.bus.on(ZoneEntered, walked_in),
                c.world.bus.on(ZoneExited, walked_out),
                c.world.bus.on(TurnStart, dawn),
            ]
        )
    for standing in c.world.zones.occupants(zone):
        enter(standing)


@power(
    "p10144",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
)
def p10144(c: Cast) -> None:
    """No attack roll: the damage simply happens. `Gear` records no
    enhancement bonus, so the implement's share of the printed total is the
    one term left off."""
    c.flat(5 + c.int_mod, dtype=DamageType.FORCE)


@power(
    "p10419",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.ACID],
    attack=Attack(INT, vs=FORT),
)
def p10419(c: Cast) -> None:
    """The "Active Familiar" rider has nothing to read: nothing in the engine
    is a familiar, so there is no square to measure three from."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.ACID)


@power(
    "p11033",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p11033(c: Cast) -> None:
    """The extra five is one target's, chosen once for the whole burst, and it
    is an Effect line -- it happens whether or not anything was hit."""
    if c.first:
        pick = c.choose(sorted(c.targets), f"{c.ref}: who takes the extra fire")
        if pick is not None:
            c.flat(5, dtype=DamageType.FIRE, on=pick)
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p12743",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.AREA, Keyword.CHARM],
)
def p12743(c: Cast) -> None:
    """No attack roll at all: the whole row is the Effect line.

    Barring opportunity actions is a veto on the window, hung on the same hold
    as the slow so one thing ends both. Barring *immediate* actions has no gate
    -- `Rules.no_reactions` is reachable only through daze and stun, and both
    carry riders this row does not print.
    """
    victim = c.target
    if victim is None:
        return
    held = c.slowed(until=When.EONT)
    if held is None:
        return

    def refuse(ev: OpportunityWindow) -> None:
        if ev.actor == victim:
            ev.cancel("cannot take opportunity actions")

    held.subs.append(
        c.world.bus.on(OpportunityWindow, refuse, window=Window.BEFORE, owner=c.me)
    )
    if c.first:
        c.note(f"{c.ref}: immediate actions are also barred, and nothing gates those")


@power(
    "p13982",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p13982(c: Cast) -> None:
    """Only *entering* the zone bites, which is not the sentence `c.burns`
    carries -- that is entering and starting a turn there -- so the latch is
    written out here.

    The bite grows by two for each creature the attack fells, and the attack
    is still being rolled when the zone is laid. The tally is therefore a
    `Dropped` watch over the caster's own turn, restricted to the creatures
    this burst caught, and the number is read when the zone actually bites.
    """
    if not c.first:
        if c.strike():
            c.damage("2d8", c.int_mod)
        return

    area = c.area()
    victims = list(c.targets)
    bite = [5]

    def tally(ev: Dropped) -> None:
        if ev.actor in victims:
            bite[0] += 2

    c.watch(Dropped, tally, until=When.EOT, on=c.me, label=f"{c.ref} tally")

    if area:
        zone = c.zone(area, label=c.ref, until=When.EONT)
        struck: dict[int, int] = {}
        inside: dict[int, Effect] = {}

        def penalise(who: int) -> None:
            if who in inside:
                return
            held = c.penalty("attack", 2, on=who, until=When.ENCOUNTER)
            if held is not None:
                inside[who] = held

        def walked_in(ev: ZoneEntered) -> None:
            if ev.zone != zone:
                return
            penalise(ev.actor)
            if struck.get(ev.actor) != c.world.round:
                struck[ev.actor] = c.world.round
                c.flat(bite[0], on=ev.actor)

        def walked_out(ev: ZoneExited) -> None:
            held = inside.pop(ev.actor, None)
            if ev.zone == zone and held is not None:
                c.world.effects.end(held, "left the zone")

        held_zone = c.world.get(zone, Zone)
        if held_zone is not None and held_zone.effect is not None:
            held_zone.effect.subs.extend(
                [
                    c.world.bus.on(ZoneEntered, walked_in),
                    c.world.bus.on(ZoneExited, walked_out),
                ]
            )
        for standing in c.world.zones.occupants(zone):
            penalise(standing)

    if c.strike():
        c.damage("2d8", c.int_mod)


@power(
    "p13983",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CLOSE, Keyword.PSYCHIC],
    attack=Attack(INT, vs=WILL),
)
def p13983(c: Cast) -> None:
    """The concealment half has no expression -- the engine keeps no state for
    it -- so the row is the damage and the thorns."""
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.PSYCHIC)
    if not c.first:
        return
    me = c.me

    def thorns(ev: Hit) -> None:
        if ev.target == me and c.adjacent(to=ev.attacker):
            c.flat(5, dtype=DamageType.PSYCHIC, on=ev.attacker)

    c.watch(Hit, thorns, until=When.EONT, on=me, label=c.ref)
    c.note(f"{c.ref}: you also gain partial concealment, and there is none here")


@power(
    "p14549",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CLOSE, Keyword.COLD, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p14549(c: Cast) -> None:
    """"Heavily obscured to creatures other than you" is `blocks_sight`, which
    is not selective: the fog hides the caster's view as well as everybody
    else's. The slow is a start of turn and leaves the caster out, as printed.
    """
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.COLD)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT, blocks_sight=True)
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(zone):
            c.slowed(until=When.EOTNT, on=ev.actor)

    held = c.world.get(zone, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.append(c.world.bus.on(TurnStart, dawn))


@power(
    "p14550",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CLOSE, Keyword.NECROTIC, Keyword.FEAR],
    attack=Attack(INT, vs=WILL),
)
def p14550(c: Cast) -> None:
    """The Will penalty is an Effect line, so it lands on every target whether
    the attack found it or not."""
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.NECROTIC)
        c.penalty("attack", 2, until=When.EONT)
    c.penalty(WILL, 2, until=When.EONT)


@power(
    "p3218",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p3218(c: Cast) -> None:
    if c.strike():
        c.immobilized()
        c.penalty("attack", 4, until=When.EONT)
    else:
        c.slowed()


@power(
    "p4020",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ILLUSION, Keyword.CONJURATION],
    attack=Attack(INT, vs=WILL),
)
def p4020(c: Cast) -> None:
    """The second printed stanza -- an opportunity action when an enemy starts
    its turn within 3 squares of the pattern -- is folded in rather than
    declared as its own ref: it hangs on the conjuration's own effect, so the
    attack it prints actually happens and stops when the pattern does.

    The pattern rolls the wizard's numbers from its own square, which is what
    `from_` is for, and the pull is anchored on it rather than on the caster.
    """
    room = [
        sq
        for sq in sorted(spread({c.here}, 10) - {c.here})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    # Ranked by what each square would catch. With no decider installed the
    # first option is the answer, and the lowest-sorted square on the board
    # is reliably the one nothing is standing near.
    room.sort(key=lambda sq: (-len(c.in_squares(spread({sq}, 3), side="enemy")), sq))
    where = c.choose(room, f"{c.ref}: where the pattern hangs")
    if where is None:
        return
    pattern = c.conjure(where, label=c.ref, until=When.EONT)
    if not pattern:
        return

    def dawn(ev: TurnStart) -> None:
        pos = c.world.get(pattern, Position)
        if ev.ghost or pos is None or ev.actor not in c.enemies():
            return
        if ev.actor not in c.in_squares(spread(pos.squares, 3)):
            return
        if c.strike(on=ev.actor, from_=pattern):
            c.pull(3, on=ev.actor, anchor=pos.square)
            c.slowed(on=ev.actor, until=When.EONT)

    conj = c.world.get(pattern, Conjuration)
    held = c.world.effects.live.get(conj.effect) if conj else None
    if held is not None:
        held.subs.append(c.world.bus.on(TurnStart, dawn))


@power(
    "p4022",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.LIGHTNING, Keyword.CONJURATION],
    attack=Attack(INT, vs=FORT),
)
def p4022(c: Cast) -> None:
    """One beetle per creature hit, and a single watch for all of them.

    The beetles are found again by their label rather than kept in a list: the
    same `Cast` is reused for every target of one use, so nothing this body
    closes over survives into the next call. The watch is armed on the first
    target whether or not anything is hit, and does nothing while there are no
    beetles to stand beside.

    A beetle goes in a free square beside its target rather than in the
    target's own square, which is occupied by definition.
    """
    if c.first:
        me, ref = c.me, c.ref

        def dawn(ev: TurnStart) -> None:
            if ev.ghost or ev.actor not in c.enemies():
                return
            near: set[Square] = set()
            for eid, conj in c.world.each(Conjuration):
                if conj.ref != ref or conj.by != me:
                    continue
                pos = c.world.get(eid, Position)
                if pos is not None:
                    near |= spread(pos.squares, 1)
            if near and ev.actor in c.in_squares(near):
                c.flat(c.con_mod, dtype=DamageType.LIGHTNING, on=ev.actor)

        c.watch(TurnStart, dawn, until=When.EONT, on=me, label=f"{c.ref} beetles")

    if not c.strike():
        return
    c.damage("1d6", c.int_mod, dtype=DamageType.LIGHTNING)
    room = [
        sq
        for sq in sorted(spread({c.there}, 1))
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    # Every one of these is a square of the target's own space or beside it,
    # so the choice between them is only which enemies the beetle ends up
    # standing near -- and with no decider installed the first is taken.
    room.sort(key=lambda sq: (-len(c.in_squares(spread({sq}, 1), side="enemy")), sq))
    if room:
        c.conjure(room[0], label=c.ref, until=When.EONT)


@power(
    "p4025",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=REF),
)
def p4025(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.COLD)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p5804",
    level=3,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(INT, vs=FORT),
)
def p5804(c: Cast) -> None:
    """The board is flat, so being lifted two squares has nowhere to go. What
    the height was *for* survives in full: dazed, immobilized and granting
    combat advantage until the start of its next turn, when it comes down in
    the space it left."""
    if not c.strike():
        return
    c.damage("2d6", c.int_mod)
    c.condition(Condition.DAZED, Condition.IMMOBILIZED, until=When.SOTNT)
    c.grants_advantage(until=When.SOTNT, to="allies")
    c.note(f"{c.ref}: the target is also held 2 squares up, and the board is flat")
