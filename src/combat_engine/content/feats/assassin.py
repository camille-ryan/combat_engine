"""Assassin feats.

Every one of these names its power by ref in its own prerequisite --
`has p9400`, `has p9402` -- so the class's shroud and its shade form
are both nameable.

I first marked three of them as waiting on `c.shrouds()` and
`c.reroll_damage()`, having guessed that neither existed. Both do, and
`scripts/todo.py` went red on the next run naming all three rows --
which is the whole reason that instrument fails on an arrived symbol
rather than merely listing it. The three are written.

What is genuinely missing is narrower still: rerolling the ones on
another row's damage dice. Two more were re-aimed off the same
mistake -- a feat that says "you can use X as an immediate interrupt"
does not need the engine to rewrite X's printed cost, because the feat
is itself a row and `c.use_power` fires X from inside it.
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
    DamageRolled,
    Miss,
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


def _hurts_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.target == me and ev.amount > 0


@power("f1786", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=NO_TARGET,
       trigger="you take damage",
       on=Trigger(DamageRolled, _hurts_me, "an attack damages you"))
def f1786(c: Cast) -> None:
    """Lets a named row be used as an immediate interrupt when you take
    damage.

    Rewriting a row's printed action was the wrong thing to want: the
    cost is header data and the menu reads it before anything runs. The
    feat does not have to change it -- this row **is** the interrupt, and
    `c.use_power` fires p9402 from inside it. p9402's own use is spent,
    which is the card: a new way in, not a second copy.

    `usage=AT_WILL` because the card prints no limit of its own; the
    limit is whatever p9402 costs.
    """
    c.use_power("p9402")


@power("f1789", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, )
def f1789(c: Cast) -> None:
    """Rerolls every 1 on one named row's damage dice.

    `c.reroll_damage` is **not** this: it rolls the whole expression twice
    and keeps the higher, which is a different and better outcome. Here each
    1 is replaced on its own and the dice that were fine keep their faces.

    Scoped by ref, so it is that row's damage and nothing else the character
    rolls.
    """
    c.reroll_ones(ref="p9400")
def _missed_with(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


@power("f1787", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you miss with p9400",
       on=Trigger(Miss, _missed_with("p9400"), "you miss with that power"))
def f1787(c: Cast) -> None:
    """A second use of a racial power after missing with p9400.

    The spec names the racial power by ref now, which is the whole of
    what was dropped -- and the clause is not a restore after all:
    "even if you have already used it" is `again=True`, which waives the
    usage limit for this one use without handing the row's own use back.
    `usage=ENCOUNTER` is the printed "once per encounter".
    """
    c.use_power("p1628", on=c.trigger.target, again=True)
