"""Warden, level 6: the rolled bonus, and dragging an ally into his own blast."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    INTERRUPT,
    MINOR,
    PERSONAL,
    SELF,
    AttackDeclared,
    Cast,
    Event,
    Keyword,
    Trigger,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.query import allies


def _weapon_attack(ctx: dict[str, Any]) -> bool:
    """The row being rolled for, in either context.

    The attack context names it `power` and the damage context names the
    detail on the roll the same thing, so one gate serves both halves of a
    line that says "an attack roll or a damage roll".
    """
    p = get(ctx.get("power") or "")
    return p is not None and Keyword.WEAPON in p.keywords


def _ally_left_himself_out(world: World, me: int, ev: Event) -> bool:
    actor = getattr(ev, "attacker", None)
    if actor is None or actor == me or getattr(ev, "target", None) != me:
        return False
    return actor in allies(world, me) and actor not in getattr(ev, "among", ())


@power(
    "p5527",
    level=6,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
)
def p5527(c: Cast) -> None:
    """A d6 per roll rather than one d6 for the duration: `dice=` is rolled
    every time the modifier is read, which is once per attack and once per
    damage roll, and that is what "whenever you make a roll" means."""
    c.bonus(
        "attack", 0, dice="1d6", kind="power", until=When.EONT, on=c.me,
        when=_weapon_attack,
    )
    c.bonus(
        "damage", 0, dice="1d6", kind="power", until=When.EONT, on=c.me,
        when=_weapon_attack,
    )


@power(
    "p5590",
    level=6,
    cls="warden",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
    trigger="an ally targets you with a power that does not include that ally as a target",
    on=Trigger(
        AttackDeclared,
        _ally_left_himself_out,
        "an ally targets you with a power he is not a target of",
    ),
)
def p5590(c: Cast) -> None:
    """Only an ally's **attack** can be answered: an attack is the one thing
    a power use announces to the bus, so this catches the blast that caught
    me and not a buff he kept off himself. The ally is added to the use that
    is still running, so its body is called for him the way it was for me."""
    ally = getattr(c.trigger, "attacker", None)
    if ally is not None:
        c.add_target(ally)
