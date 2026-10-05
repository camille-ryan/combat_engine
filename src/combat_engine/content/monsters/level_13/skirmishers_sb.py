"""Monster abilities, level 13: a second sweep of the ones that move.

`skirmishers.py` holds the first pass over this level and `skirmishers_sa.py`
one row that needed a verb; neither is touched. Numbers load from `game.db`,
so the attack and damage lines here are written exactly as the stat block
prints them -- `Attack(vs=AC, printed=18)`, `Damage("2d6", 7)` -- and the
engine takes the level term back out and rescales the dice.

The conventions of the file beside this one are kept: a row the database files
under an action heading that is plainly a **trait** is declared
`ActionType.NONE`; a stat block printing no range at all means melee 1; a
cross-referenced id is read as the row every sentence plainly means, which is
this creature's own; and **a row that both moves and swings takes the swing
first where there is anything in reach**, because the movement picks its own
destination and one taken first can leave the target behind.

Nine readings this file had to settle.

**A printed attack named by word is read back to a ref.** Several cards here
say "it makes two of *X* attacks" where *X* is one of the creature's own
lines. The row is identified by its numbers and nothing else: where a block
prints two melee lines and the card asks for the heavier one twice, the
heavier one is the ref used, and the judgement is written on the row.

**The parity veil is rolled on the blows that would land.** m115673a0 turns a
hit aside on an odd attack roll. `resolve.attack` recomputes the outcome from
the live `AttackResult` after `AttackRolled`, so a listener there has nothing
to change; `result.hit` set to False inside the `Hit` interrupt window is
turned into a real `Miss` by the engine's own `confirm` callback, and that
`Miss` is the event m115673a7 answers. The parity read is `result.natural`,
which is the die and not the total.

**A trail is a straight line, not a list of departures.** `movement.shift`
places the creature at its destination rather than walking it, so
`LeaveSquare` names the square it started in and nothing between. m5545a3
lays its flames along `c.line(start, end)` instead, which is the run the card
describes. Its own 20 fire from the database is what makes the printed
"nonfire creature" true without anything being written for it.

**"Ends its move 4 squares from where it started" is measured from
`MoveStart`.** `MoveEnd` carries only the arrival, so the departure square is
read where `_after_moving` reads it, and only on the creature's own turn -- a
push is movement and is not its move.

**A mount and its rider swapping damage has to be guarded.** `c.absorb` is
the only verb that moves a blow that has been rolled and not yet dealt, and
it *deals* the blow again -- so without a re-entrancy flag the pair bounce one
hit between them forever. Whether the blow moves is `c.may`: the card prints
a choice and no rule decides it.

**"The target cannot make opportunity attacks" is said from the other end.**
`c.no_provoke` is keyed on the **provoker** -- `on=` is who may walk away
freely -- so the sentence is laid once per creature on this one's own side.
That is complete rather than approximate: an opportunity attack is only ever
made against an enemy.

**A condition applied "instead" goes through `c.cure`.** m1487a6 trades a daze
for a lost attack. Rewriting `eff.conditions` after the fact strands the
original, and `ConditionApplied` fires from inside the handover, so the
sanctioned path is to let it land and take it off -- which is what `c.cure`
is, and which is why the row also lays its own hold for the next turn to
count.

**"Ends its turn without moving" is read off `Budget`.** Nothing records
whether a creature moved, and `Budget.move` is refreshed at `TurnStart` and
spent by a move or a shift -- so a creature that still has it at `TurnEnd`
stood still. A charge moves without spending it, which is the one case this
reading gets wrong and the only one.

**An escape DC is not a number this engine holds.** `escape.attempt` measures
the check against the grabber's own Reflex or Fortitude by design, and
`escape.py` says so; a printed "escape DC 20" has no column and is not a gap.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from combat_engine.content.monsters.level_02.skirmishers import _advantage_rider
from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_06.skirmishers import _after_moving
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_09.skirmishers import _free_square_within
from combat_engine.content.monsters.level_10.brutes import _same_stock
from combat_engine.content.monsters.level_10.skirmishers import _in_the_saddle
from combat_engine.content.monsters.level_11.lurkers import _breathe_again
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
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
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Bloodied,
    Budget,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Damage,
    DamageApplied,
    DamageRolled,
    DamageType,
    Effect,
    EffectApplied,
    Health,
    Hit,
    Initiative,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Ranged,
    Size,
    Square,
    Trigger,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    distance,
    power,
    targets_me,
    use,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    adjacent,
    alive,
    allies,
    distance_between,
    enemies,
    flanked_by,
)
from combat_engine.engine.triggers import about_me, both, by_charge, by_me, by_melee
from combat_engine.engine.types import Relation

#: Which printed ranges count as a melee attack for a rider that says so.
#: Narrower than the tuple a level down, which folds in close bursts and
#: blasts: every card in this file that narrows a rider says "melee attacks",
#: and a close burst is not one.
_MELEE_ONLY = ("melee",)

#: The conditions that hold a creature fast, for the rows that answer one.
_PINNED = (Condition.GRABBED, Condition.IMMOBILIZED, Condition.RESTRAINED)

#: Everything Large or smaller, for a printed "a Large or smaller target".
#: `Size` is a `StrEnum`, so comparing two of them sorts alphabetically and
#: says nothing -- membership is the only honest test.
_LARGE_OR_SMALLER = (Size.TINY, Size.SMALL, Size.MEDIUM, Size.LARGE)


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _foe_within(c: Cast, reach: int, *, exclude: Sequence[int] = ()) -> int | None:
    """Somebody in reach to swing at, for a row that attacks more than once.

    `_adjacent_foe` a level down measures one square, which is wrong for a
    creature whose arms are three long: the row would find nobody with the
    victim plainly inside its reach.
    """
    near = sorted(
        foe
        for foe in c.enemies()
        if foe not in exclude and alive(c.world, foe) and c.distance(foe) <= reach
    )
    return c.choose(near, f"{c.ref}: which enemy") if near else None


def _swing_and_move(c: Cast, ref: str, reach: int, move: Callable[[], None]) -> None:
    """"At any point during the movement it uses <ref>."

    The swing goes first where there is anything in reach, because the move
    picks its own destination and one taken first can leave the only target
    behind; with nothing in reach it moves and then looks again, which is the
    same printed sentence read the other way round.
    """
    victim = _foe_within(c, reach)
    if victim is not None:
        c.use_power(ref, on=victim, spend=False)
        move()
        return
    move()
    victim = _foe_within(c, reach)
    if victim is not None:
        c.use_power(ref, on=victim, spend=False)


def _labelled(c: Cast, label: str, *, on: int | None = None) -> bool:
    """Is that hold standing? Several rows here are a named state."""
    who = on if on is not None else c.me
    return any(eff.label == label for eff in c.world.effects.of(who))


def _drop_held(c: Cast, label: str, why: str, *, on: int | None = None) -> None:
    """Take every hold of that label off, if any is standing."""
    who = on if on is not None else c.me
    for eff in list(c.world.effects.of(who)):
        if eff.label == label:
            c.world.effects.end(eff, why)


def _takes_a_form(c: Cast, *forms: tuple[str, ...]) -> None:
    """A polymorph whose only combat content is which rows it locks out.

    Each printed form is the set of this creature's own attack refs it cannot
    use while wearing it, which is the whole of what the card says changes.
    The form is a labelled hold so a second use replaces the first rather
    than stacking two sets of locks, and the locks come off with it.
    """
    me = c.me
    for eff in list(c.world.effects.of(me)):
        if eff.label.startswith(f"{c.ref} form "):
            c.world.effects.end(eff, "it changes shape again")
    pick = c.choose(list(range(len(forms))), f"{c.ref}: which form")
    if pick is None:
        return
    hold = c.effect(f"{c.ref} form {pick}", until=When.ENCOUNTER, on=me)
    locked = [
        eff
        for ref in forms[pick]
        if (eff := c.forbid(ref, on=me, until=When.ENCOUNTER)) is not None
    ]

    def release() -> None:
        for eff in locked:
            c.world.effects.end(eff, "it changes shape again")

    if hold is not None:
        hold.on_end.append(release)


def _shared_hide(c: Cast, level: int) -> None:
    """"Damage dealt to either one can be redirected to the other."

    Guarded, because `c.absorb` deals the blow again and an unguarded pair
    pass one hit back and forth forever. `c.may` owns the choice: the card
    prints one and no rule settles it.
    """
    me = c.me

    def arm(rider: int) -> list[Effect | None]:
        busy: list[int] = []

        def swap(ev: DamageRolled) -> None:
            if busy or ev.amount <= 0:
                return
            if ev.target == me:
                other = rider
            elif ev.target == rider:
                other = me
            else:
                return
            if not c.may(f"{c.ref}: move the damage", who=me):
                return
            busy.append(1)
            try:
                c.absorb(ev, on=other)
            finally:
                busy.clear()

        return [
            c.watch(
                DamageRolled, swap, until=When.ENCOUNTER,
                window=Window.BEFORE, on=me, label=c.ref,
            )
        ]

    _in_the_saddle(c, arm, c.ref, level=level)


def _long_stride(c: Cast) -> None:
    """"If it ends its move 4 squares from where it started, +2d6 melee."

    The departure square is only on `MoveStart`, which is where
    `_after_moving` reads it, and the clause is its own move -- a push is
    movement and is not that. The gate is the damage context's `ranged`,
    which is how "melee attacks" is asked on that side.
    """
    me = c.me

    def paid(_kind: str, start: Square | None, end: Square, _steps: int) -> None:
        if start is None or c.turn_of() != me or distance(start, end) < 4:
            return
        if _labelled(c, f"{c.ref} far", on=me):
            return
        c.effect(f"{c.ref} far", until=When.SONT, on=me)
        c.bonus(
            "damage", 0, dice="2d6", on=me, until=When.SONT,
            when=lambda ctx: not ctx.get("ranged"),
        )

    _after_moving(c, paid)


def _moved_to_flank(world: World, me: int, ev: MoveEnd) -> bool:
    """"An enemy moves to a square where it flanks it."

    Asked on `MoveEnd`, not `MoveStart`: the flank is a fact about where the
    creature finished, and before the first step nothing has happened yet.
    """
    return (
        ev.actor != me
        and ev.actor in enemies(world, me)
        and flanked_by(world, me, ev.actor)
    )


def _no_opportunities(c: Cast, victim: int, until: When) -> None:
    """"The target cannot make opportunity attacks."

    `c.no_provoke` is keyed on the provoker, so the sentence is laid once per
    creature on this one's own side. That is the whole of it rather than most
    of it: an opportunity attack is only made against an enemy.
    """
    for mine in [c.me, *c.allies()]:
        c.no_provoke(from_=victim, on=mine, until=until)


def _astral_step(c: Cast) -> None:
    """Ten squares, and whoever is in the saddle goes too."""
    c.teleport(10, share=True)


# ==========================================================================
# m1093
# ==========================================================================


@power(
    "m1093a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 7),
)
def m1093a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1093a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 7),
    dropped=("c.contract(ref)",),
)
def m1093a1(c: Cast) -> None:
    """The burn is exact; catching the disease is the dropped half. A disease
    is a track rolled between encounters and the engine keeps none."""
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m1093a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d12", 5),
)
def m1093a2(c: Cast) -> None:
    """The long range is the card's second number and the engine keeps one:
    the short range is what a monster shoots at."""
    if c.strike():
        c.hit()


@power(
    "m1093a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1093a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Whether the target was already bloodied is read on the `Hit`, which is
    emitted before the damage is applied -- so the question is asked of the
    creature the blow was aimed at and not of what the blow left.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or _reach_kind(ev) not in _MELEE_ONLY:
            return
        if c.bloodied(on=ev.target):
            c.flat(4, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m1093a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m1093a4(c: Cast) -> None:
    """Two forms, and the only thing either changes is what it may swing.

    The first locks out the melee line that carries the disease; the second
    locks out the reach line and the ranged one, which is the pair the card
    takes away in the other shape.
    """
    _takes_a_form(c, ("m1093a1",), ("m1093a0", "m1093a2"))


@power(
    "m1093a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1093a5(c: Cast) -> None:
    """Untyped: the card prints no word in front of "bonus". The gate is the
    attack context's `opportunity`, which is set on every swing taken in an
    opportunity window."""
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m1093a6",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m1093a6(c: Cast) -> None:
    """Names the nearest enemy, and one blow against it lands harder.

    "One of its attacks" is a single payout, so the rider closes over a flag
    rather than riding every hit; designating again ends the standing pair,
    which is what "or the m1093 designates a new quarry" says.
    """
    me, ref = c.me, c.ref
    near = sorted(c.enemies(), key=lambda foe: (c.distance(foe), foe))
    if not near:
        return
    prey = near[0]
    _drop_held(c, f"{ref} quarry", "a new quarry")
    _drop_held(c, f"{ref} rider", "a new quarry")
    c.quarry(on=prey, until=When.ENCOUNTER)
    paid: list[int] = []

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target != prey or paid:
            return
        paid.append(1)
        c.damage("2d6", on=prey, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=f"{ref} rider")


@power(
    "m1093a7",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1093a7(c: Cast) -> None:
    """Untyped, and asked inside the gate rather than taken as a snapshot:
    who is nearest changes between the minor action and the shot."""
    me = c.me

    def alone(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or not ctx.get("ranged"):
            return False
        mine = distance_between(c.world, me, foe)
        return all(distance_between(c.world, mate, foe) >= mine for mate in c.allies())

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=alone)


# ==========================================================================
# m115673
# ==========================================================================

#: The veil, held as a labelled effect so the row that answers a miss and the
#: row that puts it back are asking the same question rather than each
#: keeping a flag of its own.
_M115673_VEIL = "m115673a0 veil"
_M115673_MISSED = "an attack misses the m115673"


@power(
    "m115673a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m115673a0(c: Cast) -> None:
    """An odd attack roll finds the wrong thing; an even one gets through.

    The coin is the die itself, read off the live `AttackResult` as
    `natural` -- the total would fold in every modifier, and the card names
    the roll. Set inside the `Hit` interrupt window, because `resolve.attack`
    recomputes the outcome from that object afterwards and turns `hit=False`
    into a real `Miss`; a listener on `AttackRolled` has nothing to change.

    Only melee and ranged attacks, which is what the card names. The blow
    that gets through takes the veil down, and the start of its next turn
    puts it back.
    """
    me = c.me

    def raise_it() -> None:
        if not _labelled(c, _M115673_VEIL, on=me):
            c.effect(_M115673_VEIL, until=When.ENCOUNTER, on=me)

    def blur(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.target != me or ev.attacker == me or result is None:
            return
        if not _labelled(c, _M115673_VEIL, on=me):
            return
        if _reach_kind(ev) not in ("melee", "ranged"):
            return
        if result.natural % 2:
            result.hit = False
            return
        _drop_held(c, _M115673_VEIL, "the blow found it", on=me)

    def dawn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            raise_it()

    raise_it()
    c.watch(Hit, blur, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=c.ref)
    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} back")


@power(
    "m115673a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_squeeze_speed()",),
)
def m115673a1(c: Cast) -> None:
    """Difficult terrain is exact. The squeezing half is narrower than any
    lever the engine has: `Condition.SQUEEZING` is half speed, -5 to attack
    and combat advantage in one hold, and the card waives only the speed.
    Taking the whole condition off would hand it two things nobody printed.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m115673a2",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115673a2(c: Cast) -> None:
    c.threatens(3, on=c.me, until=When.ENCOUNTER)


