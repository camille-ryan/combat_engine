"""Ranger, level 6: utility.

`p748` is the one that lands on the board. Adjacency is derived in exactly
one place -- `movement.step` diffs who the mover is next to and announces it
-- so "an enemy moves adjacent to you" is `AdjacencyGained` with the enemy
as the mover, declared with `on=` rather than quoted.

`p925` hands an ally a bonus to a skill it is not trained in. The model has
no skills and rolls no checks, so it is inert by declaration. `p10624` and
`p4397` are the same shape -- a check rerolled -- and are declared the same
way.

The later books add two zones and a handful of steps. A zone that bites is
`c.zone` plus a watch rather than `c.hazard`, wherever the printed line says
*ends its turn there*: `c.hazard` also bites on entry and at the start of a
turn, which is a different and more generous card.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
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
    REF,
    SELF,
    WILL,
    AreaBurst,
    Cast,
    CloseBurst,
    Event,
    Keyword,
    Ranged,
    Relation,
    Target,
    Trigger,
    TurnEnd,
    When,
    World,
    power,
)
from combat_engine.engine.events import AdjacencyGained, Dropped
from combat_engine.engine.query import distance_between, enemies, team

MARTIAL = [Keyword.MARTIAL]

_ENEMY_CLOSES = "an enemy moves adjacent to you"
_QUARRY_DROPS = "you reduce your quarry to 0 hit points"


def _my_quarry_dropped(world: World, me: int, ev: Event) -> bool:
    """The creature that just went down was the one this ranger had named.

    Relational, like the warlock's curse: a second ranger's quarry is not
    this one's, so the question is asked of the relation rather than of a
    label anybody could be carrying.
    """
    who = getattr(ev, "actor", None)
    return who is not None and world.relations.holds(Relation.QUARRY_OF, me, who)


def _two_enemies_close(world: World, eid: int) -> bool:
    """"You must be within 2 squares of at least two enemies.\""""
    near = [f for f in enemies(world, eid) if distance_between(world, eid, f) <= 2]
    return len(near) >= 2


def _enemy_moved_next_to_me(world: World, me: int, ev: Event) -> bool:
    """The *mover* is the enemy and the one it reached is me.

    Every step emits the pair both ways round, so reading `actor` alone
    would also answer the ranger walking up to somebody -- which is not what
    the line says.
    """
    mover = getattr(ev, "actor", None)
    if mover is None or getattr(ev, "other", None) != me:
        return False
    return team(world, mover) is not team(world, me)


@power(
    "p748",
    level=6,
    cls="ranger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_ENEMY_CLOSES,
    on=Trigger(AdjacencyGained, when=_enemy_moved_next_to_me, text=_ENEMY_CLOSES),
)
def p748(c: Cast) -> None:
    c.shift(c.wis_mod)


@power(
    "p925",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p925(c: Cast) -> None:
    c.note(f"p925: +{c.wis_mod} to one skill the ranger has and the ally does not")


@power(
    "p10621",
    level=6,
    cls="ranger",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(5),
    target=Target("ally", 2, label="You and one ally in the burst"),
    keywords=MARTIAL,
)
def p10621(c: Cast) -> None:
    """The "ally" pool includes the caster, which is what "you and one ally"
    means. The Beast line adds squares for the companion; it is not
    modelled, so that clause is dropped."""
    c.shift(1, who=c.target)


@power(
    "p10623",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10623(c: Cast) -> None:
    """The +1 only. The second sentence raises it to +2 on any turn in which
    no off-hand attack was made, and nothing announces an off-hand attack --
    the hand is an argument to `c.w`, not anything the bus carries -- so
    there is no moment at which the larger bonus could be worked out.

    Written as a gate on the grip rather than as a plain +1: the printed
    bonus only applies while two melee weapons are held, and a stance is
    kept across a change of hands.
    """
    me = c.me
    stance = c.stance(label=c.ref)
    held = c.bonus(
        AC,
        1,
        on=me,
        until=When.ENCOUNTER,
        when=lambda _ctx: c.wielding("two-weapon"),
    )
    if held is not None:
        stance.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p10624",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you make a Stealth check and dislike the result",
    out_of_combat=True,
)
def p10624(c: Cast) -> None:
    """Inert by declaration: nothing announces a check and no roll takes it,
    so there is nothing for `on=` to watch. Same shape as `p925`."""
    c.note(f"p10624: the check is rolled again with a +{c.wis_mod} bonus")


@power(
    "p13607",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("ally", 1, label="You or one ally in the burst"),
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p13607(c: Cast) -> None:
    # `c.may` asks the target, which is the creature whose surge it is.
    if c.may("spend a healing surge"):
        c.surge()


@power(
    "p13609",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p13609(c: Cast) -> None:
    """A zone plus a watch, not `c.hazard`: the printed line bites only on an
    enemy *ending* its turn there, and `c.hazard` bites on entry and at the
    start of a turn as well.

    The Move Action that relocates the zone is not written -- nothing moves a
    zone once it is placed -- and is in the report.
    """
    zone = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
    me = c.me

    def scour(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(zone):
            c.flat(c.wis_mod, on=ev.actor)

    c.watch(TurnEnd, scour, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p13626",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.TELEPORTATION],
)
def p13626(c: Cast) -> None:
    c.teleport(5)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 5, on=c.me, until=When.EONT)


@power(
    "p4397",
    level=6,
    cls="ranger",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you roll an Endurance check and dislike the result",
    out_of_combat=True,
)
def p4397(c: Cast) -> None:
    c.note("p4397: the check is rolled again, and the second result stands")


@power(
    "p4400",
    level=6,
    cls="ranger",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_two_enemies_close,
)
def p4400(c: Cast) -> None:
    """"Adjacent to at any time during this shift" is counted at the two ends
    of it. The squares in between are not walked one at a time here -- the
    decider picks a destination and `c.shift` goes there -- so the union of
    who was in reach before and after is the whole of what can be counted.
    """
    touched = {f for f in c.enemies() if c.adjacent(f)}
    c.shift(1 + c.wis_mod)
    touched |= {f for f in c.enemies() if c.adjacent(f)}
    if not touched:
        return
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, len(touched), on=c.me, until=When.EONT)


@power(
    "p9354",
    level=6,
    cls="ranger",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_QUARRY_DROPS,
    on=Trigger(Dropped, when=_my_quarry_dropped, text=_QUARRY_DROPS),
)
def p9354(c: Cast) -> None:
    """The new quarry is chosen from the enemies still standing within 5.

    `c.quarry` is what makes `c.is_quarry` true for the rows that ask, and
    the advantage is a separate hold, as the printed line has it.
    """
    pool = [f for f in c.within(5, side="enemy") if c.can_see(f)]
    chosen = c.choose(pool, f"{c.ref}: the next quarry") if pool else None
    if chosen is None:
        return
    c.quarry(on=chosen)
    c.grants_advantage(on=chosen, until=When.EONT)
