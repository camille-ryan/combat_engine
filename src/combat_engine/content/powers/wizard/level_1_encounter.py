"""Wizard, level 1: the powers that are not at-will."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    INT,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Keyword,
    Ranged,
    When,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p159",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p159(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p185",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p185(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.COLD)
    if c.first:
        # The burst leaves the ground frozen behind it. `hazard` carries the
        # whole "enters or starts its turn there, once per turn" clause.
        c.hazard(c.area(), 5, DamageType.COLD, until=When.SUSTAIN)


@power(
    "p1435",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
)
def p1435(c: Cast) -> None:
    """A rolling ball of fire that stands in a square and can be walked.

    The first row written against `c.conjure`, and it needs every part of
    it: the sphere occupies its square, burns whoever starts a turn beside
    it, is moved by a move action, attacks from its own position rather
    than the wizard's, and persists while sustained.

    The burn is an aura 1 hung on the sphere rather than on the wizard,
    which is the whole reason `c.aura` grew an `on=` -- the footprint has to
    follow the thing, not its maker.
    """
    if not c.first:
        return
    sphere = c.conjure(
        label="p1435",
        until=When.SUSTAIN,
        speed=6,
        aura=1,
        burn=(c.roll("1d4") + c.int_mod, DamageType.FIRE),
    )
    if not sphere:
        return
    # It appears swinging. Commanding it again later is a standard action,
    # which the conjuration offers for as long as it is on the board.
    if c.target is not None and c.strike(from_=sphere):
        c.damage("2d6", c.int_mod, dtype=DamageType.FIRE)
