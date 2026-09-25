"""Monster abilities, level 13: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=18)` and `Damage("2d6", 7)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the twelve levels below are kept: a row the database
files under an action heading that is plainly a **trait** is declared
`ActionType.NONE`; a stat block printing no range at all means melee 1; a
row that moves and swings takes the swing first where there is anything in
reach, because the movement picks its own destination; and a cross-referenced
id is read as the row every sentence plainly means, which is this creature's
own.

Six readings this file had to settle.

**A miss chance is rolled on the blows that would land.** The engine has no
concealment, and a 50% chance to miss applied to every attack comes to
exactly the same distribution as one rolled only on the hits -- an attack has
to beat the defence *and* find the creature either way. So m148a3 watches
`Hit` in the interrupt window and sets `result.hit` to False, which
`resolve.attack`'s own `confirm` callback turns into a real `Miss`; that is
the mechanism written for an interrupt undoing a hit, and it means the row
that answers "an attack misses because of the veil" has an event to answer.
The marker rides on the live `AttackResult`, which is the one object both the
cancelled `Hit` and the re-emitted `Miss` share.

**"It does not take a move action on its turn" is the budget.** `Budget.move`
is the only record of whether the action has been spent, and m156a1 both asks
it and spends it -- a printed line forbidding the move action and one
consuming it come to the same turn.

**Two bonuses of the same kind do not add.** m156 prints its attack twice,
"+19" and "+20 while bloodied", and the second is the racial bonus its own
trait already grants. The header keeps the printed +19 and m156a4 is the only
place the +1 is written; adding it in both places would have been one bonus
of each kind and come to +20 forever.

**A shift is one step.** `movement.shift` places the creature at its
destination rather than walking it, so "each enemy it moves adjacent to
during the move" can only be read as the enemies it finishes beside and was
not beside before -- which is what `AdjacencyGained` announces, mirrored, for
the one step it does take.

**Ongoing damage of one type does not stack.** m4807a1 prints ongoing 5 acid,
or ongoing 10 while bloodied, which is one burn whose size is read as it
lands; `c.ongoing` refuses the weaker of two and returns the standing one, so
nothing has to be swept first.

**A trail is the squares that were left.** `LeaveSquare` names each one as
the mover goes, which is the only record of where a creature has been -- a
zone built from `MoveEnd` would be one square long.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.content.monsters.level_02.skirmishers import (
    _advantage_rider,
    _squeezes_freely,
)
from combat_engine.content.monsters.level_05.skirmishers import _MELEE_KINDS, _reach_kind
from combat_engine.content.monsters.level_06.skirmishers import _after_moving
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_09.skirmishers import _free_square_within
from combat_engine.content.monsters.level_10.brutes import _same_stock
from combat_engine.content.monsters.level_10.skirmishers import _in_the_saddle
from combat_engine.content.monsters.level_11.brutes import _HELD_FAST
from combat_engine.content.monsters.level_11.lurkers import _breathe_again
from combat_engine.content.monsters.level_11.soldiers import ELEMENTS
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
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
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    Bloodied,
    Budget,
    Cast,
    CloseBlast,
    CloseBurst,
    Damage,
    DamageApplied,
    DamageType,
    Dropped,
    Effect,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    OpportunityWindow,
    SavingThrow,
    Square,
    TurnStart,
    Usage,
    When,
    Window,
    World,
    ZoneEntered,
    distance,
    footprint,
    power,
    spread,
    use,
)
from combat_engine.engine.events import AdjacencyGained, LeaveSquare, ZoneExited
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    enemies,
    flanked_by,
    has_combat_advantage,
    squares,
)
from combat_engine.engine.triggers import Trigger, about_me


def _drop_within(reach: int) -> Callable[[World, int], bool]:
    """A printed "requires combat advantage", asked at the row's own reach.

    `_has_the_drop` a level down measures one square, which is right for a
    creature whose arms are that long and wrong for one with three squares
    of reach: the row would be refused with the victim plainly inside it.
    """

    def gate(world: World, eid: int) -> bool:
        return any(
            distance_between(world, eid, foe) <= reach
            and has_combat_advantage(world, eid, foe)
            for foe in enemies(world, eid)
        )

    return gate


def _has_its_move(world: World, eid: int) -> bool:
    """Has this creature still not spent its move action this turn?

    `Budget` is the only record of it. A printed "if it does not take a move
    action" is this question asked before the row runs, and the row spends
    the action afterwards so the answer cannot change behind it.
    """
    budget = world.get(eid, Budget)
    return budget is not None and budget.move > 0


def _labelled(c: Cast, label: str, *, on: int | None = None) -> bool:
    """Is that hold standing? Several rows here are a named state."""
    return any(eff.label == label for eff in c.world.effects.of(on if on else c.me))


def _flies_and_swings(c: Cast, squares_: int, ref: str) -> None:
    """A pass: it comes down on somebody at some point during the flight.

    The swing goes first where there is anything in reach -- the flight picks
    its own destination and one taken first can leave the target behind --
    and otherwise it flies and then swings, which is the same printed
    sentence read the other way round. The waiver is the printed "it does not
    provoke opportunity attacks when moving away from the target".
    """
    waiver = c.no_provoke(until=When.EOT)
    try:
        victim = _adjacent_foe(c, ref)
        if victim is not None:
            use(c.world, c.me, ref, targets=[victim], spend=False)
            c.move(squares_)
            return
        c.move(squares_)
        victim = _adjacent_foe(c, ref)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the pass is over")
    if victim is not None and alive(c.world, victim):
        use(c.world, c.me, ref, targets=[victim], spend=False)


def _adapts(c: Cast, amount: int) -> None:
    """"Resist N to the triggering damage type, or until it does this again."

    The type is read off the event rather than chosen -- `DamageApplied` is
    the only place a packet's type can be read -- and the second use replaces
    the first, which is the hold `c.resist` labels with this row's ref.
    """
    me = c.me
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is None:
        return
    for eff in list(c.world.effects.of(me)):
        if eff.label == f"{c.ref} resist":
            c.world.effects.end(eff, "it adapts to something else")
    c.resist(amount, dtype, until=When.ENCOUNTER, on=me)


def _an_element_landed(world: World, me: int, ev: DamageApplied) -> bool:
    """`DamageApplied` names its subject `target`, so `about_me` -- which
    reads `ev.actor` and only that -- is false here forever."""
    return ev.target == me and ev.amount > 0 and ev.dtype in ELEMENTS


# ==========================================================================
# m148
# ==========================================================================

#: The veil, held as a labelled effect so the board can see whether it is up
#: -- and so the row that recharges it and the row that answers it are asking
#: the same question rather than each keeping a flag.
_M148_VEIL = "m148a3 veil"
_M148_TURNED = "an attack misses the m148 because of its m148a3"


def _turned_aside(world: World, me: int, ev: Miss) -> bool:
    """Did the veil turn this one aside, rather than the die?

    The marker rides on the live `AttackResult`, which the cancelled `Hit`
    and the `Miss` that replaces it share -- the re-emitted event is a fresh
    object and nothing else survives the swap.
    """
    return ev.target == me and bool(getattr(getattr(ev, "result", None), "blurred", False))


@power(
    "m148a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7),
)
def m148a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m148a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d6", 7),
)
def m148a1(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m148a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    requires=_drop_within(3),
    requires_text="the m148 must have combat advantage against a creature in reach",
)
def m148a2(c: Cast) -> None:
    """Three blows on one creature.

    The card spells the first two as another stat block's id; the row every
    sentence plainly means is this creature's own reach-3 attack, which is
    the one it has two of. Both rows are reached through `use` rather than
    copied, so each printed line stays in one place.
    """
    victim = c.target
    if victim is None:
        return
    for ref in ("m148a0", "m148a0", "m148a1"):
        if not alive(c.world, victim):
            return
        use(c.world, c.me, ref, targets=[victim], spend=False)


@power(
    "m148a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m148a3(c: Cast) -> None:
    """Half of what is aimed at it goes through the wrong m148.

    Filed as a standard action and plainly a trait. The coin is tossed on the
    blows that would land rather than on every attack, which is the same
    distribution -- an attack has to beat the defence and find the creature
    either way -- and it is the only version that can be written at all:
    `resolve.attack` recomputes the outcome after the roll, so a listener on
    `AttackRolled` has nothing to change, while `result.hit` set to False in
    the `Hit` interrupt window is turned into a real `Miss` by the engine's
    own `confirm` callback.

    Only melee and ranged attacks, which is what the card names, and never a
    critical, which the card exempts. The hold is the veil: the blow that
    gets through ends it, and two squares of movement on its own turn puts it
    back up.
    """
    me = c.me

    def raise_it() -> None:
        if not _labelled(c, _M148_VEIL, on=me):
            c.effect(_M148_VEIL, until=When.ENCOUNTER, on=me)

    def blur(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.target != me or ev.attacker == me or result is None:
            return
        if not _labelled(c, _M148_VEIL, on=me):
            return
        if result.critical or _reach_kind(ev) not in ("melee", "ranged"):
            return
        if c.roll("1d2") == 1:
            result.hit = False
            result.blurred = True
            return
        for eff in list(c.world.effects.of(me)):
            if eff.label == _M148_VEIL:
                c.world.effects.end(eff, "the blow found it")

    def moved(_kind: str, start: Square | None, end: Square, _steps: int) -> None:
        if start is not None and c.turn_of() == me and distance(start, end) >= 2:
            raise_it()

    raise_it()
    c.watch(Hit, blur, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=c.ref)
    _after_moving(c, moved)


@power(
    "m148a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m148a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Half speed, the -5 to attacks and the combat advantage handed out are the
    *whole* of what `Condition.SQUEEZING` is, so waiving the printed speed
    penalty waives the condition -- there is no part of it to take off on its
    own. The same reading m483a3 settled on two levels down.
    """
    c.ignores_difficult(until=When.ENCOUNTER)
    _squeezes_freely(c)


