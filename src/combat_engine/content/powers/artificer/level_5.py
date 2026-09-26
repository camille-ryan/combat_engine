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
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    Damage,
    DamageType,
    Dropped,
    Keyword,
    Melee,
    Ranged,
    Summon,
    TurnEnd,
    TurnStart,
    When,
    get,
    power,
)

from . import enemies_starting_in, holding_a_melee_weapon, one_ally


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


@power(
    "p4141",
    level=5,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    requires=holding_a_melee_weapon,
    requires_text="must be holding a melee weapon",
    thrown_by_hand=True,
    summon=Summon(speed=0, modes=("fly",), attack=Attack(INT, vs=AC)),
)
def p4141(c: Cast) -> None:
    """The command's damage is `1[W]`, which the header cannot hold: `Damage.dice`
    is a static string and which weapon was thrown is only known at use. The
    summon therefore carries the attack line and no damage line -- see the
    report. "It returns to your hand instead of costing you a surge" needs no
    saying: nothing charges a surge for a summon dropping.

    `Summon.modes` names a way of moving and carries no speed with it, so the
    printed "fly 6" is set from the body."""
    weapon = c.summon_inline(get(c.ref).summon, at=c.origin)
    if weapon:
        c.mode("fly", 6, on=weapon, until=When.ENCOUNTER)


@power(
    "p7650",
    level=5,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
    summon=Summon(
        speed=6,
        attack=Attack(INT, vs=AC, plus=2),
        damage=Damage("2d6", "int", dtype=DamageType.FIRE),
    ),
)
def p7650(c: Cast) -> None:
    """The enemies are marked *by the servant*, not by the caster, which is what
    `by=` is for. The death throe rolls its own line from the servant's square
    -- `Attack.bonus_for` is the same call `c.command` makes -- and is skipped
    if the servant has already left the board."""
    servant = c.summon_inline(get(c.ref).summon, at=c.origin)
    if not servant:
        return

    def brand(ev: TurnStart) -> None:
        if ev.actor != c.me:
            return
        for foe in c.within(1, of=servant, side="enemy"):
            c.mark(on=foe, by=servant, until=When.EONT)

    c.watch(TurnStart, brand, until=When.ENCOUNTER)

    def throe(ev: Dropped) -> None:
        if ev.actor != servant:
            return
        line = Attack(INT, vs=REF)
        bonus = line.bonus_for(c.world, servant, c.ref)
        for who in c.within(2, of=servant):
            if c.attack(bonus, REF, on=who, from_=servant):
                c.damage("1d8", c.wis_mod, dtype=DamageType.FIRE, on=who)

    c.watch(Dropped, throe, until=When.ENCOUNTER)
