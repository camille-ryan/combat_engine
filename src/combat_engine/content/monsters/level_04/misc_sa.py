"""Monster abilities, level 4: the blocks that print no role.

A role-less stat block is usually not an encounter monster. Two of the ten here
have a handful of hit points and one attack apiece -- a thing something else
puts on the board -- and the rest are the blocks a named figure fights
*alongside*: full defences, a basic attack and one trick. They are written like
any other monster, because that is what the engine makes of them: numbers load
from `game.db`, the attack line is written exactly as printed, and the damage
line goes in the header as data.

Conventions inherited from the role sweeps at this level and below:

* a **trait** costs no action, has no target, and arms what holds it;
* `Attack(vs=AC, printed=11)` is the finished total and the engine takes the
  level back out -- these blocks print attack bonuses well above their level,
  which is what a companion's card does and not an error to correct;
* a printed range of "15/30" takes the short number;
* an aura that modifies whoever stands in it lays its modifier on the
  creatures and gates on the distance, rather than storing a membership list
  that is stale the moment either of them moves.

Eight helpers are imported rather than copied.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _uncovered
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _triggering_enemy,
    _twice,
)
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _marked_foe_looks_away,
)
from combat_engine.content.monsters.level_03.brutes_sa import (
    _press,
    _while_bloodied,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Stats,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AdjacencyLost,
    AttackDeclared,
    Hit,
    Miss,
    TurnEnd,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between
from combat_engine.engine.triggers import Trigger, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _any_turn_ends_in(c: Cast, area: Any, amount: int, dtype: DamageType) -> None:
    """The toll a zone takes as a turn closes, for **any** creature in it.

    `controllers_sa._ends_turn_in_zone` is the same sentence narrowed to
    enemies, which is what most cards print; this one says "any creature" and
    its own side is standing in the fire too, so the narrower helper would be a
    row weaker than its card.
    """
    me = c.me
    squares_ = frozenset(area)

    def toll(ev: TurnEnd) -> None:
        if ev.ghost:
            return
        if ev.actor in c.in_squares(squares_, side="any"):
            c.flat(amount, dtype=dtype, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


def _ridden_by_fifth_level(world: World, eid: int) -> bool:
    """"While mounted by a friendly rider of 5th level or higher".

    The level is read off `Stats`, which is where a creature's level lives --
    `Ident` carries the ref and the role and no number. Asked as a `requires=`
    as well as in the body: a trait armed with nobody up lays nothing, and a
    row that lays nothing is indistinguishable from one written wrong.

    **`targets`, not `sources`.** `Relations.set(RIDDEN_BY, mount, rider)` is the
    direction the engine stores, so `targets` of a mount is its rider and
    `sources` of it is whatever *it* is riding -- which for a mount's own trait
    is empty every time and silently false.
    """
    for rider in world.relations.targets(Relation.RIDDEN_BY, eid):
        stats = world.get(rider, Stats)
        if stats is not None and stats.level >= 5:
            return True
    return False


def _bigger_against_an_opening(c: Cast, dice: str, better: str, bonus: int) -> None:
    """"1d6+4, or 2d6+4 if the target is granting combat advantage."

    Read off the result of the swing that has just been rolled. Asking the board
    again is too late: a one-shot grant has already been spent by then, and the
    bigger die would be paid on half the attacks that earned it.
    """
    if c.result is not None and c.result.advantage:
        c.damage(better, bonus)
    else:
        c.damage(dice, bonus)


# --------------------------------------------------------------------------
# m1461
# --------------------------------------------------------------------------


@power(
    "m1461a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m1461a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1461a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by_fifth_level,
    requires_text="it must be carrying a rider of 5th level or higher",
)
def m1461a1(c: Cast) -> None:
    """The bonus sits on the rider, not on this creature, and is gated on
    `charge` -- which is in both modifier contexts, so it is read where every
    other charge rider is read. Untyped: the card prints a bare "+5 bonus"."""
    rider = c.rider()
    stats = c.world.get(rider, Stats) if rider is not None else None
    if rider is None or stats is None or stats.level < 5:
        return
    c.bonus(
        "damage", 5, on=rider, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")),
    )


# --------------------------------------------------------------------------
# m1462
# --------------------------------------------------------------------------


@power(
    "m1462a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m1462a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5442
# --------------------------------------------------------------------------


@power(
    "m5442a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 6),
)
def m5442a0(c: Cast) -> None:
    """"Plus 1d6 thunder damage" is a second, typed blow rather than part of the
    header's expression: thunder resistance reads one of them and not the
    other."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.THUNDER)
        c.mark()


