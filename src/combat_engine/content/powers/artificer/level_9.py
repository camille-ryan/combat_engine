"""Artificer, level 9."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    INT,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    power,
)

from . import ally_struck


@power(
    "p10204",
    level=9,
    cls="artificer",
    usage=DAILY,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.HEALING, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(INT, vs=AC),
    trigger="an enemy deals damage to an ally within 5 squares of you",
    on=Trigger(Hit, ally_struck(5), "an enemy hits an ally within 5 squares"),
)
def p10204(c: Cast) -> None:
    """Whose surge it is decides whether it is worth spending, so the ally
    is asked. The two others are measured from the *target*, as printed,
    not from the caster."""
    ally = getattr(c.trigger, "target", None)
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.int_mod)
    else:
        c.half_damage(c.w(2), c.int_mod)
    if ally is not None and c.may("spend a healing surge", who=ally):
        c.surge(on=ally)
    others = [a for a in c.within(5, of=victim, side="ally") if a != ally]
    for who in others[:2]:
        c.temp_hp(c.surge_value(of=who), on=who)


@power(
    "p10205",
    level=9,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING],
)
def p10205(c: Cast) -> None:
    """The infusion only. The burst it grants once a round is a separate
    compendium row and this spec gives it no id, so there is nothing for
    `c.grant_row` to name."""
    c.resist(5, DamageType.LIGHTNING, on=c.target, until=When.ENCOUNTER)


@power(
    "p4146",
    level=9,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p4146(c: Cast) -> None:
    """`escalate` is the "each failed saving throw" line. The aftereffect
    hangs off the daze ending, which is very nearly right: it also fires if
    the daze is lifted some other way, and nothing else carries an
    aftereffect."""
    victim = c.target
    if not c.strike():
        c.half_damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)
        c.ongoing(5, DamageType.LIGHTNING)
        return
    c.damage("2d6", c.int_mod, dtype=DamageType.LIGHTNING)

    def jolt(eff: Effect) -> None:
        c.flat(5, dtype=DamageType.LIGHTNING, on=victim)

    daze = c.condition(Condition.DAZED, until=When.SAVE_ENDS, escalate=jolt)
    if daze is not None:
        daze.on_end.append(lambda: c.ongoing(5, DamageType.LIGHTNING, on=victim))


@power(
    "p4147",
    level=9,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(INT, vs=AC),
)
def p4147(c: Cast) -> None:
    """The vulnerability is printed as applying to melee attacks only and
    `c.vulnerable` takes a damage type rather than a gate, so it is written
    open. That is broader than the card -- named in the report."""
    if c.strike():
        c.damage(c.w(2), c.int_mod)
        c.slowed(until=When.SAVE_ENDS)
        c.vulnerable(5, on=c.target, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.int_mod)
        c.slowed(until=When.SAVE_ENDS)
