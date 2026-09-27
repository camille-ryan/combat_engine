"""Psion, level 3. Each row buys its augment with `augment`; a clause that
rewrites the header -- a wider target line, a burst -- is named in the row's
docstring and recorded in `docs/blocked.json` instead."""

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
    AreaBurst,
    Attack,
    AttackRolled,
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
    ring burn, which the printed line does not say. Augment 1 makes the zone
    totally obscured. Augment 2 is an area burst and is left out."""
    spent = augment(c, 1)
    where = c.there
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FIRE)
    c.hazard(
        {where}, c.wis_mod, DamageType.FIRE, until=When.EONT, sustain=None,
        blocks_sight=bool(spent),
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
            c.rooted(until=When.EONT)


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
)
def p13318(c: Cast) -> None:
    """"Moves more than 2 squares" is measured from where it stood when its
    turn began, so the square it started in has to be caught on `TurnStart`;
    `MoveEnd` alone only says where it stopped.

    Neither augment is written. Augment 1 penalises the attack rolls of
    enemies *while they stand next to the target*, and nothing scopes a
    modifier to a zone or an aura -- the four that exist are resistance,
    cover, granting advantage and difficult terrain. Augment 2 is a second
    attack against a burst centred on the target, with a target line of its
    own, and then pins both ends to each other's squares."""
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
    """Augment 1 trips the target on any move that is not a shift, which is
    `MoveEnd.kind_` and nothing else; a shove is left out of it too, since a
    creature that is pushed has not *made* a move. Augment 2 widens the target
    line to three creatures and is left out."""
    spent = augment(c, 1)
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
    is `p13320b`, which is left out: its reach is measured from the anomaly
    and a range is measured from the caster, so the row would be refused in
    exactly the situation it is printed for. Augment 2 is that block's Hit
    line and goes with it. Augment 1 is on this block: the anomaly becomes
    something your allies can flank with, which is the modifier
    `query.flankers` reads."""
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
