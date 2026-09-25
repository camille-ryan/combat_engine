"""Grabbing, the way the later fighter books keep printing it.

`c.grab` holds to the end of the fight and takes no duration, and nothing
lets go again -- there is no escape action in the engine, so a grab ends
when a row ends it. Two sentences recur often enough to be written once:
"the grab ends automatically at the end of your next turn", and the row
that opens its hand deliberately.
"""

from __future__ import annotations

from combat_engine.engine import Cast, Relation, When, World


def holds_somebody(world: World, eid: int) -> bool:
    """"Requirement: You must have a creature grabbed"."""
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def grabbed_by(c: Cast) -> list[int]:
    return sorted(c.world.relations.targets(Relation.GRABBED_BY, c.me))


def grab_until(c: Cast, until: When, *, on: int | None = None) -> None:
    """"You grab the target. The grab ends automatically at ..."

    The clock is a second, empty effect whose ending lets go, because the
    grab itself has no duration to set.
    """
    held = c.grab(on=on)
    timer = c.effect("grab clock", until=until, on=on)
    if held is None or timer is None:
        return
    timer.on_end.append(lambda: c.world.effects.end(held, "the grip opens"))


def release(c: Cast, who: int) -> None:
    """Let go: the effect holding the relation up ends, and so does it."""
    for effect in list(c.world.effects.of(who)):
        if any(
            kind is Relation.GRABBED_BY and source == c.me and target == who
            for kind, source, target in effect.relations
        ):
            c.world.effects.end(effect, c.ref)
    c.world.relations.clear(Relation.GRABBED_BY, c.me, who, c.ref)
