"""Monster abilities, level 13: the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=18)` and `Damage("2d6", 9)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the twelve levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block printing no range at all means melee 1; and a helper written for an
earlier level is imported rather than copied.

Four things this file had to settle.

**"A creature that cannot see it" has to be asked before the roll.**
`resolve.attack` breaks the hiding for whoever swung, so by the time
m4985a0's rider reaches the `Hit` the answer is no on every attack the rider
exists for -- the arrangement m2920a3 settled on a level down. The question
is asked in the `AttackDeclared` window, which is the last moment the answer
is still yes, and kept until the blow and its shove have both landed. It is
three questions, not one: the creature may be blinded, the m4985 may be
hidden from it, or there may be nothing to see along.

**Forced movement is lengthened on the event, not at the call site.**
"Increases any of the attack's forced movement by 2 squares" is about
whatever the attack goes on to do, and the attack is several rows -- so the
two squares are added to `ForcedMove` in its interrupt window, which is the
one place every push, pull and slide passes through and is still mutable.

**"Slides to any other square within the burst area"** is a destination
rather than a distance, which is what `c.slide(..., to=)` takes; the squares
offered are the ones `c.area()` reports, less the ones the creature is
already standing in.

**An elite with no second initiative count.** m73 prints no row that acts
twice, so none is written: an elite is two creatures' worth of hit points
and experience before it is anything else, and splicing a turn for one would
be inventing a printed line.

Each stat block in ref order.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_11.lurkers import (
    _extra_against_the_unready,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Usage,
    When,
    Window,
    power,
)
from combat_engine.engine.events import ActionSpent, ForcedMove
from combat_engine.engine.grid import distance
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, squares


def _unseeing(c: Cast, who: int) -> bool:
    """Can that creature not see the caster?

    Three ways to be unable to: blinded, unable to trace a line at all, or
    simply not knowing where the caster is. `c.is_hidden` is the third and
    is the one that goes false the moment the caster swings, which is why
    every reader of this asks it before the roll rather than after.
    """
    return (
        c.is_(Condition.BLINDED, on=who)
        or not c.can_see(who)
        or c.is_hidden(from_=who)
    )


# ==========================================================================
# m4985
# ==========================================================================


@power(
    "m4985a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4985a0(c: Cast) -> None:
    """Striking out of the dark is worth five damage and two squares.

    Whether the victim could see it is read in the `AttackDeclared` window,
    which runs before the resolve callback and is the last moment the answer
    is still yes: `resolve.attack` clears the hiding for whoever swung, so
    asked at the `Hit` it is no on every attack this rider exists for.

    The extra squares go on `ForcedMove` in its interrupt window rather than
    at any call site, because "any of the attack's forced movement" is
    whatever the row it rode in on goes on to do, and every push, pull and
    slide passes through that one event.

    The reading is kept per victim and spent by the blow, so a shove from
    some later row does not inherit an answer taken for an earlier swing.
    """
    me = c.me
    blind: dict[int, bool] = {}

    def sighting(ev: AttackDeclared) -> None:
        if ev.attacker == me:
            blind[ev.target] = _unseeing(c, ev.target)

    def harder(ev: Hit) -> None:
        if ev.attacker == me and blind.get(ev.target):
            c.flat(5, on=ev.target)

    def further(ev: ForcedMove) -> None:
        if ev.source == me and blind.get(ev.target):
            ev.squares += 2

    c.watch(
        AttackDeclared, sighting, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} sighting",
    )
    c.watch(Hit, harder, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(
        ForcedMove, further, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} shove",
    )


@power(
    "m4985a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 9),
)
def m4985a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4985a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=18),
)
def m4985a2(c: Cast) -> None:
    """No damage line: the shove and the borrowed swing are the whole hit.

    Who the victim swings at is the m4985's choice, not the victim's, so it
    is chosen here -- and `c.grant_attack` is the one call that makes
    somebody else attack out of turn with their own row.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.slide(2, on=victim)
    marks = sorted(
        other
        for other in c.within(20, of=victim, side="any")
        if other != victim and alive(c.world, other)
    )
    chosen = c.choose(marks, "m4985a2: who it makes them swing at") if marks else None
    if chosen is not None:
        c.grant_attack(victim, on=chosen)


@power(
    "m4985a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m4985a3(c: Cast) -> None:
    """It thins out and is gone. Two holds, because being unseen and being
    half-there are two different properties of a creature and the engine
    holds them separately."""
    c.shift(6)
    c.invisible(until=When.EONT)
    c.insubstantial(until=When.EONT)


@power(
    "m4985a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4985a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


# ==========================================================================
# m73
# ==========================================================================


@power(
    "m73a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 9),
)
def m73a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m73a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 9),
)
def m73a1(c: Cast) -> None:
    """"Slides to any other square within the burst area" names a
    destination, not a distance, so the square is picked out of the area the
    row is covering and handed to `c.slide` outright -- left to itself the
    decider would choose from every square in range and ignore the burst.

    The distance is the width of the burst, which is as far as any two of
    its squares can be apart.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit(on=victim)
    theirs = squares(c.world, victim)
    room = sorted(sq for sq in c.area() if sq not in theirs)
    if not room:
        return
    here = next(iter(theirs))
    dest = c.world.decide(c.me, "slide", room, f"{c.ref}: where it puts them")
    c.slide(max(1, distance(here, dest)), on=victim, to=dest)


@power(
    "m73a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m73a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    no range kind, so every attack carries it, and whether the blow had the
    opening is read off the `Hit` -- a one-shot grant has already been spent
    by the time a second asking could be made."""
    _extra_against_the_unready(c, "2d8")


@power(
    "m73a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m73a3(c: Cast) -> None:
    """Unseen until it does something worth seeing.

    Not `_vanish`, which gives itself away on any attack roll: this one is
    printed as giving itself away on a *standard action*, which is a
    different and wider thing -- a minor-action attack leaves it unseen and
    a standard action that is not an attack does not. `ActionSpent` is the
    one event that says which sort of action was taken.
    """
    me = c.me
    veil = c.invisible(until=When.EONT)
    if veil is None:
        return

    def showed(ev: ActionSpent) -> None:
        if ev.actor == me and ev.cost is ActionType.STANDARD and not veil.ended:
            c.world.effects.end(veil, "it did something worth seeing")

    seen = c.watch(ActionSpent, showed, until=When.EONT, on=me, label=c.ref)
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))


@power(
    "m73a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m73a4(c: Cast) -> None:
    """Who was beside it is read *before* it goes, and who it arrives beside
    after -- the printed line names two different sets of creatures and the
    teleport is the moment between them.

    "Automatically gains combat advantage" is the relation, granted by each
    creature it lands next to and held on the m73's own clock.
    """
    beside = {foe for foe in c.enemies() if c.adjacent(foe)}
    c.teleport(10)
    for foe in sorted(beside):
        if alive(c.world, foe):
            c.dazed(until=When.EONT, on=foe)
    for foe in sorted(c.enemies()):
        if c.adjacent(foe):
            c.grants_advantage(until=When.EONT, on=foe)
