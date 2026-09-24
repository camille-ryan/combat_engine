"""Monster abilities, level 5: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=10)` and `Damage("1d10", 8)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

Four things this file had to settle.

**"Or N damage while bloodied"** is two printed expressions, not one, so the
bloodied branch is rolled in the body with `c.damage`. The header keeps the
ordinary line, which is what a policy forecasts from and what an edition
conversion rescales; the branch gives that up knowingly, which is the trade
the header/body split is there to make.

**A row that picks its defence at the moment of the roll** -- "+10 vs. AC or
Reflex, whichever is lower" -- cannot put its attack in the header and use
it, because `Attack` holds one defence. The printed bonus is trimmed by hand
the way `Attack.bonus_for` trims the header's, so the row still moves with
whatever scaling the fight is on, and the header carries the line anyway so
the card can print it.

**A list of rays chosen at use** is one row with `UpTo(2)` and a choice per
target. Each ray is a separate defence and a separate rider, so none of them
can live in the header; what the header does carry is the range and the fact
that the whole thing does not provoke.

**"+4 to AC against opportunity attacks provoked by this movement"** is a
gated modifier taken down by hand the moment the move ends. `opportunity` is
in the attack context, and the defence is read out of that same context, so
the gate is one lambda -- but the duration is "this movement", which no
`When` names.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_05.brutes import _is_climbing
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Bloodied,
    Budget,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Dropped,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    OpportunityWindow,
    Ranged,
    Stats,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    use,
)
from combat_engine.engine.events import AdjacencyGained, AttackDeclared
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    adjacent,
    alive,
    allies,
    defence,
    enemies,
    flanked_by,
    has_combat_advantage,
)
from combat_engine.engine.triggers import Trigger, about_me, enemy_within


def _reach_of(ref: str) -> str:
    p = get(ref)
    return p.reach.kind if p is not None else ""


def _level_of(world: World, eid: int) -> int:
    """A creature's level, for a printed "of level 10 or lower". Anything
    with no stat block behind it is out of reach of that sentence."""
    stats = world.get(eid, Stats)
    return 99 if stats is None else stats.level


def _mobbed(c: Cast, who: int, by: int, count: int = 2) -> bool:
    """Is `who` hemmed in by `count` or more of `by`'s allies?

    The printed line is "an enemy that has two or more of its allies adjacent
    to it", which two separate stat blocks here print word for word.
    """
    return (
        sum(1 for a in allies(c.world, by) if a != by and adjacent(c.world, a, who))
        >= count
    )


# --------------------------------------------------------------------------
# m232
# --------------------------------------------------------------------------


@power(
    "m232a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m232a0(c: Cast) -> None:
    """Hits harder into a crowd, and who is standing where cannot be settled
    now -- so it is a gated damage modifier, asked as each blow is totalled.
    The damage context carries `target`, which is the whole of the gate."""
    me = c.me

    def hemmed_in(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and foe in enemies(c.world, me) and _mobbed(c, foe, me)

    c.bonus("damage", 5, until=When.ENCOUNTER, on=me, when=hemmed_in)


@power(
    "m232a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3),
)
def m232a1(c: Cast) -> None:
    """The wounded line is a second printed expression, so it is rolled here
    rather than added on top: one roll, one application, one resistance
    check."""
    if c.strike():
        if c.bloodied(on=c.me):
            c.damage("2d6", 5)
        else:
            c.hit()


@power(
    "m232a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 8),
)
def m232a2(c: Cast) -> None:
    if c.strike():
        if c.bloodied(on=c.me):
            c.damage("1d10", 10)
        else:
            c.hit()


# --------------------------------------------------------------------------
# m2817
# --------------------------------------------------------------------------


@power(
    "m2817a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 5),
)
def m2817a1(c: Cast) -> None:
    if c.strike():
        c.hit()


#: The four rays, in the printed order. Chosen per target rather than per
#: use: the printed line says two rays, each at a different creature, and
#: says nothing about their being the same ray.
_M2817_RAYS = (1, 2, 3, 4)


@power(
    "m2817a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(8),
    target=UpTo(2),
    no_provoke=True,
)
def m2817a2(c: Cast) -> None:
    """Two rays at two creatures, chosen as they are fired.

    Nothing of this fits a header: each ray names its own defence and its own
    rider, and `Attack` holds one defence. The printed +10 is trimmed by hand
    the way `Attack.bonus_for` trims a header's, so the row still moves with
    whatever scaling the fight is being played on.

    "Each beam must target a different creature" is `UpTo(2)`, whose
    targets are distinct; the body is called once for each of them.
    """
    bonus = c.world.scaling.trim(10, c.level)
    ray = c.choose(list(_M2817_RAYS), "which beam") or _M2817_RAYS[0]

    if ray == 1:
        if c.attack(bonus, REF):
            c.damage("2d6", 6, dtype=DamageType.FIRE)
    elif ray == 2:
        if c.attack(bonus, FORT):
            c.damage("1d8", 4, dtype=DamageType.NECROTIC)
            c.weakened(until=When.SAVE_ENDS)
    elif ray == 3:
        if c.attack(bonus, FORT):

            def slump(eff: Effect) -> None:
                # The escalation replaces the hold it grew out of, so ending
                # that one is also what clears this callback.
                c.world.effects.end(eff, "it sank further")
                c.unconscious(on=eff.owner, until=When.SAVE_ENDS)

            c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=slump)
    elif ray == 4 and c.attack(bonus, FORT):
        c.slide(4)


@power(
    "m2817a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
)
def m2817a3(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the hold."""
    if c.strike():
        c.immobilized(until=When.EONT)


