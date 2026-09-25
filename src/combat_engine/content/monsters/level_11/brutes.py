"""Monster abilities, level 11: the brutes.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=16)` and `Damage("3d8", 10)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

The conventions of the ten levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits and are written as such; a stat block printing no range at
all means melee 1; a printed "Effect (Immediate Interrupt)" is
`action=INTERRUPT` whatever the database's action column says; and a helper
written for an earlier level is imported rather than copied.

Six things this file had to settle.

**"Loses all resistances" is not `c.resist(-n)`.** That takes the same
number off every damage type, so a creature resisting 20 fire and nothing
else would come out *vulnerable* to the other ten. Each entry the creature
actually has is read, taken, and handed back by the hold that took it --
one hold, which is what lets m4836a3 put the weakness and the stripping on
a single saving throw rather than two.

**Dice of extra damage cannot be a modifier.** A `Mod` carries a number and
m4836a0 prints 2d6, so the trait is a watch on its own `Hit` that rolls the
die onto the blow -- the shape level 4 and level 8 both settled on. A gate
on the damage context would have been the other way round and cannot hold
dice.

**Three elites and no second initiative count.** m143, m3076 and m355 are
all elite and none of them prints a row that acts twice, so none is
written: an elite is two creatures' worth of hit points and experience
before it is anything else, and inventing a spliced turn for one would be
inventing a printed line.

**A monster spends a healing surge only when its row says so.** None of
these rows says so -- the two surges each carries at this tier are there
for a leader line to spend -- and none of them takes a second wind either.

**Squeezing is three things and this card waives two of them.** m3076a4 is
the attack penalty and the combat advantage, not the halved speed, so the
whole condition cannot simply be lifted the way level 3's is. The number is
cancelled by a number of the same size gated on the condition; not granting
combat advantage is read off the condition table by `query.grants_ca`,
which has no modifier hook, and is noted rather than approximated.

**`Bloodied` about itself cannot fire on the audit board**, which sets the
caster to half hit points before the fight starts. m3076a2 is such a row
and reports UNUSED however correct it is; it was driven by hand, at full
health, to check. See the report.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_05.brutes import _defences_down
from combat_engine.content.monsters.level_07.brutes import _crit_line
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.brutes import (
    SMALL_ENOUGH,
    _has_hold,
    _holding,
    _is_bloodied,
)
from combat_engine.content.monsters.level_09.brutes import _volley
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
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
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defences,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Miss,
    TurnStart,
    UpTo,
    Usage,
    When,
    World,
    both,
    enemy_within,
    power,
    targets_me,
    use,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, team
from combat_engine.engine.triggers import Trigger, about_me

#: The conditions m4895a0's free saving throw is allowed to answer. The
#: printed line names exactly these three and nothing else.
_HELD_FAST = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED)


def _take_resistances(c: Cast, who: int) -> Callable[[], None]:
    """Strip every resistance a creature has, and return how to give it back.

    `c.resist(-n)` is a different sentence: it takes one number off all
    eleven damage types, so a creature resisting fire alone would finish
    vulnerable to the rest. What the printed line means is each entry that
    is actually there, which is what is read and put back.

    Returned rather than applied to a hold here, so the caller can hang it
    on whichever hold the rest of its line already needs -- "save ends
    both" has to be one saving throw.
    """
    shield = c.world.get(who, Defences)
    had = dict(shield.resist) if shield is not None else {}
    if shield is not None:
        shield.resist.clear()

    def give_back() -> None:
        if shield is None:
            return
        for kind, amount in had.items():
            shield.resist[kind] = shield.resist.get(kind, 0) + amount

    return give_back


def _burning(c: Cast, who: int) -> Any:
    """The fire burn that creature is already carrying, if any."""
    for eff in c.world.effects.of(who):
        if eff.ongoing is not None and eff.ongoing[1] is DamageType.FIRE:
            return eff
    return None


# ==========================================================================
# m143
# ==========================================================================


@power(
    "m143a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d8", 10),
)
def m143a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m143a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m143a1(c: Cast) -> None:
    """The printed Effect does not say whether the two land on one creature
    or two, so the header takes up to two and a single target is bitten
    twice -- the only reading under which "if both attacks hit the same
    target" can ever be true.

    "If it has fewer than two creatures grabbed" is counted off the hold
    relation rather than remembered, because a grab can end between one use
    of this row and the next. The printed escape DC has nowhere to go: a
    grab is a relation and the engine has no contest to put a number in.
    """
    victim = c.target
    if victim is None:
        return
    if _volley(c, "m143a0", victim) and len(_holding(c.world, c.me)) < 2:
        c.grab(on=victim)


@power(
    "m143a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    damage=Damage("4d10", 10),
    requires=_has_hold,
    requires_text="the m143 must be grabbing a creature",
)
def m143a2(c: Cast) -> None:
    """No attack roll is printed: it already has hold of the thing. "One
    creature grabbed by the m143" is narrower than any `Target` can say, so
    the Requirement carries the caster's half and the body picks."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, "m143a2: which of them it crushes") if held else None
    if victim is not None:
        c.hit(on=victim)


