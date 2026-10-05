"""Invoker, level 1: the at-wills and half the encounter rows.

Two judgements run through the whole class and are not repeated in every
docstring below.

*Covenants* are the class's build fork, so a "Covenant of X" rider is
`c.build("x")` -- wrath, preservation, malediction.

*Level 21* upgrades a printed damage die and nothing else, so it is a
`c.level >= 21` pick of the dice string rather than a second row.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Defense,
    Keyword,
    MoveEnd,
    Ranged,
    UpTo,
    When,
    power,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


@power(
    "p2847",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=FORT),
)
def p2847(c: Cast) -> None:
    """"A bloodied ally adjacent to the target" leaves the caster out: the
    ally pool includes you. The printed "can be used as a ranged basic
    attack" is a property of the character, not a header field, so it is
    not declared here."""
    if c.strike():
        near = [a for a in c.within(1, of=c.target, side="ally") if a != c.me]
        extra = c.con_mod if any(c.bloodied(on=a) for a in near) else 0
        dice = "2d10" if c.level >= 21 else "1d10"
        c.damage(dice, c.wis_mod + extra, dtype=DamageType.RADIANT)


@power(
    "p2848",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=REF),
)
def p2848(c: Cast) -> None:
    if c.strike():
        dice = "2d6" if c.level >= 21 else "1d6"
        c.damage(dice, c.wis_mod, dtype=DamageType.LIGHTNING)


@power(
    "p2849",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=REF),
)
def p2849(c: Cast) -> None:
    """The rider watches `AttackRolled` rather than `AttackDeclared`: the
    opportunity flag is set on the roll, so the declaration cannot answer
    "whenever the target makes an opportunity attack"."""
    victim = c.target
    if victim is None or not c.strike():
        return
    dice = "2d6" if c.level >= 21 else "1d6"
    c.damage(dice, c.wis_mod, dtype=DamageType.LIGHTNING)

    def sting(ev: AttackRolled, who: int = victim) -> None:
        if ev.attacker == who and getattr(ev, "opportunity", False):
            c.flat(c.int_mod, dtype=DamageType.LIGHTNING, on=who)

    c.watch(AttackRolled, sting, until=When.EONT, on=victim)


@power(
    "p2850",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=FORT),
)
def p2850(c: Cast) -> None:
    if c.strike():
        c.damage("1d10" if c.level >= 21 else 0, c.wis_mod, dtype=DamageType.RADIANT)
        c.slowed(until=When.EONT)


@power(
    "p5137",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p5137(c: Cast) -> None:
    """The ranged-basic clause has no header field and is left undeclared."""
    if c.strike():
        c.damage("2d8" if c.level >= 21 else "1d8", c.wis_mod, dtype=DamageType.RADIANT)
        c.slide(1)


@power(
    "p7151",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p7151(c: Cast) -> None:
    """The level 21 line adds a fourth target. Target count is header data
    and cannot be read off the caster's level, so it is not declared."""
    if c.strike():
        c.damage("1d4", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p7152",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p7152(c: Cast) -> None:
    """Deepening the mark's penalty is written as a second -2 that is live
    only while the mark is: the mark's own duration belongs to whoever set
    it, so the rider is gated on the condition rather than given a guessed
    end."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d6" if c.level >= 21 else "1d6", c.wis_mod, dtype=DamageType.RADIANT)
    if c.is_(Condition.MARKED, on=victim):
        c.penalty(
            "attack",
            2,
            until=When.ENCOUNTER,
            when=lambda ctx, w=victim: c.is_(Condition.MARKED, on=w),
        )


@power(
    "p7153",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p7153(c: Cast) -> None:
    if c.strike():
        c.damage("2d6" if c.level >= 21 else "1d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        for d in Defense:
            c.penalty(d, 1, until=When.SONT)


@power(
    "p7385",
    level=1,
    cls="invoker",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p7385(c: Cast) -> None:
    """"Moves nearer to you" is measured against the distance at the moment
    of the hit, and paid at the end of the step rather than at its start."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d6" if c.level >= 21 else "1d6", c.wis_mod)
    c.push(1)
    was = c.distance(to=victim)

    def closer(ev: MoveEnd, who: int = victim, before: int = was) -> None:
        if ev.actor == who and c.distance(to=who) < before:
            c.flat(c.con_mod, on=who)

    c.watch(MoveEnd, closer, until=When.EOTNT, on=victim, once=True)


@power(
    "p11280",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p11280(c: Cast) -> None:
    """The secondary attack is the same target and the same ability against
    a different defence, so it rolls `c.wis_` by hand rather than the
    header line."""
    if c.strike():
        c.damage("1d10", c.wis_mod)
        c.slide(3)
        if c.attack(c.wis_, FORT):
            c.prone()


@power(
    "p11281",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=AC, plus=2),
)
def p11281(c: Cast) -> None:
    if c.strike():
        extra = c.con_mod if c.build("wrath") else 0
        c.damage("1d8", c.wis_mod + extra)
        if c.build("malediction"):
            c.penalty("attack", 2, until=When.EONT)


@power(
    "p2853",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p2853(c: Cast) -> None:
    if c.strike():
        dice = "2d6" if len(c.targets) == 1 else "1d6"
        c.damage(dice, c.wis_mod, dtype=DamageType.THUNDER)
        c.dazed(until=When.EONT)
        if c.build("wrath"):
            c.push(c.con_mod)


@power(
    "p2855",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p2855(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        c.immobilized(until=When.EONT)


@power(
    "p5187",
    level=1,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p5187(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.push(2)
