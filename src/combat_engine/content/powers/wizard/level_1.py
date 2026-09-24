"""Wizard, level 1.

Implement powers throughout, so no proficiency rides along with the attack.

Several rows leave a zone behind. `c.area()` is the only way to ask what a
burst covered, and it reads the origin off the `Cast` -- which is None when
the caller let the engine pick the aim point, so the zone lands on the
caster rather than where the burst went. Where the shape allows it the zone
is built from the squares the power actually caught instead.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
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
    Effect,
    Keyword,
    Ranged,
    When,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1167",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=FORT),
)
def p1167(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.COLD)
        c.slowed()


@power(
    "p1166",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p1166(c: Cast) -> None:
    # An area burst rolls separately against everyone it catches, and the
    # body runs once per target, so there is no loop to write here.
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p463",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
)
def p463(c: Cast) -> None:
    # No attack roll at all: the damage simply happens.
    c.flat(2 + c.int_mod, dtype=DamageType.FORCE)


@power(
    "p1164",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    # "Area 1 square within 10 squares": a burst of radius 0.
    reach=AreaBurst(0, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p1164(c: Cast) -> None:
    """The zone is the one square the power covers, which is the square the
    targets are standing in -- so it is built from there rather than from
    `c.area()`. "Or until you end it as a minor action" has no expression;
    the duration alone stands."""
    square = c.there
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FORCE)
    if c.first:
        c.hazard({square}, max(1, c.wis_mod), DamageType.FORCE, until=When.EONT)


@power(
    "p1169",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=FORT),
)
def p1169(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.THUNDER)
        c.push(max(0, c.wis_mod))


@power(
    "p1171",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=FORT),
)
def p1171(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
        c.dazed()
    else:
        c.slowed()


@power(
    "p1424",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p1424(c: Cast) -> None:
    """Difficult ground and nothing else, so a plain zone rather than a
    hazard. "Or until you end it as a minor action" is not expressible."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.COLD)
        c.prone()
    if c.first:
        c.zone(c.area(), until=When.EONT, difficult=True)


@power(
    "p416",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(INT, vs=FORT),
)
def p416(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.NECROTIC)
        c.weakened()
    else:
        c.half_damage("1d10", c.int_mod, dtype=DamageType.NECROTIC)


@power(
    "p451",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p451(c: Cast) -> None:
    """No damage at all -- the whole power is the condition.

    "First Failed Saving Throw" is `escalate`, which runs on a failed save:
    the slow ends and unconsciousness replaces it. The replacement carries no
    escalation of its own, so it cannot fire twice. The miss line is the same
    condition without that clause, as printed.
    """

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.unconscious(on=eff.owner)

    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=worsen)
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p464",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(INT, vs=REF),
)
def p464(c: Cast) -> None:
    """The secondary attack rolls the same line -- Intelligence vs. Reflex --
    so it is `c.strike(on=...)` once per creature in the burst round the
    primary target. The Effect line makes it unconditional on the primary
    attack landing. It catches allies too, which is what the row says.
    """
    primary = c.target
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.ACID)
        c.ongoing(5, DamageType.ACID)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.ACID)
        c.ongoing(2, DamageType.ACID)

    for who in c.within(1, of=primary):
        if who == primary:
            continue
        if c.strike(on=who):
            c.damage("1d8", c.int_mod, dtype=DamageType.ACID, on=who)
            c.ongoing(5, DamageType.ACID, on=who)


@power(
    "p465",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    # Printed as "one creature or object". Objects are not on the board.
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=REF),
)
def p465(c: Cast) -> None:
    """Secondary attack only on a hit, and only at enemies -- unlike p464,
    which catches everything in the burst."""
    primary = c.target
    if not c.strike():
        return
    c.damage("2d8", c.int_mod, dtype=DamageType.FORCE)

    for who in c.within(1, of=primary, side="enemy"):
        if who == primary:
            continue
        if c.strike(on=who):
            c.damage("1d10", c.int_mod, dtype=DamageType.FORCE, on=who)
