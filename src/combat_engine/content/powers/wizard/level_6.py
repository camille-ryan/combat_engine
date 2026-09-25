"""Wizard, level 6: utility.

Two of these keep themselves alive on a printed Sustain line, so both are
`When.SUSTAIN` with the named action on them; `p1229`'s sustain also has a
*condition* -- the target must still be within 5 squares -- and that half
goes through `c.on_sustain`.

`p1548` prints an area **wall**, which is not one of the shapes a `Range`
can be. Its distance is declared as the ranged 10 the printed line gives
and the run of squares is laid in the body, perpendicular to the line from
the wizard to the square it was pointed at. Its height has nowhere to go:
the board is flat.

The rows printed in the later books follow. Most are conjurations, and the
one thing to know about them here is that a conjuration **occupies** its
square -- which is exactly what `p16284`'s double prints and exactly what
`p3220`'s hound prints it does *not* do, so the hound overstates the row by
one clause and says so.

`p16283` is the other kind of wall: real blocking terrain rather than a zone
that only stops sight. `world.grid.blocking` is the door, and the squares are
taken back out of it from the holding effect's `on_end` -- only the ones this
row actually laid, so a wall raised across an existing one does not demolish
it on the way out.

Two rows here are **narrative only**. `p11035` is a ladder and a climb check;
`p13985` is darkvision, and this engine keeps no light level and no senses to
grant. Both carry `out_of_combat=True` for the same reason `level_0.py`'s
cantrips do -- deliberately inert, rather than not written yet.

Five are left out entirely; see the report. The recurring reason is that a
clause is the *whole* of the row: a familiar, a summoned creature, a spellbook,
a vertical axis, and forced movement lengthened by whoever caused it (the
`"forced"` modifier is read off the victim with a context naming only `how`,
so "the movement **you** cause" cannot be gated).
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    INT,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageType,
    Defense,
    Hit,
    Keyword,
    Position,
    Ranged,
    Relation,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    both,
    by_melee,
    enemy_within,
    get,
    hits_me,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.dsl import ANY_CREATURE, EACH_ALLY
from combat_engine.engine.zones import Zone

ARCANE = [Keyword.ARCANE]


@power(
    "p1208",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p1208(c: Cast) -> None:
    c.teleport(10)


@power(
    "p1209",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
    out_of_combat=True,
)
def p1209(c: Cast) -> None:
    c.note("p1209: you look like somebody else for an hour; touch gives it away")


@power(
    "p1229",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ANY_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
)
def p1229(c: Cast) -> None:
    """Unseen by everybody, which is a `HIDDEN_FROM` per enemy.

    Built by hand rather than with `c.invisible`, which always hides the
    caster and takes no sustain cost -- this row hides whoever it was aimed
    at and is kept going with a standard action.

    Attacking already breaks the relations inside `resolve.attack`; the
    effect is ended as well, because the printed line ends the *power*.
    """
    who = c.target
    if who is None:
        return
    watchers = [w for w in c.enemies() if w != who]
    if not watchers:
        return
    veil = c.world.effects.apply(
        who,
        c.me,
        When.SUSTAIN,
        label=f"{c.ref} unseen",
        relations=[(Relation.HIDDEN_FROM, who, w) for w in watchers],
        sustain_cost=STANDARD,
    )

    def gave_itself_away(ev: object) -> None:
        c.world.effects.end(veil, "the target attacked")

    watching = c.on_attack(
        gave_itself_away, by=who, until=When.ENCOUNTER, once=True, label=f"{c.ref} watch"
    )
    veil.on_end.append(lambda: c.world.effects.end(watching, "the power ended"))

    def still_close() -> None:
        if c.distance(to=who) > 5:
            c.world.effects.end(veil, "out of range to sustain")

    c.on_sustain(veil, still_close)


@power(
    "p1548",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
)
def p1548(c: Cast) -> None:
    """Eight squares of fog that nothing sees through.

    `blocks_sight` is the whole of "heavily obscured and blocks line of
    sight" -- `cover_between` reads it for every attack across the squares.
    """
    anchors = sorted(
        sq
        for sq in spread({c.here}, 10)
        if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, "where the wall stands")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    # Laid across the wizard's line of sight to the square it was aimed at,
    # which is the only placement the caller is not being asked to describe
    # square by square.
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [
        (anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-3, 5)
    ]
    wall = [sq for sq in run if c.world.grid.inside(sq)]
    if wall:
        c.zone(wall, label=c.ref, until=When.SUSTAIN, sustain=MINOR, blocks_sight=True)


@power(
    "p2273",
    level=6,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=WILL),
)
def p2273(c: Cast) -> None:
    """A zone or a conjuration is not a creature, so it cannot be a printed
    target here -- the row aims at one itself and rolls against whoever made
    it, which is what the printed Attack line says anyway.

    "All its effects end, including those that normally last until a target
    saves" is read as every live effect the same caster laid under the same
    label: that is how a zone's riders are named, and nothing else ties a
    save-ends effect back to the ground it came from.
    """
    reach = spread({c.here}, 10)
    found: list[tuple[int, int, str, str]] = []
    for zid, zone in c.world.zones.all():
        if zone.squares & reach:
            found.append((zid, zone.owner, zone.label, "zone"))
    for eid, conj in c.world.each(Conjuration):
        if c.distance(to=eid) <= 10:
            found.append((eid, conj.by, conj.ref, "conjuration"))
    picked = c.choose(sorted(found), "what to unmake")
    if picked is None:
        return
    which, owner, label, kind = picked
    if not c.strike(on=owner):
        return
    for effect in list(c.world.effects.live.values()):
        if effect.source == owner and label and label in effect.label:
            c.world.effects.end(effect, c.ref)
    if kind == "zone" and c.world.get(which, Zone) is not None:
        c.world.zones.end(which, c.ref)
    c.note(f"p2273: the {kind} is unmade")


def _free_near(c: Cast, origin: tuple[int, int], radius: int) -> list[tuple[int, int]]:
    """Squares within `radius` of a point that a conjuration could stand in."""
    return [
        sq
        for sq in sorted(spread({origin}, radius) - {origin})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]


@power(
    "p10072",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
)
def p10072(c: Cast) -> None:
    """Standing up is ending the prone hold, which is exactly what the stand
    action does; the choice between standing and shifting is the ally's, so it
    is offered rather than taken.

    The printed line prices the same walk two ways -- two squares for a minor,
    six for a move -- and a conjuration has one speed, so it is given the move
    action's six.
    """
    where = c.choose(_free_near(c, c.here, 10), f"{c.ref}: where the companion stands")
    if where is None:
        return
    friend = c.conjure(where, label=c.ref, until=When.ENCOUNTER, speed=6)
    if not friend:
        return
    def dawn(ev: TurnStart) -> None:
        # Asked afresh each turn rather than closed over: who is standing is
        # not what it was when the companion was called up.
        if ev.ghost or ev.actor not in c.allies() or not c.adjacent_to(friend, ev.actor):
            return
        prone = [e for e in c.world.effects.of(ev.actor) if Condition.PRONE in e.conditions]
        if prone:
            if c.may("stand up", who=ev.actor):
                for eff in prone:
                    c.world.effects.end(eff, "stood up")
        elif c.may("shift 1 square", who=ev.actor):
            c.shift(1, who=ev.actor)

    conj = c.world.get(friend, Conjuration)
    held = c.world.effects.live.get(conj.effect) if conj else None
    if held is not None:
        held.subs.append(c.world.bus.on(TurnStart, dawn))


@power(
    "p11035",
    level=6,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
    out_of_combat=True,
)
def p11035(c: Cast) -> None:
    c.note("p11035: a ladder that stands unsupported, climbed with a check")


@power(
    "p13985",
    level=6,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CLOSE, Keyword.ZONE],
    out_of_combat=True,
)
def p13985(c: Cast) -> None:
    c.note("p13985: your side sees in the dark inside the burst")


@power(
    "p13986",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.CLOSE],
)
def p13986(c: Cast) -> None:
    """Darkvision has nothing to read -- the engine keeps no light level and no
    senses -- so the resistance is the whole of the written row."""
    c.resist(5 + c.wis_mod, DamageType.NECROTIC, until=When.ENCOUNTER)


@power(
    "p14554",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ZONE],
    trigger="you are damaged by an attack",
    on=Trigger(DamageApplied, targets_me, "you are damaged by an attack"),
)
def p14554(c: Cast) -> None:
    """Removed from play is the condition of that name: the body stays in its
    square, because nothing lifts a creature off the board and puts it back,
    and the fog is laid over the top of it either way.

    Stepping back in is a teleport taken at the start of the caster's own next
    turn. Its watch is clocked on the **end** of that turn rather than its
    start: `Effects` subscribes to `TurnStart` when the world is built, so it
    is always the first listener, and a start-of-turn watch is torn down
    before it can answer the very boundary it was set for.
    """
    me = c.me
    vacated = c.here
    c.condition(Condition.REMOVED, until=When.SONT, on=me)
    c.zone({vacated}, label=c.ref, until=When.ENCOUNTER, blocks_sight=True)

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        room = [
            sq
            for sq in sorted(spread({vacated}, 5))
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) in (None, me)
        ]
        where = c.choose(room, f"{c.ref}: where you step back in")
        if where is not None:
            c.teleport(5, to=where)

    c.watch(TurnStart, dawn, until=When.EONT, on=me, once=True, label=c.ref)


@power(
    "p14555",
    level=6,
    cls="wizard",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.CLOSE],
    trigger="an enemy ends its turn within 5 squares of you",
    on=Trigger(TurnEnd, enemy_within(5), "an enemy ends its turn within 5 squares of you"),
)
def p14555(c: Cast) -> None:
    """The ally pool includes the caster, which is "you and each ally" exactly.
    The shift is offered, not taken: the printed line says *can*."""
    if c.target is not None and c.may("shift 1 square"):
        c.shift(1, who=c.target)


@power(
    "p14556",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=ARCANE,
)
def p14556(c: Cast) -> None:
    """Removed outright rather than saved against: the printed line rolls
    nothing. `ONE_ALLY`'s pool already includes the caster, which is "you or
    one ally"."""
    who = c.target
    if who is None:
        return
    holds = sorted(
        (e for e in c.world.effects.of(who) if e.when is When.SAVE_ENDS),
        key=lambda e: e.id,
    )
    picked = c.choose(holds, f"{c.ref}: which effect goes")
    if picked is not None:
        c.world.effects.end(picked, c.ref)


