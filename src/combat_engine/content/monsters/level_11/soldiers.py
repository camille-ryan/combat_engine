"""Monster abilities, level 11: the soldiers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=17)` and `Damage("2d8", 3)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the ten levels below are kept: a row filed under an
action heading that is plainly a trait is declared `ActionType.NONE` and
armed once when the fight starts; a helper written for an earlier level is
imported rather than copied; a stat block that prints no range at all means
melee 1; and a row whose printed Effect *is* a charge raises the flag by
hand, because `c.charge_at` reaches its swing through `use` and the row it
would reach for is the one already in flight.

Six things this file had to settle.

**The window on `AttackRolled` closes after the whole window, not after each
listener.** `resolve.attack` announces the roll, lets both windows run, and
*then* re-reads the defence and recomputes the outcome from `result.natural`
and `result.total`. So a free action answering its own roll -- m2870a5 --
still lands in time to change it, and the printed free action does not have
to be reinterpreted as an interrupt to work. The same fact is why m227a3 is
declared on `AttackRolled` with `would_hit_me` rather than on `Hit`: "when
hit by an attack" is decided in that window, and a defence raised after
`Hit` is announced has nothing left to do.

**"With its first action on its next turn" spans three moments.** m2947a1's
secondary needs where the victim started -- no event carries that, so it is
noted at `TurnStart` -- and then what the first action *was*. `ActionSpent`
is announced before the action happens, so an action that is not a move
settles it there and then, while a move has to wait for the `MoveEnd` that
is the first moment the new range is knowable.

**An automatic critical is written onto the live result.** m227a4 marks a
creature and the *next melee attack against it* crits. The outcome is
recomputed from the `AttackResult` after the roll's window closes, and
`c.hit()` reads `c.crit` off the same object, so the one place that can say
this is `ev.result.critical` in the `Hit`'s interrupt window -- the
arrangement `c.autohit` uses for the sibling sentence. There is no `Cast`
method for it; see the report.

**Two bonuses of the same kind do not add -- the larger wins.** m4863a1's
"-2 to all defences" is four separate modifiers, one per defence, and each
is *replaced* rather than laid beside its predecessor when a second peal of
thunder lands inside the same duration.

**Losing a weapon is losing the rows it swings.** m338a1 prints a
Requirement about a weapon the engine has no name for and, in the same
breath, says the creature cannot use that weapon while the effect lasts.
`c.forbid` on both rows says the whole of it: the Requirement is then
implicit, because a forbidden row is one `usable` already refuses.

**Swallowing, again.** m431a1 takes a creature out of the fight the way
level 10's two did: `Condition.REMOVED` is on the board and out of it, the
way back hangs on the hold's own ending rather than on a clock, and the
printed radiant clause is a saving throw handed out by name -- `c.save`
takes `against=` so the trapped creature saves against the trap and not
against whatever else it happens to be carrying.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_06.controllers import _is_humanoid, _living
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.brutes import SMALL_ENOUGH
from combat_engine.content.monsters.level_09.brutes import _put_beside
from combat_engine.content.monsters.level_10.skirmishers import EVERY_DEFENCE
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
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
    Dropped,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Movement,
    Ranged,
    Usage,
    When,
    Window,
    World,
    by_melee,
    power,
    use,
    would_hit_me,
)
from combat_engine.engine.events import ActionSpent, DamageRolled, TurnStart
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, distance_between, team
from combat_engine.engine.triggers import Trigger

#: The damage types m338a3 answers. Written out because the printed line
#: names five of the eleven and the trigger has to tell them apart.
ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _renew_all(
    c: Cast, held: list[Effect], make: Any
) -> None:
    """Replace a set of holds a row keeps re-earning, rather than stacking it.

    `_renew` a few levels down does this for one effect; "a -2 penalty to all
    defences" is four, and four of one kind do not add -- the larger wins --
    so a second peal of thunder inside the same duration would otherwise be
    four holds doing the work of one and expiring on four different clocks.
    """
    for old in held:
        if not old.ended:
            c.world.effects.end(old, "renewed")
    held.clear()
    held.extend(eff for eff in make() if eff is not None)


def _charge(c: Cast, victim: int, blow: Any) -> None:
    """Run at somebody and swing this row's own printed line at them.

    `c.charge_at` reaches the swing through `use`, and the row it would
    reach for is the one already in flight -- which a row that *is* the
    charge always is. So the flag goes up by hand, `c.run_at` walks, and the
    header rolls. The flag is what puts `charge` on the attack events and in
    both modifier contexts, which is what every charge rider reads, and it
    comes back down afterwards.
    """
    c.charge = True
    try:
        c.run_at(victim)
        blow()
    finally:
        c.charge = False


def _shifted_away_from_me(world: World, me: int, ev: MoveEnd) -> bool:
    """An adjacent enemy shifted out of reach, by a means I can follow.

    `MoveEnd` rather than `MoveStart`, which fires before the first step and
    so answers about the square the creature has not left yet. Having *been*
    adjacent is read from the distance it covered: a shift is one square, so
    a creature that is now two away was beside me when it started.

    The second half of the printed line is the movement mode. `Movement.using`
    is only written by a walk, so the mode a shift used is recomputed the way
    `movement.shift` computes it -- `mode_of`, which takes the best the
    creature has -- and the row is refused when that is something this
    creature cannot do.
    """
    from combat_engine.engine.movement import mode_of

    if ev.kind_ != "shift" or ev.actor == me:
        return False
    if team(world, ev.actor) is team(world, me):
        return False
    gap = distance_between(world, me, ev.actor)
    if gap <= 1 or gap > 2:
        return False
    mode = mode_of(world, ev.actor, None)
    mine = world.get(me, Movement)
    return mode == "walk" or bool(mine is not None and mine.modes.get(mode))


def _step_beside(c: Cast, victim: int) -> bool:
    """Shift one square, and finish next to that creature.

    `c.shift` with no `to` offers the decider every square in range, which is
    useless for a printed line that says where the step has to end.
    """
    from combat_engine.engine.query import squares

    me = c.me
    theirs = squares(c.world, victim)
    mine = squares(c.world, me)
    options = sorted(
        sq
        for sq in c.world.reachable_squares(me, 1)
        if sq not in mine and min(distance_between_sq(sq, t) for t in theirs) <= 1
    )
    if not options:
        return False
    return c.shift(to=c.world.decide(me, "shift", options, f"{c.ref}: staying with it"))


def distance_between_sq(a: tuple[int, int], b: tuple[int, int]) -> int:
    from combat_engine.engine.grid import distance

    return distance(a, b)


def _move_away_or_be_dazed(c: Cast, victim: int) -> None:
    """"Move away with its first action on its next turn, or be dazed."

    Three moments, because the printed sentence spans three. The turn opens
    and the range is noted -- nothing on any event carries where a creature
    started. The first action is spent, and `ActionSpent` is announced
    *before* the action happens, so an action that is not a move settles it
    at once and one that is has to wait. And the move ends, which is the
    first moment the new range is knowable.
    """
    me = c.me
    began: dict[str, Any] = {"at": 0, "armed": False, "moving": False}

    def opened(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim:
            return
        began["at"] = distance_between(c.world, me, victim)
        began["armed"] = True
        began["moving"] = False

    def acted(ev: ActionSpent) -> None:
        if ev.actor != victim or not began["armed"]:
            return
        if ev.cost is ActionType.MOVE:
            began["moving"] = True
            return
        began["armed"] = False
        c.dazed(until=When.EOT, on=victim)

    def landed(ev: MoveEnd) -> None:
        if ev.actor != victim or not began["armed"] or not began["moving"]:
            return
        began["armed"] = False
        if distance_between(c.world, me, victim) <= began["at"]:
            c.dazed(until=When.EOT, on=victim)

    for event, fn, tag in (
        (TurnStart, opened, "turn"),
        (ActionSpent, acted, "action"),
        (MoveEnd, landed, "move"),
    ):
        c.watch(event, fn, until=When.EOTNT, on=victim, label=f"{c.ref} {tag}")


# ==========================================================================
# m227
# ==========================================================================


@power(
    "m227a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 3),
)
def m227a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m227a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d8", 3),
)
def m227a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.EONT)


_M227_SLIPPED = "an adjacent enemy shifts away from the m227"
_M227_STRUCK = "the m227 is hit by an attack"


@power(
    "m227a2",
    level=11,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M227_SLIPPED,
    on=Trigger(MoveEnd, when=_shifted_away_from_me, text=_M227_SLIPPED),
)
def m227a2(c: Cast) -> None:
    """It goes with them.

    Declared with no target and aimed off the trigger: the dispatcher only
    points a row that takes one enemy, and this one is about the creature
    that just slipped away rather than whoever is nearest.
    """
    who = getattr(c.trigger, "actor", None)
    if who is not None and alive(c.world, who):
        _step_beside(c, who)


@power(
    "m227a3",
    level=11,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M227_STRUCK,
    on=Trigger(AttackRolled, when=would_hit_me, text=_M227_STRUCK),
)
def m227a3(c: Cast) -> None:
    """Four modifiers, because "a +2 bonus to all defenses" is four numbers
    and the engine holds each defence separately -- one modifier named "all
    defenses" would be a bonus to nothing.

    Declared on `AttackRolled` rather than on `Hit`: the defence is read
    *again* once that window closes, which is what lets a guard raised here
    turn the blow aside, and `would_hit_me` is the engine's spelling of
    "when hit by an attack" at the one moment there is still something to do
    about it.
    """
    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.EONT, on=c.me)


@power(
    "m227a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
)
def m227a4(c: Cast) -> None:
    """It picks out the weak point, and the next blow goes straight in.

    No attack roll: the printed line rolls none. The +5 goes onto whoever
    swings, at the moment the swing is announced, because the printed bonus
    belongs to the attack rather than to any one attacker -- anybody's melee
    attack against this creature is "the next melee attack made against the
    target".

    The critical is written onto the live `AttackResult` in the `Hit`'s
    interrupt window. That is the only place it can be said: the outcome is
    recomputed from that object after the roll, and `c.hit()` reads `c.crit`
    off the same one, so rigging the event's own field alone would change
    the log and not the damage. Both are set, so the log agrees with what
    lands. `c.autohit` says the sibling sentence the same way; there is no
    `Cast` method for this one, and the report asks for it.

    Spent by the first melee attack that resolves, hit or miss, which is
    what "the next" means.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    held: list[Effect] = []

    def spend(why: str) -> None:
        for eff in list(held):
            if not eff.ended:
                c.world.effects.end(eff, why)
        held.clear()

    def sharpen(ev: AttackDeclared) -> None:
        if ev.target != victim or not by_melee(c.world, me, ev):
            return
        boon = c.bonus("attack", 5, on=ev.attacker, until=When.EOT, kind="power")
        if boon is not None:
            held.append(boon)

    def straight_in(ev: Hit) -> None:
        if ev.target != victim or not by_melee(c.world, me, ev):
            return
        ev.critical = True
        result = getattr(ev, "result", None)
        if result is not None:
            result.critical = True
        spend("the blow went in")

    def wasted(ev: Miss) -> None:
        if ev.target == victim and by_melee(c.world, me, ev):
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


