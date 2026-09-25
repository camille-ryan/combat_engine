"""Warlock, level 10: utility. Four personal rows, no attack.

`p1328` is declared on `DamageRolled` rather than on the printed `Hit`, the
same seam `fighter/level_6.py` uses: the amount is on the event and mutable,
and the emitter reads it back once the window closes, so a reaction can
empty it. `targets_me` alone would also answer ongoing damage and a hazard,
and the line says "by an attack".

`p95` is the level's polymorph. "Can't take standard actions" is
`Condition.SHAPED`, the one card in the table that means exactly that, and
`revert=MINOR` is the printed way out.

`p1296` is a message carried a hundred miles and brought back. The board has
no distance like that and no conversation, so it is declared inert.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    Cast,
    Condition,
    Event,
    Keyword,
    Ranged,
    Trigger,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import DamageRolled

ARCANE = [Keyword.ARCANE]

_HURT_BY_AN_ATTACK = "you are hit and damaged by an attack"


def _attack_damaged_me(world: World, me: int, ev: Event) -> bool:
    """Damage aimed at me that a declared row dealt."""
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and get(getattr(ev, "detail", "")) is not None
    )


@power(
    "p1296",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(100),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
    out_of_combat=True,
)
def p1296(c: Cast) -> None:
    c.note("p1296: a spoken message delivered far off, and the reply brought back")


@power(
    "p1328",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_HURT_BY_AN_ATTACK,
    on=Trigger(DamageRolled, when=_attack_damaged_me, text=_HURT_BY_AN_ATTACK),
)
def p1328(c: Cast) -> None:
    ev = c.trigger
    if ev is None:
        return
    spared = getattr(ev, "amount", 0)
    ev.amount = 0
    c.note(f"p1328: {spared} damage comes to nothing")


@power(
    "p662",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p662(c: Cast) -> None:
    """"You do not need line of sight" needs no saying: `c.teleport` offers
    every square within range that the warlock would fit in, and checks
    nothing about seeing it. "If you attempt to teleport to a space you
    can't occupy, you don't move" is the same filter from the other side."""
    c.teleport(6)


@power(
    "p95",
    level=10,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.POLYMORPH],
)
def p95(c: Cast) -> None:
    """"Until the end of the encounter or for 5 minutes" is one duration on
    this board: the encounter is the only clock there is."""
    c.form(
        conditions=(Condition.INSUBSTANTIAL, Condition.SHAPED),
        modes={"fly": 6},
        until=When.ENCOUNTER,
        revert=MINOR,
        label=c.ref,
    )
