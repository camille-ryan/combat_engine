"""Wizard, level 9: the daily attacks printed after the first book.

`level_9.py` holds the four that came before; these go in their own file
rather than doubling that one's length.

Four things recur and are decided the same way throughout.

**A second printed stanza with no id of its own.** Several of these rows print
a whole second power -- its own action, its own attack line -- gated on the
first being active. Where the stanza has a *trigger* or a *sustain* to hang
from it is folded in, so the attack it prints actually happens. Where it is
simply "you can use the secondary power as a standard action", there is no
door: `c.grant_row` lends a row by ref and the stanza has no ref. Those rows
are written as the stanza that the declared action line describes, with the
other said out loud in a note.

**Teeth that are not `c.burns`.** That method is "enters, or starts its turn
there, once per turn". A row printing "**ends** its turn there", or one biting
enemies only, writes the latch out and hangs the listeners on the zone's own
effect -- `until=When.SUSTAIN` on a `c.watch` makes a hold nobody can sustain.

**"Cannot leave the zone willingly."** `MoveStart` is the only cancellable
door and it fires before a destination exists, so refusing a walk or a shift
by a held creature standing in the zone also refuses it moving *within* the
zone. That is wider than the printed line and is said in the rows that do it.

**Dual-typed damage.** "Necrotic and poison" is one hit counting as both, and
`DamageType` names one type per blow. The heavier word is used and the other
is noted.

The four summoning rows of this level are absent; see the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    INT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    Condition,
    DamageType,
    Effect,
    Gear,
    Hit,
    Keyword,
    Miss,
    Position,
    Ranged,
    Relation,
    Square,
    TurnEnd,
    When,
    Window,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.events import (
    DamageApplied,
    MoveStart,
    OpportunityWindow,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _tome(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    main = gear.main if gear else None
    return bool(main and ("tome" in main.properties or main.group == "tome"))


@power(
    "p10073",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(INT, vs=REF),
    requires=_tome,
    requires_text="needs a tome in hand",
)
def p10073(c: Cast) -> None:
    """The miss line casts a second daily out of a spellbook, and there is no
    spellbook: a creature's rows are what it knows, with no notion of which of
    them are written down or which were prepared."""
    if c.strike():
        c.damage("4d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.note(f"{c.ref}: a second ranged daily should follow, and there is no spellbook")


@power(
    "p11037",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p11037(c: Cast) -> None:
    """"Each nonprone creature in the burst" is not a filter a `Target` can
    carry, so the targets are everyone and the prone ones are stepped over in
    the body -- which is also what lets the Effect line matter: an ally that
    takes the offer to drop flat is no longer a target by the time the flames
    reach it."""
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me and c.may("drop flat", who=mate):
                c.prone(on=mate)
    victim = c.target
    if victim is None or c.is_(Condition.PRONE, on=victim):
        return
    if c.strike():
        c.damage("3d8", c.int_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("3d8", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p12746",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FEAR, Keyword.ILLUSION],
)
def p12746(c: Cast) -> None:
    """The declared row is the minor action: the haunting itself. The second
    printed stanza is a standard-action attack with no id of its own and no
    trigger or sustain to hang from, so it is noted rather than invented.

    "Another saving throw whenever it is hit by or takes damage from anything
    else" is a watch on the hold, and the damage this row does not deal is
    everything, so any `DamageApplied` against it counts.
    """
    victim = c.target
    if victim is None:
        return
    held = c.effect(f"{c.ref} haunted", until=When.SAVE_ENDS)
    if held is None:
        return

    def refuse(ev: OpportunityWindow) -> None:
        if ev.actor == victim:
            ev.cancel("cannot make opportunity attacks")

    def shaken(ev: DamageApplied) -> None:
        if ev.target == victim and ev.amount > 0 and not held.ended:
            c.world.effects.save(held)

    held.subs.extend(
        [
            c.world.bus.on(
                OpportunityWindow, refuse, window=Window.BEFORE, owner=c.me
            ),
            c.world.bus.on(DamageApplied, shaken, owner=c.me),
        ]
    )
    c.note(f"{c.ref}: the second stanza is a standard-action attack with no id of its own")


@power(
    "p12748",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA],
    attack=Attack(INT, vs=WILL),
)
def p12748(c: Cast) -> None:
    """The allies' half is an Effect line and lands before the roll."""
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate == c.me:
                continue
            c.shift(4, who=mate)
            c.bonus("damage", 4, on=mate, until=When.EONT, kind="power")
    if c.strike():
        c.condition(Condition.DAZED, Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    else:
        c.dazed(until=When.EOTNT)


@power(
    "p13990",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.NECROTIC],
    attack=Attack(INT, vs=FORT),
)
def p13990(c: Cast) -> None:
    """Damage equal to the caster's level, so there are no dice and a critical
    has nothing to maximise -- `c.flat` rather than `c.damage`."""
    if c.strike():
        c.flat(c.level, dtype=DamageType.NECROTIC)
        c.condition(
            Condition.DAZED, Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS
        )
    else:
        c.flat(c.level // 2, dtype=DamageType.NECROTIC)
        c.slowed(until=When.EONT)


@power(
    "p13991",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.AREA,
        Keyword.ILLUSION,
        Keyword.PSYCHIC,
        Keyword.ZONE,
    ],
    attack=Attack(INT, vs=WILL),
)
def p13991(c: Cast) -> None:
    """The zone is an Effect line and is laid before the attack, which is the
    printed order and also what "if the target is already dazed" needs: the
    extra five is read before this row's own daze is applied.

    Refusing to leave is a cancelled `MoveStart`, which is wider than printed
    -- it also stops the creature crossing the zone -- and not seeing out is
    `HIDDEN_FROM` pointed the other way, worked out once rather than kept up
    with as everyone walks.
    """
    if c.first:
        area = c.area()
        if area:
            zone = c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult=True)
            exposed: dict[int, Effect] = {}

            def enter(who: int) -> None:
                if who in exposed:
                    return
                held = c.grants_advantage(on=who, until=When.ENCOUNTER, to="allies")
                if held is not None:
                    exposed[who] = held

            def walked_in(ev: ZoneEntered) -> None:
                if ev.zone == zone:
                    enter(ev.actor)

            def walked_out(ev: ZoneExited) -> None:
                held = exposed.pop(ev.actor, None)
                if ev.zone == zone and held is not None:
                    c.world.effects.end(held, "left the zone")

            standing = c.world.get(zone, Zone)
            if standing is not None and standing.effect is not None:
                standing.effect.subs.extend(
                    [
                        c.world.bus.on(ZoneEntered, walked_in),
                        c.world.bus.on(ZoneExited, walked_out),
                    ]
                )
            for who in c.world.zones.occupants(zone):
                enter(who)

    victim = c.target
    if victim is None:
        return
    already = c.is_(Condition.DAZED, on=victim)
    if not c.strike():
        return
    c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
    if already:
        c.flat(5, dtype=DamageType.PSYCHIC)
    held = c.condition(Condition.DAZED, until=When.SAVE_ENDS)
    if held is None:
        return
    mine = [z for z, zone in c.world.zones.all() if zone.label == c.ref]
    penned = mine[0] if mine else 0

    def refuse(ev: MoveStart) -> None:
        if ev.actor != victim or ev.kind_ not in ("walk", "shift"):
            return
        if penned and victim in c.world.zones.occupants(penned):
            ev.cancel("held by the illusion")

    blind = [
        (Relation.HIDDEN_FROM, other, victim)
        for other in (*c.enemies(), *c.allies(), c.me)
        if penned and other != victim and other not in c.world.zones.occupants(penned)
    ]
    held.relations.extend(blind)
    for kind, src, dst in blind:
        c.world.relations.set(kind, src, dst)
    held.subs.append(
        c.world.bus.on(MoveStart, refuse, window=Window.BEFORE, owner=c.me)
    )


