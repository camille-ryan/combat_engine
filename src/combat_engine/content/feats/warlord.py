"""Warlord feats.

Almost the whole list is a rider on something the warlord already has,
and which of those things it is decides whether the row is writable.

**"When an ally spends an action point" is writable and there are five
of them.** `ActionPointSpent` is a real event and action points are
really spent now, so these are ordinary triggers.

**"Your Inspiring Word", "your Bravura Presence" are not.** Each is a
class feature named in prose with no ref -- which is exactly what the
opaque term in their own prerequisites is recording from the other
side. They carry `c.class_feature()`, the symbol the item waves settled
on for the same gap.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    NO_TARGET,
    PERSONAL,
    SELF,
    ActionPointSpent,
    ActionType,
    Cast,
    Hit,
    Keyword,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import distance_between, team

FEATURE = ("c.class_feature()",)


def _ally_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor != me and team(world, ev.actor) == team(world, me)


def _bow_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.components import Gear

    gear = world.get(me, Gear)
    p = get(ev.power)
    return (
        ev.attacker == me
        and gear is not None
        and gear.ranged is not None
        and gear.ranged.group == "bow"
        and p is not None
        and Keyword.WEAPON in p.keywords
    )


@power("f294", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally who can see you spends an action point",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f294(c: Cast) -> None:
    """A saving throw for the ally, at your Charisma rather than theirs --
    `c.save` follows `c.target`, and the row is declared with none, so
    the ally is named outright."""
    c.save(on=c.trigger.actor, bonus=c.cha_mod)


@power("f308", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally who can see you spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f308(c: Cast) -> None:
    """The bonus is to the damage of the attack the point bought, so it
    is spent on the first roll rather than left standing."""
    c.bonus("damage", c.int_mod, on=c.trigger.actor, until=When.EONT, once=True)


@power("f794", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally who can see you spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f794(c: Cast) -> None:
    """A plain "+1 bonus", so untyped."""
    c.bonus("attack", 1, on=c.trigger.actor, until=When.EONT, once=True)


@power("f779", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f779(c: Cast) -> None:
    """"Before or after the attack" is a choice with no way to express
    the ordering, and the point has already been spent by the time this
    is offered -- so the teleport happens now, which is "before"."""
    c.teleport(1, who=c.trigger.actor)


@power("f796", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with a bow attack",
       on=Trigger(Hit, _bow_hit, "you hit with a bow"))
def f796(c: Cast) -> None:
    """Allies within 10 who can see and hear you, against that one
    target, until the start of your next turn."""
    me, foe = c.me, c.trigger.target
    for friend in [a for a in team(c.world, me) if a != me]:
        if distance_between(c.world, me, friend) > 10:
            continue
        c.bonus(
            "attack", 1, on=friend, until=When.SONT,
            when=lambda ctx: (
                ctx.get("target") == foe and ctx.get("ranged", False)
            ),
        )


@power("f756", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Miss.advantage",))
def f756(c: Cast) -> None:
    """Turns on an enemy **missing** you while it has combat advantage.
    `Miss` carries no `advantage`, and the live `AttackResult` that does
    rides on `Hit` -- so the one event this row needs is the one that
    cannot answer the question."""


@power("f797", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_basic()",))
def f797(c: Cast) -> None:
    """A bonus on an attack granted by one of this character's own
    powers. A granted swing is announced as the row it is, not as a
    grant, so there is nothing to tell it from any other attack."""


def _feature(ref: str, what: str) -> None:
    """One of the rows riding on a class feature that has no ref."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=FEATURE)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} The feature is named in prose with no ref."


_feature("f218", "Adds Charisma to what one healing feature restores.")
_feature("f757", "A second benefit when that feature is used on a neighbour.")
_feature("f793", "A defence bonus riding on the same feature.")
_feature("f789", "Raises what one leader presence restores.")
_feature("f790", "Raises what a second leader presence pays.")
_feature("f791", "Raises what a third leader presence grants.")
_feature("f788", "A choice of two bonuses when a fourth presence is used.")
_feature("f759", "The same fourth presence, larger and gated on bloodied.")


@power("f765", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.obscure(level=)",))
def f765(c: Cast) -> None:
    """Softens a racial power's total concealment to partial. `c.conceal`
    grants concealment; nothing reaches into a standing zone and changes
    how thick it is."""
