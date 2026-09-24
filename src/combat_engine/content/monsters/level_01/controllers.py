"""Monster abilities, level 1: the controllers and the minions beside them.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=6)` and `Damage("1d10", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. A minion's flat damage says so with `kind=MINION`
and rescales with everything else. See `engine/scaling.py` and
`engine/monster_math.py`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    UpTo,
    Usage,
    When,
    power,
)
from combat_engine.engine.monster_math import LIMITED, MINION

from . import aquatic_edge

#: The four conditions m5030a0 pays a damage bonus against.
HAMPERED = (Condition.PRONE, Condition.IMMOBILIZED, Condition.SLOWED, Condition.RESTRAINED)


@power(
    "m239a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage(bonus=4, kind=MINION),
)
def m239a0(c: Cast) -> None:
    """"4, or 5 with combat advantage": the extra point rides on top of the
    declared damage rather than replacing it, so the row still rescales."""
    swing = c.strike()
    if swing:
        c.hit()
        if swing.advantage:
            c.flat(1)


@power(
    "m239a1",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="the m239 is missed by an attack",
)
def m239a1(c: Cast) -> None:
    c.shift(1)


@power(
    "m2796a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=5),
    damage=Damage(bonus=4, kind=MINION),
)
def m2796a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2796a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=4),
    damage=Damage(bonus=6, dtype=DamageType.ACID, kind=MINION),
)
def m2796a1(c: Cast) -> None:
    """The splash is a fixed 3 on a critical hit only, so it stays in the body
    and does not rescale. It spares the attacker, which is adjacent to its own
    target and which the printed line neither includes nor excludes."""
    if c.strike():
        c.hit()
        if c.crit:
            for who in c.within(1, of=c.target):
                if who not in (c.target, c.me):
                    c.flat(3, dtype=DamageType.ACID, on=who)


@power(
    "m2796a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def m2796a2(c: Cast) -> None:
    """A standing bonus rather than an action, whatever the section line says.
    "Grabbed by any m2796" is read as grabbed at all: a body can ask whether a
    creature is held, not what kind of thing is holding it."""
    c.bonus(
        "attack",
        4,
        until=When.ENCOUNTER,
        when=lambda ctx: c.is_(Condition.GRABBED, on=ctx["target"]),
    )


@power(
    "m2797a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
)
def m2797a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2797a1",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="an ally within 10 squares drops to 0 hit points",
)
def m2797a1(c: Cast) -> None:
    c.shift(2)


@power(
    "m2978a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 3),
)
def m2978a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.invisible(to=c.target, until=When.EONT)


@power(
    "m2978a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d6", 5, dtype=DamageType.FORCE),
)
def m2978a1(c: Cast) -> None:
    """The choice is the m2978's, so it goes through `c.choose` rather than
    being decided here."""
    if c.strike():
        c.hit()
        if c.choose(["slide", "immobilize"]) == "slide":
            c.slide(3)
        else:
            c.immobilized()


@power(
    "m2978a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d6", 5, dtype=DamageType.FORCE, kind=LIMITED),
)
def m2978a2(c: Cast) -> None:
    """Two of m2978a1, and `UpTo(2)` is what makes them different targets. The
    attack is repeated here rather than fired through that row so the damage
    is declared as a recharge power's and rescales as one."""
    if c.strike():
        c.hit()
        if c.choose(["slide", "immobilize"]) == "slide":
            c.slide(3)
        else:
            c.immobilized()


@power(
    "m2978a3",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="the m2978 is missed by a melee attack",
)
def m2978a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m414a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
)
def m414a0(c: Cast) -> None:
    """The printed Effect line moves it before the attack, not after."""
    if c.first:
        c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m414a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=3, kind=MINION),
)
def m414a1(c: Cast) -> None:
    if c.first:
        c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m4868a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def m4868a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m4868a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d6"),
)
def m4868a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m4868a3",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=4),
    damage=Damage("2d6", 2, kind=LIMITED),
)
def m4868a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()


@power(
    "m4868a4",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
)
def m4868a4(c: Cast) -> None:
    """Everyone the elemental has left bleeding, dragged a square.

    `c.suffering` asks for effects this creature is the source of, and the
    only ongoing damage it can be the source of is m4868a2's, so the label
    picks them out without anything having to keep a list.
    """
    for who in c.suffering("ongoing"):
        c.slide(1, on=who)


@power(
    "m5030a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def m5030a0(c: Cast) -> None:
    """A standing bonus, gated on the victim rather than on the m5030, so it
    is one modifier with a `when` instead of four."""
    c.bonus(
        "damage",
        2,
        until=When.ENCOUNTER,
        when=lambda ctx: any(c.is_(x, on=ctx["target"]) for x in HAMPERED),
    )


@power(
    "m5030a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m5030a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5030a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=5),
)
def m5030a2(c: Cast) -> None:
    """No damage line at all: the burst only holds people."""
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m5030a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=5),
)
def m5030a3(c: Cast) -> None:
    """No damage line at all: the whole of the hit is the fall and being kept
    down. `held` is the second, shorter clock on top of prone's own -- prone
    lasts until the creature stands, and until then it may not."""
    if c.strike():
        c.prone(held=When.EONT)


@power(
    "m5030a4",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy adjacent to the m5030 hits it",
)
def m5030a4(c: Cast) -> None:
    """Printed as a teleport to another square adjacent to whoever hit it. The
    engine's teleport picks its own destination and cannot be pointed at a
    creature, so this is a teleport 2 -- every square the printed line allows
    is inside it, and some that are not."""
    c.teleport(2)


@power(
    "m675a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage(bonus=4, kind=MINION),
)
def m675a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m675a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage(bonus=4, kind=MINION),
)
def m675a1(c: Cast) -> None:
    """10/20 is a thrown weapon's short and long range; the engine has one
    range band and the long one costs a penalty it does not model, so the row
    reaches 10."""
    if c.strike():
        c.hit()


@power(
    "m675a2",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m675a2(c: Cast) -> None:
    c.shift(1)


@power(
    "m698a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=3, kind=MINION),
)
def m698a0(c: Cast) -> None:
    if c.strike():
        c.hit()
