"""Druid, level 10: the utilities.

Two rows are absent. One commands a summoned creature and the summoning
rows themselves could not be written; the other makes four berries somebody
carries off and eats later. Both are in the report.

**`c.form` shapes the caster and nobody else.** `p9666` turns the whole
party Tiny, so its holds are applied per target through `world.effects`
directly -- which is what `c.form` does, minus the one argument it lacks.

`p13528` prints regeneration, which the engine does not hold: it is written
out as healing at the start of that creature's own turns, and only while it
is bloodied -- the same arrangement `cleric/level_9.py:p929` makes.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Event,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    TurnStart,
    UpTo,
    When,
    World,
    get,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.events import ForcedMove
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.zones import Zone

from .forms import current_form, ends_with, in_beast_form, zone_hold

PRIMAL = [Keyword.PRIMAL]
BEAST_FORM = "you must be in beast form"


def _shoved_near_me(world: World, me: int, ev: Event) -> bool:
    """"You or an ally within 10 squares is pulled, pushed, or slid."""
    who = getattr(ev, "target", None)
    if who is None:
        return False
    if who == me:
        return True
    if team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 10


def _area_or_close(world: World, me: int, ev: Event) -> bool:
    if not targets_me(world, me, ev):
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.reach.kind in ("close_burst", "close_blast", "area_burst")


def _fly(c: Cast, who: int, squares_: int) -> int:
    """Cross ground on the wing. The board is flat, so a flight is a move
    with the mode set -- which is what makes it ignore what is underfoot."""
    c.mode("fly", squares_, on=who, until=When.EOT)
    return c.move(squares_, who=who)


@power(
    "p10373",
    level=10,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.POLYMORPH],
)
def p10373(c: Cast) -> None:
    """Breathing underwater and being unable to move on land both want an
    element the board does not have; the swim speed is what is left."""
    shape = c.form(
        modes={"swim": c.speed_of()}, until=When.ENCOUNTER, revert=FREE, label=c.ref
    )
    ends_with(c, shape, c.cannot_attack(on=c.me, until=When.ENCOUNTER))


@power(
    "p13528",
    level=10,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[*PRIMAL, Keyword.HEALING],
)
def p13528(c: Cast) -> None:
    who = c.target
    if who is None:
        return

    def dawn(ev: TurnStart) -> None:
        if ev.actor == who and not ev.ghost and c.bloodied(who):
            c.heal(5, on=who)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=who, label=f"{c.ref} mends")


@power(
    "p13529",
    level=10,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p13529(c: Cast) -> None:
    """`c.save` asks the caster unless told whose throw it is."""
    who = c.target
    if who is not None:
        c.save(on=who, bonus=2)


@power(
    "p14515",
    level=10,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.POLYMORPH],
)
def p14515(c: Cast) -> None:
    """Becoming Small has nowhere to go -- `Size` is read and never written
    -- and the Perception bonus is a check. The flight is real."""
    shape = c.form(modes={"fly": 8}, until=When.ENCOUNTER, revert=FREE, label=c.ref)
    ends_with(c, shape, c.cannot_attack(on=c.me, until=When.ENCOUNTER))
    c.note(f"{c.ref}: the form is Small, and nothing here changes a creature's size")


@power(
    "p14516",
    level=10,
    cls="druid",
    usage=DAILY,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p14516(c: Cast) -> None:
    """The sustain has a payout -- somebody flies again -- and without
    `c.on_sustain` that half of the printed line goes nowhere. The hold is
    applied through `world.effects` because `c.effect` names no sustain
    cost, and "Sustain Move" is the whole of what this one is.
    """
    who = c.target
    if who is None:
        return
    _fly(c, who, 5)
    hold = c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=c.ref, sustain_cost=MOVE
    )

    def again() -> None:
        pool = sorted({c.me, *c.allies()})
        chosen = c.choose(pool, f"{c.ref}: who flies") if pool else None
        if chosen is not None:
            _fly(c, chosen, 5)

    c.on_sustain(hold, again)


@power(
    "p16123",
    level=10,
    cls="druid",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(1),
    target=UpTo(2, "ally"),
    keywords=PRIMAL,
)
def p16123(c: Cast) -> None:
    """The defence bonus is gated on the attack being an opportunity one,
    which the attack context carries; without that key it would apply to
    everything for the rest of the turn."""
    who = c.target
    if who is None:
        return
    for d in (AC, FORT, REF, WILL):
        c.bonus(
            d, 4, on=who, until=When.EOT, kind="power",
            when=lambda ctx: bool(ctx.get("opportunity")),
        )
    _fly(c, who, 6)


@power(
    "p2733",
    level=10,
    cls="druid",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=PRIMAL,
    trigger="you or an ally within 10 squares of you is pulled, pushed, or slid",
    on=Trigger(
        ForcedMove,
        when=_shoved_near_me,
        text="you or an ally within 10 squares is pulled, pushed, or slid",
    ),
)
def p2733(c: Cast) -> None:
    """"Unaffected by the forced movement" is refusing the event, which only
    an interrupt may do -- and `ForcedMove` is one of the five the engine
    honours a refusal on."""
    c.cancel()


