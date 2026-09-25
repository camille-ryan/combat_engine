"""Wizard, level 2: the utilities.

No attack rolls at this level. Every printed Trigger line is declared with
`on=` rather than quoted: prose alone is never read, and a row that only
quotes it can never fire.

`p1223` is a skill bonus and nothing else -- the whole of its Effect is a
+10 to one check, and this engine has no checks. It carries
`out_of_combat=True` for the same reason the cantrips in `level_0.py` do,
rather than an invented movement number.

The rows printed in the later books follow. Four things recur in them.

**A skill bonus beside a real effect is not a narrative row.** `p10140`,
`p6899` and `p4105` each print a check bonus alongside something that happens
on a board, so the check is dropped in a docstring line and the rest is
written. Only a row whose *whole* Effect is a check -- `p10141`, `p12742`,
`p4236` -- takes `out_of_combat=True`.

**A modifier that has to follow the board is gated, not reapplied.** "Enemies
adjacent to you", "while in the zone", "against ranged weapon attacks": each
is one `Mod` with a `when=` that reads the board at the moment the modifier is
read. Laying and re-laying them as people walk is the alternative and it
drifts.

**Two bonuses of the same kind do not add**, so a defence bonus meant to apply
"against the attack" carries `once=True` rather than a second, larger copy.

**`c.on_attack` is the wrong door on a personal row.** With no `by=` it
filters on `c.target`, which for `target=SELF` is the caster itself -- so
`p6900` writes its own `AttackDeclared` watch, which it needs anyway: its
once-per-turn latch is per enemy, where `once_per_round` is one latch for
everybody.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageType,
    Died,
    Health,
    Keyword,
    Melee,
    Position,
    Powers,
    Ranged,
    Target,
    Trigger,
    When,
    World,
    closed_on_me,
    distance,
    get,
    power,
    spread,
    would_hit_me,
)
from combat_engine.engine.components import Trap
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.query import distance_between, enemies


def _is_charm(ctx: dict[str, Any]) -> bool:
    """Is the attack being rolled a charm one? Read off the row, not the event."""
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.CHARM in p.keywords


def _enemy_closed(world: World, me: int, ev: Any) -> bool:
    """An **enemy** moved into reach of me.

    `closed_on_me` reads `mover`, which is what keeps the caster's own advance
    from setting this off -- `AdjacencyGained` is emitted mirrored, so without
    it the row fires half the time it should not. It says nothing about sides,
    and the printed line does.
    """
    if not closed_on_me(world, me, ev):
        return False
    return getattr(ev, "mover", 0) in enemies(world, me)


def _living_death_near(world: World, me: int, ev: Any) -> bool:
    """A nonminion living creature died within 5 squares.

    A minion's one hit point is in the database, so `max_hp` is what "nonminion"
    reads. "Living" is read as "not undead", which is the only half of it the
    type line can answer. `Died` is emitted before the body is lifted off the
    grid, so there is still a square to measure from.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    health = world.get(who, Health)
    if health is None or health.max_hp <= 1:
        return False
    if Cast(world=world, me=me, ref="p13980").is_kind("undead", on=who):
        return False
    return distance_between(world, me, who) <= 5


