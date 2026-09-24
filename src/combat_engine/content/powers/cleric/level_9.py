"""Cleric, level 9: daily attacks.

Two of the four leave something standing. `p60` prints an area **wall**,
which is not one of the shapes a `Range` can be, so its distance is declared
as the printed ten squares and the run of squares is laid in the body --
`level_6.py`'s arrangement for the wizard's fog. Its height has nowhere to
go: the board is flat.

`p930`'s soldiers are conjurations rather than summoned creatures: there is
no row for them to be, and `c.summon` wants one. That costs two clauses --
they occupy their squares and nothing walks through them, where the printed
line lets creatures pass -- and it means their opportunity attack is written
out here. A conjuration carries no `Health`, so `movement` never counts it
among the mover's neighbours and no `OpportunityWindow` is opened for it.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    NO_TARGET,
    REF,
    STANDARD,
    STR,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    MoveEnd,
    Ranged,
    TurnStart,
    When,
    ZoneEntered,
    power,
    spread,
)
from combat_engine.engine.events import MoveStart
from combat_engine.engine.query import hidden_from
from combat_engine.engine.zones import Zone

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


@power(
    "p180",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
)
def p180(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.wis_mod, dtype=DamageType.FIRE)
        c.ongoing(5 + c.wis_mod, DamageType.FIRE)
    else:
        c.half_damage("2d10", c.wis_mod, dtype=DamageType.FIRE)


@power(
    "p60",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*DIVINE_IMPLEMENT, Keyword.CONJURATION],
)
def p60(c: Cast) -> None:
    """The bite and the ongoing damage are one watcher rather than `c.burns`
    plus a second: both halves are the same sentence and share the printed
    once-per-turn latch, and two latches counting separately is two chances
    for them to disagree.
    """
    anchors = sorted(
        sq for sq in spread({c.here}, 10) if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, "where the wall stands")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-2, 3)]
    blades = [sq for sq in run if c.world.grid.inside(sq)]
    if not blades:
        return
    wall = c.zone(
        blades, label=c.ref, until=When.SUSTAIN, sustain=MINOR, difficult=True
    )
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.damage("3d6", c.wis_mod, on=who)
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


@power(
    "p929",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.HEALING],
    attack=Attack(STR, vs=FORT),
)
def p929(c: Cast) -> None:
    """Regeneration is not something the engine holds, so it is written out:
    healing at the start of each of the cleric's turns, and only while
    bloodied.

    The Effect block runs before the swing rather than after it, because the
    swing is skipped for an enemy that cannot be seen and the Effect is owed
    whether or not there is anything in the burst at all.
    """
    if c.first:
        me = c.me

        def regenerate(ev: TurnStart) -> None:
            if ev.actor == me and not ev.ghost and c.bloodied(on=me):
                c.heal(5, on=me)

        c.watch(
            TurnStart,
            regenerate,
            until=When.ENCOUNTER,
            on=me,
            label=f"{c.ref} regeneration",
        )
        for friend in sorted({me, *c.in_squares(c.area(), side="ally")}):
            c.bonus(AC, 2, on=friend, until=When.ENCOUNTER, kind="power")
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
        c.push(1)


@power(
    "p930",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.CONJURATION],
)
def p930(c: Cast) -> None:
    """Each soldier is given a speed of three, which is what `c.conjure`
    turns into "move it with a move action". The printed three squares are a
    budget shared between the two of them and a conjuration's speed is its
    own, so a caster who walks both spends six; there is nowhere to hang a
    shared pool.

    The opportunity attack is armed here rather than left to the policy. It
    reads the move from both ends -- who each soldier was standing next to
    when the move began, and who is out of reach when it stops -- because
    `LeaveSquare` does not say where the mover is going, and it is capped at
    one swing per soldier per turn, which is what an opportunity action is.
    """
    room = sorted(
        sq
        for sq in spread({c.here}, 10)
        if c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and sq != c.here
    )
    soldiers: list[int] = []
    for _ in range(2):
        where = c.choose(
            [sq for sq in room if sq not in soldiers], "where a soldier stands"
        )
        if where is None:
            break
        room.remove(where)
        made = c.conjure(
            where, label=c.ref, until=When.ENCOUNTER, sustain=None, speed=3
        )
        if made:
            soldiers.append(made)
    if not soldiers:
        return

    beside: dict[int, set[int]] = {s: set() for s in soldiers}
    swung: dict[int, tuple[int, int | None]] = {}

    def began(ev: MoveStart) -> None:
        for post in soldiers:
            if c.adjacent_to(post, ev.actor):
                beside[post].add(ev.actor)

    def ended(ev: MoveEnd) -> None:
        now = (c.world.round, c.turn_of())
        for post in soldiers:
            ran = ev.actor in beside[post]
            beside[post].discard(ev.actor)
            if not ran or c.adjacent_to(post, ev.actor):
                continue
            if ev.actor not in c.enemies() or swung.get(post) == now:
                continue
            swung[post] = now
            if c.attack(c.wis_, REF, on=ev.actor, from_=post):
                c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT, on=ev.actor)

    c.watch(MoveStart, began, until=When.ENCOUNTER, label=f"{c.ref} watches")
    c.watch(MoveEnd, ended, until=When.ENCOUNTER, label=f"{c.ref} strikes")
