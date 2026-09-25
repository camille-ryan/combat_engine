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
    EACH_ENEMY,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Ranged,
    TurnStart,
    When,
    power,
    spread,
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


@power(
    "p16263",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.CONJURATION],
)
def p16263(c: Cast) -> None:
    """Two conjurations, each with a one-square aura that bites.

    `burn` is the cold; the slow that goes with it has to be hung off turn
    starts by hand, because a burn deals damage and nothing else. Sustaining
    rolls a d6 to add or remove a tentacle -- a conjuration cannot be made
    from inside a sustain handler, so sustaining simply keeps the pair.

    The secondary attack printed beneath has no id of its own in the spec,
    so there is no row to declare and it is not written.
    """
    room = sorted(
        sq
        for sq in spread({c.here}, 5)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not room:
        return
    arms = [
        c.conjure(
            at=where,
            label=f"{c.ref} {n}",
            until=When.SUSTAIN,
            sustain=MINOR,
            aura=1,
            burn=(5, DamageType.COLD),
        )
        for n, where in enumerate(room[:2])
    ]

    def chill(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == c.me:
            return
        if any(c.adjacent_to(arm, ev.actor) for arm in arms):
            c.slowed(on=ev.actor, until=When.EOTNT)

    c.watch(TurnStart, chill, until=When.ENCOUNTER)


@power(
    "p4076",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CON, vs=WILL),
)
def p4076(c: Cast) -> None:
    if c.target is not None:
        if c.strike():
            c.damage("1d10", c.con_mod, dtype=DamageType.PSYCHIC)
            c.curse()
        else:
            c.half_damage("1d10", c.con_mod, dtype=DamageType.PSYCHIC)
    if not c.last:
        return

    def spite(ev: AttackDeclared) -> None:
        if ev.target == c.me and c.cursed(ev.attacker):
            c.flat(c.int_mod, dtype=DamageType.PSYCHIC, on=ev.attacker)

    c.watch(AttackDeclared, spite, until=When.ENCOUNTER)


@power(
    "p6858",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.ZONE],
    attack=Attack(CON, vs=REF),
)
def p6858(c: Cast) -> None:
    """`c.burns` is the once-a-turn bite the printed line asks for, and it
    rolls its dice per bite rather than once when the zone was made.
    Concealment is not denied -- nothing suppresses it -- and the Ugar pact
    boon has no leg to ask for."""
    if c.target is not None and c.strike():
        c.damage("1d10", c.con_mod, dtype=DamageType.FIRE)
    if not c.last:
        return
    area = c.area()
    if area:
        light = c.zone(area, label=c.ref, until=When.ENCOUNTER)
        c.burns(light, "1d10", DamageType.FIRE)


@power(
    "p6859",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
)
def p6859(c: Cast) -> None:
    """The choice at the start of each turn is the target's, which is what
    `c.may` asks by default -- it puts the question to `c.target`."""
    victim = c.target
    if c.strike():
        c.damage("2d6", c.con_mod, dtype=DamageType.PSYCHIC)
        hold = c.effect(f"{c.ref}: whispering")
        if victim is None or hold is None:
            return

        def whisper(ev: TurnStart) -> None:
            if ev.ghost or ev.actor != victim:
                return
            if c.may("go quiet rather than hurt", who=victim):
                c.dazed(on=victim, until=When.SOTNT)
            else:
                c.flat(2 * c.con_mod, dtype=DamageType.PSYCHIC, on=victim)

        hold.subs.append(c.world.bus.on(TurnStart, whisper))
        return
    # The miss deals the same dice, which is unusual and is what it prints.
    c.damage("2d6", c.con_mod, dtype=DamageType.PSYCHIC)
    c.dazed()


@power(
    "p6954",
    level=5,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=WILL),
)
def p6954(c: Cast) -> None:
    """The ally pays and the target bleeds for it, so the offer is put to the
    ally -- `c.may` asks whoever `who=` names -- and the surge is spent
    without healing anybody, which is what "loses a healing surge" means."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.NECROTIC)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.NECROTIC)
    near = sorted(f for f in c.allies() if c.distance(f) <= 5)
    for friend in near:
        if c.may("spend a surge for more of it", who=friend) and c.spend_surge(on=friend):
            c.damage("2d8", dtype=DamageType.NECROTIC)
            return
