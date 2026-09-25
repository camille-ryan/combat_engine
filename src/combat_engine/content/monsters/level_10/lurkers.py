"""Monster abilities, level 10: the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=15)` and `Damage("2d10", 7)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the nine levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block printing no range at all means melee 1; a printed "Range 5/10" is a
normal range and a long one and the normal one is what `Range` holds; and a
helper written for an earlier level is imported rather than copied.

Five things this file had to settle.

**Half damage from everything but one type** is not `Condition.INSUBSTANTIAL`:
that halves the exception too, and there is no way to exempt a damage type
from it. `DamageRolled` carries a mutable `amount` and is read back, so the
halving is a listener in the interrupt window that lets force through -- and
it asks whether the packet came off an **attack**, because the printed line
says attacks and a burn is not one.

**A light that has to be on to attack.** The trait is the arrangement rather
than a state: the row that puts the light out lays a labelled hold, and the
trait watches for that hold and hangs the two consequences on it -- unseen,
and unable to raise a hand. The hold runs to the start of its next turn,
because nothing else could end it: the printed way out of the dark is to
light up again, and a creature that cannot attack while dark would otherwise
never do anything else for the rest of the fight.

**"Removed from play"** is `Condition.REMOVED`, hung on the victim's own
saving throw rather than on a clock, and the way back is a square beside the
victim chosen when the hold ends rather than now. The same shape m727a3
settled on two levels down.

**Invisible "until it attacks" and invisible "until the end of its next
turn" are different holds.** `c.hide` is the first -- `resolve.attack`
breaks it for whoever swung, which is the printed Stealth rule -- and
`_clocked_veil` is the second, which sets the relation again as the swing
breaks it.

**"If the m326 is invisible, twice each"** is asked once for the whole use
and remembered in a labelled hold: the body runs once per target and the
first swing gives the creature away, so asking again on the second target
answers no and the row would quietly halve itself.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_06.controllers import _living
from combat_engine.content.monsters.level_07.brutes import _crit_line
from combat_engine.content.monsters.level_07.controllers import _vanish
from combat_engine.content.monsters.level_07.lurkers import _clocked_veil
from combat_engine.content.monsters.level_07.skirmishers import _hurt_by_an_attack
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.lurkers import _appear_beside, _holding
from combat_engine.content.monsters.level_09.brutes import _regenerates
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
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Effect,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    power,
    use,
)
from combat_engine.engine.events import DamageRolled, EffectApplied
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import adjacent, enemies, is_
from combat_engine.engine.triggers import Trigger, about_me, targets_me

#: The four defences, for a printed "a +4 bonus to all defenses".
EVERY_DEFENCE = (AC, FORT, REF, WILL)

#: What "a melee or a ranged attack" means as a range kind. A close burst is
#: neither, and `by_melee` counts one as melee -- which is right for the rows
#: it was written for and wrong for m130a4.
_WEAPON_RANGES = ("melee", "ranged")

#: The hold that says the m1580's light is out. The trait reads it; the
#: interrupt that douses the light lays it.
_M1580_DARK = "m1580a0 doused"


def _unseen_by(c: Cast, who: int) -> bool:
    """Can that creature see this one at all?

    Either of the two things the engine holds about not seeing: the watcher
    is blind, or this creature is hidden from it in particular.
    """
    return c.is_hidden(from_=who) or is_(c.world, who, Condition.BLINDED)


def _douse(c: Cast, until: When) -> Effect | None:
    """Put the m1580's light out, if it is not already out."""
    return None if _holding(c, _M1580_DARK) else c.effect(_M1580_DARK, until=until, on=c.me)


# ==========================================================================
# m130
# ==========================================================================


