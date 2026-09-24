"""Monster abilities, level 8: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=13)` and `Damage("2d6", 9)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the seven levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits or triggered actions and are written as such; a printed range
of "10/20" takes the **normal** range; a stat block that prints no range at
all means melee 1; and a row that moves and swings takes the swing first,
because the movement picks its own destination and one taken first can leave
the target out of reach. The two rows here that name their order outright --
"moves its speed and then uses ...", "a javelin attack followed by a charge"
-- say so, and are written as printed.

Three things this level needed that the levels below did not. **A burn that
changes hands**: an ongoing damage that moves to a friend of whoever shakes
it off. `SavingThrow` is the only announcement that a save happened and it is
emitted *before* the effect it answers is ended, which is the one moment the
creature still carrying the burn can be named; the burn is applied through
`world.effects` rather than `c.ongoing` so that it has a label, because
`SavingThrow.against` is the effect's `str` and the label is what is in it.
**A row that answers its own downfall**: `Dropped` names the creature that
went down, which on these three rows is exactly the subject the printed
sentence has -- "the m4981 drops to 0 hit points", not "it drops an enemy" --
so it is the right event here where it would be the wrong one for an
attacker-side line. And **a second reading of the same trigger**: "when an
enemy moves adjacent" is `AdjacencyGained` rather than a move event, because
`MoveStart` fires before anything has moved and `MoveEnd` cannot say whether
the creature was already standing there; that is the arrangement m2837a1
settled on.

`c.charge_at` is the engine's now -- a walk into reach plus a swing marked as
a charge -- so the private copy levels 5 and 7 grew is not imported here. The
helpers that recharge on a printed sentence, that read the drop off an attack
roll, that find a free square, and that pay out for having covered ground
were written for levels 2 to 7 and are imported rather than copied.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_02.skirmishers import _had_advantage
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _recharge_on,
)
from combat_engine.content.monsters.level_06.skirmishers import _after_moving, _renew
from combat_engine.content.monsters.level_07.skirmishers import _dodges_openings
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
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
    Square,
    UpTo,
    Usage,
    When,
    distance,
    power,
    use,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    Bloodied,
    Dropped,
    Hit,
    Miss,
    SavingThrow,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, allies, distance_between
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    enemy_within,
    targets_me,
)


def _covered_ground(c: Cast, dice: str, far: int, until: When) -> None:
    """An extra die on its attacks for having ended its move far from its start.

    Measured the way the printed line measures it: where it ended against
    where the move began, not how many squares it walked. "On its turn" is a
    real clause -- being shoved four squares on somebody else's turn is not
    this -- so whose turn it is is asked as the move ends. Dice rather than a
    flat number, so it is rolled as the blow lands instead of riding along as
    a damage modifier, and the hold is replaced rather than stacked when the
    creature earns it again on the next turn.
    """
    me, ref = c.me, c.ref
    held: list[Effect] = []

    def rider(ev: Hit) -> None:
        if ev.attacker == me:
            c.damage(dice, on=ev.target, detail=ref)

    def far_enough(_kind: str, start: Square | None, end: Square, _steps: int) -> None:
        if start is None or c.turn_of() != me or distance(start, end) < far:
            return
        _renew(
            c,
            held,
            lambda: c.watch(Hit, rider, until=until, on=me, label=f"{ref} range"),
        )

    _after_moving(c, far_enough)


def _steps_either_side(c: Cast, squares_: int) -> None:
    """"Before or after the attack, it can shift" -- one choice, not two steps.

    Asked once and taken on whichever side the answer names, which is what
    m401a3 settled on for the same printed shape.
    """
    early = c.may("step before the attack")
    if early:
        c.shift(squares_)
    if c.strike():
        c.hit()
    if not early:
        c.shift(squares_)


def _adjacent_foe(c: Cast, ref: str) -> int | None:
    """Somebody in reach to swing at, for a row that attacks more than once."""
    beside = sorted(foe for foe in c.enemies() if c.adjacent(foe))
    return c.choose(beside, f"{ref}: which enemy") if beside else None


# ==========================================================================
# Skirmishers
# ==========================================================================


# --------------------------------------------------------------------------
# m3079
# --------------------------------------------------------------------------


@power(
    "m3079a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.SLEEP],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m3079a0(c: Cast) -> None:
    """A venom that puts its victim out on the first save it fails.

    "First Failed Saving Throw" is `escalate`, which runs on every failed
    save -- so the step ends the hold it came from and applies one carrying
    no escalation of its own, and the chain can only ever fire once. The new
    condition *replaces* the old, which is what "unconscious instead of
    slowed" says; two holds would be two saving throws against one bite.
    """

    def sleep(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=eff.owner)

    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=sleep)


@power(
    "m3079a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m3079a1(c: Cast) -> None:
    """Blink across the room and bite whatever is standing there.

    The printed order is named outright, so the usual arrangement -- swing
    first, because movement picks its own destination -- is not the printed
    one and is not taken. The row declares no target for the same reason: the
    bite is used after the jump, so it picks its own from wherever it lands.
    """
    c.teleport(10)
    use(c.world, c.me, "m3079a0", spend=False)


_M3079_CLOSED = "an enemy moves adjacent to the m3079"


@power(
    "m3079a2",
    level=8,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=11),
    trigger=_M3079_CLOSED,
    on=Trigger(AdjacencyGained, when=enemy_within(1), text=_M3079_CLOSED),
)
def m3079a2(c: Cast) -> None:
    """Whoever closes is thrown somewhere else before they can swing.

    Filed as a move action and printed as an immediate interrupt; the
    trigger line is what says which it is. `AdjacencyGained` is the moment
    the printed sentence names -- `MoveStart` fires before anything has
    moved, and `MoveEnd` cannot tell closing in from a step taken while
    already adjacent. The dispatcher aims a single-enemy row at whoever the
    event was about, so no choosing is needed.
    """
    if c.strike():
        c.teleport(4, who=c.target)


# --------------------------------------------------------------------------
# m353
# --------------------------------------------------------------------------


@power(
    "m353a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4),
)
def m353a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m353a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4),
)
def m353a1(c: Cast) -> None:
    """A printed range of "10/20" takes the normal range, which is what the
    levels below settled."""
    if c.strike():
        c.hit()


@power(
    "m353a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m353a2(c: Cast) -> None:
    """A throw and then a run at somebody.

    The throw is the row that prints it rather than a copy. `c.charge_at` is
    a walk into reach plus a swing marked as a charge -- the flag is what
    puts `charge` on the attack events and in both modifier contexts, which
    is what every charge rider in the tree reads.

    The printed line names no target for the charge, so the nearest enemy is
    offered first: the creature it just threw at is often ten squares off and
    a charge that cannot reach is no charge at all.
    """
    if c.target is not None:
        use(c.world, c.me, "m353a1", targets=[c.target], spend=False)
    near = sorted(c.enemies(), key=lambda foe: (c.distance(foe), foe))
    victim = c.choose(near, "m353a2: which enemy it charges") if near else None
    if victim is not None:
        c.charge_at(victim)


@power(
    "m353a3",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m353a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it has no target, no
    attack and no moment at which it would be used."""
    _covered_ground(c, "1d8", 4, When.SONT)