# --------------------------------------------------------------------------
# m2866
# --------------------------------------------------------------------------


@power(
    "m2866a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 4),
)
def m2866a0(c: Cast) -> None:
    """No range printed where the next rows print one, so this is the
    creature's melee attack."""
    if c.strike():
        c.hit()


_M2866_CROWDED = "an enemy moves adjacent to the m2866"


@power(
    "m2866a1",
    level=5,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING),
    trigger=_M2866_CROWDED,
    on=Trigger(AdjacencyGained, when=enemy_within(1), text=_M2866_CROWDED),
)
def m2866a1(c: Cast) -> None:
    """The printed line gives the counter no range, so the header carries
    none and the roll is aimed at whoever just arrived."""
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m2866a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING),
)
def m2866a2(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2866_BLOODIED = "the m2866 is first bloodied"


@power(
    "m2866a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
    trigger=_M2866_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M2866_BLOODIED),
)
def m2866a3(c: Cast) -> None:
    """"First bloodied" needs no latch of its own: `Bloodied` is announced
    once and the row is an encounter power."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2866a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.AREA],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING),
)
def m2866a4(c: Cast) -> None:
    """The extra is one point per creature standing in the burst, counted off
    the area rather than off the target list -- the printed line says "each
    creature in the burst" and an ally in it counts as readily as a foe."""
    if not c.strike():
        return
    c.hit()
    crowd = len(c.in_squares(c.area()))
    if crowd:
        c.flat(crowd, dtype=DamageType.LIGHTNING)


# --------------------------------------------------------------------------
# m2923
# --------------------------------------------------------------------------


@power(
    "m2923a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m2923a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2923a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10"),
)
def m2923a1(c: Cast) -> None:
    """Two shots, each against whichever of the two defences is lower.

    `Attack` holds one defence, so the choice cannot be made in the header
    and the roll is assembled here; the header keeps the line so the card can
    print it. The fire die is a second damage type on the same hit, which
    `Damage` cannot say either -- it holds one type -- so the weapon die is
    `c.hit()` and the fire is its own small roll.

    The printed range is 20/40; `Range` holds one number and the engine has
    no long-range penalty to apply, so the normal band is what is written.
    """
    bonus = c.world.scaling.trim(10, c.level)
    for _ in range(2):
        foe = c.target
        softer = AC if defence(c.world, foe, AC) <= defence(c.world, foe, REF) else REF
        if c.attack(bonus, softer):
            c.hit()
            c.damage("1d6", dtype=DamageType.FIRE)


@power(
    "m2923a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.FORCE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d10", 5, dtype=DamageType.FORCE, kind=LIMITED),
)
def m2923a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2923a3",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m2923a3(c: Cast) -> None:
    c.teleport(5)


# --------------------------------------------------------------------------
# m3023
# --------------------------------------------------------------------------


