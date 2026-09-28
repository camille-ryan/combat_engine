"""Cleric feats.

The useful thing about this list is that most of its prerequisites name
the power the feat rides on **by ref** -- `has p1455`, `has p7885`. So
"when you use your healing word" is not a naming gap at all: it is
`Trigger(PowerUsed, ...)` against a ref the brief handed over, and five
rows that would otherwise be unwritable simply work.

`PowerUsed` is announced before the body runs, which is right here --
every one of these pays out *alongside* the power rather than reading
what it did.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Health,
    Miss,
    PowerUsed,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import allies, distance_between


def _i_used(ref: str):  # noqa: ANN202
    """You used that one row, named by its ref."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


@power("f1495", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1455",
       on=Trigger(PowerUsed, _i_used("p1455"), "you use p1455"))
def f1495(c: Cast) -> None:
    """**You** regain the hit points, not the target."""
    c.heal(c.str_mod, on=c.me)


@power("f1508", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1455",
       on=Trigger(PowerUsed, _i_used("p1455"), "you use p1455"))
def f1508(c: Cast) -> None:
    """The target of that power, which `PowerUsed` carries -- targets are
    chosen before the body runs, so `ev.targets` is trustworthy here
    even though what the body *does* is not yet."""
    for who in c.trigger.targets:
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, c.cha_mod, on=who, until=When.EONT,
                    kind="power", once=True)


@power("f1507", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7885",
       on=Trigger(PowerUsed, _i_used("p7885"), "you use p7885"))
def f1507(c: Cast) -> None:
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, c.cha_mod, on=c.me, until=When.EONT, kind="power")


@power("f1499", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1450 and the attack hits",
       on=Trigger(PowerUsed, _i_used("p1450"), "you use p1450"))
def f1499(c: Cast) -> None:
    """One ally within 5 spends a surge. Which ally is a choice the
    scorer cannot weigh, so the most hurt one is taken -- that is what
    the sentence is for."""
    near = [
        a for a in allies(c.world, c.me)
        if distance_between(c.world, c.me, a) <= 5
    ]
    if near:
        c.surge(on=min(near, key=lambda a: c.world.get(a, Health).hp))


@power("f1505", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_ally_hit()",))
def f1505(c: Cast) -> None:
    """Temporary hit points for **any ally** that hits an enemy under a
    named racial power's effect. The power is named by ref; what is
    missing is a trigger on somebody else's hit that reads which effect
    the target is carrying."""


@power("f1498", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1452 and the attack misses",
       on=Trigger(PowerUsed, _i_used("p1452"), "you use p1452"))
def f1498(c: Cast) -> None:
    """The miss is the enemy's attack failing rather than this power's
    own, so it carries the enemy's ref and cannot be gated on p1452.
    `PowerUsed` fires before the body -- before the reroll -- so a
    one-shot watcher armed here is on the attack the racial power was
    answering. The ally is the most hurt one within 5, as f1499 picks."""
    me = c.me

    def missed(ev: Any) -> None:
        if ev.target != me:
            return
        near = [
            a for a in allies(c.world, me)
            if distance_between(c.world, me, a) <= 5
        ]
        if near:
            c.surge(on=min(near, key=lambda a: c.world.get(a, Health).hp))

    c.watch(Miss, missed, on=me, until=When.EOT, once=True)


@power("f1500", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retarget(power=)",))
def f1500(c: Cast) -> None:
    """Narrows a racial power's blast to enemies only and pays its allies
    temporary hit points. Nothing rewrites another row's target line."""


@power("f1087", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_power_bonus()",))
def f1087(c: Cast) -> None:
    """Re-aimed. `p1589` is a ref now, so the naming gap this waited on is
    closed and was never the whole of it: what the row asks is whether
    *this* attack is the one that spent that row's `once=True` attack
    bonus, and a bonus being laid or consumed announces nothing. `Mods`
    records the number and its kind, not the act. Same hold as f2074."""


def _p146_damage(ctx: dict[str, Any]) -> bool:
    """Damage stamped by p146, including the "(half)" a miss carries."""
    ref = str(ctx.get("power") or "")
    return ref == "p146" or ref.startswith("p146 ")


@power("f1089", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1089(c: Cast) -> None:
    """A trait: the row prints no trigger of its own, so `c.watch` carries
    the rider and the row is armed once.

    `Miss` is announced inside `c.strike()`, above the body's miss branch,
    so the suppression laid here is in place before any miss damage is
    dealt. `deal_damage` stamps half damage as `"<ref> (half)"`, which is
    why the gate accepts that form as well as the bare ref. The
    immobilisation is p146's *hit* line and never reaches a miss.
    """
    me = c.me

    def missed(ev: Miss) -> None:
        if ev.attacker != me or ev.power != "p146":
            return
        c.bonus("no_miss_damage", 1, on=ev.target, until=When.EOT,
                when=_p146_damage)
        c.push(c.cha_mod, on=ev.target)

    c.watch(Miss, missed, until=When.ENCOUNTER)
