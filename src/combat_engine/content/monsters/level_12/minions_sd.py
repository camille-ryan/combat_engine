"""Monster abilities, level 12: the rest of the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. A
minion deals its printed number on a hit and takes none of this specially --
`kind=MINION` is what says the number is flat because the creature is one,
and its single hit point is in the database like every other number.

Filed here rather than appended to `minions.py` or `minions_sc.py`, which
were each written by another batch; a tree-wide edit has destroyed one
agent's work before.

The conventions of the eleven levels below are kept: a **trait** is a row
that costs no action, has no target, and arms the watches that hold it for
the rest of the fight; several rows the database files as standard actions
are plainly traits and are written as such; a stat block printing no range at
all means melee 1; a printed "Ranged 20/40" is a normal range and a long one
and the normal one is what `Range` holds; a death throe is `FREE` and never
`ActionType.NONE`, which is the spelling of a trait and would go off as the
fight began; and a helper written for an earlier level is imported rather
than copied.

Eight things this file had to settle.

**"One of its own kind adjacent to the target" is counted off `Powers`.**
Four rows here scale on how many copies of the creature are standing next to
their victim, and nothing on the board records a species. What it does record
is which rows a creature knows, and a stat block's melee row is as good an
identity as the engine has -- so the count asks for that ref.

**A scaling flat damage line stays in the header.** "2 damage per copy
adjacent" is the header's `Damage(bonus=2, kind=MINION)` dealt once per copy,
not a hand-rolled multiple: `c.hit` is what rescales a minion's number and a
product written into the body would not.

**Two numbers on one damage line, and the header holds one.** "6 necrotic
damage (8 against a bloodied target)" keeps the six, because that is what
rescales, and the heavier number is dealt flat in its place -- the
arrangement level 10 settled on for the same shape.

**A printed critical on a flat line is the difference, not the total.** "8
fire damage (crit 12)" has no dice for a critical to maximise, so the four is
added on top of the declared eight and the eight still rescales.

**Sunlight is a property of the fight, not of anybody in it**, which is what
`c.terrain` asks, and it is asked at each turn boundary rather than once,
because a fight can move into the open. "Only a single move action" is the
budget itself: no condition takes the standard and the minor and leaves the
move.

**A grab that travels is a slide of the captive into the square its captor
left.** `Moved` is the only event that carries `from_`, which is exactly the
square the grabbed creature has to end up in for the hold to survive the
step.

**"No other copy has used this power this turn" is read off the log.**
`once_per_round` counts on one creature, and the printed line counts across
every copy on the board -- so the question is asked of the events since the
current turn began.

**A tether between two stat blocks has nothing to hold it.** Two rows print
"can be no more than 20 squares away from" another creature, and there is no
relation, no component and no verb for a leash; the whole of each row is that
sentence, so each is refused in play rather than half-written.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_10.lurkers import EVERY_DEFENCE
from combat_engine.content.monsters.level_12.minions import _squares_moved_this_turn
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
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    Budget,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    Powers,
    Ranged,
    Size,
    Square,
    Target,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    World,
    power,
    targets_me,
)
from combat_engine.engine.events import PowerUsed
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import alive, distance_between
from combat_engine.engine.triggers import Trigger, about_me

#: The four printed words m115940a1 asks about before its extra packet of
#: poison lands. Any one of them is enough.
_HELPLESS_ENOUGH = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


def _kin_beside(c: Cast, victim: int, ref: str) -> list[int]:
    """The creatures standing next to the target that know that row.

    Nothing on the board records a species, so "another of its own kind" is
    asked of `Powers.known`: a stat block's own melee row is the closest thing
    to an identity the engine has, and two copies of one stat block are the
    only creatures that carry it. The caster counts itself, which is what
    "three of them adjacent to the target" means.
    """
    found = []
    for other in c.within(1, of=victim, side="any"):
        known = c.world.get(other, Powers)
        if known is not None and ref in known.known and alive(c.world, other):
            found.append(other)
    return sorted(found)


def _sunlight_kills(c: Cast) -> None:
    """Begins its turn in the open and it can barely move; ends it there and
    it is gone.

    Sunlight is a property of the fight rather than of anybody in it, which is
    what `c.terrain` asks, and it is asked at each boundary rather than now,
    because a fight can move into the open. The arrangement m812a1 settled
    seven levels down and m290a8 kept.
    """
    me, ref = c.me, c.ref

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.standard = 0
            budget.minor = 0
        c.note(f"{ref}: sunlight leaves it a single move action")

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{ref} dawn")
    c.watch(TurnEnd, dusk, until=When.ENCOUNTER, on=me, label=f"{ref} dusk")


def _drags_its_captive(c: Cast) -> None:
    """Whatever it is holding comes with it, and gets no free swing.

    `Moved` is the only movement event that carries `from_`, and that square
    is exactly where the captive has to end up for the hold to survive the
    step -- a grab breaks on distance, so sliding it into the square just
    vacated is the printed "the creature remains grabbed" rather than a
    separate re-grab.

    The waived opportunity attack is narrower than `no_provoke=True` on every
    row: the printed line waives it only for the creature being dragged, so it
    is laid per captive as the hold is taken.
    """
    me = c.me

    def along(ev: Moved) -> None:
        if ev.actor != me:
            return
        for caught in c.grabbing(of=me):
            c.slide(0, on=caught, to=ev.from_)
            c.no_provoke(from_=caught, on=me, until=When.ENCOUNTER)

    c.watch(Moved, along, until=When.ENCOUNTER, on=me, label=c.ref)


def _used_this_turn_by_another(c: Cast, ref: str) -> bool:
    """Has *another* creature already used that row since this turn began?

    `once_per_round` counts on one creature and the printed line counts across
    every copy on the board, so the question is the log's rather than the
    component's: walk back to the turn that is running and look for the row.

    The caster is left out, and not only because the printed word is "other":
    `use` announces `PowerUsed` **before** the body runs, so the row's own
    announcement is already the newest entry in the log by the time this is
    asked. Counting it refused every use, which is a row that looks finished
    and never fires.
    """
    me = c.me
    for past in reversed(c.world.bus.log):
        if isinstance(past, TurnStart) and not past.ghost:
            return False
        if isinstance(past, PowerUsed) and past.power == ref and past.actor != me:
            return True
    return False


# ==========================================================================
# m1150
# ==========================================================================


_M1150_FELLED = "the m1150 drops to 0 hit points"


@power(
    "m1150a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=5, kind=MINION),
)
def m1150a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m1150a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.POLYMORPH],
    attack=Attack(vs=WILL, printed=14),
    trigger=_M1150_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M1150_FELLED),
)
def m1150a1(c: Cast) -> None:
    """It takes somebody with it when it goes.

    The printed consequence names an affliction and the only mechanic in the
    name is domination, so that is what lands. No duration is printed at all;
    save ends is what every other hold of this weight on this level carries,
    and inventing a longer one would be inventing a printed line. See the
    report.

    No damage is printed, so `c.hit` is never called and the header declares
    none. `FREE` rather than `ActionType.NONE`: the latter is the spelling of
    a trait and the burst would go off as the fight began.
    """
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m1150a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1150a2(c: Cast) -> None:
    """Knowing where something is, at any distance, is a sense with no combat
    consequence: nothing on a board is found by it and nothing is rolled for
    it. Complete and deliberately inert."""


# ==========================================================================
# m115940
# ==========================================================================


@power(
    "m115940a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115940a0(c: Cast) -> None:
    """One sort of rough ground and not all of it, which is what the word
    `kind` is for -- the label a zone's `difficult=` gives its squares."""
    c.ignores_difficult("web", on=c.me)


