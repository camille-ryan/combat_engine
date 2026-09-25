"""Druid, level 3: the encounter attacks.

Two of these leave ground behind whose rider is not the "enters or starts
its turn there" latch `c.burns` keeps, so they use the two variants in
`forms.py` instead of hand-rolling a third and a fourth.

**Cover from a zone is `blocks_sight` and nothing else.** `p14507` prints
superior cover against ranged attacks that target AC or Reflex, and
`p9653` prints plain cover for creatures inside as well as behind. The
engine has one lever -- a zone whose squares block -- so both use it and
each says in its docstring which half of its printed line that lever cannot
reach.

Three rows print a build rider and the class table has one build; the base
line is what is written. See `level_1_c.py`.
"""

from __future__ import annotations

from combat_engine.engine import (
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
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
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    PowerUsed,
    Ranged,
    TurnEnd,
    UpTo,
    When,
    ZoneEntered,
    power,
    spread,
)
from combat_engine.engine.events import ZoneExited

from .forms import (
    burns_at_end,
    fork_mod,
    hit_anybody,
    in_beast_form,
)

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
BEAST_FORM = "you must be in beast form"


@power(
    "p14505",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.FORCE, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p14505(c: Cast) -> None:
    """"Constitution or Dexterity modifier" is the fork with no leg to stand
    on; `forms.fork_mod` takes the larger and says so."""
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.FORCE)
    if not c.first:
        return
    area = c.area()
    if area:
        zone = c.zone(area, label=c.ref, until=When.EONT)
        burns_at_end(c, zone, fork_mod(c), DamageType.FORCE, until=When.EONT)


@power(
    "p14506",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.POISON],
    attack=Attack(WIS, vs=REF),
)
def p14506(c: Cast) -> None:
    """The slow is an Effect line -- "each target is slowed" -- so a target
    the burst missed is slowed all the same. Printed close burst 2."""
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.POISON)
    c.slowed()


@power(
    "p14507",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p14507(c: Cast) -> None:
    """An eight-square wall, laid in the body; a wall is not a `Range`.

    The cover it gives is `blocks_sight`, the one lever a zone has. That is
    wider than the printed line twice over -- it shelters against melee as
    well as ranged, and against every defence rather than AC and Reflex --
    and narrower once, since the grade it produces is whatever the grid
    works out rather than superior.
    """
    anchors = sorted(
        sq for sq in spread({c.here}, 10) if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, f"{c.ref}: where the wall stands")
    if anchor is None:
        return
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i) for i in range(-4, 4)]
    line = [sq for sq in run if c.world.grid.inside(sq)]
    if not line:
        return
    c.zone(line, label=c.ref, until=When.EONT, blocks_sight=True)
    for who in sorted(c.in_squares(line, side="enemy")):
        if c.strike(on=who):
            c.damage("2d6", c.wis_mod, on=who)
            if c.may("slide the target", who=c.me):
                c.slide(1, on=who)


@power(
    "p2669",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.COLD],
    attack=Attack(WIS, vs=FORT),
)
def p2669(c: Cast) -> None:
    """The Primal Guardian rider -- a push of Constitution squares as well --
    is a build the class table does not have."""
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.COLD)
        c.prone()


@power(
    "p2689",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[
        *PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.LIGHTNING, Keyword.THUNDER,
        Keyword.ZONE,
    ],
    attack=Attack(WIS, vs=REF),
)
def p2689(c: Cast) -> None:
    """The penalty follows the enemies in and out of the zone rather than
    being laid and re-laid, and the thunder is on the way *out*, which is
    neither half of what `c.burns` latches."""
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.LIGHTNING)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT)
    foes = set(c.enemies())
    inside: dict[int, object] = {}

    def entered(ev: ZoneEntered) -> None:
        if ev.zone != zone or ev.actor not in foes or ev.actor in inside:
            return
        held = c.penalty("attack", 2, on=ev.actor, until=When.EONT)
        if held is not None:
            inside[ev.actor] = held

    def left(ev: ZoneExited) -> None:
        if ev.zone != zone or ev.actor not in foes:
            return
        held = inside.pop(ev.actor, None)
        if held is not None:
            c.world.effects.end(held, "left the thunder")
        c.flat(5, dtype=DamageType.THUNDER, on=ev.actor)

    c.watch(ZoneEntered, entered, until=When.EONT, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.EONT, on=c.me, label=f"{c.ref} out")
    for standing in c.world.zones.occupants(zone):
        if standing in foes:
            held = c.penalty("attack", 2, on=standing, until=When.EONT)
            if held is not None:
                inside[standing] = held


