"""Druid, level 5: the daily attacks that leave something standing.

`p2702` is an area wall with teeth, written the way `cleric/level_9.py:p60`
writes its own: the run of squares is laid in the body, and the bite and the
burn share one once-a-turn latch rather than having one each.

`p4898` and `p5050` both print a standing clause about the druid's own
square -- "enemies can't shift while adjacent to you", "any enemy that makes
a melee attack against you takes damage" -- and the two are written
differently on purpose. The first is a property of standing next to the
druid, which is an aura; the second is a response to an attack, which is a
watch.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    DamageType,
    Hit,
    Keyword,
    Melee,
    PowerUsed,
    Ranged,
    TurnStart,
    UpTo,
    When,
    ZoneEntered,
    get,
    power,
    spread,
)
from combat_engine.engine.events import ZoneExited
from combat_engine.engine.query import alive, can_act
from combat_engine.engine.zones import Zone

from .forms import aura_hold, in_beast_form

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
BEAST_FORM = "you must be in beast form"


@power(
    "p2702",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.CONJURATION],
)
def p2702(c: Cast) -> None:
    """Rough going costs a fixed one extra square and there is nowhere to
    name a different number, so the printed three extra is one. The wall's
    height has nowhere to go either: the board is flat.

    Line of sight through it is `blocks_sight`, which shelters what is
    behind it rather than sparing whoever is standing next to a square.
    """
    anchors = sorted(
        sq for sq in spread({c.here}, 10) if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, f"{c.ref}: where the vines climb")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-4, 4)]
    line = [sq for sq in run if c.world.grid.inside(sq)]
    if not line:
        return
    wall = c.zone(
        line, label=c.ref, until=When.SUSTAIN, sustain=MINOR,
        difficult=True, blocks_sight=True,
    )
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.damage("1d10", c.wis_mod, on=who)
        c.ongoing(5, on=who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == wall:
            bite(ev.actor)

    def dawn(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(wall):
            bite(ev.actor)

    held = c.world.get(wall, Zone)
    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(TurnStart, dawn),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
    c.note(f"{c.ref}: entering costs three extra squares, and rough going costs one")


@power(
    "p2789",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p2789(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.dazed()


@power(
    "p4898",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=FORT),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p4898(c: Cast) -> None:
    """"Slowed and can't shift (save ends both)" is one hold: `c.rooted` is
    the second half, and it hangs on the first so one saving throw answers
    the printed line rather than two."""
    if c.strike():
        c.damage("2d8", c.wis_mod)
        hold = c.slowed(until=When.SAVE_ENDS)
        still = c.rooted(until=When.SAVE_ENDS)
        if hold is not None and still is not None:
            hold.on_end.append(lambda: c.world.effects.end(still, "the hold ended"))
    else:
        c.half_damage("2d8", c.wis_mod)
    if not c.first:
        return
    foes = set(c.enemies())
    aura_hold(
        c, 1,
        lambda who: who in foes,
        lambda who: c.rooted(on=who, until=When.ENCOUNTER),
    )


@power(
    "p5049",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5049(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.wis_mod)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.wis_mod)
        c.slowed()


@power(
    "p5050",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5050(c: Cast) -> None:
    """"While you are in beast form **and able to take actions**" is two
    questions asked at the moment the enemy swings, not when the row was
    used: a stunned druid stops biting back."""
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.ongoing(5)
    else:
        c.half_damage("1d8", c.wis_mod)
    me = c.me
    foes = set(c.enemies())

    def thorns(ev: Hit) -> None:
        if ev.target != me or ev.attacker not in foes:
            return
        declared = get(ev.power)
        if declared is None or declared.reach.kind != "melee":
            return
        if in_beast_form(c.world, me) and can_act(c.world, me):
            c.flat(max(1, c.con_mod), on=ev.attacker)

    c.watch(Hit, thorns, until=When.ENCOUNTER, on=me, label=f"{c.ref} thorns")


@power(
    "p9656",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p9656(c: Cast) -> None:
    """The zone punishes two different things -- leaving it, and reaching
    out of it -- so it watches the way out and the whole target list of any
    attack made from inside. `PowerUsed` is the only event carrying that
    list, and "a creature outside it" is a question about where the targets
    are standing rather than who they are.
    """
    if c.strike():
        c.damage("2d6", c.wis_mod)
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.wis_mod)
        c.immobilized()
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.ENCOUNTER)

    def left(ev: ZoneExited) -> None:
        if ev.zone == zone and alive(c.world, ev.actor):
            c.flat(5 + c.wis_mod, on=ev.actor)

    def reached(ev: PowerUsed) -> None:
        inside = c.world.zones.occupants(zone)
        if ev.actor not in inside:
            return
        declared = get(ev.power)
        if declared is None or not declared.is_attack:
            return
        if any(who not in inside for who in ev.targets):
            c.flat(5 + c.wis_mod, on=ev.actor)

    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} out")
    c.watch(PowerUsed, reached, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} reach")
