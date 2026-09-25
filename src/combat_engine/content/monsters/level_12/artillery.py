"""Monster abilities, level 12: the artillery, and one minion.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=REF,
printed=17)` and `Damage("2d8", 5)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

The conventions of the eleven levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; several rows the database files as standard actions
are plainly traits and are written as such; a stat block printing no range
at all means melee 1; a printed "Range 20/40" is a normal range and a long
one and the normal one is what `Range` holds; a printed "Effect (Immediate
Interrupt)" is `action=INTERRUPT` whatever the database's action column
says; and a helper written for an earlier level is imported rather than
copied.

Seven things this file had to settle.

**A death throe is a free action and never `ActionType.NONE`.** Three rows
here print "(No Action)" or nothing at all. `NONE` is the spelling of a
trait: `Encounter._arm_traits` uses every `NONE` row once as the fight
begins -- which would set the burst off before anybody had been hit -- and
`triggers.WINDOW_OF` has no entry for it, so the dispatcher would never
offer the row afterwards either. `FREE` is the window the printed trigger
wants, and the dispatcher makes the exception that lets a creature answer
its own `Dropped`.

**Two printed damage types, one `Damage`.** "Fire and poison damage" is one
packet of both and the header holds one `dtype`, so it keeps the first and
both keywords carry the rest -- the arrangement level 3 settled. The
ongoing half of the same sentence is one hold for the same reason: ongoing
damage of one type does not stack, and two holds of two types would be
twice the damage and two saving throws against one printed line.

**An elite with no printed second turn gets no second initiative count.**
m260 is elite and prints no row that acts twice, so none is written:
inventing a spliced turn would be inventing a printed line.

**"Does not provoke from the targets" is narrower than the header field.**
`no_provoke=True` waives the opening for everybody standing next to the
m2825, and the printed line waives it only for the creatures being shot at.
So it is a veto on `OpportunityWindow` -- the shape m4709a0 settled seven
levels down -- and who is being shot at is read off the `PowerUsed` the
shot announced a beat earlier, which is the only place the target list of
the row in flight exists.

**A zone that outlives the creature that made it.** m3056a2 is a death
throe, so the reinforcement its zone promises arrives on a turn its maker
will never take: `TurnStart` is ticked for the dead as a ghost, and that
tick is exactly "when the m3056's next turn would occur".

**A curse that walks.** m4938a0 is the same sentence level 11's m4937a0
settled, and is written out again rather than imported: those helpers key
the stacking guard to their own ref, and two stat blocks cursing the same
creature is two curses that should each be found by their own owner.

**`Bloodied` about itself cannot fire on the audit board**, which sets the
caster to half hit points before the fight starts. m2867a3 is such a row
and reports UNUSED however correct it is; it was driven by hand, at full
health, to check. See the report.

Artillery first, then the minion, each in ref order.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_05.brutes import _defences_down
from combat_engine.content.monsters.level_10.soldiers import _moved_into_flank
from combat_engine.content.monsters.level_11.controllers import _softened
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
    AreaBurst,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Damage,
    DamageType,
    Dropped,
    Effect,
    Keyword,
    Melee,
    Mod,
    MoveEnd,
    OpportunityWindow,
    PowerUsed,
    Ranged,
    Square,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    both,
    by_melee,
    closed_on_me,
    distance,
    enemy_within,
    get,
    power,
    targets_me,
    use,
)
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, distance_between, squares, team
from combat_engine.engine.triggers import Trigger, about_me

#: How far out a creature shoved by m2552a3 is allowed to be looked for, and
#: how far m2552a5 will step to get out of a swing's way. Both printed lines
#: name a nearest square and no distance at all, so the search is bounded by
#: something rather than by the whole board.
_NEARBY = 6


def _one_hold(
    c: Cast,
    victim: int,
    *,
    ongoing: tuple[int, DamageType],
    mods: list[Mod],
) -> Effect:
    """"Save ends both", where one of the two halves is ongoing damage.

    `_held_and_softened` a level down is the same sentence and applies the
    burn straight to the hold, which was right before ongoing damage of one
    type stopped stacking. It cannot be used here: a creature already taking
    a worse burn of this type would end up with two, and two saving throws.
    So the rule `c.ongoing` enforces is enforced here as well -- a weaker
    burn is refused and a stronger one supersedes -- while the penalty still
    lands, because it is the other half of one printed sentence.
    """
    amount, dtype = ongoing
    standing = [
        e
        for e in c.world.effects.of(victim)
        if e.ongoing is not None and e.ongoing[1] is dtype
    ]
    worst = max((e.ongoing[0] for e in standing), default=0)
    if worst >= amount:
        burn = None
    else:
        burn = ongoing
        for e in standing:
            c.world.effects.end(e, "superseded by worse of the same type")
    return c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        ongoing=burn,
        mods=[(victim, m) for m in mods],
    )


def _free_square_outside(c: Cast, who: int, area: frozenset[Square]) -> Square | None:
    """The nearest square that creature fits in and the blast does not cover.

    "Slides the target to the nearest space outside the blast" names the
    destination outright, which no bare `c.slide` can do -- it offers every
    square in range to the decider instead.
    """
    from combat_engine.engine import footprint
    from combat_engine.engine.components import Position
    from combat_engine.engine.grid import spread

    pos = c.world.get(who, Position)
    if pos is None:
        return None
    here = pos.square
    options = [
        sq
        for sq in sorted(spread(pos.squares, _NEARBY))
        if sq not in area
        and all(
            c.world.grid.passable(part) and c.world.grid.occupant(part) in (None, who)
            for part in footprint(sq, pos.size)
        )
    ]
    return min(options, key=lambda sq: (distance(sq, here), sq)) if options else None


def _shot_in_flight(world: World, me: int) -> PowerUsed | None:
    """The row this creature is using right now, and who it is aimed at.

    `use` announces `PowerUsed` immediately before it opens the opportunity
    windows a ranged power opens, so the most recent one by this creature is
    the shot being taken. Nothing on `OpportunityWindow` carries a target
    list, and the printed line is about the targets.
    """
    for past in reversed(world.bus.log):
        if isinstance(past, PowerUsed) and past.actor == me:
            return past
    return None


# ==========================================================================
# m2551
# ==========================================================================


_M2551_FELLED = "the m2551 drops to 0 hit points"


@power(
    "m2551a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m2551a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2551a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
    trigger=_M2551_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M2551_FELLED),
)
def m2551a1(c: Cast) -> None:
    """It comes apart in a sheet of flame.

    A creature may answer its own downfall -- the dispatcher makes the
    exception for exactly this shape. Filed as a standard action and plainly
    a triggered one; `FREE` rather than `ActionType.NONE`, which is the
    spelling of a trait and would go off as the fight began.
    """
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m2551a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m2551a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m2552
# ==========================================================================
#
# Two of this card's sentences spell a row's id as one belonging to another
# stat block. The rows on this one are what they plainly mean.


_M2552_SWUNG_AT = "an enemy makes a melee attack roll against the m2552"


@power(
    "m2552a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 5),
)
def m2552a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m2552a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE),
)
def m2552a1(c: Cast) -> None:
    """Fire *and* poison: the header keeps the first of the two printed types
    and both keywords carry the rest.

    "Ongoing 5 fire and poison damage and a -2 penalty to attack rolls (save
    ends both)" is one hold carrying both halves, which is what makes it one
    saving throw.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _one_hold(c, victim, ongoing=(5, DamageType.FIRE), mods=_softened(c, attack=2))
    c.note(f"{c.ref}: the burn is fire and poison damage")


