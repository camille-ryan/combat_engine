"""Warden: the four sentences this class prints over and over.

Each is here because writing it per row would be a chance per row to get it
wrong, and three of the four have no ready-made method that says them.

* **A guardian form.** Twenty-one dailies open "you assume the guardian
  form of X until the end of the encounter". Being in one is being in no
  other, which is what `c.stance` does and what `c.form` does not --
  `c.form` has `revert`, a way *out*, but no notion of displacing the shape
  you were already wearing. So a form is a stance, and the modifiers it
  grants hang off it so that leaving takes them along.
* **"...is difficult terrain for your enemies".** A zone is rough or it is
  not; it has no side. `c.zone(difficult=<label>)` names the *sort* of
  going and `c.ignores_difficult(<label>)` exempts a creature from that
  sort, so the pair says the printed line for everyone on the board when
  the zone is laid.
* **A zone that bites enemies only, and a zone that bites at the *end* of
  a turn.** `c.hazard` is exactly one shape -- "any creature that enters or
  starts its turn there" -- and the warden prints three others.

`in_form` is the Requirement line every form's own attack carries. Those
attacks are written -- the importer mints each one a ref with a `b` on the
end -- and they live in `second_card.py`, which is what the gate is for.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from combat_engine.engine import (
    ActionType,
    Cast,
    Condition,
    DamageType,
    Effect,
    Gear,
    Relation,
    When,
    World,
)
from combat_engine.engine.events import Dropped, TurnEnd, TurnStart, ZoneEntered
from combat_engine.engine.grid import Square
from combat_engine.engine.query import team


def assume(c: Cast, *, conditions: Iterable[Condition] = ()) -> Effect:
    """Take on a guardian form. One at a time, so: a stance."""
    return c.stance(conditions=conditions, label=c.ref)


def while_in(c: Cast, form: Effect, *held: Effect | None) -> None:
    """Bind modifiers to a form, so that stepping out of it ends them too."""
    for eff in held:
        if eff is not None:
            form.on_end.append(lambda e=eff: c.world.effects.end(e, "form ended"))


def in_form(ref: str) -> Callable[[World, int], bool]:
    """"Requirement: the <form> power must be active."""

    def check(world: World, eid: int) -> bool:
        return any(eff.label == ref for eff in world.effects.of(eid))

    return check


def has_shield(world: World, eid: int) -> bool:
    """"Requirement: You must be wielding a shield."""
    gear = world.get(eid, Gear)
    return gear is not None and gear.shield


def rough_for_enemies(
    c: Cast,
    area: Iterable[Square],
    *,
    until: When = When.EONT,
    blocks_sight: bool = False,
    sustain: ActionType | None = None,
) -> int:
    """Difficult terrain that the caster and their allies walk through."""
    zone = c.zone(
        area, until=until, difficult=c.ref, blocks_sight=blocks_sight, sustain=sustain
    )
    for who in (c.me, *c.allies()):
        c.ignores_difficult(c.ref, on=who, until=until)
    return zone


def dropped_one_this_turn(world: World, eid: int) -> bool:
    """"Requirement: you must have reduced an enemy to 0 hit points during
    this turn." Read back off the log, which is the only record of it."""
    for ev in reversed(world.bus.log):
        if isinstance(ev, TurnStart) and ev.actor == eid:
            return False
        if isinstance(ev, Dropped) and ev.source == eid:
            return True
    return False


def marks_laid_by(world: World, eid: int) -> list[Effect]:
    """Every live mark this creature is holding on somebody."""
    return [
        eff
        for eff in list(world.effects.live.values())
        if eff.source == eid
        and any(rel is Relation.MARKED_BY for rel, _, _ in eff.relations)
    ]


def zone_named(c: Cast, label: str) -> int | None:
    """This caster's live zone with that label. A burst power's body runs
    once per target and only the first call lays the zone; the rest have to
    find it again."""
    for eid, zone in c.world.zones.all():
        if zone.label == label and zone.owner == c.me:
            return eid
    return None


def bites_enemies(
    c: Cast,
    zone: int,
    amount: int,
    dtype: DamageType = DamageType.UNTYPED,
    *,
    until: When = When.EONT,
) -> None:
    """"Any enemy that enters the zone or starts its turn there takes N."

    `c.hazard` says the same of any creature, the caster's own side
    included, which is a different printed sentence.
    """
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if who == c.me or team(c.world, who) is team(c.world, c.me):
            return
        if struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.flat(amount, dtype=dtype, on=who)

    def on_enter(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bite(ev.actor)

    def on_start(ev: TurnStart) -> None:
        if ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    c.watch(ZoneEntered, on_enter, until=until)
    c.watch(TurnStart, on_start, until=until)


def when_turn_ends_in(
    c: Cast, zone: int, fn: Callable[[int], None], *, until: When = When.EONT
) -> None:
    """"Any creature that ends its turn within the zone ..."."""

    def on_end(ev: TurnEnd) -> None:
        if ev.actor in c.world.zones.occupants(zone):
            fn(ev.actor)

    c.watch(TurnEnd, on_end, until=until)


def when_turn_starts_in(
    c: Cast, zone: int, fn: Callable[[int], None], *, until: When = When.EONT
) -> None:
    """"... that start their turns within the zone ..."."""

    def on_start(ev: TurnStart) -> None:
        if ev.actor in c.world.zones.occupants(zone):
            fn(ev.actor)

    c.watch(TurnStart, on_start, until=until)