# ==========================================================================
# m244
# ==========================================================================


@power(
    "m244a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6),
)
def m244a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m244a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m244a1(c: Cast) -> None:
    """The size is asked of the victim rather than assumed: the shove and the
    fall are both printed as conditional on it."""
    victim = c.target
    if victim is None:
        return

    def blow() -> None:
        if not c.strike(on=victim):
            return
        c.hit(on=victim)
        if c.size_of(victim) in SMALL_ENOUGH:
            c.push(3, on=victim)
            c.prone(on=victim)

    _charge(c, victim, blow)


@power(
    "m244a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 6),
)
def m244a2(c: Cast) -> None:
    """It walks over whoever is standing in the way.

    `c.overrun` is the only thing that reports who was trampled, and who was
    trampled is exactly what the printed line attacks. Called bare: with no
    destination it ranks the reachable squares by how many enemies the line
    crosses, so the walk goes through people.

    No `c.no_provoke`: this printed line says the movement provokes. Ending
    in an unoccupied space is the trample's own rule and `movement.overrun`
    already shuffles it clear.

    Declared with no target: the blows are aimed by the walk.
    """
    for victim in c.overrun():
        if victim not in c.enemies() or not alive(c.world, victim):
            continue
        if c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)


@power(
    "m244a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 7, dtype=DamageType.POISON, kind=LIMITED),
)
def m244a3(c: Cast) -> None:
    """Stone, by degrees.

    The two failed saves are a chain of `escalate`, each step ending the one
    before it, so the victim never carries two of these and never gets two
    saving throws against one breath. Stone is the end of the chain and
    carries no escalation of its own; it runs to the end of the fight,
    because nothing printed lifts it.

    The daze and the slow are one hold carrying both conditions -- applied
    separately the victim would get two saving throws against a thing the
    card says it saves against once.

    "Its own kind are immune" is asked of the stat block a creature is,
    which is an id and not a name. `EACH_ENEMY` already leaves its friends
    out; this covers the one on the other side.
    """
    victim = c.target
    if victim is None or _ref_of(c, victim) == _ref_of(c, c.me):
        return
    if not c.strike():
        return
    c.hit()

    def stone(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=eff.owner)

    def stiffen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=eff.owner, escalate=stone
        )

    c.condition(
        Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS, escalate=stiffen
    )


