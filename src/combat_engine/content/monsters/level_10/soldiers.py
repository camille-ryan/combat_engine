"""Monster abilities, level 10: the soldiers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=16)` and `Damage("1d8", 6)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the nine levels below are kept: a row filed under an
action heading that is plainly a trait is declared `ActionType.NONE` and
armed once when the fight starts; a helper written for an earlier level is
imported rather than copied; and a stat block that prints no range at all
means melee 1.

Six things this file had to settle.

**Reach for an opportunity attack is a distance, not a ring.** `c.threatens`
is a modifier on "reach", so m4928a1's three squares widen the window rather
than open extra ones: a creature stepping out of the second square is still
threatened and provokes further out, not more often. That is the method the
vocabulary offers and the one the row is written against. It does not
currently reach the board -- see the engine-bug note in the report -- and
the row is left as it is rather than approximated, because the sentence is
sayable and the saying of it is what will be fixed.

**A trample ranks its own destinations now.** `c.overrun()` with no
destination sorts the reachable squares by how many enemies the line crosses
before offering them, so a bare call walks through people. m112a1 is written
as the bare call, and unlike level 9's trample it does **not** waive
opportunity attacks: the printed line says the movement provokes.

**Two bonuses of the same kind do not add -- the larger wins.** m153 prints
"+15, or +16 while bloodied" on two rows and a separate trait that is the
whole of the difference, so the trait is written once, on the row that
prints it, as a **racial** bonus. Baking the extra point into each attack
line as well would be a second bonus of one kind and come to the same +1
twice over; writing the trait as a gated bonus of the same kind as anything
else the creature carries would come to nothing at all.

**A death that is not one.** m1578a2 is answered on the creature's own
`Dropped`, the arrangement level 9 settled: `_check_down` re-reads hit
points after the emit, so one point put back inside that window really does
keep it up, and the acid-or-fire clause kills by this watch declining to
catch it.

**Swallowing.** m201a2 and m4964a3 both take a creature out of the fight.
`Condition.REMOVED` is on the board and out of it; `c.teleport(share=True)`
is what puts a body in an occupied square, which is what "teleports the
target to the square containing its tree" means; and the way back is hung on
the hold's own ending rather than on a clock, because "when the effect ends,
the target appears" is what the printed line measures.

**`Bloodied` about itself cannot fire on the audit board**, which sets the
caster to half hit points before the fight starts. m3014a1 is such a row and
reports UNUSED however correct it is; it was driven by hand, at full health,
to check. See the report.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_07.soldiers import _hands_free, _recharge_on
from combat_engine.content.monsters.level_08.brutes import (
    SMALL_ENOUGH,
    _has_hold,
    _holding,
    _is_bloodied,
    _melee_ctx,
    _struck_by,
)
from combat_engine.content.monsters.level_09.brutes import (
    CAUTERISING,
    _dealt,
    _put_beside,
    _volley,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Effect,
    Health,
    Hit,
    Initiative,
    Keyword,
    Melee,
    Position,
    Ranged,
    Relation,
    Size,
    Square,
    Stats,
    UpTo,
    Usage,
    When,
    World,
    distance,
    footprint,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.events import (
    ConditionApplied,
    DamageApplied,
    MoveEnd,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    flanked_by,
    squares,
)
from combat_engine.engine.triggers import Trigger, about_me

#: What every printed "friendly rider of 10th level or higher" on this level
#: asks of whoever is in the saddle. The feat the same sentence asks for has
#: no counterpart -- monsters carry no feats -- and is not tested.
MOUNTED_RIDER_LEVEL = 10

#: The conditions m192a1 shrugs off at the end of each of its turns. A charm
#: is read as domination: an effect carries conditions and no keywords, so
#: the only charm the engine has a name for is the one that takes the turn.
SHAKEN_OFF = (Condition.DAZED, Condition.STUNNED, Condition.DOMINATED)


def _qualified_rider(c: Cast) -> int | None:
    """Whoever is in the saddle, if the printed Requirement lets them ride.

    Asked at the moment rather than when the trait arms: riders mount and
    fall off mid-fight, and a modifier handed out at the start of the
    encounter would go to the wrong creature or to nobody.
    """
    rider = c.rider()
    if rider is None or rider not in c.allies():
        return None
    stats = c.world.get(rider, Stats)
    return rider if stats is not None and stats.level >= MOUNTED_RIDER_LEVEL else None


def _prone_on_opportunity(c: Cast) -> None:
    """Whatever this creature catches on its way past goes down.

    Read off the `Hit`, which carries `opportunity` the way it carries
    `charge`. Not a modifier: neither knocking a creature down nor holding
    it still is a number.
    """
    me, ref = c.me, c.ref

    def floor(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            c.prone(on=ev.target)

    c.watch(Hit, floor, until=When.ENCOUNTER, on=me, label=ref)


def _beside(c: Cast, who: int, anchor: int) -> list[Square]:
    """Free squares next to `anchor` that `who` actually fits in.

    The footprint measured is the creature being moved, not the caster: a
    Large body offered a square a Medium one fits in simply does not arrive,
    which is the trap `_put_beside` was written for a level below.
    """
    here = c.world.get(who, Position)
    size = here.size if here is not None else Size.MEDIUM
    return sorted(
        sq
        for sq in spread(squares(c.world, anchor), 1)
        if all(
            c.world.grid.passable(part) and c.world.grid.occupant(part) in (None, who)
            for part in footprint(sq, size)
        )
    )


def _drag_beside(c: Cast, who: int, anchor: int, squares_: int) -> bool:
    """Slide a creature up to `squares_` and set it down next to another.

    `c.slide` with no `to` offers every square in range to the decider,
    which is useless for a printed line that says where the slide has to
    end.
    """
    mine = squares(c.world, who)
    options = [
        sq
        for sq in _beside(c, who, anchor)
        if min(distance(s, sq) for s in mine) <= squares_
    ]
    if not options:
        return False
    where = c.world.decide(c.me, "slide", options, f"{c.ref}: where it lands")
    return bool(c.slide(squares_, on=who, to=where))


def _release(c: Cast, who: int) -> None:
    """End whatever hold this creature has on that one."""
    for eff in list(c.world.effects.of(who)):
        if any(
            kind is Relation.GRABBED_BY and source == c.me
            for kind, source, _target in eff.relations
        ):
            c.world.effects.end(eff, f"{c.ref} lets go")


# ==========================================================================
# m112
# ==========================================================================


@power(
    "m112a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 6),
)
def m112a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m112a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d8", 6),
)
def m112a1(c: Cast) -> None:
    """It runs over whoever is standing in the way.

    `c.overrun` is the only thing that reports who was trampled, and who was
    trampled is exactly what the printed line attacks. Called bare: with no
    destination it now ranks the reachable squares by how many enemies the
    line crosses, so the walk goes through people rather than to the lowest
    corner of the board.

    No `c.no_provoke` here, unlike the trample a level down: this printed
    line says the movement provokes opportunity attacks. Ending in an
    unoccupied space is the trample's own rule and `movement.overrun`
    already shuffles it clear.

    Declared with no target: the blows are aimed by the walk.
    """
    for victim in c.overrun():
        if victim not in c.enemies() or not alive(c.world, victim):
            continue
        if c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)


@power(
    "m112a2",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
    requires_text="the m112 must be carrying a friendly rider of 10th level or higher",
)
def m112a2(c: Cast) -> None:
    """Filed as an encounter attack and plainly a trait.

    Read off the rider's `Hit`, which carries `charge`. A damage modifier
    would not do: the printed line adds dice rather than a number, and the
    damage context carries no `charge` to gate on anyway.
    """
    me, ref = c.me, c.ref

    def spur(ev: Hit) -> None:
        if ev.attacker != _qualified_rider(c) or not getattr(ev, "charge", False):
            return
        c.damage("2d6", dtype=DamageType.RADIANT, on=ev.target, detail=ref)

    c.watch(Hit, spur, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m112a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m112a3(c: Cast) -> None:
    """Rough ground costs it nothing.

    The other half -- crossing any solid or liquid surface -- is about what
    a square is made of, and the grid records passable or not and nothing
    else, so there is no water to walk on. Noted rather than approximated as
    a flight speed, which is a different thing.
    """
    c.ignores_difficult()
    c.note("m112a3: it can also move across any solid or liquid surface")


# ==========================================================================
# m116
# ==========================================================================


@power(
    "m116a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m116a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m116a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m116a1(c: Cast) -> None:
    """Anything it catches walking past is held where it stands."""
    me, ref = c.me, c.ref

    def hold(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            c.immobilized(until=When.EONT, on=ev.target)

    c.watch(Hit, hold, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m116a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6),
)
def m116a2(c: Cast) -> None:
    """Two damage lines and the header holds one, so the bigger of them is
    rolled here. The question is asked of the victim before the blow lands,
    which is when the printed line asks it."""
    if not c.strike():
        return
    if c.is_(Condition.IMMOBILIZED):
        c.damage("4d6", 6)
    else:
        c.hit()


@power(
    "m116a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=13),
)
def m116a3(c: Cast) -> None:
    """Two swings of the row that prints them, and a secondary on whoever
    took both.

    The header carries the secondary line rather than the two it opens with:
    that is the one roll this row makes for itself. No damage beside it --
    being held is the whole of the hit.
    """
    victim = c.target
    if victim is None or not _volley(c, "m116a2", victim):
        return
    if alive(c.world, victim) and c.strike(on=victim):
        c.immobilized(until=When.EONT, on=victim)


# ==========================================================================
# m153
# ==========================================================================


def _a_bloodied_enemy_in_reach(world: World, eid: int) -> bool:
    from combat_engine.engine.query import enemies

    return any(
        _is_bloodied(world, foe) and distance_between(world, eid, foe) <= 1
        for foe in enemies(world, eid)
    )


@power(
    "m153a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m153a0(c: Cast) -> None:
    """The printed "+16 while bloodied" is m153a3 and is written there, once,
    rather than a second time in each attack line: two bonuses of one kind
    do not add, so the same point put on twice is the same point."""
    if c.strike():
        c.hit()


@power(
    "m153a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 5),
    requires=_a_bloodied_enemy_in_reach,
    requires_text="the target must be bloodied",
)
def m153a1(c: Cast) -> None:
    """"Target must be bloodied" is narrower than any `Target` can say, so
    the Requirement carries whether there is one at all and the body picks
    from the ones there are -- rather than letting `_auto_targets` choose
    whoever is nearest and miss the point of the row."""
    hurt = sorted(foe for foe in c.enemies() if c.bloodied(foe) and c.distance(foe) <= 1)
    victim = c.choose(hurt, "m153a1: which bloodied enemy") if hurt else None
    if victim is None:
        return
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    for friend in sorted(c.allies()):
        c.bonus("attack", 2, until=When.EONT, on=friend, kind="power")


@power(
    "m153a2",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m153a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m153a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m153a3(c: Cast) -> None:
    """The point that turns every printed +15 into a +16.

    A gated modifier rather than something put on when the creature is
    bloodied and taken off when it is healed: being bloodied is a fact about
    hit points that changes both ways, and the gate is asked as the roll is
    made. `kind="racial"`, as the card says, and because it has to sit
    beside m153a5's untyped +2 rather than contend with it.
    """
    me = c.me
    c.bonus(
        "attack", 1, until=When.ENCOUNTER, on=me, kind="racial",
        when=lambda _ctx: c.bloodied(me),
    )


@power(
    "m153a4",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m153a4(c: Cast) -> None:
    _prone_on_opportunity(c)


@power(
    "m153a5",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m153a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    How many enemies are next to it changes every time anybody moves, so
    this is asked as the roll is made. `_melee_ctx` reads the reach off the
    row rather than off the context, which carries `ranged` on the attack
    side and nothing at all on the damage side.
    """
    me = c.me

    def alone_with_one(ctx: dict[str, Any]) -> bool:
        return _melee_ctx(ctx) and len(c.within(1, of=me, side="enemy")) == 1

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=alone_with_one)


