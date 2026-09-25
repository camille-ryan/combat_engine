"""Monster abilities, level 11: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=16)` and `Damage("2d4", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the ten levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits or triggered actions and are written as such; a stat block
that prints no range at all means melee 1; and a row that moves and swings
takes the swing first, because the movement picks its own destination and one
taken first can leave the target out of reach.

Five things this file had to settle.

**A printed critical line is the extra dice, not the total.** "1d12 + 12
damage, or 2d12 + 24 on a critical hit" reads as the maximum of the ordinary
line -- which `c.damage` already deals on a critical -- plus 2d12 rolled on
top. So the header keeps the ordinary line and the body adds the difference
with `c.flat(c.roll(...))`, which is the arrangement m2962a0 settled a level
down: rolling the extra through `c.damage` would maximise it too, and a
critical would come out flat.

**Two shapes, and neither is declared present.** m3033 prints one row usable
only in each of its forms, and the card never says which it starts in.
`_not_wearing` from level 6 is the answer already in the tree: the polymorph
row lays a label, and each attack row is gated on the *absence* of the other
one -- so both are open until the creature has actually chosen, and exactly
one is shut afterwards. The basic attack the loader picks is the humanoid
row, which is why humanoid is the shape the board finds it in.

**"Twice its speed" is lent, not walked twice.** `c.overrun` measures
`query.speed` and nothing else, so m483a2's double move is a speed modifier
held for the length of the trample and taken back afterwards -- the same
arrangement `_fly` uses for a flight, and the only way the ranking inside
`c.overrun` sees the further squares at all.

**Only one at a time.** m113a2 restrains one creature and the card says so,
so the row ends its own earlier hold before laying a new one. `c.suffering`
finds the victim by label; the hold is ended rather than the new one
refused, because the printed sentence is about which creature is held and
not about the row being unavailable.

**`Bloodied` about itself cannot fire on the audit board**, which halves the
caster before the fight starts. m113a5 is such a row and reports UNUSED
however correct it is; it was driven by hand, at full health, to check.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.skirmishers import _squeezes_freely
from combat_engine.content.monsters.level_06.brutes import _not_wearing
from combat_engine.content.monsters.level_06.skirmishers import _after_moving, _renew
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.brutes import _melee_ctx
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
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
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    ActionType,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    Miss,
    Position,
    Usage,
    When,
    World,
    by_melee,
    distance,
    power,
    targets_me,
    use,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    has_combat_advantage,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, both


def _flies(c: Cast, squares_: int) -> int:
    """Cover ground in the air for one move, and come down afterwards.

    Three stat blocks here print "flies N squares" and one of them has no
    fly speed at all, so the mode is lent for the length of the move and
    taken back -- `movement.mode_of` puts anything with one in the air the
    moment it moves, and `settle` would otherwise keep finding it there.
    """
    lent = c.mode("fly", squares_, until=When.EOT, on=c.me)
    try:
        return c.move(squares_)
    finally:
        if lent is not None:
            c.world.effects.end(lent, "it lands")


def _at_double_speed(c: Cast, run: Any) -> Any:
    """Do something that measures `query.speed`, with the speed doubled.

    `c.overrun` takes no distance -- it reads the legs. "Up to twice its
    speed" therefore has to be lent as a modifier for the length of the
    move, the way `_fly` lends the difference between a walk and a flight,
    or the ranking inside `c.overrun` never sees the further squares.
    """
    lent = c.bonus("speed", c.speed_of(), until=When.EOT, on=c.me, kind="untyped")
    try:
        return run()
    finally:
        if lent is not None:
            c.world.effects.end(lent, "the run is over")


def _release_earlier(c: Cast, label: str) -> None:
    """End this row's own earlier hold. "It can affect only one at a time."

    The old hold is ended rather than the new one refused: the printed
    sentence is about which creature is held, not about the row being
    unavailable while somebody is.
    """
    for who in c.suffering(label):
        for eff in list(c.world.effects.of(who)):
            if eff.label == label and eff.source == c.me:
                c.world.effects.end(eff, f"{label}: it can hold only one")


# ==========================================================================
# m113
# ==========================================================================


@power(
    "m113a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d4", 5),
)
def m113a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m113a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m113a1(c: Cast) -> None:
    """Both swings, each picking its own target.

    Declared with no target: the printed line names none, and after the
    first blow the second is rarely worth aiming at the same creature. The
    row that prints the attack is used rather than copied, so its damage
    stays in one place.
    """
    for _ in range(2):
        use(c.world, c.me, "m113a0", spend=False)


@power(
    "m113a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d4", 5),
)
def m113a2(c: Cast) -> None:
    """One creature held at a time, so the earlier hold goes first."""
    if not c.strike():
        return
    c.hit()
    _release_earlier(c, c.ref)
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m113a3",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m113a3(c: Cast) -> None:
    c.shift(1)


_M113_SWUNG_AT = "the m113 is the target of a melee attack"
_M113_BLED = "the m113 is first bloodied"


@power(
    "m113a4",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M113_SWUNG_AT,
    on=Trigger(AttackDeclared, when=both(targets_me, by_melee), text=_M113_SWUNG_AT),
)
def m113a4(c: Cast) -> None:
    """It steps aside before the blow is rolled.

    An interrupt rather than the free action the database files, because the
    printed Effect line says so and the difference is the whole of the row:
    `AttackDeclared` is announced before the die, so a step out of reach is
    still worth taking.

    The printed recharge is a sentence on top of the die the database files,
    and the two only ever agree to give the row back sooner.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    c.shift(1)


