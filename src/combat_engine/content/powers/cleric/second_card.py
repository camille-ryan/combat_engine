"""Cleric: the second stat block printed beside `p14293`.

A No Action burst that the parent's Effect line orders up -- "make the
secondary attack". Nothing in a body can use another row, so the order is
read as what it is: a trigger on the parent finishing. `PowerResolved` and
not `PowerUsed`, because the latter is announced before the parent's body
runs and the secondary is printed after the primary swing.

No `group=`: the channel divinity budget is one use for the whole card and
the parent carries it. Declared here it would refuse this half every time,
its own sibling having just been spent.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.events import PowerResolved


def _finished(ref: str):  # noqa: ANN202
    def check(world: World, me: int, ev: PowerResolved) -> bool:
        return ev.actor == me and ev.power == ref

    return check


@power(
    "p14293b",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE, Keyword.WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=WILL),
    trigger="you make the p14293 attack",
    on=Trigger(PowerResolved, _finished("p14293"), "you use the p14293 power"),
)
def p14293b(c: Cast) -> None:
    """The primary target is read off the triggering event. Fired on its own
    there is none to leave out, which is the honest reading of a burst with
    no primary attack in front of it."""
    foe = c.target
    if foe is None or not c.is_kind("undead", on=foe):
        return
    if foe in getattr(c.trigger, "targets", ()):
        return
    if c.strike():
        c.damage(0, c.cha_mod, dtype=DamageType.RADIANT)
        c.push(3 + c.cha_mod)
