"""Monster abilities, level 11: the rest of the soldiers.

`soldiers.py` holds the seven stat blocks that were written first; this is
every other level-11 soldier. The conventions are that file's: a stat block's
numbers load from `game.db`, the attack line goes in the header exactly as
printed (`Attack(vs=AC, printed=18)`), the damage line is header data so an
MM1 block can be rescaled later, and a row filed under an action heading that
is plainly a trait is declared `ActionType.NONE` and armed once when the
fight starts. A stat block that prints no range at all means melee 1, and a
printed "15/30" takes the short range, which is the only one `Range` holds.

Nine things this file had to settle.

**A printed ref that belongs to another stat block is read as this one.**
m1586a0, m2091a1, m2549a1, m3921a1 and the whole of m4421 name refs the
database's cross-reference pass lost -- a variant block printing its
parent's ids. Level 7 settled the reading: the row is written against its
own creature, because that is the only creature on the board it can be
about. Each docstring says so.

**"Marked and taking ongoing damage (save ends **both**)" is one hold, and a
mark is a relation.** `c.mark` lays `Relation.MARKED_BY` rather than a
condition, so the two clauses cannot be stacked into one `c.condition` call;
m2355a0 goes through `effects.apply` with the relation *and* the burn, which
is one saving throw for both, as printed. Two calls would be two saves.

**"-2 to all defences (save ends)" is four modifiers and one saving
throw.** A modifier is per defence, so the obvious four `c.penalty(...,
SAVE_ENDS)` calls hand the victim four saves against a line that prints one.
`_all_defences_until_save` gives the first one the save and ends the other
three with it.

**An automatic critical is written onto the live result.** m2634a5 is
m227a4's sentence narrowed to its own swings: the outcome is recomputed from
the `AttackResult` after the roll's window closes, so the one place that can
say this is `ev.result.critical` in the `Hit`'s interrupt window. Both the
event's field and the result's are set, so the log agrees with what lands.
There is still no `Cast` method for it.

**"Willingly leaves the aura" is asked of `Moved`.** It is the only movement
event carrying `from_`, so it is the only one that can say the creature *was*
inside and now is not; and `kind_` tells a walk from a shove, which is the
whole of "willingly". `ZoneExited` carries neither.

**A charge is flagged by hand.** `_charge` is imported rather than copied:
`c.charge_at` reaches its swing through `use`, and the row it would reach for
is the one already in flight.

**"Its fire resistance goes down to 0" is a negative `c.resist`.**
`c.resistances` reads what the block actually has, so the delta is computed
rather than guessed, and ending that effect is what puts the resistance back
when the temporary hit points run out -- which is the printed duration and is
not a `When`.

**A monster's weapon is not modelled, so a printed weapon Requirement is
`requires_text` and nothing else.** Written as a `requires` it would be
false forever and the row would never be offered. Where the same sentence
says what *takes* the weapon away -- m1090a1, m3828a1 -- `c.forbid` on both
rows says the whole of it and the Requirement is then implicit, which is
m338a1's reading one file over.

**Two rows print a type word that is a name.** m2344a3 and half of m3828a4
are "this creature counts as a <word> for the purpose of allies' powers".
`c.set_origin` is the verb and nothing is missing from the engine -- the word
is, and a printed name must not enter a tracked file. Neither is marked,
because a marker names an absent symbol and no symbol is absent. See the
report; the brief printed those words and that is a leak.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_09.brutes import _put_beside
from combat_engine.content.monsters.level_11.soldiers import (
    _charge,
    _disliked_my_roll,
    _shifted_away_from_me,
    _step_beside,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Defense,
    Dropped,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    MoveEnd,
    MoveStart,
    Ranged,
    Trigger,
    UpTo,
    Usage,
    When,
    Window,
    World,
    about_me,
    by_melee,
    power,
    would_hit_me,
)
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.events import (
    AdjacencyGained,
    DamageRolled,
    Escaped,
    PowerUsed,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    enemies,
    flanked_by,
    has_combat_advantage,
    squares,
    team,
)
from combat_engine.engine.relations import Relation

#: The four defences, held separately, so "all defences" is four modifiers.
EVERY_DEFENCE: tuple[Defense, ...] = (AC, FORT, REF, WILL)

#: The movement kinds a creature does not choose. `movement.forced` steps with
#: `kind=how.value`, so these three words are exactly the shoves, and anything
#: else -- walk, shift, teleport, charge -- is willing. What "willingly leaves"
#: and "shifts away" each have to tell apart.
FORCED_KINDS = ("push", "pull", "slide")

#: The conditions m5391a3 can hand a saving throw against.
LOOSENABLE = (Condition.DAZED, Condition.IMMOBILIZED, Condition.RESTRAINED)

#: The four types m2091a0 picks between, in the order the card prints them.
PICKABLE = (
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _all_defences_until_save(c: Cast, victim: int, amount: int) -> None:
    """ "A -2 penalty to all defences (save ends)": four modifiers, one save.

    A modifier is per defence, so the plain reading lays four save-ends holds
    and hands the victim four saving throws against a line that prints one.
    The first carries the save and the other three are ended with it, so the
    whole of it goes at once and only one throw is rolled.
    """
    first = c.penalty(EVERY_DEFENCE[0], amount, on=victim, until=When.SAVE_ENDS)
    rest = [
        c.penalty(defended, amount, on=victim, until=When.ENCOUNTER)
        for defended in EVERY_DEFENCE[1:]
    ]
    if first is None:
        return

    def lift() -> None:
        for eff in rest:
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "the hold was shaken off")

    first.on_end.append(lift)


def _shift_to_reach(c: Cast, victim: int, span: int) -> bool:
    """Shift up to `span` squares and finish within reach of that creature.

    `c.shift` with no `to` offers the decider every square in range, which is
    useless for a printed line that says where the step has to end.
    `_step_beside` one file over says this for a single square; this is the
    same question over a distance.
    """
    me = c.me
    theirs = squares(c.world, victim)
    mine = squares(c.world, me)
    options = sorted(
        sq
        for sq in c.world.reachable_squares(me, span)
        if sq not in mine and min(distance(sq, t) for t in theirs) <= 1
    )
    if not options:
        return False
    where = c.world.decide(me, "shift", options, f"{c.ref}: closing the gap")
    return c.shift(span, to=where)


def _gap_from(c: Cast, square: Any, who: int) -> int:
    """How far a square was from that creature, for a row reading `Moved.from_`."""
    return min(distance(square, sq) for sq in squares(c.world, who))


def _my_mark(world: World, me: int, who: int) -> bool:
    return world.relations.holds(Relation.MARKED_BY, me, who)


def _my_mark_shifts(world: World, me: int, ev: MoveStart) -> bool:
    """An enemy this creature has marked is shifting."""
    return ev.kind_ == "shift" and ev.actor != me and _my_mark(world, me, ev.actor)


def _my_mark_moves(world: World, me: int, ev: MoveStart) -> bool:
    """An enemy this creature has marked is moving, however it moves."""
    return ev.actor != me and _my_mark(world, me, ev.actor)


def _my_mark_attacks_elsewhere(world: World, me: int, ev: AttackDeclared) -> bool:
    """A marked enemy is swinging at somebody who is not this creature."""
    return (
        ev.attacker != me
        and ev.target != me
        and _my_mark(world, me, ev.attacker)
    )


def _flanked_enemy_shifts(world: World, me: int, ev: MoveStart) -> bool:
    """One of the creatures this one is flanking is slipping out of the pin."""
    if ev.kind_ != "shift" or ev.actor == me:
        return False
    if team(world, ev.actor) is team(world, me):
        return False
    return flanked_by(world, ev.actor, me)


def _hurt_me(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.amount > 0


def _burned_me(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.amount > 0 and DamageType.FIRE in ev.types()


def _my_opportunity_hit(world: World, me: int, ev: Hit) -> bool:
    """This creature's own opportunity attack landed.

    `opportunity` is a plain attribute `resolve.attack` sets after the fact,
    so it is read with `getattr` and not declared on the event.
    """
    return ev.attacker == me and bool(getattr(ev, "opportunity", False))


def _seen_for_the_first_time(world: World, me: int, ev: TurnStart) -> bool:
    """An enemy within 10 squares can see this creature.

    The printed trigger is "gains line of sight for the first time this
    encounter", and the engine announces no such moment -- there is no
    sight event at all. A turn opening inside ten squares with a clear
    line is the nearest thing any event says, and `usage=ENCOUNTER` is
    what makes it once. See the report.
    """
    if ev.ghost or ev.actor == me:
        return False
    if team(world, ev.actor) is team(world, me):
        return False
    if distance_between(world, me, ev.actor) > 10:
        return False
    return Cast(world=world, me=ev.actor, ref="m115843a3").can_see(me)


def _charmed_me(world: World, me: int, ev: AttackDeclared) -> bool:
    """A charm power is being aimed at this creature.

    `keywords_of` reads the keyword list off the ref the event carries, which
    is the only place an incoming attack says what kind of thing it is.
    """
    return ev.target == me and Keyword.CHARM in keywords_of(ev.power)


def _next_blow_of_mine_crits(c: Cast, victim: int, plus: int) -> None:
    """The next melee attack *this creature* makes against that one crits.

    m227a4's arrangement narrowed to its own swings. The +`plus` goes on at
    the moment the attack is declared, which is the last point it can reach
    the roll; the critical is written onto the live `AttackResult` in the
    `Hit`'s interrupt window, because the outcome is recomputed from that
    object after the roll and `c.hit()` reads `c.crit` off the same one --
    so rigging the event's field alone would change the log and not the
    damage. Both are set. Spent by the first melee attack that resolves,
    hit or miss, which is what "the next" means.
    """
    me = c.me
    held: list[Effect] = []

    def spend(why: str) -> None:
        for eff in list(held):
            if not eff.ended:
                c.world.effects.end(eff, why)
        held.clear()

    def sharpen(ev: AttackDeclared) -> None:
        if ev.target != victim or ev.attacker != me or not by_melee(c.world, me, ev):
            return
        boon = c.bonus("attack", plus, on=me, until=When.EOT, kind="power")
        if boon is not None:
            held.append(boon)

    def straight_in(ev: Hit) -> None:
        if ev.target != victim or ev.attacker != me or not by_melee(c.world, me, ev):
            return
        ev.critical = True
        result = getattr(ev, "result", None)
        if result is not None:
            result.critical = True
        spend("the blow went in")

    def wasted(ev: Miss) -> None:
        if ev.target == victim and ev.attacker == me:
            spend("the blow missed")

    held.append(
        c.watch(
            AttackDeclared, sharpen, until=When.ENCOUNTER, window=Window.BEFORE,
            on=me, label=f"{c.ref} opening",
        )
    )
    held.append(
        c.watch(
            Hit, straight_in, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
            label=f"{c.ref} critical",
        )
    )
    held.append(
        c.watch(Miss, wasted, until=When.ENCOUNTER, on=me, label=f"{c.ref} spent")
    )


def _bloodied_gate(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return bool(health is not None and health.bloodied)


# ==========================================================================
# m1090
# ==========================================================================


@power(
    "m1090a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d8", 5),
)
def m1090a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1090a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
    dropped=("When.ESCAPE",),
)
def m1090a1(c: Cast) -> None:
    """Pinned on the end of the weapon, which is then busy.

    The hold is laid `When.SUSTAIN` with a standard action to keep it, which
    is the printed sustain, and `c.on_sustain` is the payout half -- without
    it the "the target takes 1d8 + 5 damage and is still restrained" sentence
    goes nowhere.

    "(until escape)" has no door: `When` has no escape-tied member, so the
    hold ends when the sustain lapses rather than on a successful escape
    attempt.

    The printed Requirement -- it must still have the weapon -- is not
    written as a `requires`, because the same sentence says what takes the
    weapon away: both weapon rows are forbidden while the hold lasts, and a
    forbidden row is one `usable` already refuses.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    held = c.world.effects.apply(
        victim, me, When.SUSTAIN, label=c.ref,
        conditions=(Condition.RESTRAINED,), sustain_cost=STANDARD,
    )
    c.on_sustain(held, lambda: c.hit(on=victim))
    barred = [
        c.forbid(ref, on=me, until=When.ENCOUNTER) for ref in ("m1090a0", "m1090a1")
    ]

    def free_again() -> None:
        for eff in barred:
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "the weapon comes free")

    held.on_end.append(free_again)


