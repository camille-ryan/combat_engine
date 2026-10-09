"""Psion, level 3. A clause that only changes the dice or adds a rider is
bought in the body with `augment`; a clause that **rewrites the header** --
a wider target line, a burst -- is declared in `augments=` as
`dsl.Augment`, which settles the spend above targeting and offers each
affordable form as its own entry in the action menu."""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
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
    AdjacencyGained,
    AdjacencyLost,
    AreaBurst,
    Attack,
    AttackRolled,
    Augment,
    Cast,
    DamageType,
    Effect,
    Keyword,
    MoveEnd,
    Position,
    Ranged,
    Target,
    TurnStart,
    UpTo,
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
    augments=(
        Augment(1),
        Augment(2, reach=AreaBurst(1, 10), target=EACH_CREATURE),
    ),
)
def p11275(c: Cast) -> None:
    """The zone is the target's own square on the two cheaper forms.
    "Starts its turn adjacent to it" is dropped -- widening the zone to the
    ring would also make entering the ring burn, which the printed line
    does not say. Augment 1 makes that one square totally obscured.

    Augment 2 is an area burst against each creature in it, which is the
    header, so it is declared there -- and with the burst declared, its
    zone is the whole burst rather than one square, its dice are doubled,
    and the obscuring comes with it. The zone is laid once for the use
    rather than once per creature caught, which is what `c.first` is for.
    """
    spent = augment(c, 1, 2)
    where = c.there
    if c.strike():
        c.damage("2d6" if spent == 2 else "1d6", c.int_mod, dtype=DamageType.FIRE)
    if spent == 2:
        if c.first:
            c.hazard(
                c.area(), c.wis_mod, DamageType.FIRE, until=When.EONT,
                sustain=None, blocks_sight=True,
            )
        return
    c.hazard(
        {where}, c.wis_mod, DamageType.FIRE, until=When.EONT, sustain=None,
        blocks_sight=spent == 1,
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
    """Augment 1 roots the target as well. Augment 2 raises the dice and knocks
    it prone *instead of* slowing it -- its Hit line is written out in full
    rather than "as above", so the slow is not in it."""
    spent = augment(c)
    if c.strike():
        c.damage("1d8" if spent == 2 else "1d6", c.int_mod, dtype=DamageType.FORCE)
        if spent == 2:
            c.prone()
            return
        c.slowed(until=When.EONT)
        if spent:
            c.cannot_shift(until=When.EONT)


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
    """"The next saving throw it makes" is `once=True` on the penalty. Both
    augments add the attack penalty; Augment 2 also raises the dice and drops
    the `once`, because it penalises saving throws outright rather than one."""
    spent = augment(c)
    if c.strike():
        c.damage("2d8" if spent == 2 else "1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty("save", 2, until=When.EONT, once=spent != 2)
        if spent:
            c.penalty("attack", 2, until=When.EONT)


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
    dropped=("c.confine(to=)",),
)
def p13318(c: Cast) -> None:
    """"Moves more than 2 squares" is measured from where it stood when its
    turn began, so the square it started in has to be caught on `TurnStart`;
    `MoveEnd` alone only says where it stopped.

    Augment 1 is written now. It was dropped as a modifier scoped to an
    aura, which `c.grants_in` does -- but an aura 1 includes the square at
    its centre, so the target would have taken its own penalty. Adjacency
    is the printed word and `AdjacencyGained`/`AdjacencyLost` are the two
    events for it, so the penalty is laid and lifted as enemies close on
    the target and leave it. Augment 1's **fear keyword** is what is
    dropped in its place: it is a header field and nothing adds one for
    one use.

    Augment 2 is a **secondary** attack, and that is why it stays in the
    body rather than being declared in the header: the primary target line
    is unchanged, so nothing about the targeting of this row moves. The
    burst is centred on the primary target and rolled against Reflex, which
    is a second attack line the body makes for itself.

    Augment 2's mutual leash -- neither end may move to a square that is
    not adjacent to the other -- is still dropped, the same hold `p13041`
    names: nothing constrains where a creature may walk."""
    spent = augment(c, 1, 2)
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.int_mod)
    if spent == 1 and victim is not None:
        held: dict[int, Effect] = {}

        def pinch(who: int) -> None:
            if who == victim or who in held or who not in c.enemies():
                return
            bitten = c.penalty("attack", 2, on=who, until=When.EONT)
            if bitten is not None:
                held[who] = bitten

        def closed(ev: AdjacencyGained) -> None:
            if ev.other == victim:
                pinch(ev.actor)

        def opened(ev: AdjacencyLost) -> None:
            if ev.other == victim and ev.actor in held:
                c.end_effect(held.pop(ev.actor))

        for foe in c.within(1, of=victim, side="enemy"):
            pinch(foe)
        c.watch(AdjacencyGained, closed, until=When.EONT, on=c.me,
                label=f"{c.ref} ring")
        c.watch(AdjacencyLost, opened, until=When.EONT, on=c.me,
                label=f"{c.ref} ring")
    if spent == 2 and victim is not None:
        # The secondary is its own attack line -- Intelligence vs. Reflex
        # where the primary rolled against Fortitude -- so its bonus is
        # asked of that line rather than reassembled by hand.
        secondary = Attack(INT, vs=REF)
        bonus = secondary.bonus_for(c.world, c.me, c.ref, c.branch)
        for other in c.within(1, of=victim, side="enemy"):
            if other != victim and c.attack(bonus, REF, on=other).hit:
                c.flat(5 + c.int_mod, on=other)
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
    augments=(
        Augment(1),
        Augment(2, target=UpTo(3)),
    ),
)
def p13319(c: Cast) -> None:
    """Augment 1 trips the target on any move that is not a shift, which is
    `MoveEnd.kind_` and nothing else; a shove is left out of it too, since a
    creature that is pushed has not *made* a move.

    Augment 2 is a target line -- up to three creatures -- and a target line
    is read before the body is called, so it is declared in the header. It
    prints no Hit line of its own, so each of the three takes the base one:
    the half-speed trip, not Augment 1's wider one."""
    spent = augment(c, 1, 2) == 1
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
        if ev.actor != victim or start is None:
            return
        moved = ev.kind_ not in ("shift", "forced")
        if moved if spent else distance(start, ev.at) > far:
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
    is the second block, `p13320b`, and Augment 2 is that block's Hit line.
    Augment 1 is on this block: the anomaly becomes something your allies can
    flank with, which is the modifier `query.flankers` reads."""
    spent = augment(c, 1)
    anomaly = c.conjure(until=When.EONT, sustain=None)
    if anomaly and spent:
        c.can_flank(on=anomaly, until=When.EONT)


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
    no slide is needed. Both augments add Charisma to the free swing's damage;
    Augment 2 slides by Charisma rather than 1 square and dazes the target."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    shove = c.cha_mod if spent == 2 else 1
    beside = [e for e in c.within(1, of=victim, side="enemy") if e != victim]
    foe = beside[0] if beside else None
    if foe is None:
        for cand in c.enemies():
            if cand == victim:
                continue
            pos = c.world.get(cand, Position)
            if pos is None:
                continue
            spots = sorted(spread({pos.square}, 1))
            if any(c.slide(shove, on=victim, to=sq) for sq in spots):
                foe = cand
                break
    if foe is not None:
        c.grant_attack(
            victim, on=foe, attack_bonus=c.cha_mod,
            damage_bonus=c.cha_mod if spent else 0,
        )
    if spent == 2:
        c.dazed(until=When.EONT)


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
    """Augment 1 makes the penalty Charisma rather than 2. Augment 2 drops the
    penalty entirely and pays out on the *next* attack that hits the target's
    Fortitude -- read off `AttackRolled`, which is the only event carrying
    which defence was attacked, and `once` because the clause says one."""
    spent = augment(c)
    victim = c.target
    if not c.strike():
        return
    c.damage("2d8" if spent == 2 else "1d6", c.int_mod, dtype=DamageType.PSYCHIC)
    if spent < 2:
        c.penalty(FORT, c.cha_mod if spent else 2, until=When.EONT)
        return

    def bit(ev: AttackRolled) -> None:
        if ev.target == victim and ev.vs is FORT and ev.total >= ev.defence:
            c.flat(c.cha_mod, on=victim)

    c.watch(AttackRolled, bit, until=When.EONT, on=victim, once=True, label=c.ref)