@power(
    "p14559",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p14559(c: Cast) -> None:
    """"Each Failed Saving Throw" is `escalate`, which runs on a failed save
    and leaves the effect standing -- so it can pay out again and again, which
    is what "each" asks for and what a `First Failed` line would not."""
    victim = c.target
    if victim is None:
        return
    reach = max(0, c.wis_mod)

    def dragged(_eff: Effect) -> None:
        c.slide(reach, on=victim)

    if c.strike():
        c.damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slide(reach)
        c.world.effects.apply(
            victim,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            ongoing=(5, DamageType.PSYCHIC),
            escalate=dragged,
        )
    else:
        c.half_damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slide(reach)


@power(
    "p14560",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(INT, vs=WILL),
)
def p14560(c: Cast) -> None:
    """The zone bites an enemy that **ends** its turn in it, which is neither
    half of what `c.burns` says, so it is a `TurnEnd` watch on the zone's own
    effect."""
    if c.strike():
        c.damage("2d12", c.int_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d12", c.int_mod, dtype=DamageType.PSYCHIC)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(zone):
            c.flat(2 + c.int_mod, dtype=DamageType.PSYCHIC, on=ev.actor)

    held = c.world.get(zone, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.append(c.world.bus.on(TurnEnd, dusk))


@power(
    "p16285",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.AREA,
        Keyword.NECROTIC,
        Keyword.POISON,
        Keyword.ZONE,
    ],
    attack=Attack(INT, vs=FORT),
)
def p16285(c: Cast) -> None:
    """One hit counting as two damage types has no spelling -- `DamageType`
    names one -- so the blow is necrotic and the poison is a note.

    The cloud does drift on the sustain: a zone's squares are a field on it,
    and moving them and asking `Zones.refresh` is the whole of it. The printed
    move action that walks it three squares has no door of its own.
    """
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.NECROTIC)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.NECROTIC)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.hazard(
        area, 5, DamageType.NECROTIC, label=c.ref, until=When.SUSTAIN, sustain=MINOR
    )
    held = c.world.get(zone, Zone)

    def drift() -> None:
        cloud = c.world.get(zone, Zone)
        if cloud is None:
            return
        step = c.roll("1d4")
        way = [(1, 0), (0, 1), (-1, 0), (0, -1)][c.roll("1d4") - 1]
        moved: set[Square] = set()
        for x, y in cloud.squares:
            sq = (x + way[0] * step, y + way[1] * step)
            if c.world.grid.inside(sq):
                moved.add(sq)
        if moved:
            cloud.squares = frozenset(moved)
            c.world.zones.refresh()

    c.on_sustain(held.effect if held is not None else None, drift)
    c.note(f"{c.ref}: the blow is necrotic and poison both, and damage carries one type")


