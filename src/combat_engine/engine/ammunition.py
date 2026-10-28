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

#: How many ordinary pieces a character carries for a launcher it holds.
#:
#: **An invented number, and that is on the record.** The compendium prints
#: no quantity for a character's mundane ammunition. Camille, 2026-10-28,
#: quoted on `#520`:
#:
#:     Typical play doesn't even track arrows, but since bookkeeping here is
#:     easy, I think we can. For now, treat characters with mundane
#:     ammunition as having 50, and throwing weapons as having 5.
#:
#: So this is a supplied figure rather than a printed one, which is the
#: opposite of the position a previous comment of mine on `#877` asserted --
#: see the attribution note there. `Ammo.count`'s own docstring already
#: anticipated it: *"that is not a printed rule … so it is a field rather
#: than a constant, and whoever hands the ammunition out chooses."*
#:
#: `chargen` is the hander-out. The thrown half of the same ruling is not
#: here, because a thrown weapon is a `Weapon` the thrower picks back up
#: rather than a piece that is spent -- see `#520`.
MUNDANE = 50


#: How many copies of a throwable weapon a character carries.
#:
#: The other half of the same ruling as `MUNDANE`, and invented for the same
#: reason -- the compendium prints no quantity. Camille, 2026-10-28, on
#: `#520`:
#:
#:     For now, treat characters with mundane ammunition as having 50, and
#:     throwing weapons as having 5.
#:
#: Five rather than fifty because a thrown weapon is a weapon: it is picked
#: back up after the fight, where a loosed arrow is not, so the number is a
#: handful of spares rather than a bundle.
THROWN = 5


def is_a_throw(power: str) -> bool:
    """Is this row thrown by hand, rather than fired or swung?

    The header flag is the whole answer and nothing is inferred from the
    range line: `thrown_by_hand` is what the 22 rows that print `Ranged
    weapon` and mean "throw the thing in your hand" already declare, and
    `Power.can_branch` has gated on it since before any of this.
    """
    from .dsl import get

    p = get(power)
    return bool(p is not None and p.thrown_by_hand)


def hurl(world: World, eid: int, power: str, branch: int = 0) -> str:
    """Spend one copy of the weapon this throw was made with. Its ref, or "".

    Beside `nock` because it is the same question -- what did declaring this
    attack use up -- asked of the other kind of ranged weapon attack. The
    count floors at zero and the weapon stays in hand; `query.ready_to_throw`
    is what refuses the throw after that, for the reason `Gear.thrown_left`
    gives.

    `""` for anything untracked, which is a monster and any weapon chargen
    did not stock. The honest answer there is that nothing was spent, not
    that a throw was free.
    """
    if not is_a_throw(power):
        return ""
    gear = world.get(eid, Gear)
    if gear is None:
        return ""
    arm = gear.thrown
    if arm is None or arm.ref not in gear.thrown_left:
        return ""
    gear.thrown_left[arm.ref] = max(0, gear.thrown_left[arm.ref] - 1)
    return arm.ref


def fits(kind: str, group: str) -> bool:
    """Can that launcher loose that ammunition? An empty kind fits any."""
    return not kind or kind == FIRES.get(group, "")


def loaded(world: World, eid: int, group: str) -> Any:
    """The piece this creature would draw for a shot from that group.

    **Magic first, and the order is load-bearing now that mundane pieces
    exist.** This module's own rule is that *"a wielder with magic
    ammunition in the quiver uses it, rather than being asked each
    shot"* -- and until `#520` the quiver held nothing else, so taking the
    first fitting entry happened to satisfy that. With 50 ordinary arrows
    in there too, first-fitting would spend an arrow and leave the magic
    piece untouched, which is the one thing the module is for.

    A mundane piece carries no `ref`, so sorting on `bool(ref)` is the whole
    of the preference and needs no new field.
    """
    gear = world.get(eid, Gear)
    if gear is None:
        return None
    fitting = [a for a in gear.quiver if a.count > 0 and fits(a.kind, group)]
    if not fitting:
        return None
    return min(fitting, key=lambda a: not a.ref)


def nock(world: World, eid: int, power: str, branch: int = 0) -> str:
    """Draw and spend one piece for this attack. The item's ref, or "".

    Only for a ranged attack made with something that fires ammunition,
    which is what keeps a wizard's ranged implement attack and an area
    burst from emptying a quiver they were never loaded into.
    """
    from .resolve import _is_ranged

    if not _is_ranged(power, branch):
        return ""
    # **A throw is not a shot, and this gate was missing.** A
    # `thrown_by_hand` row *is* ranged, so a ranger holding a longbow and a
    # dagger spent an **arrow** to throw the dagger: `nock` walks `held`,
    # finds the bow, and `loaded` hands it something that fits. Harmless for
    # as long as the quiver was empty unless a magic piece had been bought
    # -- and `36fd41d` put 50 ordinary arrows in it, which is what made a
    # latent fault into a live one. `hurl` is the right spend for these.
    if is_a_throw(power):
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


def spend_load(world: World, eid: int, power: str, branch: int = 0) -> str:
    """Empty the weapon this shot was fired from. Its ref, or "".

    Beside `nock` because it answers the same per-shot question from the
    same gate: `_is_ranged` decides whether a shot happened at all, and an
    area burst or an implement attack must empty nothing, exactly as it
    must spend no ammunition.

    Only a weapon `query.needs_loading` is true of -- the three that print
    `load minor` -- is recorded. A longbow prints `load free`, which is a
    load the rules charge nothing for, so it is always ready and nothing is
    written. #675, #725.

    Returns the ref it emptied so a caller can say so; the refusal lives in
    `actions`, not here, because by the time a shot resolves it is too late
    to decline it.
    """
    from .query import needs_loading
    from .resolve import _is_ranged

    if not _is_ranged(power, branch):
        return ""
    gear = world.get(eid, Gear)
    if gear is None or gear.ranged is None:
        return ""
    if not needs_loading(gear.ranged):
        return ""
    gear.unloaded.add(gear.ranged.ref)
    return gear.ranged.ref


def fired_with(ev: Any, item: str) -> bool:
    """Was the attack behind this event shot from that item?

    False when nothing was drawn, which is the honest answer for a
    creature with an empty quiver -- and is why a property row gating on
    this stops paying out rather than answering every shot forever.
    """
    return bool(item) and getattr(ev, "ammo", "") == item