@power(
    "m3023a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 3),
)
def m3023a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3023a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.FORCE),
)
def m3023a1(c: Cast) -> None:
    """"Grants combat advantage to the m3023" names one beneficiary, which is
    what `to="me"` -- the default -- already is."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SAVE_ENDS)


@power(
    "m3023a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 6, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3023a2(c: Cast) -> None:
    """A blast with no printed target line is read as enemies, as the rest of
    the tree reads it."""
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m3023a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT, Keyword.AREA],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 6, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3023a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3023a4",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3023a4(c: Cast) -> None:
    """One point better than everybody else at flanking.

    Flanking is combat advantage and combat advantage is +2, so "a +3 bonus
    instead of +2" is one extra point gated on actually flanking -- asked as
    the roll is assembled, from the attack context's own `target`.

    The second printed clause, aiding another, is a skill-check rule and the
    engine has no aid-another to improve; it is left alone rather than
    approximated with a combat bonus the page does not grant.
    """
    me = c.me

    def outflanking(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and flanked_by(c.world, foe, me)

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=outflanking)


@power(
    "m3023a5",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    out_of_combat=True,
)
def m3023a5(c: Cast) -> None:
    c.note("m3023a5: mimics a sound or a voice; Insight opposed by its Bluff")


@power(
    "m3023a6",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FORCE],
)
def m3023a6(c: Cast) -> None:
    """Hover and the altitude limit are printed qualifiers on the mode;
    `c.mode` carries the mode and its speed and the engine tracks no
    altitude, so the flight is what is written."""
    c.mode("fly", 6, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m4793
# --------------------------------------------------------------------------


@power(
    "m4793a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 3),
)
def m4793a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4793a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m4793a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4793a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    no_provoke=True,
)
def m4793a2(c: Cast) -> None:
    """One weapon, twice -- not one of each, which is what the printed "or"
    rules out. The choice is made once, on the first target, and both swings
    are made there; the two rows that print the attacks are used rather than
    copied, so their damage lines stay in one place.

    The declared reach is the longer of the two, because the dispatcher aims
    the row before the weapon is chosen; the melee half then simply misses
    nothing it could not have reached anyway.
    """
    if not c.first:
        return
    ref = c.choose(["m4793a0", "m4793a1"], "the same weapon, twice")
    victims = [t for t in c.targets if t is not None]
    if ref is None or not victims:
        return
    shots = victims * 2 if len(victims) == 1 else victims[:2]
    for who in shots:
        use(c.world, c.me, ref, targets=[who], spend=False)


@power(
    "m4793a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m4793a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


@power(
    "m4793a4",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_climbing,
    requires_text="the m4793 must be climbing",
)
def m4793a4(c: Cast) -> None:
    """The flight lasts the move and no longer, which is why it is granted
    here and clocked to the end of the turn: `mode_of` prefers flight to a
    walk, and that is what makes `c.move` leave the wall."""
    c.mode("fly", 5, until=When.EOT)
    c.move(5)


# --------------------------------------------------------------------------
# m4803
# --------------------------------------------------------------------------


@power(
    "m4803a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m4803a0(c: Cast) -> None:
    """Extra on the blow and a splash on the victim's neighbours.

    Neither half can be a modifier: the splash is damage to somebody who is
    not the target at all, and `Mods` only ever adds to the number in front
    of it. `Hit` is announced before the damage is rolled, so answering it
    puts both alongside the blow rather than after it.

    Whether the creature was granting combat advantage is read off the
    attack's own result rather than asked again: combat advantage is decided
    as the roll is assembled, and something that granted it for one attack --
    m4803a1 below is exactly that -- may not still be granting it by the time
    the blow lands.
    """
    me = c.me

    def leech(ev: Hit) -> None:
        if ev.attacker != me:
            return
        rolled = getattr(ev, "result", None)
        had = (
            rolled.advantage
            if rolled is not None
            else has_combat_advantage(c.world, me, ev.target)
        )
        if not had:
            return
        c.flat(5, dtype=DamageType.NECROTIC, on=ev.target)
        for near in allies(c.world, ev.target):
            if near != ev.target and adjacent(c.world, near, ev.target):
                c.flat(5, dtype=DamageType.NECROTIC, on=near)

    c.watch(Hit, leech, until=When.ENCOUNTER, on=me, label="m4803a0")


@power(
    "m4803a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4803a1(c: Cast) -> None:
    """Shoots into a flank its friends made without standing in it.

    Combat advantage is not a modifier the roll adds up -- `resolve.attack`
    asks `has_combat_advantage` for itself -- so the only way to grant it is
    the relation, laid the instant the attack is declared and spent by that
    same roll. The watch sits in the `BEFORE` window because the roll happens
    inside `AttackDeclared`, and an `AFTER` listener would arrive too late.
    """
    me = c.me

    def line_up(ev: AttackDeclared) -> None:
        if ev.attacker != me or _reach_of(ev.power) != "ranged":
            return
        mates = [a for a in allies(c.world, me) if a != me]
        if any(flanked_by(c.world, ev.target, a) for a in mates):
            c.grants_advantage(on=ev.target, until=When.EONT, once=True)

    c.watch(
        AttackDeclared,
        line_up,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m4803a1",
    )


@power(
    "m4803a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 5),
)
def m4803a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4803a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 5),
)
def m4803a3(c: Cast) -> None:
    """"Each time it provokes an opportunity attack" is the window opening,
    not the attack landing: the toll is paid whether or not anybody takes the
    opening, which is what the printed line says."""
    if not c.strike():
        return
    c.hit()
    victim = c.target

    def toll(ev: OpportunityWindow) -> None:
        if ev.provoker == victim:
            c.flat(5, on=victim)

    c.watch(OpportunityWindow, toll, until=When.SAVE_ENDS, on=victim, label=c.ref)


@power(
    "m4803a4",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4803a4(c: Cast) -> None:
    """The shield is against openings *this* movement gives, so it is taken
    down by hand the moment the move is over -- no `When` names a duration
    that short. `opportunity` is in the attack context and a defence is read
    out of that same context, so the gate is one lambda."""
    guard = c.bonus(
        AC, 4, on=c.me, until=When.EONT, when=lambda ctx: bool(ctx.get("opportunity"))
    )
    c.move(4)
    if guard is not None:
        c.world.effects.end(guard, "the move is over")
    for foe in c.within(1, side="enemy"):
        c.grants_advantage(on=foe, until=When.EONT)


_M4803_DOWN = "the m4803 drops to 0 hit points"


@power(
    "m4803a5",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M4803_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M4803_DOWN),
)
def m4803a5(c: Cast) -> None:
    """No attack roll at all: the printed Effect blinds everybody adjacent,
    and the duration is each victim's own next turn."""
    c.blinded(until=When.EOTNT)


