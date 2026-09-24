"""Monster abilities, level 5: the brutes and the soldiers beside them.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=10)` and `Damage("2d8", 7)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

Several rows here are printed under an action heading and are plainly
traits; those are declared `ActionType.NONE` and armed once when the fight
starts. A printed range of "5/10" takes the short range, which is what the
creature can actually shoot without a penalty the engine does not model.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
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
    Defences,
    Defense,
    Effect,
    Event,
    Forced,
    Gear,
    Health,
    Keyword,
    Melee,
    Mod,
    Powers,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Dropped,
    ForcedMove,
    Hit,
    LeaveSquare,
    Miss,
    MoveStart,
    OpportunityWindow,
    PowerUsed,
    RelationCleared,
    RelationSet,
    TurnEnd,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.movement import walk
from combat_engine.engine.query import (
    distance_between,
    enemies,
    has_combat_advantage,
    hidden_from,
    is_,
    moving_as,
    squares,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_keyword,
    by_melee,
    targets_me,
)

#: The reaches that count as a melee attack, for the rows whose rider is on
#: "its melee attacks" rather than on one named row.
MELEE_KINDS = ("melee",)

#: The four defences, for the rows that take a penalty to all of them at once.
DEFENCES = (Defense.AC, Defense.FORT, Defense.REF, Defense.WILL)


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _holding(c: Cast) -> list[int]:
    """Whoever this creature has hold of."""
    return list(c.world.relations.targets(Relation.GRABBED_BY, c.me))


def _has_hold(world: World, eid: int) -> bool:
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def _has_an_opening(world: World, eid: int) -> bool:
    """A printed target of "a creature granting combat advantage to it".

    `requires` is handed the caster and no target, so the nearest thing it
    can say is that there is *somebody* this creature is getting the better
    of. Which one is then the chooser's business, and the body checks the
    one actually aimed at.
    """
    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


def _is_climbing(world: World, eid: int) -> bool:
    """A printed "Requirement: it must be climbing", asked from a header.

    `query.moving_as` is what `c.moving_as` asks, for a `requires=` gate that
    is handed `(world, eid)` and no `Cast`. It reads what the creature is
    *doing*; `Movement.modes` only ever said what it could do, which made a
    gate like this true for anything with a climb speed at all.
    """
    return moving_as(world, eid, "climb")


def _has_shield(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.shield


def _crit_line(c: Cast, dice: str, bonus: int) -> None:
    """A printed "crit NdX + n" line.

    It *replaces* the damage rather than adding to it, and it is a roll --
    so it is applied flat, past the engine's own rule that a critical maxes
    the declared dice, which would read the wrong number off this header.
    """
    if c.crit:
        c.flat(c.roll(dice) + bonus)
    else:
        c.hit()


def _melee_ctx(ctx: dict[str, Any]) -> bool:
    """Is the attack this modifier is being read for a melee one?

    The attack context carries `ranged`; the damage context does not, and a
    gate on a key the context has no entry for is silently false. Both carry
    the row's ref, so the reach is looked up from that instead.
    """
    p = get(ctx.get("power") or "")
    return p is not None and p.reach_of(ctx.get("branch", 0)).kind in MELEE_KINDS


def _defences_down(c: Cast, who: int, amount: int, until: When) -> Effect:
    """A printed "-N to all defences", which is four modifiers on one hold."""
    return c.world.effects.apply(
        who,
        c.me,
        until,
        label=f"{c.ref} defences",
        mods=[
            (who, Mod(what=d.value, value=-amount, kind="untyped", label=c.ref))
            for d in DEFENCES
        ],
    )


def _free_beside(c: Cast, who: int, *, near: int | None = None) -> tuple[int, int] | None:
    """An empty square next to `who`, optionally within a square of `near`.

    "Slide the target to another square adjacent to the m4801" names a
    destination rather than a distance, which is what `to=` is for -- but no
    movement op will pick the square, and an occupied one is simply refused.
    """
    taken = squares(c.world, who)
    for sq in sorted(spread(taken, 1) - taken):
        if not c.world.grid.passable(sq) or c.world.grid.occupant(sq) is not None:
            continue
        if near is not None and not (spread(squares(c.world, near), 1) & {sq}):
            continue
        return sq
    return None


def _recharge_on(c: Cast, event: type[Event], test: Callable[[Any], bool]) -> None:
    """Put this row back up when its printed line says so, not only on a die.

    The database files a plain 6+ where the stat block prints "Recharge when
    ...". The number stays in the header, because that is what
    `actions.recharge` rolls and what the card shows; this is the printed
    sentence on top of it, and the two only ever agree to make the row
    available sooner. Armed from the body, which is all that is needed: the
    row has to have been spent before there is anything to give back.
    """
    ref, me = c.ref, c.me
    label = f"{ref} recharge"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def back(ev: Event) -> None:
        known = c.world.get(me, Powers)
        if known is not None and test(ev):
            known.restore(ref)

    c.watch(event, back, until=When.ENCOUNTER, on=me, label=label)


def _saves_off_prone(c: Cast, who: tuple[int, ...]) -> None:
    """"A saving throw to avoid falling prone when an attack would knock it".

    `Effects.apply` installs everything before it announces, which is what
    makes ending an effect from inside `ConditionApplied` safe -- and
    `Effects.save` is the one that rolls, announces and ends, so the printed
    saving throw is a real one rather than a bare d20.
    """
    me = c.me

    def brace(ev: ConditionApplied) -> None:
        if ev.condition is not Condition.PRONE or ev.target not in who:
            return
        for eff in list(c.world.effects.of(ev.target)):
            if Condition.PRONE in eff.conditions:
                c.world.effects.save(eff)
                return

    c.watch(ConditionApplied, brace, until=When.ENCOUNTER, on=me, label=f"{c.ref} footing")


# ==========================================================================
# Brutes
# ==========================================================================

# -- m100 -------------------------------------------------------------------


@power(
    "m100a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m100a0(c: Cast) -> None:
    """The header keeps the untyped line that rescales; "plus 5 necrotic" is a
    second expression of its own and is dealt in the body, where it keeps its
    type and meets resistance."""
    if c.strike():
        _crit_line(c, "1d8", 11)
        c.flat(5, dtype=DamageType.NECROTIC)


@power(
    "m100a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 3),
)
def m100a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


_M100_BURSTS = "the m100 is first bloodied, and again when it drops to 0 hit points"


@power(
    "m100a2",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC),
    trigger=_M100_BURSTS,
    on=[
        Trigger(Bloodied, when=about_me, text="the m100 is first bloodied"),
        Trigger(Dropped, when=about_me, text="the m100 drops to 0 hit points"),
    ],
)
def m100a2(c: Cast) -> None:
    """Two printed triggers, so two are declared: `on=` takes a sequence and
    the row answers whichever happened. "First bloodied" needs no guard --
    `Bloodied` is emitted on the crossing and nowhere else."""
    if c.strike():
        c.hit()


# -- m103 -------------------------------------------------------------------


@power(
    "m103a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 7),
)
def m103a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m103a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d8", 7, kind=LIMITED),
    requires=_has_an_opening,
    requires_text="the target must be granting combat advantage to the m103",
)
def m103a1(c: Cast) -> None:
    """The printed restriction is per target and `Target` cannot say it, so
    `requires` carries the half about the board and the body checks the one
    actually aimed at.

    The fall and the daze are separate printed durations -- prone lasts until
    the creature stands, the daze until a save -- so they are two effects.
    """
    if c.target is None or not has_combat_advantage(c.world, c.me, c.target):
        return
    if c.strike():
        c.hit()
        c.prone()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m103a2",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m103a2(c: Cast) -> None:
    """Extra dice on the *next* attack, which is not a duration -- so it is
    armed as a watch on the damage roll that spends itself, rather than as
    `c.bonus(once=True)`, which is spent by an attack roll instead. Whether
    the victim is giving itself away is asked as the blow lands, because it
    changes between one swing and the next.
    """
    me = c.me
    armed: list[Effect] = []

    def press(ev: DamageRolled) -> None:
        if ev.source != me or ev.amount <= 0:
            return
        if not has_combat_advantage(c.world, me, ev.target):
            return
        ev.amount += c.roll("1d6")
        if armed:
            c.world.effects.end(armed[0], "spent")

    armed.append(c.watch(DamageRolled, press, until=When.EONT, on=me, label="m103a2"))


# -- m137 -------------------------------------------------------------------


@power(
    "m137a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m137a0(c: Cast) -> None:
    """An aura 2 for the board to draw, with the penalty held per occupant.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are exactly the two moments the hold should go on and
    come off. Whoever is already standing inside is caught at the end --
    making the aura refreshes membership before its id exists for a listener
    to recognise.
    """
    held: dict[int, Effect] = {}
    ring = c.aura(2, until=When.ENCOUNTER)

    def cow(who: int) -> None:
        if who in held or who not in c.enemies():
            return
        held[who] = _defences_down(c, who, 2, When.ENCOUNTER)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            cow(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label="m137a0 in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label="m137a0 out")
    for actor in c.world.zones.occupants(ring):
        cow(actor)


@power(
    "m137a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m137a1(c: Cast) -> None:
    """The secondary attack is a second roll against a different defence, so
    it cannot live in the header; its printed +8 is trimmed by hand the way
    `Attack.bonus_for` trims the header's, or the row would ignore whatever
    scaling the fight is being played on."""
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(8, c.level), FORT):
        c.damage("1d6", 2, dtype=DamageType.POISON)
        c.ongoing(5, DamageType.POISON)


# -- m217 -------------------------------------------------------------------


@power(
    "m217a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m217a0(c: Cast) -> None:
    """Folding into a small space costs this creature nothing.

    Half speed, the -5 to attacks and the combat advantage it hands out are
    the *whole* of what `Condition.SQUEEZING` is, and the printed line waives
    all three -- so the hold is taken off as it lands rather than three
    separate counterweights being written against it.
    """
    me, ref = c.me, c.ref

    def unsqueeze(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.SQUEEZING:
            return
        for eff in list(c.world.effects.of(me)):
            if Condition.SQUEEZING in eff.conditions:
                c.world.effects.end(eff, ref)

    c.watch(ConditionApplied, unsqueeze, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m217a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m217a1(c: Cast) -> None:
    """Unseen until it does something about it.

    `c.hide` is the right half of the pair: being invisible runs out on a
    clock, being hidden lasts until you give yourself away -- and
    `resolve.attack` clears it for whoever swung, which is the printed "or
    until it attacks". The Perception DC is a skill check the engine has no
    model of, and so is not tested.

    Not written: the creature that fails to notice it and walks into it,
    which is an automatic hit with m217a3. The grid refuses an occupied
    square to anybody, seen or not, so there is no such walk to answer. See
    the report.
    """
    c.hide(until=When.ENCOUNTER)


@power(
    "m217a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d6", 9, dtype=DamageType.ACID),
)
def m217a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


def _room_to_grab(world: World, eid: int) -> bool:
    return len(world.relations.targets(Relation.GRABBED_BY, eid)) <= 2


@power(
    "m217a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=8),
    requires=_room_to_grab,
    requires_text="the m217 must have no more than two creatures grabbed",
)
def m217a3(c: Cast) -> None:
    """No damage on the hit: the hold, the burning and the daze are the row.

    The step into its space comes *before* the grab, and has to: a grabbed
    creature cannot move, so the only way to put one inside the ooze is to
    put it there while it still can. `share=True` is what lets anything stand
    in an occupied square at all.

    The burning and the daze end with the grab rather than with a clock or a
    save, which is what "until the grab ends" means, so they are hung on the
    grab's own ending.

    Not written: the clause that drags whatever it holds along when it moves.
    Forced movement has no `share`, and a grabbed creature cannot shift, so
    there is no way to move one into the square the ooze has just left. See
    the report.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.shift(who=victim, to=c.here, share=True)
    hold = c.grab(on=victim)
    bite = c.condition(
        Condition.DAZED,
        until=When.ENCOUNTER,
        on=victim,
        ongoing=(10, DamageType.ACID),
    )
    if hold is not None and bite is not None:
        hold.on_end.append(lambda: c.world.effects.end(bite, "the grab ended"))
    c.no_provoke(from_=victim, until=When.ENCOUNTER)


