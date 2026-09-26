"""What the shaman rows keep saying about the spirit companion.

The spirit can be dismissed and called back, so its id is read fresh every
time rather than captured: a gate that closed over the old id goes silently
false the moment the spirit is called again.

The spirit is a creature on your side and in the target pool, which means
`c.allies()` and `c.within(..., side="ally")` count it. Every list handed
a bonus here takes it back out -- a row reading "each ally adjacent to your
spirit companion" never meant the spirit itself.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import Cast, Hit, Keyword, Square, get, spread
from combat_engine.engine.dsl import area_of
from combat_engine.engine.query import distance_between, squares


def beside_spirit(c: Cast, who: int | None) -> bool:
    """Is that creature standing next to the spirit right now?"""
    spirit = c.companion()
    return (
        who is not None
        and spirit is not None
        and who != spirit
        and c.adjacent_to(spirit, who)
    )


def near_spirit(c: Cast, who: int | None, radius: int) -> bool:
    """Is that creature within `radius` squares of the spirit?"""
    spirit = c.companion()
    if who is None or spirit is None or who == spirit:
        return False
    return distance_between(c.world, spirit, who) <= radius


def beside(c: Cast, side: str = "ally") -> list[int]:
    """Everyone standing next to the spirit."""
    spirit = c.companion()
    if spirit is None:
        return []
    return [w for w in c.within(1, of=spirit, side=side) if w != spirit]


def friends(c: Cast, *, with_me: bool = False) -> list[int]:
    """The allies, the spirit left out."""
    spirit = c.companion()
    mine = [a for a in c.allies() if a != spirit]
    return list(dict.fromkeys([c.me, *mine])) if with_me else mine


def spirit_square(c: Cast) -> Square | None:
    """The square the spirit stands in, for a push or a pull away from it."""
    spirit = c.companion()
    if spirit is None:
        return None
    return next(iter(sorted(squares(c.world, spirit))), None)


def free_square_beside(c: Cast, origin: Square | None) -> Square | None:
    if origin is None:
        return None
    for sq in sorted(spread({origin}, 1) - {origin}):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def send_spirit(c: Cast, near: int | None) -> bool:
    """Put the spirit in a free square beside that creature.

    Only moves the spirit you already have: "you teleport your spirit
    companion" is not a call, so a shaman without one gets nothing.
    """
    if near is None or c.companion() is None:
        return False
    at = next(iter(sorted(squares(c.world, near))), None)
    where = free_square_beside(c, at)
    if where is None:
        return False
    c.call_companion(at=where)
    return True


def at_range(ctx: dict[str, Any]) -> bool:
    """A ranged, close or area attack -- what cover is printed against."""
    p = get(ctx.get("power", "") or "")
    return p is not None and p.reach.kind in (
        "ranged",
        "close_burst",
        "close_blast",
        "area_burst",
    )


def by_hand(ctx: dict[str, Any]) -> bool:
    """Is the attack being modified a melee one? The damage context carries
    no `ranged` key, so the reach comes off the row itself."""
    p = get(ctx.get("power", "") or "")
    return p is not None and p.reach.kind == "melee"


def spirit_power(ctx: dict[str, Any]) -> bool:
    """A row the spirit itself makes -- its range is measured from there."""
    p = get(ctx.get("power", "") or "")
    return p is not None and p.reach.from_ == "companion"


def keyed(ctx: dict[str, Any], *words: Keyword) -> bool:
    p = get(ctx.get("power", "") or "")
    return p is not None and any(w in p.keywords for w in words)


def catches_spirit(c: Cast, ctx: dict[str, Any]) -> bool:
    """Does that attack's area cover the spirit's square?

    A close attack is measured from whoever made it, so it can be recomputed
    exactly. An area burst is aimed at a square the context does not carry,
    so the target's square stands in for the origin.
    """
    spirit = c.companion()
    p = get(ctx.get("power", "") or "")
    who = ctx.get("attacker")
    if spirit is None or p is None or who is None:
        return False
    if p.reach.kind in ("close_burst", "close_blast"):
        return bool(squares(c.world, spirit) & area_of(c.world, who, p))
    if p.reach.kind == "area_burst":
        victim = ctx.get("target")
        return (
            victim is not None
            and distance_between(c.world, spirit, victim) <= p.reach.size
        )
    return False


def pick_foe(c: Cast, who: int | None) -> int | None:
    """Who a granted basic attack swings at: somebody already in reach, or
    else the nearest enemy."""
    if who is None:
        return None
    foes = [f for f in c.enemies() if c.adjacent_to(f, who)] or c.enemies()
    if not foes:
        return None
    # A creature off the board has no squares to measure from, and
    # `distance_between` is empty-min rather than far away.
    if not squares(c.world, who):
        return foes[0]
    return min(foes, key=lambda f: distance_between(c.world, who, f))


def granted_hit(c: Cast, who: int, foe: int, **kw: Any) -> bool:
    """Did the swing somebody else was handed land? `c.grant_attack` reports
    that a row went off, not that it connected."""
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == who and ev.target == foe:
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        c.grant_attack(who, on=foe, **kw)
    finally:
        c.world.bus.off(sub)
    return bool(landed)