@power(
    "m115940a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m115940a1(c: Cast) -> None:
    """"Plus 5 poison damage if ..." is a second packet of a different type, so
    it is dealt flat beside the declared one rather than folded into it."""
    if not c.strike():
        return
    c.hit()
    if any(c.is_(cond) for cond in _HELPLESS_ENOUGH):
        c.flat(5, dtype=DamageType.POISON)


@power(
    "m115940a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=15),
)
def m115940a2(c: Cast) -> None:
    """No damage is printed, so the header declares none and nothing is
    dealt."""
    if c.strike():
        c.immobilized(until=When.EOTNT)


# ==========================================================================
# m1628
# ==========================================================================


@power(
    "m1628a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=6, dtype=DamageType.NECROTIC, kind=MINION),
)
def m1628a0(c: Cast) -> None:
    """Two numbers on one damage line: the six stays in the header because
    that is what rescales, and the heavier number is dealt in its place."""
    if not c.strike():
        return
    if c.bloodied():
        c.flat(8, dtype=DamageType.NECROTIC)
    else:
        c.hit()


@power(
    "m1628a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1628a1(c: Cast) -> None:
    """The printed sentence names a row belonging to another stat block; it is
    plainly about this one, which is the creature the clause is printed on."""
    _sunlight_kills(c)


# ==========================================================================
# m1743
# ==========================================================================


@power(
    "m1743a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage(bonus=7, kind=MINION),
)
def m1743a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1932
# ==========================================================================


_M1932_SWARM = "at least three m1932 must be adjacent to the target"


@power(
    "m1932a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=19),
    damage=Damage(bonus=6, kind=MINION),
)
def m1932a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1932a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=2, kind=MINION),
    requires_text=_M1932_SWARM,
)
def m1932a1(c: Cast) -> None:
    """Many of them on one creature, and the damage is the crowd.

    The Requirement is about the *target*, which a `requires=` gate cannot
    ask: that one is handed `(world, eid)` and no victim at all. So it is the
    printed text the card shows, and the count is asked in the body.

    "2 damage per copy adjacent" is the declared flat line dealt once per
    copy, which is what keeps the number rescaling -- a product written into
    the body would be a hand-written number the database already holds.

    The three consequences are a ladder and are read before anything is
    applied, so the daze does not immediately make its own branch true.
    """
    victim = c.target
    if victim is None:
        return
    crowd = _kin_beside(c, victim, "m1932a1")
    if len(crowd) < 3 or not c.strike():
        return
    was_pinned = c.is_(Condition.IMMOBILIZED)
    was_dulled = c.is_(Condition.DAZED)
    for _ in crowd:
        c.hit()
    if was_dulled:
        c.hit()
    elif was_pinned:
        c.dazed(until=When.EONT)
    else:
        c.immobilized(until=When.EONT)


