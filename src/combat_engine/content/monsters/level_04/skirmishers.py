"""Monster abilities, level 4: the ones that move, and the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=9)` and `Damage("1d8", 5)` -- and the engine takes the level back out
of the attack and rescales the damage if a fight is being played on another
edition's maths.

The conventions of the three levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits or death throes and are written as such; a printed range of
"5/10" takes the **normal** range; and a row that shifts and swings takes the
swing first, because the movement picks its own destination and one taken
first can leave the target out of reach.

The helpers that hold a lurker unseen, that pay for combat advantage and that
put a recharge back up on a printed sentence were written for levels 2 and 3
and are imported rather than copied.

Skirmishers first, then lurkers, each group in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_02.skirmishers import (
    _advantage_rider,
    _hides_with_cover,
    _still_hidden_on_a_miss,
    _unseen,
)
from combat_engine.content.monsters.level_03.controllers import _nonminion
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _grabbing,
    _is_bloodied,
    _not_grabbing,
    _poisoned,
    _recharge_on,
    _vanish_until_it_swings,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MELEE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
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
    Health,
    Initiative,
    Keyword,
    Melee,
    Mod,
    Movement,
    Powers,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    Window,
    World,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Hit,
    Miss,
    RelationCleared,
    RelationSet,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    cover_between,
    enemies,
    flanked_by,
    has_combat_advantage,
    is_,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    ally_within,
    both,
    by_melee,
    by_ranged,
    either,
    targets_me,
)

#: The three conditions a solo's own turn shrugs off.
_MIND_HELD = (Condition.DAZED, Condition.STUNNED, Condition.DOMINATED)


def _struck(c: Cast, ref: str, times: int, victim: int | None = None) -> list[int]:
    """Fire a row a number of times and report who it actually hit.

    `use` says whether a power went off and not whether it landed, so the
    hits are counted off the bus -- the arrangement level 3 settled on for
    the other rows that pay for landing two. With no `victim` the row picks
    its own target, which is what "after the jump, it uses ..." wants.
    """
    hits: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == c.me and ev.power == ref:
            hits.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        for _ in range(times):
            use(
                c.world, c.me, ref,
                targets=None if victim is None else [victim], spend=False,
            )
    finally:
        c.world.bus.off(sub)
    return hits


def _basic_ref(c: Cast) -> str:
    """Which row this creature's basic attack actually is.

    `c.basic()` makes the swing and says only whether it went off, so a row
    that pays for landing two of them needs the ref as well, to tell its own
    hits from anything else going on in the same window.
    """
    known = c.world.get(c.me, Powers)
    return (known.basic if known else MELEE) or MELEE


def _charge_rider(c: Cast, dice: str, *, prone: bool = False) -> None:
    """Extra damage, and sometimes a fall, on anything it lands on a charge.

    Read off the `Hit`, which carries `charge` the way it carries
    `opportunity`. A damage modifier would not do it: the printed line adds
    dice rather than a number, and one of the two knocks the target down as
    well.
    """
    me = c.me
    ref = c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not getattr(ev, "charge", False):
            return
        c.damage(dice, on=ev.target, detail=ref)
        if prone:
            c.prone(on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


def _guarded_move(c: Cast, squares_: int) -> None:
    """Move, provoking nothing, and hand the exemption back afterwards.

    A jump is a move in the engine -- there is no separate op -- so "this
    movement does not provoke opportunity attacks" is the whole of what the
    printed line adds. Ended as soon as the move is over so a second move on
    the same turn provokes the way it should.
    """
    guard = c.no_provoke()
    c.move(squares_)
    if guard is not None:
        c.world.effects.end(guard, "the move is over")


def _until_the_grab_ends(c: Cast, victim: int, *holds: Effect | None) -> None:
    """Hang some holds on a grab rather than on a clock.

    "Until the grab ends, the target takes ongoing 5 damage" is a duration
    the enum has no word for, and `When.SAVE_ENDS` is the wrong one: it
    would let a creature shake the damage off while still held. So the holds
    run to the end of the encounter and are ended by hand when the relation
    goes.
    """
    me = c.me
    live = [h for h in holds if h is not None]
    if not live:
        return

    def released(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.source != me or ev.target != victim:
            return
        for hold in live:
            c.world.effects.end(hold, "the grab ended")

    c.watch(
        RelationCleared, released, until=When.ENCOUNTER, on=me, label=f"{c.ref} grab"
    )


def _unseen_rider(c: Cast, dice: str, bonus: int = 0) -> None:
    """Extra damage on anything it lands on a creature that cannot see it.

    Asked of the relation at the moment of the `Hit`, which is readable
    because `resolve.attack` clears `HIDDEN_FROM` *after* the hit is
    announced -- the listener runs inside that emit. Asking the board any
    later answers "no" for every creature that struck from concealment.
    """
    me = c.me
    ref = c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if c.world.relations.holds(Relation.HIDDEN_FROM, me, ev.target):
            c.damage(dice, bonus, on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


def _weakened_enemy(world: World, eid: int) -> bool:
    return any(is_(world, foe, Condition.WEAKENED) for foe in enemies(world, eid))


def _has_advantage(world: World, eid: int) -> bool:
    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


def _is_insubstantial(world: World, eid: int) -> bool:
    return is_(world, eid, Condition.INSUBSTANTIAL)


def _grabbed_or_grabbing(c: Cast) -> bool:
    me = c.me
    return bool(
        c.world.relations.targets(Relation.GRABBED_BY, me)
        or c.world.relations.sources(Relation.GRABBED_BY, me)
    )


# --------------------------------------------------------------------------
# m128
# --------------------------------------------------------------------------


@power(
    "m128a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 4),
)
def m128a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m128a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 4),
)
def m128a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M128_SLAIN = "the m128 drops to 0 hit points"


@power(
    "m128a2",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M128_SLAIN,
    on=Trigger(Dropped, when=about_me, text=_M128_SLAIN),
)
def m128a2(c: Cast) -> None:
    """Filed as a standard action and plainly a death throe: the printed
    line is what happens when the creature is killed, so it is declared as
    the trigger it is rather than as something the creature spends a turn
    on. No attack roll -- the blindness is the whole of it."""
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m128a3",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m128a3(c: Cast) -> None:
    """A rider on every attack it makes, so a trait rather than an action."""
    _advantage_rider(c, "1d6", ("melee", "ranged"))


@power(
    "m128a4",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m128a4(c: Cast) -> None:
    """Four squares, harder to catch on the way, and everyone it finishes
    beside is caught out.

    The bonus is a gate rather than an effect put on and taken off around
    the move: the attack context carries `opportunity`, so the modifier is
    asked whether it applies at the moment the defence is read. It is ended
    with the move, because the printed line covers the move and nothing
    after it. The advantage has no printed clock; the end of the turn it was
    gained on is the shortest reading that is still worth having.
    """
    me = c.me
    guard = c.bonus(
        AC, 4, until=When.EOT, on=me, kind="untyped",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )
    c.move(4)
    if guard is not None:
        c.world.effects.end(guard, "the move is over")
    for foe in c.within(1, side="enemy"):
        c.grants_advantage(on=foe, until=When.EOT)


# --------------------------------------------------------------------------
# m134
# --------------------------------------------------------------------------


@power(
    "m134a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m134a0(c: Cast) -> None:
    """`kind` names which sort of rough ground, which is the whole of this
    line: webs and nothing else."""
    c.ignores_difficult("webs", until=When.ENCOUNTER)


@power(
    "m134a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 3),
)
def m134a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m134a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m134a2(c: Cast) -> None:
    """Jump first, then bite whatever the jump put it next to.

    The target is chosen after the movement rather than before it, which is
    the printed order and the only one that makes the jump worth anything --
    so the row declares no target of its own and lets m134a1 pick. `use`
    reports that the bite went off and not whether it landed, so the prone
    is paid off the bus.
    """
    _guarded_move(c, 6)
    for who in _struck(c, "m134a1", 1):
        c.prone(on=who)


@power(
    "m134a3",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m134a3(c: Cast) -> None:
    _guarded_move(c, 10)


# --------------------------------------------------------------------------
# m200
# --------------------------------------------------------------------------


@power(
    "m200a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m200a0(c: Cast) -> None:
    """The step is on the hit line with the damage -- the printed sentence
    is one clause -- so it is taken only when the bite lands."""
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m200a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m200a1(c: Cast) -> None:
    """A rider on every charge it makes, so a trait rather than an action."""
    _charge_rider(c, "1d6", prone=True)


@power(
    "m200a2",
    level=4,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m200a2(c: Cast) -> None:
    c.teleport(5)


# --------------------------------------------------------------------------
# m2800
# --------------------------------------------------------------------------


@power(
    "m2800a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 2, dtype=DamageType.ACID),
)
def m2800a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


_M2800_KIN_DROPS = "an ally within 10 squares drops to 0 hit points"


@power(
    "m2800a1",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2800_KIN_DROPS,
    on=Trigger(Dropped, when=ally_within(10), text=_M2800_KIN_DROPS),
)
def m2800a1(c: Cast) -> None:
    """The printed trigger names the kind of creature as well as the side,
    and the type line of this stat block has no word for that kind -- it
    reads beast and natural and nothing narrower -- so an ally within 10 is
    the half that can be said. The bite picks its own target, because the
    shift comes first and is the whole point of it.
    """
    c.shift(2)
    use(c.world, c.me, "m2800a0", spend=False)


@power(
    "m2800a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m2800a2(c: Cast) -> None:
    """Bite on the wing: the attack is taken first, for the reason level 1
    gives on its own three of these -- the flight picks its own destination
    and one taken first can leave the target out of reach. Leaving provokes
    nothing from the creature it bit, which is the printed exemption."""
    c.no_provoke(from_=c.target)
    use(c.world, c.me, "m2800a0", targets=[c.target], spend=False)
    c.move(8)


@power(
    "m2800a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("3d6", 4, kind=LIMITED),
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m2800a3(c: Cast) -> None:
    """The price is its wings, and flight is a movement mode rather than a
    condition, so it is lifted out of `Movement.modes` and not put back --
    "until the end of the encounter" is the rest of the fight. Taken once
    for the whole blast rather than once per creature caught in it."""
    if c.strike():
        c.hit()
    if not c.last:
        return
    moves = c.world.get(c.me, Movement)
    if moves is not None:
        moves.modes.pop("fly", None)


# --------------------------------------------------------------------------
# m2831
# --------------------------------------------------------------------------


@power(
    "m2831a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 2),
)
def m2831a0(c: Cast) -> None:
    """Whether the target was already burning is asked **before** this bite
    adds its own poison, or the first bite would always answer yes."""
    already = _poisoned(c, c.target)
    if not c.strike():
        return
    c.hit()
    c.ongoing(5, DamageType.POISON)
    if already:
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m2831a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d6", 2),
    requires=_weakened_enemy,
    requires_text="an enemy must be weakened",
)
def m2831a1(c: Cast) -> None:
    """Only into something already failing. The printed restriction is per
    target and the header's `target` field cannot say so, so `requires`
    carries the half about the board and the body checks this target."""
    if not c.is_(Condition.WEAKENED):
        return
    if c.strike():
        c.hit()


@power(
    "m2831a2",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2831a2(c: Cast) -> None:
    """Four squares of shifting, and a friend's square costs nothing.

    Stepped one square at a time, because the exemption is per square: a
    single `c.shift(4)` picks a destination and arrives, and there is no
    later moment at which to ask what it went through. `share=True` is what
    lets it stand in an ally's space at all. The number of steps is capped
    as well as the paid ones -- a free square is a step that buys nothing,
    and two allies side by side would otherwise be a loop with no end.
    """
    left, steps = 4, 0
    friends = set(c.allies())
    while left > 0 and steps < 12:
        here = c.here
        options = sorted(
            sq
            for sq in spread({here}, 1) - {here}
            if c.world.grid.passable(sq)
            and (
                c.world.grid.occupant(sq) is None
                or c.world.grid.occupant(sq) in friends
            )
        )
        if not options:
            break
        dest = c.world.decide(c.me, "shift", options, f"{c.ref}: shift {left} left")
        shared = c.world.grid.occupant(dest) is not None
        if not c.shift(to=dest, share=shared):
            break
        steps += 1
        if not shared:
            left -= 1


# --------------------------------------------------------------------------
# m3111
# --------------------------------------------------------------------------


@power(
    "m3111a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3111a0(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m3111a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3111a1(c: Cast) -> None:
    """Extra damage against whoever the pack has surrounded. The ally pool
    includes the creature itself, so it is filtered out: the printed line
    counts its allies and it is not one of them."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        pack = [a for a in c.within(1, of=ev.target, side="ally") if a != me]
        if len(pack) >= 2:
            c.flat(2, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m3111a1")


@power(
    "m3111a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4),
)
def m3111a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m3111a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_is_bloodied,
    requires_text="must be bloodied",
)
def m3111a3(c: Cast) -> None:
    """The line it repeats is the row that prints it rather than a copy, so
    the damage stays in one place."""
    for _ in range(2):
        use(c.world, c.me, "m3111a2", targets=[c.target], spend=False)


