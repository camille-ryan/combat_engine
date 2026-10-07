"""Monster abilities, level 13: the stat-block entries of the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=18)` and `Damage("2d6", 9)` -- and the engine takes the level back out
of the attack and rescales the damage.

The conventions of `lurkers.py` beside this file are kept and its helpers are
imported rather than copied: a row filed under an action heading that is
plainly a trait is declared `ActionType.NONE`, a stat block printing no range
at all means melee 1, and a printed "Range 6/12" is a normal range and a long
one with only the normal one in `Range`.

Eight things this file had to settle.

**"Attacking from invisibility" can be asked on the `Hit` after all.** The
file beside this one says it cannot, and the code disagrees:
`resolve.attack` clears `Relation.HIDDEN_FROM` for whoever swung *after* the
`for` loop that emits `Hit`/`Miss`, so the hiding is still standing through
the whole of that announcement and through every listener in its AFTER
window. What #390 is actually about is the other direction -- a row that
*re-hides* on a `Miss` is wiped by that clear a moment later. So m1077a2 and
m2515a3 read the state at the `Hit`, and m2304a5 does its work in
`AttackDeclared`'s AFTER window, which is the first moment after the clear.

**A printed secondary attack has its bonus trimmed by hand.** A second
attack line against a different defence cannot live in the header, so
m1077a1's +10 goes through `scaling.trim` the way every printed secondary
below level 12 has, and the chain of failed saves is `Effect.escalate`
ending the hold before it lays the next -- never a rewrite of
`eff.conditions`, which `Effects.apply` reads once and never looks at again.

**An aura whose radius changes is one zone, not three.** m6651's aura is
made once at aura 1 and `Zone.aura` is the radius `Zones.refresh` recomputes
from, so "the aura expands by 2 squares" and "reverts to aura 1" are
assignments to that field followed by a refresh. The concealment it carries
is a gated `c.conceal` reading the live radius, so it widens with it.

**"Any creature that enters the aura or starts its turn there" is
`c.burns`, except when the printed line narrows who.** m4484a0 exempts one
creature type and m6161a0 only bites at the start of a turn, so both are
written out by hand with a once-per-round guard; neither is a case `c.burns`
can take.

**The grab shapes here are three different clocks.** m5998a1's lasts until
the victim escapes, m6183a2's is sustained and pays out when it is, and
m2104a1's ends if the holder attacks. Each is hung on the `Effect` that
`c.grab` hands back rather than on a duration, because none of the three is
a duration. The escape DCs are the one thing missing and `c.grab(dc=)` is
the symbol fifty-eight rows already carry for it.

**"Reduced to 0 hit points by its own trait"** is `Dropped` with `source`
equal to the creature itself, which is what m2104a3's self-damage sets. A
gate on `actor` alone would have fired the burst on any killing blow.

**m2515a1's card prints no defence at all** -- "+16 vs ;" is the whole of
the attack line -- and the row is that attack, so there is no half to play.
`etl.monster.attack_defence()` is the symbol twenty-eight rows carry.

**Two stat blocks print the same pair of polymorph forms**, m6183a4 and
m6184a2, so the pair is one helper. The still form is sayable outright; the
ooze form is three clauses about squeezing and the engine holds the
condition without holding any of its costs.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers_sa import _shoved_by_hand
from combat_engine.content.monsters.level_07.controllers import _vanish
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_11.lurkers import (
    EVERY_DEFENCE,
    _breathe_again,
    _extra_against_the_unready,
    _frightful,
)
from combat_engine.content.monsters.level_12.brutes import _in_reach
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
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
    MeleeOrRanged,
    Miss,
    Ranged,
    Relation,
    Summon,
    Target,
    UpTo,
    Usage,
    When,
    Window,
    power,
)
from combat_engine.engine.components import Initiative, Movement, Powers
from combat_engine.engine.events import (
    AdjacencyGained,
    AdjacencyLost,
    Bloodied,
    DamageApplied,
    Dropped,
    EffectExpired,
    MoveEnd,
    PowerUsed,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.grid import Square, spread
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    adjacent,
    alive,
    enemies,
    has_combat_advantage,
    hidden_from,
    squares,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    by_me,
    by_melee,
    by_ranged,
)
from combat_engine.engine.zones import Zone

#: The two damage types m6651a6 answers.
_SPARKS = (DamageType.LIGHTNING, DamageType.THUNDER)

#: The conditions a printed "any dazing, dominating, or stunning effect"
#: names. Written out because each is a separate hold on the creature.
_SCRAMBLED = (Condition.DAZED, Condition.DOMINATED, Condition.STUNNED)


# --------------------------------------------------------------------------
# Shapes several of these stat blocks share
# --------------------------------------------------------------------------


def _fades(c: Cast, until: When, *, unseen: bool, concealed: bool) -> None:
    """Half-there until the clock runs out or it swings.

    Three stat blocks print the same sentence with one word different: one
    goes unseen, one merely gains concealment, and both are insubstantial and
    phasing. `c.phasing` is the printed quality here and not a stand-in for
    something narrower -- the card says phasing.

    "Until it attacks" is the attack *roll*, hit or miss, so the watch is on
    `AttackDeclared` in the AFTER window: that is the one place after the
    swing has been resolved and after `resolve.attack` has cleared the
    hiding, so a hold ended there cannot be revived by either.
    """
    me = c.me
    holds = [c.insubstantial(until=until), c.phasing(until=until)]
    if unseen:
        holds.append(c.invisible(until=until))
    if concealed:
        holds.append(c.conceal(on=me, until=until))
    live = [h for h in holds if h is not None]
    if not live:
        return

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker != me:
            return
        for hold in live:
            if not hold.ended:
                c.world.effects.end(hold, "it attacked")

    seen = c.watch(
        AttackDeclared, swung, until=until, window=Window.AFTER, on=me, label=c.ref
    )
    live[0].on_end.append(lambda: c.world.effects.end(seen, "the form is over"))


def _extra_against_the_startled(c: Cast, amount: str | int) -> None:
    """"Deals extra damage against surprised foes."

    `Condition.SURPRISED` is a condition the board can hold, so this is the
    ordinary `Hit` rider -- unlike combat advantage, being surprised is not
    spent by being read, so it is asked of the victim rather than of the
    event.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not c.is_(Condition.SURPRISED, on=ev.target):
            return
        if isinstance(amount, str):
            c.damage(amount, on=ev.target, detail=ref)
        else:
            c.flat(amount, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


def _ring_bites(c: Cast, radius: int, fn: Any, *, on_entry: bool) -> int:
    """An aura that hurts, once per turn, with a printed narrowing.

    `c.burns` is the packaged form and neither caller here fits it: m4484a0
    exempts a creature type and m6161a0 bites only at the start of a turn,
    where `c.burns` always bites on entry as well. The guard is a round per
    victim, which is what "only once per turn" means on a creature that may
    leave and come back.
    """
    me, label = c.me, c.ref
    ring = c.aura(radius, label=label, until=When.ENCOUNTER)
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if who == me or struck.get(who) == c.world.round:
            return
        if not alive(c.world, who) or not c.in_my_aura(who, label=label):
            return
        struck[who] = c.world.round
        fn(who)

    def started(ev: TurnStart) -> None:
        if not ev.ghost:
            bite(ev.actor)

    c.watch(TurnStart, started, until=When.ENCOUNTER, on=me, label=f"{label} ring")
    if on_entry:

        def entered(ev: ZoneEntered) -> None:
            if ev.zone == ring:
                bite(ev.actor)

        c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{label} edge")
    return ring


def _free_squares_beside(c: Cast, who: int, *, within: int, of: int) -> list[Square]:
    """The empty squares next to one creature and close enough to another.

    Two rows print a destination rather than a distance -- "to another square
    adjacent to that enemy", "to a square adjacent to itself" -- and
    `c.slide(to=)` and `c.shift(to=)` both take one, so the candidates are
    worked out here rather than left to the decider, which would offer every
    square in range.
    """
    grid = c.world.grid
    theirs = squares(c.world, who)
    mine = squares(c.world, of)
    ring = spread(theirs, 1) - theirs
    out = [
        sq
        for sq in sorted(ring)
        if grid.inside(sq)
        and grid.passable(sq)
        and (grid.occupant(sq) is None or sq in mine)
        and min((abs(sq[0] - m[0]) for m in mine), default=0) <= within
        and min((abs(sq[1] - m[1]) for m in mine), default=0) <= within
    ]
    return out


def _burrow_speed(c: Cast) -> int:
    """How fast the caster burrows, which is not its walking speed.

    `c.speed_of` answers the walk, and both of m6111's burrowing rows say
    "up to its burrow speed" -- a four-fold difference on this stat block.
    """
    moves = c.world.get(c.me, Movement)
    if moves is None:
        return c.speed_of()
    return int(moves.modes.get("burrow", 0)) or c.speed_of()


def _two_forms(c: Cast, ooze: str, still: str) -> None:
    """The pair of polymorph forms two of these stat blocks print verbatim.

    One form is about squeezing and the engine holds `Condition.SQUEEZING`
    without holding any of the three costs this form waives, so nothing of it
    can be laid. The other is four clauses and three of them are ordinary.

    "Remains in the chosen form until it uses this power again" is why any
    standing hold of this row's is ended first: a second use must not leave
    the first form's resistance behind.
    """
    me = c.me
    for old in list(c.world.effects.of(me)):
        if old.label == c.ref and not old.ended:
            c.world.effects.end(old, "it took another shape")
    taken = c.choose([ooze, still], f"{c.ref}: which shape")
    shape = c.world.effects.apply(me, me, When.ENCOUNTER, label=c.ref)
    if taken != still:
        return
    for hold in (
        c.resist(15, until=When.ENCOUNTER, on=me),
        c.immobilized(until=When.ENCOUNTER, on=me),
        c.cannot_attack(on=me, until=When.ENCOUNTER),
    ):
        if hold is not None:
            shape.on_end.append(lambda h=hold: c.world.effects.end(h, "it moved again"))


def _thralls(world: Any, me: int) -> list[int]:
    """Whoever is carrying m6162a2's hold right now.

    Read off the live effects rather than off a condition, because the card
    names the *row* -- "dominated or dazed by m6162a2" -- and the two
    conditions it can leave are different ones depending on whether it hit.
    """
    return sorted(
        {
            eff.owner
            for eff in world.effects.live.values()
            if eff.source == me and "m6162a2" in (eff.label or "") and not eff.ended
        }
    )


# --------------------------------------------------------------------------
# Declared trigger predicates
# --------------------------------------------------------------------------


def _bloodied_an_enemy(world: Any, me: int, ev: Any) -> bool:
    """"When its attack bloodied an enemy." `Bloodied` carries the source."""
    return ev.source == me and ev.actor != me and ev.actor in enemies(world, me)


def _felled_by_its_own(world: Any, me: int, ev: Any) -> bool:
    """"When reduced to 0 hit points by m2104a3", which damages it itself.

    `source` is the whole of the narrowing: a gate on `actor` alone would
    fire this burst on any killing blow, which is three quarters of them.
    """
    return ev.actor == me and ev.source == me


def _enemy_stepped_beside(world: Any, me: int, ev: Any) -> bool:
    """An enemy *moved* next to it. `mover` is which of the pair walked."""
    if me not in (ev.actor, ev.other):
        return False
    who = ev.other if ev.actor == me else ev.actor
    return ev.mover == who and who in enemies(world, me)


def _its_rally_lapsed(world: Any, me: int, ev: Any) -> bool:
    """"Trigger: m4484a5 ends." `EffectExpired.what` renders the label."""
    return ev.actor == me and "m4484a5" in ev.what


def _attacked_beside_a_thrall(world: Any, me: int, ev: Any) -> bool:
    """A melee or ranged attack on it while one of its thralls is adjacent."""
    if ev.target != me:
        return False
    if not (by_melee(world, me, ev) or by_ranged(world, me, ev)):
        return False
    return any(adjacent(world, me, who) for who in _thralls(world, me))


def _shocked(world: Any, me: int, ev: Any) -> bool:
    """"When it takes lightning or thunder damage." Either type, either field."""
    if ev.target != me or ev.amount <= 0:
        return False
    return ev.dtype in _SPARKS or any(d in _SPARKS for d in ev.dtypes)


# ==========================================================================
# m1077
# ==========================================================================


@power(
    "m1077a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 4),
)
def m1077a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1077a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.SLEEP],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 6),
    attack_alt=Attack(vs=FORT, printed=10),
)
def m1077a1(c: Cast) -> None:
    """A printed secondary, and two failed saves that each replace the hold.

    The secondary's +10 is trimmed by hand because a second attack line
    against a second defence cannot live in the header beside the first.

    "Immobilized instead of slowed" is not a rewrite of `eff.conditions`:
    `Effects.apply` reads that tuple once, to count the conditions in, so an
    edit afterwards lands nothing and strands the slow. Each step of the
    chain ends the hold it replaces and lays a new one, which also keeps the
    victim to one saving throw against one printed sentence.

    "Poison damage from this attack does not wake a sleeping creature" is
    already true: nothing in the engine wakes an unconscious creature when it
    is damaged, so there is no rule here to switch off.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    bonus = c.world.scaling.trim(10, c.level)
    if not c.attack(bonus, FORT, on=victim, as_="secondary"):
        return

    def sleeps(eff: Any) -> None:
        c.world.effects.end(eff, "the second save failed")
        c.unconscious(until=When.ENCOUNTER, on=eff.owner)

    def stiffens(eff: Any) -> None:
        c.world.effects.end(eff, "the first save failed")
        c.world.effects.apply(
            eff.owner,
            c.me,
            When.SAVE_ENDS,
            label=c.ref,
            conditions=(Condition.IMMOBILIZED,),
            ongoing=(10, DamageType.POISON),
            escalate=sleeps,
        )

    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=(Condition.SLOWED,),
        ongoing=(10, DamageType.POISON),
        escalate=stiffens,
    )


@power(
    "m1077a2",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="it attacks from invisibility and hits",
    on=Trigger(Hit, by_me, "it attacks from invisibility and hits"),
)
def m1077a2(c: Cast) -> None:
    """Asked at the `Hit`, which is still inside the window where it is true.

    `resolve.attack` clears `Relation.HIDDEN_FROM` for the attacker *after*
    the loop that emits `Hit`, so a reaction answering the hit is reading the
    state as it stood when the blow was struck. The file beside this one
    settles the same question in `AttackDeclared` instead, which is also
    correct and is one event earlier than it has to be.
    """
    ev = c.trigger
    if ev is None or not c.is_hidden(from_=ev.target):
        return
    c.teleport(6)


@power(
    "m1077a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m1077a3(c: Cast) -> None:
    """Three qualities at once, held separately because the engine holds them
    separately, and all of them ended by the first attack roll."""
    _fades(c, When.EONT, unseen=True, concealed=False)


@power(
    "m1077a4",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1077a4(c: Cast) -> None:
    """The whole of the printed Effect is another row, so it is used rather
    than copied -- m1077a3 is on the same stat block and needs no lending."""
    c.use_power("m1077a3", on=c.me)


@power(
    "m1077a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1077a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    The sentence names one of the block's two at-will attacks, and the other
    one is the one whose own text prints a secondary attack -- so the rider
    is gated on m1077a0, which is what is left. Gating on neither would pay
    the bonus out twice on a card that prints it once.

    Asked of the victim rather than of the event: being asleep is not spent
    by being read, the way a one-shot grant of combat advantage is.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m1077a0":
            return
        if not (
            c.is_(Condition.UNCONSCIOUS, on=ev.target)
            or c.is_(Condition.HELPLESS, on=ev.target)
        ):
            return
        c.damage("2d6", on=ev.target, detail=ref)
        c.ongoing(10, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


# ==========================================================================
# m1577
# ==========================================================================


@power(
    "m1577a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=18),
    damage=Damage("1d8", 5),
)
def m1577a0(c: Cast) -> None:
    """Only the burn is printed necrotic; the blow itself is untyped."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1577a1",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 7, kind=LIMITED),
)
def m1577a1(c: Cast) -> None:
    """"End automatically when it is no longer adjacent" is not a duration.

    `AdjacencyLost` is the one event that says the pair has come apart, and
    it names the two creatures without saying which moved -- which is right,
    because the card does not care either.

    Four modifiers, because "+2 to all defenses" written once would be a +2
    to nothing. No type word is printed, so they are untyped.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    me = c.me
    held = c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=c.ref, conditions=(Condition.RESTRAINED,)
    )
    braced = [
        c.bonus(defended, 2, on=me, until=When.ENCOUNTER) for defended in EVERY_DEFENCE
    ]

    def apart(ev: AdjacencyLost) -> None:
        if {ev.actor, ev.other} != {me, victim}:
            return
        if held is not None and not held.ended:
            c.world.effects.end(held, "it is no longer adjacent")
        for guard in braced:
            if guard is not None and not guard.ended:
                c.world.effects.end(guard, "it is no longer adjacent")

    c.watch(AdjacencyLost, apart, until=When.ENCOUNTER, on=me, label=f"{c.ref} grip")


@power(
    "m1577a2",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="its attack bloodied an enemy",
    on=Trigger(Bloodied, _bloodied_an_enemy, "its attack bloodied an enemy"),
)
def m1577a2(c: Cast) -> None:
    """`Powers.restore` is what a recharge is, and `Bloodied.source` is what
    tells its own blow from somebody else's."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m1577a1")


