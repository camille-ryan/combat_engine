"""Psion, level 9: the dailies."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    INT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    DamageType,
    Keyword,
    Ranged,
    When,
    power,
)

PSIONIC_IMPLEMENT = [Keyword.PSIONIC, Keyword.IMPLEMENT]
PSIONIC_PSYCHIC = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC]


@power(
    "p11321",
    level=9,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=FORT),
)
def p11321(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FORCE)
        c.slide(3 + c.wis_mod)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.FORCE)
        c.slide(1)


@power(
    "p11322",
    level=9,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.FORCE,
        Keyword.THUNDER,
    ],
    attack=Attack(INT, vs=FORT),
)
def p11322(c: Cast) -> None:
    """The secondary burst is an Effect line -- it happens whether or not the
    primary landed -- and rolls the same attack, so it is folded in. "Force
    and thunder damage" is dealt as force: `c.damage` carries one type, and
    both keywords are on the header either way."""
    primary = c.target
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.FORCE)
        c.push(1)
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)
    for other in c.within(1, of=primary, side="any"):
        if other == primary:
            continue
        if c.strike(on=other):
            c.damage("1d8", c.wis_mod, dtype=DamageType.THUNDER, on=other)
        else:
            c.half_damage("1d8", c.wis_mod, dtype=DamageType.THUNDER, on=other)


@power(
    "p13336",
    level=9,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=FORT),
)
def p13336(c: Cast) -> None:
    """The immediate reaction the sustained hold unlocks is printed as a second
    block under this same id, so it has no ref of its own to be declared
    under. The hold itself is here because it is what a Sustain Minor is
    spent on."""
    if c.first:
        c.effect(c.ref, on=c.me, until=When.SUSTAIN, sustain=MINOR)
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.THUNDER)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.THUNDER)


@power(
    "p13338",
    level=9,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p13338(c: Cast) -> None:
    """"Save ends both" is one effect carrying the slow and the burn, so one
    save ends the pair."""
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.PSYCHIC),
        )
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed(until=When.EONT)


@power(
    "p13339",
    level=9,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.LIGHTNING,
        Keyword.CONJURATION,
    ],
    attack=Attack(INT, vs=REF),
)
def p13339(c: Cast) -> None:
    """The once-per-round burst fired from a mote is printed as a second block
    under this same id, so it has no ref of its own -- and with it goes the
    expending, which is why the motes here last the encounter."""
    if c.first:
        made = 0
        for sq in sorted(c.area()):
            if made >= 4:
                break
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
                c.conjure(
                    at=sq,
                    until=When.ENCOUNTER,
                    sustain=None,
                    aura=1,
                    burn=(c.int_mod, DamageType.LIGHTNING),
                )
                made += 1
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)


@power(
    "p8241",
    level=9,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(INT, vs=WILL),
)
def p8241(c: Cast) -> None:
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)
    else:
        c.dazed(until=When.EONT)


@power(
    "p8242",
    level=9,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8242(c: Cast) -> None:
    """"It can't take opportunity actions" is dropped -- `c.forbid` takes one
    named row away and `c.no_basic` takes away what a row is used as; neither
    bars a category of action."""
    if c.strike():
        c.damage("2d10", c.int_mod, dtype=DamageType.PSYCHIC)
        c.ongoing(5, DamageType.PSYCHIC)
    else:
        c.half_damage("2d10", c.int_mod, dtype=DamageType.PSYCHIC)
    c.penalty("attack", 2, until=When.EONT)
    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, 2, until=When.EONT)
