"""Monster abilities, level 5: the ones that move, and the ones that hide.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=10)` and `Damage("2d8", 4)` -- and the engine takes the level back out
of the attack and rescales the damage if a fight is being played on another
edition's maths.

The conventions of the four levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard or move
actions are plainly traits or immediate actions and are written as such; a
printed range of "15/30" takes the **normal** range; a stat block that prints
no range at all means melee 1; and a row that moves and swings takes the
swing first, because the movement picks its own destination and one taken
first can leave the target out of reach. The two rows here that print the
movement first -- a trample, and one that steps both before and after -- say
so, and are written in the printed order.

Three things this level needed that the levels below did not. **A charge**
made from inside a body: `actions.perform` builds one out of a walk plus
`use(..., charge=True)`, and `_charge` does the same, because the flag is
what puts `charge` on the attack events and in both modifier contexts.
**Combat advantage against a moving set of creatures**: there is no modifier
hook on it -- `query.has_combat_advantage` reads the relation table and
nothing else -- so `_advantage_over` keeps the relation in step with the
board. And an **Aftereffect**, which is a second hold beginning when the
first one ends, and `Effect.on_end` is the only moment that can be seen.

The helpers that hold a lurker unseen, that pay for combat advantage, that
find a free square beside a creature and that clear a solo's mind were
written for levels 2, 3 and 4 and are imported rather than copied.

Skirmishers first, then lurkers, each group in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_02.skirmishers import (
    _advantage_rider,
    _conceal,
    _hides_with_cover,
    _still_hidden_on_a_miss,
    _unseen,
)
from combat_engine.content.monsters.level_03.skirmishers import (
    _SMALL_ENOUGH,
    _free_square_beside,
    _vanish_until_it_swings,
)
from combat_engine.content.monsters.level_04.skirmishers import _MIND_HELD, _basic_ref
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
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Initiative,
    Keyword,
    Melee,
    MeleeOrRanged,
    Movement,
    Position,
    Powers,
    Ranged,
    Relation,
    Square,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Died,
    Hit,
    Moved,
    RelationCleared,
    RelationSet,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.movement import walk
from combat_engine.engine.query import (
    allies,
    distance_between,
    enemies,
    flanked_by,
    squares,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_keyword,
    by_me,
    by_melee,
    by_ranged,
    either,
    enemy_target_within,
    enemy_within,
    hits_me,
    targets_me,
)

#: The ranges a printed "melee attack" covers. A close burst is a melee
#: attack in the rules and `Range.kind` spells the three separately.
_MELEE_KINDS = ("melee", "close_burst", "close_blast")


def _reach_kind(ev: Any) -> str:
    """Which sort of range the row behind this event had.

    Read through the branch, because a `MeleeOrRanged` row's range line says
    "melee" whichever half actually swung.
    """
    p = get(getattr(ev, "power", "") or "")
    return "" if p is None else p.reach_of(getattr(ev, "branch", 0)).kind


def _airborne(world: World, eid: int) -> bool:
    """Is this creature flying?

    Not a state the engine holds: `movement.mode_of` has it that a creature
    which *can* fly does, whenever it moves, which makes having the mode the
    whole of the question -- and it is a real one, because flight can be
    taken away.
    """
    moves = world.get(eid, Movement)
    return moves is not None and bool(moves.modes.get("fly"))


def _fly_speed(c: Cast) -> int:
    moves = c.world.get(c.me, Movement)
    return (moves.modes.get("fly") if moves else 0) or c.speed_of()


def _run_at(c: Cast, victim: int) -> bool:
    """Walk into reach of a named creature, the way a charge's move does.

    `c.move` picks its own destination through the decider, which is right
    for "it moves" and useless for "it charges that one" -- so the path is
    chosen here, shortest first, exactly as `actions._charges` chooses one.
    Returns whether the target is in reach afterwards.
    """
    beside = spread(squares(c.world, victim), 1)
    paths = c.world.reachable_paths(c.me, c.speed_of())
    best = min(
        (
            (len(path), dest, path)
            for dest, path in paths.items()
            if dest in beside and path
        ),
        default=None,
    )
    if best is not None:
        walk(c.world, c.me, list(best[2]))
    return c.adjacent(victim)


def _charge(c: Cast, victim: int, ref: str = "") -> bool:
    """Run at somebody and swing, with the swing marked as a charge.

    `actions.perform` makes a charge out of a walk plus `use(...,
    charge=True)`, and a row whose printed Effect reads "it charges the
    target" is doing the same thing from inside a body. The flag is not
    decoration: it is what puts `charge` on the attack events and in both
    modifier contexts, which is what every charge rider reads.
    """
    if not _run_at(c, victim):
        return False
    return use(
        c.world, c.me, ref or _basic_ref(c), targets=[victim], spend=False, charge=True
    )


def _trample_to(c: Cast, squares_: int) -> Square | None:
    """Somewhere to end a trample: that far off, and free to stand in.

    `c.overrun` with no destination offers the creature's whole speed, and a
    printed line naming a shorter distance has to name the square too --
    the walk is a straight line from here to there, so the destination is
    the whole of the decision. Gathered off the grid rather than through
    `reachable_paths`, which routes *around* bodies and so would not offer
    anything on the far side of the one being trampled. Occupied squares are
    left out, which is the printed "must end its movement in an unoccupied
    square".
    """
    here = squares(c.world, c.me)
    options = sorted(
        sq
        for sq in spread(here, squares_) - here
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not options:
        return None
    return c.world.decide(c.me, "overrun", options, f"{c.ref}: straight through")


def _advantage_over(
    c: Cast, choose: Callable[[], tuple[int | None, list[int]]]
) -> None:
    """Combat advantage against a set of enemies the board keeps changing.

    There is no modifier hook on combat advantage: `query.has_combat_advantage`
    reads conditions and the relation table and nothing else. So the only
    way to say "has combat advantage against any enemy that ..." is to keep
    the relation in step, and `choose` answers -- at the moment it is asked
    -- who gains it and whom against.

    Asked again on every step anything takes and at the top of every turn,
    which between them are what changes the answer. The holds are diffed
    rather than torn down and rebuilt, so a creature that stays surrounded
    is not announced as newly caught out once per square anybody walks.
    """
    me = c.me
    held: dict[int, Effect] = {}
    gains: list[int | None] = [None]

    def recount(_ev: Any = None) -> None:
        who, foes = choose()
        if who != gains[0]:
            # A different creature is the beneficiary -- the saddle changed
            # hands -- so nothing already granted points at the right one.
            for foe in list(held):
                c.world.effects.end(held.pop(foe), "it changed hands")
            gains[0] = who
        want = set(foes) if who is not None else set()
        for foe in list(held):
            if foe not in want:
                c.world.effects.end(held.pop(foe), "no longer surrounded")
        for foe in sorted(want - set(held)):
            held[foe] = c.world.effects.apply(
                foe,
                me,
                When.ENCOUNTER,
                label=c.ref,
                relations=[(Relation.GRANTS_CA_TO, foe, who)],
            )

    recount()
    c.watch(Moved, recount, until=When.ENCOUNTER, on=me, label=f"{c.ref} moved")
    c.watch(TurnStart, recount, until=When.ENCOUNTER, on=me, label=f"{c.ref} turn")


def _crowded(c: Cast, who: int, pack: list[int], needed: int) -> list[int]:
    """That creature's enemies with at least `needed` of `pack` beside them."""
    return [
        foe
        for foe in enemies(c.world, who)
        if sum(1 for a in pack if distance_between(c.world, a, foe) <= 1) >= needed
    ]


