"""Beast form, and the shapes of sentence every file in this package repeats.

The class's own shape-change is not in this batch: no row here *is* wild
shape. So the only doors into beast form are the nine rows printing "you
assume the <shape>" and the two at level 2 printing "you use wild shape".
Everything carrying the printed Beast Form keyword is gated on being in one
-- that is what the keyword means -- and the gate is `requires=`, so the
interface refuses the row rather than the body quietly doing nothing.

`Keyword` has no member for Beast Form, so "with beast form powers" is
asked as **"is the row that is rolling gated on `in_beast_form`"**. The
gate is the only place the fact is recorded, and reading it back keeps one
truth where a second list of refs would fall out of step with it.

Every form wears the same label. Each printed line ends the last one --
"until you use wild shape again" -- and `c.form` does not displace a
previous form the way `c.stance` displaces a stance, so the old shape is
ended by hand.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from combat_engine.engine import (
    Cast,
    Condition,
    DamageType,
    Effect,
    Event,
    TurnEnd,
    TurnStart,
    When,
    World,
    ZoneEntered,
    get,
)
from combat_engine.engine.events import Hit, PowerUsed, ZoneExited
from combat_engine.engine.types import ActionType
from combat_engine.engine.zones import Zone

#: The one label every druid form wears.
BEAST = "druid beast form"


# -- the keyword, as a gate -------------------------------------------------


def in_beast_form(world: World, eid: int) -> bool:
    """A printed Beast Form keyword, as a Requirement the interface reads."""
    return any(e.label == BEAST for e in world.effects.of(eid))


def out_of_beast_form(world: World, eid: int) -> bool:
    return not in_beast_form(world, eid)


def beast_row(ctx: dict[str, Any]) -> bool:
    """Is the row rolling this one of the beast form ones?

    Read off the gate rather than off a keyword, because there is no
    keyword. `ctx["power"]` is the ref of whatever is rolling -- the attack
    context spells it `power` and `Cast.damage` puts the same ref on the
    damage context, so one gate serves both.
    """
    p = get(ctx.get("power", "") or "")
    return p is not None and p.requires is in_beast_form


def take_beast_form(
    c: Cast,
    *,
    conditions: Iterable[Condition] = (),
    modes: dict[str, int] | None = None,
) -> Effect:
    """Assume beast form, ending whichever shape was already worn."""
    for effect in list(c.world.effects.of(c.me)):
        if effect.label == BEAST:
            c.world.effects.end(effect, "wild shape again")
    return c.form(
        conditions=conditions,
        modes=modes,
        until=When.ENCOUNTER,
        revert=ActionType.MINOR,
        label=BEAST,
    )


def current_form(c: Cast) -> Effect | None:
    """The shape this druid is wearing, for a row that ends when it does."""
    for effect in c.world.effects.of(c.me):
        if effect.label == BEAST:
            return effect
    return None


def ends_with(c: Cast, shape: Effect | None, *holds: Effect | None) -> None:
    """Tie a while-in-this-form benefit to the form itself.

    The benefits are written `until=When.ENCOUNTER` because that is the
    longer of the two printed clocks; this is the shorter one, and without
    it a druid stepping out of the shape kept what the shape gave it.
    """
    if shape is None:
        return
    for hold in holds:
        if hold is not None:
            shape.on_end.append(lambda h=hold: c.world.effects.end(h, "the form ended"))


# -- the druid's second ability ---------------------------------------------


def fork_mod(c: Cast) -> int:
    """"Your Constitution or Dexterity modifier."

    That line is the guardian/predator fork written into the row, and
    `chargen.BUILDS["druid"]` has one build named `standard`. With no leg to
    ask about, the larger of the two is taken -- which is the number the
    character actually built on either leg would have. Every row printing it
    says so in its own docstring as well.
    """
    return max(c.con_mod, c.dex_mod)


# -- reading one use of a row across its targets ----------------------------


def hit_anybody(c: Cast) -> bool:
    """Did this use of this row land on anybody yet?

    The body runs once per target against one `Cast`, so a tally cannot live
    in a local. `use` stamps a `PowerUsed` first and every `Hit` after it
    belongs to this one use.
    """
    log = c.world.bus.log
    start = 0
    for i in range(len(log) - 1, -1, -1):
        ev = log[i]
        if isinstance(ev, PowerUsed) and ev.power == c.ref and ev.actor == c.me:
            start = i
            break
    return any(
        isinstance(ev, Hit) and ev.attacker == c.me and ev.power == c.ref
        for ev in log[start:]
    )


# -- ground that does something to whoever stands on it ---------------------


def zone_hold(
    c: Cast,
    zone: int,
    eligible: Callable[[int], bool],
    hold: Callable[[int], Effect | None],
    *,
    until: When = When.ENCOUNTER,
) -> int:
    """Occupants of a zone carry a hold for as long as they are inside.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are the two moments the hold goes on and comes off.
    Whoever is already standing inside is caught at the end, because making
    the zone refreshes membership before its id exists to be recognised.
    """
    held: dict[int, Effect] = {}

    def take(who: int) -> None:
        if who in held or not eligible(who):
            return
        effect = hold(who)
        if effect is not None:
            held[who] = effect

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            take(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == zone else None
        if effect is not None:
            c.world.effects.end(effect, "left the zone")

    c.watch(ZoneEntered, entered, until=until, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=until, on=c.me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(zone):
        take(actor)
    return zone


def aura_hold(
    c: Cast,
    radius: int,
    eligible: Callable[[int], bool],
    hold: Callable[[int], Effect | None],
    *,
    until: When = When.ENCOUNTER,
    difficult: str = "",
) -> int:
    """The same, for ground that follows the druid about.

    `difficult` names the sort of rough going the aura's squares are, for
    the rows printing "the aura is difficult terrain for your enemies".
    `c.aura` takes no such argument, so it is set on the `Zone` afterwards;
    whoever is exempt is given `c.ignores_difficult` with the same word.
    """
    ring = c.aura(radius, until=until)
    if difficult:
        zone = c.world.get(ring, Zone)
        if zone is not None:
            zone.difficult = difficult
    return zone_hold(c, ring, eligible, hold, until=until)


def rough_aura(c: Cast, radius: int, *, until: When = When.ENCOUNTER) -> int:
    """Ground that follows the druid and is hard going **for enemies**.

    Difficult terrain is a property of the square rather than of who is
    standing on it, so the sort of going is named and everybody on the
    druid's own side is excused from that name. `c.aura` takes no
    `difficult=` argument, which is why the `Zone` is written to directly.
    """
    ring = c.aura(radius, until=until)
    zone = c.world.get(ring, Zone)
    if zone is not None:
        zone.difficult = c.ref
    for friend in (c.me, *c.allies()):
        c.ignores_difficult(c.ref, on=friend, until=until)
    return ring


def burns_if(
    c: Cast,
    zone: int,
    amount: str | int,
    dtype: DamageType = DamageType.UNTYPED,
    *,
    ok: Callable[[int], bool] | None = None,
    until: When = When.ENCOUNTER,
) -> None:
    """`c.burns`, but only for some of the people standing in it.

    That method bites everybody, and a great many of these zones bite
    enemies only. The once-a-turn latch is the same one it keeps.
    """
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if struck.get(who) == c.world.round or (ok is not None and not ok(who)):
            return
        struck[who] = c.world.round
        bit = c.roll(amount) if isinstance(amount, str) else amount
        c.world.damage(c.me, who, bit, dtype, detail=f"{c.ref} zone")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bite(ev.actor)

    def dawn(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    c.watch(ZoneEntered, entered, until=until, on=c.me, label=f"{c.ref} bite")
    c.watch(TurnStart, dawn, until=until, on=c.me, label=f"{c.ref} bite dawn")


def burns_at_end(
    c: Cast,
    zone: int,
    amount: str | int,
    dtype: DamageType = DamageType.UNTYPED,
    *,
    ok: Callable[[int], bool] | None = None,
    until: When = When.ENCOUNTER,
) -> None:
    """"Any creature that **ends** its turn in the zone takes N."

    A different sentence from the one `c.burns` keeps -- that one is
    entering and starting -- and it is printed at least as often.
    """

    def dusk(ev: TurnEnd) -> None:
        who = ev.actor
        if ev.ghost or who not in c.world.zones.occupants(zone):
            return
        if ok is not None and not ok(who):
            return
        bit = c.roll(amount) if isinstance(amount, str) else amount
        c.world.damage(c.me, who, bit, dtype, detail=f"{c.ref} zone")

    c.watch(TurnEnd, dusk, until=until, on=c.me, label=f"{c.ref} bite dusk")


# -- windows measured on somebody else's turn -------------------------------


def at_end_of_its_next_turn(c: Cast, who: int, fn: Callable[[], None]) -> Effect:
    """Do this at the end of that creature's **next** turn, then stop.

    The hold is ended by hand on the first turn that ends rather than left
    to a duration: `When.EOTNT` expires on the same event, and which of the
    two goes first is not something a row should have to know.
    """
    held: list[Effect] = []

    def ending(ev: TurnEnd) -> None:
        if ev.actor != who or ev.ghost or not held:
            return
        fn()
        c.world.effects.end(held[0], "its next turn ended")

    held.append(
        c.watch(TurnEnd, ending, until=When.ENCOUNTER, on=who, label=f"{c.ref} window")
    )
    return held[0]


def during_its_next_turn(
    c: Cast, who: int, event: type[Event], fn: Callable[[Any], None]
) -> Effect:
    """Watch something for the length of that creature's next turn.

    "On its next turn the target takes damage when it attacks" is a window
    that opens now and shuts when the turn does, which no single duration
    names.
    """
    held = c.watch(event, fn, until=When.ENCOUNTER, on=who, label=f"{c.ref} window")

    def shut(ev: TurnEnd) -> None:
        if ev.actor != who or ev.ghost:
            return
        if not held.ended:
            c.world.effects.end(held, "its turn ended")

    closing = c.watch(TurnEnd, shut, until=When.ENCOUNTER, on=who, label=f"{c.ref} shut")
    held.on_end.append(
        lambda: c.world.effects.end(closing, "window closed") if not closing.ended else None
    )
    return held