@power(
    "p16283",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.AREA, Keyword.CONJURATION],
)
def p16283(c: Cast) -> None:
    """Blocking terrain rather than a zone: a zone can stop sight and cannot
    stop a creature, and this wall stops both. `world.grid.blocking` is the
    door, and only the squares this row actually added are taken back out
    again, so raising it across existing rock does not demolish the rock.

    The wall is five squares laid across the line from the caster to the
    square it was pointed at, the way `p1548` lays its fog. Its one square of
    height is nothing here, and the climb is a check the engine does not roll.
    """
    anchors = sorted(
        sq
        for sq in spread({c.here}, 10)
        if c.world.grid.passable(sq)
        and sq != c.here
        and c.world.grid.occupant(sq) is None
    )
    anchor = c.choose(anchors, f"{c.ref}: where the wall stands")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-2, 3)]
    laid = [
        sq
        for sq in run
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if not laid:
        return
    c.world.grid.blocking.update(laid)

    def demolish() -> None:
        c.world.grid.blocking.difference_update(laid)

    # Hung on a zone rather than on an effect the caster owns. A zone's effect
    # belongs to the zone entity, which has no `Health`, so `Effects.bereave`
    # leaves it standing -- and a wall of stone does not fall down because the
    # wizard did.
    wall = c.zone(laid, label=c.ref, until=When.ENCOUNTER)
    held = c.world.get(wall, Zone)
    if held is not None and held.effect is not None:
        held.effect.on_end.append(demolish)


@power(
    "p16284",
    level=6,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
)
def p16284(c: Cast) -> None:
    """Two of the three printed sentences are what a conjuration *is*: it
    stands in an unoccupied square, occupies it, and lasts until the end of
    your next turn.

    The third has no expression. A power's origin is the caster's own position
    and nothing can point it somewhere else, so casting from the double's
    square is the clause this row loses.
    """
    where = c.choose(_free_near(c, c.here, 10), f"{c.ref}: where the double stands")
    if where is None:
        return
    if c.conjure(where, label=c.ref, until=When.EONT):
        c.note(f"{c.ref}: your attacks may also originate from the double's square")


@power(
    "p2835",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FIRE],
)
def p2835(c: Cast) -> None:
    """The teeth answer a melee attack **roll aimed at the caster**, not
    entering an aura, so this is a watch on the declaration with its own latch
    rather than `c.burns` -- which bites on entering and on starting a turn,
    neither of which this row prints.

    The latch is keyed on whose turn it is as well as the round, because
    "once per turn" and "once per round" differ for a creature that swings
    again on somebody else's turn.
    """
    me = c.me
    c.resist(10, DamageType.COLD, until=When.ENCOUNTER, on=me)
    c.resist(10, DamageType.FIRE, until=When.ENCOUNTER, on=me)
    bitten: dict[int, tuple[int, int | None]] = {}

    def scald(ev: AttackDeclared) -> None:
        now = (c.world.round, c.world.turn)
        if ev.target != me or ev.attacker == me or bitten.get(ev.attacker) == now:
            return
        if not by_melee(c.world, me, ev):
            return
        bitten[ev.attacker] = now
        c.damage("2d6", c.int_mod, dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(AttackDeclared, scald, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p3220",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.ILLUSION],
)
def p3220(c: Cast) -> None:
    """The hound is a conjuration so that it has a square to be within ten of
    and a speed to be moved with. That overstates the row by one clause -- a
    conjuration occupies its square and the printed hound does not -- and
    counting as an ally for flanking is lost outright, because flanking asks
    which side a creature is on and a conjuration is on none.

    The +1 is gated on the hound still being within ten squares rather than
    reapplied as the two move, and the printed sustain condition -- the hound
    leaving line of sight -- ends the power through `c.on_sustain`.
    """
    where = c.choose(_free_near(c, c.here, 10), f"{c.ref}: where the hound stands")
    if where is None:
        return
    hound = c.conjure(where, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=5)
    if not hound:
        return

    def close_enough(_ctx: dict[str, Any]) -> bool:
        return c.world.get(hound, Position) is not None and c.distance(to=hound) <= 10

    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 1, on=c.me, until=When.ENCOUNTER, kind="power", when=close_enough
        )

    def still_seen() -> None:
        if not c.can_see(to=hound):
            conj = c.world.get(hound, Conjuration)
            gone = c.world.effects.live.get(conj.effect) if conj else None
            if gone is not None:
                c.world.effects.end(gone, "the hound left your sight")

    conj = c.world.get(hound, Conjuration)
    c.on_sustain(c.world.effects.live.get(conj.effect) if conj else None, still_seen)


