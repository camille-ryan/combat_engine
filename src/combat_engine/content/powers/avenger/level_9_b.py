"""Avenger, level 9: daily attacks, second half.

The twelve that are not the shared Prerequisite swing. Three want a word.

`p7014` counts "each square it enters willingly" off `Moved`, one step at a
time, gated by whether a `MoveStart` was announced for that creature and has
not yet been closed by a `MoveEnd`. Forced movement announces neither --
`movement.forced` steps directly -- so "willingly" is exactly the difference
between a move that opened a window and one that did not, and nothing else
has to be enumerated.

`p7015`'s Aftereffect is a hold ending *by a saving throw* rather than by a
clock, and `Effect.on_end` is handed no reason. `EffectExpired` carries one,
so the aftereffect is a separate watcher reading `why == "saved"`; hanging
it on the hold itself would not work, because `Effects.end` unsubscribes an
effect's own listeners before announcing that it ended.

`p6936` regains a spent healing surge, and there is no `Cast` method for
that -- `c.spend_surge` only goes the other way. It is done on the `Health`
component; see the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Health,
    Hit,
    Keyword,
    Melee,
    Moved,
    MoveEnd,
    Ranged,
    TurnEnd,
    TurnStart,
    When,
    Window,
    by_melee,
    distance,
    power,
)
from combat_engine.engine.events import DamageApplied, EffectExpired, MoveStart
from combat_engine.engine.query import squares as squares_of

from .level_9 import DIVINE_IMPLEMENT, DIVINE_WEAPON, beside, nearest
from .oath import is_oath, sworn


@power(
    "p10406",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p10406(c: Cast) -> None:
    """One watcher for both halves of the Effect: the sworn creature is
    slowed and everybody else is shoved, and which it is has to be asked
    when the turn ends rather than now."""
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)
    if not c.first:
        return
    me = c.me

    def parting(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies() or not c.adjacent(ev.actor):
            return
        if sworn(c.world, me, ev.actor):
            c.slowed(on=ev.actor, until=When.EOTNT)
        elif c.may("push it 3 squares", who=me):
            c.push(3, on=ev.actor)

    c.watch(TurnEnd, parting, until=When.ENCOUNTER, on=me, label=f"{c.ref} ward")


@power(
    "p12297",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p12297(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.wis_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(3), c.wis_mod, dtype=DamageType.RADIANT)
    if not is_oath(c, victim):
        return
    for foe in sorted(f for f in c.within(5, side="enemy") if f != victim):
        c.grants_advantage(on=foe, until=When.EONT)


@power(
    "p3601",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.ZONE],
    attack=Attack(WIS, vs=AC),
)
def p3601(c: Cast) -> None:
    """"The zone moves with it, remaining centred on it" is what `c.aura`
    does: it follows anything with a position, and the target has one. A
    fixed `c.zone` would sit where the creature used to be.

    Concealment is not a state the engine holds, so the two sentences about
    it have nothing to attach to. See the report.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if victim is not None and c.first:
        c.aura(1, on=victim, until=When.ENCOUNTER, label=f"{c.ref} shadows")


