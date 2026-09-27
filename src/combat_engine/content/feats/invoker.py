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
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Hit,
    Keyword,
    PowerUsed,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import distance_between

#: The two covenant cards are declared rows now -- `cf:invoker-f1c0` and
#: `cf:invoker-f1c1` -- so none of these is a naming gap any more. What a
#: rider still cannot read is the event the card was used *against*: each
#: card picks the ally or the enemy off its own `c.trigger`, and
#: `PowerUsed` carries actor, power and targets and nothing else.
TRIGGER = ("PowerUsed.trigger",)

_DEFENCES = (AC, FORT, REF, WILL)


def _from_bloodied(c: Cast):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.bloodied(who)

    return gate


def _used_card(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "cf:invoker-f1c0"


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


def _feature(ref: str, what: str, todo: tuple[str, ...] = TRIGGER) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=todo)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = (
        f"{what} The card has a ref now; what it has not got is the "
        "triggering event, which is where the creature this names is picked."
    )


_feature("f1012", "Temporary hit points riding on one covenant's power.")
_feature("f1079", "Vulnerability riding on a channelled power.")
_feature("f1488", "A damage type and a save penalty on the same power.",
         todo=("c.deals(ref=)", *TRIGGER))


@power("f1491", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c0",
       on=Trigger(PowerUsed, _used_card, "you use that covenant's card"))
def f1491(c: Cast) -> None:
    """The one rider on that card that never needs the card's own trigger:
    the bonus lands on the caster's neighbours rather than on anybody the
    card picked, so `PowerUsed` alone says enough.

    "Against attacks made by bloodied creatures" is a gate on the *defence*
    context, which carries `attacker`. The damage context does not; this is
    a defence, and that side is the rich one.

    A plain "+1 bonus" with no type word printed, so untyped.
    """
    for friend in c.within(2, side="ally"):
        for defence in _DEFENCES:
            c.bonus(defence, 1, until=When.ENCOUNTER, on=friend,
                    when=_from_bloodied(c))


@power("f1239", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.as_melee(ref)",))
def f1239(c: Cast) -> None:
    """Gives five named at-wills a melee reach **and** lets each be used
    as a melee basic attack. Only the second half is sayable now.

    Re-aimed rather than half-written: the reach is what makes the
    swap mean anything, and `c.as_basic` on a row that is still ranged
    only would offer a bow shot where the game hands out a melee basic.
    `c.as_ranged` is the verb this wants the mirror of. Four of the five
    rows arrive as prose in any case, so p3705 is the whole of what
    could be written even with the reach."""