# -- m2972 ------------------------------------------------------------------


@power(
    "m2972a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2972a0(c: Cast) -> None:
    """Who is crowding the victim changes every time anything moves, so the
    gate is read at the moment the damage is rolled rather than stored. The
    caster is left out of the count: the printed line is about its allies."""
    me = c.me

    def mobbed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        return sum(1 for a in c.within(1, of=who, side="ally") if a != me) >= 2

    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=mobbed)


@power(
    "m2972a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 9),
)
def m2972a1(c: Cast) -> None:
    """Bloodied swaps the expression rather than adding to it, so the header
    keeps the printed line that rescales and the larger one is rolled here."""
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("2d6", 11)
    else:
        c.hit()


_M2972_DOWN = "the m2972 first drops to 0 hit points"


@power(
    "m2972a2",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M2972_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M2972_DOWN),
)
def m2972a2(c: Cast) -> None:
    """Back on its feet for one turn, and then down for good.

    Declared with no target at all rather than with itself: `use` skips a
    target that is not alive, and this row exists precisely for a creature
    that is not.

    "Resist 15 to all damage" is not resistance as the engine holds it --
    that is per damage type, and this is everything -- so it is taken off the
    damage roll, which is the one place a rule about *this* blow can reach.
    The hold is ended by hand before the last blow lands, or the creature
    would resist its own collapse.

    "The end of its next turn" is the first end of a turn of its own after
    now -- unless it is having one, in which case that one does not count.
    A `When.EONT` duration would have expired at the same moment the listener
    was waiting for, which is not something to rely on.

    Not written: the action point. Nothing in the engine has one. See the
    report.
    """
    me = c.me
    c.heal(5, on=me)

    def shrug(ev: DamageRolled) -> None:
        if ev.target == me and ev.amount > 0:
            ev.amount = max(0, ev.amount - 15)

    tough = c.watch(DamageRolled, shrug, until=When.ENCOUNTER, on=me, label="m2972a2")
    holder: list[Effect] = []
    skip = [1 if c.world.turn == me else 0]

    def collapse(ev: TurnEnd) -> None:
        if ev.actor != me or ev.ghost:
            return
        if skip[0]:
            skip[0] = 0
            return
        c.world.effects.end(tough, "the reprieve is over")
        if holder:
            c.world.effects.end(holder[0], "spent")
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    holder.append(
        c.watch(TurnEnd, collapse, until=When.ENCOUNTER, on=me, label="m2972a2 end")
    )