def _unbroken_veil(c: Cast, veil: Effect | None) -> None:
    """Put back the concealment the creature's own swing just cleared.

    `resolve.attack` clears `HIDDEN_FROM` for whoever attacked, which is the
    Stealth rule and the right default. A printed line reading "becomes
    invisible until the end of its next turn" is a clock rather than a
    hiding place and swinging does not stop it, so the relations the effect
    carries are set again -- and the effect's own duration still ends them.
    """
    if veil is None:
        return
    for kind, source, target in veil.relations:
        c.world.relations.set(kind, source, target)


def _cannot_attack(c: Cast, until: When) -> None:
    """Take every attack this creature has away for a while.

    "Cannot attack until the end of its next turn" has no single hold: every
    condition that stops a creature acting stops it moving as well, and this
    line does not. So each attacking row is forbidden -- which is exactly
    what `c.forbid` says, a row taken away rather than spent -- and
    `c.no_basic` takes the designation an opportunity attack reaches for.
    """
    known = c.world.get(c.me, Powers)
    if known is None:
        return
    for ref in list(known.all):
        p = get(ref)
        if p is not None and p.attack is not None:
            c.forbid(ref, on=c.me, until=until)
    c.no_basic(until=until)


def _shrug_off_the_mind(c: Cast) -> None:
    """Nothing holds this creature's mind for longer than its own turn."""
    me = c.me
    ref = c.ref

    def clear(ev: TurnEnd) -> None:
        if ev.actor != me:
            return
        for effect in list(c.world.effects.of(me)):
            if set(effect.conditions) & set(_MIND_HELD):
                c.world.effects.end(effect, ref)

    c.watch(TurnEnd, clear, until=When.ENCOUNTER, on=me, label=ref)


# ==========================================================================
# Skirmishers
# ==========================================================================


# --------------------------------------------------------------------------
# m146
# --------------------------------------------------------------------------


