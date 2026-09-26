"""Seeker: the sentences this class prints over and over.

Each is here because saying it per row would be a chance per row to get it
wrong, and none of them has a ready-made method.

* **A zone that bites, four ways.** `c.hazard` is exactly one shape -- any
  creature that enters or starts its turn there. This class prints enemies
  only, on entry only, "without shifting", and "ends its turn there", and the
  once-per-turn cap belongs to all of them.
* **"While within the zone, enemies ..."** A modifier is held on a creature
  and not on a patch of ground, so it is laid on entry and lifted on the way
  out, and the whole lot is dropped when the zone goes.
* **The two build riders.** The class table derives its secondary abilities
  as `second-str` and `second-dex`, which is what `c.build` is asked.
* **"+ 1d6" in a damage line.** `c.damage` maxes the dice it is handed and
  only those, so the second die of a two-die line has to max itself.

Two printed things this class says a great deal and the engine cannot hear:
"you can use this power as a ranged basic attack", which wants a header
field, and the crossbow the derived chassis carries, which is not a bow --
so every row requiring one is legal for nobody on the audit board. That is
the requirement being right rather than the row being wrong.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from combat_engine.engine import (
    ActionType,
    Cast,
    DamageType,
    Effect,
    Event,
    Gear,
    Health,
    Keyword,
    Position,
    When,
    World,
)
from combat_engine.engine.components import Conjuration
from combat_engine.engine.events import (
    Hit,
    MoveEnd,
    MoveStart,
    PowerUsed,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.grid import Square, spread
from combat_engine.engine.query import is_ as has_condition
from combat_engine.engine.query import team
from combat_engine.engine.types import Condition
from combat_engine.engine.zones import Zone

PRIMAL = [Keyword.PRIMAL]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]


# -- damage lines -----------------------------------------------------------


def scaled_w(c: Cast, base: int = 1) -> str:
    """An at-will's "1[W] ... Level 21: 2[W]"."""
    return c.w(base * 2 if c.level >= 21 else base)


def extra_dice(c: Cast, dice: str) -> int:
    """The "+ 1d6" half of a printed damage line, as a number.

    `c.damage` maxes the dice it is handed on a critical and cannot be handed
    two expressions -- the roller takes no `+`. So the second die is rolled
    here and maxed here, which is what the printed critical rule says of
    every die in the line.
    """
    count, _, faces = dice.partition("d")
    n = int(count or 1)
    return n * int(faces) if c.crit else c.roll(dice)


# -- printed Requirement lines ----------------------------------------------


def has_bow(world: World, eid: int) -> bool:
    """"You must be wielding a bow." A crossbow is its own group."""
    gear = world.get(eid, Gear)
    return gear is not None and any(w.group == "bow" for w in gear.held)


def has_thrown(world: World, eid: int) -> bool:
    """"A light thrown or a heavy thrown weapon", for the melee branch."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return any(
        {"light thrown", "heavy thrown"} & set(w.properties) for w in gear.melee
    )

def bloodied_or_weakened(world: World, eid: int) -> bool:
    """"You must be bloodied or weakened."""
    hp = world.get(eid, Health)
    hurt = hp is not None and hp.hp <= hp.max_hp // 2
    return hurt or has_condition(world, eid, Condition.WEAKENED)


# -- asking the board -------------------------------------------------------


def square_of(c: Cast, eid: int) -> Square | None:
    pos = c.world.get(eid, Position)
    return pos.square if pos is not None else None


def free_near(c: Cast, at: Square | None, count: int = 1) -> list[Square]:
    """Unoccupied squares next to a point. "In an unoccupied square adjacent
    to the target", which `c.conjure` can only answer for the caster."""
    if at is None:
        return []
    out = [
        sq
        for sq in sorted(spread({at}, 1) - {at})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    return out[:count]


def foes_around(c: Cast, who: int | None, radius: int = 1) -> list[int]:
    """"Each enemy adjacent to the target" -- the caster's enemies, which is
    what the printed word means, and never the target itself."""
    if who is None:
        return []
    return [e for e in c.within(radius, of=who, side="enemy") if e != who]


def shifting(c: Cast, who: int) -> bool:
    """Is that creature's current move a shift?

    `ZoneEntered` and `EnterSquare` carry no kind, so the move the step
    belongs to is read back off the log.
    """
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, MoveEnd) and ev.actor == who:
            return False
        if isinstance(ev, MoveStart) and ev.actor == who:
            return ev.kind_ == "shift"
    return False


def landed_on(c: Cast) -> list[int]:
    """Which of this use's targets it has hit so far.

    The body is called once per target and keeps nothing between calls, so
    "if you hit both targets" is read off the log back as far as the
    `PowerUsed` that opened this use.
    """
    out: list[int] = []
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, PowerUsed) and ev.actor == c.me and ev.power == c.ref:
            break
        if isinstance(ev, Hit) and ev.attacker == c.me and ev.power == c.ref:
            out.append(ev.target)
    out.reverse()
    return out


# -- holding things for a while ---------------------------------------------


def while_in(c: Cast, holder: Effect | None, *held: Effect | None) -> None:
    """Bind effects to a stance, so that leaving it takes them along."""
    if holder is None:
        return
    for eff in held:
        if eff is not None:
            holder.on_end.append(lambda e=eff: c.world.effects.end(e, "stance ended"))


