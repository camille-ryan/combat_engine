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
    target=Target("team", 1, label="bloodied"),
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    dropped=("c.grant_action('end_effect_for_surge')",),
)
def p4142(c: Cast) -> None:
    """**`c.regeneration` is the primitive, and this row hand-rolled it.**
    The old note said "there is no primitive for it" and then wrote one out
    as a `TurnStart` watch -- which worked, and is the shape three rows in
    three files had each grown separately. The verb takes the amount, the
    duration, whose it is and a `while_bloodied` gate. #1341.

    Cashing the effect in for a healing surge is the half that really is
    missing and now carries the marker: it is the target's own later minor
    action, `c.grant_action` is the facility for a granted action, and
    `actions.GRANTABLE` -- which is the authority, and raises on a word it
    does not know -- has no word for ending an effect.
    """
    ally = c.target
    if ally is None or not c.bloodied(ally) or c.con_mod <= 0:
        return
    c.regeneration(c.con_mod, on=ally, until=When.ENCOUNTER)


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
