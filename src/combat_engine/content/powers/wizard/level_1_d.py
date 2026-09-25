"""Wizard, level 1: the later books, third file.

The rows `level_1_c.py` had no room for. Its two shared helpers -- `_on_zone`,
which is `c.burns` with the dials these zones need, and `_no_opportunity` --
are imported from there rather than written twice.

`p2351` and `p16276` each print a **second stanza** whose Requirement is that
the first power be active and whose trigger is a creature arriving in the zone
the first paragraph laid. That is one power in two paragraphs rather than two
refs, so the zone is built here and the triggered attack hangs on the zone's
own effect -- it goes when the zone goes.

`p16275` prints an area **wall**, which is not a shape a `Range` can be: the
printed ten squares are the reach and the run of six is laid in the body.
Where the wall stands, and where `p4309`'s pillar stands, are *ranked* by what
each placement would catch before they are offered -- with no decider
installed the first option is the answer, and the lowest-sorted square on the
board catches nobody.
"""

from __future__ import annotations

from combat_engine.content.powers.wizard.level_1_c import (
    _on_zone,
)
from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
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
    Condition,
    DamageType,
    Keyword,
    Mod,
    MoveEnd,
    Ranged,
    TurnEnd,
    UpTo,
    When,
    distance,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration, Position
from combat_engine.engine.events import LeaveSquare

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

@power(
    "p2351",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ZONE, Keyword.AREA],
    # Declared for the second stanza, which is the only thing here that rolls.
    attack=Attack(INT, vs=REF),
)
def p2351(c: Cast) -> None:
    """The second printed stanza is folded in rather than declared as a row
    of its own: a free action whose Requirement is that this power be active
    and whose trigger is a creature entering this zone is the same thing as
    a listener hung on this zone's effect.

    Its miss slides the target two squares and says outright that the
    movement does not trigger the attack again, which is what the latch is
    for.
    """
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult=True)
    busy: set[int] = set()

    def slip(who: int) -> None:
        if who in busy:
            return
        busy.add(who)
        try:
            if c.strike(on=who):
                c.prone(on=who)
            else:
                c.slide(2, on=who)
        finally:
            busy.discard(who)

    _on_zone(c, zone, slip, entering=True)


@power(
    "p3214",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p3214(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p3215",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION, Keyword.AREA],
    attack=Attack(INT, vs=WILL),
)
def p3215(c: Cast) -> None:
    """The area goes on writhing after the attack, so it is held as a zone
    even though the row prints no zone keyword -- there is nothing else that
    remembers a patch of ground.

    Entering only: `c.burns` would bite whoever started a turn there too,
    and that is a clause this row does not print.
    """
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed()
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT)
    toll = max(1, c.int_mod)

    def writhe(who: int) -> None:
        c.flat(toll, dtype=DamageType.PSYCHIC, on=who)
        c.slowed(until=When.EOTNT, on=who)

    _on_zone(c, zone, writhe, entering=True, once_per_turn=True)


@power(
    "p3216",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.ILLUSION,
        Keyword.ZONE,
        Keyword.AREA,
    ],
    attack=Attack(INT, vs=WILL),
)
def p3216(c: Cast) -> None:
    """"Immobilized until the end of its next turn" is the target's clock,
    not the caster's, so it is `EOTNT` rather than `EONT`."""
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.prone()
        c.immobilized(until=When.EOTNT)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.prone()
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER)
    _on_zone(c, zone, lambda who: c.prone(on=who), entering=True, side="enemy")


@power(
    "p4019",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CONJURATION],
    attack=Attack(INT, vs=FORT),
)
def p4019(c: Cast) -> None:
    """The Effect line is unconditional, so the conjuration appears whether
    the attack landed or not. It stands in the target's own square, which
    `place` allows: the grid index refuses to overwrite the creature already
    there, and everything that measures distance reads `Position`.

    Both riders are the same damage at two different moments, so each is its
    own listener on the conjuration's hold. Leaving the square pays once --
    the square is remembered, and a creature already away from it is not
    leaving it again with every step.
    """
    if not c.first:
        return
    victim = c.target
    if victim is None:
        return
    where = c.there
    if c.strike():
        c.damage("1d10", c.int_mod)
    thing = c.conjure(where, label=c.ref, until=When.EONT)
    if not thing:
        return
    conj = c.world.get(thing, Conjuration)
    hold = c.world.effects.live.get(conj.effect) if conj else None
    if hold is None:
        return
    toll = max(1, c.con_mod)
    was = [where]

    def strayed(ev: MoveEnd) -> None:
        if ev.actor != victim:
            return
        if was[0] == where and ev.at != where:
            c.flat(toll, on=victim)
        was[0] = ev.at

    def dusk(ev: TurnEnd) -> None:
        pos = c.world.get(victim, Position)
        if ev.ghost or ev.actor != victim or pos is None:
            return
        if distance(pos.square, where) > 2:
            c.flat(toll, on=victim)

    hold.subs.append(c.world.bus.on(MoveEnd, strayed, owner=c.me))
    hold.subs.append(c.world.bus.on(TurnEnd, dusk, owner=c.me))


