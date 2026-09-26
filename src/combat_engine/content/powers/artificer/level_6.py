"""Artificer, level 6: the utilities."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageRolled,
    Health,
    Keyword,
    Ranged,
    SurgeSpent,
    Target,
    Trigger,
    TurnStart,
    When,
    ally_within,
    power,
)

from . import ally_struck


@power(
    "p10201",
    level=6,
    cls="artificer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=Target("ally", 1),
    keywords=[Keyword.ARCANE],
    trigger="an ally takes damage from an attack",
    on=Trigger(DamageRolled, ally_struck(10), "an ally takes damage"),
)
def p10201(c: Cast) -> None:
    """"Resist all N against the triggering attack" is `c.reduce` from the
    interrupt window, where the damage is rolled and not yet dealt. The
    temporary hit points are printed as arriving *after* the attack
    resolves, so they wait for the `DamageApplied` -- granted here they
    would soak the very blow they are meant to follow."""
    ally = getattr(c.trigger, "target", None)
    if ally is None:
        return
    ward = 5 + c.wis_mod
    c.reduce(ward)

    def after(ev: DamageApplied) -> None:
        if ev.target == ally:
            c.temp_hp(ward, on=ally)

    c.watch(DamageApplied, after, until=When.EONT, once=True)


@power(
    "p4142",
    level=6,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("ally", 1, label="bloodied"),
    keywords=[Keyword.ARCANE, Keyword.HEALING],
)
def p4142(c: Cast) -> None:
    """Regeneration is a heal at the start of each of the target's turns --
    there is no primitive for it. Cashing the effect in for a healing surge
    is the target's own later minor action and nothing declares one."""
    ally = c.target
    if ally is None or not c.bloodied(ally) or c.con_mod <= 0:
        return

    def mend(ev: TurnStart) -> None:
        if ev.actor == ally and not ev.ghost:
            c.heal(c.con_mod, on=ally)

    c.watch(TurnStart, mend, until=When.ENCOUNTER)


@power(
    "p7651",
    level=6,
    cls="artificer",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p7651(c: Cast) -> None:
    """A bonus to one skill check and nothing else, so deliberately inert."""
    c.note("p7651: a bonus to your next skill check this turn")


@power(
    "p7652",
    level=6,
    cls="artificer",
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=Target("ally", 1),
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    trigger="an ally within 10 squares of you spends a healing surge",
    on=Trigger(SurgeSpent, ally_within(10), "an ally spends a healing surge"),
)
def p7652(c: Cast) -> None:
    """`SurgeSpent` is a notification rather than a proposal, so the surge
    cannot be refused -- it is put back instead, which is the same arithmetic
    and the only way to say "does not expend the healing surge"."""
    ally = getattr(c.trigger, "actor", None)
    if ally is None:
        return
    health = c.world.get(ally, Health)
    if health is not None:
        health.surges += 1
    c.heal(c.wis_mod, on=ally)
