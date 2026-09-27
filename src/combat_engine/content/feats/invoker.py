"""Invoker feats.

Two are ordinary keyword riders. The rest name a class feature or a
channelled power in prose, which is the same gap the warlord's list has
and carries the same symbol.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Hit,
    Keyword,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import distance_between

FEATURE = ("c.class_feature()",)


def _divine_hit_near(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.DIVINE in p.keywords
        and distance_between(world, me, ev.target) <= 3
    )


@power("f483", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy within 3 squares with an invoker power",
       on=Trigger(Hit, _divine_hit_near, "you hit somebody close"))
def f483(c: Cast) -> None:
    """"An invoker power" is read as a divine one: the engine has no
    per-class keyword, and every row this character casts that carries
    `DIVINE` is one of its own."""
    c.bonus(AC, 2, on=c.me, until=When.SONT, kind="feat")


@power("f1022", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Usage.on_power_used",))
def f1022(c: Cast) -> None:
    """A bonus to the next at-will after using an encounter or daily.
    The gate on *which* power earns it needs the usage of the row that
    fired, and `PowerUsed` carries the ref rather than the header -- so
    the bonus is written and the narrowing to an at-will is dropped."""
    c.bonus("attack", 1, on=c.me, until=When.EONT, kind="feat", once=True)


def _feature(ref: str, what: str) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=FEATURE)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} Named in prose with no ref."


_feature("f1012", "Temporary hit points riding on one covenant's power.")
_feature("f1491", "A defence bonus riding on the same covenant's power.")
_feature("f1079", "Vulnerability riding on a channelled power.")
_feature("f1488", "A damage type and a save penalty on the same power.")


@power("f1239", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.as_basic(ref)",))
def f1239(c: Cast) -> None:
    """Gives five named at-wills a melee reach and lets each be used as a
    basic attack. One of the five is named by ref and four are prose --
    but even for the one, nothing adds a reach to another row or makes
    it count as a basic."""