# ==========================================================================
# m1974
# ==========================================================================


@power(
    "m1974a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=14),
    damage=Damage(bonus=5, kind=MINION),
)
def m1974a0(c: Cast) -> None:
    """"Plus necrotic damage equal to the number of them adjacent to the
    target" is a second packet of a different type, so it is flat beside the
    declared one. The caster counts itself, because it is standing there."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    crowd = len(_kin_beside(c, victim, "m1974a0"))
    if crowd:
        c.flat(crowd, dtype=DamageType.NECROTIC)


# ==========================================================================
# m2526
# ==========================================================================


@power(
    "m2526a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=5, kind=MINION),
)
def m2526a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


# ==========================================================================
# m2557
# ==========================================================================


@power(
    "m2557a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage(bonus=6, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m2557a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m2602
# ==========================================================================


@power(
    "m2602a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=6, kind=MINION),
)
def m2602a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2602a1",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2602a1(c: Cast) -> None:
    c.shift(3)


# ==========================================================================
# m2639
# ==========================================================================


@power(
    "m2639a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=19),
    damage=Damage(bonus=7, kind=MINION),
)
def m2639a0(c: Cast) -> None:
    """Only the extra is psychic, so the declared line carries no type and the
    second packet names one."""
    if not c.strike():
        return
    c.hit()
    if c.is_(Condition.IMMOBILIZED):
        c.flat(5, dtype=DamageType.PSYCHIC)


@power(
    "m2639a1",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=Target(side="enemy", count=1, max_size=Size.MEDIUM),
    keywords=[Keyword.RANGED],
    attack=Attack(vs=FORT, printed=15),
)
def m2639a1(c: Cast) -> None:
    """"Medium or smaller target" is a size filter, which `Target` does carry
    -- so this one needs no redirection in the body. No damage is printed."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m3923
# ==========================================================================


_M3923_FELLED = "the m3923 drops to 0 hit points"


@power(
    "m3923a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=8, dtype=DamageType.FIRE, kind=MINION),
)
def m3923a0(c: Cast) -> None:
    """It steps and swings in one action.

    The printed critical is four more than the ordinary line and there are no
    dice for a critical to maximise, so the difference is dealt on top and the
    declared eight still rescales.
    """
    c.shift(1)
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(4, dtype=DamageType.FIRE)


