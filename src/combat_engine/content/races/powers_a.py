"""Racial powers, the first batch: `cls` is a race ref rather than a class.

Four shapes account for nearly all of it.

**"Choose Strength, Constitution or Dexterity when you gain this."** Half a
dozen of these print three attack lines and one is picked at build time.
`Attack` takes one ability, so the header carries the first of them and the
choice itself is `c.ability_for(ref)`.

**Removed from play and back again.** "You cease to exist until the start of
your next turn" is `Condition.REMOVED`, whose rules already say the creature
can neither act nor move; the reappearance is a `c.watch` on `TurnStart`,
because the condition expiring is not itself an event a row can hang a
teleport on.

**Forced movement answered mid-flight.** `ForcedMove` is a `Decision` and
carries `target`, `source` and `squares`, so "you are pushed, pulled or
slid" is one trigger and both the count and the shover are on it. `Moved`
would be too late for the interrupt and carries neither.

**A skill bonus is a real modifier, not an inert row.** `c.bonus("skill:x")`
is read by `skills.check`, so only the rows whose entire printed effect is a
Thievery check or an hour-long disguise are `out_of_combat=True`.

**Four markers written here were wrong and are gone.** "Move through enemy
spaces" is `c.phasing`, which `movement._clear` reads to waive the body as
well as the wall; "no penalty for squeezing" is `c.ignore_condition(
Condition.SQUEEZING)`, whose rules are exactly the three the penalty is;
"until you attack" is a `c.watch` on `AttackRolled` plus `c.end_effect`;
and "difficult terrain for creatures that lack earth walk" is the
`difficult=` label, because earth walk *is* three `c.ignores_difficult`
words and `Grid.rough` skips the ones a mover ignores.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import lent
from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    DAILY,
    DEX,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    WIS,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Effect,
    ForcedMove,
    Healed,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveStart,
    Ranged,
    Rerolled,
    SavingThrow,
    SkillCheck,
    Square,
    Target,
    Trigger,
    TurnStart,
    UpTo,
    When,
    both,
    by_me,
    by_melee,
    distance,
    enemy_within,
    hits_me,
    my_check,
    power,
    rerolled_by,
    targets_me,
)
from combat_engine.engine.components import Position
from combat_engine.engine.query import allies, bloodied, distance_between, team
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.zones import Zone

#: A creature the power summons whose numbers are printed nowhere the spec
#: carries -- no monster row behind it and no block in the entry either, so
#: `Summon`'s defaults are all there is.
FROM_BLOCK = ("spec.stat_block()",)
SHADOW = [Keyword.SHADOW]


# -- small shared questions -------------------------------------------------


def _bloodied(world: Any, eid: int) -> bool:
    """"Requirement: You must be bloodied"."""
    return bloodied(world, eid)


def _beside_ally(world: Any, eid: int) -> bool:
    """"Requirement: You must be adjacent to an ally"."""
    return any(distance_between(world, eid, a) <= 1 for a in allies(world, eid))


def _is_enemy(world: Any, me: int, who: int | None) -> bool:
    return who is not None and who != me and team(world, who) is not team(world, me)


def _used(ref: str):  # noqa: ANN202
    """`PowerUsed`: this creature used that row."""

    def when(world: Any, me: int, ev: Any) -> bool:
        return ev.actor == me and ev.power == ref

    return when


def _failed_save(world: Any, me: int, ev: Any) -> bool:
    return ev.actor == me and not ev.saved


#: The two conditions p16040 names. The event carries no conditions at all,
#: so the narrowing is checked on the effect that is still standing.
_A_HOLD = frozenset({Condition.DAZED, Condition.STUNNED})


def _the_hold(world: Any, me: int, against: str) -> Any:
    """The dazing or stunning effect a saving throw was made against.

    `SavingThrow.against` is `str(eff)` and nothing else, so the effect is
    found by that rendering over the ones standing on the saver -- the route
    `items/arms._my_save_against_hold` already takes.
    """
    for eff in world.effects.of(me):
        if str(eff) == against and _A_HOLD & set(eff.conditions):
            return eff
    return None


def _saved_a_hold(world: Any, me: int, ev: Any) -> bool:
    """"You save against a dazing or stunning effect."

    The narrowing is here and not in the body so a save against anything
    else does not spend the daily.
    """
    return bool(
        ev.actor == me
        and ev.saved
        and _the_hold(world, me, getattr(ev, "against", "")) is not None
    )


def _my_kill(world: Any, me: int, ev: Any) -> bool:
    """`Dropped` names its killer `source`, and has no `target` at all."""
    return ev.source == me


def _my_bloodying(world: Any, me: int, ev: Any) -> bool:
    """`Bloodied` names its striker `source`, the shape `Dropped` has."""
    return ev.source == me and _is_enemy(world, me, ev.actor)


def _shifting(world: Any, me: int, ev: Any) -> bool:
    return ev.kind_ == "shift"


def _subject_within(squares: int):  # noqa: ANN202
    """Whoever this happened *to* is within range -- either side of the fight."""

    def check(world: Any, me: int, ev: Any) -> bool:
        who = ev.target
        return who is not None and distance_between(world, me, who) <= squares

    return check


def _bloodied_foe_attacks_us(world: Any, me: int, ev: Any) -> bool:
    """"A bloodied enemy attacks you or your ally adjacent to you"."""
    foe = ev.attacker
    if not _is_enemy(world, me, foe):
        return False
    if not bloodied(world, foe):
        return False
    who = ev.target
    if who == me:
        return True
    return (
        who is not None
        and team(world, who) is team(world, me)
        and distance_between(world, me, who) <= 1
    )


def _beside(c: Cast) -> int | None:
    """An ally standing next to the caster."""
    for mate in c.allies():
        if mate != c.me and c.adjacent(mate):
            return mate
    return None


def _until_you_attack(c: Cast, held: Effect | None) -> None:
    """"...until you attack" -- an effect with no clock, ended by a watch.

    `AttackRolled` rather than `AttackDeclared`, which is what `c.on_attack`
    watches: the printed sentence is that you attack *out of* the hiding, so
    the swing itself still has whatever the effect was worth. `advantage` is
    settled by the time this event is announced and the invisibility is gone
    for every swing after it.
    """
    if held is None:
        return
    me = c.me

    def stop(ev: Any) -> None:
        if ev.attacker == me:
            c.end_effect(held, why=f"{c.ref}: you attacked")

    c.watch(AttackRolled, stop, until=When.EONT, once=True)


# -- r33: the elemental manifestations ---------------------------------------


@power(
    "p10043",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ACID],
    attack=Attack((STR, CON, DEX), vs=REF, plus=3),
)
def p10043(c: Cast) -> None:
    """`c.overrun` is the only verb that walks through occupied squares and
    then says who was passed through, which is what "each creature whose
    space you enter" needs.

    Half the speed is the destination, not a second argument.
    `movement.overrun` walks the line from here to `to=` and never consults
    speed at all -- it is the bare `c.overrun()` that spends the whole of it,
    by picking out of everywhere a full move reaches. So the candidates come
    from `reachable_squares` at half, priced as the shift the card prints,
    and the one with the most enemies on the way is offered first, which is
    the ranking the engine's own no-destination branch uses and the reason
    it has one: with nobody playing, the first option is the answer.
    """
    me = c.me
    here = c.here
    half = max(1, c.speed_of() // 2)
    # Unoccupied, which is the printed "you must end your movement in an
    # unoccupied square": `reachable_squares` already refuses a square
    # somebody is standing in, so the trample can pass through a body and
    # not stop on one.
    options = c.world.reachable_squares(me, half, kind="shift")
    if not options:
        return
    standing = {sq: foe for foe in c.enemies() for sq in squares_of(c.world, foe)}

    def crossed(dest: Square) -> int:
        """How many enemies lie on a straight run from here to there.

        `distance` is the grid's own, so a square is on a shortest run
        exactly when the two legs through it add up to the whole -- the
        question `movement.overrun`'s private line walk answers, asked
        without a second copy of the geometry in this file.
        """
        whole = distance(here, dest)
        return len({
            foe
            for sq, foe in standing.items()
            if distance(here, sq) + distance(sq, dest) == whole
        })

    ranked = sorted(options, key=lambda dest: (-crossed(dest), dest))
    where = c.choose(ranked, f"{c.ref}: trample to")
    if where is None:
        return
    for foe in c.overrun(to=where):
        if c.strike(on=foe):
            c.damage("1d8", c.str_mod, dtype=DamageType.ACID, on=foe)


@power(
    "p10046",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p10046(c: Cast) -> None:
    """`Condition.REMOVED` already rules out acting and moving and cuts
    line of sight both ways. Coming back is hung on `TurnStart` because
    the condition running out announces nothing to teleport from."""
    c.condition(Condition.REMOVED, until=When.SONT, on=c.me)

    def back(ev: Any) -> None:
        if ev.actor == c.me:
            c.teleport(3)

    c.watch(TurnStart, back, until=When.EONT, once=True)


@power(
    "p14075",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def p14075(c: Cast) -> None:
    """`c.phasing` is what lets a creature enter an occupied square --
    `movement._clear` waives both the wall and the body for a ghost -- and
    it is also the grain-of-sand opening, which is the same sentence read
    the other way. It has to stop somewhere legal, which the form does."""
    c.insubstantial(until=When.SONT, on=c.me)
    c.no_provoke(on=c.me, until=When.SONT)
    c.phasing(until=When.SONT, on=c.me)


@power(
    "p1766",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(STR, vs=REF, plus=2),
    trigger="an enemy hits you with a melee attack",
    on=Trigger(Hit, both(hits_me, by_melee), "an enemy hits you with a melee attack"),
)
def p1766(c: Cast) -> None:
    c.strike() and c.damage("1d6", c.str_mod, dtype=DamageType.FIRE)


@power(
    "p1770",
    level=0,
    cls="r33",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p1770(c: Cast) -> None:
    """Three clauses scoped to the one move, the way `c.jump` scopes its
    two: `c.phasing` is "move through enemy spaces", and the squeezing
    penalty is exactly `conditions.RULES[Condition.SQUEEZING]`, so
    suppressing the condition is the whole of "no penalties for squeezing".

    Taking no damage from the surface crossed is a property of terrain the
    board does not deal out, so there is nothing to suppress."""
    held = (
        c.phasing(until=When.EOT, on=c.me),
        c.ignores_difficult(on=c.me, until=When.EOT),
        c.ignore_condition(Condition.SQUEEZING, on=c.me, until=When.EOT),
    )
    try:
        # Read rather than written in, so `f786` can lengthen it. #502.
        c.shift(c.squares_for(c.ref, c.speed_of()))
    finally:
        for one in held:
            if one is not None:
                c.end_effect(one, why=f"{c.ref}: the movement ended")


# -- the movement and teleport rows ------------------------------------------


@power(
    "p1449",
    level=0,
    cls="r3",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def p1449(c: Cast) -> None:
    c.teleport(5)


@power(
    "p1489",
    level=0,
    cls="r21",
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy misses you with a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses you with a melee attack"),
)
def p1489(c: Cast) -> None:
    """`c.squares_for` rather than a bare 1, so a feat lengthening this
    shift reaches it. Three feats print "you shift 1 extra square when you
    use <this row>" and `c.extend_move(ref, n)` is how they say it -- but
    the read has to be *here*, in the row being lengthened, or the entry
    is laid and nothing consults it. Found by an agent that could not
    write those three and looked at why."""
    c.shift(c.squares_for(c.ref, 1))


@power(
    "p14388",
    level=6,
    cls="r6",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Melee(1),
    target=Target("other", 1),
)
def p14388(c: Cast) -> None:
    """The advantage is read off the board *after* the swap, so the loop
    runs on the squares the two creatures have already exchanged."""
    foe = c.target
    if foe is None:
        return
    c.swap(foe)
    for other in c.enemies():
        if c.adjacent(other):
            c.grants_advantage(on=other, to=c.me, until=When.EONT)


@power(
    "p16033",
    level=2,
    cls="r16",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p16033(c: Cast) -> None:
    """`c.hover` lifts, keeps the creature airborne past the end of the
    move and lands it without falling damage. The one square of horizontal
    drift is `across=` now (#778), and it is one move action rather than a
    lift and a walk, which is why it belongs to the verb instead of a
    `c.slide` line here: the slide has to happen with the creature already
    marked as hovering or it moves something that is still on the floor.

    The printed altitude limit of 4 needs nothing: 4 is the whole lift, so
    the cap and the distance are the same number and nothing in this row can
    exceed it. A row that pushed the creature higher would be the one to ask,
    and none does.
    """
    c.hover(4, across=1, on=c.me, until=When.EONT)


@power(
    "p2474",
    level=0,
    cls="r17",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def p2474(c: Cast) -> None:
    """"You or one ally" is the ally pool, which includes the caster."""
    c.mode("fly", 5, on=c.target, until=When.EOT)
    c.move(5, who=c.target)


@power(
    "p15839",
    level=10,
    cls="r61",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=Target("other_ally", 99, everyone=True),
)
def p15839(c: Cast) -> None:
    c.mode("fly", 6, on=c.target, until=When.EOTNT)


@power(
    "p16467",
    level=10,
    cls="r23",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p16467(c: Cast) -> None:
    """The Special is a recharge with a condition, and `c.restore_use`
    is the verb for it. Arming the watch here rather than at the start of
    the fight is harmless: there is nothing to hand back unless it ran."""
    c.shift(1)
    ref = c.ref

    def again(ev: Any) -> None:
        if ev.actor == c.me:
            c.restore_use(ref, on=c.me)

    c.watch(Bloodied, again, until=When.ENCOUNTER, once=True)


@power(
    "p16545",
    level=6,
    cls="r43",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    requires=_beside_ally,
    requires_text="must be adjacent to an ally",
    dropped=("c.stealth_speed()",),
)
def p16545(c: Cast) -> None:
    """Hiding is only offered if the shift ended beside somebody, which is
    the printed condition rather than the entry requirement."""
    c.shift(c.speed_of())
    if _beside(c) is not None:
        c.hide()


# -- answering an attack ------------------------------------------------------


@power(
    "p16461",
    level=6,
    cls="r21",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you while you are adjacent to an ally",
    on=Trigger(Hit, hits_me, "an enemy hits you"),
)
def p16461(c: Cast) -> None:
    """The ally is chosen before the shift: stepping away first would put
    the only legal recipient out of reach of the printed sentence."""
    mate = _beside(c)
    c.shift(1)
    if mate is not None:
        c.redirect(to=mate)


@power(
    "p16635",
    level=6,
    cls="r22",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy's attack pushes, pulls, or slides you",
    on=Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"),
)
def p16635(c: Cast) -> None:
    ev = c.trigger
    c.cancel()
    if ev is not None and ev.source:
        c.grants_advantage(on=ev.source, to=c.me, until=When.EONT)


@power(
    "p14384",
    level=6,
    cls="r2",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="you are pulled, pushed, or slid",
    on=Trigger(ForcedMove, targets_me, "you are pulled, pushed or slid"),
)
def p14384(c: Cast) -> None:
    """`ForcedMove` carries the count, which is the whole of the bonus.
    A reaction resolves before the shove, so the number is read off the
    declaration rather than measured afterwards."""
    ev = c.trigger
    squares = max(1, ev.squares if ev is not None else 1)
    c.bonus("damage", squares, kind="power", until=When.EONT, on=c.me)


@power(
    "p377",
    level=0,
    cls="r20",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger="you take damage",
    on=Trigger(DamageRolled, targets_me, "you take damage"),
)
def p377(c: Cast) -> None:
    """"Until you attack" is the earlier of two clocks, not a shorter one."""
    _until_you_attack(c, c.invisible(on=c.me, until=When.EONT))
    # After, because f3168's lent clause is "also teleport 3 squares ...
    # **after** you become invisible".
    lent(c)


@power(
    "p7442",
    level=0,
    cls="r44",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="a bloodied enemy attacks you or your adjacent ally",
    on=Trigger(
        AttackDeclared,
        _bloodied_foe_attacks_us,
        "a bloodied enemy attacks you or an adjacent ally",
    ),
)
def p7442(c: Cast) -> None:
    """"Or charge it" is the same blow reached differently, so the run is
    taken only when the enemy is out of reach and the basic attack is the
    one thing that lands either way."""
    ev = c.trigger
    foe = ev.attacker if ev is not None else None
    if foe is None:
        return
    if not c.adjacent(foe):
        c.charge_at(foe)
    if c.basic(on=foe):
        c.dazed(on=foe, until=When.EONT)


@power(
    "p7548",
    level=0,
    cls="r46",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=Target("ally", 99, everyone=True),
    trigger="an enemy hits or misses you with an attack against your Will",
    on=(
        Trigger(Hit, targets_me, "an enemy hits you"),
        Trigger(Miss, targets_me, "an enemy misses you"),
    ),
)
def p7548(c: Cast) -> None:
    """Neither `Hit` nor `Miss` records which defence was rolled against,
    so the row answers any attack aimed at the caster."""
    c.bonus(WILL, 4, kind="power", until=When.EONT)


@power(
    "p16464",
    level=2,
    cls="r23",
    usage=DAILY,
    action=MOVE,
    reach=CloseBurst(2),
    target=Target("ally", 99, everyone=True),
)
def p16464(c: Cast) -> None:
    """The caster is in the ally pool so that the shift still happens on a
    board with nobody else in the burst; the bonus itself skips them,
    because the printed line gives it to allies only."""
    if c.target != c.me:
        for defence in (AC, FORT, REF, WILL):
            c.bonus(
                defence, 2, kind="power", until=When.EONT,
                when=lambda ctx: bool(ctx["opportunity"]),
            )
    if c.last:
        c.shift(c.speed_of())


# -- standing modifiers and stances -------------------------------------------


@power(
    "p14392",
    level=6,
    cls="r5",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
    requires=_bloodied,
    requires_text="must be bloodied",
)
def p14392(c: Cast) -> None:
    """"While you are bloodied" is a gate, not a duration. Written as one
    it also survives being healed and bloodied again, which a clock that
    expired on the first `Healed` would not -- and the closure reads the
    board rather than a context key, so it is not silently false in the
    thin damage context."""
    world, me = c.world, c.me

    def still(_ctx: dict[str, Any]) -> bool:
        return _bloodied(world, me)

    c.stance(on=me, label=c.ref)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, kind="power", until=When.STANCE, on=me, when=still)
    c.bonus("skill:stealth", 2, kind="power", until=When.STANCE, on=me, when=still)


@power(
    "p2484",
    level=0,
    cls="r30",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_bloodied,
    requires_text="must be bloodied",
)
def p2484(c: Cast) -> None:
    """No type word in front of either bonus, so both are untyped."""
    c.bonus("speed", 2, until=When.ENCOUNTER, on=c.me)
    c.bonus(AC, 1, until=When.ENCOUNTER, on=c.me)
    c.bonus(REF, 1, until=When.ENCOUNTER, on=c.me)


@power(
    "p6188",
    level=0,
    cls="r37",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p6188(c: Cast) -> None:
    """Resist all damage: `c.resist` with no type is exactly that."""
    c.resist(5, on=c.me, until=When.EONT)


@power(
    "p2324",
    level=0,
    cls="r10",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p2324(c: Cast) -> None:
    """The damage context asks the board for combat advantage itself, so
    the "if you have combat advantage" half is a gate rather than a drop."""
    c.bonus(
        "damage", 0, dice="1d6", until=When.EONT, on=c.me, once=True,
        when=lambda ctx: bool(ctx["advantage"]),
    )


@power(
    "p16640",
    level=6,
    cls="r38",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p16640(c: Cast) -> None:
    """Adjacency is asked of the board from inside the gate: the damage
    context carries the victim's id and nothing about where it stands."""
    world, me = c.world, c.me

    def close_melee(ctx: dict[str, Any]) -> bool:
        victim = ctx["target"]
        if ctx["ranged"] or victim is None:
            return False
        return distance_between(world, me, victim) <= 1

    c.bonus("damage", 0, dice="1d6", until=When.ENCOUNTER, on=c.me, when=close_melee)


@power(
    "p16383",
    level=2,
    cls="r36",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy adjacent to you shifts",
    on=Trigger(
        MoveStart,
        both(enemy_within(1), _shifting),
        "an adjacent enemy shifts",
    ),
)
def p16383(c: Cast) -> None:
    """`MoveStart`, not `MoveEnd`: by the time the shift has landed the
    enemy is no longer adjacent, which is precisely when this should fire."""
    ev = c.trigger
    foe = ev.actor if ev is not None else None
    c.shift(1)
    if foe is not None:
        c.bonus(
            "attack", 2, kind="power", until=When.EONT, on=c.me,
            when=lambda ctx: ctx["target"] == foe,
        )


@power(
    "p16687",
    level=2,
    cls="r36",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    narrative=("skill:acrobatics", "skill:athletics"),
)
def p16687(c: Cast) -> None:
    """The terrain half is ordinary and plays. The other half swaps
    athletics in for the acrobatics a movement would call for -- but
    movement here costs squares and calls for no check at all, so there is
    nothing to substitute and no mechanism missing."""
    c.ignores_difficult(on=c.me, until=When.EOT)


@power(
    "p16548",
    level=2,
    cls="r51",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CHARM],
    narrative=("skill:nature",),
)
def p16548(c: Cast) -> None:
    """One `once=True` bonus per named skill: whichever check is made
    first spends its own, which is as near as the keys get to "the next
    check". The fourth clause is a nature check on a beast, to calm or
    sway it -- neither is a thing a board does to a creature, so it is
    narrative and not a bonus waiting on a verb."""
    for skill in ("bluff", "diplomacy", "intimidate"):
        c.bonus(
            f"skill:{skill}", 5, kind="power",
            until=When.EONT, on=c.me, once=True,
        )