@power(
    "p1212",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p1212(c: Cast) -> None:
    c.shift(c.speed_of() * 2)


@power(
    "p1223",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=Target("any", 1, label="You or one creature"),
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p1223(c: Cast) -> None:
    c.note("p1223: a +10 power bonus to one check, with a running start")


@power(
    "p1235",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="you are hit by an attack",
    on=Trigger(AttackRolled, when=would_hit_me, text="you are hit by an attack"),
)
def p1235(c: Cast) -> None:
    """Raised in time to turn the blow aside, which is what an interrupt is.

    Offered on the roll rather than on the hit. `would_hit_me` reads the
    provisional result -- the die is down, the total is known, and the blow
    lands as things stand -- and the defence is read again once this window
    closes, so the +4 applies to the very attack that triggered it.
    """
    c.bonus(AC, 4, on=c.me, until=When.EONT)
    c.bonus(REF, 4, on=c.me, until=When.EONT)


@power(
    "p10140",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p10140(c: Cast) -> None:
    """The Diplomacy half is a check and there are none here; the charm half is
    an ordinary gated attack bonus, so the row is written rather than declared
    inert. The gate reads the keyword off the row being rolled, which is where
    a keyword lives -- the attack context carries the ref and nothing else
    about what kind of spell it is.
    """
    c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power", when=_is_charm)


@power(
    "p10141",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(2),
    target=Target("any", 1, label="One creature out of the fight, lower level than you"),
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p10141(c: Cast) -> None:
    c.note("p10141: the target forgets the last ten minutes, and the next one")


@power(
    "p10143",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.ILLUSION],
)
def p10143(c: Cast) -> None:
    """A Medium shape standing in one square it cannot leave is a conjuration:
    it occupies its space and nothing walks through it, which is the whole of
    what the image does to a board.

    Its defences of 10 and the two ways it ends -- an attack hitting it, a
    creature touching it -- have nowhere to go. A conjuration has no hit points
    and is not a creature, so nothing can target it, and its square cannot be
    entered to touch it. The Insight check is a check.

    The squares are offered nearest first. It is still a choice, but with
    nobody playing `World.decide` takes the first option, and sorted plainly
    that is the low corner of the board ten squares away.
    """
    room = sorted(
        (
            sq
            for sq in spread({c.here}, 10) - {c.here}
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
        ),
        key=lambda sq: (distance(sq, c.here), sq),
    )
    where = c.choose(room, f"{c.ref}: where the image stands")
    if where is None:
        return
    c.conjure(where, label=c.ref, until=When.ENCOUNTER, sustain=None)


@power(
    "p10350",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="an enemy moves adjacent to you",
    on=Trigger(
        AdjacencyGained, when=_enemy_closed, text="an enemy moves adjacent to you"
    ),
)
def p10350(c: Cast) -> None:
    """"To a square farther from the triggering enemy" is an instruction, not a
    choice, so the destination is named outright rather than left to the
    decider -- which with nobody playing takes the lowest-sorted square and
    would as happily step towards the thing.
    """
    c.insubstantial(on=c.me, until=When.EONT)
    foe = getattr(c.trigger, "mover", None)
    pos = c.world.get(foe, Position) if foe else None
    options = c.world.reachable_squares(c.me, 2)
    if not options:
        return
    if pos is None:
        c.shift(2)
        return
    c.shift(2, to=max(options, key=lambda sq: (distance(sq, pos.square), sq)))


@power(
    "p11032",
    level=2,
    cls="wizard",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def p11032(c: Cast) -> None:
    """The printed Special caps how many of these may stand at once, and it is
    kept by retiring the oldest rather than refusing the new one: a cap the
    caller cannot see would look exactly like a row that did nothing.

    "You can end this effect as a minor action" has no door -- a zone ends on
    its duration or with whatever holds it up.

    The squares are offered nearest first, so an engine with nobody playing
    roughens the ground underfoot rather than the far corner of the board.
    """
    room = sorted(
        (sq for sq in spread({c.here}, 5) if c.world.grid.passable(sq)),
        key=lambda sq: (distance(sq, c.here), sq),
    )
    where = c.choose(room, f"{c.ref}: which square turns treacherous")
    if where is None:
        return
    mine = [
        z
        for z, zone in c.world.zones.all()
        if zone.label == c.ref and zone.owner == c.me
    ]
    while len(mine) >= max(1, c.int_mod):
        c.world.zones.end(mine.pop(0), "too many at once")
    c.zone({where}, label=c.ref, until=When.ENCOUNTER, difficult=True)


@power(
    "p12742",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=Target("any", 1, label="One creature"),
    keywords=[Keyword.ARCANE, Keyword.CHARM],
    out_of_combat=True,
)
def p12742(c: Cast) -> None:
    """The printed Requirement is "outside a combat encounter", which is what
    `out_of_combat` says, and everything the row then does is conversation."""
    c.note("p12742: a failed save makes the target a trusted friend for hours")


@power(
    "p13980",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
    trigger="a nonminion living creature dies within 5 squares of you",
    on=Trigger(
        Died,
        when=_living_death_near,
        text="a nonminion living creature dies within 5 squares of you",
    ),
)
def p13980(c: Cast) -> None:
    """"His or her healing surge value" is the target's own, which is why
    `of=` is passed -- `c.surge_value()` answers for the caster."""
    who = c.target
    if who is None:
        return
    c.temp_hp(c.surge_value(of=who), on=who)


@power(
    "p14546",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="you are hit by an attack",
    on=Trigger(AttackRolled, when=would_hit_me, text="you are hit by an attack"),
)
def p14546(c: Cast) -> None:
    """"Against the attack" is `once`, and for a defence bonus that is spent
    when the blow lands or misses -- the moment the defence is read -- rather
    than on the roll that announced it."""
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=c.me, until=When.EONT, kind="power", once=True)
    c.temp_hp(2 + c.wis_mod, on=c.me)


@power(
    "p14547",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=[Keyword.ARCANE],
)
def p14547(c: Cast) -> None:
    """Second wind has no `Cast` method, so this is what `actions.perform`
    spells out: a surge spent for its hit points and +2 to AC until the start
    of that creature's next turn -- clocked on the target rather than on the
    caster, since it is the target's wind. The once-a-fight latch `legal` reads
    is kept too, so this cannot hand out a second one.

    Both halves are printed as "can", so both are offered rather than taken.
    The Prerequisite is training in a skill, which nothing here has.
    """
    who = c.target
    if who is None:
        return
    if c.may("make a saving throw", who=who):
        c.save(on=who)
    health = c.world.get(who, Health)
    known = c.world.get(who, Powers)
    if health is None or health.surges <= 0:
        return
    if known is not None and known.times("second-wind"):
        return
    if not c.may("take a second wind", who=who):
        return
    if known is not None:
        known.note_use("second-wind", c.world.round)
    c.surge(on=who)
    c.bonus(AC, 2, on=who, until=When.SOTNT, kind="untyped")


@power(
    "p16278",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(1, within=10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.AREA, Keyword.ZONE],
)
def p16278(c: Cast) -> None:
    """The light is a real patch of ground; the concealment it grants is not.
    `blocks_sight` is the wrong word for it -- that is a wall you cannot see
    through, and this is a glare that makes things harder to hit.
    """
    area = c.area()
    if not area:
        return
    c.zone(area, label=c.ref, until=When.EONT)
    c.note(f"{c.ref}: creatures in the zone have partial concealment, and there is none here")


@power(
    "p16279",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CLOSE, Keyword.ZONE],
)
def p16279(c: Cast) -> None:
    """The bonus is gated twice -- on the attack being a ranged weapon one, and
    on the defender standing in the zone at the moment the defence is read.
    That is what lets one modifier follow a creature walking in and out, and
    `query.defence` passes the attack context to the modifier, so both halves
    have something to read.
    """
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER)

    def sheltered(ctx: dict[str, Any], who: int) -> bool:
        if not ctx.get("ranged"):
            return False
        p = get(ctx.get("power", ""))
        if p is None or Keyword.WEAPON not in p.keywords:
            return False
        return who in c.world.zones.occupants(zone)

    for who in (c.me, *c.allies()):
        for d in (AC, FORT, REF, WILL):
            c.bonus(
                d, 4, on=who, until=When.ENCOUNTER, kind="power",
                when=lambda ctx, w=who: sheltered(ctx, w),
            )


@power(
    "p3217",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=NO_TARGET,
    keywords=[
        Keyword.ARCANE,
        Keyword.IMPLEMENT,
        Keyword.AREA,
        Keyword.ILLUSION,
        Keyword.ZONE,
    ],
)
def p3217(c: Cast) -> None:
    """Two halves, and only one of them can be said.

    Difficult terrain costs a fixed one extra square and there is nowhere to
    name a different number, so "2 extra instead of 1" is a note -- the same
    wall `level_9.py:p722` ran into from the other side.

    The traps' half is writable: a trap is an entity that attacks, so it takes
    a gated attack bonus that pays only against the caster's enemies. The zone
    is the printed "designated area" and is what the traps are found inside.
    """
    area = c.area()
    if not area:
        return
    c.zone(area, label=c.ref, until=When.ENCOUNTER)
    foes = c.enemies()
    for eid, _trap in c.world.each(Trap):
        pos = c.world.get(eid, Position)
        if pos is None or not (pos.squares & area):
            continue
        c.bonus(
            "attack", c.int_mod, on=eid, until=When.ENCOUNTER, kind="power",
            when=lambda ctx: ctx.get("target") in foes,
        )
    c.note(f"{c.ref}: rough going here should cost 2 extra squares, and it costs 1")


@power(
    "p4105",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p4105(c: Cast) -> None:
    """Hovering an inch off the floor is, on a board, exactly "ignores every
    sort of rough going" -- `c.ignores_difficult` with no kind named.

    Pressure plates, tremorsense and the Stealth bonus have nothing to read,
    and neither has "or until you fall": nothing in this engine falls.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "p4236",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p4236(c: Cast) -> None:
    """No `on=`: the printed trigger is making a skill check, the engine rolls
    none, and a declared trigger that can never be true is the thing the brief
    warns about."""
    c.note("p4236: one skill check rerolled, keeping the better of the two")


@power(
    "p6899",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FEAR],
)
def p6899(c: Cast) -> None:
    """The penalty is laid on everybody and gated twice -- on the attack being
    aimed at the caster, and on the attacker standing next to it. Both halves
    change as people walk, and a modifier that reads the board when it is read
    is the only thing that keeps up with that. The Intimidate bonus is a check.
    """
    me = c.me
    for who in (*c.enemies(), *c.allies()):
        c.penalty(
            "attack", 2, on=who, until=When.EONT,
            when=lambda ctx, w=who: ctx.get("target") == me and c.adjacent(to=w),
        )


@power(
    "p6900",
    level=2,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FORCE],
)
def p6900(c: Cast) -> None:
    """The trigger is an enemy *making an attack roll* while standing next to
    the caster -- `AttackDeclared`, not walking into an aura -- so this is a
    watch rather than `c.burns`.

    Written out rather than through `c.on_attack` for two reasons: with no
    `by=` that method filters on `c.target`, which on a personal row is the
    caster itself, and its `once_per_round` is one latch for everybody where
    the printed line gives each enemy its own.
    """
    me = c.me
    struck: dict[int, int] = {}

    def recoil(ev: AttackDeclared) -> None:
        foe = ev.attacker
        if foe == me or foe not in c.enemies() or not c.adjacent(to=foe):
            return
        if struck.get(foe) == c.world.round:
            return
        struck[foe] = c.world.round
        c.flat(c.int_mod, dtype=DamageType.FORCE, on=foe)

    held = c.watch(AttackDeclared, recoil, until=When.ENCOUNTER, on=me, label=c.ref)

    def slumped(ev: ConditionApplied) -> None:
        if ev.target == me and ev.condition is Condition.UNCONSCIOUS and not held.ended:
            c.world.effects.end(held, "the caster went down")

    held.subs.append(c.world.bus.on(ConditionApplied, slumped, owner=me))