@power(
    "m3923a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=15),
    damage=Damage(bonus=8, dtype=DamageType.FIRE, kind=MINION),
    trigger=_M3923_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M3923_FELLED),
)
def m3923a1(c: Cast) -> None:
    """It comes apart in a sheet of flame, and its own kind are the better for
    it.

    The step is taken before the burst is rolled even though the area was
    measured when the targets were chosen -- a body cannot re-aim an area it
    is already resolving, and the printed order is what is written.

    The benefit goes to elementals of its own element standing in the burst,
    which is read off the squares the area covers rather than off the target
    list: the target list is enemies and the clause is about allies. "+2
    bonus to defenses" prints no type word, so it is untyped, and four
    separate modifiers rather than one, which would be a +2 to nothing.
    """
    if c.first:
        c.shift(1)
    if c.strike():
        c.hit()
    if not c.last:
        return
    for other in sorted(c.in_squares(c.area())):
        kinds = c.kinds_of(on=other)
        if other != c.me and "elemental" in kinds and "fire" in kinds:
            for defended in EVERY_DEFENCE:
                c.bonus(defended, 2, on=other, until=When.EOTNT)


# ==========================================================================
# m3927
# ==========================================================================


_M3927_MISSED = "an attack misses the m3927"


@power(
    "m3927a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=8, kind=MINION),
)
def m3927a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3927a1",
    level=12,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=REF, printed=17),
    damage=Damage(bonus=9, kind=MINION),
    trigger=_M3927_MISSED,
    on=Trigger(Miss, when=targets_me, text=_M3927_MISSED),
)
def m3927a1(c: Cast) -> None:
    """A miss sends it somewhere else, and then at somebody.

    `charges=True` because the printed Effect *is* a charge: without it the
    engine measures a sword's reach before the run and refuses the row
    whenever the nearest enemy is further off than one square, which is every
    situation this row is for.

    The destination of the shift is named rather than offered -- "to move
    adjacent to another elemental of its kind" is an instruction and a bare
    `c.shift` hands every square in range to the decider. `c.run_at` is the
    charge's move; the swing is this row's own declared line.
    """
    mates = sorted(
        ally
        for ally in c.allies()
        if alive(c.world, ally)
        and "elemental" in c.kinds_of(on=ally)
        and c.distance(ally) <= 4
    )
    for mate in mates:
        where = _free_square_beside(c, mate)
        if where is not None and c.shift(3, to=where):
            c.temp_hp(10, on=mate)
            break
    quarry = sorted(
        (c.distance(foe), foe) for foe in c.enemies() if alive(c.world, foe)
    )
    if not quarry:
        return
    victim = quarry[0][1]
    c.run_at(victim)
    if c.strike(on=victim):
        c.hit(on=victim)
        c.prone(on=victim)


def _free_square_beside(c: Cast, who: int) -> Square | None:
    """An empty square next to that creature, for a row naming a destination.

    No movement operation will pick one -- `c.shift` offers every square in
    range to the decider -- and an occupied square is simply refused.
    """
    from combat_engine.engine import footprint
    from combat_engine.engine.grid import spread
    from combat_engine.engine.query import squares as squares_of

    taken = squares_of(c.world, who)
    size = c.size_of(on=c.me)
    for sq in sorted(spread(taken, 1) - taken):
        if all(
            c.world.grid.passable(part) and c.world.grid.occupant(part) in (None, c.me)
            for part in footprint(sq, size)
        ):
            return sq
    return None


# ==========================================================================
# m4035
# ==========================================================================


