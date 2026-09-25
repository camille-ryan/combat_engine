"""Monster abilities, level 12: the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. A
minion deals its printed number on a hit and takes none of this specially --
`kind=MINION` is what says the number is flat because the creature is one,
which is how it rescales, and its single hit point is in the database like
every other number.

They are filed here rather than appended to `artillery.py`, which the
convention of the levels below would otherwise ask for: another batch was
writing that file at the same time as this one.

The conventions of the eleven levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; a stat block printing no range at all means melee 1;
a printed "Range 10/20" is a normal range and a long one and the normal one
is what `Range` holds; and a helper written for an earlier level is imported
rather than copied.

Three things this file had to settle.

**Two numbers on one damage line, and the header holds one.** m2980a1
prints "5 damage (7 if it moved 3 or more squares during its turn)". The
five stays in the header, because that is what rescales, and the heavier
number is dealt flat in its place -- the arrangement level 10 settled on for
the same shape. How far it has moved is counted off the log: `Moved` is one
step, and no component remembers a turn's worth of them.

**A burn that a second hit makes worse is the existing hold's number
raised**, not a second hold: two would be two saving throws against one
printed sentence, and ongoing damage of one type does not stack anyway --
the higher applies and a second five would simply be refused.

**An aura that catches whoever starts a turn inside it** is the aura plus a
`TurnStart` watch that asks the zone who is standing there, rather than a
membership list that goes stale the moment anybody moves.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_06.controllers import _living
from combat_engine.content.monsters.level_08.brutes import _aura
from combat_engine.content.monsters.level_10.lurkers import EVERY_DEFENCE
from combat_engine.content.monsters.level_12.skirmishers import _amphibious
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    Damage,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    Miss,
    Position,
    Ranged,
    TurnStart,
    When,
    power,
    targets_me,
)
from combat_engine.engine.events import Moved
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.triggers import Trigger


def _squares_moved_this_turn(c: Cast) -> int:
    """How far this creature has moved since its turn began.

    `Moved` is one step with both ends of it, and nothing on the board
    remembers a turn's worth of them, so the log is read backwards to this
    creature's own `TurnStart` and the steps in between are counted. Forced
    movement is a step like any other here, which is what "moved" with no
    qualifier means.
    """
    me = c.me
    steps = 0
    for past in reversed(c.world.bus.log):
        if isinstance(past, TurnStart) and past.actor == me and not past.ghost:
            break
        if isinstance(past, Moved) and past.actor == me:
            steps += 1
    return steps


def _poison_burn(c: Cast, who: int) -> Any:
    """The poison burn that creature is already carrying, if any."""
    for eff in c.world.effects.of(who):
        if eff.ongoing is not None and eff.ongoing[1] is DamageType.POISON:
            return eff
    return None


# ==========================================================================
# m2980
# ==========================================================================


@power(
    "m2980a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=7, dtype=DamageType.POISON, kind=MINION),
)
def m2980a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means.

    "If the target is affected by ongoing poison damage, that ongoing damage
    increases by 5" is the *existing* burn getting worse rather than a second
    one landing: the hold is found and its number raised. Two burns would be
    two saving throws where the card prints one, and ongoing damage of one
    type does not stack in any case -- a second five would simply be
    refused, which is what the printed sentence exists to get around.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    burn = _poison_burn(c, victim)
    if burn is not None:
        burn.ongoing = (burn.ongoing[0] + 5, DamageType.POISON)


@power(
    "m2980a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=5, kind=MINION),
)
def m2980a1(c: Cast) -> None:
    """Range 10/20: the header carries the short range, which is the only
    one `Range` holds. Two numbers on one damage line and the header holds
    one, so the printed five stays there -- which is what rescales -- and
    the heavier number for having run is dealt flat in its place."""
    if not c.strike():
        return
    if _squares_moved_this_turn(c) >= 3:
        c.flat(7)
    else:
        c.hit()


@power(
    "m2980a2",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2980a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it fights better with
    its betters nearby.

    Five separate modifiers -- one names the attack roll and "all defenses"
    is four more -- and each is gated at the moment it is read, because who
    it is standing near changes every turn.
    """
    me = c.me

    def escorted(_ctx: dict[str, Any]) -> bool:
        return any(
            c.is_kind("drow", on=mate)
            for mate in c.within(5, side="ally")
            if mate != me
        )

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=escorted)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.ENCOUNTER, on=me, kind="untyped", when=escorted)