def bind_to_zone(c: Cast, zone: int, *held: Effect | None) -> None:
    """Tie watches to a zone's life. A sustained zone outlives every duration
    in `When`, so its triggers cannot be given one and have to be ended with
    it instead."""
    patch = c.world.get(zone, Zone)
    if patch is None or patch.effect is None:
        return
    for eff in held:
        if eff is not None:
            patch.effect.on_end.append(
                lambda e=eff: c.world.effects.end(e, "zone ended")
            )


def once_when(
    c: Cast,
    event: type[Event],
    who: int,
    fn: Callable[[object], None],
    *,
    until: When = When.ENCOUNTER,
) -> None:
    """"At the end of the target's next turn, ..." -- the next one only.

    `c.watch(once=True)` spends itself on the first event of the right class
    whatever creature it names, which is the wrong turn nine times in ten.
    """
    spent: list[bool] = []

    def fire(ev: object) -> None:
        if spent or getattr(ev, "actor", None) != who:
            return
        spent.append(True)
        fn(ev)
        c.world.effects.end(held, "spent")

    held = c.watch(event, fire, until=until)


# -- zones that do something ------------------------------------------------


def bites(
    c: Cast,
    zone: int,
    amount: int,
    dtype: DamageType = DamageType.UNTYPED,
    *,
    until: When = When.EONT,
    side: str = "enemy",
    on_entry: bool = True,
    on_start: bool = True,
    on_end: bool = False,
    unless_shifting: bool = False,
) -> None:
    """A zone with teeth, in whichever of the printed shapes is wanted.

    `c.hazard` says only one of them -- any creature, entering or starting
    its turn -- and the cap is always "only once per turn".
    """
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if side == "enemy" and (
            who == c.me or team(c.world, who) is team(c.world, c.me)
        ):
            return
        if struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.flat(amount, dtype=dtype, on=who)

    if on_entry:

        def entered(ev: ZoneEntered) -> None:
            if ev.zone == zone and not (unless_shifting and shifting(c, ev.actor)):
                bite(ev.actor)

        c.watch(ZoneEntered, entered, until=until)

    if on_start:

        def started(ev: TurnStart) -> None:
            if ev.actor in c.world.zones.occupants(zone):
                bite(ev.actor)

        c.watch(TurnStart, started, until=until)

    if on_end:

        def ended(ev: TurnEnd) -> None:
            if ev.actor in c.world.zones.occupants(zone):
                bite(ev.actor)

        c.watch(TurnEnd, ended, until=until)


def when_turn_starts_in(
    c: Cast, zone: int, fn: Callable[[int], None], *, until: When = When.EONT
) -> Effect:
    """"Any creature that starts its turn within the zone ..."."""

    def started(ev: TurnStart) -> None:
        if ev.actor in c.world.zones.occupants(zone):
            fn(ev.actor)

    return c.watch(TurnStart, started, until=until)


def when_turn_ends_in(
    c: Cast, zone: int, fn: Callable[[int], None], *, until: When = When.EONT
) -> Effect:
    """"Any creature that ends its turn within the zone ..."."""

    def ended(ev: TurnEnd) -> None:
        if ev.actor in c.world.zones.occupants(zone):
            fn(ev.actor)

    return c.watch(TurnEnd, ended, until=until)


def on_enemies_within(
    c: Cast,
    zone: int,
    make: Callable[[int], Effect | None],
    *,
    until: When = When.EONT,
) -> None:
    """"While within the zone, enemies <suffer something>."

    The something is a modifier, and a modifier lives on a creature. So it is
    laid on whoever is standing there, laid again on each one that walks in,
    and lifted from each one that walks out.
    """
    held: dict[int, Effect] = {}

    def lay(who: int) -> None:
        if who in held or who == c.me or team(c.world, who) is team(c.world, c.me):
            return
        eff = make(who)
        if eff is not None:
            held[who] = eff

    def lift(who: int) -> None:
        eff = held.pop(who, None)
        if eff is not None and not eff.ended:
            c.world.effects.end(eff, "left the zone")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            lay(ev.actor)

    def left(ev: ZoneExited) -> None:
        if ev.zone == zone:
            lift(ev.actor)

    c.watch(ZoneEntered, entered, until=until)
    c.watch(ZoneExited, left, until=until)
    for who in c.world.zones.occupants(zone):
        lay(who)


def rough_for_enemies(
    c: Cast,
    area: Iterable[Square],
    *,
    until: When = When.EONT,
    sustain: ActionType | None = None,
) -> int:
    """"The zone is difficult terrain for your enemies." Ground is rough or
    it is not and has no side, so the caster's own side is exempted from
    this particular sort of going."""
    zone = c.zone(area, until=until, difficult=c.ref, sustain=sustain)
    for who in (c.me, *c.allies()):
        c.ignores_difficult(c.ref, on=who, until=until)
    return zone


# -- conjurations -----------------------------------------------------------


def banish(c: Cast, eid: int) -> None:
    """Take a conjuration off the board. "Once it attacks, it disappears."""
    conj = c.world.get(eid, Conjuration)
    if conj is None or conj.effect is None:
        return
    eff = c.world.effects.live.get(conj.effect)
    if eff is not None:
        c.world.effects.end(eff, "expended")
