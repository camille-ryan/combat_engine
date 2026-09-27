"""Paladin feats.

Three of these name the power they ride on **by ref** in their own
prerequisite, so they are ordinary `PowerUsed` riders. The rest wait on
a class feature that has none.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    Ability,
    ActionType,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    PowerUsed,
    Trigger,
    When,
    power,
)


def _i_used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


@power("f290", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1566",
       on=Trigger(PowerUsed, _i_used("p1566"), "you use p1566"))
def f290(c: Cast) -> None:
    """Extra hit points for whoever that power was aimed at. `ev.targets`
    is trustworthy on `PowerUsed` -- targets are chosen before the body
    runs, even though what the body does is not yet known."""
    for who in c.trigger.targets:
        c.heal(c.cha_mod, on=who)


@power("f1512", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Health.max_surges",))
def f1512(c: Cast) -> None:
    """The healing half rides on the same ref as f290. The other half --
    one more healing surge a day -- raises a maximum, and `c.regain_surge`
    refills the pool without lifting its ceiling."""
    c.grant_row("f290", on=c.me, until=When.ENCOUNTER)


@power("f1086", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_mark()",))
def f1086(c: Cast) -> None:
    """Radiant damage when this character marks an undead creature. The
    feature is named by ref in the prerequisite, but a mark is laid by
    `c.mark` inside somebody's body and nothing announces one."""


@power("f1091", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1091(c: Cast) -> None:
    c.grant_row("f1091b", on=c.me, until=When.ENCOUNTER)


@power("f1091b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
       attack=Attack(Ability.CHA, vs=REF))
def f1091b(c: Cast) -> None:
    """A surge spent for damage rather than healing, so `c.spend_surge`
    and not `c.surge` -- the second would heal the caster, which is the
    one thing the card says does not happen."""
    if not c.is_kind("undead"):
        return
    if c.strike().hit and c.spend_surge(on=c.me):
        c.flat(c.surge_value(), dtype=DamageType.RADIANT)


@power("f1088", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_save()",))
def f1088(c: Cast) -> None:
    """Pays out when the target of a named power **succeeds** on a save
    against a necrotic effect. `SavingThrow` is announced and read back,
    but it is announced for the creature saving rather than for whoever
    laid the effect, so this character is not told."""


@power("f1497", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2483 or p2484",
       on=(
           Trigger(PowerUsed, _i_used("p2483"), "you use p2483"),
           Trigger(PowerUsed, _i_used("p2484"), "you use p2484"),
       ))
def f1497(c: Cast) -> None:
    """Both racial powers are named by ref, so both halves of the printed
    "or" are declared -- `on=` takes a sequence and declaring one of two
    looks finished."""
    c.bonus(
        "damage", c.wis_mod, on=c.me, until=When.EONT,
        when=lambda ctx: not ctx.get("ranged", False),
    )


@power("f1502", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_feature_power()",))
def f1502(c: Cast) -> None:
    """Rides on using a power of one named class feature -- the feature
    has a ref, but which rows *belong* to it is not recorded anywhere,
    so there is no set to watch for."""
