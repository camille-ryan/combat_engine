"""Monster abilities, level 1, the blocks whose type line prints no role.

Four stat blocks, 17 rows. A role-less block is usually not an encounter
monster, and these four are three different things:

* **one is a conjured servant.** Every number on its block is 0 and its two
  attack lines are printed as *the master's* ability modifier -- "+Intelligence
  +2 vs. AC". `Attack(by=)` knows only `"companion"`, so those two cannot be
  stated in the header at all and the body rolls them with `c.attack`; see
  `_master_mod`. Its leash is the one row here refused in play.
* **two are ordinary creatures with a role missing from the line**, and are
  written exactly as any other monster: numbers from `game.db`, the attack
  bonus as printed, the damage line in the header as data.
* **one is an aura creature** whose own trait halves almost everything it
  takes, which is not resistance as the engine holds it -- resistance is per
  damage type -- so it comes off the roll in the interrupt window, the one
  moment the number exists and has not yet reached hit points. `c.halve` is
  that op.

Two judgement calls worth naming:

* **"willingly enters a square in the aura" is `Moved.kind_`.** Walk, charge,
  run, shift and teleport are the creature going; push, pull and slide are it
  being shoved, and the step the engine files as `place` is being put
  somewhere. Reading the word off the event is the whole of the printed
  "willingly", so nothing is missing here.
* **a printed range band -- "10/20" -- takes the normal range.** One of the
  four rows reading one is filed as a melee line by the importer and is
  plainly a ranged one; it is written as ranged.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.minions_sa import _by_a_trap
from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_06.brutes import DEFENCES
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    ENCOUNTER,
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
    Ability,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Stats,
    When,
    Window,
    World,
    power,
)
from combat_engine.engine.events import (
    DamageRolled,
    Miss,
    Moved,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.query import (
    adjacent,
    distance_between,
    team,
)
from combat_engine.engine.query import defence as defence_of
from combat_engine.engine.triggers import Trigger, targets_me

#: The kinds of step a creature takes of its own accord. The rest -- push,
#: pull, slide, place -- are it being moved, which is what "willingly" rules
#: out.
_WILLING = frozenset({"walk", "charge", "run", "shift", "teleport"})


def _master_mod(c: Cast, a: Ability) -> int | None:
    """The master's ability modifier, which is what one block's attack lines
    are printed as.

    None when nothing has been made this thing's master, in which case the
    printed line has no number in it and the row cannot roll.
    """
    boss = c.master()
    stats = c.world.get(boss, Stats) if boss is not None else None
    return None if stats is None else stats.mod(a)


# --------------------------------------------------------------------------
# m5452 -- a conjured servant: every number it rolls is somebody else's
# --------------------------------------------------------------------------


_M5452_STRAY = "its master ends a turn more than 10 squares away"


def _master_ended_turn(world: World, me: int, ev: TurnEnd) -> bool:
    boss = world.relations.sources(Relation.MASTER_OF, me)
    if not boss or ev.actor != boss[0]:
        return False
    return distance_between(world, me, boss[0]) > 10


@power(
    "m5452a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    damage=Damage("", 6),
)
def m5452a0(c: Cast) -> None:
    """No `attack=` in the header: the printed bonus is the master's
    Intelligence modifier plus two, and a header cannot say whose numbers it
    rolls unless they belong to a companion. The damage line stays in the
    header, where it is still data."""
    bonus = _master_mod(c, Ability.INT)
    if bonus is None:
        return
    if c.attack(bonus + 2, AC):
        c.hit()


@power(
    "m5452a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    damage=Damage("", 3),
)
def m5452a1(c: Cast) -> None:
    """As m5452a0, and the grab's escape DC is the master's Will rather than
    the holder's own defence.

    **Written through `c.grab(dc=)`, and the note that said it could not be
    was wrong about which channel runs first.** That note argued
    `escape.py` offers REF or FORT with `grab_vs_fort` the only override, so
    nothing could make the DC somebody else's Will. True of the *defence*
    path and not of the printed-DC override that sits in front of it:
    `escape.attempt` reads `base = printed if printed else defence(...)`, so
    a stamped `Effect.escape_dc` **replaces** the grabber's defence rather
    than pairing with it. `query.defence` is the live, levelled read of any
    creature's defence, so "equals the master's Will" is sayable exactly.

    The number is taken when the hold is laid rather than at each escape
    attempt, which is the one thing `dc=int` cannot do and the only
    difference left: a penalty landing on the master mid-fight does not
    loosen a grab already made. The `bonus is None` guard above has already
    proved there is a master to read."""
    bonus = _master_mod(c, Ability.INT)
    if bonus is None:
        return
    if c.attack(bonus, REF):
        c.hit()
        boss = c.master()
        if boss is not None:
            # Aliased on import: `defence` is a loop variable three rows
            # down, where it is the four defence keys and not this reader.
            c.grab(dc=defence_of(c.world, boss, WILL))


@power(
    "m5452a2",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5452a2(c: Cast) -> None:
    """A conjuration's whole move action, printed out because it has none of
    its own by default. Walking its speed is the widest of the listed choices
    and the only one worth offering a policy; standing, crawling and shifting
    are already in the action menu for anything that can move at all.

    **"It cannot run" is written now**, and the diagnosis that got it here
    was the row's own: `c.no_walk` exists but its docstring says it takes
    "walk **or** run", and walking its speed is what this row is *for*, so
    the gap was a run-only prohibition. `c.no_run` is that, read by
    `query.can_run`, which the run branch of `actions._movement` now gates
    on instead of `can_walk`. #670.

    **This creature still cannot be fielded, and that is said rather than
    glossed.** `m5452` is one of three entries in `content.loader.UNUSABLE`
    -- "stat line parsed to all zeroes, including hit points" -- so the
    clause cannot be exercised in play and nothing on a board will ever
    read it. The row's previous note used that to argue the verb should
    wait for a second card, which was a fair call; what changed is that
    the asymmetry is a fault in the engine on its own terms --
    `query.can_walk`'s own docstring says the pair exists "because a row
    printing only one half was being written as the stronger card or
    dropped" -- and this was the half with no mirror.

    So the verb is proved in `drivers.run_only_bar` rather than by this
    creature, which the board cannot stand up.
    """
    c.no_run(on=c.me, until=When.ENCOUNTER)
    c.move(c.speed_of())


@power(
    "m5452a3",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5452_STRAY,
    on=Trigger(TurnEnd, when=_master_ended_turn, text=_M5452_STRAY),
)
def m5452a3(c: Cast) -> None:
    """A forced walk, and the card prints no restriction beside it.

    **`c.leash()` dropped from the marker, not implemented.** Re-reading the
    card: "the zombie walks by the most direct route to the nearest
    unoccupied square that is within 10 squares of you" is a *move*, with
    the 10 squares describing where the route ends. Nothing here says the
    creature may not then leave, which is what a tether says, so the symbol
    was naming a mechanism this row never wanted.

    The price of failing to get back -- dropping to 0 hit points -- is
    `c.kill`. What is still absent is the walk: nothing moves a creature
    *towards* a named square by the most direct route, since `c.move` picks
    its own destination through the decider and `c.flee` goes the other way.

    **Written, and the kill comes with it.** `c.walk_toward` is the
    compulsion: it picks the nearest square itself rather than ranking the
    options for `World.decide`, which is the difference between a creature
    told where to go and one asked. #513.

    The card drops the creature only if the walk would have been longer than
    8 squares -- so the route *is* the condition, and it was unmeasurable
    while the walk did not exist. Measured as the distance from where it
    stood to where it must end: `c.walk_toward` returns how far it got, and
    a shortfall against the straight-line need is what "would have been
    longer" means on a board with anything in the way.

    **The need is computed before the walk, not after.** Afterwards the
    creature has moved and the distance that mattered is gone -- which is
    the shape that would have made this read 0 every time.
    """
    from combat_engine.engine.components import Position
    from combat_engine.engine.grid import distance

    master = c.master()
    if master is None:
        return
    here = c.world.get(c.me, Position)
    there = c.world.get(master, Position)
    if here is None or there is None:
        return
    # **The nearest unoccupied square within 10 of the master.** Walked as
    # the box around the master clipped to the board rather than a scan of
    # every square: the grid has no all-squares reader, and the first draft
    # invented one.
    grid = c.world.grid
    mx, my = there.square
    want = [
        (x, y)
        for x in range(mx - 10, mx + 11)
        for y in range(my - 10, my + 11)
        if grid.inside((x, y))
        and distance((x, y), there.square) <= 10
        and grid.occupant((x, y)) is None
    ]
    if not want:
        return
    goal = min(want, key=lambda sq: distance(sq, here.square))
    need = distance(here.square, goal)
    # **`on=c.me`, not the default.** `c.walk_toward` follows `c.target`
    # like every verb that is about somebody else's body, and this card is
    # about the creature itself -- written without it first and the walk
    # silently returned 0, which is the component's commonest mistake and
    # the fifth time this default has caught somebody here.
    c.walk_toward(goal, on=c.me)
    if need > 8:
        c.kill(on=c.me)
# --------------------------------------------------------------------------
# m6277
# --------------------------------------------------------------------------


_M6277_MISSED = "an enemy misses this creature with an attack"


@power(
    "m6277a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6277a0(c: Cast) -> None:
    """A rolled rider, so it is `dice=` rather than a flat value: the die is
    rolled afresh for every blow, which is what the sentence says."""
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m6277a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6277a1(c: Cast) -> None:
    for defence in DEFENCES:
        c.bonus(defence, 2, on=c.me, until=When.ENCOUNTER, when=_by_a_trap(c))


@power(
    "m6277a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4),
)
def m6277a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6277a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m6277a3(c: Cast) -> None:
    """Filed as "Melee 10/20", which is a range band and not a reach. Written
    as the normal half of the band, where there is no penalty."""
    if c.strike():
        c.hit()


@power(
    "m6277a4",
    level=1,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ALLY,
    group="m6277",
)
def m6277a4(c: Cast) -> None:
    """The burst takes in this creature as well as its allies, and `EACH_ALLY`
    leaves the caster out -- so the step for itself is the once-per-power line
    and goes behind `c.first`."""
    c.shift(1, who=c.target)
    if c.first and c.me not in c.targets:
        c.shift(1, who=c.me)


@power(
    "m6277a5",
    level=1,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M6277_MISSED,
    on=Trigger(Miss, when=targets_me, text=_M6277_MISSED),
)
def m6277a5(c: Cast) -> None:
    """The riposte is m6277a2 itself rather than a copy of it, so one damage
    line serves both. The grant is laid on the creature that missed and spent
    by the first attack that reads it, which is this one."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.grants_advantage(on=foe, once=True, until=When.EOT)
    c.use_power("m6277a2", on=foe, spend=False)