# -- zones, forms and the rest ------------------------------------------------


@power(
    "p14017",
    level=6,
    cls="r52",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.SHADOW, Keyword.ZONE],
    )
def p14017(c: Cast) -> None:
    """A zone of dim light, which is the whole of it."""
    c.zone(c.area(), until=When.EONT, obscured="dim")


@power(
    "p16470",
    level=2,
    cls="r66",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
)
def p16470(c: Cast) -> None:
    """"The outermost squares" is the ring at the burst's full radius, not
    the whole burst.

    "For creatures that lack earth walk" is the `difficult=` label rather
    than a side: `rt:r66-t0` is three `c.ignores_difficult` calls,
    one of which is "rubble", and `Grid.rough` skips a square whose kind
    the mover ignores. So naming the going is what exempts them, and it
    exempts every other earth walker on the board too."""
    here = c.here
    ring = [sq for sq in c.area() if distance(sq, here) == 2]
    c.zone(ring, difficult="rubble", until=When.ENCOUNTER)


@power(
    "p16473",
    level=6,
    cls="r66",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def p16473(c: Cast) -> None:
    _until_you_attack(c, c.invisible(on=c.me, until=When.EONT))


@power(
    "p16476",
    level=10,
    cls="r66",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ELEMENTAL, Keyword.SUMMONING],
)
def p16476(c: Cast) -> None:
    """**It has a row now** (#459), so this is `c.summon` and the numbers are
    its own: tiny, speed 5, hit points equal to the summoner's bloodied
    value, and defences at the summoner's **minus 2** -- which the page
    prints and `Summon`'s defaults silently improved on.

    "It lacks actions of its own" is what a summon already is: spawned as
    a `Companion`, it takes no turn and acts when its summoner spends an
    action on it. The lost surge when it drops is a clause about a
    creature that is gone and nothing watches a summon's own `Dropped`.

    **The `defect=` is gone, and it had been refusing this written row.**
    It said the card defers its statistics and the entry prints no block,
    which was true when it was written and stopped being true at #459:
    `x10_93` is a full block -- tiny, elemental, speed 5, hit points equal
    to the summoner's bloodied value, defences at the summoner's -2. It
    lives in the `associate` table rather than `monster`, which is why a
    check that looked only at `monster` kept reporting the gap, and the
    extractor had already substituted the ref into this card's own spec
    text. The 13 siblings carrying the same reason still print prose with
    no ref, so theirs holds. #766.
    """
    c.summon("x10_93", at=c.origin)


