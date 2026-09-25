"""Rogue, level 10: utility, and every row of it printed behind a skill.

The Prerequisite lines gate *taking* these at character creation rather than
using them, so none is declared as a `requires` -- the reading `level_2.py`
settled. `p1396`'s **Requirement** is a different thing and is declared:
that one is checked every time the row is used.

`p1509` is its Thievery check and nothing else, so it carries
`out_of_combat=True`.

`p1515` has no check to succeed on either, but what the check buys is a
thing the board holds: the grab comes off. So it is written as the outcome
rather than declared inert.

`p142` costs one clause. The printed way out of it is the target spending a
standard action on an attack against the rogue, and granting a creature an
attack it does not have needs a row to grant -- `c.grant_row` takes a ref
and there is none for this. It is written down rather than approximated.

The rows printed in the later books follow below. Shifting *through* an
occupied square is not a thing the model can say -- a shift is a shift --
so where a row offers it, what is written is the distance.
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
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackDeclared,
    Cast,
    Condition,
    Event,
    Hit,
    Keyword,
    Melee,
    Relation,
    Trigger,
    When,
    World,
    both,
    by_melee,
    closed_on_me,
    distance,
    enemy_within,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.query import adjacent, creatures, distance_between, hidden_from, team
from combat_engine.engine.query import squares as squares_of

MARTIAL = [Keyword.MARTIAL]

#: What holds a creature in place well enough that escaping it is a thing
#: you roll for: a grab, or being tied down.
_HELD = (Condition.GRABBED, Condition.RESTRAINED)


def _is_hidden(world: World, eid: int) -> bool:
    return bool(hidden_from(world, eid))


@power(
    "p1396",
    level=10,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_is_hidden,
    requires_text="must be hidden",
)
def p1396(c: Cast) -> None:
    """Nothing in this engine gives a hiding creature away for walking --
    only attacking does, in `resolve.attack` -- so "you remain hidden during
    the move" is held by reasserting it against whoever could not see the
    rogue when it set off, rather than left to luck.

    The printed Stealth check and the square with cover to end in are both
    skill, and the model has neither, so the move is unfiltered.
    """
    unseeing = sorted(hidden_from(c.world, c.me))
    c.move(c.speed_of())
    for watcher in unseeing:
        c.hide(from_=watcher)


@power(
    "p142",
    level=10,
    cls="rogue",
    usage=DAILY,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
)
def p142(c: Cast) -> None:
    """Into the target's square, and carried wherever it goes.

    `c.ride` is "when the target moves, you move with it" exactly:
    `movement.step` carries a mount's passengers, and quietly, which is
    right -- the rogue is being taken along rather than moving.

    The only way into an occupied square is a shift, which provokes nothing,
    so the printed "provoking opportunity attacks as normal" is opened by
    hand against the enemies whose reach the rogue is leaving.
    """
    victim = c.target
    if victim is None:
        return
    seat = sorted(squares_of(c.world, victim))
    watching = [f for f in c.enemies() if adjacent(c.world, c.me, f)]
    if not seat or not c.shift(to=seat[0], share=True):
        return
    for foe in watching:
        if not adjacent(c.world, c.me, foe):
            c.provoke(foe, on=c.me, why=c.ref)
    c.ride(on=victim)
    c.grants_advantage(on=victim, until=When.ENCOUNTER, to=c.me)
    me = c.me
    c.penalty(
        "attack",
        4,
        on=victim,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == me,
    )


@power(
    "p1509",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p1509(c: Cast) -> None:
    c.note("p1509: no -10 on the next attempt to pick a pocket in a fight")


@power(
    "p1515",
    level=10,
    cls="rogue",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1515(c: Cast) -> None:
    """Whatever is holding the rogue stops holding it.

    A grab is a relation held up by an effect, so ending the effect is the
    escape; a relation left standing without one is cleared after, because
    nothing else would ever come to.
    """
    for effect in list(c.world.effects.of(c.me)):
        held = any(card in _HELD for card in effect.conditions)
        bound = any(
            kind is Relation.GRABBED_BY and target == c.me
            for kind, _source, target in effect.relations
        )
        if held or bound:
            c.world.effects.end(effect, c.ref)
    for grabber in c.world.relations.sources(Relation.GRABBED_BY, c.me):
        c.world.relations.clear(Relation.GRABBED_BY, grabber, c.me, c.ref)


_CLOSED_IN = "an enemy enters a square adjacent to you"


def _nobody_near(world: World, eid: int) -> bool:
    """The printed Requirement: no creature within 3 squares."""
    return not any(
        other != eid and distance_between(world, eid, other) <= 3
        for other in creatures(world)
    )


def _enemy_swings_at_my_neighbour(world: World, me: int, ev: Event) -> bool:
    friend = getattr(ev, "target", None)
    attacker = getattr(ev, "attacker", None)
    if friend is None or attacker is None or friend == me:
        return False
    if team(world, friend) is not team(world, me):
        return False
    if team(world, attacker) is team(world, me):
        return False
    return adjacent(world, me, friend) and by_melee(world, me, ev)


def _beside(c: Cast, victim: int, squares_: int) -> bool:
    """Shift up to `squares_` squares and end adjacent to `victim`."""
    if c.adjacent(victim):
        return True
    standing = squares_of(c.world, victim)
    here = c.here
    room = sorted(
        sq
        for sq in spread(standing, 1) - standing
        if c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and distance(here, sq) <= squares_
    )
    if not room:
        return False
    where = c.choose(room, "where you come up beside it")
    return where is not None and c.shift(to=where)


@power(
    "p10776",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p10776(c: Cast) -> None:
    """The opening outlives the window that grants it: the watch runs to the
    start of the next turn, and each opening it hands out runs to the end of
    the fight."""
    me = c.me

    def noticed(ev: AttackDeclared) -> None:
        if ev.target == me and ev.attacker != me and ev.attacker in c.enemies():
            c.grants_advantage(on=ev.attacker, until=When.ENCOUNTER)

    c.watch(
        AttackDeclared, noticed, until=When.SONT, on=c.me,
        label=f"{c.ref} marks them",
    )


@power(
    "p10777",
    level=10,
    cls="rogue",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="an ally adjacent to you is hit by an enemy's melee attack",
    on=Trigger(
        AttackDeclared,
        _enemy_swings_at_my_neighbour,
        "an ally adjacent to you is hit by an enemy's melee attack",
    ),
)
def p10777(c: Cast) -> None:
    """Taking a blow over is moving it before it is rolled -- `c.redirect`
    only works on `AttackDeclared`, and by the roll there is a result. So
    the printed "is hit by" is declared one beat earlier, which is the only
    beat at which the swap can mean anything.

    The last clause adds Intelligence to the rogue's Sneak Attack, and the
    model has no sneak attack, so there is nothing to add it to.
    """
    friend = getattr(c.trigger, "target", None)
    attacker = getattr(c.trigger, "attacker", None)
    if friend is None or attacker is None:
        return
    c.swap(friend)
    c.redirect(to=c.me)
    c.grants_advantage(on=attacker, until=When.ENCOUNTER)


@power(
    "p12725",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    trigger=_CLOSED_IN,
    on=Trigger(AdjacencyGained, both(closed_on_me, enemy_within(1)), _CLOSED_IN),
)
def p12725(c: Cast) -> None:
    """"A square that is not adjacent to the target" names where the shift
    ends, so the options are filtered rather than handed to the decider."""
    victim = c.target
    if victim is None:
        return
    c.immobilized(until=When.SOTNT)
    beside = spread(squares_of(c.world, victim), 1)
    room = sorted(
        sq
        for sq in c.world.reachable_squares(c.me, max(1, c.dex_mod))
        if sq not in beside
    )
    where = c.choose(room, "where you get clear to") if room else None
    if where is not None:
        c.shift(to=where)


@power(
    "p12726",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    trigger=_CLOSED_IN,
    on=Trigger(AdjacencyGained, both(closed_on_me, enemy_within(1)), _CLOSED_IN),
)
def p12726(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.may("shove it a square", who=c.me):
        c.slide(1)
    _beside(c, victim, 2)
    c.grants_advantage()

    def theirs(ctx: dict) -> bool:
        return ctx.get("attacker") == victim

    for wall in (AC, FORT, REF, WILL):
        c.bonus(wall, 2, on=c.me, until=When.EONT, when=theirs)


@power(
    "p12727",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p12727(c: Cast) -> None:
    c.note("p12727: draw, stow or retrieve one item on the target, unnoticed if hidden")


@power(
    "p2295",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p2295(c: Cast) -> None:
    c.shift(c.speed_of())


@power(
    "p2297",
    level=10,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_nobody_near,
    requires_text="no creature may be within 3 squares",
)
def p2297(c: Cast) -> None:
    """"Until you attack" needs no clock: `resolve.attack` gives a hiding
    creature away for whoever swung. What is left is the turn boundary."""
    c.hide(until=When.EONT)


@power(
    "p4498",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p4498(c: Cast) -> None:
    c.ignores_difficult(until=When.EONT)
    c.move(c.speed_of() + 4)


@power(
    "p4500",
    level=10,
    cls="rogue",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p4500(c: Cast) -> None:
    near = sorted(c.within(5, side="enemy"))
    foe = c.choose(near, "who you study") if near else None
    if foe is None:
        return
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "p7505",
    level=10,
    cls="rogue",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "you are hit by a melee attack"),
)
def p7505(c: Cast) -> None:
    c.shift(c.speed_of() // 2)
