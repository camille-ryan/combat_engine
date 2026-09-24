"""Monster abilities, level 8: the soldiers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=15)` and `Damage("2d6", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the seven levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE` and
armed once when the fight starts; a secondary attack is a second attack
line, so its printed bonus is trimmed by hand the way `Attack.bonus_for`
trims the header's; and a helper written for an earlier level is imported
rather than copied.

Four things this file had to settle.

**A charge whose bonus is already printed.** m2815a2 prints +16 where the
creature's ordinary swing is +15, which is the charge bonus already counted
in. So it runs at its victim with `c.run_at` and swings with its own
header, rather than `c.charge_at` -- which would mark the swing as a charge
and have `resolve.attack` add the same point a second time.

**Three turns at printed initiative counts.** `c.extra_turn` splices a
slot, and nothing takes one away, so m2815a5 removes its natural slot and
puts three in its place. The surgery waits for the first `RoundStart`:
`Encounter._arm_traits` walks the initiative order while it arms, and
editing that list underneath the loop skips or repeats other creatures'
traits.

**Its master, and the pack.** `Relation.MASTER_OF` answers "its master" for
m4885 directly. m3092's card names two ids inside a single sentence -- the
quarry is designated as one creature's and replaced by the other's -- so the
quarry is asked of this creature **and** of any m3091 standing with it,
which is the only reading under which every sentence on the card is true at
once.

**A mark punished off `PowerUsed`, not off `AttackDeclared`.** An attack is
announced once per target, so a burst that left the m4918 out would have
read as several attacks, most of which left it out. `PowerUsed` fires once
per use and carries the whole target list, which is the printed question.

**"Its weapon attacks target Reflex instead of AC"** is `AttackDeclared.vs`,
set in the interrupt window before the die is rolled. `resolve.attack` reads
the defence back off the event now, where it used to read the enclosing
parameter -- so this row was left out of the tree until it did. The other
half of the same sentence, "deal fire damage", is not kept: `DamageRolled`
carries a mutable `dtype` and `deal_damage` reads its own local for
resistance and for the announcement, so a listener that sets it changes
nothing. See the report.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_06.brutes import _is_bloodied
from combat_engine.content.monsters.level_06.skirmishers import _fiery_blows, _renew
from combat_engine.content.monsters.level_07.lurkers import _shift_beside
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
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
    OPPORTUNITY,
    PERSONAL,
    REACTION,
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
    Ident,
    Initiative,
    Keyword,
    Melee,
    Mod,
    Position,
    Relation,
    Size,
    Square,
    UpTo,
    Usage,
    When,
    Window,
    World,
    distance,
    footprint,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Budget
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Hit,
    MoveEnd,
    MoveStart,
    PowerUsed,
    RoundStart,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    adjacent,
    allies,
    creatures,
    distance_between,
    squares,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, targets_me

#: The four defences, for a printed "a -2 penalty to all defenses".
EVERY_DEFENCE = (AC, FORT, REF, WILL)

#: What a printed "moves on its turn" covers. A push is not a move the
#: creature made, and `MoveStart.kind_` is the only thing that says which.
UNDER_ITS_OWN_POWER = ("walk", "shift", "teleport", "run")


def _master_of(world: World, eid: int) -> int | None:
    """Whoever this creature serves. `Relation.MASTER_OF` runs master to
    servant, so being owned is having a *source* rather than a target."""
    owners = world.relations.sources(Relation.MASTER_OF, eid)
    return owners[0] if owners else None


def _beside_its_master(world: World, eid: int) -> bool:
    """A printed Requirement of "must be adjacent to its master"."""
    owner = _master_of(world, eid)
    return owner is not None and adjacent(world, eid, owner)


def _free_squares_near(c: Cast, who: int, radius: int) -> list[Square]:
    """Somewhere this creature fits, within `radius` of that one.

    Every square of its own footprint, not just the one its `Position`
    names: `movement.step` refuses the arrival unless the whole footprint is
    clear, so a Large creature offered one free square would have been sent
    to a square it could not stand in and would simply not have moved.
    """
    here = c.world.get(c.me, Position)
    size = here.size if here is not None else Size.MEDIUM
    return sorted(
        sq
        for sq in spread(squares(c.world, who), radius)
        if all(
            c.world.grid.passable(part)
            and c.world.grid.occupant(part) in (None, c.me)
            for part in footprint(sq, size)
        )
    )


def _blink_to(c: Cast, where: Square) -> bool:
    """Teleport to a named square, however far away it is.

    `c.teleport` offers the squares within its distance argument and refuses
    anything outside them, and a printed line that names where it arrives
    names no distance at all. The distance is therefore measured rather than
    guessed.
    """
    here = squares(c.world, c.me)
    if not here:
        return False
    return c.teleport(max(distance(sq, where) for sq in here), to=where)


# ==========================================================================
# m2815
# ==========================================================================


@power(
    "m2815a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
)
def m2815a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2815a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
)
def m2815a1(c: Cast) -> None:
    """Two packets of different types, so the second is rolled here: the
    header carries the printed line that rescales, and lightning that a
    resistance can read cannot ride along inside an untyped one."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.LIGHTNING)


