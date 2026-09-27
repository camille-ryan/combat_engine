"""Sorcerer feats.

Four of the six gate on the class's own at-wills, which is a keyword
question and therefore cheap. The two that are not turn on a soul --
one of the class's build forks -- and neither the fork nor the damage
type it picks is recorded anywhere a row can read.
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
    Hit,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.types import Usage


def _my_at_will_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.attacker == me and p is not None and p.usage is Usage.AT_WILL


@power("f998", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a sorcerer at-will attack power",
       on=Trigger(Hit, _my_at_will_hit, "you hit with an at-will"))
def f998(c: Cast) -> None:
    """Against **that** enemy only, until the end of your next turn."""
    foe = c.trigger.target
    c.bonus(
        "attack", 1, on=c.me, until=When.EONT,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power("f1028", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reach_of(power=)",))
def f1028(c: Cast) -> None:
    """Turns a ranged power into a melee one when cast through a named
    weapon group. A power's reach is header data, read before the body
    runs so the interface can draw it, and nothing rewrites it for one
    use -- the same gap the wizard's f1134 names from the other side."""


@power("f1138", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.hit_count()",))
def f1138(c: Cast) -> None:
    """A bonus after an at-will hits two or more enemies. `Hit` is
    announced per target and damage is rolled as it goes, so by the time
    the second is known the first is already paid. The wizard's f1123
    wants the same count."""


@power("f1155", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.hit_count()",))
def f1155(c: Cast) -> None:
    """The other side of f1138: a bonus after an at-will hits exactly
    one. Same count, same gap."""


@power("f1001", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("cf:sorcerer-f0s3",))
def f1001(c: Cast) -> None:
    """Two rolls for the damage type one source rolls at an extended
    rest. The source has a ref and no row, so there is no roll to make
    twice."""


@power("f1008", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("cf:sorcerer-f0s1",))
def f1008(c: Cast) -> None:
    """+2 to the resistance one source grants. The source has a ref and
    no row: resistances of a type do not add, so laying a second one from
    here would replace the feature rather than raise it."""