# ==========================================================================
# m1942
# ==========================================================================


@power(
    "m1942a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("query.phased_through(world, eid)",),
)
def m1942a0(c: Cast) -> None:
    """Nothing records that a creature has passed *through* anything.

    `movement.phasing` answers whether a creature may, and `Moved` carries
    where it came from and where it went and not what was in between -- so
    the trigger this whole trait hangs on cannot be asked, and there is no
    half of it to play without it.
    """


@power(
    "m1942a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1942a1(c: Cast) -> None:
    """"Takes half damage from any damage source" is insubstantial, which is
    exactly what `c.insubstantial` holds -- a property of the creature rather
    than of the damage, applied to every packet that reaches it."""
    c.insubstantial(until=When.ENCOUNTER, on=c.me)


@power(
    "m1942a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d8", 8, dtype=DamageType.NECROTIC),
)
def m1942a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1942a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("3d8", 8, dtype=DamageType.PSYCHIC),
)
def m1942a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1942a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1942a4(c: Cast) -> None:
    """"Save ends both" is one hold carrying the burn and the condition, so
    the victim gets one saving throw against one printed sentence."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=(Condition.IMMOBILIZED,),
        ongoing=(10, DamageType.NECROTIC),
    )


# ==========================================================================
# m2104
# ==========================================================================


@power(
    "m2104a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d12", 8),
)
def m2104a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2104a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d12", 8),
    dropped=("c.grab(sustain=)",),
)
def m2104a1(c: Cast) -> None:
    """Three clocks on one grab, and only one of them is a duration.

    The burn and the four defence bonuses are hung on the `Effect` `c.grab`
    hands back, so "until it escapes" and "while it has a target grabbed"
    both end exactly when the grab does, however it ended.

    "The grab ends if the m2104 attacks" is watched from *after* this row's
    own attack has resolved, which is why the watch is armed below
    `c.strike` and not above it. The other half of that sentence -- failing
    to sustain the grab -- is the dropped clause: a grab carries no sustain
    cost and nothing asks for one each round.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    me = c.me
    hold = c.grab(on=victim)
    if hold is None:
        return
    burn = c.ongoing(10, on=victim, until=When.ENCOUNTER)
    braced = [
        c.bonus(defended, 4, on=me, until=When.ENCOUNTER) for defended in EVERY_DEFENCE
    ]

    def released() -> None:
        if burn is not None and not burn.ended:
            c.world.effects.end(burn, "the grab is over")
        for guard in braced:
            if guard is not None and not guard.ended:
                c.world.effects.end(guard, "the grab is over")

    hold.on_end.append(released)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == me and not hold.ended:
            c.world.effects.end(hold, "it attacked")

    letting = c.watch(
        AttackDeclared, swung, until=When.ENCOUNTER, on=me, label=f"{c.ref} grip"
    )
    hold.on_end.append(lambda: c.world.effects.end(letting, "nothing held"))


