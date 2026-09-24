"""Monster abilities, level 3: the ones that move, and the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=8)` and `Damage("1d8", 5)` -- and the engine takes the level back out
of the attack and rescales the damage if a fight is being played on another
edition's maths.

The conventions level 1 and level 2 settled on are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; several rows the database files as standard actions
are plainly traits and are written as such; a printed range of "5/10" takes
the **normal** range, so the creature shoots inside the band where it has no
penalty; and combat advantage is read off the roll rather than asked of the
board afterwards, because `resolve.attack` clears `HIDDEN_FROM` the moment
the attack is over.

The helpers that hold a lurker unseen were written for level 2 and are
imported rather than copied -- five of the fifteen creatures here are the
same shape as the two there.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_02.skirmishers import (
    _advantage_rider,
    _hides_with_cover,
    _still_hidden_on_a_miss,
    _unseen,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Effect,
    Event,
    Health,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    Size,
    Square,
    Usage,
    When,
    World,
    get,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    Moved,
    PowerUsed,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    adjacent,
    cover_between,
    distance_between,
    enemies,
    flanked_by,
    squares,
)
from combat_engine.engine.triggers import Trigger, by_me

#: What "Medium or smaller" is, spelled out: `Size` is a name rather than a
#: number, so the categories cannot be compared with `<=`.
_SMALL_ENOUGH = (Size.TINY, Size.SMALL, Size.MEDIUM)


def _free_square_beside(c: Cast, who: int) -> Square | None:
    """An empty square next to that creature, for a row that names one.

    "Pulls the target to a square adjacent to its new location" and "shifts
    to a square adjacent to the target" both name a destination rather than a
    distance, which is what `to=` on the movement ops is for -- but neither
    op will pick the square, and an occupied one is simply refused.
    """
    taken = squares(c.world, who)
    for sq in sorted(spread(taken, 1) - taken):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _recharge_on(c: Cast, event: type[Event], test: Callable[[Any], bool]) -> None:
    """Put this row back up when its printed line says so, not only on a die.

    Four stat blocks here print "Recharge when ..." where the database files
    a plain 6+. The number stays in the header, because that is what
    `actions.recharge` rolls and what the card shows; this is the printed
    sentence on top of it, and the two only ever agree to make the row
    available sooner. Armed from the body, which is all that is needed: the
    row has to have been spent before there is anything to give back.
    """
    ref, me = c.ref, c.me
    label = f"{ref} recharge"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def back(ev: Event) -> None:
        known = c.world.get(me, Powers)
        if known is not None and test(ev):
            known.restore(ref)

    c.watch(event, back, until=When.ENCOUNTER, on=me, label=label)


def _reshape(c: Cast, *, drops: str = "") -> Effect:
    """Take a new shape, ending whichever one the creature was already in.

    `c.form` does not displace a previous form the way `c.stance` displaces a
    stance, and both printed lines here read "until it uses this again", so
    the old shape is ended by hand. `drops` names an attack the new shape
    cannot make; it is handed back when the shape ends.
    """
    for effect in list(c.world.effects.of(c.me)):
        if effect.label == c.ref:
            c.world.effects.end(effect, "took another shape")
    shape = c.form(until=When.ENCOUNTER, revert=MINOR, label=c.ref)
    known = c.world.get(c.me, Powers)
    if drops and known is not None and drops in known.known:
        known.known.remove(drops)
        shape.on_end.append(lambda: known.known.append(drops))
    return shape


def _poisoned(c: Cast, who: int | None) -> bool:
    """Is that creature taking ongoing poison damage, from anybody?

    Asked of the effect table rather than of anything an attack carries: the
    printed clause is about the target's condition and says nothing about
    where the poison came from.
    """
    return who is not None and any(
        eff.ongoing is not None and eff.ongoing[1] is DamageType.POISON
        for eff in c.world.effects.of(who)
    )


def _an_enemy_is_poisoned(world: World, eid: int) -> bool:
    return any(
        eff.ongoing is not None and eff.ongoing[1] is DamageType.POISON
        for foe in enemies(world, eid)
        for eff in world.effects.of(foe)
    )


def _grabbing(world: World, eid: int) -> bool:
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def _not_grabbing(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _vanish_until_it_swings(c: Cast, until: When) -> None:
    """Unseen until it attacks, or until the clock runs out.

    Attacking gives it away whether or not the attack lands, so the watch is
    on the roll rather than on the hit, and it is torn down with the veil so
    a second vanishing does not inherit the first one's listener.
    """
    veil = c.invisible(until=until)
    if veil is None:
        return
    me = c.me

    def reveal(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    seen = c.watch(AttackRolled, reveal, until=until, on=me, label=c.ref)
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))


def _creature_within(radius: int) -> Callable[[World, int, Event], bool]:
    """Anybody at all within range of me, either side.

    Neither `ally_within` nor `enemy_within` will say it: each rules out half
    the board, and the printed line reads "a living creature".
    """

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "actor", None)
        return (
            who is not None
            and who != me
            and distance_between(world, me, who) <= radius
        )

    return check


# --------------------------------------------------------------------------
# m150
# --------------------------------------------------------------------------


@power(
    "m150a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 6),
)
def m150a0(c: Cast) -> None:
    """"or 2d6 + 6 with combat advantage" is a second expression rather than a
    rider on the first, so it is rolled in the body and the header keeps the
    printed line that rescales. The advantage is read off the roll that was
    just made -- asking the board afterwards answers "no" for a creature that
    struck from concealment, which is exactly this one."""
    if not c.strike():
        return
    if c.result is not None and c.result.advantage:
        c.damage("2d6", 6)
    else:
        c.hit()


@power(
    "m150a1",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m150a1(c: Cast) -> None:
    """A disguise, which the engine has three things to say about: it is a
    shape, using it again ends the one it was in, and stepping out costs the
    same minor action. The DC 30 Insight check that sees through it is a
    skill check and there are none here, and there is no `polymorph` keyword
    to carry.
    """
    shape = _reshape(c)
    me = c.me

    def fell(ev: Dropped) -> None:
        if ev.actor == me:
            c.world.effects.end(shape, "it dropped")

    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label="m150a1 ends")


@power(
    "m150a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
)
def m150a2(c: Cast) -> None:
    """No damage at all: the opening it makes is the whole of the hit line."""
    if c.strike():
        c.grants_advantage(until=When.EONT)


# --------------------------------------------------------------------------
# m2795
# --------------------------------------------------------------------------


@power(
    "m2795a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2795a0(c: Cast) -> None:
    """It keeps hold of what it is carrying while it walks.

    There is no speed cost for grabbing in the engine -- `Condition.GRABBED`
    stops the *victim* moving and asks nothing of the grabber -- so the
    printed exemption has no penalty to lift. What the sentence plainly means
    is that the creature moves and its prisoner comes with it, and that is
    what is written: any step that would leave anything Medium or smaller it
    has hold of behind drags that creature along instead.

    The square it has just left is the wrong destination for a Large body --
    it is still standing in part of it -- so the prisoner is put in a free
    square beside wherever the step ended.
    """
    me = c.me

    def drag(ev: Moved) -> None:
        if ev.actor != me:
            return
        for held in c.world.relations.targets(Relation.GRABBED_BY, me):
            if c.size_of(on=held) not in _SMALL_ENOUGH:
                continue
            if adjacent(c.world, me, held):
                continue
            landing = _free_square_beside(c, me)
            if landing is not None:
                c.pull(1, on=held, to=landing)

    c.watch(Moved, drag, until=When.ENCOUNTER, on=me, label="m2795a0")


@power(
    "m2795a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m2795a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2795a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
    requires=_not_grabbing,
    requires_text="must not already have hold of a creature",
)
def m2795a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m2795a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 5, dtype=DamageType.ACID, kind=LIMITED),
)
def m2795a3(c: Cast) -> None:
    """"Save ends both" is one effect with one saving throw, so the slow and
    the acid are applied together rather than as two holds that would each be
    shaken off separately. The recharge is armed once for the whole blast."""
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.ACID)
        )


@power(
    "m2795a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
    requires=_grabbing,
    requires_text="must have hold of a creature",
)
def m2795a4(c: Cast) -> None:
    """Only into what it is already holding, and then it carries it off.

    `requires` carries the half about the creature -- that it has hold of
    somebody -- and the body checks that *this* target is the one held, which
    the header's `target` field cannot say. The pull names its square rather
    than a distance, which is the whole of "to a square adjacent to its new
    location".
    """
    victim = c.target
    if victim is None or not c.world.relations.holds(Relation.GRABBED_BY, c.me, victim):
        return
    if not c.strike():
        return
    c.hit()
    c.ongoing(5, DamageType.ACID)
    c.shift(2)
    landing = _free_square_beside(c, c.me)
    if landing is not None:
        # The printed line names a square rather than a distance, so one step
        # to it is the whole of the pull.
        c.pull(1, on=victim, to=landing)


# --------------------------------------------------------------------------
# m2927
# --------------------------------------------------------------------------


@power(
    "m2927a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2927a0(c: Cast) -> None:
    """Pinned down, it is easier to hit in every way.

    A gate rather than four penalties applied and taken back as the two
    conditions come and go: the modifier is asked whether it applies every
    time a defence is read, so there is no second place that has to remember
    to undo it.
    """
    me = c.me

    def pinned(_: dict) -> bool:
        return c.is_(Condition.SLOWED, on=me) or c.is_(Condition.IMMOBILIZED, on=me)

    for d in (AC, FORT, REF, WILL):
        c.penalty(d, 2, until=When.ENCOUNTER, on=me, when=pinned)


@power(
    "m2927a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("2d6", 4),
)
def m2927a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m2927a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("3d6", 3, kind=LIMITED, half_on_miss=True),
)
def m2927a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m2927a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=6),
)
def m2927a3(c: Cast) -> None:
    """Five one-square shifts rather than one jump of five.

    `c.shift(5)` picks a destination and steps to it once, so the board only
    ever sees the creature arrive -- and this line pays out *during* the
    move, the first time it comes alongside each enemy. Stepping a square at
    a time is what makes `AdjacencyGained` fire per square, which is the only
    thing that can answer "for the first time during the move".
    """
    me = c.me
    struck: set[int] = set()

    def alongside(ev: AdjacencyGained) -> None:
        foe = ev.other
        if ev.actor != me or foe in struck or foe not in c.enemies():
            return
        struck.add(foe)
        if c.strike(on=foe):
            c.prone(on=foe)

    watching = c.watch(
        AdjacencyGained, alongside, until=When.ENCOUNTER, on=me, label="m2927a3"
    )
    try:
        for _ in range(5):
            if not c.shift(1):
                break
    finally:
        c.world.effects.end(watching, "the move is over")


# --------------------------------------------------------------------------
# m3020
# --------------------------------------------------------------------------


@power(
    "m3020a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 6),
)
def m3020a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3020a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 6),
)
def m3020a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3020a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3020a2(c: Cast) -> None:
    """The attack is taken before the shift, for the reason level 1 gives on
    its own three of these: the shift picks its own destination and one taken
    first can leave the target out of reach. The printed line allows either
    order. The blade is whatever this creature's basic attack actually is,
    rather than a copy of it."""
    c.basic()
    c.shift(4)


@power(
    "m3020a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3020a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it is a rider on every
    melee attack the creature makes."""
    _advantage_rider(c, "1d6", ("melee",))