# --------------------------------------------------------------------------
# m4963
# --------------------------------------------------------------------------


#: The label the spreading burn is kept under. `SavingThrow.against` is the
#: effect's `str`, which contains the label, and that is the only way a save
#: against *this* ongoing damage can be told from any other.
_M4963_BURN = "m4963a2 ongoing"


def _the_burn(c: Cast) -> Effect | None:
    """Whoever is carrying the burn just now, if anybody.

    Read off the effect table rather than held in a closure: the row
    recharges, so a second use would otherwise leave two listeners each
    remembering a different carrier.
    """
    return next(
        (e for e in c.world.effects.live.values() if e.label == _M4963_BURN), None
    )


def _spreads(c: Cast, victim: int) -> None:
    """Ongoing psychic damage that jumps to a friend of whoever shakes it off.

    The save is caught on `SavingThrow`, which is emitted before the effect
    it answers is ended -- the one moment both the creature that saved and
    the burn itself are still there to be read.

    The two watches are armed once a fight. The row recharges, and a second
    use would otherwise hand the burn on twice for one saving throw.
    """
    me, ref = c.me, c.ref
    burn = (5, DamageType.PSYCHIC)

    def light(who: int) -> None:
        c.world.effects.apply(who, me, When.SAVE_ENDS, label=_M4963_BURN, ongoing=burn)

    light(victim)
    if any(e.label == ref for e in c.world.effects.of(me)):
        return

    def passed_on(ev: SavingThrow) -> None:
        if not ev.saved or _M4963_BURN not in ev.against:
            return
        near = sorted(
            (distance_between(c.world, ev.actor, mate), mate)
            for mate in allies(c.world, ev.actor)
            if alive(c.world, mate) and distance_between(c.world, ev.actor, mate) <= 10
        )
        if near:
            light(near[0][1])

    def expires(ev: Dropped) -> None:
        if ev.actor != me:
            return
        held = _the_burn(c)
        if held is None:
            return
        who = held.owner
        c.world.effects.end(held, "m4963a2 ended")
        c.flat(15, dtype=DamageType.PSYCHIC, on=who)

    c.watch(SavingThrow, passed_on, until=When.ENCOUNTER, on=me, label=ref)
    c.watch(Dropped, expires, until=When.ENCOUNTER, on=me, label=f"{ref} ends")


@power(
    "m4963a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 9),
)
def m4963a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m4963a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4963a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


