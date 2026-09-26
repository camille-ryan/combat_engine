"""Avenger, level 6: the trigger that reads the dice themselves.

The spec entry said `AttackResult` keeps one face and the oath's two-roll
benefit overwrites it, so nothing could ask what the dice were.
`AttackResult.rolls` now keeps every d20 face an attack has shown -- the
first, the oath's second, a reroll's -- and `better_of_two` records the
loser as well, because "the same number on each die" is asked of both.

Declared on `Hit` and on `Miss` rather than on `AttackRolled`: the oath's
second die is rolled in the `AttackRolled` window, so a row reading the
faces there would be racing the thing that produces them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    PERSONAL,
    SELF,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Miss,
    Trigger,
    World,
    power,
    spread,
)
from combat_engine.engine.query import squares as _squares

from .oath import _melee, sworn

MATCHED = (
    "you make a melee attack against your oath of enmity target and roll "
    "the same number on each die of the attack roll"
)


def _same_on_each_die(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    result = getattr(ev, "result", None)
    faces = getattr(result, "rolls", ())
    # One die is trivially "the same number on each die", and every attack
    # in the game rolls one. The printed line is about the oath's pair.
    if len(faces) < 2 or len(set(faces)) != 1:
        return False
    return sworn(world, me, getattr(ev, "target", None)) and _melee(ev)


@power(
    "p11673",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE, Keyword.TELEPORTATION],
    trigger=MATCHED,
    on=[
        Trigger(Hit, _same_on_each_die, MATCHED),
        Trigger(Miss, _same_on_each_die, MATCHED),
    ],
)
def p11673(c: Cast) -> None:
    """The extra damage is dealt as a flat 5 rather than folded into the
    triggering attack's own roll: the `Hit` is announced before the body
    that rolled it deals its damage, so this lands as part of the same blow.

    "Force or radiant" is the caster's choice, asked each time -- some
    creatures resist one and not the other, which is the whole reason the
    line offers two.
    """
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is None:
        return
    if isinstance(ev, Hit):
        dtype = c.choose([DamageType.FORCE, DamageType.RADIANT], "which damage type")
        c.flat(5, dtype=dtype or DamageType.RADIANT, on=victim)
        return
    beside = _squares(c.world, victim)
    free = [
        sq
        for sq in sorted(spread(beside, 1) - beside)
        if c.world.grid.inside(sq) and not c.in_squares([sq])
    ]
    if free:
        c.teleport(len(free), to=c.choose(free, "teleport beside the target"))