# --------------------------------------------------------------------------
# m706
# --------------------------------------------------------------------------


@power(
    "m706a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m706a0(c: Cast) -> None:
    """Ending a turn in it, not entering it or starting there, so this is a
    `TurnEnd` watch rather than `c.hazard`, whose teeth bite at the other two
    moments. The creature at the centre is what the aura comes off and is not
    standing in its own fire."""
    ring = c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def singe(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(5, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnEnd, singe, until=When.ENCOUNTER, on=me, label="m706a0")


@power(
    "m706a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 3),
)
def m706a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m706a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d4", 4),
)
def m706a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


# --------------------------------------------------------------------------
# The minions. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# m2868
# --------------------------------------------------------------------------


@power(
    "m2868a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage(bonus=5, kind=MINION),
)
def m2868a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2868a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m2868a1(c: Cast) -> None:
    """No attack line printed, so the hold simply lands; the price is the
    creature itself. Dropping it is damage dealt to it for what it has left,
    which is what announces `Dropped` -- and `Dropped` is what m2868a2 is
    waiting for."""
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    health = c.world.get(c.me, Health)
    if health is not None and health.hp > 0:
        c.flat(health.hp, on=c.me)


_M2868_DOWN = "the m2868 drops to 0 hit points"

#: Five stacks of +2 is the printed ceiling of +10.
_M2868_MAX_STACKS = 5


@power(
    "m2868a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M2868_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M2868_DOWN),
)
def m2868a2(c: Cast) -> None:
    """The one it latches on to is chosen in the body: the printed line wants
    a live demon of level 10 or lower within 5 squares, and `ONE_ALLY` would
    have let the dispatcher take whichever friend was nearest.

    The ceiling is counted off the stacks already standing, because the bonus
    is cumulative with itself and `c.bonus` has no cap of its own. A bonus to
    *melee* damage rolls is gated on the reach of whatever row is dealing it,
    which the damage context carries as `power`.
    """
    kin = sorted(
        a
        for a in c.within(5, side="ally")
        if a != c.me and alive(c.world, a) and c.is_kind("demon", on=a)
        and _level_of(c.world, a) <= 10
    )
    who = c.choose(kin, "which of its own the tentacles find") if kin else None
    if who is None:
        return
    c.heal(5, on=who)
    standing = sum(
        1 for eff in c.world.effects.of(who) if eff.label.startswith("m2868a2")
    )
    if standing >= _M2868_MAX_STACKS:
        return

    def by_hand(ctx: dict[str, Any]) -> bool:
        return _reach_of(ctx.get("power") or "") == "melee"

    c.bonus("damage", 2, on=who, until=When.ENCOUNTER, when=by_hand)


# --------------------------------------------------------------------------
# m811
# --------------------------------------------------------------------------


@power(
    "m811a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage(bonus=5, dtype=DamageType.NECROTIC, kind=MINION),
)
def m811a0(c: Cast) -> None:
    """Two printed numbers, so the wounded one is dealt here rather than
    added on top of the header's. Asked before the blow lands, or the hit
    that bloodies would pay the larger number for itself."""
    if c.strike():
        if c.bloodied():
            c.damage(bonus=7, dtype=DamageType.NECROTIC)
        else:
            c.hit()


@power(
    "m811a1",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m811a1(c: Cast) -> None:
    """Sunlight is a property of the fight rather than of anybody in it,
    which is what `c.terrain` asks -- and it is asked at the start and at the
    end of each turn rather than now, because a fight can move into the open.

    "Only a single move action" is the budget itself: `Condition.SHAPED`
    takes the standard away and leaves the minor, and the printed line leaves
    neither.
    """
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.standard = 0
            budget.minor = 0
        c.note("m811a1: sunlight leaves it a single move action")

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label="m811a1 dawn")
    c.watch(TurnEnd, dusk, until=When.ENCOUNTER, on=me, label="m811a1 dusk")
