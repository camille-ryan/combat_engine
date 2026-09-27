"""The swordmage's field of force, and nothing else.

A late arrival, and it should not have been. The class page prints it as
one of three features and roughly sixty swordmage rows read around it, but
nothing in the engine, in `chargen` or in the swordmage tree had ever laid
it -- so `p3369`, whose whole printed Effect is "your warding also covers
the other three defences", was refused for naming something that did not
exist. `docs/blocked.json` said so in as many words.

**The size is read off the page and not chosen here.** +1 while a blade is
in hand, +3 while that blade is the only thing in either hand. Both are
laid, both in the same bucket, so the larger is the one that applies and
swapping grip mid-fight moves between them without either being stale --
the alternative, one modifier recomputed, is a number that has to be
noticed changing.

`warding` is public because `p3369` mirrors it onto Fortitude, Reflex and
Will and has to agree with it exactly; a second reading of the printed
sentence in that row's file is a second chance to read it differently.

**The field is presently 0 on every swordmage `chargen` deals.** The class
line is derived from the book's proficiency column, which names a light
and a heavy blade, and `chargen._arms` has no branch for either -- so the
class falls through to the simple melee one and is handed a mace. The gate
here is the printed one and is left alone; the chassis is what wants
fixing, and its own build sections name the weapon each build carries.
Driven by hand: a longsword with the other hand free reads 3, the same
sword beside a dagger reads 1, a bow reads 0.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Condition,
    Gear,
    Keyword,
    When,
    World,
    power,
)
from combat_engine.engine.query import active

#: The weapon groups the field needs in hand. `Weapon.is_light_blade` reads
#: the property rather than the group, because a light blade is a property
#: several other rows already ask about; the heavy one has only a group.
_HEAVY_BLADE = "heavy blade"


def warding(world: World, eid: int) -> int:
    """What the field is worth right now: 0, 1 or 3.

    Recomputed rather than stored, for the reason combat advantage is:
    a hand that was free a moment ago is holding a second sword now, and
    the printed sentence is about the grip at the moment of the attack.

    Zero covers both printed ways of not having it -- no blade in hand,
    and not conscious.
    """
    gear = world.get(eid, Gear)
    if gear is None:
        return 0
    if Condition.UNCONSCIOUS in active(world, eid):
        return 0
    held = gear.held
    if not any(w.is_light_blade or w.group == _HEAVY_BLADE for w in held):
        return 0
    # "In one hand, and the other hand free (not carrying a shield, an
    # off-hand weapon, a two-handed weapon, or anything else)" -- which is
    # exactly one thing held, and that thing needing one hand.
    spare = len(held) == 1 and not held[0].two_handed and not gear.shield
    return 3 if spare else 1


@power(
    "cf:swordmage-f2",
    level=0,
    cls="swordmage",
    # A trait: the field is up from the moment the fight starts and nobody
    # spends an action raising it.
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def swordmage_warding(c: Cast) -> None:
    """A standing bonus to AC, worth more with a hand to spare.

    No `requires=` gate. The printed Requirement is about the grip and the
    grip changes during a fight, so refusing the row at the start of one
    would be answering a question at the wrong moment; each modifier asks
    it again on every roll instead.

    `stacks=False` buckets both under this row's own ref, which is how two
    readings of one sentence are made to pick the larger rather than add.
    Untyped would have given a one-handed swordmage +4.
    """
    me, world = c.me, c.world

    def at_least(size: int) -> Any:
        return lambda _ctx: warding(world, me) >= size

    for size in (1, 3):
        c.bonus(AC, size, until=When.ENCOUNTER, on=me, stacks=False, when=at_least(size))