@power(
    "m1090a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d6", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m1090a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


# ==========================================================================
# m115843
# ==========================================================================


@power(
    "m115843a0",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115843a0(c: Cast) -> None:
    """Fire catches on it and keeps burning.

    `ev.types()` rather than `ev.dtype`, because a blow that is fire *and*
    something else is still fire damage taken and the single field names only
    the first type.
    """
    me = c.me

    def caught(ev: DamageApplied) -> None:
        if _burned_me(c.world, me, ev):
            c.ongoing(5, DamageType.FIRE, on=me, until=When.SAVE_ENDS)

    c.watch(DamageApplied, caught, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m115843a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m115843a1(c: Cast) -> None:
    """`c.cannot_shift`, not `c.immobilized`: the printed line takes the shift
    away and leaves the walk."""
    if c.strike():
        c.hit()
        c.cannot_shift(until=When.SAVE_ENDS)


@power(
    "m115843a2",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m115843a2(c: Cast) -> None:
    """No attack roll: the printed line rolls none, and the slow is the whole
    of it.

    Two printed ends, neither of them a clock, so the hold runs to the end of
    the fight and both are watched for. The first is this row being used on
    somebody else -- `PowerUsed` is announced before the body runs, and its
    `targets` are chosen before that, so the new victim is already readable
    there. The second is the creature going down.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    hold = c.slowed(until=When.ENCOUNTER, on=victim)
    if hold is None:
        return

    def moved_on(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != "m115843a2":
            return
        if victim not in ev.targets and not hold.ended:
            c.world.effects.end(hold, "it fixes on somebody else")

    def gone(ev: Dropped) -> None:
        if ev.actor == me and not hold.ended:
            c.world.effects.end(hold, "the m115843 is destroyed")

    hold.subs.append(c.world.bus.on(PowerUsed, moved_on, owner=me))
    hold.subs.append(c.world.bus.on(Dropped, gone, owner=me))


_M115843_SEEN = "an enemy within 10 squares gains line of sight to the m115843"


@power(
    "m115843a3",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=14),
    trigger=_M115843_SEEN,
    on=Trigger(TurnStart, when=_seen_for_the_first_time, text=_M115843_SEEN),
)
def m115843a3(c: Cast) -> None:
    """Declared with no target and aimed off the trigger: the dispatcher only
    points a row that takes one enemy, and this one is about the creature
    that just laid eyes on it."""
    who = getattr(c.trigger, "actor", None)
    if who is None or not alive(c.world, who):
        return
    if c.strike(on=who):
        c.stunned(until=When.EONT, on=who)


# ==========================================================================
# m1454
# ==========================================================================


@power(
    "m1454a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m1454a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1454a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m1454a1(c: Cast) -> None:
    """Two attacks, and the header's line is the first of them: the printed
    damage on this row is not m1454a0's, so the bite rolls here and the
    second blow is m1454a6, which has its own line and its own area."""
    if c.strike():
        c.hit()
    c.use_power("m1454a6")


_M1454_HURT = "the m1454 takes damage"


@power(
    "m1454a2",
    level=11,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=20),
    damage=Damage("2d6", 6),
    trigger=_M1454_HURT,
    on=Trigger(DamageApplied, when=_hurt_me, text=_M1454_HURT),
)
def m1454a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1454a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=17),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1454a3(c: Cast) -> None:
    """"Each Failed Saving Throw" is `escalate`, which runs on a failed save
    and leaves the hold standing -- the ten damage is a toll on every throw,
    not a worsening that replaces the condition."""
    if not c.strike():
        return
    c.hit()
    c.condition(
        Condition.IMMOBILIZED,
        until=When.SAVE_ENDS,
        escalate=lambda eff: c.flat(10, on=eff.owner),
    )


_M1454_BLOODIED = "the m1454 is first bloodied"


@power(
    "m1454a4",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M1454_BLOODIED,
    on=Trigger(Bloodied, about_me, _M1454_BLOODIED),
)
def m1454a4(c: Cast) -> None:
    """`Bloodied` is announced once, so "first" needs no guard of its own.
    The use is free: this row is the action, and m1454a3 is spent as part of
    it rather than costing the creature a second standard."""
    c.restore_use("m1454a3")
    c.use_power("m1454a3")


@power(
    "m1454a5",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=17),
)
def m1454a5(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit.

    An aftereffect follows when the first hold ends, whichever way it ended,
    so it hangs off that hold -- not on `escalate`, which runs on a *failed*
    save and would never run at all for a hold on a turn clock.
    """
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


@power(
    "m1454a6",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 6),
)
def m1454a6(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m1586
# ==========================================================================


def _m1586_has_an_edge(world: World, eid: int) -> bool:
    """Somebody in reach this creature has combat advantage against.

    The printed Requirement is about a target and a `requires=` gate is
    handed `(world, eid)` and no target, so it asks whether *any* enemy in
    reach qualifies and the body picks which.
    """
    return any(
        distance_between(world, eid, foe) <= 1 and has_combat_advantage(world, eid, foe)
        for foe in enemies(world, eid)
    )


@power(
    "m1586a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m1586a0(c: Cast) -> None:
    """The printed mark names a ref belonging to no stat block in the tree --
    a cross-reference the database lost -- and is read as this creature's own
    next turn, which is the only clock on this board it can mean."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1586a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m1586a1(c: Cast) -> None:
    """Two of its own at-will blows, so the numbers live in m1586a0 and not
    here: this row has no line of its own to roll."""
    for _ in range(2):
        c.use_power("m1586a0", on=c.target)


@power(
    "m1586a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m1586a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1586a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    once_per_round=True,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 5),
    requires=_m1586_has_an_edge,
    requires_text="the m1586 must have combat advantage against the target",
    dropped=("Target.kind",),
)
def m1586a3(c: Cast) -> None:
    """Aimed at a creature it actually has an edge on rather than thrown away:
    `Target` filters on side, count and size and not on whether a swing would
    have combat advantage, so the chooser may hand this row somebody its own
    printed line forbids."""
    victim = _restricted_to(c, 1, lambda f: has_combat_advantage(c.world, c.me, f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.half_healing(on=victim, until=When.EONT)


@power(
    "m1586a4",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m1586a4(c: Cast) -> None:
    """Range 10/20: the header carries the short range, which is the only one
    `Range` holds and the one this can throw at without a penalty."""
    if c.strike():
        c.hit()


@power(
    "m1586a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1586a5(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    The gate is about *this* creature's flanking whoever is being hit, not
    about whoever is swinging, so the same test is laid on every ally and on
    itself. An extra rolled 2d6 rather than a flat number, which is what
    `dice=` on a damage modifier is for. Allies arriving later do not get it;
    a trait arms once.
    """
    me = c.me
    for who in [me, *c.allies()]:
        c.bonus(
            "damage", 0, dice="2d6", on=who, until=When.ENCOUNTER,
            when=lambda ctx: flanked_by(c.world, ctx["target"], me),
        )


@power(
    "m1586a6",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1586a6(c: Cast) -> None:
    """"Natural 19 and 20" is one square of range added to the crit window,
    read off the attacker at the moment of the roll."""
    c.bonus("crit_range", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "m1586a7",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m1586a7(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. `Hit.critical` is a
    declared field, so the crit is read off the event rather than recomputed
    from the roll."""
    me = c.me

    def rallied(ev: Hit) -> None:
        if ev.attacker != me or not ev.critical:
            return
        c.heal(5, on=me)
        for mate in c.within(5, of=me, side="team"):
            if mate != me:
                c.heal(5, on=mate)

    c.watch(Hit, rallied, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1792
# ==========================================================================


@power(
    "m1792a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m1792a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


_M1792_SLIPPED = "an enemy marked by the m1792 moves or attacks somebody else"


@power(
    "m1792a1",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d10", 5),
    trigger=_M1792_SLIPPED,
    on=(
        Trigger(MoveStart, when=_my_mark_moves, text=_M1792_SLIPPED),
        Trigger(AttackDeclared, when=_my_mark_attacks_elsewhere, text=_M1792_SLIPPED),
    ),
)
def m1792a1(c: Cast) -> None:
    """Both halves of the printed trigger are declared: half of it would look
    finished and would answer only one of the two sentences.

    `MoveStart` for the movement half -- by `MoveEnd` the creature has gone,
    and this is the defender's shape, which is true precisely while it is
    still in reach.

    The slide is one clause of one save-ends hold rather than a hold of its
    own: the penalty carries the saving throw and the watch is a subscription
    on it, so the victim rolls once against the whole printed sentence.
    """
    me = c.me
    ev = c.trigger
    who = getattr(ev, "actor", None)
    if who is None:
        who = getattr(ev, "attacker", None)
    if who is None or not alive(c.world, who):
        return
    if not c.strike(on=who):
        return
    c.hit(on=who)
    hold = c.penalty(WILL, 4, on=who, until=When.SAVE_ENDS)
    if hold is None:
        return

    def nudge(turn: TurnStart) -> None:
        if turn.ghost or turn.actor != who or hold.ended:
            return
        if c.may("slide it 1 square", who=me):
            c.slide(1, on=who)

    hold.subs.append(c.world.bus.on(TurnStart, nudge, owner=me))


@power(
    "m1792a2",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=UpTo(2),
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
)
def m1792a2(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)


# ==========================================================================
# m1998
# ==========================================================================


@power(
    "m1998a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 3),
)
def m1998a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m1998a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 6, kind=LIMITED),
    requires_text="the m1998 must be wielding its flail",
)
def m1998a1(c: Cast) -> None:
    """The weapon Requirement is `requires_text` and nothing else: a monster's
    weapon is not an object the engine holds, so a `requires` asking for one
    would be false forever and the row would never be offered.

    No duration is printed on the immobilisation, which means the end of this
    creature's next turn.
    """
    if c.strike():
        c.hit()
        c.slide(1)
        c.immobilized(until=When.EONT)


# ==========================================================================
# m2091
# ==========================================================================


@power(
    "m2091a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.WEAPON,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.THUNDER,
    ],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d10", 7),
)
def m2091a0(c: Cast) -> None:
    """The element is a second packet rather than a retype: the printed line
    is "1d10+7 damage **plus** 1d10 cold, fire, lightning or thunder", so the
    weapon half stays untyped and only the extra die carries a type."""
    if not c.strike():
        return
    c.hit()
    picked = c.choose(list(PICKABLE), f"{c.ref}: which element")
    if picked is not None:
        c.damage("1d10", dtype=picked)


@power(
    "m2091a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[
        Keyword.WEAPON,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.THUNDER,
    ],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d8", 5, kind=LIMITED),
)
def m2091a1(c: Cast) -> None:
    """The printed Effect is two at-will blows, so that is what the body does
    and the header's own line is never rolled.

    The extract this was written from prints an attack with no defence
    beside a damage expression and then a sentence that makes two other
    attacks instead; the numbers are kept in the header because they are
    what the card shows, and the sentence is what resolves. See the report.
    """
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.use_power("m2091a0", on=victim)


_M2091_OPENING = "the m2091 hits with an opportunity attack"


@power(
    "m2091a2",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2091_OPENING,
    on=Trigger(Hit, when=_my_opportunity_hit, text=_M2091_OPENING),
)
def m2091a2(c: Cast) -> None:
    c.shift(2)


# ==========================================================================
# m2106
# ==========================================================================


@power(
    "m2106a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m2106a0(c: Cast) -> None:
    """"2d6+6 plus 3d6 fire" is two packets, because resistance reads them
    separately and only the second is fire."""
    if c.strike():
        c.hit()
        c.damage("3d6", dtype=DamageType.FIRE)


@power(
    "m2106a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 6),
)
def m2106a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2106a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2106a2(c: Cast) -> None:
    """Two of its own at-will blows, so the numbers live in m2106a1."""
    for _ in range(2):
        c.use_power("m2106a1", on=c.target)


def _closed_on_me(world: World, me: int, ev: AdjacencyGained) -> bool:
    """An enemy moved itself into a square adjacent to this creature.

    `AdjacencyGained` is mirrored, so `other` is read rather than `actor`,
    and `mover` is what tells "an enemy moves adjacent to it" from this
    creature closing the gap itself -- which is true half the time and is
    not the printed sentence.
    """
    if ev.other != me or ev.mover == me or ev.actor == me:
        return False
    return team(world, ev.actor) is not team(world, me)


_M2106_CLOSED = "an enemy moves into a square adjacent to the m2106"


@power(
    "m2106a3",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d6", 6),
    trigger=_M2106_CLOSED,
    on=Trigger(AdjacencyGained, when=_closed_on_me, text=_M2106_CLOSED),
)
def m2106a3(c: Cast) -> None:
    """It snaps at whatever comes within reach and holds on.

    "First Failed Escape Attempt" is `Escaped`, which is emitted for a
    failure as well as a win and names the grabber in `holder` -- so the
    watch gates on that and not on `actor`, which is the creature
    struggling. The bite is not rolled again: `c.as_though_hit_by` runs the
    row with its attack forced to land, which is what "automatically hits"
    means.
    """
    me = c.me
    who = getattr(c.trigger, "actor", None)
    if who is None or not alive(c.world, who):
        return
    if not c.strike(on=who):
        return
    c.hit(on=who)
    hold = c.grab(on=who)
    if hold is None:
        return
    once: dict[str, int] = {"spent": 0}

    def struggled(ev: Escaped) -> None:
        if ev.holder != me or ev.actor != who or ev.success or once["spent"]:
            return
        once["spent"] = 1
        c.as_though_hit_by("m2106a0", on=who, by=me)

    hold.subs.append(c.world.bus.on(Escaped, struggled, owner=me))


@power(
    "m2106a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("2d10", 5, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m2106a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m2106a5",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=16),
    requires=_bloodied_gate,
    requires_text="usable only while bloodied",
)
def m2106a5(c: Cast) -> None:
    """No damage line: the shove, the fall and the daze are the whole hit.

    The Requirement is a fact about this creature rather than about a target,
    so it is safe as a `requires` -- and it can only ever become true during
    a fight, which is the direction that does not kill a row.
    """
    if c.strike():
        c.push(3)
        c.prone()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2106a6",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.COLD],
)
def m2106a6(c: Cast) -> None:
    """A shell that is paid for with its resistance to fire.

    "Its fire resistance goes down to 0" is a negative `c.resist` of whatever
    the block actually has, read with `c.resistances` rather than guessed --
    and the way back is ending that effect, which puts back exactly what the
    call moved.

    "Until the temporary hit points this power grants are gone" is not a
    `When`, so the three holds run to the end of the fight and a watch on
    damage closes them the moment the shell is spent. `Health.temp` is the
    reading; `DamageApplied.absorbed` is what came off it on one blow and
    would say nothing about whether any is left.
    """
    me = c.me
    c.temp_hp(33, on=me)
    guard = c.bonus(AC, 2, on=me, until=When.ENCOUNTER)
    had = c.resistances(on=me).get(DamageType.FIRE, 0)
    lost = (
        c.resist(-had, DamageType.FIRE, until=When.ENCOUNTER, on=me) if had else None
    )

    def spent(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        health = c.world.get(me, Health)
        if health is None or health.temp > 0:
            return
        for eff in (guard, lost):
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "the shell is gone")

    c.watch(DamageApplied, spent, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2344
# ==========================================================================


@power(
    "m2344a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 7),
)
def m2344a0(c: Cast) -> None:
    """The bloodied numbers are taken locally rather than laid as a standing
    modifier: an at-will that lays an encounter-long bonus every time it is
    used stacks one on each swing, and `plus=` reaches the roll of this swing
    only."""
    hurt = c.bloodied(on=c.me)
    if c.strike(plus=2 if hurt else 0):
        c.hit()
        if hurt:
            c.flat(2)


@power(
    "m2344a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
)
def m2344a1(c: Cast) -> None:
    """The printed Effect *is* a charge, so `charges=True`: without it the
    engine measures a sword's reach before the run and refuses the row from
    every distance a charge is for.

    `c.basic` rather than a line of its own -- the printed sentence is about
    whatever this creature's basic attack is, which is m2344a0.
    """
    victim = c.target
    if victim is None:
        return

    def blow() -> None:
        if c.basic(on=victim):
            c.flat(10, on=victim)

    _charge(c, victim, blow)


@power(
    "m2344a2",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m2344a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Declared on `AttackDeclared` rather than on `Hit`: the printed line is
    "if the m2344 is **attacked** by a charm effect", which is the
    declaration and not the outcome. `keywords_of` reads the keyword list off
    the ref the event carries, the only place an incoming attack says what
    kind of thing it is.
    """
    me = c.me

    def recoil(ev: AttackDeclared) -> None:
        if not _charmed_me(c.world, me, ev):
            return
        c.flat(10, dtype=DamageType.PSYCHIC, on=me)
        c.flat(10, dtype=DamageType.PSYCHIC, on=ev.attacker)

    c.watch(
        AttackDeclared, recoil, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=c.ref,
    )


@power(
    "m2344a3",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m2344a3(c: Cast) -> None:
    """Deliberately inert, and not a gap.

    The whole printed content of this row is a type word that another stat
    block's rows read -- and that word is a printed name, which must not
    enter a tracked file in any form. `c.set_origin` is the verb for laying a
    type word, so nothing is missing from the engine and no marker would have
    a symbol to name; and no row on this board reads the word, so laying it
    would change nothing in a fight either. The brief printed it, which is a
    leak, and the report says so.
    """
    c.note("m2344a3: a type word other stat blocks read, and nothing here does")


# ==========================================================================
# m2355
# ==========================================================================


@power(
    "m2355a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m2355a0(c: Cast) -> None:
    """Three printed numbers on one line, and the mark and the burn save
    together.

    The critical is written as its own packet because the card prints a
    critical *expression* rather than relying on the maximised dice -- and it
    goes through `c.flat(c.roll(...))`, since `c.damage` maxes its dice on a
    critical and would hand back the maximum of a line that is meant to be
    rolled.

    "Marked and ongoing 5 (save ends **both**)" is one hold. A mark is
    `Relation.MARKED_BY` rather than a condition, so `c.mark` and
    `c.ongoing` cannot be folded into one `c.condition`; the relation and the
    burn go through `effects.apply` together, which is one saving throw for
    both. Two calls would be two throws against a line that prints one.
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    weak = c.bloodied(on=victim)
    if c.crit:
        c.flat(c.roll("2d8") + (20 if weak else 15))
    else:
        c.hit()
        if weak:
            c.flat(5)
    c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=f"{c.ref} mark",
        relations=[(Relation.MARKED_BY, me, victim)],
        ongoing=(5, DamageType.UNTYPED),
    )


_M2355_DOWN = "the m2355 is reduced to 0 hit points"


@power(
    "m2355a1",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 3, dtype=DamageType.PSYCHIC),
    trigger=_M2355_DOWN,
    on=Trigger(Dropped, about_me, _M2355_DOWN),
)
def m2355a1(c: Cast) -> None:
    """A death throe: `Dropped` carries `actor`, so `about_me` is the right
    predicate here where it is wrong on the attack events."""
    if c.strike():
        c.hit()
        if c.bloodied():
            c.flat(5, dtype=DamageType.PSYCHIC)


# ==========================================================================
# m2516
# ==========================================================================


@power(
    "m2516a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5),
)
def m2516a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2516a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m2516a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2516a2",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
    dropped=("Target.kind",),
)
def m2516a2(c: Cast) -> None:
    """No damage line: dragging the creature in is the whole of the hit.

    Aimed at somebody the printed target line allows rather than thrown away
    -- `Target` filters on side, count and size and not on what a creature is
    suffering.
    """
    victim = _restricted_to(
        c,
        4,
        lambda f: any(
            c.is_(cond, on=f)
            for cond in (
                Condition.DAZED,
                Condition.STUNNED,
                Condition.UNCONSCIOUS,
                Condition.HELPLESS,
            )
        ),
    )
    if victim is None:
        return
    if c.strike(on=victim):
        _put_beside(c, victim, c.me)


@power(
    "m2516a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2516a3(c: Cast) -> None:
    """"Targets creatures without the demon keyword" is asked of the type
    words a creature carries. A burst skips whoever does not qualify rather
    than being redirected: the area is the target line, and there is nothing
    to aim."""
    victim = c.target
    if victim is None or c.is_kind("demon", on=victim):
        return
    if c.strike():
        c.hit()
        _all_defences_until_save(c, victim, 2)


# ==========================================================================
# m2549
# ==========================================================================


@power(
    "m2549a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m2549a0(c: Cast) -> None:
    """"Loses 1 healing surge" is `c.spend_surge`, which spends one and gives
    nothing back for it -- and it is aimed at the victim, because the verb is
    the caster's by default."""
    if c.strike():
        c.hit()
        c.spend_surge(on=c.target)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m2549a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
    dropped=("Target.kind",),
)
def m2549a1(c: Cast) -> None:
    """"Affects an immobilized target only" is narrower than any `Target` can
    say, so the row is aimed at an immobilised creature in range rather than
    discarded when the chooser hands it somebody else.

    The printed healing names a ref belonging to no stat block in the tree
    and is read as this creature.
    """
    victim = _restricted_to(c, 5, lambda f: c.is_(Condition.IMMOBILIZED, on=f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.heal(10, on=c.me)


_M2549_SLIPPED = "a marked enemy shifts or attacks somebody other than the m2549"


@power(
    "m2549a2",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M2549_SLIPPED,
    on=(
        Trigger(MoveStart, when=_my_mark_shifts, text=_M2549_SLIPPED),
        Trigger(AttackDeclared, when=_my_mark_attacks_elsewhere, text=_M2549_SLIPPED),
    ),
)
def m2549a2(c: Cast) -> None:
    """`c.basic(on=...)` names the victim; without it the swing would default
    to this row's own target, which a `NO_TARGET` row has none of."""
    ev = c.trigger
    who = getattr(ev, "actor", None)
    if who is None:
        who = getattr(ev, "attacker", None)
    if who is not None and alive(c.world, who):
        c.basic(on=who)


@power(
    "m2549a3",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2549a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. `c.on_attack` is the
    engine's "whenever that creature attacks", and the mark goes on whoever
    was swung at rather than on this row's own target."""
    me = c.me

    def claimed(ev: AttackDeclared) -> None:
        if ev.attacker == me and ev.target in c.enemies():
            c.mark(until=When.EONT, on=ev.target)

    c.on_attack(claimed, by=me, until=When.ENCOUNTER, label=c.ref)


@power(
    "m2549a4",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2549a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    `kind="power"` because the card prints the word, and the gate is asked
    inside the modifier rather than once when the trait arms: allies move in
    and out of reach all fight, and a defence is read again after a roll has
    been announced.
    """
    me = c.me
    for mate in c.allies():
        c.bonus(
            AC, 2, on=mate, until=When.ENCOUNTER, kind="power",
            when=lambda _ctx, who=mate: distance_between(c.world, me, who) <= 1,
        )


# ==========================================================================
# m2620
# ==========================================================================


@power(
    "m2620a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
)
def m2620a0(c: Cast) -> None:
    """It punishes the victim for hurting anybody else.

    The window is `When.SONT` -- "before the start of the m2620's next turn"
    -- and it pays once, which is what a single printed consequence means.
    `DamageApplied` rather than `Hit`, because the printed line is "deals
    damage to any creature", not "hits one".
    """
    me, victim = c.me, c.target
    if victim is None or not c.strike():
        return
    c.hit()
    paid: dict[str, int] = {"done": 0}

    def elsewhere(ev: DamageApplied) -> None:
        if ev.source != victim or ev.target == me or ev.amount <= 0 or paid["done"]:
            return
        paid["done"] = 1
        c.flat(5, dtype=DamageType.PSYCHIC, on=victim)
        c.ongoing(5, DamageType.PSYCHIC, on=victim)

    c.watch(DamageApplied, elsewhere, until=When.SONT, on=me, label=c.ref)


@power(
    "m2620a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2620a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2620a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=16),
)
def m2620a2(c: Cast) -> None:
    """No damage line, and no duration printed on the hold, which means the
    end of this creature's next turn."""
    if c.strike():
        c.immobilized(until=When.EONT)


# ==========================================================================
# m2634
# ==========================================================================


@power(
    "m2634a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 3),
)
def m2634a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2634a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d8", 3),
)
def m2634a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)


_M2634_SLIPPED = "an adjacent enemy shifts away from the m2634"
_M2634_STRUCK = "the m2634 is hit by an attack"


@power(
    "m2634a2",
    level=11,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2634_SLIPPED,
    on=Trigger(MoveEnd, when=_shifted_away_from_me, text=_M2634_SLIPPED),
)
def m2634a2(c: Cast) -> None:
    """It goes with them, and the second printed clause -- the movement mode
    -- lives in the predicate, which is where the mode a shift used can still
    be recomputed. Both halves are m227's, written once a file over."""
    who = getattr(c.trigger, "actor", None)
    if who is not None and alive(c.world, who):
        _step_beside(c, who)


@power(
    "m2634a3",
    level=11,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2634_STRUCK,
    on=Trigger(AttackRolled, when=would_hit_me, text=_M2634_STRUCK),
)
def m2634a3(c: Cast) -> None:
    """Four modifiers, because "a +2 bonus to all defenses" is four numbers.

    Declared on `AttackRolled` rather than on `Hit`: the defence is read
    again once that window closes, which is what lets a guard raised here
    turn the blow aside, and `would_hit_me` is the engine's spelling of "when
    it would be hit by an attack".

    No `kind=`: the card prints "+2 bonus" with no type word.
    """
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.EONT, on=c.me)


@power(
    "m2634a4",
    level=11,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2634a4(c: Cast) -> None:
    """The mode is granted for the turn and then flown: `c.move(at="fly")`
    needs a mode to travel at, and this creature's block prints none, so the
    row carries its own for as long as the move lasts."""
    c.mode("fly", 5, until=When.EOT, on=c.me)
    c.move(5, at="fly")


@power(
    "m2634a5",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
)
def m2634a5(c: Cast) -> None:
    """No attack roll: the printed line rolls none.

    The +5 and the automatic critical are m227a4's arrangement narrowed to
    this creature's own swings -- "the next melee attack m2634 makes" rather
    than anybody's. There is still no `Cast` method for writing a critical
    onto an attack that has not happened; see the report.
    """
    victim = c.target
    if victim is None:
        return
    _next_blow_of_mine_crits(c, victim, 5)


# ==========================================================================
# m2635
# ==========================================================================


@power(
    "m2635a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 4),
)
def m2635a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


def _my_mark_leaves_reach(world: World, me: int, ev: MoveStart) -> bool:
    """A creature this one has marked is stepping out of a square it can reach.

    `MoveStart`, because by `MoveEnd` the creature has gone and the reach
    test is false precisely when the row should fire.
    """
    return (
        ev.actor != me
        and _my_mark(world, me, ev.actor)
        and distance_between(world, me, ev.actor) <= 2
    )


_M2635_LEFT = "a creature marked by the m2635 leaves a square within its reach"


@power(
    "m2635a1",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d10", 4),
    trigger=_M2635_LEFT,
    on=Trigger(MoveStart, when=_my_mark_leaves_reach, text=_M2635_LEFT),
)
def m2635a1(c: Cast) -> None:
    """"The target's movement ends" is `c.cancel`, which only an interrupt can
    do and which is the printed window this row is declared in. The slide is
    this creature's, and happens after the move is stopped."""
    who = getattr(c.trigger, "actor", None)
    if who is None or not alive(c.world, who):
        return
    if not c.strike(on=who):
        return
    c.hit(on=who)
    c.cancel()
    c.slide(2, on=who)


@power(
    "m2635a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 4),
    requires_text="the m2635 must be wielding its halberd",
)
def m2635a2(c: Cast) -> None:
    """The weapon Requirement is `requires_text` only: a monster's weapon is
    not an object the engine holds, and a `requires` asking for one would be
    false forever."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2635a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 2),
)
def m2635a3(c: Cast) -> None:
    """Range 15/30: the header carries the short range."""
    if c.strike():
        c.hit()


# ==========================================================================
# m2714
# ==========================================================================


@power(
    "m2714a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m2714a0(c: Cast) -> None:
    """The printed "+19 and 1d8+7 against a bloodied target" is m2714a4
    saying the same thing for every attack this creature makes, so it is
    *not* written again here: two bonuses for one sentence would double it."""
    if not c.strike():
        return
    c.hit()
    c.damage("1d8", dtype=DamageType.COLD)
    c.mark(until=When.EONT)


@power(
    "m2714a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d6", 5),
)
def m2714a1(c: Cast) -> None:
    """Range 10/20 takes the short range, and the bloodied differential is
    m2714a4's."""
    if c.strike():
        c.hit()


_M2714_SLIPPED = "an enemy the m2714 is flanking shifts"
_M2714_ELSEWHERE = "a marked enemy attacks somebody other than the m2714"


@power(
    "m2714a2",
    level=11,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    trigger=_M2714_SLIPPED,
    on=Trigger(MoveStart, when=_flanked_enemy_shifts, text=_M2714_SLIPPED),
)
def m2714a2(c: Cast) -> None:
    """`MoveStart`, because the flank is only true while the creature is still
    standing in it."""
    who = getattr(c.trigger, "actor", None)
    if who is not None and alive(c.world, who):
        c.basic(on=who)


@power(
    "m2714a3",
    level=11,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    trigger=_M2714_ELSEWHERE,
    on=Trigger(AttackDeclared, when=_my_mark_attacks_elsewhere, text=_M2714_ELSEWHERE),
)
def m2714a3(c: Cast) -> None:
    """Seven squares, and the step has to finish next to the triggering enemy
    -- `c.shift` with no `to` offers the decider every square in range, which
    is useless for a line that says where the step ends."""
    who = getattr(c.trigger, "attacker", None)
    if who is None or not alive(c.world, who):
        return
    _shift_to_reach(c, who, 7)
    if c.adjacent(who):
        c.basic(on=who)


@power(
    "m2714a4",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2714a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait, and this is where
    m2714a0's and m2714a1's bloodied numbers come from.

    No `kind=` on either: the card prints "+1 bonus" and "+2 bonus" with no
    type word. The gate reads the target off the modifier context, which is
    the only place the creature being hit is named on the damage side.
    """
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx["target"]),
    )
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx["target"]),
    )


# ==========================================================================
# m3828
# ==========================================================================


@power(
    "m3828a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m3828a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3828a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m3828a1(c: Cast) -> None:
    """Pinned on the end of the weapon, which is then busy.

    The hold carries the restraint and the burn together: applied separately
    the victim would get two saving throws against a thing the card says it
    saves against once.

    The printed Requirement -- it must still have the weapon -- is not
    written as a `requires`, because the same sentence says what takes the
    weapon away: both weapon rows are forbidden while the hold lasts, and a
    forbidden row is one `usable` already refuses.
    """
    me = c.me
    if not c.strike():
        return
    c.hit()
    held = c.condition(
        Condition.RESTRAINED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED)
    )
    if held is None:
        return
    barred = [
        c.forbid(ref, on=me, until=When.ENCOUNTER) for ref in ("m3828a0", "m3828a1")
    ]

    def free_again() -> None:
        for eff in barred:
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "the weapon comes free")

    held.on_end.append(free_again)


@power(
    "m3828a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d6", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m3828a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3828a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m3828a3(c: Cast) -> None:
    """Venom on the blade, paid out on the next weapon hit.

    **Not `c.apply_poison`**, which is the verb for this sentence on a
    character and is inert on a monster: it coats "a weapon in hand", and
    `c.held` finds nothing on a stat block -- a monster's weapon is printed
    prose and not an object the engine carries -- so it returns None and the
    row never pays. It audited silent that way. A `Hit` watch narrowed by
    `Keyword.WEAPON` is what is left, and it is the printed sentence: the
    next time *this creature* hits with a weapon attack.

    The secondary is a second attack line, so its printed bonus is trimmed by
    hand the way `Attack.bonus_for` trims the header's.

    The two failed saves are a chain of `escalate`, each step ending the one
    before it, so the victim never carries two of these and never gets two
    throws against one dose. The -5 on the last throw is `save_mod`, which is
    the generic `c.condition`'s parameter -- the shortcuts take none.
    """
    me = c.me
    spent: dict[str, int] = {"done": 0}

    def bite(ev: Hit) -> None:
        victim = ev.target
        if ev.attacker != me or spent["done"]:
            return
        if Keyword.WEAPON not in keywords_of(ev.power):
            return
        spent["done"] = 1
        if not c.attack(c.world.scaling.trim(16, c.level), FORT, on=victim):
            return

        def out_cold(eff: Effect) -> None:
            c.world.effects.end(eff, "worsened")
            c.condition(
                Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=eff.owner, save_mod=-5
            )

        def sapped(eff: Effect) -> None:
            c.world.effects.end(eff, "worsened")
            c.condition(
                Condition.WEAKENED, until=When.SAVE_ENDS, on=eff.owner,
                escalate=out_cold,
            )

        hold = c.penalty("attack", 2, on=victim, until=When.SAVE_ENDS)
        if hold is not None:
            hold.escalate = sapped

    c.watch(Hit, bite, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3828a4",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.in_zone(label=)",),
)
def m3828a4(c: Cast) -> None:
    """Two clauses and neither can be laid.

    The first is about a zone another row (m43) puts on the board: this
    creature is not blinded inside it and the zone does not block its line of
    sight. Nothing can ask whether a creature is standing in *somebody
    else's* zone -- `c.in_my_aura` reads the caster's own auras and
    `c.conjurations` hands back ids with no membership test -- so the gate
    the first half needs cannot be written, and laying the immunity ungated
    would be strictly stronger than print.

    The second is a type word other stat blocks' rows read, and that word is
    a printed name. `c.set_origin` is the verb and nothing is missing from
    the engine, so it names no symbol; the brief printed the word, which is a
    leak, and the report says so.
    """


# ==========================================================================
# m3921
# ==========================================================================


@power(
    "m3921a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d8", 5),
)
def m3921a0(c: Cast) -> None:
    """The printed critical is an expression rather than the maximised line,
    so it is its own packet -- and `c.flat(c.roll(...))` rather than
    `c.damage`, which would hand back the maximum of dice meant to be
    rolled."""
    if not c.strike():
        return
    if c.crit:
        c.flat(c.roll("2d8") + 13)
    else:
        c.hit()
    c.damage("1d8", dtype=DamageType.FIRE)
    c.mark(until=When.EONT)


@power(
    "m3921a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3921a1(c: Cast) -> None:
    """The printed line names a ref belonging to no stat block in the tree,
    and is read as this creature."""
    if c.strike():
        c.hit()
        c.pull(2)
        c.ongoing(5, DamageType.FIRE)


@power(
    "m3921a2",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m3921a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. An extra rolled die
    rather than a flat number, and the mark is asked of the creature being
    hit -- read off the modifier context, the only place the damage side
    names it."""
    me = c.me
    c.bonus(
        "damage", 0, dice="1d8", dtype=DamageType.FIRE, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.marked(on=ctx["target"]),
    )


# ==========================================================================
# m4421
# ==========================================================================


@power(
    "m4421a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 2),
)
def m4421a0(c: Cast) -> None:
    """Every printed ref on this stat block belongs to another one -- a
    variant block printing its parent's ids, which the database's
    cross-reference pass lost. Each is read as this creature."""
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m4421a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 2),
)
def m4421a1(c: Cast) -> None:
    """Half of what it dealt, which is what actually came off hit points --
    `c.hit` returns that, after resistance and temporary hit points, rather
    than what the dice said."""
    if c.strike():
        c.heal(c.hit() // 2, on=c.me)


@power(
    "m4421a2",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=REF, printed=14),
)
def m4421a2(c: Cast) -> None:
    """No damage line: the blindness is the whole of the hit, and the
    teleport is an Effect that happens whether anything was hit -- so it goes
    on the last target, after the burst has resolved."""
    if c.strike():
        c.blinded(until=When.EONT)
    if c.last:
        c.teleport(5)


@power(
    "m4421a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC),
)
def m4421a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.SAVE_ENDS)


@power(
    "m4421a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
)
def m4421a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it can burn instead of
    cut, and it can press the blow home at a cost.

    Both halves are choices made as the attack is declared, which is the last
    moment the penalty can still reach the roll and the first at which there
    is an attack to ask about. The retype is `DamageRolled.dtype` written in
    the interrupt window -- the field is read back, so setting it changes the
    type that lands -- and the four extra is added to the same packet rather
    than granted as a modifier, which would be untyped and ride along with
    whatever else was going.

    `once=True` is what spends the penalty on the roll it was taken for.
    """
    me = c.me
    chosen = {"radiant": False, "press": False}

    def decide(ev: AttackDeclared) -> None:
        if ev.attacker != me:
            return
        chosen["radiant"] = c.may("deal radiant damage", who=me)
        chosen["press"] = c.may(
            "take -2 to the roll for 4 extra radiant damage", who=me, default=False
        )
        if chosen["press"]:
            c.penalty("attack", 2, on=me, until=When.EOT, once=True)

    def burn(ev: DamageRolled) -> None:
        if ev.source != me:
            return
        if chosen["radiant"] or chosen["press"]:
            ev.dtype = DamageType.RADIANT
        if chosen["press"]:
            ev.amount += 4
            chosen["press"] = False

    c.watch(
        AttackDeclared, decide, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} choice",
    )
    c.watch(
        DamageRolled, burn, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=c.ref,
    )


@power(
    "m4421a5",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m4421a5(c: Cast) -> None:
    """It takes the wound and the affliction both.

    "Takes up to 25 damage" is capped at what it can pay and still stand: the
    printed line is a transfer, not a suicide. The condition moves as a whole
    effect -- `c.transfer` carries the hold intact -- because a condition is
    never loose in the engine, it is always something an effect is holding
    up.
    """
    me, mate = c.me, c.target
    health = c.world.get(me, Health)
    if mate is None or mate == me or health is None:
        return
    amount = min(25, max(0, health.hp - 1))
    if amount <= 0:
        return
    c.flat(amount, on=me)
    c.heal(amount, on=mate)
    carried = [eff for eff in c.world.effects.of(mate) if eff.conditions]
    labels = sorted({eff.label for eff in carried})
    picked = c.choose(labels, f"{c.ref}: which condition it takes on") if labels else None
    if picked is None:
        return
    for eff in carried:
        if eff.label == picked:
            c.transfer(eff, to=me)
            break


_M4421_ROLLED = "the m4421 makes an attack roll and dislikes the result"


@power(
    "m4421a6",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4421_ROLLED,
    on=Trigger(AttackRolled, when=_disliked_my_roll, text=_M4421_ROLLED),
)
def m4421a6(c: Cast) -> None:
    """A die added to a roll already made.

    A free action is `Window.AFTER` of `AttackRolled`, and that is still in
    time: `resolve.attack` re-reads the defence and recomputes the outcome
    from `result.total` only once the whole window has closed. The number
    goes onto the live result *and* onto the announcement, so the log shows
    the roll that was actually judged.

    A skill check and an ability check are not things the engine rolls, and
    are noted.
    """
    ev = c.trigger
    result = getattr(ev, "result", None)
    if result is None:
        return
    extra = c.roll("1d6")
    result.total += extra
    ev.total += extra
    ev.bonus += extra
    c.note(f"m4421a6: it adds {extra} to the roll, and to checks it cannot make")


# ==========================================================================
# m5220
# ==========================================================================


@power(
    "m5220a0",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5220a0(c: Cast) -> None:
    """It gets back up unless fire or radiant put it down, and only once.

    `Dropped` says who struck the blow and not what with, so the types are
    taken off the `DamageApplied` immediately before it -- which is the blow
    that crossed the line and the only one that can be. `c.revives_unless` is
    the declaration that stops the policy writing a body at 0 hit points off;
    the watches are what actually stand it up, and both are needed or the row
    audits silent.

    The printed rise is deferred to the start of its next turn. It is taken
    inside the same window instead, which is level 2's reading: nothing in
    the engine owes a corpse an action, and a body that waits a round is one
    `threat_removed` has already discounted. It falls prone, as printed.
    """
    me = c.me
    c.revives_unless(DamageType.FIRE, DamageType.RADIANT, on=me)
    last: dict[str, bool] = {"finished": False}
    risen: dict[str, int] = {"count": 0}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            last["finished"] = bool(
                {DamageType.FIRE, DamageType.RADIANT} & set(ev.types())
            )

    def rise(ev: Dropped) -> None:
        if ev.actor != me or last["finished"] or risen["count"]:
            return
        risen["count"] += 1
        if c.reanimate(on=me, hp=15):
            c.prone(on=me)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


@power(
    "m5220a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m5220a1(c: Cast) -> None:
    """The mark is a printed Effect rather than a Hit rider, so it lands
    whether the blow did."""
    if c.strike():
        c.hit()
    c.mark(until=When.EONT)


@power(
    "m5220a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10, dtype=DamageType.NECROTIC),
    requires_text="the m5220 must be wielding a longsword",
)
def m5220a2(c: Cast) -> None:
    """"Instead immobilized and dazed" is one hold carrying both, not two:
    neither is save-ends here, but one hold is what the printed sentence is
    and it expires on one clock.

    The weapon Requirement is `requires_text` only; a monster's weapon is not
    an object the engine holds.
    """
    if not c.strike():
        return
    c.hit()
    if c.marked():
        c.condition(Condition.IMMOBILIZED, Condition.DAZED, until=When.EONT)
    else:
        c.immobilized(until=When.EONT)


@power(
    "m5220a3",
    level=11,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5220a3(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m5391
# ==========================================================================


@power(
    "m5391a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("4d6", 5),
)
def m5391a0(c: Cast) -> None:
    """"The target's marks on the m5391's allies end" is read off the holds
    themselves: a mark is a relation laid by an effect, and the effect names
    its source, so the ones to end are the marks whose source is the victim
    and whose owner is on this side."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    for mate in [c.me, *c.allies()]:
        for eff in list(c.world.effects.of(mate)):
            if eff.source == victim and "mark" in eff.label and not eff.ended:
                c.world.effects.end(eff, f"{c.ref}: the mark is broken")


@power(
    "m5391a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d6", 5),
)
def m5391a1(c: Cast) -> None:
    """`c.cannot_shift` beside the slow: the printed line takes the shift away
    and leaves the walk, which the slow has already shortened."""
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)
        c.cannot_shift(until=When.EONT)


@power(
    "m5391a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("5d8", 6, kind=LIMITED),
)
def m5391a2(c: Cast) -> None:
    """The printed "Recharge if the power misses" is a sentence on top of the
    die the database files, and the two only ever agree to give the row back
    sooner.

    The daze and the saving-throw penalty are one hold, because the card says
    "save ends **both**" -- `save_mod` is the generic `c.condition`'s
    parameter and the shortcuts take none. The aftereffect hangs off that
    hold, whichever way it ended.
    """
    me = c.me
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == "m5391a2")
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    hold = c.condition(Condition.DAZED, until=When.SAVE_ENDS, save_mod=-2)
    if hold is not None:
        hold.on_end.append(
            lambda: c.grants_advantage(until=When.SAVE_ENDS, on=victim, to="team")
        )


@power(
    "m5391a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(1),
    target=ONE_ALLY,
)
def m5391a3(c: Cast) -> None:
    """One of two things, and which one depends on what the ally is carrying.

    The saving throw is handed out by name -- `c.save(against=...)` picks
    which save-ends hold is being answered, rather than whichever is found
    first, which may well be a burn when the row means the daze.
    """
    mate = c.target
    if mate is None or mate == c.me:
        return
    loose = [
        eff
        for eff in c.world.effects.of(mate)
        if eff.when is When.SAVE_ENDS
        and not eff.ended
        and any(cond in LOOSENABLE for cond in eff.conditions)
    ]
    if loose and c.may("shake the hold off instead of standing", who=mate):
        c.save(on=mate, against=loose[0].label)
        return
    c.grant_action("stand", FREE, on=mate)


@power(
    "m5391a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    once_per_round=True,
)
def m5391a4(c: Cast) -> None:
    c.mark(until=When.EONT)


@power(
    "m5391a5",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5391a5(c: Cast) -> None:
    """`c.resist` with no type is resistance to everything, which is what
    "resist 10 to all damage" is."""
    c.resist(10, until=When.EONT, on=c.me)


# ==========================================================================
# m5740
# ==========================================================================


@power(
    "m5740a0",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5740a0(c: Cast) -> None:
    """"+1 for each ally adjacent, up to +4" written as four gated bonuses of
    one kind.

    Two modifiers of the same kind do not add -- the larger wins -- so laying
    +1, +2, +3 and +4 each gated on "at least that many allies beside me"
    comes to exactly the printed number and recomputes itself every time a
    defence is read. A single modifier cannot do it: its value is fixed when
    it is laid and the count changes all fight.

    `kind="power"` because the card prints the word.
    """
    me = c.me

    def beside(least: int) -> Any:
        def gate(_ctx: dict[str, Any]) -> bool:
            close = sum(
                1 for mate in c.allies() if distance_between(c.world, me, mate) <= 1
            )
            return close >= least
        return gate

    for count in (1, 2, 3, 4):
        c.bonus(AC, count, on=me, until=When.ENCOUNTER, kind="power", when=beside(count))


@power(
    "m5740a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m5740a1(c: Cast) -> None:
    """The bloodied bonus is taken locally with `plus=`: an at-will laying a
    standing modifier every time it is used stacks one on each swing."""
    if c.strike(plus=2 if c.bloodied(on=c.me) else 0):
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m5740a2",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    once_per_round=True,
    attack=Attack(vs=AC, printed=16),
    dropped=("Target.kind",),
)
def m5740a2(c: Cast) -> None:
    """No damage line: the daze is the whole of the hit.

    "One creature marked by the m5740" is narrower than any `Target` can say,
    so the row is aimed at one of its own marks rather than discarded when
    the chooser hands it somebody else.
    """
    victim = _restricted_to(c, 1, lambda f: c.marked(on=f))
    if victim is None:
        return
    if c.strike(on=victim, plus=2 if c.bloodied(on=c.me) else 0):
        c.dazed(until=When.EONT, on=victim)


@power(
    "m5740a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
)
def m5740a3(c: Cast) -> None:
    """It names a target and then comes for it.

    "If the target doesn't end its next turn adjacent" is answered on that
    creature's `TurnEnd`, which is the one moment the printed condition can
    be read -- and the charge happens there, as a free action, so the flag
    goes up by hand the way every charge in this file does. `c.no_provoke` on
    the m5740 is the printed waiver for the run.

    The printed "Recharge when first bloodied" is a sentence on top of the
    die the database files.
    """
    me, victim = c.me, c.target
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if victim is None:
        return
    c.mark(until=When.EONT, on=victim)
    once: dict[str, int] = {"spent": 0}

    def settled(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim or once["spent"]:
            return
        once["spent"] = 1
        if not alive(c.world, victim) or distance_between(c.world, me, victim) <= 1:
            return
        c.no_provoke(on=me, until=When.EOT)
        _charge(c, victim, lambda: c.basic(on=victim))

    c.watch(TurnEnd, settled, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "m5740a4",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("1d6", 6, dtype=DamageType.POISON, kind=LIMITED),
)
def m5740a4(c: Cast) -> None:
    if c.strike(plus=2 if c.bloodied(on=c.me) else 0):
        c.hit()


# ==========================================================================
# m6123
# ==========================================================================


@power(
    "m6123a0",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6123a0(c: Cast) -> None:
    """An aura 2, and anything of its that walks out of it pays for it.

    `Moved` rather than `ZoneExited`: it is the only movement event carrying
    `from_`, so it is the only one that can say the creature *was* inside and
    now is not, and its `kind_` tells a walk from a shove -- which is the
    whole of "willingly". `ZoneExited` carries neither.
    """
    me = c.me
    c.aura(2, label=c.ref, until=When.ENCOUNTER, on=me)

    def stepped_out(ev: Moved) -> None:
        who = ev.actor
        if who == me or not _my_mark(c.world, me, who):
            return
        if getattr(ev, "kind_", "") in FORCED_KINDS:
            return
        if _gap_from(c, ev.from_, me) > 2 or distance_between(c.world, me, who) <= 2:
            return
        c.provoke(me, on=who, why=c.ref)

    c.watch(Moved, stepped_out, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6123a1",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6123a1(c: Cast) -> None:
    """`kind` left off: the printed line is about every sort of rough
    ground."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m6123a2",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6123a2(c: Cast) -> None:
    """An extra throw at the top of its own turn. `c.save` follows the target
    by default, so `on=c.me` is what makes it this creature's."""
    me = c.me

    def shrug(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me and c.may("try to shake it off", who=me):
            c.save(on=me)

    c.watch(TurnStart, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6123a3",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6123a3(c: Cast) -> None:
    """`c.threatens` lays two keys and both are needed: the flag says this
    creature's opportunity window is not fixed at one square, and the reach
    says how far."""
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m6123a4",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6123a4(c: Cast) -> None:
    """Deliberately inert, and not a gap.

    The printed line says this creature and its mount are a single being and
    cannot be separated. On this board it already is one: the stat block is
    one entity, no second creature carries it, and nothing in the engine
    unseats a rider -- `c.ride` puts one on and there is no verb that takes
    one off. So there is nothing for the prohibition to prevent.
    """
    c.note("m6123a4: one being, so nothing can separate it from its mount")


@power(
    "m6123a5",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m6123a5(c: Cast) -> None:
    """The mark is asked *before* it is laid: "if the target is already marked
    by the m6123" is about the state the blow found, and renewing the mark
    first would make it true every time."""
    if not c.strike():
        return
    c.hit()
    again = c.marked()
    c.mark(until=When.EONT)
    if again:
        c.ongoing(5, DamageType.FIRE)


@power(
    "m6123a6",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m6123a6(c: Cast) -> None:
    """Two of its own at-will blows, so the numbers live in m6123a5."""
    for _ in range(2):
        c.use_power("m6123a5", on=c.target)


@power(
    "m6123a7",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.FIRE],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d12", 9, dtype=DamageType.FIRE, kind=LIMITED),
)
def m6123a7(c: Cast) -> None:
    """The slide is measured from this creature, which is what `anchor` is
    for: "to a square adjacent to him" is a destination and not a
    direction."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.ongoing(5, DamageType.FIRE)
    c.slide(2, on=victim, anchor=c.here)


_M6123_BURNED = "the m6123 takes fire damage"


@power(
    "m6123a8",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M6123_BURNED,
    on=Trigger(DamageApplied, when=_burned_me, text=_M6123_BURNED),
)
def m6123a8(c: Cast) -> None:
    c.temp_hp(15, on=c.me)


# ==========================================================================
# m6144
# ==========================================================================


@power(
    "m6144a0",
    level=11,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6144a0(c: Cast) -> None:
    c.threatens(3, on=c.me, until=When.ENCOUNTER)


@power(
    "m6144a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m6144a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6144a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 5),
)
def m6144a2(c: Cast) -> None:
    """Holding somebody costs it its reach and this row.

    The hold carries the restraint and the burn together, which is one saving
    throw for the printed "save ends both". The three consequences are
    written as what they are: this row is forbidden, the threatening-reach
    flag m6144a0 raised is cancelled by a penalty of the same size, and the
    reach bonus it laid is cancelled the same way -- which brings melee range
    back to 1 square, as printed. All three are lifted when the hold ends.
    """
    me = c.me
    if not c.strike():
        return
    c.hit()
    held = c.condition(
        Condition.RESTRAINED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED)
    )
    if held is None:
        return
    busy = [
        c.forbid("m6144a2", on=me, until=When.ENCOUNTER),
        c.penalty("threatening_reach", 1, on=me, until=When.ENCOUNTER),
        c.penalty("reach", 2, on=me, until=When.ENCOUNTER),
    ]

    def let_go() -> None:
        for eff in busy:
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "the grip comes loose")

    held.on_end.append(let_go)


@power(
    "m6144a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_ALLY,
    once_per_round=True,
)
def m6144a3(c: Cast) -> None:
    """No range is printed beside the slide, so the burst is written at the
    distance the slide covers -- the only number the line gives."""
    mate = c.target
    if mate is not None and mate != c.me:
        c.slide(3, on=mate)
