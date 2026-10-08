"""Monster abilities, level 2, the stat blocks that print no role.

Four blocks, 27 rows. A role-less type line is usually not an encounter
monster at all -- across the corpus most of them are an item's conjuration,
a mount or a summoned servant -- but these four are the other kind:
ordinary creatures whose type line simply omits the word. Every row here
has combat meaning, so nothing is `out_of_combat`.

The conventions are the ones `level_01/soldiers_sa.py` settled and they are
kept unchanged:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=9)`) and the damage line goes in the
  header as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. `turns` uses every such
  row once at the start of the encounter;
* a printed range of "15/30" takes the **normal** range.

Two of the four are leaders, and a leader's sentence is mostly about
somebody else, so `on=` is passed explicitly everywhere: almost every
`Cast` method follows `c.target`, and "m6008 or one ally within 5 squares
gains" does not.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Event,
    Keyword,
    Melee,
    MeleeOrRanged,
    Position,
    Ranged,
    Square,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    ConditionApplied,
    Hit,
    Miss,
    MoveStart,
    SavingThrow,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.triggers import Trigger, by_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _step_into_vacated(c: Cast, was: Square | None) -> None:
    """Follow the shove into the square the target just left.

    `c.shift` with a bare distance asks the controller for a destination,
    which on a quiet board walks the other way -- and the printed sentence
    names the square, so it is passed as one. Nothing happens when the shove
    failed and the square is still occupied.
    """
    if was is None:
        return
    if c.world.grid.passable(was) and c.world.grid.occupant(was) is None:
        c.shift(1, to=was)


def _square_of(c: Cast, who: int | None) -> Square | None:
    pos = c.world.get(who, Position) if who is not None else None
    return pos.square if pos else None


def _shrug_off_prone(c: Cast) -> None:
    """A save against being knocked down, taken as the hold lands.

    `Effects.apply` installs the condition and *then* announces it, so there
    is no event to cancel; the hold that put the creature down is ended
    instead, inside the same window, and nothing gets a turn in between. The
    save is rolled bare -- it is the printed saving throw and not a save
    against a standing effect.
    """
    me = c.me

    def shrug(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        if not c.save(on=me, bare=True):
            return
        for effect in list(c.world.effects.of(me)):
            if Condition.PRONE in effect.conditions:
                c.world.effects.end(effect, c.ref)

    c.watch(
        ConditionApplied, shrug, until=When.ENCOUNTER, on=me,
        label=f"{c.ref} footing",
    )


# --------------------------------------------------------------------------
# m6007
# --------------------------------------------------------------------------


@power(
    "m6007a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m6007a0(c: Cast) -> None:
    """The mark is inside the Hit here, not an Effect, so a miss lays none."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m6007a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m6007a1(c: Cast) -> None:
    """The printed Requirement is this creature's own shield, which its stat
    block equips and never puts down, so there is no gate to ask: a monster's
    kit does not change mid-fight the way a character's hands do. The shove
    and the step after it are one sentence and the step is skipped when the
    shove found nowhere to go."""
    was = _square_of(c, c.target)
    if c.strike():
        c.hit()
        if c.push(1):
            _step_into_vacated(c, was)


@power(
    "m6007a2",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
)
def m6007a2(c: Cast) -> None:
    """A penalty that only bites when the swing is aimed elsewhere.

    The attack context carries `target`, so "against any creature other than
    m6007" is the gate rather than a flat penalty plus a matching bonus --
    two modifiers of one kind do not add and the pair would have come to the
    wrong number.
    """
    me = c.me
    c.penalty("attack", 5, until=When.EONT, when=lambda ctx: ctx.get("target") != me)


_M6007_FLUBBED = "m6007 misses with an attack or fails a saving throw"


def _i_failed_a_save(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me and not getattr(ev, "saved", True)


@power(
    "m6007a3",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6007_FLUBBED,
    on=(
        Trigger(Miss, by_me, "m6007 misses with an attack"),
        Trigger(SavingThrow, _i_failed_a_save, "m6007 fails a saving throw"),
    ),
    todo=("c.boost_roll()",),
)
def m6007a3(c: Cast) -> None:
    """Both halves add to a roll that has already been made, and neither can
    be said. `c.reroll_attack` and `c.reroll_save` replace the die rather
    than raising it, which is a different number whenever the original was
    good enough once +4 is on it; `c.boost_check` does the right thing and
    only for a skill check. Both triggers are declared so the row goes live
    the day the verb lands."""


def _hit_with_its_blade(world: World, me: int, ev: Event) -> bool:
    """"Hits an enemy with the weapon it swings in a0 and a1."

    Named by ref rather than by the printed weapon: both melee rows swing
    the same thing and nothing else on the block does.
    """
    return getattr(ev, "attacker", None) == me and getattr(ev, "power", "") in (
        "m6007a0",
        "m6007a1",
    )


@power(
    "m6007a4",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="m6007 hits an enemy with the blade it swings in m6007a0 or m6007a1",
    on=Trigger(Hit, _hit_with_its_blade, "m6007 hits an enemy with its blade"),
)
def m6007a4(c: Cast) -> None:
    """Extra damage on the triggering attack, so it is dealt to that event's
    own target rather than to `c.target` -- this row is `NO_TARGET` and the
    default would be nobody."""
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is not None:
        c.damage("1d8", on=victim)


# --------------------------------------------------------------------------
# m6008
# --------------------------------------------------------------------------


@power(
    "m6008a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6008a0(c: Cast) -> None:
    """One square off every shove, and a save against being put down."""
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)
    _shrug_off_prone(c)


@power(
    "m6008a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 1),
)
def m6008a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6008a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 2),
)
def m6008a2(c: Cast) -> None:
    """"5/10" takes the normal range, so the throw stays inside the band
    where it has no penalty."""
    if c.strike():
        c.hit()


