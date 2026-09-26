"""Psion, level 1.

Every augmentable row here is written at **Augment 0** -- the effect printed
before the first Augment line, which is a complete at-will on its own. The
engine has no power points, so the augment clauses are named in each
docstring rather than folded in or guessed at.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    FORT,
    INT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    Damage,
    DamageType,
    Keyword,
    Melee,
    MoveEnd,
    Position,
    Ranged,
    Summon,
    TurnStart,
    When,
    get,
    power,
    spread,
)

PSIONIC_IMPLEMENT = [Keyword.PSIONIC, Keyword.IMPLEMENT]
PSIONIC_FORCE = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.FORCE]
PSIONIC_PSYCHIC = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC]


@power(
    "p11269",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=FORT),
)
def p11269(c: Cast) -> None:
    """Augment 1 (push equal to Wisdom modifier) and Augment 2 (extra Wisdom
    damage plus prone) are dropped: no power points."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
        c.push(1)
        for foe in c.within(1, of=c.me, side="enemy"):
            if foe != c.target:
                c.push(1, on=foe)


@power(
    "p11270",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=REF),
)
def p11270(c: Cast) -> None:
    """Augments 1 and 2 (bigger dice, pull equal to Wisdom modifier) dropped.

    The printed Special -- usable unaugmented as a ranged basic attack -- has
    no header field to declare it, so it is not said here either.
    """
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
        c.pull(1)


@power(
    "p11271",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=REF),
)
def p11271(c: Cast) -> None:
    """The standing "use a minor action to push the target 1 square" is written
    as a sustain-minor hold with the push as its payout -- the same shape, and
    the only one that gives a minor action somewhere to go. The clause ending
    it when you finish your turn adjacent to the target is dropped."""
    victim = c.target
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.FORCE)

    def shove() -> None:
        if victim is not None and c.distance(victim) <= 5:
            c.push(1, on=victim)

    c.on_sustain(c.effect(c.ref, until=When.SUSTAIN, sustain=MINOR), shove)


@power(
    "p11272",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=FORT),
)
def p11272(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("3d6", c.int_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage("3d6", c.int_mod, dtype=DamageType.FORCE)

    spent = [False]

    def stirred(ev: MoveEnd) -> None:
        if ev.actor == victim and not spent[0]:
            spent[0] = True
            c.flat(5, dtype=DamageType.FORCE, on=victim)

    c.watch(MoveEnd, stirred, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "p13302",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=FORT),
)
def p13302(c: Cast) -> None:
    """Augment 1 (enemies only) and Augment 2 (bigger dice, and the target may
    land back inside the burst) are dropped."""
    victim = c.target
    if c.strike():
        c.damage("1d6", c.int_mod)
        burst = c.area()
        for sq in sorted(spread(burst, 1) - burst):
            if c.teleport(3, who=victim, to=sq):
                break


@power(
    "p13303",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.FORCE,
        Keyword.CONJURATION,
    ],
)
def p13303(c: Cast) -> None:
    """Three clauses are dropped. "Any enemy that enters the shard's space"
    cannot happen: `c.conjure` occupies its square, so a zone laid over that
    one square would never have anybody in it -- a dead clause rather than a
    weak one. The minor-action attack made *through* the shard is printed as a
    second block under this same id and so has no ref of its own. Augment 1
    (moving the shard 5 squares) needs power points.
    """
    c.conjure(until=When.EONT, sustain=None)


@power(
    "p13305",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p13305(c: Cast) -> None:
    """Augment 1 (the target also cannot shift) is dropped; the printed
    Augment 2 line in the spec is a bare Target line with no effect."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed(until=When.EONT)


@power(
    "p13308",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(INT, vs=FORT),
)
def p13308(c: Cast) -> None:
    """The once-per-round secondary -- slide the held target 10 squares and
    attack somebody it passes -- is printed as a second block under this same
    id, so there is no ref to declare it under. Only the primary is here."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "p13310",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(INT, vs=FORT),
)
def p13310(c: Cast) -> None:
    """The squares around the target becoming *lightly* obscured is dropped:
    `c.zone` only knows `blocks_sight`, which is total obscurement."""
    if c.strike():
        c.damage("2d8", c.int_mod)
    else:
        c.half_damage("2d8", c.int_mod)
    c.ongoing(5)


