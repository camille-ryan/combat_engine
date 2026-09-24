"""Cleric, level 1: the powers that are not at-will."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnEnd,
    When,
    power,
    spread,
)


@power(
    "p891",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def p891(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
        c.mark()
        # "you or one ally within 5" -- the caster is in the pool, and is
        # usually the right answer when the caster is the one who is hurt.
        nearby = [a for a in c.within(5, side="ally")]
        if nearby:
            c.surge(on=c.choose(nearby, "who spends a healing surge"))


@power(
    "p890",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.FEAR, Keyword.IMPLEMENT],
    attack=Attack(WIS, vs=WILL),
)
def p890(c: Cast) -> None:
    if c.strike():
        # It runs, and this is explicitly *not* forced movement, so it
        # provokes on the way out -- which is the whole point of the power.
        c.flee(c.speed_of() + c.cha_mod)


@power(
    "p1455",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
    uses=2,
    once_per_round=True,
)
def p1455(c: Cast) -> None:
    """The Special line -- twice a fight, but not twice in one round."""
    hurt = [a for a in c.within(5, side="ally") if c.wounded(a)]
    if not hurt:
        return
    who = c.choose(hurt, "who is healed")
    if c.surge(on=who):
        c.heal(c.world.rng.roll("1d6").total, on=who)


@power(
    "p913",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.IMPLEMENT],
    attack=Attack(WIS, vs=WILL),
)
def p913(c: Cast) -> None:
    if c.strike():
        c.weakened(until=When.EOTNT)
    if c.first:
        # The Effect line lands once, whatever the attacks did.
        for friend in [c.me, *c.within(3, side="ally")]:
            c.heal(5, on=friend)


@power(
    "p892",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def p892(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod, dtype=DamageType.THUNDER)
        c.dazed()


@power(
    "p893",
    level=1,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p893(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.RADIANT)
    if c.first:
        # The Effect line lands once, and does not care what the attacks did.
        # A blast does not cover the caster's own square, but `in_squares`
        # counts the caster as an ally, so it comes back out.
        for friend in c.in_squares(c.area(), side="ally"):
            if friend != c.me:
                c.bonus("attack", 2, on=friend)


@power(
    "p1404",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def p1404(c: Cast) -> None:
    """Only the ongoing damage is fire; the weapon dice are printed untyped."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.ongoing(5, DamageType.FIRE)
        c.note(
            f"p1404: on a turn {c.target} attacks, it could not make a saving throw against "
            "this ongoing damage -- suppressing a saving throw is not expressible"
        )
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p914",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p914(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.wis_mod, dtype=DamageType.RADIANT)
        # A damage bonus on the caster would pay out at roughly the same rate,
        # but it is held by the wrong creature: a save-ends duration is rolled
        # by whoever holds it, and here that has to be the target.
        c.note(
            f"p914: {c.target} would be vulnerable 5 to all damage from your attacks "
            "(save ends) -- vulnerability is not expressible"
        )
    else:
        c.half_damage("3d8", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p916",
    level=1,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[
        Keyword.CONJURATION,
        Keyword.DIVINE,
        Keyword.IMPLEMENT,
        Keyword.RADIANT,
    ],
)
def p916(c: Cast) -> None:
    """A standing thing in one square that lashes out at the end of a turn.

    There is no conjuration in `Cast`, so it is a one-square zone plus a
    watcher. Two printed clauses go unsaid: the thing occupies its square
    (a zone does not), and a move action shifts it three squares (a zone
    does not move).

    The attack is rolled by hand rather than with `c.strike()`: it happens
    outside the cast, against whoever's turn just ended, not against a
    declared target.
    """
    room = [
        sq
        for sq in spread({c.here}, 5)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    # Every square in range is a legal answer, but only the ones standing next
    # to somebody can ever attack, so those are what gets offered.
    useful = [sq for sq in room if c.in_squares(spread({sq}, 1), side="enemy")]
    where = c.choose(sorted(useful or room), "where it stands")
    if where is None:
        return
    beside = spread({where}, 1)
    c.zone([where], until=When.ENCOUNTER)

    def lash(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.in_squares(beside, side="enemy"):
            return
        if c.attack(c.wis_, FORT, on=ev.actor):
            c.damage("1d8", c.wis_mod, dtype=DamageType.RADIANT, on=ev.actor)

    c.watch(TurnEnd, lash, until=When.ENCOUNTER, label="p916")
    c.note("p916: a move action would move it up to 3 squares -- a zone does not move")