@power(
    "m2552a2",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.POISON],
)
def m2552a2(c: Cast) -> None:
    """The printed Effect names a row belonging to a level 4 stat block --
    a minor-action encounter shot that burns and takes two off the target's
    attack rolls, which is this creature's own m2552a1 to the letter. That
    is the row it plainly means, and this is the minor action that fires it.

    Declared with no target: the row it reaches for picks its own.
    """
    use(c.world, c.me, "m2552a1", spend=False)


@power(
    "m2552a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2552a3(c: Cast) -> None:
    """They are driven out of the blast, and the way out costs them.

    The destination is named rather than offered: "the nearest space outside
    the blast" is an instruction, and a bare `c.slide` would hand every
    square in range to the decider. The distance is whatever it takes to get
    there, because the printed line gives none.

    "This forced movement provokes opportunity attacks" is the exception to
    the rule that forced movement never does, so the windows are opened by
    hand -- for whoever was standing next to the target as it was dragged
    away, which is who an ordinary walk out of that square would have given
    an opening to.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    watchers = [
        friend
        for friend in c.within(1, of=victim, side="ally")
        if friend != c.me and alive(c.world, friend)
    ]
    where = _free_square_outside(c, victim, c.area())
    if where is None:
        return
    need = min(distance(sq, where) for sq in squares(c.world, victim))
    if c.slide(need, on=victim, to=where):
        for friend in sorted(watchers):
            c.provoke(friend, on=victim)


@power(
    "m2552a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.POISON],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", dtype=DamageType.FIRE, kind=LIMITED),
)
def m2552a4(c: Cast) -> None:
    """A damage line with no bonus at all, which is what the card prints: the
    burn is the weight of this one."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _one_hold(c, victim, ongoing=(10, DamageType.FIRE), mods=_softened(c, attack=2))
    c.note(f"{c.ref}: the burn is fire and poison damage")


@power(
    "m2552a5",
    level=12,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2552_SWUNG_AT,
    on=Trigger(AttackDeclared, when=both(targets_me, by_melee), text=_M2552_SWUNG_AT),
)
def m2552a5(c: Cast) -> None:
    """It steps aside and something else is standing there.

    Declared on `AttackDeclared`, which is the only window in which the blow
    can still be pointed somewhere else: after the roll there is a result,
    and moving it would mean rolling again. That is also what makes this an
    interrupt rather than the reaction the shape suggests.

    How far "beyond the triggering attack's reach" is, is read off the row
    swinging rather than assumed to be one square -- a reach 3 weapon needs
    four squares of daylight. The step is taken first so the square it leaves
    is free for the thing that appears in it.

    The printed line also puts the newcomer directly after the m2552 in the
    order. `Encounter` splices a creature in by its own initiative and has no
    way to place one at a named count, so that half is noted. See the report.
    """
    ev = c.trigger
    attacker = getattr(ev, "attacker", None)
    if attacker is None:
        return
    swing = get(getattr(ev, "power", "") or "")
    reach = swing.reach_of(getattr(ev, "branch", 0)).size if swing is not None else 1
    was = c.here
    mine = squares(c.world, attacker)
    out = [
        sq
        for sq in c.world.reachable_squares(c.me, _NEARBY)
        if min(distance(sq, theirs) for theirs in mine) > reach
    ]
    if out:
        c.shift(1, to=min(out, key=lambda sq: (distance(sq, was), sq)))
    made = c.summon("m315", at=was)
    if made:
        c.redirect(to=made)
        c.note(f"{c.ref}: it acts immediately after the m2552 in the order")


# ==========================================================================
# m260
# ==========================================================================
#
# Elite, and it prints no row that acts twice: an elite is two creatures'
# worth of hit points and experience before it is anything else, and a
# second initiative count would be a printed line this card does not have.


def _wilted(c: Cast, victim: int) -> Effect:
    """"Ongoing 5 poison damage, a -2 penalty to Fortitude, and a -2 penalty
    to saving throws (save ends all)" -- one hold, so it is one saving throw.

    `_softened` is no use for the modifier half: its defence penalty is all
    four of them, and this line names one defence and the saving throw
    itself.
    """
    return _one_hold(
        c,
        victim,
        ongoing=(5, DamageType.POISON),
        mods=[
            Mod(what=FORT.value, value=-2, kind="untyped", label=c.ref),
            Mod(what="save", value=-2, kind="untyped", label=c.ref),
        ],
    )


@power(
    "m260a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 8),
)
def m260a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m260a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
)
def m260a1(c: Cast) -> None:
    """One creature or two, and the one is shot at twice.

    `UpTo(2)` is the printed "one or two creatures", and the second shot is
    rolled here rather than through `use`: the row is already in flight, and
    the guard that stops a row answering itself would refuse it.
    """
    for _ in range(2 if c.first and c.last else 1):
        if c.strike():
            c.hit()
            c.immobilized(until=When.SAVE_ENDS)