@power(
    "m146a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m146a0(c: Cast) -> None:
    """Combat advantage against whoever the herd has closed around. The ally
    pool never includes the creature itself, which is what the printed count
    of "two or more of its allies" means."""
    _advantage_over(c, lambda: (c.me, _crowded(c, c.me, c.allies(), 2)))


@power(
    "m146a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m146a1(c: Cast) -> None:
    """The same opening, handed to whoever is in the saddle.

    The count is of the *rider's* allies and expressly not of the mount, so
    the mount is filtered out of a pool it would otherwise be in. Who the
    rider is is asked each time rather than once: a rider mounts and falls
    off mid-fight, and the relation names one beneficiary.
    """

    def choose() -> tuple[int | None, list[int]]:
        rider = c.rider()
        if rider is None:
            return None, []
        pack = [a for a in allies(c.world, rider) if a != c.me]
        return rider, _crowded(c, rider, pack, 1)

    _advantage_over(c, choose)


@power(
    "m146a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m146a2(c: Cast) -> None:
    """The heavier line is a second expression rather than a rider on the
    first, so it is rolled in the body and the header keeps the printed one
    that rescales. Whether it had the drop is read off the roll that was
    just made -- asking the board afterwards answers "no" for a creature
    that struck from concealment, and this one has a trait that hands it
    concealment's equivalent."""
    down = c.is_(Condition.PRONE)
    if not c.strike():
        return
    if down:
        c.damage("3d8", 4)
    else:
        c.hit()
    if c.result is not None and c.result.advantage:
        c.prone()


# --------------------------------------------------------------------------
# m15
# --------------------------------------------------------------------------


@power(
    "m15a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE),
)
def m15a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m15a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m15a1(c: Cast) -> None:
    """Four squares straight through whoever is standing in them.

    `c.overrun` walks the line and reports whose square was entered, in
    order and each one only once, which is both halves of the printed
    restriction -- it goes through occupied squares, and it cannot swing at
    the same creature twice. The row declares no targets, because the route
    is what decides whom it catches; the swing is whatever this creature's
    basic attack actually is, which is what the printed line names.
    """
    dest = _trample_to(c, 4)
    if dest is None:
        return
    for who in c.overrun(to=dest):
        c.basic(on=who)


# --------------------------------------------------------------------------
# m272
# --------------------------------------------------------------------------


@power(
    "m272a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m272a0(c: Cast) -> None:
    """A bonus to the rider's defences, and only while the mount is up.

    Flying is asked at the moment a defence is read rather than when the
    trait arms, because flight can be taken away -- so it is a gate on the
    modifier rather than something put on and taken off. The modifier has to
    sit on the *rider*, and who that is changes mid-fight, so the four holds
    are re-homed on the two events that say so rather than handed out once.
    """
    me = c.me
    held: list[Effect] = []

    def flying(_ctx: dict[str, Any]) -> bool:
        return _airborne(c.world, me)

    def rehome(_ev: Any = None) -> None:
        for effect in held:
            c.world.effects.end(effect, "a different rider")
        held.clear()
        rider = c.rider()
        if rider is None:
            return
        for d in (AC, FORT, REF, WILL):
            hold = c.bonus(
                d, 1, until=When.ENCOUNTER, on=rider, kind="untyped", when=flying
            )
            if hold is not None:
                held.append(hold)

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == me:
            rehome()

    def unhorsed(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == me:
            rehome()

    rehome()
    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=me, label="m272a0 on")
    c.watch(RelationCleared, unhorsed, until=When.ENCOUNTER, on=me, label="m272a0 off")


@power(
    "m272a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m272a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m272a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3),
    requires=_airborne,
    requires_text="the m272 must be flying",
)
def m272a2(c: Cast) -> None:
    """A dive: it comes in at a run and this is the blow instead of a basic.

    `c.charge` is raised on the cast rather than passed to `use`, because
    the row that charges *is* the row that swings and there is no outer
    `use` to hand the flag to. It is the same flag `actions.perform` sets,
    and it is what buys the printed +1 and puts `charge` on the events.

    The header's range is melee 1, which is what level 1 settled on for the
    other row of this shape: a charge is a separate kind of action in the
    engine rather than a range a power can print, so there is no header
    field that says "anything it can run to" and the row is declared at the
    reach it strikes from. The run-in is still taken, for whoever hands it a
    target further off.

    "Lands in an unoccupied space adjacent to the target" needs no move of
    its own: altitude is not a thing the engine holds, and the run-in has
    already put it in a free square beside what it hit.
    """
    victim = c.target
    if victim is None or c.size_of(victim) not in _SMALL_ENOUGH:
        return
    if not _run_at(c, victim):
        return
    c.charge = True
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m272a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m272a3(c: Cast) -> None:
    """A pass on the wing: the swing is taken first, for the reason levels 1
    and 4 give on their own rows of this shape -- the flight picks its own
    destination and one taken first can leave the target out of reach.
    Leaving provokes nothing from the creature it struck, which is the
    printed exemption, and the claw is the row that prints it rather than a
    copy."""
    c.no_provoke(from_=c.target)
    use(c.world, c.me, "m272a1", targets=[c.target], spend=False)
    c.move(_fly_speed(c))


# --------------------------------------------------------------------------
# m2837
# --------------------------------------------------------------------------


@power(
    "m2837a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 3),
)
def m2837a0(c: Cast) -> None:
    """The secondary attack is a second roll against a different defence, so
    it cannot live in the header; its printed +8 is trimmed by hand the way
    `Attack.bonus_for` trims the header's.

    The two failed saves are a chain of `escalate`, each step ending the one
    before it, so the victim never carries two of these and never gets two
    saving throws against one bite. Stone is the end of the chain and
    carries no escalation of its own; it runs to the end of the fight,
    because nothing printed lifts it.
    """
    if not c.strike():
        return
    c.hit()
    if not c.attack(c.world.scaling.trim(8, c.level), FORT):
        return

    def stone(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.PETRIFIED, until=When.ENCOUNTER, on=eff.owner)

    def stiffen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=eff.owner, escalate=stone
        )

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=stiffen)


_M2837_CLOSED = "an enemy moves adjacent to the m2837"


@power(
    "m2837a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M2837_CLOSED,
    on=Trigger(AdjacencyGained, when=enemy_within(1), text=_M2837_CLOSED),
)
def m2837a1(c: Cast) -> None:
    """Filed as a move action and printed as an immediate interrupt; the
    trigger line is what says which it is, so it is declared as one. The
    bite is the row that prints it rather than a copy, and the step comes
    after it."""
    use(c.world, c.me, "m2837a0", targets=[c.target], spend=False)
    c.shift(3)


# --------------------------------------------------------------------------
# m2859
# --------------------------------------------------------------------------


@power(
    "m2859a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m2859a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2859a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2859a1(c: Cast) -> None:
    """A rider on every melee blow it lands, so a trait rather than an
    action. Asked at the moment of the `Hit`, which is before this attack's
    own damage: "against a bloodied target" means one that already was."""
    me = c.me
    ref = c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or _reach_kind(ev) not in _MELEE_KINDS:
            return
        if c.bloodied(on=ev.target):
            c.damage("1d8", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m2859a2",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2859a2(c: Cast) -> None:
    """Ten squares to somewhere beside whoever is already bleeding.

    The destination is named rather than left to the decider -- "into a
    square adjacent to a bloodied enemy" is an instruction, not a choice --
    so the free squares round each candidate are tried in turn, and
    `c.teleport` refuses any that is out of range or blocked.
    """
    for foe in c.enemies():
        if not c.bloodied(on=foe):
            continue
        landing = _free_square_beside(c, foe)
        if landing is not None and c.teleport(10, to=landing):
            return


_M2859_BLOODIED = "the m2859 is first bloodied"


@power(
    "m2859a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M2859_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M2859_BLOODIED),
)
def m2859a3(c: Cast) -> None:
    """"First bloodied" needs no guard of its own -- `Bloodied` is emitted on
    the crossing and nowhere else."""
    c.teleport(10)


# --------------------------------------------------------------------------
# m2913
# --------------------------------------------------------------------------


@power(
    "m2913a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 2),
)
def m2913a0(c: Cast) -> None:
    """The step is on the hit line with the damage -- one printed clause --
    so it is taken only when the bite lands."""
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m2913a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 2),
)
def m2913a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M2913_STRUCK = "an enemy adjacent to the m2913 is hit by a melee attack"


@power(
    "m2913a2",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2913_STRUCK,
    on=Trigger(Hit, when=both(enemy_target_within(1), by_melee), text=_M2913_STRUCK),
)
def m2913a2(c: Cast) -> None:
    """`enemy_target_within` reads the creature on the receiving end, which
    is what this trigger is about -- `enemy_within` reads the attacker and
    would fire on the wrong half of the sentence."""
    c.shift(2)


# --------------------------------------------------------------------------
# m2995
# --------------------------------------------------------------------------


@power(
    "m2995a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2995a0(c: Cast) -> None:
    """An extra die against anything the fight has not yet touched.

    Kept as a set filled off `DamageApplied` rather than asked of the hit
    points, because a creature healed back to full has still taken damage
    during the encounter and `c.wounded` would say it had not. Whatever the
    board was already carrying when the fight began counts too, which is
    what the second half of the test is for.
    """
    me = c.me
    ref = c.ref
    struck: set[int] = set()

    def tally(ev: DamageApplied) -> None:
        if ev.amount > 0:
            struck.add(ev.target)

    def rider(ev: Hit) -> None:
        if ev.attacker != me or _reach_kind(ev) not in _MELEE_KINDS:
            return
        if ev.target in struck or c.wounded(on=ev.target):
            return
        c.damage("1d10", on=ev.target, detail=ref)

    c.watch(DamageApplied, tally, until=When.ENCOUNTER, on=me, label=f"{ref} tally")
    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m2995a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m2995a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2995a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m2995a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2995a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m2995a3(c: Cast) -> None:
    """The one row here whose movement is printed *before* the swing as well
    as after, so the usual order -- swing first, because a shift picks its
    own destination -- is not the printed one and is not taken."""
    c.shift(1)
    if c.strike():
        c.hit()
    c.shift(1)


_M2995_LANDED = "the m2995 deals damage with an attack"


@power(
    "m2995a4",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2995_LANDED,
    on=Trigger(
        DamageRolled,
        when=both(by_me, either(by_melee, by_ranged)),
        text=_M2995_LANDED,
    ),
)
def m2995a4(c: Cast) -> None:
    """The extra die goes to whoever the triggering attack damaged.

    Answered on `DamageRolled` rather than on `DamageApplied`, which is the
    event the printed sentence describes: `by_melee` and `by_ranged` find
    the reach through `ev.detail`, and **`DamageApplied` has no `detail`
    field** -- its own docstring says it does and the dataclass does not, so
    on it both predicates are silently false. `DamageRolled` carries one,
    and its reaction window still runs before the number comes off anybody's
    hit points.

    The extra die is dealt as its own packet rather than added to the event,
    so it shows in the log the way every other rider here does.
    """
    victim = getattr(c.trigger, "target", None)
    if victim is not None and getattr(c.trigger, "amount", 0) > 0:
        c.damage("1d10", on=victim)


# --------------------------------------------------------------------------
# m3024
# --------------------------------------------------------------------------


@power(
    "m3024a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5),
)
def m3024a0(c: Cast) -> None:
    """The keyword is poison and the printed damage is untyped, which is what
    the header says: the keyword is what a resistance keys off, and the
    damage line is the damage line."""
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m3024a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.POISON),
)
def m3024a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m3024a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3024a2(c: Cast) -> None:
    """The swing is taken before the step, for the reason the levels below
    give: the shift picks its own destination and one taken first can leave
    the target out of reach. The blade is the row that prints it."""
    use(c.world, c.me, "m3024a0", targets=[c.target], spend=False)
    c.shift(4)


_M3024_SWUNG_AT = "an enemy attacks the m3024"


@power(
    "m3024a3",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 2),
    trigger=_M3024_SWUNG_AT,
    on=Trigger(AttackDeclared, when=targets_me, text=_M3024_SWUNG_AT),
)
def m3024a3(c: Cast) -> None:
    """The declaration is what is answered rather than the hit, because the
    printed trigger is being *attacked* and not being hit; as a reaction it
    still resolves after the blow, which is the window the printed effect
    wants. The triggering enemy is who the dispatcher aims it at."""
    if c.strike():
        c.hit()


