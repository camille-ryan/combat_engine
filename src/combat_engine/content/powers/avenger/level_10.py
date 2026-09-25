"""Avenger, level 10: utility. Nine rows, none of which rolls an attack.

Four of them print a Trigger, so four are declared with `on=Trigger(...)`.
Two needed a predicate of their own: no ready-made one says "an enemy
adjacent to you damages you" -- `DamageApplied` names the dealer `source`,
which `by_me` and `about_me` both miss -- and none says "you roll
initiative".

`p3658` is the only row here that reaches into the relation table. Being
unseen is held as `HIDDEN_FROM` (the hidden creature, whoever cannot see
it), so *seeing through* it is clearing that one pair rather than granting
anything. The pairs are put back when the duration runs out, but only the
ones a live effect is still holding up -- an invisibility that expired in
the meantime is gone, and restoring it would be inventing one.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    ActionType,
    AttackRolled,
    Cast,
    DamageApplied,
    DamageRolled,
    DamageType,
    Defences,
    Dropped,
    Effect,
    Event,
    Initiative,
    Keyword,
    Melee,
    Relation,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    about_me,
    distance,
    power,
    spread,
    would_hit_me,
)
from combat_engine.engine.events import InitiativeRolled, RelationSet
from combat_engine.engine.query import adjacent, team
from combat_engine.engine.query import squares as squares_of

from .oath import oath_target, sworn

DIVINE = [Keyword.DIVINE]


def _resisted(world: World, who: int, dtype: DamageType) -> int:
    held = world.get(who, Defences)
    return held.resist.get(dtype, 0) if held is not None else 0


@power(
    "p10084",
    level=10,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p10084(c: Cast) -> None:
    """The resistance is cancelled on `DamageRolled` rather than lifted off
    the creature: `resolve.deal_damage` subtracts it after that event, so
    adding the same number to the mutable `amount` leaves exactly the damage
    an unresisting creature would take -- and does it per blow, which is
    what "any enemy adjacent to you" means when the enemies keep moving.

    Its end is the sworn enemy dropping, whoever that is by then; a closure
    over the creature would go on stripping after the oath was re-sworn.
    """
    me = c.me
    victim = oath_target(c)
    held = c.world.get(victim, Defences) if victim is not None else None
    kinds = sorted(k for k, n in (held.resist.items() if held else ()) if n > 0)
    if not kinds:
        c.note(f"{c.ref}: nothing sworn against carries a resistance")
        return
    pick = c.choose(kinds, f"{c.ref}: which resistance is stripped")
    if pick is None:
        return

    holder: list[Effect] = []

    def strip(ev: DamageRolled) -> None:
        who = ev.target
        if ev.dtype is not pick or ev.amount <= 0 or who == me:
            return
        if team(c.world, who) is team(c.world, me) or not c.adjacent(who):
            return
        ev.amount += _resisted(c.world, who, pick)

    def fell(ev: Dropped) -> None:
        if holder and sworn(c.world, me, ev.actor):
            c.world.effects.end(holder[0], "the sworn enemy went down")

    holder.append(
        c.watch(
            DamageRolled, strip, until=When.ENCOUNTER, window=Window.BEFORE,
            on=me, label=f"{c.ref} laid bare",
        )
    )
    guard = c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label=f"{c.ref} until it falls")
    holder[0].on_end.append(lambda: c.world.effects.end(guard, "the stripping ended"))


@power(
    "p2938",
    level=10,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.HEALING],
)
def p2938(c: Cast) -> None:
    """Regeneration is a `TurnStart` watcher, the arrangement every other
    regenerating row in the tree uses. It stops once the avenger is down:
    regeneration heals a creature that still has hit points."""
    me = c.me

    def mend(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost and c.wounded(on=me):
            c.heal(5, on=me)

    c.watch(TurnStart, mend, until=When.ENCOUNTER, on=me, label=f"{c.ref} regeneration")


@power(
    "p3658",
    level=10,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p3658(c: Cast) -> None:
    """Watches `RelationSet` as well as clearing what is already there: the
    printed line lasts a turn and a half, and something that goes unseen
    inside that window is seen too."""
    me = c.me
    lifted: set[int] = set()

    def unveil(who: int) -> None:
        if who != me and c.world.relations.holds(Relation.HIDDEN_FROM, who, me):
            c.world.relations.clear(Relation.HIDDEN_FROM, who, me, c.ref)
            lifted.add(who)

    for who in c.within(5):
        unveil(who)

    def hid(ev: RelationSet) -> None:
        if ev.kind_ is Relation.HIDDEN_FROM and ev.target == me and c.distance(ev.source) <= 5:
            unveil(ev.source)

    effect = c.watch(RelationSet, hid, until=When.EONT, on=me, label=f"{c.ref} true sight")

    def restore() -> None:
        for who in sorted(lifted):
            if c.world.effects.carries(Relation.HIDDEN_FROM, who, me):
                c.world.relations.set(Relation.HIDDEN_FROM, who, me)

    effect.on_end.append(restore)


_ROLLED_IN = "you roll initiative at the beginning of an encounter"


@power(
    "p5342",
    level=10,
    cls="avenger",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
    trigger=_ROLLED_IN,
    on=Trigger(InitiativeRolled, when=about_me, text=_ROLLED_IN),
)
def p5342(c: Cast) -> None:
    """The five goes on `Initiative.rolled`, not through `c.bonus`: nothing
    reads a modifier called "initiative", and `_roll_initiative` sorts the
    order from that field once every creature has rolled -- so the check is
    still open at the moment this answers it.

    "The first creature in the initiative order" is the first `TurnStart` of
    the fight, which is what `once=True` on an encounter-long watch gives:
    the order does not exist yet while this runs.
    """
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        init.rolled += 5
        if c.trigger is not None:
            c.trigger.rolled = init.rolled

    def step(ev: TurnStart) -> None:
        if not ev.ghost:
            c.shift(3, who=me)

    c.watch(TurnStart, step, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} first step")


@power(
    "p5343",
    level=10,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p5343(c: Cast) -> None:
    c.resist(5, until=When.EONT, on=c.me)


@power(
    "p7019",
    level=10,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.HEALING],
)
def p7019(c: Cast) -> None:
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="power")


_HURT_BY_A_NEIGHBOUR = "an enemy adjacent to you damages you"


def _adjacent_enemy_hurt_me(world: World, me: int, ev: Event) -> bool:
    """`DamageApplied` names the dealer `source`, so no ready-made predicate
    reaches it: `by_me` and `about_me` both read other fields."""
    who = getattr(ev, "source", None)
    if who is None or who == me or getattr(ev, "target", None) != me:
        return False
    if getattr(ev, "amount", 0) <= 0:
        return False
    return team(world, who) is not team(world, me) and adjacent(world, me, who)


@power(
    "p7020",
    level=10,
    cls="avenger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE, Keyword.TELEPORTATION],
    trigger=_HURT_BY_A_NEIGHBOUR,
    on=Trigger(DamageApplied, when=_adjacent_enemy_hurt_me, text=_HURT_BY_A_NEIGHBOUR),
)
def p7020(c: Cast) -> None:
    """Aimed off the event rather than off `c.target`. The dispatcher picks
    a triggered row's target from `ev.attacker` or `ev.actor`, and a damage
    event carries neither -- so the printed "the triggering enemy" has to be
    read here or the row blinks the wrong creature about.

    The second blink is measured from where the target is standing, because
    `c.teleport` offers only squares within the distance it is given and the
    printed line names a destination instead of a distance.
    """
    victim = getattr(c.trigger, "source", None)
    if victim is None or not c.first:
        return
    c.teleport(5, who=c.me)
    mine = squares_of(c.world, c.me)
    spots = sorted(
        sq
        for sq in spread(mine, 1) - mine
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    )
    if not spots:
        return
    there = squares_of(c.world, victim)
    dest = c.choose(spots, f"{c.ref}: where the target is dragged")
    if dest is None:
        return
    reach = max(1, min(distance(sq, dest) for sq in there))
    c.teleport(reach, who=victim, to=dest)


_I_AM_HIT = "you are hit by an attack"


@power(
    "p7021",
    level=10,
    cls="avenger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.IMPLEMENT],
    trigger=_I_AM_HIT,
    on=Trigger(AttackRolled, when=would_hit_me, text=_I_AM_HIT),
)
def p7021(c: Cast) -> None:
    """The die is rolled here rather than through `c.attack`, because there
    is nobody to attack -- the number *is* the defence, and `c.attack` would
    announce a swing at a creature this row never names.

    Declared on `AttackRolled` for the reason `p1443` is: `resolve.attack`
    reads the defence again once this window closes, so a row that raises
    (or lowers) it here still decides the blow. The bonus carries a kind of
    its own so that a result worse than the printed defence really is worse
    -- under `kind="power"` the larger of the two would simply win.
    """
    ev = c.trigger
    if ev is None:
        return
    rolled = c.world.rng.d20().total + c.wis_
    c.bonus(ev.vs, rolled - ev.defence, on=c.me, until=When.EOT, kind=c.ref, once=True)


@power(
    "p7022",
    level=10,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p7022(c: Cast) -> None:
    """"And you can hover" needs nothing said, the way `m2961a4` reads it:
    `movement.settle` is the only thing that brings a flyer down and it runs
    at the end of the creature's own turn, which is inside this duration."""
    c.mode("fly", 7, until=When.EONT, on=c.me)