@power(
    "m3111a4",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3111a4(c: Cast) -> None:
    """Four squares, and whoever swings at it on the way and misses has
    given itself away.

    The bonus is gated on `opportunity` rather than applied and taken back,
    and both holds end with the jump: the printed line covers the jump. The
    advantage the miss buys outlives it, to the end of this turn, which is
    what the card says.
    """
    me = c.me
    guard = c.bonus(
        AC, 5, until=When.EOT, on=me, kind="untyped",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )

    def flinched(ev: Miss) -> None:
        if ev.target == me and getattr(ev, "opportunity", False):
            c.grants_advantage(on=ev.attacker, until=When.EOT)

    watching = c.watch(Miss, flinched, until=When.ENCOUNTER, on=me, label="m3111a4")
    try:
        c.move(4)
    finally:
        if guard is not None:
            c.world.effects.end(guard, "the jump is over")
        c.world.effects.end(watching, "the jump is over")


@power(
    "m3111a5",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_bloodied,
    requires_text="must be bloodied",
)
def m3111a5(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m319
# --------------------------------------------------------------------------


@power(
    "m319a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 3),
)
def m319a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m319a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m319a1(c: Cast) -> None:
    """The swing is taken before the step, for the reason level 1 gives on
    its own three of these: the shift picks its own destination and one
    taken first can leave the target out of reach. The blade is whatever
    this creature's basic attack actually is rather than a copy of it."""
    c.basic()
    c.shift(1)


# --------------------------------------------------------------------------
# m4708
# --------------------------------------------------------------------------


@power(
    "m4708a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4708a0(c: Cast) -> None:
    """Half its speed, and the swing taken first for the usual reason.

    The attack this names is one the stat block never prints, so it is the
    creature's basic one -- and `c.basic` is what says that without naming
    a row. "Shifts **or** climbs" is one distance either way: the engine has
    one move op and a climb speed is a mode rather than a separate action,
    so what is left of the choice is the number of squares, which is the
    same for both.
    """
    c.basic()
    c.shift(c.speed_of() // 2)


@power(
    "m4708a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4708a1(c: Cast) -> None:
    """Both swings at the one creature, and landing the pair puts it down."""
    victim = c.target
    if victim is None:
        return
    if len(_struck(c, _basic_ref(c), 2, victim)) >= 2:
        c.prone(on=victim)


# --------------------------------------------------------------------------
# m500
# --------------------------------------------------------------------------


@power(
    "m500a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 2),
)
def m500a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m500a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m500a1(c: Cast) -> None:
    """Extra on a charge, and only while it is in the air.

    Being airborne is not a state the engine holds: `movement.mode_of` has
    it that a creature which *can* fly does, whenever it moves, which makes
    having the mode the whole of the question -- and it is a real one,
    because flight can be taken away. Asked at the moment of the hit rather
    than when the trait is armed, for that reason.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not getattr(ev, "charge", False):
            return
        moves = c.world.get(me, Movement)
        if moves is not None and moves.modes.get("fly"):
            c.damage("2d6", on=ev.target, detail="m500a1")

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m500a1")


@power(
    "m500a2",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m500a2(c: Cast) -> None:
    """One good blow and it comes apart.

    Written as damage equal to whatever it has left rather than by setting
    hit points, so everything that watches for a creature going down --
    `Dropped`, `Died`, the death throes of anything standing beside it --
    sees it happen. Untyped, so its resistances have no say in it.
    """
    me = c.me

    def shatter(ev: Hit) -> None:
        if ev.target != me or not ev.critical:
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    c.watch(Hit, shatter, until=When.ENCOUNTER, on=me, label="m500a2")


# --------------------------------------------------------------------------
# m111
# --------------------------------------------------------------------------


@power(
    "m111a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m111a0(c: Cast) -> None:
    """Unseen unless it has hold of something or something has hold of it.

    Total concealment is a standing property rather than a thing it does, so
    the relation is set directly rather than through `c.hide`: a hold with a
    duration would be re-applied every time an attack broke it, and this
    line is never broken by attacking. It is re-established whenever
    anything gives it away and whenever any grab ends, and dropped the
    moment a grab begins at either end of it.
    """
    me = c.me

    def veil() -> None:
        if _grabbed_or_grabbing(c):
            return
        for foe in c.enemies():
            if not c.is_hidden(from_=foe):
                c.world.relations.set(Relation.HIDDEN_FROM, me, foe)

    def again(_ev: Any) -> None:
        veil()

    def caught(ev: RelationSet) -> None:
        if ev.kind_ is Relation.GRABBED_BY and me in (ev.source, ev.target):
            c.unhide()

    veil()
    c.watch(TurnStart, again, until=When.ENCOUNTER, on=me, label="m111a0")
    c.watch(RelationCleared, again, until=When.ENCOUNTER, on=me, label="m111a0 again")
    c.watch(RelationSet, caught, until=When.ENCOUNTER, on=me, label="m111a0 held")


@power(
    "m111a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 2),
    requires=_not_grabbing,
    requires_text="must not already have hold of a creature",
)
def m111a1(c: Cast) -> None:
    """The escape DC is not written: nothing in the engine lets a grabbed
    creature try to get free
    to set a number for. The burn is hung on the grab rather than on a
    saving throw, which is what the printed duration says."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab()
    _until_the_grab_ends(c, victim, c.ongoing(5, until=When.ENCOUNTER))


_M111_STRUCK = "the m111 is attacked by an enemy other than the one it holds"


def _not_the_prisoner(world: World, me: int, ev: AttackDeclared) -> bool:
    """Aimed at me, by somebody I am not already holding.

    The printed trigger reads "is hit by", and `c.redirect` only works
    before the die is down -- after it there is a result that would have to
    be thrown out and rolled again against a different defence. So the
    declaration is what is answered, which is the window the printed effect
    actually needs.
    """
    if ev.target != me or ev.attacker == me:
        return False
    if not world.relations.targets(Relation.GRABBED_BY, me):
        return False
    return not world.relations.holds(Relation.GRABBED_BY, me, ev.attacker)


@power(
    "m111a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    requires=_grabbing,
    requires_text="must have hold of a creature",
    trigger=_M111_STRUCK,
    on=Trigger(
        AttackDeclared,
        when=both(_not_the_prisoner, either(by_melee, by_ranged)),
        text=_M111_STRUCK,
    ),
)
def m111a2(c: Cast) -> None:
    """It holds the prisoner in the way. The printed "recharge when it hits
    with m111a1" is put on top of the die the database files, the way level
    3 settled it: the two only ever agree to make the row available sooner."""
    _recharge_on(c, Hit, lambda ev: ev.attacker == c.me and ev.power == "m111a1")
    held = c.world.relations.targets(Relation.GRABBED_BY, c.me)
    if held:
        c.redirect(to=held[0])


# --------------------------------------------------------------------------
# m2883
# --------------------------------------------------------------------------


@power(
    "m2883a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 3),
)
def m2883a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2883a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d10", 4),
    requires=_is_insubstantial,
    requires_text="usable only while insubstantial",
)
def m2883a1(c: Cast) -> None:
    """It throws the target and follows it.

    The second teleport names a square rather than a distance -- "into a
    space adjacent to the target" -- and the target has just been moved
    three squares, so the printed three is measured to a named square rather
    than counted out from where it started.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.teleport(3, who=victim)
    landing = _free_square_beside(c, victim)
    if landing is not None:
        c.teleport(20, to=landing)


_M2883_HIT = "the m2883 is hit by a melee attack"


@power(
    "m2883a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M2883_HIT,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M2883_HIT),
)
def m2883a2(c: Cast) -> None:
    c.teleport(3)


@power(
    "m2883a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2883a3(c: Cast) -> None:
    """Half out of the world until it swings, and a minor keeps it there.

    Both halves are written: insubstantial as the condition, and phasing as
    the movement mode of the same name. The hold goes through the effects
    table rather than through `c.condition` because only the table takes a
    sustain cost, and without one a `When.SUSTAIN` effect lapses at the
    first turn boundary with nothing able to keep it. Attacking ends it
    whether or not the attack lands, so the watch is on the roll, and both
    the watch and the mode are torn down with the shape.
    """
    me = c.me
    shape = c.world.effects.apply(
        me, me, When.SUSTAIN, label=c.ref,
        conditions=(Condition.INSUBSTANTIAL,), sustain_cost=MINOR,
    )
    ghost = c.phasing(until=When.ENCOUNTER)

    def reveal(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(shape, "it attacked")

    seen = c.watch(AttackRolled, reveal, until=When.ENCOUNTER, on=me, label=c.ref)
    for held in (seen, ghost):
        if held is not None:
            shape.on_end.append(
                lambda h=held: c.world.effects.end(h, "the phase is over")
            )


# --------------------------------------------------------------------------
# m3022
# --------------------------------------------------------------------------


@power(
    "m3022a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 6),
)
def m3022a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3022a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 6),
)
def m3022a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3022a2",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3022a2(c: Cast) -> None:
    """Out of sight behind its own kind.

    `cover_between` counts bodies only on a ranged line and only the
    target's own allies -- somebody in your way is cover your side gave you
    -- so asking it that way is as close as the engine comes to "cover from
    other m3022s". It cannot say *which* body provided it, so terrain in the
    way counts here too. There is no Stealth check to roll: wherever it
    could have tried, it has.
    """
    me = c.me

    def conceal() -> None:
        for foe in c.enemies():
            if not c.is_hidden(from_=foe) and cover_between(
                c.world, foe, me, ranged=True
            ) is not Cover.NONE:
                c.hide(from_=foe)

    def each_turn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            conceal()

    conceal()
    c.watch(TurnStart, each_turn, until=When.ENCOUNTER, on=me, label="m3022a2")


@power(
    "m3022a3",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3022a3(c: Cast) -> None:
    """The flanking half only, and written as the one extra point.

    Flanking is already worth +2 through combat advantage, so what the
    printed line adds is a third -- gated on flanking in particular, because
    an enemy caught out some other way is granting combat advantage and is
    not flanked, and pays nothing. "Grants a +3 instead of a +2 while aiding
    another" is a skill-check rule and aid another is not in the engine.
    """
    me = c.me
    c.bonus(
        "attack", 1, until=When.ENCOUNTER, on=me, kind="untyped",
        when=lambda ctx: flanked_by(c.world, ctx["target"], me),
    )


@power(
    "m3022a4",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3022a4(c: Cast) -> None:
    _unseen_rider(c, "2d4", 4)


@power(
    "m3022a5",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3022a5(c: Cast) -> None:
    """A skill contest and nothing else -- an Insight check against a Bluff
    check -- so it is declared inert rather than given an invented
    mechanic."""
    c.note("m3022a5: mimics sounds and voices; Insight opposes its Bluff")


@power(
    "m3022a6",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3022a6(c: Cast) -> None:
    _still_hidden_on_a_miss(c, ("ranged",))


# --------------------------------------------------------------------------
# m3055
# --------------------------------------------------------------------------


@power(
    "m3055a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3055a0(c: Cast) -> None:
    """Squeezing costs it two of the three things it normally costs.

    `Condition.SQUEEZING` is half speed, -5 to attack and combat advantage
    to everybody. The first two are numbers and are cancelled by numbers of
    the same size, gated on the condition so nothing has to remember to put
    them back: the speed is halved *after* modifiers, so a bonus equal to
    the base speed is what a halving undoes.

    The third is not written. Granting combat advantage is read off the
    condition table by `query.grants_ca` and there is no modifier hook on
    it, so an exemption from it cannot be said at all.
    """
    me = c.me

    def squeezing(_ctx: dict[str, Any]) -> bool:
        return c.is_(Condition.SQUEEZING, on=me)

    c.bonus("attack", 5, until=When.ENCOUNTER, on=me, kind="untyped", when=squeezing)
    moves = c.world.get(me, Movement)
    if moves is not None:
        c.bonus(
            "speed", moves.speed, until=When.ENCOUNTER, on=me,
            kind="untyped", when=squeezing,
        )


@power(
    "m3055a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=7),
    damage=Damage(bonus=5, dtype=DamageType.ACID),
)
def m3055a1(c: Cast) -> None:
    """No dice at all is a real damage line, not a malformed one."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m3055a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.ACID),
)
def m3055a2(c: Cast) -> None:
    """Whatever hits it while it holds somebody, the prisoner takes half.

    Answered on `DamageRolled` in the interrupt window, which is the one
    moment the number exists and has not yet come off anybody's hit points:
    the event's amount is cut and the remainder dealt to the creature it is
    holding. Dealing that half emits a `DamageRolled` of its own, aimed at
    somebody else, so the listener does not answer itself.

    Both the burn and the sharing are hung on the grab rather than on a
    clock, because that is the printed duration.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab()
    me = c.me

    def split(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        held = c.world.relations.targets(Relation.GRABBED_BY, me)
        if not held:
            return
        half = ev.amount // 2
        ev.amount -= half
        if half:
            c.flat(half, dtype=ev.dtype, on=held[0])

    shared = c.watch(
        DamageRolled, split, until=When.ENCOUNTER, window=Window.BEFORE,
        on=me, label="m3055a2 shared",
    )
    _until_the_grab_ends(
        c, victim, c.ongoing(10, DamageType.ACID, until=When.ENCOUNTER), shared
    )


# --------------------------------------------------------------------------
# m382
# --------------------------------------------------------------------------


@power(
    "m382a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
)
def m382a0(c: Cast) -> None:
    """An aura 1 whose occupants are easier to hit in every way.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are exactly the two moments the penalty should go on
    and come off. The four defences ride one effect so they end together.
    Whoever is already standing inside is caught separately at the end --
    making the aura refreshes membership before its id exists for a listener
    to recognise.
    """
    held: dict[int, Effect] = {}
    ring = c.aura(1, until=When.ENCOUNTER)

    def chill(who: int) -> None:
        if who in held or who not in c.enemies():
            return
        held[who] = c.world.effects.apply(
            who, c.me, When.ENCOUNTER, label=c.ref,
            mods=[
                (who, Mod(what=d.value, value=-2, kind="untyped", label=c.ref))
                for d in (AC, FORT, REF, WILL)
            ],
        )

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            chill(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label="m382a0 in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label="m382a0 out")
    for actor in c.world.zones.occupants(ring):
        chill(actor)


@power(
    "m382a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 2, dtype=DamageType.NECROTIC),
)
def m382a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m382a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m382a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m382a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m382a3(c: Cast) -> None:
    """Gone until it swings, with no clock on it at all."""
    _vanish_until_it_swings(c, When.ENCOUNTER)


# --------------------------------------------------------------------------
# m4886
# --------------------------------------------------------------------------


@power(
    "m4886a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4886a0(c: Cast) -> None:
    _hides_with_cover(c)


@power(
    "m4886a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m4886a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m4886a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4),
    requires=_unseen,
    requires_text="the target cannot see it",
)
def m4886a2(c: Cast) -> None:
    """Out of the dark, and then it sits on what it caught.

    "Hidden from at the start of its turn" is read as hidden from now: the
    row is used on its own turn and nothing has broken the concealment yet
    unless it has already attacked, which is the only case the two readings
    differ on, and the relation is the only thing that can be asked.

    Not written: the -2 to getting free of the grab. Nothing in the
    engine to penalise -- nothing anywhere rolls one. The other half of that
    sentence is, as `Condition.PINNED` on the encounter's clock, ended with
    the grab.
    """
    victim = c.target
    if victim is None or not c.world.relations.holds(
        Relation.HIDDEN_FROM, c.me, victim
    ):
        return
    if not c.strike():
        return
    c.hit()
    c.prone()
    c.grab()
    _until_the_grab_ends(
        c, victim, c.condition(Condition.PINNED, until=When.ENCOUNTER)
    )


@power(
    "m4886a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 9),
    requires=_grabbing,
    requires_text="must have hold of a prone creature",
)
def m4886a3(c: Cast) -> None:
    """`requires` carries the half about the creature -- that it is holding
    somebody -- and the body checks that *this* target is the one held and
    down, which the header's `target` field cannot say."""
    victim = c.target
    if victim is None or not c.world.relations.holds(
        Relation.GRABBED_BY, c.me, victim
    ):
        return
    if not c.is_(Condition.PRONE, on=victim):
        return
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m491
# --------------------------------------------------------------------------


@power(
    "m491a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
)
def m491a0(c: Cast) -> None:
    """Hurt it while it is bleeding and everything beside it is splashed.

    Either side's creature: the printed line reads "each creature adjacent
    to it" and says nothing about teams. The splash is untyped-sourced acid
    dealt flat, so it cannot itself splash again -- it lands on somebody
    other than this creature, and the watch only answers damage to this one.
    """
    me = c.me

    def spray(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0 or not c.bloodied(on=me):
            return
        for who in c.within(1, side="any"):
            if who != me:
                c.flat(5, dtype=DamageType.ACID, on=who)

    c.watch(DamageApplied, spray, until=When.ENCOUNTER, on=me, label="m491a0")


@power(
    "m491a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m491a1(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m491a2",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m491a2(c: Cast) -> None:
    """A solo acting twice a round: a second slot in the initiative order.

    The printed line gives it a free action at that count rather than a
    whole turn, and there is no way to hand out a turn with one action in
    it; `c.extra_turn` is what the engine has for a creature that acts
    again, and the slot is where the card puts it.

    The second sentence is answered on the turn boundary rather than only on
    that slot, because nothing tells the two slots apart: if it cannot act
    for being stunned or dominated, the thing stopping it ends instead. That
    is a round early on its ordinary turn, and m491a3 would have ended them
    at the close of that turn anyway.
    """
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(at=init.rolled + 10)

    def instead(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for effect in list(c.world.effects.of(me)):
            if set(effect.conditions) & {Condition.STUNNED, Condition.DOMINATED}:
                c.world.effects.end(effect, "m491a2")

    c.watch(TurnStart, instead, until=When.ENCOUNTER, on=me, label="m491a2")


@power(
    "m491a3",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m491a3(c: Cast) -> None:
    """Nothing holds its mind for longer than its own turn."""
    me = c.me

    def clear(ev: TurnEnd) -> None:
        if ev.actor != me:
            return
        for effect in list(c.world.effects.of(me)):
            if set(effect.conditions) & set(_MIND_HELD):
                c.world.effects.end(effect, "m491a3")

    c.watch(TurnEnd, clear, until=When.ENCOUNTER, on=me, label="m491a3")


@power(
    "m491a4",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 4),
)
def m491a4(c: Cast) -> None:
    """The miss line is a flat 5 rather than half of the hit, so it is
    rolled in the body: `c.hit(half=True)` would halve 2d8 + 4."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)
    else:
        c.flat(5, dtype=DamageType.ACID)


@power(
    "m491a5",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m491a5(c: Cast) -> None:
    """One creature twice or two creatures once, which is what the printed
    line offers and what `UpTo(2)` lets the caller choose between."""
    for _ in range(2 if len(c.targets) == 1 else 1):
        if c.strike():
            c.hit()


@power(
    "m491a6",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 3, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m491a6(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)
    else:
        c.hit(half=True)


@power(
    "m491a7",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
)
def m491a7(c: Cast) -> None:
    """No attack roll: the Effect line lands on everybody in the burst. The
    DC 10 Heal check that lifts it is a skill check and there are none in
    the engine, so what is left is an effect that runs the fight."""
    c.vulnerable(5, DamageType.ACID, until=When.ENCOUNTER)
    c.penalty("attack", 2, until=When.ENCOUNTER)


_M491_MISSED = "an enemy misses the m491 with a melee attack"


@power(
    "m491a8",
    level=4,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 2),
    trigger=_M491_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M491_MISSED),
)
def m491a8(c: Cast) -> None:
    """The tail catches whoever swung and everyone standing with them. Their
    allies, not the dragon's: `side="ally"` is asked of this creature, so
    the neighbours are gathered off the board and filtered by team."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.prone()
    for mate in c.within(1, of=victim, side="enemy"):
        if mate != victim:
            c.flat(5, on=mate)


_M491_BLOODIED = "the m491 is first bloodied"


@power(
    "m491a9",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M491_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M491_BLOODIED),
)
def m491a9(c: Cast) -> None:
    """`Powers.restore` is what a recharge is, so the breath comes back up
    and goes off at once. "First bloodied" needs no guard -- `Bloodied` is
    emitted on the crossing and nowhere else. The blast picks its own aim,
    which is what `_auto_targets` is for."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m491a6")
    use(c.world, c.me, "m491a6")


# --------------------------------------------------------------------------
# m676
# --------------------------------------------------------------------------


@power(
    "m676a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6"),
)
def m676a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m676a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    requires=_has_advantage,
    requires_text="requires combat advantage",
)
def m676a1(c: Cast) -> None:
    """Both swings are the row that prints them rather than copies, so the
    damage line stays in one place. The printed requirement is per target,
    so `requires` carries the half about the board and the body checks that
    it has the drop on *this* one."""
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        return
    if len(_struck(c, "m676a0", 2, victim)) >= 2:
        c.ongoing(5, on=victim)


@power(
    "m676a2",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m676a2(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee",))


_M676_TARGETED = "the m676 is targeted by a melee or a ranged attack"


@power(
    "m676a3",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M676_TARGETED,
    on=Trigger(
        AttackDeclared,
        when=both(targets_me, either(by_melee, by_ranged)),
        text=_M676_TARGETED,
    ),
)
def m676a3(c: Cast) -> None:
    """Somebody expendable is pushed into the way.

    Minion-ness is a column on the stat block that reaches no component, so
    it is read off the row the way `Cast.kinds_of` reads the type line.
    `AttackDeclared` rather than the roll, because `c.redirect` only works
    before the die is down.
    """
    beside = sorted(
        a for a in c.within(1, side="ally")
        if a != c.me and not _nonminion(c.world, a)
    )
    friend = c.choose(beside, "the blow finds a minion instead") if beside else None
    if friend is not None:
        c.redirect(to=friend)


@power(
    "m676a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m676a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m676a5",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m676a5(c: Cast) -> None:
    """Asked off the attacker at the moment the defence is read, which is
    the only place the question can be answered -- a trap is a kind of
    attacker rather than a kind of attack."""
    for d in (AC, FORT, REF, WILL):
        c.bonus(
            d, 2, until=When.ENCOUNTER, on=c.me, kind="untyped",
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )


# --------------------------------------------------------------------------
# m880
# --------------------------------------------------------------------------


@power(
    "m880a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m880a0(c: Cast) -> None:
    _unseen_rider(c, "4d6")


@power(
    "m880a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m880a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m880a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m880a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m880a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m880a3(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m880a4",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m880a4(c: Cast) -> None:
    """"Save ends both" is two holds and exactly one saving throw.

    Only the poison runs on the saving-throw clock; the penalty is given the
    encounter's and ended with it. Both on `SAVE_ENDS` would be two saves,
    and the card offers one.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    burn = c.ongoing(5, DamageType.POISON)
    hold = c.penalty("attack", 2, until=When.ENCOUNTER, on=victim)
    if burn is not None and hold is not None:
        burn.on_end.append(lambda: c.world.effects.end(hold, "saved"))