# ==========================================================================
# m2870
# ==========================================================================


@power(
    "m2870a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 2),
)
def m2870a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m2870a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("2d10", 2, kind=LIMITED),
)
def m2870a1(c: Cast) -> None:
    """Half of what it dealt, which is what actually came off hit points --
    `c.hit` returns that, after resistance and temporary hit points, rather
    than what the dice said.

    The printed recharge is a sentence on top of the die the database files,
    and the two only ever agree to give the row back sooner.
    """
    me = c.me
    _recharge_on(c, Hit, lambda ev: ev.attacker == me and ev.power == "m2870a0")
    if c.strike():
        c.heal(c.hit() // 2, on=me)


@power(
    "m2870a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m2870a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.SAVE_ENDS)


@power(
    "m2870a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
)
def m2870a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it can burn instead of
    cut, and it can press the blow home at a cost.

    Both halves are choices made as the attack is declared, which is the
    last moment the penalty can still reach the roll and the first at which
    there is an attack to be asked about. The retype is `DamageRolled.dtype`
    written in the interrupt window -- the field is read back now, so setting
    it changes the type that lands -- and the four extra is added to the same
    packet rather than granted as a modifier, which would be untyped and add
    to whatever else was riding along.

    The penalty is spent on the roll it was taken for. `once=True` is what
    does that for an attack modifier.
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
            c.penalty("attack", 2, on=me, until=When.EOT, kind="untyped", once=True)

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
    "m2870a4",
    level=11,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m2870a4(c: Cast) -> None:
    """It takes the wound and the affliction both.

    "Takes up to 25 damage" is capped at what it can pay and still stand:
    the printed line is a transfer, not a suicide. The condition moves as a
    whole effect -- ended on the ally and laid again on the m2870 with the
    same clock -- because a condition is never loose in the engine, it is
    always something an effect is holding up.
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
    carried = sorted({eff.label for eff in c.world.effects.of(mate) if eff.conditions})
    picked = c.choose(carried, f"{c.ref}: which condition it takes on") if carried else None
    if picked is None:
        return
    for eff in list(c.world.effects.of(mate)):
        if eff.label != picked or not eff.conditions:
            continue
        c.condition(*eff.conditions, until=eff.when, on=me)
        c.world.effects.end(eff, f"{c.ref}: it takes the condition on")
        break


_M2870_ROLLED = "the m2870 makes an attack roll and dislikes the result"


def _disliked_my_roll(world: World, me: int, ev: AttackRolled) -> bool:
    """My own roll, and one that is about to come up short.

    "Dislikes the result" lives in the predicate rather than in the body:
    this is a once-a-fight row, and a trigger that is true of every roll
    would offer it -- and spend it -- on a blow that was landing anyway. The
    live `AttackResult` rides on the event, which is the only place the
    provisional outcome exists.
    """
    result = getattr(ev, "result", None)
    return ev.attacker == me and result is not None and not result.hit


@power(
    "m2870a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2870_ROLLED,
    on=Trigger(AttackRolled, when=_disliked_my_roll, text=_M2870_ROLLED),
)
def m2870a5(c: Cast) -> None:
    """A die added to a roll already made.

    A free action is `Window.AFTER` of `AttackRolled`, and that is still in
    time: `resolve.attack` re-reads the defence and recomputes the outcome
    from `result.total` only once the whole window has closed. So the
    printed free action needs no reinterpretation as an interrupt -- the
    number is added to the live result and to the announcement, so the log
    shows the roll that was actually judged.

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
    c.note(f"m2870a5: it adds {extra} to the roll, and to skill checks it cannot make")


# ==========================================================================
# m2947
# ==========================================================================


@power(
    "m2947a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d12", 7),
)
def m2947a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2947a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=17),
    damage=Damage("2d8", 7, kind=LIMITED),
)
def m2947a1(c: Cast) -> None:
    """The secondary is a second attack line, and a second line's printed
    bonus is trimmed by hand the way `Attack.bonus_for` trims the header's.

    The printed recharge is a sentence on top of the die the database files,
    and the two only ever agree to give the row back sooner.
    """
    me, victim = c.me, c.target
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if victim is None or not c.strike():
        return
    c.hit()
    c.slide(2, on=victim)
    if c.attack(c.world.scaling.trim(15, c.level), WILL, on=victim):
        _move_away_or_be_dazed(c, victim)


