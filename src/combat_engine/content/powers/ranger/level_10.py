"""Ranger, level 10: utility. No attack roll anywhere in the level.

`p217` answers the same printed sentence `level_6.py`'s `p748` does, and
declares it the same way: adjacency is derived in exactly one place, so "an
enemy moves adjacent to you" is `AdjacencyGained` with the enemy as the
mover. Its destination is filtered here rather than handed to the decider,
because "you can't end your move adjacent to the triggering enemy" is a
condition on the square and `c.move` picks whatever it likes.

`p926`'s second clause -- an extra square on every shift -- is not written.
`actions.legal` offers a shift from a ring fixed at one square and nothing
reads a modifier there, so there is no such number to raise. See the report.

Two of the later rows key off a creature going down. `Dropped` carries the
creature and nothing else, so "**you** reduce an enemy to 0 hit points" is
declared on `DamageApplied` instead, where the source, the target and the
hit points left are all on the one event. Where the printed line names the
*quarry*, `Dropped` plus the relation says it, and does so once.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    WILL,
    AreaBurst,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Event,
    Keyword,
    Ranged,
    Relation,
    Target,
    Trigger,
    TurnEnd,
    When,
    World,
    distance,
    get,
    power,
    would_hit_me,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Healed,
    Hit,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.movement import walk
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import squares as squares_of

MARTIAL = [Keyword.MARTIAL]
PRIMAL = [Keyword.PRIMAL]

_ENEMY_CLOSES = "an enemy moves adjacent to you"
_I_DROP_AN_ENEMY = "you reduce an enemy to 0 hit points"
_QUARRY_DROPS = "you reduce your quarry to 0 hit points"
_HELD_AND_HIT = (
    "you are hit by an attack that makes you slowed, immobilized, "
    "restrained, or dazed"
)


def _i_dropped_an_enemy(world: World, me: int, ev: Event) -> bool:
    """My damage took an enemy to 0 or below.

    `Dropped` names the creature and no one else, so it cannot answer
    "**you** reduce": read off `DamageApplied`, which carries the source,
    the target and what it left them on.
    """
    if getattr(ev, "source", None) != me:
        return False
    who = getattr(ev, "target", None)
    if who is None or who == me or getattr(ev, "hp", 1) > 0:
        return False
    return team(world, who) is not team(world, me)


def _my_quarry_dropped(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    return who is not None and world.relations.holds(Relation.QUARRY_OF, me, who)


def _is_marked(world: World, eid: int) -> bool:
    """"You must be marked" -- by anybody, which is what the line says."""
    return bool(world.relations.sources(Relation.MARKED_BY, eid))


def _ranged_row(ref: str) -> bool:
    p = get(ref or "")
    return p is not None and p.reach.kind in ("ranged", "area_burst")


def _enemy_moved_next_to_me(world: World, me: int, ev: Event) -> bool:
    """The *mover* is the enemy and the one it reached is me."""
    mover = getattr(ev, "actor", None)
    if mover is None or getattr(ev, "other", None) != me:
        return False
    return team(world, mover) is not team(world, me)


@power(
    "p217",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_ENEMY_CLOSES,
    on=Trigger(AdjacencyGained, when=_enemy_moved_next_to_me, text=_ENEMY_CLOSES),
)
def p217(c: Cast) -> None:
    c.shift(1)
    foe = getattr(c.trigger, "actor", None)
    held = squares_of(c.world, foe) if foe is not None else frozenset()
    paths = c.world.reachable_paths(c.me, 1 + c.wis_mod)
    away = sorted(
        sq for sq in paths if not any(distance(sq, at) <= 1 for at in held)
    )
    dest = c.choose(away, "p217: where to break off to")
    if dest is not None:
        walk(c.world, c.me, paths[dest])


@power(
    "p718",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p718(c: Cast) -> None:
    """Held for the encounter and ended by hand when the stance ends, the
    arrangement `fighter/level_6.py` settled: a second stance-clocked effect
    confuses `Effects.stance_of`."""
    stance = c.stance(label=c.ref)
    easy = c.ignores_difficult(on=c.me, until=When.ENCOUNTER)
    if easy is not None:
        stance.on_end.append(lambda: c.world.effects.end(easy, "stance ended"))


@power(
    "p926",
    level=10,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p926(c: Cast) -> None:
    """The speed only. The extra square of shift has no number to raise --
    see the file's docstring -- and is left unwritten rather than paid out
    as four more squares of walking, which is a different card."""
    c.bonus("speed", 4, on=c.me, until=When.EONT)


@power(
    "p10636",
    level=10,
    cls="ranger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_HELD_AND_HIT,
    on=Trigger(AttackRolled, when=would_hit_me, text=_HELD_AND_HIT),
)
def p10636(c: Cast) -> None:
    """Declared on the roll rather than on the hit: the die is down and the
    total is known, but the defence is read again once this window closes,
    so a bonus raised here can still turn the blow aside.

    What the attack *would have done* -- slowed, immobilized, restrained or
    dazed -- cannot be asked before it resolves, so that half of the printed
    Trigger is not in the predicate. It is in the report.
    """
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 4, on=c.me, until=When.EONT, once=True)


@power(
    "p10637",
    level=10,
    cls="ranger",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p10637(c: Cast) -> None:
    """Inert by declaration. Both halves are about the check that keeps a
    creature hidden -- the penalty for moving, and being given away by an
    attack -- and the engine rolls no such check: hiding is a state `c.hide`
    sets and `resolve` clears, with no number in between to modify."""
    c.note("p10637: moving costs nothing to stay unseen, and a miss does not give you away")


@power(
    "p10638",
    level=10,
    cls="ranger",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_I_DROP_AN_ENEMY,
    on=Trigger(DamageApplied, when=_i_dropped_an_enemy, text=_I_DROP_AN_ENEMY),
)
def p10638(c: Cast) -> None:
    """The openings are closed one enemy at a time: `c.no_provoke` with no
    `from_` names the target of the power, and this row has none."""
    for foe in c.enemies():
        c.no_provoke(from_=foe, until=When.EOT)
    c.move(c.speed_of(c.me))
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT)


@power(
    "p10639",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10639(c: Cast) -> None:
    """Resistance is a number on `Defences`, not a modifier, so it takes no
    `when=` gate -- "while you are bloodied" has to be put on and taken off
    by hand. `Bloodied` announces the crossing one way and `Healed` is the
    only event that can announce it back, so both are watched.
    """
    me = c.me
    stance = c.stance(label=c.ref)
    held: list[Effect] = []

    def toughen() -> None:
        if not held and c.bloodied(me):
            got = c.resist(c.wis_mod, on=me, until=When.ENCOUNTER)
            if got is not None:
                held.append(got)

    def soften() -> None:
        if held and not c.bloodied(me):
            c.world.effects.end(held.pop(), "no longer bloodied")

    toughen()
    watches = [
        c.watch(Bloodied, lambda ev: toughen(), until=When.ENCOUNTER, on=me, label=c.ref),
        c.watch(Healed, lambda ev: soften(), until=When.ENCOUNTER, on=me, label=c.ref),
    ]
    def pack_up() -> None:
        for watching in watches:
            c.world.effects.end(watching, "stance ended")
        if held:
            c.world.effects.end(held.pop(), "stance ended")

    stance.on_end.append(pack_up)


@power(
    "p13610",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("ally", 99, everyone=True, label="You and each ally in the burst"),
    keywords=PRIMAL,
    out_of_combat=True,
)
def p13610(c: Cast) -> None:
    """Inert by declaration: seeing in the dark is not a state a creature
    holds here -- line of effect is the whole of sight -- and there are no
    checks for the second half to improve."""
    c.note("p13610: the target sees in the dark, and notices more, for the encounter")


@power(
    "p13611",
    level=10,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p13611(c: Cast) -> None:
    """A one-square zone that ends on the creature that springs it.

    `c.hazard` is the wrong shape twice over: it bites at the start of a turn
    as well as on entry, and it keeps biting. The printed line fires once and
    the zone is gone.

    Going unnoticed without a Perception check is not written -- a zone is
    visible to everyone or to no one, with no check between.
    """
    room = sorted(sq for sq in c.area() if not c.in_squares([sq]))
    spot = c.choose(room, f"{c.ref}: where the snare is laid") if room else None
    if spot is None:
        return
    zone = c.zone({spot}, until=When.ENCOUNTER, label=c.ref)
    me = c.me

    def spring(ev: ZoneEntered) -> None:
        if ev.zone != zone or ev.actor == me or ev.actor not in c.enemies():
            return
        c.flat(5 + c.wis_mod, on=ev.actor)
        c.immobilized(on=ev.actor, until=When.EONT)
        c.world.zones.end(zone, "sprung")

    c.watch(ZoneEntered, spring, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p13612",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.FIRE, Keyword.ZONE],
)
def p13612(c: Cast) -> None:
    """"Enemies grant combat advantage **while in the zone**" is a hold that
    has to be taken off again when they leave, so it is granted on entry and
    ended on exit rather than handed a duration it cannot keep.

    The Move Action that relocates the zone is not written -- nothing moves a
    zone once it is placed.
    """
    zone = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
    me = c.me
    exposed: dict[int, Effect] = {}

    def expose(who: int) -> None:
        if who in exposed or who not in c.enemies():
            return
        got = c.grants_advantage(on=who, to="allies", until=When.ENCOUNTER)
        if got is not None:
            exposed[who] = got

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            expose(ev.actor)

    def left(ev: ZoneExited) -> None:
        if ev.zone == zone and ev.actor in exposed:
            c.world.effects.end(exposed.pop(ev.actor), "left the zone")

    def scorch(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(zone):
            c.flat(c.wis_mod, dtype=DamageType.FIRE, on=ev.actor)

    for who in c.world.zones.occupants(zone):
        expose(who)
    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(TurnEnd, scorch, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p13627",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.TELEPORTATION, Keyword.ZONE],
)
def p13627(c: Cast) -> None:
    """Two one-square zones, each the other's exit. The teleport is offered
    on entry rather than made automatic: the printed line is a free action
    the character may take, not something the ground does to them."""
    room = sorted(sq for sq in c.area() if not c.in_squares([sq]))
    if len(room) < 2:
        return
    first = c.choose(room, f"{c.ref}: the first gate")
    rest = [sq for sq in room if sq != first]
    second = c.choose(rest, f"{c.ref}: the second gate") if rest else None
    if first is None or second is None:
        return
    gates = {
        c.zone({first}, until=When.ENCOUNTER, label=c.ref): second,
        c.zone({second}, until=When.ENCOUNTER, label=c.ref): first,
    }
    me = c.me

    def step_through(ev: ZoneEntered) -> None:
        out = gates.get(ev.zone)
        if out is None or (ev.actor != me and ev.actor not in c.allies()):
            return
        if c.in_squares([out]):
            return
        if c.may("step through", who=ev.actor):
            c.teleport(0, who=ev.actor, to=out)

    c.watch(ZoneEntered, step_through, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p4411",
    level=10,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p4411(c: Cast) -> None:
    """Printed as a close burst 20 aimed at the ranger and the beast
    companion. With the companion unmodelled the burst reaches nobody else,
    so the header says what is left: a minor action to move your speed."""
    c.move(c.speed_of(c.me))


@power(
    "p4413",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p4413(c: Cast) -> None:
    """The class feature the printed line names is not in the tree, but the
    condition it stands for is a fact about the board -- nobody on your side
    is nearer the target than you -- and that can be asked outright.

    The step is granted rather than charged: nothing here spends the move
    action the printed line costs.
    """
    me = c.me
    stance = c.stance(label=c.ref)

    def nearest(ev: Hit) -> None:
        if ev.attacker != me or not _ranged_row(ev.power):
            return
        if ev.target not in c.enemies():
            return
        mine = distance_between(c.world, me, ev.target)
        if any(distance_between(c.world, f, ev.target) < mine for f in c.allies()):
            return
        if c.may("give ground", who=me):
            c.shift(c.wis_mod)

    watching = c.watch(Hit, nearest, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(watching, "stance ended"))


@power(
    "p4415",
    level=10,
    cls="ranger",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_is_marked,
)
def p4415(c: Cast) -> None:
    """Every mark on the ranger goes, whoever laid it. A mark is a relation
    held up by an effect, so ending the effect is what clears it -- dropping
    the relation alone would leave the hold live and it would be set again."""
    for eff in list(c.world.effects.of(c.me)):
        if Condition.MARKED in eff.conditions or any(
            kind is Relation.MARKED_BY for kind, _s, _t in eff.relations
        ):
            c.world.effects.end(eff, c.ref)
    c.shift(1)


@power(
    "p9357",
    level=10,
    cls="ranger",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
    trigger=_QUARRY_DROPS,
    on=Trigger(Dropped, when=_my_quarry_dropped, text=_QUARRY_DROPS),
)
def p9357(c: Cast) -> None:
    """The hit points are the surge's worth without the surge being spent --
    the printed line says "regain", not "spend a healing surge"."""
    c.heal(c.surge_value() + c.str_mod, on=c.me)
