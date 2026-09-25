"""Monster abilities, level 10: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=15)` and `Damage("2d8", 9)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

The conventions of the nine levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; several rows the database files as standard actions are
plainly traits or triggered actions and are written as such; a stat block
that prints no range at all means melee 1; and a row that moves and swings
takes the swing first, because the movement picks its own destination and one
taken first can leave the target out of reach.

Five things this file had to settle.

**"When it hits with X, it does X again" cannot go through `use`.** Two stat
blocks here print a free action triggered by their own at-will landing, whose
whole content is that at-will again. The trigger is answered from inside the
first use -- `Hit` is emitted while the row is still running -- and `use`
refuses to re-enter a row already in flight, so the second swing would have
been silently skipped every time. Both rows therefore declare the printed
line in their own header and roll it, which is the arrangement m106a1 and
m3113a2 settled on two levels down, and the bite itself is written once as a
helper so the two headers cannot drift apart.

**Standing up is a `ConditionEnded`.** `actions.perform` ends every prone
hold with the reason "stood up" and announces nothing else, so that pair --
the condition and the why -- is the only thing on the bus that says an enemy
got to its feet. `ConditionEnded` names its subject `target`, so the
predicate reads that and not `actor`.

**A duplicate is a summoned creature.** `c.summon` puts one on the board and
in the initiative order; its hit points are moved across by hand, because
"loses one-quarter of its current hit points" is not damage and announcing it
as damage would pay out every rider in the fight. The two clauses that make a
duplicate a duplicate are `c.bind` -- so the rows that look for one have
something to find -- and a `DamageRolled` listener that retypes everything it
deals, which is only sayable now that `dtype` is read back off the event.

**A rider's bonus is gated rather than granted and revoked.** "While the
m489 is flying" and "with its m334a2 and m334a4 powers" are both questions
asked as the roll is made, so both are `when=` gates on a modifier that goes
on when the saddle is taken and comes off when it is empty.

**Two bonuses of the same kind do not add -- but untyped ones do.**
`Mods.total` takes the larger of two bonuses sharing a named kind and sums
untyped ones, so a hold a row keeps re-earning is replaced rather than laid
beside its predecessor; `_renew` is that arrangement.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_03.skirmishers import _free_square_beside
from combat_engine.content.monsters.level_04.skirmishers import _struck
from combat_engine.content.monsters.level_05.skirmishers import _fly_speed
from combat_engine.content.monsters.level_06.skirmishers import _after_moving, _renew
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
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
    AreaBurst,
    Attack,
    AttackRolled,
    Bloodied,
    Cast,
    Condition,
    Damage,
    DamageType,
    Defense,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Ranged,
    Relation,
    Stats,
    Usage,
    When,
    Window,
    World,
    by_charge,
    distance,
    get,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    Dropped,
    Healed,
    RelationCleared,
    RelationSet,
    SurgeSpent,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    adjacent,
    alive,
    distance_between,
    flanked_by,
    moving_as,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, ally_within, both, not_me

#: The four defences, for a printed "a +2 bonus to all defenses".
EVERY_DEFENCE: tuple[Defense, ...] = (AC, FORT, REF, WILL)


def _fly(c: Cast, squares_: int) -> int:
    """Cover ground at the fly speed rather than at the walk.

    `c.move` measures `query.speed`, which is the ground speed and nothing
    else, so a printed "flies up to its fly speed" came up short by the
    difference. The difference is lent as a speed modifier for the length of
    the move and taken back afterwards -- the arrangement `_fly_at` uses for
    a charge, with no target to aim at.
    """
    extra = max(0, _fly_speed(c) - c.speed_of())
    lent = c.bonus("speed", extra, until=When.EOT, on=c.me, kind="untyped") if extra else None
    try:
        return c.move(squares_)
    finally:
        if lent is not None:
            c.world.effects.end(lent, "it landed")


def _in_the_saddle(
    c: Cast, mount_up: Any, label: str, *, level: int = 0
) -> None:
    """Hold something on whoever is riding this creature, and take it back.

    Three stat blocks print a rider's bonus and none of them are mounted when
    the trait arms, so the saddle is watched rather than read once. `level`
    is the printed "a rider of Nth level or higher", asked of the rider's own
    `Stats` -- a character and a monster both carry one.
    """
    me = c.me
    held: dict[int, list[Effect]] = {}

    def take(who: int) -> None:
        stats = c.world.get(who, Stats)
        if who in held or stats is None or stats.level < level:
            return
        held[who] = [eff for eff in mount_up(who) if eff is not None]

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.source == me:
            take(ev.target)

    def dismounted(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.RIDDEN_BY or ev.source != me:
            return
        for eff in held.pop(ev.target, []):
            c.world.effects.end(eff, "dismounted")

    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=me, label=f"{label} on")
    c.watch(RelationCleared, dismounted, until=When.ENCOUNTER, on=me, label=f"{label} off")
    rider = c.rider()
    if rider is not None:
        take(rider)


# ==========================================================================
# m2914
# ==========================================================================


def _m2914_bite(c: Cast, victim: int) -> None:
    """The bite both of the m2914's attack rows make.

    Two totals on one line and a header holds one, so the printed base stays
    in the header -- which is what rescales -- and the second die is rolled
    here. Whether the target was already down is asked **before** the blow:
    the heavier line is for a creature that was lying there, not for one this
    attack has just floored.
    """
    down = c.is_(Condition.PRONE, on=victim)
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    if down:
        c.damage("1d8", on=victim)
        c.ongoing(5, on=victim)
    else:
        c.prone(on=victim)


@power(
    "m2914a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m2914a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.target is not None:
        _m2914_bite(c, c.target)


_M2914_STOOD = "an enemy adjacent to the m2914 stands up"


def _stood_up_beside(world: World, me: int, ev: ConditionEnded) -> bool:
    """Getting to your feet, as the bus reports it.

    `actions.perform` ends the prone hold with the reason "stood up" and
    emits nothing else, so the condition and the why together are the only
    thing that distinguishes standing from a corpse's holds being cleared.
    `ConditionEnded` names its subject `target`, not `actor`.
    """
    if ev.condition is not Condition.PRONE or ev.why != "stood up":
        return False
    if ev.target == me or team(world, ev.target) is team(world, me):
        return False
    return adjacent(world, me, ev.target)


@power(
    "m2914a1",
    level=10,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=15),
    trigger=_M2914_STOOD,
    on=Trigger(ConditionEnded, when=_stood_up_beside, text=_M2914_STOOD),
)
def m2914a1(c: Cast) -> None:
    """It puts the enemy straight back down.

    No damage line at all: the printed hit is that the creature never got
    up. The hold is laid again rather than the standing being refused --
    `actions.perform` has already ended the old one by the time this window
    opens, and the list it is walking was built before the new hold exists,
    so the fresh one survives.

    Declared with no target and aimed off the trigger: the dispatcher only
    points a row that takes one enemy, and this one is about whoever just
    stood up rather than whoever is nearest.
    """
    who = getattr(c.trigger, "target", None)
    if who is not None and c.strike(on=who):
        c.prone(on=who)


_M2914_BIT = "the m2914 hits with its m2914a0 attack"


def _bit_with_m2914a0(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power == "m2914a0"


@power(
    "m2914a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
    trigger=_M2914_BIT,
    on=Trigger(Hit, when=_bit_with_m2914a0, text=_M2914_BIT),
)
def m2914a2(c: Cast) -> None:
    """It leaps off the first victim and lands on somebody else.

    The bite is declared here rather than reached through m2914a0. This row
    answers that row's own `Hit`, so m2914a0 is in flight when the free
    action resolves and `use` refuses to re-enter a row already in flight --
    the second bite would have been silently skipped every time. The line is
    copied into the header because the engine offers nowhere else to put it;
    the body itself is shared, so the two cannot drift apart.

    A jump is a move and the engine has no separate op for one. The waiver
    names the triggering target and nobody else, which is exactly what the
    printed sentence exempts.
    """
    victim = getattr(c.trigger, "target", None)
    waiver = c.no_provoke(from_=victim, until=When.EOT) if victim is not None else None
    try:
        c.move(8)
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "it has landed")
    prey = _adjacent_foe(c, c.ref)
    if prey is not None:
        _m2914_bite(c, prey)


# ==========================================================================
# m330
# ==========================================================================


@power(
    "m330a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
)
def m330a0(c: Cast) -> None:
    """Only the burn is fire; the blow itself is printed untyped."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