@power(
    "m2815a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d12", 6, kind=LIMITED),
)
def m2815a2(c: Cast) -> None:
    """It runs at its victim and swings with the line printed here.

    `c.run_at` rather than `c.charge_at`: the printed +16 is the +15 of its
    ordinary swing with the charge bonus already counted into it, and
    `charge_at` marks the swing as a charge, which is what makes
    `resolve.attack` add that point -- so the bonus would be paid twice.
    `charge_at` also needs a row to swing with, and the row it would swing
    with is this one.
    """
    victim = c.target
    if victim is None:
        return
    c.run_at(victim)
    if c.strike():
        c.hit()
        c.prone()


_M2815_STRUCK = "the m2815 is hit by a melee attack"


@power(
    "m2815a3",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M2815_STRUCK,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M2815_STRUCK),
)
def m2815a3(c: Cast) -> None:
    """m2815a0 through the row that prints it, so its damage line stays in
    one place. Declared with no target: the row it fires carries its own
    aim, and a row taking one enemy would have had the dispatcher choose."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        use(c.world, c.me, "m2815a0", targets=[foe], spend=False)


@power(
    "m2815a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d10", 7, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m2815a4(c: Cast) -> None:
    """The card prints a burst and no target line, so the burst takes the
    enemies standing in it rather than everybody.

    "Recharge 5 **and** when first bloodied" is two ways back: the number
    stays in the header, because that is what `actions.recharge` rolls and
    what the card shows, and the printed sentence goes on top of it. Armed
    on first use, which is the first moment the row has anything to come
    back from.
    """
    me = c.me
    if c.first:
        _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


#: The counts the card prints. Absolute, not "ten above its own".
_M2815_COUNTS = (20, 15, 5)


@power(
    "m2815a5",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2815a5(c: Cast) -> None:
    """A solo acting three times a round, at the counts the card names.

    `c.extra_turn` splices a slot and nothing takes one away, so its natural
    slot comes out and three go in. The surgery waits for the first
    `RoundStart`: `Encounter._arm_traits` walks the initiative order while
    it arms, and editing that list underneath the loop would skip or repeat
    other creatures' traits. `RoundStart` is emitted after arming and before
    the first turn begins, which is the one moment the order is settled and
    nobody is walking it -- and `index` is 0 there, which is where
    `Encounter.start` expects it when it begins `order[0]`.

    Its own `Initiative.rolled` becomes the highest of the three so that
    anything spliced in later -- a summoned creature, another extra turn --
    sorts against a slot it can see.

    "A standard action instead of the normal allotment" is the move and the
    minor taken off the budget at the top of each of its turns; `_begin`
    refreshes the budget and then announces the turn, so a `TurnStart`
    listener is after the refresh rather than before it.

    Not written: it cannot delay or ready, neither of which the engine has,
    and the immediate action between each pair of turns --
    `Encounter.can_spend` allows one per round, which is the general rule
    and is what this line is an exception to. See the report.
    """
    me = c.me
    done: list[bool] = []

    def splice(_ev: RoundStart) -> None:
        if done:
            return
        done.append(True)
        encounter = c.world.encounter
        if encounter is None or me not in encounter.order:
            return
        init = c.world.get(me, Initiative)
        if init is not None:
            init.rolled = max(_M2815_COUNTS)
        encounter.order.remove(me)
        for at in _M2815_COUNTS:
            c.extra_turn(at)
        encounter.index = 0

    def allotment(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.move = budget.minor = 0

    c.watch(RoundStart, splice, until=When.ENCOUNTER, on=me, label="m2815a5 order")
    c.watch(TurnStart, allotment, until=When.ENCOUNTER, on=me, label="m2815a5")


# ==========================================================================
# m3092
# ==========================================================================


#: The other half of this pair, by id. The card's sentences alternate
#: between the two, and `Ident.ref` is what tells one stat block from
#: another -- `c.is_kind` answers about type words, which both share.
_M3092_HUNTER = "m3091"


def _the_pack(world: World, me: int) -> list[int]:
    """This creature and whichever m3091 is fighting beside it.

    The card designates a quarry as one id's and has the other id replace
    it, inside one sentence, because the pair hunt one creature between
    them. Asked of both, which is the only reading under which every
    sentence on the card is true at once.
    """
    out = [me]
    for mate in allies(world, me):
        ident = world.get(mate, Ident)
        if ident is not None and ident.ref == _M3092_HUNTER:
            out.append(mate)
    return out


def _is_pack_quarry(world: World, me: int, who: int) -> bool:
    return any(
        world.relations.holds(Relation.QUARRY_OF, hunter, who)
        for hunter in _the_pack(world, me)
    )


@power(
    "m3092a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
)
def m3092a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


_M3092_SLIPPED = "the quarry shifts within 5 squares of the m3092"


def _quarry_shifts_near(world: World, me: int, ev: MoveEnd) -> bool:
    return (
        ev.kind_ == "shift"
        and ev.actor != me
        and _is_pack_quarry(world, me, ev.actor)
        and distance_between(world, me, ev.actor) <= 5
    )


@power(
    "m3092a1",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3092_SLIPPED,
    on=Trigger(MoveEnd, when=_quarry_shifts_near, text=_M3092_SLIPPED),
)
def m3092a1(c: Cast) -> None:
    """It closes the distance the quarry just opened, and bites.

    `MoveEnd` rather than `MoveStart`: the printed trigger is a shift that
    has happened, and `MoveEnd` is the only one of the two that says what
    kind of move it was. Declared with no target -- the step is the row's
    own and the bite is m3092a0, which carries its aim.

    "While shifting it can move through enemy-occupied spaces" is not
    written: which squares a step may pass through is the grid's business
    and no `Cast` method reaches it. See the report.
    """
    prey = getattr(c.trigger, "actor", None)
    if prey is None:
        return
    _shift_beside(c, prey, c.speed_of())
    use(c.world, c.me, "m3092a0", targets=[prey], spend=False)


@power(
    "m3092a2",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3092a2(c: Cast) -> None:
    """"Takes a move action" is a move: there is no second thing a move
    action buys that this creature has, so it is written as the walk."""
    c.move(c.speed_of())


@power(
    "m3092a3",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3092a3(c: Cast) -> None:
    """The nearest enemy is named, and the pair's blows tell against it.

    "Until another is designated" is the previous naming ended by hand; the
    label is matched exactly rather than by prefix, because the extra die is
    a watch labelled off the same ref and sweeping it away would take the
    payout with the quarry.

    The extra die is rolled as the blow lands rather than ridden along as a
    damage modifier, and it is armed once for the fight -- the quarry moves,
    the rider does not.
    """
    me, ref = c.me, c.ref
    for eff in list(c.world.effects.live.values()):
        if eff.source == me and eff.label == f"{ref} quarry":
            c.world.effects.end(eff, "another quarry")
    foes = sorted(c.enemies(), key=lambda foe: (c.distance(foe), foe))
    if not foes:
        return
    c.quarry(on=foes[0])

    label = f"{ref} rider"
    if any(eff.label == label for eff in c.world.effects.of(me)):
        return

    def rider(ev: Hit) -> None:
        if ev.attacker in _the_pack(c.world, me) and _is_pack_quarry(
            c.world, me, ev.target
        ):
            c.damage("1d6", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=label)


# ==========================================================================
# m3115
# ==========================================================================


@power(
    "m3115a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 6),
)
def m3115a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3115a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m3115a1(c: Cast) -> None:
    """The hold and the bleeding are one printed effect -- "save ends both"
    -- so they hang on one `c.condition` with its `ongoing`.

    What the thicket drinks is read off the tick: `Effects._on_turn_start`
    deals ongoing damage with the effect itself as the `detail`, which is
    the only thing that tells this burn from any other the victim may be
    carrying. The watch is clocked on the caster and ended with the hold,
    because a watch hung on the victim with a save-ends duration would be a
    second thing for the victim to save against.

    "The fey or plant enemy nearest the target" is nearest from the
    *target's* side of the board, and it is this creature's own side that
    the printed enemy is -- itself included, since it is a plant and is
    often the only one.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.condition(
        Condition.IMMOBILIZED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(5, DamageType.UNTYPED),
    )
    if hold is None:
        return
    tag = f"e{hold.id}["

    def drink(ev: DamageApplied) -> None:
        if ev.target != victim or not ev.detail.startswith(tag) or ev.amount <= 0:
            return
        kin = [
            who
            for who in (c.me, *c.allies())
            if c.is_kind("fey", on=who) or c.is_kind("plant", on=who)
        ]
        if not kin:
            return
        c.heal(
            ev.amount,
            on=min(kin, key=lambda who: (distance_between(c.world, victim, who), who)),
        )

    watcher = c.watch(
        DamageApplied, drink, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} drinks"
    )
    hold.on_end.append(lambda: c.world.effects.end(watcher, "the bleeding stopped"))


