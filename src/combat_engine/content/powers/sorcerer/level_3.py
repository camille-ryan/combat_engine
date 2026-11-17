"""Sorcerer, level 3: encounter attacks.

Nothing new in shape. Two notes that apply to the whole level:

**"Cold and lightning damage"** is dealt as the first printed type and the
second rides in the keywords -- one packet carries one `DamageType`.

**Fork riders** (Dragon Magic, Wild Magic, Storm Magic, Chaos Sorcerer) are
dropped, each named where it falls; see `level_1.py` for why.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    EACH_CREATURE,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    UpTo,
    When,
    distance,
    power,
    spread,
)

from . import wild_even
from .ground import ringing
from .knives import dagger

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p10320",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=FORT),
)
def p10320(c: Cast) -> None:
    """"It must be teleported that many squares away from its original
    location" is a distance the destination has to hit exactly, so the
    square is named rather than left to `c.teleport`'s own offer -- which
    takes anything within the range.

    **The Chaos Sorcerer clause is written now** -- choosing d4, d6 or d8
    -- and "goes with the fork" was the premise `#1303` refuted for `wild`: a missing class-feature
    row read as a missing build. `BUILDS["sorcerer"]` carries all four
    sources, and the printed ref maps to its leg off its own spec text.
    #1351. Chaos Sorcerer is the `wild` leg,
    which is the one `#1303` already proved `c.build` answers.

    The choice is made **before** the roll and replaces which die is
    rolled, not its result: "you can choose to roll a d4, a d6, or a d8"
    is about the die, and a chosen distance would be a different card.
    """
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod)

    die = "1d6"
    if c.build("wild"):
        die = c.choose(["1d4", "1d6", "1d8"], f"{c.ref}: which die") or "1d6"
    far = c.roll(die)
    was = c.there
    room = sorted(
        sq
        for sq in spread({was}, far)
        if distance(sq, was) == far
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) in (None, victim)
    )
    where = c.choose(room, f"{c.ref}: where it comes out") if room else None
    if where is not None:
        c.teleport(far, who=victim, to=where)

    for near in c.within(1, of=victim, side="any"):
        if near != victim:
            c.flat(5, dtype=DamageType.THUNDER, on=near)


@power(
    "p12469",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p12469(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
        c.slowed()


@power(
    "p13427",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13427(c: Cast) -> None:
    """No ability modifier on the damage line, which is what the card
    prints for a minor action."""
    if c.strike():
        c.damage(c.w(2), dtype=DamageType.LIGHTNING)


@power(
    "p16511",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p16511(c: Cast) -> None:
    """No ability modifier on the damage line, as printed."""
    if c.strike():
        c.damage("2d10", dtype=DamageType.COLD)
        c.push(1)
        c.prone()


@power(
    "p3010",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CHA, vs=FORT),
)
def p3010(c: Cast) -> None:
    """The second bite is hung off the target's own next turn start rather
    than dealt now.

    **The Dragon Magic splash is written now**, and "goes with the fork"
    was the premise `#1303` refuted for `wild`: a missing class-feature
    row read as a missing build. `BUILDS["sorcerer"]` carries all four
    sources, and the printed ref maps to its leg off its own spec text.
    #1351.

    It lands on the neighbours **now** rather than with the delayed bite:
    the printed clause is a rider on the Hit line, and the target's
    neighbours a turn later are not the ones the card names.
    """
    victim = c.target
    if not c.strike():
        return
    c.damage("2d10", c.cha_mod, dtype=DamageType.ACID)
    bite = c.str_mod

    def later(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == victim:
            c.flat(bite, dtype=DamageType.ACID, on=victim)

    c.watch(TurnStart, later, until=When.EOTNT, on=victim, once=True, label=c.ref)
    if c.build("dragon"):
        for near in c.within(1, of=victim):
            if near != victim:
                c.flat(
                    max(0, c.str_mod),
                    dtype=DamageType.ACID,
                    on=near,
                    from_attack=False,
                )


@power(
    "p3012",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p3012(c: Cast) -> None:
    """**The Storm Magic clause is written now** -- a flight bought by
    declining every slide -- and "goes with the fork" was the premise
    `#1303` refuted for `wild`: a missing class-feature row read as a
    missing build. `BUILDS["sorcerer"]` carries `storm`. #1351.

    "**If you choose not to slide ANY targets**" is the hard part, and it
    is why the slide becomes an offer rather than a certainty on this
    leg: the clause is paid for by declining, so the row has to ask, and
    it has to remember across every creature in the blast. The memo is on
    the `Cast` -- one per use, which is the unit the sentence is about --
    and the flight is granted on `c.last`, when there is nobody left who
    might still be slid.

    **Only on the storm leg is the slide optional.** Off it the card
    prints no choice, so asking would invent one and let any sorcerer
    decline a slide the page makes automatic.

    `c.hover` is both halves at once: it lifts the creature and marks it
    as moving airborne, which is what "a fly speed ... and you can hover"
    needs and what keeps `falling.ground` from setting it back down.
    """
    storm = c.build("storm")
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.THUNDER)
        # One `if`, and `and` short-circuits, so the slide is still only
        # reached when the guard passes -- declining it must not move
        # anybody.
        if (not storm or c.may(f"{c.ref}: slide it", who=c.me)) and c.slide(
            c.dex_mod
        ):
            c.storm_slid = True
    if c.last and storm and not getattr(c, "storm_slid", False):
        c.hover(1 + max(0, c.dex_mod), until=When.EONT)


@power(
    "p3013",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.THUNDER],
    attack=Attack(CHA, vs=REF),
)
def p3013(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.COLD)


@power(
    "p3163",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=REF),
    reads_parity=True,
)
def p3163(c: Cast) -> None:
    """The Wild Magic clause lands now: the target loses **all** resistances
    until the end of your next turn, on an even roll.

    Written as `c.resistances()` read back and each one negated with
    `c.resist`, which is `p8240`'s idiom for the single-type version of the
    same sentence -- its docstring names *"the target loses that
    resistance"* as why `c.resistances` exists. There is no "strip
    everything" verb and this is two lines, so one is not invented for it.

    **Read at the moment of the hit**, which is the limit worth stating: a
    resistance laid *after* this lands is not stripped. That is what the
    printed sentence says literally -- it takes away what the target has --
    and the alternative is a standing waiver, which is a different
    mechanic. See `wild_even`. `#1303`."""
    shot = c.strike()
    if shot:
        c.damage("2d8", c.cha_mod, dtype=DamageType.FORCE)
        if wild_even(c, shot):
            for kind, amount in c.resistances().items():
                if amount > 0:
                    c.resist(-amount, kind, on=c.target, until=When.EONT)


@power(
    "p3174",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p3174(c: Cast) -> None:
    """**"Until the end of your next turn, you have concealment" is written
    now.** The old note said "concealment is not modelled", and `c.conceal`
    has been the verb for it all along -- defaulting to the caster, which
    is what every printed line granting it says. The same note's second
    half was right and is why `c.hide` is not used here: hiding outright is
    a stronger thing than this card prints. #1341.

    Laid once on `c.first` rather than per target. The blast hits each
    creature in it, so the body runs several times, and a second
    `c.conceal` would stack a second -2 the card does not give.
    """
    if c.first:
        c.conceal(on=c.me, until=When.EONT)
    if c.strike():
        c.damage("2d6", c.cha_mod)


@power(
    "p3749",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p3749(c: Cast) -> None:
    """The ring is laid around the sorcerer and stays where it was laid:
    `c.hazard` makes a zone, and a zone does not follow anybody."""
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.FIRE)
    if not c.first:
        return
    ring = ringing(c, c.me)
    if ring:
        c.hazard(
            ring, "1d6", DamageType.FIRE,
            label=c.ref, until=When.SONT, sustain=None,
        )


@power(
    "p3753",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=REF),
)
def p3753(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.COLD)
        c.slowed()


@power(
    "p5269",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(CHA, vs=REF),
)
def p5269(c: Cast) -> None:
    """Two packets of two types, which is the one case where both printed
    types are actually dealt."""
    victim = c.target
    if not c.strike():
        return
    c.damage("2d10", c.cha_mod, dtype=DamageType.LIGHTNING)
    for near in c.within(1, of=victim, side="any"):
        if near != victim:
            c.flat(c.cha_mod, dtype=DamageType.THUNDER, on=near, from_attack=False)


@power(
    "p5270",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p5270(c: Cast) -> None:
    """The Dragon Magic clause -- a bigger penalty off Strength -- goes with
    the fork, so the printed -2 stands."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.POISON)
        c.penalty(FORT, 2)


@power(
    "p5271",
    level=3,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=FORT),
    reads_parity=True,
)
def p5271(c: Cast) -> None:
    """The Wild Magic slide lands now -- by Dexterity, on an even roll, and
    **as well as** the immobilisation rather than instead of it: the clause
    adds a sentence where `p3162`'s replaces one. See `wild_even`. `#1303`."""
    shot = c.strike()
    if shot:
        c.damage("1d8", c.cha_mod, dtype=DamageType.FORCE)
        c.immobilized()
        if wild_even(c, shot):
            c.slide(c.dex_mod)