@power(
    "m115673a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 7),
)
def m115673a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115673a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d12", 10),
)
def m115673a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115673a5",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115673a5(c: Cast) -> None:
    """A shift of half its speed with one or two swings of the reach line
    somewhere in it. The swings go first where there is anything in reach;
    the second has to be a different creature, which is what the card says.
    """
    half = max(1, c.speed_of() // 2)
    struck: list[int] = []
    for _ in range(2):
        victim = _foe_within(c, 3, exclude=struck)
        if victim is None:
            break
        struck.append(victim)
        c.use_power("m115673a3", on=victim, spend=False)
    c.shift(half)
    if len(struck) < 2:
        victim = _foe_within(c, 3, exclude=struck)
        if victim is not None:
            c.use_power("m115673a3", on=victim, spend=False)


@power(
    "m115673a6",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 7, kind=LIMITED, half_on_miss=True),
)
def m115673a6(c: Cast) -> None:
    """The printed "recharge when first bloodied" rides on top of the 6+ the
    database files: the two only ever agree to make the row available
    sooner."""
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()
        c.slide(3)
    else:
        c.hit(half=True)
        c.slide(1)


@power(
    "m115673a7",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M115673_MISSED,
    on=Trigger(Miss, targets_me, _M115673_MISSED),
)
def m115673a7(c: Cast) -> None:
    """One square and a swing of the reach line, in either order. A miss the
    veil caused is a real `Miss`, so this answers that one too."""
    _swing_and_move(c, "m115673a3", 3, lambda: c.shift(1))


# ==========================================================================
# m115765
# ==========================================================================

_PSIONIC_WEAPON = [Keyword.PSYCHIC, Keyword.WEAPON]


