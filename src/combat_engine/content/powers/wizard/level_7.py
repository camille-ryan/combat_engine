"""Wizard, level 7: the encounter attacks.

Three evocations with nothing to explain and one that leaves a zone behind.
The zone's teeth bite at the start of a turn and nowhere else, so they are a
`TurnStart` watch rather than `c.hazard` or `c.burns` -- both of those also
catch whoever walks in, which is a clause this row does not print. "Only
once per turn" comes free with that: there is one turn start per turn.
"""

from __future__ import annotations

from combat_engine.engine import (
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
    DamageType,
    Keyword,
    Ranged,
    TurnStart,
    UpTo,
    When,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1430",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p1430(c: Cast) -> None:
    """"Lightly obscured" is concealment, which this engine keeps no state
    for -- it is a -2 an attacker takes, and there is no way to hang one on a
    square rather than on a creature -- so the zone carries its cold and
    nothing else. `blocks_sight` would be the wrong word for it: that is a
    wall, not a haze.
    """
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, until=When.EONT)

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.world.zones.occupants(zone):
            return
        c.flat(c.int_mod, dtype=DamageType.COLD, on=ev.actor)

    c.watch(TurnStart, dawn, until=When.EONT, label=c.ref)
    c.note(f"{c.ref}: the zone is lightly obscured, and there is no concealment here")


@power(
    "p189",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p189(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", c.int_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("3d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p251",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p251(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)


@power(
    "p454",
    level=7,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=FORT),
)
def p454(c: Cast) -> None:
    """The miss line shoves it just as far; only the fall is a hit rider."""
    if c.strike():
        c.damage("2d10", c.int_mod, dtype=DamageType.FORCE)
        c.push(3)
        c.prone()
    else:
        c.push(3)
