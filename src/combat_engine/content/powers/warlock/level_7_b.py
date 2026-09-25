"""Warlock, level 7: the encounter attacks from the books after the first.

The class's two settled readings hold throughout: `c.build` answers the
`infernal` and `fey` legs and every other pact rider is named in a comment
and left out, and a line printing two damage types at once is one amount
under the first of them with both keywords declared.

Three shapes are particular to this level.

**Two attack rolls resolved as one hit** is two `c.strike()` calls and one
damage line chosen by how many landed. That is two `AttackDeclared` events
where the card means one attack, which is the price of there being no way
to roll a die twice and keep one outcome.

**"The target makes a basic attack, and if it misses ..."** needs to know
how the granted swing went, and `c.grant_attack` answers only whether it was
taken -- so `_missed_after` catches the `Miss` off the bus for the length of
the call, as `level_1_c.py` does.

**Two magic items are named as Requirements** -- a particular blade, a
particular sword. `Weapon` carries damage, reach and a group and nothing
that could be one named item, so those two rows declare no `requires` and
say so, the way `level_1.py`'s pact prerequisites already do.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    CON,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    Condition,
    DamageApplied,
    DamageType,
    Event,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    Ranged,
    Target,
    Trigger,
    UpTo,
    When,
    World,
    power,
    targets_me,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

_ATTACKED_ME = "an enemy attacks you"
_ADJACENT_ATTACKED_ME = "an adjacent enemy attacks you"


def _adjacent_attacker(world: World, me: int, ev: Event) -> bool:
    from combat_engine.engine.query import distance_between

    foe = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and foe is not None
        and distance_between(world, foe, me) <= 1
    )


def _missed_after(c: Cast, who: int, mark: int) -> bool:
    """Hand `who` a basic attack at `mark` and say whether it missed.

    `c.grant_attack` answers whether the swing was taken, which is a
    different question -- so the `Miss` is watched for over the one call.
    """
    missed = [False]

    def note(ev: Miss) -> None:
        if ev.attacker == who:
            missed[0] = True

    sub = c.world.bus.on(Miss, note)
    try:
        c.grant_attack(who, on=mark)
    finally:
        c.world.bus.off(sub)
    return missed[0]


@power(
    "p12310",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.HEALING],
    attack=Attack(CHA, vs=REF),
)
def p12310(c: Cast) -> None:
    """Two rolls, one hit, and the dice grow if both land.

    The secondary follows a miss. The spec's Miss line names only the
    healing, but the two rows printed beside this one in the same book --
    `p12308` and `p12309` -- both hang their secondary off the miss, and a
    secondary with no trigger at all could never be reached.
    """
    victim = c.target
    landed = sum(1 for _ in range(2) if c.strike())
    if landed:
        c.damage("2d10" if landed == 2 else "1d10", c.cha_mod, dtype=DamageType.FIRE)
        c.heal(c.int_mod, on=c.me)
        if c.build("infernal"):
            c.heal(c.cha_mod, on=c.me)
        return
    c.heal(c.cha_mod, on=c.me)
    pool = sorted(e for e in c.enemies() if e != victim and c.distance(e) <= 10)
    second = c.choose(pool, f"{c.ref}: who the flames find") if pool else None
    if second is None:
        return
    again = sum(1 for _ in range(2) if c.attack(c.cha_, REF, on=second))
    if again:
        c.half_damage(
            "2d10" if again == 2 else "1d10",
            c.cha_mod,
            dtype=DamageType.FIRE,
            on=second,
        )
        c.heal(c.int_mod, on=c.me)


@power(
    "p12894",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=REF),
)
def p12894(c: Cast) -> None:
    """Both branches roll the same line, so no `attack_alt` is declared. The
    sorcerer-king rider has no leg to ask for."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.LIGHTNING)
    shove = max(0, c.int_mod)
    # The neighbours are read before the target moves: a push that opens a
    # gap would otherwise spare whoever was standing there.
    beside = [f for f in c.within(1, of=victim, side="enemy") if f != victim]
    c.push(shove)
    for foe in beside:
        c.push(shove, on=foe)


@power(
    "p13449",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(CHA, vs=WILL),
)
def p13449(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.slide(2)  # an Effect line, taken before the attack as printed
    if not c.strike():
        return
    c.damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC)
    near = sorted(f for f in c.within(1, of=victim, side="enemy") if f != victim)
    mark = c.choose(near, f"{c.ref}: who it swings at") if near else None
    if mark is not None and _missed_after(c, victim, mark):
        c.damage("1d6", dtype=DamageType.PSYCHIC)


@power(
    "p13672",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.COLD,
        Keyword.PSYCHIC,
        Keyword.TELEPORTATION,
    ],
    trigger=_ATTACKED_ME,
    on=Trigger(AttackDeclared, when=targets_me, text=_ATTACKED_ME),
)
def p13672(c: Cast) -> None:
    """The printed Requirement names one particular weapon, and `Weapon`
    carries a group and a damage die and nothing that could be a named
    item -- so no `requires` is declared."""
    c.flat(5 + c.cha_mod, dtype=DamageType.COLD)
    c.teleport(max(1, c.dex_mod))


@power(
    "p13752",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.PSYCHIC, Keyword.RADIANT],
    trigger=_ADJACENT_ATTACKED_ME,
    on=Trigger(AttackDeclared, when=_adjacent_attacker, text=_ADJACENT_ATTACKED_ME),
)
def p13752(c: Cast) -> None:
    """Its Requirement names one particular sword; see `p13672`."""
    c.flat(5 + c.cha_mod, dtype=DamageType.PSYCHIC)
    c.insubstantial(on=c.me, until=When.SONT)
    c.shift(1)