@power(
    "m2980a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2980a3(c: Cast) -> None:
    """Filed as a standard action, which a bare one-square shift is not:
    every other stat block in the tree prints this as a move action, and
    spending a standard on it would make the row one no policy ever takes.
    """
    c.shift(1)


# ==========================================================================
# m4930
# ==========================================================================


@power(
    "m4930a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4930a0(c: Cast) -> None:
    """An aura whose occupants carry the vulnerability while they are in it,
    diffed by the zone rather than recomputed."""

    def a_foe(who: int) -> bool:
        return who in c.enemies()

    def raw(who: int) -> Effect | None:
        return c.vulnerable(5, DamageType.PSYCHIC, until=When.ENCOUNTER, on=who)

    _aura(c, 1, a_foe, raw)


@power(
    "m4930a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4930a1(c: Cast) -> None:
    _amphibious(c)


@power(
    "m4930a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m4930a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m4930a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage(bonus=5, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m4930a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m4968
# ==========================================================================


@power(
    "m4968a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4968a0(c: Cast) -> None:
    """Who is inside is asked of the aura as each turn opens: the aura
    travels with its owner and a stored list of members would be stale the
    moment either of them moved. A ghost turn is nobody's turn and is left
    out."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def clinging(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slowed(until=When.EOTNT, on=ev.actor)

    c.watch(TurnStart, clinging, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4968a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m4968a2(c: Cast) -> None:
    """It steps aside and drags the target into the space it left.

    The vacated square is read before the step, because afterwards there is
    nothing left to read, and the slide names its destination outright --
    `c.slide` with no `to` offers the decider every square in range, which
    is useless for a printed line that says where the target ends up.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    pos = c.world.get(c.me, Position)
    was = pos.square if pos is not None else None
    if c.shift(1) and was is not None:
        c.slide(1, on=victim, to=was)


# ==========================================================================
# m4969
# ==========================================================================


_M4969_MISSED = "an attack misses the m4969"


@power(
    "m4969a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4969a0(c: Cast) -> None:
    """Read off the `Hit` rather than asked of the board again: a one-shot
    grant of combat advantage has already been spent by the time the blow is
    announced, so asking a second time comes back false on exactly the
    attacks this rider is for.

    Two flat, dealt as its own packet: a damage modifier would add to
    whatever else was riding along and would be paid on a blow this creature
    did not strike.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.had_advantage(ev):
            c.flat(2, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4969a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m4969a2(c: Cast) -> None:
    """The step is an Effect line, so it happens whether or not the blow
    did."""
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m4969a4",
    level=12,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4969_MISSED,
    on=Trigger(Miss, when=targets_me, text=_M4969_MISSED),
)
def m4969a4(c: Cast) -> None:
    c.shift(2)


# ==========================================================================
# m692
# ==========================================================================


@power(
    "m692a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, kind=MINION),
)
def m692a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. Only the secondary is poison, so the header carries no damage
    type.

    The secondary is a second attack line, and a second line's printed bonus
    is trimmed by hand the way `Attack.bonus_for` trims the header's.
    """
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(14, c.level), FORT):
        c.ongoing(3, DamageType.POISON)


# ==========================================================================
# m722
# ==========================================================================


@power(
    "m722a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m722a0(c: Cast) -> None:
    """Living is asked of the type line, which is the only place the engine
    records anything about being alive, and it is asked as a creature enters
    -- which is the one moment the aura's membership changes."""

    def a_living_foe(who: int) -> bool:
        return who in c.enemies() and _living(c, who)

    def cowed(who: int) -> Effect | None:
        return c.penalty("attack", 2, until=When.ENCOUNTER, on=who, kind="untyped")

    _aura(c, 1, a_living_foe, cowed)


@power(
    "m722a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage(bonus=7, kind=MINION),
)
def m722a1(c: Cast) -> None:
    if c.strike():
        c.hit()