@power(
    "p13312",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.CHARM,
    ],
    attack=Attack(INT, vs=WILL),
)
def p13312(c: Cast) -> None:
    """The save-ends hold *is* the watch: one effect on the target, so one save
    ends both the subjection and the free swing it pays out."""
    victim = c.target
    if victim is None:
        return

    def neighbours() -> list[int]:
        return [x for x in c.within(1, of=victim, side="any") if x not in (victim, c.me)]

    if c.strike():
        c.damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)

        def each_turn(ev: TurnStart) -> None:
            if ev.actor != c.me:
                return
            near = neighbours()
            foe = c.choose(near, f"{c.ref}: whom the target strikes") if near else None
            if foe is not None:
                c.grant_attack(victim, on=foe)

        c.watch(TurnStart, each_turn, until=When.SAVE_ENDS, on=victim, label=c.ref)
    else:
        c.half_damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
        near = neighbours()
        if near:
            foe = c.choose(near, f"{c.ref}: whom the target strikes")
            if foe is not None:
                penalty = -2 if foe in c.allies() else 0
                c.grant_attack(victim, on=foe, attack_bonus=penalty)


@power(
    "p13462",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.LIGHTNING,
        Keyword.CONJURATION,
    ],
    attack=Attack(INT, vs=REF),
)
def p13462(c: Cast) -> None:
    """The second block is a No Action that follows automatically at the start
    of your next turn, so it is folded in here rather than left for a ref that
    does not exist. The mote is not despawned when it goes off -- its own
    duration takes it away at the end of that turn instead. Augments 1 and 2
    (a pull toward the centre, bigger dice) are dropped."""
    mote = c.conjure(until=When.EONT, sustain=None, aura=1)
    if not mote:
        return

    def where() -> Position | None:
        return c.world.get(mote, Position)

    def creep(ev: TurnStart) -> None:
        pos = where()
        if pos is None or ev.actor == c.me:
            return
        if ev.actor in c.in_squares(spread({pos.square}, 1), side="any"):
            c.slowed(on=ev.actor, until=When.EOT)

    def detonate(ev: TurnStart) -> None:
        pos = where()
        if pos is None or ev.actor != c.me:
            return
        for who in c.in_squares(spread({pos.square}, 3), side="any"):
            if c.strike(on=who):
                c.damage("1d6", c.int_mod, dtype=DamageType.LIGHTNING, on=who)

    c.watch(TurnStart, creep, until=When.EONT, label=c.ref)
    c.watch(TurnStart, detonate, until=When.EONT, label=c.ref)


@power(
    "p8226",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8226(c: Cast) -> None:
    """Augment 1 (no opportunity attacks) and Augment 2 (bigger dice, penalty
    equal to Charisma modifier) are dropped."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p8227",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8227(c: Cast) -> None:
    """Augment 1 (the invisibility lasts a turn longer) is dropped."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.invisible(to=c.target, on=c.me, until=When.SONT)


@power(
    "p8228",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8228(c: Cast) -> None:
    """Augments 1 and 2 (penalties to Will, then to all defences) are dropped,
    as is the Special that makes the unaugmented form a ranged basic attack --
    there is no header field for that."""
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.PSYCHIC)


@power(
    "p8229",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8229(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("3d8", c.int_mod, dtype=DamageType.PSYCHIC)
    c.vulnerable(5, DamageType.PSYCHIC, until=When.SAVE_ENDS)


@power(
    "p8230",
    level=1,
    cls="psion",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8230(c: Cast) -> None:
    """The secondary is an Effect line -- it happens whether or not the primary
    landed -- and rolls the same attack, so it is folded in here."""
    primary = c.target
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.ongoing(5, DamageType.PSYCHIC)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.ongoing(3, DamageType.PSYCHIC)
    for foe in c.within(1, of=primary, side="enemy"):
        if foe != primary and c.strike(on=foe):
            c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC, on=foe)
            c.ongoing(5, DamageType.PSYCHIC, on=foe)


@power(
    "p13311",
    level=1,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=PSIONIC_PSYCHIC,
    summon=Summon(
        speed=8,
        attack=Attack(INT, vs=AC),
        damage=Damage("1d10", "int", dtype=DamageType.PSYCHIC),
    ),
)
def p13311(c: Cast) -> None:
    """Augment 0, as everywhere in this class. Augment 1 gives the servant a
    further command and is dropped with the rest of the augment clauses."""
    c.summon_inline(get(c.ref).summon, at=c.origin)