@power(
    "m2947a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=18),
    damage=Damage("1d12", 7),
)
def m2947a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m2947a3",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m2947a3(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is the only one
    `Range` holds and the one this can shoot at without a penalty."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2947a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    once_per_round=True,
    attack=Attack(vs=WILL, printed=16),
)
def m2947a4(c: Cast) -> None:
    """No damage line: the mark is the whole of the hit.

    The second half is left as a note. Cover and concealment are computed
    between two positions at the moment of the attack, and `ignore_cover` is
    an argument to one roll rather than a state a creature can be put into,
    so there is nothing to hang "cannot benefit from cover or concealment"
    on. See the report.
    """
    if c.strike():
        c.mark(until=When.EONT)
        c.note("m2947a4: the target cannot benefit from cover or concealment")


# ==========================================================================
# m338
# ==========================================================================


@power(
    "m338a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m338a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m338a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 10),
)
def m338a1(c: Cast) -> None:
    """Pinned on the end of the weapon, which is then busy.

    The hold carries the restraint and the burn together: applied separately
    the victim would get two saving throws against a thing the card says it
    saves against once.

    The printed Requirement -- it must still have the weapon -- is not
    written as a `requires`, because the same sentence says what takes the
    weapon away: both rows are forbidden while the hold lasts, and a
    forbidden row is one `usable` already refuses. Writing the Requirement
    as well would be the same rule twice, with nothing to make the first
    half ever false.
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
        c.forbid(ref, on=me, until=When.ENCOUNTER) for ref in ("m338a0", "m338a1")
    ]

    def free_again() -> None:
        for eff in barred:
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, "the weapon comes free")

    held.on_end.append(free_again)


@power(
    "m338a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("4d6", 5, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m338a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
    else:
        c.hit(half=True)


_M338_SEARED = "the m338 takes acid, cold, fire, lightning or thunder damage"


def _an_element_landed(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and ev.amount > 0 and ev.dtype in ELEMENTS


@power(
    "m338a3",
    level=11,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M338_SEARED,
    on=Trigger(DamageApplied, when=_an_element_landed, text=_M338_SEARED),
)
def m338a3(c: Cast) -> None:
    """It learns the blow, twice a fight.

    `uses=2` is the printed "2/Encounter". The second use replaces the
    first rather than adding to it, which is the printed "or until it uses
    this again", and the hold is found by the label `c.resist` gives it.
    """
    me = c.me
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is None:
        return
    for eff in list(c.world.effects.of(me)):
        if eff.label == f"{c.ref} resist":
            c.world.effects.end(eff, "it adapts to something else")
    c.resist(10, dtype, until=When.ENCOUNTER, on=me)


# ==========================================================================
# m431
# ==========================================================================


#: The hold that is being swallowed, and the one that opens m431a2 for the
#: rest of the turn. Both are found by label rather than by relation: the
#: engine has no relation for "inside", and the printed line that opens the
#: burst is about a row having been used rather than about any state.
_M431_TRAPPED = "m431a1 trapped"
_M431_OPENED = "m431a3 opened"


def _trapped_by(world: World, me: int) -> list[int]:
    return sorted(
        {
            eff.owner
            for eff in world.effects.live.values()
            if eff.label == _M431_TRAPPED and eff.source == me and not eff.ended
        }
    )


def _has_prey(world: World, eid: int) -> bool:
    return bool(_trapped_by(world, eid))


def _can_trap(world: World, eid: int) -> bool:
    """Nothing held already, and somebody living and humanoid in range.

    A character carries no type words at all, which `_is_humanoid` reads as
    "anything that is not something else" -- the reading level 6 settled and
    the only one under which a printed "living humanoid" can ever name a
    player.
    """
    from combat_engine.engine import Cast as _Cast
    from combat_engine.engine.query import enemies

    if _trapped_by(world, eid):
        return False
    ask = _Cast(world=world, me=eid, ref="m431a1")
    return any(
        distance_between(world, eid, foe) <= 5
        and _living(ask, foe)
        and _is_humanoid(ask, foe)
        for foe in enemies(world, eid)
    )


def _opened(world: World, eid: int) -> bool:
    return any(eff.label == _M431_OPENED for eff in world.effects.of(eid))


@power(
    "m431a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m431a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m431a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d8", 7, dtype=DamageType.NECROTIC),
    requires=_can_trap,
    requires_text="the m431 must have nothing trapped and a living humanoid in range",
)
def m431a1(c: Cast) -> None:
    """It takes somebody out of the fight.

    "A living humanoid" is narrower than any `Target` can say, so the
    Requirement carries whether there is one at all and the body picks from
    the ones there are -- rather than letting `_auto_targets` choose whoever
    is nearest and miss the point of the row.

    `Condition.REMOVED` is what the engine has for a creature that is on the
    board and not in the fight. The way out hangs on the hold's own ending
    rather than on a clock, because "if it succeeds on a saving throw, it
    escapes and appears" is what the printed line measures, and the square
    is chosen then rather than now. The m431 going down ends the hold, which
    is the other printed way out.

    The stat block's vulnerability line prints a third: radiant damage hands
    the prisoner a saving throw. It has no id of its own, so it lives here,
    with the hold it is about -- and `c.save(against=...)` names which
    save-ends effect is being answered, rather than whichever is found first.
    """
    me = c.me
    edible = sorted(
        foe
        for foe in c.enemies()
        if c.distance(foe) <= 5 and _living(c, foe) and _is_humanoid(c, foe)
    )
    victim = c.choose(edible, "m431a1: which of them it takes") if edible else None
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    inside = c.world.effects.apply(
        victim, me, When.SAVE_ENDS, label=_M431_TRAPPED,
        conditions=(Condition.REMOVED,),
    )

    def spill(ev: Dropped) -> None:
        if ev.actor == me and not inside.ended:
            c.world.effects.end(inside, "the m431 is destroyed")

    def seared(ev: DamageApplied) -> None:
        if ev.target == me and ev.amount > 0 and ev.dtype is DamageType.RADIANT:
            c.save(on=victim, against=_M431_TRAPPED)

    inside.subs.append(c.world.bus.on(Dropped, spill, owner=me))
    inside.subs.append(c.world.bus.on(DamageApplied, seared, owner=me))
    inside.on_end.append(lambda: _put_beside(c, victim, me))


@power(
    "m431a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 7, dtype=DamageType.NECROTIC, half_on_miss=True),
    requires=_opened,
    requires_text="the m431 must have used m431a3 this turn",
)
def m431a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m431a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    requires=_has_prey,
    requires_text="the m431 must have a creature trapped",
)
def m431a3(c: Cast) -> None:
    """It feeds, and then either keeps what it took or spends it.

    The hold that opens m431a2 is laid before the choice is offered, because
    that row's Requirement is read when it is used and the two are the same
    turn by construction. It runs to the end of this turn, which is what
    "only on the same turn" measures.

    "Cannot be returned to life with a ritual" is not a rule the engine
    holds and is noted.
    """
    me = c.me
    held = _trapped_by(c.world, me)
    victim = c.choose(held, "m431a3: which of them it feeds on") if held else None
    if victim is None:
        return
    c.flat(10, dtype=DamageType.NECROTIC, on=victim)
    c.world.effects.apply(me, me, When.EOT, label=_M431_OPENED)
    if c.may("spend it on m431a2 rather than keep it", who=me, default=False):
        use(c.world, me, "m431a2", spend=False)
    else:
        c.heal(10, on=me)
    c.note("m431a3: a creature killed by this cannot be raised")


@power(
    "m431a4",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m431a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Four modifiers, because "a +2 bonus to all defenses" is four numbers.
    Whether it is holding anybody is asked inside the gate rather than once
    when the trait arms: the prisoner escapes and is taken again, and a
    defence is read a second time after the roll has been announced, which
    is where this has to be right.
    """
    me = c.me

    def full(_ctx: dict[str, Any]) -> bool:
        return bool(_trapped_by(c.world, me))

    for defended in EVERY_DEFENCE:
        c.bonus(defended, 2, until=When.ENCOUNTER, on=me, when=full)


