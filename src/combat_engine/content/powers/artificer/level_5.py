"""Artificer, level 5.

Three of the seven printed rows create a servant with its own stat block and
are not here; see the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    INT,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnEnd,
    When,
    power,
)

from . import enemies_starting_in, one_ally


@power(
    "p10197",
    level=5,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(INT, vs=AC),
)
def p10197(c: Cast) -> None:
    """The Special line is `from_=`: the shot is measured and rolled from the
    ally's square. The teleport the Effect also grants for the encounter is a
    separate compendium row and this spec gives it no id."""
    ally = one_ally(c, c.within(5, side="ally"), "whose square the shot comes from")
    if c.strike(from_=ally):
        c.damage(c.w(3), c.int_mod, dtype=DamageType.FORCE)
        c.push(1 + c.wis_mod)
    else:
        c.half_damage(c.w(3), c.int_mod, dtype=DamageType.FORCE)
        c.push(2)


@power(
    "p10199",
    level=5,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.THUNDER],
)
def p10199(c: Cast) -> None:
    """The infusion and its retort. The burst it also grants once a round is
    a separate compendium row with no id in this spec."""
    ward = c.target
    if ward is None:
        return
    c.resist(5, DamageType.THUNDER, on=ward, until=When.ENCOUNTER)

    def jolt(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if c.adjacent_to(ward, ev.actor):
            c.flat(5, dtype=DamageType.THUNDER, on=ev.actor)

    c.watch(TurnEnd, jolt, until=When.ENCOUNTER)


@power(
    "p14402",
    level=5,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=REF),
)
def p14402(c: Cast) -> None:
    """The ally swings whether or not the artificer's own attack landed; only
    the bonus turns on that. Constitution or Wisdom is taken as the larger."""
    victim = c.target
    landed = c.strike()
    if landed:
        c.damage("2d8", c.int_mod, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)
    beside = [a for a in c.allies() if c.adjacent_to(victim, a)]
    ally = one_ally(c, beside, "who swings")
    if ally is not None:
        c.grant_attack(
            ally,
            on=victim,
            attack_bonus=max(c.con_mod, c.wis_mod) if landed else 0,
        )


@power(
    "p4140",
    level=5,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(INT, vs=AC),
)
def p4140(c: Cast) -> None:
    """The shards bite enemies only, so this is not `c.hazard` -- that one
    burns whoever is standing there, the caster's own side included, and on
    entering as well as on starting a turn."""
    if c.first:
        zone = c.zone(c.area(), until=When.ENCOUNTER)
        enemies_starting_in(c, zone, 5, DamageType.FORCE, until=When.ENCOUNTER)
    if c.strike():
        c.damage(c.w(2), c.int_mod)
    else:
        c.half_damage(c.w(2), c.int_mod)