@power(
    "m3020a4",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3020a4(c: Cast) -> None:
    """The flanking half only, and written as the one extra point.

    Flanking is already worth +2 through combat advantage, so what the
    printed line adds is a third -- gated on flanking in particular, because
    an enemy caught out some other way is granting combat advantage and is
    not flanked, and pays nothing. "Grants a +3 instead of a +2 while aiding
    another" is a skill-check rule and aid another is not in the engine.
    """
    me = c.me
    c.bonus(
        "attack",
        1,
        until=When.ENCOUNTER,
        on=me,
        kind="untyped",
        when=lambda ctx: flanked_by(c.world, ctx["target"], me),
    )


@power(
    "m3020a5",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3020a5(c: Cast) -> None:
    """A skill contest and nothing else -- an Insight check against a Bluff
    check -- so it is declared inert rather than given an invented mechanic."""
    c.note("m3020a5: mimics sounds and voices; Insight opposes its Bluff")


# --------------------------------------------------------------------------
# m3030
# --------------------------------------------------------------------------


@power(
    "m3030a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 2),
)
def m3030a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3030a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 3),
    requires=_an_enemy_is_poisoned,
    requires_text="an enemy must be taking ongoing poison damage",
)
def m3030a1(c: Cast) -> None:
    """Only into a creature already carrying poison -- usually its own.

    The printed restriction is per target and the header's `target` field
    cannot say so, so `requires` carries the half about the board and the
    body checks this target.
    """
    if not _poisoned(c, c.target):
        return
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m3030a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 3),
    requires=_unseen,
    requires_text="the target cannot see it",
)
def m3030a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.world.relations.holds(Relation.HIDDEN_FROM, c.me, victim):
        return
    if c.strike():
        c.hit()