_M330_BIT = "the m330 hits with its m330a0 attack"


def _bit_with_m330a0(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power == "m330a0"


@power(
    "m330a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
    trigger=_M330_BIT,
    on=Trigger(Hit, when=_bit_with_m330a0, text=_M330_BIT),
)
def m330a1(c: Cast) -> None:
    """It runs straight off one victim into another.

    `c.charge_at` is the card for this and cannot be used: it reaches the
    swing through `use`, and the row it would reach for -- m330a0 -- is in
    flight, since this free action answers that row's own `Hit`. So the flag
    is raised by hand, `c.run_at` walks the approach, and the printed line is
    rolled from this header. The flag is what puts `charge` on the attack
    events and in both modifier contexts, which is what every charge rider
    reads, and it comes back down afterwards.

    Six squares is this creature's speed, so the approach needs no limit of
    its own beyond the one the printed line and the legs agree on.
    """
    struck = getattr(c.trigger, "target", None)
    prey = sorted(f for f in c.enemies() if f != struck and c.distance(f) <= 6)
    victim = c.choose(prey, "m330a1: which other target") if prey else None
    if victim is None:
        return
    c.charge = True
    try:
        c.run_at(victim)
        if c.strike(on=victim):
            c.hit(on=victim)
            c.ongoing(5, DamageType.FIRE, on=victim)
    finally:
        c.charge = False


@power(
    "m330a2",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m330a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: reaching into the
    molten thing costs whoever does it.

    Watched on `AttackRolled` rather than on the window: an opportunity
    window is an offer, and the printed line is about the swing that comes of
    it. The flag rides on every attack event for exactly this.
    """
    me = c.me

    def scorch(ev: AttackRolled) -> None:
        if ev.target == me and ev.attacker != me and getattr(ev, "opportunity", False):
            c.ongoing(5, DamageType.FIRE, on=ev.attacker)

    c.watch(AttackRolled, scorch, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m334
# ==========================================================================


#: The two rows a level 10 rider improves. Read by the trait's gate, which is
#: asked as each attack is rolled.
_M334_SHARPENED = ("m334a2", "m334a4")


@power(
    "m334a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m334a0(c: Cast) -> None:
    """A rider worth having sharpens two of its rows.

    The bonus sits on the mount and is gated on which row is being rolled --
    the attack context carries the ref, which is the only thing that can tell
    m334a2 from m334a1. Untyped, because the printed line names no kind.

    "Friendly" is the side the rider is on, asked when the saddle is taken;
    the level is the rider's own.
    """
    me = c.me

    def with_those(ctx: dict[str, Any]) -> bool:
        return ctx.get("power") in _M334_SHARPENED

    def mount_up(who: int) -> list[Effect | None]:
        if who not in c.allies():
            return []
        return [
            c.bonus("attack", 2, until=When.ENCOUNTER, on=me, kind="untyped", when=with_those)
        ]

    _in_the_saddle(c, mount_up, c.ref, level=10)


@power(
    "m334a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 5),
)
def m334a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m334a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 10),
)
def m334a2(c: Cast) -> None:
    """The step is an Effect line and is printed after the attack, so it is
    taken whether or not the shot landed."""
    if c.strike():
        c.hit()
    c.shift(3)


@power(
    "m334a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m334a3(c: Cast) -> None:
    """Both attacks, in the printed order, with a step between them.

    Declared with no target: each half picks its own, and after the step they
    are rarely the same creature. The rows that print the two lines are used
    rather than copied, so their damage stays in one place.
    """
    use(c.world, c.me, "m334a1", spend=False)
    c.shift(1)
    use(c.world, c.me, "m334a2", spend=False)


@power(
    "m334a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 10, kind=LIMITED),
)
def m334a4(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m445
# ==========================================================================


@power(
    "m445a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m445a0(c: Cast) -> None:
    """Healing goes half as far inside the ring.

    `c.half_healing` on everybody standing in it would halve **every** heal
    they take, and the printed line is about a surge in particular. So the
    surge is what is watched -- `SurgeSpent` is emitted from the one place
    that decrements a pool -- and the halving is laid on for exactly the one
    heal that follows it, then ended off the `Healed` it has already bitten.
    """
    me, ref = c.me, c.ref
    ring = c.aura(3, until=When.ENCOUNTER)

    def spent(ev: SurgeSpent) -> None:
        who = ev.actor
        if who not in c.world.zones.occupants(ring) or who not in c.enemies():
            return
        hold = c.half_healing(on=who, until=When.ENCOUNTER)
        if hold is None:
            return

        def done(healed: Healed) -> None:
            if healed.target == who and not hold.ended:
                c.world.effects.end(hold, "the surge is spent")

        hold.subs.append(c.world.bus.on(Healed, done, owner=me))

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m445a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m445a1(c: Cast) -> None:
    """Underwater is a property of the fight, which `c.terrain` asks, and
    the target's type line says whether it belongs there. Both are asked as
    the roll is made rather than now, because a fight can move into the
    water. Breathing is not a rule the engine holds and is noted."""
    me = c.me

    def out_of_its_element(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return (
            c.terrain("aquatic") and who is not None and not c.is_kind("aquatic", on=who)
        )

    c.bonus(
        "attack", 2, until=When.ENCOUNTER, on=me, kind="untyped",
        when=out_of_its_element,
    )
    c.note("m445a1: it breathes underwater")


@power(
    "m445a2",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m445a2(c: Cast) -> None:
    """It slides away the moment the charge lands.

    Both `Hit` and `Miss` are watched, because the printed moment is the end
    of the charge and exactly one of the two fires per swing. The free action
    costs nothing the engine tracks -- a free action has no budget -- so the
    step is simply taken.
    """
    me = c.me

    def slip(ev: Any) -> None:
        if getattr(ev, "attacker", None) == me and by_charge(c.world, me, ev):
            c.shift(2)

    c.watch(Hit, slip, until=When.ENCOUNTER, on=me, label=f"{c.ref} hit")
    c.watch(Miss, slip, until=When.ENCOUNTER, on=me, label=f"{c.ref} missed")


@power(
    "m445a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m445a3(c: Cast) -> None:
    """The step is an Effect line, so it is taken whether or not the blow
    landed."""
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m445a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m445a4(c: Cast) -> None:
    """Two blows at one creature, and five more if both land.

    `use` says whether a row went off and not whether it landed, so the hits
    are counted off the bus -- which is what `_struck` is for. The printed
    recharge is a sentence rather than a die and the database files a 6+ as
    well; both are honoured, and the two only ever agree to make the row
    available sooner.
    """
    me, victim = c.me, c.target
    _recharge_on(c, Bloodied, lambda ev: ev.actor == me)
    if victim is None:
        return
    hits = _struck(c, "m445a3", 2, victim)
    if hits.count(victim) >= 2:
        c.flat(5, on=victim)


@power(
    "m445a5",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m445a5(c: Cast) -> None:
    """A disguise and nothing else: the shape carries no statistics, gates no
    other row, and the way through it is an Insight check, which the engine
    has no skills to roll."""
    c.note("m445a5: it appears as a young female humanoid until it changes back")


# ==========================================================================
# m489
# ==========================================================================


@power(
    "m489a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m489a0(c: Cast) -> None:
    """Its rider is a hard target while the thing is in the air.

    "While flying" is what the creature is doing now, which is
    `query.moving_as` -- `Movement.modes` only ever said what it *could* do,
    and this creature can always fly. The four defences are four separate
    modifiers, so nothing is competing with anything: one "+2 to all
    defenses" written as a single mod would be a +2 to nothing.
    """
    me = c.me

    def aloft(_ctx: dict[str, Any]) -> bool:
        return moving_as(c.world, me, "fly")

    def mount_up(who: int) -> list[Effect | None]:
        return [
            c.bonus(defended, 2, until=When.ENCOUNTER, on=who, kind="untyped", when=aloft)
            for defended in EVERY_DEFENCE
        ]

    _in_the_saddle(c, mount_up, c.ref)


@power(
    "m489a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m489a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _flying(world: World, eid: int) -> bool:
    """The printed Requirement "must be flying".

    What the creature is doing rather than what it could do:
    `movement.mode_of` puts anything with a fly speed in the air whenever it
    moves, and `movement.settle` brings it down at the end of its turn, so
    the flag is true exactly while it is up there.
    """
    return moving_as(world, eid, "fly")


@power(
    "m489a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
    requires=_flying,
    requires_text="the m489 must be flying",
)
def m489a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m489a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 3),
)
def m489a3(c: Cast) -> None:
    """The secondary is a second attack line, and a second line's printed
    bonus is trimmed by hand the way `Attack.bonus_for` trims the header's.
    Only the burn is poison."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if c.attack(c.world.scaling.trim(13, c.level), FORT, on=victim):
        c.ongoing(10, DamageType.POISON, on=victim)


#: What m489a4 may swing during its flight. The card names one of its own
#: rows and one belonging to another stat block entirely -- the same
#: cross-reference the level 8 and level 9 batches each found twice -- and
#: these two are the rows this creature plainly means: the one it leads with
#: and the one that exists only while it is in the air.
_M489_FLYBY = ("m489a1", "m489a2")


@power(
    "m489a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m489a4(c: Cast) -> None:
    """A pass: it comes down on somebody and keeps going.

    The swing goes first where there is anything in reach, because the flight
    picks its own destination and one taken first can leave the target
    behind; with nobody in reach it flies and then swings, which is the same
    printed sentence read the other way round. Either way the waiver names
    the creature it struck and nobody else, which is what the printed line
    exempts.
    """
    victim = _adjacent_foe(c, c.ref)
    if victim is None:
        _fly(c, _fly_speed(c))
        later = _adjacent_foe(c, c.ref)
        if later is not None:
            use(c.world, c.me, _M489_FLYBY[0], targets=[later], spend=False)
        return
    ref = c.choose(list(_M489_FLYBY), "m489a4: which attack") or _M489_FLYBY[0]
    use(c.world, c.me, ref, targets=[victim], spend=False)
    waiver = c.no_provoke(from_=victim, until=When.EOT)
    try:
        _fly(c, _fly_speed(c))
    finally:
        if waiver is not None:
            c.world.effects.end(waiver, "the pass is over")


# ==========================================================================
# m5002
# ==========================================================================


@power(
    "m5002a0",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5002a0(c: Cast) -> None:
    """Five more for having covered ground.

    Measured the way the printed line measures it -- where the move ended
    against where it began, not how many squares were walked -- and read at
    the end of each move, which is the only moment both ends are known.

    A flat damage modifier rather than dice rolled on the hit, because the
    printed line says "extra damage" with no die, and it is *replaced* each
    time it is earned: an untyped bonus stacks with another untyped bonus, so
    a second move in the same turn would otherwise be worth ten.
    """
    me = c.me
    held: list[Effect] = []

    def far_enough(_kind: str, start: Any, end: Any, _steps: int) -> None:
        if start is None or c.turn_of() != me or distance(start, end) < 4:
            return
        _renew(
            c,
            held,
            lambda: c.bonus("damage", 5, until=When.SONT, on=me, kind="untyped"),
        )

    _after_moving(c, far_enough)


@power(
    "m5002a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 7),
)
def m5002a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5002a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 4),
)
def m5002a2(c: Cast) -> None:
    """Come back within reach and it bites again.

    `AdjacencyGained` read from the victim's side: `mover` has to be the
    victim, because the printed sentence is about the target's approach and
    not about the m5002's. The pair is emitted mirrored, so `actor` is asked
    as well or one approach is counted twice.

    "Willingly" is what the event's `mover` field says as much as anything
    can: a shove names the shover as its source, and the mover is the one
    that moved. The swing itself is the row used again -- by then the first
    use is long finished, so nothing is in flight -- and the watch is spent
    on the first one, which is the printed "can use this attack".

    The step is an Effect line and is taken whether or not the blow landed.
    """
    me, ref = c.me, c.ref
    if c.strike():
        c.hit()
        victim = c.target

        def closed(ev: AdjacencyGained) -> None:
            if ev.mover == victim and ev.actor == victim and ev.other == me:
                use(c.world, me, ref, targets=[victim], spend=False)

        c.watch(
            AdjacencyGained, closed, until=When.EOTNT, on=me, once=True,
            label=f"{ref} waiting",
        )
    c.shift(2)


@power(
    "m5002a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5002a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.PSYCHIC)


_M5002_BIT = "the m5002 hits with m5002a1 or m5002a2"


def _bit_with_a_claw(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power in ("m5002a1", "m5002a2")


@power(
    "m5002a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger=_M5002_BIT,
    on=Trigger(Hit, when=_bit_with_a_claw, text=_M5002_BIT),
)
def m5002a4(c: Cast) -> None:
    """Extra damage on the triggering blow, which is a packet of its own
    rather than a modifier -- a modifier would be untyped and add to whatever
    else was riding along, and this one has a type.

    The printed recharge is a sentence on top of the die the database files:
    it comes back when psychic damage is done **to** it.
    """
    me = c.me
    _recharge_on(
        c,
        DamageApplied,
        lambda ev: ev.target == me and ev.amount > 0 and ev.dtype is DamageType.PSYCHIC,
    )
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.damage("2d6", dtype=DamageType.PSYCHIC, on=victim)


_M5002_FRIEND_BLED = "an ally within 3 squares of the m5002 is first bloodied"


@power(
    "m5002a5",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5002_FRIEND_BLED,
    on=Trigger(
        Bloodied, when=both(ally_within(3), not_me), text=_M5002_FRIEND_BLED
    ),
)
def m5002a5(c: Cast) -> None:
    """"First bloodied" needs no guard: `Bloodied` is emitted on the crossing
    and nowhere else. The swing picks its own target, which is what a row
    with no printed target line means."""
    use(c.world, c.me, "m5002a1", spend=False)


# ==========================================================================
# m82
# ==========================================================================


def _duplicates(c: Cast) -> list[int]:
    """Every live duplicate of this stat block.

    A duplicate is bound to the creature that made it, so the pack is the
    maker's servants -- and a duplicate has all of the m82's rows, so one
    holding none of its own reads its maker's list and finds its siblings.
    Its own list is preferred where it has one: every creature on the audit
    board is somebody's servant, and reaching for the master first made this
    answer the wrong question there.
    """
    mine = c.world.relations.targets(Relation.MASTER_OF, c.me)
    owner = c.me if mine else (c.master() or c.me)
    return sorted(
        d
        for d in c.world.relations.targets(Relation.MASTER_OF, owner)
        if d != c.me and alive(c.world, d)
    )


def _has_a_duplicate(world: World, eid: int) -> bool:
    return bool(_duplicates(Cast(world=world, me=eid, ref="m82")))


def _unmake(c: Cast, dup: int, why: str) -> None:
    """Take a duplicate off the board.

    `World.despawn` rather than a killing blow: the printed line says a
    duplicate is absorbed or simply stops being, and dealing it enough damage
    to fell it would announce a death and pay out every rider that answers
    one. Despawning unwinds the effects and relations it was holding up, and
    `Encounter.advance` steps over a slot whose creature has left play.
    """
    if c.world.get(dup, Health) is not None:
        c.note(f"{c.ref}: a duplicate is gone -- {why}")
        c.world.despawn(dup)


@power(
    "m82a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 6),
)
def m82a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m82a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
    requires=_has_a_duplicate,
    requires_text="the m82 must have a duplicate",
)
def m82a1(c: Cast) -> None:
    """It bursts one of its own copies.

    Declared with no target because the burst is centred on the duplicate
    rather than anywhere the header could name: a target list is chosen
    before the body runs, and the origin with it. The squares are gathered by
    hand from the duplicate's own footprint instead, which is what an area
    burst 1 centred there covers.

    Hit or miss, the daze lands and the m82 pays 25. The copy is spent either
    way -- the printed line ends every duplicate on this row being used, and
    the one that went off is the one that is gone.
    """
    me = c.me
    pack = _duplicates(c)
    dup = c.choose(pack, "m82a1: which duplicate bursts") if pack else None
    if dup is None:
        return
    for victim in sorted(c.in_squares(spread(squares(c.world, dup), 1), side="enemy")):
        if c.strike(on=victim):
            c.hit(on=victim)
        c.dazed(until=When.SAVE_ENDS, on=victim)
    _unmake(c, dup, "it burst")
    c.flat(25, on=me)


def _unbloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and not health.bloodied


@power(
    "m82a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.PSYCHIC],
    requires=_unbloodied,
    requires_text="the m82 must not be bloodied",
)
def m82a2(c: Cast) -> None:
    """Another of itself, with a quarter of what it has left.

    `c.summon` is both halves of putting one on the board: the creature and
    the initiative slot, which is what "makes an initiative check and joins
    the battle" asks for. Its hit points are moved across by hand -- "loses
    one-quarter of its current hit points" is not damage, and announcing it
    as damage would bloody the m82 on its own copy and pay out every rider
    in the fight.

    Three clauses hang on the copy. It is **bound**, which is what the rows
    that look for a duplicate read. It cannot make copies of its own, which
    is `c.forbid` on this very row. And everything it deals is psychic, which
    is `DamageRolled.dtype` written in the interrupt window -- the field is
    read back now, so setting it changes the type that lands.

    The last two clauses are watches on the m82's own clock: a copy that
    drifts more than ten squares off is gone, and so are all of them when the
    m82 itself goes down.
    """
    me = c.me
    health = c.world.get(me, Health)
    where = _free_square_beside(c, me)
    if health is None or where is None or len(_duplicates(c)) >= 4:
        return
    share = max(1, health.hp // 4)
    dup = c.summon("m82", at=where)
    if not dup:
        return
    health.hp = max(1, health.hp - share)
    theirs = c.world.get(dup, Health)
    if theirs is not None:
        theirs.hp = share
    c.bind(on=dup)
    c.forbid("m82a2", on=dup, until=When.ENCOUNTER)

    def as_psychic(ev: DamageRolled) -> None:
        if ev.source == dup:
            ev.dtype = DamageType.PSYCHIC

    def strayed(ev: MoveEnd) -> None:
        if ev.actor in (me, dup) and distance_between(c.world, me, dup) > 10:
            _unmake(c, dup, "it strayed out of reach")

    def fell(ev: Dropped) -> None:
        if ev.actor == me:
            _unmake(c, dup, "the m82 went down")

    c.watch(
        DamageRolled, as_psychic, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} psychic",
    )
    c.watch(MoveEnd, strayed, until=When.ENCOUNTER, on=me, label=f"{c.ref} leash")
    c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label=f"{c.ref} ends")


@power(
    "m82a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    requires=_has_a_duplicate,
    requires_text="the m82 must have a duplicate",
)
def m82a3(c: Cast) -> None:
    """It takes a copy back into itself. Only an adjacent one, which is the
    printed reach, and the fifty is a flat number rather than a surge."""
    beside = [d for d in _duplicates(c) if c.adjacent(d)]
    dup = c.choose(beside, "m82a3: which duplicate is absorbed") if beside else None
    if dup is None:
        return
    _unmake(c, dup, "it was absorbed")
    c.heal(50, on=c.me)


@power(
    "m82a4",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m82a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it fights better
    beside itself.

    The flank is asked again on the `Hit`, because one can be broken between
    the declaration and the blow, and the partner has to be one of its own
    copies -- `flanked_by` says only that somebody is on the other side. The
    die is rolled as the blow lands rather than ridden along as a damage
    modifier, which would lose the "on melee attacks" clause: the damage
    context carries no reach, so the row behind it is looked up instead.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not flanked_by(c.world, ev.target, me):
            return
        p = get(ev.power)
        if p is None or p.reach_of(getattr(ev, "branch", 0)).kind != "melee":
            return
        if any(adjacent(c.world, d, ev.target) for d in _duplicates(c)):
            c.damage("1d8", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


_M82_STRUCK = "the m82 is hit by an attack"


def _hit_with_a_copy_to_hand(world: World, me: int, ev: Hit) -> bool:
    return ev.target == me and bool(_duplicates(Cast(world=world, me=me, ref="m82a5")))


@power(
    "m82a5",
    level=10,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger=_M82_STRUCK,
    on=Trigger(Hit, when=_hit_with_a_copy_to_hand, text=_M82_STRUCK),
)
def m82a5(c: Cast) -> None:
    """The copy takes it instead.

    `DamageRolled` names its target and its type and both are read back, so
    moving the blow is two assignments in the interrupt window rather than
    damage clawed off one creature and dealt to another. The listener is laid
    when the hit is announced and torn down by the packet it catches, because
    the body's `c.hit()` has not run yet -- a reaction to a `Hit` resolves
    before the damage the hit is about to deal.

    "Any effects or secondary attacks are also deflected" is not written:
    nothing on `Cast` can move a rider from one creature to another, and the
    riders are applied by the attacking row's own body. See the report.
    """
    me = c.me
    pack = _duplicates(c)
    dup = c.choose(pack, "m82a5: which duplicate takes it") if pack else None
    if dup is None:
        return
    caught: list[Effect] = []

    def deflect(ev: DamageRolled) -> None:
        if ev.target != me or not caught:
            return
        ev.target = dup
        ev.dtype = DamageType.PSYCHIC
        c.world.effects.end(caught[0], "the blow was deflected")

    caught.append(
        c.watch(
            DamageRolled, deflect, until=When.EOT, window=Window.BEFORE, on=me,
            label=f"{c.ref} deflect",
        )
    )
    c.note("m82a5: the blow is turned onto a duplicate")