@power(
    "m2104a2",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d12", 6, kind=LIMITED, half_on_miss=True),
    trigger="it is reduced to 0 hit points by m2104a3",
    on=Trigger(Dropped, _felled_by_its_own, "its own trait reduces it to 0"),
)
def m2104a2(c: Cast) -> None:
    """A death throe, and the narrowing is `Dropped.source`.

    The printed trigger is not "when it drops" but "when *its own trait*
    drops it", and m2104a3's self-damage is dealt with the m2104 as the
    source -- so the gate is on `source` and `actor` both. `c.dying` says
    this row is a throe; it does not say what finished it.

    The burst prints no target line, so it is `EACH_OTHER`: a close burst
    never catches the creature using it unless the card says it does, and
    `EACH_CREATURE` would have the m2104 blowing itself up again.
    """
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m2104a3",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m2104a3(c: Cast) -> None:
    """The damage is its own healing surge value, read each time rather than
    once: `c.surge_value` is a quarter of the maximum and that does not move,
    but reading it per tick is what the sentence says.

    Bloodied is re-asked at each tick too -- the printed clause is "while
    bloodied", and a creature can be healed back above the line.
    """
    me = c.me

    def ending(ev: TurnEnd) -> None:
        if ev.ghost or not alive(c.world, me) or not c.bloodied(on=me):
            return
        c.flat(c.surge_value(of=me), on=me)

    c.watch(TurnEnd, ending, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m2104a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2104a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it is how the creature
    starts the fight.

    The readied attack is one shot and is armed as an immediate reaction, the
    action a readied attack costs, on an enemy *arriving* within reach --
    `MoveEnd` rather than `MoveStart`, because the creature has to be in
    reach for the swing to be legal. Spending it gives the hiding away, which
    `resolve.attack` does by itself.

    The Stealth bonus is a real modifier -- `skills.modifier` reads
    `skill:stealth` -- so it is laid rather than marked.
    """
    me = c.me
    c.hide(until=When.ENCOUNTER)
    c.bonus("skill:stealth", 5, on=me, until=When.ENCOUNTER)
    spent = [False]

    def arrived(ev: MoveEnd) -> None:
        if spent[0] or ev.actor == me or ev.actor not in enemies(c.world, me):
            return
        if c.distance(ev.actor) > c.reach("m2104a0"):
            return
        spent[0] = True
        c.basic(on=ev.actor)

    c.arm_trigger(
        MoveEnd,
        arrived,
        cost=ActionType.IMMEDIATE_REACTION,
        until=When.ENCOUNTER,
        on=me,
        label=c.ref,
    )


# ==========================================================================
# m2304
# ==========================================================================


@power(
    "m2304a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d6", 8),
    dropped=("c.reroll_ones()",),
)
def m2304a0(c: Cast) -> None:
    """The blow plays. "Reroll any damage die result of 1" is the dropped
    clause: `c.reroll_damage` rolls the whole expression twice and keeps the
    higher, which is a different and larger thing than replacing the ones."""
    if c.strike():
        c.hit()


@power(
    "m2304a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m2304a1(c: Cast) -> None:
    """Six squares with two swings somewhere inside them.

    "At any point during that movement" is written as a swing, half the
    movement, a swing, and whatever is left over -- which is the only reading
    that lets the second blow land on somebody the first step reached.

    The immunity is laid before each swing and names the creature being
    swung at, because the printed line exempts only "the targets of these
    attacks" and not every enemy it walks past.
    """
    left = 6
    for _ in range(2):
        victim = _in_reach(c, c.reach(), c.ref)
        if victim is None and left:
            left -= c.move(min(3, left))
            victim = _in_reach(c, c.reach(), c.ref)
        if victim is None:
            continue
        c.no_provoke(from_=victim, on=c.me, until=When.EOT)
        c.basic(on=victim)
    if left:
        c.move(left)


@power(
    "m2304a2",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    requires_text="requires combat advantage",
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m2304a2(c: Cast) -> None:
    """The Requirement is about the target, so it is a redirection and not a
    gate: `Target` filters on side and count and not on what the attacker has
    over a creature, so the chooser can hand this row somebody it may not
    swing at while a creature next to it qualifies. Throwing the row away
    there is the mistake; aiming it at the one that qualifies is not.
    """
    victim = _restricted_to(c, 1, lambda w: has_combat_advantage(c.world, c.me, w))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.heal(25, on=c.me)


@power(
    "m2304a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m2304a3(c: Cast) -> None:
    """Concealment rather than invisibility, which is the one word this card
    differs from m1077a3 by -- and `c.conceal` is the narrower hold, worth -2
    to attacks against it instead of hiding it outright."""
    _fades(c, When.EONT, unseen=False, concealed=True)


@power(
    "m2304a4",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2304a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. The printed line names
    no range kind, so every attack carries it, and the advantage is read off
    the `Hit` -- a one-shot grant is already spent by the time a second
    asking could be made."""
    _extra_against_the_unready(c, "3d6")


@power(
    "m2304a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2304a5(c: Cast) -> None:
    """Re-hiding has to happen after the clear, which is one event later than
    it looks.

    `resolve.attack` ends with `clear_source(HIDDEN_FROM, attacker)`, and
    that line sits *below* the loop that emits `Hit` and `Miss` -- so a row
    that hides again from a `Miss` watch is wiped a moment later and reads as
    a rule that never applies (#390). `AttackDeclared`'s AFTER window runs
    after the whole of that callback, so it is the first moment the hiding
    can be put back.

    Who it was hidden from is therefore taken in the BEFORE window, when the
    answer is still the one the card means, and the outcome is remembered
    from the announcement in between.
    """
    me = c.me
    was: list[int] = []
    missed = [False]

    def before(ev: AttackDeclared) -> None:
        if ev.attacker != me:
            return
        was[:] = [w for w in hidden_from(c.world, me)]
        missed[0] = False

    def landed(ev: Hit) -> None:
        if ev.attacker == me:
            missed[0] = False

    def failed(ev: Miss) -> None:
        if ev.attacker == me:
            missed[0] = True

    def after(ev: AttackDeclared) -> None:
        if ev.attacker != me or not missed[0]:
            return
        for watcher in was:
            if alive(c.world, watcher):
                c.hide(from_=watcher, until=When.ENCOUNTER)

    c.watch(
        AttackDeclared, before, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} sighting",
    )
    c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=f"{c.ref} hit")
    c.watch(Miss, failed, until=When.ENCOUNTER, on=me, label=f"{c.ref} miss")
    c.watch(
        AttackDeclared, after, until=When.ENCOUNTER, window=Window.AFTER, on=me,
        label=c.ref,
    )


