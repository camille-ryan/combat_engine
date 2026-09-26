"""Swordmage, level 3: the encounter attacks.

`p5742` is the one to read: the printed line takes an enemy's melee attack
away from the ally it was aimed at and spends it on somebody else. That is
an interrupt cancelling the blow and then handing the same swing back out
with `c.grant_attack`, which is the only way a body can make a creature
other than the caster swing.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
    INTERRUPT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    Trigger,
    When,
    both,
    by_melee,
    leaves_me_out,
    power,
)
from combat_engine.engine.events import ActionSpent
from combat_engine.engine.types import ActionType

from . import ally_target_within, beside, my_at_will_missed

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p10429",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
    trigger="you used a swordmage at-will attack power this turn and hit nothing",
    on=Trigger(
        Miss,
        my_at_will_missed,
        "you used a swordmage at-will attack power this turn and hit nothing",
    ),
)
def p10429(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p1729",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.THUNDER],
    attack=Attack(INT, vs=FORT),
)
def p1729(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.int_mod, dtype=DamageType.THUNDER)
        c.push(2)


@power(
    "p1737",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=AC),
)
def p1737(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.COLD)
        c.slowed()


@power(
    "p1779",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=AC),
)
def p1779(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod)
        spot = beside(c)
        if spot is not None:
            c.teleport(c.distance() + 1, who=c.target, to=spot)


@power(
    "p3336",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(INT, vs=FORT),
)
def p3336(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.ACID)


@power(
    "p3910",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p3910(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.FIRE)


@power(
    "p3915",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.POISON],
    attack=Attack(INT, vs=AC),
)
def p3915(c: Cast) -> None:
    """"When the target uses a move action" is `ActionSpent`, not a movement
    event: a shift is a move action and a push is not."""
    if not c.strike():
        return
    c.damage(c.w(2), c.int_mod)
    victim = c.target
    bite = c.con_mod

    def stir(ev: ActionSpent) -> None:
        if ev.actor == victim and ev.cost is ActionType.MOVE:
            c.flat(bite, dtype=DamageType.POISON, on=victim)

    c.watch(ActionSpent, stir, until=When.EONT, on=victim, label=c.ref)


@power(
    "p3921",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=FORT),
)
def p3921(c: Cast) -> None:
    if c.strike():
        extra = c.con_mod if c.build("ensnarement") else 0
        c.damage("1d10", c.int_mod + extra, dtype=DamageType.FORCE)
        c.immobilized()


@power(
    "p4798",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=WILL),
    thrown_by_hand=True,
    requires_text="you must throw your melee weapon at the origin square",
)
def p4798(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("2d6", c.int_mod, dtype=DamageType.FIRE)
    victim = c.target
    me = c.me

    def scorch(ev: AttackDeclared) -> None:
        if leaves_me_out(c.world, me, ev):
            c.flat(5, dtype=DamageType.FIRE, on=victim)

    c.on_attack(scorch, by=victim, until=When.EOTNT, label=c.ref)


@power(
    "p5742",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=WILL),
    trigger="an enemy hits an ally with a melee attack",
    on=Trigger(
        Hit,
        both(ally_target_within(10), by_melee),
        "an enemy hits an ally with a melee attack",
    ),
)
def p5742(c: Cast) -> None:
    """The blow is cancelled and spent again elsewhere. Only an interrupt
    can cancel, which is why the printed action type matters here."""
    if not c.strike():
        return
    foe = c.target
    c.teleport(5, who=foe)
    pool = [w for w in c.within(1, of=foe, side="any") if w != foe]
    victim = c.choose(sorted(pool), "the blow lands on") if pool else None
    c.cancel()
    if victim is not None:
        extra = c.con_mod if c.build("shielding") and c.marked(on=foe) else 0
        c.grant_attack(foe, on=victim, damage_bonus=extra)


@power(
    "p5743",
    level=3,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.LIGHTNING, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=AC),
)
def p5743(c: Cast) -> None:
    """The blink sits between the two swings, so the second is measured from
    wherever the first left me."""
    if c.strike():
        c.damage(c.w(), c.int_mod, dtype=DamageType.LIGHTNING)
        c.mark()
    first = c.target
    c.teleport(5)
    pool = [f for f in c.within(1, side="enemy") if f != first]
    second = c.choose(sorted(pool), "you come down on") if pool else None
    if second is not None and c.attack(c.int_, AC, on=second):
        c.damage(c.w(), c.int_mod, dtype=DamageType.LIGHTNING, on=second)
        c.mark(on=second)
