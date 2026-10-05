"""Monster abilities, level 13: the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. A
minion's damage is the flat number the card prints, `Damage(bonus=n,
kind=MINION)`, so an MM1 block can be rescaled later, and its single hit
point is a column like every other number.

The conventions of the twelve minion sweeps below are kept: a card printing
no range at all is melee 1, a printed "20/40" band takes the normal range, a
**trait** costs no action and has no target and arms the watches that hold it
for the rest of the fight, "another of its kind" counts by `Ident.ref`
because every creature in a fight may share a type word, and a helper written
for an earlier level is imported rather than copied.

Five things this file had to settle.

**"X damage, or Y against ..." is one packet, not two.** m5252a1, m5822a3
and m6188a0 each print a heavier number in place of the printed one. The base
stays in the header, where a rescale can find it, and the heavier number is
dealt flat *instead* -- the arrangement level 12 settled on. Adding the
difference as a second packet would be measured against resistance twice,
which for an 8-and-12 blow against resist 5 is 5 rather than 7. A line that
prints the word **extra** (m115766a0, m1761a0) is the opposite case and is a
second packet, because that is what the word means.

**"The next one of its kind to attack the same target" is laid when the swing
is declared, not up front.** m1298a2 arms a one-shot `AttackDeclared` watch in
**`Window.BEFORE`**: `Bus.emit` runs that window, then the resolver that sums
the situational modifiers, then the after-window `c.watch` defaults to -- so
the window is the whole of whether the bonus is read by the swing that woke
it, and the default is a beat too late. Handing the bonus to every one of its
kind in advance would pay it out several times where the card pays once, and
no `once=` on a bonus can fix that across several holders.

**A combined attack is one swing with the group's bonus on it.** m3842a3
counts whoever of its own block could reach the target, lends itself that
many points of attack and damage for the one shot, and borrows its own ranged
row to make it. What is missing is the pairing itself -- nothing rolls one
attack on behalf of several creatures, which is `c.combined_attack()`.

**A trail of burning ground is read off `Moved.from_`.** m5822a2 is the only
row here that needs the squares a creature *was* standing in, and `Moved` is
the one event that carries them. The zone is the old footprint minus the new
one, so a step that only shifts a Large body part way leaves behind exactly
what it vacated, and "ends its turn in the zone" is a `TurnEnd` watch asking
the zone who is standing there rather than a membership list that goes stale.

Two blocks in the role listing print no ability refs at all (m1751, m2933),
so there is nothing here to decorate for either.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.minions_sa import _kin_within
from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of
from combat_engine.content.monsters.level_03.skirmishers import _not_grabbing
from combat_engine.content.monsters.level_06.controllers import _living
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Dropped,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    Position,
    Ranged,
    Size,
    TurnEnd,
    TurnStart,
    When,
    Window,
    about_me,
    both,
    by_melee,
    footprint,
    power,
    targets_me,
)
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import cover_between
from combat_engine.engine.triggers import Trigger

# ==========================================================================
# m115766
# ==========================================================================


@power(
    "m115766a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=10, kind=MINION),
)
def m115766a0(c: Cast) -> None:
    """The psychic half is printed as "plus 5", so it is a second packet of
    its own type rather than a heavier total: only it is psychic, which is
    why the header carries no damage type."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    if c.is_(Condition.IMMOBILIZED, on=victim):
        c.flat(5, dtype=DamageType.PSYCHIC)


