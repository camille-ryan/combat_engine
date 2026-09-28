"""Psion, level 1.

The augmentable rows here ask `augment` how many power points this use is
bought with and branch on the answer. A clause that rewrites the **header**
-- a wider target line, a burst where the base is a single target -- is the
one shape a body cannot honour, because targeting happens before the body
runs; those are named in the docstring and recorded in `docs/blocked.json`.
"""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
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
    AttackDeclared,
    Augment,
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
    Window,
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
    """Augment 1 pushes the target by Wisdom instead of 1 square; the enemies
    beside you are pushed 1 either way. Augment 2 adds Wisdom to the damage and
    knocks the target prone."""
    spent = augment(c)
    if c.strike():
        extra = c.wis_mod if spent == 2 else 0
        c.damage("1d8", c.int_mod + extra, dtype=DamageType.FORCE)
        if spent == 2:
            c.prone()
        c.push(c.wis_mod if spent == 1 else 1)
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
    """Both augments raise the dice and pull by Wisdom rather than 1 square.

    The printed Special -- usable unaugmented as a ranged basic attack -- has
    no header field to declare it, so it is not said here either.
    """
    spent = augment(c)
    if c.strike():
        c.damage(("1d8", "1d10", "2d10")[spent], c.int_mod, dtype=DamageType.FORCE)
        c.pull(1 if spent == 0 else c.wis_mod)


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
    """Both augments narrow the burst to enemies, which a body can honour by
    leaving anybody else alone -- a *narrower* target line is the one kind the
    header does not have to be rewritten for. Augment 2 also raises the dice
    and lets the target land inside the burst rather than only outside it."""
    spent = augment(c)
    victim = c.target
    if spent and victim not in c.enemies():
        return
    if c.strike():
        c.damage("2d6" if spent == 2 else "1d6", c.int_mod)
        burst = c.area()
        ring = spread(burst, 1) if spent == 2 else spread(burst, 1) - burst
        for sq in sorted(ring):
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
    """Two clauses are dropped. "Any enemy that enters the shard's space"
    cannot happen: `c.conjure` occupies its square, so a zone laid over that
    one square would never have anybody in it -- a dead clause rather than a
    weak one. The minor-action attack made through the shard is `p13303b`,
    which the importer now gives a ref of its own; Augment 2 is that block's
    dice, so it belongs to that row rather than this one.

    Augment 1 is the shard's speed: `speed=` is how far its creator may move
    it with a move action, which is exactly what the clause grants.
    """
    c.conjure(until=When.EONT, sustain=None, speed=5 if augment(c, 1) else 0)


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
    augments=(
        Augment(1),
        Augment(2, reach=AreaBurst(1, 10), target=EACH_CREATURE),
    ),
)
def p13305(c: Cast) -> None:
    """Augment 1 roots the target as well.

    Augment 2 swaps the single shot for an area burst against each creature
    in it, which is the header, so it is declared there and the points are
    spent before the burst is aimed. It prints no Hit line of its own, so
    the base one applies to everybody caught -- and the root is Augment 1's
    alone."""
    spent = augment(c, 1, 2)
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.slowed(until=When.EONT)
        if spent == 1:
            c.rooted(until=When.EONT)


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
    attack somebody it passes -- is `p13308b`, gated on this hold standing on
    somebody. Only the primary is here."""
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
    """The second block is `p13462b`, a No Action whose burst is centred on
    the square the mote occupied -- a close burst is centred on the creature
    using it, so the row is left out and the detonation stays folded in here.
    The mote is not despawned when it goes off -- its own duration takes it
    away at the end of that turn instead.

    The augment is bought when the mote is conjured and spends itself a turn
    later, when the burst goes off: Augment 1 drags one of the creatures it
    caught toward the mote's square, Augment 2 raises the dice."""
    spent = augment(c)
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

    dragged = [False]

    def detonate(ev: TurnStart) -> None:
        pos = where()
        if pos is None or ev.actor != c.me:
            return
        for who in c.in_squares(spread({pos.square}, 3), side="any"):
            if c.strike(on=who):
                dice = "2d6" if spent == 2 else "1d6"
                c.damage(dice, c.int_mod, dtype=DamageType.LIGHTNING, on=who)
                if spent == 1 and not dragged[0]:
                    dragged[0] = c.pull(1, on=who, anchor=pos.square) > 0

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
    """Augment 2 raises the dice and makes the penalty Charisma rather than 2.

    Augment 1 stops the target making opportunity attacks, which no method
    says: `c.cannot_attack` bars every attack. `AttackDeclared` carries
    `opportunity` as a plain attribute, so refusing the declaration when that
    is set is the whole clause and nothing wider."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        c.damage("2d6" if spent == 2 else "1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", c.cha_mod if spent == 2 else 2, until=When.EONT)
        if spent == 1 and victim is not None:

            def refuse(ev: AttackDeclared) -> None:
                if ev.attacker == victim and getattr(ev, "opportunity", False):
                    ev.cancel("cannot make opportunity attacks")

            c.watch(
                AttackDeclared, refuse, until=When.EONT, window=Window.BEFORE,
                on=victim, label=c.ref,
            )


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
    augments=(
        Augment(1),
        Augment(2, reach=AreaBurst(1, 10), target=EACH_CREATURE),
    ),
)
def p8227(c: Cast) -> None:
    """Augment 1 holds the invisibility a turn longer.

    Augment 2 is an area burst against each creature in it, which is the
    header, so it is declared there; its dice are doubled and its
    invisibility is the base card's shorter one, which is what the card
    prints under that heading rather than "as above"."""
    spent = augment(c, 1, 2)
    if c.strike():
        c.damage("2d6" if spent == 2 else "1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        c.invisible(
            to=c.target, on=c.me, until=When.EONT if spent == 1 else When.SONT
        )


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
    """Augment 1 is a penalty to Will equal to Charisma; Augment 2 raises the
    dice and puts that penalty on every defence. The Special that makes the
    unaugmented form a ranged basic attack still has no header field."""
    spent = augment(c)
    if c.strike():
        c.damage("2d10" if spent == 2 else "1d10", c.int_mod, dtype=DamageType.PSYCHIC)
        if spent == 1:
            c.penalty(WILL, c.cha_mod, until=When.EONT)
        elif spent == 2:
            for d in (AC, FORT, REF, WILL):
                c.penalty(d, c.cha_mod, until=When.EONT)


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
    """Augment 1 gives the servant a third command -- an opportunity action
    that makes a Heal check on a dying ally. `Summon` declares a standard and
    an opportunity attack and nothing else, so there is nowhere to put it."""
    c.summon_inline(get(c.ref).summon, at=c.origin)
