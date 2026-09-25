"""Avenger, level 2: utilities.

Seven of the ten are immediate or free actions with a printed Trigger, so
the file is mostly trigger declarations. Two shapes recur:

* **"your oath of enmity target drops to 0 hit points"** is `Dropped` plus
  `sworn(world, me, ev.actor)`. The dispatcher offers a row about a creature
  that is no longer alive, so nothing else is needed for it to fire.
* **"your oath of enmity target ends its turn ... not adjacent to you"** is
  `TurnEnd` plus the same question and a distance. `TurnEnd` rather than any
  movement event: the printed line is about where the creature *stopped*.

`p6995` is the one row with a clause that has nowhere to go -- concealment
is not state this engine keeps -- so the half that is sayable is written and
the other half is a note, the way the wizard's zones do it.
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
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    Cast,
    CloseBurst,
    Dropped,
    Event,
    Health,
    Hit,
    Keyword,
    Miss,
    Square,
    Trigger,
    TurnEnd,
    When,
    World,
    both,
    by_melee,
    distance,
    hits_me,
    power,
)
from combat_engine.engine.query import adjacent, squares

from .oath import swear, sworn

OATH_DROPS = "your oath of enmity target drops to 0 hit points"


def _oath_dropped(world: World, me: int, ev: Event) -> bool:
    return sworn(world, me, ev.actor)


def _oath_ended_apart(world: World, me: int, ev: Event) -> bool:
    """"Ends its turn in a square not adjacent to you"."""
    return sworn(world, me, ev.actor) and not adjacent(world, me, ev.actor)


def _bloodied(world: World, eid: int) -> bool:
    """"Requirement: you must be bloodied"."""
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _nearest_step(c: Cast, foe: int, steps: int) -> Square | None:
    """Where a move of `steps` ends up closest to `foe`.

    `c.shift` hands the choice to the decider, which with none installed
    takes the lowest-sorted square -- "as close to the target as possible"
    is an instruction rather than a choice, so the square is named.
    """
    options = c.world.reachable_squares(c.me, steps)
    goal = squares(c.world, foe)
    if not options or not goal:
        return None
    return min(options, key=lambda sq: (min(distance(sq, g) for g in goal), sq))


@power(
    "p12456",
    level=2,
    cls="avenger",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE],
    trigger=OATH_DROPS,
    on=Trigger(Dropped, when=_oath_dropped, text=OATH_DROPS),
)
def p12456(c: Cast) -> None:
    """"One **other** enemy": the creature that just went down is excluded
    by hand. It is filtered out of the candidates anyway -- a dropped
    creature is not alive -- but the row is offered by the dispatcher and
    the guard costs a line.
    """
    victim = c.target
    if victim is None or victim == getattr(c.trigger, "actor", None):
        return
    swear(c, victim)
    c.grants_advantage(on=victim, until=When.EONT)


_MELEE_AT_ME = "an enemy hits or misses you with a melee attack"


@power(
    "p2928",
    level=2,
    cls="avenger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.TELEPORTATION],
    trigger=_MELEE_AT_ME,
    on=[
        Trigger(Hit, when=both(hits_me, by_melee), text=_MELEE_AT_ME),
        Trigger(Miss, when=both(hits_me, by_melee), text=_MELEE_AT_ME),
    ],
)
def p2928(c: Cast) -> None:
    c.teleport(3)


@power(
    "p5336",
    level=2,
    cls="avenger",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    trigger=OATH_DROPS,
    on=Trigger(Dropped, when=_oath_dropped, text=OATH_DROPS),
)
def p5336(c: Cast) -> None:
    c.temp_hp(c.surge_value(), on=c.me)


@power(
    "p5337",
    level=2,
    cls="avenger",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p5337(c: Cast) -> None:
    """"Invisible until the end of the movement" is shorter than any
    duration the engine holds, so the hold is raised and ended here rather
    than clocked."""
    veil = c.invisible(on=c.me, until=When.EOT)
    c.move(c.speed_of())
    if veil is not None:
        c.world.effects.end(veil, "the movement ended")


@power(
    "p5338",
    level=2,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE],
)
def p5338(c: Cast) -> None:
    if c.target is not None and c.can_see():
        swear(c)


_OTHER_ENEMY_HITS = "an enemy other than your oath of enmity target hits you"


def _other_enemy_hits(world: World, me: int, ev: Event) -> bool:
    return hits_me(world, me, ev) and not sworn(world, me, ev.attacker)


@power(
    "p6991",
    level=2,
    cls="avenger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    trigger=_OTHER_ENEMY_HITS,
    on=Trigger(Hit, when=_other_enemy_hits, text=_OTHER_ENEMY_HITS),
)
def p6991(c: Cast) -> None:
    """Declared on `Hit` rather than on the roll: the resistance does not
    turn the blow aside, it only has to be standing before the damage is
    dealt, and the interrupt window of `Hit` is exactly that moment.
    """
    c.resist(5, until=When.EONT, on=c.me)


@power(
    "p6992",
    level=2,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    requires=_bloodied,
    requires_text="must be bloodied",
)
def p6992(c: Cast) -> None:
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 4, on=c.me, until=When.EONT)


@power(
    "p6993",
    level=2,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p6993(c: Cast) -> None:
    """The gate asks who is sworn at the moment the damage is rolled, not
    who was sworn now: half a dozen rows re-swear mid-fight and the bonus
    follows the oath rather than the creature it happened to name.
    """
    friend = c.target
    if friend is None:
        return
    world, me = c.world, c.me
    c.bonus(
        "damage",
        c.wis_mod,
        on=friend,
        until=When.EONT,
        kind="power",
        when=lambda ctx: sworn(world, me, ctx.get("target")),
    )


_OATH_APART = "your oath of enmity target ends its turn not adjacent to you"


@power(
    "p6994",
    level=2,
    cls="avenger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    trigger=_OATH_APART,
    on=Trigger(TurnEnd, when=_oath_ended_apart, text=_OATH_APART),
)
def p6994(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    steps = max(0, c.wis_mod)
    if foe is None or steps <= 0:
        return
    landing = _nearest_step(c, foe, steps)
    if landing is not None and landing != c.here:
        c.shift(steps, to=landing)


@power(
    "p6995",
    level=2,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p6995(c: Cast) -> None:
    """The concealment has no expression -- the engine keeps no such state
    -- and neither does a duration that runs until a pool of temporary hit
    points is gone. The temporary hit points are the half that is sayable.
    """
    c.temp_hp(5 + c.level, on=c.me)
    c.note(f"{c.ref}: you also have concealment while those last, and there is none here")
