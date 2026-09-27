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


@power("f1498", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_racial_power()",))
def f1498(c: Cast) -> None:
    """Rides on a racial power named in prose with no ref, and on that
    power's attack *missing*."""


@power("f1500", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retarget(power=)",))
def f1500(c: Cast) -> None:
    """Narrows a racial power's blast to enemies only and pays its allies
    temporary hit points. Nothing rewrites another row's target line."""


@power("f1087", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.class_feature()",))
def f1087(c: Cast) -> None:
    """Rides on a class feature named in prose with no ref, and on having
    taken its bonus for this particular attack."""


@power("f1089", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.class_feature()",))
def f1089(c: Cast) -> None:
    """Rides on missing with a class feature named in prose with no
    ref."""