@power(
    "m115765a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m115765a0(c: Cast) -> None:
    """Whether the blow had combat advantage is `ev.result.advantage`, read
    off the `Hit`: asking the board again is too late, because a one-shot
    grant has already been spent by then. The extra die is typed, which is
    why this is written out rather than shared with the untyped riders."""
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.attacker != me or result is None or not result.advantage:
            return
        c.damage("2d8", on=ev.target, dtype=DamageType.PSYCHIC, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m115765a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_PSIONIC_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 12, dtype=DamageType.PSYCHIC),
)
def m115765a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115765a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_PSIONIC_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 12, dtype=DamageType.PSYCHIC),
)
def m115765a2(c: Cast) -> None:
    """The Effect line is not under the Hit line, so the step is taken
    whether or not the blow lands."""
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m115765a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=_PSIONIC_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d8", 14, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m115765a3(c: Cast) -> None:
    """"It can shift up to its speed before making the second attack" is the
    clause that reaches the second creature, so the step is taken only when
    the second one is not already in reach -- taken anyway it would as often
    walk out of reach of the target the chooser had already picked."""
    if not c.first and not c.adjacent():
        c.shift(c.speed_of())
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m115765a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115765a4(c: Cast) -> None:
    c.shift(2)


@power(
    "m115765a5",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115765a5(c: Cast) -> None:
    """Either itself or one ally within 10. The flight is a mode granted for
    the turn and then walked at, which is the only way a creature with no fly
    speed of its own covers ground in the air."""
    options = [c.me, *(mate for mate in c.allies() if c.distance(mate) <= 10)]
    who = c.choose(sorted(options), f"{c.ref}: who flies")
    if who is None:
        return
    c.mode("fly", 5, until=When.EOT, on=who)
    c.move(5, who=who, at="fly")


# ==========================================================================
# m115917
# ==========================================================================

_POISON_WEAPON = [Keyword.POISON, Keyword.WEAPON]


@power(
    "m115917a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_POISON_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 7),
    dropped=("c.cannot_mark()",),
)
def m115917a0(c: Cast) -> None:
    """The burn is exact. "Cannot mark enemies" has no lever: `c.mark` lays a
    mark and nothing withholds the ability to lay one, and `c.forbid` takes a
    *row* away rather than what a row does."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m115917a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=_POISON_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d4", 6),
)
def m115917a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m115917a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115917a2(c: Cast) -> None:
    """Shakes a mark, then four squares with one of its two attack lines
    somewhere in the middle. Which line is a choice, because one is melee and
    the other reaches ten squares and the card offers both."""
    c.cure(Condition.MARKED, on=c.me)
    ref = c.choose(["m115917a0", "m115917a1"], f"{c.ref}: which attack")
    if ref is None:
        return
    _swing_and_move(c, ref, 1 if ref == "m115917a0" else 10, lambda: c.shift(4))


# ==========================================================================
# m1289
# ==========================================================================


@power(
    "m1289a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7),
)
def m1289a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1289a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 6),
)
def m1289a1(c: Cast) -> None:
    """Two swings, which the card lets fall on one creature or two, so the
    header carries the printed line and the body rolls it per target rather
    than reaching for `c.basic` -- the printed numbers are the basic attack's
    and they are right here. "Before, between, or after" is taken as before,
    which is the one of the three that can reach a second creature."""
    if c.first:
        c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m1289a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7, kind=LIMITED),
)
def m1289a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


@power(
    "m1289a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=5),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=17),
    dropped=("c.conceal(square=)",),
)
def m1289a3(c: Cast) -> None:
    """No damage is printed on the Hit line, so nothing is dealt -- the blind
    is the whole consequence and `c.hit` with no declared damage would raise.

    The zone stands for the rest of the encounter and carries nothing:
    "lightly obscured" is concealment, which is a -2 an attacker takes and
    hangs on a *creature*; there is no way to hang one on a square.
    `blocks_sight` would be the wrong word for it -- that is a wall.
    """
    if c.strike():
        c.blinded(until=When.EONT)
    if not c.first:
        return
    area = c.area()
    if area:
        c.zone(area, until=When.ENCOUNTER, label=c.ref)


@power(
    "m1289a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1289a4(c: Cast) -> None:
    """The whole printed benefit is a Stealth penalty it does not take, and
    no Stealth check is rolled on a board. Finished and deliberately inert
    rather than unwritten."""


@power(
    "m1289a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1289a5(c: Cast) -> None:
    """"Any target it has combat advantage against" and "any target granting
    it combat advantage" are the same sentence from the two ends."""
    _advantage_rider(c, "2d6", _MELEE_ONLY)


# ==========================================================================
# m1441
# ==========================================================================


@power(
    "m1441a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7),
)
def m1441a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1441a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1441a1(c: Cast) -> None:
    """The extra swing rides on the rider's charge, so it is armed when
    somebody mounts and taken back when they get off -- nothing is in the
    saddle when a trait arms. The only melee line this block prints is the
    one the extra attack can be.

    `AttackDeclared` is the window: "in addition to its rider's charge
    attack" is beside that attack and not after its outcome. The guard stops
    the swing -- which is an attack -- from answering itself.
    """
    me = c.me

    def arm(rider: int) -> list[Effect | None]:
        busy: list[int] = []

        def extra(ev: AttackDeclared) -> None:
            if busy or ev.attacker != rider or not getattr(ev, "charge", False):
                return
            busy.append(1)
            try:
                c.use_power("m1441a0", on=ev.target, spend=False)
            finally:
                busy.clear()

        return [
            c.watch(AttackDeclared, extra, until=When.ENCOUNTER, on=me, label=c.ref)
        ]

    _in_the_saddle(c, arm, c.ref, level=13)


@power(
    "m1441a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d12", 12, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1441a2(c: Cast) -> None:
    """A close blast catches everything in front of it and the card does not
    say "enemies", so the side is everyone **other** than the creature
    breathing: `EACH_CREATURE` would put it in its own blast."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


_M1441_BLOODIED = "it is first bloodied"


@power(
    "m1441a3",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M1441_BLOODIED,
    on=Trigger(Bloodied, about_me, _M1441_BLOODIED),
)
def m1441a3(c: Cast) -> None:
    """`Bloodied` is emitted on the crossing and nowhere else, so "first"
    needs no guard of its own."""
    _breathe_again(c, "m1441a2")


@power(
    "m1441a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1441a4(c: Cast) -> None:
    _astral_step(c)


@power(
    "m1441a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1441a5(c: Cast) -> None:
    """Both directions, which is what "and vice versa" adds."""
    _shared_hide(c, 13)


@power(
    "m1441a6",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1441a6(c: Cast) -> None:
    _long_stride(c)


# ==========================================================================
# m1487
# ==========================================================================


@power(
    "m1487a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d4", 5),
)
def m1487a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1487a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
)
def m1487a1(c: Cast) -> None:
    """Three swings of the reach line, so the numbers live there and this row
    declares none of its own -- the spec's own attack line for this row has
    no defence in it and is not a line that can be written down.

    m1487a6 is the other half: each daze or stun traded away costs one of
    the three, and the holds it leaves are what that costs.
    """
    victim = c.target
    if victim is None:
        return
    lost = sum(1 for eff in c.world.effects.of(c.me) if eff.label == "m1487a6 lost")
    for _ in range(max(0, 3 - lost)):
        if not alive(c.world, victim):
            return
        use(c.world, c.me, "m1487a0", targets=[victim], spend=False)


@power(
    "m1487a2",
    level=13,
    usage=ENCOUNTER,
    uses=2,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=16),
)
def m1487a2(c: Cast) -> None:
    """No damage on the Hit line, so nothing is dealt and `c.hit` is never
    called: the burn and the daze are the consequence, and "save ends both"
    is one hold carrying the two."""
    if c.strike():
        c.condition(
            Condition.DAZED, until=When.SAVE_ENDS,
            ongoing=(10, DamageType.UNTYPED),
        )


@power(
    "m1487a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.SLEEP],
    attack=Attack(vs=FORT, printed=16),
)
def m1487a3(c: Cast) -> None:
    if c.strike():
        c.unconscious(until=When.SAVE_ENDS)


@power(
    "m1487a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1487a4(c: Cast) -> None:
    """It takes on whatever the blast found.

    The type is read off the victim's live resistances rather than chosen
    from a list the card does not print, and the card says "choose one" where
    there are several. Nothing says a later adaptation replaces an earlier
    one, so they accumulate -- resistances of different types stack anyway.
    """
    me, ref = c.me, c.ref

    def adapted(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m1487a2":
            return
        kinds = sorted(
            (d for d, n in c.resistances(on=ev.target).items() if n > 0), key=str
        )
        if not kinds:
            return
        dtype = c.choose(kinds, f"{ref}: which resistance")
        if dtype is None:
            return
        c.resist(10, dtype, until=When.ENCOUNTER, on=me)
        c.deals(dtype, until=When.ENCOUNTER, on=me)

    c.watch(Hit, adapted, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m1487a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("conditions.Rules.wake_on_damage",),
)
def m1487a5(c: Cast) -> None:
    """The clause turns off a rule the engine does not have.

    `conditions.RULES[Condition.UNCONSCIOUS]` has no wake-on-damage term and
    nothing in `resolve.deal_damage` ends an unconscious hold, so there is
    nothing here to suppress and nothing to write. Marked rather than left
    looking finished: the day damage does wake a sleeper, this row has work
    to do and the symbol goes red.
    """


@power(
    "m1487a6",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1487a6(c: Cast) -> None:
    """A daze or a stun becomes a lost swing instead.

    "Instead" cannot be written by editing the live effect: `Effects.apply`
    reads `conditions` once, to count them in, and `ConditionApplied` is
    emitted from inside that handover -- so a rewrite there strands the
    original. `c.cure` is the sanctioned path, and the hold it leaves is what
    m1487a1 counts. Multiple holds stack, which is the printed line.
    """
    me = c.me

    def instead(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition not in (Condition.DAZED, Condition.STUNNED):
            return
        if not c.cure(ev.condition, on=me):
            return
        c.effect("m1487a6 lost", until=When.EONT, on=me)

    c.watch(ConditionApplied, instead, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1516
# ==========================================================================


@power(
    "m1516a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 6),
)
def m1516a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1516a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 6),
)
def m1516a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10)


@power(
    "m1516a2",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("4d8", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m1516a2(c: Cast) -> None:
    """Two types in two sentences: the blow is poison and the burn is acid,
    and they are separate because resistance reads them separately."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m1516a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m1516a3(c: Cast) -> None:
    """No damage is printed, so nothing is dealt. The printed "recharges on a
    critical hit with any attack" rides on top of the 6+ the database
    files."""
    if c.first:
        _recharge_on(c, Hit, lambda ev: ev.attacker == c.me and ev.critical)
    if c.strike():
        c.slide(3)


# ==========================================================================
# m2055
# ==========================================================================


@power(
    "m2055a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 4),
)
def m2055a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m2055a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m2055a1(c: Cast) -> None:
    """Two swings of the only melee line this block prints, so the numbers
    stay on that row."""
    victim = c.target
    if victim is None:
        return
    for _ in range(2):
        if not alive(c.world, victim):
            return
        use(c.world, c.me, "m2055a0", targets=[victim], spend=False)


@power(
    "m2055a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d12", 6),
)
def m2055a2(c: Cast) -> None:
    """"Targets a bloodied creature" is a restriction `Target` cannot carry,
    so the row is redirected rather than thrown away: somebody else in reach
    may qualify where the chooser's pick does not.

    The heavier line is a second expression and not a second header, so it is
    rolled here: 3d12 and a weakening against a creature already held fast.
    """
    victim = c.target
    if victim is None or not c.bloodied(on=victim):
        victim = next(
            (foe for foe in sorted(c.enemies()) if c.bloodied(on=foe) and c.adjacent(foe)),
            None,
        )
    if victim is None:
        return
    held = c.is_(Condition.IMMOBILIZED, on=victim)
    if not c.strike(on=victim):
        return
    if held:
        c.damage("3d12", 6, on=victim)
        c.weakened(until=When.SAVE_ENDS, on=victim)
    else:
        c.hit(on=victim)


@power(
    "m2055a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2055a3(c: Cast) -> None:
    """The card names another block's id for the creature that arrives; the
    only creature every sentence can mean is this one."""
    c.teleport(6)
    for foe in sorted(c.enemies()):
        if c.adjacent(foe):
            c.dazed(until=When.EONT, on=foe)


# ==========================================================================
# m2637
# ==========================================================================


@power(
    "m2637a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7),
)
def m2637a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2637a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 7),
)
def m2637a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2637a2",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2637a2(c: Cast) -> None:
    """Three extra swings on the rider's charge, each at a different foe.

    The card asks for two of one line and one of the other; the lighter of
    the two melee lines is read as the pair, which is the reading the sibling
    block a few refs up settles -- its single extra swing is the heavier
    line, so the heavier one is the single here too.
    """
    me = c.me

    def arm(rider: int) -> list[Effect | None]:
        busy: list[int] = []

        def extra(ev: AttackDeclared) -> None:
            if busy or ev.attacker != rider or not getattr(ev, "charge", False):
                return
            busy.append(1)
            try:
                struck: list[int] = []
                for ref in ("m2637a1", "m2637a1", "m2637a0"):
                    victim = next(
                        (
                            foe
                            for foe in sorted(c.enemies())
                            if foe not in struck and c.distance(foe) <= 2
                        ),
                        None,
                    )
                    if victim is None:
                        return
                    struck.append(victim)
                    c.use_power(ref, on=victim, spend=False)
            finally:
                busy.clear()

        return [
            c.watch(AttackDeclared, extra, until=When.ENCOUNTER, on=me, label=c.ref)
        ]

    _in_the_saddle(c, arm, c.ref, level=13)