@power(
    "p4110",
    level=6,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE,
)
def p4110(c: Cast) -> None:
    """The Insight half is a skill check and there are none.

    The +2 is gated on the creature *and* on the row aiming at its Will. The
    attack context carries no defence, so the defence is read back off the
    power in the registry -- the same lookup `by_melee` does for reach.
    """
    victim = c.target
    if victim is None:
        return

    def against_will(ctx: dict[str, Any]) -> bool:
        if ctx.get("target") != victim:
            return False
        p = get(ctx.get("power") or "")
        line = p.attack_of(ctx.get("branch", 0)) if p is not None else None
        return line is not None and line.vs is Defense.WILL

    c.bonus("attack", 2, on=c.me, until=When.EONT, when=against_will)


@power(
    "p6902",
    level=6,
    cls="wizard",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger="an enemy hits you with a melee attack",
    on=Trigger(Hit, both(hits_me, by_melee), "an enemy hits you with a melee attack"),
)
def p6902(c: Cast) -> None:
    """"A space that is not adjacent to an enemy" is worked out here rather
    than left to the decider, which takes the lowest-sorted square and would
    put the caster straight back in somebody's face."""
    me = c.me
    threatened: set[tuple[int, int]] = set()
    for foe in c.enemies():
        pos = c.world.get(foe, Position)
        if pos is not None:
            threatened |= spread(pos.squares, 1)
    room = [
        sq
        for sq in sorted(spread({c.here}, 5))
        if c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) in (None, me)
        and sq not in threatened
    ]
    where = c.choose(room, f"{c.ref}: where you step out to")
    if where is not None:
        c.teleport(5, to=where)
