"""Monster abilities, level 10: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=WILL,
printed=15)` and `Damage("2d6", 3)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

The conventions of the nine levels below are kept: a **trait** is a row that
costs no action, has no target, and arms the watches that hold it for the
rest of the fight; a stat block printing no range at all means melee 1; and
a printed "minor 1/round" is `action=MINOR` plus `once_per_round`, which is
the field that remembers the round without spending a use.

Three things this file had to settle.

**A creature that comes back up.** The m417 has three skulls and loses one
each time it is felled; the first two drops heal it to full instead of
killing it. That is `usage=ENCOUNTER` with `uses=2` -- two uses of a
triggered free action -- and the healing happens inside the `Dropped`
window, which `resolve._check_down` re-reads hit points after, so the fall
is undone before the dropped conditions are ever applied.

**Putting a destroyed minion back on its feet** is a heal plus a square.
`resolve._die` lifts the body out of the occupancy index and leaves
`Position` naming the square it fell in, so healing alone gives back a
creature that nothing can walk into and nothing blocks. The square is
reclaimed with a teleport of no distance, which is the one call that goes
through `movement.step` and re-indexes it.

**A burn that spreads.** "While the target is taking ongoing poison damage
from this attack, it deals 2 poison to each creature adjacent to it at the
start of its turn" hangs on the burn's own subscriptions, so it stops when
the burn stops rather than needing a clock of its own -- and the two poison
damage comes from the **victim**, which is who the printed line names as
dealing it.

Artillery first, then the minions, each group in ref order.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_03.controllers import _nonminion
from combat_engine.content.monsters.level_04.controllers import _level_of
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Budget,
    Cast,
    Damage,
    DamageType,
    Dropped,
    Health,
    Keyword,
    Melee,
    Position,
    Ranged,
    TurnEnd,
    TurnStart,
    When,
    power,
)
from combat_engine.engine.monster_math import MINION
from combat_engine.engine.query import adjacent, alive, allies
from combat_engine.engine.triggers import Trigger, about_me

# ==========================================================================
# m417
# ==========================================================================


@power(
    "m417a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 2),
)
def m417a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. Two expressions on one line and the header holds one, so the
    untyped half stays in the header and the necrotic is rolled here."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.NECROTIC)


@power(
    "m417a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("1d6", 3, dtype=DamageType.COLD),
)
def m417a1(c: Cast) -> None:
    """"Minor 1/round" is the action plus `once_per_round`, which remembers
    the round without spending a use an at-will does not have."""
    if c.strike():
        c.hit()
        c.push(5)


@power(
    "m417a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m417a2(c: Cast) -> None:
    """A destroyed minion put back on its feet.

    Declared with no target, because the dispatcher only offers live
    creatures and every one of this row's is dead -- the same arrangement
    m135a3 settled on six levels down. Minion-ness and level are read off the
    stat block, which is the only place either is recorded.

    "Full normal hit points" is a minion's one. The square is reclaimed as
    well: `resolve._die` lifts the body out of the occupancy index and leaves
    `Position` naming where it fell, so a heal on its own gives back a
    creature nothing can walk into. A teleport of no distance is the one call
    that goes back through `movement.step` and re-indexes it, and it falls
    back to a square beside its own when something has moved into it.
    """
    me = c.me
    fallen = sorted(
        who
        for who in allies(c.world, me)
        if not alive(c.world, who)
        and not _nonminion(c.world, who)
        and c.is_kind("undead", on=who)
        and _level_of(c.world, who) <= c.level + 2
        and c.distance(who) <= 10
    )
    who = c.choose(fallen, "m417a2: which of the fallen rises") if fallen else None
    if who is None:
        return
    health = c.world.get(who, Health)
    where = c.world.get(who, Position)
    if health is None:
        return
    c.heal(health.max_hp, on=who)
    if where is not None:
        c.teleport(0, who=who, to=where.square, share=True)


@power(
    "m417a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 3, dtype=DamageType.FIRE),
)
def m417a3(c: Cast) -> None:
    """"Fire and necrotic damage" is one roll of two types and a header holds
    one, so the first printed type is kept and a creature resistant only to
    the other takes this in full -- the approximation the levels below
    settled on for the same shape."""
    if c.strike():
        c.hit()


_M417_FELL = "the m417 drops to 0 hit points"


@power(
    "m417a4",
    level=10,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M417_FELL,
    on=Trigger(Dropped, when=about_me, text=_M417_FELL),
)
def m417a4(c: Cast) -> None:
    """Three skulls, and the first two falls are not the end of it.

    `uses=2` is the two skulls that can be spent: the third fall finds the
    row used up and the creature stays down, which is the printed "when all
    three are destroyed". A count kept on the stat block rather than in a
    closure, so it survives the row being offered from anywhere.

    The heal lands inside the `Dropped` window. `resolve._check_down` reads
    hit points **again** after that window closes and returns when they are
    positive, so the fall is undone before unconscious, prone and dying are
    ever applied -- which is what "instantly heals to full" means.
    """
    health = c.world.get(c.me, Health)
    if health is None:
        return
    c.heal(health.max_hp, on=c.me)
    c.note("m417a4: one of its skulls is destroyed")


# ==========================================================================
# m466
# ==========================================================================


@power(
    "m466a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 8),
)
def m466a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m466a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.POISON),
)
def m466a1(c: Cast) -> None:
    """The burn spreads to whoever is standing next to whoever is burning.

    The splash hangs on the burn's own subscriptions rather than on a clock,
    so it lasts exactly as long as the ongoing damage does -- which is what
    "while the target is taking ongoing poison damage from this attack"
    says. The two damage comes from the **victim**: the printed line names it
    as dealing it, and hanging it on the m466 would credit the wrong
    creature and pay the wrong riders.

    The penalty is an Effect line, so it lands whether or not the blow did.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        burn = c.ongoing(5, DamageType.POISON, on=victim)
        if burn is not None:

            def seeps(ev: TurnStart) -> None:
                if ev.ghost or ev.actor != victim or burn.ended:
                    return
                for other in sorted(c.world.entities):
                    if other != victim and adjacent(c.world, victim, other):
                        c.world.damage(
                            victim, other, 2, DamageType.POISON, detail=c.ref
                        )

            burn.subs.append(c.world.bus.on(TurnStart, seeps, owner=c.me))
    c.penalty("attack", 2, until=When.EONT, on=victim)