@power(
    "m148a5",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(3),
    target=NO_TARGET,
    trigger=_M148_TURNED,
    on=Trigger(Miss, when=_turned_aside, text=_M148_TURNED),
)
def m148a5(c: Cast) -> None:
    """A swing back at whoever swung at the wrong one, and a step away.

    Declared with no target and aimed off the trigger: the dispatcher points
    a row at the nearest enemy, and this one is about the creature that
    missed. `c.basic` rolls whichever row this creature's basic attack
    actually is.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None or not alive(c.world, who) or c.distance(who) > 3:
        who = _adjacent_foe(c, c.ref)
    if who is not None:
        c.basic(on=who)
    c.shift(1)


@power(
    "m148a6",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m148a6(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: everything inside its
    reach is in danger of an opportunity attack, not only what is adjacent."""
    c.threatens(3)


# ==========================================================================
# m156
# ==========================================================================


@power(
    "m156a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d6", 4),
)
def m156a0(c: Cast) -> None:
    """The printed "+20 while bloodied" is m156a4's racial bonus and is
    written there, once. The printed "crit 2d6 + 10" is the maximum of the
    ordinary line -- which `c.damage` already deals on a critical -- plus 2d6
    on top, and the extra is rolled with `c.flat` because `c.damage` would
    maximise that too."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("2d6"))


@power(
    "m156a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    requires=_has_its_move,
    requires_text="the m156 must not have taken a move action this turn",
)
def m156a1(c: Cast) -> None:
    """A step and both blades, bought with the turn's move action.

    "If the m156 doesn't take a move action on its turn" is `Budget.move`,
    which is the only record there is of it: the gate asks and the row then
    spends it, because a printed line forbidding the move action and one
    consuming it come to the same turn. The printed "or vice versa" -- the
    same trade made the other way about -- has no second row to be, and the
    database files this one as a standard action.

    Declared with no target: after the step the second blow is rarely worth
    aiming at the same creature.
    """
    if c.world.encounter is not None:
        c.world.encounter.spend(c.me, MOVE)
    c.shift(1)
    for _ in range(2):
        prey = _adjacent_foe(c, c.ref)
        if prey is None:
            return
        use(c.world, c.me, "m156a0", targets=[prey], spend=False)


@power(
    "m156a2",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d6", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m156a2(c: Cast) -> None:
    """The printed "+15 while bloodied" is m156a4's racial bonus, which
    applies to every attack roll and is written once, there."""
    if c.strike():
        c.hit()


@power(
    "m156a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m156a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    melee and ranged attacks, so a close blast of its own is left out."""
    _advantage_rider(c, "1d6", ("melee", "ranged"))


