"""Avenger, level 7: encounter attacks.

Three judgements recur here.

The oath is a hold rather than a relation (see `oath.py`), so a row whose
printed **Target** is the oath target reads it with `oath_target(c)` rather
than taking whatever the dispatcher offered. `p10405` is the only one of
those; it finds no oath target on a board where nobody swore, and its
printed Effect -- the shove -- still happens, which is the card.

Four rows print a rider naming a build this chargen does not offer. Each is
gated on `c.build(...)` all the same, with the ungated half left as what an
avenger without that build gets. This is the warlord precedent recorded in
`warlord/level_7_b.py`.

`p7011` is `EACH_OTHER` rather than `EACH_CREATURE`: a close burst does not
catch the creature standing at its centre, and `EACH_CREATURE` would have
had the avenger rolling against its own Will.

`p3517` watches `MoveEnd` rather than `MoveStart`: the slide it grants has
to happen after the move it answers. Forced movement announces neither, so
the watcher cannot answer its own slide and there is no loop to guard.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Event,
    Health,
    Hit,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    Trigger,
    When,
    World,
    both,
    distance,
    hits_me,
    power,
    spread,
)
from combat_engine.engine.events import AdjacencyGained, DamageApplied
from combat_engine.engine.query import squares as squares_of

from .oath import is_oath, oath_target, swear, sworn

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


def _beside(c: Cast, who: int) -> list[tuple[int, int]]:
    """Every empty square adjacent to a creature. "To a square adjacent to
    you" names a destination, and a destination has to be somewhere it can
    actually stand."""
    theirs = squares_of(c.world, who)
    return sorted(
        sq
        for sq in spread(theirs, 1) - theirs
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    )


def _nearest(c: Cast, spots: list[tuple[int, int]]) -> tuple[int, int]:
    return min(spots, key=lambda sq: (distance(c.here, sq), sq))


def _gap(c: Cast, who: int, sq: tuple[int, int]) -> int:
    """How far a square is from a creature, measured off its whole footprint."""
    return min(distance(sq, theirs) for theirs in squares_of(c.world, who))


@power(
    "p10405",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p10405(c: Cast) -> None:
    """The shove is an Effect and lands whether or not there is anybody to
    swing at; the swing goes at the oath target, which is the printed
    Target rather than the one the dispatcher picked."""
    for foe in sorted(f for f in c.within(1, side="enemy") if not is_oath(c, f)):
        c.push(3, on=foe)
    victim = oath_target(c)
    if victim is not None and c.strike(on=victim):
        c.damage(c.w(2), c.wis_mod, on=victim)


_OTHER_HITS_ME = "an enemy other than your oath of enmity target hits you"


def _not_my_oath(world: World, me: int, ev: Event) -> bool:
    return not sworn(world, me, getattr(ev, "attacker", None))


@power(
    "p11040",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=FORT),
    trigger=_OTHER_HITS_ME,
    on=Trigger(Hit, when=both(hits_me, _not_my_oath), text=_OTHER_HITS_ME),
)
def p11040(c: Cast) -> None:
    """The triggering enemy is read off the event rather than trusted to be
    whoever the dispatcher aimed at."""
    foe = getattr(c.trigger, "attacker", None) or c.target
    if foe is None or not c.strike(on=foe):
        return
    c.damage("2d8", c.wis_mod, dtype=DamageType.LIGHTNING, on=foe)
    c.push(3, on=foe)
    victim = oath_target(c)
    if victim is not None:
        c.pull(3, on=victim)


@power(
    "p12296",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.ILLUSION],
    attack=Attack(WIS, vs=REF),
)
def p12296(c: Cast) -> None:
    """"Invisible to all enemies other than the target" is one hold per
    enemy: `c.invisible` names a single watcher."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d8", c.wis_mod)
    swear(c, victim)
    for foe in sorted(f for f in c.enemies() if f != victim):
        c.invisible(to=foe, on=c.me, until=When.EONT)