@power(
    "m130a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m130a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. The printed "crit 1d8 + 13" *replaces* the damage and is a roll,
    so it is dealt flat -- past the engine's own rule that a critical maxes
    the declared dice, which would read the wrong number off this header."""
    if c.strike():
        _crit_line(c, "1d8", 13)


@power(
    "m130a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 5),
)
def m130a1(c: Cast) -> None:
    """5/10 is a normal range and a long one, and `Range` holds one number,
    so the normal range is written."""
    if c.strike():
        c.hit()


@power(
    "m130a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(4, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m130a2(c: Cast) -> None:
    """A zone of darkness, held up by sustaining it.

    `blocks_sight` is what `cover_between` reads, and it deliberately
    excludes the squares either party is standing in -- so this shelters what
    is behind it rather than what is inside it, which is what a wall of
    darkness does. Darkvision is a sense and the engine holds none, so the
    exemption is noted rather than invented.
    """
    c.zone(
        c.area(), label=c.ref, until=When.SUSTAIN, blocks_sight=True, sustain=MINOR
    )
    c.note("m130a2: a creature with darkvision sees through it")


_M130_FELL = "the m130 drops to 0 hit points"


@power(
    "m130a3",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M130_FELL,
    on=Trigger(Dropped, when=about_me, text=_M130_FELL),
)
def m130a3(c: Cast) -> None:
    """A death throe. The dispatcher offers it to a creature that is no
    longer alive, which is the only way a row of this shape fires, and
    `Dropped` names its subject `actor`.

    No attack roll at all: the printed line blinds each enemy outright.
    """
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m130a4",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m130a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Read off the `Hit` rather than asked of the board again: a one-shot grant
    of combat advantage has already been spent by the time the blow is
    announced, so asking a second time comes back false on exactly the
    attacks this rider is for. "Melee and ranged attacks" is those two range
    kinds and no others -- a burst is neither.
    """
    me, ref = c.me, c.ref

    def rider(ev: Any) -> None:
        if ev.attacker != me or not c.had_advantage(ev):
            return
        if _reach_kind(ev) in _WEAPON_RANGES:
            c.damage("2d6", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m130a5",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m130a5(c: Cast) -> None:
    """A slinking four squares.

    The guard is gated on `opportunity`, which the attack context carries for
    exactly this, and comes down as the move ends. What it ends its move
    beside is asked afterwards -- the printed line is about where it stops,
    not what it passed -- and the advantage is its own, for the rest of its
    turn.
    """
    me = c.me

    def against_openings(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity"))

    guard = c.bonus(AC, 4, until=When.EOT, on=me, when=against_openings)
    try:
        c.move(4)
    finally:
        if guard is not None:
            c.world.effects.end(guard, "the move is over")
    for foe in sorted(c.within(1, side="enemy")):
        c.grants_advantage(on=foe, to=me, until=When.EOT)


@power(
    "m130a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m130a6(c: Cast) -> None:
    """"Invisible until the end of its next turn" is a clock rather than a
    hiding place, so attacking does not end it -- which is what
    `_clocked_veil` sets the relation again for."""
    _clocked_veil(c, When.EONT)


# ==========================================================================
# m1580
# ==========================================================================


@power(
    "m1580a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1580a0(c: Cast) -> None:
    """The light, and what goes with putting it out.

    The trait is the arrangement rather than a state of its own: the row that
    douses the light lays a labelled hold, and this hangs both printed
    consequences on it -- unseen while it is dark, and unable to attack until
    it lights up again. `EffectApplied` is what announces a hold carrying
    nothing but its label, which is the only reason this can be watched for.

    Both consequences run to the end of the encounter and are ended by the
    hold rather than by a clock of their own, so they last exactly as long as
    the dark does.
    """
    me = c.me

    def doused(ev: EffectApplied) -> None:
        if ev.target != me or ev.label != _M1580_DARK:
            return
        hold = next(
            (eff for eff in c.world.effects.of(me) if eff.label == _M1580_DARK), None
        )
        if hold is None:
            return
        for held in (
            c.invisible(until=When.ENCOUNTER),
            c.cannot_attack(on=me, until=When.ENCOUNTER),
        ):
            if held is not None:
                hold.on_end.append(
                    lambda h=held: c.world.effects.end(h, "the light is back")
                )

    c.watch(EffectApplied, doused, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m1580a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1580a1(c: Cast) -> None:
    """Half of everything but force.

    `Condition.INSUBSTANTIAL` is the near neighbour and the wrong one: it
    halves force as well and nothing can exempt a type from it. The packet
    itself is halved instead, in the window where `DamageRolled.amount` is
    still negotiable, and only where it came off an **attack** -- the printed
    line says attacks, and a burn or a zone is not one.
    """
    me = c.me

    def soften(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0 or ev.dtype is DamageType.FORCE:
            return
        if _hurt_by_an_attack(c.world, me, ev):
            ev.amount //= 2

    c.watch(
        DamageRolled, soften, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=c.ref,
    )


@power(
    "m1580a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 11, dtype=DamageType.RADIANT),
)
def m1580a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1580a3",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 9, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1580a3(c: Cast) -> None:
    """"One bloodied living creature" is a target line no `Target` can say --
    one carries a side and a count -- so the aim is narrowed here. Living is
    asked of the type line, which is the only place the engine records
    anything about being alive.

    The fourteen is an Effect line in all but name: it is printed on the hit,
    so it goes with the blow.
    """
    victim = c.target
    if victim is None or not c.bloodied(victim) or not _living(c, victim):
        victim = c.choose(
            [
                foe
                for foe in sorted(c.enemies())
                if c.distance(foe) <= 3 and c.bloodied(foe) and _living(c, foe)
            ],
            "m1580a3: which bloodied creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.weakened(until=When.SAVE_ENDS, on=victim)
    c.heal(14, on=c.me)


@power(
    "m1580a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(20),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
)
def m1580a4(c: Cast) -> None:
    """No damage line at all: the pull and the daze are the whole of the hit.

    "One creature in the burst that can see" is narrowed here: a blind
    creature cannot be led anywhere by a light, and neither can one with
    nothing between it and the wisp to see along.
    """
    victim = c.target
    if victim is None or is_(c.world, victim, Condition.BLINDED) or not c.can_see(victim):
        return
    if c.strike(on=victim):
        c.pull(3, on=victim)
        c.dazed(until=When.SAVE_ENDS, on=victim)


_M1580_MISSED = "an attack misses the m1580"


@power(
    "m1580a5",
    level=10,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M1580_MISSED,
    on=Trigger(Miss, when=targets_me, text=_M1580_MISSED),
)
def m1580a5(c: Cast) -> None:
    """It goes out and is somewhere else.

    The dark runs to the start of its next turn. No clock is printed, and it
    is the only one that works: the trait above bars it from attacking while
    the light is out, so a hold with no end would leave the creature drifting
    for the rest of the fight. Relighting is a free action it takes on its
    own turn, which is what that comes to.
    """
    _douse(c, When.SONT)
    c.teleport(5)


# ==========================================================================
# m3081
# ==========================================================================


@power(
    "m3081a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m3081a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means.

    "Ongoing 5 necrotic and poison" is one burn of two types and an effect
    holds one, so the first printed type is kept and a creature resistant
    only to the other takes it in full -- the approximation the levels below
    settled on for the same shape. "Save ends both" is one effect carrying
    the hold and the burn together.
    """
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m3081a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3081a1(c: Cast) -> None:
    """Four separate modifiers, so nothing is competing with anything: one
    "+4 to all defenses" written as a single mod would be a +4 to nothing."""
    c.shift(5)
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 4, until=When.SONT, on=c.me)


@power(
    "m3081a2",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3081a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. Said twice, once per
    word, which is how `c.ignores_difficult` takes a printed list -- the
    labels are the ones a web zone and a swarm's ring give their squares."""
    c.ignores_difficult("web", until=When.ENCOUNTER)
    c.ignores_difficult("swarm", until=When.ENCOUNTER)


# ==========================================================================
# m326
# ==========================================================================


@power(
    "m326a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m326a0(c: Cast) -> None:
    """Regeneration, written out: the engine holds no such thing, and "has at
    least 1 hit point" is `hp > 0` rather than `alive`."""
    _regenerates(c, 5)


@power(
    "m326a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d12", 8),
)
def m326a1(c: Cast) -> None:
    """The rider is read off the roll this body just made rather than asked
    of the board again: a one-shot grant of combat advantage has already been
    spent by then, and a blow struck from concealment would answer no."""
    if not c.strike():
        return
    c.hit()
    if c.result is not None and c.result.advantage:
        c.damage("2d6")


@power(
    "m326a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m326a2(c: Cast) -> None:
    """Two creatures, and twice each if it is not being seen.

    Whether it is unseen is asked once for the whole use and kept in a hold
    that lasts the turn: the body runs once per target, and the first swing
    gives the creature away -- so asking again on the second target answers
    no and the row would quietly halve itself.

    The row that prints the blow is used rather than copied, so its damage
    stays in one place.
    """
    me, ref = c.me, c.ref
    unseen = f"{ref} unseen"
    if c.first and c.is_hidden():
        c.effect(unseen, until=When.EOT, on=me)
    if c.target is None:
        return
    for _ in range(2 if _holding(c, unseen) else 1):
        use(c.world, me, "m326a1", targets=[c.target], spend=False)


@power(
    "m326a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 12, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m326a3(c: Cast) -> None:
    """The printed recharge is a sentence on top of the die the database
    files, and the two only ever agree to make the row available sooner."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m326a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d6", 10, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m326a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m326a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m326a5(c: Cast) -> None:
    """"Until immediately after it uses an attack power" is the roll giving
    it away, hit or miss, which is what `_vanish` watches for."""
    _vanish(c, When.ENCOUNTER)


@power(
    "m326a6",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m326a6(c: Cast) -> None:
    """A disguise and nothing else: the shape carries no statistics, gates no
    other row, and the way through it is an Insight check, which the engine
    has no skills to roll."""
    c.note("m326a6: it appears as a Medium or Large humanoid until it changes back")


# ==========================================================================
# m4860
# ==========================================================================


@power(
    "m4860a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4860a0(c: Cast) -> None:
    """Out of sight the moment nobody is standing over it.

    Both printed ends are what `_vanish` holds: a clock of its own next turn,
    and the attack roll that gives it away whichever way the die falls.
    """
    me = c.me

    def stirs(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or c.within(1, side="enemy"):
            return
        _vanish(c, When.EONT)

    c.watch(TurnStart, stirs, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4860a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 5),
)
def m4860a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4860a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d8", 5),
)
def m4860a2(c: Cast) -> None:
    """Whether the target could see it is asked **before** the roll: the
    swing is what breaks the hiding, so asked afterwards the answer is no for
    every creature every time."""
    victim = c.target
    if victim is None:
        return
    blind = _unseen_by(c, victim)
    if c.strike(on=victim):
        c.hit(on=victim)
        if blind:
            c.dazed(until=When.EONT, on=victim)


# ==========================================================================
# m4990
# ==========================================================================


@power(
    "m4990a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m4990a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4990a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC),
)
def m4990a1(c: Cast) -> None:
    """The card spells the blinding's clock as another stat block's id; the
    creature every sentence plainly means is this one, and its own next turn
    is the clock."""
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


def _blind_neighbour(world: World, eid: int) -> bool:
    """Is there anybody in reach that cannot see this creature?

    The printed target line rather than a printed Requirement, declared as
    one because it is the whole of what makes the row usable: with every
    enemy watching there is no legal target, and a row that is offered and
    then finds nobody is indistinguishable from one written wrong.
    """
    ask = Cast(world=world, me=eid, ref="m4990a2")
    return any(
        adjacent(world, eid, foe) and _unseen_by(ask, foe)
        for foe in enemies(world, eid)
    )


@power(
    "m4990a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=WILL, printed=13),
    requires=_blind_neighbour,
    requires_text="a creature in reach must not be able to see the m4990",
)
def m4990a2(c: Cast) -> None:
    """It steps into its victim's head and is not on the board until let go.

    No damage line: the burn and the daze are the whole of the hit, and they
    are one effect because the card prints one saving throw.

    "One creature that cannot see the m4990" is a target line no `Target` can
    say, so the aim is narrowed here. `Condition.REMOVED` is what the engine
    has for a creature that is present and out of the fight; it hangs on the
    victim's own hold rather than on a clock, and the way back is a square
    beside the victim chosen when the hold ends rather than now. Dropping the
    victim ends it too, which is the printed second way out.
    """
    me = c.me
    victim = c.target
    if victim is None or not _unseen_by(c, victim):
        victim = c.choose(
            [foe for foe in sorted(c.enemies()) if c.adjacent(foe) and _unseen_by(c, foe)],
            "m4990a2: which creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    hold = c.condition(
        Condition.DAZED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(20, DamageType.PSYCHIC),
    )
    if hold is None:
        return
    inside = c.condition(Condition.REMOVED, until=When.ENCOUNTER, on=me)

    def felled(ev: Dropped) -> None:
        if ev.actor == victim and not hold.ended:
            c.world.effects.end(hold, "the target fell")

    def step_out() -> None:
        if inside is not None:
            c.world.effects.end(inside, "it comes back")
        _appear_beside(c, victim)

    hold.subs.append(c.world.bus.on(Dropped, felled, owner=me))
    hold.on_end.append(step_out)


@power(
    "m4990a3",
    level=10,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m4990a3(c: Cast) -> None:
    """The opening is offered to its whole side, which is what a printed
    "grants combat advantage" with nobody named means."""
    for foe in sorted(c.within(1, side="enemy")):
        c.grants_advantage(on=foe, to="allies", until=When.EONT)
    c.teleport(3)


_M4990_BIT = "the m4990 hits with m4990a0 or m4990a1"


def _bit_with_either(world: World, me: int, ev: Any) -> bool:
    return ev.attacker == me and ev.power in ("m4990a0", "m4990a1")


@power(
    "m4990a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger=_M4990_BIT,
    on=Trigger(Hit, when=_bit_with_either, text=_M4990_BIT),
)
def m4990a4(c: Cast) -> None:
    """Extra damage on the triggering blow, as a packet of its own rather
    than a modifier -- a modifier would add to whatever else was riding
    along and would lose the type."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("2d6", dtype=DamageType.PSYCHIC, on=victim)
