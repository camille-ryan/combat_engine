"""Monster abilities, level 7: the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=12)` and `Damage("2d6", 4)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the six levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard or free
actions are plainly traits or immediate actions and are written as such; and
a secondary attack is a second attack line, so its printed bonus is trimmed
by hand the way `Attack.bonus_for` trims the header's.

Five things this file had to settle.

**"Becomes invisible until <clock>"** is a duration rather than a hiding
place, and attacking does not end it -- but `resolve.attack` clears
`HIDDEN_FROM` for whoever swung, which is the Stealth rule and the right
default for `c.hide`. So the relation is put back as it is broken, and only
the effect's own clock ends it. Level 5 did this by hand around one swing;
here it is a watch, because the clock outlives the row that set it.

**"While adjacent to any enemy, it is invisible"** is neither a clock nor a
hiding place: it is a fact about the board, so the hold is kept in step with
the board -- recounted on every step anything takes and at the top of every
turn, which between them are what change the answer, and diffed rather than
rebuilt so a creature that stays in contact is not announced as vanishing
once per square anybody walks.

**"If the target moves away before the end of its next turn"** needs both
ends of the move: `MoveEnd` carries only the arrival, and `MoveStart` fires
before the creature has moved, so the distance is taken there and compared
here. The watches are clocked on the target, which is whose next turn the
printed line names.

**"It shifts 6 squares, moving with the triggering enemy"** cannot happen
when the trigger fires -- the enemy has not moved yet, which is exactly what
`MoveStart` means. So the printed trigger is declared on `MoveStart`, where
"an enemy **adjacent to it** moves" is still true, and the shift is taken on
that same move's `MoveEnd`, which is what "as it completes the move" says.
The destination is chosen here rather than by the decider, because the
printed line says where the shift must end.

**"Save ends" on a hold whose subject is the caster.** m4922a3 makes the
*caster* invisible and the *target* rolls the save, and a save-ends effect is
clocked on whoever it sits on -- so `c.invisible` would have the caster
saving against its own concealment. The effect is applied to the target
instead, carrying the same relation, which is how level 6 wrote a grab whose
clock belonged to somebody else.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.skirmishers import _not_grabbing
from combat_engine.content.monsters.level_04.skirmishers import (
    _guarded_move,
    _until_the_grab_ends,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Usage,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.events import (
    DamageApplied,
    Event,
    Hit,
    Miss,
    Moved,
    MoveEnd,
    MoveStart,
    RelationCleared,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.query import (
    distance_between,
    has_combat_advantage,
    squares,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    both,
    by_melee,
    enemy_within,
    targets_me,
)


def _clocked_veil(c: Cast, until: When) -> Effect | None:
    """"Becomes invisible until <clock>" -- a duration, not a hiding place.

    `resolve.attack` clears `HIDDEN_FROM` for whoever swung, which is the
    Stealth rule and the right default for `c.hide`. A printed clock is not
    ended by attacking, so the relation is set again as it is broken -- only
    where the break was the swing, which is what `why` distinguishes -- and
    the watch comes down with the veil.
    """
    veil = c.invisible(until=until)
    if veil is None:
        return None
    me = c.me

    def broke(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
            return
        if ev.why == "attacked":
            c.world.relations.set(Relation.HIDDEN_FROM, me, ev.target)

    seen = c.watch(RelationCleared, broke, until=until, on=me, label=f"{c.ref} veil")
    veil.on_end.append(lambda: c.world.effects.end(seen, "the veil is down"))
    return veil


def _shift_beside(c: Cast, victim: int, squares_: int) -> bool:
    """Shift up to `squares_`, ending next to a named creature.

    `c.shift` with no `to` offers every square in range to the decider,
    which is right for "shift 6" and useless for a line that says where the
    shift has to end.
    """
    beside = spread(squares(c.world, victim), 1)
    options = sorted(
        sq for sq in c.world.reachable_squares(c.me, squares_) if sq in beside
    )
    if not options:
        return False
    where = c.world.decide(c.me, "shift", options, f"{c.ref}: stay beside it")
    return c.shift(to=where)


# --------------------------------------------------------------------------
# m451
# --------------------------------------------------------------------------


@power(
    "m451a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m451a0(c: Cast) -> None:
    """"+12, or +13 against a bloodied target" is one printed attack line
    with a conditional point on it rather than two lines, so the header
    keeps the +12 and the point goes on with `c.strike(plus=...)`.

    The secondary is a second attack line and a row carries one, so its
    printed +10 is trimmed by hand the way `Attack.bonus_for` trims the
    header's -- the row still moves with whatever scaling the fight is on.
    """
    if not c.strike(plus=1 if c.bloodied() else 0):
        return
    c.hit()
    if c.attack(c.world.scaling.trim(10, c.level), FORT):
        c.ongoing(10, DamageType.POISON)


@power(
    "m451a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m451a1(c: Cast) -> None:
    c.teleport(5)
    _clocked_veil(c, When.EONT)


@power(
    "m451a2",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m451a2(c: Cast) -> None:
    """Paid back to whoever drew blood since it last acted.

    Nothing holds "an enemy that hit it since its last turn": `Hit` is
    announced and forgotten, and this is a minor action rather than a trait
    with a watch already armed. So the log is read back -- the same place
    level 6 reads attribution from -- and it is read at the moment the
    attack is *made* rather than now, which is when the printed sentence
    asks the question and which is why the answer is a gate rather than a
    list taken here.

    Teams are compared directly: `query.enemies` filters out the dead, and
    a creature that hit it and then fell is still one that hit it.
    """
    me = c.me

    def drew_blood(who: Any) -> bool:
        if who is None or team(c.world, who) is team(c.world, me):
            return False
        for past in reversed(c.world.bus.log):
            if isinstance(past, TurnEnd) and past.actor == me and not past.ghost:
                return False
            if isinstance(past, Hit) and past.target == me and past.attacker == who:
                return True
        return False

    c.bonus(
        "attack",
        1,
        until=When.ENCOUNTER,
        on=me,
        once=True,
        when=lambda ctx: drew_blood(ctx.get("target")),
    )

    def rider(ev: Hit) -> None:
        if ev.attacker == me and drew_blood(ev.target):
            c.flat(3, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, once=True, label="m451a2")


# --------------------------------------------------------------------------
# m4905
# --------------------------------------------------------------------------


@power(
    "m4905a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4905a0(c: Cast) -> None:
    """There are no skill checks in the engine, so the whole of this aura is
    a penalty to a roll that is never made -- declared inert rather than
    given an invented mechanic."""
    c.note("m4905a0: aura 5; enemies inside take -5 to skill checks")


@power(
    "m4905a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m4905a1(c: Cast) -> None:
    """Unseen for as long as anything is standing next to it.

    Neither a clock nor a hiding place but a fact about the board, so the
    hold is kept in step with it: recounted on every step anything takes and
    at the top of every turn, which between them are what change the answer.
    Diffed rather than rebuilt -- the veil is only torn down and remade when
    the set of creatures it hides from actually changes -- so a creature
    that stays in contact is not announced as vanishing once per square
    anybody walks.

    Swinging clears `HIDDEN_FROM` for whoever swung, which is the Stealth
    rule and not this printed line, so a break by attack is put straight
    back while it is still in contact.
    """
    me = c.me
    veil: list[Effect] = []
    covered: set[int] = set()

    def recount(_ev: Any = None) -> None:
        close = any(distance_between(c.world, me, foe) <= 1 for foe in c.enemies())
        want = set(c.enemies()) if close else set()
        if want == covered:
            return
        if veil:
            c.world.effects.end(veil.pop(), "m4905a1")
        covered.clear()
        if not want:
            return
        hold = c.invisible(until=When.ENCOUNTER)
        if hold is not None:
            veil.append(hold)
            covered.update(want)

    def broke(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
            return
        if ev.why == "attacked" and ev.target in covered:
            c.world.relations.set(Relation.HIDDEN_FROM, me, ev.target)

    recount()
    c.watch(Moved, recount, until=When.ENCOUNTER, on=me, label="m4905a1")
    c.watch(TurnStart, recount, until=When.ENCOUNTER, on=me, label="m4905a1 turn")
    c.watch(RelationCleared, broke, until=When.ENCOUNTER, on=me, label="m4905a1 seen")


@power(
    "m4905a2",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4905a2(c: Cast) -> None:
    """Dice rather than a flat number, so it is rolled as the blow lands
    instead of riding along as a damage modifier. Read off the `Hit`, which
    carries `opportunity` the way it carries `charge`."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            c.damage("2d6", on=ev.target, detail="m4905a2")

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m4905a2")