# -- m3026 ------------------------------------------------------------------


@power(
    "m3026a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 4),
)
def m3026a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means."""
    if c.strike():
        c.hit()


@power(
    "m3026a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3026a1(c: Cast) -> None:
    """m3026a0 twice, through the row that prints it, so its damage line stays
    in one place. `use` reports that a power went off rather than that it hit,
    so the two hits are counted off the bus -- which is also the only way to
    tell them from anything else swinging in the same window.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m3026a0":
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=me)
    try:
        for _ in range(2):
            use(c.world, me, "m3026a0", targets=[victim], spend=False)
    finally:
        c.world.bus.off(sub)
    if landed.count(victim) == 2:
        c.grab(on=victim)


@power(
    "m3026a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    damage=Damage("2d6", 8),
    requires=_has_hold,
    requires_text="the m3026 must have a creature grabbed",
)
def m3026a2(c: Cast) -> None:
    """No attack roll at all -- the printed target is the creature in its
    jaws, which no `Target` can say, so the header takes one enemy and the
    body aims at whoever is actually being held."""
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is not None:
        c.hit(on=victim)


@power(
    "m3026a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=8),
)
def m3026a3(c: Cast) -> None:
    """No damage: the penalty is the whole row."""
    if c.strike():
        c.penalty("attack", 2, until=When.SAVE_ENDS)


# -- m381 -------------------------------------------------------------------