@power(
    "p2734",
    level=10,
    cls="druid",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.TELEPORTATION],
)
def p2734(c: Cast) -> None:
    """Somewhere else entirely is `Condition.REMOVED`, which is exactly
    "cannot act and cannot move". The board keeps the square the druid left
    -- nothing here lifts a creature off the grid -- so the reappearance is
    a teleport of up to ten squares from it when the hold ends.

    "Or as a move action before then" is the printed early exit, which is
    what `drop_cost` on a form names; a plain condition has no such door, so
    the clock is the only way out.
    """
    hold = c.condition(Condition.REMOVED, until=When.EONT, on=c.me)
    if hold is not None:
        hold.on_end.append(lambda: c.teleport(10))


@power(
    "p2844",
    level=10,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p2844(c: Cast) -> None:
    """Resistance is written onto `Defences` and cannot be gated the way a
    modifier can, so "while you are in beast form" is held by tying it to
    the shape: it goes when the shape goes. A druid that changes back and
    then changes again does not get it a second time, which the printed
    line would allow.
    """
    ends_with(
        c, current_form(c),
        c.resist(max(1, c.con_mod), until=When.ENCOUNTER, on=c.me),
    )


@power(
    "p4894",
    level=10,
    cls="druid",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=PRIMAL,
    trigger="you are targeted by an area or a close attack",
    on=Trigger(
        AttackDeclared,
        when=_area_or_close,
        text="you are targeted by an area or a close attack",
    ),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p4894(c: Cast) -> None:
    """The swap happens before the burst resolves, which is what makes it
    worth doing: an interrupt runs while the attack is still being declared.

    The partner is chosen here rather than taken from `c.target`. A
    triggered row is aimed by the dispatcher only when it takes a single
    enemy, and this one takes "one creature" -- so left alone it aimed at
    the druid, which is a swap with itself.
    """
    pool = sorted(who for who in c.within(1, side="other") if who != c.me)
    if not pool:
        return
    foes = set(c.enemies())
    pool.sort(key=lambda who: (who not in foes, who))
    other = c.choose(pool, f"{c.ref}: who stands where you were")
    if other is not None:
        c.swap(other)


@power(
    "p5057",
    level=10,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=SELF,
    keywords=[*PRIMAL, Keyword.ZONE],
)
def p5057(c: Cast) -> None:
    """The vulnerability follows the enemies in and out rather than being
    laid once, and the sustain grows the zone -- both halves of the printed
    Sustain line, where the clock alone is only one of them."""
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR, difficult=True)
    foes = set(c.enemies())
    zone_hold(
        c, zone,
        lambda who: who in foes,
        lambda who: c.vulnerable(
            5, DamageType.COLD, until=When.ENCOUNTER, on=who
        ),
    )
    held = c.world.get(zone, Zone)
    if held is None:
        return
    grown = [2]

    def spread_out() -> None:
        if grown[0] >= 5:
            return
        grown[0] += 1
        held.squares = frozenset(spread(held.squares, 1))
        c.world.zones.refresh()

    c.on_sustain(held.effect, spread_out)


@power(
    "p51",
    level=10,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=SELF,
    keywords=[*PRIMAL, Keyword.ZONE],
)
def p51(c: Cast) -> None:
    """The saving-throw bonus is against ongoing fire and acid *only*, which
    the save context can answer: it carries the effect being saved against,
    and an ongoing burn carries its own type."""
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER)
    friends = {c.me, *c.allies()}

    def burning(ctx: dict[str, Any]) -> bool:
        effect = ctx.get("effect")
        burn = getattr(effect, "ongoing", None)
        return burn is not None and burn[1] in (DamageType.FIRE, DamageType.ACID)

    def shelter(who: int) -> Any:
        c.resist(10, DamageType.FIRE, until=When.ENCOUNTER, on=who)
        c.resist(10, DamageType.ACID, until=When.ENCOUNTER, on=who)
        return c.bonus(
            "save", 2, on=who, until=When.ENCOUNTER, kind="power", when=burning
        )

    zone_hold(c, zone, lambda who: who in friends, shelter)


@power(
    "p9666",
    level=10,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[*PRIMAL, Keyword.POLYMORPH],
)
def p9666(c: Cast) -> None:
    """One shape per target, applied through `world.effects` because
    `c.form` shapes the caster and takes no `on=`. Each target may drop it
    as a minor action, which is what `drop_cost` names -- the same door
    `c.form` puts on its own.
    """
    who = c.target
    if who is None:
        return
    shape = c.world.effects.apply(
        who, c.me, When.EONT, label=c.ref, drop_cost=MINOR
    )
    for hold in (
        c.cannot_attack(on=who, until=When.EONT),
        c.bonus(AC, 2, on=who, until=When.EONT, kind="power"),
        c.bonus(REF, 2, on=who, until=When.EONT, kind="power"),
    ):
        if hold is not None:
            shape.on_end.append(
                lambda h=hold: c.world.effects.end(h, "the form ended")
            )
    if c.first:
        c.note(f"{c.ref}: +5 to Stealth, and a Sustain Minor that would hold every target's form")
