"""Artificer: the shapes this class repeats.

Written once here because each of them is a chance to be silently wrong.

* "An enemy hits one of your allies" is the class's commonest trigger and no
  stock predicate says it: `ally_within` reads the *attacker* on a `Hit`, so
  it is false for every row of this shape, and `targets_my_side` counts the
  caster and names no distance.
* "Burst centered on an ally" is not a range the header can spell. It is
  declared as an area burst aimed at a square and `ally_at` finds who is
  standing in it.
* "Deals extra damage with weapon or fire attacks" is a gate on the damage
  context, which carries the power's ref and nothing about the attacker.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from combat_engine.engine import (
    Cast,
    DamageType,
    Event,
    Keyword,
    Relation,
    Square,
    TurnStart,
    When,
    World,
    get,
    spread,
)
from combat_engine.engine.query import distance_between, team


def ally_struck(squares: int = 99) -> Callable[[World, int, Event], bool]:
    """Somebody on my side other than me is on the receiving end of this."""

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "target", None)
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def servant_struck(squares: int = 5) -> Callable[[World, int, Event], bool]:
    """One of my summoned creatures, within range, is the one being hit."""

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "target", None)
        if who is None or not world.relations.holds(Relation.MASTER_OF, me, who):
            return False
        return distance_between(world, me, who) <= squares

    return check


def ally_at(c: Cast, *, within: int = 5) -> int | None:
    """The ally a burst is printed as being centred on: whoever stands in
    the origin square, or the closest one to it."""
    origin = c.origin or c.here
    for radius in range(within + 1):
        found = c.in_squares(spread({origin}, radius), side="ally")
        if found:
            return found[0]
    return None


def one_ally(c: Cast, pool: list[int], prompt: str) -> int | None:
    """"Choose one ally": the decider picks, an empty board picks nobody."""
    return c.choose(pool, prompt) if pool else None


def with_keyword(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """A damage-context gate: "with weapon or fire attacks"."""

    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and any(w in p.keywords for w in words)

    return gate


def near(c: Cast, thing: int, who: int, squares: int) -> bool:
    """Is `who` within that many squares of `thing`? A conjuration counts."""
    return distance_between(c.world, thing, who) <= squares


def free_squares(c: Cast, area: Iterable[Square], count: int) -> list[Square]:
    """Unoccupied ground, for the rows that put something down."""
    out: list[Square] = []
    for sq in sorted(area):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            out.append(sq)
            if len(out) == count:
                break
    return out


def zone_alive(c: Cast, zone: int) -> bool:
    return any(eid == zone for eid, _ in c.world.zones.all())


def enemies_starting_in(
    c: Cast,
    zone: int,
    amount: int,
    dtype: DamageType = DamageType.UNTYPED,
    *,
    until: When = When.ENCOUNTER,
) -> None:
    """"An enemy that starts its turn in the zone takes N."

    `c.burns` says the same of anybody, the caster's own side included, and
    also bites on entering, neither of which this line prints.
    """

    def on_turn(ev: TurnStart) -> None:
        if ev.ghost or not zone_alive(c, zone):
            return
        if ev.actor in c.world.zones.occupants(zone) and ev.actor in c.enemies():
            c.flat(amount, dtype=dtype, on=ev.actor)

    c.watch(TurnStart, on_turn, until=until)
