"""Ranger feats.

The class's two halves split this list almost exactly in two.

**The quarry half is writable.** `cf:ranger-f1` is named by ref in every
one of their prerequisites, `c.quarry` lays the relation and
`world.relations.holds` reads it back, so "against the target of your
quarry" is a real question.

**The beast half is not, and all of it is waiting on one thing.** Ten
rows here gate on a class feature the engine does not have -- their
prerequisites all carry the same opaque term, which is the same gap
`docs/blocked.json` records as `cf:ranger-style-beast`. Marked
`c.beast()`, one symbol, so the day a beast companion exists
`scripts/todo.py` names every row that was waiting for it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Hit,
    Relation,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import team

BEAST = ("c.beast()",)


def _is_my_quarry(c: Cast, who: int | None) -> bool:
    """Is that creature the one this ranger has marked as its quarry?

    `c.quarry` lays `Relation.QUARRY_OF` from the ranger to the target,
    and the relation table is the only thing that remembers it -- there
    is no condition and no effect label to match on.
    """
    return who is not None and c.world.relations.holds(
        Relation.QUARRY_OF, c.me, who
    )


def _crit_on_quarry(kind: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        p = get(ev.power)
        return (
            ev.attacker == me
            and ev.critical
            and p is not None
            and (p.reach.kind == kind or (kind == "ranged" and p.reach.alt))
            and world.relations.holds(Relation.QUARRY_OF, me, ev.target)
        )

    return when


@power("f280", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit your quarry with a melee attack",
       on=Trigger(Hit, _crit_on_quarry("melee"), "you crit your quarry"))
def f280(c: Cast) -> None:
    """A free shift and a penalty on that enemy's attacks **against
    you**, which the attack context reaches through `attacker`."""
    me = c.me
    c.shift(1)
    c.penalty(
        "attack", 2, on=c.trigger.target, until=When.EONT,
        when=lambda ctx: ctx.get("target") == me,
    )


@power("f301", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit your quarry with a ranged attack",
       on=Trigger(Hit, _crit_on_quarry("ranged"), "you crit your quarry"))
def f301(c: Cast) -> None:
    """Your **allies**, not you."""
    me = c.me
    foe = c.trigger.target
    for friend in [a for a in team(c.world, me) if a != me]:
        c.bonus(
            "attack", 1, on=friend, until=When.SONT,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("f783", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f783(c: Cast) -> None:
    """Allies deal more to whatever this ranger has marked. Read off the
    relation each time rather than fixed at arming, because the quarry
    moves from creature to creature over a fight."""
    me = c.me
    for friend in [a for a in team(c.world, me) if a != me]:
        c.bonus(
            "damage", 1, on=friend, until=When.ENCOUNTER,
            when=lambda ctx: _is_my_quarry(c, ctx.get("target")),
        )


@power("f761", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_reroll()",))
def f761(c: Cast) -> None:
    """Extra damage when a reroll granted by one racial power lands on
    the quarry. The quarry half is written as a standing damage bonus;
    what is dropped is the narrowing to *rerolled* attacks, because
    nothing announces that a roll was a reroll."""
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _is_my_quarry(c, ctx.get("target")),
    )


@power("f273", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f273(c: Cast) -> None:
    """Raises the die another row rolls, from d6 to d8. The dice are a
    string inside that row's body and nothing reaches in."""


@power("f786", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_move()",))
def f786(c: Cast) -> None:
    """Adds two squares to the distance two named racial powers move you.
    Both are named by ref, so this is not a naming gap -- nothing adds to
    the distance a *particular* row moves."""


@power("f764", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f764(c: Cast) -> None:
    """A Stealth bonus with cover outdoors. The engine has no outdoors."""


@power("f777", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f777(c: Cast) -> None:
    """Finding and hiding tracks. Not a fight."""


# -- everything waiting on the beast companion ------------------------------


def _beast(ref: str, what: str) -> None:
    """One of the ten rows that need a beast companion on the board."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=BEAST)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} There is no beast companion to do it to."


_beast("f752", "A skill bonus for the companion.")
_beast("f753", "An opportunity attack when the companion is struck.")
_beast("f754", "Skill training for the companion.")
_beast("f760", "A resistance for the companion, keyed to a racial power.")
_beast("f766", "A damage bonus when the companion flanks your target.")
_beast("f773", "The companion is immune to your own racial power.")
_beast("f776", "The companion ignores difficult terrain when it shifts.")
_beast("f780", "The companion changes origin and teleports with you.")
_beast("f781", "Fire resistance for the companion.")
_beast("f785", "A defence bonus for the companion.")