# ==========================================================================
# m2515
# ==========================================================================


@power(
    "m2515a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC),
)
def m2515a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2515a1",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    requires_text="requires combat advantage",
    todo=("etl.monster.attack_defence()",),
)
def m2515a1(c: Cast) -> None:
    """The card prints "+16 vs ;" and no defence at all, and the row is that
    attack -- so there is nothing left to play and nothing to guess. A lost
    defence is named, not invented: m1135a1 settled that and twenty-eight
    rows carry the same symbol.
    """


@power(
    "m2515a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("c.zone(exempt=)", "c.light()"),
)
def m2515a2(c: Cast) -> None:
    """The blast, and a patch of dark that bites at the start of a turn.

    Not `c.burns`: that bites on entering the zone as well, and this card
    only charges for starting a turn there. The damage is rolled per tick
    rather than once when the zone is laid, which is what a dice expression
    in a zone means.

    Two clauses are dropped. The zone blocks sight for everybody, where the
    card exempts whatever can see in darkness -- `c.zone(exempt=)` is the
    symbol twelve rows carry for that. And "cannot be illuminated" has
    nothing to refuse, because light is not a thing the board holds.
    """
    if c.strike():
        c.hit()
    if not c.first:
        return
    me = c.me
    dark = c.zone(c.area(), label=c.ref, until=When.EONT, blocks_sight=True)

    def started(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(dark):
            c.flat(c.roll("1d6") + 6, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnStart, started, until=When.EONT, on=me, label=f"{c.ref} dark")
    _recharge_on(c, Bloodied, lambda ev: getattr(ev, "actor", -1) == me)


@power(
    "m2515a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.no_surges()",),
)
def m2515a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait, and the whole of it is
    the one clause the engine cannot say.

    "Cannot spend healing surges" has no verb: `c.no_healing` stops healing
    outright, which is wider than the card prints. Nothing else is in the
    sentence, so this is `todo=` -- an empty body offered in play would
    report working.
    """


# ==========================================================================
# m2647
# ==========================================================================

#: The tag m2647a3 leaves on an enemy, so m2647a2 can read which marks came
#: from that row rather than from any other mark on the board.
_M2647_MARK = "m2647a3 mark"


def _marked_by_its_ally(world: Any, me: int, ev: Any) -> bool:
    """An ally swinging at an enemy m2647a3 had that ally mark.

    The tag names the row, which is the whole of the printed narrowing:
    "marked because of m2647a3" is not the same question as "marked".
    """
    if ev.attacker == me:
        return False
    if team(world, ev.attacker) is not team(world, me):
        return False
    return any(
        eff.owner == ev.target and eff.source == me and eff.label == _M2647_MARK
        for eff in world.effects.live.values()
        if not eff.ended
    )


@power(
    "m2647a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m2647a0(c: Cast) -> None:
    """"Crit 18 + 2d6" is two statements: 18 is the maximum of the printed
    line, which `c.damage` already rolls on a critical, and the 2d6 beside it
    is extra. It is added with `c.flat(c.roll(...))` because a rolled die
    inside the crit branch would come out maximum too."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("2d6"))


