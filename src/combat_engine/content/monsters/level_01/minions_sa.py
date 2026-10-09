"""Monster abilities, level 1, minions: the whole undeclared set.

Thirty-two stat blocks, 61 rows. Five of the blocks print no ability at all
and so have no ref to decorate; they are not here and are not a gap.

The conventions, and the judgement calls that are not obvious:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=6)`) and the damage line goes in the
  header as data, `kind=MINION` for a minion's fixed number and
  `kind=LIMITED` for the one encounter attack in the file, so an MM1 block
  can be rescaled to MM3 maths later;
* **"4 damage (5 damage with combat advantage)" is two numbers and the
  header holds one**, so the bigger one is the body's, and the advantage is
  read off the roll (`result.advantage`) rather than asked of the board
  afterwards -- `resolve.attack` clears the grant the moment the attack is
  over, so asking again is always too late;
* a printed range band -- "10/20", "5/10" -- takes the **normal** range, so
  the creature shoots inside the band where it has no penalty;
* a **trait** is a row that costs no action, has no target, and arms the
  gates that hold it for the rest of the fight. Several rows the database
  files as standard actions are plainly traits and are written as such;
* **"while at least two others are within 5 squares" is a gated modifier**,
  not a hold put on and taken off: who stands where changes every time
  anybody moves, and the gate is read at the moment the defence is. "Another
  of these" is an `Ident` match (`_same_row`), because `c.is_kind` answers
  about type words that several different stat blocks share;
* **a move-and-swing row takes the swing first.** The move picks its own
  destination through the decider and one taken first can leave the target
  out of reach; the printed lines all allow the attack at any point in the
  movement.

Five rows are a companion's benefit to its master -- a Stealth penalty
waived, a Perception bonus for following tracks, a Thievery check made on
command -- and carry `out_of_combat=True`. One of the five does have a
combat meaning and is written properly: spotting creatures is a check a
fight really makes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.forms import _not_in, _shapechange
from combat_engine.content.monsters.level_06.brutes import DEFENCES, _same_row
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_OTHER,
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
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Dropped,
    Hit,
    Miss,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    adjacent,
    creatures,
    distance_between,
    team,
)
from combat_engine.engine.triggers import Trigger, both, by_melee, targets_me

#: The three reaches a printed "close or an area attack" covers.
_SPREAD = ("close_burst", "close_blast", "area_burst")


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _by_a_trap(c: Cast) -> Callable[[dict[str, Any]], bool]:
    """"+2 to all defences against traps", as the gate a defence is read
    through. The attacker is in the attack context and nowhere else, so the
    narrowing is a key rather than a watcher."""

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.is_trap(who)

    return gate


def _in_a_crowd(
    c: Cast, ref: str, radius: int, least: int
) -> Callable[[dict[str, Any]], bool]:
    """"While at least two others are within 5 squares", as a gate.

    The gate ignores the context entirely -- it is about the board, not about
    the attack -- and counts by `Ident`, because the type words these blocks
    print are shared with a dozen others.
    """
    me = c.me

    def gate(_ctx: dict[str, Any]) -> bool:
        return (
            sum(
                1
                for a in c.allies()
                if a != me
                and _same_row(c, a, ref)
                and distance_between(c.world, a, me) <= radius
            )
            >= least
        )

    return gate


def _by_spread(world: World, me: int, ev: Any) -> bool:
    """A close or an area attack, read off the reach of the row that made it.

    There is no ready-made predicate for it and the keywords on the event say
    nothing about shape, so the row itself is asked.
    """
    p = get(getattr(ev, "power", ""))
    return p is not None and p.reach_of(getattr(ev, "branch", 0)).kind in _SPREAD


# --------------------------------------------------------------------------
# m1058
# --------------------------------------------------------------------------


@power(
    "m1058a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=0),
    damage=Damage("", 2, kind=MINION),
    dropped=("c.contract(ref)",),
    requires=_not_in("humanoid"),
    requires_text="it must not be in humanoid form",
)
def m1058a0(c: Cast) -> None:
    """The printed bonus really is +0 and is written as printed; the engine
    takes the level term out of it like any other.

    The second clause hands the target a second ref to carry, which nothing
    can do.
    """
    if c.strike():
        c.hit()


@power(
    "m1058a1",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m1058a1(c: Cast) -> None:
    """It alters its physical form: beast, humanoid.

    **Which attacks each shape forbids is on the attack rows**, not here. The
    card states them as a loss ("it loses its bite attack in humanoid form"),
    which is a Requirement on the bite; putting it here as a `c.forbid` would
    have to be undone by hand every time the shape changed, and was not.

    `beast` leads the list because that is the shape the block describes it
    in, and one form replaces another -- which is what "until it uses this
    power again" means.
    """
    _shapechange(c, "beast", "humanoid")
@power(
    "m1058a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1058a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Both halves of the
    sentence are keys the damage context already carries, so neither needs a
    watcher of its own."""
    c.bonus(
        "damage",
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and not ctx.get("ranged"),
    )


