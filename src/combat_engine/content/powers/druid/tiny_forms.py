"""Druid: the two utilities that add a shape to wild shape rather than take one.

Both print "until the end of the encounter, **you can use wild shape to
assume** the form of X", which is not the same sentence as the nine rows
that print "you assume the form of X". Nothing happens when the row is
used: it opens a door, and the door is `p5032`. So each of these arms a
hold for the fight and watches for the druid going into beast form while it
stands; the shape offered is the one this row describes, and declining it
leaves the ordinary beast form the class already had.

`p5051`'s second sentence -- "you can use wild shape to change among this
form, another beast form, and your humanoid form" -- needs no code:
`take_beast_form` already ends whichever shape was worn, and `p5032` is
already the way back out.

Neither form can attack, which is the only reason `c.cannot_attack` is
here; picking things up and manipulating objects are inventory, and the
engine has none.

**The door is watched by the form appearing, not by the row being used.**
`PowerUsed` is emitted before the body runs, so a watch on it answers
while the druid is still in whatever shape it was in -- and the dressing
would be hung on the form it is leaving. `EffectApplied` carrying the
form's own label is the moment the shape exists.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    DAILY,
    FREE,
    PERSONAL,
    SELF,
    Cast,
    Effect,
    Keyword,
    Powers,
    When,
    World,
    power,
)
from combat_engine.engine.events import EffectApplied

from .forms import BEAST, current_form, ends_with

#: The class's own shape-change, and the row these two hang off.
WILD_SHAPE = "p5032"

PRIMAL = [Keyword.PRIMAL]


def has_wild_shape(world: World, eid: int) -> bool:
    """"Prerequisite: You must have the wild shape power."""
    known = world.get(eid, Powers)
    return known is not None and WILD_SHAPE in known.known


def _offer(c: Cast, dress: Callable[[], tuple[Effect | None, ...]]) -> None:
    """Arm "you can use wild shape to assume the form of X" for the fight."""
    me = c.me
    if c.effect(c.ref, until=When.ENCOUNTER, on=me) is None:
        return

    def on_change(ev: EffectApplied) -> None:
        if ev.target != me or ev.label != BEAST:
            return
        shape = current_form(c)
        if shape is None or not c.may("take the smaller shape", who=me):
            return
        ends_with(c, shape, *dress())

    c.watch(EffectApplied, on_change, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p5046",
    level=2,
    cls="druid",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=has_wild_shape,
    requires_text="you must have the shape-change row",
)
def p5046(c: Cast) -> None:
    """A shape worth taking for the Stealth bonus and nothing else, which is
    what the card is: the rest of its Effect is what the shape cannot do."""
    _offer(
        c,
        lambda: (
            c.bonus("skill:stealth", 5, on=c.me, until=When.ENCOUNTER),
            c.cannot_attack(on=c.me, until=When.ENCOUNTER),
        ),
    )


@power(
    "p5051",
    level=6,
    cls="druid",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=has_wild_shape,
    requires_text="you must have the shape-change row",
)
def p5051(c: Cast) -> None:
    """"Your walking speed becomes 2" is a penalty rather than a setting --
    nothing assigns a speed -- so it is the difference, measured when the
    shape is taken."""
    speed = c.speed_of()
    _offer(
        c,
        lambda: (
            c.mode("fly", speed, on=c.me, until=When.ENCOUNTER),
            c.penalty("speed", max(0, speed - 2), on=c.me, until=When.ENCOUNTER),
            c.cannot_attack(on=c.me, until=When.ENCOUNTER),
        ),
    )