@power(
    "p13906",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=FORT),
)
def p13906(c: Cast) -> None:
    # The gloom pact rider has no leg to ask for.
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
        c.blinded()


@power(
    "p13916",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(CHA, vs=FORT),
)
def p13916(c: Cast) -> None:
    # The star pact rider -- a slide and a splash at the start of your next
    # turn -- has no leg to ask for.
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.COLD)


@power(
    "p15904",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=REF),
)
def p15904(c: Cast) -> None:
    """"If you hit both targets" needs the body to remember across its calls,
    and it is called once per target with nothing carried between -- so each
    creature hit is given a named hold and `c.suffering` reads them back on
    the last call. The star pact rider has no leg to ask for.
    """
    if c.strike():
        c.damage("2d6", c.con_mod, dtype=DamageType.COLD)
        c.effect(f"{c.ref} rimed", until=When.EOT)
    if not c.last:
        return
    caught = c.suffering(f"{c.ref} rimed")
    if len(caught) == 2 and c.may("trade the two of them about", who=c.me):
        c.swap(caught[1], who=caught[0])


@power(
    "p15905",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CON, vs=FORT),
)
def p15905(c: Cast) -> None:
    # The star pact rider is the whole of this row's zone, so with no leg to
    # ask for there is no zone and no Zone keyword.
    if c.target is not None and c.strike():
        c.damage("2d8", c.con_mod, dtype=DamageType.ACID)


@power(
    "p16352",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
    trigger=_ADJACENT_ATTACKED_ME,
    on=Trigger(AttackDeclared, when=_adjacent_attacker, text=_ADJACENT_ATTACKED_ME),
)
def p16352(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EOTNT)
        if c.build("fey"):
            c.flat(3 + c.int_mod, dtype=DamageType.PSYCHIC)


@power(
    "p1871",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=REF, plus=2),
)
def p1871(c: Cast) -> None:
    """The extra die is rolled when it is promised rather than when it is
    paid: a modifier holds a number, not an expression. The dark pact rider
    -- the same reward for merely bloodying -- has no leg to ask for."""
    from combat_engine.engine import Health

    victim = c.target
    if not c.strike():
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.NECROTIC)
    hp = c.world.get(victim, Health) if victim is not None else None
    if hp is not None and hp.hp <= 0:
        c.bonus("damage", c.roll("1d8"), on=c.me, until=When.EONT, once=True)


@power(
    "p1872",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p1872(c: Cast) -> None:
    """"An undead target cannot move closer to you" is the clause with no
    method: `c.immovable` is about being shoved and `c.rooted` about
    shifting, and neither forbids walking towards somebody."""
    if c.strike():
        c.damage("1d12", c.cha_mod, dtype=DamageType.NECROTIC)
        c.dazed(until=When.EOTNT)


@power(
    "p4093",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p4093(c: Cast) -> None:
    # The star pact rider has no leg to ask for.
    if c.target is not None and c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.dazed()


@power(
    "p4094",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CON, vs=REF),
)
def p4094(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d6", c.con_mod, dtype=DamageType.ACID)
    c.blinded()
    if c.build("infernal"):
        for foe in c.within(1, of=victim, side="enemy"):
            if foe != victim:
                c.flat(c.int_mod, dtype=DamageType.ACID, on=foe)


@power(
    "p4095",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=REF),
)
def p4095(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("2d8", c.cha_mod)
    dose = c.int_mod * (2 if c.build("fey") else 1)
    if dose <= 0:
        return
    spent = [False]

    def seep(ev: DamageApplied) -> None:
        if spent[0] or ev.target != victim or ev.amount <= 0:
            return
        spent[0] = True
        c.flat(dose, dtype=DamageType.POISON, on=victim)

    c.watch(DamageApplied, seep, until=When.EONT)


@power(
    "p4097",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p4097(c: Cast) -> None:
    # The dark pact rider -- damage every time it swings -- has no leg.
    if c.strike():
        c.damage("2d8", c.cha_mod)
        c.penalty("attack", 2)


@power(
    "p4177",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.HEALING],
    attack=Attack(CON, vs=REF),
)
def p4177(c: Cast) -> None:
    """A creature's "adjacent allies", read from this side of the board, are
    the ones on my own side standing next to it. The vestige pact rider
    would heal all of them instead of one."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("2d8", c.con_mod)
    near = sorted(f for f in c.within(1, of=victim, side="ally") if f != c.me)
    friend = c.choose(near, f"{c.ref}: who is mended") if near else None
    if friend is not None:
        c.heal(c.int_mod, on=friend)


@power(
    "p4285",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p4285(c: Cast) -> None:
    """"Spends its next standard action swinging at nothing" is a standard
    action gone, which is `Condition.SHAPED` -- the one card in the table
    that means exactly that. The star pact rider has no leg to ask for."""
    if c.strike():
        c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.condition(Condition.SHAPED, until=When.EOTNT)


@power(
    "p4286",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    # "The enemy closest to you" cannot be asked of a target line, so the
    # restriction is written down and any one enemy may be aimed at.
    target=Target("enemy", 1, label="One enemy closest to you"),
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=REF),
)
def p4286(c: Cast) -> None:
    # The star pact rider would double the range.
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.NECROTIC)
        c.pull(max(0, c.cha_mod))


@power(
    "p5919",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID, Keyword.NECROTIC],
    attack=Attack(CON, vs=FORT),
)
def p5919(c: Cast) -> None:
    # The vestige pact rider has no leg to ask for.
    if c.strike():
        c.damage("1d12", c.con_mod, dtype=DamageType.ACID)


@power(
    "p7437",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p7437(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.COLD)
        c.slowed(until=When.SAVE_ENDS)
        if c.build("fey"):
            c.push(1 + max(0, c.int_mod))