_M2637_FLANKED = "an enemy moves to a square where it flanks the m2637"


@power(
    "m2637a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d10", 7),
    trigger=_M2637_FLANKED,
    on=Trigger(MoveEnd, _moved_to_flank, _M2637_FLANKED),
)
def m2637a3(c: Cast) -> None:
    """Filed as a move action and printed as an immediate reaction. Aimed off
    the trigger rather than at the chooser's pick: the card says "targets
    triggering enemy", and an enemy that did not move into the flank is not
    that one."""
    victim = getattr(c.trigger, "actor", None) or c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.prone(on=victim)
        c.shift(2)


@power(
    "m2637a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d12", 12, dtype=DamageType.FIRE, kind=LIMITED),
)
def m2637a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


_M2637_BLOODIED = "it is first bloodied"


@power(
    "m2637a5",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M2637_BLOODIED,
    on=Trigger(Bloodied, about_me, _M2637_BLOODIED),
)
def m2637a5(c: Cast) -> None:
    """At-will in the database and "when first bloodied" on the card, which
    agree: `Bloodied` is emitted on the crossing and nowhere else."""
    _breathe_again(c, "m2637a4")


@power(
    "m2637a6",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2637a6(c: Cast) -> None:
    _astral_step(c)


@power(
    "m2637a7",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2637a7(c: Cast) -> None:
    _shared_hide(c, 13)


@power(
    "m2637a8",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2637a8(c: Cast) -> None:
    _long_stride(c)


# ==========================================================================
# m3258
# ==========================================================================


@power(
    "m3258a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d4", 5),
)
def m3258a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3258a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d4", 10),
)
def m3258a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3258a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("4d4", 10, kind=LIMITED),
    requires_text="requires the weapon this stat block carries",
)
def m3258a2(c: Cast) -> None:
    """The printed Requirement names the weapon the block already carries, so
    it is satisfied by construction and a `Gear` gate would refuse the row
    forever -- a monster has none.

    The size limit is a membership test: `Size` is a `StrEnum`, so comparing
    two of them sorts words. The sustain hold is what the payout hangs from;
    the grab itself needs no sustaining in this engine, which keeps it until
    somebody escapes.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.size_of(on=victim) not in _LARGE_OR_SMALLER:
        return
    c.grab(on=victim)
    # Not `f"{ref} grab"`: that is the label `c.grab` already uses, and two
    # holds of one name on one creature make the payout unfindable.
    held = c.effect(f"{c.ref} squeeze", until=When.SUSTAIN, on=victim, sustain=MINOR)

    def squeeze() -> None:
        c.damage("2d4", 10, on=victim)

    c.on_sustain(held, squeeze)


@power(
    "m3258a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    requires_text="requires the weapon this stat block carries",
)
def m3258a3(c: Cast) -> None:
    """Two swings of the reach line, so its numbers stay there. `c.use_power`
    rather than `use`, because the printed "if both attacks hit" needs the
    borrowed row's result and that is what it leaves in `c.result`."""
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        if not alive(c.world, victim):
            break
        c.use_power("m3258a0", on=victim, spend=False)
        landed += 1 if c.landed else 0
    if landed < 2 or not alive(c.world, victim):
        return
    if c.choose(["slide", "prone"], f"{c.ref}: which") == "prone":
        c.prone(on=victim)
    else:
        c.slide(1, on=victim)