@power(
    "m156a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m156a4(c: Cast) -> None:
    """A racial bonus, gated on its own health as the roll is made.

    Asked at the roll rather than watched for, because the crossing works
    both ways -- healing above half takes it away again -- and the gate is
    read every time the modifier is totalled. `kind="racial"` keeps it clear
    of anything else it might be standing beside: two bonuses of one kind do
    not add.
    """
    me = c.me
    c.bonus(
        "attack",
        1,
        until=When.ENCOUNTER,
        on=me,
        kind="racial",
        when=lambda _ctx: c.bloodied(me),
    )


@power(
    "m156a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m156a5(c: Cast) -> None:
    """Three squares, back as soon as both blades have found different men.

    The printed recharge is a sentence on top of the die the database files.
    m156a1 swings the row that prints the attack rather than declaring one of
    its own, so what the tally can see is the blade rather than the row that
    drew it twice -- and two different enemies attacked with it inside one
    round is that row and nothing else, since nothing else swings it twice in
    a turn.
    """
    me = c.me
    struck: dict[int, set[int]] = {}

    def paired(ev: AttackDeclared) -> bool:
        if ev.attacker != me or ev.power != "m156a0":
            return False
        seen = struck.setdefault(c.world.round, set())
        seen.add(ev.target)
        return len(seen) >= 2

    _recharge_on(c, AttackDeclared, paired)
    c.shift(3)


# ==========================================================================
# m1622
# ==========================================================================

_M1622_OPENED = "the m1622's movement draws an opportunity attack"
_M1622_CLOUD = "m1622a5 cloud"


def _drew_an_opening(world: World, me: int, ev: OpportunityWindow) -> bool:
    """The window opens on the creature that provoked, and `why` is where
    `movement.step` says the provocation was a step rather than a spell."""
    return ev.provoker == me and ev.why == "moved away"


@power(
    "m1622a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 5),
)
def m1622a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1622a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d6", 5),
)
def m1622a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1622a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m1622a2(c: Cast) -> None:
    """One of each blade, each picking its own target.

    Declared with no target: the printed line names none, and the two rows
    are reached through `use` so each printed line stays in one place.
    """
    for ref in ("m1622a0", "m1622a1"):
        prey = _adjacent_foe(c, c.ref)
        if prey is not None:
            use(c.world, c.me, ref, targets=[prey], spend=False)


@power(
    "m1622a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m1622a3(c: Cast) -> None:
    """The printed "requires longsword" is satisfied by construction: this
    creature carries both blades as part of its stat block and the
    requirement names which of the two the row swings, not a state it can be
    out of. A `Gear` gate would refuse it forever -- a monster has none."""
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


@power(
    "m1622a4",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M1622_OPENED,
    on=Trigger(OpportunityWindow, when=_drew_an_opening, text=_M1622_OPENED),
)
def m1622a4(c: Cast) -> None:
    """A free action, which is what the card's own action line says, against
    whoever the step gave an opening to. Declared with no target and aimed
    off the trigger: the window names the creature that gets the swing."""
    who = getattr(c.trigger, "actor", None)
    if who is not None and alive(c.world, who) and c.adjacent(who):
        use(c.world, c.me, "m1622a0", targets=[who], spend=False)


@power(
    "m1622a5",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m1622a5(c: Cast) -> None:
    """A cloud that blinds whoever is inside it, for as long as they are.

    "Until it exits" is not a duration the enum has, so the hold is laid on
    entering and taken off on leaving -- the `ZoneEntered`/`ZoneExited` diff
    m137a0 settled on. Anyone standing in it when it is laid is caught too.

    `blocks_sight` is a wall rather than a haze and blocks the line for
    everybody, including this creature; the printed exemption has nowhere to
    go and is noted.
    """
    me = c.me
    held: dict[int, Effect] = {}
    zone = c.zone(c.area(), label=_M1622_CLOUD, until=When.EONT, blocks_sight=True)

    def caught(who: int) -> None:
        if who == me or who in held:
            return
        blind = c.blinded(until=When.ENCOUNTER, on=who)
        if blind is not None:
            held[who] = blind

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            caught(ev.actor)

    def left(ev: ZoneExited) -> None:
        blind = held.pop(ev.actor, None) if ev.zone == zone else None
        if blind is not None:
            c.world.effects.end(blind, "it walked out of the cloud")

    c.watch(ZoneEntered, entered, until=When.EONT, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.EONT, on=me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(zone):
        caught(actor)
    c.note("m1622a5: the m1622 itself sees through the cloud")


@power(
    "m1622a6",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m1622a6(c: Cast) -> None:
    """The longsword all round, and the short sword after whatever it hits.

    The secondary is this creature's own short sword row, reached through
    `use`: it is a different attack line against a different set of dice and
    cannot live beside the first in one header.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None and alive(c.world, victim):
        use(c.world, c.me, "m1622a1", targets=[victim], spend=False)


# ==========================================================================
# m2896
# ==========================================================================

_M2896_FLANKED = "an enemy moves to a space where it flanks the m2896"
_M2896_BLED = "the m2896 is first bloodied"


def _moved_into_flank(world: World, me: int, ev: MoveEnd) -> bool:
    """`MoveEnd`, not `MoveStart`: the question is about the square the
    creature has arrived in, and `MoveStart` fires before the first step."""
    return ev.actor != me and flanked_by(world, me, ev.actor)


@power(
    "m2896a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m2896a0(c: Cast) -> None:
    """The acid is a second packet rather than part of the declared line: the
    header's damage is untyped and only the rider is acid. Both steps are
    taken, before and after, which is what the printed order says."""
    c.shift(2)
    if c.strike():
        c.hit()
        c.damage("2d6", dtype=DamageType.ACID)
    c.shift(2)


@power(
    "m2896a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6),
)
def m2896a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2896a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m2896a2(c: Cast) -> None:
    """Two swings and then three squares away. Declared with no target: the
    printed line names none, and the row that prints the attack is used
    rather than copied."""
    for _ in range(2):
        prey = _adjacent_foe(c, c.ref)
        if prey is None:
            break
        use(c.world, c.me, "m2896a1", targets=[prey], spend=False)
    c.shift(3)


@power(
    "m2896a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m2896a3(c: Cast) -> None:
    """A flying pass with one blow in it.

    Declared with no target, because a target list is chosen before the body
    runs and the creature it swings at may be fourteen squares away when it
    starts. This one has a fly speed of its own, so `movement.mode_of` puts
    it in the air the moment it moves and no mode has to be lent.
    """
    _flies_and_swings(c, 14, "m2896a1")


@power(
    "m2896a4",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6),
    trigger=_M2896_FLANKED,
    on=Trigger(MoveEnd, when=_moved_into_flank, text=_M2896_FLANKED),
)
def m2896a4(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the printed line
    says the triggering enemy, which is rarely the one a dispatcher would
    pick."""
    who = getattr(c.trigger, "actor", None)
    if who is None or not alive(c.world, who):
        return
    if c.strike(on=who):
        c.hit(on=who)
    c.shift(2)


@power(
    "m2896a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d10", 6, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m2896a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m2896a6",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2896_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2896_BLED),
)
def m2896a6(c: Cast) -> None:
    """The card spells its own breath as another stat block's id; the row
    every sentence plainly means is this one's, which is the only thing it
    has to recharge. "First bloodied" needs no guard: `Bloodied` is emitted
    on the crossing and nowhere else."""
    _breathe_again(c, "m2896a5")


@power(
    "m2896a7",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=14),
)
def m2896a7(c: Cast) -> None:
    """No damage line at all: the stun is the whole of the hit. The
    Aftereffect begins when the stun ends, whichever way it ended, and the
    end of an effect is the only moment that can be seen."""
    if not c.strike():
        return
    victim = c.target
    held = c.stunned(until=When.EONT)
    if held is not None and victim is not None:
        held.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


@power(
    "m2896a8",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2896a8(c: Cast) -> None:
    """Saving throws at the top of its turn as well as at the bottom.

    Filed as a standard action and plainly a trait. The end-of-turn saves are
    the engine's own and are left alone; this is the extra one, and only
    against the three conditions the card names -- which `c.save(against=)`
    picks by label and the printed line picks by condition, so the effects
    are found here and `Effects.save` rolls each, the same call `c.save`
    makes and the one that announces a `SavingThrow`.
    """
    me = c.me

    def shrug(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if eff.when is When.SAVE_ENDS and any(
                cond in _HELD_FAST for cond in eff.conditions
            ):
                c.world.effects.save(eff)

    c.watch(TurnStart, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2916
# ==========================================================================


@power(
    "m2916a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d4"),
)
def m2916a0(c: Cast) -> None:
    """The five is the poison and the 4d4 is not, so the rider is a second
    packet rather than a bonus on the declared line."""
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.POISON)


@power(
    "m2916a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=16),
)
def m2916a1(c: Cast) -> None:
    """It slides past and everybody it comes up against goes down.

    No damage line at all: the fall is the whole of the hit. `movement.shift`
    places the creature at its destination rather than walking it there, so
    "each enemy it moves adjacent to during the move" reads as the enemies it
    finishes beside and was not beside before -- which is exactly what
    `AdjacencyGained` announces for the one step a shift takes.

    The destination is *ranked* by how many enemies it ends up beside, the
    way `c.overrun` ranks a trample: a bare `c.shift` offers the reachable
    squares in sorted order and `World.decide` takes the first with nobody
    playing the monster, so the slide reliably went to the top-left corner
    and met nobody at all.
    """
    me = c.me
    met: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other not in met:
            met.append(ev.other)

    theirs = {foe: squares(c.world, foe) for foe in c.enemies()}
    size = c.size_of(on=me)

    def gathers(sq: Square) -> int:
        covered = spread(footprint(sq, size), 1)
        return sum(1 for seats in theirs.values() if seats & covered)

    ranked = sorted(
        c.world.reachable_squares(me, c.speed_of()), key=lambda sq: (-gathers(sq), sq)
    )
    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=f"{c.ref} met")
    try:
        if ranked:
            c.shift(
                c.speed_of(),
                to=c.world.decide(me, "shift", ranked, f"{c.ref}: where it slides"),
            )
    finally:
        c.world.effects.end(watcher, "the slide is over")
    for victim in met:
        if victim in c.enemies() and alive(c.world, victim) and c.strike(on=victim):
            c.prone(on=victim)


@power(
    "m2916a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d6", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m2916a2(c: Cast) -> None:
    """The printed recharge is a sentence on top of the die the database
    files, and the two only ever agree to give the row back sooner."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2916a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2916a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    no range, so it rides every attack it makes."""
    _advantage_rider(c, "2d6")


@power(
    "m2916a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2916a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    "Once per round" is latched on the round rather than on its turn: the
    printed word is round, and an opportunity attack on somebody else's turn
    is a hit it can feed on.
    """
    me = c.me
    fed: dict[int, int] = {}

    def feed(ev: Hit) -> None:
        if ev.attacker != me or not c.bloodied(me) or fed.get(me) == c.world.round:
            return
        fed[me] = c.world.round
        c.temp_hp(10, on=me)

    c.watch(Hit, feed, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m347
# ==========================================================================

_M347_TRAIL = "m347a3 trail"


@power(
    "m347a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m347a0(c: Cast) -> None:
    """Only against an opening. `opportunity` is in the attack context for
    exactly this, and gating on the attacking row's ref instead would catch a
    standard-action basic and miss a creature whose opportunity attack is
    something else."""
    c.bonus(
        AC,
        2,
        until=When.ENCOUNTER,
        on=c.me,
        kind="untyped",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m347a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m347a1(c: Cast) -> None:
    """Whoever is in the saddle shares its hide. Watched rather than read
    once: nothing is mounted when a trait arms."""
    _in_the_saddle(
        c,
        lambda who: [c.resist(20, DamageType.FIRE, until=When.ENCOUNTER, on=who)],
        c.ref,
    )


@power(
    "m347a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 7),
)
def m347a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m347a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.ZONE],
)
def m347a3(c: Cast) -> None:
    """It runs, and the ground it came off burns.

    `LeaveSquare` names each square as the mover goes, which is the only
    record of where a creature has been -- a zone built from `MoveEnd` would
    be one square long. The toll for entering is `c.burns`, which is the
    printed "any creature that enters the zone"; the toll for hitting it
    while it runs is a separate listener that lives only for the move, which
    is what "during this move" narrows it to. Ten feet tall is a vertical
    measurement and the grid is flat.
    """
    me = c.me
    behind: set[Square] = set()

    def vacated(ev: LeaveSquare) -> None:
        if ev.actor == me:
            behind.add(ev.square)

    def scorch(ev: Hit) -> None:
        if ev.target == me and ev.attacker != me and _reach_kind(ev) in _MELEE_KINDS:
            c.flat(10, dtype=DamageType.FIRE, on=ev.attacker)

    left = c.watch(LeaveSquare, vacated, until=When.EOT, on=me, label=f"{c.ref} squares")
    burn = c.watch(Hit, scorch, until=When.EOT, on=me, label=f"{c.ref} while running")
    try:
        c.move(c.speed_of())
    finally:
        c.world.effects.end(left, "the run is over")
        c.world.effects.end(burn, "the run is over")
    if behind:
        zone = c.zone(sorted(behind), label=_M347_TRAIL, until=When.EONT)
        c.burns(zone, 10, DamageType.FIRE)


@power(
    "m347a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m347a4(c: Cast) -> None:
    """The rider comes along without being named: `movement.step` carries a
    passenger wherever its mount arrives, and a teleport is a step."""
    c.teleport(c.speed_of())


# ==========================================================================
# m471
# ==========================================================================

_M471_BLED = "the m471 is first bloodied"
_M471_SEARED = "the m471 takes acid, cold, fire, lightning or thunder damage"


@power(
    "m471a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 8),
)
def m471a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m471a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m471a1(c: Cast) -> None:
    """A flying pass with one blow in it. Declared with no target: the
    creature it swings at may be eight squares away when it starts, and a
    target list is chosen before the body runs."""
    _flies_and_swings(c, c.speed_of(), "m471a0")


@power(
    "m471a2",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("3d10", 6, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
    trigger=_M471_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M471_BLED),
)
def m471a2(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m471a3",
    level=13,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M471_SEARED,
    on=Trigger(DamageApplied, when=_an_element_landed, text=_M471_SEARED),
)
def m471a3(c: Cast) -> None:
    """`uses=2` is the printed "2/Encounter". The card spells the row it
    replaces as another stat block's id; the one it plainly means is itself,
    which is what the hold is labelled with. A free action resolves after the
    blow, so the first hit of that type is taken in full and every later one
    is not."""
    _adapts(c, 10)


# ==========================================================================
# m4807
# ==========================================================================

_M4807_SEARED = "the m4807 takes acid, cold, fire, lightning or thunder damage"


def _felled_by_me(world: World, me: int, ev: Dropped) -> bool:
    """Whose blow put that creature down. `Dropped` names only the creature
    that fell, so the last damage it took is the only record of it -- and
    `query.enemies` filters out the dead, so the side is compared directly."""
    from combat_engine.engine.query import team

    if ev.actor == me or team(world, ev.actor) is team(world, me):
        return False
    for earlier in reversed(world.bus.log):
        if isinstance(earlier, DamageApplied) and earlier.target == ev.actor:
            return earlier.source == me
    return False


@power(
    "m4807a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
)
def m4807a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and the toll taken off whoever lands
    a melee blow from inside it. A close burst is a melee attack by the
    printed rule, which is what `_MELEE_KINDS` spells out."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def spatter(ev: Hit) -> None:
        if ev.target != me or ev.attacker == me or _reach_kind(ev) not in _MELEE_KINDS:
            return
        if ev.attacker in c.enemies() and ev.attacker in c.world.zones.occupants(ring):
            c.flat(5, dtype=DamageType.ACID, on=ev.attacker)

    c.watch(Hit, spatter, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4807a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 3),
)
def m4807a1(c: Cast) -> None:
    """One burn whose size is read as it lands, not two burns. Ongoing damage
    of one type does not stack -- the highest applies -- so the ten while
    bloodied supersedes a five already standing and the five is refused under
    a ten, which is the printed rule doing the arithmetic."""
    if c.strike():
        c.hit()
        c.ongoing(10 if c.bloodied(c.me) else 5, DamageType.ACID)


@power(
    "m4807a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 3),
)
def m4807a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m4807a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    requires=_drop_within(1),
    requires_text="the m4807 must have combat advantage against an adjacent enemy",
)
def m4807a3(c: Cast) -> None:
    """Both claws on one creature that cannot see them coming.

    The card spells the second as another stat block's id; the row every
    sentence plainly means is this creature's other claw. Both are reached
    through `use`, so each printed line stays in one place.

    Declared with no target: the printed line names a creature granting
    combat advantage, and the dispatcher aims at the nearest enemy -- which
    is a different creature most of the time, and leaves the row doing
    nothing at all.
    """
    open_to_it = sorted(
        foe
        for foe in c.enemies()
        if c.adjacent(foe) and has_combat_advantage(c.world, c.me, foe)
    )
    victim = c.choose(open_to_it, f"{c.ref}: which enemy") if open_to_it else None
    if victim is None:
        return
    for ref in ("m4807a1", "m4807a2"):
        if not alive(c.world, victim):
            return
        use(c.world, c.me, ref, targets=[victim], spend=False)


@power(
    "m4807a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
)
def m4807a4(c: Cast) -> None:
    """It throws somebody across the room and follows them there.

    No die at all in the header: the card prints a condition where the
    database files a number, and `actions.recharge` skips a row whose
    recharge is zero -- so the printed sentence is the only way this comes
    back. The step after is measured from where the victim has landed, which
    is why it is taken as a teleport to a named square rather than a distance.
    """
    me = c.me
    _recharge_on(c, Dropped, lambda ev: _felled_by_me(c.world, me, ev))
    victim = c.target
    if victim is None or not c.adjacent(victim):
        return
    c.teleport(7, who=victim)
    beside = _free_square_within(c, victim, 1)
    if beside:
        where = c.world.decide(me, "teleport", beside, f"{c.ref}: where it lands")
        c.teleport(max(1, distance(c.here, where)), to=where)
    c.grants_advantage(until=When.EONT, on=victim)


@power(
    "m4807a5",
    level=13,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4807_SEARED,
    on=Trigger(DamageApplied, when=_an_element_landed, text=_M4807_SEARED),
)
def m4807a5(c: Cast) -> None:
    """`uses=2` is the printed "2/Encounter", and the second use replaces the
    first rather than adding to it."""
    _adapts(c, 20)


# ==========================================================================
# m4912
# ==========================================================================


@power(
    "m4912a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4912a0(c: Cast) -> None:
    """Whoever is in the saddle is harder to hit for being there."""
    _in_the_saddle(
        c,
        lambda who: [c.bonus(AC, 2, until=When.ENCOUNTER, on=who, kind="untyped")],
        c.ref,
    )


@power(
    "m4912a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4912a1(c: Cast) -> None:
    """A miss next to this thing costs ten.

    The rider covers its rider as well as itself, which is read off the
    relation as the blow lands rather than when the trait arms -- a mount
    picks up and puts down riders all fight. The attacker has to be adjacent
    to the *mount*, which is what the printed line measures from.
    """
    me = c.me

    def backlash(ev: Miss) -> None:
        seat = c.rider()
        if ev.target not in (me, seat) or ev.attacker == me:
            return
        if _reach_kind(ev) not in _MELEE_KINDS or not c.adjacent(ev.attacker):
            return
        c.flat(10, on=ev.attacker)

    c.watch(Miss, backlash, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4912a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 7),
)
def m4912a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4912a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m4912a3(c: Cast) -> None:
    """The step comes first and the victim is whoever it ends up beside, so
    the row is declared with no target: the dispatcher aims before the body
    runs."""
    c.shift(max(1, c.speed_of() // 2))
    prey = _adjacent_foe(c, c.ref)
    if prey is not None:
        use(c.world, c.me, "m4912a2", targets=[prey], spend=False)


_M4912_HELD = "m4912a4 terror"


@power(
    "m4912a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
)
def m4912a4(c: Cast) -> None:
    """No damage line on the hit: the burn and the opening are the whole of
    it, and "save ends both" is one effect carrying them -- the advantage is
    held by the creature that grants it and cannot ride the same hold, so it
    is tied to it by the hold's ending.

    The save is refused while the victim stands beside one of these, which is
    `c.unsave` on the throw itself: `SavingThrow` is announced before it is
    acted on, and "any m4912" is two creatures off one stat block, which is
    `Ident.ref` and nothing else.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    me = c.me
    hold = c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=_M4912_HELD, ongoing=(10, DamageType.PSYCHIC)
    )
    open_to = c.grants_advantage(until=When.SAVE_ENDS, on=victim, to="allies")
    if open_to is not None:
        hold.on_end.append(lambda: c.world.effects.end(open_to, "the terror passed"))

    def pinned(ev: SavingThrow) -> None:
        if hold.ended or ev.actor != victim or _M4912_HELD not in ev.against:
            return
        if any(
            _same_stock(c.world, me, near)
            for near in c.within(1, of=victim)
            if near != victim
        ):
            c.unsave(ev)

    hold.subs.append(c.world.bus.on(SavingThrow, pinned, owner=me))


# ==========================================================================
# m4950
# ==========================================================================

_M4950_FELLED = "the m4950 drops to 0 hit points"


@power(
    "m4950a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m4950a0(c: Cast) -> None:
    """Whoever it catches unready burns for it.

    "Did that attack have combat advantage" is read off the roll -- asking
    the board again is too late, because a one-shot grant has been spent by
    the time the `Hit` is announced.
    """
    me = c.me

    def scorch(ev: Hit) -> None:
        if ev.attacker == me and c.had_advantage(ev):
            c.ongoing(10, DamageType.FIRE, on=ev.target)

    c.watch(Hit, scorch, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4950a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 5),
)
def m4950a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4950a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d10", 10),
)
def m4950a2(c: Cast) -> None:
    """A charge whose blow is this row's own line.

    `c.charge_at` cannot be used: it reaches the swing through `use` and the
    row it would reach for is this one, already in flight -- so the flag goes
    up by hand, `c.run_at` walks, and the header rolls. The flag is what puts
    `charge` on the attack events and in both modifier contexts, which is
    what every charge rider reads.
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
    "m4950a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d6", 7, kind=LIMITED),
)
def m4950a3(c: Cast) -> None:
    """It goes through everybody in the way.

    `c.overrun` is the only thing that reports who was trampled, and who was
    trampled is exactly who the printed line swings at. Called bare, it ranks
    the reachable squares by how many enemies the line crosses, so the run
    goes through people. The opportunity attacks are not waived -- the
    printed line expects them and charges ten for landing one -- and that
    listener lives only for the length of the run, which is what "provoked by
    this movement" narrows it to.
    """
    me = c.me

    def scorch(ev: Hit) -> None:
        if ev.target == me and ev.attacker != me and getattr(ev, "opportunity", False):
            c.flat(10, dtype=DamageType.FIRE, on=ev.attacker)

    burn = c.watch(Hit, scorch, until=When.EOT, on=me, label=f"{c.ref} while running")
    try:
        trampled = c.overrun()
    finally:
        c.world.effects.end(burn, "the run is over")
    for victim in trampled:
        if alive(c.world, victim) and c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)


@power(
    "m4950a4",
    level=13,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M4950_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4950_FELLED),
)
def m4950a4(c: Cast) -> None:
    """A death throe, and an interrupt because the card's Effect line says so.

    The dispatcher offers it to a creature that is no longer alive, which is
    the only way a row of this shape fires; `c.dying` is what carries the
    swing past the gate that would otherwise refuse it, and `use` reaches the
    row that prints the attack because this row is the one in flight, not
    that one.
    """
    me = c.me
    prey = _adjacent_foe(c, c.ref)
    if prey is None:
        return
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m4950a1":
            landed.append(ev.target)

    counter = c.watch(Hit, tally, until=When.EOT, on=me, label=f"{c.ref} tally")
    try:
        use(c.world, me, "m4950a1", targets=[prey], spend=False)
    finally:
        c.world.effects.end(counter, "the last blow is struck")
    if prey in landed:
        c.push(2, on=prey)
        c.prone(on=prey)


# ==========================================================================
# m709
# ==========================================================================

_M709_PHAGE = "m709a0 contagion"
_M709_BLED = "the m709 is first bloodied"


@power(
    "m709a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 2),
)
def m709a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means.

    The secondary is a second attack line against a different defence, so it
    cannot live in the header; its printed +16 is trimmed by hand the way
    `Attack.bonus_for` trims the header's. The contagion is a disease track
    the engine has no model of, so it is a named hold on the save-ends clock
    rather than an invented condition.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if c.attack(c.world.scaling.trim(16, c.level), FORT, on=victim):
        c.effect(_M709_PHAGE, until=When.SAVE_ENDS, on=victim)


@power(
    "m709a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("1d8", 2, kind=LIMITED),
)
def m709a2(c: Cast) -> None:
    """"The target shifts 3 squares" is the target moving under its own power
    rather than being slid, which is what `who=` says -- a slide of the same
    distance would be the m709 placing it and a different card."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.shift(3, who=victim)
    c.prone(on=victim)


@power(
    "m709a3",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M709_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M709_BLED),
)
def m709a3(c: Cast) -> None:
    """Insubstantial is a property of the creature rather than of the damage,
    and it runs to the end of its next turn, which is what the card
    measures."""
    c.teleport(8)
    c.insubstantial(until=When.EONT)
