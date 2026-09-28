"""Druid feats.

"While you are in beast form" is answered by the class itself:
`content/powers/druid/forms.py` labels the shape and exports
`in_beast_form(world, eid)`. Imported rather than re-derived, for the
same reason the avenger's `sworn` is -- two versions of the same
question are two chances to disagree, and this one is the version the
form itself uses.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.druid.forms import in_beast_form
from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Keyword,
    PowerUsed,
    Trigger,
    When,
    power,
)
from combat_engine.engine.components import Initiative
from combat_engine.engine.dsl import get
from combat_engine.engine.events import InitiativeRolled
from combat_engine.engine.query import allies, distance_between
from combat_engine.engine.triggers import about_me


def _rolled(c: Cast):  # noqa: ANN202
    """How high an ally rolled. `Initiative.rolled` is the die plus its
    modifiers -- the number the order was sorted on."""

    def key(who: int) -> int:
        init = c.world.get(who, Initiative)
        return init.rolled if init is not None else 0

    return key


@power("f552", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f552(c: Cast) -> None:
    """A charge bonus while in beast form. Both halves are asked per
    attack: a druid changes shape mid-fight, which is the whole point of
    the class."""
    me = c.me
    shaped = lambda ctx: in_beast_form(c.world, me)  # noqa: E731
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: shaped(ctx) and ctx.get("charge", False))
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER,
            when=lambda ctx: shaped(ctx) and ctx.get("charge", False))


@power("f555", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f555(c: Cast) -> None:
    """A damage bonus in beast form against anything granting combat
    advantage.

    The advantage half used to be dropped: the damage context carried
    no `advantage` and only the attack context did. It carries one
    now, asked of the board at damage time -- see the note in
    `resolve.deal_damage` about what that costs on a one-shot grant.
    """
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            in_beast_form(c.world, me) and ctx.get("advantage", False)
        ),
    )


@power("f1822", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p5032 to take beast form",
       on=Trigger(PowerUsed, lambda w, me, ev: (
           ev.actor == me and ev.power == "p5032"
       ), "you wild shape"))
def f1822(c: Cast) -> None:
    """A shift on changing shape. `PowerUsed` fires **before** the body,
    so the form is not on yet -- which is right here, because the row
    shifts either way and does not read the shape."""
    c.shift(1)


@power("f1018", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1018(c: Cast) -> None:
    """A bonus against bloodied enemies with primal powers. Gated on the
    power's keyword and on the target, both of which the attack context
    carries."""
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.PRIMAL in p.keywords
            and c.bloodied(on=ctx.get("target"))
        ),
    )


@power("f1019", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you roll initiative",
       on=Trigger(InitiativeRolled, about_me, "you roll initiative"))
def f1019(c: Cast) -> None:
    """Lets an **ally** within 5 reroll initiative.

    I first marked this as waiting, reasoning that traits are armed after
    the opening rolls. They are -- but a row with a printed trigger is
    not armed as a trait: `triggers.arm` subscribes from the registry and
    `Encounter.start` calls it *before* `_roll_initiative`, on purpose.
    Eighteen power rows already answer this event.

    The lowest roller is the one who wants a second chance.
    """
    me = c.me
    near = [
        a for a in allies(c.world, me)
        if a != me and distance_between(c.world, me, a) <= 5
    ]
    if not near:
        return
    slowest = min(near, key=_rolled(c))
    c.reroll_initiative(on=slowest)


def _reverting(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """`p5032` being used to *drop* the shape rather than take it.

    One row, both directions -- so the direction is read off the board,
    and `PowerUsed` fires before the body, which is the one window in
    which the druid is still shaped.
    """
    return ev.actor == me and ev.power == "p5032" and in_beast_form(world, me)


@power("f1770", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p5032 to leave beast form",
       on=Trigger(PowerUsed, _reverting, "you drop the shape"))
def f1770(c: Cast) -> None:
    """Shift 2 squares instead of 1 on leaving beast form.

    Re-read: `c.form` does announce the shape dropping -- `Effects.end`
    emits a `ConditionEnded` per condition and an `EffectExpired` -- but
    none of that is needed here, because the shift this lengthens is
    `p5032`'s own and the row that takes it is the moment. The extra
    square is taken before `p5032`'s, which is the same two squares of
    displacement either way.
    """
    c.shift(1)