@power(
    "p4305",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p4305(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slide(1)


@power(
    "p4309",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING, Keyword.CONJURATION],
)
def p4309(c: Cast) -> None:
    """The pillar occupies its square, which is what makes it a conjuration
    rather than a zone. Its reach is an aura 1 hung on it, and the bite is
    hung on that aura by hand rather than passed as `burn=`: `c.burns` is
    entering **and** starting a turn there, and this row prints only the
    arrival.

    Where it stands is ranked by how many enemies it would threaten, for the
    reason `p16275` ranks its wall.
    """
    room = [
        sq
        for sq in spread({c.here}, 10)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if not room:
        return
    ranked = sorted(
        room,
        key=lambda sq: (-len(c.in_squares(spread({sq}, 1), side="enemy")), sq),
    )
    where = c.choose(ranked, "where the pillar stands")
    if where is None:
        return
    pillar = c.conjure(where, label=c.ref, until=When.EONT)
    if not pillar:
        return
    ring = c.aura(1, label=c.ref, until=When.EONT, on=pillar)
    bolt = f"1d6+{c.int_mod}"
    _on_zone(
        c,
        ring,
        lambda who: c.flat(c.roll(bolt), dtype=DamageType.LIGHTNING, on=who),
        entering=True,
        side="enemy",
    )


@power(
    "p5799",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.FIRE,
        Keyword.FORCE,
        Keyword.ZONE,
        Keyword.AREA,
    ],
    attack=Attack(INT, vs=REF),
)
def p5799(c: Cast) -> None:
    """Enemies only, which is the one dial `c.hazard` does not have."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FORCE)
        c.prone()
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT)
    _on_zone(
        c,
        zone,
        lambda who: c.flat(2, dtype=DamageType.FIRE, on=who),
        entering=True,
        starting=True,
        side="enemy",
        once_per_turn=True,
    )


@power(
    "p5800",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(INT, vs=REF),
)
def p5800(c: Cast) -> None:
    """Two clauses are left off. Concealment at more than five squares has no
    expression -- the engine keeps no concealment state, and there is nowhere
    to hang one that depends on how far away the attacker is standing. The
    rider naming a class feature has nothing to name: no such feature is
    declared.
    """
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.ACID)


@power(
    "p5801",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p5801(c: Cast) -> None:
    """The rider naming a class feature is left off: no such feature is
    declared, so there is nothing for it to hang its bonus on."""
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.LIGHTNING)
        c.push(1)


@power(
    "p5802",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION, Keyword.AREA],
    attack=Attack(INT, vs=WILL),
)
def p5802(c: Cast) -> None:
    """The slow and the penalty are "save ends **both**", so they are one
    hold with one saving throw -- which is also the only place the
    Aftereffect can live. An aftereffect follows the hold going, whichever
    way it went, which is `on_end` rather than `escalate`.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        # No damage on the miss line: the shorter hold is the whole of it.
        c.slowed()
        c.penalty("attack", 2, until=When.EONT)
        return
    c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC)
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=(Condition.SLOWED,),
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
        on_end=[lambda: c.prone(on=victim)],
    )


@power(
    "p5803",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
)
def p5803(c: Cast) -> None:
    """One conjuration per target, each standing in that target's own space.
    The Effect line resolves after the Hit line, so the ball goes down where
    the slide left the target rather than where it started.

    The printed secondary is an opportunity action the thunderball takes, and
    a conjuration has no actions of its own -- but its trigger, a creature
    moving out of its square, is exactly `LeaveSquare`. It rolls from the
    ball's position with its maker's numbers, which is what `from_` is for.
    """
    victim = c.target
    if c.strike():
        c.damage("3d6", c.int_mod, dtype=DamageType.THUNDER)
        c.slide(3)
    else:
        c.half_damage("3d6", c.int_mod, dtype=DamageType.THUNDER)
        c.slide(1)
    if victim is None:
        return
    pos = c.world.get(victim, Position)
    if pos is None:
        return
    where = pos.square
    ball = c.conjure(where, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    if not ball:
        return
    conj = c.world.get(ball, Conjuration)
    hold = c.world.effects.live.get(conj.effect) if conj else None
    if hold is None:
        return

    def bolted(ev: LeaveSquare) -> None:
        if ev.square != where or ev.actor == ball:
            return
        if c.strike(on=ev.actor, from_=ball):
            c.flat(5, dtype=DamageType.THUNDER, on=ev.actor)

    hold.subs.append(c.world.bus.on(LeaveSquare, bolted, owner=c.me))


@power(
    "p7406",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.AREA],
    attack=Attack(INT, vs=FORT),
)
def p7406(c: Cast) -> None:
    """"Any enemy **in the power's area**" is not the same list as the ones
    it hit: a creature that walks in afterwards takes the penalty too, and
    one that walks out stops taking it. So the modifier goes on every enemy
    and is gated on standing in the squares, rather than being handed to
    whoever happened to be caught.

    The hit line is a flat modifier with no dice, so there is nothing for a
    critical to maximise.
    """
    if c.strike():
        c.damage(0, c.int_mod, dtype=DamageType.COLD)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    for foe in c.enemies():
        c.penalty(
            "attack",
            2,
            on=foe,
            until=When.EONT,
            when=lambda _ctx, who=foe: who in c.in_squares(area),
        )