@power(
    "m4035a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=7, kind=MINION),
)
def m4035a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4035a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=19),
    damage=Damage(bonus=5, kind=MINION),
)
def m4035a1(c: Cast) -> None:
    """Ranged 20/40: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()


@power(
    "m4035a2",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4035a2(c: Cast) -> None:
    """Extra damage when the victim is already surrounded.

    Both halves of the printed line are gates on the swing rather than facts
    about now: `ctx["ranged"]` is how the damage side tells a melee blow from
    a shot, and the crowd is counted when the blow lands because it moves.
    "An extra 5 damage" prints no type word and is untyped.
    """
    me = c.me

    def outnumbered(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or ctx.get("ranged"):
            return False
        beside = [
            other
            for other in c.within(1, of=who, side="any")
            if other != who and alive(c.world, other) and other not in c.enemies()
        ]
        return len(beside) >= 2

    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=outnumbered)


# ==========================================================================
# m4130
# ==========================================================================


@power(
    "m4130a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=6, kind=MINION),
)
def m4130a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4130a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=6, kind=MINION),
)
def m4130a1(c: Cast) -> None:
    """Ranged 3/6: the header carries the short range.

    The printed Effect names a row belonging to another stat block and is
    plainly about this one. Having to go and pick the thrown weapon up again
    cannot be said: a stat block carries no `Gear`, so there is nothing on the
    ground and nothing to retrieve, and `c.forbid` would need a duration the
    card does not print. See the report.
    """
    if c.strike():
        c.hit()


@power(
    "m4130a2",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4130a2(c: Cast) -> None:
    """Two numbers in two sentences and neither prints a type word, so both
    are untyped -- and they are two calls, because one is on the roll and one
    is on the damage."""
    me = c.me

    def wounded(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.bloodied(on=who)

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=wounded)
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=wounded)


# ==========================================================================
# m5230
# ==========================================================================
#
# Three move actions, each about a heading the board does not keep. The
# distance of each is written and the facing of each is the named gap.


@power(
    "m5230a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=21),
    damage=Damage(bonus=9, kind=MINION),
)
def m5230a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5230a1",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.heading()",),
)
def m5230a1(c: Cast) -> None:
    """Its full speed forward. Nothing on the board records which way a
    creature is facing, so "directly forward or diagonally forward, and it
    cannot turn" has nowhere to be asked -- the distance is exact and the
    facing is the named gap."""
    c.move(c.speed_of(), at="fly")


@power(
    "m5230a2",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.heading()",),
)
def m5230a2(c: Cast) -> None:
    """Half its speed, and the one turn it is allowed is the same gap."""
    c.move(max(1, c.speed_of() // 2), at="fly")


@power(
    "m5230a3",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.heading()",),
)
def m5230a3(c: Cast) -> None:
    """As far as it went last time, counted off the log.

    `Moved` is one step and nothing on the board remembers a move action's
    worth of them, so the steps since this creature's turn began are what
    "the previous move action" comes to -- this creature's only movement is
    these three rows and it gets one move action a turn.
    """
    c.move(_squares_moved_this_turn(c), at="fly")


# ==========================================================================
# m5481
# ==========================================================================


@power(
    "m5481a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.tether()",),
)
def m5481a0(c: Cast) -> None:
    """A leash to another stat block, and nothing holds one.

    `c.bind` makes a servant and `c.guard` makes a protector; neither carries
    a distance, and no component, relation or verb says "these two may not be
    more than N squares apart". The whole of the row is that sentence, so it
    is refused in play rather than half-written.
    """


@power(
    "m5481a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5481a1(c: Cast) -> None:
    _drags_its_captive(c)


@power(
    "m5481a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m5481a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5481a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage(bonus=10, kind=MINION),
)
def m5481a3(c: Cast) -> None:
    """"One creature grabbed by it" is a restriction `Target` cannot express:
    it filters on side, count and size and not on what a creature is
    suffering, so the chooser may hand this row somebody its own target line
    forbids. `_restricted_to` redirects to a captive in reach rather than
    throwing the row away; `Target.kind` is the gap."""
    victim = _restricted_to(c, 1, lambda foe: c.me in c.grabbed_by(on=foe))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.dazed(until=When.EOTNT, on=victim)


# ==========================================================================
# m5482
# ==========================================================================


@power(
    "m5482a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.tether()",),
)
def m5482a0(c: Cast) -> None:
    """The same sentence m5481a0 prints, and the same gap: nothing on the
    board holds two creatures a named distance apart."""


@power(
    "m5482a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5482a1(c: Cast) -> None:
    _drags_its_captive(c)


@power(
    "m5482a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m5482a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5482a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage(bonus=10, kind=MINION),
)
def m5482a3(c: Cast) -> None:
    """The slide names its destination -- "to a square adjacent to it" -- which
    is what `to=` is for; a bare `c.slide` offers every square in range to the
    decider instead. The captive is usually already there, in which case the
    three squares buy nothing, which is what the printed line amounts to."""
    victim = _restricted_to(c, 1, lambda foe: c.me in c.grabbed_by(on=foe))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    where = _free_square_beside(c, c.me)
    if where is not None:
        c.slide(3, on=victim, to=where)


# ==========================================================================
# m5722
# ==========================================================================


_M5722_STRUCK = "an enemy within 7 squares hits the m5722"


def _m5722_hit_from_range(world: World, me: int, ev: Hit) -> bool:
    return (
        getattr(ev, "target", None) == me
        and ev.attacker != me
        and distance_between(world, me, ev.attacker) <= 7
    )


@power(
    "m5722a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=8, kind=MINION),
)
def m5722a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5722a1",
    level=12,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5722_STRUCK,
    on=Trigger(Hit, when=_m5722_hit_from_range, text=_M5722_STRUCK),
)
def m5722a1(c: Cast) -> None:
    """One of them answers, not all of them.

    "No other copy has used this power during this turn" is counted across
    every copy on the board and `once_per_round` counts on one creature, so
    the guard is the log's. `c.charge_at` is the run and the swing together,
    and the swing is this creature's own melee row rather than a line of this
    one's -- the card prints none.

    The movement provoking nothing is laid first, because by the time the
    charge has resolved the windows are already shut.
    """
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None or _used_this_turn_by_another(c, c.ref):
        return
    c.no_provoke(on=c.me, until=When.EOT)
    c.charge_at(attacker, ref="m5722a0")


# ==========================================================================
# m6128
# ==========================================================================
#
# Eight extra lives, spent one at a time, and two gated bonuses that read how
# many are left. Nothing on the board counts lives, so this row's own tally
# is what the pair of them share.


_M6128_LIVES: dict[int, int] = {}
_M6128_START = 8
_M6128_FELLED = "the m6128 drops to 0 hit points while an extra life remains"


def _m6128_lives(c: Cast) -> int:
    return _M6128_LIVES.setdefault(c.me, _M6128_START)


@power(
    "m6128a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6128a0(c: Cast) -> None:
    """The tally, and the two bonuses that read it.

    Two gates rather than one that returns a number: two bonuses of the same
    kind do not add and the larger wins, so a +2 while five remain and a +4
    while two remain come to +4 at the bottom of the ladder, which is what the
    printed "increases to" means. Written the other way -- a +2 plus a second
    +2 -- it would be +2 forever.

    Neither prints a type word, so both are untyped, and the defence half is
    four modifiers because one written once would be a bonus to nothing.

    `c.revives_unless` implements nothing; it records the fact so the policy
    stops writing the creature off at 0 hit points. m6128a4 is what actually
    stands it up.
    """
    me = c.me
    _M6128_LIVES[me] = _M6128_START
    c.revives_unless(on=me)

    def down_to(left: int) -> Any:
        return lambda ctx: _M6128_LIVES.get(me, _M6128_START) <= left

    for cap, amount in ((5, 2), (2, 4)):
        c.bonus("attack", amount, on=me, until=When.ENCOUNTER, when=down_to(cap))
        c.bonus("damage", amount, on=me, until=When.ENCOUNTER, when=down_to(cap))
        for defended in EVERY_DEFENCE:
            c.bonus(defended, amount, on=me, until=When.ENCOUNTER, when=down_to(cap))


@power(
    "m6128a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m6128a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6128a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m6128a2(c: Cast) -> None:
    """A shift its whole speed with one swing somewhere in it.

    The swing is this creature's own melee row, used rather than copied so its
    numbers stay in one header -- which is also why this row declares neither
    an attack nor damage. The step is taken first: "during the movement" is a
    choice the engine has no way to interleave, and arriving before swinging
    is the half of it that matters, because the shift is what brings the
    target into reach.
    """
    victim = c.target
    c.shift(c.speed_of())
    if victim is not None:
        c.use_power("m6128a1", on=victim, spend=False)


@power(
    "m6128a3",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m6128a3(c: Cast) -> None:
    c.teleport(10)


@power(
    "m6128a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.TELEPORTATION],
    trigger=_M6128_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M6128_FELLED),
)
def m6128a4(c: Cast) -> None:
    """It spends a life and gets up somewhere else, unseen.

    A creature at 0 hit points is dying rather than dead and keeps its slot,
    so a single point is all it takes -- and the row refuses itself when no
    life is left, which is the printed Trigger and not a guard invented for
    it. `FREE` rather than `ActionType.NONE`: the dispatcher makes the
    exception that lets a creature answer its own `Dropped`, and a trait would
    fire at the top of the fight.

    "Until she attacks" is the other half of the invisibility's duration, so
    the hold is ended from a watch on the next attack it declares rather than
    left to the clock alone.
    """
    me = c.me
    if _m6128_lives(c) <= 0:
        return
    _M6128_LIVES[me] = _m6128_lives(c) - 1
    c.heal(1, on=me)
    c.teleport(10)
    unseen = c.invisible(on=me, until=When.EONT)
    if unseen is None:
        return

    def seen(ev: Any) -> None:
        if getattr(ev, "attacker", None) == me:
            c.world.effects.end(unseen, "it attacked")

    c.watch(AttackDeclared, seen, until=When.EONT, on=me, label=f"{c.ref} unseen")
