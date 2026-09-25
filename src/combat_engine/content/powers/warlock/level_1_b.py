"""Warlock, level 1: the rows from the books after the first, part one.

Four things recur across this batch and the next, and are settled here once.

**Pacts.** `chargen.BUILDS["warlock"]` carries two legs, `infernal` and
`fey`, and `c.build` answers those. A rider printed for the star, dark,
vestige, sorcerer-king, gloom or elemental pact has no leg to ask for, so
the base row is written in full and the rider is named in a comment rather
than guessed at or handed to everybody. A row whose *whole* content is such
a pact is absent -- see the report.

**Two damage types at once** -- "necrotic and psychic" -- is one amount in
the printed rules and `c.damage` carries one `dtype`, so the first named
type is dealt and both keywords are declared.

**"You do not expend this power"** has no method: nothing refunds a use. The
rest of such a line is written and the refund is left out.

**"Charisma or Constitution"** is fixed once at first level and a header
holds one ability, so the Charisma line is the one written, as `level_1.py`
already does for `p1333`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    CON,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    MeleeOrRanged,
    Ranged,
    UpTo,
    When,
    ZoneEntered,
    power,
    spread,
)
from combat_engine.engine.events import MoveEnd
from combat_engine.engine.query import squares as squares_of

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _backlash(c: Cast) -> None:
    """The Miss line three of these share: pay psychic damage for a bonus.

    "You do not expend this power" is the half that cannot be said -- no
    method gives a use back -- so what is written is the price and the
    bonus it buys against the same target.
    """
    if not c.may("take the backlash", who=c.me):
        return
    c.flat(5 + c.level // 2, dtype=DamageType.PSYCHIC, on=c.me)
    c.bonus("attack", 4, on=c.me, kind="power", until=When.EONT, once=True)


@power(
    "p10378",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
)
def p10378(c: Cast) -> None:
    """Losing every resistance and immunity is a named hold and nothing more.

    Nothing suppresses a creature's resistances, so the save-ends effect is
    applied for its own sake: it can be seen, it can be saved against, and
    it is what the Infernal Pact's penalty to the first save attaches to.
    """
    if c.strike():
        c.damage("3d10", c.con_mod, dtype=DamageType.PSYCHIC)
        c.effect(f"{c.ref}: resistances and immunities suppressed")
        if c.build("infernal"):
            c.penalty("save", 2, once=True)
    else:
        _backlash(c)


@power(
    "p10379",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CON, vs=WILL),
)
def p10379(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        _backlash(c)
        return
    c.damage("3d10", c.con_mod, dtype=DamageType.PSYCHIC)
    caught = {victim}
    if victim is not None:
        caught |= {f for f in c.within(1, of=victim, side="enemy")}
    if c.build("infernal"):
        caught |= set(c.within(2, side="enemy"))
    for foe in sorted(f for f in caught if f is not None):
        c.penalty("attack", 2, kind="power", on=foe)


@power(
    "p11303",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=REF),
)
def p11303(c: Cast) -> None:
    """The Thaxter pact boon is dropped: no such leg in the class's builds."""
    if c.int_mod > 0 and c.may("step", who=c.me):
        c.shift(c.int_mod)  # "before or after"; before is what a body can take
    if c.strike():
        c.damage("3d6", c.con_mod)
    else:
        c.half_damage("3d6", c.con_mod)


@power(
    "p12307",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p12307(c: Cast) -> None:
    """"Reroll the attack roll" on your own miss is written as a second swing.

    `c.reroll_attack` reads the roll off `c.trigger`, and a row fired as an
    action is handed no event, so it would silently do nothing. One more
    strike at the same target, taken once and paid for the same way, is the
    same outcome by a different road.
    """
    if c.strike():
        c.damage("1d10", c.cha_mod)
        return
    if not c.may("pay for a second shot", who=c.me):
        return
    c.flat(c.level, on=c.me)
    if c.strike():
        c.damage("1d10", c.cha_mod)


@power(
    "p12308",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=FORT),
)
def p12308(c: Cast) -> None:
    """"Cannot willingly move closer to you" is the clause with no method.

    `c.immovable` is about being shoved and `c.rooted` about shifting;
    neither forbids a creature walking towards somebody. It is left out of
    the primary and the secondary alike rather than approximated.
    """
    victim = c.target
    if c.strike():
        c.damage("2d10", c.cha_mod)
        if c.build("infernal"):
            c.resist(2 + c.int_mod, on=c.me, until=When.EONT)
        return
    c.flat(c.level, on=c.me)
    pool = sorted(e for e in c.enemies() if e != victim and c.distance(e) <= 10)
    second = c.choose(pool, f"{c.ref}: who the backlash finds") if pool else None
    if second is not None and c.attack(c.cha_, FORT, on=second):
        c.half_damage("2d10", c.cha_mod, on=second)


