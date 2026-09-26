"""Ardent, level 10: one enemy the caster can always find."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    FREE,
    ONE_CREATURE,
    Cast,
    CloseBurst,
    Event,
    Hit,
    Keyword,
    Trigger,
    When,
    World,
    power,
    targets_my_side,
)


def _hits_an_ally_of_mine(world: World, me: int, ev: Event) -> bool:
    """"An enemy hits your ally" -- your ally, not you.

    `targets_my_side` is also true when the caster is the one hit, and the
    printed trigger is about somebody else.
    """
    struck = getattr(ev, "target", None)
    return struck is not None and struck != me and targets_my_side(world, me, ev)


@power(
    "p13784",
    level=10,
    cls="ardent",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC],
    trigger="an enemy hits your ally with an attack",
    on=Trigger(Hit, _hits_an_ally_of_mine, "an enemy hits your ally"),
)
def p13784(c: Cast) -> None:
    """The target is the creature that swung, which the header cannot name, so
    it comes off the triggering event. `c.truesight(of=)` is the "you always
    know its exact location" half -- the one shape of that sense aimed at a
    single named creature -- and `c.no_cover` gated on `attacker` is the
    other, which is narrower than `c.ignore_cover` on the caster: the card
    blinds nobody else's shot."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None) if ev is not None else c.target
    if foe is None:
        return
    c.truesight(of=foe, on=c.me, until=When.ENCOUNTER)

    def by_me(ctx: dict[str, Any]) -> bool:
        return ctx.get("attacker") == c.me

    c.no_cover(on=foe, until=When.ENCOUNTER, when=by_me)