# ==========================================================================
# m2959
# ==========================================================================


_M2959_STRUCK = "the m2959 is hit by an adjacent enemy"


@power(
    "m2959a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 6),
)
def m2959a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The printed "crit 4d4 + 14" *replaces* the damage and is a roll,
    so it is dealt flat, past the engine's own rule that a critical maxes
    the declared dice.

    Only the burn is printed as fire; the declared line is untyped, so the
    header carries no type and the ongoing names one.
    """
    if c.strike():
        _crit_line(c, "4d4", 14)
        c.ongoing(5, DamageType.FIRE)


@power(
    "m2959a1",
    level=11,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    trigger=_M2959_STRUCK,
    on=Trigger(Hit, when=both(targets_me, enemy_within(1)), text=_M2959_STRUCK),
)
def m2959a1(c: Cast) -> None:
    """It answers the blow by setting whoever struck it further alight.

    The dispatcher aims a single-enemy row at whoever the event was about,
    so `c.target` is the attacker without the body having to read it off
    the trigger.

    "If the target is already taking ongoing fire damage, that damage
    increases by 5" is the *existing* burn getting worse rather than a
    second one landing, so the hold is found and its number raised -- two
    burns would be two saving throws where the card prints one.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    burn = _burning(c, victim)
    if burn is not None:
        burn.ongoing = (burn.ongoing[0] + 5, DamageType.FIRE)
    else:
        c.ongoing(5, DamageType.FIRE, on=victim)


def _against_a_fire_burn(ctx: dict[str, Any]) -> bool:
    """Is this saving throw the one against an ongoing fire effect?

    `Effects.save` hands the gate `actor`, `effect` and `label`, which is
    the only context a save modifier ever sees -- and it is enough, because
    the effect itself says what it burns with.
    """
    eff = ctx.get("effect")
    ongoing = getattr(eff, "ongoing", None)
    return ongoing is not None and ongoing[1] is DamageType.FIRE


@power(
    "m2959a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=12),
)
def m2959a2(c: Cast) -> None:
    """No damage on the hit at all: the burn and the penalty are the whole
    of it, which is why the header carries no damage line.

    The penalty is gated on what is being saved against rather than held as
    a flat -2 to every save, which is a much heavier card than the one
    printed.
    """
    if c.strike():
        c.ongoing(5, DamageType.FIRE)
        c.penalty("save", 2, until=When.ENCOUNTER, when=_against_a_fire_burn)


# ==========================================================================
# m3076
# ==========================================================================


_M3076_BLED = "the m3076 is first bloodied"
_M3076_DEALT = "the m3076 scores a critical hit"
_M3076_TOOK = "the m3076 is subject to a critical hit"


def _crit_by_me(world: World, me: int, ev: Hit) -> bool:
    return ev.critical and ev.attacker == me


def _crit_on_me(world: World, me: int, ev: Hit) -> bool:
    return ev.critical and ev.target == me


@power(
    "m3076a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 6),
)
def m3076a0(c: Cast) -> None:
    """The printed "crit 4d8 + 22" replaces the damage and is a roll."""
    if c.strike():
        _crit_line(c, "4d8", 22)


@power(
    "m3076a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 6),
)
def m3076a1(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "4d8", 22)


@power(
    "m3076a2",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3076_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M3076_BLED),
)
def m3076a2(c: Cast) -> None:
    """The burst goes off by itself the moment the shell cracks.

    "First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else. Declared with no target because the burst it reaches
    for picks its own.
    """
    use(c.world, c.me, "m3076a1", spend=False)