@power(
    "m6008a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
)
def m6008a3(c: Cast) -> None:
    """The gift is "next damage roll **against the target**", which is three
    narrowings at once: `once=True` spends it on one roll, the gate reads the
    victim off the damage context, and the clock is the recipient's own next
    turn rather than the leader's. `kind="power"` is the word the card prints
    in front of "bonus"."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    pool = [c.me, *c.within(5, side="ally")]
    who = c.choose(pool, "who takes the opening") or c.me
    c.bonus(
        "damage", 3, on=who, until=When.EOTNT, kind="power", once=True,
        when=lambda ctx: ctx.get("target") == victim,
    )


@power(
    "m6008a4",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ANY_CREATURE,
)
def m6008a4(c: Cast) -> None:
    """"Until the target attacks" is a second clock beside the printed one,
    so the four holds are kept and ended by hand from a watch rather than
    given a duration that cannot express it. `once=True` on the watch so one
    swing spends it and nothing later re-reads it."""
    who = c.target
    if who is None:
        return
    holds = [
        c.bonus(defence, 5, on=who, until=When.EONT)
        for defence in (AC, FORT, REF, WILL)
    ]

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker != who:
            return
        for hold in holds:
            c.end_effect(hold, why=f"{c.ref} spent")

    c.watch(
        AttackDeclared, swung, until=When.EONT, on=who, once=True,
        label=f"{c.ref} ward",
    )


@power(
    "m6008a5",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d8", 5, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m6008a5(c: Cast) -> None:
    """The blessing is for allies standing in the blast, which is a different
    set from the targets, so it is read off the area under `c.first` -- once
    per use, not once per enemy caught."""
    if c.strike():
        c.hit()
    if c.first:
        for friend in c.in_squares(c.area(), side="ally"):
            c.bonus("attack", 2, on=friend, until=When.EONT, kind="power")


@power(
    "m6008a6",
    level=2,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m6008a6(c: Cast) -> None:
    """"2/Encounter" is `uses=2`. `ONE_ALLY`'s pool holds the caster as well,
    which is what "m6008 or one ally" means."""
    c.surge(on=c.target)


@power(
    "m6008a7",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m6008a7(c: Cast) -> None:
    """A monster carries one surge per tier so a line like this has something
    to spend, and takes no second wind of its own; this row is the printed
    sentence saying otherwise. `cost=` is the printed action, not the
    standard action the rule charges a character."""
    c.second_wind(on=c.me, cost=MINOR)


# --------------------------------------------------------------------------
# m6009
# --------------------------------------------------------------------------


@power(
    "m6009a0",
    level=2,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6009a0(c: Cast) -> None:
    """Asked as the attack bonus is totalled rather than armed when it is
    bloodied: nothing announces the line being crossed back the other way,
    and a hold laid on `Bloodied` would outlive a heal."""
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(me),
    )


@power(
    "m6009a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
)
def m6009a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6009a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 5),
)
def m6009a2(c: Cast) -> None:
    """`MoveStart`, not `MoveEnd`: an opportunity attack interrupts the move,
    and by the end of a shift the creature has already arrived. The row is an
    Effect, so the watch is armed whether the swing landed or not."""
    victim = c.target
    if c.strike():
        c.hit()
    if victim is None:
        return

    def shifted(ev: MoveStart) -> None:
        if ev.actor != victim or getattr(ev, "kind_", "") != "shift":
            return
        friends = c.within(1, of=victim, side="ally") or c.allies()
        if not friends:
            return
        chosen = c.choose(friends, "which ally takes the swing") or friends[0]
        c.provoke(chosen, on=victim, why=c.ref)

    c.watch(
        MoveStart, shifted, until=When.SONT, on=c.me, once=True,
        label=f"{c.ref} on {victim}",
    )


@power(
    "m6009a3",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d10", 5, kind=LIMITED),
)
def m6009a3(c: Cast) -> None:
    """`c.grant_attack` rather than `c.basic`: the swing is the ally's, out of
    turn, and `damage_bonus=` is the printed +3 on that one roll."""
    victim = c.target
    if not c.strike():
        return
    c.hit()
    friends = c.within(1, of=victim, side="ally")
    if not friends or victim is None:
        return
    chosen = c.choose(friends, "which ally strikes") or friends[0]
    c.grant_attack(chosen, on=victim, damage_bonus=3)


@power(
    "m6009a4",
    level=2,
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_OTHER_ALLY,
)
def m6009a4(c: Cast) -> None:
    """"The target takes a move action" drops one into the budget the turn is
    already spending. `ONE_OTHER_ALLY`, because the printed line says "one
    ally" and the pool `ONE_ALLY` names holds the caster too."""
    c.extra_action(MOVE, on=c.target)


