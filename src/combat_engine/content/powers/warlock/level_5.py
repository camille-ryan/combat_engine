"""Warlock, level 5: the daily attacks.

Two of the four print the same unusual shape: "the target is subjected to
<something> (save ends). Until the effect ends, you can use a minor action
once per round, starting on your next turn, to ...". That is a save-ends
effect carrying a `sustain_cost`, which `actions._sustaining` offers exactly
once a round for as long as the effect lives and never on the turn it was
applied -- all three clauses, for free. `c.effect` does not take the cost,
so the hold is applied through `world.effects` directly and the payout half
goes on with `c.on_sustain`.

A creature's "adjacent allies" are, read from this side of the board, the
enemies standing next to it.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    CON,
    DAILY,
    EACH_CREATURE,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Ranged,
    When,
    power,
)
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _its_allies(c: Cast, victim: int) -> list[int]:
    """"One of its adjacent allies of your choice"."""
    return sorted(e for e in c.within(1, of=victim, side="enemy") if e != victim)


@power(
    "p1320",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p1320(c: Cast) -> None:
    """The hit line and the minor action are the same sentence twice, so one
    closure serves both.

    `c.grant_attack` with no `ref` rolls whatever that creature's own basic
    attack is, which is what "a melee basic attack" means for a monster that
    has replaced its.
    """
    victim = c.target
    landed = c.strike()
    if landed:
        c.damage("2d10", c.cha_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d10", c.cha_mod, dtype=DamageType.PSYCHIC)
    if victim is None:
        return

    def turn_on_a_friend() -> None:
        near = _its_allies(c, victim)
        friend = c.choose(near, "which of its allies it turns on")
        if friend is not None:
            c.grant_attack(victim, on=friend)

    if landed:
        turn_on_a_friend()
    # The Effect line lands on a miss too.
    madness = c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label="p1320", sustain_cost=MINOR
    )
    c.on_sustain(madness, turn_on_a_friend)


@power(
    "p1343",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CON, vs=REF),
)
def p1343(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.con_mod, dtype=DamageType.FIRE)
    # "The targets take ongoing 5 fire" is an Effect line: everything the
    # burst covered burns, hit or not.
    c.ongoing(5, DamageType.FIRE)


@power(
    "p1472",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p1472(c: Cast) -> None:
    """One damage roll shared by everybody it reaches, which is how a line
    naming a single expression and several creatures reads.

    The splash is "each of *your* enemies adjacent to it", so an ally caught
    in the same press is not bitten.
    """
    victim = c.target
    if c.strike():
        c.damage("3d10", c.cha_mod)
    else:
        c.half_damage("3d10", c.cha_mod)
    if victim is None:
        return

    def bite() -> None:
        amount = c.roll("1d10")
        c.flat(amount, on=victim)
        for foe in _its_allies(c, victim):
            c.flat(amount, on=foe)

    fangs = c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label="p1472", sustain_cost=MINOR
    )
    c.on_sustain(fangs, bite)


@power(
    "p62",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    # No primary target line at all: the whole row is its Effect and the
    # secondary attack that sustaining it makes.
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(CON, vs=FORT),
)
def p62(c: Cast) -> None:
    """Darkness is a zone rather than a `c.hazard` because only a zone can
    say it blocks line of sight; `c.burns` is what gives one the teeth
    `c.hazard` would have built in.

    The bite is rolled once, when the zone is made, because a zone carries a
    number and not an expression -- the same compromise the conjured sphere
    of flame makes.
    """
    area = c.area()
    if not area:
        return
    dark = c.zone(
        area, label="p62", until=When.SUSTAIN, blocks_sight=True, sustain=MINOR
    )
    c.burns(dark, c.roll("2d10"), DamageType.NECROTIC)

    def secondary() -> None:
        # "Each creature within the zone" -- allies included, as printed.
        for who in c.world.zones.occupants(dark):
            if c.strike(on=who):
                c.damage("1d6", c.con_mod, dtype=DamageType.NECROTIC, on=who)

    zone = c.world.get(dark, Zone)
    c.on_sustain(zone.effect if zone else None, secondary)
