"""Psion, level 10: blinking as far as whoever just blinked."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Event,
    Keyword,
    Moved,
    Trigger,
    World,
    ally_within,
    both,
    distance,
    either,
    enemy_within,
    power,
)


def _a_teleport(world: World, me: int, ev: Event) -> bool:
    """`kind_` rides on `Moved` as a plain attribute, so it is read with
    `getattr`. `MoveEnd` knows the word too and not the squares, and the
    squares are the whole payout of this row."""
    return getattr(ev, "kind_", "") == "teleport"


@power(
    "p13345",
    level=10,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
    trigger="a creature within 10 squares of you teleports",
    on=Trigger(
        Moved,
        both(_a_teleport, either(ally_within(10), enemy_within(10))),
        "a creature within 10 squares of you teleports",
    ),
)
def p13345(c: Cast) -> None:
    """"A creature" is either side, so both radius predicates, which between
    them are every other creature on the board. The distance comes off the
    event's own two squares rather than being asked of the board afterwards:
    by then the creature has arrived."""
    ev = c.trigger
    if ev is None:
        return
    hop = distance(ev.from_, ev.to)
    if hop:
        c.teleport(hop)
