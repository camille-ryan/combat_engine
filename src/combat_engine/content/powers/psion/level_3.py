"""Psion, level 3. Augment 0 throughout; dropped augments are named per row."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    EACH_CREATURE,
    FORT,
    INT,
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
    MoveEnd,
    Position,
    Ranged,
    Target,
    TurnStart,
    When,
    distance,
    power,
    spread,
)

PSIONIC_IMPLEMENT = [Keyword.PSIONIC, Keyword.IMPLEMENT]
PSIONIC_FORCE = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.FORCE]
PSIONIC_PSYCHIC = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC]


@power(
    "p11275",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.FIRE,
        Keyword.ZONE,
    ],
    attack=Attack(INT, vs=REF),
)
def p11275(c: Cast) -> None:
    """The zone is the target's own square. "Starts its turn adjacent to it"
    is dropped -- widening the zone to the ring would also make entering the
    ring burn, which the printed line does not say. Augment 1 (the zone is
    totally obscured) and Augment 2 are dropped."""
    where = c.there
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FIRE)
    c.hazard(
        {where}, c.wis_mod, DamageType.FIRE, until=When.EONT, sustain=None
    )


@power(
    "p11276",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=FORT),
)
def p11276(c: Cast) -> None:
    """Augment 1 (cannot shift) and Augment 2 (bigger dice, prone) dropped."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FORCE)
        c.slowed(until=When.EONT)


@power(
    "p13317",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p13317(c: Cast) -> None:
    """"The next saving throw it makes" is `once=True` on the penalty.
    Augments 1 and 2 (an attack penalty as well) are dropped."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty("save", 2, until=When.EONT, once=True)


@power(
    "p13318",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(INT, vs=FORT),
)
def p13318(c: Cast) -> None:
    """"Moves more than 2 squares" is measured from where it stood when its
    turn began, so the square it started in has to be caught on `TurnStart`;
    `MoveEnd` alone only says where it stopped. Augment 1 (fear, and a
    penalty for standing next to it) and Augment 2 are dropped."""
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.int_mod)
    began: dict[str, object] = {}

    def began_turn(ev: TurnStart) -> None:
        pos = c.world.get(victim, Position) if ev.actor == victim else None
        if pos is not None:
            began["at"] = pos.square

    def stopped(ev: MoveEnd) -> None:
        start = began.get("at")
        if ev.actor == victim and start is not None and distance(start, ev.at) > 2:
            began.pop("at")
            c.flat(5, on=victim)

    c.watch(TurnStart, began_turn, until=When.EOTNT, on=victim, label=c.ref)
    c.watch(MoveEnd, stopped, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "p13319",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=REF),
)
def p13319(c: Cast) -> None:
    """Augment 1 (any move other than a shift) and Augment 2 (up to three
    targets) are dropped."""
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
    far = max(1, c.speed_of(victim) // 2)
    began: dict[str, object] = {}

    def began_turn(ev: TurnStart) -> None:
        pos = c.world.get(victim, Position) if ev.actor == victim else None
        if pos is not None:
            began["at"] = pos.square

    def stopped(ev: MoveEnd) -> None:
        start = began.get("at")
        if ev.actor == victim and start is not None and distance(start, ev.at) > far:
            began.pop("at")
            c.prone(on=victim)

    c.watch(TurnStart, began_turn, until=When.EOTNT, on=victim, label=c.ref)
    c.watch(MoveEnd, stopped, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "p13320",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.CONJURATION,
    ],
)
def p13320(c: Cast) -> None:
    """Only the conjuration. The opportunity attack made through the anomaly
    is printed as a second block under this same id, so it has no ref of its
    own to be declared under."""
    c.conjure(until=When.EONT, sustain=None)


@power(
    "p8233",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=Target(side="enemy", count=1),
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p8233(c: Cast) -> None:
    """"Adjacent to an enemy" is an enemy of *yours*, so the target is shoved
    next to one of its own and made to swing. If it already stands beside one,
    no slide is needed. Augments 1 and 2 (a damage bonus, a longer slide and a
    daze) are dropped."""
    victim = c.target
    if victim is None or not c.strike():
        return
    beside = [e for e in c.within(1, of=victim, side="enemy") if e != victim]
    foe = beside[0] if beside else None
    if foe is None:
        for cand in c.enemies():
            if cand == victim:
                continue
            pos = c.world.get(cand, Position)
            if pos is None:
                continue
            if any(c.slide(1, on=victim, to=sq) for sq in sorted(spread({pos.square}, 1))):
                foe = cand
                break
    if foe is not None:
        c.grant_attack(victim, on=foe, attack_bonus=c.cha_mod)


@power(
    "p8234",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8234(c: Cast) -> None:
    """Augment 1 (penalty equal to Charisma modifier) and Augment 2 are
    dropped."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty(FORT, 2, until=When.EONT)
