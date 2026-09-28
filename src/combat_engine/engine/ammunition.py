"""Which shot came out of which quiver.

A magic arrow is not a weapon and it is not a worn item: its benefit
belongs to the *one shot* fired from it, and then it is gone. Nothing
recorded that, so every ammunition property in the tree answered every
ranged hit its wearer ever made and never ran out.

The fix rides the road `opportunity` and `charge` already ride. One piece
is drawn when a ranged weapon attack is declared, and the item's ref is
set on all four attack events and put in the attack context -- so "you
hit an enemy with an attack using this ammunition" is a gate on
`ev.ammo`, exactly as precise as `c.weapon_of` is for a coated blade and
for the same reason.

Drawing is automatic. A wielder with magic ammunition in the quiver uses
it, rather than being asked each shot: the decision is not one a policy
could score and the printed item exists to be used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .components import Gear

if TYPE_CHECKING:
    from .ecs import World

#: Which weapon group fires which ammunition. The only rules table here,
#: and it is the printed one -- a bow takes arrows and a crossbow does
#: not. A group that is absent fires nothing, which is every melee
#: weapon and every implement.
FIRES: dict[str, str] = {
    "bow": "arrow",
    "crossbow": "bolt",
    "sling": "stone",
}


def fits(kind: str, group: str) -> bool:
    """Can that launcher loose that ammunition? An empty kind fits any."""
    return not kind or kind == FIRES.get(group, "")


def loaded(world: World, eid: int, group: str) -> Any:
    """The piece this creature would draw for a shot from that group."""
    gear = world.get(eid, Gear)
    if gear is None:
        return None
    return next(
        (a for a in gear.quiver if a.count > 0 and fits(a.kind, group)), None
    )


def nock(world: World, eid: int, power: str, branch: int = 0) -> str:
    """Draw and spend one piece for this attack. The item's ref, or "".

    Only for a ranged attack made with something that fires ammunition,
    which is what keeps a wizard's ranged implement attack and an area
    burst from emptying a quiver they were never loaded into.
    """
    from .resolve import _is_ranged

    if not _is_ranged(power, branch):
        return ""
    gear = world.get(eid, Gear)
    if gear is None or not gear.quiver:
        return ""
    for arm in gear.held:
        piece = loaded(world, eid, arm.group)
        if piece is not None:
            piece.count -= 1
            if piece.count <= 0:
                gear.quiver = [a for a in gear.quiver if a is not piece]
            return piece.ref
    return ""


def fired_with(ev: Any, item: str) -> bool:
    """Was the attack behind this event shot from that item?

    False when nothing was drawn, which is the honest answer for a
    creature with an empty quiver -- and is why a property row gating on
    this stops paying out rather than answering every shot forever.
    """
    return bool(item) and getattr(ev, "ammo", "") == item