@power(
    "m5442a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 6),
)
def m5442a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5442a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5442a2(c: Cast) -> None:
    _twice(c, "m5442a1")


@power(
    "m5442a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("3d6", 6, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5442a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m6403
# --------------------------------------------------------------------------

#: The row the two stances modify. A monster's basic attack is one of its own
#: rows, so "a basic attack using a weapon" is asked by ref.
_M6403_BASIC = "m6403a2"


@power(
    "m6403a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.cover_from()",),
)
def m6403a0(c: Cast) -> None:
    """Cover held on the geometry, which is what `c.cover_in` is: taken on
    entering and given back on leaving, following the aura as it moves. The
    "against ranged attacks" narrowing has nowhere to go -- carried cover is
    read with an empty context, so a gate on `ranged` there is false forever."""
    c.cover_in(c.aura(1, until=When.ENCOUNTER), side="ally")


@power(
    "m6403a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.move_through()",),
)
def m6403a1(c: Cast) -> None:
    """An ordinary creature cannot stand in another's square anyway, so the only
    thing this clause rules out is the exceptions -- a teleport, a phasing
    creature, a shared space. Those all route through the same question about
    who may occupy whose square, and nothing can answer it from this side."""


@power(
    "m6403a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m6403a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6403a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m6403a3(c: Cast) -> None:
    """Power, because that is the word the card prints in front of "bonus"."""
    me = c.me
    c.immobilized(until=When.SONT, on=me)
    for where in (AC, FORT, REF, WILL):
        c.bonus(where, 5, on=me, until=When.SONT, kind="power")


@power(
    "m6403a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def m6403a4(c: Cast) -> None:
    """`When.STANCE` rather than a duration: the bonus lasts exactly as long as
    the stance it is printed under, and the other stance on this block ends it
    by replacing it."""
    c.stance(on=c.me, label=c.ref)
    c.bonus(
        "damage", 2, on=c.me, until=When.STANCE, kind="power",
        when=lambda ctx: ctx.get("power") == _M6403_BASIC,
    )


@power(
    "m6403a5",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
)
def m6403a5(c: Cast) -> None:
    me = c.me
    c.stance(on=me, label=c.ref)

    def hobble(ev: Hit) -> None:
        if ev.attacker == me and ev.power == _M6403_BASIC:
            c.slowed(on=ev.target, until=When.EONT)

    c.watch(Hit, hobble, until=When.STANCE, on=me, label=f"{c.ref} drag")


# --------------------------------------------------------------------------
# m6474
# --------------------------------------------------------------------------


@power(
    "m6474a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6474a0(c: Cast) -> None:
    """The aura is drawn for the board and the penalty is laid on the enemies,
    gated on standing inside it: a membership list would be stale the moment
    either of them moved. "An ally who has a similar aura active" is asked by
    the marker this row lays on itself, so two of these blocks shelter each
    other without either knowing the other's name."""
    me = c.me
    label = f"{c.ref} watch"
    c.aura(1, until=When.ENCOUNTER)
    c.effect(label, until=When.ENCOUNTER, on=me)

    def looking_elsewhere(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("attacker")
        victim = ctx.get("target")
        if foe is None or victim is None:
            return False
        if distance_between(c.world, me, foe) > 1:
            return False
        if c.marked(on=foe):
            return False
        return not any(e.label == label for e in c.world.effects.of(victim))

    for foe in c.enemies():
        c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=looking_elsewhere)


@power(
    "m6474a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:bluff",),
)
def m6474a1(c: Cast) -> None:
    """Mimicking a voice is an opposed Bluff against a listener's Insight, and
    the only consequence the card gives it is whether somebody believes what
    they heard. Nothing on a board is listening and no Insight check is rolled
    in a fight, so there is no gap here to fill -- a verb to hold the trick
    would be a mechanism nobody would ever pass a purpose to."""


@power(
    "m6474a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m6474a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6474a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 3),
)
def m6474a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6474a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m6474a4(c: Cast) -> None:
    """"Recharge if the attack misses" cannot be a watch on this row's own
    `Miss` -- the miss belongs to the row it reaches for -- so the use is handed
    back here, which is the same sentence read from the other end."""
    foe = c.target
    if foe is None:
        return
    c.use_power("m6474a2", on=foe)
    if c.landed:
        c.dazed(on=foe, until=When.EONT)
    else:
        c.restore_use(c.ref, on=c.me)


# --------------------------------------------------------------------------
# m6480
# --------------------------------------------------------------------------


@power(
    "m6480a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 5),
)
def m6480a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m6480a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m6480a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6480a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m6480a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6480a3",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy marked by it attacks somebody else",
    on=Trigger(
        AttackDeclared, _marked_foe_looks_away,
        "an enemy it marked attacks without including it",
    ),
)
def m6480a3(c: Cast) -> None:
    """Aimed off the triggering event rather than off a target line: an
    interrupt declares no target, and `PowerUsed.targets` would name whoever
    the enemy was swinging at."""
    who = _triggering_enemy(c)
    if who is not None:
        c.use_power("m6480a0", on=who)


# --------------------------------------------------------------------------
# m6490
# --------------------------------------------------------------------------


@power(
    "m6490a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m6490a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6490a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 2),
)
def m6490a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6490a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6490a2(c: Cast) -> None:
    """"Charge **or** make a basic attack" is the ally's choice and is decided by
    where it is standing: the swing when something is already in reach, the run
    when nothing is. `c.charge_at(who=)` hands over the move and the flag, which
    `c.grant_attack` does not."""
    c.move(c.speed_of())
    near = _press(c)
    if near:
        c.basic(on=near[0])
    mate = next((a for a in c.within(5, side="ally") if a != c.me), None)
    if mate is None:
        return
    reachable = [foe for foe in c.enemies() if c.adjacent_to(foe, mate)]
    if reachable:
        c.basic(who=mate, on=reachable[0])
    else:
        far = c.enemies()
        if far:
            c.charge_at(far[0], who=mate)


@power(
    "m6490a3",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
)
def m6490a3(c: Cast) -> None:
    c.temp_hp(15)


# --------------------------------------------------------------------------
# m6491
# --------------------------------------------------------------------------


@power(
    "m6491a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m6491a0(c: Cast) -> None:
    if c.strike():
        _bigger_against_an_opening(c, "1d6", "2d6", 4)


@power(
    "m6491a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m6491a1(c: Cast) -> None:
    """Cover is a fact about two positions, so it is measured at the swing
    rather than asked of a modifier; "no other creature adjacent" is the second
    half and leaves the target itself out of the count."""
    foe = c.target
    alone = foe is not None and not [
        other for other in c.within(1, of=foe) if other != foe
    ]
    if c.strike():
        if alone and _uncovered(c, foe):
            c.damage("2d8", 5)
        else:
            c.hit()


# --------------------------------------------------------------------------
# m6493
# --------------------------------------------------------------------------


@power(
    "m6493a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6493a0(c: Cast) -> None:
    """Gated at the lookup rather than armed on `Bloodied`: the creature can be
    healed back over the line and a bonus laid once would never come off."""
    hurt = _while_bloodied(c)
    for where in (AC, FORT, REF, WILL):
        c.bonus(where, 2, on=c.me, until=When.ENCOUNTER, kind="power", when=hurt)


@power(
    "m6493a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m6493a1(c: Cast) -> None:
    if c.strike():
        _bigger_against_an_opening(c, "1d6", "2d6", 5)


@power(
    "m6493a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.ZONE],
    attack=Attack(vs=REF, printed=10),
)
def m6493a2(c: Cast) -> None:
    """No damage line at all: the whole of the hit is the burn, so there is
    nothing for the header to carry and `c.hit()` would have nothing to pay.
    The zone is laid once for the use, on the squares the burst has drawn."""
    if c.strike():
        c.ongoing(5, DamageType.FIRE)
    if c.first:
        area = c.area()
        c.zone(area, label=c.ref, until=When.ENCOUNTER)
        _any_turn_ends_in(c, area, 3, DamageType.FIRE)


@power(
    "m6493a3",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy misses it with an attack",
    on=Trigger(Miss, targets_me, "an enemy misses it"),
)
def m6493a3(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m6595
# --------------------------------------------------------------------------


@power(
    "m6595a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
)
def m6595a0(c: Cast) -> None:
    """The mark is printed as an Effect and not under the Hit, so it is laid
    whether the swing landed or not."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m6595a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m6595a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.temp_hp(5, on=c.me)
        c.dazed(until=When.EONT)


@power(
    "m6595a2",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=ONE_ALLY,
)
def m6595a2(c: Cast) -> None:
    """Two endings, and only one of them is a duration: the bonus runs to the
    end of its own next turn on the clock, and `AdjacencyLost` is the only
    announcement of the other -- the two of them being parted."""
    mate = c.target
    if mate is None:
        return
    held = c.bonus(AC, 5, on=mate, until=When.EONT)
    if held is None:
        return
    me = c.me

    def parted(ev: AdjacencyLost) -> None:
        if {ev.actor, ev.other} == {me, mate}:
            c.world.effects.end(held, "no longer adjacent")

    c.watch(
        AdjacencyLost, parted, until=When.EONT, on=me, once=True,
        label=f"{c.ref} guard",
    )