@power(
    "m260a2",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 8, dtype=DamageType.POISON, kind=LIMITED),
)
def m260a2(c: Cast) -> None:
    """"Creatures in the blast", so it catches its own side too.

    The printed Effect is not conditional on anything landing, and it happens
    once rather than once per creature caught -- so it is hung on the last
    target, by which point every attack has been rolled.
    """
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _wilted(c, victim)
    if c.last:
        c.shift(c.speed_of())


@power(
    "m260a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 9, kind=LIMITED, half_on_miss=True),
)
def m260a3(c: Cast) -> None:
    """The damage line prints no type -- only the keyword is thunder -- so the
    header carries none."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


# ==========================================================================
# m2825
# ==========================================================================


_M2825_FLANKED = "a creature moves into a space where it flanks the m2825"


@power(
    "m2825a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 4),
)
def m2825a0(c: Cast) -> None:
    """The charge rider is read off the use in hand rather than armed as a
    watch: this is the row being swung, so `c.charge` already says whether
    the engine is running it as a charge, and a watch laid down here would be
    laid down again on every swing."""
    if c.strike():
        c.hit()
        if c.charge:
            c.damage("1d6")


@power(
    "m2825a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 4),
    trigger=_M2825_FLANKED,
    on=Trigger(MoveEnd, when=_moved_into_flank, text=_M2825_FLANKED),
)
def m2825a1(c: Cast) -> None:
    """Filed as a move action and printed as an immediate reaction; the
    trigger line is what says which it is. `MoveEnd` is the moment the
    printed sentence names -- the question is about the square the creature
    has arrived in, and `MoveStart` fires before the first step."""
    if c.strike():
        c.hit()


@power(
    "m2825a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(25),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d12", 2),
)
def m2825a2(c: Cast) -> None:
    """Range 25/50: the header carries the short range, which is the only one
    the engine measures.

    The second shot is rolled here rather than through `use`, which would be
    refused as the row answering itself, and it is offered the other enemies
    as well as the first -- "the same target or a different one" is the
    printed choice.
    """
    if c.strike():
        c.hit()
    victim = c.target
    again = sorted(
        foe
        for foe in c.enemies()
        if alive(c.world, foe) and c.distance(foe) <= 25 and c.can_see(foe)
    )
    if victim in again:
        again.remove(victim)
        again.insert(0, victim)
    other = c.choose(again, f"{c.ref}: who the second shot is at") if again else None
    if other is not None and c.strike(on=other):
        c.hit(on=other)


@power(
    "m2825a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(25),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=19),
    damage=Damage("1d12", 5),
)
def m2825a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


@power(
    "m2825a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(25),
    target=UpTo(3),
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("1d12", 5, kind=LIMITED),
)
def m2825a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2825a5",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2825a5(c: Cast) -> None:
    """Shooting at somebody gives the people it is shooting at no opening.

    Not `no_provoke=True` on each ranged row, which waives the opening for
    *everybody* standing next to it: the printed line waives it only for the
    creatures being shot at, and the man with the axe beside it still gets
    his swing. So the window is refused as it opens, the way m4709a0 refuses
    one only while its owner is climbing.

    Who is being shot at is read off the `PowerUsed` the shot announced a
    beat earlier -- `use` emits it immediately before it opens these windows
    -- because nothing on `OpportunityWindow` carries a target list.
    """
    me = c.me

    def spare_the_targets(ev: OpportunityWindow) -> None:
        if ev.provoker != me:
            return
        shot = _shot_in_flight(c.world, me)
        if shot is None or ev.actor not in shot.targets:
            return
        p = get(shot.power)
        if p is not None and p.reach.kind == "ranged":
            ev.cancel(c.ref)

    c.watch(
        OpportunityWindow,
        spare_the_targets,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )


# ==========================================================================
# m2867
# ==========================================================================


_M2867_CLOSED = "an enemy moves adjacent to the m2867"
_M2867_BLED = "the m2867 is first bloodied"


@power(
    "m2867a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 5),
)
def m2867a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2867a1",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING),
    trigger=_M2867_CLOSED,
    on=Trigger(
        AdjacencyGained, when=both(closed_on_me, enemy_within(1)), text=_M2867_CLOSED
    ),
)
def m2867a1(c: Cast) -> None:
    """Filed as a move action and printed as an immediate interrupt; the
    trigger line is what says which it is. `AdjacencyGained` is the moment
    the printed sentence names, and `closed_on_me` is what keeps the row from
    answering its own approach -- the event is emitted mirrored, so both ends
    see it."""
    if c.strike():
        c.hit()


@power(
    "m2867a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=19),
    damage=Damage("2d8", 5, dtype=DamageType.LIGHTNING),
)
def m2867a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2867a3",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
    trigger=_M2867_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M2867_BLED),
)
def m2867a3(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2867a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING),
)
def m2867a4(c: Cast) -> None:
    """Everybody in the burst, its own side included -- which is what the
    clause about allies is there for.

    "One extra point for each creature in the burst" counts the crowd off the
    squares the burst covers rather than off the target list, because the
    printed line counts creatures rather than targets.

    The recharge bonus cannot be written: `actions.recharge` rolls a d20
    against the number in the header and reads no modifier, so there is
    nowhere for a +1 to go. Noted rather than approximated. See the report.
    """
    crowd = len(c.in_squares(c.area()))
    if not c.strike():
        return
    c.hit()
    if crowd:
        c.flat(crowd, dtype=DamageType.LIGHTNING)
    if c.target in c.allies():
        c.note(f"{c.ref}: +1 to its recharge rolls at the start of its next turn")


# ==========================================================================
# m3056
# ==========================================================================


_M3056_FELLED = "the m3056 drops to 0 hit points"


@power(
    "m3056a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d4", 6, dtype=DamageType.FIRE),
)
def m3056a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3056a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE),
)
def m3056a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3056a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d8", 5, dtype=DamageType.FIRE),
    trigger=_M3056_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M3056_FELLED),
)
def m3056a2(c: Cast) -> None:
    """It burns where it fell, and something comes out of the fire.

    The zone is laid once for the whole burst rather than once per creature
    caught, and `c.burns` is what gives it teeth -- entering it and starting
    a turn in it, once each per round, which is the printed pair.

    "When the m3056's next turn would occur" is the creature's own next
    `TurnStart` and is not asked to be a ghost's: a creature at 0 hit points
    is dying rather than dead, keeps its slot, and its turn comes round in
    the ordinary way -- and a slot ticked for the dead is ticked too. Either
    is the moment the printed line names.

    `once=True` is not what makes it happen once: the bus spends a one-shot
    subscription on the first event of that class whoever it is about, so
    the watch would have been torn down by the next creature's turn
    beginning. The hold ends itself instead, once it has paid out.
    """
    if c.strike():
        c.hit()
    if not c.first:
        return
    blaze = c.zone(c.area(), until=When.ENCOUNTER)
    c.burns(blaze, 5, DamageType.FIRE)
    me, inside = c.me, sorted(c.area())
    hold: list[Effect] = []

    def relief(ev: TurnStart) -> None:
        if ev.actor != me or not hold:
            return
        c.summon("m3058", at=inside[0] if inside else None)
        c.world.effects.end(hold[0], "the reinforcement has arrived")

    hold.append(
        c.watch(TurnStart, relief, until=When.ENCOUNTER, on=me, label=c.ref)
    )


@power(
    "m3056a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3056a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


# ==========================================================================
# m388
# ==========================================================================


@power(
    "m388a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 4),
)
def m388a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. Only the burn is printed as fire, so the header carries no type
    and the ongoing names one."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m388a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(12),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d6", 1),
)
def m388a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m388a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d6", 1, half_on_miss=True),
)
def m388a2(c: Cast) -> None:
    """The miss is half the damage and no burn, which is why the two are not
    written as one branch: three of this creature's rows set the same fire,
    and only the ones that land do."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
    else:
        c.hit(half=True)