@power(
    "p14022",
    level=6,
    cls="r53",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH, Keyword.SHADOW],
    )
def p14022(c: Cast) -> None:
    """A polymorph, not a stance: you are in the form and may step out of
    it for a minor, which is what `revert` means. The darkvision belongs to
    the form and ends with it."""
    c.form(until=When.ENCOUNTER, revert=MINOR, label=c.ref)
    c.darkvision(until=When.ENCOUNTER)
    c.cannot_attack(on=c.me, until=When.ENCOUNTER)
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)
    for skill in ("athletics", "perception", "stealth"):
        c.bonus(f"skill:{skill}", 5, kind="power", until=When.ENCOUNTER, on=c.me)


@power(
    "p14033",
    level=0,
    cls="r53",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you kill or bloody an enemy",
    on=(
        Trigger(Dropped, _my_kill, "you drop an enemy"),
        Trigger(Bloodied, _my_bloodying, "you bloody an enemy"),
    ),
)
def p14033(c: Cast) -> None:
    pick = c.choose(["shift", "temporary hit points", "attack bonus"], "which benefit")
    if pick == "shift":
        c.shift(c.speed_of())
    elif pick == "temporary hit points":
        c.temp_hp(5 + c.level // 2, on=c.me)
    else:
        c.bonus("attack", 2, kind="power", until=When.EONT, on=c.me)


@power(
    "p14396",
    level=6,
    cls="r7",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p14396(c: Cast) -> None:
    """An extra action in the turn's budget, not a second turn."""
    c.extra_action(ActionType.MOVE, on=c.me)


@power(
    "p11739",
    level=0,
    cls="r51",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=UpTo(3),
    attack=Attack((STR, DEX, WIS), vs=AC, plus=3),
)
def p11739(c: Cast) -> None:
    """"A bonus to the damage roll equal to the number of targets" is read
    off `c.targets`, which is the whole list rather than this one."""
    if c.strike():
        c.damage("1d8", c.str_mod + len(c.targets))


@power(
    "p2481",
    level=0,
    cls="r25",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def p2481(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        if c.may("spend a healing surge"):
            c.surge(on=c.me)


@power(
    "p16387",
    level=2,
    cls="r8",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
)
def p16387(c: Cast) -> None:
    """An opposed check is a check against the other side's passive score,
    which is what `c.passive` is for."""
    foe = c.target
    if foe is None:
        return
    if c.check("bluff", c.passive("insight", of=foe)):
        c.push(1, on=foe)
        c.no_provoke(on=c.me, from_=foe, until=When.SONT)


@power(
    "p16658",
    level=2,
    cls="r69",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make an Arcana, Dungeoneering, or Thievery check",
    on=Trigger(
        SkillCheck,
        my_check("arcana", "dungeoneering", "thievery"),
        "you make one of three checks",
    ),
)
def p16658(c: Cast) -> None:
    """"Take either result" is the better of the two in every play."""
    c.reroll_check(keep="best")


@power(
    "p15844",
    level=6,
    cls="r62",
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=Target("any", 1),
    trigger="a creature within 10 squares regains hit points or is damaged",
    on=(
        Trigger(Healed, _subject_within(10), "a creature nearby is healed"),
        Trigger(DamageApplied, _subject_within(10), "a creature nearby is damaged"),
    ),
    dropped=("DamageApplied.from_attack",),
)
def p15844(c: Cast) -> None:
    """Which half pays out is decided by which event was answered, so the
    body reads the trigger rather than asking the board anything.

    `DamageApplied`, not `DamageRolled`: the printed trigger is damage that
    landed, and a blow a resistance ate whole is not it. Neither event
    records whether an attack was behind the blow -- `from_attack` is an
    argument to `resolve.deal_damage` and reaches nothing -- so the
    ongoing-damage case fires this too."""
    ev = c.trigger
    who = ev.target if ev is not None else c.target
    if who is None:
        return
    if isinstance(ev, Healed):
        c.heal(c.roll("2d6"), on=who)
    else:
        c.damage("2d6", on=who)


@power(
    "p15831",
    level=6,
    cls="r60",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    dropped=("query.wooden_scenery()", "c.reappear(at=)"),
)
def p15831(c: Cast) -> None:
    """Coming back in the square you left is what `Condition.REMOVED`
    already does; the alternative destination twenty squares off, and the
    wooden object the Requirement names, have nothing to read."""
    c.surge(on=c.me)
    c.condition(Condition.REMOVED, until=When.SONT, on=c.me)


@power(
    "p16655",
    level=0,
    cls="r68",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POISON],
)
def p16655(c: Cast) -> None:
    """The printed target is one of five weapon groups, or an arrow or a
    bolt; `c.apply_poison(groups=)` coats one of them and the poison rides
    only blows made with it. Ammunition is not modelled and the card's
    other answer is a weapon, so nothing of the sentence is lost.

    `escalate` is the first-failed-save line, which is one effect with two
    faces rather than two effects."""

    def bite(ev: Any) -> None:
        victim = ev.target
        c.flat(c.roll("1d6"), dtype=DamageType.POISON, on=victim)

        def worse(eff: Effect) -> None:
            c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=eff.owner)

        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=worse)

    c.apply_poison(
        bite,
        groups=("axe", "heavy blade", "light blade", "pick", "spear"),
    )


@power(
    "p16036",
    level=10,
    cls="r16",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
)
def p16036(c: Cast) -> None:
    """The targets are not creatures, so the attack line is rolled by hand
    against whoever made each one. `c.dispel` is the verb that also unwinds
    the holds a zone laid, which is the "including those a save can end"
    clause."""
    area = c.area()
    bonus = max(c.int_mod, c.cha_mod) + c.level // 2 + 4
    for eid, zone in list(c.world.each(Zone)):
        if not (zone.squares & area) or not zone.owner:
            continue
        if c.attack(bonus, vs=WILL, on=zone.owner):
            c.dispel(eid)
    for thing in c.conjurations():
        spot = c.world.get(thing, Position)
        if spot is None or spot.square not in area:
            continue
        maker = c.made_by(thing)
        if maker and c.attack(bonus, vs=WILL, on=maker):
            c.dispel(thing)


def _my_charge_starts(world: Any, me: int, ev: MoveStart) -> bool:
    """`MoveStart.kind_` is a declared field and `actions` passes
    `kind="charge"` for a charge's run, so "you charge" is askable here."""
    return ev.actor == me and ev.kind_ == "charge"


@power(
    "p16379",
    level=6,
    cls="r1",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you charge an enemy",
    on=Trigger(MoveStart, _my_charge_starts, "you charge an enemy"),
)
def p16379(c: Cast) -> None:
    """`MoveStart` is the only window early enough to cover the charge's own
    run, and it does record that the run is a charge -- the old marker
    (`MoveStart.charge`) named a field that is spelled `kind_` and is set on
    every emission, which is the trap `AUTHORING.md` describes: reading the
    dataclass for `charge` finds nothing and the row looks blocked. Without
    the narrowing this fired on any move the creature started."""
    c.no_provoke(on=c.me, until=When.EOT)


# -- the rows that are waiting on something -----------------------------------


@power(
    "p13213",
    level=0,
    cls="r7",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss with an attack or fail a saving throw",
    on=(
        Trigger(Miss, by_me, "you miss with an attack"),
        Trigger(SavingThrow, _failed_save, "you fail a saving throw"),
    ),
)
def p13213(c: Cast) -> None:
    """"You gain a +4 racial bonus to the attack roll or the saving throw."

    **Written.** Both halves are one call: `c.boost_roll` routes on the
    event that fired, and this row declares both triggers already -- a
    `Miss` and a failed `SavingThrow` -- so the unnamed kind answers
    whichever arrived.

    A reroll is the wrong half of the pair and the old note said so: it
    would turn a near miss into a fresh die, where the card adds to the one
    on the table.
    """
    c.boost_roll(4)


@power(
    "p16040",
    level=10,
    cls="r3",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you save against a dazing or stunning effect",
    on=Trigger(SavingThrow, _saved_a_hold, "you save against a daze or a stun"),
)
def p16040(c: Cast) -> None:
    """**Written: the effect is still standing when the save is announced.**

    `SavingThrow` is announced *before* it is acted on -- its own docstring
    says exactly that -- so the hold it names is still on the saver while
    this row runs and `str(eff) == ev.against` finds it over
    `world.effects.of`. The old marker wanted one field for three
    questions, and the effect answers all three without it: "was it a daze
    or a stun" is `eff.conditions`, "who laid it" is `eff.source`, and
    "lay it on them instead" is `c.condition`.

    Re-laid as the conditions it carries rather than by moving the effect:
    the printed duration here is the end of *your* next turn, not whatever
    the original ran on, so a fresh hold is the faithful reading."""
    held = _the_hold(c.world, c.me, getattr(c.trigger, "against", ""))
    if held is None:
        return
    foe = getattr(held, "source", None)
    if foe is None or foe == c.me:
        return
    c.condition(*held.conditions, until=When.EONT, on=foe)


@power(
    "p16044",
    level=10,
    cls="r4",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use p1450 to reroll an attack and dislike the result",
    on=Trigger(Rerolled, rerolled_by("p1450", roll="attack"),
               "p1450 has rerolled your attack"),
)
def p16044(c: Cast) -> None:
    """Roll it a third time with a +2 power bonus, and keep that.

    **The trigger moved off `PowerUsed`, which was the fault.** That event
    fires *above* the body of the row doing the rolling, so this row was
    offered before `p1450` had rerolled anything -- there was no second
    result to dislike, which is what its old docstring said. `Rerolled`
    fires after, with the new face and the live result on it. #496.

    `keep="new"` is the printed "use this result, even if it's lower", and
    `bonus=2` is one clause with the reroll rather than a `c.bonus` laid
    afterwards, which the next roll would read instead of this one.
    """
    c.reroll_attack(keep="new", bonus=2)


def _under_a_save(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """"You start your turn subject to an effect that a save can end."

    `about_me` is only the first half of that sentence. The second is a
    question about what is standing on the creature, which nothing in
    `triggers` asks, and without it the power is offered every turn and
    spends itself ending nothing.
    """
    from combat_engine.engine.durations import When as _When

    return ev.actor == me and any(
        eff.when is _When.SAVE_ENDS for eff in world.effects.of(me)
    )


@power(
    "p2478",
    level=0,
    cls="r22",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you start your turn subject to an effect a save can end",
    on=Trigger(TurnStart, _under_a_save, "you start your turn under one"),
)
def p2478(c: Cast) -> None:
    """Ending a save-ends effect outright is not rolling a saving throw:
    it cannot fail, so `c.save` is the wrong verb for it.

    The printed Trigger is two clauses -- the turn starting *and* being
    subject to such an effect -- and declaring only the first would offer
    the power on every turn of the fight and spend it on nothing."""
    c.end_effect(on=c.me, save_ends=True)


@power(
    "p16551",
    level=10,
    cls="r51",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    )
def p16551(c: Cast) -> None:
    """Blindsight 10, until the end of your next turn. Not truesight: one
    ignores concealment within its radius, the other pierces invisibility,
    and the row wants the first."""
    c.blindsight(10, until=When.EONT)


# -- deliberately inert: the printed effect is not a combat effect ------------


@power(
    "p15836",
    level=0,
    cls="r61",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    out_of_combat=True,
)
def p15836(c: Cast) -> None:
    """Shrinking a door or a table so it can be carried. The target is an
    object, the duration is an extended rest and nothing about it is
    measured in a fight."""


@power(
    "p16458",
    level=2,
    cls="r21",
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    out_of_combat=True,
)
def p16458(c: Cast) -> None:
    """A Thievery check to pick a pocket: the whole printed Effect."""


@power(
    "p16542",
    level=2,
    cls="r43",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW],
    out_of_combat=True,
)
def p16542(c: Cast) -> None:
    """An hour-long disguise and a bonus to the Bluff check that sells it.
    No mechanical hold, no duration a fight would ever see out."""
