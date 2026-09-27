"""Invoker: the second stat block printed beside `p5192`.

The blade is a conjuration, so the Requirement is that it is standing
rather than a hold on the caster, and the swing comes from where it is.
`NO_TARGET` because the printed target is the creature named by the
trigger and a melee reach in the header would be measured from the invoker
-- which would refuse the row whenever the blade was doing its job.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import *
from combat_engine.engine.components import Conjuration
from combat_engine.engine.query import distance_between, team


def _blade(world: World, me: int, ref: str) -> int | None:
    for eid in list(world.having(Conjuration)):
        made = world.get(eid, Conjuration)
        if made is not None and made.by == me and made.ref == ref:
            return eid
    return None


def _standing(ref: str):  # noqa: ANN202
    def check(world: World, eid: int) -> bool:
        return _blade(world, eid, ref) is not None

    return check


def _hits_my_ally_near_the_blade(ref: str, within: int = 10):  # noqa: ANN202
    """"An enemy within 10 squares of the blade hits your ally."

    Measured from the blade, not from the invoker, and the ally is somebody
    else -- the printed word is "ally", so being hit yourself is not it.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        victim = getattr(ev, "target", None)
        who = getattr(ev, "attacker", None)
        if victim is None or who is None or victim == me:
            return False
        if team(world, victim) is not team(world, me):
            return False
        if team(world, who) is team(world, me):
            return False
        blade = _blade(world, me, ref)
        return blade is not None and distance_between(world, blade, who) <= within

    return check


@power(
    "p5192b",
    level=5,
    cls="invoker",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.CONJURATION],
    attack=Attack(WIS, vs=REF),
    requires=_standing("p5192"),
    requires_text="the p5192 conjuration must be standing",
    trigger="an enemy within 10 squares of the blade hits your ally",
    on=Trigger(
        Hit,
        _hits_my_ally_near_the_blade("p5192"),
        "an enemy within 10 squares of the blade hits your ally",
    ),
)
def p5192b(c: Cast) -> None:
    """The move is the printed Effect and happens before the swing, which is
    the whole point of an interrupt here. The blade is relocated outright
    rather than walked: the printed line names the destination and puts no
    distance on the trip."""
    blade = _blade(c.world, c.me, "p5192")
    foe = getattr(c.trigger, "attacker", None)
    if blade is None or foe is None:
        return
    spot = c.world.get(foe, Position)
    if spot is None:
        return
    if not c.adjacent_to(blade, foe):
        for sq in sorted(spread({spot.square}, 1) - {spot.square}):
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
                c.teleport(11, who=blade, to=sq)
                break
    if c.strike(on=foe, from_=blade):
        c.damage("1d8", c.wis_mod, on=foe)