# --------------------------------------------------------------------------
# m6533
# --------------------------------------------------------------------------


@power(
    "m6533a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
)
def m6533a0(c: Cast) -> None:
    """An aura that burns whoever steps into it of their own accord.

    The ring is made so the board can draw it; the damage hangs off `Moved`
    rather than off `ZoneEntered`, because that event says nothing about how
    the creature got there and "willingly" is the whole difference. Moving
    from one square of the aura to another counts, which is what "enters a
    square in the aura" says.

    The once-per-turn limit is cleared as the creature's own turn opens.
    """
    me = c.me
    burned: set[int] = set()
    c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def stepped(ev: Moved) -> None:
        if ev.actor == me or getattr(ev, "kind_", "") not in _WILLING:
            return
        if ev.actor in burned or team(c.world, ev.actor) is team(c.world, me):
            return
        if not adjacent(c.world, me, ev.actor):
            return
        burned.add(ev.actor)
        c.flat(5, dtype=DamageType.LIGHTNING, on=ev.actor)

    def opens(ev: TurnStart) -> None:
        burned.discard(ev.actor)

    c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(TurnStart, opens, until=When.ENCOUNTER, on=me, label=f"{c.ref}:turn")


@power(
    "m6533a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6533a1(c: Cast) -> None:
    """"Half damage from any source" is not resistance, which the engine holds
    per damage type; it comes off the roll in the interrupt window, the one
    moment the number exists and has not reached hit points yet.

    Psychic is both an exception to the halving and what switches it off, so
    the two clauses are the same branch. A blow of several types counts as
    psychic if any part of it is.
    """
    me = c.me
    state = {"off": False}

    def soften(ev: DamageRolled) -> None:
        if ev.target != me:
            return
        types = ev.types()
        if DamageType.PSYCHIC in types:
            state["off"] = True
            return
        if state["off"] or DamageType.FORCE in types:
            return
        c.halve(ev)

    def opens(ev: TurnStart) -> None:
        if ev.actor == me:
            state["off"] = False

    c.watch(
        DamageRolled,
        soften,
        until=When.ENCOUNTER,
        on=me,
        window=Window.BEFORE,
        label=c.ref,
    )
    c.watch(TurnStart, opens, until=When.ENCOUNTER, on=me, label=f"{c.ref}:turn")


@power(
    "m6533a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6533a2(c: Cast) -> None:
    """Half speed, the -5 to attacks and the combat advantage handed out are
    the *whole* of what the squeezing condition is, and the printed line
    waives all three -- so the hold comes off as it lands rather than three
    counterweights being written against it. Level 3 settled this shape."""
    _squeezes_freely(c)


@power(
    "m6533a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.LIGHTNING),
)
def m6533a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m6559
# --------------------------------------------------------------------------


@power(
    "m6559a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6559a0(c: Cast) -> None:
    """A punishment aura that costs the creature its own composure: the daze
    is part of the printed clause and goes on itself, not on the attacker.

    Hung on `Miss` rather than on the aura's own membership, because the
    trigger is the swing and not the standing: an enemy adjacent at the moment
    it misses is the whole sentence.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def missed(ev: Miss) -> None:
        if ev.attacker == me or not adjacent(c.world, me, ev.attacker):
            return
        if team(c.world, ev.attacker) is team(c.world, me):
            return
        if ev.target != me and team(c.world, ev.target) is not team(c.world, me):
            return
        c.flat(4, on=ev.attacker)
        c.dazed(on=me, until=When.SONT)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6559a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m6559a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6559a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m6559a2(c: Cast) -> None:
    """The Effect line runs whether or not the blow lands and names one ally,
    so it is outside the hit branch and behind `c.first`."""
    if c.strike():
        c.hit()
        c.push(1)
    if c.first:
        mates = sorted(a for a in c.allies() if c.adjacent(a))
        if mates:
            mate = c.choose(mates, "m6559a2: which ally steps")
            if mate is not None:
                c.shift(1, who=mate)