@power(
    "m381a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m381a0(c: Cast) -> None:
    """A bonus held by whoever is in the saddle, and only while the mount bleeds.

    A modifier lives on a creature, and which creature that is changes when
    somebody mounts or falls off -- so the hold follows `RIDDEN_BY` being set
    and cleared rather than being handed out once. Being bloodied is asked
    inside the gate for the same reason: hit points cross back and forth.

    The gate reads the reach off the row rather than the attack context's
    `ranged`, because the damage context does not carry that key and a gate
    on a key the context has no entry for is silently false.
    """
    me = c.me
    held: dict[int, list[Effect]] = {}

    def gate(ctx: dict[str, Any]) -> bool:
        return c.bloodied(me) and _melee_ctx(ctx)

    def mount_up(who: int) -> None:
        if who in held:
            return
        held[who] = [
            eff
            for eff in (
                c.bonus("attack", 2, until=When.ENCOUNTER, on=who, when=gate),
                c.bonus("damage", 2, until=When.ENCOUNTER, on=who, when=gate),
            )
            if eff is not None
        ]

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == me:
            mount_up(ev.target)

    def dismounted(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.RIDDEN_BY or ev.source != me:
            return
        for eff in held.pop(ev.target, []):
            c.world.effects.end(eff, "dismounted")

    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=me, label="m381a0 on")
    c.watch(RelationCleared, dismounted, until=When.ENCOUNTER, on=me, label="m381a0 off")
    rider = c.rider()
    if rider is not None:
        mount_up(rider)


@power(
    "m381a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 5),
)
def m381a1(c: Cast) -> None:
    """Bloodied is worth two points on the roll and two on the damage, and the
    damage is a second expression rather than a bonus -- so the header keeps
    the printed line that rescales and the larger one is rolled here."""
    hurt = c.bloodied(c.me)
    if not c.strike(plus=2 if hurt else 0):
        return
    if hurt:
        c.damage("2d10", 7)
    else:
        c.hit()


def _run_in(c: Cast) -> int | None:
    """Pick somebody to charge and close on them. Returns who, or nobody.

    An adjacent enemy costs no ground and is taken first; otherwise it is the
    shortest walk that ends beside one, which is what a charge is. The move
    is spent as well as the standard, because a charge takes both.
    """
    paths = c.world.reachable_paths(c.me, c.speed_of())
    best: tuple[int, list[tuple[int, int]], int] | None = None
    for foe in sorted(c.enemies()):
        if c.adjacent(foe):
            return foe
        beside = spread(squares(c.world, foe), 1)
        run = min(
            ((len(p), p, foe) for dest, p in paths.items() if dest in beside and p),
            default=None,
        )
        if run is not None and (best is None or run[0] < best[0]):
            best = run
    if best is None:
        return None
    walk(c.world, c.me, list(best[1]))
    if c.world.encounter is not None:
        c.world.encounter.spend(c.me, ActionType.MOVE)
    return best[2]


@power(
    "m381a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m381a2(c: Cast) -> None:
    """The row is the charge, not a rider on one.

    The engine's charge action swings whatever `Powers.basic` points at, and
    this stat block's basic is m381a1 -- so a row that only replaced the
    swing could never be reached at all. It therefore runs in itself, and
    declares no target to do it: a melee row with one would be refused for
    reach before the body ever got to close the distance, which is the whole
    of what a charge is for.

    `c.charge` is the flag `use(charge=True)` would have set, and setting it
    is what puts the printed +1 on the roll, the `charge` on every attack
    event, and the key in both modifier contexts where a rider can read it --
    m381a0's is one of those.
    """
    victim = _run_in(c)
    if victim is None:
        return
    c.charge = True
    hurt = c.bloodied(c.me)
    for _ in range(2):
        if c.strike(on=victim, plus=2 if hurt else 0):
            if hurt:
                c.damage("1d6", 6, on=victim)
            else:
                c.hit(on=victim)


# -- m4709 ------------------------------------------------------------------


@power(
    "m4709a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4709a0(c: Cast) -> None:
    """Not `c.no_provoke`, which waives the window outright: the printed line
    waives it only while the creature is on a wall, so the opening is refused
    as it opens and only then."""
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        if ev.provoker == me and c.moving_as("climb"):
            ev.cancel(c.ref)

    c.watch(
        OpportunityWindow,
        veto,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m4709a0",
    )


@power(
    "m4709a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 5),
)
def m4709a1(c: Cast) -> None:
    """The printed line is unqualified, so the opening is granted to this
    creature's whole side rather than to itself alone."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "m4709a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
    damage=Damage("3d10", 8, kind=LIMITED),
)
def m4709a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.prone()


@power(
    "m4709a3",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m4709a3(c: Cast) -> None:
    """Only the beasts among them, which is a type word and so is sayable --
    `c.is_kind` reads the stat block's own type line."""
    if c.target is not None and c.is_kind("beast", c.target):
        c.bonus("attack", 2, until=When.EONT, on=c.target)


# -- m4791 ------------------------------------------------------------------


@power(
    "m4791a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage(bonus=6, kind=MINION),
)
def m4791a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4791a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage(bonus=8, kind=MINION),
)
def m4791a1(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()


@power(
    "m4791a2",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_climbing,
    requires_text="the m4791 must be climbing",
)
def m4791a2(c: Cast) -> None:
    """It lets go of the wall, so the flight is granted for the move and taken
    back when the turn ends: `mode_of` picks flight over a walk when the
    creature has it, which is what makes `c.move` a flight rather than a
    scramble."""
    c.mode("fly", 5, until=When.EOT)
    c.move(5)


_M4791_DOWN = "the m4791 drops to 0 hit points"


@power(
    "m4791a3",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M4791_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M4791_DOWN),
)
def m4791a3(c: Cast) -> None:
    """A death spasm with no attack roll: everyone next to it is simply worse
    off, on the *enemy's* clock rather than the m4791's, which is what the
    card prints -- and it has no next turn to measure anything against."""
    if c.target is not None:
        _defences_down(c, c.target, 2, When.EOTNT)


# -- m4792 ------------------------------------------------------------------


@power(
    "m4792a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d4", 5),
)
def m4792a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4792a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d4", 5),
)
def m4792a1(c: Cast) -> None:
    """Range 5/10: the header carries the short range."""
    if c.strike():
        c.hit()