@power(
    "m3024a4",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
)
def m3024a4(c: Cast) -> None:
    """No attack roll: the blindness is the whole of it."""
    c.blinded(until=When.EOT)


@power(
    "m3024a5",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3024a5(c: Cast) -> None:
    """The flanking half only, and written as the one extra point.

    Flanking is already worth +2 through combat advantage, so what the
    printed line adds is a third -- gated on flanking in particular, because
    an enemy caught out some other way is granting combat advantage and is
    not flanked, and pays nothing. "Grants a +3 instead of a +2 while aiding
    another" is a skill-check rule and aid another is not in the engine.
    """
    me = c.me
    c.bonus(
        "attack",
        1,
        until=When.ENCOUNTER,
        on=me,
        kind="untyped",
        when=lambda ctx: flanked_by(c.world, ctx["target"], me),
    )


@power(
    "m3024a6",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3024a6(c: Cast) -> None:
    """A skill contest and nothing else -- an Insight check against a Bluff
    check -- so it is declared inert rather than given an invented
    mechanic."""
    c.note("m3024a6: mimics sounds and voices; Insight opposes its Bluff")


# --------------------------------------------------------------------------
# m455
# --------------------------------------------------------------------------


@power(
    "m455a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m455a0(c: Cast) -> None:
    """The step is an Effect line rather than part of the hit, so it is taken
    whether or not the claw lands -- and taken after it, because a shift
    picks its own destination and one taken first can leave the target out
    of reach. "Loses a healing surge" is a surge spent for nothing, which is
    what `c.spend_surge` is."""
    if c.strike():
        c.hit()
        c.spend_surge()
    c.shift(3)


# --------------------------------------------------------------------------
# m4852
# --------------------------------------------------------------------------


@power(
    "m4852a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4852a0(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m4852a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4852a1(c: Cast) -> None:
    """Combat advantage against anybody standing beside the one it serves.

    Who its master is and where that master is standing both change during a
    fight, so the set is recomputed rather than worked out once.
    """

    def choose() -> tuple[int | None, list[int]]:
        master = c.master()
        if master is None:
            return c.me, []
        return c.me, [
            foe
            for foe in c.enemies()
            if distance_between(c.world, master, foe) <= 1
        ]

    _advantage_over(c, choose)


@power(
    "m4852a2",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4852a2(c: Cast) -> None:
    """Shared sight, hearing and speech, and nothing else. Declared inert
    rather than given an invented mechanic."""
    c.note("m4852a2: its master sees, hears and speaks through it")


@power(
    "m4852a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m4852a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4852a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m4852a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4852a5",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
)
def m4852a5(c: Cast) -> None:
    """Either weapon, and a step either way.

    The printed line offers a choice between two rows, which is exactly what
    a two-branch range is: the caller picks the branch, `c.ranged` says
    which was picked, and provoking is decided per branch the same way. The
    swing is taken before the step for the usual reason.
    """
    ref = "m4852a4" if c.ranged else "m4852a3"
    use(c.world, c.me, ref, targets=[c.target], spend=False)
    c.shift(3)


# --------------------------------------------------------------------------
# m493
# --------------------------------------------------------------------------


@power(
    "m493a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m493a0(c: Cast) -> None:
    """An aura 1 that only bites while the dragon itself is bleeding.

    The aura is made once and stands for the fight; whether it pays out is
    asked at the moment an enemy's turn ends, because both halves of the
    question -- is the dragon bloodied, is that enemy -- change during one.
    `c.burns` will not say it: that deals a flat number on entry, and this
    is ongoing damage handed out on the way out of a turn.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def linger(ev: TurnEnd) -> None:
        if ev.ghost or not c.bloodied(on=me):
            return
        if ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        amount = 10 if c.bloodied(on=ev.actor) else 5
        c.ongoing(amount, DamageType.POISON, on=ev.actor)

    c.watch(TurnEnd, linger, until=When.ENCOUNTER, on=me, label="m493a0")


@power(
    "m493a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m493a1(c: Cast) -> None:
    _shrug_off_the_mind(c)


@power(
    "m493a2",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m493a2(c: Cast) -> None:
    """A solo acting twice a round: a second slot in the initiative order.

    The printed line gives it a free action at that count rather than a
    whole turn, and there is no way to hand out a turn with one action in
    it; `c.extra_turn` is what the engine has for a creature that acts
    again, and the slot is where the card puts it.

    The last sentence is answered on the turn boundary rather than only on
    that slot, because nothing tells the two slots apart: if it cannot act
    for being stunned or dominated, the thing stopping it ends instead.

    The +4 to defences against opportunity attacks is printed here and is
    about the movement m493a6 makes, so it is written where that movement
    is -- nothing can tell a use of that row triggered by this slot from an
    ordinary one.
    """
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(at=init.rolled + 10)

    def instead(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for effect in list(c.world.effects.of(me)):
            if set(effect.conditions) & {Condition.STUNNED, Condition.DOMINATED}:
                c.world.effects.end(effect, "m493a2")

    c.watch(TurnStart, instead, until=When.ENCOUNTER, on=me, label="m493a2")


@power(
    "m493a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 4),
)
def m493a3(c: Cast) -> None:
    """The miss line is a flat 5 rather than half of the hit, so it is rolled
    in the body: `c.hit(half=True)` would halve 2d10 + 4."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
    else:
        c.flat(5, dtype=DamageType.POISON)


@power(
    "m493a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m493a4(c: Cast) -> None:
    """One creature twice or two creatures once, which is what the printed
    line offers and what `UpTo(2)` lets the caller choose between. The step
    is on the hit line, so it is taken per blow that lands."""
    for _ in range(2 if len(c.targets) == 1 else 1):
        if c.strike():
            c.hit()
            c.shift(2)


@power(
    "m493a5",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d10", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m493a5(c: Cast) -> None:
    """"Save ends both" is one effect with two halves and exactly one saving
    throw -- applied separately it would be two saves against a thing the
    card says is one.

    The Aftereffect is a second, lighter hold that begins when the first one
    is shaken off, and the end of an effect is the only moment that can be
    seen, so it is hung there. `on_end` also runs when the fight does, which
    is the cost of being able to say it at all.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    held = c.condition(
        Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON)
    )
    if held is not None and victim is not None:
        held.on_end.append(lambda: c.slowed(until=When.SAVE_ENDS, on=victim))


@power(
    "m493a6",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m493a6(c: Cast) -> None:
    """A flight with a bite or a breath somewhere in it.

    The attack is taken first, for the reason the other rows of this shape
    give: the flight picks its own destination and one taken first can leave
    the target out of reach. The breath is tried before the bite, since the
    printed line offers it only "if the power is recharged" -- `use` refuses
    a spent row and says so, which is the whole of that condition.

    "Ignoring slowing effects during the movement" is written as the
    distance rather than as an exemption: `query.speed` caps a slowed
    creature at 2 and there is no hook to lift a cap, but `c.move` is handed
    a budget and honours it, so it is handed the printed fly speed.

    The +4 against opportunity attacks is m493a2's sentence about this move.
    It is a gate rather than something put on and taken off, because the
    attack context carries `opportunity`, and it ends with the flight.
    """
    if not use(c.world, c.me, "m493a5"):
        use(c.world, c.me, "m493a3", spend=False)
    me = c.me
    guards = [
        c.bonus(
            d,
            4,
            until=When.EOT,
            on=me,
            kind="untyped",
            when=lambda ctx: bool(ctx.get("opportunity")),
        )
        for d in (AC, FORT, REF, WILL)
    ]
    try:
        c.move(_fly_speed(c))
    finally:
        for guard in guards:
            if guard is not None:
                c.world.effects.end(guard, "the flight is over")


@power(
    "m493a7",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=8),
)
def m493a7(c: Cast) -> None:
    """No damage at all: the slide is the whole of the hit line."""
    if c.strike():
        c.slide(3)


_M493_BLOODIED = "the m493 is first bloodied"


@power(
    "m493a8",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M493_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M493_BLOODIED),
)
def m493a8(c: Cast) -> None:
    """`Powers.restore` is what a recharge is, so the breath comes back up and
    goes off at once. The blast picks its own aim, which is what
    `_auto_targets` is for."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m493a5")
    use(c.world, c.me, "m493a5")


# --------------------------------------------------------------------------
# m5034
# --------------------------------------------------------------------------


@power(
    "m5034a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5034a0(c: Cast) -> None:
    """Five more on anything it lands at a run.

    A gated damage modifier rather than a watch on the hit: the damage
    context carries `charge`, so the gate can ask, and the printed line adds
    a flat number rather than dice.
    """
    c.bonus(
        "damage",
        5,
        until=When.ENCOUNTER,
        on=c.me,
        kind="untyped",
        when=lambda ctx: bool(ctx.get("charge")),
    )


@power(
    "m5034a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 6),
)
def m5034a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5034a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(7),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m5034a2(c: Cast) -> None:
    """The scream, and then it comes in at a run. The charge is a walk into
    reach plus a swing marked as one, which is what `_charge` does and what
    m5034a0 reads."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _charge(c, victim)


@power(
    "m5034a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m5034a3(c: Cast) -> None:
    """Straight through the line, swinging at whoever it goes over.

    `c.overrun` walks the line and reports whose square was entered, in
    order and each one only once, which is both the trampling and the
    printed "for the first time". The row declares no targets because the
    route decides whom it catches; the attack line is still data in the
    header and `c.strike(on=...)` rolls it against each in turn.
    """
    dest = _trample_to(c, c.speed_of())
    if dest is None:
        return
    for who in c.overrun(to=dest):
        if c.strike(on=who):
            c.hit(on=who)
            c.prone(on=who)


@power(
    "m5034a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d10", 6, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5034a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


# ==========================================================================
# Lurkers
# ==========================================================================


# --------------------------------------------------------------------------
# m1279
# --------------------------------------------------------------------------


@power(
    "m1279a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4),
)
def m1279a0(c: Cast) -> None:
    """The printed critical is a die more than a maximised one: 1d8 + 12 is
    the maximum of 1d8 + 4 with another 1d8 on top. The extra die is dealt
    flat, because `c.damage` maximises its dice on a critical and would make
    it 8 every time."""
    if c.strike():
        c.hit()
        if c.crit:
            c.flat(c.roll("1d8"))


@power(
    "m1279a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m1279a1(c: Cast) -> None:
    """Gone, a swing out of nowhere, and two steps.

    The veil goes up first, because the whole point of it is the opening the
    attack then has. The swing is taken before the step, which is the other
    way round from the printed order and the reason the levels below give
    for doing it: the shift picks its own destination, and one taken first
    puts the blade out of reach of everything on the board.

    Swinging clears `HIDDEN_FROM` for whoever swung, which is the Stealth
    rule and not this printed clock, so it is put back -- "until the end of
    its next turn" is a duration and attacking does not end it.
    """
    veil = c.invisible(until=When.EONT)
    use(c.world, c.me, "m1279a0", spend=False)
    _unbroken_veil(c, veil)
    c.shift(2)


@power(
    "m1279a2",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1279a2(c: Cast) -> None:
    _advantage_rider(c, "1d6")


_M1279_HURT = "the m1279 takes damage"


@power(
    "m1279a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger=_M1279_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M1279_HURT),
)
def m1279a3(c: Cast) -> None:
    """`targets_me` rather than `about_me`: a damage event names its subject
    `target`, and `about_me` reads `ev.actor` and only that."""
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m1279a4",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1279a4(c: Cast) -> None:
    """One Stealth check, at the top of the fight and nowhere else.

    There are no skill checks in the engine, so what is left that can be
    said is the consequence: wherever it had cover or concealment when the
    fight began, it is unseen. Tried again on its own first turn and never
    after -- a trait is armed before initiative is rolled, and this printed
    line is about that moment rather than about getting back out of sight,
    which is what m4901a0 prints instead.
    """
    me = c.me
    done: list[int] = []

    def first_turn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost and not done:
            done.append(1)
            _conceal(c)

    _conceal(c)
    c.watch(TurnStart, first_turn, until=When.ENCOUNTER, on=me, label="m1279a4")


_M1279_HIT = "an enemy hits the m1279"


@power(
    "m1279a5",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M1279_HIT,
    on=Trigger(Hit, when=hits_me, text=_M1279_HIT),
)
def m1279a5(c: Cast) -> None:
    c.teleport(1)


# --------------------------------------------------------------------------
# m2904
# --------------------------------------------------------------------------


@power(
    "m2904a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m2904a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2904a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m2904a2(c: Cast) -> None:
    """The line it repeats is the row that prints it rather than a copy, so
    the damage stays in one place."""
    for _ in range(2):
        use(c.world, c.me, "m2904a1", targets=[c.target], spend=False)


_M2904_HIT = "the m2904 is hit by an attack"


@power(
    "m2904a3",
    level=5,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
    trigger=_M2904_HIT,
    on=Trigger(Hit, when=targets_me, text=_M2904_HIT),
)
def m2904a3(c: Cast) -> None:
    """Scales turned, and a swing back.

    "Resist 5 to all damage of the triggering attack" is not resistance:
    resistance is held per damage type and this is one blow, whatever it
    happens to be made of. So it is taken off the damage roll instead, in
    the interrupt window -- the one moment the number exists and has not yet
    come off anybody's hit points -- and only for the blow that triggered
    this, which is why the source and the row are both checked and the hold
    spends itself on the first one it answers.
    """
    me = c.me
    ev = c.trigger
    attacker = getattr(ev, "attacker", None)
    blow = getattr(ev, "power", "")
    spent: list[int] = []

    def shrug(hurt: DamageRolled) -> None:
        if spent or hurt.target != me:
            return
        if hurt.source != attacker or hurt.detail != blow:
            return
        spent.append(1)
        hurt.amount = max(0, hurt.amount - 5)

    c.watch(
        DamageRolled,
        shrug,
        until=When.EONT,
        window=Window.BEFORE,
        on=me,
        label="m2904a3 scales",
    )
    if c.strike():
        c.hit()


@power(
    "m2904a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=6),
    damage=Damage(
        "2d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True
    ),
)
def m2904a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)
    else:
        c.hit(half=True)


_M2904_BLOODIED = "the m2904 is first bloodied"


@power(
    "m2904a5",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2904_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M2904_BLOODIED),
)
def m2904a5(c: Cast) -> None:
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m2904a4")
    use(c.world, c.me, "m2904a4")


@power(
    "m2904a6",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=6),
)
def m2904a6(c: Cast) -> None:
    """No damage at all -- the hold is the whole of the hit, and what follows
    it. The Aftereffect begins when the stun ends, and the end of an effect
    is the only moment that can be seen, so it is hung there."""
    if not c.strike():
        return
    victim = c.target
    held = c.stunned(until=When.EONT)
    if held is not None and victim is not None:
        held.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# --------------------------------------------------------------------------
# m318
# --------------------------------------------------------------------------


@power(
    "m318a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m318a0(c: Cast) -> None:
    _still_hidden_on_a_miss(c, ("ranged",))


@power(
    "m318a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 1),
)
def m318a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m318a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3),
)
def m318a2(c: Cast) -> None:
    """The secondary attack is a second roll against a different defence, so
    it cannot live in the header; its printed +8 is trimmed by hand the way
    `Attack.bonus_for` trims the header's. "Save ends both" is one effect
    carrying the burn, which is one saving throw rather than two."""
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(8, c.level), FORT):
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON)
        )


# --------------------------------------------------------------------------
# m4901
# --------------------------------------------------------------------------


@power(
    "m4901a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4901a0(c: Cast) -> None:
    """The first half is what `_hides_with_cover` says: there is no
    requirement in the engine to lower and no skill check to roll, so
    wherever it could try, it has.

    The second half needs nothing written. Moving into the open does not
    give a creature away here -- only attacking does, in `resolve.attack` --
    so "remains hidden from those creatures" is already how it behaves.
    """
    _hides_with_cover(c)


@power(
    "m4901a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4901a1(c: Cast) -> None:
    """Five more against anybody caught on their own.

    Its *own* allies, not the target's: the printed line counts the m4901's
    friends standing beside the target, so the neighbours are gathered off
    the board and filtered by side. The pool `c.within` returns for "ally"
    includes the creature itself, which is not one of its own allies.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if _reach_kind(ev) not in (*_MELEE_KINDS, "ranged"):
            return
        if any(a != me for a in c.within(1, of=ev.target, side="ally")):
            return
        c.flat(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m4901a1")


@power(
    "m4901a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 8),
)
def m4901a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4901a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m4901a3(c: Cast) -> None:
    if c.strike():
        c.hit()


_M4901_SHOT = "the m4901 hits with m4901a3"


def _with_the_bow(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "power", "") == "m4901a3"


@power(
    "m4901a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    requires=_unseen,
    requires_text="the m4901 must be hidden",
    trigger=_M4901_SHOT,
    on=Trigger(Hit, when=_with_the_bow, text=_M4901_SHOT),
)
def m4901a4(c: Cast) -> None:
    """The Requirement holds at the moment it is offered: `resolve.attack`
    clears `HIDDEN_FROM` *after* the `Hit` is announced, so the row is asked
    while the creature is still unseen, which is what the printed line
    means."""
    c.shift(2)


# --------------------------------------------------------------------------
# m690
# --------------------------------------------------------------------------


@power(
    "m690a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m690a0(c: Cast) -> None:
    """Half of everything but force, and radiant puts it out for a turn.

    Not `c.insubstantial`: that halves force too, and the printed line
    excepts it. So the halving is taken off the damage roll in the interrupt
    window, which is the one moment the number exists and has not yet come
    off hit points. Radiant is not itself halved -- it is what switches the
    trait off, and it does so before the blow that carries it is reduced.
    """
    me = c.me
    doused: list[int] = []

    def half(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        if ev.dtype is DamageType.RADIANT:
            doused.append(1)
            return
        if not doused and ev.dtype is not DamageType.FORCE:
            ev.amount //= 2

    def dawn(ev: TurnStart) -> None:
        if ev.actor == me:
            doused.clear()

    c.watch(
        DamageRolled,
        half,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m690a0",
    )
    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label="m690a0 dawn")


@power(
    "m690a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m690a1(c: Cast) -> None:
    """Whoever it kills gets up again as another of its kind.

    `Died` says who died and not who did it, so the last creature to take
    hit points off each victim is remembered as it happens and read back
    when the body drops. The new one arrives at the top of this creature's
    next turn, in the square the humanoid died in -- `_die` lifts the corpse
    off the grid, so that square is free. `c.summon` puts it on the board
    **and** in the initiative order, which is the half that makes it act at
    all and the half a bare spawn does not do.
    """
    me = c.me
    killer: dict[int, int] = {}
    waiting: list[Square] = []

    def blame(ev: DamageApplied) -> None:
        if ev.amount > 0:
            killer[ev.target] = ev.source

    def claim(ev: Died) -> None:
        if killer.get(ev.actor) != me or not c.is_kind("humanoid", on=ev.actor):
            return
        where = c.world.get(ev.actor, Position)
        waiting.append(where.square if where is not None else c.here)

    def rise(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        while waiting:
            c.summon("m690", waiting.pop(0))

    c.watch(DamageApplied, blame, until=When.ENCOUNTER, on=me, label="m690a1 blame")
    c.watch(Died, claim, until=When.ENCOUNTER, on=me, label="m690a1 claim")
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label="m690a1 rise")


@power(
    "m690a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
)
def m690a2(c: Cast) -> None:
    """The heavier line is a second expression rather than a rider, so it is
    rolled in the body and the header keeps the printed one that rescales.
    Whether it was unseen is asked **before** the swing: `resolve.attack`
    clears `HIDDEN_FROM` for whoever attacked, so asking afterwards answers
    no for every blow struck out of the dark."""
    unseen = c.target is not None and c.is_hidden(from_=c.target)
    if not c.strike():
        return
    if unseen:
        c.damage("4d6", 14, dtype=DamageType.NECROTIC)
    else:
        c.hit()


_M690_STRUCK = "an attack that deals neither force nor radiant damage hits the m690"


def _not_bright(world: World, me: int, ev: Any) -> bool:
    """Neither force nor radiant.

    Read off the attacking row's keywords, which is all there is at the
    moment of the `Hit` -- the damage has not been rolled yet, so nothing on
    the event says what the blow is made of.
    """
    return not (
        by_keyword(Keyword.FORCE)(world, me, ev)
        or by_keyword(Keyword.RADIANT)(world, me, ev)
    )


@power(
    "m690a3",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M690_STRUCK,
    on=Trigger(Hit, when=both(targets_me, _not_bright), text=_M690_STRUCK),
)
def m690a3(c: Cast) -> None:
    """Gone, elsewhere, and no use to anybody until its next turn is over.

    "Until it hits or misses with an attack or until the end of the
    encounter" is exactly what `_vanish_until_it_swings` holds, given the
    encounter's clock. The last clause has no single hold of its own -- see
    `_cannot_attack` -- so it is written as every attack it has being taken
    away for the duration.
    """
    _vanish_until_it_swings(c, When.ENCOUNTER)
    c.teleport(6)
    _cannot_attack(c, When.EONT)


# --------------------------------------------------------------------------
# m708
# --------------------------------------------------------------------------


@power(
    "m708a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8"),
)
def m708a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.insubstantial(until=When.SONT)


_M708_SWUNG_AT = "the m708 is attacked by a melee attack"


@power(
    "m708a1",
    level=5,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M708_SWUNG_AT,
    on=Trigger(AttackDeclared, when=both(targets_me, by_melee), text=_M708_SWUNG_AT),
)
def m708a1(c: Cast) -> None:
    """The declaration is what is answered rather than the roll: the printed
    trigger is being attacked, and stepping out of reach before the die is
    down is the whole of what the row buys."""
    c.shift(2)
