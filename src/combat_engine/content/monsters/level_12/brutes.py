"""Monster abilities, level 12: the brutes.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=17)` and `Damage("3d10", 9)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

The conventions of the eleven levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; several rows the database files as standard actions
are plainly traits and are written as such; a stat block printing no range
at all means melee 1; a printed "Effect (Immediate Interrupt)" is
`action=INTERRUPT`, a printed "Effect (Immediate Reaction)" is
`ActionType.IMMEDIATE_REACTION`, and a printed "No Action" is `action=FREE`
-- whatever the database's action column says, and because `WINDOW_OF` maps
no window to `ActionType.NONE`, so a declared trigger on one could never be
offered at all; and a helper written for an earlier level is imported rather
than copied.

Seven things this file had to settle.

**Losing an attack instead of being dazed.** m198a2 refuses the condition
and remembers the debt. Refusing it is the *one* condition taken off the
hold that carried it rather than the hold ended, because "dazed and weakened
(save ends both)" is one hold and ending it would shake off the half the
card never touched; `Conditions` counts sources, so the count comes down by
one with it. The debt is a token with the solo's own clock, which m198a1
spends and a turn passing throws away -- "on its next turn" is a turn, not a
duration.

**No printed second initiative count.** m198 is solo and m212, m2877, m2982
and m3049 are elite, and not one of them prints a row that acts twice. None
is written: a second slot is a printed line, and inventing one for a card
that does not print it is inventing a card.

**Backing away from whoever burned it.** `c.flee` measures from the
*caster*, and the creature running in m212a0 is the caster -- so it would
run away from where it was standing rather than from the attacker. The path
is chosen here instead, every step of it further from the creature that
landed the blow, which is the printed sentence exactly.

**"It grants combat advantage" is read from the caster's side.**
`to="allies"` is the *caster's* own side, which is the wrong half of the
board when the creature granting the opening is the caster. The
beneficiaries are named one enemy at a time.

**A card that spells ids belonging to other stat blocks.** Every sentence on
m3097 names m723, and m3097a1 gives back "m1783a1". The creature is this
one, and the row it gives back is its own expendable attack -- the only
thing on the block there is to regain.

**Ongoing damage of one type does not stack.** m3097a2 lays 10 on a hit and
5 on a miss; `c.ongoing` refuses the weaker one and hands back the standing
one, so a miss on a creature already burning from the hit adds nothing.
That is the printed rule and not a row that failed.

**`Bloodied` about itself cannot fire on the audit board**, which sets the
caster to half hit points before the fight starts. m2826a3 is such a row and
reports UNUSED however correct it is; it was driven by hand, at full health,
to check. See the report.

Each stat block in ref order.
"""

from __future__ import annotations

from itertools import pairwise

from combat_engine.content.monsters.level_04.skirmishers import _struck
from combat_engine.content.monsters.level_07.brutes import _crit_line
from combat_engine.content.monsters.level_07.soldiers import _hands_free, _recharge_on
from combat_engine.content.monsters.level_08.brutes import _aura, _has_hold, _holding, _is_bloodied
from combat_engine.content.monsters.level_09.brutes import _regenerates, _volley
from combat_engine.content.monsters.level_10.soldiers import _moved_into_flank
from combat_engine.content.monsters.level_11.soldiers import _charge
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
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
    Conditions,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Powers,
    Square,
    Usage,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    ConditionEnded,
    DamageApplied,
    Dropped,
    ForcedMove,
    Hit,
    Miss,
    MoveEnd,
    MoveStart,
    OpportunityWindow,
    TurnStart,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.movement import walk
from combat_engine.engine.query import alive, squares, team
from combat_engine.engine.triggers import Trigger, about_me, ally_within

#: What m198a2 answers. The printed line names these two and nothing else.
_DULLED = (Condition.DAZED, Condition.STUNNED)

#: One attack the m198 owes. Labelled rather than counted in a closure,
#: because the row that takes the debt on and the row that pays it are two
#: rows and the board is the only thing they share.
_M198_LOST = "m198a2 lost"

#: The three rows m5004a5 pays out on.
_M5004_BLOWS = ("m5004a0", "m5004a1", "m5004a3")


def _in_reach(c: Cast, radius: int, ref: str) -> int | None:
    """Somebody to swing at, for a row that attacks more than once."""
    near = sorted(
        foe for foe in c.enemies() if c.distance(foe) <= radius and alive(c.world, foe)
    )
    return c.choose(near, f"{ref}: which enemy") if near else None