@power(
    "m113a5",
    level=11,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M113_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M113_BLED),
)
def m113a5(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else. The blow that bloodied it belongs to somebody else, so
    m113a0 is not in flight and can be reached through `use`."""
    for _ in range(2):
        use(c.world, c.me, "m113a0", spend=False)


# ==========================================================================
# m255
# ==========================================================================


@power(
    "m255a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d12", 12),
)
def m255a0(c: Cast) -> None:
    """A high-crit line. The printed "2d12 + 24 on a critical hit" is the
    maximum of the ordinary line -- which `c.damage` already deals on a
    critical -- plus 2d12 on top, and the extra is rolled with `c.flat`
    because `c.damage` would maximise that too."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("2d12"))


_M255_FRIEND_SWUNG_AT = "an enemy within 2 squares of the m255 attacks an ally of it"


def _swung_at_my_ally(world: World, me: int, ev: AttackDeclared) -> bool:
    """An enemy near me is attacking somebody on my side -- but not me.

    Sides are compared directly rather than through `query.enemies`, which
    filters out the dead; and the distance is measured to the attacker,
    which is the creature the printed line puts the radius on.
    """
    who, victim = ev.attacker, ev.target
    if who == me or victim == me:
        return False
    if team(world, who) is team(world, me):
        return False
    if team(world, victim) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 2


@power(
    "m255a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M255_FRIEND_SWUNG_AT,
    on=Trigger(AttackDeclared, when=_swung_at_my_ally, text=_M255_FRIEND_SWUNG_AT),
)
def m255a1(c: Cast) -> None:
    """A step and a swing at whoever went for its friend.

    Declared with no target and aimed off the trigger: the dispatcher only
    points a row that takes one enemy, and this one is about the creature
    that swung rather than whoever is nearest. The step comes first, because
    the printed order is the printed order and one square can be the
    difference between reaching the attacker and not.
    """
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    c.shift(1)
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and alive(c.world, foe):
        use(c.world, me, "m255a0", targets=[foe], spend=False)


# ==========================================================================
# m2885
# ==========================================================================


@power(
    "m2885a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6, dtype=DamageType.FORCE),
)
def m2885a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m2885a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6, dtype=DamageType.FORCE, kind=LIMITED),
)
def m2885a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2885_MISSED = "the m2885 is missed by a melee attack"


@power(
    "m2885a2",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2885_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M2885_MISSED),
)
def m2885a2(c: Cast) -> None:
    """It slips out of the way and goes half-there.

    Insubstantial and phasing are two separate holds because they are two
    separate things -- one halves what lands and the other is a way of
    moving -- and both run to the end of its next turn, which is what the
    card measures.
    """
    c.shift(2)
    c.insubstantial(until=When.EONT)
    c.phasing(until=When.EONT)


