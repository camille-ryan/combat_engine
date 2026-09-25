"""Monster abilities, level 11: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=18)` and `Damage("2d10", 8)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

The conventions of the ten levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; a stat block printing no range at all means melee 1; a
printed "Range 5/10" is a normal range and a long one and the normal one is
what `Range` holds; a printed "Effect (Immediate Interrupt)" is
`action=INTERRUPT` whatever the database's action column says; and a helper
written for an earlier level is imported rather than copied.

Four things this file had to settle.

**A bonus that lasts one attack roll on its own turn.** m660a0 is a
`once=True` attack bonus laid at the start of each ally's turn -- but
`When.EOT` is clocked on whoever *applied* the effect, which is the m660,
so a bonus meant to lapse at the end of the ally's turn would have hung on
until the m660's. The hold is therefore ended on that ally's own `TurnEnd`
as well, which is the clock the printed line actually names.

**"Granting combat advantage to that ally" is per reader.** m5019a0's aura
is a damage modifier whose gate asks `query.has_combat_advantage` of the
ally carrying it and the creature being swung at -- the damage context
carries `target` and nothing about who is swinging, so the attacker has to
come from the closure rather than from the context.

**A burn that a second hit makes worse** is the existing hold's number
raised, not a second hold: two would be two saving throws against one
printed sentence. The same shape the brutes at this level settled on.

**Willing movement is `MoveEnd`.** Forced movement never emits one -- a
push, a pull and a slide all go through `movement.forced`, which announces
`ForcedMove` and steps -- so watching `MoveEnd` is exactly the printed "if
it willingly moves", with no need to enumerate what does not count. The
watch also asks whose turn it is, because "during its next turn" is a turn
and not a duration.

Artillery first, then the minions, each group in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.controllers import _same_stock
from combat_engine.content.monsters.level_08.brutes import _aura
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Effect,
    Hit,
    Keyword,
    Melee,
    Mod,
    MoveEnd,
    Ranged,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    ally_within,
    distance,
    power,
    targets_me,
    use,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, has_combat_advantage, is_
from combat_engine.engine.triggers import Trigger, about_me

# ==========================================================================
# m5019
# ==========================================================================


@power(
    "m5019a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5019a0(c: Cast) -> None:
    """Five more damage to anything that has dropped its guard, for whoever
    is standing inside the ring.

    The gate reads the creature being swung at off the damage context --
    which carries `target` and no attacker at all -- and the creature doing
    the swinging off the closure, because the modifier belongs to one named
    ally and the question is asked from that ally's side.

    The aura helper is the right one here: the bonus is carried for exactly
    as long as its owner stands inside, and `ZoneEntered`/`ZoneExited` are
    the two moments it should go on and come off.
    """
    me = c.me

    def eligible(who: int) -> bool:
        return who != me and who in c.allies()

    def hold(who: int) -> Effect | None:
        def off_guard(ctx: dict[str, Any]) -> bool:
            victim = ctx.get("target")
            return victim is not None and has_combat_advantage(c.world, who, victim)

        return c.bonus(
            "damage", 5, until=When.ENCOUNTER, on=who, kind="power", when=off_guard
        )

    _aura(c, 5, eligible, hold)


@power(
    "m5019a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5019a1(c: Cast) -> None:
    """A Stealth check made in circumstances that normally forbid one, and
    the engine rolls no Stealth: hiding here is a relation a row sets, not a
    check anything makes, and there is no requirement to lower. Deliberately
    inert rather than given an invented mechanic."""
    c.note("m5019a1: it can hide with superior cover or total concealment")


@power(
    "m5019a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 5),
)
def m5019a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5019a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 8),
)
def m5019a3(c: Cast) -> None:
    """Range 15/30: the header carries the short range, which is the only one
    the engine measures.

    "Grants combat advantage" with nobody named is the whole of the m5019's
    side, which is `to="allies"` -- the relation names one beneficiary at a
    time and the method holds them all on one effect.
    """
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "m5019a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5019a4(c: Cast) -> None:
    """The shot is m5019a3 used again, and a hit opens a swing for a friend.

    Whether it landed cannot be read off `use`, which reports that a row
    could be used and not that it hit, so the hits are counted off the bus
    for as long as the shot is in the air -- the arrangement `_volley`
    settled on two levels down.

    Declared with no target: the row it reaches for picks its own, and the
    free swing is aimed at whatever that turned out to be.
    """
    me = c.me
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m5019a3":
            landed.append(ev.target)

    counter = c.watch(Hit, tally, until=When.EOT, on=me, label=f"{c.ref} tally")
    try:
        use(c.world, me, "m5019a3", spend=False)
    finally:
        c.world.effects.end(counter, "the shot has landed")

    for victim in landed:
        if not alive(c.world, victim):
            continue
        near = sorted(
            friend
            for friend in c.within(1, of=victim, side="ally")
            if friend != me and alive(c.world, friend)
        )
        chosen = c.choose(near, f"{c.ref}: which ally strikes") if near else None
        if chosen is not None:
            c.grant_attack(chosen, on=victim)


# ==========================================================================
# m660
# ==========================================================================
#
# Four of this card's sentences spell the creature's id as one belonging to
# a different stat block. This creature is the one they plainly mean.


_M660_STRUCK = "an attack hits the m660"


@power(
    "m660a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m660a0(c: Cast) -> None:
    """One +2 to one roll, on each ally's own turn, for anything that can
    hear it.

    Written as the attack roll of the four the printed line offers: a skill
    check and an ability check are not rolled anywhere in the engine, and a
    bonus that could be spent on either would be a bonus nothing ever spends.

    `once=True` is what makes it *one* roll. The duration is the awkward
    half: `When.EOT` is clocked on whoever applied the effect -- the m660 --
    so the hold would have outlived the ally's turn by most of a round. It
    is given the target's clock and then ended on that ally's own `TurnEnd`,
    which is the boundary the printed line names.

    Hearing is asked as not being deafened, which is the only thing the
    engine records about ears.
    """
    me = c.me
    ring = c.aura(10, until=When.ENCOUNTER)

    def inspire(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.allies():
            return
        who = ev.actor
        if who not in c.world.zones.occupants(ring):
            return
        if is_(c.world, who, Condition.DEAFENED):
            return
        boon = c.bonus(
            "attack", 2, until=When.EOTNT, on=who, kind="power", once=True
        )
        if boon is None:
            return

        def lapse(done: TurnEnd) -> None:
            if done.actor == who and not boon.ended:
                c.world.effects.end(boon, "the turn is over")

        boon.subs.append(c.world.bus.on(TurnEnd, lapse, owner=who))

    c.watch(TurnStart, inspire, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m660a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m660a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m660a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m660a2(c: Cast) -> None:
    """Already slowed is asked before the rider lands, not after: the printed
    line is about the state the target arrived in."""
    already = c.is_(Condition.SLOWED)
    if not c.strike():
        return
    c.hit()
    if already:
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m660a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("3d8", 8, kind=LIMITED),
)
def m660a3(c: Cast) -> None:
    """"Creatures in the blast", so it catches its own side too -- and its
    own side is what the halving clause is there for."""
    if c.strike():
        c.hit(half=c.is_kind("aberrant"))
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m660a4",
    level=11,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m660a4(c: Cast) -> None:
    c.teleport(3)


@power(
    "m660a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M660_STRUCK,
    on=Trigger(Hit, when=targets_me, text=_M660_STRUCK),
)
def m660a5(c: Cast) -> None:
    """Declared `INTERRUPT` because the printed Effect says so, whatever the
    database's action column reads. It does not dodge the blow -- the hit is
    already announced -- which is what the card prints: the m660 is
    somewhere else by the time anybody follows up."""
    c.teleport(3)


# ==========================================================================
# m75
# ==========================================================================


def _rattled(c: Cast, who: int) -> Effect | None:
    """"Dazed and a -2 penalty to attack rolls (save ends both)".

    One hold carrying both. `c.condition` takes conditions and ongoing
    damage and no modifier, so the effect is applied directly -- which is
    the only way the victim gets one saving throw rather than two.
    """
    return c.world.effects.apply(
        who,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        conditions=(Condition.DAZED,),
        mods=[(who, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
    )


@power(
    "m75a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 3),
)
def m75a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m75a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 6),
)
def m75a1(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is the only one
    the engine measures."""
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _rattled(c, victim)


