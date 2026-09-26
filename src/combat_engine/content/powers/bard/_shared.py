"""Helpers the bard files share: geometry, and reaching into a live attack roll.

No rows live here. The bard prints "an ally within 5 squares", "a square
adjacent to the target" and "replace the ally's attack roll with yours" over
and over, and each of those is a few lines that would otherwise be written a
dozen times and be wrong in one of them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import *


def gap(c: Cast, a: int, b: int) -> int:
    """Squares between two creatures; 99 when either is not on the board."""
    first = c.world.get(a, Position)
    second = c.world.get(b, Position)
    if first is None or second is None:
        return 99
    return distance(first.square, second.square)


def square_of(c: Cast, who: int | None) -> Square | None:
    pos = c.world.get(who, Position) if who is not None else None
    return pos.square if pos else None


def free_near(c: Cast, spot: Square | None, skip: frozenset[Square] = frozenset()) -> Square | None:
    """An empty square next to `spot`, for a row that lands somebody there."""
    if spot is None:
        return None
    grid = c.world.grid
    for sq in sorted(spread({spot}, 1)):
        if sq == spot or sq in skip:
            continue
        if grid.passable(sq) and grid.occupant(sq) is None:
            return sq
    return None


def in_aura(c: Cast, who: int | None, zone: int = 0) -> bool:
    """Is that creature standing in the caster's own live aura right now?"""
    zid = zone or c.my_aura()
    return bool(zid) and who is not None and who in c.world.zones.occupants(zid)


def aura_allies(c: Cast, zone: int = 0) -> list[int]:
    """The caster's allies standing in the aura; empty when there is no aura.

    "One of your allies" is the printed word, so the caster is not in it.
    """
    zid = zone or c.my_aura()
    if not zid:
        return []
    inside = set(c.world.zones.occupants(zid))
    return [w for w in c.allies() if w in inside]


def by_basic(c: Cast, ev: Any) -> bool:
    """Was that attack a basic attack, for a monster as well as a character?

    A monster points `Powers.basic` at one of its own rows, so comparing
    against the engine's two refs alone would answer no for every monster.
    """
    refs = {MELEE, RANGED}
    known = c.world.get(getattr(ev, "attacker", None), Powers)
    if known is not None:
        refs |= {known.basic, known.ranged} - {""}
    return getattr(ev, "power", "") in refs


def while_in(c: Cast, zone: int, give: Any, side: str = "ally") -> None:
    """`c.grants_in` for what is not a modifier -- a relation, or a bar.

    The engine already does the enter/exit bookkeeping in
    `Cast._while_inside`, which is private; going through it here keeps one
    copy of it rather than one per row. A public `c.while_in` would retire
    this helper.
    """
    c._while_inside(zone, give, side)


def use_roll(ev: Any, face: int) -> bool:
    """Put a number of your own on an attack that has been announced.

    `resolve.attack` re-reads the result *after* `AttackRolled` goes out, so a
    listener in that window still decides the outcome -- which is what
    `c.reroll_attack` relies on for a row the dispatcher offered. A `c.watch`
    handler has the event but not `c.trigger`, so it needs this instead.
    """
    res = getattr(ev, "result", None)
    if res is None:
        return False
    res.total += face - res.natural
    res.natural = face
    return True


def reroll(c: Cast, ev: Any, *, keep: str = "best") -> bool:
    """Roll that attack's d20 again, keeping the better face unless told not to."""
    res = getattr(ev, "result", None)
    if res is None:
        return False
    fresh = c.roll("1d20")
    return use_roll(ev, max(res.natural, fresh) if keep == "best" else fresh)
