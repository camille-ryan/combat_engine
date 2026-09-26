"""Druid, level 0: the class features and the sentinel's companion rows.

Two things settle most of this file.

**Species is not knowable.** `c.call_companion` builds a body whose numbers
come off its owner and the spec names no database ref for a wolf, a bear or
a living zephyr, so "your *wolf* animal companion" is read as "your animal
companion" -- the precedent `ranger/level_2_b.py` set, and for the same
reason: a question that is always false is what a broken row looks like.

**Cantrips are cantrips.** Four of the rows below produce light, open a
door, smell a corpse or pull a rope out of the ground. Those carry
`out_of_combat=True` rather than an invented combat effect.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Companion,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Square,
    Summon,
    Trigger,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.query import distance_between
from combat_engine.engine.query import squares as squares_of

PRIMAL = [Keyword.PRIMAL]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]

_COMPANION_HIT = "your animal companion hits an enemy within 5 squares of you"


def _companion_of(world: World, owner: int) -> int | None:
    """`c.companion` without a `Cast`, for a trigger predicate."""
    for eid in world.having(Companion):
        if world.get(eid, Companion).owner == owner:
            return eid
    return None


def _companion_hit_near_me(world: World, me: int, ev: Hit) -> bool:
    beast = _companion_of(world, me)
    if beast is None or ev.attacker != beast:
        return False
    return distance_between(world, me, ev.target) <= 5


def _free_square_beside(c: Cast, thing: int) -> Square | None:
    """An empty square touching `thing`, for a slide that names where to."""
    theirs = squares_of(c.world, thing)
    if not theirs:
        return None
    for sq in sorted(spread(theirs, 1) - theirs):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


@power(
    "p13506",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13506(c: Cast) -> None:
    """The companion's half is an Effect line, so it happens whether or not
    the druid's own swing lands. "Its animal attack" is whatever that
    creature's basic attack is -- `c.basic(who=)` reads `Powers.basic`,
    which is the only place a companion's attack is recorded.
    """
    dice = c.w(3 if c.level >= 27 else 2 if c.level >= 17 else 1)
    if c.strike():
        c.damage(dice, c.wis_mod)

    beast = c.companion()
    if beast is None:
        return
    c.move_companion(c.speed_of(beast))
    reachable = c.within(1, of=beast, side="enemy")
    if reachable:
        c.basic(who=beast, on=reachable[0])


@power(
    "p13524",
    level=0,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL,
    requires_text="must be used at the end of an extended rest",
    out_of_combat=True,
)
def p13524(c: Cast) -> None:
    """Raising the dead between fights: the target is off the board, and the
    surges the ritual costs cannot be regained until three milestones, which
    is a scale no encounter measures."""
    c.note(f"{c.ref}: the dead are restored, at the cost of four surges")


@power(
    "p13540",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PRIMAL,
    trigger=_COMPANION_HIT,
    on=Trigger(Hit, _companion_hit_near_me, _COMPANION_HIT),
)
def p13540(c: Cast) -> None:
    """The printed Target is the creature the companion just hit, which the
    targeting layer never chose -- it is read off the event instead."""
    ev = c.trigger
    if ev is not None:
        c.prone(on=ev.target)


@power(
    "p13541",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PRIMAL,
)
def p13541(c: Cast) -> None:
    """The companion is not a creature the targeting layer offers -- it takes
    no turn and is on nobody's side -- so it is reached through
    `c.companion()` and the burst is the reach rather than the filter."""
    beast = c.companion()
    if beast is not None and distance_between(c.world, c.me, beast) <= 5:
        c.resist(10, on=beast, until=When.EONT)


@power(
    "p15852",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p15852(c: Cast) -> None:
    """"Difficult terrain for all creatures except you" is the zone plus one
    exemption: `c.zone(difficult=<word>)` labels the going and
    `c.ignores_difficult(<word>)` is the druid stepping over it. A bare
    `difficult=True` would slow the caster too.

    Dismissing the zone as a minor action is dropped -- `sustain=` holds a
    zone up, and nothing takes one down early. See the report.
    """
    aim = c.origin or c.here
    if aim is None:
        return
    size = 3 if c.level >= 21 else 2 if c.level >= 11 else 1
    c.zone(spread({aim}, size), until=When.ENCOUNTER, difficult=c.ref)
    c.ignores_difficult(c.ref, on=c.me, until=When.ENCOUNTER)


@power(
    "p15853",
    level=0,
    cls="druid",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.CONJURATION],
)
def p15853(c: Cast) -> None:
    """A conjuration that carries things. It occupies no square against
    anybody -- the printed line never says it blocks -- so `solid` is left
    off, which is the default reading for a conjuration.

    Everything the spirit then *does* is object handling and lamplight, so
    the minor, move and free actions listed are noted rather than modelled.
    """
    c.conjure(at=c.origin, label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=5)


@power(
    "p15854",
    level=0,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p15854(c: Cast) -> None:
    """"Nothing you do with this power can deal damage or hinder another
    creature's actions" is the printed Special, and it is also the reason
    this is declared inert rather than written."""
    c.note(f"{c.ref}: brighter light, an unlatched door, a gust, a spark")


@power(
    "p15855",
    level=0,
    cls="druid",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p15855(c: Cast) -> None:
    """Four senses, all of them skill checks. The +5 to Perception and
    Insight is the only number and neither skill is rolled in a fight."""
    c.note(f"{c.ref}: senses disease, plants, poison and the dead nearby")


@power(
    "p15856",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=PRIMAL,
)
def p15856(c: Cast) -> None:
    """"Not created by a power" falls out for free: rough ground made by a
    power lives on its `Zone`, and only the map's own squares are in
    `Grid.difficult`. So clearing those and putting them back when the
    effect ends says the printed line exactly, and a zone laid over the
    same squares is untouched.

    "Composed of grass, underbrush or vines" is not asked -- the grid's
    label for a square is a word the map chose and there is no list of
    which words are plants.
    """
    cleared = {
        sq: kind
        for sq in spread({c.here}, 1)
        if (kind := c.world.grid.difficult.get(sq)) is not None
    }
    if not cleared:
        return
    for sq in cleared:
        del c.world.grid.difficult[sq]
    hold = c.effect(c.ref, until=When.EONT, on=c.me)
    if hold is not None:
        hold.on_end.append(lambda: c.world.grid.difficult.update(cleared))


@power(
    "p15857",
    level=0,
    cls="druid",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p15857(c: Cast) -> None:
    """Fifty feet of rope. The engine has no rope."""
    c.note(f"{c.ref}: a vine that serves as a silk rope")


@power(
    "p15858",
    level=0,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.SUMMONING],
    summon=Summon(),
)
def p15858(c: Cast) -> None:
    """The printed block is "a creature of your Primal Aspect of your level
    or lower" and prints no numbers at all, so the summon takes `Summon`'s
    defaults -- the summoner's defences, a surge's worth of hit points, no
    attack of its own. The actions it can be commanded to take are the ones
    its own entry lists, and there is no entry.

    The surge it costs when it falls is the half that is printed in
    mechanics, and that is watched for. Dismissing it as a minor action is
    dropped with the other dismissals; see the report.
    """
    beast = c.summon_inline(get(c.ref).summon, at=c.origin)

    def fell(ev: Dropped) -> None:
        if ev.actor == beast:
            c.spend_surge(on=c.me)

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=c.me, once=True, label=c.ref)


@power(
    "p16117",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PRIMAL,
    trigger=_COMPANION_HIT,
    on=Trigger(Hit, _companion_hit_near_me, _COMPANION_HIT),
)
def p16117(c: Cast) -> None:
    """The second slide names its destination -- "to a square adjacent to the
    zephyr" -- so the square is found first and passed as `to=`; handed to
    the decider a five-square slide would happily go the other way.
    """
    ev = c.trigger
    beast = c.companion()
    if ev is None or beast is None:
        return
    c.slide(3, on=beast)
    landing = _free_square_beside(c, beast)
    if landing is not None:
        c.slide(5, on=ev.target, to=landing)