@power(
    "p4865",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=FORT),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p4865(c: Cast) -> None:
    """The destination is named outright rather than left to the decider:
    "to a square in the blast or adjacent to it" is an instruction, and with
    nobody playing the decider takes the lowest-sorted square on the board.
    """
    area = c.area()
    landed = bool(c.strike())
    if landed:
        c.damage("2d6", c.wis_mod)
    if not c.last or not (landed or hit_anybody(c)) or not area:
        return
    room = [
        sq
        for sq in c.world.reachable_squares(c.me, 4)
        if sq in area or spread({sq}, 1) & area
    ]
    if room:
        c.shift(4, to=sorted(room)[0])


@power(
    "p5047",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5047(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.slide(2)


@power(
    "p5048",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5048(c: Cast) -> None:
    """The shift comes between the two attacks, which is the whole point of
    the row: the second target is found from where the druid ends up."""
    first = c.target
    if c.strike():
        c.damage("1d6", c.wis_mod)
        c.dazed()
    c.shift(2)
    pool = sorted(foe for foe in c.within(1, side="enemy") if foe != first)
    second = c.choose(pool, f"{c.ref}: who the second bite catches") if pool else None
    if second is None:
        return
    if c.strike(on=second):
        c.damage("1d6", c.wis_mod, on=second)
        c.dazed(on=second)


@power(
    "p9649",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p9649(c: Cast) -> None:
    """The shift is printed as an Effect *before* the attack, so it happens
    whether or not there was ever anything to bite. The Primal Predator
    rider -- a second shift afterwards -- is a build the class table lacks.
    """
    c.shift(3)
    if c.strike():
        c.damage("2d8", c.wis_mod)


@power(
    "p9651",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA],
    attack=Attack(WIS, vs=REF),
)
def p9651(c: Cast) -> None:
    """Not a beast form row -- it has no such keyword -- but its rider only
    pays while the druid is in one, so the shape is asked at the moment an
    enemy swings rather than when the row was used.

    "Hits or misses you" is both events, which is why there are two watches:
    declaring one of them would look finished and be half a rule.
    """
    if c.strike():
        c.damage("2d6", c.wis_mod)
    if not c.first:
        return
    me = c.me
    foes = set(c.enemies())

    def recoil(ev: Hit | Miss) -> None:
        if ev.target != me or ev.attacker not in foes:
            return
        if in_beast_form(c.world, me):
            c.flat(5, on=ev.attacker)

    c.watch(Hit, recoil, until=When.EONT, on=me, label=f"{c.ref} hit")
    c.watch(Miss, recoil, until=When.EONT, on=me, label=f"{c.ref} miss")


@power(
    "p9652",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.THUNDER],
    attack=Attack(WIS, vs=WILL),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p9652(c: Cast) -> None:
    """The slide is owed at the **end** of the turn, not when the attack
    happens, so the offence is remembered and paid off later. `PowerUsed`
    carries the whole target list, which is what "doesn't include you"
    needs; an attack event is announced once per target and cannot answer it.

    The Primal Guardian rider -- 2 + Constitution squares -- is a build the
    class table does not have.
    """
    if not c.strike():
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.THUNDER)
    c.mark()
    victim = c.target
    if victim is None:
        return
    me = c.me
    owed: list[int] = []

    def swung(ev: PowerUsed) -> None:
        if ev.actor == victim and me not in ev.targets:
            owed.append(c.world.round)

    def dusk(ev: TurnEnd) -> None:
        if ev.actor == victim and not ev.ghost and owed:
            owed.clear()
            c.slide(3, on=victim)

    c.watch(PowerUsed, swung, until=When.EONT, on=me, label=f"{c.ref} ignored")
    c.watch(TurnEnd, dusk, until=When.EONT, on=me, label=f"{c.ref} slide")


@power(
    "p9653",
    level=3,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p9653(c: Cast) -> None:
    """The thorns bite whoever enters, which is `c.burns` exactly -- it also
    bites at the start of a turn spent inside, which this printed line does
    not, and that is the one place the method is wider than the row.

    The cover is `blocks_sight`, which shelters what is *behind* the zone
    and not what is standing in it; the printed line grants both.
    """
    if c.strike():
        c.damage("2d6", c.wis_mod)
        c.slowed()
    if not c.first:
        return
    area = c.area()
    if area:
        zone = c.zone(area, label=c.ref, until=When.EONT, blocks_sight=True)
        c.burns(zone, 5)