@power(
    "m3115a2",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
)
def m3115a2(c: Cast) -> None:
    """No attack roll at all: the whole of it is the hold, so it is applied
    outright.

    One effect with six modifiers on it rather than six effects, because the
    card gives it one saving throw. The further -5 is the effect's own
    `save_mod`, which is exactly "a penalty to saving throws **against this
    effect**" -- the -2 above it is the general one and both are paid.

    The Nature check that lifts the -5 is a skill check, which the engine
    does not have, so it is noted rather than invented.
    """
    victim = c.target
    if victim is None:
        return
    mods = [
        (victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref)),
        (victim, Mod(what="save", value=-2, kind="untyped", label=c.ref)),
    ]
    mods += [
        (victim, Mod(what=d.value, value=-2, kind="untyped", label=c.ref))
        for d in EVERY_DEFENCE
    ]
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref, mods=mods, save_mod=-5
    )
    c.note("m3115a2: a DC 20 Nature check as a minor action lifts the -5 to saves")


# ==========================================================================
# m393
# ==========================================================================


@power(
    "m393a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m393a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and a toll paid for ending a turn
    inside it.

    Not the aura helper, whose hold is carried for as long as its owner is
    standing in it: this one takes nothing away and gives nothing, it bites
    once at a boundary, so membership is measured at that moment.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def bite(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.flat(10, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnEnd, bite, until=When.ENCOUNTER, on=me, label="m393a0")


@power(
    "m393a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m393a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


# ==========================================================================
# m407
# ==========================================================================


@power(
    "m407a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 3),
)
def m407a0(c: Cast) -> None:
    """The printed crit line carries a die of its own.

    `c.damage` already maxes the dice on a critical, which is the ordinary
    rule; "crit 1d6 + 11" is that total with a further die on top, which is
    what a high-crit weapon adds and what has to be rolled here.
    """
    if c.strike():
        c.hit()
        if c.crit:
            c.damage("1d6")


@power(
    "m407a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m407a1(c: Cast) -> None:
    """One creature twice or two creatures once, which is what "two attacks"
    offers and what `UpTo(2)` lets the caller choose between. The row that
    prints the attack is used rather than copied, so its damage line -- and
    its crit die -- stay in one place."""
    if c.target is None:
        return
    for _ in range(2 if len(c.targets) == 1 else 1):
        use(c.world, c.me, "m407a0", targets=[c.target], spend=False)


@power(
    "m407a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m407a2(c: Cast) -> None:
    """The katar first, and the shadows only if it landed.

    `use` reports that a power went off rather than that it hit, so the hit
    that opens the secondary is counted off the bus. The secondary is a
    second roll against a different defence and cannot live in a header, so
    its printed +11 is trimmed by hand the way `Attack.bonus_for` trims the
    header's -- the row still moves with whatever scaling the fight is on.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m407a0":
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=me)
    try:
        use(c.world, me, "m407a0", targets=[victim], spend=False)
    finally:
        c.world.bus.off(sub)
    if victim not in landed:
        return
    if c.attack(c.world.scaling.trim(11, c.level), REF, on=victim):
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)


@power(
    "m407a3",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m407a3(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


# ==========================================================================
# m4885
# ==========================================================================


@power(
    "m4885a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m4885a0(c: Cast) -> None:
    """An Effect line, so the mark is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m4885a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7, kind=LIMITED),
)
def m4885a1(c: Cast) -> None:
    """The printed recharge is its master being hurt rather than a die. The
    number stays in the header, because that is what `actions.recharge`
    rolls and what the card shows; this is the printed sentence on top of
    it, and the two only ever agree to make the row available sooner."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == _master_of(c.world, me))
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m4885a2",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m4885a2(c: Cast) -> None:
    """To its master's side, from wherever it is: the printed line names the
    destination and no distance, so the distance is measured off the
    destination rather than assumed."""
    owner = c.master()
    if owner is None:
        return
    near = _free_squares_near(c, owner, 2)
    if not near:
        return
    _blink_to(c, c.world.decide(c.me, "teleport", near, f"{c.ref}: beside its master"))


_M4885_STRUCK = "the m4885's master takes damage"


def _master_is_struck(world: World, me: int, ev: DamageRolled) -> bool:
    owner = _master_of(world, me)
    return owner is not None and ev.target == owner


@power(
    "m4885a3",
    level=8,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_beside_its_master,
    requires_text="the m4885 must be adjacent to its master",
    trigger=_M4885_STRUCK,
    on=Trigger(DamageRolled, when=_master_is_struck, text=_M4885_STRUCK),
)
def m4885a3(c: Cast) -> None:
    """The whole blow moved onto it, which is what `c.absorb` does and what
    an interrupt is for: the damage is still a proposal in that window.

    Declared with no target -- the creature this is done to is its master,
    and a row taking one enemy would have been aimed at one by the
    dispatcher.
    """
    c.absorb()


# ==========================================================================
# m4918
# ==========================================================================


@power(
    "m4918a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m4918a0(c: Cast) -> None:
    """Three squares from where it started, and its blows catch light.

    Displacement from the square it began the *turn* in, not squares
    covered: the printed line measures from where it stood, so the opening
    square is taken at `TurnStart` and compared at the end of each move it
    makes. Two moves in one turn are therefore one journey, which is what
    the sentence says and what counting steps per move would have missed.

    The payout is a rider on the `Hit` rather than `c.bonus("damage", 5)`,
    which would add to whatever packet is already being dealt and lose the
    fire a resistance reads. Renewed rather than stacked: moving again
    inside the same turn is one hold with a fresh clock, not two riders.
    """
    me = c.me
    began: dict[str, Square | None] = {"at": None}
    held: list[Effect] = []

    def opening(ev: TurnStart) -> None:
        if ev.actor != me:
            return
        here = c.world.get(me, Position)
        began["at"] = here.square if here is not None else None

    def far_enough(ev: MoveEnd) -> None:
        start = began["at"]
        if ev.actor != me or start is None or distance(start, ev.at) < 3:
            return
        _renew(c, held, lambda: _fiery_blows(c, [me], 5, When.EONT))

    c.watch(TurnStart, opening, until=When.ENCOUNTER, on=me, label="m4918a0 from")
    c.watch(MoveEnd, far_enough, until=When.ENCOUNTER, on=me, label="m4918a0")


@power(
    "m4918a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 8),
)
def m4918a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4918a2",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("3d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m4918a2(c: Cast) -> None:
    """"Creatures in the blast" is everything caught, not only enemies."""
    if c.strike():
        c.hit()
        c.mark(until=When.SAVE_ENDS)


_M4918_MOVED = "an enemy marked by the m4918 moves on its turn"


def _marked_moves(world: World, me: int, ev: MoveStart) -> bool:
    """Its own move, on its own turn, from somewhere this one can reach.

    `MoveStart`, which fires before the creature has gone anywhere -- the
    only moment an enemy walking away is still standing within reach of a
    melee 1 swing. `kind_` is what tells a walk from a shove: a push is not
    a move the creature made, and the printed line says the enemy moves.
    """
    return (
        ev.actor != me
        and ev.kind_ in UNDER_ITS_OWN_POWER
        and world.turn == ev.actor
        and world.relations.holds(Relation.MARKED_BY, me, ev.actor)
        and distance_between(world, me, ev.actor) <= 1
    )


@power(
    "m4918a3",
    level=8,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 8),
    trigger=_M4918_MOVED,
    on=Trigger(MoveStart, when=_marked_moves, text=_M4918_MOVED),
)
def m4918a3(c: Cast) -> None:
    if c.target is not None and c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


_M4918_IGNORED = "an enemy marked by the m4918 attacks without including it"


def _marked_looks_away(world: World, me: int, ev: PowerUsed) -> bool:
    """A use of an attack that left this creature out.

    Off `PowerUsed` rather than `AttackDeclared`: an attack is announced
    once per target, so a burst that caught three allies and not the m4918
    would have read as three attacks, all of which left it out, and the
    reaction would have been offered for each. This fires once per use and
    carries the whole target list, which is the printed question.
    """
    p = get(ev.power)
    return (
        ev.actor != me
        and p is not None
        and p.is_attack
        and me not in ev.targets
        and world.relations.holds(Relation.MARKED_BY, me, ev.actor)
        and distance_between(world, me, ev.actor) <= 3
    )


@power(
    "m4918a4",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBlast(3),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE),
    trigger=_M4918_IGNORED,
    on=Trigger(PowerUsed, when=_marked_looks_away, text=_M4918_IGNORED),
)
def m4918a4(c: Cast) -> None:
    """A blast that catches one named creature: the printed target is the
    triggering enemy and nobody else in the cone.

    Declared with no target, so the aim is the event's and only the event's.
    The dispatcher hands a single-enemy row the creature the event names
    *if* that creature is a legal target of the row, and a blast's legal
    targets depend on which way it is pointed -- so on the turns it did not
    match, the row would have been aimed at whoever else was standing in
    front of it.
    """
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)


# ==========================================================================
# m61
# ==========================================================================


@power(
    "m61a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m61a0(c: Cast) -> None:
    """Harder to hit until somebody draws blood.

    An attack modifier is read off the **attacker**, so a -2 on attacks
    against this creature is laid on everybody else and gated on who is
    being swung at. The gate also asks whether it is bloodied yet, at the
    moment the roll is made rather than when the penalty was handed out,
    because that is the moment the printed sentence stops being true.
    """
    me = c.me

    def unproven(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == me and not c.bloodied(me)

    for other in creatures(c.world):
        if other != me:
            c.penalty("attack", 2, on=other, until=When.ENCOUNTER, when=unproven)


@power(
    "m61a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 6),
)
def m61a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m61a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d4", 6),
)
def m61a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m61a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m61a3(c: Cast) -> None:
    """Both blows, through the rows that print them, so their damage lines
    stay in one place. The card names no second target, so both land on the
    one creature this is aimed at."""
    victim = c.target
    if victim is None:
        return
    for ref in ("m61a1", "m61a2"):
        use(c.world, c.me, ref, targets=[victim], spend=False)


@power(
    "m61a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m61a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


def _is_weapon_row(ref: str) -> bool:
    """Was that a weapon attack? Read off the row, which is where the keyword
    lives -- the attack events carry only the ref."""
    row = get(ref) if ref else None
    return row is not None and Keyword.WEAPON in row.keywords


@power(
    "m61a5",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    requires=_is_bloodied,
    requires_text="the m61 must be bloodied",
)
def m61a5(c: Cast) -> None:
    """Which defence a weapon attack goes against, switched for a round.

    `AttackDeclared` is emitted before the die is rolled and `resolve.attack`
    reads `vs` back off it, so the swap is one assignment in the interrupt
    window. It is armed per attack rather than per row because "its weapon
    attacks" is not a named row and the creature has two of them.

    The other half of the printed sentence -- that those attacks deal fire
    damage -- is not kept. `DamageRolled.dtype` is mutable and nothing reads
    it back, so setting it would be a line that looks like it works.
    """
    me = c.me

    def aim(ev: AttackDeclared) -> None:
        if ev.attacker == me and _is_weapon_row(ev.power):
            ev.vs = REF

    c.watch(
        AttackDeclared,
        aim,
        until=When.SONT,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )


# ==========================================================================
# m673
# ==========================================================================


@power(
    "m673a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 6),
)
def m673a0(c: Cast) -> None:
    """A blow, a mark, and a second roll that leaves the victim open.

    The secondary is a second attack line and a row carries one, so its
    printed +10 is trimmed by hand the way `Attack.bonus_for` trims the
    header's. Its four penalties are one effect with one ending, because
    the card gives them one.

    "Or until it dies" needs nothing: `Effects.on_death` ends every
    `When.ENCOUNTER` effect whose source is the creature that fell, on the
    grounds that nothing else is coming to clear it.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.mark(on=victim)
    if not c.attack(c.world.scaling.trim(10, c.level), WILL, on=victim):
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.ENCOUNTER,
        label=f"{c.ref} shaken",
        mods=[
            (victim, Mod(what=d.value, value=-2, kind="untyped", label=c.ref))
            for d in EVERY_DEFENCE
        ],
    )


@power(
    "m673a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m673a1(c: Cast) -> None:
    """"Requires flail" is the weapon keyword: a monster's weapon is its own
    and `Power.can_branch` lets a creature with no `Gear` swing it."""
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)


_M673_BLED = "the m673 is first bloodied"


@power(
    "m673a2",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M673_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M673_BLED),
)
def m673a2(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the
    crossing and nowhere else."""
    c.bonus("damage", 4, until=When.ENCOUNTER, on=c.me)


_M673_HELD = "the m673 suffers an effect that a save can end"


def _caught_by_a_save(world: World, me: int, ev: ConditionApplied) -> bool:
    """`ev.target`, not `ev.actor`: a condition event names its subject
    `target`, and a predicate reading `actor` here is false forever."""
    return ev.target == me and ev.duration == When.SAVE_ENDS.value


@power(
    "m673a3",
    level=8,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M673_HELD,
    on=Trigger(ConditionApplied, when=_caught_by_a_save, text=_M673_HELD),
)
def m673a3(c: Cast) -> None:
    """A save-ends effect arriving is announced as the condition it carries,
    which is the only event that says a hold has been laid on somebody. An
    effect that is nothing but ongoing damage announces no condition and so
    cannot be answered here -- see the report.

    `c.save` takes the first save-ends effect it finds, which is the one
    just applied unless the creature was already carrying another.
    """
    c.save()
