"""Wizard feats.

Almost all of these gate on a *keyword* rather than on a named row,
which is the cheapest gate there is: the attack context carries the
power's ref and `dsl.get` reads its keywords off the header. So
"whenever you use an arcane illusion power" is a one-line lambda where
the same sentence about a class feature would be a marker.

The exception is the two that reach into another row's shape -- growing
a blast, borrowing a weapon as an implement -- and both say so.
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
    Keyword,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get

#: The five the card lists. Read here rather than inline so the two rows
#: that want them cannot drift apart.
_ELEMENTAL = (
    Keyword.ACID, Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING,
    Keyword.THUNDER,
)


def _has(ctx: dict, *words: Keyword) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and any(w in p.keywords for w in words)


def _illusion_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.ILLUSION in p.keywords
        and Keyword.ARCANE in p.keywords
    )


@power("f682", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.grants_advantage(until_save=)",),
       trigger="you hit with an arcane illusion power",
       on=Trigger(Hit, _illusion_hit, "you hit with an illusion"))
def f682(c: Cast) -> None:
    """Combat advantage against what an illusion hit. The longer form --
    "until it saves, if the power has a save-ends effect" -- needs a
    duration that ends on a *particular* effect's save, which `When` has
    no member for; the end-of-next-turn form is written."""
    c.grants_advantage(on=c.trigger.target, until=When.EONT)


@power("f1140", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1140(c: Cast) -> None:
    """A feat bonus on every arcane illusion power, attack and damage
    both. The later steps are out of scope."""
    me = c.me
    for what in ("attack", "damage"):
        c.bonus(
            what, 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: _has(ctx, Keyword.ILLUSION),
        )


@power("f1132", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1132(c: Cast) -> None:
    """Strength to the damage of five elemental keywords. Gated on the
    *power's* keywords rather than on the damage type, which is what the
    card says -- a fire power that happens to deal untyped damage still
    counts."""
    c.bonus(
        "damage", c.str_mod, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _has(ctx, *_ELEMENTAL),
    )


@power("f677", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.summoned_by_me()",))
def f677(c: Cast) -> None:
    """A defence bonus for creatures this wizard has summoned. `c.summon`
    puts one on the board and `Summoned` announces it, but nothing keeps
    a list of whose summons are whose after the fact."""


@power("f1123", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.hit_count()",))
def f1123(c: Cast) -> None:
    """A damage bonus when one power hits two or more creatures. `Hit` is
    announced per target and the damage for each is rolled as it goes,
    so by the time the second hit is known the first has already been
    paid."""


@power("f1134", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.widen_area()",))
def f1134(c: Cast) -> None:
    """Trades damage for a larger blast or burst. The area is header
    data, read before the body runs so the interface can draw it, and
    nothing rewrites it for one use."""


@power("f1128", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.counts_as(group=)",))
def f1128(c: Cast) -> None:
    """Lets one weapon be an implement for this class, with its
    enhancement but not its proficiency. `c.as_implement` rewrites the
    group outright, which would hand over the proficiency too -- the
    printed line is narrower than the verb. Same symbol the rogue's
    f799 wants."""


@power("f276", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f276(c: Cast) -> None:
    """More spells in the spellbook. `Powers.owned` is the book and
    `chargen.spellbook` fills it, so this is a build-time number rather
    than anything that happens in a fight."""
