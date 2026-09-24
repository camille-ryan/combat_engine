"""Monster abilities, level 9: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=14)` and `Damage("2d6", 7)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the eight levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits or triggered actions and are written as such; a stat block
that prints no range at all means melee 1; and a row that moves and swings
takes the swing first, because the movement picks its own destination and one
taken first can leave the target out of reach.

Five things this level needed that the levels below did not.

**A hit turned into a miss from inside the hit.** m147a0 refuses every blow
whose die came up odd. `resolve.attack` re-reads `result.hit` in the resolve
callback of the `Hit` -- that is what `c.reroll_attack` leans on -- so a
`Window.BEFORE` listener that clears the flag gets a real `Miss` emitted in
the `Hit`'s place, riders and all. Cancelling the `Hit` by hand would have
stopped the announcement and left the result saying it landed.

**Its own approach, told from the enemy's.** m3072a1 swings at everything it
moves next to during a shift, which is `AdjacencyGained` read the other way
round from the usual: `mover` has to be the creature itself. The event is
emitted mirrored, so the pair is filtered on `actor` as well, or every
neighbour is counted twice.

**Threat at two squares.** `movement.step` opens an opportunity window for
whoever the mover was standing next to, and the one square is written into
it. m147a1 therefore watches `Moved` and opens the second ring itself with
`c.provoke`, gated on the enemy having been *exactly* two squares off -- at
one the engine has already opened one and two windows would be two swings.

**A vulnerability that moves.** m3072a3 holds its six damage types as one
`c.vulnerable` and five `c.resist`, and swaps two of them whenever the soft
one is struck. `c.resist` is the mirror of `c.vulnerable`; before it existed
this had to be written as a negative vulnerability.

**Underground is how it is moving.** The engine has no depth, and
`movement.mode_of` has it that a creature which can burrow does, every time
it moves. So "the m104 must be underground" is `moving_as("burrow")`, and
m104a3 -- whose whole content is coming up -- clears the flag by hand when it
surfaces. There is nothing else that could mean it.

The helpers that recharge on a printed sentence, that move without provoking,
that pay out for having covered ground, that hide behind whatever cover there
is, and that read the range off the row behind an event were written for
levels 2 to 8 and are imported rather than copied.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_02.skirmishers import _conceal, _shed
from combat_engine.content.monsters.level_03.skirmishers import _recharge_on
from combat_engine.content.monsters.level_04.skirmishers import _guarded_move
from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_06.skirmishers import _after_moving
from combat_engine.content.monsters.level_07.controllers import _vanish
from combat_engine.content.monsters.level_07.skirmishers import _hurt_by_an_attack
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    Movement,
    Position,
    Powers,
    Ranged,
    Relation,
    Size,
    Square,
    UpTo,
    Usage,
    When,
    Window,
    World,
    distance,
    footprint,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    Bloodied,
    DamageApplied,
    EnterSquare,
    MoveStart,
    RoundStart,
    TurnEnd,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    cover_between,
    creatures,
    distance_between,
    flanked_by,
    is_,
    moving_as,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, both, by_melee, targets_me

#: Sizes a printed "Large or bigger" covers.
_BIG = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)

#: What "a melee or a ranged attack" means as a range kind. A close burst is
#: neither, and `by_melee` counts one as melee -- which is right for the
#: rows it was written for and wrong for m147a0.
_WEAPON_RANGES = ("melee", "ranged")


def _holding_label(c: Cast, label: str) -> bool:
    """Is the caster already carrying a hold under this exact label?

    A once-per-use latch for a row whose body runs once per target: `c.first`
    answers "is this the first target", which is a different question when
    the clause is "on a hit" and the first target was missed.
    """
    return any(e.label == label for e in c.world.effects.of(c.me))


def _bit_an_enemy(world: World, me: int, ev: DamageApplied, *, felled: bool = True) -> bool:
    """Did this creature just bloody an enemy, or put one down?

    On `DamageApplied`, not on `Bloodied` or `Dropped`: both of those name
    the **victim** as `actor`, so a row whose printed subject is the attacker
    cannot be hung on either. This one carries `source`, `hp` and `amount`,
    which is everything the sentence asks. Sides are compared with `team`
    rather than with `query.enemies`, which filters out the dead and is false
    exactly on the drop this is watching for.
    """

    if ev.source != me or ev.amount <= 0 or ev.target == me:
        return False
    if team(world, ev.target) is team(world, me):
        return False
    health = world.get(ev.target, Health)
    if health is None:
        return False
    half = health.max_hp // 2
    crossed = ev.hp <= half < ev.hp + ev.amount
    return crossed or (felled and ev.hp <= 0)


def _free_square_within(c: Cast, of: int, radius: int, *, mover: int | None = None) -> list[Square]:
    """Squares within `radius` of a creature that another one could stand in.

    Checked against the mover's whole footprint: `movement.step` refuses the
    arrival unless every square a Large creature covers is clear, so a list
    built from single squares offers destinations it cannot use.
    """
    who = c.me if mover is None else mover
    here = c.world.get(who, Position)
    size = here.size if here is not None else Size.MEDIUM
    return sorted(
        sq
        for sq in spread(squares(c.world, of), radius)
        if all(
            c.world.grid.passable(part) and c.world.grid.occupant(part) in (None, who)
            for part in footprint(sq, size)
        )
    )


def _at_the_off(c: Cast, fn: Callable[[], None]) -> None:
    """Run something once, when the fight is under way rather than while it
    is being set up.

    Two traits here ask whether the creature has cover, and a trait arms
    while `Encounter.start` is still walking the initiative order -- before
    anyone has taken a step. `RoundStart` is emitted after arming and before
    the first turn, which is the moment the printed "when it rolls
    initiative" names.
    """
    done: list[bool] = []

    def once(_ev: RoundStart) -> None:
        if not done:
            done.append(True)
            fn()

    c.watch(RoundStart, once, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} at the off")


# ==========================================================================
# m104
# ==========================================================================


@power(
    "m104a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m104a0(c: Cast) -> None:
    """The ground it goes into and comes out of stays broken.

    Both ends of the tunnel, which is what the printed line names: the
    square the move began in and the square it ended in, each taken as the
    creature's whole footprint because a Large creature churns four of them.
    Gated on the move having been a burrow -- `movement.mode_of` puts this
    creature underground whenever it walks, so that is nearly always, but a
    push or a teleport is not digging and does not count.
    """
    me, ref = c.me, c.ref

    def churn(_kind: str, start: Square | None, end: Square, _steps: int) -> None:
        if start is None or not moving_as(c.world, me, "burrow"):
            return
        here = c.world.get(me, Position)
        size = here.size if here is not None else Size.MEDIUM
        c.zone(
            footprint(start, size) | footprint(end, size),
            label=f"{ref} spoil",
            until=When.ENCOUNTER,
            difficult=True,
        )

    _after_moving(c, churn)


@power(
    "m104a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 7),
)
def m104a1(c: Cast) -> None:
    """"3d6 + 7, or 5d6 + 7 against a prone target" is one line with two
    totals, so the header keeps the printed base -- which is what rescales --
    and the two extra dice are rolled here."""
    if c.strike():
        c.hit()
        if c.is_(Condition.PRONE):
            c.damage("2d6")


@power(
    "m104a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m104a2(c: Cast) -> None:
    """A jump and then a bite. The printed order is named outright -- "jumps
    up to 5 squares and then uses" -- so the usual arrangement of swinging
    first is not the printed one and is not taken. The row declares no
    target: the bite picks its own from wherever it lands."""
    _guarded_move(c, 5)
    use(c.world, c.me, "m104a1", spend=False)


def _underground(world: World, eid: int) -> bool:
    """A printed Requirement of "must be underground".

    There is no depth on the board. What there is is `Movement.using`, which
    says how the creature is moving *now* and is held past the end of the
    move -- so a creature that burrowed is still down there, and one that has
    surfaced is not. It is the only thing that could mean this.
    """
    return moving_as(world, eid, "burrow")


@power(
    "m104a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 5, half_on_miss=True),
    requires=_underground,
    requires_text="the m104 must be underground",
)
def m104a3(c: Cast) -> None:
    """It comes up under the party.

    Declared with no target, because the burst is thrown from where the move
    *ends* and a header target list is chosen before the body runs -- so the
    printed order would have caught whoever was standing round the hole it
    started in. The burst is gathered by hand afterwards instead.

    Surfacing is the flag going out: `movement.mode_of` would otherwise keep
    this creature burrowing for the rest of the fight, and the Requirement
    above it would never be false again.
    """
    _guarded_move(c, c.speed_of())
    moves = c.world.get(c.me, Movement)
    if moves is not None:
        moves.using = ""
    for foe in c.within(2, side="other"):
        if c.strike(on=foe):
            c.hit(on=foe)
        else:
            c.hit(on=foe, half=True)


@power(
    "m104a4",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=12),
)
def m104a4(c: Cast) -> None:
    """It tunnels under the feet of whoever is in the way.

    The squares each enemy stands in are taken before the move and matched
    against `EnterSquare`, which is the only event that says which squares
    were passed *through* -- `MoveEnd` gives the arrival and `Moved` one
    step. A burrowing creature travels overhead as far as `movement._clear`
    is concerned, so it may cross an occupied square at all.

    One bite each, and a Large creature emits four `EnterSquare` per step, so
    the enemies already bitten are remembered rather than counted.
    """
    me = c.me
    under = {sq: foe for foe in c.enemies() for sq in squares(c.world, foe)}
    bitten: set[int] = set()

    def beneath(ev: EnterSquare) -> None:
        if ev.actor != me:
            return
        foe = under.get(ev.square)
        if foe is None or foe in bitten:
            return
        bitten.add(foe)
        if c.strike(on=foe):
            c.prone(on=foe)

    watcher = c.watch(EnterSquare, beneath, until=When.EOT, on=me, label=c.ref)
    _guarded_move(c, c.speed_of())
    c.world.effects.end(watcher, "the burrow is over")


# ==========================================================================
# m147
# ==========================================================================


#: The hold that says the trait is spent for the moment. Read by label
#: rather than kept in a closure, because the trait arms once and the lapse
#: comes and goes for the rest of the fight.
_M147_LAPSED = "m147a0 lapsed"


@power(
    "m147a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m147a0(c: Cast) -> None:
    """An odd die goes through the image; an even one finds the beast.

    The `Hit` is answered in its interrupt window and the *result* is
    cleared rather than the event cancelled: `resolve.attack` reads
    `result.hit` back in the resolve callback and emits a `Miss` in the
    `Hit`'s place when the two disagree, so every rider hung on the hit goes
    with it. Cancelling the event by hand stops the announcement and leaves
    the attack still saying it landed.

    "A melee or a ranged attack" is those two range kinds and no others --
    `by_melee` counts a close burst as melee, which is right for the rows it
    was written for and would let this trait turn aside a blast.
    """
    me, ref = c.me, c.ref

    def veil(ev: Hit) -> None:
        if ev.target != me or _reach_kind(ev) not in _WEAPON_RANGES:
            return
        result = getattr(ev, "result", None)
        if result is None or _holding_label(c, _M147_LAPSED):
            return
        if result.natural % 2:
            result.hit = False
        else:
            c.effect(_M147_LAPSED, until=When.SONT, on=me)

    c.watch(Hit, veil, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=ref)


@power(
    "m147a1",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m147a1(c: Cast) -> None:
    """It threatens the ring two squares out as well as the one beside it.

    `movement.step` writes the one square into itself -- it opens a window
    for whoever the mover was standing next to and nothing says otherwise --
    so the second ring is opened here. Only for an enemy that was **exactly**
    two squares off: at one the engine has already opened a window of its
    own, and both firing would be two swings for one step.

    Watched on `Moved`, which is the only event carrying both ends of a
    single step. That puts this window a beat after the engine's, which
    interrupts the move; the difference is one square of travel.
    """
    me, ref = c.me, c.ref

    def slipped(ev: Moved) -> None:
        if ev.actor == me or ev.actor not in c.enemies():
            return
        mine = squares(c.world, me)
        was = min(distance(sq, ev.from_) for sq in mine)
        now = min(distance(sq, ev.to) for sq in mine)
        if was == 2 and now > 2:
            c.provoke(me, on=ev.actor, why=ref)

    c.watch(Moved, slipped, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m147a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 7),
)
def m147a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m147a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 6),
)
def m147a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m147a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m147a4(c: Cast) -> None:
    """A step, with a swing at either end of it.

    The spec names a row belonging to a different stat block -- a level 13
    creature's, at a level 13 attack bonus -- which is the same
    cross-reference the level 8 batch found twice. The row this creature
    plainly means is its own longer reach, m147a2, and that is what is
    swung; see the report.

    One swing before the step and one after, because the two have to land on
    different creatures and a step is what puts a second one in reach. The
    second is offered rather than taken: the printed line says once **or**
    twice.
    """
    me = c.me
    struck: list[int] = []

    def swing() -> None:
        near = sorted(
            foe for foe in c.enemies() if c.distance(foe) <= 2 and foe not in struck
        )
        victim = c.choose(near, "m147a4: which enemy") if near else None
        if victim is not None:
            struck.append(victim)
            use(c.world, me, "m147a2", targets=[victim], spend=False)

    swing()
    c.shift(max(1, c.speed_of() // 2))
    if not struck or c.may("swing a second time"):
        swing()


_M147_MISSED = "an attack misses the m147"


@power(
    "m147a5",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M147_MISSED,
    on=Trigger(Miss, when=targets_me, text=_M147_MISSED),
)
def m147a5(c: Cast) -> None:
    """"Effect (Free Action)" with a trigger line is `FREE` plus a declared
    `on=`. Any attack, at any range: the printed sentence names no kind."""
    c.shift(1)


# ==========================================================================
# m165
# ==========================================================================


@power(
    "m165a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m165a0(c: Cast) -> None:
    """Worse when it has somebody to itself.

    Counted before the blow lands, because a target that drops stops being
    an enemy and the count would then read one fewer than the printed line
    means. The extra five is a flat packet on top of the header's line,
    which is what keeps the header rescalable.
    """
    alone = sum(1 for foe in c.enemies() if c.adjacent(foe)) == 1
    if c.strike():
        c.hit()
        if alone:
            c.flat(5)


@power(
    "m165a1",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m165a1(c: Cast) -> None:
    c.note("m165a1: it looks like some Medium humanoid; an Insight check beats its Bluff")


def _great_plants(world: World, eid: int) -> list[int]:
    """Every Large-or-bigger plant standing on the board.

    A `requires=` gate is handed `(world, eid)` and no `Cast`, and a
    creature's type line is only readable through `Cast.kinds_of` -- so one
    is made here rather than the lookup being written out a second time.
    A tree is scenery, which the grid does not have; a plant creature is
    what remains of the printed list.
    """
    ask = Cast(world=world, me=eid, ref="m165a2")
    out = []
    for who in creatures(world):
        pos = world.get(who, Position) if who != eid else None
        if pos is not None and pos.size in _BIG and ask.is_kind("plant", on=who):
            out.append(who)
    return out


def _beside_a_great_plant(world: World, eid: int) -> bool:
    return any(
        distance_between(world, eid, plant) <= 1 for plant in _great_plants(world, eid)
    )


@power(
    "m165a2",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    requires=_beside_a_great_plant,
    requires_text="the m165 must begin and end adjacent to a Large or larger plant",
)
def m165a2(c: Cast) -> None:
    """Out of one thicket and into another.

    The Requirement covers the near end; the far end is covered by choosing
    only from squares beside a plant. `c.teleport` checks the distance and
    the footprint itself, so the destination is offered rather than measured
    here.
    """
    reachable = spread(squares(c.world, c.me), 8)
    spots = sorted(
        {
            sq
            for plant in _great_plants(c.world, c.me)
            for sq in _free_square_within(c, plant, 1)
            if sq in reachable
        }
    )
    if spots:
        c.teleport(8, to=c.world.decide(c.me, "teleport", spots, f"{c.ref}: to which thicket"))


# ==========================================================================
# m2976
# ==========================================================================


@power(
    "m2976a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d12", 6),
)
def m2976a0(c: Cast) -> None:
    if c.strike():
        c.hit()


#: The four defences, for a printed "a +3 bonus to all defenses".
EVERY_DEFENCE = (AC, FORT, REF, WILL)


@power(
    "m2976a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d12", 5, kind=LIMITED),
)
def m2976a1(c: Cast) -> None:
    """A swing that splashes, and a guard raised whether or not it lands.

    "Recharges when first bloodied" is the printed sentence on top of the
    die the database files; `Bloodied` is emitted on the crossing and
    nowhere else, so "first" needs no guard of its own, and the creature it
    names is this one -- the event's subject and the sentence's agree here.

    The Effect line is not on the hit, so the four defences go up either
    way. Four separate `what`s, so nothing is competing with anything: two
    bonuses of one kind do not add, and a "+3 to all defenses" written as
    one modifier would have been a +3 to nothing.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    victim = c.target
    if c.strike():
        c.hit()
        splash = sorted(
            foe
            for foe in c.enemies()
            if foe != victim and victim is not None and c.adjacent_to(victim, foe)
        )
        if splash:
            spread_to = c.choose(splash, "m2976a1: which neighbour")
            if spread_to is not None:
                c.damage("1d12", on=spread_to)
    for defence in EVERY_DEFENCE:
        c.bonus(defence, 3, until=When.SONT, on=me)
    c.note("m2976a1: when charging, it may swing this in place of a melee basic attack")


