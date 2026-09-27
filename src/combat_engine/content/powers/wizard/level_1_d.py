"""Wizard, level 1: the later books, third file.

The rows `level_1_c.py` had no room for. Its two shared helpers -- `_on_zone`,
which is `c.burns` with the dials these zones need, and `_no_opportunity` --
are imported from there rather than written twice.

`p2351` and `p16276` each print a **second stanza** whose Requirement is that
the first power be active and whose trigger is a creature arriving in the zone
the first paragraph laid. `p2351`'s has a ref of its own -- `p2351b`, in
`second_card.py` -- so this row lays the ice and nothing else. `p16276`'s
does not, so its zone is built here and the triggered attack hangs on the
zone's own effect -- it goes when the zone goes.

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
    AC,
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
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Mod,
    MoveEnd,
    Ranged,
    Summon,
    TurnEnd,
    UpTo,
    When,
    Window,
    World,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration, Position, Powers
from combat_engine.engine.events import LeaveSquare, MoveStart

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
    """Only the ice. The second printed stanza -- the free action that trips
    whoever walks onto it -- is `p2351b` now, gated on this zone standing."""
    area = c.area()
    if not area:
        return
    c.zone(area, label=c.ref, until=When.ENCOUNTER, difficult=True)


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


def _at_will_or_basic(ref: str) -> bool:
    """Was that hit made with an at-will or basic attack?

    Both of the engine's basic attacks are declared at-will, so the one test
    answers the pair -- which is what "a basic or at-will attack" prints.
    """
    p = get(ref)
    return p is not None and p.usage is AT_WILL


def _reach_is(ref: str, *kinds: str) -> bool:
    """Was that row's printed range one of these?

    The damage context carries no reach, so a clause about melee, close or
    area attacks has to read it off the row that dealt them.
    """
    p = get(ref)
    return p is not None and p.reach is not None and p.reach.kind in kinds


def _commands_on_opportunity(c: Cast, made: int, *, mark: bool = False) -> None:
    """A summon's printed Opportunity Attack command.

    `OpportunityWindow` opens for creatures that threaten the mover, and a
    companion is not offered one -- so the condition the printed clause
    actually names is written out instead: an adjacent enemy walks, and the
    summoner spends its opportunity action having the creature swing with
    the line in the header's `summon=`. `MoveStart` rather than `MoveEnd`,
    because by the end the enemy has left and the adjacency is false exactly
    when the clause should fire. One swing per enemy per round, which is
    what an opportunity attack costs.
    """
    struck: dict[int, int] = {}

    def swing(ev: MoveStart) -> None:
        if ev.kind_ != "walk" or struck.get(ev.actor) == c.world.round:
            return
        if not c.adjacent_to(made, ev.actor) or ev.actor not in c.enemies():
            return
        struck[ev.actor] = c.world.round
        if c.command(made, on=ev.actor) and mark:
            c.mark(on=ev.actor, by=made, until=When.EONT)

    c.watch(
        MoveStart, swing, until=When.ENCOUNTER, window=Window.BEFORE,
        label=f"{c.ref} opportunity command",
    )


@power(
    "p11840",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=ARCANE_IMPLEMENT,
    summon=Summon(speed=5, attack=Attack(INT, vs=REF), damage=Damage("2d6", "int")),
)
def p11840(c: Cast) -> None:
    """The special command is a standard action spent on a later turn and
    nothing offers one, so the header carries the line `c.command` rolls and
    nothing spends it; "one or two creatures" has nowhere to go either. The
    symbiosis is not gated on the summoned creature still standing -- nothing asks
    whether a companion is still on the board.
    """
    made = c.summon_inline(get(c.ref).summon, at=c.origin)
    if not made:
        return

    def death_throe(ev: Dropped) -> None:
        if ev.actor == made:
            for who in c.within(1, of=made):
                c.flat(5, dtype=DamageType.POISON, on=who)

    c.watch(Dropped, death_throe, until=When.ENCOUNTER, label=f"{c.ref} death throe")

    def symbiosis(ev: Hit) -> None:
        if ev.attacker != c.me or not _at_will_or_basic(ev.power):
            return
        victim = ev.target
        c.on_attack(
            lambda _e: c.flat(5, on=victim),
            by=victim, until=When.EOTNT, once=True, label=f"{c.ref} symbiosis",
        )

    c.watch(Hit, symbiosis, until=When.ENCOUNTER, label=f"{c.ref} symbiosis watch")


@power(
    "p11841",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=ARCANE_IMPLEMENT,
    summon=Summon(speed=8, attack=Attack(INT, vs=REF), damage=Damage("1d10", "int")),
)
def p11841(c: Cast) -> None:
    """`Summon` carries one attack line and no shape, so the command's close
    burst and the slide it prints are not held, and the standard action that
    would spend it has no door. The defence bonus is gated on `opportunity`,
    which the attack context carries.
    """
    c.summon_inline(get(c.ref).summon, at=c.origin)
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="power")
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 4, on=c.me, until=When.ENCOUNTER, kind="power",
            when=lambda ctx: bool(ctx.get("opportunity")),
        )


@power(
    "p4016",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    summon=Summon(
        speed=6, defences=2, modes=("fly",),
        attack=Attack(INT, vs=REF),
        damage=Damage("1d8", "int", dtype=DamageType.FIRE),
    ),
)
def p4016(c: Cast) -> None:
    """`Summon.defences` is one offset for all four and the printed +2 is to
    AC and Fortitude alone, so Reflex and Will come out 2 too high. Hovering
    has nowhere to go. The standard-action command has no door; the
    opportunity one is written, since that is a moment the board reaches.
    """
    made = c.summon_inline(get(c.ref).summon, at=c.origin)
    if made:
        _commands_on_opportunity(c, made)


#: The at-will `p7429`'s Prerequisite names. Identified by mechanics, which
#: are unique in the class: the only wizard at-will at Ranged 20 carrying the
#: force keyword and rolling no attack.
_PREREQUISITE = "p463"


def _knows_the_at_will(world: World, eid: int) -> bool:
    """"Prerequisite: you must know the at-will wizard power named."""
    known = world.get(eid, Powers)
    return known is not None and _PREREQUISITE in known.all


@power(
    "p7429",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    requires=_knows_the_at_will,
    requires_text=f"must know {_PREREQUISITE}",
)
def p7429(c: Cast) -> None:
    """The printed Effect is the cheaper action and nothing else, so the row
    is one `c.recast`: the at-will keeps its standard-action entry in the
    menu and gains a minor-action one, once a turn, until the fight ends."""
    c.recast(_PREREQUISITE, action=MINOR, until=When.ENCOUNTER)