@power(
    "m4792a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 3),
)
def m4792a2(c: Cast) -> None:
    """One row, four swings: the Effect line says the attack below is made
    four times, so the declared line is rolled four times rather than the row
    being used four times."""
    for _ in range(4):
        if c.strike():
            c.hit()


@power(
    "m4792a3",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_climbing,
    requires_text="the m4792 must be climbing",
)
def m4792a3(c: Cast) -> None:
    """The flight is granted for the move and taken back at the end of the
    turn, so `mode_of` reads it while `c.move` is running and not after."""
    c.mode("fly", 5, until=When.EOT)
    c.move(5)


# -- m4850 ------------------------------------------------------------------


@power(
    "m4850a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m4850a0(c: Cast) -> None:
    """An aura 1 for the board to draw, biting at the end of a turn rather
    than the start of one -- `c.hazard` does both ends and entry besides,
    which this line does not."""
    c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def reek(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.flat(3, dtype=DamageType.POISON, on=ev.actor)

    c.watch(TurnEnd, reek, until=When.ENCOUNTER, on=me, label="m4850a0")


@power(
    "m4850a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", dtype=DamageType.FIRE),
)
def m4850a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m4850a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8"),
)
def m4850a2(c: Cast) -> None:
    """Resistance is held per damage type on the creature, so losing it is
    the entry being lifted out and put back when the hold runs out -- the way
    `c.mode` lifts a movement mode."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    defences = c.world.get(victim, Defences) if victim is not None else None
    if defences is None:
        return
    had = defences.resist.pop(DamageType.FIRE, None)
    if had is None:
        return
    def restore() -> None:
        defences.resist[DamageType.FIRE] = had

    hold = c.effect(f"{c.ref} no fire resistance", until=When.EONT, on=victim)
    if hold is None:
        restore()
        return
    hold.on_end.append(restore)


@power(
    "m4850a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_is_bloodied,
    requires_text="the m4850 must be bloodied",
)
def m4850a3(c: Cast) -> None:
    """Both rows through the ones that print them, so their damage lines stay
    in one place. Each may pick its own victim; pointed at one creature, that
    creature takes both, which is the same two attacks either way."""
    if c.target is None:
        return
    use(c.world, c.me, "m4850a1", targets=[c.target], spend=False)
    use(c.world, c.me, "m4850a2", targets=[c.target], spend=False)


_M4850_SCORCHED = "the m4850 is hit by a fire attack"


@power(
    "m4850a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M4850_SCORCHED,
    on=Trigger(Hit, when=both(targets_me, by_keyword(Keyword.FIRE)), text=_M4850_SCORCHED),
)
def m4850a4(c: Cast) -> None:
    """Everyone in the aura m4850a0 draws, which is a radius of one."""
    for foe in c.within(1, side="enemy"):
        c.flat(5, dtype=DamageType.FIRE, on=foe)


# -- m4915 ------------------------------------------------------------------


@power(
    "m4915a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage(bonus=6, kind=MINION),
)
def m4915a0(c: Cast) -> None:
    """Standing beside a friend swaps the number rather than adding to it, so
    the header keeps the printed one and the larger is dealt here."""
    if not c.strike():
        return
    if any(a != c.me for a in c.within(1, side="ally")):
        c.damage(0, 10)
    else:
        c.hit()


@power(
    "m4915a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=8),
)
def m4915a1(c: Cast) -> None:
    """No damage on the hit -- the burning is the whole row."""
    if c.strike():
        c.ongoing(5, DamageType.FIRE)


# ==========================================================================
# Soldiers
# ==========================================================================

# -- m157 -------------------------------------------------------------------


@power(
    "m157a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 9),
)
def m157a0(c: Cast) -> None:
    """Bloodied is one point on the roll and nothing on the damage, so it is a
    modifier to this swing rather than a second expression."""
    if c.strike(plus=1 if c.bloodied(c.me) else 0):
        c.hit()


@power(
    "m157a1",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m157a1(c: Cast) -> None:
    """"Creatures in the blast" is everything caught, not only enemies."""
    if c.strike():
        c.hit()


_M157_SLIPPED = "an enemy leaves a square adjacent to the m157"


def _neighbour_leaves(world: World, me: int, ev: LeaveSquare) -> bool:
    """The square being vacated, while its owner is still standing in it.

    `LeaveSquare` rather than `AdjacencyLost`: adjacency is diffed after the
    mover has arrived, so by then the enemy is out of reach and the interrupt
    this row is could not swing at it. This one is announced first, which is
    also the printed order. "Leaves a square adjacent" catches a shift as
    well as a walk, which is why it is not the opportunity window either.
    """
    return (
        ev.actor != me
        and ev.actor in enemies(world, me)
        and ev.square in spread(squares(world, me), 1)
    )


@power(
    "m157a2",
    level=5,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    trigger=_M157_SLIPPED,
    on=Trigger(LeaveSquare, when=_neighbour_leaves, text=_M157_SLIPPED),
)
def m157a2(c: Cast) -> None:
    """m157a0 through the row that prints it, so its damage line stays in one
    place."""
    who = getattr(c.trigger, "actor", None) or c.target
    if who is not None:
        use(c.world, c.me, "m157a0", targets=[who], spend=False)


_M157_MISSED = "the m157 misses an enemy with m157a0"


def _missed_with_blade(world: World, me: int, ev: Miss) -> bool:
    return ev.attacker == me and ev.power == "m157a0"


@power(
    "m157a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M157_MISSED,
    on=Trigger(Miss, when=_missed_with_blade, text=_M157_MISSED),
)
def m157a3(c: Cast) -> None:
    """A second swing at whoever it just missed, and the printed recharge on
    top of the die the database files for it.

    The dispatcher aims a triggered row at whoever caused the event, and here
    that is the m157 itself -- so the row declares no target and reads the
    one that was missed off the trigger.
    """
    _recharge_on(c, PowerUsed, lambda ev: ev.actor == c.me and ev.power == "m157a2")
    who = getattr(c.trigger, "target", None)
    if who is not None:
        use(c.world, c.me, "m157a0", targets=[who], spend=False)


# -- m169 -------------------------------------------------------------------


@power(
    "m169a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m169a0(c: Cast) -> None:
    """A held modifier rather than a watcher, because it applies to shoves
    from anywhere -- `forced` reads it off the target before it steps."""
    c.resist_forced(1)


@power(
    "m169a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m169a1(c: Cast) -> None:
    _saves_off_prone(c, (c.me,))


@power(
    "m169a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 3),
)
def m169a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m169a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 5),
)
def m169a3(c: Cast) -> None:
    """Range 5/10: the header carries the short range."""
    if c.strike():
        c.hit()


@power(
    "m169a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d6", 5, kind=LIMITED),
    requires=_has_shield,
    requires_text="the m169 must be wielding a shield",
)
def m169a4(c: Cast) -> None:
    """"Either ... or" is a real choice and has to be offered as one."""
    if not c.strike():
        return
    c.hit()
    if c.choose(["knock it prone", "push it 1 square"], "m169a4") == "knock it prone":
        c.prone()
    else:
        c.push(1)


_M169_SHOVED = "an enemy tries to push the m169 or knock it prone"


def _shoved_at_me(world: World, me: int, ev: ForcedMove) -> bool:
    return ev.target == me and ev.how is Forced.PUSH and ev.source in enemies(world, me)


def _floored_by_enemy(world: World, me: int, ev: ConditionApplied) -> bool:
    return (
        ev.target == me
        and ev.condition is Condition.PRONE
        and ev.source in enemies(world, me)
    )


@power(
    "m169a5",
    level=5,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M169_SHOVED,
    on=[
        Trigger(ForcedMove, when=_shoved_at_me, text="an enemy tries to push the m169"),
        Trigger(ConditionApplied, when=_floored_by_enemy, text="or knock it prone"),
    ],
)
def m169a5(c: Cast) -> None:
    """Two printed triggers and two events: being shoved is a `ForcedMove` and
    being knocked down is a `ConditionApplied`, so both are declared rather
    than half the sentence.

    Neither event names its cause `attacker` or `actor`, so the dispatcher
    cannot aim the row and the enemy is read off the trigger here. Both name
    it `source`, which is also why `about_me` would be silently false on
    either -- it reads `ev.actor` and only that.
    """
    who = getattr(c.trigger, "source", None)
    if who is not None:
        c.basic(on=who)


# -- m247 -------------------------------------------------------------------

#: What m247a0 offers a saving throw against.
_M247_HELD = (Condition.IMMOBILIZED, Condition.STUNNED)

#: The printed target of m247a2: a creature already off its feet.
_M247_PINNED = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)


@power(
    "m247a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m247a0(c: Cast) -> None:
    """Light loosens its grip: one creature, one save, off the damage it took.

    `DamageApplied` rather than `DamageRolled` -- the printed line pays out
    on damage actually taken, and a blow a resistance swallowed entirely is
    not that. `c.suffering` is what asks which creatures are carrying
    something this one applied.
    """
    me = c.me

    def slacken(ev: DamageApplied) -> None:
        if ev.target != me or ev.dtype is not DamageType.RADIANT or ev.amount <= 0:
            return
        for victim in c.suffering(by=me):
            for eff in list(c.world.effects.of(victim)):
                if eff.source == me and any(cond in _M247_HELD for cond in eff.conditions):
                    c.world.effects.save(eff)
                    return

    c.watch(DamageApplied, slacken, until=When.ENCOUNTER, on=me, label="m247a0")


@power(
    "m247a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m247a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


def _somebody_pinned(world: World, eid: int) -> bool:
    return any(
        any(is_(world, foe, cond) for cond in _M247_PINNED) for foe in enemies(world, eid)
    )


@power(
    "m247a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("4d6", 6),
    requires=_somebody_pinned,
    requires_text="the target must be immobilized, restrained, stunned or unconscious",
)
def m247a2(c: Cast) -> None:
    """The printed restriction is per target and `Target` cannot say it, so
    `requires` carries the half about the board and the body checks the one
    actually aimed at."""
    if not any(c.is_(cond) for cond in _M247_PINNED):
        return
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


# -- m274 -------------------------------------------------------------------


@power(
    "m274a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m274a0(c: Cast) -> None:
    """Its allies' bonus is against *that* enemy, so it is a gated modifier
    rather than a flat one: the gate reads the target out of whichever
    context is asking, and both the attack and the damage context carry it."""
    me = c.me

    def rally(ev: Hit) -> None:
        if ev.attacker != me or not by_melee(c.world, me, ev):
            return
        victim = ev.target
        for friend in c.allies():
            for what in ("attack", "damage"):
                c.bonus(
                    what,
                    2,
                    until=When.EONT,
                    on=friend,
                    when=lambda ctx, v=victim: ctx.get("target") == v,
                )

    c.watch(Hit, rally, until=When.ENCOUNTER, on=me, label="m274a0")


@power(
    "m274a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m274a1(c: Cast) -> None:
    """An Effect line, so the mark is laid on a miss too."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m274a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m274a2(c: Cast) -> None:
    """"Allies in the burst" leaves the caster out, and the `ally` pool puts
    it in -- so it is dropped here."""
    if c.target is not None and c.target != c.me:
        c.shift(3, who=c.target)