@power(
    "m115766a1",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
)
def m115766a1(c: Cast) -> None:
    """No damage on the hit line, so no `damage=` and no `c.hit()` -- the
    hold is the whole of it, and it is what m115766a0's heavier half looks
    for."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m1298
# ==========================================================================


@power(
    "m1298a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=7, kind=MINION),
)
def m1298a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1298a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage(bonus=8, kind=MINION),
)
def m1298a1(c: Cast) -> None:
    """Range 20/40: the header carries the normal range, which is the only
    one `Range` holds."""
    if c.strike():
        c.hit()


@power(
    "m1298a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m1298a2(c: Cast) -> None:
    """A basic attack, and then an opening for the next of its own kind.

    The bonus is laid inside an `AttackDeclared` watch rather than handed out
    in advance, so exactly one swing gets it: laid on every one of its kind up
    front it would pay out once per creature. **`Window.BEFORE` is what makes
    that work.** `Bus.emit` runs the before-window, then the resolver -- and
    the resolver is where `resolve.attack` sums the situational modifiers --
    then the after-window, which `c.watch` defaults to. Armed after, the
    bonus lands on the attacker a moment too late to be read and the swing
    rolls plain; driven both ways on a board, the kin swing came in at the
    same number as the control until the window moved.

    Who counts as the same kind is `Ident.ref`, and the watch is not closed
    to this creature itself -- "the next" may well be this one again next
    turn, and its own basic attack has already resolved by the time the
    watch is armed.
    """
    victim = c.target
    if victim is None:
        return
    mine = _ref_of(c, c.me)
    c.basic(on=victim)

    def opening(ev: AttackDeclared) -> None:
        if ev.target != victim or _ref_of(c, ev.attacker) != mine:
            return
        c.bonus(
            "attack", 2, on=ev.attacker, kind="power",
            until=When.ENCOUNTER, once=True,
        )

    c.watch(
        AttackDeclared, opening, until=When.ENCOUNTER, on=c.me,
        window=Window.BEFORE, once=True, label=c.ref,
    )


# ==========================================================================
# m1615
# ==========================================================================


@power(
    "m1615a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, kind=MINION),
)
def m1615a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m1761
# ==========================================================================


@power(
    "m1761a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=5, kind=MINION),
)
def m1761a0(c: Cast) -> None:
    """A printed "Reach 4" is the melee range, which is where `Melee(4)`
    puts it.

    "If the target is already dazed it takes an extra 2 damage instead" is
    read before the hold lands, and the "instead" governs the daze: a
    creature already dazed takes the extra and the save-ends hold is not
    laid a second time.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    already = c.is_(Condition.DAZED, on=victim)
    c.hit()
    if already:
        c.flat(2)
    else:
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m2099
# ==========================================================================


@power(
    "m2099a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=14),
)
def m2099a0(c: Cast) -> None:
    """The burn is the whole hit line, so the header declares no damage and
    the body never calls `c.hit()`."""
    if c.strike():
        c.ongoing(5, DamageType.POISON)


# ==========================================================================
# m2644
# ==========================================================================


@power(
    "m2644a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=8, kind=MINION),
)
def m2644a0(c: Cast) -> None:
    """The licence to cross rough ground is lent for the length of the step
    only: granted to the end of the fight it would be a standing trait the
    card does not print."""
    if not c.strike():
        return
    c.hit()
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(2)