@power(
    "m4905a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m4905a3(c: Cast) -> None:
    """A blow, and a leg caught on the way out.

    "Moves away" needs both ends of the move: `MoveEnd` carries only the
    arrival and `MoveStart` fires before the creature has moved, so the
    distance is taken there and compared here. Both watches are clocked on
    the target, which is whose next turn the printed line names.
    """
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    me = c.me
    was = [distance_between(c.world, me, victim)]

    def began(ev: MoveStart) -> None:
        if ev.actor == victim:
            was[0] = distance_between(c.world, me, victim)

    def ended(ev: MoveEnd) -> None:
        if ev.actor == victim and distance_between(c.world, me, victim) > was[0]:
            c.prone(on=victim)

    c.watch(MoveStart, began, until=When.EOTNT, on=victim, label="m4905a3 from")
    c.watch(MoveEnd, ended, until=When.EOTNT, on=victim, label="m4905a3 away")


_M4905_MISSED = "an enemy adjacent to the m4905 misses it with a melee attack"


@power(
    "m4905a4",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4905_MISSED,
    on=Trigger(
        Miss,
        when=both(targets_me, by_melee, enemy_within(1)),
        text=_M4905_MISSED,
    ),
)
def m4905a4(c: Cast) -> None:
    """Filed as a free action and printed as an immediate reaction; the
    trigger line is what says which it is. `enemy_within(1)` reads the
    attacker off a `Miss`, which carries no `actor`, and compares teams
    directly."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.swap(foe)


_M4905_SLIPPED = "an enemy adjacent to the m4905 moves"


@power(
    "m4905a5",
    level=7,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4905_SLIPPED,
    on=Trigger(MoveStart, when=enemy_within(1), text=_M4905_SLIPPED),
)
def m4905a5(c: Cast) -> None:
    """It goes where the enemy goes, and is still beside it at the end.

    The trigger is `MoveStart`, which fires before the creature has moved --
    which is the only moment "an enemy **adjacent to it** moves" is still
    true. The shift itself waits for that same move's `MoveEnd`, because
    "moving with the triggering enemy as it completes the move" is not
    something that can be taken before the move happens, and the
    destination is picked here rather than by the decider because the
    printed line says the shift must end adjacent.
    """
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return

    def tag_along(ev: MoveEnd) -> None:
        if ev.actor == foe:
            _shift_beside(c, foe, 6)

    c.watch(MoveEnd, tag_along, until=When.EONT, on=c.me, once=True, label="m4905a5")


# --------------------------------------------------------------------------
# m4922
# --------------------------------------------------------------------------


@power(
    "m4922a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 5),
)
def m4922a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4922a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
    requires=_not_grabbing,
    requires_text="the m4922 must not have a creature grabbed",
)
def m4922a1(c: Cast) -> None:
    """A jump onto somebody who was not watching, and then it holds on.

    A jump is a move in the engine, so "without provoking opportunity
    attacks" is the whole of what the printed Effect adds -- and the
    exemption is handed back as the move ends, so a second move on the same
    turn provokes as it should.

    The printed restriction is per target and the header's `target` field
    cannot say so, so the aim is narrowed here -- and narrowed after the
    jump, because that is the printed order and because the creature the
    dispatcher chose is often out of reach once it lands.

    "While the target is grabbed" is a duration the enum has no word for and
    `When.SAVE_ENDS` is the wrong one -- it would let the victim shake the
    daze off while still held -- so the holds run to the end of the fight
    and are ended by hand when the grab goes.
    """
    _guarded_move(c, 4)
    victim = c.target
    if (
        victim is None
        or not c.adjacent(victim)
        or not has_combat_advantage(c.world, c.me, victim)
    ):
        victim = c.choose(
            [
                foe
                for foe in c.enemies()
                if c.adjacent(foe) and has_combat_advantage(c.world, c.me, foe)
            ],
            "m4922a1: which creature",
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.grab(on=victim)
    _until_the_grab_ends(
        c,
        victim,
        c.condition(Condition.DAZED, until=When.ENCOUNTER, on=victim),
        c.ongoing(
            5, DamageType.PSYCHIC, on=victim, until=When.ENCOUNTER
        ),
    )


@power(
    "m4922a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m4922a2(c: Cast) -> None:
    """The printed line names no beneficiary, so it is everybody on this
    creature's side -- `to="allies"`, which is the relation once per ally on
    a single effect."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "m4922a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=10),
)
def m4922a3(c: Cast) -> None:
    """No damage at all -- going unseen by one creature is the whole hit.

    `c.invisible` hangs its hold on the caster, and a save-ends effect is
    clocked on whoever it sits on, so the caster would be rolling saves
    against its own concealment. The effect is applied to the target
    instead, carrying the same `HIDDEN_FROM` relation, which puts the
    saving throw where the printed line puts it.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label="m4922a3 unseen",
        relations=[(Relation.HIDDEN_FROM, c.me, victim)],
    )


_M4922_JOLTED = "the m4922 takes damage while subject to an effect a save can end"


def _hurt_while_held(world: World, me: int, ev: Event) -> bool:
    """`targets_me` rather than `about_me`: a damage event names its subject
    `target`, and `about_me` reads `ev.actor` and only that."""
    if getattr(ev, "target", None) != me:
        return False
    return any(eff.when is When.SAVE_ENDS for eff in world.effects.of(me))


@power(
    "m4922a4",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4922_JOLTED,
    on=Trigger(DamageApplied, when=_hurt_while_held, text=_M4922_JOLTED),
)
def m4922a4(c: Cast) -> None:
    """A No Action, which is a free action with no cost attached -- there is
    no cheaper cost in the engine and nothing counts free actions."""
    c.save()


# --------------------------------------------------------------------------
# m718
# --------------------------------------------------------------------------


@power(
    "m718a0",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m718a0(c: Cast) -> None:
    """Harder to shake off once it has hold of something.

    A gated modifier rather than a hold put on and taken off, because what
    it is holding changes with every escape and every kill, and the gate is
    asked at the moment the defence is read. The gate ignores the context
    entirely -- it is about the relation table, not about the attack.

    The printed text names another stat block's id throughout; the row ids
    are this one's and they are what is written.
    """
    me = c.me

    def holding(_ctx: dict[str, Any]) -> bool:
        return bool(c.world.relations.targets(Relation.GRABBED_BY, me))

    for defence in (AC, REF):
        c.bonus(defence, 2, until=When.ENCOUNTER, on=me, kind="untyped", when=holding)


@power(
    "m718a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6"),
)
def m718a1(c: Cast) -> None:
    """Once it has hold there is nothing else it can bite and no roll to
    make: the printed line narrows the target to the creature it is holding
    and says the attack hits automatically, so the damage is dealt without
    a `c.strike` at all.

    The grab and what hangs on it are only applied when there was not one
    already -- re-grabbing a creature it is holding would stack a second
    burn under the same sentence. "Until the grab ends" is a duration the
    enum has no word for, so the hold runs to the end of the fight and is
    ended by hand when the relation goes. The escape DC is a skill check the
    engine does not have.
    """
    held = c.world.relations.targets(Relation.GRABBED_BY, c.me)
    victim = held[0] if held else c.target
    if victim is None:
        return
    if held:
        c.hit(on=victim)
        return
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.grab(on=victim)
    _until_the_grab_ends(c, victim, c.ongoing(10, on=victim, until=When.ENCOUNTER))