@power(
    "m3076a3",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=f"{_M3076_DEALT} or {_M3076_TOOK}",
    on=(
        Trigger(Hit, when=_crit_by_me, text=_M3076_DEALT),
        Trigger(Hit, when=_crit_on_me, text=_M3076_TOOK),
    ),
)
def m3076a3(c: Cast) -> None:
    """A critical either way rattles it.

    Two declared triggers rather than one predicate reading both: they are
    two printed sentences and the card should show both. Filed as a standard
    action and plainly a triggered one -- nobody chooses to be stunned by
    their own good luck.
    """
    c.dazed(until=When.EONT, on=c.me)


@power(
    "m3076a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3076a4(c: Cast) -> None:
    """Squeezing costs it one of the three things it normally costs.

    `Condition.SQUEEZING` is half speed, -5 to attack and combat advantage
    to everybody. This card waives the second and the third and keeps the
    first, so the condition itself cannot be lifted the way level 3's is --
    that would hand back the speed as well. The attack penalty is a number
    and is cancelled by a number of the same size, gated on the condition so
    nothing has to remember to put it back.

    Not granting combat advantage is not written: `query.grants_ca` reads it
    off the condition table and there is no modifier hook on it, so the
    exemption cannot be said at all. See the report.
    """
    me = c.me

    def squeezing(_ctx: dict[str, Any]) -> bool:
        return c.is_(Condition.SQUEEZING, on=me)

    c.bonus("attack", 5, until=When.ENCOUNTER, on=me, kind="untyped", when=squeezing)
    c.note("m3076a4: it grants no combat advantage while squeezing")


# ==========================================================================
# m355
# ==========================================================================


@power(
    "m355a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 6),
)
def m355a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m355a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m355a1(c: Cast) -> None:
    """The printed Requirement names the weapon in its hand, and a monster's
    gear is not modelled by name -- it is the same line m355a0 swings, so the
    row is left usable rather than gated on something nothing can answer.

    "A Medium or smaller target" is a size the board knows, so that half is
    written."""
    if c.strike():
        c.hit()
        if c.size_of() in SMALL_ENOUGH:
            c.prone()


# ==========================================================================
# m4836
# ==========================================================================


@power(
    "m4836a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4836a0(c: Cast) -> None:
    """A die of extra damage on anything already bleeding.

    A damage modifier will not carry it: a `Mod` holds a number and the
    printed line adds dice. So it rides on its own `Hit` instead, which is
    the shape level 4 and level 8 both settled on -- and bloodied is asked
    at that moment, because a blow that bloodies its target has bloodied it
    by the time the rider applies.
    """
    me, ref = c.me, c.ref

    def harder(ev: Hit) -> None:
        if ev.attacker != me or team(c.world, ev.target) is team(c.world, me):
            return
        if _is_bloodied(c.world, ev.target):
            c.damage("2d6", on=ev.target, detail=ref)

    c.watch(Hit, harder, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m4836a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d12", 5),
)
def m4836a1(c: Cast) -> None:
    """"Until the end of its next turn" is the *target's* next turn, which is
    `When.EOTNT` -- the one duration clocked on whoever carries it."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.world.effects.apply(
        victim, c.me, When.EOTNT,
        label=f"{c.ref} resistances",
        on_end=[_take_resistances(c, victim)],
    )


@power(
    "m4836a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d12", 5),
)
def m4836a2(c: Cast) -> None:
    """"If the target is bloodied after this attack" is asked after the shove
    as well as after the damage, which is what "after this attack" means."""
    if c.strike():
        c.hit()
        c.push(3)
        if c.bloodied():
            c.prone()


@power(
    "m4836a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d12", 5, kind=LIMITED),
)
def m4836a3(c: Cast) -> None:
    """"Weakened and loses all resistances (save ends both)" is one hold
    carrying both: the weakness is a condition on it and the stripping is
    undone when it ends, so the victim rolls one saving throw against one
    printed sentence rather than two."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS,
        label=c.ref,
        conditions=(Condition.WEAKENED,),
        on_end=[_take_resistances(c, victim)],
    )


# ==========================================================================
# m4895
# ==========================================================================


_M4895_FELLED = "the m4895 drops to 0 hit points"


@power(
    "m4895a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4895a0(c: Cast) -> None:
    """One free saving throw a turn, and only against being held.

    `c.save(against=...)` picks by label fragment, and what the printed line
    picks by is the *conditions* the effect carries -- so the effect is
    found here and `Effects.save` rolls it, which is the same call
    `c.save` makes and the one that announces a `SavingThrow`.

    A compulsion rather than an offer: "can make a saving throw" is a
    permission the creature always takes, and a watch on its own turn
    beginning is how every other row of this shape is written.
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
                return

    c.watch(TurnStart, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4895a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 10),
)
def m4895a1(c: Cast) -> None:
    """The seven is a second packet on a creature the attack never targeted,
    so it is flat damage rather than anything the header could carry."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    others = sorted(foe for foe in c.enemies() if foe != victim and c.adjacent(foe))
    caught = c.choose(others, "m4895a1: who else the swing catches") if others else None
    if caught is not None:
        c.flat(7, on=caught)


@power(
    "m4895a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d10", 14, kind=LIMITED),
)
def m4895a2(c: Cast) -> None:
    """"Recharge if the power misses" is a board state rather than a die.

    The number stays in the header, because that is what the card shows and
    what `actions.recharge` rolls; this is the printed sentence on top of
    it, and the two only ever agree to give the row back sooner.
    """
    me, ref = c.me, c.ref
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == ref)
    if c.strike():
        c.hit()