# ==========================================================================
# m4896
# ==========================================================================


@power(
    "m4896a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 4),
)
def m4896a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4896a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d8", 7),
)
def m4896a1(c: Cast) -> None:
    """Range 10/20: the header carries the short range. "Pushes 2 squares or
    knocks it prone" is the thrower's choice and is asked as one."""
    if not c.strike():
        return
    c.hit()
    if c.choose(["push", "prone"], f"{c.ref}: shove it or floor it") == "prone":
        c.prone()
    else:
        c.push(2)


@power(
    "m4896a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m4896a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m4938
# ==========================================================================
#
# The aura sentence names the thing it inflicts by an id belonging to a
# different stat block. Nothing on that block is reached: the curse is this
# trait's own, and is filed under this trait's ref.


def _cursed_by(c: Cast, who: int) -> bool:
    """Is that creature already carrying m4938a0's curse?

    The guard the printed "multiple curses do not stack" asks for, and the
    same question the spreading half asks of a neighbour. Keyed to this
    trait's own ref: another stat block's curse is another stat block's to
    find.
    """
    return any(eff.label.startswith(c.ref) for eff in c.world.effects.of(who))


def _lay_curse(c: Cast, who: int) -> None:
    """-2 to every defence and vulnerable 5 to everything, for a turn.

    Two holds rather than one, because a vulnerability is not a `Mod` and
    `c.vulnerable` keeps its own -- so the defence hold ends the other with
    it and both run out on the same clock.
    """
    if _cursed_by(c, who):
        return
    hold = _defences_down(c, who, 2, When.EOTNT)
    weakness = c.vulnerable(5, on=who, until=When.EOTNT)
    if weakness is not None:
        hold.on_end.append(lambda: c.world.effects.end(weakness, "the curse lifts"))


@power(
    "m4938a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4938a0(c: Cast) -> None:
    """An aura 1 that curses whoever starts a turn in it, and a curse that
    walks to the next creature along.

    Not the aura helper, whose hold is carried for as long as its owner
    stands inside: this one is taken at a boundary and then keeps its own
    clock, so membership is measured at that moment and read off the zone the
    aura made rather than by distance.

    The spreading half is checked on the same turn beginning and against the
    *cursed creature's own side*: "any ally of that creature" is who the
    printed line names, so a second m4938 standing beside a cursed enemy does
    not catch it.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def each_turn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        who = ev.actor
        if who in c.enemies() and who in c.world.zones.occupants(ring):
            _lay_curse(c, who)
            return
        mine = team(c.world, who)
        for other in c.within(1, of=who, side="any"):
            if other != who and team(c.world, other) is mine and _cursed_by(c, other):
                _lay_curse(c, who)
                return

    c.watch(TurnStart, each_turn, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4938a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5),
)
def m4938a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4938a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage("2d8", 5, dtype=DamageType.POISON),
)
def m4938a2(c: Cast) -> None:
    """Range 20/40: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m4938a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=17),
    damage=Damage("2d8", 5),
    requires_text="the m4938 must be wielding a ranged weapon",
)
def m4938a3(c: Cast) -> None:
    """The printed Requirement is a piece of equipment, and a monster in this
    engine carries no `Gear` -- `c.wielding` answers for a character's kit
    and is false for every stat block there is. Carried as the printed text
    so the card shows it, and not as a gate, which would refuse the row for a
    reason that is about the engine rather than the board.

    "Grants combat advantage" with nobody named is the whole of the m4938's
    side, which is `to="allies"`.
    """
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "m4938a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d8", 5, kind=LIMITED),
    requires_text="the m4938 must be wielding a ranged weapon",
)
def m4938a4(c: Cast) -> None:
    """The rot spreads to whoever stands beside the rotting creature.

    "Until the target saves" is the burn's own lifetime rather than a
    duration of its own, so the watch is ended by the hold that carries the
    ongoing damage -- one saving throw ends both halves, which is what the
    printed line says. The damage line itself prints no type; only the burn
    and the keyword are necrotic.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    burn = c.ongoing(10, DamageType.NECROTIC)
    if burn is None:
        return

    def rot(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == victim:
            return
        if team(c.world, ev.actor) is not team(c.world, victim):
            return
        if distance_between(c.world, ev.actor, victim) <= 1:
            c.flat(10, dtype=DamageType.NECROTIC, on=ev.actor)

    spreading = c.watch(
        TurnStart, rot, until=When.ENCOUNTER, on=victim, label=f"{c.ref} spread"
    )
    burn.on_end.append(lambda: c.world.effects.end(spreading, "the target saved"))


# ==========================================================================
# The minion. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# ==========================================================================


# --------------------------------------------------------------------------
# m4970
# --------------------------------------------------------------------------


_M4970_FELLED = "the m4970 drops to 0 hit points"


@power(
    "m4970a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=8, kind=MINION),
)
def m4970a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4970a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage(bonus=8, dtype=DamageType.PSYCHIC, kind=MINION),
    trigger=_M4970_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4970_FELLED),
)
def m4970a3(c: Cast) -> None:
    """Printed "(No Action)" and written `FREE`: `ActionType.NONE` is the
    spelling of a trait, which `Encounter._arm_traits` uses once as the fight
    begins and which the dispatcher has no window for -- so the burst would
    go off at the top of the fight and never again."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
