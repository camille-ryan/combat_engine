"""Assassin feats.

Every one of these names its power by ref in its own prerequisite --
`has p9400`, `has p9402` -- so the class's shroud and its shade form
are both nameable.

I first marked three of them as waiting on `c.shrouds()` and
`c.reroll_damage()`, having guessed that neither existed. Both do, and
`scripts/todo.py` went red on the next run naming all three rows --
which is the whole reason that instrument fails on an arrived symbol
rather than merely listing it. The three are written.

What is genuinely missing is narrower: rewriting the *action* a named
row costs, and rerolling the ones on another row's damage dice.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    SELF,
    ActionPointSpent,
    ActionType,
    Bloodied,
    Cast,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import enemies


def _my_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


def _i_am_bloodied(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


@power("f1790", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you spend an action point",
       on=Trigger(ActionPointSpent, _my_point, "you spend an action point"))
def f1790(c: Cast) -> None:
    """Another shroud on whoever already carries one. `c.shroud` lays it
    and caps at the printed four, so nothing is counted here."""
    for foe in enemies(c.world, c.me):
        if c.shrouds(foe):
            c.shroud(on=foe)
            return


@power("f1788", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="the first time you are bloodied",
       on=Trigger(Bloodied, _i_am_bloodied, "you become bloodied"))
def f1788(c: Cast) -> None:
    """An enemy already carrying a shroud takes extra from the next
    attack. `usage=ENCOUNTER` is the printed "first time", so the body
    counts nothing itself."""
    me = c.me
    chosen = next((f for f in enemies(c.world, me) if c.shrouds(f)), None)
    if chosen is None:
        return
    c.bonus(
        "damage", c.dex_mod, on=me, until=When.EONT, once=True,
        when=lambda ctx: ctx.get("target") == chosen,
    )


@power("f1791", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1791(c: Cast) -> None:
    """`c.reroll_damage` is the printed sentence exactly -- roll twice,
    keep the higher -- and it takes the duration, so the row is one
    call."""
    c.reroll_damage(on=c.me, until=When.ENCOUNTER)


@power("f1786", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recost(p9402)",))
def f1786(c: Cast) -> None:
    """Changes what action a named row costs, to an immediate interrupt
    on taking damage. The action is header data, read by the menu before
    anything runs, and nothing rewrites it."""


@power("f1789", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reroll_ones()",))
def f1789(c: Cast) -> None:
    """Rerolls every 1 on one named row's damage dice. `c.reroll_damage`
    rolls the whole thing twice, which is a different and better
    outcome, so it is not a substitute. One implement block wants the
    same symbol."""


@power("f1787", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.restore_use(racial)",))
def f1787(c: Cast) -> None:
    """A second use of a racial power after missing a shrouded enemy.
    `c.restore_use` takes a ref and the shroud is readable -- what the
    spec does not give is the racial power's ref, so the row watches for
    nothing and the restore is dropped."""