@power(
    "p12887",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=FORT),
)
def p12887(c: Cast) -> None:
    """Both branches roll the same line, so no `attack_alt` is declared."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.NECROTIC)
        c.grants_advantage(to="allies")
    # The sorcerer-king rider -- spend your fell might for 1d8 more -- has
    # no build to ask for.


@power(
    "p12888",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=FORT),
)
def p12888(c: Cast) -> None:
    """The bonus is the allies' and is spent only on this one creature, so it
    is a gated modifier held by each of them rather than anything on the
    target. The sorcerer-king rider that doubles it is dropped."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("2d6", c.cha_mod, dtype=DamageType.RADIANT)
    for friend in c.allies():
        c.bonus(
            "attack",
            1,
            on=friend,
            kind="power",
            until=When.EONT,
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )


@power(
    "p12889",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(CHA, vs=FORT),
)
def p12889(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
        c.grants_advantage(to="allies", until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.NECROTIC)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
    c.pull(2)  # an Effect line: it lands either way


@power(
    "p13634",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=REF),
)
def p13634(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.FORCE)


@power(
    "p13635",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p13635(c: Cast) -> None:
    if c.target is not None:
        if c.strike():
            c.damage("2d6", c.cha_mod, dtype=DamageType.COLD)
            c.slowed(until=When.SAVE_ENDS)
        else:
            c.half_damage("2d6", c.cha_mod, dtype=DamageType.COLD)
    if c.last:
        # The Effect line lands whether the burst caught anybody or not,
        # which is why it hangs off the last call rather than the first hit.
        c.bonus(AC, 2, on=c.me, kind="power", until=When.ENCOUNTER)
        c.bonus(FORT, 2, on=c.me, kind="power", until=When.ENCOUNTER)


@power(
    "p13636",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p13636(c: Cast) -> None:
    if c.target is None:
        return
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.FIRE)


@power(
    "p13637",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p13637(c: Cast) -> None:
    """"If you miss every target the power is not expended" is the refund
    nothing here can give back, so only the attack half is written."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    near = sorted(w for w in c.within(1, of=victim) if w != victim)
    mark = c.choose(near, f"{c.ref}: who it turns on") if near else None
    if mark is not None:
        c.grant_attack(victim, on=mark)


@power(
    "p13877",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p13877(c: Cast) -> None:
    """The bite is an Effect line, so it is armed on a miss as well.

    "Your Dexterity modifier or Intelligence modifier" is the pact's
    secondary either way; Dexterity is the one written, and neither leg the
    class carries uses it, so this is the smaller of the two.
    """
    victim = c.target
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.COLD)
    if victim is None:
        return
    bitten = [False]

    def stepped(ev: MoveEnd) -> None:
        if bitten[0] or ev.actor != victim or c.turn_of() != victim:
            return
        bitten[0] = True
        c.flat(2 + c.dex_mod, dtype=DamageType.COLD, on=victim)

    c.watch(MoveEnd, stepped, until=When.EOTNT)


@power(
    "p13878",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=WILL),
)
def p13878(c: Cast) -> None:
    """The second way out -- a move action and an opposed check against you
    -- is not written: no check is rolled here and nothing spends a target's
    action to end an effect. The saving throw remains."""
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.FORCE)
        c.ongoing(5, DamageType.FORCE)


@power(
    "p13879",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(CHA, vs=REF),
)
def p13879(c: Cast) -> None:
    """"Willingly enters" cannot be told from being shoved in: `ZoneEntered`
    says who arrived and not why, so everything that walks in is caught."""
    if c.target is not None:
        if c.strike():
            c.damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
            c.immobilized(until=When.SAVE_ENDS)
        else:
            c.half_damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
            c.slowed(until=When.SAVE_ENDS)
    if not c.last:
        return
    area = c.area()
    if not area:
        return
    mire = c.zone(area, label=c.ref, until=When.ENCOUNTER)

    def caught(ev: ZoneEntered) -> None:
        if ev.zone == mire:
            c.immobilized(on=ev.actor, until=When.EOTNT)

    c.watch(ZoneEntered, caught, until=When.ENCOUNTER)


@power(
    "p13902",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p13902(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.push(2)


@power(
    "p13904",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p13904(c: Cast) -> None:
    # The gloom pact rider -- psychic damage if it stays put -- has no leg.
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.push(2)


@power(
    "p13914",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=REF),
)
def p13914(c: Cast) -> None:
    # The star pact rider -- the burst also leaves difficult ground -- has
    # no leg, so the row leaves no zone and carries no Zone keyword.
    if c.target is not None and c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.COLD)
        c.slowed()


@power(
    "p13952",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.COLD,
        Keyword.NECROTIC,
        Keyword.CONJURATION,
    ],
    attack=Attack(CHA, vs=REF),
)
def p13952(c: Cast) -> None:
    """The shadow stands next to the target and opens up whoever is beside it.

    Only the enemies standing there when it arrives are opened up: the
    printed line is a standing property of the square, and re-reading who is
    adjacent each round would need a hold on the conjuration that
    `c.conjure` does not hand back. The secondary attack printed under it
    has no ref of its own in the spec and so is not written.
    """
    victim = c.target
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.COLD)
    if victim is None:
        return
    room = sorted(
        sq
        for sq in spread(squares_of(c.world, victim), 1)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if not room:
        return
    shade = c.conjure(at=room[0], label=c.ref, until=When.SUSTAIN, aura=1)
    for foe in c.enemies():
        if c.adjacent_to(shade, foe):
            c.grants_advantage(on=foe, until=When.EONT)


@power(
    "p15902",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
)
def p15902(c: Cast) -> None:
    # The star pact rider -- advantage and a slow -- has no leg to ask for.
    if c.strike():
        c.damage("2d6", c.con_mod, dtype=DamageType.PSYCHIC)


@power(
    "p16256",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=REF),
)
def p16256(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    # "One creature within 5 squares of the target" -- anybody, including
    # the target itself, which is what the line allows.
    near = sorted(c.within(5, of=victim))
    splash = c.choose(near, f"{c.ref}: who the echo finds") if near else None
    if splash is not None:
        c.flat(c.con_mod, dtype=DamageType.PSYCHIC, on=splash)


@power(
    "p16261",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID, Keyword.ZONE],
    attack=Attack(CHA, vs=FORT),
)
def p16261(c: Cast) -> None:
    """The zone's bite is `c.burns`, which catches a creature entering as
    well as one starting its turn there; the printed line is "ends its
    turn", and that is the nearest the zone model comes.

    Sustaining rolls a d6 to grow or shrink the pool by a square. A zone's
    area is fixed once made, so sustaining simply keeps it.
    """
    if c.target is not None:
        if c.strike():
            c.damage("2d6", c.cha_mod, dtype=DamageType.ACID)
            c.ongoing(5, DamageType.ACID)
        else:
            c.half_damage("2d6", c.cha_mod, dtype=DamageType.ACID)
    if not c.last:
        return
    area = c.area()
    if area:
        pool = c.zone(area, label=c.ref, until=When.SUSTAIN, difficult=True)
        c.burns(pool, 5, DamageType.ACID)


@power(
    "p16350",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=REF),
)
def p16350(c: Cast) -> None:
    if c.target is not None and c.strike():
        c.damage("1d6", c.cha_mod)
        if c.build("fey"):
            c.flat(c.int_mod, dtype=DamageType.POISON)
