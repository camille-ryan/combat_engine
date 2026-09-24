"""Warlord, level 9: the daily attacks.

`p1114`'s free swings deal no damage -- "its target takes no damage, but
falls prone" -- and there is no way to ask for an attack without one, so the
damage is refused where the engine offers it: `DamageRolled` is a proposal
and cancelling it is how "the attack deals no damage" is written. The
listener is put on and taken off around each granted swing so it silences
that ally's blow and nothing else's.

`p137` is a charge the row makes itself: `c.charge_at` would use the
creature's basic attack or a named row, and the row it wants is this one, so
the walk and the flag are set by hand and `c.strike` follows. Its standing
Effect -- an ally charging as an immediate reaction -- has no vocabulary and
is written down rather than approximated.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Health,
    Hit,
    Keyword,
    Melee,
    Window,
    distance,
    power,
)
from combat_engine.engine.events import DamageRolled
from combat_engine.engine.movement import walk
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _friends_within(c: Cast, squares: int) -> list[int]:
    """"Each ally within N squares of you" -- never the warlord itself."""
    return sorted(a for a in c.within(squares, side="ally") if a != c.me)


def _close_in(c: Cast, friend: int, squares_: int) -> int | None:
    """Walk an ally into reach of somebody and say who.

    The walk is aimed rather than handed to the decider, which knows nothing
    about the swing that follows it and will as soon retreat -- the same
    trap `ranger/level_5.py` records for a shift. An ally already standing
    next to an enemy stays where it is: the three squares are a printed
    "up to".
    """
    near = sorted(c.within(1, of=friend, side="enemy"))
    if near:
        return c.choose(near, "who that ally trips")
    paths = c.world.reachable_paths(friend, squares_)
    for where in sorted(paths):
        reachable = sorted(
            foe
            for foe in c.enemies()
            if min(distance(where, sq) for sq in squares_of(c.world, foe)) <= 1
        )
        if not reachable:
            continue
        walk(c.world, friend, paths[where])
        return c.choose(reachable, "who that ally trips")
    return None


@power(
    "p1114",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1114(c: Cast) -> None:
    """The free action is a printed "can", so each ally is asked; the three
    squares are walked before the swing because the ally has to reach
    something to hit it, and the pool it swings at is whatever it is standing
    next to once it has.
    """
    if not c.strike():
        c.half_damage(c.w(3), c.str_mod)
        c.prone()
        return
    c.damage(c.w(3), c.str_mod)
    c.prone()
    for friend in _friends_within(c, 10):
        if not c.may("move and swing", who=friend):
            continue
        victim = _close_in(c, friend, 3)
        if victim is not None:
            _trip(c, friend, victim)


def _trip(c: Cast, friend: int, victim: int) -> None:
    """One granted basic attack that knocks down instead of hurting."""
    floored: list[int] = []

    def mute(ev: DamageRolled) -> None:
        if ev.source == friend:
            ev.cancel("the blow only knocks it down")

    def landed(ev: Hit) -> None:
        if ev.attacker == friend:
            floored.append(ev.target)

    subs = [
        c.world.bus.on(DamageRolled, mute, window=Window.BEFORE),
        c.world.bus.on(Hit, landed),
    ]
    try:
        c.grant_attack(friend, on=victim)
    finally:
        for sub in subs:
            c.world.bus.off(sub)
    for who in floored:
        c.prone(on=who)


@power(
    "p1115",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1115(c: Cast) -> None:
    """"If you reduce the target to 0 hit points with this attack" is read off
    the target's hit points straight after the damage, rather than watched
    for: `Dropped` also fires for a creature something else finished.

    The temporary hit points are an Effect line, so the allies get them on a
    miss too -- just without the rider.
    """
    victim = c.target
    dropped = False
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        health = c.world.get(victim, Health) if victim is not None else None
        dropped = health is not None and health.hp <= 0
    amount = 15 + (c.cha_mod if dropped else 0)
    pool = _friends_within(c, 10)
    for _ in range(2):
        friend = c.choose(pool, "who is steadied", optional=True) if pool else None
        if friend is None:
            return
        pool.remove(friend)
        c.temp_hp(amount, on=friend)


@power(
    "p137",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p137(c: Cast) -> None:
    """`c.charge` is the flag `use(..., charge=True)` would have set, and it
    is what puts `charge` on the attack events and in both modifier contexts
    -- which is what every charge rider reads.
    """
    victim = c.target
    if victim is None:
        return
    c.run_at(victim)
    c.charge = True
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    c.note(
        f"{c.ref}: for the rest of the encounter, an ally within 5 squares of where "
        "you start a charge could charge the same creature as an immediate reaction "
        "-- there is no way to make somebody else charge"
    )