@power(
    "m4963a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4963a2(c: Cast) -> None:
    """"Recharge if the power misses" on top of the die the database files.

    `_recharge_on` is the printed sentence and the header's 6 is the roll;
    the two only ever agree to make the row available sooner. The row is
    spent before its body runs, so there is always something to give back by
    the time the miss is announced.
    """
    me = c.me
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == "m4963a2")
    if c.strike():
        c.hit()
        if c.target is not None:
            _spreads(c, c.target)


@power(
    "m4963a3",
    level=8,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m4963a3(c: Cast) -> None:
    """One step, or a run and a swing -- the printed line offers a choice.

    "Moves its speed and then uses" names its order outright, so the usual
    arrangement of swinging first is not taken here. The row declares no
    target: after the run, the blow picks its own from wherever it arrives.
    """
    if c.may("move its speed and then attack"):
        c.move(c.speed_of())
        use(c.world, c.me, "m4963a0", spend=False)
    else:
        c.shift(1)


_M4963_MISSED = "an enemy misses the m4963 with a melee attack"


@power(
    "m4963a4",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4963_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M4963_MISSED),
)
def m4963a4(c: Cast) -> None:
    """Filed as a free action and printed as an immediate reaction, which is
    what the Effect line says and what is declared. `by_melee` reads the
    reach off the row behind the miss rather than off its keywords."""
    c.shift(3)


# --------------------------------------------------------------------------
# m4981
# --------------------------------------------------------------------------


@power(
    "m4981a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 9),
)
def m4981a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4981a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 9),
)
def m4981a1(c: Cast) -> None:
    _steps_either_side(c, 1)


@power(
    "m4981a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 9, kind=LIMITED),
)
def m4981a2(c: Cast) -> None:
    """The necrotic is a second expression on the same hit, so it is rolled in
    the body and the header keeps the printed line that rescales.

    The Effect line is a saving throw taken *at the end of the encounter*
    against contracting a disease, and neither half exists: there is no
    post-encounter step to roll it in and nothing a creature can catch. It is
    noted rather than approximated, because inventing a combat effect for it
    would be inventing one the card does not have.
    """
    if not c.strike():
        return
    c.hit()
    c.damage("2d6", dtype=DamageType.NECROTIC)
    if c.bloodied():
        c.note("m4981a2: a save at the end of the encounter, or m6000a3 (stage 1)")


_M4981_DOWN = "the m4981 drops to 0 hit points"


@power(
    "m4981a3",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4981_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M4981_DOWN),
)
def m4981a3(c: Cast) -> None:
    """What was inside it crawls out when it falls.

    "Effect (No Action)" is a free action with a trigger, which is what
    `FREE` plus a declared `on=` is. `Dropped` names the creature that went
    down and here that is the subject the printed sentence has, so it is the
    right event; the dispatcher lets a creature answer its own downfall,
    which is the whole of what this row is.

    The spec prints the subject's id as a shorter one belonging to a
    different stat block; this creature is the one it plainly names, and is
    the one written. `c.summon` puts the newcomer in the initiative order as
    well as on the board.
    """
    spot = _free_square_beside(c, c.me)
    if spot is not None:
        c.summon("m4980", at=spot)


# --------------------------------------------------------------------------
# m658
# --------------------------------------------------------------------------


@power(
    "m658a0",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m658a0(c: Cast) -> None:
    """Extra damage on anything that is not watching it.

    Dice rather than a flat number, so it is rolled as the blow lands instead
    of riding along as a damage modifier. Whether the target was caught out
    is read off the roll that was just made: asking the board afterwards
    answers "no" for a blow struck from concealment, and a one-shot grant has
    already been spent by then.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker == me and _had_advantage(ev):
            c.damage("2d6", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m658a1",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m658a1(c: Cast) -> None:
    _dodges_openings(c, 5)


@power(
    "m658a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 7),
)
def m658a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m658a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 4),
)
def m658a3(c: Cast) -> None:
    """"One or two creatures" is what `UpTo(2)` lets the caller choose
    between; the body is called once for each of them."""
    if c.strike():
        c.hit()


@power(
    "m658a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m658a4(c: Cast) -> None:
    """Four blows with a step between each of them.

    "Recharge when first bloodied" is the printed sentence on top of the die
    the database files; `Bloodied` is emitted on the crossing and nowhere
    else, so "first" needs no guard of its own, and the creature it names is
    this one -- the event's subject and the sentence's are the same here.

    The printed line names the melee weapon rather than the thrown one: the
    step after every blow is what makes four of them reach anybody, and four
    ranged attacks into one or two creatures would be eight rolls rather than
    four. The row declares no targets, because each step can bring a
    different creature into reach.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    for _ in range(4):
        victim = _adjacent_foe(c, "m658a4")
        if victim is not None:
            use(c.world, c.me, "m658a2", targets=[victim], spend=False)
        c.shift(1)