@power(
    "p16286",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
)
def p16286(c: Cast) -> None:
    """The fist is the declared minor action. Its blast is the second printed
    stanza, an at-will standard action with no id of its own; the one door it
    has is the sustain the first stanza prints, so `c.on_sustain` swings it --
    once a round rather than at will, which is a reduction and is said out
    loud. It does not swing on arrival, which the row does not print either.

    Flanking with a conjuration is not something `query.flanked_by` can see:
    it asks which creatures are on which side, and this is not a creature.
    """
    room = [
        sq
        for sq in sorted(spread({c.here}, 20) - {c.here})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    # Ranked by what the blast would catch from there. With no decider
    # installed the first option is the answer, and the lowest-sorted square
    # on the board is reliably the one nothing is standing near.
    room.sort(key=lambda sq: (-len(c.in_squares(spread({sq}, 2), side="enemy")), sq))
    fist = c.conjure(
        c.choose(room, f"{c.ref}: where the fist lands"),
        label=c.ref,
        until=When.SUSTAIN,
        sustain=MINOR,
    )
    if not fist:
        return

    def punch() -> None:
        pos = c.world.get(fist, Position)
        if pos is None:
            return
        caught = [
            foe
            for foe in sorted(c.enemies())
            if foe in c.in_squares(spread(pos.squares, 2))
        ]
        for foe in caught:
            if c.strike(on=foe, from_=fist):
                c.damage("3d6", c.int_mod, on=foe)
                c.prone(on=foe)

    conj = c.world.get(fist, Conjuration)
    held = c.world.effects.live.get(conj.effect) if conj else None
    c.on_sustain(held, punch)
    c.note(f"{c.ref}: the blast is at will, and the sustain is the only door it has")


@power(
    "p16288",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE],
)
def p16288(c: Cast) -> None:
    """The declared row is the globes and what standing next to them costs.
    The second printed stanza -- a minor-action bolt that spends one globe --
    has no id of its own and no trigger or sustain to hang from, so nothing
    ever spends a globe here and the retaliation stays at its full five.
    """
    me = c.me
    globes = [5]

    def scorch(ev: Hit) -> None:
        if ev.target != me or globes[0] <= 0:
            return
        if c.adjacent(to=ev.attacker):
            c.flat(3 * globes[0], dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, scorch, until=When.ENCOUNTER, on=me, label=c.ref)
    c.note(f"{c.ref}: the bolt that spends a globe is a second stanza with no id")