@power(
    "m4895a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 8, kind=LIMITED),
)
def m4895a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4895a4",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4895_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4895_FELLED),
)
def m4895a4(c: Cast) -> None:
    """One last walk and one last swing as it goes down.

    A creature may answer its own downfall -- the dispatcher makes the
    exception for exactly this shape. Declared `INTERRUPT` because the
    printed Effect says so, whatever the database's action column reads.

    The blow is the at-will melee line rather than the recharge one: the
    printed sentence names the weapon, and that is the row it swings with
    every turn. Declared with no target because by this point there may be
    nobody left in reach, and the walk decides who there is.
    """
    c.move(max(1, c.speed_of() // 2))
    near = sorted(
        (foe for foe in c.enemies() if c.distance(foe) <= 2 and alive(c.world, foe)),
        key=lambda foe: (c.distance(foe), foe),
    )
    if near:
        use(c.world, c.me, "m4895a1", targets=[near[0]], spend=False)


# ==========================================================================
# m4937
# ==========================================================================
#
# The aura sentence names the thing it inflicts by an id belonging to a
# different stat block. Nothing on that block is reached: the curse is this
# trait's own, and is filed under this trait's ref.


def _cursed_by(c: Cast, who: int) -> bool:
    """Is that creature already carrying m4937a0's curse?

    The guard the printed "multiple curses do not stack" asks for, and the
    same question the spreading half asks of a neighbour.
    """
    return any(eff.label.startswith("m4937a0") for eff in c.world.effects.of(who))


def _lay_curse(c: Cast, who: int) -> None:
    """The curse itself: -2 to every defence and vulnerable 5 to everything.

    Two holds rather than one, because a vulnerability is not a `Mod` and
    `c.vulnerable` keeps its own -- so the defence hold ends the other with
    it, and both run out on the same clock. The stacking guard reads the
    first, which is the one either half arrives with.
    """
    if _cursed_by(c, who):
        return
    hold = _defences_down(c, who, 2, When.EOTNT)
    weakness = c.vulnerable(5, on=who, until=When.EOTNT)
    if weakness is not None:
        hold.on_end.append(lambda: c.world.effects.end(weakness, "the curse lifts"))


@power(
    "m4937a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4937a0(c: Cast) -> None:
    """An aura 1 that curses, and a curse that walks to the next creature.

    Not the aura helper, whose hold is carried for as long as its owner
    stands inside: this one is taken at a boundary and then keeps its own
    clock, so membership is measured at that moment and read off the zone
    the aura made rather than by distance -- the ring the board draws and
    the ring the curse is caught in are the same object.

    The spreading half is checked on the same turn beginning, and against
    the *cursed creature's own side*: "any ally of that creature" is who the
    printed line names, so a second m4937 standing next to a cursed enemy
    does not catch it.
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
    "m4937a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 10),
)
def m4937a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4937a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m4937a2(c: Cast) -> None:
    """"Until the end of the m4937's next turn" is the caster's clock, which
    is `When.EONT` -- not the target's."""
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)