@power(
    "m3258a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3258a4(c: Cast) -> None:
    """No range is named, so every attack it makes."""
    _advantage_rider(c, "2d6")


_M3258_HIT = "it hits with a melee attack"


@power(
    "m3258a5",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3258_HIT,
    on=Trigger(Hit, both(by_me, by_melee), _M3258_HIT),
)
def m3258a5(c: Cast) -> None:
    c.shift(1)


_M3258_CHARGE = "it charges"


@power(
    "m3258a6",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3258_CHARGE,
    on=Trigger(AttackDeclared, both(by_me, by_charge), _M3258_CHARGE),
)
def m3258a6(c: Cast) -> None:
    """One ally runs in at the same creature. The target comes off the
    trigger rather than off a chooser: "the same target" is an instruction."""
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    near = sorted(mate for mate in c.allies() if c.distance(mate) <= 5)
    mate = c.choose(near, f"{c.ref}: which ally") if near else None
    if mate is not None:
        c.charge_at(victim, who=mate)


_M3258_SAVEABLE = "it is subjected to an effect that a save can end"


def _save_ends_on_me(world: World, me: int, ev: EffectApplied) -> bool:
    """`EffectApplied` is the only event a save-ends hold carrying nothing but
    ongoing damage announces; `ConditionApplied` fires for half of them."""
    return ev.target == me and ev.save_ends


@power(
    "m3258a7",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3258_SAVEABLE,
    on=Trigger(EffectApplied, _save_ends_on_me, _M3258_SAVEABLE),
)
def m3258a7(c: Cast) -> None:
    """`on=c.me`: the row is `NO_TARGET`, and `c.save` follows `c.target`
    first. `against` names the hold that has just landed, so the throw is
    made against that one and not against whichever save-ends effect is
    oldest."""
    c.save(on=c.me, against=getattr(c.trigger, "label", ""))


# ==========================================================================
# m3841
# ==========================================================================


@power(
    "m3841a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 8),
)
def m3841a0(c: Cast) -> None:
    """The step is under the Hit line, so it is taken only on a hit."""
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m3841a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d4", 6),
)
def m3841a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3841a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3841a2(c: Cast) -> None:
    """The melee line, two squares, then the thrown one -- in the printed
    order, because this one names where the step goes rather than leaving it
    to be read either way."""
    victim = _foe_within(c, 1)
    if victim is not None:
        c.use_power("m3841a0", on=victim, spend=False)
    c.shift(2)
    mark = _foe_within(c, 5)
    if mark is not None:
        c.use_power("m3841a1", on=mark, spend=False)


@power(
    "m3841a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 8, kind=LIMITED),
)
def m3841a3(c: Cast) -> None:
    """The ally's swing is aimed explicitly: `c.basic`'s `who` is who swings
    and `on` is who gets hit, and without the second it would fall on
    whatever this row's own target happens to be."""
    if not c.strike():
        return
    c.hit()
    near = sorted(c.allies())
    mate = c.choose(near, f"{c.ref}: which ally") if near else None
    if mate is None:
        return
    c.shift(1, who=mate)
    mark = next(
        (foe for foe in sorted(c.enemies()) if adjacent(c.world, mate, foe)), None
    )
    if mark is not None:
        c.basic(who=mate, on=mark)


# ==========================================================================
# m3843
# ==========================================================================


@power(
    "m3843a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_POISON_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6),
)
def m3843a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


@power(
    "m3843a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d6", 4),
    dropped=("c.contract(ref)",),
)
def m3843a1(c: Cast) -> None:
    """As m1093a1: the burn lands, the disease has no verb to carry it."""
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m3843a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=_POISON_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 6, dtype=DamageType.POISON),
)
def m3843a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3843a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3843a3(c: Cast) -> None:
    """Two swings of the poisoned melee line on one creature, three squares,
    two more on somebody else."""
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    first = _foe_within(c, 1)
    if first is not None:
        for _ in range(2):
            if alive(c.world, first):
                c.use_power("m3843a0", on=first, spend=False)
    c.shift(3)
    second = _foe_within(c, 1, exclude=[first] if first is not None else [])
    if second is not None:
        for _ in range(2):
            if alive(c.world, second):
                c.use_power("m3843a0", on=second, spend=False)


@power(
    "m3843a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m3843a4(c: Cast) -> None:
    """Two forms, and only one of them takes anything away: the melee line
    that carries the disease. The other locks out nothing, which is the whole
    of what the card says about it."""
    _takes_a_form(c, (), ("m3843a1",))


@power(
    "m3843a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3843a5(c: Cast) -> None:
    _advantage_rider(c, "2d6", _MELEE_ONLY)


# ==========================================================================
# m3948
# ==========================================================================


@power(
    "m3948a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_POISON_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 7),
)
def m3948a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3948a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_POISON_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7),
)
def m3948a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3948a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3948a2(c: Cast) -> None:
    """One swing of each melee line. The card names them by weapon and the
    block prints two: the heavier dice are the first named."""
    for ref in ("m3948a0", "m3948a1"):
        victim = _foe_within(c, 1)
        if victim is None:
            return
        c.use_power(ref, on=victim, spend=False)


@power(
    "m3948a3",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    dropped=("c.zone(side=)",),
)
def m3948a3(c: Cast) -> None:
    """A cloud that stops sight and blinds whoever is in it.

    `blocks_sight` is terrain and cuts both ways, so the printed "for all
    creatures except the m3948" is the dropped half -- a zone has no side and
    the owner sees no better through its own. The blind is laid on whoever is
    in the cloud now and on whoever walks into it, which is the only reading
    of "while entirely within" the engine can measure.
    """
    area = c.area()
    if not area:
        return
    zone = c.zone(area, blocks_sight=True, until=When.EONT, label=c.ref)
    me = c.me

    def fog(who: int) -> None:
        if who != me:
            c.blinded(until=When.EONT, on=who)

    for who in c.world.zones.occupants(zone):
        fog(who)

    def arrived(ev: Any) -> None:
        if ev.zone == zone:
            fog(ev.actor)

    from combat_engine.engine.events import ZoneEntered

    c.watch(ZoneEntered, arrived, until=When.EONT, on=me, label=f"{c.ref} in")


# ==========================================================================
# m4031
# ==========================================================================


@power(
    "m4031a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 6),
)
def m4031a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4031a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d6", 6),
)
def m4031a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4031a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m4031a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m4031a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4031a3(c: Cast) -> None:
    """This one is the rider, not the mount, so the saddle is read from the
    other end: `Relation.RIDDEN_BY` is set mount-to-rider, so a rider's
    mounts are its `sources`.

    The gate is asked inside the veto, where `c.no_provoke` reads it, rather
    than once when the trait arms -- nothing is in the saddle at the start of
    a fight.
    """
    me = c.me
    c.no_provoke(
        on=me, until=When.ENCOUNTER,
        when=lambda _ctx: bool(c.world.relations.sources(Relation.RIDDEN_BY, me)),
    )


# ==========================================================================
# m4464
# ==========================================================================


@power(
    "m4464a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m4464a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4464a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d6", 5),
)
def m4464a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4464a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m4464a2(c: Cast) -> None:
    """Swing, step, swing at somebody else, step. `c.basic` because the card
    says basic attack and this block prints two melee lines -- which of them
    is the basic is the creature's own business, not this row's."""
    first = _foe_within(c, 1)
    if first is not None:
        c.basic(on=first)
    c.shift(1)
    second = _foe_within(c, 1, exclude=[first] if first is not None else [])
    if second is not None:
        c.basic(on=second)
    c.shift(1)


@power(
    "m4464a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 5),
    requires_text="requires the weapon this stat block carries",
)
def m4464a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.cure(Condition.MARKED, on=c.me)


_M4464_HURT = "it takes damage"


@power(
    "m4464a4",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M4464_HURT,
    on=Trigger(DamageApplied, targets_me, _M4464_HURT),
)
def m4464a4(c: Cast) -> None:
    """"Until it attacks" is ended on `AttackDeclared`, which is the earliest
    announcement of a swing -- the hold has to be gone before the roll it
    would otherwise help."""
    me = c.me
    hold = c.invisible(on=me, until=When.EONT)
    if hold is None:
        return

    def reveal(ev: AttackDeclared) -> None:
        if ev.attacker == me:
            c.world.effects.end(hold, "it attacked")

    c.watch(
        AttackDeclared, reveal, until=When.EONT,
        window=Window.BEFORE, on=me, label=c.ref,
    )