def _refuse(c: Cast, who: int, cond: Condition) -> None:
    """Take one condition off a creature and leave the rest of its hold alone.

    Ending the effect is the level 8 shape and the wrong one here: a hold
    reading "dazed and weakened (save ends both)" carries two conditions and
    only one of them is being refused. `Conditions` counts sources, so the
    condition comes off the effect that imposed it and the count comes down
    with it.
    """
    conds = c.world.get(who, Conditions)
    for eff in list(c.world.effects.of(who)):
        if cond not in eff.conditions:
            continue
        eff.conditions = tuple(k for k in eff.conditions if k is not cond)
        if conds is not None and conds.remove(cond):
            c.world.bus.emit(ConditionEnded(target=who, condition=cond, why=c.ref))


def _exposed(c: Cast, until: When) -> None:
    """The caster itself grants combat advantage, to everybody who wants it.

    `to="allies"` is the caster's own side, which is exactly the wrong half
    of the board for a printed line about the caster dropping its guard, so
    the beneficiaries are named one enemy at a time.
    """
    for foe in sorted(c.enemies()):
        c.grants_advantage(on=c.me, to=foe, until=until)


def _back_away(c: Cast, from_whom: int, budget: int) -> int:
    """Walk up to `budget` squares, every step further from that creature.

    `c.flee` is the same sentence measured from the caster, and the creature
    running here *is* the caster -- it would run from where it was standing
    rather than from whoever hit it. Paths are read in sorted order so the
    same seed walks the same way twice.
    """
    theirs = squares(c.world, from_whom)
    if not theirs or budget <= 0:
        return 0

    def gap(sq: Square) -> int:
        return min(distance(sq, s) for s in theirs)

    best: list[Square] = []
    for _dest, path in sorted(c.world.reachable_paths(c.me, budget).items()):
        if not path or len(path) <= len(best):
            continue
        steps = [c.here, *path]
        if all(gap(b) > gap(a) for a, b in pairwise(steps)):
            best = list(path)
    return walk(c.world, c.me, best) if best else 0


def _trample(c: Cast, budget: int) -> list[int]:
    """Walk that far through whoever is in the way, and say who that was.

    A bare `c.overrun()` ranks its own destinations but spends the creature's
    plain speed, and a printed line that walks further has to rank them
    itself -- offered in plain sorted order the answer with no decider
    installed is the lowest corner of the board, which tramples nobody.
    """
    reach = c.world.reachable_squares(c.me, budget)
    if not reach:
        return []
    here = squares(c.world, c.me)
    foes = sorted(c.enemies())

    def in_the_way(dest: Square) -> int:
        span = min(distance(sq, dest) for sq in here)
        return sum(
            1
            for foe in foes
            if any(
                min(distance(sq, f) for sq in here) + distance(f, dest) == span
                for f in squares(c.world, foe)
            )
        )

    lines = sorted(reach, key=lambda sq: (-in_the_way(sq), sq))
    where = c.world.decide(c.me, "overrun", lines, f"{c.ref}: trample to")
    return c.overrun(to=where)


# ==========================================================================
# m198
# ==========================================================================


@power(
    "m198a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 5),
)
def m198a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m198a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m198a1(c: Cast) -> None:
    """Four bites, less whatever m198a2 has taken off this turn.

    Declared with no target: each bite picks from whoever is in reach at the
    time, and four of them can empty the squares in front of it. The debts
    are spent as they are counted, so a turn in which it bites twice does
    not pay the same daze twice.
    """
    owed = [eff for eff in c.world.effects.of(c.me) if eff.label == _M198_LOST][:4]
    for eff in owed:
        c.world.effects.end(eff, "an attack given up")
    for _ in range(4 - len(owed)):
        victim = _in_reach(c, 2, c.ref)
        if victim is None:
            return
        use(c.world, c.me, "m198a0", targets=[victim], spend=False)