# ==========================================================================
# m4863
# ==========================================================================


@power(
    "m4863a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4863a0(c: Cast) -> None:
    """Earth and rock are not in its way. `c.phasing` is exactly that, and it
    still has to stop somewhere it fits."""
    c.phasing()


@power(
    "m4863a1",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4863a1(c: Cast) -> None:
    """Thunder shakes it apart for a while.

    Four penalties, one per defence, and they are *replaced* rather than
    laid beside their predecessors when a second peal lands inside the same
    duration: two modifiers of one kind do not add, so the second set would
    be four holds doing the work of one and expiring on four clocks.
    """
    me = c.me
    held: list[Effect] = []

    def shaken(ev: DamageApplied) -> None:
        if ev.target != me or ev.amount <= 0 or ev.dtype is not DamageType.THUNDER:
            return
        _renew_all(
            c,
            held,
            lambda: [
                c.penalty(defended, 2, until=When.EONT, on=me, kind="untyped")
                for defended in EVERY_DEFENCE
            ],
        )

    c.watch(DamageApplied, shaken, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4863a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("3d8", 6),
)
def m4863a2(c: Cast) -> None:
    """`c.rooted`, not `c.immobilized`: the printed line takes the shift away
    and leaves the walk, which is the whole reason the two are different."""
    if c.strike():
        c.hit()
        c.rooted(until=When.EONT)


@power(
    "m4863a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(4),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m4863a3(c: Cast) -> None:
    """The printed recharge is a sentence on top of the die the database
    files, and the two only ever agree to give the row back sooner."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if c.strike():
        c.hit()
        c.slide(2)
        c.prone()
