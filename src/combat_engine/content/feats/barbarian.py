"""Barbarian feats.

`Keyword.RAGE` does not exist -- `docs/blocked.json` records
`cf:barbarian-rage` waiting on it -- so "while raging" is not a state
anything can ask about. Two rows here want it and name it exactly.

The two that do not are ordinary triggers.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageApplied,
    Dropped,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import allies

RAGE = ("Keyword.RAGE",)


@power("f454", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reduce an enemy to 0 hit points",
       on=Trigger(Dropped, lambda w, me, ev: (
           getattr(ev, "source", None) == me
       ), "you drop an enemy"))
def f454(c: Cast) -> None:
    """A **weapon** damage bonus, so it is gated on the power carrying
    the weapon keyword rather than left open -- the card says weapon and
    a barbarian's rage rows are not all of them."""
    from combat_engine.engine import Keyword
    from combat_engine.engine.dsl import get

    c.bonus(
        "damage", 2, on=c.me, until=When.EONT, kind="feat",
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.WEAPON in p.keywords
        ),
    )


def _i_bloodied_it(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """Did *this* blow of mine take the target across half?

    **`Bloodied` carries `actor` and nothing else.** This row was
    declared on it with a predicate reading `ev.source`, which no
    `Bloodied` has ever had -- so the predicate was False forever and
    the row was inert from the day it was written. A `getattr` with a
    default is what hid it.

    `DamageApplied` carries `source`, `amount` and the hit points left
    *after* the blow, which is everything the question needs: the
    crossing is `hp` at or under half where `hp + amount` was above it.
    Five item rows carry `Bloodied.source` as a marker for the same gap
    and the same derivation would close all of them.
    """
    from combat_engine.engine import Health

    if ev.source != me:
        return False
    health = world.get(ev.target, Health)
    if health is None:
        return False
    half = health.max_hp // 2
    return ev.hp <= half < ev.hp + ev.amount


@power("f1826", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you bloody an enemy",
       on=Trigger(DamageApplied, _i_bloodied_it, "you bloody an enemy"))
def f1826(c: Cast) -> None:
    """"You **or** an ally" is a choice the scorer cannot weigh, so the
    bonus is laid on everybody -- each one is spent by its own next
    attack against that enemy, which comes to the same thing when only
    one of them takes the swing."""
    me, foe = c.me, c.trigger.target
    for who in [me, *(a for a in allies(c.world, me) if a != me)]:
        c.bonus(
            "damage", c.cha_mod, on=who, until=When.ENCOUNTER, once=True,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("f593", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RAGE)
def f593(c: Cast) -> None:
    """A damage bonus while raging. Rage is not a state anything holds
    -- the class's daily attack rows carry no keyword declaring it, which
    is the same gap `cf:barbarian-rage` has been waiting on."""


@power("f1720", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RAGE)
def f1720(c: Cast) -> None:
    """Extra radiant damage after spending a surge **while raging**.
    `SurgeSpent` is announced, so the trigger half is writable; the rage
    half is not, and half a gate would pay out every time."""


@power("f1009", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("cf:barbarian-f1s0",))
def f1009(c: Cast) -> None:
    """Raises the temporary hit points a class feature pays. Named in
    prose with no ref."""


@power("f1010", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.widen_area()",))
def f1010(c: Cast) -> None:
    """Grows a named power's burst and pays a damage bonus, both while
    raging. The area is header data read before the body runs, so
    nothing rewrites it for one use -- the same gap the wizard's f1134
    names."""
