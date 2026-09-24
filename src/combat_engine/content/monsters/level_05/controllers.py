"""Monster abilities, level 5: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=10)` and `Damage("1d10", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths.

A **blast or burst with no printed target line** is read as enemies, as the
rest of the tree reads it.

Four readings this file had to settle.

**"The zone is centred on it and moves with it"** is an aura, not a zone: a
zone is a set of squares and does not follow anybody. What the aura does is
then a watch, because the damage is two points *per ally standing in it* and
a hazard's bite is a fixed number.

**"Regains hit points only once per round in this way"** is a latch that has
to outlive one call of the body -- the row is resolved once per target and
one ally can be adjacent to three of them -- so it is a module-level table
keyed by the world it happened in, not a closure.

**"Recharge when no enemy is dominated by this power"** is not a recharge at
all: nothing rolls for it and there is no turn on which it comes back. It is
an at-will with an entry condition, which is what `requires` is, and written
that way it is available exactly when the printed sentence says it is.

**"Recharges when first bloodied"** is an encounter power that gets its use
handed back. `Powers.restore` is the only thing that gives a spent row back,
and the watch that calls it is armed by the row itself -- so a creature
bloodied before it ever fired gets nothing, which is what "first" means.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_05.artillery import _mobbed, _reach_of
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    Powers,
    Ranged,
    Target,
    TurnStart,
    Usage,
    When,
    World,
    get,
    power,
    use,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    adjacent,
    alive,
    allies,
    enemies,
    has_combat_advantage,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    ally_within,
    both,
    by_melee,
    enemy_within,
    targets_me,
)

#: The four defences, for the rows that move all of them at once.
DEFENCES = (AC, FORT, REF, WILL)


def _has_an_opening(world: World, eid: int) -> bool:
    """A printed "Requirement: combat advantage", asked of the board.

    `requires` is handed the caster and no target, so the nearest thing it
    can say is that there is somebody this creature is currently getting the
    better of. Which one is then the chooser's business.
    """
    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


def _beside_an_ally(world: World, eid: int) -> bool:
    return any(a != eid and adjacent(world, a, eid) for a in allies(world, eid))


def _dominated_by(world: World, master: int, who: int) -> bool:
    """Is that creature dominated **by this one**?

    `Conditions` says only that a creature is dominated; who is holding the
    strings is on the effect that applied it, which is the half the printed
    lines here care about.
    """
    return any(
        eff.source == master and Condition.DOMINATED in eff.conditions
        for eff in world.effects.of(who)
    )


def _granted_hit(c: Cast, who: int, foe: int, ref: str = "") -> bool:
    """Did the swing somebody else was handed actually land?

    `c.grant_attack` reports that a row went off and not that it hit, and two
    rows here pay out differently for the two.
    """
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == who and ev.target == foe:
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        c.grant_attack(who, on=foe, ref=ref)
    finally:
        c.world.bus.off(sub)
    return bool(landed)


# --------------------------------------------------------------------------
# m191
# --------------------------------------------------------------------------


@power(
    "m191a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 3),
)
def m191a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m191a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 3),
    requires=_has_an_opening,
    requires_text="the m191 must have combat advantage",
)
def m191a1(c: Cast) -> None:
    """The secondary attack is a second roll against a different defence, so
    it cannot live in the header; its printed +8 is trimmed by hand the way
    `Attack.bonus_for` trims the header's, or the row would ignore whatever
    scaling the fight is being played on."""
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(8, c.level), FORT):
        c.ongoing(5, DamageType.POISON)


@power(
    "m191a2",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=9),
)
def m191a2(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the hold."""
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m191a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA, Keyword.ZONE],
    attack=Attack(vs=REF, printed=9),
)
def m191a3(c: Cast) -> None:
    """The webs are laid once for the whole power, not once per target, and
    they are named so that m191a4 below can say which sort of rough ground it
    walks through."""
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER, difficult="web", label="m191a3 web")
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m191a4",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m191a4(c: Cast) -> None:
    """Filed as a standard action and plainly a trait. `c.ignores_difficult`
    takes the label the ground was given, which is the one m191a3 gives its
    webs."""
    c.ignores_difficult("web")


# --------------------------------------------------------------------------
# m2801
# --------------------------------------------------------------------------


@power(
    "m2801a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m2801a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2801a1",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage(bonus=3),
)
def m2801a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


_M2801_KIN_DOWN = "one of its own within 10 squares drops to 0 hit points"


