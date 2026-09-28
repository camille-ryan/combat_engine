"""Battlemind: the stat block each of these rows is printed beside.

Every one of them is the second card of a stance, a form or a zone -- the
thing the battlemind may do for as long as the first card holds. They had
no ids until the importer began minting one per block, so each was folded
into its parent as a subscription, which cost the printed action nothing.
Declared properly they cost what the card says: an opportunity action, an
immediate interrupt, a move.

`active` is their shared Requirement. Every parent here leaves a hold
labelled with its own ref -- that is what `c.stance` does -- except the one
that lays a zone, which needs the battlemind standing in it as well.

One of the six is left out: `p12426b`, whose damage is owed for a space the
shift *passes through*, and a shift is a single `step` to its destination
with no squares in between. See `docs/blocked.json`.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.content.powers.cards import active
from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    DAILY,
    INTERRUPT,
    MOVE,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    SELF,
    Attack,
    AttackDeclared,
    Cast,
    DamageApplied,
    Hit,
    Keyword,
    Melee,
    MoveStart,
    SavingThrow,
    Trigger,
    TurnEnd,
    When,
    Window,
    World,
    power,
)
from combat_engine.engine.events import Event
from combat_engine.engine.query import adjacent, allies, enemies
from combat_engine.engine.types import Relation
from combat_engine.engine.zones import Zone

from . import PSIONIC_WEAPON, shift_beside

_MARKED_WALK = (
    "an adjacent enemy marked by you moves without shifting on its turn"
)


def _walks_past_me(world: World, me: int, ev: Event) -> bool:
    """The commonest battlemind trigger, printed word for word on three rows.

    `MoveStart` rather than `MoveEnd`: the swing is an opportunity action and
    belongs in the interrupt window, and by the time the move has finished the
    enemy is no longer adjacent -- which is false exactly when the row should
    fire. `kind_` is what separates a walk from a shift.
    """
    who = ev.actor
    return (
        ev.kind_ == "walk"
        and world.turn == who
        and who in enemies(world, me)
        and adjacent(world, me, who)
        and world.relations.holds(Relation.MARKED_BY, me, who)
    )


def _hurts_an_ally(world: World, me: int, ev: Event) -> bool:
    """"An enemy marked by you deals damage to an ally with an attack that
    does not include you as a target."

    The last clause is read as "the damage did not land on me". `DamageApplied`
    carries one victim and no target list, so a burst that caught the
    battlemind as well as the ally still answers here.
    """
    return (
        ev.amount > 0
        and ev.target != me
        and ev.target in allies(world, me)
        and ev.source in enemies(world, me)
        and world.relations.holds(Relation.MARKED_BY, me, ev.source)
    )


def _in_my_zone(ref: str) -> Callable[[World, int], bool]:
    """"While you are within the zone, you can use this power."

    Two questions rather than one: the parent's zone has to be standing, and
    the battlemind has to be inside it. `active` asks neither -- a zone is not
    a hold on its creature.
    """

    def check(world: World, eid: int) -> bool:
        from combat_engine.engine.query import squares

        mine = squares(world, eid)
        return any(
            zone.label == ref and zone.owner == eid and bool(zone.squares & mine)
            for _, zone in world.each(Zone)
        )

    return check


def _swings_inside(ref: str) -> Callable[[World, int, Event], bool]:
    """"An enemy within the zone makes an attack that does not include you."""

    def check(world: World, me: int, ev: Event) -> bool:
        from combat_engine.engine.query import squares

        foe = ev.attacker
        if foe == me or ev.target == me or foe not in enemies(world, me):
            return False
        standing = squares(world, foe)
        return any(
            zone.label == ref and zone.owner == me and bool(zone.squares & standing)
            for _, zone in world.each(Zone)
        )

    return check


@power(
    "p2623b",
    level=1,
    cls="battlemind",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
    requires=active("p2623"),
    requires_text="the p2623 power must be active",
    trigger=_MARKED_WALK,
    on=Trigger(MoveStart, _walks_past_me, _MARKED_WALK),
)
def p2623b(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.con_mod)


