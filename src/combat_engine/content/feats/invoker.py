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
    DamageType,
    Hit,
    Keyword,
    PowerResolved,
    PowerUsed,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import Melee, get
from combat_engine.engine.query import distance_between
from combat_engine.engine.types import Usage

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


def _bigger_divine(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A divine encounter or daily attack power, used on your own turn."""
    p = get(ev.power)
    return (
        ev.actor == me
        and world.turn == me
        and p is not None
        and Keyword.DIVINE in p.keywords
        and p.usage in (Usage.ENCOUNTER, Usage.DAILY)
        and (p.attack is not None or p.attack_alt is not None)
    )


def _at_will_divine(ctx: dict[str, Any]) -> bool:
    p = get(str(ctx.get("power") or ""))
    return (
        p is not None
        and Keyword.DIVINE in p.keywords
        and p.usage is Usage.AT_WILL
    )


@power("f1022", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a divine encounter or daily attack power on your turn",
       on=Trigger(PowerUsed, _bigger_divine, "you spend a bigger divine power"))
def f1022(c: Cast) -> None:
    """A bonus to the next at-will after spending an encounter or daily.

    Re-read: `PowerUsed` does carry only the ref, and `dsl.get` turns a
    ref into the declared row -- whose `usage`, `keywords` and `attack`
    are all header fields. So `Usage.on_power_used` named a lookup that
    already worked, on both sides of the row: the earning half is now a
    declared trigger rather than a standing bonus that any power bought,
    and the spending half is a gate on the attack context.

    It was also written as a trait laying a modifier flat, which is the
    printed trigger going nowhere -- a row holds one or the other.
    """
    c.bonus("attack", 1, on=c.me, until=When.EONT, kind="feat", once=True,
            when=_at_will_divine)


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
       reach=PERSONAL, target=SELF,
       trigger="you use cf:invoker-f1c1",
       on=Trigger(PowerUsed, _used_card_b, "you use that covenant's card"))
def f1488(c: Cast) -> None:
    """Written. Three clauses: the retype, the keyword, and the save
    penalty that was already here.

    "Deals fire **and** radiant damage" is `c.deals(dtypes=)` -- one blow
    of two types, which the target resists only as far as it resists both.
    `ref=` names the one card it speaks for, and that narrowing is what
    makes it safe to lay on a creature at all: without it the retype would
    recolour everything the invoker does.

    **The keyword comes with it, not after it.** "Gains the fire keyword"
    is `c.counts_as_keyword`, and shipping the retype without it would be a
    card that reads fire and deals none -- or the reverse, which is worse,
    since a fire-keyword gate elsewhere would pay on radiant damage.

    **Laid on the trigger although the clause is standing, and that is
    sound here rather than a compromise.** The card states a permanent
    property of one power, and a declared `on=` means this body runs only
    when the trigger fires -- but the trigger *is* the use of that very
    power, and `PowerUsed` is announced before the card's damage rolls.
    `f1079` beside this uses `PowerResolved` for the opposite reason and
    says so. So the retype is in place for every roll it could speak for,
    and there is no moment at which the card is used without it."""
    c.deals(
        dtypes=(DamageType.FIRE, DamageType.RADIANT),
        ref="cf:invoker-f1c1", on=c.me, until=When.ENCOUNTER,
    )
    c.counts_as_keyword(
        "cf:invoker-f1c1", Keyword.FIRE, on=c.me, until=When.ENCOUNTER,
    )
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


#: The five at-wills this feat names, one per class that can take it. Every
#: clause on the card is identical: a melee reach **in addition to** the
#: printed one, and the row usable as a melee basic attack.
_TOUCHED = ("p2847", "p5259", "p3705", "p1333", "p463")


@power("f1239", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1239(c: Cast) -> None:
    """Written, both halves, for all five rows.

    The note here said only the basic-attack half was sayable, and that
    "four of the five rows arrive as prose in any case, so `p3705` is the
    whole of what could be written". **Both halves of that are now false.**
    All five arrive as refs -- the card lists `p2847`, `p5259`, `p3705`,
    `p1333` and `p463`, one per class that may take the feat -- and the
    reach half landed as `dsl.branches_for`. #614.

    **"In addition to its normal range" is the card saying `optional=`
    out loud.** This is the clearest of the eleven: the printed ranged
    aiming stays, and a melee one joins it. A replacement would have taken
    the ranged aiming away from an at-will the character leans on.

    `Melee(1)` and not `by_weapon=True`: the card prints melee *touch*,
    which is reach 1 for anybody and is not the wielded weapon's reach.

    The reach is why `c.as_basic` means anything here, which is what the
    old note was right about -- offering a still-ranged row as a melee
    basic would hand out a bow shot where the game asks for a swing. Both
    go on together or neither does.

    Ungated by class: a character may only know the row its own class
    grants, and a reshape on a row nobody knows is never consulted.
    """
    for ref in _TOUCHED:
        c.reshape_area(
            lambda _r: Melee(1),
            ref=ref,
            optional=True,
            on=c.me,
            until=When.ENCOUNTER,
        )
    c.as_basic(*_TOUCHED, on=c.me, until=When.ENCOUNTER)