@power(
    "m3030a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3030a3(c: Cast) -> None:
    """A rider on every attack, so a trait rather than an action."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and _poisoned(c, ev.target):
            c.flat(2, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m3030a3")


# --------------------------------------------------------------------------
# m3071
# --------------------------------------------------------------------------


@power(
    "m3071a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
)
def m3071a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3071a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3071a1(c: Cast) -> None:
    """Trample and keep going, with the target given no opening as it leaves.

    The hooves are m3071a0 rather than a copy, so the damage line stays in
    one place, and the attack is taken before the move for the reason level 1
    gives: the move picks its own destination and one taken first can leave
    the target out of reach.
    """
    c.no_provoke(from_=c.target)
    use(c.world, c.me, "m3071a0", targets=[c.target], spend=False)
    c.move(c.speed_of())


@power(
    "m3071a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=6),
)
def m3071a2(c: Cast) -> None:
    """No damage: the whole of the hit line is the flinch it puts in them."""
    if c.strike():
        c.penalty("attack", 2, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m360
# --------------------------------------------------------------------------


@power(
    "m360a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 3),
)
def m360a0(c: Cast) -> None:
    """The printed critical -- 1d12 + 15 -- is the ordinary rule: a critical
    maxes the dice, and 12 + 3 is what the card prints."""
    if c.strike():
        c.hit()


@power(
    "m360a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m360a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m360a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m360a2(c: Cast) -> None:
    """The surge and the ten hit points are two lines, not one: a monster's
    surge is a quarter of its maximum and the card names a flat number, so
    the surge is spent for nothing and the printed amount is healed."""
    c.basic()
    c.spend_surge(on=c.me)
    c.heal(10, on=c.me)


@power(
    "m360a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m360a3(c: Cast) -> None:
    """Cover is cancelled by paying it back, as a gate on the attack roll.

    `c.strike(ignore_cover=True)` says this in one word, but a trait cannot
    reach into the bodies of the rows it modifies -- and this one modifies
    every ranged attack the creature makes, including its basic. What is left
    is a modifier of exactly the size cover is worth, asked at the moment the
    roll is put together: `resolve.attack` subtracts the cover and then adds
    every "attack" mod whose gate is true, so the two cancel.

    Two of them rather than one because the amount varies and a modifier's
    value is fixed while its gate is not -- only one gate can be true at a
    time. Total concealment is not cover in the engine and so is untouched,
    which is what the printed exception asks for.
    """
    me = c.me

    def blocked_by(amount: int) -> Callable[[dict[str, Any]], bool]:
        def gate(ctx: dict[str, Any]) -> bool:
            p = get(ctx.get("power") or "")
            who = ctx.get("target")
            if p is None or who is None or p.reach.kind != "ranged":
                return False
            if distance_between(c.world, me, who) > 5:
                return False
            return int(cover_between(c.world, me, who, ranged=True)) == amount

        return gate

    for cover in (Cover.PARTIAL, Cover.SUPERIOR):
        c.bonus(
            "attack",
            int(cover),
            until=When.ENCOUNTER,
            on=me,
            kind="untyped",
            when=blocked_by(int(cover)),
        )


# --------------------------------------------------------------------------
# m376
# --------------------------------------------------------------------------


@power(
    "m376a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
)
def m376a0(c: Cast) -> None:
    """The flight is an Effect line and is taken whether the bite landed or
    not. The exemption is ended as soon as the flight is over, so a second
    move on the same turn provokes the way it should."""
    if c.strike():
        c.hit()
    guard = c.no_provoke()
    c.move(4)
    if guard is not None:
        c.world.effects.end(guard, "the flight is over")


@power(
    "m376a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d8", 4),
    requires=_unseen,
    requires_text="the target cannot see it",
)
def m376a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.world.relations.holds(Relation.HIDDEN_FROM, c.me, victim):
        return
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m376a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m376a2(c: Cast) -> None:
    """Gone until it swings, with no clock on it at all."""
    _recharge_on(c, DamageApplied, lambda ev: ev.target == c.me)
    _vanish_until_it_swings(c, When.ENCOUNTER)


# --------------------------------------------------------------------------
# m411
# --------------------------------------------------------------------------


@power(
    "m411a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m411a0(c: Cast) -> None:
    """Light is a property of the fight, which is what `c.terrain` asks.

    It answers False in an ordinary daylit encounter, which is the whole
    reason the check is written out rather than assumed -- the same
    arrangement the underwater creatures use for their bonus.
    """
    dark = c.terrain("darkness") or c.terrain("dim light")
    if c.strike(plus=2 if dark else 0):
        c.hit()
        if dark:
            c.flat(6)


@power(
    "m411a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m411a1(c: Cast) -> None:
    """Swoop, bite, and away, with the target given no opening as it goes."""
    c.no_provoke(from_=c.target)
    c.basic()
    c.move(8)


# --------------------------------------------------------------------------
# m478
# --------------------------------------------------------------------------


@power(
    "m478a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m478a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m478a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 2),
)
def m478a1(c: Cast) -> None:
    """The bleed is written; the disease contracted with it is not.

    Diseases are a track of escalating states rolled between encounters and
    there is nothing in the engine that holds one, so the half of the line
    that lands in a fight is the only half written. There is no `disease`
    keyword to carry either.
    """
    if c.strike():
        c.hit()
        c.ongoing(2)


@power(
    "m478a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m478a2(c: Cast) -> None:
    """Wearing a person is what costs it its disease-bearing bite.

    The two shapes differ by exactly one thing the engine can hold, so that
    is what is asked: taking the human form lifts m478a1 out of what the
    creature knows and reverting hands it back.
    """
    human = c.choose(["human", "dire rat"], "which shape") == "human"
    _reshape(c, drops="m478a1" if human else "")


@power(
    "m478a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m478a3(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee",))


# --------------------------------------------------------------------------
# m4788
# --------------------------------------------------------------------------


@power(
    "m4788a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4788a0(c: Cast) -> None:
    _still_hidden_on_a_miss(c, ("ranged",))


@power(
    "m4788a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
)
def m4788a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4788a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 4),
)
def m4788a2(c: Cast) -> None:
    """One creature on the line at a time, so the previous one is cut loose.

    The printed line makes that a rule rather than a courtesy, and the hold
    carries this row's ref as its label, which is the only thing that tells
    one strand from anything else the creature has going.

    Not written: the Sustain Standard line, which repeats the damage and the
    pull. `Effect` can be sustained -- the clock refreshes -- but nothing
    runs when it is, so "Sustain Standard: *do this*" has nowhere to go. Nor
    is the filament attackable: it has no position and no hit points of its
    own, and a creature is the only thing an attack can be aimed at here.
    """
    victim = c.target
    if victim is None:
        return
    for effect in list(c.world.effects.live.values()):
        if effect.label == c.ref and effect.source == c.me:
            c.world.effects.end(effect, "the line was cast again")
    if not c.strike():
        return
    c.hit()
    c.pull(3)
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m4799
# --------------------------------------------------------------------------


@power(
    "m4799a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4799a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m4799a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m4799a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4799a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4799a2(c: Cast) -> None:
    """Both bites, and landing the pair opens the third.

    The two attacks are the row that prints them rather than copies, so the
    damage line stays in one place. `use` reports whether a power went off
    and not whether it hit, so the hits are counted off the bus for the
    duration of the pair -- the arrangement level 2 settled on for the other
    row that pays for landing two.
    """
    victim = c.target
    if victim is None:
        return
    landed: list[str] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim and ev.power == "m4799a1":
            landed.append(ev.power)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        for _ in range(2):
            use(c.world, c.me, "m4799a1", targets=[victim], spend=False)
    finally:
        c.world.bus.off(sub)
    if len(landed) < 2:
        return
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m4799a3")
    use(c.world, c.me, "m4799a3", targets=[victim])


@power(
    "m4799a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 4, kind=LIMITED),
)
def m4799a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


_M4799_MISSED = "the m4799 misses with an attack"


@power(
    "m4799a4",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4799_MISSED,
    on=Trigger(Miss, when=by_me, text=_M4799_MISSED),
)
def m4799a4(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m481
# --------------------------------------------------------------------------


@power(
    "m481a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
)
def m481a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m481a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m481a1(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m481a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 3, kind=LIMITED),
)
def m481a2(c: Cast) -> None:
    """"Save ends both" is two holds and exactly one saving throw.

    Only the poison runs on the saving-throw clock; the penalty is given the
    encounter's and ended with it. Both on `SAVE_ENDS` would be two saves,
    and the card offers one -- which is the difference between shaking the
    whole thing off and shaking off half of it.
    """
    _recharge_on(
        c, PowerUsed, lambda ev: ev.actor == c.me and ev.power == "m481a1"
    )
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    burn = c.ongoing(10, DamageType.POISON)
    hold = c.penalty(WILL, 2, until=When.ENCOUNTER, on=victim)
    if burn is not None and hold is not None:
        burn.on_end.append(lambda: c.world.effects.end(hold, "saved"))


# --------------------------------------------------------------------------
# m4992
# --------------------------------------------------------------------------


@power(
    "m4992a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4992a0(c: Cast) -> None:
    _hides_with_cover(c)


@power(
    "m4992a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4992a1(c: Cast) -> None:
    """The whole of this line is an exemption from two Stealth check
    penalties, and there are no skill checks in the engine to be exempt from.
    Declared inert rather than approximated: m4992a0 already carries the part
    of the creature's stealth that a fight can see."""
    c.note("m4992a1: no Stealth penalty for moving more than 2 squares or running")


@power(
    "m4992a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4992a2(c: Cast) -> None:
    """Five extra against anybody it was unseen by when the turn began.

    Not the same clause as combat advantage even though being unseen grants
    it, and not the same as being unseen *now* either: the printed line fixes
    the list at the start of the turn, so a creature that spots it halfway
    through still pays and a creature flanking it never does. The list is
    therefore taken at `TurnStart` rather than asked of the board at the
    moment of the hit.
    """
    me = c.me
    blind: set[int] = set()

    def snapshot(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            blind.clear()
            blind.update(c.world.relations.targets(Relation.HIDDEN_FROM, me))

    def rider(ev: Hit) -> None:
        if ev.attacker == me and ev.target in blind:
            c.flat(5, on=ev.target)

    blind.update(c.world.relations.targets(Relation.HIDDEN_FROM, me))
    c.watch(TurnStart, snapshot, until=When.ENCOUNTER, on=me, label="m4992a2 list")
    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m4992a2")


@power(
    "m4992a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 6),
)
def m4992a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4992a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 2, kind=LIMITED),
)
def m4992a4(c: Cast) -> None:
    """Three rolls, all at the one declared target.

    The printed line is one attack made three times and says nothing about
    spreading them, and `target` can only say how many creatures a row takes,
    not how many rolls it makes -- `UpTo(3)` would be three *creatures* and
    one roll each, which fires once against a lone enemy. Three rolls at the
    target is the half that is always true.
    """
    for _ in range(3):
        if c.strike():
            c.hit()
            c.immobilized(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m5053
# --------------------------------------------------------------------------


@power(
    "m5053a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5053a0(c: Cast) -> None:
    _hides_with_cover(c)


@power(
    "m5053a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d8", 6, dtype=DamageType.NECROTIC),
)
def m5053a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5053a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 8, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m5053a2(c: Cast) -> None:
    """It rides the target's shadow until the target shakes it off.

    Standing in the target's square cannot be said -- `movement.step` refuses
    an occupied one and there is no way to ask for it -- so the meld is
    written as everything else it does: it goes wherever the target goes
    without provoking, which is what a shift already is; it is much harder to
    hit; it is much harder to miss *that* creature with; and when the save
    lands it is left adjacent, which is where the printed line puts it.

    Only the hold on the target runs on the saving-throw clock. The bonuses
    sit on the creature itself, so giving them their own `SAVE_ENDS` would
    have the wrong creature rolling to end them -- they are hung on the
    hold's end instead.
    """
    _recharge_on(
        c, PowerUsed, lambda ev: ev.actor == c.me and ev.power == "m5053a3"
    )
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    me = c.me
    meld = c.effect(f"{c.ref} meld", until=When.SAVE_ENDS, on=victim)
    if meld is None:
        return

    def follow(ev: Moved) -> None:
        if ev.actor != victim:
            return
        landing = _free_square_beside(c, victim)
        if landing is not None:
            c.shift(to=landing)

    held: list[Effect | None] = [
        c.watch(Moved, follow, until=When.ENCOUNTER, on=me, label="m5053a2 follow")
    ]
    held += [
        c.bonus(d, 4, until=When.ENCOUNTER, on=me, kind="untyped")
        for d in (AC, FORT, REF, WILL)
    ]
    held.append(
        c.bonus(
            "attack",
            5,
            until=When.ENCOUNTER,
            on=me,
            kind="untyped",
            when=lambda ctx: ctx.get("target") == victim,
        )
    )

    def release() -> None:
        for effect in held:
            if effect is not None:
                c.world.effects.end(effect, "the target shook it off")
        landing = _free_square_beside(c, victim)
        if landing is not None:
            c.shift(to=landing)

    meld.on_end.append(release)


_M5053_DROPPED = "a living creature within 5 squares drops to 0 hit points or fewer"


@power(
    "m5053a3",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M5053_DROPPED,
    on=Trigger(Dropped, when=_creature_within(5), text=_M5053_DROPPED),
)
def m5053a3(c: Cast) -> None:
    """Either side's creature counts: the printed line says "a living
    creature", and `ally_within` and `enemy_within` each rule out half the
    board."""
    who = getattr(c.trigger, "actor", None)
    if who is not None:
        landing = _free_square_beside(c, who)
        if landing is not None:
            c.teleport(20, to=landing)
    c.bonus("attack", 2, until=When.EONT, on=c.me)