# --------------------------------------------------------------------------
# m1568
# --------------------------------------------------------------------------


@power(
    "m1568a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 2, dtype=DamageType.POISON, kind=MINION),
)
def m1568a0(c: Cast) -> None:
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.damage(0, 3, dtype=DamageType.POISON)
    else:
        c.hit()


# --------------------------------------------------------------------------
# m1651
# --------------------------------------------------------------------------


@power(
    "m1651a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("", 4, kind=MINION),
)
def m1651a0(c: Cast) -> None:
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.damage(0, 5)
    else:
        c.hit()


@power(
    "m1651a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m1651a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m1658
# --------------------------------------------------------------------------


@power(
    "m1658a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("", 4, dtype=DamageType.COLD, kind=MINION),
)
def m1658a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1658a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("", 4, dtype=DamageType.COLD, kind=MINION),
)
def m1658a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m1922
# --------------------------------------------------------------------------


@power(
    "m1922a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1922a0(c: Cast) -> None:
    """Three of these round a creature slow it as its turn opens.

    Every one of them arms this, so the hold would go on three times over.
    The guard is "is it slowed already" rather than a shared label, because
    the three watchers belong to three different creatures and an effect's
    label is only unique within one of them.
    """

    def opens(ev: TurnStart) -> None:
        if ev.ghost or c.is_(Condition.SLOWED, on=ev.actor):
            return
        near = sum(
            1
            for other in creatures(c.world)
            if _same_row(c, other, "m1922") and adjacent(c.world, other, ev.actor)
        )
        if near >= 3:
            c.slowed(on=ev.actor, until=When.SOTNT)

    c.watch(TurnStart, opens, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m1922a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("", 4, kind=MINION),
)
def m1922a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1922a2",
    level=1,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m1922a2(c: Cast) -> None:
    c.shift(8)


# --------------------------------------------------------------------------
# m1956
# --------------------------------------------------------------------------


@power(
    "m1956a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("", 5, dtype=DamageType.NECROTIC, kind=MINION),
)
def m1956a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m2013
# --------------------------------------------------------------------------


@power(
    "m2013a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("", 4, dtype=DamageType.NECROTIC, kind=MINION),
)
def m2013a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power(
    "m2013a1",
    level=1,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2013a1(c: Cast) -> None:
    c.shift(6)


# --------------------------------------------------------------------------
# m3530
# --------------------------------------------------------------------------


@power(
    "m3530a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, kind=MINION),
)
def m3530a0(c: Cast) -> None:
    """The printed +11 is five points clear of every other block at this
    level. It is written as printed; see the report."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4232
# --------------------------------------------------------------------------


_M4232_CRIT = "this creature or an ally within 5 squares scores a critical hit"


def _crit_nearby(world: World, me: int, ev: Hit) -> bool:
    if not getattr(ev, "critical", False):
        return False
    if ev.attacker == me:
        return True
    if team(world, ev.attacker) is not team(world, me):
        return False
    return distance_between(world, me, ev.attacker) <= 5


@power(
    "m4232a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m4232a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4232a1",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M4232_CRIT,
    on=Trigger(Hit, when=_crit_nearby, text=_M4232_CRIT),
)
def m4232a1(c: Cast) -> None:
    """Declared with no target: the dispatcher would aim this at whoever was
    hit, and the printed line picks an adjacent enemy of its own -- which on
    an ally's critical is somebody else entirely."""
    foes = sorted(e for e in c.enemies() if c.adjacent(e))
    if not foes:
        return
    victim = c.choose(foes, "m4232a1: who it swings at")
    if victim is not None:
        c.basic(on=victim)


# --------------------------------------------------------------------------
# m4454
# --------------------------------------------------------------------------


@power(
    "m4454a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m4454a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4454a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4454a1(c: Cast) -> None:
    """Swing, then cover the ground without the target getting a swing in.

    The blow is the creature's own basic rather than a copy of m4454a0, so a
    stand-in filed for it is honoured. Taken before the move for the reason
    the tree's other move-and-swing rows give: the move picks its own
    destination and one taken first can leave the target out of reach.
    """
    c.no_provoke(from_=c.target)
    c.basic(on=c.target)
    c.move(6, at="fly")


# --------------------------------------------------------------------------
# m4494
# --------------------------------------------------------------------------


@power(
    "m4494a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m4494a0(c: Cast) -> None:
    """The printed crit is a flat 6 rather than a maximised roll, because a
    minion's damage is a number and there is nothing to maximise -- so
    `c.hit()` would deal 4 on a critical."""
    result = c.strike()
    if not result:
        return
    if result.critical:
        c.damage(0, 6)
    else:
        c.hit()


@power(
    "m4494a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 3, kind=MINION),
)
def m4494a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4494a2",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4494a2(c: Cast) -> None:
    c.shift(1)


@power(
    "m4494a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4494a3(c: Cast) -> None:
    for defence in DEFENCES:
        c.bonus(
            defence, 2, on=c.me, until=When.ENCOUNTER, when=_by_a_trap(c)
        )


# --------------------------------------------------------------------------
# m4614
# --------------------------------------------------------------------------


@power(
    "m4614a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 3, kind=MINION),
)
def m4614a0(c: Cast) -> None:
    if not c.strike():
        return
    if c.is_(Condition.PRONE):
        c.damage(0, 6)
    else:
        c.hit()


@power(
    "m4614a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4614a1(c: Cast) -> None:
    """Half its speed, rounded down, and never less than the one square a
    shift is. The swing goes first -- see the module note."""
    c.basic(on=c.target)
    c.shift(max(1, c.speed_of() // 2))


# --------------------------------------------------------------------------
# m4618
# --------------------------------------------------------------------------


_MISSED_ME = "this creature is missed by an attack"


@power(
    "m4618a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m4618a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4618a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m4618a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4618a2",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_MISSED_ME,
    on=Trigger(Miss, when=targets_me, text=_MISSED_ME),
)
def m4618a2(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4694
# --------------------------------------------------------------------------


@power(
    "m4694a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m4694a0(c: Cast) -> None:
    """The damage branch is read before the knock-down, so a target the row
    itself floors still takes the smaller number -- which is the printed
    order of the two clauses."""
    result = c.strike()
    if not result:
        return
    if c.is_(Condition.PRONE):
        c.damage(0, 6)
    else:
        c.hit()
    if result.advantage:
        c.prone()


# --------------------------------------------------------------------------
# m4742
# --------------------------------------------------------------------------


_MISSED_ME_MELEE = "this creature is missed by a melee attack"


@power(
    "m4742a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, dtype=DamageType.NECROTIC, kind=MINION),
)
def m4742a0(c: Cast) -> None:
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.damage(0, 5, dtype=DamageType.NECROTIC)
    else:
        c.hit()


@power(
    "m4742a1",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_MISSED_ME_MELEE,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_MISSED_ME_MELEE),
)
def m4742a1(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5304
# --------------------------------------------------------------------------


@power(
    "m5304a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5304a0(c: Cast) -> None:
    """Flanking counted rather than paired, so it is `c.gains_advantage` on
    the attacker: the set of surrounded creatures is not knowable when the
    trait arms. "Its allies" leaves the creature itself out."""
    me = c.me

    def surrounded(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return (
            sum(1 for a in c.allies() if a != me and adjacent(c.world, a, victim))
            >= 2
        )

    c.gains_advantage(surrounded, until=When.ENCOUNTER, on=me)


@power(
    "m5304a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5304a1(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


@power(
    "m5304a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m5304a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5430
# --------------------------------------------------------------------------


@power(
    "m5430a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m5430a0(c: Cast) -> None:
    result = c.strike()
    if not result:
        return
    if c.bloodied():
        c.damage(0, 5)
    else:
        c.hit()


@power(
    "m5430a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
)
def m5430a1(c: Cast) -> None:
    """The claw is m5430a0 rather than a copy of it, so its two damage
    numbers stay in one place. The shift follows the swing -- see the module
    note."""
    c.use_power("m5430a0", on=c.target, spend=False)
    c.shift(3)


# --------------------------------------------------------------------------
# m5443
# --------------------------------------------------------------------------


_M5443_SPLASH = "a close or an area attack hits or misses this creature"


@power(
    "m5443a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m5443a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5443a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
)
def m5443a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5443a2",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5443a2(c: Cast) -> None:
    c.shift(1)


@power(
    "m5443a3",
    level=1,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5443_SPLASH,
    on=Trigger(
        AttackDeclared, when=both(targets_me, _by_spread), text=_M5443_SPLASH
    ),
)
def m5443a3(c: Cast) -> None:
    """"Hits or misses" answered by an interrupt is the declaration, not the
    outcome: by `Hit` or `Miss` the window an interrupt lives in has closed,
    and stepping out of a blast afterwards would be too late to matter."""
    c.shift(3)


# --------------------------------------------------------------------------
# m5535
# --------------------------------------------------------------------------


@power(
    "m5535a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("", 4, kind=MINION),
)
def m5535a0(c: Cast) -> None:
    """The Effect line runs whether or not the attack lands, so the step is
    outside the hit branch and guarded by `c.first`."""
    if c.strike():
        c.hit()
        c.slide(2)
    if c.first:
        c.shift(1)


@power(
    "m5535a1",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=4),
    damage=Damage("", 10, kind=LIMITED),
)
def m5535a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded()


# --------------------------------------------------------------------------
# m5865
# --------------------------------------------------------------------------


@power(
    "m5865a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5865a0(c: Cast) -> None:
    """A held modifier rather than a watcher: the printed line covers shoves
    from anywhere, and `"forced"` is the one key all three kinds read."""
    c.resist_forced(3, on=c.me, until=When.ENCOUNTER)


@power(
    "m5865a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 3, dtype=DamageType.POISON, kind=MINION),
)
def m5865a1(c: Cast) -> None:
    """This one's step is printed *before* the attack, so it is taken there
    rather than after it: the target has already been chosen and the reach
    was measured when the row was declared.

    "Granting combat advantage to it" is read off the roll, which is wider
    than the printed sentence by the cases where the advantage came from
    somewhere else -- and is the only reading available, because the grant is
    spent by the time the body could ask.
    """
    if c.first:
        c.shift(2)
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.damage(0, 5, dtype=DamageType.POISON)
    else:
        c.hit()


# --------------------------------------------------------------------------
# m5897 -- m5901: five companions, and what a master gets for having one
# --------------------------------------------------------------------------


@power(
    "m5897a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5897a0(c: Cast) -> None:
    """The whole printed benefit is the -5 Stealth penalty for moving more
    than two squares, waived for the master. The engine levies no such
    penalty, so there is nothing to lift and nothing missing."""


@power(
    "m5898a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5898a0(c: Cast) -> None:
    """A Perception bonus for finding and following tracks. No fight rolls
    that check, so the whole row is inert rather than partly missing."""


@power(
    "m5899a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5899a0(c: Cast) -> None:
    """The one of these five with a combat meaning: spotting creatures is a
    Perception check a fight really makes, against anything hidden.

    The ten squares are a gate read as the check is rolled rather than a hold
    put on and taken off, because the pair move independently.
    """
    boss = c.master()
    if boss is None:
        return
    me = c.me
    c.bonus(
        "skill:perception",
        4,
        on=boss,
        until=When.ENCOUNTER,
        when=lambda _ctx: distance_between(c.world, me, boss) <= 10,
    )


@power(
    "m5900a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5900a0(c: Cast) -> None:
    """A Thievery check made on command, at the master's modifier plus two.
    Nothing on a board picks a pocket."""


@power(
    "m5901a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5901a0(c: Cast) -> None:
    """As m5900a0: a Thievery check made on command, and no fight rolls
    one."""


# --------------------------------------------------------------------------
# m6046
# --------------------------------------------------------------------------


@power(
    "m6046a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6046a0(c: Cast) -> None:
    """`opportunity` is a key the attack context already carries, so this is
    four gated modifiers and no watcher."""
    for defence in DEFENCES:
        c.bonus(
            defence,
            2,
            on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("opportunity")),
        )


# --------------------------------------------------------------------------
# m6210
# --------------------------------------------------------------------------


def _is_grabbed(world: World, eid: int) -> bool:
    """The printed "one creature grabbing it", as an entry requirement.

    There is no target word for it, and a row offered with no legal target
    looks usable and does nothing.
    """
    from combat_engine.engine.escape import holders

    return bool(holders(world, eid))


@power(
    "m6210a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 4, kind=MINION),
    requires=_is_grabbed,
    requires_text="must be held in a grab",
)
def m6210a0(c: Cast) -> None:
    """It can only hit whatever is holding it, so a target the engine aimed
    somewhere else is redirected to a holder rather than swung at."""
    holders = set(c.grabbed_by())
    victim = c.target if c.target in holders else next(iter(sorted(holders)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m6210a1",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_MISSED_ME,
    on=Trigger(Miss, when=targets_me, text=_MISSED_ME),
)
def m6210a1(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


# --------------------------------------------------------------------------
# m6565
# --------------------------------------------------------------------------


@power(
    "m6565a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 3, kind=MINION),
)
def m6565a0(c: Cast) -> None:
    """The crowd bonus is counted at the moment of the blow and added as a
    flat rider, so it meets resistance as part of the same untyped blow."""
    if not c.strike():
        return
    c.hit()
    extra = sum(1 for a in c.allies() if c.adjacent(a))
    if extra:
        c.flat(extra)


# --------------------------------------------------------------------------
# m6573
# --------------------------------------------------------------------------


_M6573_DOWN = "an enemy within 10 squares drops this creature to 0 hit points"


def _dropped_nearby(world: World, me: int, ev: Dropped) -> bool:
    if ev.actor != me or ev.source is None:
        return False
    if team(world, ev.source) is team(world, me):
        return False
    return distance_between(world, me, ev.source) <= 10


@power(
    "m6573a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("", 3, kind=MINION),
)
def m6573a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6573a1",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6573a1(c: Cast) -> None:
    """Rough ground is waived for the length of the step and taken back at
    the end of the turn, because the printed line is about this move and not
    about the creature."""
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(c.speed_of())


@power(
    "m6573a2",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6573_DOWN,
    on=Trigger(Dropped, when=_dropped_nearby, text=_M6573_DOWN),
)
def m6573a2(c: Cast) -> None:
    """A death throe, so it reads its killer off the event rather than off a
    target: `Dropped` carries the source and the dispatcher has nobody to aim
    this at.

    The printed duration outlasts the fight -- "until it takes an extended
    rest" -- and the encounter is the longest the engine holds, which inside
    one fight is the same thing.
    """
    foe = getattr(c.trigger, "source", None)
    if foe is None:
        return
    c.vulnerable(5, DamageType.NECROTIC, on=foe, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m860
# --------------------------------------------------------------------------


@power(
    "m860a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("", 2, kind=MINION),
)
def m860a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m860a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m860a1(c: Cast) -> None:
    """Braver in a crowd, counted by `Ident`. The printed sentence names a
    third ref for the crowd and this block is not it -- see the report -- so
    the count is of this block, which is the one the sentence is printed on.
    "Power bonus" is the word the card prints."""
    for defence in DEFENCES:
        c.bonus(
            defence,
            2,
            on=c.me,
            until=When.ENCOUNTER,
            kind="power",
            when=_in_a_crowd(c, "m860", 5, 2),
        )


# --------------------------------------------------------------------------
# m968
# --------------------------------------------------------------------------


@power(
    "m968a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage("", 2, kind=MINION),
)
def m968a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m971
# --------------------------------------------------------------------------


@power(
    "m971a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("", 2, kind=MINION),
)
def m971a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m971a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m971a1(c: Cast) -> None:
    """The same shape as m860a1, and this one's printed sentence does name
    its own block."""
    for defence in DEFENCES:
        c.bonus(
            defence,
            2,
            on=c.me,
            until=When.ENCOUNTER,
            kind="power",
            when=_in_a_crowd(c, "m971", 5, 2),
        )