@power(
    "m2976a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d12", 6),
)
def m2976a2(c: Cast) -> None:
    """The critical line is a condition rather than more damage, so it reads
    off `c.crit` rather than being rolled."""
    if c.strike():
        c.hit()
        c.slide(2)
        if c.crit:
            c.prone()


_M2976_HURT = "the m2976 takes damage"


@power(
    "m2976a3",
    level=9,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger=_M2976_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M2976_HURT),
)
def m2976a3(c: Cast) -> None:
    """Gone the moment it is touched, until it swings or its turn is over.

    `targets_me` rather than `about_me`: a damage event names its subject
    `target`, and the other predicate is false on it forever. Any damage at
    all, which is what the printed trigger says -- a burn counts.

    The veil is torn down on its own attack roll, hit or miss, which is the
    printed "until after it hits or misses with an attack" -- `_vanish` is
    that arrangement, written for a controller two levels down.
    """
    _vanish(c, When.EONT)


@power(
    "m2976a4",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2976a4(c: Cast) -> None:
    """It is already out of sight when the fight starts, if there is anything
    to be out of sight behind.

    Judged at `RoundStart` rather than while the trait arms: arming happens
    inside `Encounter.start`, which is still walking the initiative order,
    and the printed line is about the moment initiative is rolled. There is
    no Stealth check to roll, so having the cover is the whole of it.
    """
    _at_the_off(c, lambda: _conceal(c))


_M2976_FELLED = "the m2976 bloodies an enemy or drops one"


def _m2976_felled(world: World, me: int, ev: DamageApplied) -> bool:
    return _bit_an_enemy(world, me, ev)


@power(
    "m2976a5",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2976_FELLED,
    on=Trigger(DamageApplied, when=_m2976_felled, text=_M2976_FELLED),
)
def m2976a5(c: Cast) -> None:
    """Off the damage, because the two events that name bloodying and
    dropping both name the **victim** and this sentence's subject is the
    attacker. See `_bit_an_enemy`."""
    c.shift(5)
    c.bonus("damage", 3, until=When.EONT, on=c.me)


# ==========================================================================
# m3013
# ==========================================================================


@power(
    "m3013a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m3013a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3013a1",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3013a1(c: Cast) -> None:
    c.mode("climb", 7, until=When.EONT)


@power(
    "m3013a2",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3013a2(c: Cast) -> None:
    """It fights better with somebody on the other side.

    The attack bonus is a gated modifier, because an attack modifier is read
    off the attacker and the gate is about who is being swung at. The extra
    damage is dice rolled as the blow lands rather than a damage modifier,
    which would add to whatever packet was already being dealt -- and it is
    asked again on the `Hit`, since a flank can be broken between the
    declaration and the blow.
    """
    me, ref = c.me, c.ref

    def flanking(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and flanked_by(c.world, victim, me)

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, kind="untyped", when=flanking)

    def rider(ev: Hit) -> None:
        if ev.attacker == me and flanked_by(c.world, ev.target, me):
            c.damage("2d6", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


# ==========================================================================
# m3072
# ==========================================================================


@power(
    "m3072a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 3),
)
def m3072a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3072a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3072a1(c: Cast) -> None:
    """It walks its two squares and lashes out at everything it passes.

    `AdjacencyGained` read from the other side of the usual: `mover` has to
    be this creature, because the printed line is about **its** approach
    rather than somebody else's. That field is what `closed_on_me` reads to
    exclude exactly this case, and without it the two sentences are the same
    event. The pair is emitted mirrored, so `actor` is checked as well or
    every neighbour is counted twice.

    The swings come after the step rather than during it: an attack resolved
    from inside `movement.step` would land while the creature is between
    squares, and the printed line settles for "during the shift".
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    met: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other not in met:
            met.append(ev.other)

    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=c.ref)
    c.shift(2)
    c.world.effects.end(watcher, "the shift is over")
    for who in met:
        use(c.world, me, "m3072a0", targets=[who], spend=False)


_M3072_HURT = "the m3072 takes damage from an attack"


@power(
    "m3072a2",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M3072_HURT,
    on=Trigger(
        DamageApplied, when=both(targets_me, _hurt_by_an_attack), text=_M3072_HURT
    ),
)
def m3072a2(c: Cast) -> None:
    c.shift(1)


#: The six the card rolls between.
_M3072_TYPES = (
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.PSYCHIC,
    DamageType.THUNDER,
)


@power(
    "m3072a3",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3072a3(c: Cast) -> None:
    """One soft spot that moves every time it is found.

    Five resistances and one vulnerability, held as effects so that each can
    be ended and replaced on its own. `c.resist` is the mirror of
    `c.vulnerable`; before it existed the five had to be written as negative
    vulnerabilities, which came to the same arithmetic and put "vulnerable
    -5" on the card.

    The swap is read off `DamageApplied` rather than off the roll, because
    the printed line is "when it takes damage of the type", and damage that
    a resistance ate entirely is not damage taken.
    """
    me, ref = c.me, c.ref
    guards: dict[DamageType, Effect] = {}
    soft: list[DamageType] = []
    exposure: list[Effect] = []

    def shield(kind: DamageType) -> None:
        held = c.resist(5, kind, until=When.ENCOUNTER, on=me)
        if held is not None:
            guards[kind] = held

    def expose(kind: DamageType) -> None:
        held = guards.pop(kind, None)
        if held is not None:
            c.world.effects.end(held, ref)
        for old in exposure:
            c.world.effects.end(old, ref)
        exposure.clear()
        soft.clear()
        soft.append(kind)
        fresh = c.vulnerable(10, kind, until=When.ENCOUNTER, on=me)
        if fresh is not None:
            exposure.append(fresh)

    opened = c.world.rng.choice(list(_M3072_TYPES))
    for kind in _M3072_TYPES:
        if kind is not opened:
            shield(kind)
    expose(opened)

    def shifts(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0 or not soft or ev.dtype is not soft[0]:
            return
        was = soft[0]
        shield(was)
        expose(c.world.rng.choice([k for k in _M3072_TYPES if k is not was]))

    c.watch(DamageApplied, shifts, until=When.ENCOUNTER, on=me, label=ref)


# ==========================================================================
# m3116
# ==========================================================================


@power(
    "m3116a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 5),
)
def m3116a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3116a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
)
def m3116a1(c: Cast) -> None:
    """"Each against a different target" is what `UpTo(3)` chooses between,
    and the body is called once per creature picked -- so three different
    ones is the only thing it can be. The row that prints the attack is used
    rather than copied, so its damage line stays in one place."""
    if c.target is not None:
        use(c.world, c.me, "m3116a0", targets=[c.target], spend=False)


@power(
    "m3116a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m3116a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3116a3",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3116a3(c: Cast) -> None:
    """Stone is not in its way. `c.phasing` is the mode that says so -- it
    still has to stop somewhere it fits, which is what "as if it were loose
    earth" leaves standing."""
    c.phasing(until=When.ENCOUNTER)


_M3116_MISSED = "a melee attack misses the m3116"


@power(
    "m3116a4",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M3116_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M3116_MISSED),
)
def m3116a4(c: Cast) -> None:
    """It drops into the ground. `movement.mode_of` puts a creature with a
    burrow speed and nothing faster underground whenever it moves, so the
    plain walk is the burrow the printed line names."""
    c.move(c.speed_of())


@power(
    "m3116a5",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3116a5(c: Cast) -> None:
    """Half buried, and worth less cover the moment it pulls itself out.

    "Until it moves" is not a duration the enum has, so the hold runs to the
    end of the encounter and is ended by hand on `MoveStart` -- before the
    first step rather than after the last, because a creature hauling itself
    out of the ground is not dug in for the journey.
    """
    me = c.me
    dug_in = c.bonus(AC, 2, until=When.ENCOUNTER, on=me, kind="untyped")
    if dug_in is None:
        return

    def rises(ev: MoveStart) -> None:
        if ev.actor == me:
            c.world.effects.end(dug_in, "it moved")

    watcher = c.watch(MoveStart, rises, until=When.ENCOUNTER, on=me, label=f"{c.ref} dug in")
    dug_in.on_end.append(lambda: c.world.effects.end(watcher, "no longer dug in"))


# ==========================================================================
# m380
# ==========================================================================


@power(
    "m380a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 7),
)
def m380a0(c: Cast) -> None:
    if c.strike():
        c.hit()


def _free_to_run(world: World, eid: int) -> bool:
    """The printed "cannot use this power while immobilized or slowed"."""
    return not is_(world, eid, Condition.IMMOBILIZED) and not is_(
        world, eid, Condition.SLOWED
    )


@power(
    "m380a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    requires=_free_to_run,
    requires_text="the m380 must not be immobilized or slowed",
)
def m380a1(c: Cast) -> None:
    """Two swings with a run between them.

    "At any two points during its move" is one blow before and one after, so
    that the run puts a second creature in reach. The -2 is a modifier laid
    on the caster and lifted the moment the row is done, rather than passed
    to each swing: `c.basic` uses whichever row this creature's basic attack
    actually is, and that row rolls its own attack.

    Declared with no target -- each swing picks its own, and after the run
    they are not the same creature.
    """
    me = c.me
    toll = c.penalty("attack", 2, on=me, until=When.EOT)
    try:
        for step in (0, 1):
            if step:
                c.move(c.speed_of())
            victim = _adjacent_foe(c, "m380a1")
            if victim is not None:
                c.basic(on=victim)
    finally:
        if toll is not None:
            c.world.effects.end(toll, "the run is over")


@power(
    "m380a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m380a2(c: Cast) -> None:
    c.shift(10)


def _is_stuck(world: World, eid: int) -> bool:
    return is_(world, eid, Condition.IMMOBILIZED)


@power(
    "m380a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_stuck,
    requires_text="the m380 must be immobilized",
)
def m380a3(c: Cast) -> None:
    """The hold goes, whatever laid it: the printed line is not a saving
    throw and does not care how the creature was pinned down. Only the
    immobilisation, so an effect carrying other conditions keeps them."""
    for held in list(c.world.effects.of(c.me)):
        if Condition.IMMOBILIZED in held.conditions:
            c.world.effects.end(held, c.ref)


# ==========================================================================
# m461
# ==========================================================================


@power(
    "m461a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 3),
)
def m461a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m461a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d6", 3),
)
def m461a1(c: Cast) -> None:
    """It runs at somebody and swings with the line printed here.

    `c.run_at` rather than `c.charge_at`: the printed +15 is the +14 of its
    ordinary swing with the charge bonus already counted into it, and
    `charge_at` marks the swing as a charge, which is what makes
    `resolve.attack` add that point -- so it would be paid twice. The same
    call m2815a2 settled on one level down.
    """
    victim = c.target
    if victim is None:
        return
    c.run_at(victim)
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m461a2",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.HEALING],
)
def m461a2(c: Cast) -> None:
    """The ally chooses which of the two it takes.

    `c.may` asks the **target**, which is who the printed line leaves the
    choice to, and `c.save` defaults to the caster -- so it is aimed. The
    surge is tried and the saving throw taken when it comes to nothing:
    `c.surge` returns what it healed, and a creature with an empty pool has
    not spent one, so the choice is not a choice. `loader.spawn` gives every
    monster `surges=0`, which makes the first half of this row inert for any
    ally that is not a character; see the report.
    """
    who = c.target
    if who is None:
        return
    if c.may("spend a healing surge") and c.surge(on=who):
        return
    c.save(on=who)


@power(
    "m461a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=12),
)
def m461a3(c: Cast) -> None:
    """Its victim will not touch it, and turns on anybody who does.

    Two halves of one printed effect, so they hang on one saving throw:
    `c.cannot_attack(against=...)` is the hold the victim saves against, and
    the compelled swing is a watch clocked on the **caster** and ended with
    the hold. Hung on the victim with a save-ends duration it would have
    been a second thing for the victim to save against.

    In the interrupt window, because an opportunity attack interrupts what
    provoked it. `c.grant_attack` is the door: the swing is the charmed
    creature's, not this one's, and the +2 rides on it.

    "Recharges when no creature is affected by the power" is the hold ending
    rather than a die, so the row is handed back from `on_end`. The header's
    6 stays, because that is what `actions.recharge` rolls and what the card
    shows; the two only ever agree to make it available sooner.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    me, ref = c.me, c.ref
    hold = c.cannot_attack(on=victim, against=me, until=When.SAVE_ENDS)
    if hold is None:
        return

    def defends(ev: AttackDeclared) -> None:
        if ev.target != me or ev.attacker == victim:
            return
        if distance_between(c.world, victim, ev.attacker) <= 1:
            c.grant_attack(victim, on=ev.attacker, attack_bonus=2, trigger=ev)

    watcher = c.watch(
        AttackDeclared,
        defends,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=f"{ref} compelled",
    )
    hold.on_end.append(lambda: c.world.effects.end(watcher, "the charm ended"))
    known = c.world.get(me, Powers)
    if known is not None:
        hold.on_end.append(lambda: known.restore(ref))


@power(
    "m461a4",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m461a4(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m4782
# ==========================================================================
#
# The card spells this creature's id as a shorter one belonging to a
# different stat block in four of its six rows. This creature is the one
# every sentence plainly means, and is the one written; the same
# cross-reference turned up twice in the level 8 batch.


@power(
    "m4782a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m4782a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and a toll only while it is hurt.

    Not the aura helper, whose hold is carried for as long as its owner is
    standing inside: this one takes nothing away and gives nothing, it bites
    once at a boundary, so membership and the bloodied clause are both
    measured at that moment.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def scorch(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.bloodied(me) and c.distance(ev.actor) <= 1:
            c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnEnd, scorch, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4782a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m4782a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT)


@power(
    "m4782a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m4782a2(c: Cast) -> None:
    """"At any point during the shift" is either side of it, and the side is
    chosen by where there is somebody to hit: the swing goes first when it
    can, because a step picks its own destination and one taken first can
    leave the target out of reach."""
    victim = _adjacent_foe(c, "m4782a2")
    if victim is not None:
        use(c.world, c.me, "m4782a1", targets=[victim], spend=False)
        c.shift(4)
        return
    c.shift(4)
    later = _adjacent_foe(c, "m4782a2")
    if later is not None:
        use(c.world, c.me, "m4782a1", targets=[later], spend=False)


@power(
    "m4782a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE),
)
def m4782a3(c: Cast) -> None:
    if c.strike():
        c.hit()


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _not_bloodied(world: World, eid: int) -> bool:
    return not _is_bloodied(world, eid)


@power(
    "m4782a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d10", 5, dtype=DamageType.FIRE, kind=LIMITED),
    requires=_is_bloodied,
    requires_text="the m4782 must be bloodied",
)
def m4782a4(c: Cast) -> None:
    """It burns everything beside it and gets out.

    The burst catches the enemies standing in it; the flight is one printed
    movement however many of them were caught, and it is on the hit line, so
    it goes on the first blow that lands. The body runs once per target and
    keeps no state between calls, so the latch is a hold on the caster --
    `c.first` would have flown on a miss against the first creature and
    stayed put after a hit on the second.
    """
    if not c.strike():
        return
    c.hit()
    flown = f"{c.ref} flew"
    if not _holding_label(c, flown):
        c.effect(flown, until=When.EOT, on=c.me)
        _guarded_move(c, 8)


@power(
    "m4782a5",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    requires=_not_bloodied,
    requires_text="the m4782 must not be bloodied",
    out_of_combat=True,
)
def m4782a5(c: Cast) -> None:
    c.note("m4782a5: it takes the appearance of one particular Medium humanoid")


# ==========================================================================
# m5018
# ==========================================================================


@power(
    "m5018a0",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5018a0(c: Cast) -> None:
    """Five more against anything that is not watching it.

    Read off the roll that was just made rather than asked of the board
    afterwards: a one-shot grant has already been spent by the time `Hit` is
    announced, and a blow struck from concealment answers "no". `c.
    had_advantage` is that reading. It is wider than the printed "granting
    combat advantage **to it**" by the width of a flank, which is the only
    approximation here.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.had_advantage(ev):
            c.flat(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5018a1",
    level=9,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5018a1(c: Cast) -> None:
    """Hidden behind anything that hides it properly.

    Superior cover only -- `Cover.SUPERIOR` is what the grid calls it -- so
    the partial cover of a corner is not enough, which is the difference
    between this trait and the one on m2976. Total concealment is the same
    state and the grid has no second way to say it.
    """

    def slip_away() -> None:
        for foe in c.enemies():
            if not c.is_hidden(from_=foe) and (
                cover_between(c.world, foe, c.me) is Cover.SUPERIOR
            ):
                c.hide(from_=foe)

    _at_the_off(c, slip_away)


@power(
    "m5018a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5018a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5018a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d12", 8, kind=LIMITED),
)
def m5018a3(c: Cast) -> None:
    """The slide names where it ends, not merely how far, so the destination
    is chosen from the squares within two of the caster and handed to
    `c.slide` as `to` -- which is exactly the case that argument exists for.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    there = squares(c.world, victim)
    near = [
        sq
        for sq in _free_square_within(c, c.me, 2, mover=victim)
        if min(distance(sq, s) for s in there) <= 5
    ]
    if near:
        c.slide(5, to=c.world.decide(c.me, "slide", near, f"{c.ref}: drag it to which square"))


@power(
    "m5018a4",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5018a4(c: Cast) -> None:
    """It shrugs off whoever claimed it and steps away.

    Both halves of a mark go -- the effect and the relation -- since either
    one left behind keeps half of it alive. Not written: moving through
    enemy-occupied squares during the shift, which is the grid's business
    and no `Cast` method reaches it. See the report.
    """
    _shed(c, Relation.MARKED_BY)
    c.shift(3)


@power(
    "m5018a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=12),
)
def m5018a5(c: Cast) -> None:
    """One or the other, never both: the printed line offers a choice."""
    if not c.strike():
        return
    if c.may("knock it down rather than drag it"):
        c.prone()
    else:
        c.slide(3)