@power(
    "p4036",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p4036(c: Cast) -> None:
    """"Including itself" is a real option and is offered as one. The punish
    reads the reach off the row that missed, which is where a melee attack is
    recorded -- the `Miss` event carries no reach of its own.
    """
    victim = c.target
    if victim is None:
        return

    def punish(ev: Miss) -> None:
        if ev.attacker != victim:
            return
        p = get(ev.power)
        if p is not None and p.reach.kind in ("melee", "close_burst", "close_blast"):
            c.flat(5, on=victim)

    c.watch(Miss, punish, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} flailing")
    if not c.strike():
        return
    marks = sorted({*c.within(1, of=victim), victim})
    mark = c.choose(marks, f"{c.ref}: who the target swings at")
    if mark is not None:
        c.grant_attack(victim, on=mark)


@power(
    "p4071",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.AREA,
        Keyword.FEAR,
        Keyword.ILLUSION,
        Keyword.PSYCHIC,
        Keyword.ZONE,
    ],
    attack=Attack(INT, vs=WILL),
)
def p4071(c: Cast) -> None:
    """The zone lasts until nobody is held by it, so its ending hangs off the
    holds rather than a clock: the last one to go takes the zone with it.

    Being shoved out is a `ZoneExited` that was not the creature's own doing,
    which is read off whether a forced move is in progress -- the exit arrives
    inside the shove. Refusing to leave willingly is a cancelled `MoveStart`,
    wider than printed for the reason the module docstring gives.
    """
    if c.first:
        area = c.area()
        if area:
            c.zone(area, label=c.ref, until=When.ENCOUNTER)
    mine = [z for z, zone in c.world.zones.all() if zone.label == c.ref]
    penned = mine[0] if mine else 0
    victim = c.target
    if victim is None or not penned:
        return
    landed = c.strike()
    held = c.effect(
        f"{c.ref} safety", until=When.SAVE_ENDS if landed else When.EONT
    )
    if held is None:
        return

    def refuse(ev: MoveStart) -> None:
        if ev.actor != victim or ev.kind_ not in ("walk", "shift"):
            return
        if victim in c.world.zones.occupants(penned):
            ev.cancel("the illusion of safety")

    def shoved(ev: ZoneExited) -> None:
        if ev.zone != penned or ev.actor != victim or held.ended:
            return
        c.damage("2d8", c.int_mod, dtype=DamageType.PSYCHIC, on=victim)
        c.world.effects.end(held, "driven out of the zone")

    blind = [
        (Relation.HIDDEN_FROM, other, victim)
        for other in (*c.enemies(), *c.allies(), c.me)
        if other != victim and other not in c.world.zones.occupants(penned)
    ]
    held.relations.extend(blind)
    for kind, src, dst in blind:
        c.world.relations.set(kind, src, dst)
    held.subs.extend(
        [
            c.world.bus.on(MoveStart, refuse, window=Window.BEFORE, owner=c.me),
            c.world.bus.on(ZoneExited, shoved, owner=c.me),
        ]
    )

    def last_one_out() -> None:
        if not c.suffering(f"{c.ref} safety"):
            c.world.zones.end(penned, "nobody is held by it")

    held.on_end.append(last_one_out)


@power(
    "p4084",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    # "One creature adjacent to the hound" -- the hound is placed next to
    # whoever was picked, which is the same thing said from the other end.
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
)
def p4084(c: Cast) -> None:
    """The hound swings as it appears, which is the printed line, and is walked
    six squares with a move action, which `c.conjure`'s speed is. Having it
    repeat the attack for a minor action has no door: a conjuration offers its
    creator a move and nothing else.

    "-2 to its next attack roll that targets you" is a one-shot gated penalty,
    and `once` spends it on the roll, which is when an attack modifier is read.
    """
    if not c.first:
        return
    victim = c.target
    if victim is None:
        return
    me = c.me
    room = [
        sq
        for sq in sorted(spread({c.there}, 1) - {c.there})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    hound = c.conjure(
        c.choose(room, f"{c.ref}: where the hound stands"),
        label=c.ref,
        until=When.ENCOUNTER,
        sustain=None,
        speed=6,
    )
    if not hound:
        return
    if c.strike(from_=hound):
        c.damage("3d4", c.int_mod)
        c.penalty(
            "attack", 2, on=victim, until=When.ENCOUNTER, once=True,
            when=lambda ctx: ctx.get("target") == me,
        )
    c.note(f"{c.ref}: the hound should also repeat its attack for a minor action")


@power(
    "p5807",
    level=9,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.FEAR, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p5807(c: Cast) -> None:
    """Hit and miss leave the same hold; only the worsening is the hit's.

    `escalate` runs on a failed save and `on_end` is the Aftereffect -- and the
    two meet, because worsening ends the first hold. The flag keeps the slow
    from arriving a turn early when that happens.
    """
    victim = c.target
    if victim is None:
        return
    landed = c.strike()
    worsened: list[bool] = []

    def afterwards() -> None:
        if not worsened:
            c.slowed(on=victim, until=When.SAVE_ENDS)

    def worsen(eff: Effect) -> None:
        worsened.append(True)
        c.world.effects.end(eff, "worsened")
        deeper = c.condition(Condition.HELPLESS, until=When.SAVE_ENDS, on=victim)
        if deeper is not None:
            deeper.on_end.append(lambda: c.slowed(on=victim, until=When.SAVE_ENDS))

    held = c.condition(
        Condition.IMMOBILIZED,
        until=When.SAVE_ENDS,
        escalate=worsen if landed else None,
    )
    if held is not None:
        held.on_end.append(afterwards)