@power(
    "m2885a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2885a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: two more to hit for
    having covered ground.

    Measured the way the printed line measures it -- where the move ended
    against where it began, not how many squares were walked -- and read at
    the end of each move, which is the only moment both ends are known.

    The bonus is *replaced* each time it is earned rather than laid beside
    its predecessor, which a second untyped modifier would be, and it is
    gated on the attack being a melee one: the attack context carries
    `ranged` and the reach lives on the row, which is what `_melee_ctx`
    reads.
    """
    me = c.me
    held: list[Effect] = []

    def far_enough(_kind: str, start: Any, end: Any, _steps: int) -> None:
        if start is None or c.turn_of() != me or distance(start, end) < 4:
            return
        _renew(
            c,
            held,
            lambda: c.bonus(
                "attack", 2, until=When.EOT, on=me, kind="untyped", when=_melee_ctx
            ),
        )

    _after_moving(c, far_enough)


# ==========================================================================
# m2924
# ==========================================================================


@power(
    "m2924a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 3, dtype=DamageType.RADIANT),
)
def m2924a0(c: Cast) -> None:
    """The penalty is only against this creature, which is a gate asked as
    the roll is made rather than a flat three off everything the victim
    does."""
    me = c.me
    if not c.strike():
        return
    c.hit()

    def against_me(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == me

    c.penalty("attack", 3, until=When.EONT, when=against_me)


@power(
    "m2924a1",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=14),
)
def m2924a1(c: Cast) -> None:
    """A step in, a swing, and a step out.

    No damage line at all: the printed hit is the pair of conditions, and
    they are one hold carrying both -- applied separately the victim would
    get two saving throws against a thing the card says it saves against
    once.
    """
    c.shift(3)
    if c.strike():
        c.condition(Condition.WEAKENED, Condition.SLOWED, until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)
    c.shift(3)


@power(
    "m2924a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 4, dtype=DamageType.RADIANT),
)
def m2924a2(c: Cast) -> None:
    """It cuts one and moves onto another.

    m2924a0 is reached through `use` rather than copied into this header:
    this row is not answering that row's own event, so nothing is in flight
    and the printed line stays in one place. The second creature is picked
    after the step, which is the printed order and usually a different
    answer from picking it before.
    """
    me, first = c.me, c.target
    if not c.strike():
        return
    c.hit()
    c.shift(3)
    others = sorted(foe for foe in c.enemies() if foe != first and c.adjacent(foe))
    victim = c.choose(others, "m2924a2: which other target") if others else None
    if victim is not None:
        use(c.world, me, "m2924a0", targets=[victim], spend=False)


@power(
    "m2924a3",
    level=11,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m2924a3(c: Cast) -> None:
    """A pass: it comes down on somebody at some point during the flight.

    Declared with no target, because a target list is chosen before the body
    runs and the creature it swings at may be eight squares away when it
    starts. The swing goes first where there is anything in reach -- the
    flight picks its own destination and one taken first can leave the
    target behind -- and otherwise it flies and then swings, which is the
    same printed sentence read the other way round.

    This creature has no fly speed of its own, so the mode is lent for the
    length of the move and taken back. Only the burn is poison.
    """
    waiver = c.no_provoke(until=When.EOT)
    try:
        victim = _adjacent_foe(c, c.ref)
        if victim is None:
            _flies(c, 8)
            victim = _adjacent_foe(c, c.ref)
        else:
            _flies(c, 8)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the pass is over")
    if victim is not None and alive(c.world, victim) and c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(10, DamageType.POISON, on=victim)


def _has_the_drop(world: World, eid: int) -> bool:
    """The printed Requirement: combat advantage against somebody adjacent."""
    from combat_engine.engine.query import enemies

    return any(
        distance_between(world, eid, foe) <= 1 and has_combat_advantage(world, eid, foe)
        for foe in enemies(world, eid)
    )


@power(
    "m2924a4",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    requires=_has_the_drop,
    requires_text="the m2924 must have combat advantage against an adjacent enemy",
)
def m2924a4(c: Cast) -> None:
    """One square, and it has to end up beside the same creature.

    `c.shift` with no `to` offers the decider every square in range, which
    is useless for a printed line that says where the step has to finish.
    The destinations are gathered by hand: next to the target, one square
    from here, and somewhere this body fits.
    """
    me = c.me
    near = sorted(
        foe
        for foe in c.enemies()
        if c.adjacent(foe) and has_combat_advantage(c.world, me, foe)
    )
    victim = c.choose(near, "m2924a4: which enemy") if near else None
    if victim is None:
        return
    mine = squares(c.world, me)
    beside = sorted(
        sq
        for sq in c.world.reachable_squares(me, 1)
        if min(distance(sq, s) for s in squares(c.world, victim)) <= 1
        and sq not in mine
    )
    if beside:
        c.shift(to=c.world.decide(me, "shift", beside, f"{c.ref}: where it steps"))


@power(
    "m2924a5",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m2924a5(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m3033
# ==========================================================================
#
# The two shapes, and the labels the attack rows read their Requirement off.
# The card never says which one it starts a fight in, so neither row is
# gated on a form being *present*: both are open until m3033a5 has picked
# one, and from then on exactly one of them is shut. That is `_not_wearing`,
# written for the same sentence five levels down.

_M3033_BEAST = "m3033a5 beast"
_M3033_HUMANOID = "m3033a5 humanoid"


@power(
    "m3033a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
    requires=_not_wearing(_M3033_BEAST),
    requires_text="the m3033 must be in its humanoid shape",
)
def m3033a0(c: Cast) -> None:
    """The printed "crit 4d6 + 18" is the maximum of the ordinary line, which
    a critical already deals, plus 4d6 rolled on top."""
    if not c.strike():
        return
    c.hit()
    if c.crit:
        c.flat(c.roll("4d6"))


@power(
    "m3033a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
    requires=_not_wearing(_M3033_HUMANOID),
    requires_text="the m3033 must be in its beast shape",
)
def m3033a1(c: Cast) -> None:
    """The contagion is a disease track the engine has no model of, so it is
    a named hold on the save-ends clock rather than an invented condition --
    which is what `c.effect` is for, and what the rows that read it would
    look for."""
    if not c.strike():
        return
    c.hit()
    c.effect("m3033a1 exposed", until=When.SAVE_ENDS)


@power(
    "m3033a2",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m3033a2(c: Cast) -> None:
    """Two basic attacks with a step between them.

    `c.basic` swings whatever this creature's basic attack actually is,
    which follows the shape it is in rather than naming a row. Declared with
    no target: after the step the second swing is rarely the same creature.
    """
    for i in range(2):
        if i:
            c.shift(1)
        prey = _adjacent_foe(c, c.ref)
        if prey is not None:
            c.basic(on=prey)


@power(
    "m3033a3",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m3033a3(c: Cast) -> None:
    """A charge whose blow is this row's own line.

    "Usable only when charging" is satisfied by construction: the row *is*
    the charge. `c.charge_at` cannot be used, because it reaches the swing
    through `use` and the row it would reach for is this one, already in
    flight -- so the flag goes up by hand, `c.run_at` walks, and the header
    rolls. The flag is what puts `charge` on the attack events and in both
    modifier contexts, which is what every charge rider reads.

    The vacated square is read before the shove, because after it there is
    nothing left to read.
    """
    victim = c.target
    if victim is None:
        return
    pos = c.world.get(victim, Position)
    was = pos.square if pos is not None else None
    c.charge = True
    try:
        c.run_at(victim)
        if not c.strike(on=victim):
            return
        c.hit(on=victim)
        c.push(1, on=victim)
        c.prone(on=victim)
    finally:
        c.charge = False
    if was is not None:
        c.shift(to=was)


_M3033_MISSED = "an attack misses the m3033"


@power(
    "m3033a4",
    level=11,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M3033_MISSED,
    on=Trigger(Miss, when=targets_me, text=_M3033_MISSED),
)
def m3033a4(c: Cast) -> None:
    """A swing back and a step away.

    Declared with no target and aimed at whoever swung, where that creature
    is still in reach: `c.basic` rolls whichever row this shape's basic
    attack actually is.
    """
    who = getattr(c.trigger, "attacker", None)
    if who is None or not c.adjacent(who) or not alive(c.world, who):
        who = _adjacent_foe(c, c.ref)
    if who is not None:
        c.basic(on=who)
    c.shift(2)


@power(
    "m3033a5",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m3033a5(c: Cast) -> None:
    """Either shape, and taking one ends the other.

    The form carries no conditions and no movement modes: the printed line
    changes what the creature looks like and nothing else, so all it is here
    is the label m3033a0 and m3033a1 read their Requirement off. `c.form`
    does not displace a previous form the way `c.stance` displaces a stance,
    so the old shape is ended by hand.
    """
    for eff in list(c.world.effects.of(c.me)):
        if eff.label in (_M3033_BEAST, _M3033_HUMANOID):
            c.world.effects.end(eff, "it changed shape again")
    shape = c.choose([_M3033_BEAST, _M3033_HUMANOID], "which shape") or _M3033_BEAST
    c.form(until=When.ENCOUNTER, revert=MINOR, label=shape)


# ==========================================================================
# m3064
# ==========================================================================


@power(
    "m3064a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3064a0(c: Cast) -> None:
    """Narrative only: what it swallowed is recoverable from it afterwards,
    and the engine holds no inventory and no treasure."""
    c.note("m3064a0: what it destroys can be recovered from its stomach at full value")


@power(
    "m3064a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 11),
)
def m3064a1(c: Cast) -> None:
    """The rider is left as a note rather than invented: `Gear` records what
    a creature is wearing and nothing about an enhancement bonus, so there
    is no number for the printed line to reduce. See the report."""
    if c.strike():
        c.hit()
        c.note("m3064a1: the target's magic armour is decaying")


# ==========================================================================
# m483
# ==========================================================================


@power(
    "m483a0",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE),
)
def m483a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m483a1",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m483a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m483a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m483a2(c: Cast) -> None:
    """It runs through everybody in the way and burns them on the way past.

    `c.overrun` is the only thing that reports who was trampled, and who was
    trampled is exactly what the printed line burns. Called bare: with no
    destination it ranks the reachable squares by how many enemies the line
    crosses, so the run goes through people. Ending in an unoccupied space is
    the trample's own rule and `movement.overrun` already shuffles it clear.

    Twice its speed is lent for the length of the run, because `c.overrun`
    reads the legs rather than taking a distance. The waiver is the printed
    "without provoking opportunity attacks", and it names everybody because
    the printed line does.

    Ten flat, not a damage line: the printed toll is the same for each
    creature whose space it enters and no attack is rolled for it.
    """
    waiver = c.no_provoke(until=When.EOT)
    try:
        trampled = _at_double_speed(c, c.overrun)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the run is over")
    for victim in trampled:
        if alive(c.world, victim):
            c.flat(10, dtype=DamageType.FIRE, on=victim)


@power(
    "m483a3",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m483a3(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: folding into a small
    space costs this creature nothing."""
    _squeezes_freely(c)


# ==========================================================================
# m4866
# ==========================================================================


@power(
    "m4866a0",
    level=11,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4866a0(c: Cast) -> None:
    """Cold stops it slipping about.

    `c.rooted` rather than `c.immobilized`: the printed line takes the shift
    away and leaves the walk, which is the whole reason the two conditions
    are different. Read off `DamageApplied`, which is the only event that
    says how much actually came off and of what type.
    """
    me = c.me

    def chilled(ev: DamageApplied) -> None:
        if ev.target == me and ev.amount > 0 and ev.dtype is DamageType.COLD:
            c.rooted(until=When.EONT, on=me)

    c.watch(DamageApplied, chilled, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4866a1",
    level=11,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=14),
)
def m4866a1(c: Cast) -> None:
    """No damage line at all: the burn is the whole of the hit."""
    if c.strike():
        c.ongoing(10, DamageType.FIRE)


@power(
    "m4866a2",
    level=11,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4866a2(c: Cast) -> None:
    c.shift(2)


_M4866_STRUCK = "an attack hits the m4866"


@power(
    "m4866a3",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M4866_STRUCK,
    on=Trigger(Hit, when=targets_me, text=_M4866_STRUCK),
)
def m4866a3(c: Cast) -> None:
    """Five flat to everyone standing next to it, with no attack rolled.

    Declared with no target: the printed line names each adjacent enemy, and
    a burst's target list is chosen before the body runs -- which is a
    different set of creatures from the ones beside it when the blow lands.
    """
    for foe in sorted(c.within(1, side="enemy")):
        c.flat(5, dtype=DamageType.FIRE, on=foe)