@power(
    "p2943",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p2943(c: Cast) -> None:
    if c.first:
        c.phasing(on=c.me, until=When.EOT)
        c.shift(2 + c.dex_mod if c.build("pursuit") else 3)
    if c.strike():
        c.damage(c.w(2), c.wis_mod)


@power(
    "p3517",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p3517(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d8", c.wis_mod)

    def drift(ev: MoveEnd) -> None:
        if ev.actor == victim and c.may("slide it 2 squares", who=c.me):
            c.slide(2, on=victim)

    c.watch(MoveEnd, drift, until=When.EONT, on=c.me, label=f"{c.ref} drift")


@power(
    "p3522",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=AC),
)
def p3522(c: Cast) -> None:
    """"Each enemy within 2 squares of the target" counts the target itself,
    which is within nought of it."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(1), c.wis_mod)
    far = 1 + c.int_mod if c.build("retribution") else 2
    for foe in sorted(c.within(2, of=victim, side="enemy")):
        c.teleport(far, who=foe)


@power(
    "p3523",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=AC),
)
def p3523(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.wis_mod)
    spots = sorted(
        {sq for foe in c.enemies() for sq in _beside(c, foe) if distance(c.here, sq) <= 10}
    )
    dest = c.choose(spots, "where you appear") if spots else None
    if dest is not None:
        c.teleport(distance(c.here, dest), to=dest)


@power(
    "p6935",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.NECROTIC, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p6935(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(1), c.wis_mod)
    health = c.world.get(victim, Health)
    if health is None or health.hp > 0:
        return
    for foe in sorted(f for f in c.within(1, of=victim, side="enemy") if f != victim):
        c.flat(5, dtype=DamageType.NECROTIC, on=foe)
    for foe in sorted(c.within(1, side="enemy")):
        c.flat(5, dtype=DamageType.RADIANT, on=foe)


@power(
    "p7009",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(WIS, vs=AC),
)
def p7009(c: Cast) -> None:
    """"Or if you have reduced your oath of enmity target to 0 hit points
    during this encounter" is read back off the log: a blow of this
    avenger's that took somebody to nothing, where that somebody is still
    carrying this avenger's oath. Nothing else in the engine remembers it.
    """
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(1), c.wis_mod)
    health = c.world.get(victim, Health) if victim is not None else None
    felled = health is not None and health.hp <= 0
    if not felled:
        felled = any(
            isinstance(e, DamageApplied)
            and e.source == c.me
            and e.hp <= 0
            and sworn(c.world, c.me, e.target)
            for e in c.world.bus.log
        )
    if felled and c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)
    c.bonus("damage", c.wis_mod, until=When.EONT, on=c.me, once=True)


@power(
    "p7010",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.CHARM],
    attack=Attack(WIS, vs=AC),
)
def p7010(c: Cast) -> None:
    """The shove names its destination rather than its direction: "to a
    square adjacent to at least one of your allies" is an instruction, and
    a push left to the decider goes wherever it likes."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2), c.wis_mod)
    far = 1 + c.int_mod if c.build("unity") else 1
    spots = sorted(
        {
            sq
            for friend in c.allies()
            for sq in _beside(c, friend)
            if _gap(c, victim, sq) <= far
        }
    )
    dest = c.choose(spots, "where the target is driven") if spots else None
    if dest is not None:
        c.push(far, on=victim, to=dest)


@power(
    "p7011",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p7011(c: Cast) -> None:
    """The oath target is the only one that takes damage; everything else in
    the burst is moved and nothing more, which is why the header carries no
    damage line."""
    victim = c.target
    if victim is None or not c.strike():
        return
    if not is_oath(c, victim):
        c.push(3)
        return
    c.damage("2d10", c.wis_mod, dtype=DamageType.RADIANT)
    spots = _beside(c, c.me)
    if spots:
        c.pull(max(1, c.distance(victim)), on=victim, to=_nearest(c, spots))


@power(
    "p7012",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=REF),
)
def p7012(c: Cast) -> None:
    """"An enemy can take this damage only once per turn" is kept per enemy
    against the round and whose turn it is, which is the only pair that
    identifies a turn."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)
        spots = _beside(c, c.me)
        if spots:
            dest = _nearest(c, spots)
            c.teleport(distance(c.here, dest), who=victim, to=dest)

    paid: dict[int, tuple[int, int | None]] = {}
    me = c.me

    def closed(ev: AdjacencyGained) -> None:
        if ev.actor != me or ev.mover != ev.other or ev.other not in c.enemies():
            return
        now = (c.world.round, c.turn_of())
        if paid.get(ev.other) == now:
            return
        paid[ev.other] = now
        c.flat(5, dtype=DamageType.RADIANT, on=victim)

    c.watch(AdjacencyGained, closed, until=When.EONT, on=me, label=f"{c.ref} ward")


@power(
    "p7699",
    level=7,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7699(c: Cast) -> None:
    """"No other creatures" means nobody but the two of you, so the caster
    and the target are each left out of the other's count. Asked before the
    swing, which is when the attack is made."""
    victim = c.target
    crowd = [f for f in c.within(1, side="any") if f not in (c.me, victim)]
    if victim is not None:
        crowd += [f for f in c.within(1, of=victim, side="any") if f not in (c.me, victim)]
    extra = c.dex_mod if c.build("pursuit") and not crowd else 0
    if not c.strike():
        return
    c.damage(c.w(2), c.wis_mod + extra)
    if victim is None:
        return
    pool = [victim, *sorted(f for f in c.within(5, of=victim, side="enemy") if f != victim)]
    who = c.choose(pool, "who is pinned in place")
    if who is not None:
        c.immobilized(on=who, until=When.EONT)