@power(
    "m75a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m75a2(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _rattled(c, victim)


# ==========================================================================
# The minions. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# ==========================================================================


# --------------------------------------------------------------------------
# m315
# --------------------------------------------------------------------------


@power(
    "m315a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m315a0(c: Cast) -> None:
    """Two of these pressed together are harder to hit than one.

    A gated modifier rather than a hold put on and taken off as they shuffle
    about: the gate is asked as the attack is resolved, which is the moment
    the printed adjacency is measured. Two creatures are the same sort when
    `Ident.ref` says so, which is the only thing on the board that does.
    """
    me = c.me

    def shoulder_to_shoulder(_ctx: dict[str, Any]) -> bool:
        return any(
            other != me and _same_stock(c.world, me, other)
            for other in c.within(1, of=me, side="any")
        )

    c.bonus(
        AC, 2, until=When.ENCOUNTER, on=me, kind="untyped",
        when=shoulder_to_shoulder,
    )


@power(
    "m315a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=9, kind=MINION),
)
def m315a1(c: Cast) -> None:
    """The nine is untyped and only the rider burns, so the header carries no
    damage type.

    "Willingly moves" is `MoveEnd`: forced movement goes through
    `movement.forced`, which announces `ForcedMove` and steps, and emits no
    `MoveEnd` at all -- so the event is exactly the printed sentence without
    having to enumerate what does not count. Whose turn it is, is asked as
    well, because "during its next turn" names a turn rather than a
    duration, and the watch spends itself on the first step.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()

    def scorch(ev: MoveEnd) -> None:
        if ev.actor == victim and c.turn_of() == victim:
            c.flat(4, dtype=DamageType.FIRE, on=victim)

    c.watch(
        MoveEnd, scorch, until=When.EOTNT, on=victim, once=True, label=c.ref
    )


# --------------------------------------------------------------------------
# m354
# --------------------------------------------------------------------------


@power(
    "m354a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage(bonus=8, kind=MINION),
)
def m354a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5003
# --------------------------------------------------------------------------


_M5003_MATE_BLED = "an ally within 3 squares of the m5003 is first bloodied"
_M5003_FELLED = "the m5003 drops to 0 hit points"


@power(
    "m5003a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage(bonus=8, kind=MINION),
)
def m5003a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5003a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage(bonus=8, kind=MINION),
)
def m5003a1(c: Cast) -> None:
    """It runs past, bites, and keeps going with the victim in its teeth.

    "Makes the attack at any point during the move" is written as closing to
    reach and swinging there, which is the only point in the move at which
    the attack can land; what is left of the speed is then the rest of the
    move, measured from where it set off rather than guessed at.

    The drag is `c.pull` for exactly as far as it went, which is what "pulls
    the target with it" comes to -- a pull is the forced move that ends
    nearer whoever is doing it, so the victim finishes beside it wherever it
    stopped. Continuing is a choice, so it is asked as one, and it is the
    m5003's choice rather than the victim's.
    """
    victim = c.target
    if victim is None:
        return
    start = c.here
    c.run_at(victim)
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    left = c.speed_of() - distance(start, c.here)
    if left <= 0 or not c.may("carry it off", who=c.me):
        return
    c.no_provoke(from_=victim, until=When.EOT)
    moved = c.move(left)
    if moved:
        c.pull(moved, on=victim)


@power(
    "m5003a2",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M5003_MATE_BLED,
    on=Trigger(Bloodied, when=ally_within(3), text=_M5003_MATE_BLED),
)
def m5003a2(c: Cast) -> None:
    """Declared with no target: the event is about an ally, so the
    dispatcher's aim would point the bite at the wrong creature -- the row
    picks from whoever is actually in reach."""
    near = sorted(
        (foe for foe in c.enemies() if c.adjacent(foe)),
        key=lambda foe: (c.distance(foe), foe),
    )
    if near:
        use(c.world, c.me, "m5003a0", targets=[near[0]], spend=False)


@power(
    "m5003a3",
    level=11,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M5003_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M5003_FELLED),
)
def m5003a3(c: Cast) -> None:
    """One last bite as it goes down.

    A creature may answer its own downfall -- the dispatcher makes the
    exception for exactly this shape. Declared `INTERRUPT` because the
    printed Effect says so, whatever the database's action column reads.
    """
    near = sorted(
        (foe for foe in c.enemies() if c.adjacent(foe)),
        key=lambda foe: (c.distance(foe), foe),
    )
    if near:
        use(c.world, c.me, "m5003a0", targets=[near[0]], spend=False)


# --------------------------------------------------------------------------
# m58
# --------------------------------------------------------------------------


@power(
    "m58a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, dtype=DamageType.FIRE, kind=MINION),
)
def m58a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()