# ==========================================================================
# m1578
# ==========================================================================
#
# Two of this card's sentences spell the creature's id as a shorter one
# belonging to a different stat block. This creature is the one they plainly
# mean, and is the one written.


_M1578_BLED = "an attack by the m1578 bloodies an enemy"


def _my_blow_bled_them(world: World, me: int, ev: Bloodied) -> bool:
    """`Bloodied` names only who fell. Who felled it exists in one place,
    which is the log, and `_struck_by` reads the nearest earlier blow."""
    return ev.actor != me and _struck_by(world, ev, ev.actor) == me


@power(
    "m1578a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m1578a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1578a1",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
    trigger=_M1578_BLED,
    on=Trigger(Bloodied, when=_my_blow_bled_them, text=_M1578_BLED),
)
def m1578a1(c: Cast) -> None:
    """The swing is this row's own declared line rather than m1578a0 used
    again. `Bloodied` is emitted from inside the damage that caused it, so
    the row that bloodied the enemy is still in flight and `use` refuses to
    re-enter it -- which would make this fire and do nothing exactly when it
    is supposed to.
    """
    if c.strike():
        c.hit()


@power(
    "m1578a2",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1578a2(c: Cast) -> None:
    """Refusing to die, answered on its own `Dropped`.

    `_check_down` re-reads hit points after the emit, which is what makes a
    row that heals itself inside that window stay up -- so one point goes
    back, the body lies there unconscious until the start of its next turn,
    and it gets up with ten.

    An ordinary blow landing on the body drops it again and puts the point
    back without laying a second hold: it stays down and still gets up. Acid
    or fire is the clause that kills, and it kills by this watch declining
    to catch it, which is the only reading under which "it is destroyed" and
    "an ordinary attack does not stop it" are both true.
    """
    me = c.me
    down = f"{c.ref} down"

    def get_up() -> None:
        health = c.world.get(me, Health)
        if health is not None and alive(c.world, me) and health.hp < 10:
            c.heal(10 - health.hp, on=me)

    def falls(ev: Dropped) -> None:
        if ev.actor != me or _dealt(c.world, ev, me, CAUTERISING):
            return
        c.heal(1, on=me)
        if any(eff.label == down for eff in c.world.effects.of(me)):
            return
        c.prone(on=me)
        hold = c.world.effects.apply(
            me, me, When.SONT, label=down, conditions=(Condition.UNCONSCIOUS,)
        )
        hold.on_end.append(get_up)

    c.watch(Dropped, falls, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m192
# ==========================================================================


@power(
    "m192a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m192a0(c: Cast) -> None:
    """An elite acting twice a round: a second slot in the initiative order.

    The spliced slot sorts ten above its own, which is how the two are told
    apart and is the arrangement every double-initiative creature below uses.
    Both are full turns here, so unlike the solos there is nothing to spend
    out of the second turn's budget.

    The immediate-action half is noted rather than written: `Encounter`
    already allows one immediate action per round and one opportunity action
    per other creature's turn, and nothing can raise either ceiling.
    """
    init = c.world.get(c.me, Initiative)
    if init is not None:
        c.extra_turn(init.rolled + 10)
    c.note("m192a0: it may take two immediate actions a round, one between turns")


@power(
    "m192a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m192a1(c: Cast) -> None:
    """It shrugs off whatever is holding it as each of its turns closes.

    "Charm" is read as domination: an effect carries conditions and no
    keywords, so the only charm the engine has a name for is the one that
    takes the turn away.
    """
    me = c.me

    def shrug(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if any(cond in SHAKEN_OFF for cond in eff.conditions):
                c.world.effects.end(eff, c.ref)

    c.watch(TurnEnd, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m192a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d12", 12),
)
def m192a2(c: Cast) -> None:
    """The mark is an Effect line, so it lands whether or not the blow did."""
    if c.strike():
        c.hit()
        c.push(1)
    c.mark(until=When.EONT)


_M192_FLANKED = "an enemy enters a square from which it flanks the m192"


def _moved_into_flank(world: World, me: int, ev: MoveEnd) -> bool:
    """`MoveEnd`, not `MoveStart`: the question is about the square the
    creature has arrived in, and `MoveStart` fires before the first step."""
    return ev.actor != me and flanked_by(world, me, ev.actor)


@power(
    "m192a3",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    trigger=_M192_FLANKED,
    on=Trigger(MoveEnd, when=_moved_into_flank, text=_M192_FLANKED),
)
def m192a3(c: Cast) -> None:
    """No damage line at all: the shove is the whole of the hit."""
    if c.strike():
        c.push(3)


# ==========================================================================
# m201
# ==========================================================================
#
# Two of this card's sentences spell this creature's id as one belonging to
# other stat blocks. This creature is the one they plainly mean.


_M201_INSIDE = "m201a2 swallowed"


def _swallowable(world: World, eid: int) -> bool:
    for who in _holding(world, eid):
        pos = world.get(who, Position)
        if _is_bloodied(world, who) and pos is not None and pos.size in SMALL_ENOUGH:
            return True
    return False


@power(
    "m201a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6),
    requires=_hands_free,
    requires_text="the m201 must not already be grabbing a creature",
)
def m201a0(c: Cast) -> None:
    """"It cannot make these attacks while grabbing" is a printed
    Requirement, which is a fact about the caster and so belongs in the
    header rather than as a guard in the body."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m201a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 6, half_on_miss=True),
    requires=_has_hold,
    requires_text="the m201 must be grabbing a creature",
)
def m201a1(c: Cast) -> None:
    """"The creature grabbed in its jaws" is narrower than any target line
    the header can say, so the Requirement carries the half of it that is
    about the caster and the body picks from what it actually has hold of."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m201a1: which of them it worries") if held else None
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
    else:
        c.hit(on=victim, half=True)


@power(
    "m201a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=15),
    requires=_swallowable,
    requires_text="the m201 must be grabbing a bloodied Medium or smaller creature",
)
def m201a2(c: Cast) -> None:
    """It swallows what it is holding.

    "Dazed and restrained (no save)" is one hold on the encounter clock
    carrying both conditions -- applied separately the victim would get two
    saving throws against a thing the card says it does not get one against
    at all. The ten a round is hung on the hold rather than written as
    `ongoing`, which is paid at the victim's turn and save-ends by nature;
    the printed line pays at the m201's.

    The way out is the m201 dying, so it hangs on `Dropped` and sets the
    creature down in a square the body used to fill.

    Not written: the swallowed creature may make only basic attacks.
    `c.forbid` takes one row away and `c.no_basic` takes away what a row is
    *used as*; neither can say "everything except". See the report.
    """
    me = c.me
    edible = sorted(
        who
        for who in _holding(c.world, me)
        if c.bloodied(who) and c.size_of(who) in SMALL_ENOUGH
    )
    victim = c.choose(edible, "m201a2: which of them it swallows") if edible else None
    if victim is None or not c.strike(on=victim):
        return
    inside = c.world.effects.apply(
        victim, me, When.ENCOUNTER, label=_M201_INSIDE,
        conditions=(Condition.DAZED, Condition.RESTRAINED),
    )

    def digest(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or inside.ended:
            return
        c.flat(10, on=victim)

    def spill(ev: Dropped) -> None:
        if ev.actor == me and not inside.ended:
            c.world.effects.end(inside, "the gullet is opened")

    inside.subs.append(c.world.bus.on(TurnStart, digest, owner=me))
    inside.subs.append(c.world.bus.on(Dropped, spill, owner=me))
    inside.on_end.append(lambda: _put_beside(c, victim, me))
    c.note("m201a2: the swallowed creature can make only basic attacks")


# ==========================================================================
# m2962
# ==========================================================================


@power(
    "m2962a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d12", 5),
)
def m2962a0(c: Cast) -> None:
    """A high-crit line and a mark with teeth.

    The extra die is `c.flat(c.roll(...))` rather than `c.damage`: a
    critical maxes every die `c.damage` rolls, so the printed "1d12 + 17"
    written the obvious way would come out at 12 + 17 instead of a roll on
    top of the maximum.

    The penalty is a gated modifier held for the fight rather than a second
    save-ends effect, which would give the victim two saving throws against
    one printed sentence. The gate asks whether the mark is still there,
    which is what ties the two together.
    """
    me, victim = c.me, c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("1d12"))
    c.mark(until=When.SAVE_ENDS)

    def against_its_friends(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and who != me and c.marked(on=victim) and who in c.allies()

    c.penalty(
        "damage", 5, on=victim, until=When.ENCOUNTER, when=against_its_friends
    )


@power(
    "m2962a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d6", 5),
)
def m2962a1(c: Cast) -> None:
    """The square is read before the shove, because after it there is
    nothing left to read: the printed line follows the body into the space
    it was standing in, and `c.shift` with no `to` would offer the decider
    every square in range instead."""
    victim = c.target
    pos = c.world.get(victim, Position) if victim is not None else None
    was = pos.square if pos is not None else None
    if not c.strike():
        return
    c.hit()
    if c.push(1) and was is not None:
        c.shift(to=was)


@power(
    "m2962a2",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=12),
)
def m2962a2(c: Cast) -> None:
    """No damage line: going down is the whole of the hit."""
    if c.strike():
        c.prone()


@power(
    "m2962a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2962a3(c: Cast) -> None:
    """One square less of every shove, and it does not fall over.

    The refusal is written the way level 8 wrote the swarm's: `Effects.apply`
    installs everything before it announces, so ending the hold from inside
    `ConditionApplied` is safe and leaves nothing half-applied behind.
    """
    me = c.me
    c.resist_forced(1)

    def stay_up(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        for eff in list(c.world.effects.of(me)):
            if Condition.PRONE in eff.conditions:
                c.world.effects.end(eff, c.ref)

    c.watch(ConditionApplied, stay_up, until=When.ENCOUNTER, on=me, label=f"{c.ref} up")


# ==========================================================================
# m3014
# ==========================================================================


_M3014_BLED = "the m3014 is first bloodied"


@power(
    "m3014a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m3014a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m3014a1",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    trigger=_M3014_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M3014_BLED),
)
def m3014a1(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else.

    The choice is each ally's own, so it is asked of that ally rather than
    of the m3014 -- `c.may` defaults to `c.target`, which here *is* the
    ally. A swing with nobody in reach is not a choice at all, so the step
    is what happens when there is no one to hit.
    """
    mate = c.target
    if mate is None or mate == c.me:
        return
    reachable = sorted(
        foe for foe in c.enemies() if distance_between(c.world, mate, foe) <= 1
    )
    if reachable and c.may("swing rather than step"):
        c.grant_attack(mate, on=reachable[0])
    else:
        c.shift(3, who=mate)


@power(
    "m3014a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
)
def m3014a2(c: Cast) -> None:
    """"Each enemy adjacent to it" is read from the target's side of the
    board, so the creatures given the opening are the m3014's own -- itself
    included, which is what standing next to the thing it just called out
    means.

    `c.provoke` opens a real window rather than making the attacks itself:
    the engine already has the window and whoever plays the monsters answers
    it, which is what makes "may" a may.
    """
    victim = c.target
    if victim is None:
        return
    for friend in sorted([c.me, *c.allies()]):
        if distance_between(c.world, friend, victim) <= 1 and friend != victim:
            c.provoke(friend, on=victim, why=c.ref)


@power(
    "m3014a3",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3014a3(c: Cast) -> None:
    c.mode("climb", 7, until=When.EONT, on=c.me)


@power(
    "m3014a4",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3014a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Who it is flanking changes every time anybody moves, so the point is a
    gated modifier asked as the roll is made. The dice are not: a modifier
    is one number, so the extra 2d6 is rolled off the `Hit`.
    """
    me, ref = c.me, c.ref

    def flanking(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and flanked_by(c.world, victim, me)

    def pile_on(ev: Hit) -> None:
        if ev.attacker == me and flanked_by(c.world, ev.target, me):
            c.damage("2d6", on=ev.target, detail=ref)

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=flanking)
    c.watch(Hit, pile_on, until=When.ENCOUNTER, on=me, label=ref)


# ==========================================================================
# m351
# ==========================================================================


_M351_FELLED = "the m351 is reduced to 0 hit points"


@power(
    "m351a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 6),
)
def m351a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m351a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 6),
)
def m351a1(c: Cast) -> None:
    """A charge whose blow is this row's own line.

    `c.charge_at` reaches the swing through `use`, and `use` refuses to
    re-enter a row already in flight -- which a row that *is* the charge
    always is. So the flag goes up by hand, `c.run_at` walks, and the header
    rolls. The flag is not decoration: it is what puts `charge` on the
    attack events and in the modifier contexts every charge rider reads, and
    it comes back down afterwards so nothing else this turn is paid twice.
    """
    victim = c.target
    if victim is None:
        return
    c.charge = True
    try:
        c.run_at(victim)
        if c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)
    finally:
        c.charge = False


@power(
    "m351a2",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M351_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M351_FELLED),
)
def m351a2(c: Cast) -> None:
    """One last swing as it goes down.

    A creature may answer its own downfall -- the dispatcher makes the
    exception for exactly this shape -- and `c.basic` swings whatever this
    creature's basic attack actually is rather than the engine's generic
    one. Declared with no target because the row picks from whoever is still
    in reach, and by this point that may be nobody.
    """
    near = sorted(
        (foe for foe in c.enemies() if c.adjacent(foe)),
        key=lambda foe: (c.distance(foe), foe),
    )
    if near:
        c.basic(on=near[0])


