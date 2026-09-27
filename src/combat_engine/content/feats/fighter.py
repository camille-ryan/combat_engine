"""Fighter feats.

Three families, and two of them share one gap.

**"An attack granted by Combat Challenge."** Five rows turn on it. The
feature's ref is in their own prerequisite, so it is not a naming
problem -- the problem is that a granted basic attack is announced as
`mba` like any other, and nothing records who granted it. Marked
`c.on_granted_basic()`, the same symbol two general feats already name.

**The invigorating keyword.** Four rows turn on a keyword the engine
does not have, and `Keyword` is read off the enum so the gap is exact.

**The weapon-group riders** -- a hammer, a flail, an axe or a pick -- are
writable, because `Gear` carries the group and `c.wielding` asks. The
save-narrowing half of two of them is writable too, now that the saving
throw's context carries the conditions and the ongoing damage it is
against.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Condition,
    Dropped,
    Gear,
    Hit,
    Size,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import enemies, holding, team

#: The conditions a hammer or a mace is printed as making stick.
_STICKY = ("dazed", "immobilized", "slowed", "stunned")


def _i_crit_in_melee(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.dsl import get

    p = get(ev.power)
    return (
        ev.attacker == me
        and ev.critical
        and p is not None
        and p.reach.kind == "melee"
    )


def _i_killed_in_melee(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return getattr(ev, "source", None) == me


def _holding(c: Cast, *groups: str) -> bool:
    """Is the caster swinging one of these weapon groups?"""
    return any(holding(c.world, c.me, g) for g in groups)


@power("f364", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f364(c: Cast) -> None:
    """A penalty to the saves against the four conditions this weapon's
    blows are printed as making stick. The saving throw's context carries
    the conditions the effect holds, which is what makes the narrowing
    sayable rather than a blanket penalty on every save.

    The weapon is checked when the trait arms rather than per save: what
    is in hand at the top of the fight is what the feat is about, and the
    save happens on somebody else's turn when `c.me` is not swinging.
    """
    if not _holding(c, "hammer", "mace"):
        return
    for foe in enemies(c.world, c.me):
        c.penalty(
            "save", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx: any(
                str(x.value) in _STICKY for x in ctx.get("conditions", ())
            ),
        )


@power("f368", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a melee attack",
       on=Trigger(Hit, _i_crit_in_melee, "you crit in melee"))
def f368(c: Cast) -> None:
    """Against **that target's** attacks only, which the attack context
    reaches through `attacker`."""
    foe = c.trigger.target
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 2, on=c.me, until=When.EONT,
            when=lambda ctx: ctx.get("attacker") == foe,
        )


@power("f405", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reduce an enemy to 0 hit points with a melee attack",
       on=Trigger(Dropped, _i_killed_in_melee, "you drop an enemy"))
def f405(c: Cast) -> None:
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER)


@power("f407", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f407(c: Cast) -> None:
    """A surprised enemy is one that has not had its first turn, which
    `Condition.SURPRISED` holds -- the surprise round put it there."""
    c.bonus(
        "damage", 4, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and c.is_(Condition.SURPRISED, on=ctx["target"])
        ),
    )


@power("f416", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f416(c: Cast) -> None:
    """A charge against a target already giving you combat advantage. Both
    are keys the *attack* context carries; the damage context carries
    `charge` but not `advantage`, so the extra is a damage bonus gated on
    the charge and the advantage is read off the hit."""
    if not _holding(c, "light blade", "spear"):
        return
    c.bonus(
        "damage", c.roll(c.w(1)), on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("charge", False),
    )


@power("f772", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you knock an enemy prone with a flail",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me, "you hit"))
def f772(c: Cast) -> None:
    """Only when the blow actually put the target down, so the prone is
    checked after the fact rather than assumed from the hit."""
    if not _holding(c, "flail"):
        return
    foe = c.trigger.target
    if c.is_(Condition.PRONE, on=foe):
        c.slide(1, on=foe)


@power("f778", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f778(c: Cast) -> None:
    """Two blades of any mix. `Gear.two_weapon` is the printed question
    and already excludes a shield, which is the other half of it."""
    gear = c.world.get(c.me, Gear)
    if gear is None or not gear.two_weapon:
        return
    if all(w.group in ("light blade", "heavy blade") for w in gear.melee):
        c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER)


@power("f782", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f782(c: Cast) -> None:
    """**Allies**, not you. A mark is a relation, so the gate asks whether
    the creature being hit is one this character marked."""
    me = c.me
    for friend in [a for a in team(c.world, me) if a != me]:
        c.bonus(
            "damage", 1, on=friend, until=When.ENCOUNTER,
            when=lambda ctx: (
                ctx.get("target") is not None
                and c.marked(on=ctx["target"], by=me)
            ),
        )


@power("f402", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f402(c: Cast) -> None:
    """Large or larger, and marked by you: two questions the attack
    context can answer between `target` and the relation table."""
    me = c.me
    big = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and c.marked(on=ctx["target"], by=me)
            and c.size_of(ctx["target"]) in big
        ),
    )


# -- the two families that are waiting on something -------------------------


@power("f286", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_basic()",))
def f286(c: Cast) -> None:
    """A rider on the attack one class feature grants. The feature's ref
    is in this feat's own prerequisite, so it is not a naming problem --
    a granted basic is announced as `mba` like any other and nothing
    records who granted it."""


@power("f300", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_basic()",))
def f300(c: Cast) -> None:
    """Same shape as f286, paying damage rather than a penalty."""


@power("f306", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_basic()",))
def f306(c: Cast) -> None:
    """Same shape as f286, pushing rather than paying."""


@power("f771", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_basic()",))
def f771(c: Cast) -> None:
    """Same shape as f286, adding a modifier to the granted swing."""


@power("f755", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.INVIGORATING",))
def f755(c: Cast) -> None:
    """Turns on a keyword the engine does not have. `Keyword` is read off
    the enum, so the gap is exact rather than a judgement."""


@power("f758", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.INVIGORATING",))
def f758(c: Cast) -> None:
    """Same keyword, triggered by a racial power."""


@power("f774", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.INVIGORATING",))
def f774(c: Cast) -> None:
    """Same keyword, raising the temporary hit points it pays."""


@power("f792", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.INVIGORATING",))
def f792(c: Cast) -> None:
    """Same keyword, a smaller version of f774."""


@power("f371", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_second_wind()",))
def f371(c: Cast) -> None:
    """Second wind is an action rather than a power, so it announces
    nothing a trigger can answer."""


@power("f372", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_second_wind()",))
def f372(c: Cast) -> None:
    """Same gap as f371, paying an attack bonus rather than defences."""


@power("f769", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f769(c: Cast) -> None:
    """Untyped ongoing damage from an axe or a pick. The saving throw's
    context carries whether the effect is ongoing and what type it is, so
    "no damage type" is a real question rather than an approximation."""
    if not _holding(c, "axe", "pick"):
        return
    for foe in enemies(c.world, c.me):
        c.penalty(
            "save", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("ongoing") and ctx.get("dtype") is None,
        )
