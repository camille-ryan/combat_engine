"""Psion, level 2: bringing somebody along when you blink."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    PERSONAL,
    SELF,
    Cast,
    Event,
    Keyword,
    Moved,
    Trigger,
    World,
    both,
    by_me,
    power,
    spread,
)


def _a_teleport(world: World, me: int, ev: Event) -> bool:
    """`Moved` carries `kind_` as a plain attribute set on every emission, so
    `getattr` rather than a field read -- and this is the only move event that
    also carries where the creature came from."""
    return getattr(ev, "kind_", "") == "teleport"


@power(
    "p13315",
    level=2,
    cls="psion",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
    trigger="you teleport or a creature teleports you",
    on=Trigger(Moved, both(by_me, _a_teleport), "you teleport"),
)
def p13315(c: Cast) -> None:
    """The printed target is "one ally adjacent to you **before** the
    teleport", and no header range can say that -- `Melee(1)` is measured from
    where the caster has already arrived, which is the one place the ally is
    not. So the row is Personal and the ally is picked in the body out of
    `Moved.from_`, the only move event that knows both where the creature came
    from and that it got there by teleporting."""
    ev = c.trigger
    came_from = getattr(ev, "from_", None) if ev is not None else None
    if came_from is None:
        return
    near = [a for a in c.in_squares(spread({came_from}, 1), side="ally") if a != c.me]
    if not near:
        return
    friend = c.choose(near, "who comes with you")
    if friend is None:
        return
    landing = sorted(
        sq
        for sq in spread({c.here}, 1)
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    )
    if landing:
        c.teleport(1, who=friend, to=landing[0])