# ==========================================================================
# The minions. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# ==========================================================================


# --------------------------------------------------------------------------
# m812
# --------------------------------------------------------------------------


@power(
    "m812a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage(bonus=6, dtype=DamageType.NECROTIC, kind=MINION),
)
def m812a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. Two numbers on one line and the header holds one, so the printed
    six stays there -- which is what rescales -- and the heavier number
    against a bloodied target is dealt flat in its place."""
    if not c.strike():
        return
    if c.bloodied():
        c.flat(8, dtype=DamageType.NECROTIC)
    else:
        c.hit()


@power(
    "m812a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m812a1(c: Cast) -> None:
    """Filed as a standard action and plainly a trait.

    Sunlight is a property of the fight rather than of anybody in it, which
    is what `c.terrain` asks, and it is asked at each end of the turn rather
    than now, because a fight can move into the open. The same arrangement
    m811a1 settled on five levels down.

    "Only a single move action" is the budget itself: there is no condition
    that takes the standard and the minor and leaves the move.
    """
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.standard = 0
            budget.minor = 0
        c.note("m812a1: sunlight leaves it a single move action")

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me or not c.terrain("sunlight"):
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label="m812a1 dawn")
    c.watch(TurnEnd, dusk, until=When.ENCOUNTER, on=me, label="m812a1 dusk")
