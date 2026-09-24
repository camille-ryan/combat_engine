"""Monster abilities, level 9: the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=14)` and `Damage("2d6", 5)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the eight levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block printing no range at all means melee 1; and a helper written for an
earlier level is imported rather than copied.

Five things this file had to settle.

**Two bonuses of the same kind do not add.** "+2 to AC and Reflex with one
creature adjacent, or +4 with two or more" is a +2 and a gated **+4**, not a
+2 and a second +2: `Mods.total` takes the larger of two bonuses sharing a
kind, which is the printed stacking rule, and the additive reading comes to
+2 forever while looking exactly like a working trait.

**A shape that cannot act.** `Condition.STUNNED` would be the obvious way to
write "cannot take actions except to end the effect", and it is the wrong
one: `actions.legal` returns nothing but "end turn" for a creature that
cannot act, so the printed way *out* of the shape would be unreachable and
the creature would sit in it for the rest of the fight. Its attacks are
taken away instead -- `c.forbid` for the rows and `c.no_basic` for what a
granted swing reaches for -- and given back when the shape ends.

**"Deals only half damage with its attacks"** is `Condition.WEAKENED`
exactly: `query.deals_half` reads that condition and nothing else. So the
insubstantial form carries both conditions rather than inventing a second
halving that the first would then apply twice.

**"Flies up to its fly speed and attacks"** is `c.run_at` plus a loan.
`c.run_at` measures `query.speed`, which is the ground speed, so a printed
fly speed came up short by the difference every time. The difference is lent
as a speed modifier for the length of the move rather than the pathfinder
being copied a fourth time.

**"Deals an extra 2d6 against a target it has combat advantage against"** is
`c.had_advantage(ev)`, read off the `Hit`. Asking `has_combat_advantage`
again is too late: a one-shot grant has already been spent by then, so the
rider would have been silently missing on exactly the attacks it is for.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_05.skirmishers import _fly_speed
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
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
    WILL,
    ActionType,
    Attack,
    Cast,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Usage,
    When,
    World,
    power,
    use,
)
from combat_engine.engine.events import AdjacencyGained, DamageApplied, Hit, TurnStart
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import enemies, is_, team
from combat_engine.engine.triggers import Trigger, closed_on_me, targets_me

#: The rows the m173's shell takes away while it is worn, and the label the
#: shell is held under. Both are read by the row that lays it and by nothing
#: else, but the pair belongs together at the top.
_M173_SHELL = "m173a2 shell"
_M173_ATTACKS = ("m173a0", "m173a1")

#: The label the m428's insubstantial form is held under. The row that turns
#: invisible is printed as usable only while it is worn, which is a
#: Requirement and has to be answered from `(world, eid)`.
_M428_MIST = "m428a4 mist"

#: The rows the m419 borrows while it is wearing another shape.
_M419_BORROWED = ("m122a0", "m122a1")
_M419_SHAPE = "m419a2 shape"


def _wearing(label: str):  # noqa: ANN202
    """A printed Requirement naming a shape the creature may be in."""

    def gate(world: World, eid: int) -> bool:
        return any(eff.label == label for eff in world.effects.of(eid))

    return gate


def _fly_at(c: Cast, victim: int) -> bool:
    """Close on that creature at the fly speed rather than at the walk.

    `c.run_at` is the move half of a charge and measures `query.speed`, which
    is the ground speed and nothing else -- so a printed "flies up to its fly
    speed" came up short by the difference. The difference is lent as a speed
    modifier for the length of the move and taken back afterwards, rather
    than the pathfinder being copied a fourth time.
    """
    extra = max(0, _fly_speed(c) - c.speed_of())
    lent = (
        c.bonus("speed", extra, until=When.EOT, on=c.me, kind="untyped")
        if extra
        else None
    )
    try:
        return c.run_at(victim)
    finally:
        if lent is not None:
            c.world.effects.end(lent, "it landed")


def _nearest_foe(c: Cast) -> int | None:
    """Whoever this creature would go for, when the row picks rather than the
    dispatcher. Ties break on the id, so a replay of the same seed goes for
    the same creature."""
    foes = sorted(c.enemies())
    return min(foes, key=lambda f: (c.distance(f), f)) if foes else None


# ==========================================================================
# m173
# ==========================================================================


@power(
    "m173a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m173a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m173a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m173a1(c: Cast) -> None:
    """The waiver goes up before the move rather than after it, because an
    opportunity window opens while the creature is still in the square it is
    leaving. It runs to the end of the turn, which is the whole of the
    printed movement.

    The blow is the row that prints it, used rather than copied.
    """
    victim = c.target or _nearest_foe(c)
    if victim is None:
        return
    waiver = c.no_provoke(until=When.EOT)
    try:
        _fly_at(c, victim)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "it has landed")
    if c.adjacent(victim):
        use(c.world, c.me, "m173a0", targets=[victim], spend=False)


@power(
    "m173a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m173a2(c: Cast) -> None:
    """The shell: resistance, a trickle of temporary hit points, and no way
    to hurt anybody until it opens up again.

    "Resist 25 to all damage" is `c.resist` with no type named, which is the
    mirror of `c.vulnerable` and the reason a row like this could not be
    written a level ago.

    "Cannot take actions except to end the effect" is its attacks taken away
    rather than `Condition.STUNNED`: a creature that cannot act is offered
    nothing at all by `actions.legal`, including the drop that is the printed
    way out. `c.no_basic` goes with the forbidding, because what a charge and
    an opportunity attack reach for is the designation rather than the row.

    Tremorsense is a sense, and the engine holds none, so it is noted.
    """
    me = c.me
    shell = c.form(until=When.ENCOUNTER, revert=MINOR, label=_M173_SHELL)

    def undo(hold: Effect | None) -> None:
        if hold is not None:
            shell.on_end.append(lambda: c.world.effects.end(hold, "it opened up"))

    undo(c.resist(25, until=When.ENCOUNTER, on=me))
    undo(c.no_basic(until=When.ENCOUNTER, on=me))
    for ref in _M173_ATTACKS:
        undo(c.forbid(ref, on=me, until=When.ENCOUNTER))

    def trickle(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me and not shell.ended:
            c.temp_hp(5, on=me)

    shell.subs.append(c.world.bus.on(TurnStart, trickle, owner=me))
    shell.on_end.append(
        lambda: c.bonus("damage", 20, until=When.EONT, on=me, once=True)
    )
    c.note("m173a2: tremorsense 10 while the shell is closed")


# ==========================================================================
# m2938
# ==========================================================================


@power(
    "m2938a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.THUNDER],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 2, dtype=DamageType.COLD),
)
def m2938a0(c: Cast) -> None:
    """"Cold and thunder damage" is one roll of two types and a header holds
    one, so the first printed type is kept and a creature resistant only to
    the other takes this in full. The approximation the level below settled
    on for the same shape."""
    if c.strike():
        c.hit()


def _hunting(world: World, hunter: int, prey: int) -> bool:
    """Relational, like a curse: another hunter's quarry is not this one's.

    Asked of the relation rather than of a label, because `c.quarry` hangs
    its effect on the **hunter** and names the prey only in the relation it
    carries -- so looking for a hold on the victim finds nothing.
    """
    return world.relations.holds(Relation.QUARRY_OF, hunter, prey)


def _has_quarry(world: World, eid: int) -> bool:
    return any(_hunting(world, eid, foe) for foe in enemies(world, eid))


@power(
    "m2938a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.THUNDER],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d12", 5, dtype=DamageType.COLD),
    requires=_has_quarry,
    requires_text="the m2938 must have a quarry",
)
def m2938a1(c: Cast) -> None:
    """The printed target is its quarry, which no `Target` can say, so the
    header takes one enemy and the body aims at whoever it is hunting.

    The quarry is released on a hit, which is what the relation carrying it
    ending means -- the hold is `c.quarry`'s and ending it is how a row says
    "no longer designated".
    """
    me = c.me
    hunted = [foe for foe in sorted(c.enemies()) if _hunting(c.world, me, foe)]
    victim = c.target if c.target in hunted else next(iter(hunted), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    for eff in list(c.world.effects.live.values()):
        if eff.source == me and (Relation.QUARRY_OF, me, victim) in eff.relations:
            c.world.effects.end(eff, "it let the quarry go")


@power(
    "m2938a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m2938a2(c: Cast) -> None:
    """The printed recharge is a sentence rather than a die, and the database
    files a 6+ as well. Both are honoured: the die in the header, because
    that is what the card shows and what `actions.recharge` rolls, and the
    sentence armed on top of it by the row itself -- so a hit landed before
    this was ever used gives nothing back.

    Naming the quarry is an Effect line, so it happens whether or not the
    shot landed.
    """
    me = c.me
    _recharge_on(
        c,
        Hit,
        lambda ev: ev.attacker == me and ev.power == "m2938a1",
    )
    if c.strike():
        c.hit()
        c.prone()
    c.quarry()


_M2938_HURT = "the m2938 takes damage"


@power(
    "m2938a3",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2938_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M2938_HURT),
)
def m2938a3(c: Cast) -> None:
    """"Moves through enemies' spaces" is the nearest thing the engine holds
    to phasing, which is what walls and bodies both come to for a creature
    that is not really there. The waiver names nobody, which is what covers
    every opening rather than one creature's."""
    c.no_provoke(until=When.EONT)
    c.phasing(until=When.EONT)