@power(
    "m2801a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2801_KIN_DOWN,
    on=Trigger(Dropped, when=ally_within(10), text=_M2801_KIN_DOWN),
)
def m2801a2(c: Cast) -> None:
    """The step comes first, as printed, so the bite reaches whatever the
    step brought into range. The row that prints the bite is used rather
    than copied, so its numbers stay in one place."""
    c.shift(2)
    reachable = sorted(f for f in c.within(2, side="enemy") if alive(c.world, f))
    foe = c.choose(reachable, "who the mandibles find") if reachable else None
    if foe is not None:
        use(c.world, c.me, "m2801a1", targets=[foe], spend=False)


@power(
    "m2801a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(4),
    target=NO_TARGET,
    keywords=[Keyword.ACID, Keyword.ZONE],
)
def m2801a3(c: Cast) -> None:
    """A zone that follows its maker is an aura: `c.zone` holds squares and
    squares do not walk. What it does is a watch rather than `c.hazard`,
    because the number is two points per ally standing in the gas and a
    hazard bites for a fixed amount.

    Which allies count is every one of them inside the cloud. The stat block
    names a kind of creature there and this file may not read that name, so
    the reading is its own swarm, which is what the printed sentence is
    about.
    """
    me = c.me
    cloud = c.aura(4, until=When.ENCOUNTER, label=c.ref)

    def gas(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        inside = c.world.zones.occupants(cloud)
        if ev.actor not in inside:
            return
        swarm = sum(1 for a in allies(c.world, me) if a in inside)
        if swarm:
            c.flat(2 * swarm, dtype=DamageType.ACID, on=ev.actor)

    c.watch(TurnStart, gas, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m2801a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.AREA],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d6", 2, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m2801a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


# --------------------------------------------------------------------------
# m3012
# --------------------------------------------------------------------------


@power(
    "m3012a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3012a0(c: Cast) -> None:
    """Gated on who is standing where rather than put on and taken off as
    people move: the gate is asked when the defence is read, so nothing has
    to watch the board."""
    me = c.me

    def shoulder_to_shoulder(_ctx: dict[str, Any]) -> bool:
        return _beside_an_ally(c.world, me)

    for defence in DEFENCES:
        c.bonus(defence, 2, on=me, until=When.ENCOUNTER, when=shoulder_to_shoulder)


@power(
    "m3012a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m3012a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3012a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=8),
)
def m3012a2(c: Cast) -> None:
    """"Cannot use a standard action during its next turn" is
    `Condition.SHAPED`, the one card in the table that means exactly that,
    held to the end of the victim's own next turn."""
    if c.strike():
        c.condition(Condition.SHAPED, until=When.EOTNT)


@power(
    "m3012a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_OTHER_ALLY,
)
def m3012a3(c: Cast) -> None:
    """"One ally in the burst" excludes the m3012 itself, which is what
    `ONE_OTHER_ALLY` is for. The step is printed as the ally's own choice of
    before or after, so it is offered as one."""
    friend = c.target
    if friend is None:
        return
    early = c.may("step before the attack", who=friend, default=False)
    if early:
        c.shift(1, who=friend)
    reachable = sorted(f for f in c.enemies() if alive(c.world, f))
    foe = c.choose(reachable, "who the ally swings at") if reachable else None
    if foe is not None:
        c.grant_attack(friend, on=foe)
    if not early:
        c.shift(1, who=friend)


@power(
    "m3012a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_OTHER_ALLY,
)
def m3012a4(c: Cast) -> None:
    """A whole power handed to somebody else, not just a basic attack.

    Which one is the ally's choice out of its own list, filtered to the three
    usages the printed line names and to the rows that actually attack -- a
    triggered row is left out, having a printed trigger of its own that this
    does not supply.
    """
    friend = c.target
    if friend is None:
        return
    known = c.world.get(friend, Powers)
    options = sorted(
        ref
        for ref in (known.all if known else [])
        if _is_free_attack(ref)
    )
    chosen = c.choose(options, "which power the ally uses") if options else None
    if chosen is None:
        return
    reachable = sorted(f for f in c.enemies() if alive(c.world, f))
    foe = c.choose(reachable, "who the ally uses it on") if reachable else None
    if foe is not None:
        c.grant_attack(friend, on=foe, ref=chosen)


def _is_free_attack(ref: str) -> bool:
    """An at-will, encounter or recharge attack power somebody else can be
    handed. Triggered rows are out: they come with a printed trigger this
    does not supply."""
    p = get(ref)
    return (
        p is not None
        and p.is_attack
        and not p.triggers
        and p.usage in (Usage.AT_WILL, Usage.ENCOUNTER, Usage.RECHARGE)
        and p.action is ActionType.STANDARD
    )


# --------------------------------------------------------------------------
# m3112
# --------------------------------------------------------------------------


@power(
    "m3112a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 5),
)
def m3112a0(c: Cast) -> None:
    if c.strike():
        c.hit()


#: Which round each ally last drank from m3112a1, keyed by the world it
#: happened in. The row is resolved once per target and one ally can stand
#: beside three of them, so the printed once-a-round limit cannot live in
#: the body.
_M3112_FED: dict[tuple[int, int], int] = {}


@power(
    "m3112a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 4, kind=LIMITED),
)
def m3112a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    for friend in c.within(1, of=c.target, side="ally"):
        if friend == c.me or not c.is_kind("undead", on=friend):
            continue
        key = (id(c.world), friend)
        if _M3112_FED.get(key) == c.world.round:
            continue
        _M3112_FED[key] = c.world.round
        c.heal(5, on=friend)


@power(
    "m3112a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 4, dtype=DamageType.THUNDER),
)
def m3112a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m3112a3",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3112a3(c: Cast) -> None:
    """Melee only, so the gate asks the reach of whichever row is dealing the
    blow -- the damage context carries the ref as `power`, and that is the
    only thing on it that says how far the attack reached."""
    me = c.me

    def hemmed_in(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or foe not in enemies(c.world, me):
            return False
        if _reach_of(ctx.get("power") or "") != "melee":
            return False
        return _mobbed(c, foe, me)

    c.bonus("damage", 2, until=When.ENCOUNTER, on=me, when=hemmed_in)


# --------------------------------------------------------------------------
# m359
# --------------------------------------------------------------------------


def _is_bloodied(world: World, eid: int) -> bool:
    from combat_engine.engine import Health

    health = world.get(eid, Health)
    return health is not None and health.bloodied


@power(
    "m359a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3),
)
def m359a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m359a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON, Keyword.MELEE],
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m359a1(c: Cast) -> None:
    """The surge and the thirteen hit points are two lines, not one: a
    monster's surge is a quarter of its maximum and the card names a flat
    number, so the surge is spent for nothing and the printed amount is
    healed."""
    c.basic()
    c.spend_surge()
    c.heal(13, on=c.me)


_M359_DOWN = "the m359 is reduced to 0 hit points"


@power(
    "m359a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    trigger=_M359_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M359_DOWN),
)
def m359a2(c: Cast) -> None:
    """One last swing on the way down. `c.basic` rolls whatever this
    creature's basic attack actually is, which for a monster is one of its
    own rows."""
    c.basic()


@power(
    "m359a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=8),
)
def m359a3(c: Cast) -> None:
    if c.strike():
        c.penalty(AC, 4, until=When.SAVE_ENDS)


@power(
    "m359a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.RANGED],
)
def m359a4(c: Cast) -> None:
    """The swing is the ally's, so it is granted rather than rolled here --
    and the payout differs on a hit and on a miss, which `c.grant_attack`
    does not report, so the blow is counted off the bus.

    The printed line names a kind of creature this file may not read, so the
    ally is whichever one the chooser picks.
    """
    friend = c.target
    if friend is None or friend == c.me:
        return
    reachable = sorted(f for f in c.within(1, of=friend, side="enemy") if alive(c.world, f))
    foe = c.choose(reachable, "who the ally swings at") if reachable else None
    if foe is None:
        return
    c.heal(15 if _granted_hit(c, friend, foe) else 5, on=friend)


@power(
    "m359a5",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.AREA],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 3, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m359a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


# --------------------------------------------------------------------------
# m4904
# --------------------------------------------------------------------------


@power(
    "m4904a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4904a0(c: Cast) -> None:
    c.note("m4904a0: aura 5; enemies inside take -5 to skill checks")


@power(
    "m4904a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m4904a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4904a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.AREA],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4904a2(c: Cast) -> None:
    """"Cannot shift or stand up" is two cards: `ROOTED` bars the shift and
    `PINNED` bars getting up. Both on one effect, so the victim gets one
    saving throw and not two."""
    if c.strike():
        c.hit()
        c.condition(Condition.ROOTED, Condition.PINNED, until=When.SAVE_ENDS)
    else:
        c.condition(Condition.ROOTED, Condition.PINNED, until=When.EOTNT)


@power(
    "m4904a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=8),
)
def m4904a3(c: Cast) -> None:
    if c.strike():
        c.prone()


_M4904_MISSED = "an enemy adjacent to the m4904 misses it with a melee attack"


@power(
    "m4904a4",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4904_MISSED,
    on=Trigger(
        Miss,
        when=both(targets_me, by_melee, enemy_within(1)),
        text=_M4904_MISSED,
    ),
)
def m4904a4(c: Cast) -> None:
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None:
        c.swap(attacker)


# --------------------------------------------------------------------------
# m4962
# --------------------------------------------------------------------------


def _nobody_dominated(world: World, eid: int) -> bool:
    return not any(_dominated_by(world, eid, foe) for foe in enemies(world, eid))


@power(
    "m4962a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4962a0(c: Cast) -> None:
    """"A creature dominated by it" is the relation, not the condition: who
    is holding the strings is on the effect that applied the domination."""
    me = c.me

    def puppet_beside_it(_ctx: dict[str, Any]) -> bool:
        return any(
            _dominated_by(c.world, me, who)
            for who in c.within(1, of=me)
            if who != me
        )

    for defence in DEFENCES:
        c.bonus(defence, 3, on=me, until=When.ENCOUNTER, when=puppet_beside_it)


@power(
    "m4962a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m4962a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m4962a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
)
def m4962a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4962a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=Target("enemy", 1, label="One slowed or dazed creature"),
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=8),
    requires=_nobody_dominated,
    requires_text="no enemy may already be dominated by this power",
)
def m4962a3(c: Cast) -> None:
    """"Recharge when no enemy is dominated by this power" is not a recharge:
    nothing rolls for it and there is no turn on which it comes back. It is
    an at-will with an entry condition, and `requires` is what that is.

    The printed target restriction is enforced here rather than declared,
    because `Target` carries a side and a count and no condition; a row aimed
    at a creature that is neither slowed nor dazed simply does not go off.
    """
    if not (c.is_(Condition.SLOWED) or c.is_(Condition.DAZED)):
        return
    if c.strike():
        c.pull(3)
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m4962a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.SLEEP, Keyword.AREA],
    attack=Attack(vs=WILL, printed=10),
)
def m4962a4(c: Cast) -> None:
    """"Nondominated enemies" is asked before the roll -- a creature already
    under its thumb is not attacked at all. No damage: the whole of the hit
    is the sleep, and the escalation replaces the hold it grew out of, so
    ending that is also what clears the callback.
    """
    if _dominated_by(c.world, c.me, c.target):
        return
    if not c.strike():
        return

    def slump(eff: Any) -> None:
        c.world.effects.end(eff, "it sank further")
        c.unconscious(on=eff.owner, until=When.SAVE_ENDS)

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=slump)


