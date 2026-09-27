"""Druid feats.

"While you are in beast form" is answered by the class itself:
`content/powers/druid/forms.py` labels the shape and exports
`in_beast_form(world, eid)`. Imported rather than re-derived, for the
same reason the avenger's `sworn` is -- two versions of the same
question are two chances to disagree, and this one is the version the
form itself uses.
"""

from __future__ import annotations

from combat_engine.content.powers.druid.forms import in_beast_form
from combat_engine.engine import (
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
from combat_engine.engine.dsl import get


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
       reach=PERSONAL, target=SELF, dropped=("resolve.dmg_ctx.advantage",))
def f555(c: Cast) -> None:
    """A damage bonus in beast form against anything granting combat
    advantage. The form half is written; the advantage half is dropped
    because the *damage* context carries no `advantage` -- only the
    attack context does -- and gating on a key it does not have would
    be silently false."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: in_beast_form(c.world, me),
    )


@power("f1822", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
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


@power("f1019", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reroll_initiative(on=)",))
def f1019(c: Cast) -> None:
    """Lets an **ally** reroll initiative. `c.reroll_initiative` takes an
    `on=` and would do it -- but the moment is "when you roll
    initiative", and initiative is rolled by `Encounter.start` before
    any trait has been armed."""


@power("f1770", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_revert()",))
def f1770(c: Cast) -> None:
    """Lengthens the shift taken when leaving beast form. `c.form` takes
    a `revert` action but announces nothing when the shape drops, so
    there is no moment to lengthen."""