@power(
    "m198a2",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m198a2(c: Cast) -> None:
    """Dazing a solo this size only costs it a bite.

    Filed as a standard action and plainly a trait: nobody chooses to shrug
    off a stun. The condition is refused as it lands -- one condition off
    the hold that carried it, not the hold ended, since "dazed and weakened"
    is one saving throw and only half of it is being waived -- and a token
    is laid for the attack that is owed. "Multiple such effects stack" is
    why it is a token per condition rather than a flag.
    """
    me = c.me

    def shrug(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition not in _DULLED:
            return
        _refuse(c, me, ev.condition)
        c.world.effects.apply(me, me, When.EONT, label=_M198_LOST)

    c.watch(ConditionApplied, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m198a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m198a3(c: Cast) -> None:
    """Two squares of threat rather than one.

    `c.threatens` widens the opening the window is measured against, which
    is the direction this rule runs: everything within its reach is
    something it can answer, rather than more answers than a round allows.
    """
    c.threatens(2)


# ==========================================================================
# m212
# ==========================================================================


_M212_HURT = "an attack damages the m212 while it is bloodied"


def _hurt_while_bloodied(world: World, me: int, ev: DamageApplied) -> bool:
    """Damage from an *attack*: a zone or a burn it is carrying is not one,
    and `detail` naming a row is the only thing that tells them apart."""
    return (
        ev.target == me
        and ev.amount > 0
        and get(ev.detail or "") is not None
        and _is_bloodied(world, me)
    )


@power(
    "m212a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m212a0(c: Cast) -> None:
    """Fire makes it bolt, and a corner it cannot bolt out of leaves it open.

    "From an attack" is read off `detail`, which names the row that dealt
    the damage -- the standing burn it walked into does not set it running.
    The run is its own movement, so it provokes on the way out, which is the
    point of the printed line.
    """
    me = c.me

    def bolt(ev: DamageApplied) -> None:
        if ev.target != me or ev.dtype is not DamageType.FIRE or ev.amount <= 0:
            return
        if get(ev.detail or "") is None:
            return
        pace = c.speed_of()
        if _back_away(c, ev.source, pace) * 2 < pace:
            _exposed(c, When.EONT)

    c.watch(DamageApplied, bolt, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m212a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m212a1(c: Cast) -> None:
    """Lightning wakes it up rather than hurting it.

    `c.basic` swings whatever this creature's basic attack actually is,
    which for a monster is one of its own rows, and the free action costs it
    nothing out of its own turn.
    """
    me = c.me

    def answer(ev: DamageApplied) -> None:
        if ev.target != me or ev.dtype is not DamageType.LIGHTNING or ev.amount <= 0:
            return
        victim = _in_reach(c, 2, c.ref)
        if victim is not None:
            c.basic(on=victim)

    c.watch(DamageApplied, answer, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m212a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d10", 9),
)
def m212a2(c: Cast) -> None:
    """"+17, or +19 while bloodied" is the printed line plus two rather than
    a second attack line: two bonuses of one kind do not add, so a gated one
    beside the header's own would have been invisible."""
    if c.strike(plus=2 if c.bloodied(c.me) else 0):
        c.hit()


@power(
    "m212a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m212a3(c: Cast) -> None:
    """Two swings of the row that prints the line, and whatever they land on
    goes down. Which of them hit cannot be read off `use`, which reports
    that a row could be used and not that it landed."""
    for victim in sorted(set(_struck(c, "m212a2", 2))):
        c.prone(on=victim)


@power(
    "m212a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m212a4(c: Cast) -> None:
    """It walks over whoever is standing in the way.

    `c.overrun` is the only thing that reports who was trampled, and who was
    trampled is exactly what the printed line attacks -- but the walk is two
    squares longer than its speed, which the bare call would not reach, so
    the destination is ranked here. Nothing waives the opportunity attacks:
    the printed line does not.
    """
    for victim in _trample(c, c.speed_of() + 2):
        if victim in c.enemies() and alive(c.world, victim):
            use(c.world, c.me, "m212a2", targets=[victim], spend=False)


@power(
    "m212a5",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M212_HURT,
    on=Trigger(DamageApplied, when=_hurt_while_bloodied, text=_M212_HURT),
)
def m212a5(c: Cast) -> None:
    """A wounded construct swings at whatever is nearest to hand.

    "A random target" is genuinely random and not the attacker: the printed
    line is the thing flailing. Declared with no target, because the
    dispatcher would aim it at whoever caused the damage.
    """
    near = sorted(
        foe for foe in c.enemies() if c.distance(foe) <= 2 and alive(c.world, foe)
    )
    if near:
        victim = c.world.rng.choice(near)
        use(c.world, c.me, "m212a2", targets=[victim], spend=False)


# ==========================================================================
# m2826
# ==========================================================================


_M2826_FLANKED = "a creature moves into a space where it flanks the m2826"
_M2826_BLED = "the m2826 is first bloodied"


@power(
    "m2826a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 6),
)
def m2826a0(c: Cast) -> None:
    """The charge die is rolled rather than added flat, so a critical maxes
    it along with the rest; `c.charge` is the flag the engine raises for the
    whole of the run and the swing."""
    if c.strike():
        c.hit()
        if c.charge:
            c.damage("1d10")


@power(
    "m2826a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 6),
    trigger=_M2826_FLANKED,
    on=Trigger(MoveEnd, when=_moved_into_flank, text=_M2826_FLANKED),
)
def m2826a1(c: Cast) -> None:
    """`MoveEnd`, not `MoveStart`: the question is about the square the
    creature arrived in. Filed as a move action and printed as an immediate
    reaction; the trigger line is what says which it is, and the dispatcher
    aims a single-enemy row at whoever the event was about."""
    if c.strike():
        c.hit()


@power(
    "m2826a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m2826a2(c: Cast) -> None:
    """The printed recharge sits on top of the die the database files, and
    `Bloodied` is emitted on the crossing and nowhere else, so "first" needs
    no guard of its own.

    The Special is noted rather than written: what a charge swings with is
    `Powers.basic`, and there is no second slot for a row a charge may reach
    for instead.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        if c.charge:
            c.damage("1d10")
        c.push(2)
        c.prone()
    c.note("m2826a2: when charging, it may swing this in place of a melee basic attack")


@power(
    "m2826a3",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 6, kind=LIMITED),
    trigger=_M2826_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2826_BLED),
)
def m2826a3(c: Cast) -> None:
    """One swing the moment it is hurt. The event is about the m2826 itself,
    so the dispatcher passes no target and the header's own reach picks
    one."""
    if c.strike():
        c.hit()
        c.push(2)


# ==========================================================================
# m2877
# ==========================================================================


@power(
    "m2877a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 4),
)
def m2877a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2877a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(3),
    target=NO_TARGET,
)
def m2877a1(c: Cast) -> None:
    """One sweep of the reach, at everybody standing in it.

    Declared with no target and the row that prints the line swung once per
    enemy, rather than a close burst: the printed sentence measures its
    reach, which is three squares of melee and not an area.
    """
    for foe in sorted(c.within(3, side="enemy")):
        if alive(c.world, foe):
            use(c.world, c.me, "m2877a0", targets=[foe], spend=False)


@power(
    "m2877a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d6", 5, kind=LIMITED),
)
def m2877a2(c: Cast) -> None:
    """The grip breaks at range, which is a place and not a clock -- so the
    hold carries the ordinary saving throw and a watch on the victim's own
    turn beginning ends it early when it has got far enough away."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    ridden = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if ridden is None:
        return

    def slip(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim or ridden.ended:
            return
        if c.distance(victim) > 3:
            c.world.effects.end(ridden, "out of reach")

    ridden.subs.append(c.world.bus.on(TurnStart, slip, owner=c.me))


# ==========================================================================
# m2982
# ==========================================================================


_M2982_BLED = "the m2982 is first bloodied"
_M2982_FELLED = "the m2982 drops to 0 hit points"


@power(
    "m2982a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m2982a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2982a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2982a1(c: Cast) -> None:
    """Two swings at two creatures, and the daze only if both land.

    The header takes one target and the second is picked here, because
    `UpTo(2)` would call the body twice and "if both attacks hit" is a
    question about the pair. With nobody else in reach it swings once, which
    is the only thing left to do.
    """
    first = c.target
    if first is None:
        return
    others = sorted(
        foe
        for foe in c.enemies()
        if foe != first and c.distance(foe) <= 2 and alive(c.world, foe)
    )
    second = c.choose(others, f"{c.ref}: the other target") if others else None
    landed = _struck(c, "m2982a0", 1, first)
    if second is not None:
        landed += _struck(c, "m2982a0", 1, second)
    if len(landed) == 2:
        for victim in landed:
            c.dazed(until=When.EONT, on=victim)


@power(
    "m2982a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("4d8", 6, kind=LIMITED),
)
def m2982a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2982a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=f"{_M2982_BLED}, {_M2982_FELLED}",
    on=(
        Trigger(Bloodied, when=about_me, text=_M2982_BLED),
        Trigger(Dropped, when=about_me, text=_M2982_FELLED),
    ),
)
def m2982a3(c: Cast) -> None:
    """Twice a fight, and the second time is on the way down.

    "If the power is not expended" is asked by trying it: `use` refuses a
    spent row and says so, which is the same question without a second copy
    of the bookkeeping. The trigger goes with both attempts, because a
    creature answering its own downfall is only allowed to act at all while
    the engine can see that is what it is doing.
    """
    if use(c.world, c.me, "m2982a2", trigger=c.trigger):
        return
    victim = _in_reach(c, 2, c.ref)
    if victim is not None:
        use(c.world, c.me, "m2982a0", targets=[victim], spend=False, trigger=c.trigger)


@power(
    "m2982a4",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2982a4(c: Cast) -> None:
    """Swinging at it as it goes past costs blood whether or not the swing
    lands: the printed line is about making the attack, so it is read off
    `AttackDeclared` rather than the `Hit` -- which carries the flag too and
    would charge only for the ones that connect."""
    me = c.me

    def backlash(ev: AttackDeclared) -> None:
        if ev.target == me and getattr(ev, "opportunity", False):
            c.damage("2d6", on=ev.attacker, detail=c.ref)

    c.watch(AttackDeclared, backlash, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3049
# ==========================================================================


_M3049_STRUCK = "the m3049 damages an enemy"
_M3049_MATE_STRUCK = "an ally within 10 squares of the m3049 damages an enemy"


def _damaged_a_foe(world: World, me: int, ev: DamageApplied) -> bool:
    return (
        ev.source == me
        and ev.amount > 0
        and ev.target != me
        and team(world, ev.target) is not team(world, me)
    )


def _ally_damaged_a_foe(world: World, me: int, ev: DamageApplied) -> bool:
    """An ally of mine hurt an enemy of mine, within ten squares.

    `ally_within` reads the creature the event is *about*, and a
    `DamageApplied` has no `actor` at all -- it falls through to the target,
    which is the creature that was hurt, so the question it would answer is
    the wrong one twice over.
    """
    from combat_engine.engine.query import distance_between

    who = ev.source
    return (
        who != me
        and ev.amount > 0
        and team(world, who) is team(world, me)
        and team(world, ev.target) is not team(world, me)
        and distance_between(world, me, who) <= 10
    )


@power(
    "m3049a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d4", 6),
)
def m3049a0(c: Cast) -> None:
    """The five is a second packet on creatures the attack never targeted,
    so it is flat damage rather than anything the header could carry. "Each
    creature adjacent to the target" is everybody standing there, the
    m3049's own side included -- it is a club, and the printed line names no
    side. The m3049 itself is left out: it is the one swinging.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    for other in sorted(c.within(1, of=victim, side="any")):
        if other not in (victim, c.me) and alive(c.world, other):
            c.flat(5, on=other)


@power(
    "m3049a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m3049a1(c: Cast) -> None:
    """A swing, a step, and a swing at somebody else.

    Declared with no target: the step is there to bring a second creature
    into reach, so who the second blow can land on is not known until it has
    been taken. Both blows are the row that prints the line, which keeps its
    damage in one place.
    """
    first = _in_reach(c, 2, c.ref)
    if first is None:
        return
    use(c.world, c.me, "m3049a0", targets=[first], spend=False)
    c.shift(1)
    others = sorted(
        foe
        for foe in c.enemies()
        if foe != first and c.distance(foe) <= 2 and alive(c.world, foe)
    )
    second = c.choose(others, f"{c.ref}: the other target") if others else None
    if second is not None:
        use(c.world, c.me, "m3049a0", targets=[second], spend=False)


@power(
    "m3049a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("5d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3049a2(c: Cast) -> None:
    """Necrotic *and* poison: the header keeps the first of the two printed
    types and both keywords carry the rest. The two weaknesses are two
    holds, because a vulnerability is named per damage type and a creature
    can be open to both at once."""
    if c.first:
        me = c.me
        _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if not c.strike():
        return
    c.hit()
    c.vulnerable(5, DamageType.NECROTIC, until=When.EONT)
    c.vulnerable(5, DamageType.POISON, until=When.EONT)


@power(
    "m3049a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
    trigger=_M3049_STRUCK,
    on=Trigger(DamageApplied, when=_damaged_a_foe, text=_M3049_STRUCK),
)
def m3049a3(c: Cast) -> None:
    """No damage line at all: the opening is the whole of the hit, and it is
    the m3049's own -- "grants combat advantage to the m3049" names one
    beneficiary, which is what `to="me"` already is."""
    if c.strike():
        c.grants_advantage(until=When.EONT)


@power(
    "m3049a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3049_MATE_STRUCK,
    on=Trigger(DamageApplied, when=_ally_damaged_a_foe, text=_M3049_MATE_STRUCK),
)
def m3049a4(c: Cast) -> None:
    """The ally that struck the blow is the one rewarded, so it is read off
    the event rather than picked: the row has no target of its own and the
    dispatcher aims nothing at a `NO_TARGET` row."""
    friend = getattr(c.trigger, "source", None)
    if friend is not None:
        c.temp_hp(5, on=friend)


@power(
    "m3049a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3049a5(c: Cast) -> None:
    """A disguise and a contest of two skills, and neither is a thing the
    engine rolls: appearance is not modelled, and there is no Bluff to be
    beaten by an Insight check. Deliberately inert rather than given an
    invented combat effect."""
    c.note("m3049a5: it can appear as any Medium or Large humanoid")


# ==========================================================================
# m3097
# ==========================================================================
#
# Every sentence on this card spells the creature's id as one belonging to a
# different stat block, and m3097a1 gives back a row belonging to a third.
# This creature is the one they plainly mean, and the row it gives back is
# its own expendable attack -- the only thing on the block to regain.


_M3097_DOUSED = "m3097a0 doused"
_M3097_FELLED = "the m3097 drops to 0 hit points"

#: The two damage types that stop the regeneration, as the card prints them.
_SEARING = (DamageType.ACID, DamageType.FIRE)


@power(
    "m3097a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3097a0(c: Cast) -> None:
    """Regeneration, and the two damage types that switch it off for a turn.

    The helper is level 9's: "whenever it starts its turn and has at least 1
    hit point" is `hp > 0` rather than `alive`, which is the printed line
    saying it does not knit itself back together once it is down.
    """
    me = c.me
    _regenerates(c, 5, _M3097_DOUSED)

    def douse(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype in _SEARING and ev.amount > 0:
            c.effect(_M3097_DOUSED, until=When.EONT, on=me)

    c.watch(DamageApplied, douse, until=When.ENCOUNTER, on=me, label=f"{c.ref} doused")


@power(
    "m3097a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d10", 9),
)
def m3097a1(c: Cast) -> None:
    """Bloodying something gives it its big swing back.

    "Bloodies the target" is the crossing and not the state, so it is asked
    on both sides of the blow -- a target that was already bloodied gives
    nothing back.
    """
    was = c.bloodied()
    if not c.strike():
        return
    c.hit()
    known = c.world.get(c.me, Powers)
    if not was and c.bloodied() and known is not None:
        known.restore("m3097a2")


@power(
    "m3097a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d10", 5, kind=LIMITED, half_on_miss=True),
)
def m3097a2(c: Cast) -> None:
    """The miss lays a weaker burn of the same type than the hit does, and
    only the highest of one type applies -- so a miss on a creature already
    burning from this row adds nothing and hands back what it is carrying,
    which is the printed stacking rule rather than a line that failed."""
    if c.strike():
        c.hit()
        c.ongoing(10)
    else:
        c.hit(half=True)
        c.ongoing(5)


@power(
    "m3097a3",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("4d6", 7, kind=LIMITED),
    trigger=_M3097_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M3097_FELLED),
)
def m3097a3(c: Cast) -> None:
    """It comes apart, and everything standing near it is caught.

    A creature may answer its own downfall -- the dispatcher makes the
    exception for exactly this shape. "No Action" is written as a free
    action: there is no cheaper cost in the engine, and a row with no
    window at all could never be offered.

    "The m3097 is destroyed" has nowhere to go: dropping to 0 leaves a
    creature dying rather than dead, and nothing finishes one off. Noted.
    """
    if c.strike():
        c.hit()
    if c.first:
        c.note("m3097a3: it is destroyed")


# ==========================================================================
# m434
# ==========================================================================


@power(
    "m434a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 4),
)
def m434a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The swarm's resistance and its weakness are numbers and load from
    the database like every other one."""
    if c.strike():
        c.hit()
        c.ongoing(5)


# ==========================================================================
# m4898
# ==========================================================================


@power(
    "m4898a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4898a0(c: Cast) -> None:
    """Standing next to it is enough to be off balance.

    The opening is offered to the m4898's whole side, which is what a
    printed "grant combat advantage" with nobody named means. The aura
    helper is the right one: the hold is carried for exactly as long as its
    owner is inside, and entering and leaving are the two moments it should
    go on and come off.
    """

    def eligible(who: int) -> bool:
        return who in c.enemies()

    def hold(who: int) -> Effect | None:
        return c.grants_advantage(on=who, to="allies", until=When.ENCOUNTER)

    _aura(c, 1, eligible, hold)


@power(
    "m4898a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4898a1(c: Cast) -> None:
    """Not `c.no_provoke`, which waives the window outright: the printed line
    waives it only while the creature is on a wall, so the opening is refused
    as it opens and only then. `Movement.using` is set before the first step,
    so the question is true for the whole climb."""
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        if ev.provoker == me and c.moving_as("climb"):
            ev.cancel(c.ref)

    c.watch(
        OpportunityWindow,
        veto,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )


@power(
    "m4898a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d12", 10),
)
def m4898a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4898a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d12", 6, kind=LIMITED),
)
def m4898a3(c: Cast) -> None:
    """One row, four swings: the printed Effect says the attack below is made
    four times, so the declared line is rolled four times rather than another
    row being reached for -- this one's damage is its own and lighter than
    m4898a2's. Each swing picks its own creature, since the printed line
    names none."""
    for _ in range(4):
        victim = _in_reach(c, 2, c.ref)
        if victim is None:
            return
        if c.strike(on=victim):
            c.hit(on=victim)


# ==========================================================================
# m4949
# ==========================================================================


_M4949_FELLED = "the m4949 drops to 0 hit points"


@power(
    "m4949a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6),
)
def m4949a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4949a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_hands_free,
    requires_text="the m4949 must not have a creature grabbed",
)
def m4949a1(c: Cast) -> None:
    """Both blows on one creature, and it has hold of it if both land.

    The Requirement is a fact about the caster and so belongs in the header.
    Whether both hit cannot be read off `use`, which reports that a row could
    be used and not that it landed, so `_volley` counts them off the bus.
    """
    victim = c.target
    if victim is not None and _volley(c, "m4949a0", victim):
        c.grab(on=victim)


@power(
    "m4949a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m4949a2(c: Cast) -> None:
    """The row *is* the charge, so the flag goes up by hand and the header
    rolls: `c.charge_at` reaches its swing through `use`, and the row it
    would reach for is this one, already in flight."""
    victim = c.target
    if victim is None:
        return

    def blow() -> None:
        if c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)

    _charge(c, victim, blow)


@power(
    "m4949a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 6, kind=LIMITED),
    requires=_has_hold,
    requires_text="the m4949 must have a creature grabbed",
)
def m4949a3(c: Cast) -> None:
    """"One creature grabbed by the m4949" is narrower than any `Target` can
    say, so the Requirement carries the caster's half and the body picks.

    The printed recharge is on the *end of the turn* after a miss; the row is
    given back as the miss lands, which is the earliest the two can differ
    and never the wrong way -- and the header's die stays, because that is
    what the card shows.

    "Dazed and weakened (save ends both)" is one hold carrying both, which
    is what makes it one saving throw. The 20 hit points are healing and not
    a surge: no printed line here spends one.
    """
    me, ref = c.me, c.ref
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == ref)
    held = sorted(_holding(c.world, me))
    victim = c.choose(held, f"{ref}: which of them it savages") if held else None
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.condition(Condition.DAZED, Condition.WEAKENED, until=When.SAVE_ENDS, on=victim)
    c.heal(20, on=me)


@power(
    "m4949a4",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M4949_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4949_FELLED),
)
def m4949a4(c: Cast) -> None:
    """One last gore as it goes down.

    The trigger is handed to the swing as well: `use` only makes the
    exception for a creature answering its own downfall when it can see that
    is what is happening, and a killing blow that overshoots leaves the
    m4949 unable to act for the very reason this row exists.
    """
    me = c.me
    victim = _in_reach(c, 1, c.ref)
    if victim is None:
        return
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m4949a0":
            landed.append(ev.target)

    counter = c.watch(Hit, tally, until=When.EOT, on=me, label=f"{c.ref} tally")
    try:
        use(c.world, me, "m4949a0", targets=[victim], spend=False, trigger=c.trigger)
    finally:
        c.world.effects.end(counter, "the blow has landed")
    for who in landed:
        c.dazed(until=When.EOTNT, on=who)


# ==========================================================================
# m5004
# ==========================================================================


_M5004_SHOVED = "an enemy is pushed, pulled or slid next to the m5004"
_M5004_MATE_BLED = "an ally within 3 squares of the m5004 is first bloodied"
_M5004_BIT = "the m5004 hits with m5004a0, m5004a1 or m5004a3"


def _shoved_beside_me(world: World, me: int, ev: AdjacencyGained) -> bool:
    """An enemy was pushed, pulled or slid into a square next to this one.

    Forced movement steps like any other, so the adjacency it makes is
    announced the same way -- but `ForcedMove` is emitted and both its
    windows are done *before* the first step, so a reaction declared on it
    would resolve where nothing has moved yet. How the creature got there is
    read back off the log instead: a walk, a shift and a teleport all
    announce `MoveStart` first and a shove announces `ForcedMove`, so
    whichever came last is what it is doing.

    `AdjacencyGained` is emitted mirrored, and this is the half whose
    `actor` is the creature that moved -- not `closed_on_me`, which accepts
    either half and so fired on a neighbour's adjacency as readily as on
    this creature's. It is also the half the dispatcher can aim: it reads
    `actor`, which here is the creature that was shoved.
    """
    mover = getattr(ev, "mover", 0)
    if ev.other != me or mover != ev.actor or mover == me:
        return False
    if team(world, mover) is team(world, me):
        return False
    for past in reversed(world.bus.log[: ev.seq]):
        if isinstance(past, MoveStart) and past.actor == mover:
            return False
        if isinstance(past, ForcedMove) and past.target == mover:
            return True
    return False


def _its_own_blow(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power in _M5004_BLOWS


def _psychic_on_me(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.dtype is DamageType.PSYCHIC and ev.amount > 0


@power(
    "m5004a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d10", 7),
)
def m5004a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5004a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d8", 7),
)
def m5004a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5004a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d10", 3, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5004a2(c: Cast) -> None:
    """The printed recharge sits on top of the die the database files, and
    the two only ever agree to give the row back sooner. The weakness is to
    everything rather than to one type, which is `c.vulnerable` with no type
    named; the miss leaves the same weakness on a shorter clock."""
    if c.first:
        _recharge_on(c, DamageApplied, lambda ev: _psychic_on_me(c.world, c.me, ev))
    if c.strike():
        c.hit()
        c.vulnerable(5, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.vulnerable(5, until=When.EONT)


@power(
    "m5004a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d12", 6),
    trigger=_M5004_SHOVED,
    on=Trigger(AdjacencyGained, when=_shoved_beside_me, text=_M5004_SHOVED),
)
def m5004a3(c: Cast) -> None:
    """Anything shoved into its space gets bitten for it."""
    if c.strike():
        c.hit()


@power(
    "m5004a4",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M5004_MATE_BLED,
    on=Trigger(Bloodied, when=ally_within(3), text=_M5004_MATE_BLED),
)
def m5004a4(c: Cast) -> None:
    """Declared with no target: the event is about an ally, so the
    dispatcher's aim would point the bite at the wrong creature -- the row
    picks from whoever is actually in reach."""
    victim = _in_reach(c, 1, c.ref)
    if victim is not None:
        use(c.world, c.me, "m5004a0", targets=[victim], spend=False)


@power(
    "m5004a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger=_M5004_BIT,
    on=Trigger(Hit, when=_its_own_blow, text=_M5004_BIT),
)
def m5004a5(c: Cast) -> None:
    """The extra dice ride on the blow being answered, so they are dealt to
    whoever it landed on and rolled rather than added flat."""
    if c.first:
        _recharge_on(c, DamageApplied, lambda ev: _psychic_on_me(c.world, c.me, ev))
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("2d8", dtype=DamageType.PSYCHIC, on=victim)


# ==========================================================================
# m648
# ==========================================================================


@power(
    "m648a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 3),
)
def m648a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The printed "crit 2d12 + 15" *replaces* the damage and is a roll,
    so it is dealt flat, past the engine's own rule that a critical maxes
    the declared dice; the fire is a second packet and is rolled, so a
    critical maxes that one."""
    if c.strike():
        _crit_line(c, "2d12", 15)
        c.damage("1d10", dtype=DamageType.FIRE)


@power(
    "m648a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 3, kind=LIMITED),
    requires_text="the m648 must be wielding a greataxe",
)
def m648a1(c: Cast) -> None:
    """The printed Requirement names a weapon, and a monster in this engine
    carries no `Gear` -- `c.wielding` answers for a character's kit and is
    false for every stat block there is. It is carried as the printed text so
    the card shows it, and not as a gate, which would refuse the row for a
    reason about the engine rather than the board."""
    if c.strike():
        _crit_line(c, "2d12", 15)
        c.damage("1d10", dtype=DamageType.FIRE)
        c.ongoing(10, DamageType.FIRE)


# ==========================================================================
# m661
# ==========================================================================


@power(
    "m661a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 12),
)
def m661a0(c: Cast) -> None:
    """"Or 4d8 + 15 while bloodied" is a second expression rather than a
    rider, so the header keeps the printed line and the other is rolled
    here; the two points on the attack are a plus rather than a bonus,
    because two bonuses of one kind do not add."""
    hard = c.bloodied(c.me)
    if not c.strike(plus=2 if hard else 0):
        return
    if hard:
        c.damage("4d8", 15)
    else:
        c.hit()