@power(
    "p3602",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p3602(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
        c.save(on=c.me, bonus=5)
    else:
        c.half_damage(c.w(3), c.wis_mod)
        c.save(on=c.me)


@power(
    "p3636",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p3636(c: Cast) -> None:
    if c.first:
        c.shift(5)
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if c.last:
        c.shift(5)


@power(
    "p3638",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p3638(c: Cast) -> None:
    """"If the target moves on its turn" is remembered rather than answered:
    the shift is owed at the *end* of that turn, so the move sets a flag and
    the turn boundary spends it.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if victim is None or not c.first:
        return
    stirred: list[int] = []
    me = c.me

    def stir(ev: MoveEnd) -> None:
        if ev.actor == victim and c.turn_of() == victim:
            stirred.append(1)

    def chase(ev: TurnEnd) -> None:
        if ev.actor != victim or not stirred:
            return
        stirred.clear()
        if not c.may("shift 3 squares closer", who=me):
            return
        gap = c.distance(victim)
        closer = sorted(
            sq
            for sq in c.world.reachable_squares(me, 3)
            if min(distance(sq, theirs) for theirs in squares_of(c.world, victim)) < gap
        )
        dest = c.choose(closer, "where you follow") if closer else None
        if dest is not None:
            c.shift(3, to=dest)

    c.watch(MoveEnd, stir, until=When.ENCOUNTER, on=me, label=f"{c.ref} watch")
    c.watch(TurnEnd, chase, until=When.ENCOUNTER, on=me, label=f"{c.ref} chase")


@power(
    "p6936",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p6936(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)
    health = c.world.get(victim, Health) if victim is not None else None
    if health is None or health.hp > 0:
        return
    mine = c.world.get(c.me, Health)
    if mine is not None:
        mine.surges += 1
        c.note("a spent healing surge comes back")


@power(
    "p7014",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=AC),
)
def p7014(c: Cast) -> None:
    """Both listeners hang on one hold, so the single printed saving throw
    ends the whole sentence. The miss line is the same sentence on a clock
    instead of a save, which is the only difference between the two."""
    victim = c.target
    landed = c.strike()
    if landed:
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.PSYCHIC)
    if victim is None:
        return
    hold = c.effect(
        f"{c.ref} thorns",
        until=When.SAVE_ENDS if landed else When.EONT,
        on=victim,
    )
    if hold is None:
        return
    walking = [False]

    def opened(ev: MoveStart) -> None:
        if ev.actor == victim:
            walking[0] = True

    def closed(ev: MoveEnd) -> None:
        if ev.actor == victim:
            walking[0] = False

    def bite(ev: Moved) -> None:
        if ev.actor == victim and walking[0]:
            c.flat(5, dtype=DamageType.PSYCHIC, on=victim)

    bus = c.world.bus
    hold.subs.append(bus.on(MoveStart, opened, window=Window.BEFORE, owner=c.me))
    hold.subs.append(bus.on(Moved, bite, owner=c.me))
    hold.subs.append(bus.on(MoveEnd, closed, owner=c.me))


@power(
    "p7015",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p7015(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        c.half_damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
        return
    c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
    c.pull(1)
    if victim is None:
        return
    hold = c.effect(f"{c.ref} glare", until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    mark = str(hold)

    def dawn(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost and c.adjacent(victim):
            c.flat(10, dtype=DamageType.RADIANT, on=victim)

    hold.subs.append(c.world.bus.on(TurnStart, dawn, owner=c.me))

    def after(ev: EffectExpired) -> None:
        same = ev.actor == victim and ev.why == "saved" and ev.what == mark
        if same and c.adjacent(victim):
            c.push(2, on=victim)

    c.watch(
        EffectExpired, after, until=When.ENCOUNTER, on=c.me, once=True,
        label=f"{c.ref} after {victim}",
    )


@power(
    "p7016",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7016(c: Cast) -> None:
    """The burn is an Effect and lands on a miss too. "Whenever the target
    takes this ongoing damage" is matched on the detail string the clock
    stamps each tick with, which names the effect and nothing else."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    if victim is None:
        return
    burn = c.ongoing(5)
    if burn is None:
        return
    mark = str(burn)

    def ache(ev: DamageApplied) -> None:
        if ev.target != victim or ev.detail != mark:
            return
        c.bonus(
            "damage", max(0, c.wis_mod), until=When.EONT, on=c.me, once=True,
            when=lambda ctx: sworn(c.world, c.me, ctx.get("target")),
        )

    burn.subs.append(c.world.bus.on(DamageApplied, ache, owner=c.me))


@power(
    "p7017",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7017(c: Cast) -> None:
    """The secondary rolls longhand: one header carries one attack line, and
    this one's second is a different defence in a burst of its own."""
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)
    for foe in sorted(f for f in c.within(1, side="enemy") if f != victim):
        if c.attack(c.wis_, FORT, on=foe):
            c.push(c.roll("1d4"), on=foe)


@power(
    "p7018",
    level=9,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[
        *DIVINE_IMPLEMENT, Keyword.PSYCHIC, Keyword.TELEPORTATION,
    ],
    attack=Attack(WIS, vs=WILL),
)
def p7018(c: Cast) -> None:
    """The teleport is on both branches, so it is done once after the swing
    rather than written twice."""
    victim = c.target
    landed = c.strike()
    if landed:
        c.damage("2d10", c.wis_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d10", c.wis_mod, dtype=DamageType.PSYCHIC)
    if victim is None:
        return
    spots = beside(c, c.me)
    if spots:
        dest = nearest(c, spots)
        c.teleport(distance(c.here, dest), who=victim, to=dest)
    if landed:
        c.dazed(until=When.SAVE_ENDS)
    me = c.me

    def press(ev: Hit) -> None:
        if ev.attacker != me or ev.target != victim:
            return
        if not by_melee(c.world, me, ev) or not c.may("close in", who=me):
            return
        c.shift(1)
        room = beside(c, me)
        if room:
            here = nearest(c, room)
            c.slide(max(1, c.distance(victim)), on=victim, to=here)

    c.watch(Hit, press, until=When.ENCOUNTER, on=me, label=f"{c.ref} press")
