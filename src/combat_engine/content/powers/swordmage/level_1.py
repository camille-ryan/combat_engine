"""Swordmage, level 1: the first ten attack rows.

The class's two habits start here. It teleports constantly, and "to a square
adjacent to you" is a named destination -- so those rows find the square
first and pass `to=`, rather than letting the decider pick anywhere in range.
And it punishes its own mark: `c.marked` asks whose mark it is, where
`c.is_(Condition.MARKED)` would happily pay off another defender's.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    INT,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    SavingThrow,
    Target,
    Trigger,
    TurnStart,
    When,
    both,
    by_melee,
    power,
)

from . import ally_target_within, beside, by_my_mark, teleported_beside_me

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p12217",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.LIGHTNING, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=AC),
    trigger="an ally within 5 squares of you is hit by an enemy you have marked",
    on=Trigger(
        Hit,
        both(ally_target_within(5), by_my_mark),
        "an ally within 5 squares of you is hit by an enemy you have marked",
    ),
)
def p12217(c: Cast) -> None:
    """`ally_within` reads the *attacker* on a `Hit`, which is the wrong end
    of the sentence, and no stock predicate asks whose mark the attacker
    carries -- hence the two local ones."""
    spot = beside(c)
    if spot is not None:
        c.teleport(c.distance() + 1, who=c.target, to=spot)
    if c.strike():
        c.damage(c.w(2), c.int_mod)
        c.ongoing(5, DamageType.LIGHTNING)
    else:
        c.half_damage(c.w(2), c.int_mod)
        c.flat(5, dtype=DamageType.LIGHTNING)


@power(
    "p13445",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.ILLUSION, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=AC),
)
def p13445(c: Cast) -> None:
    """The standing half is a watch on every melee hit of mine for the rest
    of the fight; the blink it buys is optional, so it asks."""
    if c.strike():
        c.damage(c.w(2), c.int_mod)
        c.mark()
    else:
        c.half_damage(c.w(2), c.int_mod)
    c.teleport(5)
    c.invisible(on=c.me, until=When.EONT)
    me = c.me

    def blink(ev: Hit) -> None:
        if ev.attacker == me and by_melee(c.world, me, ev) and c.may("blink", who=me):
            c.teleport(3, who=me)

    c.watch(Hit, blink, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p16009",
    level=1,
    cls="swordmage",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=REF),
)
def p16009(c: Cast) -> None:
    """The mounted clause reads the charge flag and the mount relation, both
    of which the context already carries."""
    if c.strike():
        extra = c.int_mod if c.charge and c.mount() is not None else 0
        c.damage("2d8" if c.level >= 21 else "1d8", extra, dtype=DamageType.THUNDER)
        c.slowed()


@power(
    "p16010",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
    trigger="you teleport an enemy to a square adjacent to you on your turn",
    on=Trigger(
        MoveEnd,
        teleported_beside_me,
        "you teleport an enemy to a square adjacent to you on your turn",
    ),
)
def p16010(c: Cast) -> None:
    if c.strike():
        extra = c.con_mod if c.build("ensnarement") else 0
        c.damage(c.w(), c.int_mod + extra)


@power(
    "p16011",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=Target("enemy", 1, label="marked by you"),
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p16011(c: Cast) -> None:
    """The printed Aftereffect pays out when the immobilisation is shaken
    off, so it hangs on the saving throw rather than on a second duration.
    The target restriction is a relation, so it is read as the row runs."""
    if not c.marked():
        return
    victim = c.target
    if c.immobilized(until=When.SAVE_ENDS) is None:
        return
    me = c.me

    def follow(ev: SavingThrow) -> None:
        if ev.actor != victim or not ev.saved or not c.may("follow", who=me):
            return
        spot = beside(c, victim)
        if spot is not None and c.teleport(10, who=me, to=spot):
            c.basic(on=victim, who=me)

    c.watch(SavingThrow, follow, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p1710",
    level=1,
    cls="swordmage",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=REF),
)
def p1710(c: Cast) -> None:
    if c.strike():
        c.damage("2d6" if c.level >= 21 else "1d6", c.int_mod, dtype=DamageType.FORCE)


@power(
    "p1711",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.LIGHTNING],
    attack=Attack(INT, vs=AC),
)
def p1711(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod)
    nearby = [f for f in c.within(5, of=c.target, side="enemy") if f != c.target]
    second = c.choose(sorted(nearby), "the arc jumps to") if nearby else None
    if second is not None and c.attack(c.int_, REF, on=second):
        c.damage("1d6", c.int_mod, dtype=DamageType.LIGHTNING, on=second)


@power(
    "p1721",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p1721(c: Cast) -> None:
    """The Special is permission to swap this in for a basic attack on a
    charge, which is a property of the row rather than an effect of it."""
    if c.strike():
        c.damage(c.w(), c.int_mod)
        c.immobilized()


@power(
    "p1724",
    level=1,
    cls="swordmage",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FIRE],
    attack=Attack(INT, vs=AC),
)
def p1724(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.int_mod, dtype=DamageType.FIRE)
        for foe in c.within(1, of=c.target, side="enemy"):
            if foe != c.target:
                c.flat(c.str_mod, dtype=DamageType.FIRE, on=foe)


@power(
    "p1725",
    level=1,
    cls="swordmage",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.THUNDER],
    attack=Attack(INT, vs=AC),
)
def p1725(c: Cast) -> None:
    """Two clauses read at two different moments: adjacency at the start of
    the target's next turn, the step away during it. The rider rolls through
    `c.flat` so that a critical on the original swing cannot maximise it."""
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.int_mod)
    victim = c.target
    state: dict[str, bool] = {}

    def begin(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost:
            state["armed"] = c.adjacent(victim)

    def leaving(ev: MoveEnd) -> None:
        if ev.actor != victim or state.get("spent") or not state.get("armed"):
            return
        if c.distance(victim) > 1:
            state["spent"] = True
            c.flat(c.roll("1d6") + c.con_mod, dtype=DamageType.THUNDER, on=victim)

    c.watch(TurnStart, begin, until=When.EOTNT, on=victim, label=c.ref)
    c.watch(MoveEnd, leaving, until=When.EOTNT, on=victim, label=c.ref)