@power(
    "m2644a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=7, kind=MINION),
)
def m2644a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2644a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2644a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Read off the `Hit` rather than asked of the board again: a one-shot grant
    of combat advantage has already been spent by the time the blow is
    announced, so asking a second time comes back false on exactly the
    attacks this rider is for. Dealt as its own packet, because a damage
    modifier would also be paid on a blow this creature did not strike.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.had_advantage(ev):
            c.flat(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2649
# ==========================================================================


@power(
    "m2649a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage(bonus=4, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m2649a0(c: Cast) -> None:
    """Three clauses on one hit line, and the step is the third of them --
    printed inside the Hit rather than as an Effect, so a miss leaves this
    creature where it stood.

    The penalty takes no `kind`: the card prints no type word, and
    `c.penalty` takes none in any case.
    """
    if not c.strike():
        return
    c.hit()
    c.penalty(WILL, 2, until=When.EONT)
    c.slowed(until=When.EONT)
    c.shift(1)


# ==========================================================================
# m3842
# ==========================================================================


@power(
    "m3842a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage(bonus=9, kind=MINION),
)
def m3842a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3842a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage(bonus=9, kind=MINION),
)
def m3842a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3842a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3842a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: two standing
    modifiers, both gated on the same sentence.

    Neither prints a type word, so both are untyped. Cover is a fact about
    two positions and is asked at the moment of the swing -- `cover_between`
    traces it then, and nothing stores it -- which is also why the gate
    cannot be computed once when the trait is armed.
    """
    me = c.me

    def unsheltered(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if not ctx.get("ranged") or victim is None:
            return False
        return cover_between(c.world, me, victim, ranged=True) is Cover.NONE

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=unsheltered)
    c.bonus("damage", 3, on=me, until=When.ENCOUNTER, when=unsheltered)


@power(
    "m3842a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    dropped=("c.combined_attack()",),
)
def m3842a3(c: Cast) -> None:
    """One shot carrying the whole group's bonus.

    Who is taking part is counted by `Ident.ref` and by whether the target is
    inside that creature's own printed range, which is what "participating"
    can mean on a board -- `_kin_within` counts this creature in, so the
    count is the printed "for each" without an adjustment.

    The bonuses are lent for this one shot and the row it borrows is its own
    ranged attack, so the printed numbers stay in that header and are never
    written twice. The pairing itself is the gap: nothing rolls one attack on
    behalf of several creatures, and the others do not pay for it.
    """
    victim = c.target
    if victim is None:
        return
    joined = len(_kin_within(c, 15, victim)) or 1
    c.bonus("attack", joined, on=c.me, until=When.EOT, once=True)
    c.bonus("damage", joined, on=c.me, until=When.EOT, once=True)
    c.use_power("m3842a1", on=victim)


# ==========================================================================
# m3900
# ==========================================================================


@power(
    "m3900a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage(bonus=9, kind=MINION),
)
def m3900a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m3900a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(8),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=15),
    damage=Damage(bonus=9, kind=MINION),
)
def m3900a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m3930
# ==========================================================================


@power(
    "m3930a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage(bonus=9, dtype=DamageType.COLD, kind=MINION),
)
def m3930a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M3930_MISSED = "a melee attack misses it"


@power(
    "m3930a1",
    level=13,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.COLD],
    damage=Damage(bonus=4, dtype=DamageType.COLD, kind=MINION),
    trigger=_M3930_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M3930_MISSED),
)
def m3930a1(c: Cast) -> None:
    """No attack roll is printed, so the four is dealt outright -- still from
    the header, because it is this creature's flat minion damage and rescales
    with the rest of them.

    The attacker is read off the trigger rather than from `c.target`: the row
    targets itself, which is what a reaction with no printed target line is.
    """
    ev = c.trigger
    foe = getattr(ev, "attacker", None) if ev is not None else None
    if foe is None:
        return
    c.hit(on=foe)
    c.slide(3, on=foe)


# ==========================================================================
# m4216
# ==========================================================================


@power(
    "m4216a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage(bonus=6, kind=MINION),
)
def m4216a0(c: Cast) -> None:
    """"6 damage (crit 9)" needs the branch written out: `c.damage` maxes
    *dice* on a critical and a minion's damage is a flat number with no dice
    in it, so the printed critical total would otherwise come out as the
    ordinary one."""
    if not c.strike():
        return
    if c.crit:
        c.flat(9)
    else:
        c.hit()


@power(
    "m4216a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage(bonus=6, kind=MINION),
)
def m4216a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4216a2",
    level=13,
    usage=AT_WILL,
    action=ActionType.MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4216a2(c: Cast) -> None:
    """No attack roll is printed: the mark lands. "Until the end of its next
    turn" is the target's turn, which is `When.EOTNT`."""
    c.mark(until=When.EOTNT)


@power(
    "m4216a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m4216a3(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m5109
# ==========================================================================


@power(
    "m5109a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage(bonus=10, kind=MINION),
)
def m5109a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5252
# ==========================================================================


@power(
    "m5252a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5252a0(c: Cast) -> None:
    """Who is inside is asked of the aura as each turn opens: the aura
    travels with its owner and a stored list of members would be stale the
    moment either of them moved. A ghost turn is nobody's turn and is left
    out, and "until the start of its next turn" is measured against the
    creature caught rather than against this one."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def clinging(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slowed(until=When.SOTNT, on=ev.actor)

    c.watch(TurnStart, clinging, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5252a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage(bonus=8, kind=MINION),
)
def m5252a1(c: Cast) -> None:
    """The heavier number replaces the printed one rather than adding to it:
    one packet is what the card deals, and two would be measured against
    resistance twice. The eight stays in the header, where a rescale finds
    it. m5252a0's aura is what makes the heavier number the common case."""
    victim = c.target
    if victim is None or not c.strike():
        return
    if c.is_(Condition.SLOWED, on=victim):
        c.flat(12)
    else:
        c.hit()


@power(
    "m5252a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5252a2(c: Cast) -> None:
    """The flight is lent for the length of the move: the block has no fly
    mode of its own and `c.move(at="fly")` measures the mode rather than the
    ground speed, so without the grant it walks.

    "It must land at the end of this movement, or it falls" is the landing
    asked for outright: `c.fall` is what the printed clause means where the
    move has left it off the ground, and the grant expires with the turn so
    nothing keeps it up afterwards.
    """
    c.mode("fly", 5, until=When.EOT, on=c.me)
    c.move(5, at="fly")
    if c.height() > 0:
        c.fall(on=c.me)


# ==========================================================================
# m5822
# ==========================================================================


@power(
    "m5822a0",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5822a0(c: Cast) -> None:
    """Twenty-four hours later is after every fight this engine runs: the
    whole printed clause is what happens between encounters, so the row is
    finished and deliberately inert rather than unwritten. `c.reanimate`
    would be the wrong verb -- it puts a creature back on *this* board, which
    is a different sentence."""


@power(
    "m5822a1",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.untargetable()",),
)
def m5822a1(c: Cast) -> None:
    """Being an illegal target is the whole of this row, and nothing says it.

    `c.conceal` and `c.invisible` change the odds of being hit and
    `Condition.REMOVED` takes the creature out of the fight altogether;
    neither is "cannot be the target of any attack" while it stands there
    fighting. The rider half is sayable -- `c.rider()` and its level -- but
    with nothing to gate there is no row to gate, so this is a `todo` and
    not a `dropped`.
    """


@power(
    "m5822a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.ZONE],
)
def m5822a2(c: Cast) -> None:
    """The squares it left, which only `Moved.from_` knows.

    A footprint is taken at both ends of the step and the zone is the
    difference, so a Large body that steps one square leaves behind the two
    it vacated and not the four it was standing in. `EnterSquare` and
    `LeaveSquare` are per square and would each want pairing back up; this
    is one event with both ends of the step on it.

    "Ends its turn in the zone" is a `TurnEnd` watch, armed for the zone's own
    lifetime, rather than `c.burns` -- that one pays on entering and on
    starting a turn, which is a different sentence. Who is standing there is
    asked of the **squares** and not of `zones.occupants`: that index is kept
    by the movement events, and a creature put into the zone by anything that
    does not step -- a teleport that writes a position, a slide resolved
    elsewhere -- is missing from it while plainly standing in the fire.

    `c.size_of()` is asked of `c.me` outright. It follows `c.target`, like
    every other method whose subject is somebody else, and on a trait that
    has no target it answers Medium for everything -- which made a Large
    body leave a one-square trail instead of its footprint.
    """
    me = c.me
    size = c.size_of(me)

    def trail(ev: Moved) -> None:
        if ev.actor != me:
            return
        left = footprint(ev.from_, size) - footprint(ev.to, size)
        if not left:
            return
        c.zone(left, until=When.EONT, label=c.ref)

        def scorch(turn: TurnEnd) -> None:
            if turn.ghost or turn.actor not in c.in_squares(left, side="enemy"):
                return
            c.flat(10, dtype=DamageType.FIRE, on=turn.actor)

        c.watch(TurnEnd, scorch, until=When.EONT, on=me, label=c.ref)

    c.watch(Moved, trail, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5822a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=11, kind=MINION),
)
def m5822a3(c: Cast) -> None:
    """The heavier number replaces the printed one, as m5252a1's does. Read
    off `c.result`, because a one-shot grant of combat advantage is already
    spent by the time the blow lands and asking the board again comes back
    false on exactly the swings the card pays for."""
    if not c.strike():
        return
    if c.result is not None and c.result.advantage:
        c.flat(15)
    else:
        c.hit()


@power(
    "m5822a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=11, kind=MINION),
)
def m5822a4(c: Cast) -> None:
    """The step is an Effect line, so it happens whether or not the blow
    did."""
    if c.strike():
        c.hit()
    c.shift(1)


# ==========================================================================
# m6188
# ==========================================================================


@power(
    "m6188a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=10, kind=MINION),
)
def m6188a0(c: Cast) -> None:
    """"Granting combat advantage to it" is the same question the swing
    already answered, so it is read off `c.result` rather than asked again --
    and that is the only reading that catches a one-shot grant, which is
    spent by the time the blow lands. The heavier number replaces the printed
    one."""
    if not c.strike():
        return
    if c.result is not None and c.result.advantage:
        c.flat(12)
    else:
        c.hit()


# ==========================================================================
# m6516
# ==========================================================================


@power(
    "m6516a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=10, kind=MINION),
    requires=_not_grabbing,
    requires_text="must have no creature grabbed",
    dropped=("c.grab(dc=)",),
)
def m6516a0(c: Cast) -> None:
    """The Requirement is a fact about this creature at the moment it acts
    and cannot be read off a target, so it is a `requires=` on an ordinary
    attack row -- not a trait, where a Requirement false at the start of the
    fight would refuse the row for good.

    The printed escape DC has nowhere to go: a grab is escaped against the
    grabber's defences and `c.grab` takes no number.
    """
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m6516a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    damage=Damage(bonus=15, kind=MINION),
    dropped=("Target.relation",),
)
def m6516a1(c: Cast) -> None:
    """An Effect line with no attack roll: the fifteen simply lands, which is
    why the header declares damage and no attack.

    The printed target line is "one creature grabbed by it", which `Target`
    cannot say, so the victim is taken from the grab rather than from
    whoever the chooser offered -- `Target.relation` is the gap, and the AI
    policy reading the header is what it costs.
    """
    held = sorted(c.grabbing())
    if not held:
        return
    c.hit(on=held[0])


# ==========================================================================
# m6518
# ==========================================================================


@power(
    "m6518a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=10, dtype=DamageType.NECROTIC, kind=MINION),
)
def m6518a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EOTNT)


_M6518_DROPPED = "it drops to 0 hit points"


@power(
    "m6518a1",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage(bonus=10, dtype=DamageType.NECROTIC, kind=MINION),
    trigger=_M6518_DROPPED,
    on=Trigger(Dropped, about_me, _M6518_DROPPED),
    dropped=("Dropped.power", "Target.creature_kind"),
)
def m6518a1(c: Cast) -> None:
    """A death throe, handed over in the keyword column as a standard
    at-will and written as the free action its trigger makes it.

    `EACH_OTHER` and not `EACH_CREATURE`: the burst catches friend and foe
    alike, which is what "living creatures in the burst" says, and the side
    "any" would also catch the creature setting it off.

    Two clauses the engine cannot reach. "As a result of a weapon attack"
    asks what the killing blow was made with, and `Dropped` carries who
    struck it and nothing about the blow. "Living creatures" is a target
    line `Target` cannot say, so it is asked of each target in the body
    instead.
    """
    victim = c.target
    if victim is None or not _living(c, victim) or not c.strike():
        return
    c.hit()
    if c.size_of(victim) not in (Size.SMALL, Size.MEDIUM):
        return
    health = c.world.get(victim, Health)
    if health is None or health.hp > 0:
        return
    pos = c.world.get(victim, Position)
    c.summon("m6081", at=pos.square if pos is not None else None)