# ==========================================================================
# m4928
# ==========================================================================


#: How many creatures the printed line lets it hold at once, and the label
#: of the single sustain that pays for all of them.
_M4928_ARMS = 8
_M4928_SUSTAIN = "m4928a2 sustain"


@power(
    "m4928a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4928a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m4928a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4928a1(c: Cast) -> None:
    """Three squares of threat rather than one.

    `c.threatens` raises the reach the opportunity window is measured
    against, which is the direction the rule runs here: a creature that
    walks out of the second square is still threatened and provokes further
    out. It is a wider opening, not more of them.
    """
    c.threatens(3)


@power(
    "m4928a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 5),
)
def m4928a2(c: Cast) -> None:
    """A grab, and one sustain that pays for all of them.

    The printed Sustain Minor keeps every grab going at once, so it is a
    single hold on the m4928 rather than one per victim -- eight sustains
    for eight tentacles would be eight minor actions. The grabs themselves
    hang on the encounter and need no keeping alive; the five damage is the
    payout half, which is what `c.on_sustain` is for and what used to be
    dropped from every line of this shape.
    """
    me = c.me
    if not c.strike():
        return
    c.hit()
    if len(_holding(c.world, me)) < _M4928_ARMS:
        c.grab()
    if any(eff.label == _M4928_SUSTAIN for eff in c.world.effects.of(me)):
        return

    def squeeze() -> None:
        for who in sorted(_holding(c.world, me)):
            c.flat(5, on=who)

    holder = c.world.effects.apply(
        me, me, When.SUSTAIN, label=_M4928_SUSTAIN, sustain_cost=MINOR
    )
    c.on_sustain(holder, squeeze)


@power(
    "m4928a5",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m4928a5(c: Cast) -> None:
    """Churned water that stays where it was made.

    Not `c.burns`, which bites on entering as well and pays nothing but
    damage: the printed toll is start-of-turn only and slides the creature
    as well, so the watch is written out.

    The m4928 is left out of its own churn. "Any creature" read literally
    includes the thing standing in the middle of it, which would have it
    paying itself five a round for the whole fight.

    Not written: moving the zone up to 3 squares once a round as a minor
    action. The card gives that no id of its own and nothing on `Cast`
    relocates a zone. See the report.
    """
    me = c.me
    zid = c.zone(c.area(), until=When.ENCOUNTER, difficult=True)

    def churn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor not in c.world.zones.occupants(zid):
            return
        c.flat(5, on=ev.actor)
        c.slide(2, on=ev.actor)

    c.watch(TurnStart, churn, until=When.ENCOUNTER, on=me, label=c.ref)
    c.note("m4928a5: once a round, a minor action moves the churn up to 3 squares")


@power(
    "m4928a6",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d8", 5),
    requires=_has_hold,
    requires_text="the m4928 must be grabbing a creature",
)
def m4928a6(c: Cast) -> None:
    """"One creature grabbed by the m4928" is narrower than any `Target`, so
    the Requirement carries the caster's half and the body picks."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m4928a6: which of them it batters") if held else None
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.slide(3, on=victim)


@power(
    "m4928a7",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(6),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d8", 5),
    requires=_has_hold,
    requires_text="the m4928 must be grabbing a creature",
)
def m4928a7(c: Cast) -> None:
    """It swings what it is holding at somebody else.

    The slide names its destination, because the printed line does: the body
    has to land next to the second creature or there is no attack on both of
    them. The grab is ended by ending the hold that carries the relation
    rather than by clearing the relation directly, so whatever else hangs off
    that hold comes off with it.
    """
    me = c.me
    held = sorted(_holding(c.world, me))
    victim = c.choose(held, "m4928a7: which of them it swings") if held else None
    if victim is None:
        return
    others = sorted(
        foe for foe in c.enemies() if foe != victim and c.distance(foe) <= 6
    )
    anchor = c.choose(others, "m4928a7: who it swings them into") if others else None
    if anchor is None:
        return
    _drag_beside(c, victim, anchor, 5)
    _release(c, victim)
    for who in (victim, anchor):
        if alive(c.world, who) and c.strike(on=who):
            c.hit(on=who)
            c.prone(on=who)


@power(
    "m4928a8",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 4, dtype=DamageType.POISON),
    once_per_round=True,
)
def m4928a8(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


_M4928_BITTEN = "a creature grabbed by the m4928 damages it"


def _prisoner_struck_me(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.source in _holding(world, me)


@power(
    "m4928a9",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4928_BITTEN,
    on=Trigger(DamageApplied, when=_prisoner_struck_me, text=_M4928_BITTEN),
)
def m4928a9(c: Cast) -> None:
    """Every prisoner pays for one of them fighting back."""
    for who in sorted(_holding(c.world, c.me)):
        c.flat(5, on=who)


# ==========================================================================
# m4964
# ==========================================================================


#: The label the tree is conjured under, and what the other four rows find
#: it by. A conjuration rather than a zone: the printed line gives it a
#: square of its own that a creature has to be teleported into.
_M4964_TREE = "m4964a1"


def _tree_of(world: World, me: int) -> int | None:
    for eid, conj in world.each(Conjuration):
        if conj.by == me and conj.ref == _M4964_TREE:
            return eid
    return None


def _near_its_tree(world: World, eid: int) -> bool:
    tree = _tree_of(world, eid)
    return tree is not None and distance_between(world, eid, tree) <= 6


@power(
    "m4964a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m4964a0(c: Cast) -> None:
    """"At least 1 hit point" is `hp > 0` rather than `alive`: the printed
    sentence is about not knitting itself back together once it is down."""
    me = c.me

    def knit(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        health = c.world.get(me, Health)
        tree = _tree_of(c.world, me)
        if health is None or health.hp <= 0 or tree is None:
            return
        if c.adjacent_to(tree, me) or distance_between(c.world, me, tree) == 0:
            c.heal(5, on=me)

    c.watch(TurnStart, knit, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4964a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4964a1(c: Cast) -> None:
    """The tree the other four rows are about.

    A conjuration rather than a zone, because the printed line gives it a
    square it occupies -- which is what m4964a3 teleports a creature *into*
    and what m4964a5 teleports beside. It lasts the fight and costs nothing
    to keep, so no sustain.

    Not written: the m4964 having superior cover while inside it, and the
    tree counting as an ally for flanking. Cover is computed from two
    positions at the moment of the attack and nothing grants it; flanking
    counts creatures, and a conjuration deliberately is not one. See the
    report.
    """
    if _tree_of(c.world, c.me) is None:
        c.conjure(label=_M4964_TREE, until=When.ENCOUNTER, sustain=None)
    c.note("m4964a1: it has superior cover in the tree and flanks with it")


@power(
    "m4964a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 5),
)
def m4964a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4964a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=13),
    requires=_near_its_tree,
    requires_text="the m4964 must have a tree",
)
def m4964a3(c: Cast) -> None:
    """It feeds somebody to the tree and steps back to it.

    `share=True` is what puts a body in an occupied square, and the tree
    occupies its own -- so the printed "teleports the target to the square
    containing the tree" is one call rather than a shove at the nearest
    empty space beside it. The creature is off the board a moment later
    anyway, and where it comes back is chosen when it comes back rather than
    now.

    The Effect line -- the m4964's own step -- happens whether or not the
    attack landed, so it is outside the branch.

    "Recharge when no enemy is within its tree" is a board state rather than
    a die. The header's 6 stays, because that is what the card shows and
    what `actions.recharge` rolls; this is the printed sentence on top of
    it, and the two only ever agree to give the row back sooner.
    """
    me = c.me
    tree = _tree_of(c.world, me)
    if tree is None:
        return
    _recharge_on(
        c,
        TurnStart,
        lambda _ev: not [
            foe
            for foe in c.enemies()
            if squares(c.world, foe) & squares(c.world, tree)
        ],
    )
    victim = c.target
    if victim is not None and c.strike(on=victim):
        where = next(iter(sorted(squares(c.world, tree))), None)
        if where is not None:
            c.teleport(6, who=victim, to=where, share=True)
        gone = c.condition(Condition.REMOVED, until=When.SAVE_ENDS, on=victim)
        if gone is not None:
            gone.on_end.append(lambda: _put_beside(c, victim, tree))
    beside = _beside(c, me, tree)
    if beside:
        c.teleport(8, to=c.world.decide(me, "teleport", beside, f"{c.ref}: back to it"))


@power(
    "m4964a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 9, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4964a4(c: Cast) -> None:
    """Walk away from it and it hurts.

    "Closer than when it began its turn" is a measurement at two moments, so
    the distance is taken at the victim's `TurnStart` and compared at its
    `TurnEnd`. Nothing else can answer it: no event carries where a creature
    started.

    The Effect line lands whether or not the blow did, and it is the whole
    of the row's reach into the rest of the fight, so both watches and the
    mark come off together when the m4964 goes down.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
    started: dict[int, int] = {}
    held: list[Effect] = []

    def mark_the_range(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == victim:
            started[victim] = distance_between(c.world, me, victim)

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        now = distance_between(c.world, me, victim)
        if now <= 1 or now < started.get(victim, now):
            return
        c.flat(5, on=victim)

    def let_go(ev: Dropped) -> None:
        if ev.actor != me:
            return
        for eff in held:
            if not eff.ended:
                c.world.effects.end(eff, "the m4964 is down")

    held += [
        eff
        for eff in (
            c.mark(until=When.ENCOUNTER, on=victim),
            c.watch(TurnStart, mark_the_range, until=When.ENCOUNTER, on=me, label=c.ref),
            c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll"),
        )
        if eff is not None
    ]
    c.watch(Dropped, let_go, until=When.ENCOUNTER, on=me, label=f"{c.ref} ends")


@power(
    "m4964a5",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    requires=_near_its_tree,
    requires_text="the m4964 must be within 6 squares of its tree",
)
def m4964a5(c: Cast) -> None:
    me = c.me
    tree = _tree_of(c.world, me)
    if tree is None:
        return
    beside = _beside(c, me, tree)
    if beside:
        where = c.world.decide(me, "teleport", beside, f"{c.ref}: back to its tree")
        c.teleport(6, to=where)