@power(
    "p2629b",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
    requires=active("p2629"),
    requires_text="the p2629 power must be active",
    trigger=_MARKED_WALK,
    on=Trigger(MoveStart, _walks_past_me, _MARKED_WALK),
)
def p2629b(c: Cast) -> None:
    """The pull is a free action offered at the end of the target's turn, so
    it is a watch rather than a second line of this body."""
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w(), c.con_mod)

    def reel(ev: TurnEnd) -> None:
        if ev.actor == victim and c.may("pull it back", who=c.me):
            c.pull(c.speed_of(victim), on=victim)

    c.watch(TurnEnd, reel, until=When.EOTNT, on=c.me)


@power(
    "p2636b",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(CON, vs=AC),
    requires=active("p2636"),
    requires_text="the p2636 power must be active",
    trigger=_MARKED_WALK,
    on=Trigger(MoveStart, _walks_past_me, _MARKED_WALK),
)
def p2636b(c: Cast) -> None:
    """The damage line carries no ability modifier at this tier. The forced
    failure answers `SavingThrow` in the interrupt window, since the throw is
    announced before it is acted on."""
    if not c.strike():
        return
    victim = c.target
    c.damage(c.w())

    def botch(ev: SavingThrow) -> None:
        if ev.actor == victim:
            c.unsave(ev)

    c.watch(
        SavingThrow, botch, until=When.EOT, on=c.me, once=True, window=Window.BEFORE
    )


@power(
    "p13037b",
    level=2,
    cls="battlemind",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.STANCE, Keyword.WEAPON],
    requires=active("p13037"),
    requires_text="the p13037 power must be active",
    trigger="an enemy marked by you damages an ally with an attack that leaves you out",
    on=Trigger(
        DamageApplied,
        _hurts_an_ally,
        "an enemy marked by you damages an ally with an attack that leaves you out",
    ),
)
def p13037b(c: Cast) -> None:
    """"A melee basic attack or a charge attack" is one swing either way: the
    charge is only there to cover the distance, so the run happens first when
    the enemy is out of reach. Whether it landed is read off the bus, since
    `c.basic` reports that the row was used and not that it hit."""
    foe = getattr(c.trigger, "source", None)
    if foe is None:
        return
    if not c.adjacent(foe):
        c.run_at(foe)
    landed: list[int] = []

    def seen(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == foe:
            landed.append(1)

    watcher = c.world.bus.on(Hit, seen, owner=c.me)
    try:
        c.basic(on=foe)
    finally:
        c.world.bus.off(watcher)
    if landed:
        c.prone(on=foe)


@power(
    "p13057b",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(CON, vs=AC),
    charges=True,
    requires=_in_my_zone("p13057"),
    requires_text="you must be inside the p13057 zone",
    trigger="an enemy in the zone attacks somebody other than you",
    on=Trigger(
        AttackDeclared,
        _swings_inside("p13057"),
        "an enemy in the zone attacks somebody other than you",
    ),
)
def p13057b(c: Cast) -> None:
    """`charges=True` is the only header field that says "measure the reach
    *after* the movement". The printed Effect closes the distance before the
    swing, so without it the row is refused whenever the enemy is anywhere in
    the zone but not already adjacent -- which is every situation it is for.
    """
    foe = c.target
    if foe is None:
        return
    shift_beside(c, max(1, c.speed_of()), foe)
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.mark(until=When.EONT)


@power(
    "p12426b",
    level=9,
    cls="battlemind",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.FORCE, Keyword.STANCE],
    requires=active("p12426"),
    requires_text="the p12426 power must be active",
    dropped=("c.shift(path=)", "c.phasing(through=)"),
)
def p12426b(c: Cast) -> None:
    """The shift is exact. Passing **through** the space of an enemy marked by
    you is not: `movement.shift` is one step to the destination, so no square
    between the two is ever entered and nothing announces one -- the force
    damage the first such entry charges has no moment to happen in.
    `c.phasing` would open everybody's space, not one named creature's.
    """
    c.shift(3)