# --------------------------------------------------------------------------
# m650
# --------------------------------------------------------------------------


@power(
    "m650a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m650a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m650a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=REF, printed=8),
)
def m650a1(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the hold."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m724
# --------------------------------------------------------------------------


@power(
    "m724a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 4),
)
def m724a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m724a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CLOSE],
    attack=Attack(vs=REF, printed=10),
)
def m724a1(c: Cast) -> None:
    """"Save ends both" wants the hold and the damage on one effect, which is
    what `ongoing=` on `c.condition` is for: applied separately the victim
    gets two saving throws and may shake off half of a thing the page says is
    one."""
    if c.strike():
        c.condition(
            Condition.RESTRAINED,
            until=When.SAVE_ENDS,
            ongoing=(10, DamageType.UNTYPED),
        )


@power(
    "m724a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m724a2(c: Cast) -> None:
    c.note("m724a2: squeezes through any crack an inch wide, unslowed")


# --------------------------------------------------------------------------
# m882
# --------------------------------------------------------------------------


@power(
    "m882a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 1),
)
def m882a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m882a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 4, dtype=DamageType.FIRE),
)
def m882a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m882a2",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m882a2(c: Cast) -> None:
    """"Save ends both" wants the penalty and the poison on one effect, and
    `c.condition` carries conditions and ongoing damage but no modifier -- so
    this one is applied directly, which is the only way the victim gets one
    saving throw rather than two."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
        ongoing=(2, DamageType.POISON),
    )


@power(
    "m882a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m882a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, Condition.DAZED, until=When.SAVE_ENDS)


@power(
    "m882a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.AREA],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("3d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m882a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M882_BLOODIED = "the m882 is first bloodied"


@power(
    "m882a5",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.AREA],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("3d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m882a5(c: Cast) -> None:
    """"Recharges when first bloodied" is an encounter power that gets its
    use handed back. `Powers.restore` is the only thing that gives a spent
    row back, and the watch that calls it is armed by the row itself -- so a
    creature bloodied before this ever fired gets nothing, which is what
    "first" means."""
    if c.first:
        known = c.world.get(c.me, Powers)
        ref, me = c.ref, c.me

        def again(ev: Bloodied) -> None:
            if ev.actor == me and known is not None:
                known.restore(ref)

        c.watch(Bloodied, again, until=When.ENCOUNTER, on=me, once=True, label=c.ref)
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)