_M274_GRIPPED = "the m274 is subject to an effect that a save can end"


def _save_ends_on_me(world: World, me: int, ev: ConditionApplied) -> bool:
    return ev.target == me and ev.duration == When.SAVE_ENDS.value


@power(
    "m274a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M274_GRIPPED,
    on=Trigger(ConditionApplied, when=_save_ends_on_me, text=_M274_GRIPPED),
)
def m274a3(c: Cast) -> None:
    """`ConditionApplied` names its subject `target`, so `targets_me` is the
    predicate and `about_me` would be silently false.

    It is also the narrower half of the printed line: a save-ends effect that
    carries only ongoing damage announces no condition and so cannot be
    answered. See the report.
    """
    c.save()


# -- m2928 ------------------------------------------------------------------


@power(
    "m2928a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8"),
)
def m2928a0(c: Cast) -> None:
    """"Plus 1d6 fire" is a second expression of its own, so the header keeps
    the untyped line that rescales and the fire is rolled in the body."""
    if not c.strike():
        return
    c.hit()
    c.damage("1d6", dtype=DamageType.FIRE)
    c.vulnerable(5, DamageType.FIRE, until=When.EONT)
    c.mark()


@power(
    "m2928a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m2928a1(c: Cast) -> None:
    """Range 5/10: the header carries the short range."""
    if c.strike():
        c.hit()


_M2928_SLIPPED = "an enemy within 2 squares of the m2928 shifts"


def _enemy_shifts_near(world: World, me: int, ev: MoveStart) -> bool:
    who = ev.actor
    if ev.kind_ != "shift" or who == me or who not in enemies(world, me):
        return False
    return distance_between(world, me, who) <= 2


@power(
    "m2928a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.THUNDER],
    trigger=_M2928_SLIPPED,
    on=Trigger(MoveStart, when=_enemy_shifts_near, text=_M2928_SLIPPED),
)
def m2928a2(c: Cast) -> None:
    """m2928a0 through the row that prints it, so its damage line stays in one
    place -- and `use` reports that a power went off rather than that it hit,
    so the hit that opens the secondary attack is counted off the bus.

    The secondary is a second roll against a different defence and cannot
    live in a header; its printed +10 is trimmed by hand the way
    `Attack.bonus_for` trims the header's.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m2928a0":
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=me)
    try:
        use(c.world, me, "m2928a0", targets=[victim], spend=False)
    finally:
        c.world.bus.off(sub)
    if victim not in landed:
        return
    if c.attack(c.world.scaling.trim(10, c.level), FORT, on=victim):
        c.flat(5, dtype=DamageType.THUNDER, on=victim)
        c.stunned(until=When.SAVE_ENDS, on=victim)


# -- m4801 ------------------------------------------------------------------


@power(
    "m4801a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4801a0(c: Cast) -> None:
    """An aura 3, and inside it its friends press an advantage.

    The modifier is held by each ally rather than by the caster -- it is
    their attack roll -- so membership is diffed off the zone, and whether
    the creature being swung at is bloodied is asked at the moment of the
    roll, since that changes with every blow.
    """
    held: dict[int, Effect] = {}
    ring = c.aura(3, until=When.ENCOUNTER)

    def press(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.bloodied(who)

    def urge(who: int) -> None:
        if who in held or who == c.me or who not in c.allies():
            return
        effect = c.bonus("attack", 2, until=When.ENCOUNTER, on=who, when=press)
        if effect is not None:
            held[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            urge(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label="m4801a0 in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label="m4801a0 out")
    for actor in c.world.zones.occupants(ring):
        urge(actor)


@power(
    "m4801a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4801a1(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m4801a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m4801a2(c: Cast) -> None:
    """"To another square adjacent to the m4801" names a destination rather
    than a distance, which is what `to=` is for -- and the square has to be
    one the target could reach in a single step, or the slide is not one."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    dest = _free_beside(c, c.me, near=victim)
    if dest is not None:
        c.slide(1, to=dest)


@power(
    "m4801a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4801a3(c: Cast) -> None:
    """m4801a2 against each of them, through the row that prints it.

    Whether the target actually moved is read off its square before and
    after: the slide can fail for want of anywhere to go, and the free swing
    it buys is printed as conditional on it having happened.
    """
    victim = c.target
    if victim is None:
        return
    before = squares(c.world, victim)
    use(c.world, c.me, "m4801a2", targets=[victim], spend=False)
    if squares(c.world, victim) == before:
        return
    beside = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
    if beside:
        c.grant_attack(beside[0], on=victim)


@power(
    "m4801a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=10),
)
def m4801a4(c: Cast) -> None:
    """No damage: the haul and the mark are the whole row."""
    if c.strike():
        c.pull(3)
        c.mark()


_M4801_BLED = "the m4801 is first bloodied"


@power(
    "m4801a5",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    trigger=_M4801_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M4801_BLED),
)
def m4801a5(c: Cast) -> None:
    """Its friends close ranks and swing.

    The destination is named rather than left to the decider: "must end the
    shift closer than it began" is a restriction on where, not a distance, so
    the reachable squares are filtered to the ones that are nearer and the
    nearest of those is taken. The swing is a basic attack at whatever is
    within reach afterwards, which is what a free melee basic can hit.
    """
    me = c.me
    mine = squares(c.world, me)
    for friend in c.within(5, side="ally"):
        if friend == me:
            continue
        was = distance_between(c.world, friend, me)
        nearer = sorted(
            sq
            for sq in c.world.reachable_squares(friend, 4)
            if min(distance(sq, s) for s in mine) < was
        )
        if nearer:
            c.shift(who=friend, to=nearer[0])
        foes = c.within(1, of=friend, side="enemy")
        if foes:
            c.grant_attack(friend, on=foes[0])


# -- m4993 ------------------------------------------------------------------


@power(
    "m4993a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4993a0(c: Cast) -> None:
    """A Stealth check penalty the engine does not levy, so there is nothing
    to waive. Declared inert rather than given an invented mechanic."""
    c.note("m4993a0: takes no Stealth penalty for moving quickly or running")


@power(
    "m4993a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m4993a1(c: Cast) -> None:
    """Attacking gives you away -- `resolve.attack` clears the concealment for
    whoever swung -- so a row that keeps its own hides again afterwards, and
    only if it had it to begin with. The mark is an Effect line and is laid
    on a miss too."""
    victim = c.target
    was_unseen = victim is not None and c.is_hidden(from_=victim)
    if c.strike():
        c.hit()
        if was_unseen:
            c.hide(from_=victim, until=When.ENCOUNTER)
    c.mark()


def _cannot_be_seen(world: World, eid: int) -> bool:
    if hidden_from(world, eid):
        return True
    return any(is_(world, foe, Condition.BLINDED) for foe in enemies(world, eid))


@power(
    "m4993a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 6, kind=LIMITED),
    requires=_cannot_be_seen,
    requires_text="the target must not be able to see the m4993",
)
def m4993a2(c: Cast) -> None:
    """Unable to see it means one of two things -- the m4993 is hidden from
    it, or it cannot see at all -- and both are asked of the target actually
    aimed at, since `requires` is handed none."""
    victim = c.target
    if victim is None:
        return
    if not (c.is_hidden(from_=victim) or c.is_(Condition.BLINDED, on=victim)):
        return
    if c.strike():
        c.hit()
        c.ongoing(5)
    c.mark()


_M4993_SLIPPED = "an enemy marked by the m4993 shifts"


def _marked_enemy_shifts(world: World, me: int, ev: MoveStart) -> bool:
    return (
        ev.kind_ == "shift"
        and ev.actor != me
        and world.relations.holds(Relation.MARKED_BY, me, ev.actor)
    )


@power(
    "m4993a3",
    level=5,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M4993_SLIPPED,
    on=Trigger(MoveStart, when=_marked_enemy_shifts, text=_M4993_SLIPPED),
)
def m4993a3(c: Cast) -> None:
    """An opportunity action resolves before the step, which is why the
    trigger watches the start of the shift rather than the adjacency it
    loses."""
    if c.target is not None:
        use(c.world, c.me, "m4993a1", targets=[c.target], spend=False)


# -- m729 -------------------------------------------------------------------


@power(
    "m729a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m729a0(c: Cast) -> None:
    """Both halves, and the second covers whoever is in the saddle as well.

    Who that is is asked as the fall happens rather than when the trait arms:
    a rider mounts and falls off mid-fight, and a list taken once would name
    the wrong creature or nobody.
    """
    c.resist_forced(1)
    me = c.me

    def brace(ev: ConditionApplied) -> None:
        if ev.condition is not Condition.PRONE:
            return
        if ev.target != me and ev.target != c.rider():
            return
        for eff in list(c.world.effects.of(ev.target)):
            if Condition.PRONE in eff.conditions:
                c.world.effects.save(eff)
                return

    c.watch(ConditionApplied, brace, until=When.ENCOUNTER, on=me, label="m729a0 footing")


@power(
    "m729a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m729a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M729_BOLTED = "an adjacent enemy moves out of reach without teleporting"


def _somebody_ran(world: World, me: int, ev: OpportunityWindow) -> bool:
    """The printed sentence, which the engine already spells out for itself.

    "Willingly moves, without teleporting, to a square that is not adjacent"
    is exactly the test `movement.step` makes before it opens this window --
    a shift, a teleport and every kind of shove are all in `_SAFE` and open
    none. Nothing else on the board says all four of those things at once.
    """
    return ev.actor == me and ev.why == "moved away"


@power(
    "m729a2",
    level=5,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 6),
    trigger=_M729_BOLTED,
    on=Trigger(OpportunityWindow, when=_somebody_ran, text=_M729_BOLTED),
)
def m729a2(c: Cast) -> None:
    """The window names the mover as `provoker`, not as `actor` -- `actor` is
    the creature being offered the chance -- so the target is read off the
    trigger rather than left to the dispatcher, which aims at `ev.actor` and
    would have pointed this at the m729 itself.

    The printed "while the m729 is not flying" is not declared: flying is a
    movement mode rather than a state, and nothing can ask whether a creature
    is in the air right now. See the report.
    """
    who = getattr(c.trigger, "provoker", None)
    if who is None:
        return
    if c.strike(on=who):
        c.hit(on=who)
        c.prone(on=who)