@power(
    "m2647a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m2647a1(c: Cast) -> None:
    """"Ranged 6/12" is a normal range and a long one, and `Range` holds the
    normal one -- the long-range penalty is the engine's business."""
    if c.strike():
        c.hit()


@power(
    "m2647a2",
    level=13,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=MeleeOrRanged(1, 6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("4d6", 6),
    trigger="an ally attacks an enemy that ally marked because of m2647a3",
    on=Trigger(
        AttackDeclared,
        _marked_by_its_ally,
        "an ally attacks an enemy it marked because of m2647a3",
        window=Window.AFTER,
    ),
)
def m2647a2(c: Cast) -> None:
    """Two weapons, one row, and which one swings is the distance.

    The card prints a damage line and no attack line of its own, because it
    says the m2647 *makes* one of the two attacks the block prints -- and
    both of those are +18 vs AC, which is what the header declares.

    The printed Requirement names the two weapons, and a monster is always
    holding its own: the attacks it is required to be able to make are rows
    on this same stat block, so the Requirement cannot be false in a fight
    and there is nothing to gate.

    "Crit 30 + 2d6" with the melee weapon is the maximum of 4d6 + 6 plus an
    extra roll, exactly as m2647a0 reads, and it is printed for that branch
    alone.
    """
    ev = c.trigger
    victim = getattr(ev, "target", None) if ev is not None else None
    if victim is None or not alive(c.world, victim):
        return
    near = c.adjacent(victim)
    if c.strike(on=victim):
        c.hit(on=victim)
        if c.crit and near:
            c.flat(c.roll("2d6"), on=victim)


@power(
    "m2647a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=NO_TARGET,
    requires_text="requires an ally in the area",
)
def m2647a3(c: Cast) -> None:
    """One ally per enemy, each ally used once, and the mark belongs to the
    ally rather than to the m2647 -- `c.mark(by=)` is what says so.

    A tag goes on beside each mark because m2647a2's trigger is narrower than
    "marked": it is marked *by this row*, and a defender's own mark on the
    same creature must not set it off.

    The defence bonus reads the live set inside the gate rather than a
    snapshot: the pairing is redone every time this row is used and the
    bonus has to follow it.
    """
    me = c.me
    inside = c.area()
    allies = [a for a in c.in_squares(inside, side="team") if a != me]
    foes = [f for f in c.in_squares(inside, side="enemy") if alive(c.world, f)]
    if not allies or not foes:
        return
    marked: set[int] = set()
    for foe in sorted(foes):
        if not allies:
            break
        helper = c.choose(sorted(allies), f"{c.ref}: who marks {foe}")
        if helper is None:
            break
        allies.remove(helper)
        c.mark(on=foe, by=helper, until=When.EONT)
        c.effect(_M2647_MARK, on=foe, until=When.EONT)
        marked.add(foe)
    if not marked:
        return
    for defended in EVERY_DEFENCE:
        c.bonus(
            defended,
            2,
            on=me,
            until=When.EONT,
            when=lambda ctx: ctx.get("attacker") in marked,
        )


# ==========================================================================
# m3222
# ==========================================================================


@power(
    "m3222a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m3222a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3222a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7),
)
def m3222a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3222a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m3222a2(c: Cast) -> None:
    """The Perception penalty is a real modifier, not a narrative one:
    `skills.modifier` reads `skill:perception`, and `c.passive` is what a row
    going unseen has to beat -- so -5 there costs the victim something in a
    fight and is laid rather than marked.

    The Effect half runs whether the blast hit or not, and it hides the
    m3222 from that one creature rather than from the board, which is what
    `c.invisible(to=)` holds.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        c.penalty("skill:perception", 5, until=When.EONT, on=victim)
    c.invisible(to=victim, on=c.me, until=When.EONT)


@power(
    "m3222a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m3222a3(c: Cast) -> None:
    """A step in, a swing, a step out. The swing is "a basic melee or basic
    ranged attack", so which one is the branch `c.basic(ranged=)` picks, and
    the choice is the m3222's."""
    c.shift(2)
    far = c.choose([False, True], f"{c.ref}: swing at range")
    c.basic(ranged=bool(far))
    c.shift(2)


@power(
    "m3222a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m3222a4(c: Cast) -> None:
    """Looking like somebody else is the whole printed Effect. Nothing in a
    fight reads what a creature looks like -- there is no disguise check on a
    board -- so this is deliberately inert rather than unwritten."""


@power(
    "m3222a5",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.stealth_speed()",),
)
def m3222a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait, and all of it waits on
    one absence.

    The card waives a penalty and softens another, and the engine holds
    neither: `skills.modifier` knows nothing about how fast the creature was
    moving when it rolled. There is nothing here to cancel, so there is no
    half of this to play.
    """


@power(
    "m3222a6",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3222a6(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Not `_extra_against_the_unready`, which pays damage and nothing else:
    this card hangs a condition on the same sentence, so the rider is
    written out. The advantage is read off the `Hit` for the same reason that
    helper does -- asking the board again answers no on exactly the attacks
    the rider exists for.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not c.had_advantage(ev):
            return
        c.damage("2d8", on=ev.target, detail=ref)
        c.slowed(until=When.EONT, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


# ==========================================================================
# m4157
# ==========================================================================


@power(
    "m4157a0",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d12", 7),
)
def m4157a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4157a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 7),
)
def m4157a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4157a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m4157a2(c: Cast) -> None:
    """Three swings: the pair and the single one.

    The card names two of one attack and one of another, and the block
    prints exactly two at-will melee lines -- so the single one is the
    heavier die, m4157a0, and m4157a1 is the pair. m4157a3 names the single
    attack too, which is the other half of the same reading.

    Each use picks its own target, which is what a row printing no target of
    its own leaves open.
    """
    for ref in ("m4157a1", "m4157a1", "m4157a0"):
        victim = _in_reach(c, c.reach(ref), c.ref)
        if victim is None:
            return
        c.use_power(ref, on=victim, spend=False)


@power(
    "m4157a3",
    level=13,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    trigger="an enemy moves adjacent to it",
    on=Trigger(
        AdjacencyGained, _enemy_stepped_beside, "an enemy moves adjacent to it"
    ),
)
def m4157a3(c: Cast) -> None:
    """`AdjacencyGained` is the printed sentence, and `MoveEnd` is not.

    "An enemy moves adjacent" is about a pair of creatures becoming
    neighbours, which is the one thing that event says; `mover` is what tells
    the enemy walking in from the m4157 walking over. `MoveStart` would
    resolve before the step and `MoveEnd` would have to measure the distance
    again.
    """
    ev = c.trigger
    foe = None
    if ev is not None:
        foe = ev.other if ev.actor == c.me else ev.actor
    if foe is None or not alive(c.world, foe):
        return
    c.use_power("m4157a0", on=foe, spend=False)
    if c.landed:
        c.grants_advantage(until=When.SAVE_ENDS, on=foe)


@power(
    "m4157a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 4, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m4157a4(c: Cast) -> None:
    """"Save ends both" over a burn and a blindness of one creature.

    "Treats the m4157 as invisible" is `Relation.HIDDEN_FROM` pointed one
    way, and it has to ride on the same hold as the burn or the victim gets
    two saving throws against one printed sentence -- which is why the
    relation is handed to `Effects.apply` rather than laid with
    `c.invisible`.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        ongoing=(5, DamageType.POISON),
        relations=[(Relation.HIDDEN_FROM, c.me, victim)],
    )


@power(
    "m4157a5",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4157a5(c: Cast) -> None:
    """`Powers.restore` is what a recharge is, and the use follows it in the
    same breath -- the card prints both halves of one sentence."""
    _breathe_again(c, "m4157a4")


@power(
    "m4157a6",
    level=13,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=16),
)
def m4157a6(c: Cast) -> None:
    """No damage line at all, so no `c.hit`: the stun is the whole of the hit.

    The Aftereffect begins when the stun ends, however it ended, and the end
    of an effect is the only moment that can be seen -- which is the shape
    the level 11 helper settled on and this card prints unchanged.
    """
    _frightful(c)


@power(
    "m4157a7",
    level=13,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.lose_mode()",),
)
def m4157a7(c: Cast) -> None:
    """A form with five clauses, a way out, and a payout for taking it.

    `until=When.SUSTAIN` with `sustain=MINOR` is the printed clock, and the
    way out is `revert=FREE` -- "can return to its normal form as a free
    action on its turn" is what `Effect.drop_cost` holds. The creatures
    granting combat advantage are the payout for *returning*, so they hang on
    the form's end rather than on anything the body does now.

    Squeezing through a Tiny aperture needs nothing: the narrowest gap the
    grid has is one square, which this creature already fits.

    "Can't fly" is the dropped clause. Nothing takes a movement mode away --
    `c.mode` only grants them -- so the flight stays.
    """
    me = c.me
    c.shift(4)
    shape = c.form(
        modes={"climb": 6},
        until=When.SUSTAIN,
        revert=ActionType.FREE,
        label=c.ref,
    )
    for hold in (
        c.cannot_attack(on=me, until=When.SUSTAIN),
        c.ignores_difficult(on=me, until=When.SUSTAIN),
        c.no_provoke(on=me, until=When.SUSTAIN),
    ):
        if hold is not None:
            shape.on_end.append(lambda h=hold: c.world.effects.end(h, "it is itself again"))

    def returned() -> None:
        for who in sorted(c.within(2, of=me, side="any")):
            if who != me and alive(c.world, who):
                c.grants_advantage(until=When.EONT, on=who)

    shape.on_end.append(returned)


@power(
    "m4157a8",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m4157a8(c: Cast) -> None:
    """Appearing as somebody else, and nothing a fight reads. The cross
    reference in the printed text points at this same row, which is the
    compendium quoting its own heading."""


@power(
    "m4157a9",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4157a9(c: Cast) -> None:
    """Filed as a standard action and plainly a trait, and the printed line
    names no range kind, so every attack carries it."""
    _extra_against_the_unready(c, "2d6")


# ==========================================================================
# m4484
# ==========================================================================


@power(
    "m4484a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m4484a0(c: Cast) -> None:
    """An aura that charges everything but its own kind.

    `c.burns` is the packaged version of "enters or starts its turn there,
    once per turn" and cannot be used, because the printed line exempts a
    creature type and `c.burns` takes no filter. The exemption is read off
    `c.kinds_of` at the moment of the bite rather than when the aura is made:
    nothing stops a creature gaining or losing a type word mid-fight, and the
    aura outlives the turn it was laid on.
    """
    _ring_bites(
        c,
        2,
        lambda who: (
            None
            if "aquatic" in c.kinds_of(who)
            else c.flat(10, dtype=DamageType.PSYCHIC, on=who)
        ),
        on_entry=True,
    )


@power(
    "m4484a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4484a1(c: Cast) -> None:
    """Breathing underwater is already true of the engine: nothing drowns, so
    there is no rule for this half of the sentence to switch off.

    The bonus is doubly gated -- the fight has to be in water and the victim
    has to be the wrong sort of creature -- and both halves are asked inside
    the gate, where they are re-read per swing. No type word is printed, so
    it is untyped.
    """
    c.bonus(
        "attack",
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.terrain("aquatic")
        and "aquatic" not in c.kinds_of(ctx.get("target", -1)),
    )


@power(
    "m4484a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 9),
)
def m4484a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4484a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="one blinded creature",
        conditions=frozenset({Condition.BLINDED}),
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 13),
)
def m4484a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4484a4",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="it must be adjacent to an enemy",
)
def m4484a4(c: Cast) -> None:
    """"To another square adjacent to that enemy" is a destination, not a
    distance, so the squares are worked out and one is handed to `c.shift`
    outright -- left to itself the decider would offer every square within
    three and step out of reach.

    The Requirement is asked in the body rather than declared: adjacency
    changes between rounds, and a `requires=` on a row that can become legal
    later is the wrong clock for it.
    """
    beside = sorted(f for f in c.enemies() if c.adjacent(f))
    if not beside:
        return
    foe = c.choose(beside, f"{c.ref}: which enemy it circles")
    if foe is None:
        return
    room = [
        sq
        for sq in _free_squares_beside(c, foe, within=3, of=c.me)
        if sq not in squares(c.world, c.me)
    ]
    if not room:
        return
    dest = c.world.decide(c.me, "shift", room, f"{c.ref}: where it ends up")
    c.shift(3, to=dest)


@power(
    "m4484a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ALLY,
)
def m4484a5(c: Cast) -> None:
    """Two printed bonuses with the type word in front of each, so both are
    power bonuses, and the m4484's own four are laid once rather than once
    per ally.

    A hold labelled with this row's ref goes up beside them, because
    m4484a6's printed trigger is "m4484a5 ends" and `EffectExpired` renders
    the label -- a bonus's own effect would do, but only while somebody is in
    the burst to carry one.
    """
    c.bonus(FORT, 2, kind="power", until=When.EONT)
    c.bonus(WILL, 2, kind="power", until=When.EONT)
    if not c.first:
        return
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, kind="power", on=c.me, until=When.EONT)
    c.effect(c.ref, on=c.me, until=When.EONT)


@power(
    "m4484a6",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=16),
    trigger="m4484a5 ends",
    on=Trigger(EffectExpired, _its_rally_lapsed, "m4484a5 ends"),
)
def m4484a6(c: Cast) -> None:
    """No Action with a printed Trigger, which `WINDOW_OF` files after the
    event. No damage line at all, so no `c.hit`: the blindness is the hit."""
    if c.strike():
        c.blinded(until=When.SAVE_ENDS)


# ==========================================================================
# m5715
# ==========================================================================


@power(
    "m5715a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
    todo=("World.sunlight",),
)
def m5715a0(c: Cast) -> None:
    """"In direct sunlight" is the whole of the trigger and the board holds
    no light at all, so there is nothing to ask and no half to play. The
    symbol is the one m5303a1 already carries for the same absence."""


@power(
    "m5715a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 7),
)
def m5715a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5715a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m5715a2(c: Cast) -> None:
    """Not `_fades`: this form runs on a clock and does *not* end when the
    creature attacks, because while it holds the creature cannot attack at
    all. Four holds on one duration, all of them the printed sentence."""
    me = c.me
    c.insubstantial(until=When.SONT, on=me)
    c.phasing(until=When.SONT, on=me)
    c.cannot_attack(on=me, until=When.SONT)
    c.no_provoke(on=me, until=When.SONT)


@power(
    "m5715a3",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=18),
    damage=Damage("5d8", 10, kind=LIMITED, half_on_miss=True),
)
def m5715a3(c: Cast) -> None:
    """"At the end of the target's next turn, if it is still grabbed" is a
    question asked once, later -- so the watch is `once=True` on that
    creature's turn ending and re-asks the grab rather than assuming it.

    `Powers.restore` on the printed recharge line, which names another row on
    the same block. The escape DC is the dropped clause: `c.grab` takes no
    number and the engine rolls the ordinary escape.
    """
    me = c.me
    _recharge_on(
        c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m5715a2"
    )
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()
    if c.grab(on=victim, dc=20) is None:
        return

    def still_held(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        if me in c.grabbed_by(on=victim):
            c.weakened(until=When.SAVE_ENDS, on=victim)

    c.watch(
        TurnEnd, still_held, until=When.ENCOUNTER, on=me, once=True,
        label=f"{c.ref} grip",
    )


@power(
    "m5715a4",
    level=13,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION, Keyword.TELEPORTATION],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m5715a4(c: Cast) -> None:
    """Four bodies on the board, and a swap that costs five.

    `c.summon_inline` is what puts a creature the power itself defines on the
    board: the card prints its hit points and says its defences are the
    m5715's, which is `Summon(hp=1)` with no offset. They take no turn, which
    is right -- the printed line gives them nothing to do.

    The swap is an immediate interrupt by the card and is written as a watch
    in the BEFORE window of `Hit`, where the two creatures can still change
    places before the blow is counted. "A duplicate it can see" is asked of
    each candidate rather than assumed.
    """
    me = c.me
    grid = c.world.grid
    room = [
        sq
        for sq in sorted(c.area())
        if grid.inside(sq) and grid.passable(sq) and grid.occupant(sq) is None
    ]
    doubles: set[int] = set()
    for sq in room[:4]:
        made = c.summon_inline(Summon(hp=1, speed=0, label=c.ref), at=sq)
        if made:
            doubles.add(made)
    if not doubles:
        return

    def struck(ev: Hit) -> None:
        if ev.target != me or not doubles:
            return
        if not (by_melee(c.world, me, ev) or by_ranged(c.world, me, ev)):
            return
        seen = sorted(d for d in doubles if alive(c.world, d) and c.can_see(d))
        if seen:
            c.swap(seen[0], who=me)

    def shattered(ev: Dropped) -> None:
        if ev.actor in doubles:
            doubles.discard(ev.actor)
            c.flat(5, on=me)

    c.watch(
        Hit, struck, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} swap",
    )
    c.watch(Dropped, shattered, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m5998
# ==========================================================================


@power(
    "m5998a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5998a0(c: Cast) -> None:
    """Three clauses, and the third is already true of the grid.

    Sharing its square lives on the creature being entered rather than on the
    mover. The shove immunity is gated: `c.immovable` would refuse a push
    from anywhere and the printed line refuses only melee and ranged attacks,
    so it is a shortening large enough to swallow any of them with the reach
    read off the row that shoved. Squeezing through the narrowest opening
    needs nothing -- the smallest gap the grid has is one square.
    """
    c.shares_space(difficult=True)
    c.resist_forced(99, when=_shoved_by_hand)


@power(
    "m5998a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
)
def m5998a1(c: Cast) -> None:
    """The hit line prints no damage, so there is no `c.hit` here at all --
    the grab is the hit and the two numbers beside it are the burn while it
    lasts and the parting blow when it ends.

    Both hang on the `Effect` `c.grab` hands back, because "until the grab
    ends" is not a duration the engine has. The escape DC is the one clause
    `c.grab` cannot carry.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    hold = c.grab(on=victim, dc=20)
    if hold is None:
        return
    burn = c.ongoing(10, on=victim, until=When.ENCOUNTER)

    def let_go() -> None:
        if burn is not None and not burn.ended:
            c.world.effects.end(burn, "the grab is over")
        if alive(c.world, victim):
            c.flat(10, on=victim)

    hold.on_end.append(let_go)


@power(
    "m5998a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=Target(
        "enemy", 1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    keywords=[Keyword.DISEASE, Keyword.POISON, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d4", 8, half_on_miss=True),
    dropped=("c.contract(ref)",),
)
def m5998a2(c: Cast) -> None:
    """Two packets, because the card prints two: an untyped blow in the
    header and a second one that is poison *and* psychic at once, which is
    what `dtypes` is for.

    The disease at the end of the encounter is the dropped clause -- nothing
    contracts one, and forty-five rows wait on the same verb.
    """
    both_types = (DamageType.POISON, DamageType.PSYCHIC)
    if c.strike():
        c.hit()
        c.damage("4d10", dtypes=both_types)
    else:
        c.hit(half=True)
        c.half_damage("4d10", dtypes=both_types)


@power(
    "m5998a3",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5998a3(c: Cast) -> None:
    """A jump is ground crossed rather than walked over, which is why it is
    `c.jump` and not `c.move`. Who it landed on top of is asked after the
    jump and of the square it is actually in -- the swarm shares space, so
    that is a set rather than one creature."""
    me = c.me
    c.jump(2)
    for who in c.in_squares(squares(c.world, me), side="any"):
        if who != me and alive(c.world, who):
            c.grants_advantage(until=When.EOT, on=who)


# ==========================================================================
# m6111
# ==========================================================================


@power(
    "m6111a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6111a0(c: Cast) -> None:
    """The printed line names no range kind, so every attack carries it."""
    _extra_against_the_unready(c, "4d10")


@power(
    "m6111a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6111a1(c: Cast) -> None:
    """The printed clause excludes itself from a fight: "while not engaged in
    combat" is the Requirement, so there is no moment on a board where this
    applies. Deliberately inert rather than unwritten -- `c.hide` exists and
    this sentence is not asking for it."""


@power(
    "m6111a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d10", 5),
)
def m6111a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6111a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
)
def m6111a3(c: Cast) -> None:
    """No damage line, so no `c.hit`: the pull is the whole of the hit, and
    how far is the victim's own speed rather than a printed number."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.pull(max(1, c.speed_of(victim)), on=victim)
    c.grants_advantage(until=When.EONT, on=victim)


@power(
    "m6111a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("4d10", 8, kind=LIMITED, half_on_miss=True),
    requires_text="it must be burrowing",
)
def m6111a4(c: Cast) -> None:
    """The move and the burst it arrives with.

    Every square the board has is aboveground -- `Grid.elevation` records a
    floor and nothing records being inside the ground -- so "burrows to a
    square aboveground" is a burrow move and the attack is where it stops.

    The Requirement is printed and not declared: `requires=` is read when the
    row is offered, and a creature cannot be mid-burrow then, so gating on it
    would refuse the row every time. What the row *does* is burrow, which is
    the sentence read the other way round.
    """
    if c.first:
        _recharge_on(
            c, PowerUsed, lambda ev: ev.actor == c.me and ev.power == "m6111a5"
        )
        c.no_provoke(on=c.me, until=When.EOT)
        c.move(_burrow_speed(c), at="burrow")
    if c.strike():
        c.hit()
        c.push(4)
    else:
        c.hit(half=True)
        c.push(2)


@power(
    "m6111a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6111a5(c: Cast) -> None:
    """"Ends its turn completely submerged" is read as still burrowing when
    the turn ends: `c.moving_as` is held past the end of the move, which is
    exactly the distinction -- a creature that burrowed and came up on foot
    is not moving as a burrower any more.
    """
    me = c.me
    _recharge_on(c, PowerUsed, lambda ev: ev.actor == me and ev.power == "m6111a4")
    c.no_provoke(on=me, until=When.EOT)
    c.move(_burrow_speed(c), at="burrow")

    def ending(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        if c.moving_as("burrow", on=me):
            c.resist(15, until=When.SONT, on=me)

    c.watch(TurnEnd, ending, until=When.EOT, on=me, once=True, label=c.ref)


# ==========================================================================
# m6161
# ==========================================================================

#: The hold m6161a5 lays to say its aura is charged. Read by m6161a0, which
#: is where the aura's damage is actually dealt.
_M6161_CHARGED = "m6161a5 charge"


@power(
    "m6161a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6161a0(c: Cast) -> None:
    """One aura, two payouts, and a gate on being seen.

    Not `c.burns`: that bites on entry too, where this card charges only for
    starting a turn in the ring. The lightning m6161a5 adds is read off a
    labelled hold rather than written into a second aura, because the printed
    sentence says *her aura also deals* -- one ring, more teeth.

    "If she is not invisible" is asked per victim, which is what being unseen
    is: a creature hidden from one enemy and not another takes no damage off
    the first and does off the second.
    """
    me = c.me

    def bite(who: int) -> None:
        if team(c.world, who) is team(c.world, me):
            return
        if c.is_hidden(from_=who):
            return
        c.flat(10, on=who)
        if any(
            eff.label == _M6161_CHARGED and not eff.ended
            for eff in c.world.effects.of(me)
        ):
            c.flat(10, dtype=DamageType.LIGHTNING, on=who)

    _ring_bites(c, 2, bite, on_entry=False)


@power(
    "m6161a1",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6161a1(c: Cast) -> None:
    """"Any dazing, dominating, or stunning effect on her ends" is the whole
    effect and not the condition, so it is `c.end_effect(carrying=)` rather
    than `c.cure` -- a hold reading "dazed and takes ongoing 5" goes
    entirely, which is what the card says. Looped per condition because
    `end_effect` takes one hold off per call."""
    me = c.me

    def ending(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for cond in _SCRAMBLED:
            while c.end_effect(on=me, carrying=cond) is not None:
                pass

    c.watch(TurnEnd, ending, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6161a2",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m6161a2(c: Cast) -> None:
    """A second slot in the order, and a scripted turn inside it.

    "On an initiative of 10 + her initiative check" is a spliced slot, which
    is how every double-initiative creature in the tree is written -- and
    because the slot is a real turn, the script has to be hung on its start
    rather than offered as an action. The two turns are told apart by
    counting them within the round: the second is the spliced one.

    The last sentence is the alternative rather than an extra: a creature
    that cannot take free actions does the one thing it can, which is shed
    whatever is stopping it.
    """
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(init.rolled + 10)
    seen: dict[int, int] = {}

    def spliced(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        seen[ev.round] = seen.get(ev.round, 0) + 1
        if seen[ev.round] < 2:
            return
        for cond in (Condition.DOMINATED, Condition.STUNNED, Condition.UNCONSCIOUS):
            if c.is_(cond, on=me):
                c.end_effect(on=me, carrying=cond)
                return
        c.teleport(5)
        veil = c.invisible(until=When.EOT, on=me)
        c.use_power("m6161a4", who=me, spend=False)
        if veil is not None and not veil.ended:
            c.world.effects.end(veil, "she becomes visible again")

    c.watch(TurnStart, spliced, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6161a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m6161a3(c: Cast) -> None:
    """Two packets of one blow: the header carries the untyped half and the
    lightning is a second expression, which is the only way a card printing
    "X damage plus Y lightning damage" can resist each half separately."""
    if c.strike():
        c.hit()
        c.damage("1d6", 6, dtype=DamageType.LIGHTNING)


@power(
    "m6161a4",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    requires=lambda world, eid: bool(hidden_from(world, eid)),
    requires_text="she must be invisible",
)
def m6161a4(c: Cast) -> None:
    """The Requirement is a fact about the creature rather than the board, so
    it is declared: `requires=` is evaluated when the row is offered, and
    being unseen is exactly what is true at that moment.

    Each use picks its own target, which is what a row printing no target of
    its own leaves open.
    """
    for _ in range(2):
        victim = _in_reach(c, c.reach("m6161a3"), c.ref)
        if victim is None:
            return
        c.use_power("m6161a3", on=victim, spend=False)


@power(
    "m6161a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("3d8", 12, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m6161a5(c: Cast) -> None:
    """The Effect half is a hold rather than a second aura: m6161a0 reads the
    label and adds the lightning to the ring it already keeps, which is what
    "her aura **also** deals" says."""
    if c.strike():
        c.hit()
        c.slide(3)
    else:
        c.hit(half=True)
        c.slide(1)
    if c.first:
        c.effect(_M6161_CHARGED, on=c.me, until=When.SONT)


@power(
    "m6161a6",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m6161a6(c: Cast) -> None:
    """"Until she hits or misses with an attack" is the attack roll, whichever
    way it lands, which is what `_vanish` watches."""
    _vanish(c, When.EONT)


@power(
    "m6161a7",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="she is first bloodied",
    on=Trigger(Bloodied, about_me, "she is first bloodied"),
)
def m6161a7(c: Cast) -> None:
    """The recharge and the use are one printed sentence."""
    _breathe_again(c, "m6161a5")


# ==========================================================================
# m6162
# ==========================================================================


@power(
    "m6162a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("query.light_level(world, square)",),
)
def m6162a0(c: Cast) -> None:
    """The concealment plays and the upgrade cannot be asked for.

    Partial concealment is a standing hold and is laid outright. The second
    sentence turns on where the light is, and the board holds no light level
    at all -- twelve rows wait on the same reader -- so there is no moment at
    which the swap could be made.
    """
    c.conceal(on=c.me, until=When.ENCOUNTER)


@power(
    "m6162a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 2),
)
def m6162a1(c: Cast) -> None:
    """Only the burn is printed necrotic. The extra dice are a condition on
    the victim rather than on the swing, so they are asked of the board -- a
    daze is not spent by being read."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.NECROTIC)
        if c.is_(Condition.DAZED) or c.is_(Condition.DOMINATED):
            c.damage("3d8", detail=c.ref)


@power(
    "m6162a2",
    level=13,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=16),
)
def m6162a2(c: Cast) -> None:
    """Hit and miss both leave a hold, and the Effect runs either way.

    No damage line at all, so no `c.hit`. The slide names a destination --
    "to a square adjacent to itself" -- so the candidates are worked out and
    one is handed to `c.slide` outright.

    The label is this row's ref, which is what m6162a3 and m6162a4 read: both
    of them name the row rather than the condition, and the row can leave
    either of two.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT, on=victim)
    else:
        c.dazed(until=When.EONT, on=victim)
    room = _free_squares_beside(c, c.me, within=5, of=victim)
    if room:
        dest = c.world.decide(c.me, "slide", room, f"{c.ref}: where it draws them")
        c.slide(5, on=victim, to=dest)


@power(
    "m6162a3",
    level=13,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="it must have a creature dominated",
)
def m6162a3(c: Cast) -> None:
    """"Staying adjacent during the movement" is settled at the end of it:
    the engine moves a creature in one step, so the thrall is slid to a
    square beside wherever the m6162 finished rather than walked alongside.

    The Requirement is asked in the body, because having something dominated
    becomes true and false mid-fight and a `requires=` read once at the
    moment of offering is the wrong clock.
    """
    me = c.me
    thralls = [w for w in _thralls(c.world, me) if c.adjacent(w)]
    if not thralls:
        return
    who = thralls[0]
    c.shift(c.speed_of())
    if c.adjacent(who):
        return
    room = _free_squares_beside(c, me, within=99, of=who)
    if room:
        dest = c.world.decide(me, "slide", room, f"{c.ref}: where it drags them")
        c.slide(c.speed_of(), on=who, to=dest)


@power(
    "m6162a4",
    level=13,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a melee or ranged attack targets it while a creature it has "
    "affected with m6162a2 is adjacent",
    on=Trigger(
        AttackDeclared,
        _attacked_beside_a_thrall,
        "a melee or ranged attack targets it beside one of its thralls",
        window=Window.BEFORE,
    ),
)
def m6162a4(c: Cast) -> None:
    """A free action that has to resolve in the interrupt window, because
    pointing an attack somewhere else is only possible before it is rolled --
    which is what `Trigger(window=)` is for.

    Which creature is read off the live holds rather than off a condition:
    the card names m6162a2 and that row leaves a domination on a hit and a
    daze on a miss, so the condition is not the question.
    """
    shield = [w for w in _thralls(c.world, c.me) if c.adjacent(w)]
    if not shield:
        return
    c.redirect(to=shield[0])


@power(
    "m6162a5",
    level=13,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="it is bloodied",
    on=Trigger(Bloodied, about_me, "it is bloodied"),
)
def m6162a5(c: Cast) -> None:
    """Ten squares and then unseen until it swings, which is `_vanish`'s
    clock -- the attack roll gives it away whether or not it lands."""
    c.teleport(10)
    _vanish(c, When.EONT)


# ==========================================================================
# m6183
# ==========================================================================


@power(
    "m6183a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6183a0(c: Cast) -> None:
    """Surprise is a condition the board holds, so unlike combat advantage it
    can be asked of the victim at the moment of the blow."""
    _extra_against_the_startled(c, "3d6")


@power(
    "m6183a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 7),
)
def m6183a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6183a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=UpTo(2),
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 7),
)
def m6183a2(c: Cast) -> None:
    """How many targets depends on what it is already holding, which has to
    be asked before the first grab of this use lands -- so the whole row runs
    on the first call and the rest return.

    The grip is one sustained hold covering every grab the row made, because
    the printed Sustain line extends all of them together and pays out per
    grabbed creature. `When.SUSTAIN` is the clock and the payout is
    `c.on_sustain`; both read the live set rather than a snapshot, so a
    victim that escaped in between is not charged.
    """
    if not c.first:
        return
    me = c.me
    room = 1 if c.grabbing(of=me) else 2
    grip = c.effect(
        f"{c.ref} grip", on=me, until=When.SUSTAIN, sustain=ActionType.STANDARD
    )
    taken: list[int] = []
    for victim in c.targets[:room]:
        if not c.strike(on=victim):
            continue
        c.hit(on=victim)
        if c.grab(on=victim, dc=25) is not None:
            taken.append(victim)
    if not taken:
        return
    c.on_sustain(
        grip,
        lambda: [
            c.flat(15, dtype=DamageType.ACID, on=w)
            for w in c.grabbing(of=me)
            if alive(c.world, w)
        ],
    )
    if grip is not None:
        grip.on_end.append(
            lambda: [c.escape(on=w, auto=True) for w in c.grabbing(of=me)]
        )


@power(
    "m6183a3",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(3),
    target=Target(
        "enemy", 1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=AC, printed=18),
    damage=Damage("3d8", 7),
)
def m6183a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6183a4",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    dropped=(
        "c.ignore_squeeze_penalty()",
        "c.speed_while_squeezing()",
        "c.no_advantage(squeezing=)",
    ),
    narrative=("skill:perception",),
)
def m6183a4(c: Cast) -> None:
    """One of the two forms plays whole and the other has nothing in it the
    engine can hold.

    The still form is resistance, a hold and a ban, all three of them
    ordinary. Its last sentence is a Perception DC to tell a creature from a
    rock, and nothing on a board rolls one -- there is no symbol waiting to
    be built there, which is why that clause is narrative and the squeezing
    ones are not.

    The ooze form waives the three costs of squeezing and the engine charges
    none of them: `Condition.SQUEEZING` is held, and the half speed, the -5
    and the combat advantage it is meant to carry are not. Two rows already
    wait on the same pair of symbols.
    """
    _two_forms(c, "m6183a4s0", "m6183a4s1")


# ==========================================================================
# m6184
# ==========================================================================


@power(
    "m6184a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6184a0(c: Cast) -> None:
    """A flat five rather than dice, which a minion's numbers usually are."""
    _extra_against_the_startled(c, 5)


@power(
    "m6184a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("", 10, kind=MINION),
)
def m6184a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6184a2",
    level=13,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    dropped=(
        "c.ignore_squeeze_penalty()",
        "c.speed_while_squeezing()",
        "c.no_advantage(squeezing=)",
    ),
    narrative=("skill:perception",),
)
def m6184a2(c: Cast) -> None:
    """The same pair of forms m6183a4 prints, word for word, so it is the
    same helper -- and the same two kinds of absence.

    The still form's last sentence is a perception check to tell a creature
    from a rock, and nothing on a board rolls one, so that clause narrows a
    skill rather than waiting on a verb. The three squeezing clauses are the
    other kind and are dropped.
    """
    _two_forms(c, "m6184a2s0", "m6184a2s1")


# ==========================================================================
# m6651
# ==========================================================================

#: m6651's aura is made by m6651a0 and resized by two other rows, so they
#: all have to name the same label to find it.
_M6651_AURA = "m6651a0"


def _aura_radius(c: Cast, label: str) -> int:
    """How wide the caster's own aura is right now.

    `Zone.aura` is the radius `Zones.refresh` recomputes the footprint from,
    so it is both the reader and the writer for a card that resizes one.
    """
    zid = c.my_aura(label)
    zone = c.world.get(zid, Zone) if zid else None
    return 0 if zone is None or zone.aura is None else zone.aura


@power(
    "m6651a0",
    level=13,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6651a0(c: Cast) -> None:
    """An aura carrying concealment, and the concealment reads the live edge.

    The ring is made once at aura 1 and two other rows resize it, so the gate
    asks `c.in_my_aura` at the moment of each swing rather than freezing a
    distance -- a snapshot would be wrong the first time the aura grew.
    """
    c.aura(1, label=_M6651_AURA, until=When.ENCOUNTER)
    c.conceal(
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.in_my_aura(ctx.get("attacker", -1), label=_M6651_AURA),
    )


@power(
    "m6651a1",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 7),
)
def m6651a1(c: Cast) -> None:
    """Two packets, so each is resisted on its own."""
    if c.strike():
        c.hit()
        c.damage("2d6", dtype=DamageType.COLD)


@power(
    "m6651a2",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d4", 6),
)
def m6651a2(c: Cast) -> None:
    """Only the burn is printed lightning; the blow itself is untyped."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.LIGHTNING)


@power(
    "m6651a3",
    level=13,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m6651a3(c: Cast) -> None:
    """Two swings, and which pair is the m6651's choice.

    The block prints two at-will melee lines and this row names them as one
    of each or two of the second, so the longer reach is the single attack
    and the shorter one is the one that can be doubled.
    """
    pair = c.choose(
        [("m6651a1", "m6651a2"), ("m6651a2", "m6651a2")], f"{c.ref}: which pair"
    )
    for ref in pair or ():
        victim = _in_reach(c, c.reach(ref), c.ref)
        if victim is None:
            return
        c.use_power(ref, on=victim, spend=False)


@power(
    "m6651a4",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6651a4(c: Cast) -> None:
    """`Zone.aura` is the radius, so widening the ring is one assignment and
    a refresh -- `Zones.refresh` recomputes the footprint from that field
    every time anything moves, which is why nothing else has to be told.

    The printed recharge line is a condition on the die, so both are kept:
    the number is what `actions.recharge` rolls and the sentence only ever
    makes the row available sooner.
    """
    me = c.me
    _recharge_on(
        c,
        TurnStart,
        lambda ev: ev.actor == me and _aura_radius(c, _M6651_AURA) < 5,
    )
    c.resize_aura(_M6651_AURA, plus=2)


@power(
    "m6651a5",
    level=13,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.overrun(shift=)",),
)
def m6651a5(c: Cast) -> None:
    """Four clauses and one of them walks where the card shifts.

    "Any effect that includes immobilized, restrained, or slowed ends" is the
    whole hold rather than the condition, which is `c.end_effect(carrying=)`.

    `c.overrun` is the verb that passes through creatures and says which ones
    -- `c.phasing` would walk through walls and floors as well, which is
    wider than this line -- and what is left over is that it walks where the
    card shifts, so it provokes. That is the dropped clause.
    """
    me = c.me
    _recharge_on(
        c,
        TurnStart,
        lambda ev: ev.actor == me and _aura_radius(c, _M6651_AURA) >= 5,
    )
    for cond in (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED):
        while c.end_effect(on=me, carrying=cond) is not None:
            pass
    c.insubstantial(until=When.EONT, on=me)
    for foe in c.overrun():
        if not alive(c.world, foe):
            continue
        c.use_power("m6651a1", on=foe, spend=False)
        if c.landed:
            c.slide(3, on=foe)
            c.prone(on=foe)
    c.resize_aura(_M6651_AURA, to=1)


@power(
    "m6651a6",
    level=13,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=SELF,
    trigger="it takes lightning or thunder damage",
    on=Trigger(DamageApplied, _shocked, "it takes lightning or thunder damage"),
)
def m6651a6(c: Cast) -> None:
    """Both halves of the printed Effect, and the shift is optional by the
    card -- a monster takes the step, which is what the policy is for."""
    c.insubstantial(until=When.EONT, on=c.me)
    c.shift(c.speed_of())