# ==========================================================================
# m419
# ==========================================================================


@power(
    "m419a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d4", 3),
)
def m419a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. Only the burn is poison."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


@power(
    "m419a1",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m419a1(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it fights better in a
    crowd.

    A +2 and a gated **+4**, not two +2s. Two bonuses of the same kind do not
    add -- the larger wins, which is the printed stacking rule -- so the
    additive reading would come to +2 whether one creature was beside it or
    four, and would read exactly like a working trait.

    Who is standing beside it changes every time anybody moves, so both are
    gated modifiers asked as the defence is looked up rather than effects put
    on and taken off.
    """
    me = c.me

    def crowded(count: int):  # noqa: ANN202
        def gate(_ctx: dict[str, Any]) -> bool:
            return len(c.within(1, of=me, side="other")) >= count

        return gate

    for defended in (AC, REF):
        c.bonus(defended, 2, until=When.ENCOUNTER, on=me, when=crowded(1))
        c.bonus(defended, 4, until=When.ENCOUNTER, on=me, when=crowded(2))


@power(
    "m419a2",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m419a2(c: Cast) -> None:
    """Wearing another creature's shape, as far as the engine can hold it.

    What it can hold is the other stat block's *rows*, which is `c.grant_row`
    -- the opposite number of `c.forbid`, and the reason this row is written
    at all rather than left out. They go when the shape goes.

    What it cannot hold is the rest: defences, speed and ability scores are
    components on the entity and there is no method that swaps one creature's
    for another's. That half is noted. See the report.

    `revert=MINOR` is the printed way back, and the shape is not a stance, so
    an earlier one is ended by hand before a new one is taken.
    """
    me = c.me
    for eff in list(c.world.effects.of(me)):
        if eff.label == _M419_SHAPE:
            c.world.effects.end(eff, "it changed shape again")
    shape = c.form(until=When.ENCOUNTER, revert=MINOR, label=_M419_SHAPE)
    for ref in _M419_BORROWED:
        borrowed = c.grant_row(ref, on=me, until=When.ENCOUNTER)
        if borrowed is not None:
            shape.on_end.append(
                lambda g=borrowed: c.world.effects.end(g, "it changed back")
            )
    c.note("m419a2: it keeps its own hit points and borrows the m122's rows")


# ==========================================================================
# m428
# ==========================================================================


@power(
    "m428a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m428a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


_M428_CLOSED = "an enemy moves or shifts into a square adjacent to the m428"


def _enemy_closed_on_me(world: World, me: int, ev: AdjacencyGained) -> bool:
    """`closed_on_me` reads `mover`, which is what tells "an enemy moves
    adjacent to it" from the m428 closing the gap itself -- the event is
    emitted mirrored, so without it the trigger was true half the time for
    the wrong reason. The side is asked here because the predicate does not.
    """
    if not closed_on_me(world, me, ev):
        return False
    return team(world, ev.mover) is not team(world, me)


@power(
    "m428a1",
    level=9,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 2),
    trigger=_M428_CLOSED,
    on=Trigger(AdjacencyGained, when=_enemy_closed_on_me, text=_M428_CLOSED),
)
def m428a1(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the dispatcher only
    points a row that takes one enemy, and `AdjacencyGained` names the mover
    rather than an attacker."""
    who = getattr(c.trigger, "mover", None)
    if who and c.strike(on=who):
        c.hit(on=who)


@power(
    "m428a2",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m428a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Read off the `Hit` rather than asked of the board again: a one-shot grant
    of combat advantage has already been spent by the time the blow is
    announced, so asking a second time comes back false on exactly the
    attacks this rider is for.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.had_advantage(ev):
            c.damage("2d6", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m428a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    requires=_wearing(_M428_MIST),
    requires_text="the m428 must be insubstantial",
)
def m428a3(c: Cast) -> None:
    """`c.hide` rather than `c.invisible`: the printed duration is not a
    clock but "until it makes an attack", and `resolve.attack` breaks the
    relation for whoever swung -- which is exactly that sentence.

    Ending it early is printed as a free action and there is nothing to spend
    one on: what ends it is attacking, which the creature does anyway.
    """
    c.hide(until=When.ENCOUNTER)


@power(
    "m428a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m428a4(c: Cast) -> None:
    """Both halves are conditions the engine already holds:
    `Condition.INSUBSTANTIAL` halves what reaches it and `Condition.WEAKENED`
    is what `query.deals_half` reads, so "deals only half damage with its
    attacks" is that condition and not a second halving laid beside it.

    `revert=FREE` is the printed way out. The Stealth bonus is a skill and
    the engine rolls none, so it is noted.
    """
    me = c.me
    if is_(c.world, me, Condition.INSUBSTANTIAL) and any(
        eff.label == _M428_MIST for eff in c.world.effects.of(me)
    ):
        return
    c.form(
        conditions=(Condition.INSUBSTANTIAL, Condition.WEAKENED),
        until=When.ENCOUNTER,
        revert=FREE,
        label=_M428_MIST,
    )
    c.note("m428a4: +5 to Stealth while it is mist")
