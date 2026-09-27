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
    PowerResolved,
    PowerUsed,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import distance_between

_DEFENCES = (AC, FORT, REF, WILL)


def _from_bloodied(c: Cast):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.bloodied(who)

    return gate


def _used_card(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "cf:invoker-f1c0"


def _used_card_b(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "cf:invoker-f1c1"


def _struck(ev: Any) -> int | None:
    """The ally `cf:invoker-f1c0` answered for.

    That card is `NO_TARGET` and reads the pair off its own trigger, so
    `PowerUsed.targets` is empty and the ally lives one event down:
    `ev.trigger` is the `Hit`, whose `target` is the ally and whose
    `attacker` is the enemy.
    """
    return getattr(getattr(ev, "trigger", None), "target", None)


def _striker(ev: Any) -> int | None:
    """The enemy off a covenant card's trigger.

    `cf:invoker-f1c1` declares `target=ONE_CREATURE` and then aims at
    this creature with `on=`, so its `PowerUsed.targets` names whoever
    the burst happened to pick and never the one the card burned.
    """
    return getattr(getattr(ev, "trigger", None), "attacker", None)


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


@power("f1012", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c0",
       on=Trigger(PowerUsed, _used_card, "you use that covenant's card"))
def f1012(c: Cast) -> None:
    """"One ally hit by the triggering attack" is the ally that card was
    played for, and the card names exactly one, so the choice printed
    here has a single option."""
    ally = _struck(c.trigger)
    if ally is not None:
        c.temp_hp(3 + c.int_mod, on=ally)


@power("f1079", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c1",
       on=Trigger(PowerResolved, _used_card_b, "you use that covenant's card"))
def f1079(c: Cast) -> None:
    """On the resolution rather than the use: the printed line is
    vulnerability to all *other* damage, and `PowerUsed` fires before the
    card's own radiant hit, which would then be taken at +2."""
    foe = _striker(c.trigger)
    if foe is not None:
        c.vulnerable(2, on=foe, until=When.EONT)


@power("f1488", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.deals(ref=)",),
       trigger="you use cf:invoker-f1c1",
       on=Trigger(PowerUsed, _used_card_b, "you use that covenant's card"))
def f1488(c: Cast) -> None:
    """The save penalty is written; the damage type is dropped. `c.deals`
    rewrites what *this creature's* attacks deal for a duration, and the
    printed line rewrites one named row's line for good."""
    foe = _striker(c.trigger)
    if foe is not None:
        c.penalty("save", 1, on=foe, until=When.EONT)


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