@power(
    "m6009a5",
    level=2,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m6009a5(c: Cast) -> None:
    c.surge(on=c.target)


@power(
    "m6009a6",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 2, dtype=DamageType.FIRE, kind=LIMITED),
)
def m6009a6(c: Cast) -> None:
    """"Creatures in the blast", not enemies: this one catches its own side
    and `EACH_CREATURE` is the pool that says so."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m6010
# --------------------------------------------------------------------------


@power(
    "m6010a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 5),
)
def m6010a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6010a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 5),
)
def m6010a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6010a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 15),
    target=ONE_CREATURE,
)
def m6010a2(c: Cast) -> None:
    """One row that spends another, so the bonus is laid on the caster first
    and the borrowed row's own `c.hit()` picks it up: the damage lives in
    a0's and a1's headers and writing it again here would freeze the number
    against a later rescale. Which of the two is used follows the reach the
    board allows -- there is no printed rule choosing between them, and
    rolling a melee swing at a target four squares off would be refused."""
    victim = c.target
    if victim is None:
        return
    ref = "m6010a0" if c.adjacent(victim) else "m6010a1"
    c.bonus("damage", 3, on=c.me, until=When.EOT, once=True)
    c.use_power(ref, on=victim, spend=False)


@power(
    "m6010a3",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m6010a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m6010a4",
    level=2,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6010a4(c: Cast) -> None:
    """"Up to its speed", read off the board rather than written down: the
    number is in `game.db` and a literal here would go stale the moment
    anything slowed it."""
    c.shift(c.speed_of(c.me))


@power(
    "m6010a5",
    level=2,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m6010a5(c: Cast) -> None:
    """The cloud is a sight-blocking zone, and the blindness is hung on the
    geometry: `ZoneEntered` and `ZoneExited` are what "until they exit"
    means, and a creature caught at the moment it forms is blinded without
    entering anything. Each hold runs on the zone's own clock, so when the
    cloud goes the blindness goes with it and no cure is needed.

    "Totally obscured" is the dropped half -- a zone blocks sight outright or
    not at all, and there is nothing between the two for concealment to come
    out of. The caster's own immunity is the `!= me` on every branch.
    """
    me = c.me
    cloud = c.zone(c.area(), until=When.EONT, blocks_sight=True,
                   label=f"{c.ref} cloud", obscured="dark")
    held: dict[int, Effect | None] = {}

    def blind(who: int) -> None:
        if who == me or who in held:
            return
        held[who] = c.blinded(on=who, until=When.EONT)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == cloud:
            blind(ev.actor)

    def left(ev: ZoneExited) -> None:
        if ev.zone != cloud:
            return
        hold = held.pop(ev.actor, None)
        if hold is not None:
            c.end_effect(hold, why=f"{c.ref} left behind")

    for caught in c.in_squares(c.area()):
        blind(caught)
    c.watch(ZoneEntered, entered, until=When.EONT, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.EONT, on=me, label=f"{c.ref} out")


def _hit_something_off_guard(world: World, me: int, ev: Event) -> bool:
    """"Hits an enemy granting combat advantage to him."

    Read off the attack's own result rather than asked again: a one-shot
    grant has been spent by the time the blow lands, so `has_combat_advantage`
    answers False exactly when the row should fire.
    """
    if getattr(ev, "attacker", None) != me:
        return False
    result = getattr(ev, "result", None)
    return bool(result is not None and result.advantage)


@power(
    "m6010a6",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
    trigger="m6010 hits an enemy granting combat advantage to him",
    on=Trigger(
        Hit, _hit_something_off_guard, "m6010 hits an enemy granting it advantage"
    ),
)
def m6010a6(c: Cast) -> None:
    """"1/turn" is `once_per_round=True`. The extra damage goes to the
    triggering event's target; this row has none of its own."""
    ev: Any = c.trigger
    victim = getattr(ev, "target", None)
    if victim is not None:
        c.damage("1d6", on=victim)