@power(
    "m4464a5",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4464a5(c: Cast) -> None:
    """Three squares through stone, and it may stop inside.

    `c.merge` is the printed ending: the square is solid already, so nothing
    reaches in and nothing reaches out. The restriction on what it may do in
    there needs nothing written -- with no line of effect to anything there
    is no attack it could make, and a Perception check is not rolled on a
    board.
    """
    waiver = c.phasing(until=When.EOT, on=c.me)
    c.move(3)
    if waiver is not None:
        c.world.effects.end(waiver, "the move is over")
    if c.may(f"{c.ref}: stop inside the stone"):
        c.merge(until=When.ENCOUNTER)


@power(
    "m4464a6",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4464a6(c: Cast) -> None:
    """A Stealth check at the opening roll, and `InitiativeRolled` is the
    event that announces one.

    "Cover or concealment" is asked of the board: concealment is a modifier
    on the creature, and cover is computed between two positions, so the
    question is whether any enemy's line to it is blocked. The DC is the best
    passive Perception on the other side, which is what a hidden creature has
    to beat.
    """
    me = c.me

    def opening(ev: Any) -> None:
        if ev.actor != me:
            return
        from combat_engine.engine.query import cover_between

        foes = sorted(enemies(c.world, me))
        hidden = c.total("concealment", on=me) > 0 or any(
            cover_between(c.world, foe, me) for foe in foes
        )
        if not hidden or not foes:
            return
        dc = max(c.passive("perception", of=foe) for foe in foes)
        if c.check("stealth", dc):
            c.hide(until=When.ENCOUNTER)

    from combat_engine.engine.events import InitiativeRolled

    c.watch(InitiativeRolled, opening, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4464a7",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    dropped=("Scenery.stone",),
)
def m4464a7(c: Cast) -> None:
    """Three squares. What the two ends are made of is the dropped half: the
    map records passability and a handful of scenery kinds, and stone is not
    one of them, so the restriction cannot be asked at either end."""
    c.teleport(3)


# ==========================================================================
# m4539
# ==========================================================================


@power(
    "m4539a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_PSIONIC_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m4539a0(c: Cast) -> None:
    """Two expressions on one line and a header holds one, so the printed
    base stays in the header -- which is what rescales -- and the typed die
    is rolled here."""
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.PSYCHIC)


@power(
    "m4539a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_PSIONIC_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m4539a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d8", dtype=DamageType.PSYCHIC)
    c.shift(2)


@power(
    "m4539a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m4539a2(c: Cast) -> None:
    """Three swings at three different creatures, with five squares of
    teleport available before each. The blink is taken only when there is
    nobody new in reach, which is the clause that reaches the next one."""
    struck: list[int] = []
    for _ in range(3):
        victim = _foe_within(c, 1, exclude=struck)
        if victim is None:
            c.teleport(5)
            victim = _foe_within(c, 1, exclude=struck)
        if victim is None:
            return
        struck.append(victim)
        c.use_power("m4539a0", on=victim, spend=False)


_M4539_HELD = "it is grabbed, immobilized, or restrained"


def _held_fast(world: World, me: int, ev: ConditionApplied) -> bool:
    """`ConditionApplied` names its subject `target`, so `about_me` -- which
    reads `ev.actor` and only that -- is false here forever."""
    return ev.target == me and ev.condition in _PINNED


@power(
    "m4539a3",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 5),
    trigger=_M4539_HELD,
    on=Trigger(ConditionApplied, _held_fast, _M4539_HELD),
)
def m4539a3(c: Cast) -> None:
    """Aimed at whoever laid the hold, which `ConditionApplied.source` names:
    the chooser would hand over whoever is nearest, and that is not the
    printed target."""
    holder = getattr(c.trigger, "source", None)
    if holder is None:
        return
    if c.strike(on=holder):
        c.hit(on=holder)
        c.cure(*_PINNED, on=c.me)
        c.shift(3)


@power(
    "m4539a4",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4539a4(c: Cast) -> None:
    options = [c.me, *(mate for mate in c.allies() if c.distance(mate) <= 10)]
    who = c.choose(sorted(options), f"{c.ref}: who flies")
    if who is None:
        return
    c.mode("fly", 5, until=When.EOT, on=who)
    c.move(5, who=who, at="fly")


# ==========================================================================
# m4600
# ==========================================================================


@power(
    "m4600a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=22),
    damage=Damage("2d10", 5),
)
def m4600a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4600a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=22),
    damage=Damage("2d8", 5),
)
def m4600a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4600a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4600a2(c: Cast) -> None:
    """Two swings of the reach line, so its numbers stay there -- this row's
    own printed attack line names no defence and no dice and is not a line
    that can be written down.

    "Slides one target it hits" is one slide however many land, which is why
    the hits are collected rather than slid as they happen.
    """
    landed: list[int] = []
    struck: list[int] = []
    for _ in range(2):
        victim = _foe_within(c, 2, exclude=struck)
        if victim is None:
            break
        struck.append(victim)
        c.use_power("m4600a0", on=victim, spend=False)
        if c.landed:
            landed.append(victim)
    if landed:
        pick = c.choose(landed, f"{c.ref}: slide which")
        if pick is not None:
            c.slide(1, on=pick)
    c.shift(3)


@power(
    "m4600a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    once_per_round=True,
    attack=Attack(vs=WILL, printed=20),
)
def m4600a3(c: Cast) -> None:
    """No damage is printed. "Cannot benefit from invisibility or
    concealment" is `c.no_cover`, which is the one hold that takes both of
    those away, and the advantage is a second clause on the same duration."""
    if c.strike():
        c.no_cover(until=When.EONT)
        c.grants_advantage(until=When.EONT)


@power(
    "m4600a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=22),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m4600a4(c: Cast) -> None:
    """One of the two, or both on a critical. The choice is made per target,
    which is what "the target is either ... or ..." reads as."""
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.slowed(until=When.SAVE_ENDS)
        c.ongoing(10)
    elif c.choose(["slow", "burn"], f"{c.ref}: which") == "burn":
        c.ongoing(10)
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4600a5",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4600a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    `flanked_by` asks whether the ally and one of *its* allies have the
    creature between them; this one also has to be adjacent for the flank to
    be the one the card means.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker == me or ev.attacker not in c.allies():
            return
        if not c.adjacent(ev.target) or not flanked_by(c.world, ev.target, ev.attacker):
            return
        c.damage("1d8", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


_M4600_CLOSED = "an ally moves adjacent to a creature within 2 squares of it"


def _ally_closed_in(world: World, me: int, ev: MoveEnd) -> bool:
    if ev.actor == me or ev.actor not in allies(world, me):
        return False
    return any(
        adjacent(world, ev.actor, foe)
        for foe in enemies(world, me)
        if distance_between(world, me, foe) <= 2
    )


@power(
    "m4600a6",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4600_CLOSED,
    on=Trigger(MoveEnd, _ally_closed_in, _M4600_CLOSED),
)
def m4600a6(c: Cast) -> None:
    """"It must end this shift in a flanking position" is a destination, not a
    choice, so the square is picked here: a bare `c.shift` goes wherever the
    decider says and that is not what the card instructs."""
    mate = getattr(c.trigger, "actor", None)
    if mate is None:
        return
    me = c.me
    reachable = set(c.world.reachable_squares(me, 2))
    for foe in sorted(c.enemies()):
        if not adjacent(c.world, mate, foe):
            continue
        for square in _free_square_within(c, foe, 1):
            if square not in reachable:
                continue
            here = c.here
            if c.shift(2, to=square) and flanked_by(c.world, foe, mate):
                return
            if c.here != here:
                c.shift(2, to=here)
    c.shift(2)


# ==========================================================================
# m5432
# ==========================================================================


@power(
    "m5432a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 6),
)
def m5432a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5432a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 3),
)
def m5432a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5432a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5432a2(c: Cast) -> None:
    """Twice with the lighter of the two melee lines -- the one that slows.
    Two of it comes to more than one of the heavier line, which is what a
    doubled attack is for, and the heavier one is the line the other row uses
    singly."""
    for _ in range(2):
        victim = _foe_within(c, 1)
        if victim is None:
            return
        c.use_power("m5432a1", on=victim, spend=False)


@power(
    "m5432a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5432a3(c: Cast) -> None:
    """The heavier melee line, four squares, the same line against somebody
    else."""
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    first = _foe_within(c, 1)
    if first is not None:
        c.use_power("m5432a0", on=first, spend=False)
    c.shift(4)
    second = _foe_within(c, 1, exclude=[first] if first is not None else [])
    if second is not None:
        c.use_power("m5432a0", on=second, spend=False)


@power(
    "m5432a4",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d10", 3, dtype=DamageType.FORCE, kind=LIMITED),
)
def m5432a4(c: Cast) -> None:
    """"Creatures in the blast" is everything in front of it and not itself,
    which is `EACH_OTHER`: `EACH_CREATURE` is side "any" and would put the
    creature in its own blast."""
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m5432a5",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5432a5(c: Cast) -> None:
    """Six squares of leap, then a shove, then two squares to somebody's
    side. The last step names its destination -- "to a square adjacent to an
    enemy" -- so the square is picked rather than left to the decider, which
    with nothing installed takes the lowest square on the board."""
    waiver = c.no_provoke(on=c.me, until=When.EOT)
    c.jump(6)
    if waiver is not None:
        c.world.effects.end(waiver, "the leap is over")
    for foe in sorted(c.enemies()):
        if c.adjacent(foe):
            c.push(2, on=foe)
    reachable = set(c.world.reachable_squares(c.me, 2))
    beside = sorted(
        square
        for foe in c.enemies()
        for square in _free_square_within(c, foe, 1)
        if square in reachable
    )
    if beside:
        c.shift(2, to=beside[0])
    else:
        c.shift(2)


_M5432_FLANKED = "an enemy moves to a square where it flanks the m5432"


@power(
    "m5432a6",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    trigger=_M5432_FLANKED,
    on=Trigger(MoveEnd, _moved_to_flank, _M5432_FLANKED),
)
def m5432a6(c: Cast) -> None:
    """No damage on the Hit line, so none is dealt: the fall and the burn are
    the whole consequence."""
    victim = getattr(c.trigger, "actor", None) or c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.prone(on=victim)
        c.ongoing(10, on=victim)


# ==========================================================================
# m5545
# ==========================================================================


@power(
    "m5545a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5545a0(c: Cast) -> None:
    """`Condition.CANNOT_SHIFT` rather than immobilised: the card takes the
    shift away and leaves the walk, which is exactly the distinction that
    condition is named for."""
    me = c.me

    def chilled(ev: DamageApplied) -> None:
        if ev.target == me and ev.amount > 0 and ev.dtype is DamageType.COLD:
            c.cannot_shift(on=me, until=When.EONT)

    c.watch(DamageApplied, chilled, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5545a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 8, dtype=DamageType.FIRE),
)
def m5545a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5545a2",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5545a2(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


@power(
    "m5545a3",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m5545a3(c: Cast) -> None:
    """The squares it shifted through catch fire for the rest of the fight.

    `movement.shift` places the creature at its destination rather than
    walking it, so `LeaveSquare` names where it started and nothing between;
    `c.line` is the run the card describes and is read from the two ends.

    "Each time a nonfire creature enters" needs nothing written: this
    creature's own resistance is in the database and covers it, and anything
    else made of fire carries its own.
    """
    start = c.here
    c.shift(c.speed_of())
    trail = c.line(start, c.here)
    if trail:
        c.hazard(
            trail, 10, DamageType.FIRE,
            until=When.ENCOUNTER, sustain=None, label=c.ref,
        )


# ==========================================================================
# m5651
# ==========================================================================


@power(
    "m5651a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=_POISON_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d4", 4),
)
def m5651a0(c: Cast) -> None:
    """Whether the blow had combat advantage is read off the result rather
    than asked of the board again -- a one-shot grant is already spent by
    then. One burn either way: of one type only the highest applies, so the
    heavier number is laid where it is earned and not added on."""
    if not c.strike():
        return
    c.hit()
    heavy = c.result is not None and c.result.advantage
    c.ongoing(10 if heavy else 5, DamageType.POISON)


@power(
    "m5651a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
    requires=lambda world, eid: not (
        (h := world.get(eid, Health)) is not None and h.bloodied
    ),
    requires_text="usable only while it is not bloodied",
)
def m5651a1(c: Cast) -> None:
    """No damage is printed: the swing it makes somebody else take is the
    whole of it. `c.basic`'s `who` is who swings and `on` is who gets hit --
    without the second the blow would fall on this row's own target, which is
    the creature being charmed."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    marks = sorted(foe for foe in c.enemies() if foe != victim)
    mark = c.choose(marks, f"{c.ref}: whom it swings at") if marks else None
    if mark is None:
        return
    c.bonus("attack", 4, on=victim, until=When.EONT, once=True)
    c.basic(who=victim, on=mark)


@power(
    "m5651a2",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5651a2(c: Cast) -> None:
    """Partial, so `total=False`: the -5 is the other printed word."""
    c.shift(3)
    c.conceal(on=c.me, until=When.EONT)


_M5651_BLOODIED = "it becomes bloodied"


@power(
    "m5651a3",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d10", 7, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
    trigger=_M5651_BLOODIED,
    on=Trigger(Bloodied, about_me, _M5651_BLOODIED),
)
def m5651a3(c: Cast) -> None:
    """The Effect line sits below the Miss line, so the daze lands on
    everything in the burst whether the blow found it or not."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    c.dazed(until=When.EONT)


_M5651_STRUCK = "it is hit by an attack while it is not bloodied"


def _hit_while_whole(world: World, me: int, ev: Hit) -> bool:
    health = world.get(me, Health)
    return ev.target == me and health is not None and not health.bloodied


@power(
    "m5651a4",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5651_STRUCK,
    on=Trigger(Hit, _hit_while_whole, _M5651_STRUCK),
)
def m5651a4(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m5679
# ==========================================================================


@power(
    "m5679a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 10),
)
def m5679a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5679a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5679a1(c: Cast) -> None:
    _swing_and_move(c, "m5679a0", 1, lambda: c.shift(3))


@power(
    "m5679a2",
    level=13,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m5679a2(c: Cast) -> None:
    """"Save ends both" is one hold carrying the burn and the penalty, so the
    two go and come back together. `c.penalty` takes no `kind` and that is
    the rule."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m5679a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m5679a3(c: Cast) -> None:
    """`Relation.RIDDEN_BY` is set mount-to-rider, so the thing this creature
    is riding is one of its `sources` -- and getting off is clearing the same
    relation rather than any verb of its own."""
    me = c.me
    seat = c.world.relations.sources(Relation.RIDDEN_BY, me)
    if seat:
        for mount in seat:
            c.world.relations.clear(Relation.RIDDEN_BY, mount, me)
        return
    near = sorted(mate for mate in c.allies() if c.adjacent(mate))
    mount = c.choose(near, f"{c.ref}: which mount") if near else None
    if mount is not None:
        c.ride(on=mount)


_M5679_STRUCK = "an adjacent enemy hits it or its mount"


def _struck_the_pair(world: World, me: int, ev: Hit) -> bool:
    seat = world.relations.sources(Relation.RIDDEN_BY, me)
    return (ev.target == me or ev.target in seat) and adjacent(world, me, ev.attacker)


@power(
    "m5679a4",
    level=13,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 10, kind=LIMITED),
    trigger=_M5679_STRUCK,
    on=Trigger(Hit, _struck_the_pair, _M5679_STRUCK),
)
def m5679a4(c: Cast) -> None:
    victim = getattr(c.trigger, "attacker", None) or c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.push(2, on=victim)
        c.prone(on=victim)


_M5679_MOUNT_HURT = "its mount takes damage while it is on it"


def _mount_is_hurt(world: World, me: int, ev: DamageRolled) -> bool:
    return ev.amount > 0 and ev.target in world.relations.sources(Relation.RIDDEN_BY, me)


@power(
    "m5679a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5679_MOUNT_HURT,
    on=Trigger(DamageRolled, _mount_is_hurt, _M5679_MOUNT_HURT),
)
def m5679a5(c: Cast) -> None:
    """An interrupt, so the blow has been rolled and not yet dealt, which is
    the only window `c.absorb` can take it in."""
    c.absorb(c.trigger, on=c.me)


# ==========================================================================
# m5879
# ==========================================================================


@power(
    "m5879a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m5879a0(c: Cast) -> None:
    """The aura stands all fight and the burn is gated on bloodied, asked at
    the moment a turn ends rather than when the trait arms -- it is false
    then and would never become true."""
    me = c.me
    aura = c.aura(1, label=c.ref, until=When.ENCOUNTER, on=me)

    def dusk(ev: TurnEnd) -> None:
        if not c.bloodied(on=me) or ev.actor == me:
            return
        if ev.actor in enemies(c.world, me) and ev.actor in c.world.zones.occupants(aura):
            c.flat(10, dtype=DamageType.POISON, on=ev.actor)

    c.watch(TurnEnd, dusk, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5879a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5879a1(c: Cast) -> None:
    me = c.me

    def dusk(ev: TurnEnd) -> None:
        if ev.actor == me:
            c.cure(Condition.DAZED, Condition.STUNNED, Condition.DOMINATED, on=me)

    c.watch(TurnEnd, dusk, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5879a2",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.extra_turn(free_only=)",),
)
def m5879a2(c: Cast) -> None:
    """A second slot in the order, at ten over its own check.

    `Initiative.rolled` is that check, so the count is computed and
    `c.extra_turn` is the engine's way of saying a solo acts again. What is
    dropped is the *shape* of the slot: the card gives a free action that
    flies and swings once, and the engine's second slot is a whole turn, so
    the +4 to defences against opportunity attacks that rides on that one
    movement has no movement to ride on either.

    The other printed half is written: a dominating or stunning effect ends
    instead of the attack being made, which is asked at the start of each of
    its turns.
    """
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(at=10 + init.rolled)

    def dawn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            c.cure(Condition.STUNNED, Condition.DOMINATED, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5879a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 5, half_on_miss=True),
)
def m5879a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
    else:
        c.hit(half=True)


@power(
    "m5879a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 5),
)
def m5879a4(c: Cast) -> None:
    """"If he targets only one creature he can make this attack twice" is a
    second roll on the same victim, taken on the one pass the body makes."""
    for swing in range(2):
        if swing and len(c.targets) != 1:
            return
        if c.strike():
            c.hit()
            c.shift(2)


@power(
    "m5879a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d10", 5, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m5879a5(c: Cast) -> None:
    """Two burns of one type, and of one type only the highest applies -- so
    the Miss line's 5 is simply the weaker of the two and needs no sweeping
    before it is laid."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS,
            ongoing=(10, DamageType.POISON),
        )
    else:
        c.hit(half=True)
        c.ongoing(5, DamageType.POISON)


@power(
    "m5879a6",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("3d12", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5879a6(c: Cast) -> None:
    """The push is as far as the target can walk, which is `c.speed_of` asked
    of the target -- it defaults to the caster, so it is named."""
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()
        c.push(c.speed_of(c.target))
    else:
        c.hit(half=True)
    if c.last:
        c.shift(c.speed_of())


@power(
    "m5879a7",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
)
def m5879a7(c: Cast) -> None:
    """One creature in the blast, so the target is one and not everything --
    and no damage is printed, so none is dealt."""
    if c.strike():
        c.slide(3)


_M5879_STILL = "an adjacent enemy ends its turn without moving"


def _stood_still(world: World, me: int, ev: TurnEnd) -> bool:
    """Nothing records whether a creature moved, and `Budget.move` is the
    only thing that can answer: it is refreshed at `TurnStart` and spent by a
    move or a shift, so still having it at the end is standing still. A charge
    moves without spending it, which is the one case this gets wrong."""
    budget = world.get(ev.actor, Budget)
    return (
        ev.actor != me
        and ev.actor in enemies(world, me)
        and adjacent(world, me, ev.actor)
        and budget is not None
        and budget.move > 0
    )


@power(
    "m5879a8",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d8", 7),
    trigger=_M5879_STILL,
    on=Trigger(TurnEnd, _stood_still, _M5879_STILL),
)
def m5879a8(c: Cast) -> None:
    victim = getattr(c.trigger, "actor", None) or c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.prone(on=victim)


_M5879_BLOODIED = "it is first bloodied"


@power(
    "m5879a9",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5879_BLOODIED,
    on=Trigger(Bloodied, about_me, _M5879_BLOODIED),
)
def m5879a9(c: Cast) -> None:
    _breathe_again(c, "m5879a5")


# ==========================================================================
# m5916
# ==========================================================================


@power(
    "m5916a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5916a0(c: Cast) -> None:
    """No range is named, so every attack."""
    _advantage_rider(c, "2d6")


@power(
    "m5916a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5916a1(c: Cast) -> None:
    """"Even if the effect doesn't normally allow a saving throw" is what
    `bare=True` is for: it rolls without looking for a save-ends hold to roll
    against, and the hold carrying the condition is then ended by hand. A
    hold that *is* save-ends gets its throw the same way, a round early,
    which is what the card gives it."""
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for cond in (Condition.IMMOBILIZED, Condition.SLOWED):
            if not c.is_(cond, on=me):
                continue
            hold = next(
                (eff for eff in c.world.effects.of(me) if cond in eff.conditions), None
            )
            if hold is not None and c.save(on=me, bare=True):
                c.world.effects.end(hold, c.ref)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5916a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d4", 11),
)
def m5916a2(c: Cast) -> None:
    """The Effect line is not under the Hit line, so the opportunity windows
    close whether the blow landed or not."""
    if c.strike():
        c.hit()
    victim = c.target
    if victim is not None:
        _no_opportunities(c, victim, When.EONT)


@power(
    "m5916a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d4", 11, kind=LIMITED),
)
def m5916a3(c: Cast) -> None:
    """A run of up to its speed with three swings in it, each at a different
    creature. The step is taken one square at a time so that the swings fall
    where there is somebody to swing at, which is what "during this movement"
    means; `NO_TARGET` because the row's own effect is the run."""
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    left = c.speed_of()
    struck: list[int] = []
    while len(struck) < 3:
        victim = next(
            (
                foe
                for foe in sorted(c.enemies())
                if foe not in struck and alive(c.world, foe) and c.adjacent(foe)
            ),
            None,
        )
        if victim is not None:
            struck.append(victim)
            if c.strike(on=victim):
                c.hit(on=victim)
                c.condition(
                    Condition.SLOWED, until=When.SAVE_ENDS, on=victim,
                    ongoing=(5, DamageType.UNTYPED),
                )
            continue
        if left <= 0 or not c.shift(1):
            return
        left -= 1


@power(
    "m5916a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5916a4(c: Cast) -> None:
    """"Each slide 1 square, swapping positions" is `c.swap`, which lifts both
    before either lands -- done one at a time, each sees the other's square
    as occupied and neither moves."""
    near = sorted(
        who for who in c.within(1, side="any") if who != c.me and c.adjacent(who)
    )
    other = c.choose(near, f"{c.ref}: swap with whom") if near else None
    if other is not None:
        c.swap(other)


# ==========================================================================
# m6018
# ==========================================================================


@power(
    "m6018a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6018a0(c: Cast) -> None:
    """"-2 for each one of them adjacent to it" is laid once per creature
    rather than counted: each copy of this stat block arms its own trait, so
    each lays its own -2 and the total is the count the card asks for.
    Counting them here would multiply the penalty by the number of traits
    armed.

    `escape` is the modifier key the escape action reads -- deliberately not
    a skill, because a bonus to getting out of a grab is not a bonus to
    tumbling.
    """
    me = c.me

    def held(ev: ConditionApplied) -> None:
        if ev.condition is not Condition.GRABBED:
            return
        if ev.source != me and not _same_stock(c.world, me, ev.source):
            return
        if not c.adjacent(ev.target):
            return
        c.penalty("escape", 2, on=ev.target, until=When.ENCOUNTER)

    c.watch(ConditionApplied, held, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6018a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 5),
)
def m6018a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6018a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d10", 5),
)
def m6018a2(c: Cast) -> None:
    """The printed escape DC has no column: `escape.attempt` measures the
    check against this creature's own Reflex or Fortitude by design, which is
    the printed action and not an approximation of it."""
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m6018a3",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d10", 10, kind=LIMITED, half_on_miss=True),
)
def m6018a3(c: Cast) -> None:
    """"One creature grabbed by a creature other than this one" is a
    restriction `Target` cannot carry, so the row is redirected rather than
    thrown away -- returning would throw it away while somebody in reach
    qualifies."""
    def held_by_another(who: int) -> bool:
        holders = c.world.relations.sources(Relation.GRABBED_BY, who)
        return any(holder != c.me for holder in holders)

    victim = c.target
    if victim is None or not held_by_another(victim):
        victim = next(
            (
                foe
                for foe in sorted(c.enemies())
                if held_by_another(foe) and c.adjacent(foe)
            ),
            None,
        )
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
    else:
        c.hit(on=victim, half=True)


@power(
    "m6018a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6018a4(c: Cast) -> None:
    """"Must end this movement adjacent to an enemy" is a destination, and
    `c.move` picks its own; `c.run_at` is the walk that goes somewhere named.
    The extra four squares are laid as a bonus to speed first, because that
    is the number `run_at` measures the run against."""
    victim = _foe_within(c, 99)
    if victim is None:
        return
    extra = c.bonus("speed", 4, on=c.me, until=When.EOT)
    try:
        c.run_at(victim)
    finally:
        if extra is not None:
            c.world.effects.end(extra, "the move is over")


# ==========================================================================
# m6149
# ==========================================================================

_THUNDER_WEAPON = [Keyword.THUNDER, Keyword.WEAPON]


@power(
    "m6149a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=_THUNDER_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 11),
)
def m6149a0(c: Cast) -> None:
    """The high-crit die is rolled and then laid flat: `c.damage` maxes its
    dice on a critical, so an extra rolled die inside the crit branch would
    come out at its maximum rather than rolled."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("3d6"), dtype=DamageType.THUNDER)
    c.push(2)


@power(
    "m6149a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6149a1(c: Cast) -> None:
    for _ in range(2):
        victim = _foe_within(c, 2)
        if victim is None:
            return
        c.use_power("m6149a0", on=victim, spend=False)


@power(
    "m6149a2",
    level=13,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=_THUNDER_WEAPON,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 11, kind=LIMITED),
)
def m6149a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.damage("2d8", dtype=DamageType.THUNDER)
    if c.crit:
        c.flat(c.roll("3d6"), dtype=DamageType.THUNDER)
    c.push(2)


@power(
    "m6149a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=Melee(0),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d6", 5, kind=LIMITED),
)
def m6149a3(c: Cast) -> None:
    """A trample. `c.overrun` is the only verb that walks through whoever is
    in the way and says who that was -- `c.move` refuses an occupied square
    and reports nothing about what it passed.

    It measures `c.speed_of`, which is this row's printed distance: the card
    says "up to his speed" and names no other mode, so nothing is lost to the
    trap that catches a printed burrow or climb speed.
    """
    for victim in c.overrun():
        if not alive(c.world, victim):
            continue
        if c.strike(on=victim):
            c.hit(on=victim)
            c.push(2, on=victim)
            c.prone(on=victim)
